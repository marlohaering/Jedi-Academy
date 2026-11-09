# Light side staff bot and full Force duel rules

Status: proposed design for user approval. Implementation and training have not started.

## Intent and scope

Upgrade the existing companion into a strong light-side staff-saber opponent in FFA and full Force private duels. Its specialties are pull into flip kick, pull-assisted saber throws, and staff attacks. Winning takes priority over variety or entertainment. Defensive play, recovery, opportunistic attacks, and retreat are permitted.

Deliver three connected parts in order: correct full Force duel rules, a scripted combat baseline with repeatable evaluation, and self-play reinforcement learning over tactical decisions. Train duel combat before multi-opponent FFA. A two-hour experiment establishes feasibility; it does not promise expert strength.

All maintained changes and documents live under `web/`. Root Raven reference code remains untouched. Original PK3s remain local, ignored, and unpublished. No deployment, paid compute, dependency installation, or system-tool installation is part of design approval. New installations require a concrete proposal and user approval.

## Existing implementation

`web/server/Dockerfile` builds the dedicated OpenJK engine at `260c59c` and the JA++ server game module at `6407f98`. The production combat AI is JA++ `game/ai_main.cpp`, not the browser's OpenJK game source. Maintain a reproducible patch against the pinned JA++ source during the image build, with patch failure stopping the build.

`web/server/japp/lua/sv/companion/plugin.lua` currently manages one Kyle-profile bot named BOT while humans are connected. Preserve that lifecycle and replace its combat profile. Lua does not currently expose the per-frame input control needed for this policy; the combat integration belongs in C++.

Private full Force duels currently grant every power at level 3 and later restore powers. Bot acceptance currently calls the normal duel path. Private duels also have distinct regeneration, kick damage, damage filtering, and winner recovery. Browser prediction currently lacks JA++ full Force event handling. Configuration alone cannot implement the agreed behavior.

## Approaches

The selected approach patches existing JA++ private duels and adds a C++ bot policy boundary, retaining engine movement, damage, navigation, and command plumbing. This avoids duplicating duel isolation and keeps actual game rules authoritative.

A separate duel system would duplicate challenge lifecycle, isolation, and cleanup. Configuration alone cannot preserve Force builds or repair bot acceptance. Neither was selected.

For learning, the selected approach learns tactical decisions over scripted movement and combo controllers. Direct learning of all per-frame inputs remains a possible later project because its sample requirements and action complexity are substantially greater. A purely scripted version remains the baseline and fallback.

## Full Force private duel contract

`/engage_duel` remains the existing normal saber-only mode. `/engage_fullforceduel` starts the mode below, and bot acceptance must preserve the offered mode. Neither mode silently changes into the other.

- Both participants begin at 100 health and 100 armor.
- Preserve each participant's legal Force alignment, known powers, and levels. Do not grant, borrow, or restore an artificial all-powers build.
- Use current FFA Force regeneration and flip-kick damage dynamically, rather than copying their present numeric values into separate duel settings.
- Allow saber, flip-kick/melee, and legitimate Force damage between the two participants. Opponents may use their own legal dark-side builds; the bot remains light side.
- Disable guns, hooks, jetpacks, map pickups, and all holdables during the duel. Preserve blocked inventory for afterward rather than granting new equipment.
- Prevent pre-existing deployables or temporary equipment effects from contributing to the duel. Exact safe entity cleanup is an implementation decision; unrelated players' effects must remain intact.
- Retain isolation from other players, including damage and Force interactions in both directions. Preserve the existing countdown, duel result reporting, multiple simultaneous duels, and no distance-based separation limit.
- After the duel, the survivor keeps remaining health, armor, and Force, with no automatic healing, armor refill, respawn, or winner invulnerability. The loser follows normal FFA respawn behavior. Normal duel recovery stays unchanged.

Builder decisions: preserve existing Force reserve and ongoing legal Force effects at entry because only health and armor were specified to reset; retain normal gameplay restrictions such as saber-lock and animation constraints. Keep temporarily suppressed equipment inactive after the duel until the player activates it again. Restore its ownership where safe, not its previous active effect.

Scope server changes with full Force mode throughout entry, active combat, victory, death, disconnection, and cancellation. Remove obsolete Force restoration paths for this mode so cleanup cannot overwrite the real build. Fix both private-duel damage gates without enabling guns or outsider damage. Retain normal saber-duel behavior in every shared branch.

