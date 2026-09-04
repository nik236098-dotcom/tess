'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { stringToCard, freshDeck } = require('../server/poker/cards');
const { Hand, ActionError } = require('../server/poker/hand');

// Собирает колоду так, чтобы игроки получили заданные карманные карты,
// а на борд легли заданные общие карты. Порядок раздачи — как в Hand._deal.
function stackDeck({ playerCount, dealerIndex, holes, board }) {
  const used = [];
  const deck = new Array(52).fill(null);
  const order = [];
  for (let round = 0; round < 2; round++) {
    for (let i = 1; i <= playerCount; i++) order.push((dealerIndex + i) % playerCount);
  }
  order.forEach((seat, position) => {
    const cards = holes[seat];
    const card = stringToCard(cards[position < playerCount ? 0 : 1]);
    deck[position] = card;
    used.push(card);
  });

  const boardCards = board.map(stringToCard);
  const boardSlots = [
    playerCount * 2 + 1, // флоп после сжигания
    playerCount * 2 + 2,
    playerCount * 2 + 3,
    playerCount * 2 + 5, // тёрн
    playerCount * 2 + 7, // ривер
  ];
  boardCards.forEach((card, i) => {
    deck[boardSlots[i]] = card;
    used.push(card);
  });

  const rest = freshDeck().filter((c) => !used.includes(c));
  for (let i = 0; i < deck.length; i++) if (deck[i] === null) deck[i] = rest.shift();
  return deck;
}

const players = (...stacks) => stacks.map((stack, i) => ({ id: `p${i}`, stack }));

