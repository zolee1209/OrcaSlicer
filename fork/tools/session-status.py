#!/usr/bin/env python3
"""Session eleji állapotjelentés a forkról. Csak olvas: nem fetchel, nem módosít semmit.

Használat:  python3 fork/tools/session-status.py
"""

import datetime as dt
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from forklib import (git, git_lines, git_out, git_z, is_protected, features_for_path,
                     load_config, profile_bucket, ref_exists, upstream_ref)


def days_ago(ts):
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromtimestamp(ts, dt.timezone.utc)).days


def main():
    cfg = load_config()
    up = upstream_ref(cfg)
    cadence = int(cfg.get("sync", {}).get("cadence_days", 30))
    questions = []

    branch = git_out("branch", "--show-current") or "(detached HEAD)"
    head = git_out("log", "-1", "--format=%h %s")
    print("# Fork session-állapot\n")
    print(f"- Ág: `{branch}` @ {head}")

    for name, label in (("rebase-merge", "REBASE"), ("rebase-apply", "REBASE"), ("MERGE_HEAD", "MERGE"),
                        ("CHERRY_PICK_HEAD", "CHERRY-PICK")):
        if os.path.exists(git_out("rev-parse", "--git-path", name)):
            print(f"- ⚠️ Folyamatban lévő {label}!")
            questions.append(f"Folyamatban lévő {label} van – folytassuk, vagy szakítsuk meg?")
            break

    if ref_exists("@{u}"):
        behind, ahead = git_out("rev-list", "--left-right", "--count", "@{u}...HEAD").split()
        print(f"- Távoli ág: `{git_out('rev-parse', '--abbrev-ref', '@{u}')}` – {ahead} commit előrébb, {behind} lemaradva")
        if int(ahead) and int(behind):
            questions.append(f"A helyi és a távoli ág elvált ({ahead} előrébb, {behind} lemaradva) – NE pusholj, előbb beszéljük meg.")
        elif int(ahead):
            questions.append(f"{ahead} pusholatlan commit – feltöltés (felhasználó futtatja): VS Code Sync, vagy `git push`")
    else:
        print("- Távoli ág: nincs beállítva")
        if branch != "(detached HEAD)" and git_out("rev-list", "--count", "HEAD", "--not", "--remotes=origin") != "0":
            questions.append(f"Az ág még nincs az originen – feltöltés (felhasználó futtatja): `git push -u origin {branch}`")

    # Nem commitolt változások, funkciónként
    entries = git_z("status", "--porcelain=v1", "-z", "--untracked-files=all")
    by_feature = defaultdict(list)
    protected = []
    i = 0
    while i < len(entries):
        e = entries[i]
        code, path = e[:2], e[3:]
        if code[0] in "RC":
            i += 1  # a régi név következik, átugorjuk
        i += 1
        if is_protected(cfg, path):
            protected.append(f"{code} {path}")
        feats = features_for_path(cfg, path)
        if not feats and profile_bucket(cfg, path) == "prune":
            feats = ["profiles-vendor-prune"]
        by_feature[", ".join(feats) or "(nincs funkcióhoz rendelve)"].append(f"{code} {path}")

    total = sum(len(v) for v in by_feature.values())
    print(f"- Nem commitolt változás: {total} fájl")
    for feat, files in sorted(by_feature.items()):
        print(f"  - **{feat}**: {len(files)} fájl")
        for f in files[:8]:
            print(f"    - `{f}`")
        if len(files) > 8:
            print(f"    - … +{len(files) - 8}")
    if protected:
        print(f"- ⛔ VÉDETT fájl módosult ({len(protected)}): csak kifejezett utasításra szabad – ellenőrizni!")
        for p in protected[:8]:
            print(f"  - `{p}`")
        questions.append("Védett (Ratrig) fájl módosult – a felhasználó kérte ezt kifejezetten?")
    if total and not protected:
        questions.append("Nem commitolt változások vannak – commitoljuk új ágra (`feature/<id>`), a jelenlegi ágra, vagy hagyjuk?")

    # Viszony a mainline-hoz
    print()
    if not ref_exists(up):
        print(f"- Upstream ref `{up}` nem létezik – `git fetch {up.split('/')[0]}` szükséges.")
    else:
        base = git_out("merge-base", "HEAD", up)
        base_ts = int(git_out("log", "-1", "--format=%ct", base))
        own = git_lines("log", "--format=%s", f"{base}..HEAD")
        behind_up = int(git_out("rev-list", "--count", f"{base}..{up}"))
        print(f"- Közös pont a mainline-nal: `{base[:10]}` ({git_out('log', '-1', '--format=%cs', base)}, {days_ago(base_ts)} napja)")
        print(f"- Saját commitok a közös pont óta: {len(own)}; ebből `[fork:<id>]` előtag nélkül: "
              f"{sum(1 for s in own if not s.startswith('[fork:'))}")
        fetch_head = git_out("rev-parse", "--git-path", "FETCH_HEAD")
        fetched = f"{days_ago(os.path.getmtime(fetch_head))} napja" if os.path.exists(fetch_head) else "ismeretlen"
        print(f"- Mainline új commitjai a közös pont óta: {behind_up} (utolsó fetch: {fetched})")
        if days_ago(base_ts) >= cadence:
            questions.append(f"Az utolsó szinkron óta {days_ago(base_ts)} nap telt el (küszöb: {cadence}) – "
                             "kéred a szinkron-riportot? (fetch + `fork/tools/sync-report.py`, csak elemzés)")

    # Párhuzamos munkák
    wts = [l.split(" ", 1)[1] for l in git_lines("worktree", "list", "--porcelain") if l.startswith("worktree ")]
    if len(wts) > 1:
        print(f"- További worktree-k: " + ", ".join(f"`{w}`" for w in wts[1:]))
    side = git_lines("branch", "--list", "custom/rebased-*", "backup/*", "sync/*", "--format=%(refname:short)")
    side = [b for b in side if b != branch]
    if side:
        print("- Egyéb fork-ágak: " + ", ".join(f"`{b}`" for b in side))

    print("\n## Javasolt kérdések a felhasználónak")
    if questions:
        for q in questions:
            print(f"- {q}")
    else:
        print("- Nincs teendő; kérdezd meg, melyik funkción dolgozunk (fork/features.yaml id vagy új funkció).")


if __name__ == "__main__":
    main()
