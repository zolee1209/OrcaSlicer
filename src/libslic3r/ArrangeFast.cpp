#include "ArrangeFast.hpp"

#include "BoundingBox.hpp"
#include "ClipperUtils.hpp"
#include "ExPolygon.hpp"
#include "Polygon.hpp"
#include "libslic3r.h"

#include <boost/log/trivial.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <vector>

namespace Slic3r { namespace arrangement {

namespace {

using Vec2l = Eigen::Matrix<int64_t, 2, 1>;

// Same limit as the nesting backend (MAX_NUM_PLATES in libnest2d).
constexpr int FAST_MAX_PLATES = 36;
constexpr double FAST_PI = 3.14159265358979323846;

struct Rect
{
    int64_t x0{0}, y0{0}, x1{0}, y1{0};
    int64_t w() const { return x1 - x0; }
    int64_t h() const { return y1 - y0; }
};

inline bool intersects(const Rect &a, const Rect &b) { return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1; }
inline bool contains(const Rect &a, const Rect &b) { return a.x0 <= b.x0 && a.y0 <= b.y0 && a.x1 >= b.x1 && a.y1 >= b.y1; }

// One orientation of a shape: the rotation and the box of the inflated, rotated hull.
struct Orient
{
    double  angle{0.};
    int64_t w{0}, h{0};
    // translation = cell min corner + (offx, offy)
    int64_t offx{0}, offy{0};
};

struct ClassKey
{
    Points             pts;
    int64_t            inflation{0};
    double             rotation{0.};
    std::vector<int>   extruders;

    bool operator<(const ClassKey &o) const
    {
        if (inflation != o.inflation) return inflation < o.inflation;
        if (rotation != o.rotation) return rotation < o.rotation;
        if (extruders != o.extruders) return extruders < o.extruders;
        if (pts.size() != o.pts.size()) return pts.size() < o.pts.size();
        for (size_t i = 0; i < pts.size(); ++i) {
            if (pts[i].x() != o.pts[i].x()) return pts[i].x() < o.pts[i].x();
            if (pts[i].y() != o.pts[i].y()) return pts[i].y() < o.pts[i].y();
        }
        return false;
    }
};

struct ShapeClass
{
    size_t              first_item{0};
    int                 count{0};
    std::vector<Orient> allowed; // orientations the members may use
};

struct Placed
{
    size_t  item;
    int     orient; // index into the class' allowed vector
    Rect    cell;
};

// A plate with the MaxRects free list.
struct Plate
{
    std::vector<Rect>   free_rects;
    std::vector<Rect>   obstacles;
    std::vector<Placed> placed;
    std::set<int>       extruders;              // extruders of the items (and fixed objects) on the plate
    std::optional<Rect> tower;                  // prime tower footprint, taken once the plate is multi-material
    bool                tower_reserved{false};  // the prime tower is among the obstacles
    bool                tower_blocked{false};   // the prime tower overlaps a placed item

    void occupy(const Rect &used)
    {
        std::vector<Rect> out;
        out.reserve(free_rects.size() + 4);
        for (const Rect &fr : free_rects) {
            if (!intersects(fr, used)) {
                out.push_back(fr);
                continue;
            }
            if (used.x0 > fr.x0) out.push_back({fr.x0, fr.y0, used.x0, fr.y1});
            if (used.x1 < fr.x1) out.push_back({used.x1, fr.y0, fr.x1, fr.y1});
            if (used.y0 > fr.y0) out.push_back({fr.x0, fr.y0, fr.x1, used.y0});
            if (used.y1 < fr.y1) out.push_back({fr.x0, used.y1, fr.x1, fr.y1});
        }
        // Remove the rectangles contained in another one (and duplicates).
        std::vector<char> drop(out.size(), 0);
        for (size_t i = 0; i < out.size(); ++i) {
            if (drop[i])
                continue;
            for (size_t j = 0; j < out.size(); ++j) {
                if (i == j || drop[j])
                    continue;
                if (contains(out[j], out[i])) {
                    drop[i] = 1;
                    break;
                }
            }
        }
        free_rects.clear();
        for (size_t i = 0; i < out.size(); ++i)
            if (!drop[i])
                free_rects.push_back(out[i]);
    }

