# Mobile concept: the MP client on phones

Status: concept agreed 2026-11-06. P1–P4 are implemented (see the results sections below). Open: Pixel 9a
measurements, control tuning, the iOS pass.

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

- `repack.py … profile=mobile` builds a second client pk3, `jka-mp-mobile.pk3`, with a budget of
  **≤ 200 MB**. `start.sh` builds it in the background at container start (≈16 s on a laptop).
  - `textures/` and `models/map_objects/` are kept only where the map, the game code or a global shader
    references them.
  - Single-player-only content is dropped: SP dialogue, mission-select planets, per-level animation sets
    and other maps' ambience.
  - Images are scaled to ≤ 256 px (fonts and lightmaps untouched). Opaque TGAs become JPEGs. WAVs become
    22 kHz mono.
  - `sv_pure 0` already allows clients with different files. Desktop keeps the full pk3.
  - The gateway manifest lists both variants (`paks`, `mobile`). The shell picks one by detection. If the
    mobile pk3 is not built yet, phones get a "try again in a few minutes" message.
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
- 30 fps by default (`?fps=N` overrides), to limit heat and battery drain. The shell caps the rate by
  skipping display frames in its `requestAnimationFrame` wrapper, and the engine runs with
  `com_maxfps 0`. The engine's own cap busy-waits inside the frame in the browser: it burned the whole
  33 ms frame on the CPU.
- **Render-path work was out of scope here** (P0 dropped 2026-11-06), but master has since added batched
  drawing through streamed buffer objects (`rd-vanilla/tr_webgl_arrays.cpp`). That is what P0 was for.
  After rebasing onto it (headless, laptop GPU): phone mode at 914×412 takes 5.8 ms per frame (p95
  7.7 ms; before: ≈19 ms), and desktop at 1280×720 takes 4.8 ms. Resolution and the frame cap remain the
  phone-specific levers.

### Input

- A JS/HTML **touch overlay** (`shell-mp/touch.js`) on top of the canvas calls a small exported C API
  (`codemp/client/cl_input.cpp`, under `__EMSCRIPTEN__`):
  - `web_move(x, y)`: analog move, added to the usercmd in `CL_CreateCmd`. Below 55 % deflection it sets
    `BUTTON_WALKING`. The stock joystick path (`cl.joystickAxis[]`) is not used, because
    `CL_JoystickMove` turns and pitches with its axes instead of moving.
  - `web_look(dx, dy)`: look delta, queued as a mouse event (so menus get it too).
  - `web_key(key, down)`: key events. `web_cmd(text)`: console commands such as `+attack`; the buttons
    use these, so they do not depend on the player's binds.
  - `web_state()`: player state for the overlay (connection, key catcher, weapons, known force powers,
    team, …).
- The browser **Gamepad API** feeds the same functions from the same JS layer, in both modes. Standard
  mapping: left stick move, right stick look, RT attack, LT alt, A jump, B crouch, X use, Y force,
  LB / D-pad left-right cycle the force power, RB / D-pad down next / previous weapon, D-pad up saber
  style, Back scores, Start menu. Pressing a pad button hides the touch overlay until the next touch.
- Rejected:
  - SDL finger events in `sdl_input.cpp`: harder to style, and the overlay would be duplicated.
  - Pure console commands such as `+forward`: digital movement only.
- **Layout v1** is fixed. Settings cover size, opacity and look sensitivity, stored in `localStorage`.
  Buttons cannot be moved.
  - **Left half:** a floating move stick. A light push walks, full deflection runs.
  - **Right half:** dragging aims, including drags that start on a button, so attacking and aiming
    work at the same time.
  - **Right-thumb cluster:** Attack (hold), Alt-attack, Jump, Crouch.
  - **Upper right:** Force: tap uses the selected power, holding it holds grip, lightning and drain.
    The chip above the button shows the selected power, and tapping it opens the force radial.
    (Changed from "long press opens the radial": a long press is needed for the hold powers.)
    Weapon: tap cycles, long press opens a radial with the owned weapons and "Saber style".
  - Radials: slide onto an item and release, or tap an item. A tap outside closes them.
  - **Top left:** Use/Action, Menu, Scoreboard.

### Menus and chat

- Phone players never see the original UI menus. On connect the shell sends `team free` and closes the
  menu (pulled forward into P2, because phones cannot get into a match otherwise).
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
| **P1** Memory and resolution ✅ | No double copy. Hunk size and memory cap. `repack.py profile=mobile`. Manifest variant. Mobile resolution and frame cap | Loads and runs on the 9a (still without controls). Pk3 ≤ 200 MB. Tab memory and frame time measured |
| **P2** Input ✅ | C API `web_move` / `web_look` / `web_key`. Touch overlay layout v1. Gamepad API | Move, aim, attack, jump, force and weapon all work by touch and gamepad |
| **P3** Menus and chat ✅ | Auto `team free`. HTML pause menu. Quick-chat and keyboard chat | A full match from join to disconnect without the original menus |
| **P4** PWA and polish ✅ (iOS pass open) | Manifest, persistent storage, wake lock, orientation screen, audio unlock, settings | Acceptance bar met. iOS pass on a real device |

## P1 results (2026-11-06)

Measured in headless Chrome (Playwright phone emulation, 915×412 CSS px, laptop GPU) against a local
container. These are not Pixel 9a numbers yet.

| | Desktop | Mobile |
|---|---|---|
| Client pk3 | 778 MB | **129 MB** (≈40 s at 27 Mbit/s) |
| Render size | 1280×720 | 914×412 |
| Frame rate | 60 fps | 30 fps (cap) |
| Renderer process RSS in a match | ≈1160 MB | **≈510 MB** |
| wasm heap | 256 MB | 256 MB (`com_hunkmegs 128`, `MAXIMUM_MEMORY` 1 GB) |

