'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { Room, RoomError, describeCombination } = require('../server/room');
const { stringToCard } = require('../server/poker/cards');

const cards = (line) => line.split(' ').map(stringToCard);

function table({ settings = {}, players = ['Аня', 'Боря'] } = {}) {
  const host = { id: 'u0', name: players[0] };
  const room = new Room('TEST1', host, { buyIn: 1000, smallBlind: 5, bigBlind: 10, ...settings });
  players.slice(1).forEach((name, i) => room.addMember({ id: `u${i + 1}`, name }));
  players.forEach((_, i) => room.sit(`u${i}`, i));
  return room;
}

test('хозяин выдаёт фишки командой из чата', (t) => {
  const room = table();
  t.after(() => room.dispose());

  const reply = room.chat('u0', '/дать Боря 500');
  assert.match(reply, /Боря/);
  assert.strictEqual(room.seatOf('u1').stack, 1500);
});

test('фишки можно выдать по номеру места', (t) => {
  const room = table();
  t.after(() => room.dispose());

  room.chat('u0', '/дать 2 250');
  assert.strictEqual(room.seatOf('u1').stack, 1250);
});

test('команда /стек выставляет точный стек, /забрать списывает', (t) => {
  const room = table();
  t.after(() => room.dispose());

  room.chat('u0', '/стек Боря 300');
  assert.strictEqual(room.seatOf('u1').stack, 300);

  room.chat('u0', '/забрать Боря 100');
  assert.strictEqual(room.seatOf('u1').stack, 200);

  assert.throws(() => room.chat('u0', '/забрать Боря 5000'), RoomError);
});

test('команда /всем раздаёт фишки всем за столом', (t) => {
  const room = table({ players: ['Аня', 'Боря', 'Вика'] });
  t.after(() => room.dispose());

  room.chat('u0', '/всем 200');
  assert.deepStrictEqual(
    room.seats.filter(Boolean).map((seat) => seat.stack),
    [1200, 1200, 1200]
  );
});

test('фишки выдаёт только хозяин стола', (t) => {
  const room = table();
  t.after(() => room.dispose());

  assert.throws(() => room.chat('u1', '/дать Аня 1000'), /только хозяин/);
  assert.strictEqual(room.seatOf('u0').stack, 1000);
});

test('неизвестная команда и неизвестный игрок дают понятную ошибку', (t) => {
  const room = table();
  t.after(() => room.dispose());

  assert.throws(() => room.chat('u0', '/чтототакое'), /Неизвестная команда/);
  assert.throws(() => room.chat('u0', '/дать Петя 100'), /нет игрока/);
});

test('во время раздачи фишки начисляются после её конца', (t) => {
  const room = table();
  t.after(() => room.dispose());
  room.start('u0');

  const before = room.hand.player('u1').stack;
  room.chat('u0', '/дать Боря 500');
  assert.strictEqual(room.hand.player('u1').stack, before, 'посреди раздачи стек не меняется');

  // Хедз-ап: баттон пасует, раздача заканчивается, начисление применяется.
  room.applyAction(room.hand.actingPlayer.id, 'fold');
  assert.strictEqual(room.seatOf('u1').stack + room.seatOf('u0').stack, 2500);
  assert.ok(room.seatOf('u1').stack >= 1500);
});

test('игрок без фишек возвращается в игру после выдачи', (t) => {
  const room = table();
  t.after(() => room.dispose());

  room.chat('u0', '/стек Боря 0');
  room.seatOf('u1').sittingOut = true;
  room.seatOf('u1').brokeSitOut = true;

  room.chat('u0', '/дать Боря 800');
  assert.strictEqual(room.seatOf('u1').stack, 800);
  assert.strictEqual(room.seatOf('u1').sittingOut, false);
});

test('тот, кто пропускает раздачи по своей воле, так и остаётся вне игры', (t) => {
  const room = table();
  t.after(() => room.dispose());

  room.setSittingOut('u1', true);
  room.chat('u0', '/дать Боря 500');
  assert.strictEqual(room.seatOf('u1').sittingOut, true, 'решение игрока не отменяется выдачей фишек');
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

test('команда /стек посреди раздачи выставляет ровно указанный стек', (t) => {
  const room = table();
  t.after(() => room.dispose());
  room.start('u0');

  room.chat('u0', '/стек Боря 1234');
  assert.notStrictEqual(room.seatOf('u1').stack, 1234, 'посреди раздачи стек ещё прежний');

  room.applyAction(room.hand.actingPlayer.id, 'fold');
  assert.strictEqual(room.seatOf('u1').stack, 1234, 'после раздачи ровно столько, сколько выставили');
});
