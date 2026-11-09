// Held commands and analog movement shared by the touch and gamepad adapters.
// A source can be a pointer object or a gamepad token. Only the last owner releases
// a command. The most recently engaged stick wins until neutral; jitter cannot steal it.
window.createInputState = function (command, movement) {
  'use strict';
  const holds = new Map(), moves = new Map();
  let mx = 0, my = 0;
  function updateMovement() {
    const values = [...moves.values()];
    const [x, y] = values.length ? values[values.length - 1] : [0, 0];
    if (x !== mx || y !== my) { mx = x; my = y; movement(x, y); }
  }
  function hold(source, action, down) {
    let owners = holds.get(action);
    if (down) {
      if (!owners) { owners = new Set(); holds.set(action, owners); }
      if (owners.has(source)) return;
      owners.add(source);
      if (owners.size === 1) command('+' + action);
    } else if (owners && owners.delete(source) && !owners.size) {
      holds.delete(action);
      command('-' + action);
    }
  }
  return {
    hold,
    move(source, x, y) {
      const prev = moves.get(source);
      if (prev && prev[0] === x && prev[1] === y) return;
      if (x || y) moves.set(source, [x, y]);
      else moves.delete(source);
      updateMovement();
    },
    release(source) {
      for (const action of holds.keys()) hold(source, action, false);
      moves.delete(source);
      updateMovement();
    },
  };
};
