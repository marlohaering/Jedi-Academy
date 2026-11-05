#!/usr/bin/env bash
# Builds the browser version of Jedi Academy (OpenJK SP engine + placeholder assets).
#
# Requirements:
#   - emsdk 2.0.11 activated (`source /path/to/emsdk/emsdk_env.sh`)
#     (newer Emscripten releases removed the Regal GL emulation this port relies on)
#   - cmake + ninja (or make), python3 with Pillow
#
# Output: web/dist/  -> serve with `python3 -m http.server -d web/dist`
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"
DIST="$HERE/dist"

if ! command -v emcc >/dev/null; then
  echo "emcc not found - activate emsdk 2.0.11 first (source emsdk_env.sh)" >&2
  exit 1
fi

GEN="Unix Makefiles"
command -v ninja >/dev/null && GEN=Ninja

mkdir -p "$BUILD" "$DIST/base"
emcmake cmake -S "$HERE/engine" -B "$BUILD" -G "$GEN" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build "$BUILD" -j"$(nproc)"

cp "$BUILD"/jedi_academy.{js,wasm} "$DIST/"
cp "$HERE/shell/index.html" "$DIST/index.html"

python3 "$HERE/assets/build_pk3.py" "$DIST/base"
echo "Done. Run: python3 -m http.server -d '$DIST' 8000  and open http://localhost:8000/"
