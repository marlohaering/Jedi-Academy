// Touch controls and gamepad for the browser MP client (web/MOBILE.md, phase P2).
//
// Talks to the engine through the exported C API in codemp/client/cl_input.cpp:
//   _web_move(x, y)  analog move (-1..1)     _web_look(dx, dy)  look delta (mouse path)
//   _web_key(k, d)   key event               web_cmd(text)      console command (via ccall)
//   _web_state()     -> int[12] player state (see WS below)
//
// Layout v1 (fixed): left part = floating move stick, right part = look-drag (also drags that start on
// a button), right-thumb cluster attack / alt / jump / crouch, Force (tap/hold = selected power, the
// chip above it opens the force radial), Weapon (tap = next, long press = weapon radial with saber
// styles), top left Use / Menu / Scores. Settings in localStorage 'jka-touch': {size, opacity, look}.
(function () {
  'use strict';
  const WS = { state: 0, catcher: 1, valid: 2, weapons: 3, weapon: 4, forceKnown: 5, forceSel: 6,
               team: 7, health: 8, pmType: 9, saberStyle: 10, forcePower: 11 };
  const CA_ACTIVE = 8, KEYCATCH_CONSOLE = 1, KEYCATCH_UI = 2, KEYCATCH_MESSAGE = 4, TEAM_SPECTATOR = 3;
  const K_ESCAPE = 27;

  // force powers by FP_* index: [label, command, hold?]
  const FORCE = {
    0: ['Heal', 'force_heal'], 2: ['Speed', 'force_speed'], 3: ['Push', 'force_throw'],
    4: ['Pull', 'force_pull'], 5: ['Mind trick', 'force_distract'], 6: ['Grip', 'force_grip', true],
    7: ['Lightning', 'force_lightning', true], 8: ['Rage', 'force_rage'], 9: ['Protect', 'force_protect'],
    10: ['Absorb', 'force_absorb'], 11: ['Team heal', 'force_healother'],
    12: ['Energize', 'force_forcepowerother'], 13: ['Drain', 'force_drain', true], 14: ['Sight', 'force_seeing'],
  };
  const FORCE_ORDER = [3, 4, 2, 6, 7, 13, 0, 9, 10, 8, 5, 14, 11, 12];
  // weapons by WP_* index: label; selected with "weapon N" (cgame numbering, see CG_Weapon_f)
  const WEAPONS = {
    3: 'Saber', 2: 'Melee', 4: 'Pistol', 5: 'Blaster', 6: 'Disruptor', 7: 'Bowcaster', 8: 'Repeater',
    9: 'DEMP 2', 10: 'Flechette', 11: 'Rocket', 12: 'Thermal', 13: 'Trip mine', 14: 'Det pack',
    15: 'Concussion', 16: 'Bryar',
  };
  const weaponCmd = wp => 'weapon ' + (wp <= 3 ? 1 : wp - 2);

  let M = null, settings = { size: 1, opacity: 0.5, look: 2.5 };
  try { Object.assign(settings, JSON.parse(localStorage.getItem('jka-touch') || '{}')); } catch (e) {}
  let st = new Int32Array(12);
  let forceSel = null;   // FP index chosen in the radial (JS side, independent of the engine's selection)

  const cmd = t => M.ccall('web_cmd', null, ['string'], [t]);
  const key = k => { M._web_key(k, 1); M._web_key(k, 0); };
  function readState() {
    const p = M._web_state() >> 2;
    st = M.HEAP32.slice(p, p + 12);
    return st;
  }
  const has = (mask, bit) => (mask >>> bit) & 1;

  function forcePower() {
    if (forceSel != null && has(st[WS.forceKnown], forceSel)) return forceSel;
    return FORCE_ORDER.find(fp => has(st[WS.forceKnown], fp));
  }
  // press / release of the Force button (or gamepad Y)
  let heldForce = null;
  function forceDown() {
    const fp = forcePower();
    if (fp == null) { cmd('+useforce'); heldForce = 'useforce'; return; }
    const [, c, hold] = FORCE[fp];
    if (hold) { cmd('+' + c); heldForce = c; } else cmd(c);
  }
  function forceUp() { if (heldForce) { cmd('-' + heldForce); heldForce = null; } }

  // ---------- DOM ----------
  const css = `
  #touch { position:fixed; inset:0; z-index:1; touch-action:none; user-select:none; -webkit-user-select:none;
    -webkit-touch-callout:none; display:none; --s:${settings.size}; --o:${settings.opacity}; }
  #touch.on { display:block; }
  #touch .b { position:absolute; border-radius:50%; display:flex; align-items:center; justify-content:center;
    width:calc(var(--d) * var(--s) * 1px); height:calc(var(--d) * var(--s) * 1px);
    background:rgba(20,30,50,calc(var(--o) * .9)); border:2px solid rgba(200,220,255,var(--o));
    color:rgba(235,242,255,calc(var(--o) + .3)); font:600 calc(12px * var(--s)) system-ui, sans-serif;
    text-transform:uppercase; letter-spacing:.04em; box-sizing:border-box; }
  #touch .b.down { background:rgba(74,163,255,calc(var(--o) + .2)); }
  #touch .b[data-btn=full] { font-size:calc(22px * var(--s)); }
  #touch.fs .b[data-btn=full] { display:none; }
  #touch .stick { position:absolute; border-radius:50%; pointer-events:none; display:none;
    border:2px solid rgba(200,220,255,var(--o)); box-sizing:border-box; }
  #touch .stick.base { width:calc(120px * var(--s)); height:calc(120px * var(--s)); margin:calc(-60px * var(--s)); }
  #touch .stick.knob { width:calc(54px * var(--s)); height:calc(54px * var(--s)); margin:calc(-27px * var(--s));
    background:rgba(200,220,255,calc(var(--o) * .7)); }
  #touch .chip { position:absolute; padding:4px 10px; border-radius:12px; font:600 calc(11px * var(--s)) system-ui;
    background:rgba(20,30,50,calc(var(--o) * .9)); border:1px solid rgba(200,220,255,var(--o));
    color:rgba(235,242,255,calc(var(--o) + .3)); white-space:nowrap; }
  #radial { position:fixed; inset:0; z-index:4; display:none; touch-action:none; background:rgba(0,0,0,.35); }
  #radial.on { display:block; }
  #radial .it { position:absolute; width:84px; height:84px; margin:-42px; border-radius:50%; display:flex;
    align-items:center; justify-content:center; text-align:center; font:600 12px system-ui; color:#eaf2ff;
    background:rgba(20,30,50,.85); border:2px solid rgba(200,220,255,.6); box-sizing:border-box; }
  #radial .it.cur { border-color:#ffe81f; }
  #radial .it.hot { background:rgba(74,163,255,.9); color:#000; }
  `;
  // [id, label, diameter, position (right/bottom/left/top in px, scaled by --s)]
  const BUTTONS = [
    ['attack', 'Attack', 92, { right: 26, bottom: 30 }],
    ['alt', 'Alt', 62, { right: 136, bottom: 18 }],
    ['jump', 'Jump', 66, { right: 40, bottom: 140 }],
    ['crouch', 'Crouch', 58, { right: 130, bottom: 96 }],
    ['force', 'Force', 62, { right: 126, bottom: 176 }],
    ['weapon', 'Weapon', 56, { right: 44, bottom: 230 }],
    ['use', 'Use', 54, { left: 16, top: 16 }],
    ['menu', 'Menu', 54, { left: 80, top: 16 }],
    ['scores', 'Scores', 54, { left: 144, top: 16 }],
    ['full', '⛶', 54, { left: 208, top: 16 }],
  ];
  // held buttons: console commands sent on press (+) and release (-)
  const HOLD = { attack: 'attack', alt: 'altattack', jump: 'moveup', crouch: 'movedown', use: 'use', scores: 'scores' };

  let root, base, knob, chip, radial;
  function build() {
    const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
    root = document.createElement('div'); root.id = 'touch';
    root.addEventListener('contextmenu', e => e.preventDefault());
    for (const [id, label, d, pos] of BUTTONS) {
      const b = document.createElement('div');
      b.className = 'b'; b.dataset.btn = id; b.textContent = label; b.style.setProperty('--d', d);
      for (const [k, v] of Object.entries(pos)) b.style[k] = `calc(${v}px * var(--s))`;
      root.appendChild(b);
    }
    chip = document.createElement('div'); chip.className = 'chip'; chip.dataset.btn = 'forcesel';
    chip.style.right = 'calc(118px * var(--s))'; chip.style.bottom = 'calc(246px * var(--s))';
    root.appendChild(chip);
    base = document.createElement('div'); base.className = 'stick base';
    knob = document.createElement('div'); knob.className = 'stick knob';
    root.append(base, knob);
    radial = document.createElement('div'); radial.id = 'radial';
    document.body.append(root, radial);
    root.addEventListener('pointerdown', onDown);
    root.addEventListener('pointermove', onMove);
    root.addEventListener('pointerup', onUp);
    root.addEventListener('pointercancel', onUp);
    radial.addEventListener('pointerdown', onRadialDown);
    radial.addEventListener('pointermove', onRadialMove);
    radial.addEventListener('pointerup', onRadialUp);
  }

  // ---------- pointers ----------
  const ptrs = new Map();   // pointerId -> { kind: 'stick'|'look'|'btn', btn, el, x, y, ox, oy, timer }
  let lookAccX = 0, lookAccY = 0;
  const STICK_R = () => 60 * settings.size;

  function look(dx, dy) {
    lookAccX += dx * settings.look; lookAccY += dy * settings.look;
    const ix = Math.trunc(lookAccX), iy = Math.trunc(lookAccY);
    if (ix || iy) { M._web_look(ix, iy); lookAccX -= ix; lookAccY -= iy; }
  }
  function onDown(e) {
    // touch pointers are implicitly captured already; this only matters for mouse/pen and may throw
    try { root.setPointerCapture(e.pointerId); } catch (err) {}
    const el = e.target.closest('[data-btn]');
    const p = { x: e.clientX, y: e.clientY, ox: e.clientX, oy: e.clientY };
    ptrs.set(e.pointerId, p);
    if (el) {
      p.kind = 'btn'; p.btn = el.dataset.btn; p.el = el; el.classList.add('down');
      press(p);
    } else if (e.clientX < innerWidth * 0.45) {
      if ([...ptrs.values()].some(q => q.kind === 'stick')) { p.kind = 'look'; return; }
      p.kind = 'stick';
      base.style.left = knob.style.left = e.clientX + 'px';
      base.style.top = knob.style.top = e.clientY + 'px';
      base.style.display = knob.style.display = 'block';
    } else p.kind = 'look';
  }
  function onMove(e) {
    const p = ptrs.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    p.x = e.clientX; p.y = e.clientY;
    if (p.kind === 'stick') {
      let vx = e.clientX - p.ox, vy = e.clientY - p.oy;
      const r = STICK_R(), len = Math.hypot(vx, vy);
      if (len > r) { vx *= r / len; vy *= r / len; }
      knob.style.left = (p.ox + vx) + 'px'; knob.style.top = (p.oy + vy) + 'px';
      M._web_move(vx / r, -vy / r);
    } else if (p.kind === 'look' || (p.kind === 'btn' && p.btn !== 'weapon' && p.btn !== 'forcesel')) {
      look(dx, dy);
    } else if (p.kind === 'btn' && p.btn === 'weapon' && Math.hypot(p.x - p.ox, p.y - p.oy) > 12) {
      look(dx, dy);
    }
  }
  function onUp(e) {
    const p = ptrs.get(e.pointerId);
    if (!p) return;
    ptrs.delete(e.pointerId);
    if (p.kind === 'stick') {
      M._web_move(0, 0);
      base.style.display = knob.style.display = 'none';
    } else if (p.kind === 'btn') {
      p.el.classList.remove('down');
      release(p);
    }
  }

  function press(p) {
    const b = p.btn;
    if (HOLD[b]) cmd('+' + HOLD[b]);
    else if (b === 'force') forceDown();
    else if (b === 'menu') key(K_ESCAPE);
    else if (b === 'forcesel') openForceRadial(p);
    else if (b === 'weapon') p.timer = setTimeout(() => { p.timer = null; p.radial = true; openWeaponRadial(p); }, 400);
  }
  function release(p) {
    const b = p.btn;
    if (b === 'full') fullscreen();   // on release: a touch's pointerup carries the user activation
    else if (HOLD[b]) cmd('-' + HOLD[b]);
    else if (b === 'force') forceUp();
    else if (b === 'weapon' && p.timer) { clearTimeout(p.timer); cmd('weapnext'); }
  }

  // ---------- radial selectors ----------
  let items = [], hot = null, radialPtr = null;
  function openRadial(list, origin) {
    radial.textContent = '';
    const cx = innerWidth / 2, cy = innerHeight / 2, r = Math.min(130, innerHeight / 2 - 50);
    items = list.map((it, i) => {
      const a = -Math.PI / 2 + i * 2 * Math.PI / list.length;
      const el = document.createElement('div');
      el.className = 'it' + (it.cur ? ' cur' : ''); el.textContent = it.label;
      el.style.left = (cx + r * Math.cos(a)) + 'px'; el.style.top = (cy + r * Math.sin(a)) + 'px';
      radial.appendChild(el);
      return { ...it, el };
    });
    radial.classList.add('on');
    // the finger that opened the radial can pick by sliding onto an item and releasing
    if (origin) {
      radialPtr = origin.pointerId;
      ptrs.delete(origin.pointerId);
      origin.el.classList.remove('down');
    }
  }
  function closeRadial() { radial.classList.remove('on'); items = []; hot = null; radialPtr = null; }
  function itemAt(x, y) {
    const el = document.elementFromPoint(x, y);
    return items.find(it => it.el === el);
  }
  function setHot(it) { if (hot) hot.el.classList.remove('hot'); hot = it || null; if (hot) hot.el.classList.add('hot'); }
  function onRadialDown(e) { setHot(items.find(it => it.el === e.target) || itemAt(e.clientX, e.clientY)); }
  function onRadialMove(e) { if (e.buttons || e.pointerType === 'touch') setHot(itemAt(e.clientX, e.clientY)); }
  function onRadialUp(e) {
    const it = itemAt(e.clientX, e.clientY) || hot;   // the highlighted item (finger may end slightly off)
    if (it) { it.pick(); closeRadial(); }
    else if (e.pointerId !== radialPtr) closeRadial();   // tap outside closes; the opening finger may lift anywhere
    else { radialPtr = null; setHot(null); }
  }
  // releases of the opening finger are delivered to #touch (pointer capture); forward them
  function forwardToRadial(e) {
    if (radial.classList.contains('on') && e.pointerId === radialPtr) {
      if (e.type === 'pointermove') setHot(itemAt(e.clientX, e.clientY));
      else onRadialUp(e);
    }
  }

  function openForceRadial(p) {
    readState();
    const cur = forcePower();
    const list = FORCE_ORDER.filter(fp => has(st[WS.forceKnown], fp)).map(fp => ({
      label: FORCE[fp][0], cur: fp === cur, pick: () => { forceSel = fp; updateChip(); },
    }));
    if (list.length) openRadial(list, { pointerId: p ? [...ptrs.entries()].find(([, q]) => q === p)?.[0] : null, el: chip });
  }
  function openWeaponRadial(p) {
    readState();
    const list = Object.keys(WEAPONS).map(Number).filter(wp => has(st[WS.weapons], wp) && !(wp === 2 && has(st[WS.weapons], 3)))
      .sort((a, b) => a - b)
      .map(wp => ({ label: WEAPONS[wp], cur: wp === st[WS.weapon], pick: () => cmd(weaponCmd(wp)) }));
    if (st[WS.weapon] === 3) list.push({ label: 'Saber style', pick: () => cmd('saberAttackCycle') });
    const id = [...ptrs.entries()].find(([, q]) => q === p)?.[0];
    if (list.length) openRadial(list, { pointerId: id, el: p.el });
  }

  function updateChip() {
    const fp = forcePower();
    chip.textContent = fp == null ? 'Force ▾' : FORCE[fp][0] + ' ▾';
  }

  // ---------- gamepad (standard mapping) ----------
  const PAD_HOLD = { 0: 'moveup', 1: 'movedown', 2: 'use', 6: 'altattack', 7: 'attack', 8: 'scores' };
  let padPrev = [], padLast = 0;
  function pollPad(now) {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    const pad = [...pads].find(g => g && g.connected);
    if (!pad) return;
    const dt = Math.min(0.1, (now - (padLast || now)) / 1000); padLast = now;
    const dz = v => Math.abs(v) < 0.15 ? 0 : (v - Math.sign(v) * 0.15) / 0.85;
    const lx = dz(pad.axes[0] || 0), ly = dz(pad.axes[1] || 0);
    M._web_move(lx, -ly);
    const rx = dz(pad.axes[2] || 0), ry = dz(pad.axes[3] || 0);
    if (rx || ry) look(rx * Math.abs(rx) * 700 * dt, ry * Math.abs(ry) * 500 * dt);
    pad.buttons.forEach((b, i) => {
      const down = b.pressed, was = padPrev[i];
      if (down === !!was) return;
      padPrev[i] = down;
      if (PAD_HOLD[i]) cmd((down ? '+' : '-') + PAD_HOLD[i]);
      else if (i === 3) down ? forceDown() : forceUp();
      else if (!down) return;
      else if (i === 4 || i === 14 || i === 15) cycleForce(i === 14 ? -1 : 1);
      else if (i === 5) cmd('weapnext');
      else if (i === 13) cmd('weapprev');
      else if (i === 12) cmd('saberAttackCycle');
      else if (i === 9) key(K_ESCAPE);
    });
    if (pad.buttons.some(b => b.pressed)) root.classList.remove('on'), padActive = true;
  }
  let padActive = false;
  function cycleForce(dir) {
    readState();
    const known = FORCE_ORDER.filter(fp => has(st[WS.forceKnown], fp));
    if (!known.length) return;
    const i = known.indexOf(forcePower());
    forceSel = known[(i + dir + known.length) % known.length];
    updateChip();
  }

  // ---------- show / hide, auto-join ----------
  let joined = false, touchMode = false;
  function tick() {
    if (!M || !M._web_state) return;
    readState();
    const active = st[WS.state] === CA_ACTIVE && st[WS.valid];
    // phones cannot use the original menus: join the game automatically once (P3 adds an HTML menu)
    if (touchMode && active && !joined) {
      joined = true;
      if (st[WS.team] === TEAM_SPECTATOR) cmd('team free');
      if (st[WS.catcher] & KEYCATCH_UI) key(K_ESCAPE);
    }
    const blocked = st[WS.catcher] & (KEYCATCH_CONSOLE | KEYCATCH_UI | KEYCATCH_MESSAGE);
    const show = touchMode && active && !blocked && !padActive;
    root.classList.toggle('on', show);
    if (!show && ptrs.size) { for (const id of [...ptrs.keys()]) onUp({ pointerId: id }); }
    if (show) updateChip();
  }

  // Fullscreen on the whole document (the overlay must stay visible), then lock landscape.
  // Not needed when running as an installed app (display: fullscreen).
  const isFullscreen = () => !!document.fullscreenElement || matchMedia('(display-mode: fullscreen)').matches;
  function fullscreen() {
    const el = document.documentElement;
    if (isFullscreen() || !el.requestFullscreen) return;
    el.requestFullscreen({ navigationUI: 'hide' })
      .then(() => screen.orientation && screen.orientation.lock && screen.orientation.lock('landscape'))
      .catch(() => {});
  }
  function onFullscreenChange() { if (root) root.classList.toggle('fs', isFullscreen()); }
  document.addEventListener('fullscreenchange', onFullscreenChange);

  window.WebInput = {
    fullscreen,
    // touch: show the touch overlay (phones); the gamepad works in both modes
    init(module, touch) {
      M = module; touchMode = touch;
      build();
      root.addEventListener('pointermove', forwardToRadial);
      root.addEventListener('pointerup', forwardToRadial);
      addEventListener('pointerdown', () => { if (padActive && touchMode) padActive = false; }, true);
      setInterval(tick, 250);
      onFullscreenChange();
    },
    frame(now) { if (M && M._web_move) pollPad(now); },
    // when the menu is open the overlay is hidden; P3 replaces the original menus
    settings,
  };
})();
