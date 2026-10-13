# CLI

### Arrange behavior and diagnostics (#15033, #15836, #15837, #15733)
⚠️ Fork-releváns: ez közvetlenül érinti az `src/OrcaSlicer.cpp`, `src/libslic3r/PrintConfig.cpp` és `Arrange.cpp` környékét, ahol a fork saját `--arrange-mode fast|nest`, `--arrange-info` és `ArrangeFast` logikát ad hozzá. Az upstream CLI arrange alapértelmezetten már nem forgat objektumokat: az `--allow-rotations` opció defaultja `false`, és STL/OBJ/STEP inputnál is `-50` (`CLI_NO_SUITABLE_OBJECTS`) lehet az eredmény, ha az objektum csak forgatással férne fel; ilyen esetben stderr-re külön ok kerül. Új CLI opció az `--align-to-y-axis` (`coBool`, default `false`): ha explicit meg van adva, felülírja az i3 printerek GUI-val egyező automatikus Y-tengelyes igazítását, ha nincs megadva, a régi printer-structure szabály marad. A globális `--arrange` projektág már lefoglalja a prime tower helyét is, projektből vett filament-használattal és plate-specifikus tower pozícióval, a custom arrange végső igazítása pedig már clampeli a halmot az ágyra off-center `best_object_pos` esetén is.

### Mesh orientation and inspection actions (#15073)
⚠️ Fork-releváns: új CLI transform/action kulcsok kerülnek ugyanabba a `CLITransformConfigDef`/`CLIActionsConfigDef` felületbe, ahol a fork saját CLI opciói élnek. Új `--inspect-mesh` (`coBool`, default `false`) JSON-t ír stdout-ra az objektumok bounding boxairól és a Lay-on-Face által választható convex-hull face-ekről, majd kilép; input hiányában vagy inkompatibilis actionnel `CLI_INVALID_PARAMS`. Új transformok: `--ground-largest-face` (`coBool`, default `false`), `--ground-face-normal NX,NY,NZ` (`coString`, default `""`) és `--ground-face-point X,Y,Z` (`coString`, default `""`), mind parancssori sorrendben futnak, a korábbi `--rotate-*` transzformokat figyelembe veszik, és az `--orient 1` utánuk felülírhatja az orientációt. A `--ground-face-normal` és `--ground-face-point` üres vagy rosszul parse-olható értéke hibára fut, a point mód több objektumnál csak a találó objektumokat groundolja, de ha egyiknél sincs találat, invalid params lesz.

### Paint inspection action (#14608)
Új `--inspect-paint` (`coBool`, default `false`) action JSON-t ír stdout-ra a modellekben tárolt per-facet paint állapotokról: support enforcer/blocker, seam, MMU/extruder segmentation és fuzzy skin. A kimenet objektum/volume/layer/state bontásban facet countot, mm² felületet és mesh-local bounding boxot ad, empty layereknél `{"empty": true}`, felül összesítéssel. Actionként van regisztrálva, GUI fallback nélkül tiszta `0` exitre megy, de más munka-actionökkel (`--slice`, `--export-3mf`, stb.) ütközve `CLI_INVALID_PARAMS`, input nélkül szintén `CLI_INVALID_PARAMS`.

### Strict mode, result.json warnings and cleaner stdout (#14601, #15698, #15834, #16339)
⚠️ Fork-releváns: a fork `result.json`, `--gcode-stats`, `.moves` sidecar és export pipeline kiegészítései ugyanazokat a CLI exit/result utakat érinthetik. Új `--strict` (`coBool`, default `false`) CI/headless módot ad: a NON_CRITICAL slicing warning, például support szükséges de tiltott állapot, `CLI_SLICING_ERROR`-ral megszakítja a futást még G-code export előtt; `--strict --no-check` tiltott és `CLI_INVALID_PARAMS`. Linuxon a `result.json` két új top-level mezőt kap: `warnings` tömböt stabil `class` mezővel (`slicing_warning_non_critical`, `plate_id`, `text`) és `strict_mode` boolt; nem strict futásban a warning csak rögzül, a `return_code` marad a verdict. A `--export-settings -` most a merged config JSON-t stdout-ra írja, inkompatibilis stdout/action kombinációkat előre elutasít, invalid UTF-8-at stdout módban U+FFFD-re cserél, file-outputnál viszont megtartja a strict viselkedést; a `CLI_NO_SUITABLE_OBJECTS` `-50` üzenet már nem feltételez 3MF uploadot, a per-object `SlicingErrors` pedig objektumnévvel kerül stderrre és `result.json` error stringbe.

