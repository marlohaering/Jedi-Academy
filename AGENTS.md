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
- Log in at `/login`, open `/?timer`, click `#play`. `?timer` keeps the main loop running in headless
  or hidden tabs; `?log` shows the engine log, and F9 toggles it.
- Headless mouse clicks do not move the in-game UI cursor. Use the console instead: `~`, `team free`,
  `say …`.
- `fly logs` shows `ClientConnect`, `ChangeTeam` and `say:` lines from the dedicated server.

## Gotchas

- All players reach `openjkded` from `127.0.0.1` through the gateway. Keep `g_antiFakePlayer 0` and
  `sv_pure 0` (clients use the repacked pk3).
- Changing the map: edit `server.cfg`, and also the `map=` and `music=` arguments of `repack.py` in
  `start.sh`.
- Performance: the client spends ~11 ms/frame (laptop iGPU, 60 fps), mostly in Regal's per-vertex
  emulation (`R_ArrayElementDiscrete`). `r_primitives 2` (glDrawElements) would take ~2.6 ms, but it
  renders a black screen under Regal. Fixing it is the main client-side optimisation left.
- Measured from Hamburg: ~23 ms WebSocket game-path RTT (edge `ams` → machine `fra`), ~230 Mbit/s pk3
  download. `sv_fps 40` keeps the added snapshot latency low.
- Ask the user before installing SDKs, packages or system tools.