    // Bottom-left position for a box of the given size, false if it does not fit.
    bool find(int64_t w, int64_t h, int64_t &x, int64_t &y) const
    {
        bool    found = false;
        int64_t best_top = 0, best_x = 0;
        for (const Rect &fr : free_rects) {
            if (fr.w() < w || fr.h() < h)
                continue;
            const int64_t top = fr.y0 + h;
            if (!found || top < best_top || (top == best_top && fr.x0 < best_x)) {
                found    = true;
                best_top = top;
                best_x   = fr.x0;
                y        = fr.y0;
            }
        }
        x = best_x;
        return found;
    }
};

Rect to_rect(const BoundingBox &bb) { return {bb.min.x(), bb.min.y(), bb.max.x(), bb.max.y()}; }

// Inflates the (counter clockwise) contour the same way the nesting backend inflates an item.
Polygon inflated_contour(const Polygon &contour, int64_t inflation)
{
    Polygon base = contour;
    if (base.is_clockwise())
        base.reverse();
    if (inflation == 0)
        return base;
    ExPolygons res = offset_ex(ExPolygon(base), float(inflation), jtSquare);
    return res.empty() ? base : res.front().contour;
}

bool orient_of(const Polygon &inflated, double angle, Orient &out)
{
    Polygon p = inflated;
    p.rotate(angle);
    const BoundingBox bb(p.points);
    if (!bb.defined)
        return false;
    out.angle = angle;
    out.w     = bb.max.x() - bb.min.x();
    out.h     = bb.max.y() - bb.min.y();
    out.offx  = -int64_t(bb.min.x());
    out.offy  = -int64_t(bb.min.y());
    return true;
}

} // namespace

bool arrange_fast(ArrangePolygons &items, const ArrangePolygons &excludes, const BoundingBox &bed, const ArrangeParams &params)
{
    using clock = std::chrono::steady_clock;
    const auto t_start = clock::now();

    if (items.empty())
        return true;

    auto unsupported = [](const char *reason) {
        BOOST_LOG_TRIVIAL(info) << "arrange_fast: not supported (" << reason << "), falling back to nesting";
        return false;
    };

    if (params.is_seq_print)
        return unsupported("print sequence is By object");
    if (params.is_belt)
        return unsupported("belt printer (belt order packing)");
    if (!params.allow_multi_materials_on_same_plate)
        return unsupported("multiple materials on the same plate are not allowed");
    if (!bed.defined || bed.size().x() <= 0 || bed.size().y() <= 0)
        return unsupported("invalid bed");
    for (const ArrangePolygon &ap : items)
        if (ap.poly.contour.points.size() < 3)
            return unsupported("degenerated item");

    const Rect    bin{bed.min.x(), bed.min.y(), bed.max.x(), bed.max.y()};
    const int64_t bin_w = bin.w(), bin_h = bin.h();

    // 1. group the items to shape classes
    std::map<ClassKey, int> class_index;
    std::vector<ShapeClass> classes;
    std::vector<int>        item_class(items.size(), -1);
    for (size_t i = 0; i < items.size(); ++i) {
        const ArrangePolygon &ap = items[i];
        ClassKey              key;
        key.pts       = ap.poly.contour.points;
        key.inflation = ap.inflation;
        key.rotation  = ap.rotation;
        key.extruders = ap.extrude_ids;
        auto it = class_index.find(key);
        if (it == class_index.end()) {
            it = class_index.emplace(std::move(key), int(classes.size())).first;
            classes.emplace_back();
            classes.back().first_item = i;
        }
        item_class[i] = it->second;
        ++classes[it->second].count;
    }

    // 2. orientations of every class
    for (ShapeClass &cls : classes) {
        const ArrangePolygon &ap       = items[cls.first_item];
        const Polygon         inflated = inflated_contour(ap.poly.contour, ap.inflation);

        std::vector<Orient> fitting;
        auto                try_angle = [&](double delta) {
            Orient o;
            if (orient_of(inflated, ap.rotation + delta, o) && o.w <= bin_w && o.h <= bin_h)
                fitting.push_back(o);
        };
        try_angle(0.);
        // Align to Y axis: the caller pre-rotated the item, so 90 degrees is only a fallback when 0 does not fit.
        if (params.allow_rotations && !(params.align_to_y_axis && !fitting.empty()))
            try_angle(FAST_PI / 2.);
        if (fitting.empty() && params.allow_rotations) {
            // Neither 0 nor 90 degrees fits: try the diagonal placement (long items) and keep the smaller box.
            try_angle(FAST_PI / 4.);
            try_angle(3. * FAST_PI / 4.);
            if (fitting.size() == 2 && fitting[1].w * fitting[1].h < fitting[0].w * fitting[0].h)
                std::swap(fitting[0], fitting[1]);
            if (!fitting.empty()) {
                fitting.resize(1);
                BOOST_LOG_TRIVIAL(info) << "arrange_fast: item " << ap.name << " does not fit at 0/90 degrees, using the "
                                        << int(std::lround((fitting[0].angle - ap.rotation) * 180. / FAST_PI)) << " degree orientation";
            }
        }
        if (fitting.empty())
            return unsupported("an item does not fit on an empty plate");

        if (cls.count >= 2 && fitting.size() > 1) {
            // Many identical items: one orientation for all of them, the one with the larger grid capacity.
            size_t  best     = 0;
            int64_t best_cap = -1;
            for (size_t k = 0; k < fitting.size(); ++k) {
                const int64_t cap = (bin_w / fitting[k].w) * (bin_h / fitting[k].h);
                if (cap > best_cap) {
                    best_cap = cap;
                    best     = k;
                }
            }
            fitting = {fitting[best]};
        }
        cls.allowed = std::move(fitting);
    }

    // 3. fixed obstacles
    //  - per plate: the fixed items of that plate (unselected objects, virtual regions)
    //  - every plate: params.excluded_regions / nonprefered_regions (the latter conservatively kept free)
    //  - plates the caller did not prepare (overflow): the virtual regions of the first prepared plate
    //  - prime tower: a conditional obstacle. The caller reserves one on every plate when any plate is
    //    multi-material, but a single-material plate prints no tower, so it only takes space once the
    //    plate becomes multi-material (the plate's own tower, else the first plate's tower as template).
    auto to_obstacle = [](const ArrangePolygon &fx, int64_t infl) {
        Polygon p = fx.poly.contour;
        if (p.is_clockwise())
            p.reverse();
        if (infl != 0) {
            ExPolygons res = offset_ex(ExPolygon(p), float(infl), jtSquare);
            if (!res.empty())
                p = res.front().contour;
        }
        p.rotate(fx.rotation);
        p.translate(fx.translation.x(), fx.translation.y());
        return to_rect(BoundingBox(p.points));
    };
    // The nesting backend shrinks fixed items by 2*EPSILON after inflating them.
    const int64_t fixed_shrink = int64_t(scaled(2. * EPSILON));

    struct PlateFixed
    {
        std::vector<Rect>   rects;
        std::set<int>       extruders;
        bool                has_virtual{false};
        std::optional<Rect> tower;
    };
    std::map<int, PlateFixed> fixed;
    std::optional<Rect>       tower_template;
    int                       tower_template_bed   = -1;
    int                       virtual_template_bed = -1;
    std::map<int, std::vector<Rect>> virtual_rects;
    for (const ArrangePolygon &fx : excludes) {
        if (fx.poly.contour.points.size() < 3)
            continue;
        const int  bed_idx = std::max(fx.bed_idx, 0);
        const Rect r       = to_obstacle(fx, int64_t(fx.inflation) - fixed_shrink);
        PlateFixed &pf     = fixed[bed_idx];
        if (fx.is_wipe_tower) {
            pf.tower = r;
            if (tower_template_bed < 0 || bed_idx < tower_template_bed) {
                tower_template     = r;
                tower_template_bed = bed_idx;
            }
            continue;
        }
        pf.rects.push_back(r);
        if (fx.is_virt_object) {
            pf.has_virtual = true;
            virtual_rects[bed_idx].push_back(r);
            if (virtual_template_bed < 0 || bed_idx < virtual_template_bed)
                virtual_template_bed = bed_idx;
        } else {
            pf.extruders.insert(fx.extrude_ids.begin(), fx.extrude_ids.end());
        }
    }
    std::vector<Rect> every_plate;
    for (const ArrangePolygons *regions : {&params.excluded_regions, &params.nonprefered_regions})
        for (const ArrangePolygon &rg : *regions)
            if (rg.poly.contour.points.size() >= 3)
                every_plate.push_back(to_obstacle(rg, int64_t(rg.inflation)));

    // 4. placement order: priority, extruders, larger first, identical items together
    std::vector<size_t> order(items.size());
    std::iota(order.begin(), order.end(), size_t(0));
    auto area_of = [&](size_t i) {
        const Orient &o = classes[item_class[i]].allowed.front();
        return o.w * o.h;
    };
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        const ArrangePolygon &pa = items[a], &pb = items[b];
        if (pa.priority != pb.priority)
            return pa.priority > pb.priority;
        if (pa.extrude_ids != pb.extrude_ids)
            return pa.extrude_ids < pb.extrude_ids;
        const int64_t aa = area_of(a), ab = area_of(b);
        if (aa != ab)
            return aa > ab;
        return item_class[a] < item_class[b];
    });

