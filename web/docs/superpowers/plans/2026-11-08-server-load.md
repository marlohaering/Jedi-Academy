# Server Load Implementation Plan

> Implement inline using executing-plans.

**Goal:** Show dedicated-server CPU, resident memory and UDP response time during play.
**Architecture:** Gateway background sampler reads /proc for the PID exported by start.sh and performs bounded getinfo queries. An authenticated no-cache endpoint serves the latest sample. The shell polls without overlapping requests.
**Tech Stack:** Python stdlib/aiohttp; plain JavaScript/CSS.
**Spec:** ../specs/2026-11-08-server-load-design.md

## Constraints
No dependencies, engine changes, reference-source changes or deployment. All changes in web/.

## Review Focus
Missing process data, process restart, UDP timeout, stale network data and touch-control overlap must not imply healthy current data.

## Tasks
- [x] Test CPU delta, process restart and missing process data using temporary proc fixtures.
- [x] Implement sampling and authenticated endpoint in gateway.py; export GAME_PID in start.sh.
- [x] Add small noninteractive shell indicator; bound requests, show stale/unknown state and warning text as well as color.
- [x] Run server tests, shell/JS syntax checks and diff checks; document metric semantics.

## Verification record
Process fixture test passed after failing for missing sampler. Live procfs sampling passed. Six Node VM checks passed (healthy, warning, overloaded, no reply, stale, fetch failure). Python compilation, JavaScript syntax, shell syntax and git diff whitespace checks passed. Full gateway integration was not run: local aiohttp is unavailable; no packages installed. No deployment performed.
