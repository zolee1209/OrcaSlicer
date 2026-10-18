// FORK(perf-tree-support): output-identical speed-ups of the organic (3D) tree support generator.
// Kept in a fork-owned header so that TreeSupport3D.cpp only carries thin call sites.
#ifndef slic3r_TreeSupport3DPerf_hpp_
#define slic3r_TreeSupport3DPerf_hpp_

#include "../BoundingBox.hpp"
#include "../ClipperUtils.hpp"
#include "../Polygon.hpp"
#include "TreeSupportCommon.hpp"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <utility>
#include <vector>

namespace Slic3r::TreeSupport3D {

// append() reserves exactly the needed size, so appending many vectors one by one to the same
// destination reallocates (and, as Polygon's move constructor is not noexcept, deep copies) every
// time: quadratic in the number of appends. Geometric growth makes it linear; the resulting
// sequence of elements is the same.
template<class T, class A>
inline void append_geometric(std::vector<T, A> &dest, std::vector<T, A> &&src)
{
    if (dest.empty()) {
        dest = std::move(src);
    } else {
        if (dest.capacity() < dest.size() + src.size())
            dest.reserve(std::max(dest.size() + src.size(), 2 * dest.capacity()));
        std::move(std::begin(src), std::end(src), std::back_inserter(dest));
    }
    src.clear();
    src.shrink_to_fit();
}

// Cheap conservative pre-test of merge_influence_areas_two_elements(): returns true only if the exact
// test, intersection(safe_offset_inc(small, delta, collision, step, 0, 0), bigger), cannot have an area
// above tiny_area_threshold(), so the pair would be rejected anyway.
//
// A square-joined offset contains the round-joined one of the same distance. The margin adds the
// Douglas-Peucker deviation of every polygons_simplify() call inside safe_offset_inc() (0.015 mm each,
// one per 10 steps plus the final one), its 0.002 mm fallback for unions that collapse, and integer
// rounding per offset step. Clipper2 may drop micro-components (a few square micrometers) from a
// square-joined offset that the round-joined one keeps; inputs with any component under (0.1 mm)^2 go
// to the exact test, as does an empty offset.
inline bool merge_overlap_impossible(const Polygons &small, const Polygons &bigger, coord_t delta, coord_t safe_step_size)
{
    if (small.empty() || bigger.empty())
        return false;
    const double min_component_area = sqr(scaled<double>(0.1));
    for (const Polygon &p : small)
        if (std::abs(p.area()) < min_component_area)
            return false;
    const coord_t step   = std::max<coord_t>(1, safe_step_size);
    const coord_t steps  = delta / step;
    const coord_t margin = delta + scaled<coord_t>(0.015) * (2 + steps / 10) + scaled<coord_t>(0.002) + 10 * (steps + 3);
    BoundingBox   bb_small = get_extents(small);
    bb_small.offset(margin);
    if (! bb_small.overlap(get_extents(bigger)))
        return true;
    const Polygons grown = offset(small, float(margin), jtSquare);
    return ! grown.empty() && area(intersection(grown, bigger)) <= tiny_area_threshold();
}

} // namespace Slic3r::TreeSupport3D

#endif // slic3r_TreeSupport3DPerf_hpp_
