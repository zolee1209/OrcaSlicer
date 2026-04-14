# Optimalizált build – Intel Xeon Gold 6148 (skylake-avx512)

## Rendszerkövetelmények

Ubuntu 24.04 (Noble), két Xeon Gold 6148 processzor.

### Szükséges csomagok (egyszeri telepítés, sudo szükséges)

```bash
# 1. Rendszer build-függőségek (standard OrcaSlicer)
bash build_linux.sh -u

# 2. GCC 15 – Ubuntu Toolchain PPA
sudo add-apt-repository ppa:ubuntu-toolchain-r/test
sudo apt-get update
sudo apt-get install -y gcc-15 g++-15

# 3. Clang 20 – LLVM official apt repo
curl -fsSL https://apt.llvm.org/llvm.sh -o /tmp/llvm.sh
chmod +x /tmp/llvm.sh
sudo bash /tmp/llvm.sh 20 all
rm /tmp/llvm.sh

# Ellenőrzés
gcc-15 --version    # → gcc-15 (Ubuntu 15.2.0-...) 15.2.0
clang-20 --version  # → Ubuntu clang version 20.1.8
```

> **Miért ez a két verzió?**
> - A Flatpak 2.3.2 bináris GCC 15.2.0-val fordult (Arch Linux toolchain). Ezzel egyező fordítóverziót kaptunk.
> - Clang 20 jobb AVX-512 integer auto-vektorizálót tartalmaz a Clipper polygon műveletekhez, mint GCC 15. A `clang-20` fordít, a `gcc-15` biztosítja a runtime library-kat (`libstdc++`, `libgcc_s`).

---

## Build parancs

### Első build (deps + slicer, ~12 perc)

```bash
bash build_linux.sh -x -c -d -s
```

### Újraépítés (csak slicer, ~5 perc, ha a deps nem változott)

```bash
bash build_linux.sh -x -c -s
```

### Kapcsolók magyarázata

| Kapcsoló | Jelentés |
|----------|----------|
| `-x` | Natív CPU optimalizáció (Xeon 6148) |
| `-c` | Clean build (törli a `build/` könyvtárat) |
| `-d` | Deps újrafordítása (TBB, Boost, wxWidgets, stb.) |
| `-s` | OrcaSlicer bináris fordítása |

> Az `-i` (AppImage) kapcsoló elhagyható — a bináris közvetlenül futtatható:
> `./build/src/Release/orca-slicer`

---

## Mit csinál a `-x` kapcsoló

A `build_linux.sh`-ban definiált natív optimalizációs blokk az alábbi beállításokat alkalmazza:

### Fordító

**Clang 20** automatikusan kiválasztva (keresési sorrend: `22 21 20 19 18 17 16`).
Ha Clang nem elérhető, fallback: GCC 15 → GCC 14 → rendszer GCC.

### Fordítási flagek

```
-O3
-march=skylake-avx512    # Xeon 6148 pontos ISA: AVX-512F/BW/CD/DQ/VL + FMA + BMI1/2 + AES
-mtune=skylake-avx512    # Skylake-SP scheduling/latency modell
-flto=thin               # Clang ThinLTO: cross-module inlining a deps határain átnyúlva
-fno-plt                 # PLT trampoline eliminálás shared library hívásoknál
-fomit-frame-pointer     # Egy extra regiszter felszabadul hot loop-okban
-DNDEBUG
```

### Linker

**ld.gold** – multi-pass archive scanning (szükséges a statikus TBB + dinamikus TBB `.so` vegyes linkeléshez). Az LLD single-pass természete miatt a TBB `r1::` szimbólumok nem oldódnak fel LLD-del.

A `CMAKE_LINKER` explicit `/usr/bin/ld.gold`-ra van állítva, hogy a Clang 20 ne auto-detektálja az `ld.lld-20`-at.

### Runtime

```
-static-libgcc
-static-libstdc++
```

A C++ runtime statikusan linkelve → nincs GCC verziófüggőség futásidőben.

### TBB

A `deps/TBB/TBB.cmake`-ben `BUILD_SHARED_LIBS=ON` — a TBB **dinamikus** `.so`-ként épül (`libtbb.so.12`). Ez szükséges a ThinLTO + statikus archívum kompatibilitáshoz (a statikus `libtbb.a`-ban lévő `r1::` szimbólumok LTO-val nem feloldhatók).

A `libtbb.so.12.5` és `libtbbmalloc.so.2.5` fájlok a `deps/build/OrcaSlicer_dep/usr/local/lib/`-ben vannak. Ha az alkalmazást más gépre másolod, ezeket az `orca-slicer` mellé kell helyezni és `LD_LIBRARY_PATH`-ba felvenni.

### Strip

A build után a bináris automatikusan strip-pelve lesz (`strip --strip-all`): ~115MB → ~94MB.

---

## Kész bináris helye

```
build/src/Release/orca-slicer
```

---

## Teljes konfiguráció áttekintése (utolsó sikeres build)

| Paraméter | Érték |
|-----------|-------|
| Fordító | Clang 20.1.8 |
| GCC runtime | GCC 15.2.0 |
| `-march` | `skylake-avx512` |
| LTO | ThinLTO (`-flto=thin`) |
| Linker | ld.gold 1.16 |
| TBB | dinamikus (`libtbb.so.12.5`) |
| Strip | igen |
| Binary méret | 94MB |
| zmm (AVX-512) utasítások | ~4289 |
| Max GLIBC igény | GLIBC_2.38 |
| Build idő (deps + slicer) | ~8.5 perc (40 core) |

---

## Összehasonlítás a Flatpak 2.3.2-vel

| | Flatpak 2.3.2 | Optimalizált build |
|---|---|---|
| Fordító | GCC 15.2.0 (Arch Linux) | Clang 20.1.8 |
| Méret | 94MB | 94MB |
| AVX-512 (zmm) | ~4296 | ~4289 |
| ThinLTO | nem | **igen** |
| `-march=skylake-avx512` | nem ismert | **igen** |
| GLIBC igény | 2.42 (Flatpak sandbox) | **2.38** (bármely Ubuntu 22.04+) |
| TBB | dinamikus | **dinamikus** |

---

## Ismert problémák és megkerülésük

### `ld.lld` auto-detektálás Clang 20-zal
A Clang 20 telepítésekor a CMake automatikusan az `ld.lld-20`-at választja linkerként. A `build_linux.sh` ezt felülírja a `CMAKE_LINKER=/usr/bin/ld.gold` explicit beállításával a `NATIVE_OPT_CFLAGS` tömbben.

### TBB + LTO inkompatibilitás
A GCC full LTO (`-flto=auto`) nem működik statikus TBB archívummal — a `r1::` ABI szimbólumok nem oldódnak fel. Clang ThinLTO + dinamikus TBB + ld.gold kombinációval a probléma megkerülhető.

### `libgstreamer1.0-dev` hiánya
A Clang 20 apt telepítése eltávolíthatja ezt a csomagot. Ha a cmake konfiguráció `gstreamer-1.0 not found` hibával áll meg:
```bash
sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
```