- All 131 shaders of `mp/ffa3` resolve to images in the mobile pk3. Music is still included.
- Detection works without parameters under phone emulation (`(pointer: coarse)` + touch).
- Bug found and fixed: rounding the render width *up* (915 → 916 px) made the window larger than the
  screen, and SDL then found no display mode, so GL init failed. The shell rounds down.
- Still open for P1 on the real device: tab memory and frame time on the Pixel 9a (Brave, Vanadium).

## P2 results (2026-11-06)

Tested headless (touch emulation, fake gamepad) against a local container:

- Auto-join, move stick, look drag (also with two fingers at once), attack, force (power used,
  energy drops), weapon radial (Saber, Pistol, Saber style), force radial pick: all work. Gamepad
  move, look and buttons work on desktop. The touch overlay stays hidden on desktop.
- Bug found on the Pixel 9a and fixed: started in portrait, the landscape canvas was larger than
  `screen.width`, SDL found no display mode, and GL init failed. The engine now continues without a mode
  list in the browser (`shared/sdl/sdl_window.cpp`; the list only feeds the resolution menu). The
  "turn your phone sideways" screen was pulled forward from P4.
- Known issues: the buttons overlap the HUD corners (health and force/ammo). Sensitivity and button
  sizes are untuned until tested on the phone.

## PWA and fullscreen, pulled forward from P4 (2026-11-06)

After the first phone test (Brave, Pixel 9a): the bottom of the picture was behind the address bar, a
fullscreen mode broke the overlay, and the page could not be installed.

- The canvas is `position: fixed; inset: 0; object-fit: contain` instead of `100vw × 100vh` (on Android,
  `100vh` reaches under the address bar). The picture keeps its aspect ratio when bars appear or
  disappear.
- The mobile render size comes from `screen.width/height` (landscape, ≤ 1280 wide) instead of the
  window size, since the game runs fullscreen.
- Tapping "Join game" requests fullscreen on the whole document (`documentElement`, so the overlay stays
  visible) and locks landscape. A ⛶ button in the overlay does the same after leaving fullscreen.
- Installable: `manifest.webmanifest` (`display: fullscreen`, `orientation: landscape`), icons, and a
  pass-through service worker `sw.js`. The gateway serves these four files without the session cookie,
  because browsers fetch the manifest and icons without credentials.

## P3 results (2026-11-06)

- The Menu button (and gamepad Start) opens an HTML pause menu, built in `touch.js`. The game keeps
  running behind it, and movement and held buttons are released when it opens.
  - Game: Resume, Join game (`team free`), Spectate (`team spectator`), Saber style.
  - Chat: eight quick-chat buttons, plus a text field that opens the phone keyboard. `"`, `\` and `;`
    are stripped before `say`.
  - Settings: look speed, button size, opacity (live, `localStorage 'jka-touch'`), 30/60 fps
    (`'jka-fps'`, applied at once through `setMaxFps`), rename (`name`, `'jka-name'`).
  - Leave match: `disconnect`, then reload to the start screen.
- If anything opens one of the original menus on a phone, it is closed again within 250 ms.
- Text fields stop key events from bubbling to `window`, where SDL would swallow them.
- Bug found and fixed: the click that follows the tap on Menu landed on the freshly opened menu (on
  "Resume" with larger buttons) and closed it. The menu ignores clicks for 400 ms after opening.
- The server refuses team changes within 5 s of the last one and prints a message. A second tap after
  that works.
- Tested headless against a local container: all menu actions arrive on the server (`say:`,
  `ChangeTeam`, `ClientRename`, `ClientDisconnect`).

## P4 results (2026-11-06)

PWA, fullscreen and the rotate screen: see above. Phone lifecycle in `touch.js`:

- **Audio:** SDL resumes its AudioContext only on the first touch. The page now resumes it on every
  touch and when the page becomes visible again (Android suspends it after the screen was off).
- **Screen wake lock** while the page is visible, re-acquired after returning.
- **Background:** after 2 minutes hidden (`?bgms=` overrides it for tests), the client disconnects
  cleanly. On return, a screen says so and offers Reconnect (a reload, with the pk3 from the cache).
  The same screen ("Connection lost") appears whenever the connection drops, instead of the original
  main menu, which cannot be used by touch.
- **Persistent storage:** `navigator.storage.persist()` once the pk3 is loaded.
- **Unexpected fullscreen:** reported once from the phone: the overlay ended up in a corner and stopped
  working, then fullscreen ended by itself. The same symptom appears when the *canvas* instead of the
  page becomes the fullscreen element. The page now leaves such a fullscreen at once (the proper page
  fullscreen remains) and notes it in the F9 log (`[touch] fullscreen on unexpected element …`). The
  trigger is still unknown.
- Tested headless: audio resume, wake lock, canvas-fullscreen safeguard, background disconnect + screen.

## Rebased onto JA+ (2026-11-06)

- `repack.py` keeps master's multi-pk3 handling (`pk3s()` over the base dir plus `mod=<dir>`, skipping
  code pk3s and DLLs). The mobile profile runs on top of it. JA+'s `models/players/_humanoid/`
  (`_humanoid.gla`, `animation.cfg`, `animevents.cfg` from `base/japlus_gla_anims.pk3`) stays: emotes and
  the right animations depend on it. Only the SP level sets `_humanoid_<level>/` are dropped. Checked
  with a fake mod directory.
- `start.sh` builds the phone pk3 with the same `mod=` argument and its own `.mod` marker, so it rebuilds
  when `FS_GAME` changes (and when `repack.py` is newer).
- The shell's frame loop combines master's rAF stall fallback with the phone frame cap and gamepad
  polling.

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
