'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { Room, RoomError, describeCombination } = require('../server/room');
const { Accounts } = require('../server/accounts');
const { stringToCard } = require('../server/poker/cards');

const cards = (line) => line.split(' ').map(stringToCard);

function table({ settings = {}, players = ['Аня', 'Боря'], balance = 10000 } = {}) {
  const bank = new Accounts({ startingBalance: balance });
  players.forEach((name, i) => bank.ensure({ id: `u${i}`, name }));

  const host = { id: 'u0', name: players[0] };
  const room = new Room('TEST1', host, { buyIn: 1000, smallBlind: 5, bigBlind: 10, ...settings }, { bank });
  players.slice(1).forEach((name, i) => room.addMember({ id: `u${i + 1}`, name }));
  players.forEach((_, i) => room.sit(`u${i}`, i));
  room.bankRef = bank;
  return room;
}

test('посадка списывает вход с баланса, а уход возвращает стек', (t) => {
  const room = table({ balance: 5000 });
  t.after(() => room.dispose());

  assert.strictEqual(room.bankRef.balanceOf('u0'), 4000, 'вход в 1000 ушёл со счёта');
  assert.strictEqual(room.seatOf('u0').stack, 1000);

  room.stand('u0');
  assert.strictEqual(room.bankRef.balanceOf('u0'), 5000, 'стек вернулся на баланс');
  assert.strictEqual(room.seats[0], null);
});

test('без фишек на балансе за стол не сесть', (t) => {
  const room = table({ balance: 1000, players: ['Аня', 'Боря'] });
  t.after(() => room.dispose());

  room.addMember({ id: 'u2', name: 'Вика' });
  room.bankRef.ensure({ id: 'u2', name: 'Вика' });
  room.bankRef.grant('u2', 100, 'set');

  assert.throws(() => room.sit('u2', 2), /не хватает фишек/);
  assert.strictEqual(room.seats[2], null);
});

test('уход посреди раздачи откладывается до её конца', (t) => {
  // Втроём пас одного игрока раздачу не заканчивает — есть на чём проверить.
  const room = table({ balance: 5000, players: ['Аня', 'Боря', 'Вика'] });
  t.after(() => room.dispose());
  room.start('u0');

  const actor = room.hand.actingPlayer.id;
  room.stand(actor);
  assert.ok(room.seatOf(actor), 'место держится, пока идут ставки');
  assert.strictEqual(room.seatOf(actor).leaveAfterHand, true);
  assert.strictEqual(room.bankRef.balanceOf(actor), 4000, 'баланс пока не трогали');

  // Доигрываем: остаётся один игрок, раздача завершается.
  room.applyAction(room.hand.actingPlayer.id, 'fold');

  assert.strictEqual(room.seatIndexOf(actor), -1, 'после раздачи место освободилось');
  assert.strictEqual(room.bankRef.balanceOf(actor), 5000, 'весь стек вернулся на баланс');
});

test('пополнение предлагается, только когда стек реально просел', (t) => {
  const room = table({ balance: 3000 });
  t.after(() => room.dispose());

  const seat = room.seatOf('u1');
  seat.stack = 990; // потеряли всего десятку
  assert.strictEqual(room.stateFor('u1').you.canRebuy, false, 'кнопка не должна лезть после первой потери');

  seat.stack = 200;
  assert.strictEqual(room.stateFor('u1').you.canRebuy, true);
});

test('пополнение стека берёт фишки с баланса', (t) => {
  const room = table({ balance: 3000 });
  t.after(() => room.dispose());

  const seat = room.seatOf('u1');
  seat.stack = 200;
  room.rebuy('u1');

  assert.strictEqual(seat.stack, 1000, 'стек дотянули до размера входа');
  assert.strictEqual(room.bankRef.balanceOf('u1'), 1200, 'списали ровно недостающие 800');
});

test('пополнение ограничено остатком на балансе', (t) => {
  const room = table({ balance: 1300 });
  t.after(() => room.dispose());

  const seat = room.seatOf('u1');
  seat.stack = 100;
  room.rebuy('u1');

  assert.strictEqual(seat.stack, 400, 'добавили всё, что было на балансе');
  assert.strictEqual(room.bankRef.balanceOf('u1'), 0);
});

test('фишки со стола возвращаются на балансы при закрытии комнаты', (t) => {
  const room = table({ balance: 5000 });
  t.after(() => room.dispose());

  room.cashOutAll();
  assert.strictEqual(room.bankRef.balanceOf('u0'), 5000);
  assert.strictEqual(room.bankRef.balanceOf('u1'), 5000);
  assert.deepStrictEqual(room.seats.filter(Boolean), []);
});