### CLI preset and mixed-filament parity (#15449, #15595, #15636, #15642, #15953, #16038, #16047, #16157, #16247)
⚠️ Fork-releváns: a fork `--load-settings full project JSON`, `--export-slicedata/--load-slicedata` és projekt/preset cache útjai érzékenyek a preset-merge sorrendre. A CLI kompatibilitási check már ugyanazt a `compatible_printers_condition` logikát értékeli, mint a GUI, és a 3MF-ből átnevezett kompatibilitási kulcsokat visszafordítja ellenőrzés előtt. A CLI 3MF export most kitölti a `different_settings_to_system` oszlopokat a user preset parenthez képesti diffből és a parancssori override-okból is, így GUI reopen után nem vesznek el örökölt process/filament/machine értékek. Mixed filamentnél a CLI megtartja a prime towert, nem recompute-olja rosszul a flush matrix mixed slotjait, visszautasítja a saját filament nélküli vagy eltérő filament-type komponensekből álló mixed slotot (`CLI_MIXED_FILAMENT_INVALID`, `-69`), és a mixed-colour metadata tömböket, valamint device drying értékeket slotonként GUI-kompatibilisen méretezi/merge-eli.

# Teljesítmény

### G-code export hot paths (#16026, #16028, #16050, #16031, #16108, #16167)
⚠️ Fork-releváns: ezek nagy része `GCode.cpp`, `GCodeWriter`, `GCodeProcessor` és pipeline szintű módosítás, ami ütközhet a fork parallel chunked G-code exportjával (`GCode::clone_for_parallel_chunk`), `.moves` sidecarral és `--gcode-stats` feldolgozással. A claimelt gyorsulások: typed config apply 7-26%, cached config lookupok 3-9%, parallel overhang precompute 4-17%, post-processing fixek up to 7%, olcsóbb G-code text building up to 8%, post-processed G-code per-line copy nélkül up to 6%. A változások konkrétan string-append alapú `GCodeWriter` útvonalakat, instance-name cache-t, actual-speed move beszúrásokat, placeholder/postprocess gyorsításokat, config-érték cache-elést és TBB pipeline-ba előre számolt overhang layereket vezetnek be. Külön figyelendő, hogy a parallel overhang precompute már a generator előtt épít `PrecomputedOverhangLayer` adatokat, és a pipeline tokenláncba adja be őket.

### Slicing hot paths (#16183, #16113)
A slicing oldalon up to 5% gyorsulást ad, hogy több layer/support útvonal nem másolja feleslegesen a print configot. Az overhang/curl útvonal up to 9% gyorsulást kap azzal, hogy curled wall estimate csak akkor fut, ha ténylegesen olvassa valamelyik régió a slowdown-for-curled-perimeters adatot; mellékhatásként javítja a stale fan commandokat is újraszeletelésnél.

### Clipper2 2.0.1 migration (#15969)
⚠️ Fork-releváns: polygon clipping, arrange és slicing geometriák széles körét érinti, ezért a fork `ArrangeFast`/custom arrange és geometriára épülő headless output regresszióira figyelni kell. Az upstream törli a régi Clipper kódot, Clipper2 2.0.1-re migrál, és több libslic3r polygon/offset/region/support/slicer útvonalat átvezet az új API-ra. A cél teljesítményjavítás és modernizált clipping backend, jelentős diff-fel és sok geometriai teszttel.

