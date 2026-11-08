# Performance CPU verification, 2026-11-08

User approved performance-1x / 2 GiB. Updated live Fly machine 8111546b901d48 in fra, verified CPU kind performance, one vCPU, 2048 MiB, and passing health check. Persisted the size in web/fly.toml and pushed commit 9a9ac43. Existing application image was retained; no application rebuild was necessary.

## Repeat load test

Same method as the shared-CPU test: authenticated RCON, unique skill-5 bots, process CPU/RSS and localhost UDP getstatus replies. Also sampled VM steal from /proc/stat. Started from an empty server, temporarily disabled frag/time limits and companion. Extended ffa3 to 45 seconds and added 60 seconds back on duel1 to exercise the reported lingering lag.

| Stage | Duration | Mean CPU | Response p95 | Response maximum | Timeouts |
|---|---:|---:|---:|---:|---:|
| idle | 12 s | 3.3 % | 0.2 ms | 0.2 ms | 0 |
| 16 bots | 22 s | 8.7 % | 0.2 ms | 0.2 ms | 0 |
| 32 bots | 30 s | 15.5 % | 0.2 ms | 0.2 ms | 0 |
| 32 bots map change duel2 | 30 s | 24.5 % | 0.2 ms | 2.5 ms | 0 |
| 32 bots map change ffa3 | 45 s | 19.1 % | 0.2 ms | 0.3 ms | 0 |
| 32 bots back to duel1 | 60 s | 15.4 % | 0.3 ms | 1.1 ms | 0 |

All sampled occupied-server status responses contained the expected 16 or 32 players. No bots were lost across map changes. Across all 32-bot stages, VM steal averaged 0.0–0.1%, instead of the previous ~93% during degradation. Game-process RAM peaked at about 174 MiB. There were no query timeouts in any stage, including a full minute after returning from ffa3 to duel1.

This supports CPU scheduling limits as the cause of the earlier server stalls: changing only the CPU class removed the reproduced degradation. It does not guarantee 32 real browsers will behave identically; WebSocket/network load, client rendering and longer-term behavior remain outside this bot-only test. Queries start after the map command returns, so they do not measure the entire map-loading interruption.

## Cleanup

Removed test bots; restored mp/duel1, fraglimit 30, timelimit 15, bot_minplayers 0, companion_paused 0. Re-enabled auto-stop (stop); min_machines_running remains 0. Performance CPU and 2 GiB stay configured permanently. Raw samples and comparison chart are alongside this report.
