# Upstream OrcaSlicer változások - A csoport

## Többfúvókás / IDEX / belt

### iXex: Parallel Printing Support for IDEX and IQEX Printers (#13086)

⚠️ Fork-releváns: IDEX/multi-extruder logika, G-code export, arrange és CLI-guard érintett. Az új IMEX/IDEX/IQEX rendszer több független X-carriage-et kezel: copy, mirror, Span, több gantry, firmware-managed center-origin és per-plate módválasztás. Slicing előtt zónákat validál, arrange-et a primary zónára korlátoz, G-code elejére mode G-code-ot injektál, parallel módban per-tool Pressure Advance és per-layer hőmérséklet parancsokat ír; `physical_extruder_map` MMU/AFC esetben logical filament slot -> physical extruder leképezést ad, hibás vagy hiányos mapnél identity fallbackkel.

Új config opciók: `is_imex` ("IDEX/IQEX Printer", default `false`), `imex_firmware_managed_zones` ("Firmware-managed zones", `false`), `imex_gantry_count` ("Gantry Count", `1`), `imex_tools_per_gantry` ("Tools per Gantry", `2`), `imex_tool_layout` ("Tool 0 Position", `front-left`), `imex_nozzle_clearance_x` / `imex_nozzle_clearance_y` ("Nozzle Clearance X/Y", `30.0` mm), `imex_carriage_margin` ("Safety Margin", `0.0`), `imex_viz_theme` ("Visualization Theme", `standard`), `imex_parallel_mode` ("IDEX/IQEX Print Mode", `primary`), `imex_head_filament_map` ("IDEX/IQEX head filament map", empty), `imex_mode_names`, `imex_mode_active_tools`, `imex_mode_gcodes` (mind empty list). Meglévő profilok alapviselkedése nem változik, mert `is_imex=false` és plate mode `primary`.

### Merge Belt Printing Into Upstream (#14394)

⚠️ Fork-releváns: GCodeWriter/GCodeProcessor, arrange, preview, CLI és purge/wipe tower path érintett. Conveyor-belt/infinite-Z printer támogatást hoz: mesh pre-slice rotation, belt-floor support clipping, G-code back-transform, machine-frame shear/remap, belt-aware brim, belt purge tower és designed/raw preview. Belt mód csak `belt_printer=true` mellett aktív; nem belt printereken a régi XY/Z pipeline marad.

Új/fő config opciók: `belt_printer` ("Enable belt printing", `false`), `belt_printer_infinite_y` ("Infinite Y axis", `true`), `belt_slice_rotation` ("Belt tilt axis", `X`), `belt_slice_rotation_angle` ("Belt tilt angle", `45`), `belt_frame_tilt_decouple` ("Decouple machine-frame tilt", `false`), `belt_frame_tilt_angle` ("Machine-frame tilt angle", `45`), `gcode_remap_x/y/z` ("G-code remap X/Y/Z", `+X/+Y/+Z`), `build_plate_tilt_x/y` ("Build plate tilt X/Y", `0`), `belt_support_floor_offset` ("Support Floor Z offset", `0`), `enable_belt_purge_tower` ("Enable belt purge tower", `false`), `belt_purge_tower_width` ("Belt purge tower width", `35`), `belt_purge_tower_object` ("Belt purge tower object", `false`), `leading_brim_length` ("Leading brim length", `0`), `extra_brim_width` ("Extra brim width", `0`), plus `brim_type=leading_edge_only` enum value. Default profilokra nincs output-változás, mert belt mód kikapcsolt.

### Extruder/nozzle variants and multi-nozzle sizing (#15964, #16007, #15986, #14125)

⚠️ Fork-releváns: multi-extruder/nozzle variant választás, G-code Pressure Advance emisszió és CLI slicing érintett. Az extruder variants rendszer már minden printeren működik; a sidebarban választható printer/nozzle volume type, multi-extruder gépen extruderenként. A filament cooling, temperature limits, ramming és PA/adaptive PA adatok variant-aware módon olvasódnak, a régi egyértékes profilok értékei minden variánsra szétterülnek.

