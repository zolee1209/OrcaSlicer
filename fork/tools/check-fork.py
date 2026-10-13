#!/usr/bin/env python3
"""A fork nyilvántartás (fork/features.yaml) és a kód összhangjának ellenőrzése. Csak olvas.

Ellenőrzi:
  - features.yaml: kötelező mezők, egyedi id-k, érvényes státusz, létező fájlok, elérhető commitok
  - kódcímkék: // FORK(<id>) vagy # FORK(<id>), BEGIN/END párok, ismeretlen id-k
  - címkézetlen funkciók (van upstream fájlba nyúló hook, de nincs FORK címke)
  - commitok [fork:<id>] előtag nélkül a mainline közös pont óta
  - védett fájlok nem commitolt módosítása

Kilépési kód: 1, ha HIBA van (figyelmeztetésnél 0).
Használat:  python3 fork/tools/check-fork.py [--strict]   (--strict: a figyelmeztetés is hiba)
"""

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from forklib import (git, git_lines, git_out, git_z, is_protected, load_config, ref_exists,
                     upstream_ref, REPO)

STATUSES = {"fork-only", "superseded", "dropped"}
TAG_RE = re.compile(r"FORK\(([a-z0-9][a-z0-9-]*)\)(?:\s+(BEGIN|END))?")
# Ezekben a fájlokban a címke csak dokumentáció, nem kódjelölés.
DOC_PATHS = ("fork/", ".github/instructions/orca-fork.instructions.md", ".github/skills/orca-fork/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    errors, warnings, infos = [], [], []
    feats = cfg.get("features") or []

    # features.yaml
    ids = [f.get("id") for f in feats]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"features.yaml: duplikált id: {dup}")
    for f in feats:
        fid = f.get("id", "?")
        for key in ("id", "name", "status"):
            if not f.get(key):
                errors.append(f"features.yaml [{fid}]: hiányzó mező: {key}")
        if f.get("status") not in STATUSES:
            errors.append(f"features.yaml [{fid}]: érvénytelen status: {f.get('status')}")
        # A hook lehet törölt upstream fájl is (pl. profiles-vendor-prune), ezért csak az owned_files-t nézzük.
        for p in f.get("owned_files") or []:
            if not os.path.exists(os.path.join(REPO, p)) and f.get("status") == "fork-only":
                warnings.append(f"[{fid}] owned_files: nem létezik: {p}")
        for c in f.get("commits") or []:
            if not ref_exists(f"{c}^{{commit}}"):
                warnings.append(f"[{fid}] commit nem található: {c}")
            elif git("merge-base", "--is-ancestor", c, "HEAD", check=False).returncode != 0:
                infos.append(f"[{fid}] commit nem része a HEAD-nek (rebase után várható): {c}")

    # Kódcímkék
    grep = git("grep", "-n", "-I", "-E", r"FORK\([a-z0-9-]+\)", check=False, ok_codes=(0, 1))
    tagged = defaultdict(set)
    open_blocks = defaultdict(list)
    for line in grep.stdout.splitlines():
        path, lineno, text = line.split(":", 2)
        if path.startswith(DOC_PATHS):
            continue
        for m in TAG_RE.finditer(text):
            tid, kind = m.group(1), m.group(2)
            if tid not in ids:
                errors.append(f"{path}:{lineno}: ismeretlen funkció-id a címkében: {tid}")
            tagged[tid].add(path)
            if kind == "BEGIN":
                open_blocks[(path, tid)].append(lineno)
            elif kind == "END":
                if open_blocks[(path, tid)]:
                    open_blocks[(path, tid)].pop()
                else:
                    errors.append(f"{path}:{lineno}: FORK({tid}) END nyitó BEGIN nélkül")
    for (path, tid), lines in open_blocks.items():
        for ln in lines:
            errors.append(f"{path}:{ln}: FORK({tid}) BEGIN lezáró END nélkül")

    code_ext = (".cpp", ".hpp", ".h", ".c", ".cmake", ".txt", ".sh", ".in", ".py")
    for f in feats:
        if f.get("status") != "fork-only":
            continue
        hooks = [h for h in f.get("hooks") or [] if h.endswith(code_ext) or os.path.basename(h) == "build_linux.sh"]
        if hooks and f["id"] not in tagged:
            warnings.append(f"[{f['id']}] címkézetlen: upstream fájlba nyúlik ({', '.join(hooks[:3])}"
                            f"{'…' if len(hooks) > 3 else ''}), de nincs FORK({f['id']}) címke")
        missing = [h for h in hooks if f["id"] in tagged and h not in tagged[f["id"]]]
        for h in missing:
            warnings.append(f"[{f['id']}] a hook fájlban nincs címke: {h}")

    # Commit-előtagok
    up = upstream_ref(cfg)
    if ref_exists(up):
        base = git_out("merge-base", "HEAD", up)
        subjects = git_lines("log", "--format=%h %s", f"{base}..HEAD")
        bad = [s for s in subjects if not s.split(" ", 1)[1].startswith("[fork:")]
        if bad:
            warnings.append(f"{len(bad)}/{len(subjects)} saját commit [fork:<id>] előtag nélkül (pl. {bad[0]})")
        for s in subjects:
            m = re.match(r"\S+ \[fork:([a-z0-9-]+)\]", s)
            if m and m.group(1) not in ids and m.group(1) != "meta":
                errors.append(f"commit ismeretlen funkció-id-vel: {s}")

    # Védett fájlok
    changed = git_z("diff", "-z", "--name-only", "HEAD")
    prot = [p for p in changed if is_protected(cfg, p)]
    if prot:
        warnings.append(f"Védett fájl módosult (csak kifejezett utasításra szabad): {len(prot)} – pl. {prot[0]}")

    for title, items in (("HIBA", errors), ("FIGYELMEZTETÉS", warnings), ("INFO", infos)):
        if items:
            print(f"## {title} ({len(items)})")
            for i in items:
                print(f"- {i}")
            print()
    print(f"Összesen: {len(errors)} hiba, {len(warnings)} figyelmeztetés, {len(infos)} info")
    sys.exit(1 if errors or (args.strict and warnings) else 0)


if __name__ == "__main__":
    main()