test('подсказка комбинации считается по видимым картам', () => {
  assert.strictEqual(describeCombination(cards('9c 9d'), []), 'Пара 9');
  assert.strictEqual(describeCombination(cards('Ac Kd'), []), null, 'до флопа без пары подсказки нет');
  assert.strictEqual(describeCombination(cards('9c 9d'), cards('9h 2s 7c')), 'Тройка 9');
  assert.strictEqual(describeCombination(cards('Ac Kd'), cards('Qh Js Tc')), 'Стрит до A');
  assert.strictEqual(describeCombination(cards('2c 7d'), cards('9h 2s 7c 2d 7s')), 'Фулл-хаус 7 на 2');
});

test('чужая комбинация не попадает в состояние до вскрытия', (t) => {
  const room = table();
  t.after(() => room.dispose());
  room.start('u0');

  const view = room.stateFor('u0');
  const mine = view.seats[view.you.seatIndex];
  const opponent = view.seats.find((seat) => !seat.empty && seat.index !== view.you.seatIndex);

  assert.deepStrictEqual(opponent.cards, ['??', '??']);
  assert.strictEqual(opponent.combination, null, 'подсказка соперника скрыта');
  assert.ok(mine.cards.every((card) => card !== '??'));
});

test('карточка стола для открытого списка', (t) => {
  const room = table({ players: ['Аня', 'Боря', 'Вика'] });
  t.after(() => room.dispose());

  const summary = room.summary();
  assert.strictEqual(summary.code, 'TEST1');
  assert.strictEqual(summary.host, 'Аня');
  assert.strictEqual(summary.players, 3);
  assert.strictEqual(summary.isPublic, true, 'по умолчанию стол открыт');
  assert.strictEqual(summary.hasFreeSeat, true);
});

test('стол можно сделать закрытым', (t) => {
  const room = table({ settings: { isPublic: false } });
  t.after(() => room.dispose());
  assert.strictEqual(room.summary().isPublic, false);
});

// ——— Блекджек ———

function blackjackTable({ settings = {}, balance = 10000 } = {}) {
  const bank = new Accounts({ startingBalance: balance });
  ['Аня', 'Боря'].forEach((name, i) => bank.ensure({ id: `u${i}`, name }));

  const room = new Room(
    'BJ001',
    { id: 'u0', name: 'Аня' },
    { game: 'blackjack', minBet: 10, maxBet: 200, buyIn: 1000, ...settings },
    { bank }
  );
  room.addMember({ id: 'u1', name: 'Боря' });
  room.sit('u0', 0);
  room.sit('u1', 1);
  room.bankRef = bank;
  return room;
}

const playOut = (room) => {
  let guard = 0;
  while (room.round && !room.round.complete && guard++ < 30) {
    room.applyAction(room.round.actingId, 'stand');
  }
};

test('блекджековый стол всегда на два места', (t) => {
  const room = blackjackTable({ settings: { maxPlayers: 6 } });
  t.after(() => room.dispose());
  assert.strictEqual(room.seats.length, 2);
  assert.strictEqual(room.settings.game, 'blackjack');
});

test('раздача начинается со ставки, её назначает тот, кто ходит первым', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');

  assert.strictEqual(room.status, 'betting');
  assert.notStrictEqual(room.openerSeat, room.secondSeat);
  const opener = room.seats[room.openerSeat].userId;
  assert.deepStrictEqual(room.stateFor(opener).you.betTurn, { min: 10, max: 200 });
  assert.strictEqual(room.stateFor(room.seats[room.secondSeat].userId).you.betTurn, null);
});

test('соперник ставку не назначает', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');

  const second = room.seats[room.secondSeat].userId;
  assert.throws(() => room.applyAction(second, 'bet', 50), /назначает соперник/);
});

test('ставка проверяется на минимум и максимум', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');
  const opener = room.seats[room.openerSeat].userId;

  assert.throws(() => room.applyAction(opener, 'bet', 5), /Минимальная ставка/);
  assert.throws(() => room.applyAction(opener, 'bet', 5000), /Максимальная ставка/);
  room.applyAction(opener, 'bet', 100);
  assert.strictEqual(room.status, 'playing');
});

test('карты соперника закрыты, пока идёт раздача', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');
  const opener = room.seats[room.openerSeat].userId;
  const second = room.seats[room.secondSeat].userId;
  room.applyAction(opener, 'bet', 50);

  const view = room.stateFor(second);
  const mine = view.seats[room.secondSeat];
  const theirs = view.seats[room.openerSeat];

  assert.ok(!mine.cards.includes('??'), 'свои карты видно');
  assert.match(mine.combination, /^Очки: \d+$/);
  assert.deepStrictEqual(theirs.cards, ['??', '??'], 'чужие закрыты');
  assert.strictEqual(theirs.total, null, 'и очки соперника не подсказываем');

  // После раздачи руки открываются обоим. Ходы делаем через playOut:
  // при 21 с двух карт ход переходит сам, и жать «стоп» вслепую нельзя.
  playOut(room);
  const after = room.stateFor(opener).seats[room.secondSeat];
  assert.ok(!after.cards.includes('??'));
  assert.match(after.combination, /^Очки: \d+$/);
});

