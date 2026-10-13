# OrcaSlicer mainline változások (2026-09-04 → 2026-10-13)

Alap: 1170b048e8 (a fork utolsó közös pontja) → upstream/main 008ee792f6. 386 PR érinti a forrást; gépprofil-változások kihagyva.

# 1. Szeletelő motor / G-code
## Upstream OrcaSlicer változások - A csoport

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

# 2. GUI / felhasználói felület
# Upstream OrcaSlicer változások - B szekció

## Textúra-elmozdítás (texture displacement)

### Texture Displacement gizmo and bake pipeline (#14662, #16148, #16395, #16391, #16392, #16394, #16320, #16242, #16149, #16147, #16393) ⚠️ Fork-releváns

Új paint-style **Texture Displacement** gizmo került a modellfelületre festhető grayscale height-map reliefhez: a felhasználó Brush/Face/Connected-area móddal jelöl területet, legfeljebb 8 layer-t keverhet, majd **Bake** után valódi mesh-geometriát kap. A UI a gizmo panelen és az UV Editor pane-ben jelenik meg; projekciók: Triplanar, Cylindrical, Spherical, Unwrap (LSCM), From view, plusz az új **Model UV**, amely az importált modell saját UV channel-jét használja. A sorozat hozzáadta a slider-ek pontos gépelését, az **Adjust image** panelt (Brightness, Contrast, Sharpness, Blur, Hue), a Checker/Distortion view javításait, UV-editor tooltipjeit, texture orientation fixet, és a Bake közbeni szín/paint megőrzést. A mixed-filament részek a texture színeiből filament mix slotokat tudnak létrehozni; a **Mixed colors** setting alapértelmezése 8, és csak a Bake írja át a projekt filamentjeit, a preview nem. A #16148 módosítja a `.3mf` formátumot: a layer stack, textúrák, paint masks (`paint_texture_0..7`), UV seam/island adatok és editor state bekerülnek az archívumba; a baked relief meglévő mesh-geometriaként is round-tripel, ezért ez 3MF- és libslic3r-releváns, de a slicer kimenet csak akkor változik, ha a user Bake-kel módosította a modellt.

## Design fül (CAD)

### Sketch-first parametric CAD Design tab (#15238, #16019, #16158, #16227; e027f8b225) ⚠️ Fork-releváns

Az új **Design** tab egy sketch-first parametric CAD környezetet ad OrcaSlicerbe: sketch, constraint, solid feature tree, majd commit a plate-re. A funkció `SLIC3R_CAD` build gate és az `enable_cad_feature` app pref mögött van; kapcsolódó új app config kulcsok: `auto_close_sketch_loops`, `design_connector_face_glyph`, `design_show_bed`. A UI-ban feature tree, sketch tools, reference plane választás, Revolve/Text/Fillet/Chamfer/Hole/Thread és jobb minőségű studio lighting jelenik meg; a follow-up eltávolította a külön Prepare-beli CAD Primitive/Sketch gizmo-kat, így a CAD workflow a Design tabra koncentrál. A CAD recipe 3MF/BBS-3MF-ben persistálódik, ezért projekt újranyitáskor szerkeszthető feature history jön vissza, nem csak frozen mesh. Slicing output közvetlenül nem változik, de a committed CAD body valódi geometriaként szeletelődik; a 3MF persistence és libslic3r CAD kernel miatt headless fork szempontból releváns.

## Speed Dial

### Speed Dial action palette improvements (#15562, #15867, #16369; e72ace164b)

A **Speed Dial** parancspaletta unified keresést kapott actions, commands, plugin actions és settings között, fuzzy matchinggel, kategóriafejlécekkel, recent listával és pinnelhető favourites sávval. A dialog a Space shortcutról nyitható, Preferences-ben kezelhető az `enable_speed_dial`, a recent limit pedig `speed_dial_recent_count`; a #16369 miatt lokalizált UI mellett angol action nevekre is lehet keresni. A plugin page capabilities is bekerülnek actionként: egy plugin által adott top-level notebook page Speed Dialból megnyitható, és overflowból is látható tabra vált. Ez UI-only: slicing outputot és 3MF-et nem módosít.

## Előnézet / 3D nézet

### Section View in 3D canvas (#15879)

Új **Section view** került a 3D canvas bal alsó toolbarjába Prepare, assembly view és Preview nézetekhez. A panel sliderrel állítja a vágási mélységet, **Set viewing angle** gombbal a kamera felé forgatja a plane-t, Alt + mouse wheel pedig a canvasból mozgatja a metszetet. Csak view setting: modellt, slice-ot, 3MF-et és plate thumbnailt nem módosít.

### Center of mass markers (#16291) ⚠️ Fork-releváns

