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

# slim client pk3 for the browsers (rebuilt when the game data, the mod, the map list or repack.py changes)
CLIENT_DATA_DIR="${CLIENT_DATA_DIR:-/data/web}"
# maps the clients can load: the server.cfg map plus the stock FFA and duel maps for admins (map changes
# to a map missing here leave the browser players without the bsp)
CLIENT_MAPS="mp/ffa1,mp/ffa2,mp/ffa3,mp/ffa4,mp/ffa5,mp/duel1,mp/duel2,mp/duel3,mp/duel4,mp/duel5,mp/duel6,mp/duel7,mp/duel8,mp/duel9,mp/duel10"
# .mod remembers which mod and maps a pk3 was built for, so changing either rebuilds it
PK3_KEY="$FS_GAME_ARGS|$CLIENT_MAPS"
mkdir -p "$CLIENT_DATA_DIR"
PK3="$CLIENT_DATA_DIR/jka-mp.pk3"
if ls "$DATA_DIR"/*.pk3 >/dev/null 2>&1; then
  if [ ! -f "$PK3" ] || [ "$(cat "$PK3.mod" 2>/dev/null)" != "$PK3_KEY" ] || \
     [ -n "$(find "$DATA_DIR" $MOD_DIR -name '*.pk3' -newer "$PK3")" ] || [ /opt/gateway/repack.py -nt "$PK3" ]; then
    echo "building client pk3..."
    # a broken/partial upload must not take the whole machine down
    if python3 /opt/gateway/repack.py "$DATA_DIR" "$PK3" "map=$CLIENT_MAPS" ${MOD_DIR:+"mod=$MOD_DIR"}; then
      printf '%s' "$PK3_KEY" > "$PK3.mod"
    else
      echo "client pk3 build failed (incomplete game data?)" >&2
    fi
  fi
  # phone variant (web/MOBILE.md), built in the background; the manifest lists it once it exists.
  # Same mod, map and marker logic as above.
  MPK3="$CLIENT_DATA_DIR/jka-mp-mobile.pk3"
  if [ ! -f "$MPK3" ] || [ "$(cat "$MPK3.mod" 2>/dev/null)" != "$PK3_KEY" ] || \
     [ -n "$(find "$DATA_DIR" $MOD_DIR -name '*.pk3' -newer "$MPK3")" ] || [ /opt/gateway/repack.py -nt "$MPK3" ]; then
    echo "building mobile client pk3 in the background..."
    ( if nice python3 /opt/gateway/repack.py "$DATA_DIR" "$MPK3" "map=$CLIENT_MAPS" ${MOD_DIR:+"mod=$MOD_DIR"} profile=mobile; then
        printf '%s' "$PK3_KEY" > "$MPK3.mod"
      else
        echo "mobile client pk3 build failed" >&2
      fi ) &
  fi
fi
export CLIENT_DATA_DIR

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