test('в журнале не видно, какую карту взял соперник', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');
  const opener = room.seats[room.openerSeat].userId;
  room.applyAction(opener, 'bet', 50);

  // Событие добора подставляем сами: какие карты придут — дело случая,
  // а проверить нужно ровно то, как оно попадает в журнал.
  room.round.events.push({ type: 'hit', playerId: opener, card: stringToCard('Ks') });
  room.logRoundEvents();

  const lines = room.log.map((line) => line.text).join('\n');
  assert.match(lines, /берёт карту/);
  assert.ok(!/берёт[^\n]*[♠♥♦♣]/.test(lines), 'достоинство карты в журнал не попадает');
});

test('очередь ходить первым переходит к сопернику', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');

  const firstOpener = room.openerSeat;
  room.applyAction(room.seats[room.openerSeat].userId, 'bet', 50);
  playOut(room);
  assert.ok(room.lastResult, 'раздача завершилась');

  room.startRound();
  assert.notStrictEqual(room.openerSeat, firstOpener, 'теперь начинает второй');
});

test('фишки только переходят между игроками', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');

  for (let i = 0; i < 25 && room.seats.every(Boolean); i++) {
    if (room.status !== 'betting') room.startRound();
    if (room.status !== 'betting') break;
    const opener = room.seats[room.openerSeat].userId;
    const max = room.maxBet;
    if (max < room.settings.minBet) break;
    room.applyAction(opener, 'bet', Math.min(50, max));
    playOut(room);
    const total = room.seats.filter(Boolean).reduce((sum, seat) => sum + seat.stack, 0);
    assert.strictEqual(total, 2000, `после раздачи ${i + 1} сумма фишек изменилась`);
  }
});

test('уход посреди раздачи откладывается до её конца', (t) => {
  const room = blackjackTable();
  t.after(() => room.dispose());
  room.start('u0');
  const opener = room.seats[room.openerSeat].userId;
  room.applyAction(opener, 'bet', 50);

  room.stand(opener);
  assert.ok(room.seatOf(opener), 'место держится, пока идёт раздача');
  playOut(room);
  assert.strictEqual(room.seatIndexOf(opener), -1, 'после раздачи место освободилось');
});

// ——— Кнопки управления столом ———

test('начать игру можно только когда есть с кем', (t) => {
  const room = table({ players: ['Аня', 'Боря'] });
  t.after(() => room.dispose());

  assert.strictEqual(room.stateFor('u0').you.canStart, true);
  assert.strictEqual(room.stateFor('u1').you.canStart, false, 'начинает только хозяин');

  room.stand('u1');
  assert.strictEqual(room.stateFor('u0').you.canStart, false, 'в одиночку игру не начать');

  room.sit('u1', 1);
  room.start('u0');
  assert.strictEqual(room.stateFor('u0').you.canStart, false, 'игра уже идёт');
});

test('кто дважды подряд промолчал, встаёт из-за стола', (t) => {
  const room = table({ players: ['Аня', 'Боря', 'Вика'], balance: 5000 });
  t.after(() => room.dispose());
  room.start('u0');

  const quiet = room.hand.actingPlayer.id;
  const seatIndex = room.seatIndexOf(quiet);

  room.noteTimeout(quiet);
  assert.ok(room.seatOf(quiet), 'один пропуск — ещё не повод');
  assert.strictEqual(room.seatOf(quiet).missedTurns, 1);

  room.noteTimeout(quiet);
  assert.strictEqual(room.seats[seatIndex].leaveAfterHand, true, 'уйдёт после раздачи');

  // Доигрываем — место освобождается, фишки возвращаются на баланс.
  let guard = 0;
  while (room.hand && !room.hand.complete && guard++ < 40) {
    room.applyAction(room.hand.actingPlayer.id, 'fold');
  }
  assert.strictEqual(room.seatIndexOf(quiet), -1, 'выбыл');
  assert.ok(room.bankRef.balanceOf(quiet) > 4000, 'стек вернулся на баланс');
});

test('ответ обнуляет счётчик молчания', (t) => {
  const room = table({ players: ['Аня', 'Боря', 'Вика'] });
  t.after(() => room.dispose());
  room.start('u0');

  const actor = room.hand.actingPlayer.id;
  room.noteTimeout(actor);
  assert.strictEqual(room.seatOf(actor).missedTurns, 1);

  room.applyAction(actor, 'fold');
  assert.strictEqual(room.seatOf(actor).missedTurns, 0, 'походил — счётчик сброшен');
});
