#ifndef slic3r_GCode_KlipperPlanner_hpp_
#define slic3r_GCode_KlipperPlanner_hpp_

// FORK(klipper-time-estimate): port of Klipper's look-ahead planner for the G-code time estimator.
//
// Source: klippy/toolhead.py (Move, LookAheadQueue) and klippy/kinematics/extruder.py
// (PrinterExtruder.calc_junction) of Klipper v0.12.0-402-g2817b348. The Marlin style planner of
// GCodeProcessor differs from Klipper in three ways that make it optimistic on a Klipper machine:
//  - minimum_cruise_ratio (formerly max_accel_to_decel) caps the peak speed of short moves;
//  - the junction speed uses the junction deviation of the toolhead acceleration but the actual
//    (axis limited) acceleration of both moves, and a centripetal limit for short segments, so a
//    corner into a Z hop is taken at ~1 mm/s instead of the square corner velocity;
//  - a change of the extrusion ratio across a corner is limited by instantaneous_corner_velocity,
//    and extrude-only moves always start and end at rest.

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace Slic3r {
namespace KlipperPlanner {

// Toolhead state at the moment a move is queued (SET_VELOCITY_LIMIT / M204 / printer.cfg).
struct Settings
{
    double max_accel{ 0. };               // [printer] max_accel, SET_VELOCITY_LIMIT ACCEL, M204 S
    double square_corner_velocity{ 5. };  // [printer] square_corner_velocity
    double min_cruise_ratio{ 0.5 };       // [printer] minimum_cruise_ratio
    double instant_corner_velocity{ 1. }; // [extruder] instantaneous_corner_velocity
};

// Klipper's Move, reduced to what the planner needs. All velocities are squared, in (mm/s)^2.
struct Move
{
    bool   kinematic{ false };
    double move_d{ 0. };
    double accel{ 0. };
    double junction_deviation{ 0. };
    double axes_r[4]{ 0., 0., 0., 0. };
    double max_cruise_v2{ 0. };
    double delta_v2{ 0. };
    double smooth_delta_v2{ 0. };
    double max_start_v2{ 0. };
    double max_smoothed_v2{ 0. };
    // Planned junction speeds, written by flush().
    double start_v2{ 0. };
    double cruise_v2{ 0. };
    double end_v2{ 0. };
};

// Move.__init__ followed by the kinematic / extruder limit_speed() calls. The caller passes the speed
// and acceleration it already limited per axis (Z ratio, extrude-only and retraction limits), which is
// what limit_speed() leaves in Move.max_cruise_v2 and Move.accel.
void init_move(Move &move, const Settings &settings, double move_d, bool kinematic, const double axes_r[4],
               double cruise_v, double accel);

// Move.calc_junction(prev_move). Leaves the junction at rest when either move is extrude-only.
void calc_junction(Move &move, const Move &prev, const Settings &settings);

inline void set_junction(Move &move, double start_v2, double cruise_v2, double end_v2)
{
    move.start_v2  = start_v2;
    move.cruise_v2 = cruise_v2;
    move.end_v2    = end_v2;
}

// LookAheadQueue.flush(lazy) over moves [0, count), assuming a full stop after the last one.
// A lazy flush only plans the moves that later moves can no longer change and returns their count
// (0 if none yet); a full flush plans and returns all of them. at(i) returns the i-th Move&.
template<class At> size_t flush(size_t count, bool lazy, At &&at)
{
    struct Delayed
    {
        Move  *move;
        double start_v2;
        double end_v2;
    };
    std::vector<Delayed> delayed;
    size_t flush_count        = count;
    bool   update_flush_count = lazy;
    double next_end_v2 = 0., next_smoothed_v2 = 0., peak_cruise_v2 = 0.;
    for (size_t i = count; i-- > 0;) {
        Move        &move                  = at(i);
        const double reachable_start_v2    = next_end_v2 + move.delta_v2;
        const double start_v2              = std::min(move.max_start_v2, reachable_start_v2);
        const double reachable_smoothed_v2 = next_smoothed_v2 + move.smooth_delta_v2;
        const double smoothed_v2           = std::min(move.max_smoothed_v2, reachable_smoothed_v2);
        if (smoothed_v2 < reachable_smoothed_v2) {
            // It's possible for this move to accelerate
            if (smoothed_v2 + move.smooth_delta_v2 > next_smoothed_v2 || !delayed.empty()) {
                // This move can decelerate or this is a full accel move after a full decel move
                if (update_flush_count && peak_cruise_v2 != 0.) {
                    flush_count        = i;
                    update_flush_count = false;
                }
                peak_cruise_v2 = std::min(move.max_cruise_v2, (smoothed_v2 + reachable_smoothed_v2) * .5);
                if (!delayed.empty()) {
                    // Propagate peak_cruise_v2 to any delayed moves
                    if (!update_flush_count && i < flush_count) {
                        double mc_v2 = peak_cruise_v2;
                        for (auto it = delayed.rbegin(); it != delayed.rend(); ++it) {
                            mc_v2 = std::min(mc_v2, it->start_v2);
                            set_junction(*it->move, std::min(it->start_v2, mc_v2), mc_v2, std::min(it->end_v2, mc_v2));
                        }
                    }
                    delayed.clear();
                }
            }
            if (!update_flush_count && i < flush_count) {
                const double cruise_v2 = std::min({ (start_v2 + reachable_start_v2) * .5, move.max_cruise_v2, peak_cruise_v2 });
                set_junction(move, std::min(start_v2, cruise_v2), cruise_v2, std::min(next_end_v2, cruise_v2));
            }
        } else {
            // Delay calculating this move until peak_cruise_v2 is known
            delayed.push_back({ &move, start_v2, next_end_v2 });
        }
        next_end_v2      = start_v2;
        next_smoothed_v2 = smoothed_v2;
    }
    return update_flush_count ? 0 : flush_count;
}

// Plans GCodeProcessor time blocks (which carry a Move in their `klipper` member) and writes the result
// into their feedrate profile and trapezoid. keep_last_n_blocks > 0 means more moves will follow, so
// the flush is lazy, as Klipper's own while printing; 0 is a full stop (M400, G4, end of file).
// Returns the number of leading blocks whose timing is final.
template<class Block> size_t plan_time_blocks(std::vector<Block> &blocks, size_t keep_last_n_blocks)
{
    // A lazy flush finds nothing to finalize only on an unusually long run of moves that can't
    // accelerate; bound the queue the way the firmware's buffer does, by a full flush then.
    static constexpr size_t max_lazy_queue = 8192;

    auto at = [&blocks](size_t i) -> Move & { return blocks[i].klipper; };
    size_t n_final = 0;
    if (keep_last_n_blocks == 0)
        n_final = flush(blocks.size(), false, at);
    else {
        n_final = flush(blocks.size(), true, at);
        if (n_final == 0 && blocks.size() > max_lazy_queue) {
            flush(blocks.size(), false, at);
            n_final = blocks.size() - std::min(keep_last_n_blocks, blocks.size());
        }
    }

    for (size_t i = 0; i < n_final; ++i) {
        Block      &block = blocks[i];
        const Move &move  = block.klipper;
        block.feedrate_profile.entry  = float(std::sqrt(move.start_v2));
        block.feedrate_profile.cruise = float(std::sqrt(move.cruise_v2));
        block.feedrate_profile.exit   = float(std::sqrt(move.end_v2));
        block.calculate_trapezoid();
        block.flags.recalculate = false;
    }
    return n_final;
}

} // namespace KlipperPlanner
} // namespace Slic3r

#endif // slic3r_GCode_KlipperPlanner_hpp_
