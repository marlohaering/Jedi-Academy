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
- An additional live browser attempt did not reach active play within 180 seconds. The live server
  concurrently reported 32/32 occupied slots, one human and mp/ctf1. Existing players were not kicked
  to force this optional check. Local end-to-end tests passed as above.

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

Auto-stop was temporarily disabled for file transfer. Restoring it is pending user confirmation
because it requires restarting the occupied live machine. The repository fly.toml continues to
specify auto-stop=stop and performance-1x / 2 GB.
