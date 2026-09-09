'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { HiloGame, HiloError } = require('../server/hilo/game');
const make = (...ranks) => new HiloGame({ rng: () => ({ rank: ranks.shift() || 8, suit: 's' }) });
test('every rank: inclusive high/low odds agree with all 13 outcomes', () => {
  for (let rank = 1; rank <= 13; rank++) {
    for (const direction of ['high', 'low']) {
      let wins = 0;
      for (let next = 1; next <= 13; next++) {
        const g = make(rank, next); g.start(100, 0);
        if (g.odds(direction) === 1) { assert.throws(() => g.pick(direction, 1), HiloError); continue; }
        const p = g.odds(direction); g.pick(direction, 1);
        if (g.phase === 'play') { wins++; assert.ok(g.multiplier * p <= .97 + 1e-10); }
      }
      const g = make(rank);
      if (g.odds(direction) < 1) assert.equal(wins / 13, g.odds(direction));
    }
  }
});
test('stale requests, invalid bets, second start and duplicate cashout cannot mutate a round', () => {
  const g = make(8, 8);
  for (const amount of [NaN, Infinity, -1, 0, 9, 10.5, '100', 10000001]) assert.throws(() => g.start(amount, 0), HiloError);
  g.start(100, 0);
  assert.throws(() => g.start(100, 1), HiloError);
  assert.throws(() => g.pick('high', 0), HiloError);
  assert.throws(() => g.pick('bad', 1), HiloError);
  g.pick('high', 1); g.cashout(g.revision);
  assert.equal(g.payout, 210);
  assert.throws(() => g.cashout(g.revision), HiloError);
});
test('skip preserves bet and multiplier; loss pays zero; a new round resets history', () => {
  const g = make(8, 9, 7, 13);
  g.start(100, 0); g.skip(1); assert.equal(g.multiplier, 1); assert.equal(g.bet, 100);
  g.pick('high', 2); assert.equal(g.phase, 'done'); assert.equal(g.payout, 0);
  assert.throws(() => g.pick('low', g.revision), HiloError);
  g.start(200, g.revision); assert.equal(g.history.length, 1); assert.equal(g.multiplier, 1);
});
test('untouched stake can be returned and maximum multiplier settles automatically', () => {
  const g = make(8); g.start(100, 0); g.cashout(1); assert.equal(g.payout, 100);
  const cap = make(1); cap.start(100, 0); cap.rng = () => ({ rank: 1, suit: 's' });
  while (cap.phase === 'play') cap.pick('low', cap.revision);
  assert.equal(cap.multiplier, 10000); assert.equal(cap.payout, 1000000);
});
test('saved round restores its visible card, revision and earned payout', () => {
  const g = make(8, 8); g.start(100, 0); g.pick('high', 1);
  const recovered = make(2); recovered.restore(JSON.parse(JSON.stringify(g.snapshot())));
  assert.deepEqual(recovered.state(), g.state());
  recovered.cashout(recovered.revision); assert.equal(recovered.payout, 210);
});