    // 5. pack
    std::vector<Plate> plates;
    auto               open_plate = [&]() -> Plate & {
        const int plate_idx = int(plates.size());
        plates.emplace_back();
        Plate &pl = plates.back();
        pl.free_rects.push_back(bin);
        auto it = fixed.find(plate_idx);
        if (it != fixed.end()) {
            pl.obstacles = it->second.rects;
            pl.extruders = it->second.extruders;
            if (it->second.tower)
                pl.tower = it->second.tower;
        }
        if (!pl.tower)
            pl.tower = tower_template;
        if ((it == fixed.end() || !it->second.has_virtual) && virtual_template_bed >= 0) {
            const std::vector<Rect> &tmpl = virtual_rects[virtual_template_bed];
            pl.obstacles.insert(pl.obstacles.end(), tmpl.begin(), tmpl.end());
        }
        pl.obstacles.insert(pl.obstacles.end(), every_plate.begin(), every_plate.end());
        // Fixed objects already make the plate multi-material: the tower is needed from the start.
        if (pl.tower && pl.extruders.size() > 1) {
            pl.obstacles.push_back(*pl.tower);
            pl.tower_reserved = true;
        }
        for (const Rect &o : pl.obstacles)
            pl.occupy(o);
        return pl;
    };

    struct Choice
    {
        int     orient;
        int64_t x, y;
    };
    auto try_plate = [&](Plate &pl, const ShapeClass &cls, Choice &out) {
        bool    found = false;
        int64_t best_top = 0, best_x = 0;
        for (size_t k = 0; k < cls.allowed.size(); ++k) {
            int64_t x, y;
            if (!pl.find(cls.allowed[k].w, cls.allowed[k].h, x, y))
                continue;
            const int64_t top = y + cls.allowed[k].h;
            if (!found || top < best_top || (top == best_top && x < best_x)) {
                found    = true;
                best_top = top;
                best_x   = x;
                out      = {int(k), x, y};
            }
        }
        return found;
    };