Browser changes must recognize and clear full Force mode from JA++ duel events, and permit the appropriate Force prediction only in that mode. Verify jump/contact flip-kick behavior against the server; avoid globally enabling Force during normal private duels.

## Bot identity and build

Use a stock double-bladed staff saber and light alignment. Neutral powers are permitted; dark-side powers, including Lightning, Grip, Drain, and Rage, are forbidden. The earlier lightning-poking idea is superseded.

Initial rank-7 build uses the verified 100-point budget:

| Power | Level | Cumulative cost |
| --- | --- | --- |
| Jump | 3 | 8 |
| Push | 3 | 10 |
| Pull | 3 | 10 |
| Absorb | 3 | 10 |
| Heal | 3 | 12 |
| Saber offense | 3 | 14 |
| Saber defense | 3 | 14 |
| Saber throw | 3 | 18 |
| Speed | 1 | 2 |
| Sight | 1 | 2 |
| Total | | 100 |

Other powers start at zero. Validate the actual spawned configuration against engine legalization, not only the serialized profile. Compare alternative legal builds later; learning the allocation is outside the first experiment.

In FFA the bot also uses only its saber and legal Force powers, without guns, hooks, jetpacks, or holdables. Other players retain normal FFA equipment access. The existing companion becomes the strong bot rather than adding a separately summoned opponent.

## Observation and action boundary

Combat decisions consume a restricted observation object rather than raw enemy `playerState`. The scripted and learned policies share this boundary. Old combat and Force branches must not run alongside it and bypass its restrictions.

Allow the bot its own resources, legal build, movement and animation state; world geometry queries for movement; and opponent cues a player could observe. Do not expose exact enemy health, armor, Force reserve, private input, hidden targets, or internal animation/move identifiers that reveal more than visible motion. Derive visible cues from actual visibility and audible game events. Sight may reveal information only to the extent the active power provides it to a human player.

Start with approximately 180 ms latency for newly observed opponent actions, quantized consistently at server ticks. Already chosen actions and continuous movement may continue; anticipation based on earlier observations is allowed. New targets, counters, and combo cancellations cannot consult fresh undisclosed state. Low-level controllers may immediately honor the bot's own state and physical collisions, but must use the same delayed opponent observations.

Exact cue schema, bounded turn rates, memory limits, and visibility sampling are builder choices to document and test. Target tracking retains last-seen observations without secretly updating hidden positions. The policy may adapt during the current match, but player-specific memory resets at the match boundary and is not retained across sessions.

Outputs pass through ordinary movement, view, button, and Force-selection inputs. Never grant damage, teleport, refill resources, alter opponents, or bypass the game simulation to execute a technique.

## Scripted controllers and tactical policy

Implement reusable controllers for spacing, approach, strafe, disengagement, recovery/defense, pull-to-flip-kick, blade switching, saber throwing, and staff attacks. Controllers validate preconditions, track progress, and return completion or failure. Bound action duration so an obsolete commitment can end after the reaction limit.

A flip kick is a jump/contact maneuver, distinct from staff alternate-attack kicks. It requires compatible movement and close contact; Pull does not guarantee contact or knockdown. Preserve the game's knockdown randomness and immunity rules.

Stock staffs cannot throw with both blades active. Disable the second blade, wait for the medium-style weapon state, throw with legal clearance and resources, and reactivate only after the saber returns. Avoid pulling an opponent so close that the throw cannot start.

The scripted baseline selects among these options using distance, visible threats, its own resources, and observed outcomes. FFA adds target selection, multiple-threat awareness, opportunistic finishing, and escape planning. It may attack distracted opponents and avoid unfavorable engagements. Use existing navigation where it is adequate; local combat movement must still obey the restricted observation boundary.

## Self play architecture

Use isolated local headless dedicated-server simulations with local game assets. Each worker runs the actual patched game rules, not an approximate replacement combat simulator. Seed and record episodes; reset combat state, resources, entities, policy memory, and start positions between episodes. Randomize legal starting conditions and opponent builds while keeping evaluation seeds held out.

Provide a training-only stepping and observation/action interface. Normal server operation does not expose it. Preserve the 40 Hz world step and ordinary bot/world ordering when accelerating. Simply raising `timescale` coarsens server physics; existing catch-up stepping does not run bot decisions once per simulated frame. Therefore accelerated stepping requires explicit verification before its throughput counts as a benchmark result. Reproducibility is a tested target, not an assumption of exact bitwise determinism.

The learner selects tactical options and bounded parameters; scripted controllers execute their inputs. Training and deployment use the same observation normalization, action masks, reaction queue, controllers, and policy semantics. Include enough bounded history for opponent tendencies without persistent player profiles.

