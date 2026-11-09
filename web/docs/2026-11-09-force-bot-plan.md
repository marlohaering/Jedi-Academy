# Staff Bot and Self Play Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Read the approved design before execution. Steps use checkbox syntax for tracking.

**Goal:** Deliver a light-side staff companion strong in FFA and full Force duels, with corrected duel rules and a measured local self-play experiment.

**Architecture:** Patch pinned JA++ and OpenJK sources reproducibly from `web/`. Share sanitized observations and ordinary-input controllers between scripted and learned policies. Train a compact tactical network in isolated stepped dedicated servers; run exported inference inside the native game module.

**Tech Stack:** C/C++, JA++ `6407f98`, OpenJK `260c59c`, Lua, Python, existing Podman and Emscripten 2.0.11. Proposed training stack: CPU PyTorch, Gymnasium, NumPy, Stable Baselines3 and sb3-contrib MaskablePPO; exact compatible versions and installation require approval at Task 10.

**Spec:** [Approved design](2026-11-09-force-bot-design.md).

## Global constraints

- All maintained work lives under `web/`; leave Raven reference code untouched.
- No copyrighted game assets, passwords, generated datasets, or model checkpoints enter Git or public artifacts.
- Ask before installing SDKs, packages or system tools; design/plan approval does not approve installation.
- No deployment or paid compute is authorized.
- Normal private duels stay saber-only. Full Force duels start at 100/100, preserve legal Force builds, use FFA regeneration and kick damage, and prohibit guns/hooks/jetpacks/pickups/holdables.
- The bot uses staff, neutral/light powers, and the design's exact 100-point build in both FFA and duels.
- Approximately 180 ms opponent-reaction latency; choose eight 25 ms ticks (200 ms, rounding upward) so no opponent cue arrives early.
- No raw opponent state in either policy or its controllers; adaptation resets at match boundaries.
- At most four simulation workers, a 30-minute benchmark, and two hours of initial duel training. Later FFA training needs a separately agreed budget.
- Expert strength is a measured goal, not a delivery claim; human duel target is 70% wins over 30 completed duels, with draws and all attempts reported.

## Review focus

- A full Force duel ends during a death, disconnect, map transition, or event loss: real Force builds survive and browser mode clears. Tests in Tasks 2 and 3.
- An outsider, old projectile, or pre-existing deployable contacts a duelist: no outsider interference or forbidden equipment damage. Tests in Task 2.
- A hidden opponent changes state or an old client slot is reused: neither decision latency nor tracking leaks new information. Tests in Tasks 4 and 6.
- A worker crashes, sends malformed data, or fails reset: the learner fails the episode clearly and production never blocks on IPC. Tests in Tasks 8 and 9.
- An invalid model or mismatched action schema loads: use the scripted fallback; do not execute unintended actions. Tests in Task 11.

## File and interface map

Keep source overlays outside runtime Lua/assets: `web/server/native/` contains new JA++ C++ modules, `web/server/patches/` patches pinned JA++/OpenJK integration points, and `web/server/prepare-native.py` checks revisions and applies both. Docker copies only runtime assets from `server/japp/` as before.

- `native/duel_rules.{h,cpp}`: scoped full Force rules and cleanup helpers.
- `native/bot_types.h`, `bot_observation.{h,cpp}`: observation schema, delayed history and masks.
- `native/bot_controller.{h,cpp}`, `bot_policy.{h,cpp}`: input controllers, baseline and lifecycle.
- `native/bot_model.{h,cpp}`: versioned model validation and native inference.
- `native/training_session.{h,cpp}`: training-only episode control and telemetry.
- `web/training/schema.json`: authoritative versioned feature/action field order; generate a native header and Python constants from it.
- `web/training/{protocol,env,pool,reward,train,export,evaluate,experiment}.py`: standard-library protocol/tooling plus approval-gated ML imports.
- `web/training/.gitignore`: ignore environments, caches, logs, rollouts and checkpoints locally; no new root ignore files.
- `web/tests/native/`: native unit and real-engine scenario fixtures.
- `web/tests/test_{prepare_native,training_protocol,training_env,training_reward,training_export}.py`: Python tests.
- `web/server/build-native.sh`, `web/tests/run-native.sh`: reproducible local/container builds and tests without implicit installation.
- `web/docs/force-bot-operations.md`: execution commands, approved dependency versions, evaluation conditions and rollback.

