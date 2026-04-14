#include "CliPresetResolver.hpp"

#include <boost/filesystem.hpp>
#include <boost/log/trivial.hpp>
#include <boost/algorithm/string/predicate.hpp>

#include "Utils.hpp"  // resources_dir()

namespace Slic3r {

namespace fs = boost::filesystem;

// ---------------------------------------------------------------------------
// find_preset_file
// ---------------------------------------------------------------------------
std::string CliPresetResolver::find_preset_file(
    const std::string&              preset_name,
    const std::vector<std::string>& search_dirs)
{
    const std::string filename = preset_name + ".json";
    for (const auto& dir : search_dirs) {
        fs::path candidate = fs::path(dir) / filename;
        if (fs::exists(candidate))
            return candidate.string();
    }
    return {};
}

// ---------------------------------------------------------------------------
// load_one – raw single-file load, no inherits resolution
// ---------------------------------------------------------------------------
bool CliPresetResolver::load_one(
    const std::string&                  file,
    ForwardCompatibilitySubstitutionRule rule,
    DynamicPrintConfig&                 out_config,
    std::string&                        out_inherits,
    std::string&                        out_reason)
{
    std::map<std::string, std::string> key_values;
    out_config.load_from_json(file, rule, key_values, out_reason);
    if (!out_reason.empty()) {
        BOOST_LOG_TRIVIAL(error) << "CliPresetResolver: failed to load " << file
                                 << ": " << out_reason;
        return false;
    }

    // Extract the inherits value if present
    auto it = key_values.find("inherits");
    if (it != key_values.end())
        out_inherits = it->second;
    else
        out_inherits.clear();

    // Also check the config option directly (some loaders put it there)
    if (out_inherits.empty()) {
        const ConfigOption* opt = out_config.option("inherits");
        if (opt) {
            const ConfigOptionString* s = dynamic_cast<const ConfigOptionString*>(opt);
            if (s && !s->value.empty())
                out_inherits = s->value;
        }
    }

    return true;
}

// ---------------------------------------------------------------------------
// resolve – recursive inherits chain resolver
// ---------------------------------------------------------------------------
bool CliPresetResolver::resolve(
    const std::string&                  file,
    ForwardCompatibilitySubstitutionRule rule,
    DynamicPrintConfig&                 out_config,
    std::string&                        out_reason,
    const std::vector<std::string>&     extra_search_dirs)
{
    // Build the search path list:
    //   1. Directory of the input file itself
    //   2. All extra search dirs provided by caller
    //   3. All vendor sub-directories under resources/profiles/
    std::vector<std::string> search_dirs;

    const fs::path file_dir = fs::path(file).parent_path();
    search_dirs.push_back(file_dir.string());

    for (const auto& d : extra_search_dirs)
        search_dirs.push_back(d);

    // Walk resources/profiles/<vendor>/<type>/ directories
    const fs::path profiles_root = fs::path(resources_dir()) / "profiles";
    if (fs::is_directory(profiles_root)) {
        for (const auto& vendor_entry : fs::directory_iterator(profiles_root)) {
            if (!fs::is_directory(vendor_entry)) continue;
            for (const auto& type_entry : fs::directory_iterator(vendor_entry)) {
                if (fs::is_directory(type_entry))
                    search_dirs.push_back(type_entry.path().string());
            }
        }
    }

    // ------------------------------------------------------------------
    // Walk the inherits chain bottom-up, collecting each layer.
    // Layer 0 = the file the user specified.
    // Layer N = the root ancestor with no inherits.
    // We then apply them top-down (root first, leaf last).
    // ------------------------------------------------------------------
    struct Layer {
        std::string        file;
        DynamicPrintConfig config;
    };
    std::vector<Layer> layers;

    std::string current_file = file;
    int depth = 0;

    while (!current_file.empty() && depth < kMaxDepth) {
        Layer layer;
        layer.file = current_file;
        std::string inherits_name;

        if (!load_one(current_file, rule, layer.config, inherits_name, out_reason))
            return false;

        BOOST_LOG_TRIVIAL(debug) << "CliPresetResolver: loaded " << current_file
                                 << (inherits_name.empty() ? "" : " (inherits: " + inherits_name + ")");

        layers.push_back(std::move(layer));

        if (inherits_name.empty())
            break; // reached the root

        // Find the parent file
        current_file = find_preset_file(inherits_name, search_dirs);
        if (current_file.empty()) {
            BOOST_LOG_TRIVIAL(warning) << "CliPresetResolver: cannot find parent preset '"
                                       << inherits_name << "' for " << layers.back().file
                                       << " – using partial config";
            break;
        }
        ++depth;
    }

    if (depth >= kMaxDepth) {
        BOOST_LOG_TRIVIAL(warning) << "CliPresetResolver: inherits chain too deep (>= "
                                   << kMaxDepth << ") for " << file << ", stopping";
    }

    // ------------------------------------------------------------------
    // Merge top-down: root (last layer) provides the base; each child
    // overrides with its own keys.
    // ------------------------------------------------------------------
    out_config.clear();

    // Apply root first
    for (int i = (int)layers.size() - 1; i >= 0; --i) {
        // apply(other, true) = overwrite only keys present in other
        out_config.apply(layers[i].config, true);
    }

    // Keep the top-level "inherits" value (layer[0] = the original file) in the
    // resolved config so callers can read the direct parent name (e.g. to set
    // new_printer_system_name for compatibility checks).  The slicing engine
    // ignores unknown string options, so leaving it in is safe.

    BOOST_LOG_TRIVIAL(info) << "CliPresetResolver: resolved " << file
                            << " through " << layers.size() << " layer(s)";
    return true;
}

} // namespace Slic3r
