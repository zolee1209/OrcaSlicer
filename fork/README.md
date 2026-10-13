# Fork-karbantartás

Ebben a mappában van minden, ami a saját fork (`zolee1209/OrcaSlicer`) és a mainline
(`OrcaSlicer/OrcaSlicer`) közötti szinkronizációhoz és a saját funkciók nyilvántartásához tartozik.
A mappa nincs upstreamben, ezért rebase-nél soha nem ütközik.

## Tartalom

- `features.yaml` – **a hiteles nyilvántartás**: saját funkciók (fájlok, CLI-opciók, döntések, rebase-szabályok),
  szinkron-beállítások, védett fájlok, profilszabályok.
- `tools/` – determinisztikus scriptek (Python 3 + PyYAML), lásd lent.
- `upstream-sync/<dátum>/` – egy-egy szinkronizációs kör anyaga
  - `upstream-changes.md` – a mainline változásai magyarul, témák szerint, ⚠️ = fork-releváns
  - `rebase-trial-notes.md` / `rebase-notes.md` – rebase-jegyzőkönyv
  - `report.md` – a `sync-report.py` kimenete
  - `data/` – nyers listák

Copilot-integráció (a repó gyökeréből):
- `.github/instructions/orca-fork.instructions.md` – minden sessionben betöltődő szabályok
- `.github/skills/orca-fork/SKILL.md` – eljárások (session eleje, új funkció, commit, havi szinkron)

## Scriptek

```bash
python3 fork/tools/session-status.py                 # állapot + javasolt kérdések (csak olvas)
python3 fork/tools/sync-report.py --fetch --out fork/upstream-sync/$(date +%F)/report.md
python3 fork/tools/check-fork.py                     # features.yaml <-> kód <-> commitok
python3 fork/tools/prune-profiles.py                 # profilállapot; módosítás csak --apply-jal:
python3 fork/tools/prune-profiles.py --resolve-conflicts --apply     # rebase közben
python3 fork/tools/prune-profiles.py --prune --apply                 # más gyártók törlése
python3 fork/tools/prune-profiles.py --restore-ratrig <ref> --apply  # Ratrig = fork verziója
```

## Konvenciók

- Kódcímke upstream fájlban: `// FORK(<id>): ...` vagy `// FORK(<id>) BEGIN` … `// FORK(<id>) END`
- Commit-tárgy: `[fork:<id>] ...`
- Ágak: `custom/rebased-<YYYY-MM>` (fork fő ág, `sync.fork_branch`), `feature/<id>`, `backup/pre-sync-<dátum>`