Shared native types use namespace `webbot` and fixed-size bounded storage. Define `Tick=int64_t`, `BotId=int`, `Mode { Ffa, NormalDuel, FullForceDuel }`, `Observation`, `ActionMask`, `TacticalAction`, `ControllerState`, `Command`, `EpisodeConfig`, and `EpisodeResult` in `bot_types.h`. `Command` contains desired movement axes, view angles, button bits and requested Force selection, never direct state mutations. Engine adapters alone translate it to existing bot input plumbing.

Training decisions occur every four world ticks (100 ms); controllers execute every 25 ms world tick. Opposition cues are served from the eight-tick delay buffer. Own state remains current. Model and scripted policies share this schedule and schema. A pending controller cannot access fresh opponent state for cancellation.

## Stage A: Full Force rules

### Task 1: Reproducible native patch build and test runner

**Files:** Create `server/prepare-native.py`, `server/build-native.sh`, `server/patches/README.md`, `tests/test_prepare_native.py`, `tests/run-native.sh` under `web/`; modify `web/server/Dockerfile`.

**Interfaces:** `prepare_native(source: Path, project: str) -> None` accepts `japp` or `openjk`, checks the full expected commit, applies sorted project patches with `git apply --check` first, and copies project overlays. `build-native.sh --source-root PATH --output PATH` builds the pinned sources using already available tools; missing tools produce a specific error without installing them. `run-native.sh [CASE]` returns nonzero on failure and emits case names.

- [ ] Write `test_wrong_revision_rejected`, `test_patch_failure_leaves_source_unchanged`, and `test_clean_pinned_tree_prepares`; assertions: wrong revision fails, invalid patch fails before any overlay/mutation, valid fixture produces expected source.
- [ ] Run `python3 -m unittest discover -s web/tests -p test_prepare_native.py`; confirm failure before implementing the preparer.
- [ ] Implement the preparer and runner; split clone/checkout, preparation and compilation in Docker so patches invalidate the correct layer. Keep JA++ build flags and output placement unchanged. Support both existing source trees and clean fetched clones without installing dependencies automatically.
- [ ] Repeat the test command; run `web/tests/run-native.sh smoke` after producing a module. If SCons/build prerequisites are unavailable, stop the build path with an exact approval request; do not claim native checks passed.
- [ ] Commit the working patch/build integration and its tests.

### Task 2: Full Force contract and lifecycle

**Files:** Create `web/server/native/duel_rules.{h,cpp}`, `web/server/patches/japp/0001-full-force-rules.patch`, `web/tests/native/duel_rules_test.cpp`, `web/tests/native/scenarios/duels.json`; modify `web/server/server.cfg`.

**Interfaces:** `bool IsFullForceDuel(const gentity_t*)`; `void BeginFullForceDuel(gentity_t*, gentity_t*)`; `void FinishFullForceDuel(gentity_t*, gentity_t*)`; `bool DuelAllowsDamage(const gentity_t*, const gentity_t*, int mod)`; `int DuelForceRegenMs(const gentity_t*)`; `int DuelFlipKickDamage(const gentity_t*)`. Integrate with pinned `g_cmds.cpp`, `g_active.cpp`, `g_combat.cpp`, `w_force.cpp`, `ai_main.cpp`, `g_local.h` and game `SConscript`.

- [ ] Write native/scenario tests asserting full Force start is exactly 100/100 for both players; levels/known bits/alignment/reserves are unchanged; FFA regeneration/kick cvar changes apply dynamically; normal-duel behavior is unchanged.
- [ ] Add cases for both challenge modes and bot acceptance, opposing legal dark powers, flip-kick damage, blocked guns/holdables/pickups, pre-existing seekers/sentries, outsider damage/Force in both directions, death/disconnect/cancel/map change, and simultaneous duels. Assert the survivor retains remaining resources and gains no winner invulnerability; loser respawns normally.
- [ ] Run `web/tests/run-native.sh duel_rules`; require tests to fail against the unpatched rules.
- [ ] Implement the helpers and integration patch. Record requested challenge mode explicitly until acceptance; remove full Force grants/restoration, preserve normal-duel paths, retain damage identity guards before scoped damage allowance, suppress forbidden equipment without deleting its ownership, and reject blocked holdables at authoritative use sites. Handle pre-duel projectiles/deployables by owner and duel identity rather than classname alone. Retain normal saber-only weapon locking.
- [ ] Correct the `g_privateDuel` bitmask comment: bit 4 respawns participants after a duel, bit 8 disables distance separation; retain normal duel configuration. Route full Force winner cleanup around respawn/refill behavior instead of changing the shared mask.
- [ ] Run `web/tests/run-native.sh duel_rules` and `python3 -m unittest discover -s web/tests -p 'test_*.py'`; commit once actual game scenarios and unit checks pass.