# Függőségek / build

### CGAL 6.2.1 (#16258)
A CGAL 5.6.3-ról 6.2.1-re frissül, és ehhez igazodnak a libigl/cgal bridge include-ok és a CGAL-t használó mesh/CAD/texture repair útvonalak. Headless import/boolean/repair pipeline-oknál nem új CLI feature, de dependency és numerikus viselkedés változhat.

### OCCT 8.0.1 (#16089)
Az OCCT 8.0.1-re frissítés célja gyorsabb STEP import és Design tab, plusz Windows STEP crash javítás. A diff érinti a STEP olvasót, CAD document/geometry/sketch engine-t, SVG/text shape környékét és tesztadatokat; headless pipeline-ban főleg STEP inputnál releváns.

### Remove OpenCSG, GLEW and GLU (#16318)
Az upstream eltávolítja a már nem használt OpenCSG, GLEW és GLU függőségeket, valamint a hozzájuk tartozó build/find modulokat és sandboxot. Build oldalon nagy törlés, runtime funkcionális változást nem céloz.

### CMake and spnav build cleanup (#16097, #14223)
A minimum CMake verzió 3.10-re nő, a dependency build scriptek ehhez igazodnak. A SpaceNavigator/spnav linkelés fallbacket kap dinamikus linkelésre, ami platformos build-kompatibilitási javítás.

# Biztonság

### Plugin download TLS and CA handling (#16253, #15654, #16128)
A Cloud plugin letöltése már ellenőrzi a TLS certifikátot. A HTTP init CA bundle probe-ja nem dob kivételt unreadable path esetén, hanem továbbpróbál más CA bundle helyeket, és az OpenSSL default cert env változó hiánya sem segfaultol.

### Project metadata and attachment hardening (#15956)
A Project page már textként vagy szűrt DOM-ként rendereli a 3MF-ből jövő model/profile/author/description/accessory adatokat, nem live HTML konkatenációként. Az attachment megnyitás csak az auxiliary könyvtáron belüli regular fileokra engedett, symlink escape elutasítva, program/script jellegű vagy ismeretlen típusoknál megerősítés kell, és a description képei csak HTTPS-en maradhatnak.

### Archive and config import confinement (#15957, #15608)
Az updater és plugin archive extraction most `extract_archive_confined`/root-check helperrel garantálja, hogy zip entry és symlink target ne írjon a célkönyvtáron kívülre; NUL-t tartalmazó pathok elutasítva vannak. A config import is a preset könyvtárba van szorítva: zip entry basename, preset name és bundle id ellenőrzött, platformfüggetlenül kezelve a `/` és `\` szeparátorokat.

### Malformed model import hardening (#15948, #15958, #15959, #16059)
Az OBJ loader bounds-checkeli a texture-coordinate indexeket, kezeli a hiányzó/out-of-range/relatív `vt` eseteket és a `vt u v w` formát; a DRC loader elutasítja a POSITION nélküli vagy rossz face-indexes mesh-eket. A 3MF XML zip entry méretét int limit előtt validálja, a plate id `<1` már hiba, a sérült paint bitstream nem olvas túl és warninggal dobja az adott triangle adatot, a ciklikus 3MF component reference pedig elutasításra kerül.

### Download names, file URLs and malformed network replies (#15955, #15961, #15947)
A szerver által adott `Content-Disposition`/import link fájlnevek sanitized basename-re szűkülnek, unused-name keresés előtt és közvetlen final rename előtt is védve. A lokális embedded web page URL-ek percent-encoded `file://` helperrel készülnek, így `#`, `%`, `?` vagy UNC/Windows path nem töri el a webview-t. Duet/MKS/UltiMaker/Flashforge/UserManager network JSON parsing már nem tud callbackből kivétellel appot vagy upload queue-t megölni; hibát reportol, és a queue továbbmegy.

# Nyomtató-kapcsolat

