#!/bin/sh
# Starts the OpenJK dedicated server (UDP on localhost only) and the web gateway.
set -e
mkdir -p "$DATA_DIR" "$(dirname "$DATA_DIR")/home"
if ! ls "$DATA_DIR"/*.pk3 >/dev/null 2>&1; then
  echo "No pk3 files in $DATA_DIR - upload the game data first (see web/server/README.md)" >&2
fi
# optional server mod: a directory next to base/ on the volume, e.g. FS_GAME=japlus with
# the JA++ game module from the image (/opt/openjk/japlus); the mod dir's asset pk3s also go into the client pk3
MOD_DIR=""
FS_GAME_ARGS=""
if [ -n "$FS_GAME" ]; then
  if [ -d "$(dirname "$DATA_DIR")/$FS_GAME" ]; then
    MOD_DIR="$(dirname "$DATA_DIR")/$FS_GAME"
    FS_GAME_ARGS="+set fs_game $FS_GAME"
  else
    echo "FS_GAME=$FS_GAME but $(dirname "$DATA_DIR")/$FS_GAME is missing - running base" >&2
  fi
fi

# The browser asks for core + current-map packages; existing legacy pk3s remain readable
# during migration but are no longer rebuilt alongside the new package library.
CLIENT_DATA_DIR="${CLIENT_DATA_DIR:-/data/web}"
mkdir -p "$CLIENT_DATA_DIR"
export CLIENT_DATA_DIR

# Content-addressed per-map packages are published atomically; game startup stays responsive.
( python3 /opt/gateway/bundles.py "$DATA_DIR" "$CLIENT_DATA_DIR/map-paks" "$MOD_DIR" || echo "map package build failed; keeping previous catalog" >&2 ) &

# fs_basepath points at the volume (base/*.pk3); the game module comes from fs_cdpath
/opt/openjk/openjkded.x86_64 $FS_GAME_ARGS +set dedicated 1 +set net_ip 127.0.0.1 +set net_port "$GAME_PORT" \
  +set fs_cdpath /opt/openjk +set fs_basepath "$(dirname "$DATA_DIR")" +set fs_homepath "$(dirname "$DATA_DIR")/home" \
  +exec server.cfg &
GAME_PID=$!
export GAME_PID
python3 /opt/gateway/gateway.py &
WEB_PID=$!
# exit (and let fly restart the machine) when either process dies
while kill -0 $GAME_PID 2>/dev/null && kill -0 $WEB_PID 2>/dev/null; do sleep 5; done
echo "a process exited - stopping" >&2
kill $GAME_PID $WEB_PID 2>/dev/null || true
exit 1
