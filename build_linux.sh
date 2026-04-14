#!/usr/bin/env bash
set -e # Exit immediately if a command exits with a non-zero status.
SECONDS=0

SCRIPT_NAME=$(basename "$0")
SCRIPT_PATH=$(dirname "$(readlink -f "${0}")")

pushd "${SCRIPT_PATH}" > /dev/null

function usage() {
    echo "Usage: ./${SCRIPT_NAME} [-1][-b][-c][-d][-D][-e][-h][-i][-j N][-p][-r][-s][-t][-u][-l][-L][-x]"
    echo "   -1: limit builds to one core (where possible)"
    echo "   -j N: limit builds to N cores (where possible)"
    echo "   -b: build in Debug mode"
    echo "   -c: force a clean build"
    echo "   -C: enable ANSI-colored compile output (GNU/Clang only)"
    echo "   -d: download and build dependencies in ./deps/ (build prerequisite)"
    echo "   -D: dry run"
    echo "   -e: build in RelWithDebInfo mode"
    echo "   -h: prints this help text"
    echo "   -i: build the Orca Slicer AppImage (optional)"
    echo "   -p: boost ccache hit rate by disabling precompiled headers (default: ON)"
    echo "   -r: skip RAM and disk checks (low RAM compiling)"
    echo "   -s: build the Orca Slicer (optional)"
    echo "   -t: build tests (optional), requires -s flag"
    echo "   -u: install system dependencies (asks for sudo password; build prerequisite)"
    echo "   -l: use Clang instead of GCC (default: GCC)"
    echo "   -L: use ld.lld as linker (if available)"
    echo "   -x: native CPU optimized build (Xeon 6148 / skylake-avx512, GCC 14, LTO, strip)"
    echo "For a first use, you want to './${SCRIPT_NAME} -u'"
    echo "   and then './${SCRIPT_NAME} -dsi'"
}

SLIC3R_PRECOMPILED_HEADERS="ON"

unset name
BUILD_DIR=build
BUILD_CONFIG=Release
while getopts ":1j:bcCdDehiprstulLx" opt ; do
  case ${opt} in
    1 )
        export CMAKE_BUILD_PARALLEL_LEVEL=1
        ;;
    j )
        export CMAKE_BUILD_PARALLEL_LEVEL=$OPTARG
        ;;
    b )
        BUILD_DIR=build-dbg
        BUILD_CONFIG=Debug
        ;;
    c )
        CLEAN_BUILD=1
        ;;
    C )
        COLORED_OUTPUT="-DCOLORED_OUTPUT=ON"
        ;;
    d )
        BUILD_DEPS="1"
        ;;
    D )
        DRY_RUN="1"
        ;;
    e )
        BUILD_DIR=build-dbginfo
        BUILD_CONFIG=RelWithDebInfo
        ;;
    h ) usage
        exit 1
        ;;
    i )
        BUILD_IMAGE="1"
        ;;
    p )
        SLIC3R_PRECOMPILED_HEADERS="OFF"
        ;;
    r )
        SKIP_RAM_CHECK="1"
        ;;
    s )
        BUILD_ORCA="1"
        ;;
    t )
        BUILD_TESTS="1"
        ;;
    u )
        export UPDATE_LIB="1"
        ;;
    l )
        USE_CLANG="1"
        ;;
    L )
        USE_LLD="1"
        ;;
    x )
        NATIVE_OPTIMIZED="1"
        ;;
    * )
	echo "Unknown argument '${opt}', aborting."
	exit 1
	;;
  esac
done

if [ ${OPTIND} -eq 1 ] ; then
    usage
    exit 1
fi

function check_available_memory_and_disk() {
    FREE_MEM_GB=$(free --gibi --total | grep 'Mem' | rev | cut --delimiter=" " --fields=1 | rev)
    MIN_MEM_GB=10

    FREE_DISK_KB=$(df --block-size=1K . | tail -1 | awk '{print $4}')
    MIN_DISK_KB=$((10 * 1024 * 1024))

    if [[ ${FREE_MEM_GB} -le ${MIN_MEM_GB} ]] ; then
        echo -e "\nERROR: Orca Slicer Builder requires at least ${MIN_MEM_GB}G of 'available' mem (system has only ${FREE_MEM_GB}G available)"
        echo && free --human && echo
        echo "Invoke with -r to skip RAM and disk checks."
        exit 2
    fi

    if [[ ${FREE_DISK_KB} -le ${MIN_DISK_KB} ]] ; then
        echo -e "\nERROR: Orca Slicer Builder requires at least $(echo "${MIN_DISK_KB}" |awk '{ printf "%.1fG\n", $1/1024/1024; }') (system has only $(echo "${FREE_DISK_KB}" | awk '{ printf "%.1fG\n", $1/1024/1024; }') disk free)"
        echo && df --human-readable . && echo
        echo "Invoke with -r to skip ram and disk checks."
        exit 1
    fi
}