### Task 3: Browser full Force prediction

**Files:** Modify `web/engine-mp/codemp/cgame/{cg_event.c,cg_local.h,cg_main.c,cg_predict.c}` and `web/engine-mp/codemp/game/bg_misc.c`; create `web/tests/native/duel_prediction_test.cpp` and `web/tests/duel-browser.cjs`.

**Interfaces:** Store local client full Force event state without changing network `playerState` layout. Expose `qboolean CG_IsFullForceDuel(void)` through the existing cgame build boundary for shared prediction. Clear state when a snapshot shows no duel, when local client changes, and on map/init. Use pinned JA++ event values after checking their definitions; do not infer them from truthiness alone.

- [ ] Add tests for normal start, full Force start, countdown/start event, end, missed end event followed by nonduel snapshot, and map transition. Assert only full Force permits the selected legal Force actions and saber throw; normal duel remains restricted.
- [ ] Run `web/tests/run-native.sh duel_prediction` and confirm baseline failure.
- [ ] Implement the event/state bridge and narrow prediction exception. Preserve ordinary restrictions such as unavailable powers, saber locks and insufficient resources. Compare JA++ jump/contact flip-kick semantics with the browser and carry over only necessary advertised-mode behavior.
- [ ] Build with the existing Emscripten 2.0.11 toolchain using `cd web && ./build-mp.sh`, inspect the complete log for signature mismatch warnings and `dist-mp/openjk_mp.js` for `missing function:`. Do not install a toolchain.
- [ ] Run native tests and `node web/tests/duel-browser.cjs` against a local server using existing Chrome/SwiftShader guidance; verify full Force throw/contact kick and unchanged normal duel. Commit verified client support.

## Stage B: Scripted companion and evaluation

### Task 4: Delayed observation boundary

**Files:** Create `web/server/native/{bot_types.h,bot_observation.h,bot_observation.cpp}`, `web/training/{schema.json,generate_schema.py}`, `web/tests/native/bot_observation_test.cpp`, `web/tests/test_training_schema.py`.

**Interfaces:** `Observation Observe(BotId, Tick)`; `ActionMask AllowedActions(const Observation&)`; `void ResetObservations(BotId)`; `generate_schema(schema: Path, output_root: Path) -> None`. Engine raw data enters only the observation adapter; controllers/policies consume `Observation`.

Use a version-1 tensor of four historical 128-float frames sampled every 100 ms (512 floats), with oldest-to-newest order. Each frame contains 24 self fields, four observed-target slots of 24 fields, and eight world probes. Slots carry internal generation-tagged public target identities outside the tensor. Targets are selected from delayed observable cues, never from live hidden proximity.

Self fields: health, armor, Force, position xyz, velocity xyz, yaw sin/cos, pitch, grounded, saber airborne, blade state, weapon ready, knocked down, Absorb active, Speed active, saber lock, own recovery time, active option, option elapsed, duel mode. Per-target fields: visible, cue age, relative xyz, observed velocity xyz, observed yaw sin/cos, attack/block/kick/throw cues, observed Force-effect cue, hostility, and eight match-local counters for observed approach/retreat/attack/block/power/throw and the bot's combo success/failure. World probes: four horizontal clearances and four ledge depths. Document fixed scales/clamps in `schema.json`; missing values and padded history are zero with validity cues.