A canvas toolbar menü új **Center of mass** eleme Prepare és Preview nézetben tömegközéppont markereket rajzol plate, object instance, assembly body, illetve Preview-ban support/raft szintre. A markerre kattintva tömeg, volume, bounding-box pozíció és inertia adatok jelennek meg; az app pref kulcs `show_center_of_mass`, alapból off. Prepare-ben a mesh és filament density alapján számol, Preview-ban a `GCodeProcessor` az aktuális toolpath tömegeloszlását összegzi, ezért a layer sliderrel a tömegközéppont mozgása is látható. G-code vagy modell nem változik, de libslic3r/GCodeProcessor adatútvonalat érint, ezért headless környezetben figyelendő.

### Faster Preview rendering and lower memory (#15884, #15833, #16389, #15674, #15664, #16440, #16065, #15883) ⚠️ Fork-releváns

A Preview több teljesítményjavítást kapott: cached per-layer sums váltják a per-frame lineáris kereséseket, index buffer csökkenti a segment draw shader hívásait, 16-bit index javít régi GPU-kon, és top-down camera esetén fordított toolpath draw order csökkenti az overdraw-t. A 3D viewport mouse hover terhelése is csökkent `SceneCache`, skipped identical frames és elhagyott felesleges raycast miatt; kapcsolódó app prefs: `opengl_scene_cache`, `opengl_skip_identical_frames`, `opengl_show_render_timings`, `opengl_realistic_shadows`. A G-code preview betöltése és resetje kevesebb peak memóriát tart meg; a #16065 a `GCodeProcessorResult` move assignment/reset útvonalat is javítja. Rendering behavior és G-code nem változik, de a GCodeProcessor/libvgcode memóriaútvonal miatt a CLI/headless export pipeline körül is releváns lehet.

### Preview view defaults, colors and X-Ray (#15769, #15809, #15770)

A G-code Preview default view type most konfigurálható: `preview_default_view_type` értékei közt az `auto` és `last` viselkedés is szerepel, a legutóbbi választás `preview_last_view_type` alatt tárolódik. A Preview színei és realistic view integrációja javult; az `opengl_realistic_preview` pref külön engedi a Preview canvasra is rátenni a realistic view/shadow/SSAO költségesebb útját. Az új **X-Ray** view mode a 3D viewport shader útján segít belátni a modell belsejébe. Ezek nézet- és preferencia-változások, slicing outputot és 3MF-et nem módosítanak.

## Felhasználói felület

### Assignable keyboard shortcuts (#15706)

A shortcut rendszer szerkeszthetővé vált: Preferences > Control alatt **Keyboard shortcuts** dialog nyílik, és sok canvas/gizmo/menu action saját `Shortcut` azonosítót kapott. A Speed Dial alap shortcutja Space, a shortcuts persistence külön `shortcuts` config sectionben történik. Ez UI-only, nem érinti a szeletelést vagy a 3MF-et.

### Lazy-loaded main window panels (#15811)

A főablak paneljei idle-ben vagy első használatkor épülnek fel, így startup gyorsabb, különösen sok tab/panel esetén. A változás a GUI konstrukciót, deferred page construction helper-eket és plugin/design panelek életciklusát érinti. Slicing output, 3MF és preset formátum nem változik.

### Everyday UI polish and workflow preferences (#13946, #15774, #16015, #15620, #15902, #16363)

Az AMS material dropdown favorit filamenteket kapott: a csillag ikon a **AMSMaterialsSetting** dialogban jelöl, a lista tetején **Favorite filaments** szekció jelenik meg, a tárolt app config kulcs `ams_favorite_filament_ids`. A print/export gomb meg tudja jegyezni az utolsó választott print actiont a `remember_print_action` pref alapján; a background job alatt az undo/redo blokkolva van, hogy a job ne térjen vissza elavult modellállapotra. macOS/Linux context menu ikonok, egységesebb DPI-aware scroll rate, és `.po` kataloguson át fordított web dialog/page szövegek javítják a mindennapi UX-et. Ezek nem változtatják a szeletelési eredményt vagy a 3MF formátumot.

### Multi-nozzle and extruder UI cleanup (#16075, #16162, #15083)

A multi-nozzle UI kompaktabb és olvashatóbb lett: új guidance ikon, kisebb wrapping, jobb modified-state jelzés, BBL nozzle selector igazítás és compact BBL nozzle widget. A Printer settings és Publish dialog több extruder esetén multiswitch-et használ külön tabok helyett; T1/T2 illetve Left/Right terminológiát és dinamikus paddinget kap. A #16162 a több extruderből származó default értékek és revert/modified állapot kezelését is javítja, de új `PrintConfig` opciót nem adott hozzá. Elsősorban UI/preset editing felület, slicing output csak a user tényleges preset változtatásain keresztül változik.

## Presetek kezelése, 3MF és mesh repair

### Publish 3MF Workflow (#15251) ⚠️ Fork-releváns

