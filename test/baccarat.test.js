'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { deal, total, cardPoints, bankerDraws, BaccaratError } = require('../server/baccarat/game');
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

test('выплаты: сторона 1:1, ничья 8:1, при ничьей ставка на сторону возвращается', () => {
  // игрок 9+7=6, банкир K+4=4; игрок стоит (6), банкир берёт (4, игрок не брал) → 4+2=6 → ничья
  const tie = deal({ zone: 'player', amount: 100, deck: deck('9h Kd 7c 4s 2d') });
  assert.strictEqual(tie.winner, 'tie');
  assert.strictEqual(tie.payout, 100, 'ставка вернулась');
  const tieBet = deal({ zone: 'tie', amount: 100, deck: deck('9h Kd 7c 4s 2d') });
  assert.strictEqual(tieBet.payout, 900);
  // игрок 9+7=6, банкир K+5=5 → банкир берёт 3 → 8; банкир выиграл
  const banker = deal({ zone: 'banker', amount: 100, deck: deck('9h Kd 7c 5s 3d') });
  assert.strictEqual(banker.winner, 'banker');
  assert.strictEqual(banker.payout, 200);
  assert.strictEqual(deal({ zone: 'player', amount: 100, deck: deck('9h Kd 7c 5s 3d') }).payout, 0);
});

test('неизвестная зона отклоняется', () => {
  assert.throws(() => deal({ zone: 'dragon', amount: 100 }), BaccaratError);
});
