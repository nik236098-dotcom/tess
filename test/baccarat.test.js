'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { deal, total, cardPoints, bankerDraws, normalizeBets, isPerfectPair, freshShoe, BaccaratError, DECKS } = require('../server/baccarat/game');
const { stringToCard } = require('../server/poker/cards');

// Колода задаётся в порядке раздачи: P1 B1 P2 B2 P3 B3.
const deck = (line) => line.split(' ').map(stringToCard).reverse();

test('очки: туз 1, картинки 0, сумма по модулю 10', () => {
  assert.strictEqual(cardPoints(stringToCard('As')), 1);
  assert.strictEqual(cardPoints(stringToCard('Kd')), 0);
  assert.strictEqual(cardPoints(stringToCard('Tc')), 0);
  assert.strictEqual(cardPoints(stringToCard('9h')), 9);
  assert.strictEqual(total(['9h', '7c'].map(stringToCard)), 6);
});

test('натуральные 8/9 — третьих карт нет', () => {
  const r = deal({ zone: 'player', amount: 100, deck: deck('9h Kd 8c 4s 2d 3d') });
  assert.deepStrictEqual(r.player, ['9h', '8c']);
  assert.deepStrictEqual(r.banker, ['Kd', '4s', '2d'], 'игрок стоял на 7, банкир на 4 берёт');
  assert.strictEqual(r.playerTotal, 7);
  assert.strictEqual(r.natural, false, '9+8=17→7 — не натуральная');
  const n = deal({ zone: 'player', amount: 100, deck: deck('9h Kd Tc 4s 2d 3d') });
  assert.strictEqual(n.natural, true);
  assert.strictEqual(n.player.length, 2);
  assert.strictEqual(n.banker.length, 2);
});

test('игрок берёт на 0–5, стоит на 6–7', () => {
  const r = deal({ zone: 'player', amount: 100, deck: deck('2h 3d 3c 4s 9d 5c') });
  assert.strictEqual(r.player.length, 3, '2+3=5 — берёт');
  const s = deal({ zone: 'player', amount: 100, deck: deck('3h 3d 3c 4s 9d 5c') });
  assert.strictEqual(s.player.length, 2, '3+3=6 — стоит');
});

test('правило третьей карты банкира', () => {
  const T = stringToCard('Tc'); // третья карта игрока = 0
  assert.strictEqual(bankerDraws(3, stringToCard('8d')), false, 'на 3 не берёт против 8');
  assert.strictEqual(bankerDraws(3, T), true);
  assert.strictEqual(bankerDraws(4, stringToCard('2d')), true);
  assert.strictEqual(bankerDraws(4, stringToCard('9d')), false);
  assert.strictEqual(bankerDraws(5, stringToCard('4d')), true);
  assert.strictEqual(bankerDraws(5, stringToCard('3d')), false);
  assert.strictEqual(bankerDraws(6, stringToCard('6d')), true);
  assert.strictEqual(bankerDraws(6, stringToCard('5d')), false);
  assert.strictEqual(bankerDraws(7, stringToCard('6d')), false);
  assert.strictEqual(bankerDraws(5, null), true, 'игрок стоял — банкир берёт на 5');
  assert.strictEqual(bankerDraws(6, null), false);
});

test('выплаты: игрок 1:1, банкир 0.95:1 (комиссия), ничья 8:1, при ничьей ставка на сторону возвращается', () => {
  // игрок 9+7=6, банкир K+4=4; игрок стоит (6), банкир берёт (4, игрок не брал) → 4+2=6 → ничья
  const tie = deal({ zone: 'player', amount: 100, deck: deck('9h Kd 7c 4s 2d') });
  assert.strictEqual(tie.winner, 'tie');
  assert.strictEqual(tie.payout, 100, 'ставка вернулась');
  const tieBet = deal({ zone: 'tie', amount: 100, deck: deck('9h Kd 7c 4s 2d') });
  assert.strictEqual(tieBet.payout, 900);
  // игрок 9+7=6, банкир K+5=5 → банкир берёт 3 → 8; банкир выиграл
  const banker = deal({ zone: 'banker', amount: 100, deck: deck('9h Kd 7c 5s 3d') });
  assert.strictEqual(banker.winner, 'banker');
  assert.strictEqual(banker.payout, 195, '100 · 1.95 — 5 % комиссии казино');
  assert.strictEqual(deal({ zone: 'player', amount: 100, deck: deck('9h Kd 7c 5s 3d') }).payout, 0);
});

