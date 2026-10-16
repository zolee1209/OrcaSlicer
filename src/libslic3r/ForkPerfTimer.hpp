#ifndef slic3r_ForkPerfTimer_hpp_
#define slic3r_ForkPerfTimer_hpp_

// FORK(perf-phase-timers): wall-clock timing of the G-code export and preview phases.
// Every record is logged at info level as "[fork-perf] <name>: <ms> ms", so the timers are
// silent unless the log level is info or more verbose (CLI --debug 4, GUI log_severity_level=info).

#include <chrono>
#include <cstdio>

#include <boost/log/trivial.hpp>

namespace Slic3r {

using ForkPerfClock = std::chrono::steady_clock;

inline double fork_perf_ms_since(ForkPerfClock::time_point start)
{
    return std::chrono::duration<double, std::milli>(ForkPerfClock::now() - start).count();
}

inline void fork_perf_log(const char *name, double ms)
{
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.1f", ms);
    BOOST_LOG_TRIVIAL(info) << "[fork-perf] " << name << ": " << buf << " ms";
}

// Logs the time elapsed since construction when it goes out of scope (or at stop()).
class ForkPerfScope
{
public:
    explicit ForkPerfScope(const char *name) : m_name(name), m_start(ForkPerfClock::now()) {}
    ~ForkPerfScope() { stop(); }
    ForkPerfScope(const ForkPerfScope &) = delete;
    ForkPerfScope &operator=(const ForkPerfScope &) = delete;

    void stop()
    {
        if (m_name != nullptr) {
            fork_perf_log(m_name, fork_perf_ms_since(m_start));
            m_name = nullptr;
        }
    }

private:
    const char               *m_name;
    ForkPerfClock::time_point m_start;
};

} // namespace Slic3r

#endif // slic3r_ForkPerfTimer_hpp_
