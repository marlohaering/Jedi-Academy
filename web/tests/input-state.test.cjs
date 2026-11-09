const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function setup() {
  const events = [];
  const context = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../shell-mp/input-state.js'), 'utf8'), context);
  const input = context.window.createInputState(t => events.push(t), (x, y) => events.push([x, y]));
  return { input, events };
}
test('a held command is released only after its last owner releases', () => {
  const { input, events } = setup();
  input.hold('touch', 'attack', true);
  input.hold('pad', 'attack', true);
  input.hold('touch', 'attack', false);
  assert.deepEqual(events, ['+attack']);
  input.release('pad');
  assert.deepEqual(events, ['+attack', '-attack']);
});
test('disconnect releases commands and movement, once', () => {
  const { input, events } = setup();
  input.hold('pad', 'attack', true);
  input.move('pad', 0, 1);
  input.release('pad');
  input.release('pad');
  assert.deepEqual(events, ['+attack', [0, 1], '-attack', [0, 0]]);
});
test('idle or unchanged gamepad samples cannot overwrite a live touch stick', () => {
  const { input, events } = setup();
  input.move('pad', 1, 0);
  input.move('touch', 0, 1);
  input.move('pad', 1, 0);
  input.move('pad', 0, 0);
  assert.deepEqual(events, [[1, 0], [0, 1]]);
  input.release('touch');
  assert.deepEqual(events.at(-1), [0, 0]);
});
test('releasing the current movement owner restores another active source', () => {
  const { input, events } = setup();
  input.move('pad', 1, 0);
  input.move('touch', 0, 1);
  input.release('touch');
  assert.deepEqual(events.at(-1), [1, 0]);
});
test('an already engaged stick cannot steal ownership through analog jitter', () => {
  const { input, events } = setup();
  input.move('pad', 1, 0);
  input.move('touch', 0, 1);
  input.move('pad', 0.99, 0);
  assert.deepEqual(events, [[1, 0], [0, 1]]);
  input.release('touch');
  assert.deepEqual(events.at(-1), [0.99, 0]);
});