Új **File > Publish** workflow készült megosztható `.3mf` projektekhez, amelyek nem írják felül a fogadó teljes printer/filament/process presetjeit. A Publish dialog Printer/Filament/Process tabokon kereshető/selectable settings listát ad, filament slotonként requirementeket és opcionális full publish-t kezel. Exportkor a published 3MF csak a kiválasztott kulcsokat, material identityt és plate geometryt írja, metadata mezőkkel (`published`, `published_keys`, `published_material_keys`); importkor csak author-selected settingek alkalmazódnak, a recipient preset többi része megmarad. Ez 3MF formátumot, preset load/match szabályokat és libslic3r preset bundle logikát érint, ezért fork-releváns.

### Printer bundle bed assets (#15965) ⚠️ Fork-releváns

A printer bundle export most opcionálisan becsomagolja a `bed_custom_texture` és `bed_custom_model` fájlokat a `.orca_printer` zip `bed/` alá. Importkor a bundle kicsomagolja az asseteket saját folderébe, és a preset pathokat az új helyre írja át; path traversal jellegű utak elutasításra kerülnek. A manifest `printer_asset` bejegyzése printerenként kezeli a bed asseteket, régi bundle hiányzó assettel továbbra is betölthető. Ez preset bundle formátum és preset loading változás, slicing outputot közvetlenül nem módosít.

### Safer and faster preset/config IO (#15558, #15861, #15943) ⚠️ Fork-releváns

A parent nélküli preset mentésekor a **Detach from parent** viselkedés kevésbé zavaró parentless profiloknál. A config/preset fájlok több instance között OS-level lockot és atomic write-ot kaptak (`InstanceLock`, `write_file_atomically()`), így kevesebb a részlegesen olvasott JSON/.info és az interleaving save; read-only CLI scan nem hoz létre lockot. A preset betöltés párhuzamosabb lett, cache/resolve helper-ekkel jelentős startup/load gyorsulást céloz. Ez preset inheritance/load/save viselkedést érint, ezért headless/preset-kezelő forkoknál különösen fontos.

### CGAL mesh repair, Fix All and CLI `--repair` (#16366) ⚠️ Fork-releváns

A **Fix Model** CGAL 6.2 alapú `repair_mesh()` implementációt kapott: crack welding, coincident triangle cancellation, orientation fix, hole filling, local self-intersection removal és nonzero-winding union. A GUI-ban Fix Model mellett **Fix All** és **Fix All Plates** menük jelennek meg, a STEP surface model import és Split to parts edge case-ek javultak. Új `PrintConfig` option: `repair`, amely a parancssoros `--repair` útvonalat újra engedélyezi, és ugyanazt a mesh repair logikát használja. Ez közvetlenül CLI/headless és libslic3r mesh-előkészítés változás, a slicing output javított/repaired mesh esetén változhat.

## Plugin rendszer és printer-agent API

### Plugin host UI and lifecycle APIs (#15293, #15318, #15736, #16324, #16118, #16254, #15568, #16257, #16335)

A plugin API lifecycle eventeket kapott project, slicing pipeline, plate/model edit, preset, device és print/send job eseményekre; a plugin a payload után célzott API-kon kérhet részleteket. A plater notification API egyszerű host notificationt ad, a dockable HTML panel API pedig `orca.host.ui.create_dock_panel(...)` hívással AUI dock pane-be ágyaz plugin HTML-t, `post/show/hide/close/is_open` handle-lel. Új host fact API-k: `app_info()`, `gl_info()`, `selected_printer()`, `plater.project_path()` és `plater.export_3mf_copy(path)`; az utóbbi auditált fájlírásként viselkedik, de a projekt mentett állapotát nem módosítja. A local plugin version most a PEP 723 file headerből frissül, az `os.exec` audit kategória permission promptot kapott, a plugin UI dialogok/panelek szebb stílust, késleltetett dock-pane létrehozást és X11 maximize fixet kaptak. Ezek főleg GUI/plugin API változások; slicing outputot és 3MF formátumot nem módosítanak, kivéve hogy plugin export-copy API külön 3MF másolatot tud írni explicit plugin actionként.

### Configurable printer agents and Python plugin safety (#16027, #15710, #15819)

A printer-agent infrastruktúra Bambu-only feltételezésekből általánosabb agent registry felé mozdult, Moonraker/Qidi/Snapmaker/Orca agent útvonalakkal, kamerastream támogatással és agent-specifikus command/file-transfer/network viselkedéssel. A globális kísérleti `use_printer_agents` toggle alapból off, így legacy print-host behavior marad, amíg a user nem kapcsolja; a printer presetben agent id alapú választás és device reset/swap logika működik. A Python printer agent trampoline most elkapja a plugin kivételeket, logolja őket, és a missing-agent fallback értékeket adja vissza, így egy hibás agent nem dönti le a hostot; `bind_detect` out-param átadás is javult. Ez printer/device plugin API és network UI változás, nem 3MF vagy slicing output változás.

# 3. CLI / teljesítmény / build / biztonság
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
