# Browser multiplayer server (FFA on mp/duel1)

```
browser (openjk_mp.wasm) --wss://host/ws--> gateway.py --UDP 127.0.0.1:29070--> openjkded (mp/duel1, FFA)
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

## Server mod: JA++

The image builds the server-side game module of [JA++](https://github.com/Razish/japp) (GPL, pinned in
the Dockerfile) and installs it with its Lua plugins (`server/japp/`) to `/opt/openjk/japlus`.
`FS_GAME=japlus` (set in `fly.toml`; locally `-e FS_GAME=japlus`) switches it on when `/data/japlus`
exists on the volume. The browser client keeps its built-in cgame/ui, which JA++ supports: all server
features work (admin commands, `/amhug`-style emotes, `/aminfo`), only JA++'s client-side extras are
missing.

* Welcome message: `welcome_motd` in `server.cfg`, shown after joining and again on `/ammotd`
  (`server/japp/lua/sv/welcome/plugin.lua`). `g_motd` is the line on the stock loading screen.
* Admins: accounts in `admins.json` under `fs_homepath` (`/data/home/japlus/admins.json` on the volume,
  never in the repo), each with user, password, privilege bitmask and rank. Log in with
  `/amlogin <user> <password>`; rcon `adminadd`/`admindel`/`adminlist` manage them (`adminadd` echoes
  the password into the log). `rconpassword` is in `/data/base/secrets.cfg`.
* `japp_maxConnPerIP` is raised in `server.cfg`: every player arrives from 127.0.0.1 via the gateway.
* Asset pk3s in `/data/japlus` (and extra pk3s in `/data/base`) are merged into the client pk3.

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
