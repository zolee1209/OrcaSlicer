// FORK(perf-gcode-processor): exact, y-bucketed point-in-polygon for large polygons.
#ifndef slic3r_ForkRingIndex_hpp_
#define slic3r_ForkRingIndex_hpp_

#include "ExPolygon.hpp"
#include "Point.hpp"

#include <algorithm>
#include <cstdint>
#include <vector>

namespace Slic3r {

// The edges of one ring, bucketed by their y-range, answering Clipper1's PointInPolygon() (1 inside, 0 outside,
// -1 on the boundary) exactly like Slic3r's point_in_polygon(): an edge whose y-range misses the point neither
// flips the parity nor reports the boundary, and the edges contribute independently of each other, so testing
// only the edges of the point's bucket gives the result of the full scan.
class RingPointInPolygonIndex
{
public:
    void build(const Points &points)
    {
        m_points = &points;
        m_start.clear();
        m_edges.clear();
        if (points.size() < 3)
            return;
        m_ymin = m_ymax = points.front().y();
        for (const Point &p : points) {
            m_ymin = std::min(m_ymin, p.y());
            m_ymax = std::max(m_ymax, p.y());
        }
        const size_t buckets = std::clamp<size_t>(points.size() / 4, 1, 4096);
        m_bucket_height      = std::max<int64_t>(1, (int64_t(m_ymax) - int64_t(m_ymin)) / int64_t(buckets) + 1);
        std::vector<uint32_t> count(buckets + 1, 0);
        for_each_edge_bucket([&count](size_t, size_t bucket) { ++count[bucket + 1]; });
        for (size_t k = 1; k <= buckets; ++k)
            count[k] += count[k - 1];
        m_start = count;
        m_edges.assign(count[buckets], 0);
        for_each_edge_bucket([this, &count](size_t edge, size_t bucket) { m_edges[count[bucket]++] = uint32_t(edge); });
    }

    int point_in_polygon(const Point &pt) const
    {
        if (m_start.empty() || pt.y() < m_ymin || pt.y() > m_ymax)
            return 0;
        const Points  &path   = *m_points;
        const size_t   cnt    = path.size();
        const size_t   bucket = size_t((int64_t(pt.y()) - int64_t(m_ymin)) / m_bucket_height);
        int            result = 0;
        for (uint32_t k = m_start[bucket]; k != m_start[bucket + 1]; ++k) {
            const size_t i      = m_edges[k];
            const Point &ip     = path[i];
            const Point &ipNext = path[i + 1 == cnt ? 0 : i + 1];
            if (ipNext.y() == pt.y() && ((ipNext.x() == pt.x()) || (ip.y() == pt.y() && ((ipNext.x() > pt.x()) == (ip.x() < pt.x())))))
                return -1;
            if ((ip.y() < pt.y()) != (ipNext.y() < pt.y())) {
                if (ip.x() >= pt.x()) {
                    if (ipNext.x() > pt.x())
                        result = 1 - result;
                    else {
                        int64_t d = int64_t(ip.x() - pt.x()) * int64_t(ipNext.y() - pt.y()) - int64_t(ipNext.x() - pt.x()) * int64_t(ip.y() - pt.y());
                        if (!d) return -1;
                        if ((d > 0) == (ipNext.y() > ip.y())) result = 1 - result;
                    }
                } else if (ipNext.x() > pt.x()) {
                    int64_t d = int64_t(ip.x() - pt.x()) * int64_t(ipNext.y() - pt.y()) - int64_t(ipNext.x() - pt.x()) * int64_t(ip.y() - pt.y());
                    if (!d) return -1;
                    if ((d > 0) == (ipNext.y() > ip.y())) result = 1 - result;
                }
            }
        }
        return result;
    }

private:
    template<class F> void for_each_edge_bucket(F &&f) const
    {
        const Points &pts = *m_points;
        for (size_t i = 0; i < pts.size(); ++i) {
            const Point &a = pts[i], &b = pts[i + 1 == pts.size() ? 0 : i + 1];
            const size_t lo = size_t((int64_t(std::min(a.y(), b.y())) - int64_t(m_ymin)) / m_bucket_height);
            const size_t hi = size_t((int64_t(std::max(a.y(), b.y())) - int64_t(m_ymin)) / m_bucket_height);
            for (size_t k = lo; k <= hi; ++k)
                f(i, k);
        }
    }

    const Points         *m_points{ nullptr };
    coord_t               m_ymin{ 0 };
    coord_t               m_ymax{ -1 };
    int64_t               m_bucket_height{ 1 };
    std::vector<uint32_t> m_start;
    std::vector<uint32_t> m_edges;
};

// ExPolygon::contains(point) (border_result = true) answered through RingPointInPolygonIndex. The ExPolygon must
// outlive the index and must not change after build().
class ExPolygonContainsIndex
{
public:
    bool built() const { return m_built; }
    void build(const ExPolygon &expoly)
    {
        m_rings.assign(1 + expoly.holes.size(), {});
        m_rings.front().build(expoly.contour.points);
        for (size_t i = 0; i < expoly.holes.size(); ++i)
            m_rings[i + 1].build(expoly.holes[i].points);
        m_built = true;
    }
    bool contains(const Point &point) const
    {
        // Outside the contour and not on its boundary.
        if (m_rings.front().point_in_polygon(point) == 0)
            return false;
        // Strictly inside a hole.
        for (size_t i = 1; i < m_rings.size(); ++i)
            if (m_rings[i].point_in_polygon(point) == 1)
                return false;
        return true;
    }

private:
    std::vector<RingPointInPolygonIndex> m_rings;
    bool                                 m_built{ false };
};

} // namespace Slic3r

#endif // slic3r_ForkRingIndex_hpp_
