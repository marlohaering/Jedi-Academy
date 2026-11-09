const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function setup(touch = false) {
  const elements = new Map(), listeners = {}, documentListeners = {}, events = [], intervals = [];
  class Element {
    constructor() {
      this.children = []; this.dataset = {}; this.style = { setProperty() {} }; this.listeners = {};
      const classes = new Set();
      this.classList = { add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x),
        toggle: (x, on) => on ? classes.add(x) : classes.delete(x) };
    }
    set id(value) { this._id = value; elements.set(value, this); }
    get id() { return this._id; }
    append(...items) { this.children.push(...items); }
    appendChild(item) { this.append(item); }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    querySelector(name) { this.queries ||= {}; return this.queries[name] ||= new Element(); }
    querySelectorAll() { return []; }
    closest() { return this.dataset.btn ? this : null; }
    setPointerCapture() {}
  }
  const document = { head: new Element(), body: new Element(), hidden: false,
    createElement: () => new Element(), addEventListener: (name, fn) => (documentListeners[name] ||= []).push(fn), getElementById: id => elements.get(id) };
  const state = new Int32Array(13); state[0] = 8; state[2] = 1;
  let pads = [];
  const context = { document, navigator: { getGamepads: () => pads }, localStorage: { getItem() {} },
    console, URLSearchParams, location: { search: '' }, performance: { now: () => 1000 },
    setInterval: fn => intervals.push(fn), setTimeout() {}, clearTimeout() {}, matchMedia: () => ({ matches: false }),
    innerWidth: 915, innerHeight: 412, addEventListener: (name, fn) => (listeners[name] ||= []).push(fn) };
  context.window = context;
  vm.createContext(context);
  for (const file of ['input-state.js', 'touch.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, '../shell-mp', file), 'utf8'), context);
  context.WebInput.init({ HEAP32: state, _web_state: () => 0, _web_move: (x, y) => events.push([x, y]),
    ccall: (name, _type, _types, args) => events.push(args[0]), _web_key: (key, down) => events.push(['key', key, down]) }, touch);
  const pad = { id: 'test', index: 0, mapping: 'standard', connected: true, axes: [0, -1, 0, 0],
    buttons: Array.from({ length: 16 }, (_, i) => ({ pressed: i === 7 })) };
  return { events, pad, frame: () => context.WebInput.frame(1000), setPads: p => pads = p,
    tick: () => intervals.forEach(fn => fn()), menu: elements.get('pmenu'),
    hidden: value => { document.hidden = value; (documentListeners.visibilitychange || []).forEach(fn => fn()); },
    emit: name => (listeners[name] || []).forEach(fn => fn()), root: elements.get('touch'), Element, state };
}
test('real gamepad polling neutralizes held input after unplug', () => {
  const t = setup(); t.setPads([t.pad]); t.frame(); t.setPads([]); t.frame();
  assert.deepEqual(t.events, [[0, 1], '+attack', '-attack', [0, 0]]);
});
test('touch and gamepad share attack ownership through the actual adapters', () => {
  const t = setup(), button = new t.Element(); button.dataset.btn = 'attack';
  t.setPads([t.pad]); t.frame();
  t.root.listeners.pointerdown[0]({ pointerId: 1, target: button, clientX: 800, clientY: 350 });
  t.setPads([]); t.frame();
  assert.equal(t.events.includes('-attack'), false);
  t.root.listeners.pointerup[0]({ pointerId: 1 });
  assert.equal(t.events.at(-1), '-attack');
});
test('blur releases gamepad and polling cannot reacquire until focus', () => {
  const t = setup(); t.setPads([t.pad]); t.frame(); t.emit('blur'); t.frame();
  assert.equal(t.events.filter(e => e === '+attack').length, 1);
  assert.ok(t.events.includes('-attack'));
  t.emit('focus'); t.frame();
  assert.equal(t.events.filter(e => e === '+attack').length, 2);
});

test('Start opens and closes phone menu on separate presses, never while held', () => {
  const t = setup(true); t.pad.buttons[7].pressed = false; t.pad.buttons[9].pressed = true;
  t.setPads([t.pad]); t.frame(); assert.equal(t.menu.classList.contains('on'), true);
  t.frame(); assert.equal(t.menu.classList.contains('on'), true);
  t.pad.buttons[9].pressed = false; t.frame();
  t.pad.buttons[9].pressed = true; t.frame(); assert.equal(t.menu.classList.contains('on'), false);
});
test('Start sends Escape even when the desktop game menu catches input', () => {
  const t = setup(); t.pad.buttons[7].pressed = false; t.pad.buttons[9].pressed = true;
  t.setPads([t.pad]); t.frame(); t.state[1] = 2;
  t.pad.buttons[9].pressed = false; t.frame(); t.pad.buttons[9].pressed = true; t.frame();
  assert.equal(t.events.filter(e => Array.isArray(e) && e[0] === 'key' && e[2] === 1).length, 2);
});
test('hiding the touch overlay does not interrupt a gamepad hold', () => {
  const t = setup(true), button = new t.Element(); button.dataset.btn = 'attack';
  t.root.listeners.pointerdown[0]({ pointerId: 1, target: button, clientX: 800, clientY: 350 });
  t.setPads([t.pad]); t.frame(); t.tick(); t.frame();
  assert.equal(t.events.filter(e => e === '+attack').length, 1);
  assert.equal(t.events.includes('-attack'), false);
});
test('pause keeps gamepad mode and the touch overlay hidden after resume', () => {
  const t = setup(true); t.setPads([t.pad]); t.frame();
  t.state[1] = 4; t.frame(); t.pad.buttons[7].pressed = false; t.state[1] = 0; t.frame(); t.tick();
  assert.equal(t.root.classList.contains('on'), false);
});
test('visibility change releases all sources immediately and prevents reacquisition while hidden', () => {
  const t = setup(); t.setPads([t.pad]); t.frame(); t.hidden(true);
  assert.ok(t.events.includes('-attack')); assert.deepEqual(t.events.at(-1), [0, 0]);
  t.frame(); assert.equal(t.events.filter(e => e === '+attack').length, 1);
  t.hidden(false); t.frame(); assert.equal(t.events.filter(e => e === '+attack').length, 2);
});
test('switching pads releases the previous pad actions', () => {
  const t = setup(); t.setPads([t.pad]); t.frame();
  t.setPads([{ ...t.pad, id: 'other', index: 1, axes: [], buttons: [] }]); t.frame();
  assert.ok(t.events.includes('-attack')); assert.deepEqual(t.events.at(-1), [0, 0]);
});
test('Force keeps its last owner across touch and pad release', () => {
  const t = setup(), button = new t.Element(); button.dataset.btn = 'force';
  t.pad.buttons[7].pressed = false; t.pad.buttons[3].pressed = true;
  t.root.listeners.pointerdown[0]({ pointerId: 1, target: button, clientX: 800, clientY: 350 });
  t.setPads([t.pad]); t.frame(); t.root.listeners.pointerup[0]({ pointerId: 1 });
  assert.equal(t.events.includes('-useforce'), false);
  t.setPads([]); t.frame(); assert.ok(t.events.includes('-useforce'));
});