- [ ] Write tests asserting two worlds differing only in hidden enemy reserves/health/input produce identical observations, actions and masks; cues at tick T remain unavailable until T+8; collision/self-state updates remain immediate; stale targets never get hidden position updates.
- [ ] Test death, map reset, client-slot reuse, target leaving visibility, history padding, finite/clamped features and the exact generated shape/order across Python/C++.
- [ ] Run `web/tests/run-native.sh bot_observation` and `python3 -m unittest discover -s web/tests -p test_training_schema.py`; confirm failure.
- [ ] Implement the bounded buffers, adapters, generated schema and sanitization. Capture audibility/visibility from actual game events/traces. Sight only changes cues when active and legally observable. Exclude internal move identifiers, exact enemy resources and fresh target state from outputs.
- [ ] Repeat both commands and commit the boundary.

### Task 5: Ordinary-input combat controllers

**Files:** Create `web/server/native/bot_controller.{h,cpp}`, `web/server/patches/japp/0002-bot-input.patch`, `web/tests/native/bot_controller_test.cpp`, `web/tests/native/scenarios/staff.json`.

**Interfaces:** `enum class Option { Hold, Approach, Retreat, StrafeLeft, StrafeRight, StaffAttack, StaffKick, PullFlipKick, PullThrow, Push, Absorb, Heal, Speed, Sight, TargetNext, TargetPrevious, Count }`; `void StartController(ControllerState&, TacticalAction, Tick)`; `Command StepController(ControllerState&, const Observation&, Tick)`; `void ResetController(ControllerState&)`. A tactical action is one option; target cycling and discrete options avoid an unbounded parameter space. Keep Hold valid at all times. Force levels and legal execution come from own state.

- [ ] Test legal command sequences for approach/retreat/strafe, fresh-jump pull/contact flipkick, staff alt-kick, blade disable -> ready/clearance -> throw -> returned -> reactivate, defensive Push/Absorb, Heal/Speed/Sight and failure recovery.
- [ ] Assert no controller mutates world/health/resources or reads enemy entities directly; delayed cue changes cannot trigger early cancellation; failed clearances and low Force select safe commands rather than retries every frame.
- [ ] Run `web/tests/run-native.sh bot_controller` and confirm failures; implement controllers using existing input accumulation and `BotUpdateInput` conversion. Bypass legacy combat/Force branches for controlled bots; preserve noncontrolled bots.
- [ ] Run unit tests and `web/tests/run-native.sh staff_scenarios` at fixed positions, checking actual damage, movement, staff state and Force cost. Keep random knockdown probabilistic. Commit the controllers.

### Task 6: Scripted FFA and duel companion

**Files:** Create `web/server/native/bot_policy.{h,cpp}`, `web/server/japp/botfiles/web_staff.{bot,jkb}`, `web/server/patches/japp/0003-staff-policy.patch`, `web/tests/native/bot_policy_test.cpp`; modify companion `plugin.lua` and `web/server/README.md`.

**Interfaces:** `TacticalAction ChooseScripted(const Observation&, const ActionMask&)`; `void RunBot(BotId, Tick)`; `void ResetBot(BotId)`; `enum class PolicyMode { Scripted, Learned }`. Add server cvars `web_bot_policy` (default `scripted`) and `web_bot_model` (default empty). Identify controlled bots with an explicit profile marker, not only the display name BOT.

- [ ] Test exact legal spawned Force allocation and staff model, human-connected singleton lifecycle, bot-only training lifecycle override, and unaffected ordinary bots. Assert normal and full Force challenges preserve their requested mode.
- [ ] Add tactical cases for repeated approaches, failed combos, low own Force, healing openings, two attackers, a distracted target, a target leaving visibility, human FFA gunfire, slot reuse and a map transition. Verify no guns/hooks/jetpacks/holdables appear in bot actions, and match-local tendencies reset at the map/match boundary.
- [ ] Run `web/tests/run-native.sh bot_policy` before implementation; implement score-based scripted option choice, target selection and bounded turn rates over sanitized observations. Reuse waypoint navigation only behind an adapter that cannot supply fresh hidden enemy positions.
- [ ] Run policy tests and `web/tests/run-native.sh companion_scenarios`; run existing `node --test web/tests/*.test.cjs`. Commit the functioning scripted companion.

### Task 7: Structured evaluation before learning

