# Jedi Academy in the browser

This folder makes Raven's Jedi Academy source playable in a web browser. The engine is OpenJK compiled to
WebAssembly with Emscripten. There are two independent parts:

| Part | What it is | Game data |
|---|---|---|
| **Multiplayer server** (`engine-mp/`, `server/`, `shell-mp/`) | Password-protected online FFA server on `mp/ffa3`. Everyone who opens the page joins the same game. | Original `assets0-3.pk3` (not in the repo) |
| **Single-player demo** (`engine/`, `assets/`, `shell/`) | SP engine with a generated placeholder level, models, textures and sounds | Generated, no original data needed |

Live server: **https://jka.haering.me** (also https://jka-web-ffa.fly.dev). The password is stored as the
fly.io secret `JKA_PASSWORD`.

---

## Multiplayer server

### How it works

```
Browser                                  fly.io machine (jka-web-ffa, fra)
┌──────────────────────┐   HTTPS / WSS   ┌──────────────────────────────────────────────┐
│ index.html (shell-mp)│ ──────────────▶ │ gateway.py (aiohttp, :8080)                  │
│ openjk_mp.wasm       │                 │  /login     password → signed cookie (30 d)  │
│  (OpenJK MP client:  │                 │  /, *.js/.wasm  client files                 │
│   engine + cgame +   │                 │  /base/*    slim client pk3 (cached by the   │
│   ui + renderer)     │                 │             browser after the first visit)   │
│                      │  UDP datagrams  │  /ws        WebSocket ⇄ UDP bridge           │
│ Emscripten sockets ──┼── as WebSocket ─┼──▶ one UDP socket per browser ──┐           │
└──────────────────────┘    messages     │                                 ▼           │
                                         │ openjkded (OpenJK dedicated, 127.0.0.1:29070)│
                                         │  mp/ffa3, g_gametype 0 (FFA), 16 slots       │
                                         │ /data volume: base/assets0-3.pk3, web/*.pk3  │
                                         └──────────────────────────────────────────────┘
```

* **Browsers cannot send UDP.** Emscripten's socket layer sends every UDP datagram as one binary
  WebSocket message. The gateway forwards each WebSocket to its own UDP socket on the dedicated server,
  so to the server every browser looks like a normal client from `127.0.0.1:<port>`.
* **The game server is not reachable from outside.** It only listens on localhost, so the gateway with
  its password check is the only way in. Without a valid cookie the page, the game data and the
  WebSocket all return 401.
* **Client and server use the same OpenJK version** (commit `260c59c`), so the game logic matches.
* **Player download:** `server/repack.py` builds one slim `jka-mp.pk3` (≈780 MB instead of 1.2 GB) for the
  browsers at container start. It leaves out cinematics, non-English dialogue, every map except ffa3 and
  single-player music. The browser keeps it in Cache Storage, so it is only downloaded once. The server
  itself uses the original pk3s (`sv_pure 0`).

### Browser port of the MP client (`engine-mp/`)

