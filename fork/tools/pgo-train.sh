#!/usr/bin/env bash
# FORK(build-pgo): PGO-profil előállítása a fő build/ fordításához (build_linux.sh -x -s -P <profdata>).
#
# 1. Instrumentált build a build-pgo-gen/ könyvtárba: ugyanazok a C/C++ flagek, mint a fő build/ (CMakeCache.txt-ből,
#    tehát előbb kell egy `build_linux.sh -x -s`), plusz -fprofile-generate. Linker: lld, mert a gold az instrumentált
#    ThinLTO-t a nem instrumentált statikus deps-szel (pl. libdraco.a) nem tudja linkelni ("discarded section").
#    A profilt a linker nem befolyásolja; a végső PGO-build a megszokott gold-dal készül.
# 2. Profilgyűjtés: a fork/tools/bench.py futásai az instrumentált binárissal, EGYSZÁLÚAN (taskset 1 CPU), párhuzamosan
#    külön CPU-kon. Több szálon a közös profil-számlálók miatt 20–60× lassabb (cache-line kontenció); külön folyamatok
#    nem osztoznak a számlálókon. A számlált munka a szálszámtól független.
# 3. llvm-profdata merge -> <out>/merged.profdata
#
# Használat:  fork/tools/pgo-train.sh [-j N] [-o OUTDIR] [--skip-build]
#   -j N         fordítási és ThinLTO link-szálak (alap: 20; memória: csúcs ~28 GB)
#   -o OUTDIR    profil-könyvtár (alap: build-pgo-data)
#   --skip-build csak profilgyűjtés + merge a meglévő build-pgo-gen binárissal
# Környezet:  ORCA_BENCH_STL (helmet), ORCA_PGO_BENCHY (Benchy STL) a profilgyűjtő modellekhez.
# Idő ezen a gépen: build ~10 perc (-j 20), profilgyűjtés ~20 perc, utána a PGO-build ~8 perc.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
JOBS=20
OUT="$REPO/build-pgo-data"
SKIP_BUILD=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -j) JOBS=$2; shift 2 ;;
        -o) OUT=$(realpath -m "$2"); shift 2 ;;
        --skip-build) SKIP_BUILD=1; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "Ismeretlen argumentum: $1"; exit 1 ;;
    esac
done

MAIN_CACHE="$REPO/build/CMakeCache.txt"
GEN_DIR="$REPO/build-pgo-gen"
GEN_BIN="$GEN_DIR/src/Release/orca-slicer"
HELMET=${ORCA_BENCH_STL:-$HOME/Letöltések/Battle_Damaged_Helmet.stl}
BENCHY=${ORCA_PGO_BENCHY:-$HOME/www/testfiles/3DBenchy.stl}

cache_get() { grep -m1 "^$1:" "$MAIN_CACHE" | cut -d= -f2-; }
# Drop the flags of an earlier PGO build, so that the instrumented build is not itself profile-guided.
strip_pgo() { tr ' ' '\n' <<< "$1" | grep -v -e '^-fprofile-' -e '^-Wno-profile-instr' -e '^-Wno-backend-plugin' | tr '\n' ' '; }

[[ -f "$MAIN_CACHE" ]] || { echo "Nincs $MAIN_CACHE – előbb: bash build_linux.sh -x -s"; exit 1; }
CXX=$(cache_get CMAKE_CXX_COMPILER)
CC=$(cache_get CMAKE_C_COMPILER)
[[ "$CXX" == *clang* ]] || { echo "A fő build nem Clang-gal készült ($CXX); a PGO a -x Clang útvonalát feltételezi."; exit 1; }
VER=$(sed -n 's/.*clang++-\([0-9]*\)$/\1/p' <<< "$CXX")
LLD=$(command -v "ld.lld${VER:+-$VER}" || command -v ld.lld)
PROFDATA=$(command -v "llvm-profdata${VER:+-$VER}" || command -v llvm-profdata)
CFLAGS=$(strip_pgo "$(cache_get CMAKE_C_FLAGS_RELEASE)")
CXXFLAGS=$(strip_pgo "$(cache_get CMAKE_CXX_FLAGS_RELEASE)")
for f in "$HELMET" "$BENCHY"; do [[ -f "$f" ]] || { echo "Hiányzó profilgyűjtő modell: $f"; exit 1; }; done