test('хедз-ап: баттон ставит малый блайнд и ходит первым на префлопе', () => {
  const hand = new Hand({ players: players(1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  assert.strictEqual(hand.player('p0').committed, 10);
  assert.strictEqual(hand.player('p1').committed, 20);
  assert.strictEqual(hand.actingPlayer.id, 'p0');
});

test('за тремя игроками блайнды слева от баттона, первым ходит UTG', () => {
  const hand = new Hand({ players: players(1000, 1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  assert.strictEqual(hand.player('p1').committed, 10);
  assert.strictEqual(hand.player('p2').committed, 20);
  assert.strictEqual(hand.actingPlayer.id, 'p0');
});

test('все пасуют — банк забирает большой блайнд, лишнее возвращается', () => {
  const hand = new Hand({ players: players(1000, 1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  hand.act('p0', 'fold');
  hand.act('p1', 'fold');
  assert.ok(hand.complete);
  assert.strictEqual(hand.player('p2').stack, 1010);
  assert.strictEqual(hand.player('p1').stack, 990);
  assert.strictEqual(hand.result.showdown, false);
});

test('большой блайнд получает опцию рейза, когда все уравняли', () => {
  const hand = new Hand({ players: players(1000, 1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  hand.act('p0', 'call');
  hand.act('p1', 'call');
  assert.strictEqual(hand.phase, 'preflop');
  assert.strictEqual(hand.actingPlayer.id, 'p2');
  assert.ok(hand.legalActions('p2').canCheck);
  hand.act('p2', 'check');
  assert.strictEqual(hand.phase, 'flop');
  assert.strictEqual(hand.board.length, 3);
  assert.strictEqual(hand.actingPlayer.id, 'p1', 'после флопа первым ходит малый блайнд');
});

test('минимальный рейз проверяется', () => {
  const hand = new Hand({ players: players(1000, 1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  assert.strictEqual(hand.legalActions('p0').minRaiseTo, 40);
  assert.throws(() => hand.act('p0', 'raise', 30), ActionError);
  hand.act('p0', 'raise', 60);
  assert.strictEqual(hand.legalActions('p1').minRaiseTo, 100, 'следующий минимальный рейз — до 100');
});

test('вскрытие: сильнейшая рука забирает банк', () => {
  const deck = stackDeck({
    playerCount: 2,
    dealerIndex: 0,
    holes: { 0: ['Ac', 'Ad'], 1: ['Kc', 'Kd'] },
    board: ['2h', '7s', '9c', 'Jd', '4s'],
  });
  const hand = new Hand({ players: players(1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20, deck });
  hand.act('p0', 'call');
  hand.act('p1', 'check');
  hand.act('p1', 'check');
  hand.act('p0', 'check');
  hand.act('p1', 'check');
  hand.act('p0', 'check');
  hand.act('p1', 'check');
  hand.act('p0', 'check');
  assert.ok(hand.complete);
  assert.strictEqual(hand.result.showdown, true);
  assert.strictEqual(hand.player('p0').stack, 1020);
  assert.strictEqual(hand.player('p1').stack, 980);
  assert.strictEqual(hand.result.winners[0].hand.name, 'Пара A');
});

test('ничья делит банк поровну', () => {
  const deck = stackDeck({
    playerCount: 2,
    dealerIndex: 0,
    holes: { 0: ['2c', '3d'], 1: ['2h', '3s'] },
    board: ['Ac', 'Ad', 'Ah', 'As', 'Kd'],
  });
  const hand = new Hand({ players: players(1000, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20, deck });
  hand.act('p0', 'call');
  hand.act('p1', 'check');
  for (let i = 0; i < 6; i++) hand.act(hand.actingPlayer.id, 'check');
  assert.strictEqual(hand.player('p0').stack, 1000);
  assert.strictEqual(hand.player('p1').stack, 1000);
});

test('сайд-поты: короткий стек не может выиграть больше, чем поставил', () => {
  // p0 — баттон (100), p1 — малый блайнд (50), p2 — большой блайнд (200).
  const deck = stackDeck({
    playerCount: 3,
    dealerIndex: 0,
    holes: { 0: ['Kc', 'Kd'], 1: ['Ac', 'Ad'], 2: ['Qc', 'Qd'] },
    board: ['2h', '7s', '9c', 'Jd', '4s'],
  });
  const hand = new Hand({
    players: players(100, 50, 200),
    dealerIndex: 0,
    smallBlind: 10,
    bigBlind: 20,
    deck,
  });
  hand.act('p0', 'allin'); // 100
  hand.act('p1', 'allin'); // всего 50
  hand.act('p2', 'call'); // уравнивает до 100
  assert.ok(hand.complete);

  // Основной банк 150 берут тузы, сайд-пот 100 — короли.
  assert.strictEqual(hand.player('p1').stack, 150);
  assert.strictEqual(hand.player('p0').stack, 100);
  assert.strictEqual(hand.player('p2').stack, 100);
});

test('невостребованный олл-ин возвращается ставившему', () => {
  const hand = new Hand({ players: players(1000, 100, 1000), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  hand.act('p0', 'raise', 500);
  hand.act('p1', 'fold');
  hand.act('p2', 'fold');
  assert.strictEqual(hand.player('p0').stack, 1030, 'забрал блайнды, лишние 480 вернулись');
});

test('после олл-инов борд докручивается до ривера', () => {
  const hand = new Hand({ players: players(200, 200), dealerIndex: 0, smallBlind: 10, bigBlind: 20 });
  hand.act('p0', 'allin');
  hand.act('p1', 'call');
  assert.ok(hand.complete);
  assert.strictEqual(hand.result.board.length, 5);
  const total = hand.player('p0').stack + hand.player('p1').stack;
  assert.strictEqual(total, 400, 'фишки не появляются и не исчезают');
});

test('пот, за который некому бороться, возвращается вкладчикам', () => {
  // Двое торговались между собой поверх олл-инов, а потом оба спасовали.
  // Их деньги не должны исчезнуть: за этот уровень ставок бороться уже некому.
  const hand = new Hand({
    players: players(153, 519, 35, 42),
    dealerIndex: 3,
    smallBlind: 10,
    bigBlind: 20,
  });

  const moves = [
    ['p2', 'call'], ['p3', 'raise', 40], ['p0', 'call'], ['p1', 'raise', 60],
    ['p2', 'call'], ['p3', 'call'], ['p0', 'raise', 80], ['p1', 'raise', 100], ['p0', 'call'],
    ['p0', 'raise', 20], ['p1', 'call'],
    ['p0', 'check'], ['p1', 'check'],
    ['p0', 'fold'], ['p1', 'fold'],
  ];
  for (const [id, action, amount] of moves) hand.act(id, action, amount);

  assert.ok(hand.complete);
  const total = hand.players.reduce((sum, p) => sum + p.stack, 0);
  assert.strictEqual(total, 749, 'фишки не исчезли');

  // 156 фишек уровня, до которого не дотянулись олл-ины, делятся пополам.
  assert.strictEqual(hand.player('p0').stack, 33 + 78);
  assert.strictEqual(hand.player('p1').stack, 399 + 78);
  assert.deepStrictEqual(
    hand.result.refunds.map((r) => r.amount).sort(),
    [78, 78]
  );
});

// Детерминированный генератор: падение всегда воспроизводится по номеру попытки.
function mulberry32(seed) {
  let a = seed;
  return function next() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

test('фишки сохраняются в двух тысячах случайных раздач', () => {
  for (let seed = 1; seed <= 2000; seed++) {
    const rng = mulberry32(seed);
    const count = 2 + Math.floor(rng() * 3);
    const stacks = Array.from({ length: count }, () => 20 + Math.floor(rng() * 500));
    const hand = new Hand({
      players: players(...stacks),
      dealerIndex: Math.floor(rng() * count),
      smallBlind: 10,
      bigBlind: 20,
      rng,
    });

    let guard = 0;
    while (!hand.complete && guard++ < 300) {
      const actor = hand.actingPlayer;
      const legal = hand.legalActions(actor.id);
      const roll = rng();
      if (roll < 0.15) hand.act(actor.id, 'fold');
      else if (roll < 0.7) hand.act(actor.id, legal.canCheck ? 'check' : 'call');
      else if (legal.canRaise) hand.act(actor.id, 'raise', legal.minRaiseTo);
      else hand.act(actor.id, legal.canCheck ? 'check' : 'call');
    }

    assert.ok(hand.complete, `раздача ${seed} должна завершаться`);
    const after = hand.players.reduce((sum, p) => sum + p.stack, 0);
    assert.strictEqual(after, stacks.reduce((a, b) => a + b, 0), `раздача ${seed}: сумма фишек изменилась`);
  }
});
