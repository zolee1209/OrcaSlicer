"""Közös segédfüggvények a fork/tools scriptekhez. Csak olvas, semmit nem módosít."""

import fnmatch
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FEATURES_FILE = os.path.join(REPO, "fork", "features.yaml")
PROFILES_DIR = "resources/profiles"


def git(*args, check=True, ok_codes=(0,)):
    proc = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    if check and proc.returncode not in ok_codes:
        raise RuntimeError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc


def git_out(*args, **kw):
    return git(*args, **kw).stdout.strip()


def git_lines(*args, **kw):
    out = git(*args, **kw).stdout
    return [line for line in out.split("\n") if line]


def git_z(*args):
    out = git(*args).stdout
    return [x for x in out.split("\0") if x]


def ref_exists(ref):
    return git("rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def load_config():
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML hiányzik: pip install pyyaml")
    with open(FEATURES_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def upstream_ref(cfg):
    s = cfg.get("sync", {})
    return f"{s.get('upstream_remote', 'upstream')}/{s.get('upstream_branch', 'main')}"


def match_glob(path, pattern):
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return path == base or path.startswith(base + "/")
    return fnmatch.fnmatchcase(path, pattern)


def match_any(path, patterns):
    return any(match_glob(path, p) for p in patterns)


def path_in(path, entry):
    """A path egyezik egy features.yaml fájl/mappa bejegyzéssel (mappánál prefix)."""
    entry = entry.rstrip("/")
    return path == entry or path.startswith(entry + "/")


def features_for_path(cfg, path):
    hits = []
    for f in cfg.get("features", []):
        for key in ("owned_files", "hooks"):
            if any(path_in(path, e) for e in f.get(key) or []):
                hits.append(f["id"])
                break
    return hits


def profile_rules(cfg):
    """(keep, keep_upstream) a profiles-vendor-prune bejegyzésből, resources/profiles-hoz relatív nevekkel."""
    for f in cfg.get("features", []):
        if f["id"] == "profiles-vendor-prune":
            return list(f.get("keep") or []), list(f.get("keep_upstream") or [])
    return [], []


def profile_bucket(cfg, path):
    """resources/profiles alatti útvonal besorolása: 'keep' | 'keep_upstream' | 'prune' | None (nem profil)."""
    if not path.startswith(PROFILES_DIR + "/"):
        return None
    rel = path[len(PROFILES_DIR) + 1:]
    top = rel.split("/", 1)[0]
    keep, keep_up = profile_rules(cfg)
    if top in keep:
        return "keep"
    if top in keep_up:
        return "keep_upstream"
    return "prune"


def is_protected(cfg, path):
    return match_any(path, cfg.get("sync", {}).get("protected") or [])
