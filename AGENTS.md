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
| `web/server/` | `gateway.py` (login, static files, WebSocket⇄UDP bridge), `repack.py` (slim client pk3), `start.sh`, `server.cfg`, `Dockerfile` |
| `web/shell-mp/` | MP game page (pk3 download + Cache Storage, auto-connect) |
| `web/fly.toml` | fly.io app `jka-web-ffa` (fra, shared-cpu-1x, 2 GB, volume `jka_data` on `/data`, auto-stop) |
| `web/engine/`, `web/assets/`, `web/shell/` | SP demo: StaticJK engine + generated placeholder assets (`assets/gen/*.py`) |
| `web/data/base/` | Original `assets0-3.pk3` (1.2 GB). **Git-ignored, never commit or publish** |

## Build and run

The toolchain is **Emscripten 2.0.11** exactly, because newer releases dropped Regal (OpenGL 1.x on
WebGL). Its libjpeg port URL is dead and has to be patched to
`https://www.ijg.org/files/jpegsrc.v9c.tar.gz`.

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
- Headless mouse clicks do not move the in-game UI cursor. Use the console instead: `~`, `team free`,
  `say …`.
- `fly logs` shows `ClientConnect`, `ChangeTeam` and `say:` lines from the dedicated server.

## Gotchas

- Hidden tabs pause `requestAnimationFrame`. The shell then drives `Com_Frame` from a Worker timer at
  20 fps, otherwise queued snapshots flood cgame on return (`CG_ReadNextSnapshot: way out of range`).
- All players reach `openjkded` from `127.0.0.1` through the gateway. Keep `g_antiFakePlayer 0` and
  `sv_pure 0` (clients use the repacked pk3).
- Changing the map: edit `server.cfg`, and also the `map=` and `music=` arguments of `repack.py` in
  `start.sh`.
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
