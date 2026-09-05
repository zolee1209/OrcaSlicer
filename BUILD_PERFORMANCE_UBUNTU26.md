# Futásidő-optimalizált build – Ubuntu 26.04 LTS, 2× Xeon Gold 6148, 64GB RAM

Cél: **a lehető leggyorsabban futó szeletelés**, nem a legkisebb bináris. GPU (RTX 3050)
a szeleteléshez **nem releváns** — a Clipper/geometria/G-code motor 100%-ban CPU+TBB
munkaterhelés, a GPU csak az OpenGL preview/thumbnail renderelésnél számít.

## Környezet-frissülés (24.04 → 26.04) — amit ez ingyen hoz

| | 24.04 (régi doksi) | 26.04 (most) |
|---|---|---|
| Alap `gcc` | 13 (PPA-ból telepített 15) | **15.2.0 (natívan, nincs PPA kellék)** |
| Alap `clang` | (LLVM script 20) | **21.1.8 (natívan telepítve)** |
| `ld.lld` | 20 | 21.1.8 |
| glibc | 2.38 cél (kompatibilitás miatt) | 2.43 (nem gond, ha nem viszed más gépre) |
| GCC 16 | nincs | **snapshot csomag elérhető** (`16-20260322-1ubuntu1`, kísérleti, nem stabil release) |
| `mold` linker | nem volt csomagolva | **elérhető apt-ból** (2.40.4) |

A `build_linux.sh` clang-keresési sorrendje (`22 21 20 19 18 17 16`) már eddig is a
legújabbat választja — **külön script-módosítás nélkül** clang-21-re vált egy sima
újrafordítással.

## CPU: `-march=skylake-avx512` marad helyes

`lscpu` megerősítve: `avx512f avx512dq avx512cd avx512bw avx512vl`, de **nincs**
`avx512_vnni`/`avx512bf16` → a CPU tényleg Skylake-SP (nem Cascade Lake), a
`-march=cascadelake` hibás/nem biztonságos célzás lenne. `skylake-avx512` a helyes,
pontos cél, nem kell változtatni.

## Amit ebben a körben bevezettünk (build_linux.sh, `-x` blokk)

**jemalloc allokátor** — a szeletelés erősen párhuzamos (TBB `parallel_for` a Clipper
polygon-műveleteken), ez sokat allokál/felszabadít sok szálból egyszerre; a glibc
szál-arénás mallocja ezen a mintázaton kontendál. A `libjemalloc2` csomag már telepítve
van a gépen (más csomag függőségeként) — a build script most ezt észleli
(`ldconfig -p | grep libjemalloc`) és belinkeli pontos soname-mel
(`-l:libjemalloc.so.2`, nincs szükség `libjemalloc-dev`-re). Tisztán link-time
interpozíció, forráskód-módosítás nélkül.

## Futásidejű (OS-szintű) tuning javaslatok — NEM build_linux.sh rész

Ezeket a rendszeren kell beállítani, nem a fordítás része. **Egyik sem lett még
alkalmazva**, mert root kell hozzájuk vagy más folyamatokat is érintenek:

1. **CPU governor**: jelenleg `schedutil`, nem `performance`. Szerver/batch
   szeletelési munkaterhelésnél a `performance` governor kiküszöböli a
   frekvencia-felfutás késleltetését:
   ```bash
   sudo cpupower frequency-set -g performance
   ```
2. **NUMA**: 2 socket, 20 mag/socket, nincs HT. 40 szálas TBB futtatásnál a
   memória-elhelyezés számít — `numactl --interleave=all` egyenletesen szórja a
   memóriát mindkét node közt (elkerüli az egy-node "first touch" hotspot-ot):
   ```bash
   numactl --interleave=all ./build/src/Release/orca-slicer ...
   ```
   (A www app `api_routes.py`-jában van egy kikommentezett
   `--cpunodebind=0 --membind=0` — az EGY node-ra korlátozna (20 mag, alacsonyabb
   memória-late­ncy), az `--interleave=all` valószínűleg jobb, ha mind a 40 magot
   ki akarod használni. Empirikusan érdemes mindkettőt lemérni nagy modellen.)
3. **Transparent Huge Pages**: jelenleg `madvise`. `always`-re állítás
   rendszerszinten segíthet nagy memóriaigényű modelleknél, de más folyamatokat is
   érint — csak akkor érdemes, ha megmérjük, hogy tényleg számít.

## Következő kör: Profile-Guided Optimization (PGO) — még NINCS implementálva

A legnagyobb várható további nyereség, de 2-fázisú build kell hozzá (kb. a duplája
az időnek): (1) `-fprofile-generate`-tel fordítás, (2) néhány reprezentatív (kis és
nagy) modell szeletelése az instrumentált binárissal, (3) `llvm-profdata-21 merge`,
(4) újrafordítás `-fprofile-use`-zal. `llvm-profdata-20`/`-21` már telepítve van.
Ehhez külön menetben térünk vissza, ha ez a kör beválik.

## Kipróbálásra érdemes, de NEM alapértelmezett (kísérleti)

- **`mold` linker** (`sudo apt install mold`): gyorsabb linkelés, és elvileg jobban
  kezeli a többlépéses archívum-feloldást, mint `ld.lld` — ha ez igaz rá, akkor
  esetleg megengedhetné a **statikus TBB + ThinLTO** kombót (jelenleg a TBB
  dinamikus `.so`, mert `ld.gold` kellett a `r1::` szimbólumok miatt). Futásidejű
  sebességre önmagában a linker választása nem hat, csak ha ezáltal több
  cross-modul inline-olás válik lehetővé LTO alatt.
- **GCC 16 snapshot** (`16-20260322-1ubuntu1`): fejlesztői előzetes, nem stabil
  kiadás — érdemes lemérni Clang 21 ellenében, de nem alapértelmezett, amíg nem
  stabil release.

## Build parancs (ez a kör, 40 mag)

```bash
bash build_linux.sh -x -c -s -j 40
```

Kimenet: `build/src/Release/orca-slicer` (a `build/src/Release/` mappa emellett
tartalmazza a csomagolt Python runtime-ot, `uv`-t és az ffmpeg megosztott
libeket is — ez a jelenlegi upstream `build_linux_image.sh` mindig lefuttatja
`-s`-hez, `-i` AppImage-csomagolás nélkül is; ez NEM hibás konfiguráció, csak az
upstream 1573 commit egyike bevezette ezt a bundle-viselkedést).
