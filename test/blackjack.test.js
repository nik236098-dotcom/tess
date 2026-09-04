'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { stringToCard, freshDeck } = require('../server/poker/cards');
const { BlackjackDuel, BlackjackError, handValue } = require('../server/blackjack/round');

// Карты идут по кругу: первому, второму, первому, второму, дальше добор по порядку.
function stackDeck(firstCards, secondCards, rest = []) {
  const order = [
    firstCards[0], secondCards[0], firstCards[1], secondCards[1], ...rest,
  ].map(stringToCard);
  const used = new Set(order);
  return [...order, ...freshDeck().filter((card) => !used.has(card))];
}

function duel(firstCards, secondCards, rest = [], options = {}) {
  return new BlackjackDuel({
    firstId: 'a',
    secondId: 'b',
    bet: 100,
    firstStack: 1000,
    secondStack: 1000,
    deck: stackDeck(firstCards, secondCards, rest),
    ...options,
  });
}

test('туз считается то за 11, то за 1', () => {
  const value = (line) => handValue(line.split(' ').map(stringToCard));
  assert.deepStrictEqual(value('Ah 9c'), { total: 20, soft: true, busted: false });
  assert.deepStrictEqual(value('Ah 9c 5d'), { total: 15, soft: false, busted: false });
  assert.deepStrictEqual(value('Ah Ac 9d'), { total: 21, soft: true, busted: false });
  assert.deepStrictEqual(value('Kh Qc 5d'), { total: 25, soft: false, busted: true });
});

test('карты обоих открыты сразу — прятать нечего', () => {
  const game = duel(['Kh', '7c'], ['9d', '6s']);
  assert.strictEqual(game.cardsOf('a').length, 2);
  assert.strictEqual(game.cardsOf('b').length, 2);
  assert.strictEqual(game.valueOf('a').total, 17);
  assert.strictEqual(game.valueOf('b').total, 15);
});

test('первым ходит тот, кто назначал ставку', () => {
  const game = duel(['Kh', '7c'], ['9d', '6s']);
  assert.strictEqual(game.actingId, 'a');
  assert.throws(() => game.act('b', 'hit'), /не ваш ход/);
  game.act('a', 'stand');
  assert.strictEqual(game.actingId, 'b');
});

test('кто ближе к 21, тот и забирает', () => {
  const game = duel(['Kh', '9c'], ['9d', '8s']);
  game.act('a', 'stand');
  game.act('b', 'stand');
  assert.strictEqual(game.result.winnerId, 'a');
  assert.strictEqual(game.result.amount, 100);
  assert.strictEqual(game.stackOf('a'), 1100);
  assert.strictEqual(game.stackOf('b'), 900);
});

test('равные суммы — ничья, фишки не двигаются', () => {
  const game = duel(['Kh', '9c'], ['9d', 'Ts']);
  game.act('a', 'stand');
  game.act('b', 'stand');
  assert.strictEqual(game.result.winnerId, null);
  assert.strictEqual(game.stackOf('a'), 1000);
  assert.strictEqual(game.stackOf('b'), 1000);
});

test('перебор сразу отдаёт банк сопернику', () => {
  const game = duel(['Kh', '7c'], ['9d', '6s'], ['Qh']);
  game.act('a', 'hit'); // 17 + 10 = перебор
  assert.ok(game.complete, 'соперник добирать уже не должен');
  assert.strictEqual(game.result.winnerId, 'b');
  assert.match(game.result.reason, /перебор/);
  assert.strictEqual(game.stackOf('b'), 1100);
});

test('перебор второго тоже заканчивает раздачу', () => {
  const game = duel(['Kh', '7c'], ['9d', '6s'], ['Qh']);
  game.act('a', 'stand');
  game.act('b', 'hit'); // 15 + 10 = перебор
  assert.strictEqual(game.result.winnerId, 'a');
});

test('блекджек у одного заканчивает раздачу сразу', () => {
  const game = duel(['Ah', 'Kc'], ['9d', '7s']);
  assert.ok(game.complete);
  assert.strictEqual(game.result.winnerId, 'a');
  assert.strictEqual(game.result.reason, 'блекджек');
  assert.strictEqual(game.result.amount, 100, 'платится ровно ставка — казино тут нет');
});

test('блекджек у обоих — ничья', () => {
  const game = duel(['Ah', 'Kc'], ['Ad', 'Qs']);
  assert.strictEqual(game.result.winnerId, null);
  assert.strictEqual(game.stackOf('a'), 1000);
});

test('на 21 ход переходит сам', () => {
  const game = duel(['Kh', '5c'], ['9d', '6s'], ['6h']);
  game.act('a', 'hit'); // 15 + 6 = 21
  assert.strictEqual(game.actingId, 'b', 'добирать на 21 нечего');
  assert.strictEqual(game.valueOf('a').total, 21);
});

test('ставка не может превышать меньший из стеков', () => {
  assert.throws(
    () => duel(['Kh', '7c'], ['9d', '6s'], [], { bet: 500, secondStack: 300 }),
    /максимум 300/
  );
});

test('выигрыш ограничен стеком проигравшего', () => {
  const game = duel(['Kh', '9c'], ['9d', '8s'], [], { bet: 100, secondStack: 100 });
  game.act('a', 'stand');
  game.act('b', 'stand');
  assert.strictEqual(game.result.amount, 100);
  assert.strictEqual(game.stackOf('b'), 0);
});

test('фишки сохраняются в случайных раздачах', () => {
  for (let seed = 0; seed < 500; seed++) {
    const game = new BlackjackDuel({
      firstId: 'a', secondId: 'b', bet: 50, firstStack: 500, secondStack: 500,
    });
    let guard = 0;
    while (!game.complete && guard++ < 30) {
      const id = game.actingId;
      const legal = game.legalActions(id);
      if (legal.canHit && game.valueOf(id).total < 17) game.act(id, 'hit');
      else game.act(id, 'stand');
    }
    assert.ok(game.complete, 'раздача должна завершаться');
    assert.strictEqual(game.stackOf('a') + game.stackOf('b'), 1000, 'фишки не появляются и не исчезают');
  }
});
