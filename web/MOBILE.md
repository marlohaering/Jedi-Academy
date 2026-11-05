# Mobile concept: the MP client on phones

Status: concept, agreed 2026-11-06. Nothing is implemented yet.

Goal: a phone player opens `jka.haering.me` in the browser and plays on the same FFA server as desktop
players.

## Starting point (as of commit `54234f8`)

| Area | Today | Why it fails on a phone |
|---|---|---|
| Assets | One `jka-mp.pk3` of ≈780 MB. The shell keeps it as a `Uint8Array` and copies it into MEMFS with `FS.writeFile` (`shell-mp/index.html:168`) | About 1.5 GB of tab memory before the game starts. Mobile browsers kill the tab |
| Memory | `INITIAL_MEMORY` 256 MB, growth on, no `MAXIMUM_MEMORY`, `com_hunkmegs 256` | No upper bound, so the tab is killed instead of failing cleanly |
| Rendering | Regal (GL 1.x → WebGL1), ≈11 ms/frame on a laptop iGPU, mostly in `R_ArrayElementDiscrete`. `r_mode -2` (desktop resolution) | A phone GPU and CPU is several times slower. Native resolution on a high-DPI screen makes it worse |
| Input | SDL2 keyboard and mouse only (`shared/sdl/sdl_input.cpp`). No touch or game-controller code. A classic joystick path into `cl.joystickAxis[]` exists (`codemp/client/cl_input.cpp:992`) | No way to move or aim |
| Menus | After `+connect` the player goes through the original UI menus (Join Game, …) | Built for a mouse cursor |
| Shell | No resize, devicePixelRatio, orientation, fullscreen or audio-unlock handling | Wrong size, no fullscreen, possibly no sound |

## Targets and acceptance bar

- **Platforms:** Android in Chromium-based browsers is the main target. iOS Safari is "best effort": the
  code avoids known WebKit pitfalls, but no iPhone is available for development. Before release one
  test pass runs on a real iPhone, borrowed or from a device farm. Until then iOS does not count
  against the acceptance bar.
- **Reference device:** Pixel 9a, GrapheneOS, Brave. Spot checks in Vanadium. Debugging over USB via
  `chrome://inspect`.