**Files:** Create `web/training/{protocol.py,evaluate.py}`, `web/server/native/training_session.{h,cpp}`, `web/server/patches/japp/0004-training-telemetry.patch`, `web/tests/test_training_protocol.py`, `web/tests/native/evaluation_test.cpp`, `web/docs/force-bot-operations.md`.

**Interfaces:** `EpisodeResult` includes episode id, seed, mode, winner/draw/reason, elapsed ticks, kills/deaths, damage, initial/final resources, controller failures and policy ids. `evaluate(records: Iterable[dict]) -> dict` aggregates all attempts and reports completed duels separately from draw/invalid counts. Hidden reward/telemetry fields are physically separate from observations.

- [ ] Write aggregation tests for 21/30 wins, draws, disconnects, simultaneous death, incomplete/crashed episodes and duplicate result ids. Assert no silent exclusion of losses and no false success claims for missing human matches.
- [ ] Write engine tests for one outcome per episode, real attacker/victim/MOD attribution, and no hidden telemetry in policy observations; run `web/tests/run-native.sh evaluation` and `python3 -m unittest discover -s web/tests -p test_training_protocol.py` to confirm failures.
- [ ] Implement versioned JSONL records and result aggregation. Document controlled human-duel and repeated FFA evaluation procedures, maps/conditions, scripted baseline identifier, and log locations.
- [ ] Repeat tests and collect an automated baseline report with the current scripted policy. Human evaluation stays explicitly pending until the user plays. Commit evaluation tooling.

## Stage C: Stepped self play and bounded experiment

### Task 8: Real-engine seeded stepping and clean reset

**Files:** Create `web/server/patches/openjk/0001-training-step.patch`, `web/server/patches/japp/0005-training-reset.patch`, `web/tests/native/training_step_test.cpp`, `web/tests/native/scenarios/training.json`; extend `training_session.{h,cpp}`.

**Interfaces:** `void ResetEpisode(const EpisodeConfig&)`; `EpisodeResult AdvanceWorldTicks(uint32_t count)`; `bool EpisodeFinished()`. EpisodeConfig includes seed, map, start positions, mode, legal builds, opponent ids and max ticks. Training mode requires an explicit startup switch, localhost-only binding and no companion lifecycle script. Production does not create the training endpoint.

- [ ] Test equal action/seed traces at real-time versus accelerated execution: same 25 ms world steps, bot calls/order, combat outcomes and resource use within defined floating tolerance. Reject unsupported tick rates. Test timeout at 4800 ticks (120 simulated seconds).
- [ ] Test reset after active Force, thrown sabers, missiles, deployables, dead clients and policy memory. Repeating a seed must reproduce the tested trace on the same build; cross-build bitwise determinism is not required.
- [ ] Run `web/tests/run-native.sh training_step` and confirm failures; implement an explicit native stepping path preserving the original per-tick ordering without scaling physics time. Control engine/game RNG seeds and record all build/schema hashes.
- [ ] Implement clean worker restart as the reference reset first. Optimize to in-process reset only if equivalence cases pass; include restart/reset cost in throughput.
- [ ] Repeat training tests and a normal-server smoke test proving training mode is off by default and ordinary pacing unchanged; commit the step environment.

### Task 9: Worker protocol and environment adapter

**Files:** Create `web/training/{env.py,experiment.py}`, `web/tests/test_training_env.py`; extend `protocol.py`, native training session, operations docs and `.gitignore`.

**Interfaces:** Length-bounded newline JSON protocol v1 on inherited local pipes: `hello`, `reset`, `step`, `close` requests, monotonically increasing ids and matching replies. `step` takes one action for each controlled bot and advances four world ticks; replies contain per-bot observation/mask and separate reward/result telemetry. `Worker.reset(config: dict) -> dict`, `Worker.step(actions: dict[int,int]) -> dict`, `Worker.close() -> None`. Gym adapter follows approved Gymnasium reset/step API after Task 10 installation.

- [ ] Test malformed JSON, oversized frames, bad protocol/schema ids, invalid/fully masked actions, duplicate/out-of-order replies, a crash midstep, timeout, interrupted shutdown and seed reset. Assert a failed worker never becomes a draw/win and production inference never waits for this transport.
- [ ] Run `python3 -m unittest discover -s web/tests -p test_training_env.py` before implementation; implement subprocess ownership, bounded reads/deadlines and guaranteed worker cleanup. Keep IPC handling exclusively in the explicit training path.
- [ ] Repeat tests and `web/tests/run-native.sh training_protocol`; run a short two-bot episode using only standard-library tooling. Commit the worker interface.

