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
* Companion bot: while at least one human is connected, a bot named `BOT` (Kyle Katarn's bot profile,
  skill 3) plays along and is kicked when the last human leaves (`server/japp/lua/sv/companion/plugin.lua`,
  needs `bot_enable 1`). Bot name, profile and skill are constants at the top of the plugin.
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

## Fill the server with unique skill-5 bots

From the client console (with RCON configured):

```text
rcon exec fill-bots.cfg
```

The config removes existing bots (humans stay connected), disables `bot_minplayers`,
pauses the Companion Lua plugin via `companion_paused 1`, then tries each of the 43 stock
`botlist` names exactly once with `addbot "name" 5 free 0`. All added bots are skill 5. The fixed, mixed order interleaves shuffled light-side and other
profiles, so Jedi are represented before the slot limit is reached; executing again uses the same order.
Names come from the stock `botfiles/bots.txt`; no original asset files are distributed.
Repeated execution replaces the roster rather than adding duplicate bots.
Once all slots are occupied, subsequent commands report no free slots; that is expected.
This is an FFA config and does not continuously refill slots or execute itself on map changes.

The current default `sv_maxclients` is 32: one human leaves room for 31 bots. This script
does not change the slot limit or restart the map. For a larger test, configure the desired
`sv_maxclients` separately and apply it with a map change before executing the config.
To remove the bots and resume the usual skill-3 companion:

```text
rcon exec clear-bots.cfg
```

Both configs are included in `/opt/openjk/base/` by the image build. They and the updated
Companion plugin must be installed on the server before use. Merely saving them on the client
is insufficient: `rcon exec` reads the server filesystem. An existing copy on the data volume
may override the image copy; update/remove that copy if necessary.

The live server keeps a mirrored copy of `fill-bots.cfg` on the volume at `/data/base/fill-bots.cfg`
to allow updates without a restart. Keep this copy in sync when changing the packaged config.

### E-Web animation dependency

Ghoul2 `.glm` headers reference a `.gla` animation without its extension. The repacker
keeps this dependency explicitly, including `models/map_objects/hoth/model.gla` for
the E-Web. A missing animation makes that model fail to load even when the mesh exists.
The live volume also contains small `jka-animation-fix.pk3` and
`jka-animation-fix-mobile.pk3` patches for existing cached client packages, allowing
the repair without a restart or full download. The normal authenticated manifest
includes these automatically on page reload. They can be removed once both full
client packages have been rebuilt with the corrected repacker. Game data stays on
the private server volume; do not commit these packages.


## On-demand map packages

`bundles.py <base> <output> [mod]` builds desktop/mobile packages for every installed BSP.
Live output is `/data/web/map-paks/`, with an atomically published `bundles.json` catalog.
Files needed by the same set of maps share one package, so they are not duplicated across maps.
Core includes weapons, player/NPC/vehicle assets, effects and menus; map groups include BSPs,
map textures/props, music and mobile ambience. Existing mobile image/audio reductions remain.
Animation dependencies are retained. This supplies map assets; it does not guarantee that SP
levels have appropriate multiplayer spawn points or game logic.

Authenticated `GET /base/manifest.json?map=current` or `?map=mp/ctf1` selects only that map's
requirements in `paks` (desktop) and `mobile`. A missing catalog falls back to compatible legacy
packages; unavailable maps produce a retryable response instead of launching a missing BSP.
Without the map query, the legacy manifest never enumerates the new bundle directory.

The shell verifies response lengths before caching and keeps versioned packages in Cache Storage.
Only core and the selected map stay mounted in MEMFS; older visited maps remain in the browser
cache. `CL_InitDownloads` yields to JavaScript before loading cgame/collision data. The connection
keeps running during downloads, then `FS_Restart` and `donedl` refresh the game state. Ticket checks,
cancellation and native indexing acknowledgements prevent stale downloads from resuming the wrong
map or bypassing filesystem indexing after disconnect. Failures expose a retry button, without
reloading the page or deliberately ending the connection. The game's own map-change/admin policy
still applies to sessions.

Startup builds only the new package catalog; legacy packages are a read-only migration fallback. A script/input fingerprint avoids rebuilding
unchanged packages; builds use a lock, deterministic ZIP metadata, content hashes and atomic catalog
publication. Unreferenced package versions older than 24 hours are collected at the next build;
active catalog packages are retained. Keep disk headroom for the largest temporary package during
rebuilds. Interrupted builds keep the previous catalog usable.

Verification: `python3 -m unittest discover -s web/server -p 'test_*.py'` and
`node --test web/shell-mp/test-map-assets.cjs`. Real headless Chrome tests cover initial entry,
`duel1 → ctf1 → duel1`, cached return without pk3 requests, HTTP failure/retry, a 35-second download
with server timeout 30 seconds, and a second map change during download. Browser checks must use
Playwright polling by timer (`polling: 100`), not rAF, because the shell owns the engine's rAF loop.
