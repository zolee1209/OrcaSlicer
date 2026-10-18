// FORK(klipper-time-estimate): the Klipper look-ahead port must reproduce Klipper's own planner.
// The expected times come from Klipper v0.12.0-402-g2817b348 klippy/toolhead.py (Move and
// LookAheadQueue run unmodified) fed the same G-code with the same limits as make_klipper_config().

#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>

#include "libslic3r/GCode/GCodeProcessor.hpp"
#include "libslic3r/GCode/KlipperPlanner.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "libslic3r/Utils.hpp"

#include "test_utils.hpp"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>

using namespace Slic3r;
using Catch::Matchers::WithinAbs;

namespace {

constexpr size_t NORMAL = static_cast<size_t>(PrintEstimatedStatistics::ETimeMode::Normal);

// printer.cfg: max_accel 1000 (the G-code sets it too, as Orca starts travels at its own default),
// max_z_velocity 80, max_z_accel 200, square_corner_velocity 5;
// [extruder] max_extrude_only_velocity 60, max_extrude_only_accel 8000, instantaneous_corner_velocity 1.
FullPrintConfig make_klipper_config(GCodeFlavor flavor = gcfKlipper)
{
    FullPrintConfig config;
    config.gcode_flavor.value       = flavor;
    config.filament_diameter.values = {1.75};
    config.filament_map.values      = {1};
    const std::vector<double> accel = {1000.0, 1000.0};
    const std::vector<double> xy    = {20000.0, 20000.0};
    config.machine_max_acceleration_extruding.values  = accel;
    config.machine_max_acceleration_travel.values     = accel;
    config.machine_max_acceleration_retracting.values = {8000.0, 8000.0};
    config.machine_max_acceleration_x.values          = xy;
    config.machine_max_acceleration_y.values          = xy;
    config.machine_max_acceleration_z.values          = {200.0, 200.0};
    config.machine_max_acceleration_e.values          = {8000.0, 8000.0};
    config.machine_max_speed_x.values                 = {500.0, 500.0};
    config.machine_max_speed_y.values                 = {500.0, 500.0};
    config.machine_max_speed_z.values                 = {80.0, 80.0};
    config.machine_max_speed_e.values                 = {60.0, 60.0};
    config.machine_max_jerk_x.values                  = {5.0, 5.0};
    config.machine_max_jerk_y.values                  = {5.0, 5.0};
    config.machine_max_jerk_z.values                  = {0.4, 0.4};
    config.machine_max_jerk_e.values                  = {5.0, 5.0};
    config.machine_min_extruding_rate.values          = {0.0, 0.0};
    config.machine_min_travel_rate.values             = {0.0, 0.0};
    config.machine_minimum_cruise_ratio.value          = 0.5;
    config.machine_instantaneous_corner_velocity.value = 1.0;
    return config;
}

double estimate(const FullPrintConfig& config, const std::string& gcode)
{
    const bool previous_is_bbl_printer = GCodeProcessor::s_IsBBLPrinter;
    GCodeProcessor::s_IsBBLPrinter     = false;
    const ScopeGuard restore_flag([previous_is_bbl_printer] { GCodeProcessor::s_IsBBLPrinter = previous_is_bbl_printer; });
    ScopedTemporaryFile temp(".gcode");
    {
        std::ofstream os(temp.string());
        os << gcode;
    }
    GCodeProcessor proc;
    proc.apply_config(config);
    proc.process_file(temp.string());
    return proc.get_result().print_statistics.modes[NORMAL].time;
}

// 30 extruding segments of 3mm, turning 60 degrees each: too short to reach 200mm/s, so the peak
// speed of every segment is set by minimum_cruise_ratio.
std::string zigzag(const std::string& header = "")
{
    std::ostringstream os;
    os << std::fixed << std::setprecision(4) << "SET_VELOCITY_LIMIT ACCEL=1000\nM83\nG1 Z0.2 F1200\nG1 X50 Y50 F12000\n" << header;
    double x = 50.0, y = 50.0;
    for (int i = 0; i < 30; ++i) {
        const double a = (i % 2 == 0 ? 30.0 : -30.0) * M_PI / 180.0;
        x += 3.0 * std::cos(a);
        y += 3.0 * std::sin(a);
        os << "G1 X" << x << " Y" << y << " E0.1 F12000\n";
    }
    return os.str();
}

// Ten retract, Z hop, travel, unhop, unretract cycles between extrusions.
std::string hops()
{
    std::ostringstream os;
    os << std::fixed << std::setprecision(3) << "SET_VELOCITY_LIMIT ACCEL=1000\nM83\nG1 Z0.2 F1200\nG1 X50 Y50 F12000\n";
    double x = 50.0;
    for (int i = 0; i < 10; ++i) {
        os << "G1 X" << x + 10 << " Y50 E0.4 F6000\n"
           << "G1 E-0.8 F3600\nG1 Z0.4 F12000\nG1 X" << x + 20 << " Y60 F12000\nG1 Z0.2\nG1 E0.8 F3600\n"
           << "G1 X" << x + 20 << " Y50 E0.4 F6000\n";
        x += 20.0;
    }
    return os.str();
}

} // namespace

