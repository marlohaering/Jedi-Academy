#!/bin/sh
# Starts the OpenJK dedicated server (UDP on localhost only) and the web gateway.
set -e
mkdir -p "$DATA_DIR" /tmp/jkhome
if ! ls "$DATA_DIR"/*.pk3 >/dev/null 2>&1; then
  echo "No pk3 files in $DATA_DIR - upload the game data first (see web/server/README.md)" >&2
fi
# slim client pk3 for the browsers (rebuilt when the game data changes)
CLIENT_DATA_DIR="${CLIENT_DATA_DIR:-/data/web}"
mkdir -p "$CLIENT_DATA_DIR"
if ls "$DATA_DIR"/*.pk3 >/dev/null 2>&1; then
  if [ ! -f "$CLIENT_DATA_DIR/jka-mp.pk3" ] || [ -n "$(find "$DATA_DIR" -name '*.pk3' -newer "$CLIENT_DATA_DIR/jka-mp.pk3")" ]; then
    echo "building client pk3..."
    # a broken/partial upload must not take the whole machine down
    python3 /opt/gateway/repack.py "$DATA_DIR" "$CLIENT_DATA_DIR/jka-mp.pk3" || echo "client pk3 build failed (incomplete game data?)" >&2
  fi
fi
export CLIENT_DATA_DIR

# fs_basepath points at the volume (base/*.pk3); the game module comes from fs_cdpath
/opt/openjk/openjkded.x86_64 +set dedicated 1 +set net_ip 127.0.0.1 +set net_port "$GAME_PORT" \
  +set fs_cdpath /opt/openjk +set fs_basepath "$(dirname "$DATA_DIR")" +set fs_homepath /tmp/jkhome \
  +exec server.cfg &
GAME_PID=$!
python3 /opt/gateway/gateway.py &
WEB_PID=$!
# exit (and let fly restart the machine) when either process dies
while kill -0 $GAME_PID 2>/dev/null && kill -0 $WEB_PID 2>/dev/null; do sleep 5; done
echo "a process exited - stopping" >&2
kill $GAME_PID $WEB_PID 2>/dev/null || true
exit 1
