# Browser multiplayer server (FFA on mp/ffa3)

```
browser (openjk_mp.wasm) --wss://host/ws--> gateway.py --UDP 127.0.0.1:29070--> openjkded (mp/ffa3, FFA)
```

* `gateway.py`: password login (signed cookie), serves the client and the pk3s, bridges WebSocket <-> UDP.
* `openjkded`: stock OpenJK dedicated server, built from the same OpenJK commit as the browser client.
  Its UDP port only listens on localhost; the only way in is through the gateway.

## Build

```sh
source /path/to/emsdk-2.0.11/emsdk_env.sh
./build-mp.sh                               # -> dist-mp/ (client)
podman build -f server/Dockerfile -t jka-mp .   # run from web/
```

## Run locally

```sh
mkdir -p data/base && cp /path/to/GameData/base/assets*.pk3 data/base/
podman run --rm -p 8080:8080 -e JKA_PASSWORD=secret -v ./data:/data:Z jka-mp
# open http://localhost:8080
```

## Deploy to fly.io

```sh
fly apps create jka-web-ffa            # or your own name (also in fly.toml)
fly volumes create jka_data --region fra --size 3
fly secrets set JKA_PASSWORD='choose-a-password'
fly deploy
# upload the game data to the volume (once)
fly ssh sftp shell   # then: mkdir /data/base ; put assets0.pk3 /data/base/assets0.pk3 ...
fly machine restart
```

The pk3 files are copyrighted game data: keep the server password-protected and only share it
with people who own the game.