    // Like try_plate(), but reserves the prime tower first when the item makes the plate multi-material.
    // The plate is only changed (tower occupied) when the item fits next to the tower.
    size_t towers_added = 0;
    auto   place_on = [&](Plate &pl, const ShapeClass &cls, const std::vector<int> &item_extruders, Choice &out) {
        bool needs_tower = false;
        if (pl.tower && !pl.tower_reserved) {
            std::set<int> ext = pl.extruders;
            ext.insert(item_extruders.begin(), item_extruders.end());
            needs_tower = ext.size() > 1;
        }
        if (!needs_tower)
            return try_plate(pl, cls, out);
        if (pl.tower_blocked)
            return false;
        for (const Placed &pd : pl.placed)
            if (intersects(pd.cell, *pl.tower)) {
                pl.tower_blocked = true;
                return false;
            }
        std::vector<Rect> saved = pl.free_rects;
        pl.occupy(*pl.tower);
        if (!try_plate(pl, cls, out)) {
            pl.free_rects = std::move(saved);
            return false;
        }
        pl.obstacles.push_back(*pl.tower);
        pl.tower_reserved = true;
        ++towers_added;
        return true;
    };

    std::vector<int>    result_plate(items.size(), 0);
    std::vector<size_t> placed_index(items.size(), 0); // index into Plate::placed
    for (size_t idx : order) {
        const ShapeClass &cls = classes[item_class[idx]];
        const std::vector<int> &item_extruders = items[idx].extrude_ids;
        Choice            ch;
        int               plate_id = -1;
        for (size_t p = 0; p < plates.size(); ++p)
            if (place_on(plates[p], cls, item_extruders, ch)) {
                plate_id = int(p);
                break;
            }
        if (plate_id < 0) {
            if (int(plates.size()) >= FAST_MAX_PLATES)
                return unsupported("more plates are needed than the maximum");
            Plate &pl = open_plate();
            if (!place_on(pl, cls, item_extruders, ch))
                return unsupported("an item does not fit on an empty plate (fixed items in the way)");
            plate_id = int(plates.size()) - 1;
        }
        Plate        &pl = plates[plate_id];
        const Orient &o  = cls.allowed[ch.orient];
        const Rect    cell{ch.x, ch.y, ch.x + o.w, ch.y + o.h};
        pl.occupy(cell);
        pl.extruders.insert(item_extruders.begin(), item_extruders.end());
        placed_index[idx] = pl.placed.size();
        pl.placed.push_back({idx, ch.orient, cell});
        result_plate[idx] = plate_id;
    }