- **Orientation:** landscape only. Portrait shows a "rotate your phone" screen.
- **Install form:** a PWA (manifest, standalone display) that also works as a plain tab.
- **"Playable" means:**
  - Frame rate: no fixed target, because render-path work is out of scope (see "Rendering and
    performance"). Frame time on the Pixel 9a is measured and recorded in every phase.
  - First load ≤ 60 s on 4G. Later loads come from the cache.
  - A player can join, move, aim, fight with the saber, use force powers and chat.
  - A 10-minute match runs without a crash and without bad thermal throttling.

## Gameplay scope

- The full MP feature set (all weapons, saber styles, force powers), on the same server and in the same
  match as desktop players (cross-play).
- No aim assist, because it would need server-side changes to game logic. Mouse users have an aim
  advantage. That is acceptable on a casual server.
- A small set of on-screen buttons. Rarer actions go into radial selectors.

## Decisions

### Mobile detection

Mobile mode is on when `(pointer: coarse)` matches and touch is available. `?mobile` and `?desktop`
override it, so mobile mode can be tested on desktop too.

### Assets and memory

- `repack.py --mobile` builds a second client pk3, `jka-mp-mobile.pk3`, with a budget of **≤ 200 MB**.
  It contains only `mp/ffa3` and the models, sounds and effects actually needed. Textures are scaled to
  ≤ 256 px and re-encoded as JPEG. Sounds are 22 kHz mono.
  - `sv_pure 0` already allows clients with different files. Desktop keeps the full pk3.
  - The gateway manifest lists both variants. The shell picks one by detection.
- If the budget is still exceeded, cut in this order:
  1. Music, all of it or all but one track.
  2. Taunt, victory and death voice lines.
  3. Player models beyond a default set of about 8 (with skins). Desktop players using a cut model
     appear as the default model.
  4. Textures down to 128 px.

  Gameplay-relevant sounds (saber, weapons, force) are never cut.
- **No double copy:** the downloaded buffer is handed to MEMFS directly, with no second copy into the
  file system. The code that reads from the cache must not keep a reference to it either.
- `com_hunkmegs` drops to about 128 on mobile. A `MAXIMUM_MEMORY` cap makes the engine fail with a
  readable error instead of the tab being killed. The real values come from P1 measurements.
- `navigator.storage.persist()` keeps the browser from evicting the cache. This matters most on iOS,
  which evicts data a site has not used for 7 days.

### Rendering and performance

- Mobile renders at CSS-pixel resolution, ignoring devicePixelRatio, with the width capped at 1280.
  It uses `r_mode -1` with `r_customwidth` and `r_customheight`, set once at start, since landscape is
  locked.
- `com_maxfps 30` by default, with an option for 60, to limit heat and battery drain.
- **Render-path work is out of scope** (decided 2026-11-06, P0 dropped). Regal and the current draw
  path stay as they are. Resolution and `com_maxfps` are the only performance levers.
- If the frame rate turns out to be unplayable, possible later work, in order:
  1. Make `r_primitives 2` (glDrawElements) render correctly under Regal. On the laptop that takes the
     frame time from ≈11 to ≈2.6 ms. Desktop benefits too.
  2. A small direct WebGL backend for the rd-vanilla tessellator (`RB_StageIteratorGeneric` and
     friends).
  3. Replace Regal with gl4es.

### Input

- A JS/HTML **touch overlay** on top of the canvas calls a small exported C API:
  - `web_move(x, y)`: analog move stick, written into `cl.joystickAxis[]`.
  - `web_look(dx, dy)`: look-drag, sent through `CL_MouseEvent`.
  - `web_key(key, down)`: buttons, as key events, so the normal binds apply.
- The browser **Gamepad API** feeds the same functions from the same JS layer.
- Rejected:
  - SDL finger events in `sdl_input.cpp`: harder to style, and the overlay would be duplicated.
  - Pure console commands such as `+forward`: digital movement only.
- **Layout v1** is fixed. Settings cover size, opacity and look sensitivity, stored in `localStorage`.
  Buttons cannot be moved.
  - **Left half:** a floating move stick. A light push walks, full deflection runs.
  - **Right half:** dragging aims, including drags that start on a button, so attacking and aiming
    work at the same time.
  - **Right-thumb cluster:** Attack (hold), Alt-attack, Jump, Crouch.
  - **Upper right:** Force: tap uses the selected power, long press opens a radial to pick one.
    Weapon: tap cycles, long press opens a radial. Saber style is in the radial too.
  - **Top left:** Use/Action, Menu, Scoreboard.

### Menus and chat

- Phone players never see the original UI menus. On connect the shell sends `team free`.
- An **HTML pause menu**, opened with the Menu button, covers team/spectate, saber style, force and
  weapon selection, quick-chat, settings, the scoreboard and disconnect. Every action is a console
  command.
- Using the original menus by tapping (tap as mouse) is not supported.
- **Chat:** one-tap quick-chat presets ("gg", "nice", "1v1?", …). A "type" button opens the phone
  keyboard through a hidden `<input>` and sends `say …`.

### PWA and shell

- A manifest with `display: standalone` and `orientation: landscape`. On iOS this is the only way to get
  a view without browser chrome, because iPhones have no Fullscreen API. On Android, also use the
  Fullscreen API and `screen.orientation.lock` where they exist.
- Screen Wake Lock while in a match.
- Resume the WebAudio/SDL audio context on the first touch (audio unlock).
- The existing Worker timer for hidden tabs stays. On mobile, also disconnect cleanly when the tab
  stays in the background for a long time.

## Phases

Every phase is deployed and tested on the Pixel 9a. There is no P0: render-path work was dropped, and
its cheap part (resolution, frame cap) moved into P1.

| Phase | Content | Done when |
|---|---|---|
| **P1** Memory and resolution | No double copy. Hunk size and memory cap. `repack.py --mobile`. Manifest variant. Mobile resolution and `com_maxfps` | Loads and runs on the 9a (still without controls). Pk3 ≤ 200 MB. Tab memory and frame time measured |
| **P2** Input | C API `web_move` / `web_look` / `web_key`. Touch overlay layout v1. Gamepad API | Move, aim, attack, jump, force and weapon all work by touch and gamepad |
| **P3** Menus and chat | Auto `team free`. HTML pause menu. Quick-chat and keyboard chat | A full match from join to disconnect without the original menus |
| **P4** PWA and polish | Manifest, persistent storage, wake lock, orientation screen, audio unlock, settings | Acceptance bar met. iOS pass on a real device |

## Open risks

- **Frame rate:** with the render path out of scope, the game may run but be too slow to play
  comfortably. P1 measures this early on the 9a.
- **Memory headroom:** GrapheneOS's hardened malloc and each browser's per-tab limit are unknown. P1
  measures them.
- **iOS:** WebKit memory limits and WebGL quirks stay untested until the release pass.
- **Thermals:** a 10-minute match at 30 fps may still throttle. The resolution cap and `com_maxfps` are
  the main levers.
- **Download time:** 200 MB in 60 s needs ≈27 Mbit/s. That is realistic on good 4G, not on weak
  coverage. If needed, the cut order above goes further.
