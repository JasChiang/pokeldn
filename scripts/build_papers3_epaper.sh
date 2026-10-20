#!/usr/bin/env bash
# Build only: no serial access, flash writes, resets, or GitHub operations.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export POKELDN_PAPERS3=1
export POKELDN_PAPERS3_EPAPER=1
cd "$ROOT_DIR/firmware/esp32"
BUILD_DIR="${POKELDN_PAPERS3_BUILD_DIR:-build-papers3-epaper}"
mkdir -p "$BUILD_DIR"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
if [[ ! -f "$BUILD_DIR/CMakeCache.txt" ]]; then
    idf.py -B "$BUILD_DIR" -D "SDKCONFIG=$BUILD_DIR/sdkconfig" \
        -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.esp32s3;sdkconfig.defaults.papers3;sdkconfig.defaults.papers3-epaper' \
        set-target esp32s3
fi
idf.py -B "$BUILD_DIR" build
idf.py -B "$BUILD_DIR" merge-bin -o "$BUILD_DIR/pokeldn-radio-s3-papers3-1.6.2-v2.bin"
