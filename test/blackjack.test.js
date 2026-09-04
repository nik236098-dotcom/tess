'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { stringToCard, freshDeck } = require('../server/poker/cards');
const { BlackjackRound, BlackjackError, handValue } = require('../server/blackjack/round');

// Колода раскладывается так: игрок, дилер, игрок, дилер, дальше добор по порядку.
function stackDeck(playerCards, dealerCards, rest = []) {
  const order = [
    playerCards[0], dealerCards[0], playerCards[1], dealerCards[1],
    ...rest,
  ].map(stringToCard);
  const used = new Set(order);
  const tail = freshDeck().filter((card) => !used.has(card));
  return [...order, ...tail];
}

function round(playerCards, dealerCards, rest = [], options = {}) {
  return new BlackjackRound({
    playerId: 'p',
    dealerId: 'd',
    bet: 100,
    playerStack: 1000,
    dealerStack: 1000,
    deck: stackDeck(playerCards, dealerCards, rest),
    ...options,
  });
}

test('туз считается то за 11, то за 1', () => {
  const value = (line) => handValue(line.split(' ').map(stringToCard));
  assert.deepStrictEqual(value('Ah 9c'), { total: 20, soft: true, busted: false });
  assert.deepStrictEqual(value('Ah 9c 5d'), { total: 15, soft: false, busted: false });
  assert.deepStrictEqual(value('Ah Ac 9d'), { total: 21, soft: true, busted: false });
  assert.deepStrictEqual(value('Kh Qc 5d'), { total: 25, soft: false, busted: true });
  assert.strictEqual(value('Kh Ac').total, 21);
});

test('блекджек игрока платит полторы ставки', () => {
  const game = round(['Ah', 'Kc'], ['9d', '7s']);
  assert.ok(game.complete);
  assert.strictEqual(game.result.winner, 'player');
  assert.strictEqual(game.result.natural, true);
  assert.strictEqual(game.result.delta, 150);
  assert.strictEqual(game.playerStack, 1150);
  assert.strictEqual(game.dealerStack, 850);
});

test('блекджек у обоих — ничья', () => {
  const game = round(['Ah', 'Kc'], ['Ad', 'Qs']);
  assert.strictEqual(game.result.winner, 'push');
  assert.strictEqual(game.result.delta, 0);
  assert.strictEqual(game.playerStack, 1000);
});

test('блекджек дилера забирает ставку', () => {
  const game = round(['9h', '7c'], ['Ad', 'Qs']);
  assert.strictEqual(game.result.winner, 'dealer');
  assert.strictEqual(game.result.delta, -100);
});

test('перебор игрока заканчивает раздачу сразу', () => {
  const game = round(['Kh', '7c'], ['9d', '7s'], ['Qh']);
  assert.strictEqual(game.actingId, 'p');
  game.act('p', 'hit'); // 17 + 10 = перебор
  assert.ok(game.complete);
  assert.strictEqual(game.result.winner, 'dealer');
  assert.match(game.result.reason, /перебор у игрока/);
});

test('после паса игрока ходит дилер, его перебор — выигрыш игрока', () => {
  const game = round(['Kh', '7c'], ['9d', '6s'], ['Qh']);
  game.act('p', 'stand');
  assert.strictEqual(game.phase, 'dealer');
  assert.strictEqual(game.actingId, 'd');
  game.act('d', 'hit'); // 15 + 10 = перебор
  assert.strictEqual(game.result.winner, 'player');
  assert.strictEqual(game.result.delta, 100);
});

test('сравнение сумм: больше — тот и выиграл', () => {
  const game = round(['Kh', '9c'], ['9d', '8s']);
  game.act('p', 'stand');
  game.act('d', 'stand');
  assert.strictEqual(game.result.winner, 'player');
  assert.strictEqual(game.result.playerTotal, 19);
  assert.strictEqual(game.result.dealerTotal, 17);
});

test('равные суммы — ничья, фишки не двигаются', () => {
  const game = round(['Kh', '9c'], ['9d', 'Ts']);
  game.act('p', 'stand');
  game.act('d', 'stand');
  assert.strictEqual(game.result.winner, 'push');
  assert.strictEqual(game.playerStack, 1000);
  assert.strictEqual(game.dealerStack, 1000);
});

test('удвоение берёт одну карту и удваивает ставку', () => {
  const game = round(['6h', '5c'], ['9d', '7s'], ['Th']);
  assert.strictEqual(game.legalActions('p').canDouble, true);
  game.act('p', 'double');
  assert.strictEqual(game.bet, 200);
  assert.strictEqual(game.playerCards.length, 3);
  assert.strictEqual(game.phase, 'dealer', 'после удвоения ход сразу у дилера');
  game.act('d', 'stand');
  assert.strictEqual(game.result.winner, 'player');
  assert.strictEqual(game.result.delta, 200);
});

test('удвоить нельзя, если фишек не хватает', () => {
  const game = round(['6h', '5c'], ['9d', '7s'], [], { playerStack: 150, dealerStack: 1000 });
  assert.strictEqual(game.legalActions('p').canDouble, false);
  assert.throws(() => game.act('p', 'double'), BlackjackError);
});

test('карты дилера закрыты, пока ходит игрок', () => {
  const game = round(['Kh', '7c'], ['9d', '6s']);
  assert.strictEqual(game.visibleDealerCards().length, 1);
  game.act('p', 'stand');
  assert.strictEqual(game.visibleDealerCards().length, 2);
});

test('ставка не может превышать меньший из стеков', () => {
  assert.throws(
    () => round(['Kh', '7c'], ['9d', '6s'], [], { bet: 500, dealerStack: 300 }),
    /максимум 300/
  );
});

test('выигрыш не превышает того, что есть у дилера', () => {
  const game = round(['Ah', 'Kc'], ['9d', '7s'], [], { bet: 100, dealerStack: 120 });
  // Блекджек платил бы 150, но у дилера всего 120.
  assert.strictEqual(game.result.delta, 120);
  assert.strictEqual(game.dealerStack, 0);
});

test('чужой ход не принимается', () => {
  const game = round(['Kh', '7c'], ['9d', '6s']);
  assert.throws(() => game.act('d', 'hit'), /не ваш ход/);
});

test('фишки сохраняются в случайных раздачах', () => {
  for (let seed = 0; seed < 500; seed++) {
    const game = new BlackjackRound({
      playerId: 'p', dealerId: 'd', bet: 50, playerStack: 500, dealerStack: 500,
    });
    let guard = 0;
    while (!game.complete && guard++ < 30) {
      const id = game.actingId;
      const legal = game.legalActions(id);
      const value = id === 'p' ? game.playerValue : game.dealerValue;
      if (legal.canHit && value.total < 17) game.act(id, 'hit');
      else game.act(id, 'stand');
    }
    assert.ok(game.complete, 'раздача должна завершаться');
    assert.strictEqual(game.playerStack + game.dealerStack, 1000, 'фишки не появляются и не исчезают');
  }
});