Train against a pool of earlier checkpoints, the scripted baseline, and opponents with varied legal builds and behaviors. Do not train only against the latest identical copy. Start with duels; later train and test multi-opponent FFA, including threats from FFA weapons the bot itself does not use.

Use a compact CPU policy. The builder selects the learning algorithm and dependency versions after compatibility checks, and proposes exact installations for approval. Prefer a small server-side inference implementation with an explicit versioned model format so production does not require Python, paid services, or a large ML runtime. Verify exported inference against the learner before evaluation. Invalid or missing models select the scripted fallback with a clear operator log.

## Reward and experiment budget

Primary reward is duel victory or defeat. Unfinished training duels terminate as draws at two simulated minutes; this does not change live duel duration. Draws must not receive positive terminal reward. Supporting damage-advantage shaping is modest, bounded, and symmetric; no reward for pressing buttons, attempting combos, or merely surviving. Track retreat and draw frequency to detect stalling.

Builder choices: use win/loss rewards of +1/-1 and draw reward 0 initially. Record decomposed reward terms and their bounds. Exact shaping coefficients and FFA rewards are tuning decisions, with wins and actual evaluation results remaining authoritative. Training instrumentation may measure hidden outcomes for reward and metrics, but never expose them as policy observations.

The first local experiment is at most 30 minutes of performance benchmarking followed by up to two hours of duel training, with at most four simulation workers. Later FFA training needs a separately agreed resource budget before it runs. Do not start the two-hour training budget until basic correctness and stepping equivalence pass. Cap resource use for the local machine and checkpoint so the experiment can be interrupted. Report measured world steps and decisions per second, match completions, memory, and learning results. Do not extrapolate expert performance from raw training speed.

No training libraries are installed in the inspected host Python environment. The machine has eight CPU cores and about 16 GiB available RAM at inspection. Existing Podman images and build tooling may reduce setup work, but dependency availability and compatibility still need concrete checks. A failed feasibility check produces a specific blocker and recommendation, not an unverified training result.

## Validation and promotion

First verify duel state transitions, preserved Force builds, 100/100 start, FFA regeneration, legal melee/Force damage, prohibited equipment, outsider isolation, unchanged normal duels, and winner/loser cleanup. Test both human and bot challenge acceptance. Include death, disconnect, cancellation, and simultaneous duels.

Verify fixed-position staff blade switching, throw clearance, pull/flip-kick execution, and browser prediction. Check every wasm build for signature mismatch warnings and unresolved `missing function:` entries. Use the repository's Chrome/SwiftShader and mobile-profile guidance for browser checks.

Observation tests must prove hidden state does not affect decisions and fresh opponent actions cannot bypass latency through a controller or legacy branch. Compare accelerated and real-time simulation under identical seeded actions before training. Test episode resets and model export parity.

Evaluate checkpoints against held-out scripted opponents, earlier versions, varied builds, maps and seeds. Keep evaluation separate from pool updates and training. Promote only after measured improvement over the scripted baseline without violating behavior constraints; retain rollback to the scripted baseline.

The initial human strength target is at least 70% wins across 30 completed duels against the user. Report every attempted duel, draws, durations, conditions, and win counts; do not discard unfavorable outcomes or claim statistical certainty from this small sample. FFA evaluation reports kills, deaths, score per minute, participants, equipment conditions, and maps in repeated matches. There is no agreed numeric FFA threshold; the builder should report comparative results rather than invent one.

User evaluation is required to establish human strength. Successful builds, self-play reward increases, and wins against stock bots do not establish that target. Preserve a replay or decision trace sufficient to investigate failures without logging secrets or publishing copyrighted assets.

## Delivery stages and remaining decisions

1. Patch and verify the agreed full Force rules and necessary browser prediction.
2. Implement and verify the restricted scripted staff companion and evaluation harness.
3. Build the stepped self-play environment, propose exact dependency installation, and benchmark it.
4. Run the approved bounded duel-training experiment and report held-out results.
5. Extend self-play to FFA and perform human evaluation; keep the scripted fallback unless promotion criteria pass.

The user has selected the behavior and budget above. Implementation details left to the builder include file layout, IPC transport, model size, algorithm choice, controller parameters, test fixtures, cleanup mechanisms, and statistical reporting, within these constraints. Any change to game rules, information access, resource budget, or bot identity returns for user decision. Live deployment requires separate authorization.