if [[ -z "$SKIP_BUILD" ]]; then
    echo ">>> Instrumentált build: $GEN_DIR (-j $JOBS, $CXX, lld)"
    GEN="-fprofile-generate"
    LINK="-flto=thin -fuse-ld=lld -Wl,--thinlto-jobs=$JOBS"
    cmake -S "$REPO" -B "$GEN_DIR" -G "Ninja Multi-Config" \
        -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_LINKER="$LLD" \
        -DDEP_BUILD_DIR="$(cache_get DEP_BUILD_DIR)" -DCMAKE_PREFIX_PATH="$(cache_get CMAKE_PREFIX_PATH)" \
        "-DCMAKE_C_FLAGS_RELEASE=$CFLAGS $GEN" "-DCMAKE_CXX_FLAGS_RELEASE=$CXXFLAGS $GEN" \
        "-DCMAKE_EXE_LINKER_FLAGS_RELEASE=$LINK -static-libgcc -static-libstdc++ -l:libjemalloc.so.2 $GEN" \
        "-DCMAKE_SHARED_LINKER_FLAGS_RELEASE=$LINK $GEN" "-DCMAKE_MODULE_LINKER_FLAGS_RELEASE=$LINK $GEN" \
        -DSLIC3R_PCH=ON -DORCA_TOOLS=ON > "$GEN_DIR.configure.log" 2>&1 || { tail -20 "$GEN_DIR.configure.log"; exit 1; }
    # Build-time helpers (e.g. encoding-check) are instrumented too; keep their profiles out of the source tree.
    LLVM_PROFILE_FILE="$GEN_DIR/build-helpers-%p.profraw" cmake --build "$GEN_DIR" --config Release --target OrcaSlicer -j "$JOBS"
fi
[[ -x "$GEN_BIN" ]] || { echo "Nincs instrumentált bináris: $GEN_BIN"; exit 1; }

mkdir -p "$OUT"
rm -f "$OUT"/*.profraw "$OUT/merged.profdata"
echo ">>> Profilgyűjtés (egyszálú futások párhuzamosan, CPU-hoz kötve): $OUT"
BENCH=(python3 "$REPO/fork/tools/bench.py" run)
COMMON=(--bin "$GEN_BIN" --env "LLVM_PROFILE_FILE=$OUT/%p-%m.profraw")
NOSUP="$REPO/fork/bench/process/nosupport.json"
CPUS=$(nproc)
pids=()
taskset -c 0                 "${BENCH[@]}" pgo-train-helmet         "${COMMON[@]}" --stl "$HELMET" > "$OUT/train-helmet.log" 2>&1 & pids+=($!)
taskset -c $((CPUS / 2))     "${BENCH[@]}" pgo-train-benchy         "${COMMON[@]}" --stl "$BENCHY" -- --clone-objects 20 > "$OUT/train-benchy.log" 2>&1 & pids+=($!)
taskset -c $((CPUS / 2 + 1)) "${BENCH[@]}" pgo-train-benchy-nosup   "${COMMON[@]}" --stl "$BENCHY" --process "$NOSUP" -- --clone-objects 20 > "$OUT/train-benchy-nosup.log" 2>&1 & pids+=($!)
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
grep -h "^\[pgo-train" "$OUT"/train-*.log || true
if [[ $fail -ne 0 ]] || grep -q "exit=[1-9]" "$OUT"/train-*.log; then
    echo "Hiba a profilgyűjtésben, lásd $OUT/train-*.log"; exit 1
fi

"$PROFDATA" merge -o "$OUT/merged.profdata" "$OUT"/*.profraw
rm -f "$OUT"/*.profraw
echo ">>> Kész: $OUT/merged.profdata"
echo "    PGO-s fő build:  bash build_linux.sh -x -s -j $JOBS -P $OUT/merged.profdata"
