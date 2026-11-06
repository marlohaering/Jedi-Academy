# AGENTS.md

This repo has two parts:

- **Raven's GPL source release of Jedi Academy** (`code/`, `codemp/`, `tools/`, …). It is untouched
  reference code.
- **`web/`, which makes the game playable in the browser.** Everything we build lives here. Read
  `web/README.md` for the architecture and full instructions.

## Layout

| Path | What |
|---|---|
| `web/engine-mp/` | OpenJK MP (commit `260c59c`) ported to WebAssembly. Client = engine + cgame + ui + rd-vanilla, statically linked into `openjk_mp.wasm` |
| `web/engine-mp/web-rename/` | `gen_rename.py` and the generated `{cgame,ui,renderer}.h` symbol-prefix headers |
| `web/server/` | `gateway.py` (login, static files, WebSocket⇄UDP bridge), `repack.py` (slim client pk3; `profile=mobile` for phones), `start.sh`, `server.cfg`, `Dockerfile` |
| `web/shell-mp/` | MP game page (pk3 download + Cache Storage, auto-connect) |
| `web/fly.toml` | fly.io app `jka-web-ffa` (fra, shared-cpu-1x, 2 GB, volume `jka_data` on `/data`, auto-stop) |
| `web/engine/`, `web/assets/`, `web/shell/` | SP demo: StaticJK engine + generated placeholder assets (`assets/gen/*.py`) |
| `web/data/base/` | Original `assets0-3.pk3` (1.2 GB). **Git-ignored, never commit or publish** |

## Build and run

The toolchain is **Emscripten 2.0.11** exactly, because newer releases dropped Regal (OpenGL 1.x on
WebGL). Its libjpeg port URL is dead and has to be patched to
`https://www.ijg.org/files/jpegsrc.v9c.tar.gz`, and its `HASH` to that file's sha512 (sha256
`682aee46…a4a278d`).

The toolchain is installed once in the **main checkout**, `~/repositories/Jedi-Academy/web/.toolchain/`
(emsdk + a venv with cmake and ninja, listed in `.git/info/exclude`). Worktrees use it from there:

```sh
T=~/repositories/Jedi-Academy/web/.toolchain
source $T/emsdk/emsdk_env.sh && export PATH=$T/venv/bin:$PATH
```

```sh
source /path/to/emsdk/emsdk_env.sh                 # plus cmake + ninja on PATH
cd web && ./build-mp.sh                            # → web/dist-mp/
podman build -f server/Dockerfile -t jka-mp .      # dedicated server is compiled inside the image
podman run --rm -p 8080:8080 -e JKA_PASSWORD=secret -v ./data:/data:Z jka-mp
./build.sh                                         # SP demo → web/dist/
```

- `build-mp.sh` regenerates the rename headers only when they are missing. Delete
  `web-rename/{cgame,ui,renderer}.h` after adding or removing source files in cgame/ui/rd-vanilla or the
  engine.
- Check every build for `wasm-ld: warning: function signature mismatch`. In WebAssembly a mismatch
  becomes a `RuntimeError: unreachable` at runtime. Native builds tolerate it.
- Check `dist-mp/openjk_mp.js` for `missing function:` entries. The link runs with
  `ERROR_ON_UNDEFINED_SYMBOLS=0`, so unresolved symbols only fail at runtime.

## Deploy (fly.io, `jka.haering.me`)

- Deploy: `cd web && fly deploy --ha=false`, after `./build-mp.sh`. The image copies `dist-mp/`.
- Password: `fly secrets set JKA_PASSWORD=…`. Never write the password into the repo.
- DNS: `jka.haering.me` has A and AAAA records in Cloudflare (`cf dns records …`, DNS only, not
  proxied). The TLS certificate comes from fly.
- Uploading pk3s to the volume:
  1. Turn auto-stop off first: `fly machine update <id> --autostop=off`. SSH/SFTP traffic does not keep
     the machine awake.
  2. `fly ssh sftp put` does not overwrite: `rm` the remote file before each upload.
  3. Turn auto-stop back on: `--autostop=stop`.
  4. Restart the machine so `start.sh` rebuilds `/data/web/jka-mp.pk3`.

## Testing

