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

## Server mods (JA+)

The server image is 32-bit (i386), so it can load closed-source server mods that only exist as
`jampgamei386.so`, through OpenJK's legacy game API. Tested with JA+ v2.4 Build 7. The browser
client keeps its built-in cgame/ui, which JA+ allows on `sv_pure 0` servers: everything
server-side works (`/amhelp`, emotes, admin commands), only the client plugin's extra menus and
HUD are missing.

The mod lives on the volume, next to `base/`, not in the image:

```
data/base/japlus_gla_anims.pk3      # from the JA+ base/ folder: the extra emote animations
data/japlus/jampgamei386.so         # the Linux game module
data/japlus/japlus_sabers.pk3, efx_MOD.pk3, admin.cfg, chat.cfg, saber.cfg, ...
```

Don't copy JA+'s `server.cfg` (it would override ours) or the `jampgamex86.pk3`/`clientPlugin*`
pk3s (native code the browser can't load). Then run with `-e FS_GAME=japlus` (on fly:
`[env] FS_GAME = "japlus"` in `fly.toml`). `start.sh` adds `+set fs_game japlus` and rebuilds the
client pk3 with the mod's asset pk3s. Our `server.cfg` sets the JA+ cvars that matter behind the
gateway (`jp_maxConnFromIP`, `jp_autoQUIT`). `rconpassword` and the JA+ admin passwords
(`jp_councilPass`, `jp_knightPass`, `jp_instructorPass`) go into `data/base/secrets.cfg` on the
volume, which `server.cfg` execs; never put them in the repo. Log in in game with
`/amlogin <password>`.

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
