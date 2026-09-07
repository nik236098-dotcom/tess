'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { play, normalize, chanceOf, multiplierFor, NvutiError } = require('../server/nvuti/game');

test('шанс и множитель: 97 % от честного, вниз до сотых', () => {
  assert.strictEqual(chanceOf(75, 'under'), 75);
  assert.strictEqual(chanceOf(75, 'over'), 25);
  assert.strictEqual(multiplierFor(75), 1.29); // 97/75 = 1.293
  assert.strictEqual(multiplierFor(25), 3.88);
  assert.strictEqual(multiplierFor(50), 1.94);
  assert.strictEqual(multiplierFor(5), 19.4);
});

test('число только от 5 до 95, режим только under/over', () => {
  assert.throws(() => normalize(4, 'under'), NvutiError);
  assert.throws(() => normalize(96, 'over'), NvutiError);
  assert.throws(() => normalize(50, 'both'), NvutiError);
  assert.deepStrictEqual(normalize('50', 'over'), { target: 50, mode: 'over' });
});

test('«меньше 75»: бросок 75 выигрывает, 76 — нет', () => {
  const win = play({ bet: 1000, target: 75, mode: 'under', roll: 75 });
  assert.strictEqual(win.won, true);
  assert.strictEqual(win.payout, 1290);
  assert.strictEqual(win.net, 290);
  const lose = play({ bet: 1000, target: 75, mode: 'under', roll: 76 });
  assert.strictEqual(lose.won, false);
  assert.strictEqual(lose.payout, 0);
  assert.strictEqual(lose.net, -1000);
});

test('«больше 75»: бросок 76 выигрывает, 75 — нет', () => {
  const win = play({ bet: 1000, target: 75, mode: 'over', roll: 76 });
  assert.strictEqual(win.won, true);
  assert.strictEqual(win.multiplier, 3.88);
  assert.strictEqual(win.payout, 3880);
  assert.strictEqual(play({ bet: 1000, target: 75, mode: 'over', roll: 75 }).won, false);
});

test('случайный бросок всегда в пределах 1–100', () => {
  for (let i = 0; i < 500; i += 1) {
    const { roll } = play({ bet: 100, target: 50, mode: 'under' });
    assert.ok(Number.isInteger(roll) && roll >= 1 && roll <= 100);
  }
});
