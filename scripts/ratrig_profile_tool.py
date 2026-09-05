#!/usr/bin/env python3
"""Bulk editor / sync tool for the Ratrig vendor profile pack
(resources/profiles/Ratrig + resources/profiles/Ratrig.json).

Problem it solves: hundreds of machine/process json files share values that
should be identical (or deliberately scaled) across siblings, and hand-editing
each file is error-prone. This tool lets you inspect, bulk-set, and sync
specific keys across many profiles at once, and can also "promote" a preset
you tweaked and saved inside OrcaSlicer's own GUI (a user preset, which only
contains the keys you actually changed) back into the vendor files.

Every mutating command bumps Ratrig.json's version (unless --no-bump) and
runs `validate` afterwards.

Examples
--------
Show a key's value across all 0.4mm process profiles (spot divergence):
    ./ratrig_profile_tool.py show bridge_speed --type process --pattern "*0.4*"

Bulk-set a key on all IDEX machine profiles:
    ./ratrig_profile_tool.py set retraction_speed '["140"]' --type machine --pattern "*IDEX*"

Copy specific keys from one machine profile onto its siblings:
    ./ratrig_profile_tool.py sync --source "RatRig V-Core 4 IDEX 500 0.4 nozzle" \\
        --keys machine_max_acceleration_x,machine_max_acceleration_y \\
        --type machine --pattern "RatRig V-Core 4 IDEX 500 * nozzle"

Promote a preset you saved from OrcaSlicer's own GUI onto its vendor siblings:
    ./ratrig_profile_tool.py promote --name "My Tweaked Process" --type process \\
        --target-pattern "*0.4*"

Just validate the current state:
    ./ratrig_profile_tool.py validate
"""
import argparse
import fnmatch
import json
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO_ROOT / "resources" / "profiles"
VENDOR_NAME = "Ratrig"
VENDOR_JSON = PROFILES_DIR / f"{VENDOR_NAME}.json"
VENDOR_DIR = PROFILES_DIR / VENDOR_NAME

TYPE_TO_SECTION = {
    "machine_model": "machine_model_list",
    "machine": "machine_list",
    "process": "process_list",
    "filament": "filament_list",
}
EXPECTED_TYPE = {v: k for k, v in TYPE_TO_SECTION.items()}

# Preset-level metadata that is never a "value" to sync/promote.
METADATA_KEYS = {
    "type", "name", "from", "setting_id", "instantiation", "inherits",
    "compatible_printers", "compatible_printers_condition", "version",
    "filament_id", "base_id", "print_settings_id", "filament_settings_id",
    "printer_settings_id", "renamed_from", "alias", "update_time",
}

USER_TYPE_DIR = {"machine": "machine", "process": "process", "filament": "filament"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp, object_pairs_hook=OrderedDict)


def dump_json(path, data, *, indent, trailing_newline):
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(text)


def file_style(path):
    """(indent, trailing_newline) matching this repo's on-disk convention."""
    if path.parent.name == "filament":
        return 2, True
    return 4, False