- Use headless Chrome through Playwright with `channel: 'chrome'` and the args
  `--use-angle=swiftshader --enable-unsafe-swiftshader`.
- Log in at `/login`, open `/?timer`, click `#play`. `?timer` drives the main loop from a timer instead
  of `requestAnimationFrame`, which headless Chrome may not fire; `?log` shows the engine log, and F9
  toggles it.
- Phone mode: a context with `isMobile: true, hasTouch: true` and a landscape viewport (e.g. 915×412)
  is detected automatically; `?mobile` forces it in any context. `?timer` bypasses the 30 fps cap.
- Touch tests: use a context with `hasTouch: true` but *without* `isMobile`, plus `?mobile`, and send
  touches with CDP `Input.dispatchTouchEvent`. With `isMobile` the pointer events report wrong
  coordinates (screen center, or rotated after `setViewportSize`).
- A fake gamepad (`navigator.getGamepads` override) needs `id`, `index` and `mapping`, otherwise
  Emscripten's SDL joystick code throws and stops the main loop.
- Headless mouse clicks do not move the in-game UI cursor. Use the console instead: `~`, `team free`,
  `say …`.
- `fly logs` shows `ClientConnect`, `ChangeTeam` and `say:` lines from the dedicated server.

## Gotchas

- `requestAnimationFrame` stops in hidden tabs, and also in windows covered by another app while
  `document.hidden` stays false (Linux/Wayland). When rAF has been silent for 250 ms, the shell drives
  `Com_Frame` from a Worker timer at 20 fps. Without it, queued snapshots flood cgame on return
  (`CG_ReadNextSnapshot: way out of range`) and the server drops the client after `sv_timeout`.
- All players reach `openjkded` from `127.0.0.1` through the gateway. Keep `g_antiFakePlayer 0` and
  `sv_pure 0` (clients use the repacked pk3).
- The server runs the JA++ mod (game module built in the Dockerfile, Lua plugins in `server/japp/`,
  `FS_GAME=japlus` in `fly.toml`). Behind the gateway every player is `127.0.0.1`, so
  `japp_maxConnPerIP` is raised in `server.cfg`. Passwords live on the volume only:
  `/data/base/secrets.cfg` (rcon) and `/data/home/japlus/admins.json` (JA++ admin accounts).
- JA++ grappling hook (`japp_allowHook`, `+button12`) and `/jetpack` (`japp_allowJetpack`) work with
  the stock cgame, but no rope is drawn and the pull is not predicted (slight jitter); only the JA++ cgame
  fixes that. Hook pull speed and jetpack fuel are hardcoded. The shell binds F (hook) and J (jetpack)
  through `web_bind_default` when those keys are unbound; the client config is not persisted, so this
  runs every session.
- Changing the map: edit `server.cfg`. Every map the server can switch to must be in `CLIENT_MAPS` in
  `start.sh` (currently ffa1–5 + duel1–10; default map mp/duel1). `server/japp/scripts/duel.arena` marks the duel maps as FFA maps too, so JA++ `/ammap ffa mp/duelN` accepts them, otherwise browser players lack the bsp and textures.
- `repack.py` must write directory entries into the pk3 (`models/players/`, …): the engine lists pk3
  subdirectories only from those, and the UI's character lists stay empty without them.
- Rendering: Regal never uploads client-side vertex arrays for glDrawElements/glDrawArrays (its VAO
  shadow buffers stay empty, so batched draws come out black). `rd-vanilla/tr_webgl_arrays.cpp`
  intercepts the `qgl*Pointer`/`qglDraw*` calls (macros at the end of `qgl.h`), streams the arrays into
  buffer objects and converts indices to 16-bit and GL_QUADS to triangles. The client links with
  `-sFULL_ES2=1`. With `r_primitives 3` the old per-vertex path comes back, for comparisons.
  Engine time per frame on the laptop iGPU: 11 ms → 6 ms.
- Verify rendering changes by pixel-diffing old against new at fixed spots: a local server with `devmap`
  (cheats) and `setviewpos x y z yaw` from the client console.
- Measured from Hamburg: ~23 ms WebSocket game-path RTT (edge `ams` → machine `fra`), ~230 Mbit/s pk3
  download. `sv_fps 40` keeps the added snapshot latency low.
- Ask the user before installing SDKs, packages or system tools.
