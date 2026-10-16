# G-code fázis profil – `--parallel` (2026-10-16)

Funkció: `parallel-gcode-export`. Ág: `feature/parallel-gcode-export` (bázis `05e1d85f73`).
Státusz: **elemzés kész, tervezés/végrehajtás nem indult** – későbbi feldolgozásra.

## Mérés

- Bináris: `build/src/Release/orca-slicer` (2026-10-16 21:03, `-x` build: LTO, strippelt).
- Gép: 40 szál. CLI log: `~/.orca-slicer-cli/log/cli_20261016_213032_178321.log.0`.
- Futtatás (a GUI-s környezetből `DISPLAY`/`WAYLAND_DISPLAY` nélkül kell indítani, különben
  GLib-GIO-ERROR `org.gnome.settings-daemon.plugins.xsettings ... antialiasing` → SIGABRT):

```bash
S=/home/rextruder/.config/OrcaSlicer/system/Ratrig
env -u DISPLAY -u WAYLAND_DISPLAY /mnt/Bulk/OrcaSlicer/OrcaSlicer/build/src/Release/orca-slicer --debug 4 \
  --load-settings "$S/machine/RatRig V-Core 4 IDEX 500 0.4 nozzle.json;$S/process/0.20mm Normal @RatRig V-Core 4 IDEX 500 0.4.json" \
  --load-filaments "$S/filament/RatRig Generic ABS.json" --filament-colour '#BCEC00' --parallel \
  --slice 0 --outputdir /tmp/pbench/out /home/rextruder/www/testfiles/3DBenchy.stl --clone-objects 100
```

- Eredmény: 102,8 s wall, 550 s user, peak RSS 7,1 GB; plate 1 (98 db): 446 MB G-code + 480 MB `.moves`.

## Idővonal (plate 1, másodperc a start óta)

| Szakasz | Ablak | Idő | Jelleg |
|---|---|---|---|
| Szeletelés eleje | 0 → 2,9 | 2,9 s | |
| Skirt/brim → Optimizing toolpath (`print::process: first time_using_cache is 39 secs`) | 2,9 → 42,6 | **39,6 s** | G-code előtti fázis |
| Path conflicts check | 42,6 → 45,05 | 2,5 s | |
| `SeamPlacer::init` – 98 objektum, főszálon, egyenként | 45,05 → 62,87 | **17,8 s** | soros |
| Párhuzamos rétegszöveg-generálás (chunkok) | 62,87 → 65,40 | 2,5 s | párhuzamos |
| `output_stream.write` + `GCodeProcessor::process_buffer` | 65,40 → 95,14 | **29,8 s** | soros, ~15 MB/s |
| `GCodeProcessor::finalize` (post-process: M73, fájl újraírás) | 95,14 → 99,35 | 4,2 s | soros I/O |
| `.moves` export, plate 2 | 99,35 → 102,7 | ~3 s | |

## Megállapítások

1. **SeamPlacer nem használja a megosztott objektumokat.** `SeamPlacer::init`
   (`src/libslic3r/GCode/SeamPlacer.cpp`) minden `PrintObject`-re külön fut, holott a klónok
   `PrintObject::get_shared_object()`-tel már megosztott szeletelésűek. Alias a gyökér-objektumra
   (`m_seam_per_object` lookup) → becsült nyereség ~17 s; a soros útnak is jó.
   Kockázat: `spRandom` seam minden klónon azonos lenne; ellenőrizendő, hogy a shared objektumok
   seam-konfigja mindig egyezik-e.
2. **A párhuzamos ágon a GCodeProcessor teljesen soros, átfedés nélkül.**
   `GCode::process_layers_parallel` minden chunk szövegét kigenerálja, csak utána írja sorban
   az `output_stream`-be (→ `process_buffer`). A soros pipeline ezt átfedi a generálással.
   Chunk-streaming (chunk 0 rétegenként, a többi sorrendben, ahogy elkészül) legfeljebb ~2,5 s-ot
   hozna, mert maga a generálás már gyors. Az igazi cél a processzor ~30 s-a.
3. **GCodeProcessor gyorsítás** – profil kell. Akadályok: a bináris strippelt (`build_linux.sh`
   `strip --strip-all`, 763. sor), `perf_event_paranoid=4`, nincs sudo, `ptrace_scope=1`
   (gdb csak szülőként csatolhat). Lehetséges út: strip nélküli újralinkelés + gdb-ből indított,
   SIGINT-es mintavétel. Ötletek: parse (GCodeReader) és állapotgép külön szálon (pipeline);
   `GCodeOutputStream::write` felesleges `std::string` másolata (kicsi).
4. **finalize** 4,2 s – a 446 MB-os fájl újraírása; alacsony prioritás.
5. **A 39,6 s-os előfázis** a legnagyobb egyedi blokk – nem utófázis, külön vizsgálandó.

## Funkcionális térkép: az „utolsó réteg kész” után (2026-10-16, 2. rész)

A GUI alapból a soros pipeline-t futtatja (`--parallel` csak akkor él, ha a GUI-t is azzal indítják:
`Print::set_default_parallel_gcode_export`, `src/OrcaSlicer.cpp`).
Soros út: `tbb::parallel_pipeline(12, …)` → a GCodeProcessor legfeljebb ~12 réteggel jár a generálás mögött.
`--parallel` út: a „layer N/N” után a teljes processzor-munka még hátravan (Benchy x100: 29,8 s csend).