function print_and_run() {
    cmd=()
    # Remove empty arguments, leading and trailing spaces
    for item in "$@" ; do
        if [[ -n $item ]]; then
            # Trim leading/trailing whitespace without splitting on internal spaces
            item="${item#"${item%%[![:space:]]*}"}"
            item="${item%"${item##*[![:space:]]}"}"
            cmd+=( "${item}" )
        fi
    done

    echo "${cmd[@]}"
    if [[ -z "${DRY_RUN}" ]] ; then
        "${cmd[@]}"
    fi
}

# cmake 4.x compatibility workaround
export CMAKE_POLICY_VERSION_MINIMUM=3.5

DISTRIBUTION=$(awk -F= '/^ID=/ {print $2}' /etc/os-release | tr -d '"')
DISTRIBUTION_LIKE=$(awk -F= '/^ID_LIKE=/ {print $2}' /etc/os-release | tr -d '"')
# Check for direct distribution match to Ubuntu/Debian
if [ "${DISTRIBUTION}" == "ubuntu" ] || [ "${DISTRIBUTION}" == "linuxmint" ] ; then
    DISTRIBUTION="debian"
# Check if distribution is Debian/Ubuntu-like based on ID_LIKE
elif [[ "${DISTRIBUTION_LIKE}" == *"debian"* ]] || [[ "${DISTRIBUTION_LIKE}" == *"ubuntu"* ]] ; then
    DISTRIBUTION="debian"
elif [[ "${DISTRIBUTION_LIKE}" == *"arch"* ]] ; then
    DISTRIBUTION="arch"
elif [[ "${DISTRIBUTION_LIKE}" == *"suse"* ]] ; then
    DISTRIBUTION="suse"
fi

if [ ! -f "./scripts/linux.d/${DISTRIBUTION}" ] ; then
    echo "Your distribution \"${DISTRIBUTION}\" is not supported by system-dependency scripts in ./scripts/linux.d/"
    echo "Please resolve dependencies manually and contribute a script for your distribution to upstream."
    exit 1
else
    echo "resolving system dependencies for distribution \"${DISTRIBUTION}\" ..."
    # shellcheck source=/dev/null
    source "./scripts/linux.d/${DISTRIBUTION}"
fi

echo "FOUND_GTK3_DEV=${FOUND_GTK3_DEV}"
if [[ -z "${FOUND_GTK3_DEV}" ]] ; then
    echo "Error, you must install the dependencies before."
    echo "Use option -u with sudo"
    exit 1
fi

echo "Changing date in version..."
{
    # change date in version
    sed --in-place "s/+UNKNOWN/_$(date '+%F')/" version.inc
}
echo "done"


if [[ -z "${SKIP_RAM_CHECK}" ]] ; then
    check_available_memory_and_disk
fi

# ---------------------------------------------------------------------------
# -x: Native CPU optimized build for Xeon 6148 (skylake-avx512)
#
#   Uses Clang (preferred) or GCC 14 with:
#     - -march=skylake-avx512 / -mtune=skylake-avx512
#     - -O3 with full vectorization
#     - ThinLTO (Clang+LLD) — works with static TBB unlike GCC full LTO
#     - -fno-plt, -fomit-frame-pointer
#     - Static C++ runtime (no libstdc++/libgcc runtime dependency)
#     - LLD linker (required for Clang ThinLTO)
#     - strip --strip-all on the final binary
# ---------------------------------------------------------------------------
NATIVE_OPT_CFLAGS=()
NATIVE_OPT_LDFLAGS=()
NATIVE_OPT_STRIP="0"

if [[ -n "${NATIVE_OPTIMIZED}" ]] ; then
    echo ">>> Native optimized build enabled (Xeon 6148 / skylake-avx512)"

    # --- CPU architecture flags ---
    # skylake-avx512: AVX-512F/BW/CD/DQ/VL, AVX2, FMA, BMI1/2, POPCNT, AES
    ARCH_FLAGS="-march=skylake-avx512 -mtune=skylake-avx512"

    # --- Additional codegen flags ---
    EXTRA_FLAGS="-fno-plt -fomit-frame-pointer"

    # --- Compiler selection ---
    # Clang 18 is strongly preferred: its auto-vectorizer produces significantly
    # better AVX-512 code than GCC 13/14 for the Clipper/polygon workloads in
    # OrcaSlicer.  Clang also supports ThinLTO with LLD, which works correctly
    # with static TBB (unlike GCC full LTO which fails on TBB's r1:: symbols).
    CLANG_BIN=""
    CLANGPP_BIN=""
    for ver in 22 21 20 19 18 17 16; do
        if command -v clang-${ver} >/dev/null 2>&1 && command -v clang++-${ver} >/dev/null 2>&1; then
            CLANG_BIN="clang-${ver}"
            CLANGPP_BIN="clang++-${ver}"
            break
        fi
    done
    if [[ -z "${CLANG_BIN}" ]] && command -v clang >/dev/null 2>&1; then
        CLANG_BIN="clang"
        CLANGPP_BIN="clang++"
    fi

    if [[ -n "${CLANG_BIN}" && -z "${USE_CLANG}" ]] ; then
        # -x sets Clang automatically (USE_CLANG path handled below)
        USE_CLANG_NATIVE="${CLANG_BIN}"
        USE_CLANGPP_NATIVE="${CLANGPP_BIN}"
        echo ">>> Using Clang ($(${CLANG_BIN} --version | head -1))"

        # Linker: ld.gold is required because:
        # 1) TBB is now a shared library, but OpenVDB/other static archives still
        #    reference TBB r1:: symbols via template instantiations in .a files.
        #    ld.gold (unlike ld.lld) does multi-pass archive scanning and resolves
        #    these cross-archive dependencies correctly.
        # 2) Clang supports ThinLTO with ld.gold via the LLVM plugin.
        # 3) -fuse-ld=gold is faster than ld.bfd while being more compatible than lld.
        if command -v ld.gold >/dev/null 2>&1; then
            LINKER_FLAG="-fuse-ld=gold"
            LTO_FLAGS="-flto=thin"
            echo ">>> ThinLTO   : enabled (-flto=thin via Clang+gold)"
        else
            LINKER_FLAG="-fuse-ld=lld"
            LTO_FLAGS="-flto=thin"
            echo ">>> ThinLTO   : enabled (-flto=thin via Clang+lld)"
        fi

        # Static C++ runtime (Clang uses libstdc++ on Linux by default)
        STATIC_RUNTIME_LDFLAGS="-static-libgcc -static-libstdc++"
    else
        # Fallback: GCC 14 without LTO (GCC LTO incompatible with static TBB)
        LTO_FLAGS=""
        if command -v gcc-14 >/dev/null 2>&1 ; then
            echo ">>> Clang not found, using GCC 14 ($(gcc-14 --version | head -1))"
            export CC=gcc-14
            export CXX=g++-14
            export AR=gcc-ar-14
            export RANLIB=gcc-ranlib-14
            export NM=gcc-nm-14
        else
            echo ">>> Using system GCC ($(gcc --version | head -1))"
        fi
        if command -v ld.gold >/dev/null 2>&1 ; then
            LINKER_FLAG="-fuse-ld=gold"
        else
            LINKER_FLAG=""
        fi
        STATIC_RUNTIME_LDFLAGS="-static-libgcc -static-libstdc++"
        echo ">>> LTO       : skipped (GCC + static TBB incompatible)"
    fi

    # Build the CMake flag arrays.
    # CMAKE_LINKER is set explicitly to ld.gold to prevent CMake from
    # auto-detecting ld.lld-20 (which Clang 20 ships alongside and CMake
    # prefers when it finds the llvm toolchain).
    GOLD_BIN=$(command -v ld.gold)
    NATIVE_OPT_CFLAGS=(
        "-DCMAKE_LINKER=${GOLD_BIN}"
        "-DCMAKE_C_FLAGS_RELEASE=-O3 ${ARCH_FLAGS} ${LTO_FLAGS} ${EXTRA_FLAGS} -DNDEBUG"
        "-DCMAKE_CXX_FLAGS_RELEASE=-O3 ${ARCH_FLAGS} ${LTO_FLAGS} ${EXTRA_FLAGS} -DNDEBUG"
        "-DCMAKE_EXE_LINKER_FLAGS_RELEASE=${LTO_FLAGS} ${STATIC_RUNTIME_LDFLAGS} ${LINKER_FLAG}"
        "-DCMAKE_SHARED_LINKER_FLAGS_RELEASE=${LTO_FLAGS} ${LINKER_FLAG}"
        "-DCMAKE_MODULE_LINKER_FLAGS_RELEASE=${LTO_FLAGS} ${LINKER_FLAG}"
    )

    # Strip the binary after linking
    NATIVE_OPT_STRIP="1"

    echo ">>> Arch flags : ${ARCH_FLAGS}"
    echo ">>> Extra flags: ${EXTRA_FLAGS}"
    echo ">>> LTO flags  : ${LTO_FLAGS:-none}"
    echo ">>> Linker     : ${LINKER_FLAG:-ld.bfd (default)}"
fi

export CMAKE_C_CXX_COMPILER_CLANG=()
if [[ -n "${USE_CLANG_NATIVE}" ]] ; then
    # -x mode: use the specific versioned Clang found above
    CLANG_BIN_PATH=$(command -v "${USE_CLANG_NATIVE}")
    CLANGPP_BIN_PATH=$(command -v "${USE_CLANGPP_NATIVE}")
    export CMAKE_C_CXX_COMPILER_CLANG=(-DCMAKE_C_COMPILER="${CLANG_BIN_PATH}" -DCMAKE_CXX_COMPILER="${CLANGPP_BIN_PATH}")
elif [[ -n "${USE_CLANG}" ]] ; then
    export CMAKE_C_CXX_COMPILER_CLANG=(-DCMAKE_C_COMPILER=/usr/bin/clang -DCMAKE_CXX_COMPILER=/usr/bin/clang++)
elif [[ -n "${CC}" ]] ; then
    # GCC 14 (or other) set via environment — pass it to CMake explicitly
    export CMAKE_C_CXX_COMPILER_CLANG=(-DCMAKE_C_COMPILER="${CC}" -DCMAKE_CXX_COMPILER="${CXX}")
fi

# Configure use of ld.lld as the linker when requested via -L flag.
# In -x mode, linker selection is handled inside the NATIVE_OPTIMIZED block above
# (LINKER_FLAG embedded in NATIVE_OPT_CFLAGS *_RELEASE variants).
export CMAKE_LLD_LINKER_ARGS=()
if [[ -n "${USE_LLD}" && -z "${NATIVE_OPTIMIZED}" ]] ; then
    if command -v ld.lld >/dev/null 2>&1 ; then
        LLD_BIN=$(command -v ld.lld)
        export CMAKE_LLD_LINKER_ARGS=(-DCMAKE_LINKER="${LLD_BIN}" -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld -DCMAKE_SHARED_LINKER_FLAGS=-fuse-ld=lld -DCMAKE_MODULE_LINKER_FLAGS=-fuse-ld=lld)
    else
        echo "Error: ld.lld not found. Please install the 'lld' package (e.g., sudo apt install lld) or omit -L."
        exit 1
    fi
fi

if [[ -n "${BUILD_DEPS}" ]] ; then
    echo "Configuring dependencies..."
    read -r -a BUILD_ARGS <<< "${DEPS_EXTRA_BUILD_ARGS}"
    if [[ -n "${CLEAN_BUILD}" ]]
    then
        print_and_run rm -fr deps/$BUILD_DIR
    fi
    mkdir -p deps/$BUILD_DIR
    if [[ $BUILD_CONFIG != Release ]] ; then
        BUILD_ARGS+=(-DCMAKE_BUILD_TYPE="${BUILD_CONFIG}")
    fi

    # Pass native optimization flags to deps build as well so that TBB,
    # Clipper2, and other compute-heavy libs also benefit from the target ISA.
    print_and_run cmake -S deps -B deps/$BUILD_DIR "${CMAKE_C_CXX_COMPILER_CLANG[@]}" "${CMAKE_LLD_LINKER_ARGS[@]}" "${NATIVE_OPT_CFLAGS[@]}" -G Ninja "${COLORED_OUTPUT}" "${BUILD_ARGS[@]}"
    print_and_run cmake --build deps/$BUILD_DIR
fi

if [[ -n "${BUILD_ORCA}" ]] || [[ -n "${BUILD_TESTS}" ]] ; then
    echo "Configuring OrcaSlicer..."
    if [[ -n "${CLEAN_BUILD}" ]] ; then
        print_and_run rm -fr $BUILD_DIR
    fi
    read -r -a BUILD_ARGS <<< "${ORCA_EXTRA_BUILD_ARGS}"
    if [[ $BUILD_CONFIG != Release ]] ; then
        BUILD_ARGS+=(-DCMAKE_BUILD_TYPE="${BUILD_CONFIG}")
    fi
    if [[ -n "${BUILD_TESTS}" ]] ; then
        BUILD_ARGS+=(-DBUILD_TESTS=ON)
    fi
    if [[ -n "${ORCA_UPDATER_SIG_KEY}" ]] ; then
        BUILD_ARGS+=(-DORCA_UPDATER_SIG_KEY="${ORCA_UPDATER_SIG_KEY}")
    fi

    print_and_run cmake -S . -B $BUILD_DIR "${CMAKE_C_CXX_COMPILER_CLANG[@]}" "${CMAKE_LLD_LINKER_ARGS[@]}" "${NATIVE_OPT_CFLAGS[@]}" -G "Ninja Multi-Config" \
-DSLIC3R_PCH=${SLIC3R_PRECOMPILED_HEADERS} \
-DORCA_TOOLS=ON \
"${COLORED_OUTPUT}" \
"${BUILD_ARGS[@]}"
    echo "done"
    if [[ -n "${BUILD_ORCA}" ]]; then
	echo "Building OrcaSlicer ..."
	print_and_run cmake --build $BUILD_DIR --config "${BUILD_CONFIG}" --target OrcaSlicer
	echo "Building OrcaSlicer_profile_validator .."
	print_and_run cmake --build $BUILD_DIR --config "${BUILD_CONFIG}" --target OrcaSlicer_profile_validator
	./scripts/run_gettext.sh

        # Strip the binary if native optimized build was requested.
        # Removes debug symbols: reduces binary size and dynamic linker overhead.
        if [[ "${NATIVE_OPT_STRIP}" == "1" ]] ; then
            ORCA_BIN="${BUILD_DIR}/src/${BUILD_CONFIG}/orca-slicer"
            if [[ -f "${ORCA_BIN}" ]] ; then
                BEFORE=$(du -sh "${ORCA_BIN}" | cut -f1)
                strip --strip-all "${ORCA_BIN}"
                AFTER=$(du -sh "${ORCA_BIN}" | cut -f1)
                echo ">>> Stripped binary: ${BEFORE} -> ${AFTER} (${ORCA_BIN})"
            fi

            # Copy any dynamic shared libraries that the binary requires from the
            # deps install prefix into the package/bin directory so the AppImage
            # wrapper script (which sets LD_LIBRARY_PATH=$DIR/bin) can find them.
            PKG_BIN="${BUILD_DIR}/package/bin"
            if [[ -d "${PKG_BIN}" ]] ; then
                DEPS_LIB="${SCRIPT_PATH}/deps/build/OrcaSlicer_dep/usr/local/lib"
                for so in $(ldd "${ORCA_BIN}" 2>/dev/null | awk '/=> \//{print $3}' | grep "${DEPS_LIB}"); do
                    # Copy the real file and the versioned symlink
                    REAL_SO=$(readlink -f "${so}")
                    cp -f "${REAL_SO}" "${PKG_BIN}/"
                    # Also copy the .so symlink (basename)
                    [[ "${so}" != "${REAL_SO}" ]] && cp -f "${so}" "${PKG_BIN}/" 2>/dev/null || true
                    echo ">>> Bundled shared lib: $(basename ${REAL_SO}) -> ${PKG_BIN}/"
                done
            fi
        fi
    fi
    if [[ -n "${BUILD_TESTS}" ]] ; then
	echo "Building tests ..."
	print_and_run cmake --build ${BUILD_DIR} --config "${BUILD_CONFIG}" --target tests/all
    fi
    echo "done"
fi

if [[ -n "${BUILD_IMAGE}" || -n "${BUILD_ORCA}" ]] ; then
    pushd $BUILD_DIR > /dev/null
    build_linux_image="./src/build_linux_image.sh"
    if [[ -e ${build_linux_image} ]] ; then
        extra_script_args=""
        if [[ -n "${BUILD_IMAGE}" ]] ; then
            extra_script_args="-i"
        fi
        print_and_run ${build_linux_image} ${extra_script_args} -R "${BUILD_CONFIG}"

        echo "done"
    fi
    popd > /dev/null # build
fi

elapsed=$SECONDS
printf "\nBuild completed in %dh %dm %ds\n" $((elapsed/3600)) $((elapsed%3600/60)) $((elapsed%60))

popd > /dev/null # ${SCRIPT_PATH}
