'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { MinesGame, MinesError, multiplier, layoutMines, SIZE } = require('../server/mines/game');

// Детерминированный генератор: мины ложатся в первые `n` клеток после
// перемешивания, а перемешивание с rng=0 оставляет порядок 0..24 с конца.
const zero = () => 0;
const minesOf = (game) => Array.from(game.layout).sort((a, b) => a - b);

test('множитель: 97 % от честного, вниз до сотых', () => {
  assert.strictEqual(multiplier(3, 0), 1);
  assert.strictEqual(multiplier(3, 1), 1.1); // 25/22 · 0.97 = 1.102
  assert.strictEqual(multiplier(3, 3), 1.44); // 25·24·23 / (22·21·20) · 0.97 = 1.449
  assert.strictEqual(multiplier(24, 1), 24.25); // единственная безопасная клетка
  assert.ok(multiplier(1, 24) > 20, 'все клетки при одной мине');
});

test('раскладка: ровно столько мин, сколько просили, все в поле', () => {
  for (const n of [1, 3, 10, 24]) {
    const layout = layoutMines(n, Math.random);
    assert.strictEqual(layout.size, n);
    for (const cell of layout) assert.ok(cell >= 0 && cell < SIZE);
  }
});

test('старт: проверка ставки и числа мин', () => {
  const game = new MinesGame({ minBet: 10, maxBet: 1000 });
  assert.throws(() => game.start(5, 3), MinesError);
  assert.throws(() => game.start(2000, 3), MinesError);
  assert.throws(() => game.start(100, 0), MinesError);
  assert.throws(() => game.start(100, 25), MinesError);
  game.start(100, 3, zero);
  assert.strictEqual(game.phase, 'play');
  assert.throws(() => game.start(100, 3), MinesError, 'второй раунд поверх идущего');
});

test('мина заканчивает раунд без выплаты и раскрывает поле', () => {
  const game = new MinesGame();
  game.start(100, 3, zero);
  const [mine] = minesOf(game);
  game.open(mine);
  const s = game.state();
  assert.strictEqual(s.phase, 'done');
  assert.strictEqual(s.result, 'lose');
  assert.strictEqual(s.payout, 0);
  assert.strictEqual(s.net, -100);
  assert.strictEqual(s.boom, mine);
  assert.strictEqual(s.field.filter((c) => c === 'mine').length, 3);
  assert.throws(() => game.open(0), MinesError);
});

test('забрать можно только после первой безопасной клетки', () => {
  const game = new MinesGame();
  game.start(1000, 3, zero);
  assert.throws(() => game.cashout(), MinesError);
  const mines = new Set(game.layout);
  const safe = Array.from({ length: SIZE }, (_, i) => i).filter((i) => !mines.has(i));
  game.open(safe[0]);
  assert.throws(() => game.open(safe[0]), MinesError, 'повторное открытие');
  assert.strictEqual(game.state().multiplier, 1.1);
  assert.strictEqual(game.state().next, 1.25);
  game.open(safe[1]);
  game.open(safe[2]);
  game.cashout();
  const s = game.state();
  assert.strictEqual(s.result, 'win');
  assert.strictEqual(s.payout, 1440);
  assert.strictEqual(s.net, 440);
  assert.strictEqual(s.field.length, SIZE);
  assert.strictEqual(s.next, null);
});

test('все безопасные клетки открыты — выплата сразу', () => {
  const game = new MinesGame();
  game.start(100, 24, zero);
  const mines = new Set(game.layout);
  const safe = Array.from({ length: SIZE }, (_, i) => i).find((i) => !mines.has(i));
  game.open(safe);
  assert.strictEqual(game.phase, 'done');
  assert.strictEqual(game.result, 'win');
  assert.strictEqual(game.payout, 2425);
});

test('состояние до конца раунда не выдаёт мины', () => {
  const game = new MinesGame();
  game.start(100, 5, Math.random);
  const s = game.state();
  assert.strictEqual(s.field, null);
  assert.strictEqual(s.boom, null);
  assert.deepStrictEqual(s.opened, []);
});
