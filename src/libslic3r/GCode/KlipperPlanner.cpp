// FORK(klipper-time-estimate): Klipper look-ahead planner for the G-code time estimator.
// See KlipperPlanner.hpp for the rationale and the Klipper revision this follows.

#include "KlipperPlanner.hpp"

#include "GCodeProcessor.hpp"

#include <regex>
#include <string>

namespace Slic3r {
namespace KlipperPlanner {

void init_move(Move &move, const Settings &settings, double move_d, bool kinematic, const double axes_r[4],
               double cruise_v, double accel)
{
    move           = Move();
    move.kinematic = kinematic;
    move.move_d    = move_d;
    move.accel     = accel;
    // toolhead.py _calc_junction_deviation(): from the toolhead acceleration, not the move's own.
    if (settings.max_accel > 0.)
        move.junction_deviation = settings.square_corner_velocity * settings.square_corner_velocity * (std::sqrt(2.) - 1.) /
                                  settings.max_accel;
    for (int a = 0; a < 4; ++a)
        move.axes_r[a] = axes_r[a];
    move.max_cruise_v2 = cruise_v * cruise_v;
    move.delta_v2      = 2. * move_d * accel;
    // smooth_delta_v2 starts from max_accel_to_decel and limit_speed() caps it by delta_v2.
    const double max_accel_to_decel = settings.max_accel * (1. - settings.min_cruise_ratio);
    move.smooth_delta_v2            = std::min(2. * move_d * max_accel_to_decel, move.delta_v2);
}

void calc_junction(Move &move, const Move &prev, const Settings &settings)
{
    if (!move.kinematic || !prev.kinematic)
        return;
    // PrinterExtruder.calc_junction()
    const double diff_r      = move.axes_r[3] - prev.axes_r[3];
    const double extruder_v2 = (diff_r != 0.) ? std::pow(settings.instant_corner_velocity / std::abs(diff_r), 2) : move.max_cruise_v2;
    double max_start_v2 = std::min({ extruder_v2, move.max_cruise_v2, prev.max_cruise_v2, prev.max_start_v2 + prev.delta_v2 });
    // Find max velocity using "approximated centripetal velocity"
    const double junction_cos_theta = -(move.axes_r[0] * prev.axes_r[0] + move.axes_r[1] * prev.axes_r[1] +
                                        move.axes_r[2] * prev.axes_r[2]);
    const double sin_theta_d2           = std::sqrt(std::max(0.5 * (1.0 - junction_cos_theta), 0.));
    const double cos_theta_d2           = std::sqrt(std::max(0.5 * (1.0 + junction_cos_theta), 0.));
    const double one_minus_sin_theta_d2 = 1. - sin_theta_d2;
    if (one_minus_sin_theta_d2 > 0. && cos_theta_d2 > 0.) {
        const double R_jd        = sin_theta_d2 / one_minus_sin_theta_d2;
        const double move_jd_v2  = R_jd * move.junction_deviation * move.accel;
        const double pmove_jd_v2 = R_jd * prev.junction_deviation * prev.accel;
        // Approximated circle must contact moves no further than mid-move
        const double quarter_tan_theta_d2 = .25 * sin_theta_d2 / cos_theta_d2;
        const double move_centripetal_v2  = move.delta_v2 * quarter_tan_theta_d2;
        const double pmove_centripetal_v2 = prev.delta_v2 * quarter_tan_theta_d2;
        max_start_v2 = std::min({ max_start_v2, move_jd_v2, pmove_jd_v2, move_centripetal_v2, pmove_centripetal_v2 });
    }
    move.max_start_v2    = max_start_v2;
    move.max_smoothed_v2 = std::min(max_start_v2, prev.max_smoothed_v2 + prev.smooth_delta_v2);
}

} // namespace KlipperPlanner

static float klipper_option_value(const ConfigOptionFloats &option, size_t id)
{
    return option.values.empty() ? 0.0f :
                                   static_cast<float>(id < option.values.size() ? option.values[id] : option.values.front());
}

void GCodeProcessor::klipper_init_block(TimeBlock &block, const AxisCoords &delta_pos, EMoveType type, size_t mode_id) const
{
    const TimeMachine         &machine = m_time_processor.machines[mode_id];
    const MachineEnvelopeConfig &limits = m_time_processor.machine_limits;

    KlipperPlanner::Settings settings;
    // Klipper has a single toolhead acceleration; Orca tracks the same SET_VELOCITY_LIMIT ACCEL / M204 S
    // value as print and travel acceleration (an extrude-only move is queued under the print one).
    settings.max_accel               = (type == EMoveType::Travel) ? machine.travel_acceleration : machine.acceleration;
    settings.square_corner_velocity  = klipper_option_value(limits.machine_max_jerk_x, mode_id);
    settings.min_cruise_ratio        = std::clamp(limits.machine_minimum_cruise_ratio.value, 0., 0.999);
    settings.instant_corner_velocity = std::max(limits.machine_instantaneous_corner_velocity.value, 0.);

    const double xyz_d     = std::sqrt(sqr(delta_pos[X]) + sqr(delta_pos[Y]) + sqr(delta_pos[Z]));
    const bool   kinematic = xyz_d >= 1e-9;
    double       axes_r[4] = { 0., 0., 0., 0. };
    if (kinematic) {
        for (int a = X; a <= Z; ++a)
            axes_r[a] = delta_pos[a] / xyz_d;
        axes_r[E] = delta_pos[E] * machine.extrude_factor_override_percentage / xyz_d;
    } else
        axes_r[E] = (delta_pos[E] < 0.) ? -1. : 1.;

    KlipperPlanner::init_move(block.klipper, settings, block.distance, kinematic, axes_r, block.feedrate_profile.cruise,
                              block.acceleration);
    if (!machine.blocks.empty())
        KlipperPlanner::calc_junction(block.klipper, machine.blocks.back().klipper, settings);
}

void GCodeProcessor::klipper_process_set_velocity_limit(const GCodeReader::GCodeLine &line)
{
    // toolhead.py cmd_SET_VELOCITY_LIMIT: MINIMUM_CRUISE_RATIO wins; otherwise the deprecated
    // ACCEL_TO_DECEL (still emitted by Orca's accel_to_decel option) is converted to a ratio of ACCEL,
    // or of the current acceleration when the line has no ACCEL.
    static const std::regex mcr_pattern("\\sMINIMUM_CRUISE_RATIO\\s*=\\s*([0-9]*\\.?[0-9]*)");
    static const std::regex a2d_pattern("\\sACCEL_TO_DECEL\\s*=\\s*([0-9]*\\.?[0-9]*)");
    static const std::regex accel_pattern("\\sACCEL\\s*=\\s*([0-9]*\\.?[0-9]*)");

    auto read = [&line](const std::regex &pattern, double &value) {
        std::smatch matches;
        const std::string &raw = line.raw();
        if (!std::regex_search(raw, matches, pattern) || matches.size() != 2)
            return false;
        try {
            value = std::stod(matches[1]);
        } catch (...) {
            return false;
        }
        return true;
    };

    double mcr = 0., a2d = 0., accel = 0.;
    if (read(mcr_pattern, mcr)) {
        if (mcr < 0. || mcr >= 1.)
            return; // Klipper rejects the command
    } else if (read(a2d_pattern, a2d) && a2d > 0.) {
        if (!read(accel_pattern, accel) || accel <= 0.)
            accel = m_time_processor.machines[static_cast<size_t>(PrintEstimatedStatistics::ETimeMode::Normal)].acceleration;
        if (accel <= 0.)
            return;
        mcr = 1. - std::min(1., a2d / accel);
    } else
        return;
    m_time_processor.machine_limits.machine_minimum_cruise_ratio.value = mcr;
}

} // namespace Slic3r
