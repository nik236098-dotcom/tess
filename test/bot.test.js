'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { Room } = require('../server/room');
const { Hand } = require('../server/poker/hand');
const { Accounts } = require('../server/accounts');
const { stringToCard } = require('../server/poker/cards');
const { observe, equity, chooseAction, startingStrength } = require('../server/poker/bot');
const cards = s => s.split(' ').map(stringToCard);
function rng(seed = 9821) { return () => ((seed = Math.imul(seed, 1664525) + 1013904223 >>> 0) / 4294967296); }
function setup(t, options = {}) {
  const bank = new Accounts({ startingBalance: 10000 });
  const owner = { id: 'owner', name: 'Admin' }; bank.ensure(owner);
  const room = new Room('TEST', owner, { maxPlayers: 8, minBuyIn: 100, buyIn: 1000 }, { bank, botDelay: 5, ...options });
  t.after(() => room.dispose());
  return { room, bank };
}
function observation(hole, board = '', variant = 'holdem') {
  const hand = new Hand({ players: [{ id: 'a', stack: 1000 }, { id: 'b', stack: 1000 }], dealerIndex: 0, smallBlind: 5, bigBlind: 10, variant, rng: rng() });
  hand.player('a').hole = cards(hole); hand.board = board ? cards(board) : [];
  hand.phase = board ? 'river' : 'preflop';
  return observe(hand, 'a');
}

test('бот получает только свои карты, борд и публичные данные', () => {
  const hand = new Hand({ players: [{ id: 'a', stack: 1000 }, { id: 'b', stack: 1000 }], dealerIndex: 0, smallBlind: 5, bigBlind: 10 });
  const before = observe(hand, 'a');
  hand.player('b').hole = [0, 1]; hand.deck.reverse(); hand.deckPos = 30;
  assert.deepEqual(observe(hand, 'a'), before);
  assert.equal('hole' in before.players[1], false);
  assert.equal('deck' in before, false);
});

test('AA выше 72o; сильная рука открывается рейзом, мусор пасует на рейз', () => {
  assert.ok(startingStrength(cards('As Ah')) > startingStrength(cards('7c 2d')));
  assert.equal(chooseAction(observation('As Ah'), { rng: rng(), iterations: 90 }).action, 'raise');
  const weak = observation('7c 2d'); weak.currentBet = 60; weak.legal.callAmount = 55;
  assert.equal(chooseAction(weak, { rng: rng() }).action, 'fold');
});

test('натсовый флеш ценится, а омаха требует ровно две карманные карты', () => {
  const nuts = observation('As Ks', 'Qs 8s 3s 2d 7h');
  assert.equal(equity(nuts, { rng: rng(), iterations: 70 }), 1);
  assert.equal(chooseAction(nuts, { rng: rng(), iterations: 70 }).action, 'raise');
  const omaha = observation('As Kd Qh Jc', '2s 4s 6s 8s Ts', 'omaha');
  assert.ok(equity(omaha, { rng: rng(), iterations: 120, budgetMs: 2000 }) < .8, 'одного туза пик недостаточно для флеша');
});

test('в омахе и холдеме решения проходят проверку движка, фишки сохраняются', () => {
  for (const variant of ['holdem', 'omaha']) {
    for (let game = 0; game < 4; game++) {
      const hand = new Hand({ players: Array.from({ length: 4 }, (_, i) => ({ id: String(i), stack: 100 + i * 25 })), dealerIndex: game, smallBlind: 5, bigBlind: 10, variant, rng: rng(33 + game) });
      let actions = 0;
      while (!hand.complete && actions++ < 120) {
        const id = hand.actingPlayer.id;
        const decision = chooseAction(observe(hand, id), { rng: rng(game * 129 + actions), iterations: 24, budgetMs: 20 });
        assert.doesNotThrow(() => hand.act(id, decision.action, decision.amount));
      }
      assert.ok(hand.complete);
      assert.equal(hand.result.players.reduce((n, p) => n + p.stack, 0), 550);
    }
  }
});

test('посадка и удаление бота сохраняют баланс владельца; невалидное место не списывает деньги', t => {
  const { room, bank } = setup(t);
  for (const index of [-1, 1.5, 8, '2', null]) assert.throws(() => room.addBot('owner', index, 500));
  assert.equal(bank.balanceOf('owner'), 10000);
  const id = room.addBot('owner', 2, 500);
  assert.equal(bank.balanceOf('owner'), 9500);
  assert.equal(room.stateFor('owner').seats[2].isBot, true);
  assert.throws(() => room.addBot('owner', 2, 500), /занято/);
  assert.equal(bank.balanceOf('owner'), 9500);
  room.removeBot(2);
  assert.equal(bank.balanceOf('owner'), 10000);
  assert.equal(room.members.has(id), false);
});

test('боты не начинают раздачи без сидящего человека и уходят с владельцем', t => {
  const { room, bank } = setup(t); room.autoStart = true;
  room.addBot('owner', 2, 500); room.addBot('owner', 4, 500);
  assert.equal(room.hand, null);
  room.removeMember('owner');
  assert.equal(room.seats.filter(Boolean).length, 0);
  assert.equal(bank.balanceOf('owner'), 10000);
});

test('удаление во время раздачи возвращает остатки после расчёта банка', t => {
  const { room, bank } = setup(t, { botRunner: () => new Promise(() => {}) });
  room.sit('owner', 0, 500); const bot = room.addBot('owner', 1, 500); room.addBot('owner', 2, 500);
  room.start('owner'); room.removeBot(1);
  while (!room.hand.complete) room.applyAction(room.hand.actingPlayer.id, 'fold');
  assert.equal(room.seatOf(bot), null);
  room.cashOutAll();
  assert.equal(bank.balanceOf('owner'), 10000);
});

test('отменённый ответ бота не применяется к следующему ходу', async t => {
  let resolveDecision;
  const { room } = setup(t, { botRunner: () => new Promise(resolve => { resolveDecision = resolve; }) });
  room.sit('owner', 0, 500); room.addBot('owner', 1, 500); room.start('owner');
  room.applyAction('owner', 'call');
  assert.equal(typeof resolveDecision, 'function');
  room.removeBot(1); const handNumber = room.handNumber;
  resolveDecision({ action: 'raise', amount: 400 });
  await new Promise(resolve => setTimeout(resolve, 25));
  assert.equal(room.handNumber, handNumber); assert.equal(room.seats[1], null);
});

test('настоящий worker самостоятельно отвечает человеку', { timeout: 6000 }, async t => {
  const { room } = setup(t);
  room.sit('owner', 0, 500); room.addBot('owner', 1, 500); room.start('owner');
  room.applyAction('owner', 'call');
  const started = Date.now();
  while (!room.hand.complete && room.hand.actingPlayer.id !== 'owner') {
    await once(room, 'update');
  }
  assert.ok(Date.now() - started < 4000);
  assert.ok(room.botHistory.some(e => e.id.startsWith('bot:')));
});