### Moonraker Upload & Print race (#15032)
A Moonraker upload most `print=true` form fieldet küld, és az upload válasz top-level `print_started`/`print_queued` mezői alapján eldönti, hogy Moonraker már átvette-e a print indítását. Ez javítja a power-on-upload konfigurációk 503-as race-ét, miközben régebbi vagy inkompatibilis szervereknél megmarad az explicit `/printer/print/start` fallback.

### Bambu network plugin 02.08.04 (#16202)
A Bambu Network Plug-in 02.08.04 sorozat támogatottá válik, a `PrintParams` layout `queue_plate_id` mezővel igazodik az új ABI-hoz. A 02.08.01 kikerül a whitelistből, mert már nem illeszkedik és macOS 27-en dyld miatt sem tölthető megbízhatóan; stored unsupported verzió esetén a meglévő fallback a latest sorozatra fut.

### Creality K1-family CFS (#14089)
A Creality K1/K1C/K1 SE/K1_CFS-C profilok és host integration CFS-támogatást kapnak. A változás profilokat, discoveryt és `CrealityPrint` upload/host kódot érint.

### UltiMaker S5 local API (#14062)
Új UltiMaker S5 profilok, local API print host, credential generation flow és upload támogatás kerül be, Single Extruder/Fast process profilokkal és buildplate modellel. A Generate API Key gomb csak UltiMaker hostnál jelenik meg, és a platformos buildhibák is javítva vannak.

### WebUI printer pages after language switch (#14547)
A Device tab / plugin webview oldalak nyelvváltás és Windows webview recreate után nem maradnak blank állapotban: lazy plugin page build, újra létrehozott browser és Project info replay kezeli a hot-reloadot. Ez printer WebUI integrációt érint, nem slicing outputot.

# Preset feloldás

### System preset resolution and cache-only installs (#15953, #16038, #16047, #15693)
⚠️ Fork-releváns: a preset load/merge sorrend és cache-only vendor load a fork `--load-settings` és headless project JSON útvonalával ütközhet. A CLI most release installokon is tud system presetet resolve-olni, ahol csak preset cache van telepítve: read-only load olvassa, de nem írja a cache-t. Projektből hiányzó printer/process/filament kulcsok a system preset aktuális értékeiből töltődnek fel GUI-val azonos szabállyal, az OTA/cache-only vendor tree-ket is kezelve. A #15693 ugyanennek a vendor-resolve útnak a teljesítményregresszióját javítja: egy futáson belül minden vendor tree és OrcaFilamentLibrary csak egyszer töltődik, a példamérésben machine+process+4 filament 5.00 s-ről 0.99 s-re ment.

### Preset inheritance and compatibility (#15449, #15438)
A CLI inherited preseteket vendor manifesten keresztül old fel, typeless preset JSON-oknál a megfelelő preset collectiont próbálja, és hiányzó/cross-type/duplikált identity esetén nem választ csendben rossz jelöltet. A printer/process kompatibilitás ellenőrzése már a GUI `is_compatible_with_printer()` politikáját használja, beleértve a `compatible_printers_condition` kiértékelését és a 3MF-ben átnevezett compatibility kulcsok visszafordítását.

### Extruder variant value preservation (#16046, #16107, #16355)
A user preset, project és cloud-sync útvonalak egységesebb variant-column fallback szabályt kapnak: ha a parent új nozzle/extruder variantot kapott, a hiányzó variant az adott extruder első child/project variantjának értékét veszi, nem a parent defaultját. Cloud upload mindig küldi a variant layoutot, és régi letöltött presetet a parent layout alapján olvas, így dual-nozzle printereken a jobb nozzle beállításai nem vesznek el sync után.

### Legacy filament printer migration (#16367)
A 2.4.2 óta átnevezett/szűkített system filament presetek miatt eltűnő user filament compatibility listákhoz migrációs flow került be. Induláskor vagy Help menüből felajánlja a hiányzó printerek visszaírását, backup zipet készít, lockolja a user preset írásokat, és cloud-synced preseteket uploadra jelöl.