def parse_value(raw):
    """Parse a CLI value as JSON (so numbers/lists/bools work); fall back to raw string."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


class ProfileGraph:
    def __init__(self):
        self.manifest = load_json(VENDOR_JSON)
        self.entries = {}  # (section, name) -> {"sub_path", "path", "content"}
        for section in TYPE_TO_SECTION.values():
            for e in self.manifest.get(section, []):
                path = VENDOR_DIR / e["sub_path"]
                self.entries[(section, e["name"])] = {
                    "sub_path": e["sub_path"],
                    "path": path,
                    "content": load_json(path),
                }

    def iter_type(self, type_):
        section = TYPE_TO_SECTION[type_]
        for (sec, name), info in self.entries.items():
            if sec == section:
                yield name, info

    def matching(self, type_, pattern):
        for name, info in self.iter_type(type_):
            if pattern is None or fnmatch.fnmatch(name, pattern):
                yield name, info

    def find_by_name(self, name):
        for (_sec, n), info in self.entries.items():
            if n == name:
                return info
        return None

    def save_entry(self, info):
        indent, nl = file_style(info["path"])
        dump_json(info["path"], info["content"], indent=indent, trailing_newline=nl)

    def bump_version(self):
        version = self.manifest.get("version", "0.0.0.0")
        parts = version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)
        self.manifest["version"] = new_version
        dump_json(VENDOR_JSON, self.manifest, indent=4, trailing_newline=False)
        return version, new_version


def cmd_show(args, graph):
    rows = sorted(graph.matching(args.type, args.pattern))
    if not rows:
        print("No matching profiles.")
        return
    by_value = defaultdict(list)
    for name, info in rows:
        val = info["content"].get(args.key, "<missing>")
        by_value[json.dumps(val, sort_keys=True)].append(name)

    print(f"Key: {args.key}   ({len(rows)} matching '{args.type}' profiles)")
    print(f"Distinct values: {len(by_value)}")
    for val_json, names in sorted(by_value.items(), key=lambda kv: -len(kv[1])):
        val = json.loads(val_json)
        print(f"\n  value = {val!r}   ({len(names)} files)")
        for n in names:
            print(f"    - {n}")
    if len(by_value) > 1:
        print("\n[DIVERGENT] this key has more than one distinct value across the matched profiles.")


def cmd_set(args, graph):
    value = parse_value(args.value)
    changed = []
    for name, info in sorted(graph.matching(args.type, args.pattern)):
        old = info["content"].get(args.key, "<missing>")
        if old == value:
            continue
        changed.append((name, old, value))
        if not args.dry_run:
            info["content"][args.key] = value
            graph.save_entry(info)
    print(f"{'[DRY RUN] ' if args.dry_run else ''}{len(changed)} file(s) changed (key={args.key})")
    for name, old, new in changed:
        print(f"  {name}: {old!r} -> {new!r}")
    return len(changed)


def cmd_sync(args, graph):
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    source_info = graph.find_by_name(args.source)
    if source_info is None:
        src_path = Path(args.source)
        if not src_path.exists():
            print(f"ERROR: source '{args.source}' not found as a profile name or file path", file=sys.stderr)
            sys.exit(1)
        source_info = {"content": load_json(src_path), "path": src_path}

    source_name = source_info["content"].get("name")
    changed = []
    for name, info in sorted(graph.matching(args.type, args.pattern)):
        if name == source_name:
            continue
        for key in keys:
            if key not in source_info["content"]:
                print(f"WARNING: source has no key '{key}', skipping", file=sys.stderr)
                continue
            new_val = source_info["content"][key]
            old_val = info["content"].get(key, "<missing>")
            if old_val == new_val:
                continue
            changed.append((name, key, old_val, new_val))
            if not args.dry_run:
                info["content"][key] = new_val
        if not args.dry_run:
            graph.save_entry(info)
    print(f"{'[DRY RUN] ' if args.dry_run else ''}{len(changed)} key change(s) applied from '{args.source}'")
    for name, key, old, new in changed:
        print(f"  {name}.{key}: {old!r} -> {new!r}")
    return len(changed)


def find_user_preset_file(name, type_):
    user_root = Path.home() / ".config" / "OrcaSlicer" / "user"
    if not user_root.exists():
        return None
    candidates = []
    for user_dir in user_root.iterdir():
        if not user_dir.is_dir():
            continue
        p = user_dir / USER_TYPE_DIR[type_] / f"{name}.json"
        if p.exists():
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def cmd_promote(args, graph):
    if args.file:
        src_path = Path(args.file)
    else:
        if not args.name:
            print("ERROR: give either --name or --file", file=sys.stderr)
            sys.exit(1)
        src_path = find_user_preset_file(args.name, args.type)
        if src_path is None:
            print(f"ERROR: could not find a saved user preset named '{args.name}' of type "
                  f"'{args.type}' under ~/.config/OrcaSlicer/user/*/{USER_TYPE_DIR[args.type]}/",
                  file=sys.stderr)
            sys.exit(1)

    print(f"Reading saved user preset: {src_path}")
    src = load_json(src_path)
    overrides = {k: v for k, v in src.items() if k not in METADATA_KEYS}
    if not overrides:
        print("Nothing to promote -- the saved preset has no overridden keys vs. its parent.")
        return 0
    print(f"Overridden keys in '{src.get('name')}': {', '.join(overrides.keys())}")

    targets = []
    seen = set()
    for t in args.target:
        info = graph.find_by_name(t)
        if info is None:
            print(f"WARNING: target '{t}' not found among vendor profiles, skipping", file=sys.stderr)
            continue
        targets.append((t, info))
        seen.add(t)
    if args.target_pattern:
        for name, info in graph.matching(args.type, args.target_pattern):
            if name not in seen:
                targets.append((name, info))
                seen.add(name)
    if not targets:
        print("ERROR: no targets specified (use --target and/or --target-pattern)", file=sys.stderr)
        sys.exit(1)

    changed = []
    for name, info in sorted(targets):
        for key, val in overrides.items():
            old = info["content"].get(key, "<missing>")
            if old == val:
                continue
            changed.append((name, key, old, val))
            if not args.dry_run:
                info["content"][key] = val
        if not args.dry_run:
            graph.save_entry(info)
    print(f"{'[DRY RUN] ' if args.dry_run else ''}{len(changed)} key change(s) promoted to {len(targets)} target file(s)")
    for name, key, old, new in changed:
        print(f"  {name}.{key}: {old!r} -> {new!r}")
    return len(changed)


def run_structural_checks(graph):
    errors = []
    seen = defaultdict(list)
    for (sec, name) in graph.entries:
        seen[name].append(sec)
    for name, secs in seen.items():
        if len(secs) > 1:
            errors.append(f"name '{name}' appears in multiple sections: {secs}")

    machine_names = {n for (s, n) in graph.entries if s == "machine_list"}
    counts = defaultdict(list)
    for (sec, name), info in graph.entries.items():
        t = info["content"].get("type")
        if t != EXPECTED_TYPE[sec]:
            errors.append(f"[{sec}] '{name}' has type={t!r}, expected {EXPECTED_TYPE[sec]!r}")
        if sec == "process_list":
            for cp in (info["content"].get("compatible_printers") or []):
                if cp not in machine_names:
                    errors.append(f"process '{name}' references unknown printer '{cp}'")
                counts[cp].append(name)

    for name, info in graph.iter_type("machine"):
        if str(info["content"].get("instantiation", "")).lower() != "true":
            continue
        n = len(counts.get(name, []))
        if n != 4:
            errors.append(f"machine '{name}' has {n} compatible process(es) (expected 4)")

    return errors


def cmd_validate(graph):
    errors = run_structural_checks(graph)
    if errors:
        print(f"[STRUCTURAL] {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("[STRUCTURAL] OK")

    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "orca_extra_profile_check.py"),
         "--vendor", VENDOR_NAME, "--check-filaments", "--check-materials", "--check-obsolete-keys"],
        capture_output=True, text=True,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        errors.append("orca_extra_profile_check.py reported errors")
    return errors


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="show a key's value across matching profiles")
    p_show.add_argument("key")
    p_show.add_argument("--type", required=True, choices=sorted(TYPE_TO_SECTION))
    p_show.add_argument("--pattern", default=None, help="fnmatch glob on profile name")

    p_set = sub.add_parser("set", help="bulk-set a key to a value across matching profiles")
    p_set.add_argument("key")
    p_set.add_argument("value", help="new value; parsed as JSON if possible, else raw string")
    p_set.add_argument("--type", required=True, choices=sorted(TYPE_TO_SECTION))
    p_set.add_argument("--pattern", default=None, help="fnmatch glob on profile name")
    p_set.add_argument("--dry-run", action="store_true")
    p_set.add_argument("--no-bump", action="store_true")

    p_sync = sub.add_parser("sync", help="copy specific keys from one profile onto matching targets")
    p_sync.add_argument("--source", required=True, help="profile name or file path to copy values FROM")
    p_sync.add_argument("--keys", required=True, help="comma-separated list of keys to copy")
    p_sync.add_argument("--type", required=True, choices=sorted(TYPE_TO_SECTION))
    p_sync.add_argument("--pattern", default=None, help="glob restricting targets (source is always skipped)")
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--no-bump", action="store_true")

    p_promote = sub.add_parser("promote", help="apply a saved OrcaSlicer user preset's overrides onto vendor files")
    p_promote.add_argument("--name", help="user preset name (auto-located under ~/.config/OrcaSlicer/user)")
    p_promote.add_argument("--file", help="explicit path to a saved user preset json (overrides --name)")
    p_promote.add_argument("--type", required=True, choices=["machine", "process", "filament"])
    p_promote.add_argument("--target", action="append", default=[], help="exact vendor profile name (repeatable)")
    p_promote.add_argument("--target-pattern", default=None, help="glob on vendor profile names")
    p_promote.add_argument("--dry-run", action="store_true")
    p_promote.add_argument("--no-bump", action="store_true")

    sub.add_parser("validate", help="run structural + official profile checks")

    return parser


def main():
    args = build_parser().parse_args()

    if args.command == "validate":
        errors = cmd_validate(ProfileGraph())
        sys.exit(1 if errors else 0)

    graph = ProfileGraph()
    if args.command == "show":
        cmd_show(args, graph)
        return

    if args.command == "set":
        n = cmd_set(args, graph)
    elif args.command == "sync":
        n = cmd_sync(args, graph)
    elif args.command == "promote":
        n = cmd_promote(args, graph)
    else:
        raise AssertionError(args.command)

    if n and not args.dry_run and not args.no_bump:
        old_v, new_v = graph.bump_version()
        print(f"\nBumped {VENDOR_NAME}.json version: {old_v} -> {new_v}")

    if n and not args.dry_run:
        print()
        errors = cmd_validate(graph)
        if errors:
            sys.exit(1)


if __name__ == "__main__":
    main()