`nozzle_diameter_for_filament()` Bambu/H2D/X2D esetben a filament map alapján választ fúvókaátmérőt, így eltérő nozzle size-os tooloknál a flow/support/infill számítás a helyes extruder nozzle-ját használja. Új külön profile key nem jelent meg; a meglévő variant tömbök validációja szigorodott, és a `nozzle_volume_type` enum új értékeket kapott (`E3D High Flow`, `Extra High Flow`). Meglévő single-variant profiloknál nincs szándékos változás; output ott változik, ahol korábban rossz variáns értékei kerültek G-code-ba.

### Toolchange Cyclic Order (#14868)

⚠️ Fork-releváns: tool ordering / multi-extruder toolchange sorrend. Fix ciklikus toolchange sorrendet lehet megadni, amely rétegenként stabil tool sequence-et használhat a default, minimális toolchange-re optimalizáló sorrend helyett. Ez több extra toolchange-et okozhat, de javíthatja a hűlési időt és felületi minőséget.

Új opciók: `toolchange_cyclic_order` ("Cyclic order", default empty string) és `toolchange_cyclic_first_layer` ("Apply cyclic order to first layer", default `false`). Ha nincs ciklikus sorrend megadva, vagy first-layer flag off, a meglévő profilok viselkedése marad.

## Kitöltés (infill)

### Adaptive TPMS (#16005)

Gyroid, TPMS-D és TPMS-FK sparse infill sűrűsége adaptívan változhat a felülettől a belső mag felé. A `distance_warp`, `smooth_blend`, `stepped_shells`, `lobes` és `normal_x/y/z` módok más-más 3D/2D mezőt használnak; csak internal sparse infillt érint, object geometryt nem. Disabled default mellett régi output marad.

Új opciók: `tpms_adaptive` ("Adaptive density (experimental)", default `disabled`), `tpms_interior_density` ("Interior density", default `5%`), `tpms_adaptive_gradient` ("Adaptive gradient", default `linear`). A surface density továbbra is `sparse_infill_density`.

### Separated and non-crossing multiline infill (#16274, #15931, #15887, #16002)

`separated_infills` kiterjed sparse, internal solid infill és bridge anchorokra: több disconnected body egy objecten belül saját bounding box/center szerint kap mintát. A multiline infill non-crossing centerline stratégiája Grid/Triangles/Tri-hexagon/Cubic és Adaptive/Support Cubic mintákban csökkenti a kereszteződő vastag falak túlextrudálását. A Cubic multiline stratégia külön folytonos, rétegenként forgó 0/60/120 fokos path-rendszert kapott; a gyroid generálás optimalizáltabb bounding-box alapú wave építésre vált.

Új config key nincs ezekben a PR-ekben; a meglévő `separated_infills` defaultja továbbra is off, Adaptive/Support Cubic body-onkénti kitöltése viszont a dokumentált viselkedés része. Default profilokon csak az érintett minták belső path ordering/geometriai stabilitása változhat, ha a kapcsolódó opciók/patternök aktívak.

### Spiral Inset and 3D Honeycomb top fill (#15085, #15705, #12541)

Új `spiralinset` infill enum érték került a sparse és solid infill pattern listába ("Spiral Inset"). A pattern concentric/spiral jelleggel, kevés megszakítással tölti az islandeket, és a #15705 javítása nem hagy center plugot internal solid Spiral Inset esetén. A #12541 opcionálisan kitölti a 3D Honeycomb/truncated octahedron cellák felső nyitott részeit.

Új opció: `infill_complete_top` ("Fill pattern tops", default `false`). A Spiral Inset nem lesz default pattern; a 3D Honeycomb top-fill is off by default, tehát meglévő profilok alapoutputja nem változik.

### Clamp Ironing Line Spacing to a Usable Minimum (#15949)

Az ironing line spacing 0 vagy túl kicsi értéke 3MF-ből, CLI-ból vagy filament override-ból bejuthatott, concentric ironingnál végtelen slicinget, rectilinearnál néma kihagyást okozva. A top surface és support ironing most a GUI-ban már létező 0.05 mm floorra clampel; a concentric filler non-positive stepnél korán visszatér. Új opció nincs, shipped profilok változatlanok; csak invalid/túl kicsi értékű projektek viselkedése javul.

## Varrat (seam), falak, wipe, fuzzy skin

### Precise Seam placement and rework (#12974, #16072)