### Bambu profile includes (#15869)
A Bambu Lab syncelt presetek már betöltik a BambuStudio-s template/include fájlokat, így visszajönnek a közös start/end G-code és dual-nozzle beállítások. Ez Bambu Lab profilverziót emel, a többi vendor profilját nem célozza.

# Fontos hibajavítások (CLI/headless szempontból)

- `b920116fbd` (#15379): G-code file loadnál a `; MANUAL_TOOL_CHANGE` kommentek újra beállítják a manual filament change állapotot, így a toolchange preview/processor nem mindent első filamentre sorol.
- `4a20168742` (#16331): multi-toolhead 3MF betöltése már nem akad el, ha nincs `filament_self_index`.
- `018c4f49ee` (#16016): üres `Metadata/project_settings.config` esetén a CLI `--info` és a printable-height olvasások nem null dereference-szel omlanak össze.
- `d1a3ef68c5` (#15978): malformed project, üres/negatív assemble-list filament, plate metadata nélküli `--slice N --arrange 1` és input nélküli `--assemble` már validált hiba, nem SIGSEGV.
- `d1d14329d9` (#16025): ugyanannak a sliced printnek az ismételt exportja determinisztikusabb, mert a chaining már nem fordítja meg in-place a layer extrusion entity listákat.
- `ff2f42016a` (#16004): project settings nélküli 3MF CLI betöltésnél a `printable_height` hiánya nem crash, hanem unknown heightként kezelt `0`.
- `561737f407`: CLI `--export-3mf` thumbnail render után nem segfaultol plater/wx application hiányában.
- `45bc39a47a` (#15745): a CLI OpenGL context verzió javítása stabilabbá teszi a headless/CLI thumbnailes export útvonalat.
- `ea471dc82d` (#15866): wx application nélküli model inicializáció flat-normal fallbackre megy, így CLI thumbnail geometry init nem preference-olvasásban omlik el.
- `6a07853933` (#15915): file header G-code placeholder feldolgozás crashét javítja a G-code exportban.
- `ac3997c0d1` (#15289): toolchange flush-volume és HRC per-filament lookupok bounds-checket kapnak, rövid legacy/minimal multi-extruder configoknál nem olvasnak túl.
- `bd1304443c` (#14789): H2C/tool-ordering/wipe-tower/G-code export több per-filament array olvasása clamping accessorokon megy át, rövid config arrayeknél nem UB.
- `efc9f253ee` (#14803): relatív parancssori input pathok még a working directory `<data_dir>/log` alá váltása előtt abszolútra oldódnak, így `orca-slicer ./file.3mf` működik.
- `aef9ca2efb` (#15666): object label G-code nem hibázik toolchange esetén, ha nincs object instance.
- `c5965fa4d9` (#15662): perimeter region merge után törlődnek a stale pathok, ami slicing correctness regressziókat előz meg.
- `74cf148384` (#15425): sequential-print arrange beállítások már nem ignorálódnak és perzisztálódnak, ami by-object pipeline-ban fontos.
- `fa3dbfcc6f` (#15582): Windows G-code export failure valódi hibaüzenetet ad, nem `length_error`/generic unknown error rejti el.
- `8e064659ad` (#15563): per-layer intersection line sorrend canonical sortot kap, így parallel slicing thread schedulingtől kevésbé lesz run-to-run eltérő G-code.
- `bcb4f17d9a` (#15438): CLI inherited preset resolution vendor manifesteken át működik, typeless preseteknél explicit missing/cross-type/duplicate hibákkal.
- `886d43d37a` (#15564): support fill cost thresholdök nem fagynak be az első hívás értékeire, így több konfiguráció egymás utáni szeletelése korrekt marad.
- `6014f3fb43` (#15451): project-settings útvonalon egy újabb null dereference guard került be.
- `0224741105` (#15539): organic support nem generálódik bele az object top surface-ekbe.
- `134b9ad96e` (#15525): organic tree support már nem eggyel kevesebb bottom interface layert készít a beállítottnál.
