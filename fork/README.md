# Fork-karbantartás

Ebben a mappában van minden, ami a saját fork (`zolee1209/OrcaSlicer`) és a mainline
(`OrcaSlicer/OrcaSlicer`) közötti szinkronizációhoz és a saját funkciók nyilvántartásához tartozik.
A mappa nincs upstreamben, ezért rebase-nél soha nem ütközik.

## Tartalom

- `features.yaml` – **a hiteles nyilvántartás**: saját funkciók (fájlok, CLI-opciók, döntések, rebase-szabályok),
  szinkron-beállítások, védett fájlok, profilszabályok.
- `tools/` – determinisztikus scriptek (Python 3 + PyYAML), lásd lent.
- `bench/process/` – rögzített process-profil(ok) a teljesítményméréshez (a felhasználói profil változása ne torzítsa a mérést).
- `perf/` – teljesítmény-elemzések, mérési jegyzőkönyvek.
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

## Teljesítménymérés

```bash
python3 fork/tools/bench.py run base --runs 3 --cpu          # helmet + tree support referencia, medián, CPU/fázis
python3 fork/tools/bench.py run proto --runs 3 --env ORCA_X=1 # ugyanez környezeti kapcsolóval
python3 fork/tools/bench.py compare base proto               # idők + geometriai digest (AZONOS/ELTÉR)
python3 fork/tools/bench.py run prof --profile               # gperftools CPU-profil (perf/sudo nélkül)
python3 fork/tools/gprof-report.py build/src/Release/orca-slicer build/bench/prof/run-1/cpu.prof --top 40 [--cum|--callers RE|--within RE]
```

- Kimenet: `build/bench/<címke>/` (nem tmpfs; a G-code/.moves futás után törlődik, `--keep` megtartja).
- Időmérők a kódban: `src/libslic3r/ForkPerfTimer.hpp` (`ForkPerfScope`), log: `[fork-perf] <név>: <ms> ms`
  (`--debug 4`); a bench.py ezeket gyűjti.
- Profilozáshoz nem strippelt bináris kell (sima `ninja -f build-Release.ninja orca-slicer`; a `build_linux.sh -x` strippel).
- Zaj ezen a gépen ~±4%: döntéshez `--runs 3`.

## Konvenciók

- Kódcímke upstream fájlban: `// FORK(<id>): ...` vagy `// FORK(<id>) BEGIN` … `// FORK(<id>) END`
- Commit-tárgy: `[fork:<id>] ...`
- Ágak: `custom/rebased-<YYYY-MM>` (fork fő ág, `sync.fork_branch`), `feature/<id>`, `backup/pre-sync-<dátum>`