TEST_CASE("Klipper print time follows Klipper's own look-ahead", "[GCodeTiming][Klipper]")
{
    SECTION("short moves are capped by minimum_cruise_ratio") {
        REQUIRE_THAT(estimate(make_klipper_config(), zigzag()), WithinAbs(3.600, 0.002));

        FullPrintConfig no_mcr                    = make_klipper_config();
        no_mcr.machine_minimum_cruise_ratio.value = 0.0;
        REQUIRE_THAT(estimate(no_mcr, zigzag()), WithinAbs(3.403, 0.002));
    }

    SECTION("ACCEL_TO_DECEL in the G-code sets the ratio, as Klipper converts it") {
        // 250 of ACCEL=1000 is a minimum_cruise_ratio of 0.75 and overrides the printer setting.
        REQUIRE_THAT(estimate(make_klipper_config(), zigzag("SET_VELOCITY_LIMIT ACCEL=1000 ACCEL_TO_DECEL=250\n")),
                     WithinAbs(4.158, 0.002));
        REQUIRE_THAT(estimate(make_klipper_config(), zigzag("SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.75\n")),
                     WithinAbs(4.158, 0.002));
    }

    SECTION("Z hops and extrude-only moves corner at Klipper's speeds") {
        // The junction into a Z hop uses the Z limited acceleration (~2mm/s, not the square corner
        // velocity) and a retraction starts and ends at rest.
        REQUIRE_THAT(estimate(make_klipper_config(), hops()), WithinAbs(9.157, 0.002));
    }

    SECTION("the look-ahead and its settings are Klipper only") {
        FullPrintConfig marlin = make_klipper_config(gcfMarlinLegacy);
        const double    before = estimate(marlin, zigzag());
        marlin.machine_minimum_cruise_ratio.value          = 0.0;
        marlin.machine_instantaneous_corner_velocity.value = 50.0;
        REQUIRE(estimate(marlin, zigzag()) == before);
    }
}

TEST_CASE("Klipper look-ahead flush matches toolhead.py", "[GCodeTiming][Klipper]")
{
    // A 10mm move from rest to rest at 1000mm/s^2 with a cap of 100mm/s: v^2 = d * a reaches 10000,
    // so the full trapezoid fits; minimum_cruise_ratio 0.5 halves the usable acceleration.
    KlipperPlanner::Settings settings;
    settings.max_accel        = 1000.;
    settings.min_cruise_ratio = 0.5;
    const double axes_r[4]    = {1., 0., 0., 0.};

    KlipperPlanner::Move move;
    KlipperPlanner::init_move(move, settings, 10., true, axes_r, 100., 1000.);
    std::vector<KlipperPlanner::Move> moves{move};
    REQUIRE(KlipperPlanner::flush(moves.size(), false, [&moves](size_t i) -> KlipperPlanner::Move& { return moves[i]; }) == 1);
    REQUIRE_THAT(moves[0].start_v2, WithinAbs(0., 1e-9));
    REQUIRE_THAT(moves[0].end_v2, WithinAbs(0., 1e-9));
    // peak = (0 + 2 * d * a * (1 - mcr)) / 2 = 5000
    REQUIRE_THAT(moves[0].cruise_v2, WithinAbs(5000., 1e-6));

    SECTION("a lazy flush keeps moves whose speed later moves can still change") {
        std::vector<KlipperPlanner::Move> one{move};
        REQUIRE(KlipperPlanner::flush(one.size(), true, [&one](size_t i) -> KlipperPlanner::Move& { return one[i]; }) == 0);
    }
}
