#!/usr/bin/env python3
"""A profilszabályok végrehajtása (profiles-vendor-prune, profiles-ratrig).

Alapból SZÁRAZ FUTÁS: csak kiírja, mit tenne. Változtatni csak --apply-jal lehet. Soha nem commitol.

Szabályok (fork/features.yaml):
  keep           (Ratrig)                        – mindig a fork verziója, tartalmához a script nem nyúl
  keep_upstream  (OrcaFilamentLibrary, Custom)   – az upstream verziója
  minden más gyártó                              – törlendő a gitből

Módok:
  (nincs kapcsoló)          állapot: mi van most a fában a szabályokhoz képest
  --resolve-conflicts       rebase/merge közben: a resources/profiles alatti ütközések feloldása a szabályok szerint
  --prune                   a nem megtartott gyártók fájljainak törlése a gitből (pl. rebase után új upstream gyártók)
  --restore-ratrig REF      a védett Ratrig fájlok pontos visszaállítása REF állapotára (rebase után)

Példa:
  python3 fork/tools/prune-profiles.py --resolve-conflicts            # szárazon
  python3 fork/tools/prune-profiles.py --resolve-conflicts --apply
  python3 fork/tools/prune-profiles.py --restore-ratrig backup/pre-rebase-2026-10-13 --apply
"""

import argparse
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from forklib import (git_lines, git_out, git_z, is_protected, load_config, profile_bucket,
                     PROFILES_DIR, REPO)


def run_pathspec(args, paths, apply):
    """git <args> a megadott útvonalakra; száraz futásnál nem csinál semmit."""
    if not paths or not apply:
        return
    # A "--" elválasztó és a --pathspec-from-file nem használható együtt.
    args = [a for a in args if a != "--"]
    proc = subprocess.run(["git", "-C", REPO, *args, "--pathspec-from-file=-", "--pathspec-file-nul"],
                          input="\0".join(paths), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"git {' '.join(args)} hiba: {proc.stderr.strip()}")


def in_progress():
    if os.path.exists(git_out("rev-parse", "--git-path", "rebase-merge")) or \
       os.path.exists(git_out("rev-parse", "--git-path", "rebase-apply")) or \
       os.path.exists(git_out("rev-parse", "--git-path", "CHERRY_PICK_HEAD")):
        return "rebase"
    if os.path.exists(git_out("rev-parse", "--git-path", "MERGE_HEAD")):
        return "merge"
    return None


def resolve_conflicts(cfg, apply):
    mode = in_progress()
    if not mode:
        sys.exit("Nincs folyamatban rebase vagy merge.")
    # Rebase-nél az "ours" (2) az upstream alapú új történet, a "theirs" (3) a fork commit.
    # Merge-nél (upstream behúzása a fork ágba) fordítva.
    fork_stage, up_stage = ("3", "2") if mode == "rebase" else ("2", "3")
    stages = {}
    for e in git_z("ls-files", "-u", "-z", "--", PROFILES_DIR):
        meta, path = e.split("\t", 1)
        stages.setdefault(path, set()).add(meta.split()[2])
    take_fork, take_up, remove, untouched = [], [], [], []
    for path, st in sorted(stages.items()):
        bucket = profile_bucket(cfg, path)
        if bucket == "prune":
            remove.append(path)
        elif bucket == "keep" or is_protected(cfg, path):
            (take_fork if fork_stage in st else remove).append(path)
        elif bucket == "keep_upstream":
            (take_up if up_stage in st else remove).append(path)
        else:
            untouched.append(path)
    side = {"2": "--ours", "3": "--theirs"}
    print(f"[{mode}] profil-ütközések: {len(stages)}")
    print(f"  fork verziója (keep/védett): {len(take_fork)}")
    print(f"  upstream verziója (keep_upstream): {len(take_up)}")
    print(f"  törlés: {len(remove)}")
    if untouched:
        print(f"  NEM kezelt: {len(untouched)}")
    for path in take_fork[:20]:
        print(f"    fork  {path}")
    run_pathspec(["checkout", side[fork_stage], "--"], take_fork, apply)
    run_pathspec(["checkout", side[up_stage], "--"], take_up, apply)
    run_pathspec(["add", "--"], take_fork + take_up, apply)
    run_pathspec(["rm", "-q", "-f", "--"], remove, apply)
    fork_ref = "HEAD" if mode == "merge" else "<a rebase előtti fork-ág, pl. backup/...>"
    print("FIGYELEM: a nem ütköző upstream változások a védett Ratrig fájlokba is beolvadhattak.")
    print(f"  Rebase/merge befejezése után: prune-profiles.py --restore-ratrig {fork_ref} --apply")
    remaining = [r for r in git_lines("diff", "--name-only", "--diff-filter=U") if profile_bucket(cfg, r) is None]
    print(f"Profilokon kívüli ütközés (kézi feloldás kell): {len(remaining)}")
    for r in remaining:
        print(f"    {r}")


def prune(cfg, apply):
    tracked = git_z("ls-files", "-z", "--", PROFILES_DIR)
    remove = [p for p in tracked if profile_bucket(cfg, p) == "prune"]
    vendors = Counter(p[len(PROFILES_DIR) + 1:].split("/", 1)[0] for p in remove)
    print(f"Törlendő profilfájlok: {len(remove)} ({len(vendors)} gyártó/bejegyzés)")
    for v, n in sorted(vendors.items()):
        print(f"  {n:6d}  {v}")
    run_pathspec(["rm", "-q", "-f", "--"], remove, apply)


def restore_ratrig(cfg, ref, apply):
    prot = cfg.get("sync", {}).get("protected") or []
    roots = sorted({p[:-3] if p.endswith("/**") else p for p in prot})
    in_ref = set(git_z("ls-tree", "-r", "-z", "--name-only", ref, "--", *roots))
    now = set(git_z("ls-files", "-z", "--", *roots))
    changed = git_lines("diff", "--name-only", ref, "--", *roots)
    extra = sorted(now - in_ref)
    print(f"Védett fájlok eltérése {ref}-hez képest: {len(changed)} (ebből {len(extra)} nincs meg {ref}-ben)")
    for c in changed[:30]:
        print(f"    {c}")
    run_pathspec(["rm", "-q", "-f", "--"], extra, apply)
    run_pathspec(["checkout", ref, "--"], sorted(in_ref), apply)


def status(cfg):
    tracked = git_z("ls-files", "-z", "--", PROFILES_DIR)
    c = Counter(profile_bucket(cfg, p) for p in tracked)
    print(f"Profilfájlok a gitben: keep={c['keep']}  keep_upstream={c['keep_upstream']}  törlendő={c['prune']}")
    if c["prune"]:
        print("  → --prune --apply eltávolítaná a nem megtartott gyártókat")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--resolve-conflicts", action="store_true")
    g.add_argument("--prune", action="store_true")
    g.add_argument("--restore-ratrig", metavar="REF")
    ap.add_argument("--apply", action="store_true", help="végrehajtás (enélkül száraz futás)")
    a = ap.parse_args()
    cfg = load_config()
    if a.resolve_conflicts:
        resolve_conflicts(cfg, a.apply)
    elif a.prune:
        prune(cfg, a.apply)
    elif a.restore_ratrig:
        restore_ratrig(cfg, a.restore_ratrig, a.apply)
    else:
        status(cfg)
    if not a.apply and (a.resolve_conflicts or a.prune or a.restore_ratrig):
        print("\n(száraz futás – semmi nem változott; végrehajtás: --apply)")


if __name__ == "__main__":
    main()
