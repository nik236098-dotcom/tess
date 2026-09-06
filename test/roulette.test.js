'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { WHEEL_ORDER, colourOf, normalizeBets, settle, spin, RouletteError } = require('../server/roulette/wheel');

const limits = { minBet: 100, maxBet: 1000000, maxTotal: 10000 };

test('колесо: 37 карманов, каждое число один раз', () => {
  assert.strictEqual(WHEEL_ORDER.length, 37);
  assert.deepStrictEqual([...WHEEL_ORDER].sort((a, b) => a - b), Array.from({ length: 37 }, (_, i) => i));
});

test('цвета: зеро зелёное, 1 красное, 2 чёрное, 10 чёрное, 19 красное', () => {
  assert.strictEqual(colourOf(0), 'green');
  assert.strictEqual(colourOf(1), 'red');
  assert.strictEqual(colourOf(2), 'black');
  assert.strictEqual(colourOf(10), 'black');
  assert.strictEqual(colourOf(19), 'red');
});

test('число платит 35:1, ставка возвращается', () => {
  const { bets } = normalizeBets([{ type: 'straight', value: 17, amount: 100 }], limits);
  const r = settle(bets, 17);
  assert.strictEqual(r.payout, 3600);
  assert.strictEqual(r.net, 3500);
  assert.strictEqual(settle(bets, 18).payout, 0);
});

test('колонки и дюжины 2:1', () => {
  const { bets } = normalizeBets([
    { type: 'column', value: 2, amount: 100 }, // 2,5,8,...,35
    { type: 'dozen', value: 3, amount: 100 },  // 25..36
  ], limits);
  const r = settle(bets, 35);
  assert.deepStrictEqual(r.bets.map((b) => b.won), [true, true]);
  assert.strictEqual(r.payout, 600);
  assert.strictEqual(settle(bets, 0).payout, 0, 'зеро не входит ни в колонку, ни в дюжину');
});

test('равные шансы 1:1 и зеро против всех', () => {
  const { bets } = normalizeBets([
    { type: 'red', amount: 100 }, { type: 'black', amount: 100 },
    { type: 'even', amount: 100 }, { type: 'odd', amount: 100 },
    { type: 'low', amount: 100 }, { type: 'high', amount: 100 },
  ], limits);
  const r = settle(bets, 19); // красное, нечётное, high
  assert.deepStrictEqual(r.bets.map((b) => b.won), [true, false, false, true, false, true]);
  assert.strictEqual(r.payout, 600);
  assert.strictEqual(r.net, 0);
  assert.strictEqual(settle(bets, 0).payout, 0, 'на зеро проигрывают все равные шансы');
});

test('ставки проверяются: тип, значение, минимум, общий лимит', () => {
  assert.throws(() => normalizeBets([], limits), RouletteError);
  assert.throws(() => normalizeBets([{ type: 'split', amount: 100 }], limits), /Неизвестный тип/);
  assert.throws(() => normalizeBets([{ type: 'straight', value: 37, amount: 100 }], limits), /Некорректная/);
  assert.throws(() => normalizeBets([{ type: 'red', amount: 50 }], limits), /Минимальная/);
  assert.throws(() => normalizeBets([{ type: 'red', amount: 6000 }, { type: 'black', amount: 6000 }], limits), /Недостаточно средств/);
  const { total } = normalizeBets([{ type: 'red', amount: 300 }, { type: 'straight', value: 0, amount: 200 }], limits);
  assert.strictEqual(total, 500);
});

test('розыгрыш даёт число 0..36', () => {
  const { bets } = normalizeBets([{ type: 'red', amount: 100 }], limits);
  for (const v of [0, 0.5, 0.999999]) {
    const r = spin(bets, () => v);
    assert.ok(r.number >= 0 && r.number <= 36);
  }
  assert.strictEqual(spin(bets, () => 0).number, 0);
  assert.strictEqual(spin(bets, () => 0.999999).number, 36);
});