⚠️ Fork-releváns: seam placement G-code export idején fut, és #16072 `GCode.cpp`-t is érint. A Precise Seam non-printing helper/modifier volumekkel vezérli, hova kerülhet a seam külső perimeteren. Hat volume type dolgozik priority szerint: `PRECISE_SEAM_CENTER`, `LEFT`, `RIGHT` erős pontot kényszerít; `ENFORCED`, `BLOCKED`, `NEUTRAL` gyenge zónát ad.

#16072 újraírja a perimeter-intersection és segment extraction logikát: több régió/hole, full containment, clipped fragments és source-edge binding pontosabban kezelődik, a known limitationök csökkennek. Új PrintConfig opció nincs; a feature model volume metadata/3MF alapján működik. Precise Seam volume nélküli objektumokon a régi seam placement marad.

### Scarf Seam cleanup and calibration interaction (#15832, #15543)

A scarf seam már nem hagy sub-millimetre flat segmenteket a ramp elején/végén: túl rövid maradék esetén a ramp a következő vertexig nő, mikronos végszegmensek trimelődnek, és a teljes-loop scarf hossza clampelve van. Ez csökkenti a planner lassulását/megállását a seamnél. Retraction calibration aktiválásakor a GUI automatikusan kikapcsolja a scarf seams opciót, hogy a kalibrációt ne torzítsa. Új config nincs; csak scarf seam vagy kalibrációs workflow esetén változik output.

### Wipe inward for external perimeters (#15407)

⚠️ Fork-releváns: G-code wipe path generation érintett. External perimeter wipe közben a nozzle befelé, már kinyomtatott anyag felé mozdulhat, így kevésbé melegíti újra a friss külső falat és csökkentheti a seam wipe nyomát. Csak external wallokra és hole boundarykre vonatkozik, csak ha van alkalmas, korábban nyomtatott belső támaszfal; különben fallback a régi wipe path.

Új opciók: `wipe_inward` ("Wipe inward", default `false`) és `wipe_inward_distance` ("Wipe inward distance", default `50%` of `outer_wall_line_width`, mm vagy %). Existing profilokon nincs változás, mert a feature off by default; retraction/PA kalibrációk alatt G-code generálás is tiltja.

### Print unsupported walls last (#15411)

⚠️ Fork-releváns: perimeter G-code ordering (`GCode.cpp`) változik. A teljesen levegőben futó wall loopok késleltethetők, hogy a bridge/infill előbb adjon alátámasztást; ez csökkenti unsupported falak lehúzását vagy lerogyását. A logika nem vakon minden overhang falat mozgat: a már támogatott/anchor szerepű loopok megtartják helyüket.

Új opció: `unsupported_wall_last` ("Print unsupported walls last", default `false`). Default profilokon nincs változás.

### Fuzzy skin stability fixes (#13891, #15566)

Fuzzy skin már nem kerül bridge-like overhang perimeter szakaszokra, ha azok a lower slice alapján nincsenek eléggé megtámasztva; ezzel a bridge/overhang felület sima maradhat. A min junction width floor most layer-height alapján, skálázott coordban számolódik, így nagy noise amplitude vagy ridged multifractal noise nem viheti negatív/érvénytelen szélességbe az Arachne pathot. Új config nincs; fuzzy skin nélküli profilok változatlanok, fuzzy skin aktív modelleken bridge/overhang és extrém noise esetén változik a kimenet.

### Painted Multi-Material deterministic slicing (#15899)

Painted multi-material modellek G-code-ja korábban thread-schedule függő lehetett: ±1 µm koordináták és island order eltérések jelentek meg. A slab line ordering, top/bottom projection gather és painted-line sort total ordering lett. Új config nincs; a cél determinisztikus, nem más geometriájú output.

## Törlőtorony / szerszámváltás / G-code

### Wipe tower estimation and sparse-layer behavior (#15485, #15841, #15532, #15760, #16435)

⚠️ Fork-releváns: wipe tower/G-code path, GUI/CLI placement estimate és egyes `GCode.cpp` érintések. #15532 egy közös `estimate_wipe_tower_footprint()` függvénybe vonja össze a GUI, validation, arrange/placement és CLI wipe tower méretezést, így layer height, filament count, brim és object height ugyanabból a számításból jön. #15760 megszünteti az egyetlen használt filament melletti phantom prime tower preview/reservationt; #16435 mixed filament slotoknál a physical componentek szerint méretez, nem slotonként túlbecsülve.

