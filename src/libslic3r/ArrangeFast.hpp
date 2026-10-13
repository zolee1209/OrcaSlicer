#ifndef slic3r_ArrangeFast_hpp_
#define slic3r_ArrangeFast_hpp_

#include "Arrange.hpp"

namespace Slic3r { namespace arrangement {

// Fast, bounding-box based arrangement for rectangular beds.
//
// Every item is represented by the axis aligned bounding box of its inflated convex hull in one of a few
// orientations (0/90 degrees, or 45/135 degrees for items that do not fit otherwise) and the boxes are packed
// with a MaxRects (bottom-left) packer, plate by plate. Identical items form a regular grid.
//
// Returns false (leaving the input untouched) when the case is not supported, the caller then has to use
// the general purpose nesting. The reason is logged.
bool arrange_fast(ArrangePolygons &items, const ArrangePolygons &excludes, const BoundingBox &bed, const ArrangeParams &params);

}} // namespace Slic3r::arrangement

#endif // slic3r_ArrangeFast_hpp_
