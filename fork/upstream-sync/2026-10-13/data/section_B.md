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