### Task 10: Approved training environment and reward/pool

**Files:** Create `web/training/{requirements.in,requirements.lock,reward.py,pool.py,train.py}`, `web/tests/test_training_reward.py`, `web/tests/test_training_pool.py`; extend `env.py` and operations docs.

**Interfaces:** `reward(previous: dict, current: dict, result: dict | None) -> float`; `OpponentPool.sample(seed: int) -> dict`; `OpponentPool.add(checkpoint: Path, metadata: dict) -> None`; `train(config: dict) -> Path`. Opponent sampler mixes scripted, previous checkpoints and varied legal builds, excluding held-out evaluation fixtures.

- [ ] Before any installation, check compatible CPU wheels using official package metadata and an existing supported Python/container interpreter. Present the exact interpreter, pinned direct/transitive packages, destination, download size estimate, and install command for approval. Do not modify the engine's Emscripten environment. Stop dependent training work until approved.
- [ ] Write reward tests: terminal +1/-1/0, two-minute timeout 0, no action/attempt rewards, no positive reward for waiting, finite bounded symmetric damage shaping. Bound total damage shaping to ±0.1 per episode so it cannot dominate victory. Test separate telemetry/observation paths.
- [ ] Write pool tests for reproducible sampling, mixed opponents, checkpoint immutability, missing checkpoints, held-out exclusion and normal legal builds. Run `python3 -m unittest discover -s web/tests -p 'test_training_*.py'` before implementation.
- [ ] After approval, install into the isolated destination, capture a reproducible lock, implement the Gym adapter, pool and CPU `MaskablePPO('MlpPolicy', ...)`. Start with two 64-unit Tanh layers each for actor/critic, a discrete 16-option action space, in-environment masks, seed control and four-frame input history. Use mask-aware evaluation. Log options, reward components, outcomes and draw rate.
- [ ] Test the adapter with synthetic episodes and run a tiny actual-server smoke rollout separate from the two-hour experiment. Assert parameters change, checkpoints reload, masks are respected and interruption saves/cleans up. Commit code and lock only, never installed environments or checkpoints.

### Task 11: Export and nonblocking native inference

**Files:** Create `web/training/export.py`, `web/server/native/bot_model.{h,cpp}`, `web/server/patches/japp/0006-model-policy.patch`, `web/tests/test_training_export.py`, `web/tests/native/bot_model_test.cpp`; extend `bot_policy.cpp`.

**Interfaces:** `export(checkpoint: Path, destination: Path) -> None`; `bool LoadModel(const char* path, Model&, ModelError&)`; `TacticalAction ChooseLearned(const Model&, const Observation&, const ActionMask&)`. Model JSON v1 holds schema hash, option order, normalization constants, dense layer shapes/weights/biases and source build/checkpoint metadata. Export actor only; native dense/Tanh computation, masked logits and deterministic argmax must match Python. No Python/ML runtime or training IPC in production.

- [ ] Test frozen fixtures for Python/native logits within 1e-5 and matching masked argmax, with tied-logit ordering fixed to lowest valid action index. Verify Hold fallback if no valid action remains.
- [ ] Test truncated/oversized files, NaN/Inf, wrong dimensions, unsupported activations, bad schema/action hashes and a missing file. Assert logged scripted fallback without server failure, reloading only at safe explicit boundaries, and bounded inference work.
- [ ] Run `web/tests/run-native.sh bot_model` and `python3 -m unittest discover -s web/tests -p test_training_export.py` before implementation; implement strict loading and the small forward pass using bundled parsing facilities. Keep model paths local and immutable per match.
- [ ] Repeat tests with a real smoke-trained checkpoint and run `web/tests/run-native.sh learned_policy_scenarios`; verify the 200 ms cue boundary and forbidden-action tests still pass in learned mode. Commit inference, keeping the model artifact ignored.

### Task 12: Bounded duel experiment and promotion report

**Files:** Extend `web/training/{experiment.py,evaluate.py}`, create `web/training/configs/duel-pilot.json`, update operations docs; write ignored raw results/checkpoints and a sanitized Markdown experiment report under `web/docs/`.