A copy of [OpenJK](https://github.com/JACoders/OpenJK) at `260c59c` (`codemp/`, `shared/`, `lib/`), with
these changes:

| Change | Files |
|---|---|
| Emscripten build: SDL2, zlib, libpng, libjpeg and Regal (OpenGL 1.x on WebGL) come from Emscripten ports; cgame, ui and rd-vanilla are static libraries linked into one `openjk_mp.wasm` | `CMakeLists.txt`, `codemp/**/CMakeLists.txt` |
| Static modules instead of `dlopen`: `Sys_LoadGameDll` and `Sys_LoadDll` return the linked-in `cgame_GetModuleAPI`, `ui_GetModuleAPI` and `renderer_GetRefAPI` (`OJK_STATIC_MODULES`) | `shared/sys/sys_main.cpp`, `codemp/client/cl_main.cpp` |
| Symbol renaming: every module carries its own copy of shared code (q_shared, bg_*, ui_shared …). `web-rename/gen_rename.py` finds the symbols that clash and writes `#define` headers that are force-included per module | `web-rename/` |
| Browser main loop (`emscripten_set_main_loop`) | `shared/sys/sys_main.cpp` |
| GL context via Regal, no `glext.h`, index drawing through `R_ArrayElementDiscrete` (same as StaticJK) | `shared/sdl/sdl_window.cpp`, `codemp/rd-vanilla/*` |
| Sockets: no `FIONBIO` ioctl (Emscripten sockets never block) | `codemp/qcommon/net_ip.cpp` |
| No console stdin, no `getpwuid`, no `sched_setaffinity` | `shared/sys/*` |
| Fixed signature mismatches that only break in WebAssembly (`openjk_minizip_free`, `C_MP3Stream_Decode`), renamed mp3 `window()` | `lib/minizip/unzip.c`, `codemp/mp3code/*` |

### Build

Requirements:
* Emscripten **2.0.11**. Newer releases removed Regal.
  * Its `libjpeg` port still downloads from the dead bintray URL. Change `tools/ports/libjpeg.py` to
    `https://www.ijg.org/files/jpegsrc.v9c.tar.gz`.
* cmake, ninja, python3
* podman or docker

```sh
source /path/to/emsdk/emsdk_env.sh
cd web
./build-mp.sh                                    # → dist-mp/ (openjk_mp.js/.wasm + index.html)
podman build -f server/Dockerfile -t jka-mp .    # dedicated server + gateway + client
```

The image build compiles `openjkded` from OpenJK `260c59c` inside the container, so no host compiler is
needed for the server.

### Run locally

```sh
mkdir -p data/base && cp /path/to/GameData/base/assets*.pk3 data/base/   # data/ is git-ignored
podman run --rm -p 8080:8080 -e JKA_PASSWORD=secret -v ./data:/data:Z jka-mp
# http://localhost:8080 → password → name → "Join game" → in the game menu "Join Game"
```

### Deployment (fly.io)

`fly.toml` settings:

| Setting | Value |
|---|---|
| App | `jka-web-ffa` |
| Region | `fra` |
| Machine | `shared-cpu-1x`, 1 GB, enough for ~4 players |
| Volume | 3 GB `jka_data` mounted at `/data` |
| Idle behaviour | Sleeps when nobody is connected (`auto_stop_machines = "stop"`), wakes up on the next request |

```sh
fly deploy --ha=false                         # from web/, after ./build-mp.sh
fly secrets set JKA_PASSWORD='…'              # change the password
# game data, once - keep the machine awake meanwhile (SSH traffic does not count as activity):
fly machine update <id> --autostop=off
fly ssh sftp put data/base/assets0.pk3 /data/base/assets0.pk3   # … assets1-3 likewise
fly machine update <id> --autostop=stop && fly machine restart <id>   # repacks the client pk3
fly logs                                      # server log: connects, team changes, chat
```

* **DNS:** `jka.haering.me` points at the app's fly IPs via A and AAAA records in Cloudflare (DNS only,
  not proxied). The TLS certificate comes from fly (`fly certs show jka.haering.me`).
* **Server settings** (map, time and frag limits, slots) are in `server/server.cfg`.
* **Changing the map:** set it in `server.cfg`, then adjust the `map=` and `music=` arguments of `repack.py`
  in `server/start.sh`.

### Notes and limits

* The pk3 files are copyrighted game data. Keep the server password-protected, and only give the
  password to people who own the game.
* `g_antiFakePlayer 0`: all players arrive from 127.0.0.1, so the per-IP limit would block the fourth
  player.
* First visit: the browser downloads ≈780 MB once. Later visits load from the browser cache.
* Performance depends on the GPU. Regal translates old OpenGL immediate-mode drawing to WebGL in software.

---

## Single-player demo (placeholder assets)

`build.sh` builds the OpenJK SP engine from `engine/`, a copy of
[StaticJK](https://github.com/Rinnegatamante/StaticJK) by Luka Klacar. StaticJK is OpenJK SP ported to
Emscripten.

`assets/build_pk3.py` then generates `zz_placeholder.pk3`, containing:
* menus and fonts
* procedural textures
* simple Ghoul2 characters with animations
* weapons and effects
* synthesised sounds
* a small test level `academy`, with stormtroopers and reborn

```sh
./build.sh && python3 -m http.server -d dist 8000   # http://localhost:8000/?map=academy
```
