#!/usr/bin/env python3
"""Szinkron-riport: mit hozna a mainline, és mi ütközne a forkkal. AI nélküli előszűrés.

Alapból csak olvas. A --fetch kapcsoló lefuttatja a `git fetch <upstream>`-et (csak a távoli
követő refeket frissíti). A --out a riportot fájlba is kiírja.

Használat:
  python3 fork/tools/sync-report.py [--fetch] [--target upstream/main] [--out fájl.md]
"""

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from forklib import (git, git_lines, git_out, features_for_path, is_protected, load_config,
                     match_any, profile_bucket, upstream_ref, PROFILES_DIR)


def classify_conflict(cfg, path):
    b = profile_bucket(cfg, path)
    if b == "prune":
        return "auto: törlés (profiles-vendor-prune)"
    if is_protected(cfg, path):
        return "auto: fork verziója (védett)"
    if b == "keep_upstream":
        return "auto: upstream verziója (keep_upstream)"
    feats = features_for_path(cfg, path)
    return "kézi: " + (", ".join(feats) if feats else "nincs funkcióhoz rendelve")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="git fetch az upstream remote-ról a riport előtt")
    ap.add_argument("--target", help="cél ref (alap: features.yaml sync.upstream_remote/branch)")
    ap.add_argument("--out", help="riport mentése ide is")
    ap.add_argument("--max-commits", type=int, default=8, help="fájlonként listázott upstream commitok")
    args = ap.parse_args()

    cfg = load_config()
    target = args.target or upstream_ref(cfg)
    ignore = cfg.get("sync", {}).get("ignore") or []
    if args.fetch:
        git("fetch", target.split("/")[0])

    out = []
    p = out.append
    base = git_out("merge-base", "HEAD", target)
    head = git_out("rev-parse", "--short=10", "HEAD")
    p(f"# Szinkron-riport: `{git_out('branch', '--show-current') or head}` → `{target}`\n")
    p(f"- Közös pont: `{base[:10]}` ({git_out('log', '-1', '--format=%cs', base)})")
    p(f"- Cél: `{git_out('rev-parse', '--short=10', target)}` ({git_out('log', '-1', '--format=%cs', target)})")
    p(f"- Mainline commitok: {git_out('rev-list', '--count', f'{base}..{target}')} "
      f"(első szülős / PR: {git_out('rev-list', '--first-parent', '--count', f'{base}..{target}')})")
    tags = git_lines("for-each-ref", "--format=%(refname:short)", "--merged", target, "--no-merged", base, "refs/tags")
    if tags:
        p(f"- Új release tagek: {', '.join(tags[-10:])}")

    fork_files = set(git_lines("diff", "--name-only", "--no-renames", base, "HEAD"))
    up_files = set(git_lines("diff", "--name-only", "--no-renames", base, target))

    def relevant(path):
        b = profile_bucket(cfg, path)
        if b == "prune":
            return False
        if b in ("keep", "keep_upstream"):
            return True
        return not match_any(path, ignore)

    # 1. Előrejelzett ütközések (merge-szimuláció; a rebase commitonként ennél többet is adhat)
    p("\n## 1. Előrejelzett ütközések\n")
    mt = git("merge-tree", "--write-tree", "--name-only", "--no-messages", "HEAD", target, check=False)
    conflicted = mt.stdout.split("\n")[1:] if mt.returncode == 1 else []
    conflicted = [c for c in conflicted if c]
    if mt.returncode not in (0, 1):
        p(f"merge-tree hiba: {mt.stderr.strip()}")
    groups = defaultdict(list)
    for c in conflicted:
        groups[classify_conflict(cfg, c)].append(c)
    if not conflicted:
        p("Nincs előrejelzett ütközés.")
    for g in sorted(groups, key=lambda k: (not k.startswith("kézi"), k)):
        files = groups[g]
        p(f"- **{g}**: {len(files)} fájl")
        if g.startswith("kézi"):
            for f in files:
                p(f"  - `{f}`")

    # 2. Upstream változások a mi fájljainkban, funkciónként
    p("\n## 2. Upstream változások a fork által érintett fájlokban\n")
    overlap = sorted(f for f in fork_files & up_files if relevant(f) and not is_protected(cfg, f))
    by_feat = defaultdict(list)
    for f in overlap:
        for feat in features_for_path(cfg, f) or ["(nincs funkcióhoz rendelve)"]:
            by_feat[feat].append(f)
    if not overlap:
        p("Nincs átfedés.")
    for feat in sorted(by_feat):
        p(f"### {feat}")
        for f in by_feat[feat]:
            commits = git_lines("log", "--first-parent", "--format=%h %cs %s", f"{base}..{target}", "--", f)
            p(f"- `{f}` – {len(commits)} upstream PR/commit")
            for c in commits[:args.max_commits]:
                p(f"  - {c}")
            if len(commits) > args.max_commits:
                p(f"  - … +{len(commits) - args.max_commits}")

    # 3. Funkciók átfedés nélkül
    touched = set(by_feat)
    quiet = [f["id"] for f in cfg.get("features", []) if f["id"] not in touched and f.get("status") != "superseded"]
    p("\n## 3. Funkciók upstream átfedés nélkül\n")
    p(", ".join(f"`{q}`" for q in quiet) or "–")

    # 4. Automatikusan kezelt területek
    p("\n## 4. Automatikusan kezelt / figyelmen kívül hagyott területek\n")
    prot = sorted(f for f in up_files if is_protected(cfg, f))
    p(f"- Védett fájlok, upstream változás ELDOBVA (fork verziója marad): {len(prot)}")
    for f in prot[:15]:
        p(f"  - `{f}`")
    if len(prot) > 15:
        p(f"  - … +{len(prot) - 15}")
    base_vendors = {l.rsplit('/', 1)[-1] for l in git_lines("ls-tree", "-d", "--name-only", base, PROFILES_DIR + "/")}
    new_vendors = sorted({l.rsplit('/', 1)[-1] for l in git_lines("ls-tree", "-d", "--name-only", target, PROFILES_DIR + "/")}
                         - base_vendors)
    pruned_up = sum(1 for f in up_files if profile_bucket(cfg, f) == "prune")
    p(f"- Más gyártók profiljai: {pruned_up} upstream változás figyelmen kívül"
      + (f"; új gyártómappák (rebase után törlendők): {', '.join(new_vendors)}" if new_vendors else ""))
    keep_up = sorted(f for f in up_files if profile_bucket(cfg, f) == "keep_upstream")
    p(f"- keep_upstream profilok (OrcaFilamentLibrary, Custom): {len(keep_up)} upstream változás, automatikusan átjön")
    ign = sum(1 for f in up_files if profile_bucket(cfg, f) is None and match_any(f, ignore))
    p(f"- `sync.ignore` szerint kihagyott egyéb fájlok: {ign}")
    other = sorted(f for f in up_files - fork_files if relevant(f) and profile_bucket(cfg, f) is None)
    p(f"- Upstream-only változás (nem ütközik, nem a mi kódunk): {len(other)} fájl")

    text = "\n".join(out) + "\n"
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
