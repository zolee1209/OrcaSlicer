#ifndef slic3r_CliPresetResolver_hpp_
#define slic3r_CliPresetResolver_hpp_

#include <string>
#include <vector>
#include "PrintConfig.hpp"

namespace Slic3r {

/**
 * CLI Preset Inherits Resolver
 *
 * Resolves the "inherits" chain for preset JSON files loaded via the CLI,
 * without requiring the full GUI PresetBundle infrastructure.
 *
 * The GUI resolves inherits through PresetCollection::load_presets() which
 * indexes all vendor profiles into memory first.  In CLI mode we do it lazily:
 * given a JSON file with "inherits": "fdm_filament_abs", we search for the
 * parent in the same directory, then walk up through the vendor profiles
 * directory tree.
 *
 * Usage:
 *   DynamicPrintConfig resolved;
 *   std::string reason;
 *   CliPresetResolver::resolve(
 *       "/path/to/filament/MyProfile.json",
 *       ForwardCompatibilitySubstitutionRule::EnableSilent,
 *       resolved, reason);
 *   // resolved now contains all inherited keys merged in bottom-up order
 */
class CliPresetResolver {
public:
    /**
     * Resolve a preset JSON file including its full "inherits" chain.
     *
     * @param file              Path to the preset JSON to load.
     * @param rule              Substitution rule for forward-compat loading.
     * @param out_config        Output: fully resolved DynamicPrintConfig.
     * @param out_reason        Output: non-empty if loading failed.
     * @param extra_search_dirs Additional directories to search for parent presets
     *                          (beyond the file's own directory and resources/profiles).
     * @return true on success
     */
    static bool resolve(
        const std::string&                      file,
        ForwardCompatibilitySubstitutionRule     rule,
        DynamicPrintConfig&                     out_config,
        std::string&                            out_reason,
        const std::vector<std::string>&         extra_search_dirs = {});

private:
    static constexpr int kMaxDepth = 16; // guard against circular inherits

    /**
     * Load a single JSON file into a DynamicPrintConfig without resolving
     * inherits (raw load).  Returns the "inherits" value via out_inherits.
     */
    static bool load_one(
        const std::string&                  file,
        ForwardCompatibilitySubstitutionRule rule,
        DynamicPrintConfig&                 out_config,
        std::string&                        out_inherits,
        std::string&                        out_reason);

    /**
     * Search for a preset JSON by name (without .json extension) in
     * search_dirs.  Returns the full path or empty string if not found.
     */
    static std::string find_preset_file(
        const std::string&              preset_name,
        const std::vector<std::string>& search_dirs);
};

} // namespace Slic3r

#endif // slic3r_CliPresetResolver_hpp_