| # | Lépés | Hol | Szál | CLI mérés (Benchy x100) |
|---|---|---|---|---|
| 1 | Hátralévő rétegek GCodeProcessor-a (`output_stream.write` → `process_buffer`: parse, időbecslés, `result.moves`) | `GCode::process_layers[_parallel]` | soros | soros út: ≤12 réteg; `--parallel`: **29,8 s** |
| 2 | Záró G-code: retract, filament/machine end gcode, M73 placeholder, CONFIG_BLOCK (teljes config szövegként), filament statisztika kommentek | `GCode::_do_export` vége | soros | ~0 |
| 3 | `GCodeProcessor::finalize`: tárgy-tömegek, wipe-szélesség, utolsó időszámítás, `update_estimated_times_stats`, **`run_post_process`** (teljes fájl újraolvasása + újraírása: M73, filament-stat placeholderek, ActualSpeedMove, backtrace), opcionálisan `run_second_pass_injection` (csak pre-heating) | `GCodeProcessor.cpp` | soros | **4,2 s** (446 MB) |
| 4 | Statisztika (`update_print_estimated_stats`), tömeg-ellenőrzés | `GCode::do_export` | soros | ~0 |
| 5 | **`.moves` sidecar export** (fork `moves-sidecar`) – GUI-ban is lefut, pedig ott senki nem olvassa | `GCodeProcessor::export_moves_file` | soros | ~1–3 s (480 MB írás) |
| 6 | `extract_result` (move), `.tmp` → végleges átnevezés | `GCode::do_export` | soros | ~0 |
| 7 | CLI: plate 2…, `result.json`, `--gcode-stats` stb. | `OrcaSlicer.cpp` | soros | plate 2 + egyéb ~3 s |
| 8 | GUI: `bspsGCodeFinalize` – csak exportnál másol/post-process szkript; előnézetnél csak státusz | `BackgroundSlicingProcess::process_fff` | háttér | – |
| 9 | GUI: `GCodeViewer::load_as_gcode` → `libvgcode::convert` (2 menet a `moves`-on) → `ViewerImpl::load` (≥5 menet a csúcsokon: rétegek, idők, opciók, layer_duration, first-vertex, `extract_pos_and_or_hwa`) → GPU-feltöltés → `update_view_full_range`/színek → GCodeViewer idő-statisztika menet a `moves`-on → `load_shells` | GUI főszál | **soros, GUI-szálon** | nem mérhető CLI-ből (~20 M csúcs) |

Megfigyelések a GUI-hoz (kódból, mérés nélkül):
- A 9. lépés teljes egészében a GUI főszálon, egyszálú ciklusokkal fut ~20 M elemen; több menet ugyanazon
  az adaton → memória-sávszélesség-korlátos. Párhuzamosítható / összevonható menetek.
- Az 5. lépés GUI-ban felesleges I/O (veszteségmentesen kihagyható GUI-ban).
- A 3. lépés a teljes fájlt újraírja; a beszúrandó sorok száma kicsi → olcsóbb megoldás lehet.
- GUI-mérés kell: `--debug 4` + jelölő-logok a 3/5/9. lépés köré, vagy strip nélküli build + mintavétel.

## Mérés `perf-phase-timers` időmérőkkel (2026-10-16 22:00 után)

Kiértékelés: `[fork-perf]` sorok a logban (CLI: `~/.orca-slicer-cli/log/cli_*.log.0`, GUI: `~/.config/OrcaSlicer/log/debug_*.log.0`,
GUI-hoz `log_severity_level = info`).

| Lépés | CLI Benchy x100 `--parallel` | CLI x100 soros | GUI 61 db soros | GUI 61 db `--parallel` |
|---|---|---|---|---|
| SeamPlacer::init | 17,9 s | 17,8 s | 10,8 s | 10,9 s |
| Rétegszöveg-generálás | 2,75 s | (átfedve) | (átfedve) | 6,9 s |
| Írás + GCodeProcessor | 30,5 s | 35,3 s | 18,0 s | 13,5 s |
| `process_layers` összesen | – | 35,8 s | 29,6 s | – |
| Farok az utolsó réteg után (processzor) | 30,5 s | 0,27 s | 0,10 s | 13,5 s |
| `_do_export` vége → finalize (nem mért) | ~1,4 s | ~1,3 s | ~0,9 s | ~0,9 s |
| finalize (`run_post_process`) | 2,8 s | 3,0 s | 1,7 s | 1,7 s |
| `.moves` | 0,4 s | 0,4 s | 0,24 s | 0,24 s |
| do_export összesen | 56,1 s | 58,6 s | 43,7 s | 34,6 s |
| GUI `libvgcode::convert` | – | – | 1,22 s | 1,21 s |
| GUI `Viewer::load` (+GPU) | – | – | 2,98 s | 2,97 s |
| GUI egyéb (bbox, statisztika, gcode ablak) | – | – | 0,5 s | 0,3 s |
| GUI első render | – | – | 0,95 s | 0,95 s |
| **Utolsó réteg → 3D kép** | – | – | **~8,5 s** | **~22 s** |

Következtetések:
- A GCodeProcessor mindkét módban a fő tétel; `--parallel` módban teljes egészében az utolsó réteg után fut.
- `--parallel` a do_export-ot GUI-ban ~9 s-mal rövidíti, de a látható „utolsó réteg → kép” idő nő (13,5 s processzor-farok).
- A GUI előnézet-betöltés (~5,7 s) mindkét módban azonos.