**Interfaces:** `run_experiment(config: dict) -> dict` persists phase, monotonic wall-clock budget, worker count, build/schema hashes and checkpoints. Resuming cannot reset the used budget. Held-out evaluation uses fixed seeds/maps/builds and mask-aware deterministic policy evaluation against the same scripted baseline conditions.

- [ ] Test wall-clock stop/resume, zero completed episodes, worker failure, interrupted learner, inflated self-play rewards without held-out improvement, and all-draw outcomes. Assert no automatic promotion in these cases.
- [ ] Run standard-library budget/evaluation tests before implementing the runner; then enforce at most 1800 seconds benchmarking plus 7200 seconds training and at most four workers. Bound Torch CPU threads too, so four simulation workers do not imply unbounded learner CPU use.
- [ ] Verify Stage A/B and stepping/export checks pass, then run the benchmark. Report world ticks/decisions per second, resets/completed matches, memory and correctness; stop with a concrete blocker if fidelity fails.
- [ ] Run the bounded duel experiment only if dependencies were approved and the benchmark passed. Save checkpoints and evaluate against held-out opponents/builds/maps; report scripted versus learned results, draws, durations and all failures. Keep `web_bot_policy=scripted` unless measured promotion criteria pass.
- [ ] Document the exact candidate and invite the agreed 30-duel human evaluation when available. Mark the 70% target unverified until played. Commit only sanitized reports/docs; no deployment.

### Task 13: FFA evaluation and training readiness

**Files:** Create `web/training/configs/ffa-evaluation.json`; extend `env.py`, `pool.py`, `evaluate.py`, native training session and `web/tests/test_training_env.py`; update operations docs.

**Interfaces:** Existing worker reset accepts FFA with multiple participants; existing schema presents up to four delayed observed threats without changing model dimensions. `evaluate` reports kills, deaths, score/minute, match lengths, map, builds, opponent policy mix and human participation.

- [ ] Test three-or-more-player target switching, opponents with guns/holdables, offscreen attacks, respawn state, stale target slots, match-end adaptation reset, and no cross-player reward/observation leakage. Assert ordinary production companion lifecycle still owns exactly one upgraded bot.
- [ ] Run `python3 -m unittest discover -s web/tests -p test_training_env.py` and `web/tests/run-native.sh ffa_scenarios` before implementing multi-opponent episodes; extend episode handling without weakening the observation boundary or bot equipment limits.
- [ ] Run scripted and duel-trained FFA evaluations on identical conditions; compare kills/deaths/score per minute and report outcomes without inventing a numeric FFA acceptance threshold.
- [ ] Prepare the concrete FFA self-play configuration, reward definition based on match outcome with bounded damage shaping, and a measured resource-budget proposal. Ask for that budget before any extended FFA training; no assumption that the initial two-hour duel budget covers it.
- [ ] After that budget is agreed, train/evaluate FFA candidates against held-out opponents and human matches, recheck duel performance for regression, and retain the scripted fallback. Commit sanitized results and operations documentation.

## Self review and final verification

- [ ] Cross-check every design requirement against Tasks 1–13; verify generated tensor/action schemas and model metadata match in Python/C++.
- [ ] Run only relevant native, protocol, browser and existing tests after each change; rerun the full required set before final handoff. A missing dependency or absent human evaluation is reported as pending, never passing.
- [ ] Review the whole branch for information leaks, input bypasses, weakened duel isolation, stale mode cleanup and simulation drift. No installation, training beyond approved budgets, or deployment occurs as part of review.
- [ ] Final report separates implemented/verified functionality, measured self-play results, pending human evaluation, and any unrun FFA training. Include commit ids and local artifact paths without exposing secrets or copyrighted data.

## Training library references

MaskablePPO supports the proposed discrete masked actions; masks must be implemented inside worker environments for subprocess use, and evaluation must also be mask-aware: [official sb3-contrib documentation](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html). Policy layer shapes and activation are configurable: [official Stable Baselines3 policy guide](https://stable-baselines3.readthedocs.io/en/master/guide/custom_policy.html). Check supported versions and exact export shapes against the approved installed release at Task 10 rather than assuming the documentation's latest version is compatible with the host's Python 3.15.
