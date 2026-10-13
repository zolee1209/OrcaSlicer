# Próba-rebase upstream/main-re – jegyzőkönyv (2026-10-13)

## Állapot

| Elem | Érték |
|---|---|
| Fork ág (érintetlen) | `custom/rebased-2026-09` = `4d976bac18` = `origin/custom/rebased-2026-09` |
| Mentés | ág `backup/pre-rebase-2026-10-13`, tag `pre-rebase-2026-10-13` |
| Régi közös pont | `1170b048e8` (2026-09-04, #15479) |
| Új upstream | `upstream/main` = `008ee792f6` (2026-10-13) – 1980 commit, ebből 386 PR érinti a forrást |
| Próba-rebase ág | `custom/rebased-2026-10` (`477f05313c`), worktree: `/mnt/Bulk/OrcaSlicer/OrcaSlicer-rebase` |
| Build | **NINCS lefordítva, NINCS tesztelve.** Deps rebuild kell (CGAL 6.2, OCCT 8, Clipper2 2.0.1, új OpenSSL/SLVS/DataChannel). A félkész `deps/build` törölhető. |

Eldobás, ha nem kell:

```bash
cd /mnt/Bulk/OrcaSlicer/OrcaSlicer
git worktree remove --force ../OrcaSlicer-rebase
git branch -D custom/rebased-2026-10
```

## Commitok és ütközésfeloldások

⚠️ = jóváhagyás nélkül hozott döntés, át kell beszélni.

| Régi | Új | Commit | Ütközés és feloldás |
|---|---|---|---|
| 001591cade | db43e2bb85 | CLI multicolor IDEX + json inherits resolver | ⚠️ `OrcaSlicer.cpp` `load_config_file`: **az upstream verzió maradt** (`resolve_preset`, #15953/#16047/#15693). **A saját `CliPresetResolver.cpp/.hpp` törölve**, és kikerült a CMake-ből. A `PrintConfig.cpp`-ben az upstream kód maradt, a fork `extruder_type` szintézise és a `--filament-colour` opció automatikusan bekerült. A `build_linux.sh`-ban az upstream `-J` és a fork `-x` kapcsoló össze lett fésülve, és a `NATIVE_OPT_CFLAGS` a deps buildre is érvényes. |
| dd41308900 | 22d0a67571 | Nem-Ratrig profilok törlése | Kb. 6000 modify/delete és rename/delete ütközés → törlés (a fork szándéka). |
| 84b69f170a | cdea9ce03d | `.moves` sidecar + CLI/build javítások | A `Print.cpp`-ben az `export_moves_file` megmaradt. ⚠️ `Plater.cpp`, combo eseménykezelő: **az upstream variant-választó maradt, a fork IDEX „mindkét fúvóka egy combóval” logikája kimaradt.** `Plater.cpp`, `update_presets`: az upstream `FindString(variant)` és a fork `diameter_source` blokkja össze lett fésülve (`multi_extruder_rows` esetén ellenőrizni kell). `OrcaSlicer.cpp` thumbnail: a fork korai GL-inicializálása maradt, az upstream GL 3.3 + fallback javítása át lett véve. |
| a234a984dd | 59058af7b9 | Ratrig profilrendszer | ⚠️ Ratrig fájlokban (40) a fork verziója maradt → **az upstream Ratrig-profiljavítások elvesztek**. A 9 egyéb vendor-fájlban az upstream verzió maradt. A 17, fork által törölt fájl törölve. |
| c8838b1b31 | c5b6ddb6be | FilAr visszaállítás | tiszta |
| b80db00a81 | cec168510d | Ratrig `setting_id` | tiszta |
| 31cd1e6740 | e134a598fd | `--load-settings` projekt-JSON | Az upstream `load_config_file`-hoz igazítva: a config már be van töltve, a `raw_config` kikerült. |
| c5e6580b07 | 57546d135f | jemalloc + `ORCA_SKIP_MOVES_EXPORT` | `Print.cpp`: env-feltétel az upstream kódon. |
| 5ff243f626 | de0e87ca61 | `--gcode-stats` | include-ok összefésülve |
| 888405cb6e | 83315d8534 | slicedata JSON javítás | tiszta |
| 58b69357d0 | e49b3c5e89 | slicedata bináris | tiszta |
| 5625901be6 | eab4c99e4a | slicedata párhuzamos | tiszta |
| ebd9b59d8e | — (kihagyva) | GLModel CLI crash guard | Az upstream ugyanezt javította, a commit üres lett. |
| 49607d49f4 | 5442021239 | `--parallel` chunkolt G-code export | Az `OrcaSlicer.cpp`-ben a parallel flag és az upstream `--inspect-*` ellenőrzések együtt maradtak. A GL hint duplikáció (fork 3.2 / upstream 3.3) helyett az upstream 3.3 maradt. `Print.cpp`: upstream IMEX offset + `set_parallel_export`. `GCode.cpp`: `m_seam_placer->` és a Precise Seam figyelmeztetés. ⚠️ **Nincs ellenőrizve:** a `clone_for_parallel_chunk` nem kapja meg az IMEX offsetet és az upstream extrusion-quality előszámítását (#16050). A javítási kísérletet visszavontam. |
| 58666c1874 | b49d4b79db | brim bbox prefilter | tiszta |
| d9bd347454 | df069a9438 | TSP cap | tiszta |
| 4d976bac18 | 477f05313c | fast arrange + `--arrange-info` | `.gitignore`, include-ok. ⚠️ **Nyitott:** az `ArrangeFast` nem kezeli az új `is_belt` paramétert (#14394) és a prime tower foglalást (#15837). |

## Nyitott kérdések az átbeszéléshez

1. Kell-e még a `CliPresetResolver`, vagy elég az upstream `resolve_preset`?
2. Fast arrange: belt nyomtatóknál, prime tower foglalásnál és `--align-to-y-axis` mellett mi legyen a viselkedés?
3. `--parallel`: igazítsuk az upstream export-optimalizációkhoz, vagy előbb mérjük meg, kell-e még egyáltalán?
4. Ratrig profilok: fork vagy upstream verzió, illetve összefésülés?
5. Plater IDEX combo: kell-e a fork GUI-logikája?

## Döntések a próba-rebase után (2026-10-13 este) – ezek felülírják a fenti feloldások egy részét

Részletek: `fork/features.yaml` (`decision` mezők).

- `cli-preset-resolver`: a SAJÁT resolver marad → a db43e2bb85 feloldása hibás, javítandó.
- `gui-idex-nozzle-combo`: a fork logikája marad → a cdea9ce03d `Plater.cpp` feloldása hibás, javítandó.
- `profiles-ratrig`: SZIGORÚAN a fork fájljai → `prune-profiles.py --restore-ratrig backup/pre-rebase-2026-10-13 --apply`.
- `profiles-vendor-prune`: a gitben csak Ratrig + OrcaFilamentLibrary + Custom → `prune-profiles.py --prune --apply`.
- `parallel-gcode-export`, `slicedata-cache`, `cli-idex-multicolor`: maradnak; a `--parallel` klónozást
  az upstream export-változásaihoz igazítani kell.
- Javasolt út: a próba-ág megtartása + célzott javító commitok (olcsóbb, mint az újrakezdés) – jóváhagyásra vár.

## Javítások a próba-ágon (2026-10-13 éjjel)

| Commit | Funkció | Tartalom |
|---|---|---|
| 5fa2ffd30a | `fork-meta` | a `cb0947b96f` átvétele (features.yaml, tools, Copilot-szabályok) |
| 0471e628b1 | `cli-preset-resolver` | saját resolver vissza, FORK blokk az upstream `load_config_file`-ban; keresési mappák a `CliPresetResolver::sibling_search_dirs()`-ben |
| b1d69abefd | `gui-idex-nozzle-combo` | `Plater.cpp` = upstream; az upstream variáns-választó lefedi → `superseded` (GUI-teszt build után) |
| 6530053928 | `profiles-vendor-prune`, `profiles-ratrig` | 4750 fájl / 61 gyártó törölve; Ratrig = `backup/pre-rebase-2026-10-13` (az upstream `@RatRig` átnevezések kimaradtak) |

Még nyitott:
- `--parallel`: a `clone_for_parallel_chunk` igazítása (IMEX offset, #16050).
- `arrange-fast`: `is_belt`, prime tower, `--align-to-y-axis`.
- Build (deps rebuild) és CLI-teszt; az upstream `tests/cli` ctest a BBL profilok hiánya miatt nem fut.
- Opcionális: rebase a friss `upstream/main`-re (+2 commit, `de3af0b7de`).
