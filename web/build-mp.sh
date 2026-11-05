#!/usr/bin/env bash
# Builds the browser multiplayer client (OpenJK MP engine + cgame + ui + rd-vanilla, statically linked).
#
# Requirements: emsdk 2.0.11 activated (source emsdk_env.sh), cmake, ninja, python3.
# Output: web/dist-mp/openjk_mp.{js,wasm} + index.html
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/engine-mp"
BUILD="$HERE/build-mp"
DIST="$HERE/dist-mp"
RENAME="$SRC/web-rename"

command -v emcc >/dev/null || { echo "emcc not found - activate emsdk 2.0.11 first" >&2; exit 1; }
NM="$(dirname "$(command -v emcc)")/../bin/llvm-nm"
[ -x "$NM" ] || NM="$(cd "$(dirname "$(command -v emcc)")/.." && pwd)/bin/llvm-nm"

configure() {
  emcmake cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DBuildMPEngine=ON -DBuildMPRdVanilla=ON -DBuildMPCGame=ON -DBuildMPUI=ON \
    -DBuildMPDed=OFF -DBuildMPGame=OFF -DBuildMPRend2=OFF \
    -DBuildSPEngine=OFF -DBuildSPGame=OFF -DBuildSPRdVanilla=OFF >/dev/null
}

# Pass 1 (only when the rename headers are missing): compile everything once,
# collect the clashing symbols, write web-rename/{cgame,ui,renderer}.h
if [ ! -f "$RENAME/cgame.h" ] || [ ! -f "$RENAME/ui.h" ] || [ ! -f "$RENAME/renderer.h" ]; then
  rm -f "$RENAME"/{cgame,ui,renderer}.h
  configure
  cmake --build "$BUILD" -j"$(nproc)" -- -k 0 || true   # final link fails on duplicate symbols - expected
  ENGINE_OBJS=$(find "$BUILD/codemp/CMakeFiles" -path '*openjk*' -name '*.o')
  args=()
  for o in $ENGINE_OBJS; do args+=("engine=$o"); done
  for lib in "$BUILD"/codemp/*botlib*.a "$BUILD"/lib/minizip/*.a; do [ -f "$lib" ] && args+=("engine=$lib"); done
  python3 "$RENAME/gen_rename.py" "$NM" "$RENAME" "${args[@]}" \
    "cgame=$(find "$BUILD" -name 'cgame*.a')" \
    "ui=$(find "$BUILD" -name 'ui*.a')" \
    "renderer=$(find "$BUILD" -name 'rd-vanilla*.a')"
fi

configure
cmake --build "$BUILD" -j"$(nproc)"

mkdir -p "$DIST"
cp "$BUILD"/codemp/openjk_mp.{js,wasm} "$DIST/" 2>/dev/null || cp "$BUILD"/openjk_mp.{js,wasm} "$DIST/"
cp "$HERE"/shell-mp/*.{html,js,png,webmanifest} "$DIST/"
echo "Done: $DIST"
