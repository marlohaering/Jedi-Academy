# On-demand map downloads

User requested direct implementation: integrated engine downloads, progress and browser cache, no page reload.

- [x] Build versioned core/shared/map packages for every installed BSP, separately for desktop/mobile. Assign shared files to dependency groups so maps do not duplicate them. Publish a catalog atomically and retain the legacy package fallback.
- [x] Serve authenticated manifests for a requested map. New shell downloads only current-map requirements and verifies response sizes before caching.
- [x] Pause map initialization at CL_InitDownloads while the shell downloads/mounts missing packages. Resume via FS_Restart and the existing donedl handshake. Ignore superseded map completions. Keep the engine/network loop running.
- [x] Show progress, retry and failure UI during first load and map changes; preserve cache/settings and never reload the page.
- [x] Verify package dependency coverage and no duplication, endpoint validation/fallback, cache/truncated response handling and map-change races. Build pinned Emscripten engine; check signature and undefined-function warnings. Exercise actual map transitions where available.

Operational choice: package generation runs separately from the game server; new catalog publication is atomic. No copyrighted output goes in git. Deployment must retain enough disk headroom and existing client compatibility. Browser cache stores visited map bundles; MEMFS only gains bundles actually requested during the current session.


Verification ledger:
- Python tests cover exclusive shared ownership, map-specific selection, reproducible rebuild hashes, Ghoul2 animation dependencies and reuse of parsed model metadata.
- Five Node tests cover missing packages, same-map gamestate coalescing, stale completion, failure/retry, and disconnect cancellation. Mounted packages are distinguished from native-indexed packages.
- Container HTTP integration covers authentication, current-map lookup, unsupported/invalid maps and catalog/legacy fallback.
- Pinned Emscripten build passed; no function-signature mismatch or missing-function entries.
- Real headless Chrome passed duel1→ctf1→duel1, cache-only return, HTTP failure/retry, 35-second download with sv_timeout=30, and map changes during download.
- Independent review findings fixed: native filesystem-indexing acknowledgement, deterministic ZIP directories, and retirement of duplicate legacy builds with catalog-safe orphan cleanup.
- Production migration: stage MP catalog first within the 3 GiB volume, deploy with auto-stop temporarily disabled, retire legacy files, publish remaining installed maps, restore auto-stop. Preserve all production JA++ override archives; game data never enters git.

Completion: all 57 production-map packages published and SHA-256 verified, including JA++ overrides. Auto-stop restored after approved restart. A real HTTPS browser loaded the current map and entered the live game. See ../../on-demand-map-verification.md.