    // 6. align the pile of every plate (the same alignment the nesting applies at the end)
    const bool user_pos = std::abs(params.align_center.x() - 0.5) > 0.001 || std::abs(params.align_center.y() - 0.5) > 0.001;
    std::vector<Vec2l> shift(plates.size(), Vec2l::Zero());
    if (params.do_final_align) {
        const Vec2l target(bin.x0 + int64_t(double(bin_w) * (user_pos ? params.align_center.x() : 0.5)),
                           bin.y0 + int64_t(double(bin_h) * (user_pos ? params.align_center.y() : 0.5)));
        for (size_t p = 0; p < plates.size(); ++p) {
            const Plate &pl = plates[p];
            if (pl.placed.empty())
                continue;
            Rect pile = pl.placed.front().cell;
            for (const Placed &pd : pl.placed) {
                pile.x0 = std::min(pile.x0, pd.cell.x0);
                pile.y0 = std::min(pile.y0, pd.cell.y0);
                pile.x1 = std::max(pile.x1, pd.cell.x1);
                pile.y1 = std::max(pile.y1, pd.cell.y1);
            }
            Vec2l d((target.x() - (pile.x0 + pile.x1) / 2), (target.y() - (pile.y0 + pile.y1) / 2));
            d.x() = std::max(bin.x0 - pile.x0, std::min(bin.x1 - pile.x1, d.x()));
            d.y() = std::max(bin.y0 - pile.y0, std::min(bin.y1 - pile.y1, d.y()));
            // Keep the pile off the fixed items: use the largest fraction of the shift that does not collide.
            static const double fractions[] = {1., .75, .5, .25, 0.};
            for (double f : fractions) {
                const Vec2l ds(int64_t(double(d.x()) * f), int64_t(double(d.y()) * f));
                bool        collide = false;
                for (const Placed &pd : pl.placed) {
                    const Rect moved{pd.cell.x0 + ds.x(), pd.cell.y0 + ds.y(), pd.cell.x1 + ds.x(), pd.cell.y1 + ds.y()};
                    for (const Rect &ob : pl.obstacles)
                        if (intersects(moved, ob)) {
                            collide = true;
                            break;
                        }
                    if (collide)
                        break;
                }
                if (!collide) {
                    shift[p] = ds;
                    break;
                }
            }
        }
    }

    // 7. write the result back; the item id is the placement order, like in the nesting
    int placement_order = 0;
    for (size_t idx : order) {
        const int            plate_id = result_plate[idx];
        const Plate         &pl       = plates[plate_id];
        ArrangePolygon      &ap       = items[idx];
        const ShapeClass    &cls      = classes[item_class[idx]];
        const Placed        &pd       = pl.placed[placed_index[idx]];
        const Orient &o = cls.allowed[pd.orient];
        ap.translation  = Vec2crd(coord_t(pd.cell.x0 + shift[plate_id].x() + o.offx), coord_t(pd.cell.y0 + shift[plate_id].y() + o.offy));
        ap.rotation     = o.angle;
        ap.bed_idx      = plate_id;
        ap.itemid       = placement_order++;
    }

    const double ms = std::chrono::duration<double, std::milli>(clock::now() - t_start).count();
    BOOST_LOG_TRIVIAL(info) << "arrange_fast: " << items.size() << " items, " << classes.size() << " shape classes, " << plates.size()
                            << " plate(s), " << towers_added << " prime tower(s) reserved, " << ms << " ms";
    return true;
}

}} // namespace Slic3r::arrangement