#15485 portolja a BBS wipe tower javításokat: `wipe_tower_no_sparse_layers` clearance szabályai egységesebbek, a compacted tower körül objektum-height és rod/lid clearance validáció történik; új opció: `extruder_clearance_dist_to_rod` ("Distance to rod", default `40` mm). #15841 hozzáadja a sparse tower layers összevonását: `wipe_tower_sparse_layers_combination` ("Combine sparse layers", default `false`), amely egymást követő, filament change nélküli tower layereket egy vastagabb layerként nyomtathat, nozzle max layer height korláttal. Defaultból a régi one tower layer per object layer viselkedés marad.

### Print time placeholders and estimated-time comment location (#13063, #15897)

⚠️ Fork-releváns: `GCode.cpp` és `GCodeProcessor` post-processing érintett. Új placeholder komponensek kerültek a print statistics/post-processing rendszerbe: `print_time_total_sec`, `print_time_day`, `print_time_hour`, `print_time_minute`, `print_time_sec`; ezek days/hours/minutes/seconds bontást adnak start/end/custom G-code template-ekhez. A régi `print_time_sec` jelentése seconds component lett, a total seconds külön `print_time_total_sec`.

#15897 az estimated printing time commentet a config block után írja, nem elé. Ez G-code fájlszerkezetet változtat, de nyomtatási toolpathot nem. Shipped profilok csak akkor változnak láthatóan, ha ezekre a placeholder/comment pozícióra támaszkodnak.

### FanMover skip around toolchange G-code (#15904)

⚠️ Fork-releváns: `FanMover` és toolchange G-code export. A FanMover korábban kettévághatta a `change_filament_gcode` / toolchange template move-jait, hogy késleltetett fan parancsot szúrjon be; Bambu firmware T command közbeni head move-ja miatt ez téves köztes waypointot okozhatott. A toolchange saját G-code-ja most `;_FAN_MOVER_SKIP_START/END` tagek közé kerül, FanMover bent hagyja a fan parancsokat és eltávolítja a tageket. Új config nincs; csak fan speed-up/kick-start + toolchange template esetén változik az output.

## Támasz / raft

### Deterministic tree support and reslice memory/closing-radius fixes (#15565, #16066)

Tree support determinisztikusabb lett: a minimum spanning tree és TreeSupport sorrendezési források stabilabb eredményt adnak. #16066 reslice közbeni layer leakeket javít: tree support cache felszabadul, object slice sharing váltáskor régi layer adat felszabadul, és elephant-foot compensation minden object saját slice closing radius értékét használja. Új config nincs; output csak tree support vagy eltérő object closing radius / elephant-foot compensation esetén változhat.

### Raft expansion UI behavior (#16416)

A meglévő `raft_expansion` opció bekerült a Support / Raft csoportba, csak raft bekapcsolásakor látszik. Slim, Strong és Hybrid tree support stílusoknál a mező disabled, mert ezek a raft méretét a first-layer expansion alapján kezelik. Új config nincs; slicing output nem változik, ha a felhasználó nem módosítja az eddig rejtettebb beállítást.

## Egyéb slicing / GUI / profile-identitás

### Multi Object Vase Settings from Plate Settings Change (#16091)

Több objektumos vase mód beállítás alkalmazásakor a plate-level diff listát már nem írja felül az első object saját diffje. Minden object külön megkapja a szükséges vase-related beállításokat (`wall_loops=1`, `top_shell_layers=0`, infill/support kikapcsolás stb.). Új config nincs; csak multi-object vase settings alkalmazásakor változik a GUI által írt object config.

### Filament ID redesign (#15513)

`filament_id` most product identity alapján, tooling/CI által mintage-elt, ütközésmentesebb az egész profile libraryben. Ez AMS/CFS/spool sync megbízhatóságot javít, és Bambu catalog ID-kat boundary translation kezeli, nem profile ID-ként. Rengeteg filament profile változik, de print setting output cél szerint nem; profile-only részeket nem részleteztem. Új slicing config nincs.
