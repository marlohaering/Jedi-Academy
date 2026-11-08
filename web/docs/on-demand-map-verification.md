# On-demand map verification, 2026-11-08

Implementation commit dd0259a deployed to jka-web-ffa. All 57 installed maps have authenticated
package manifests; desktop/mobile catalogs and file SHA-256 checks were verified before publication.
Production JA++ overrides (japlus_gla_anims.pk3, efx_MOD.pk3, japlus_sabers.pk3) are included.
The catalog input fingerprint matches the original archives and scripts on the live machine.
Original server assets were retained; only superseded client aggregates were retired.

## Verification

- Five Python tests: map/shared ownership, dependency coverage, deterministic package rebuilds,
  animation retention and reuse of parsed model metadata.
- Five Node tests: only missing packages mounted, same-map request coalescing, superseded downloads,
  failure/retry and disconnect cancellation. Mounted state is not confused with native filesystem indexing.
- Container HTTP tests: unauthorized requests rejected, current-map selection, invalid/missing maps,
  and legacy fallback while a catalog is unavailable.
- Emscripten 2.0.11 build passed. No function signature mismatch warnings or missing-function stubs.
- Headless Chrome (SwiftShader, mobile assets, timer-based assertions) passed initial join,
  duel1 → ctf1 → duel1, return from browser cache without pk3 network requests, HTTP 503/retry,
  a 35-second download with sv_timeout 30, and a second map change during download.
- The same basic browser transition test also passed with the exact production mod archives.
- Independent review identified native indexing acknowledgement, deterministic directory entries
  and legacy disk duplication; each was corrected and verified.
- Live HTTPS/gateway checks verified the map manifest, ranged authenticated package download,
  character portraits, source fingerprint and catalog publication.
- The first additional live browser attempt did not reach active play while the occupied live
  server reported 32/32 slots. After the user explicitly approved the final restart, a fresh
  HTTPS browser loaded the current-map packages and entered the live game successfully.

## Data size (compressed, decimal MB)

| Profile | Map | Packages | Current-map download including core |
|---|---|---:|---:|
| desktop | mp/duel1 | 12 | 365.0 MB |
| desktop | mp/ctf1 | 55 | 374.0 MB |
| desktop | mp/ffa3 | 60 | 383.1 MB |
| mobile | mp/duel1 | 13 | 122.9 MB |
| mobile | mp/ctf1 | 55 | 124.1 MB |
| mobile | mp/ffa3 | 61 | 130.5 MB |

The library is about 1.25 GB in total, but clients receive only their map's requirements.
After migration the existing 3 GiB server volume has about 384 MiB free; the largest temporary
package is about 343 MiB. Future substantial asset additions may require more volume headroom.
No server size, player limit, force regeneration, human clients or current game state was changed
as part of the final checks.

Auto-stop was temporarily disabled for file transfer and restored after the user approved the
final restart. Live configuration confirms auto-stop enabled, performance CPU, one vCPU and
2048 MiB RAM. The repository fly.toml continues to specify auto-stop=stop and performance-1x / 2 GB.

## hoth2 reliable-command recovery

A cold/slow hoth2 download can receive and acknowledge more than the engine's 128 reliable
server-command history entries before cgame starts consuming them. The fresh post-download
gamestate supplies authoritative configstrings, but the previous executed-command checkpoint
can still point outside that history. Reproduced the reported `CL_GetServerCommand: a reliable
command was cycled out` error with a 35-second download and 165 server messages.

The browser client now rebases an irrecoverably old checkpoint to the complete gamestate's
sequence. Normal pre-gamestate replay remains unchanged when the required history is available;
active-game overflow checks are not bypassed. The same regression passes with the fix. Quiet
hoth2 entry also passed. Pinned Emscripten build and existing Python/Node suites pass.

Reproducible local browser regression (never use the live server):

```sh
PLAYWRIGHT_MODULE=/path/to/existing/playwright \
JKA_TEST_CONTAINER=jka-on-demand-test \
node web/tests/map-download-reliable.cjs
```

The fixture expects the documented localhost gateway on 8282, local-only-test credentials,
readable map packages at /data/web/map-paks, and engine home /tmp/home. No game assets are in git.
The run also logs unrelated missing Hoth texture/music warnings; those are outside this fix.