test('неизвестная зона отклоняется', () => {
  assert.throws(() => deal({ zone: 'dragon', amount: 100 }), BaccaratError);
});

test('пара: первые две карты стороны одного достоинства, платит 11:1', () => {
  // игрок 9h 9c = 18→8 (натуральная, пара), банкир Kd 4s
  const r = deal({ bets: [{ zone: 'playerPair', amount: 100 }, { zone: 'bankerPair', amount: 100 }, { zone: 'player', amount: 100 }], deck: deck('9h Kd 9c 4s') });
  assert.strictEqual(r.playerPair, true);
  assert.strictEqual(r.bankerPair, false);
  assert.deepStrictEqual(r.bets.map((b) => b.payout), [1200, 0, 200]);
  assert.strictEqual(r.net, 1400 - 300);
});

test('Perfect Pair: совпадают ранг и масть, платит 50:1, обычную пару не отменяет', () => {
  // игрок 9h 9h — буквально одна и та же карта дважды (возможно только из
  // многоколодного башмака); банкир Kd 4s — обычная пара, не идеальная.
  const r = deal({
    bets: [
      { zone: 'playerPerfectPair', amount: 100 },
      { zone: 'playerPair', amount: 100 },
      { zone: 'bankerPerfectPair', amount: 100 },
    ],
    deck: deck('9h Kd 9h 4s'),
  });
  assert.strictEqual(r.playerPerfectPair, true);
  assert.strictEqual(r.playerPair, true, 'идеальная пара — тоже пара по рангу');
  assert.strictEqual(r.bankerPerfectPair, false);
  assert.deepStrictEqual(r.bets.map((b) => b.payout), [5100, 1200, 0]);
});

test('isPerfectPair: та же карта дважды — идеальная пара, разная масть — нет', () => {
  assert.strictEqual(isPerfectPair([stringToCard('9h'), stringToCard('9h')]), true);
  assert.strictEqual(isPerfectPair([stringToCard('9h'), stringToCard('9c')]), false);
  assert.strictEqual(isPerfectPair([stringToCard('9h')]), false);
});

test('башмак: 8 колод по 52 карты, каждая карта встречается 8 раз', () => {
  const shoe = freshShoe();
  assert.strictEqual(shoe.length, 52 * DECKS);
  const counts = new Map();
  for (const card of shoe) counts.set(card, (counts.get(card) || 0) + 1);
  assert.strictEqual(counts.size, 52);
  for (const count of counts.values()) assert.strictEqual(count, DECKS);
});

test('без переданной колоды раздача берёт карты из многоколодного башмака', () => {
  // Тасуем реальным rng — просто проверяем, что игра не падает и карты валидны.
  const r = deal({ zone: 'player', amount: 100 });
  assert.strictEqual(r.player.length >= 2, true);
  assert.strictEqual(r.banker.length >= 2, true);
});

test('несколько ставок: проверка зон, повторов и общей суммы', () => {
  const limits = { minBet: 100, maxBet: 1000000, maxTotal: 1000 };
  assert.throws(() => normalizeBets([], limits), BaccaratError);
  assert.throws(() => normalizeBets([{ zone: 'player', amount: 100 }, { zone: 'player', amount: 100 }], limits), /повторяется/);
  assert.throws(() => normalizeBets([{ zone: 'player', amount: 600 }, { zone: 'tie', amount: 600 }], limits), /Недостаточно/);
  assert.strictEqual(normalizeBets([{ zone: 'player', amount: 300 }, { zone: 'tie', amount: 200 }], limits).total, 500);
});
