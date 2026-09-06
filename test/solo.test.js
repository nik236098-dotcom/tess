'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { SoloBlackjack, SoloError } = require('../server/blackjack/solo');
const { stringToCard } = require('../server/poker/cards');

// Колода задаётся с конца: pop() берёт последнюю карту, поэтому порядок раздачи —
// последняя карта списка идёт первой. Пишем в порядке раздачи и переворачиваем.
const deck = (line) => line.split(' ').map(stringToCard).reverse();

test('раздача: по две карты, у дилера одна закрыта', () => {
  const game = new SoloBlackjack({ deck: deck('9s 5d 7h Kc 2c 3c') });
  const s = game.start(500);
  assert.strictEqual(s.phase, 'play');
  assert.deepStrictEqual(s.hands[0].cards, ['9s', '7h']);
  assert.deepStrictEqual(s.dealer.cards, ['5d', '??']);
  assert.strictEqual(s.dealer.total, 5, 'считается только открытая карта');
  assert.strictEqual(s.options.hit, true);
  assert.strictEqual(s.options.double, true);
  assert.strictEqual(s.options.split, false);
});

test('дилер добирает до 16 и стоит на 17', () => {
  // игрок 9+7=16 стоит; дилер 5+Q=15 → берёт 2 → 17, стоп; 17 > 16 — игрок проиграл
  const game = new SoloBlackjack({ deck: deck('9s 5d 7h Qc 2c 9c') });
  game.start(500);
  const s = game.stand();
  assert.strictEqual(s.phase, 'done');
  assert.deepStrictEqual(s.dealer.cards, ['5d', 'Qc', '2c']);
  assert.strictEqual(s.results.dealerTotal, 17);
  assert.strictEqual(s.results.hands[0].outcome, 'lose');
  assert.strictEqual(s.results.payout, 0);
});

test('дилер на мягких 17 тоже стоит', () => {
  // игрок 10+8=18; дилер A+6 = мягкие 17 — не берёт; 18 > 17 — победа 1:1
  const game = new SoloBlackjack({ deck: deck('Ts Ad 8h 6c 9c') });
  game.start(300);
  const s = game.stand();
  assert.deepStrictEqual(s.dealer.cards, ['Ad', '6c']);
  assert.strictEqual(s.results.hands[0].outcome, 'win');
  assert.strictEqual(s.results.payout, 600);
});

test('блекджек с раздачи платит 3 к 2 и заканчивает раздачу сразу', () => {
  const game = new SoloBlackjack({ deck: deck('As 5d Kh 9c') });
  const s = game.start(1000);
  assert.strictEqual(s.phase, 'done');
  assert.strictEqual(s.results.hands[0].outcome, 'blackjack');
  assert.strictEqual(s.results.payout, 2500, 'ставка плюс полторы ставки');
  assert.strictEqual(s.dealer.revealed, true);
});

test('перебор игрока — проигрыш, дилер карт не берёт', () => {
  const game = new SoloBlackjack({ deck: deck('Ts 5d 6h 9c Kd') });
  game.start(200);
  const s = game.hit();
  assert.strictEqual(s.hands[0].busted, true);
  assert.strictEqual(s.phase, 'done');
  assert.deepStrictEqual(s.dealer.cards, ['5d', '9c'], 'дилер только открылся');
  assert.strictEqual(s.results.hands[0].outcome, 'bust');
});

test('ничья возвращает ставку', () => {
  const game = new SoloBlackjack({ deck: deck('Ts 9d 8h 9c') });
  game.start(400);
  const s = game.stand();
  assert.strictEqual(s.results.hands[0].outcome, 'push');
  assert.strictEqual(s.results.payout, 400);
  assert.strictEqual(s.results.net, 0);
});

test('удвоение: одна карта, ставка вдвое', () => {
  // игрок 5+6=11, удваивает → K = 21; дилер 9+7=16 → берёт 2 → 18; победа 2×800
  const game = new SoloBlackjack({ deck: deck('5s 9d 6h 7c Kd 2c') });
  game.start(400);
  const s = game.double();
  assert.strictEqual(s.hands[0].doubled, true);
  assert.strictEqual(s.hands[0].bet, 800);
  assert.strictEqual(s.hands[0].cards.length, 3);
  assert.strictEqual(s.results.hands[0].outcome, 'win');
  assert.strictEqual(s.results.payout, 1600);
});

test('сплит: две руки, каждая играется по очереди', () => {
  // 8s 8h → сплит: рука1 8s+2c, рука2 8h+3c; обе стоят; дилер 9d+7d=16 → берёт 5c = 21
  const game = new SoloBlackjack({ deck: deck('8s 9d 8h 7d 2c 3c 5c') });
  game.start(100);
  assert.strictEqual(game.state().options.split, true);
  let s = game.split();
  assert.strictEqual(s.hands.length, 2);
  assert.deepStrictEqual(s.hands[0].cards, ['8s', '2c']);
  assert.deepStrictEqual(s.hands[1].cards, ['8h', '3c']);
  assert.strictEqual(s.hands[0].active, true);
  s = game.stand();
  assert.strictEqual(s.hands[1].active, true, 'ход перешёл ко второй руке');
  s = game.stand();
  assert.strictEqual(s.phase, 'done');
  assert.strictEqual(s.results.dealerTotal, 21);
  assert.deepStrictEqual(s.results.hands.map((h) => h.outcome), ['lose', 'lose']);
  assert.strictEqual(s.results.stake, 200);
});

test('удвоить и разделить можно, только если хватает денег', () => {
  const game = new SoloBlackjack({ deck: deck('8s 9d 8h 7d 2c') });
  game.start(100);
  assert.deepStrictEqual(game.state(50).options, { hit: true, stand: true, double: false, split: false });
  assert.deepStrictEqual(game.state(100).options, { hit: true, stand: true, double: true, split: true });
});

test('ставка вне границ отклоняется', () => {
  const game = new SoloBlackjack({ minBet: 100, maxBet: 1000 });
  assert.throws(() => game.start(50), SoloError);
  assert.throws(() => game.start(5000), SoloError);
});

test('после раздачи можно начать заново с той же ставкой', () => {
  const game = new SoloBlackjack({ deck: deck('Ts 9d 8h 9c') });
  game.start(400);
  game.stand();
  const s = game.reset();
  assert.strictEqual(s.phase, 'bet');
  assert.strictEqual(s.bet, 400);
  assert.deepStrictEqual(s.hands, []);
  assert.deepStrictEqual(s.dealer.cards, []);
});
