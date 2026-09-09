'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { once } = require('node:events');

// Поднимаем настоящий сервер и играем раздачу двумя клиентами через WebSocket:
// так проверяется и самописный протокол WebSocket, и обмен командами.
const { createApp } = require('../server/index');

async function startServer(t, options = {}) {
  const server = createApp({
    botToken: '',
    devLogin: true,
    accountsFile: null,
    ...options,
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.shutdown());
  return server.address().port;
}

function connect(port) {
  const socket = new WebSocket(`ws://127.0.0.1:${port}/ws`);
  const inbox = [];
  const waiters = [];

  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    const waiter = waiters.find((w) => w.match(message));
    if (waiter) {
      waiters.splice(waiters.indexOf(waiter), 1);
      waiter.resolve(message);
    } else {
      inbox.push(message);
    }
  });

  return {
    socket,
    send: (message) => socket.send(JSON.stringify(message)),
    // Ждёт первое сообщение, подходящее под условие (в том числе уже полученное).
    wait(match, timeout = 4000) {
      const index = inbox.findIndex(match);
      if (index >= 0) return Promise.resolve(inbox.splice(index, 1)[0]);
      return new Promise((resolve, reject) => {
        const waiter = { match, resolve };
        waiters.push(waiter);
        setTimeout(() => {
          if (waiters.includes(waiter)) {
            waiters.splice(waiters.indexOf(waiter), 1);
            reject(new Error('Не дождались сообщения от сервера'));
          }
        }, timeout).unref();
      });
    },
    close: () => socket.close(),
  };
}

const byType = (type) => (message) => message.type === type;

test('двое игроков создают стол и играют раздачу', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const alice = connect(port);
  const bob = connect(port);
  await Promise.all([once(alice.socket, 'open'), once(bob.socket, 'open')]);
  t.after(() => {
    alice.close();
    bob.close();
  });

  alice.send({ type: 'auth', name: 'Аня', devId: 'alice' });
  bob.send({ type: 'auth', name: 'Боря', devId: 'bob' });
  await Promise.all([alice.wait(byType('auth_ok')), bob.wait(byType('auth_ok'))]);

  alice.send({ type: 'create_room', settings: { smallBlind: 5, bigBlind: 10, buyIn: 500, maxPlayers: 2 } });
  const joined = await alice.wait(byType('joined'));
  assert.strictEqual(joined.code.length, 5);

  bob.send({ type: 'join_room', code: joined.code });
  await bob.wait(byType('joined'));

  alice.send({ type: 'sit', seat: 0 });
  bob.send({ type: 'sit', seat: 1 });
  await alice.wait((m) => m.type === 'state' && m.seats.filter((s) => !s.empty).length === 2);

  alice.send({ type: 'start' });
  const dealt = await alice.wait((m) => m.type === 'state' && m.status === 'playing');

  // Свои карты видно, чужие — закрыты.
  const mySeat = dealt.seats[dealt.you.seatIndex];
  assert.strictEqual(mySeat.cards.length, 2);
  assert.ok(!mySeat.cards.includes('??'), 'свои карты открыты');
  const opponent = dealt.seats.find((s) => !s.empty && s.index !== dealt.you.seatIndex);
  assert.deepStrictEqual(opponent.cards, ['??', '??'], 'чужие карты скрыты');

  // Ходит тот, у кого в состоянии есть список доступных действий.
  const actor = dealt.you.legal ? alice : bob;
  const waiter = dealt.you.legal ? bob : alice;
  assert.ok(actor === alice || (await waiter.wait((m) => m.type === 'state' && Boolean(m.you.legal))));

  actor.send({ type: 'action', action: 'fold' });
  const finished = await alice.wait((m) => m.type === 'state' && m.lastResult);
  assert.strictEqual(finished.lastResult.showdown, false);
  assert.strictEqual(finished.lastResult.winners.length, 1);

  const total = finished.seats.filter((s) => !s.empty).reduce((sum, s) => sum + s.stack, 0);
  assert.strictEqual(total, 1000, 'фишки на столе сохранились');
});

test('чат долетает до всех за столом', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const host = connect(port);
  const guest = connect(port);
  await Promise.all([once(host.socket, 'open'), once(guest.socket, 'open')]);
  t.after(() => {
    host.close();
    guest.close();
  });

  host.send({ type: 'auth', name: 'Хозяин', devId: 'host' });
  guest.send({ type: 'auth', name: 'Гость', devId: 'guest' });
  await Promise.all([host.wait(byType('auth_ok')), guest.wait(byType('auth_ok'))]);

  host.send({ type: 'create_room', settings: {} });
  const { code } = await host.wait(byType('joined'));
  guest.send({ type: 'join_room', code });
  await guest.wait(byType('joined'));

  host.send({ type: 'chat', text: 'всем привет' });
  const received = await guest.wait(byType('chat'));
  assert.strictEqual(received.text, 'всем привет');
  assert.strictEqual(received.name, 'Хозяин');
});

test('неизвестный код комнаты даёт понятную ошибку', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const client = connect(port);
  await once(client.socket, 'open');
  t.after(() => client.close());

  client.send({ type: 'auth', name: 'Кто-то', devId: 'nobody' });
  await client.wait(byType('auth_ok'));
  client.send({ type: 'join_room', code: 'ZZZZZ' });
  const error = await client.wait(byType('error'));
  assert.match(error.message, /не найдена/i);
});

test('после обрыва связи игрок возвращается за свой стек', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const host = connect(port);
  const guest = connect(port);
  await Promise.all([once(host.socket, 'open'), once(guest.socket, 'open')]);
  t.after(() => {
    host.close();
    guest.close();
  });

  host.send({ type: 'auth', name: 'Хозяин', devId: 'h1' });
  guest.send({ type: 'auth', name: 'Гость', devId: 'g1' });
  await Promise.all([host.wait(byType('auth_ok')), guest.wait(byType('auth_ok'))]);

  host.send({ type: 'create_room', settings: { buyIn: 750 } });
  const { code } = await host.wait(byType('joined'));
  guest.send({ type: 'join_room', code });
  await guest.wait(byType('joined'));
  guest.send({ type: 'sit', seat: 1 });
  await guest.wait((m) => m.type === 'state' && m.you.seatIndex === 1);

  // Ждём именно закрытия сокета, а не «на глазок», иначе тест плавает.
  const closed = once(guest.socket, 'close');
  guest.close();
  await closed;
  await new Promise((resolve) => setTimeout(resolve, 50));

  // Тот же devId — сервер узнаёт игрока и сажает обратно.
  const again = connect(port);
  await once(again.socket, 'open');
  t.after(() => again.close());
  again.send({ type: 'auth', name: 'Гость', devId: 'g1' });
  await again.wait(byType('auth_ok'));
  const restored = await again.wait(byType('state'));

  assert.strictEqual(restored.code, code);
  assert.strictEqual(restored.you.seatIndex, 1);
  assert.strictEqual(restored.seats[1].stack, 750);
  assert.strictEqual(restored.seats[1].connected, true);
});

test('открытые столы видны в общем списке', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const host = connect(port);
  const stranger = connect(port);
  await Promise.all([once(host.socket, 'open'), once(stranger.socket, 'open')]);
  t.after(() => {
    host.close();
    stranger.close();
  });

  host.send({ type: 'auth', name: 'Аня', devId: 'open-host' });
  stranger.send({ type: 'auth', name: 'Прохожий', devId: 'stranger' });
  await Promise.all([host.wait(byType('auth_ok')), stranger.wait(byType('auth_ok'))]);

  host.send({ type: 'create_room', settings: { smallBlind: 25, bigBlind: 50 } });
  const { code } = await host.wait(byType('joined'));

  // Постороннему хватает списка — код спрашивать не нужно.
  stranger.send({ type: 'list_rooms' });
  const list = await stranger.wait(byType('rooms'));
  const found = list.rooms.find((room) => room.code === code);
  assert.ok(found, 'стол виден в списке');
  assert.strictEqual(found.host, 'Аня');
  assert.strictEqual(found.smallBlind, 25);

  stranger.send({ type: 'join_room', code: found.code });
  const joined = await stranger.wait(byType('joined'));
  assert.strictEqual(joined.code, code);
});

test('закрытый стол в списке не показывается', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const host = connect(port);
  const stranger = connect(port);
  await Promise.all([once(host.socket, 'open'), once(stranger.socket, 'open')]);
  t.after(() => {
    host.close();
    stranger.close();
  });

  host.send({ type: 'auth', name: 'Аня', devId: 'private-host' });
  stranger.send({ type: 'auth', name: 'Прохожий', devId: 'stranger2' });
  await Promise.all([host.wait(byType('auth_ok')), stranger.wait(byType('auth_ok'))]);

  host.send({ type: 'create_room', settings: { isPublic: false } });
  const { code } = await host.wait(byType('joined'));

  stranger.send({ type: 'list_rooms' });
  const list = await stranger.wait(byType('rooms'));
  assert.ok(!list.rooms.some((room) => room.code === code), 'закрытый стол скрыт');

  // Но по коду в него всё равно можно зайти.
  stranger.send({ type: 'join_room', code });
  assert.strictEqual((await stranger.wait(byType('joined'))).code, code);
});

test('админ выдаёт деньги на баланс по Telegram ID', { timeout: 10000 }, async (t) => {
  // Админ определяется списком ID, а не тем, кто создал стол.
  const port = await startServer(t, { devAdmin: false, adminIds: ['dev:boss'] });

  const admin = connect(port);
  const player = connect(port);
  await Promise.all([once(admin.socket, 'open'), once(player.socket, 'open')]);
  t.after(() => {
    admin.close();
    player.close();
  });

  admin.send({ type: 'auth', name: 'Админ', devId: 'boss' });
  player.send({ type: 'auth', name: 'Игрок', devId: 'player1' });
  const [adminAuth, playerAuth] = await Promise.all([
    admin.wait(byType('auth_ok')),
    player.wait(byType('auth_ok')),
  ]);
  assert.strictEqual(adminAuth.isAdmin, true);
  assert.strictEqual(playerAuth.isAdmin, false);
  const before = playerAuth.balance;

  admin.send({ type: 'admin_grant', target: 'dev:player1', amount: 2500, mode: 'add' });
  const update = await player.wait(byType('balance'));
  assert.strictEqual(update.balance, before + 2500);

  // Обычный игрок себе ничего не начислит.
  player.send({ type: 'admin_grant', target: 'dev:player1', amount: 999999, mode: 'add' });
  const denied = await player.wait(byType('error'));
  assert.match(denied.message, /только админ/);
});

test('команда /дать адресуется по ID, а не по имени', { timeout: 10000 }, async (t) => {
  const port = await startServer(t, { devAdmin: false, adminIds: ['dev:boss'] });

  const admin = connect(port);
  const first = connect(port);
  const second = connect(port);
  await Promise.all([once(admin.socket, 'open'), once(first.socket, 'open'), once(second.socket, 'open')]);
  t.after(() => {
    admin.close();
    first.close();
    second.close();
  });

  // Два тёзки: адресация по имени была бы неоднозначной.
  admin.send({ type: 'auth', name: 'Админ', devId: 'boss' });
  first.send({ type: 'auth', name: 'Саша', devId: 'sasha-1' });
  second.send({ type: 'auth', name: 'Саша', devId: 'sasha-2' });
  const auths = await Promise.all([
    admin.wait(byType('auth_ok')),
    first.wait(byType('auth_ok')),
    second.wait(byType('auth_ok')),
  ]);
  const start = auths[1].balance;

  admin.send({ type: 'create_room', settings: {} });
  await admin.wait(byType('joined'));
  // Админ пишет сумму в долларах — на баланс ложатся центы.
  admin.send({ type: 'chat', text: '/дать dev:sasha-2 7' });
  const reply = await admin.wait(byType('system'));
  assert.match(reply.text, /\$7\.00|баланс/);

  const changed = await second.wait(byType('balance'));
  assert.strictEqual(changed.balance, start + 700);

  first.send({ type: 'balance' });
  const untouched = await first.wait(byType('balance'));
  assert.strictEqual(untouched.balance, start, 'у тёзки баланс не изменился');
});

test('посадка за стол списывает вход с баланса', { timeout: 10000 }, async (t) => {
  const port = await startServer(t);

  const client = connect(port);
  await once(client.socket, 'open');
  t.after(() => client.close());

  client.send({ type: 'auth', name: 'Аня', devId: 'balance-sit' });
  const auth = await client.wait(byType('auth_ok'));

  client.send({ type: 'create_room', settings: { buyIn: 1000 } });
  await client.wait(byType('joined'));
  client.send({ type: 'sit', seat: 0 });

  const seated = await client.wait((m) => m.type === 'state' && m.you.seatIndex === 0);
  assert.strictEqual(seated.you.balance, auth.balance - 1000);
  assert.strictEqual(seated.seats[0].stack, 1000);

  client.send({ type: 'stand' });
  const stood = await client.wait((m) => m.type === 'state' && m.you.seatIndex === null);
  assert.strictEqual(stood.you.balance, auth.balance, 'фишки вернулись на баланс');
});

test('добавление и удаление ботов разрешено только администратору', { timeout: 8000 }, async t => {
  const port = await startServer(t, { devAdmin: false, adminIds: ['dev:admin-bots'] });
  const admin = connect(port), user = connect(port);
  await Promise.all([once(admin.socket, 'open'), once(user.socket, 'open')]);
  t.after(() => { admin.close(); user.close(); });
  admin.send({ type: 'auth', name: 'Admin', devId: 'admin-bots' });
  user.send({ type: 'auth', name: 'Player', devId: 'user-bots' });
  assert.equal((await admin.wait(byType('auth_ok'))).isAdmin, true);
  assert.equal((await user.wait(byType('auth_ok'))).isAdmin, false);
  admin.send({ type: 'create_room', settings: { buyIn: 500, minBuyIn: 100, maxPlayers: 8 } });
  const { code } = await admin.wait(byType('joined'));
  user.send({ type: 'join_room', code }); await user.wait(byType('joined'));
  admin.send({ type: 'admin_grant', target: 'dev:admin-bots', amount: 10000, mode: 'set' });
  await admin.wait(m => m.type === 'balance' && m.balance === 10000);
  user.send({ type: 'admin_add_bot', seat: 2, amount: 500, isAdmin: true });
  assert.match((await user.wait(byType('error'))).message, /админ/);
  admin.send({ type: 'admin_add_bot', seat: 2, amount: 500 });
  const added = await admin.wait(m => m.type === 'state' && m.seats[2]?.isBot);
  assert.equal(added.you.balance, 9500);
  assert.match(added.seats[2].name, /^Бот /);
  user.send({ type: 'admin_remove_bot', seat: 2 });
  assert.match((await user.wait(byType('error'))).message, /админ/);
  admin.send({ type: 'admin_remove_bot', seat: 2 });
  const removed = await admin.wait(m => m.type === 'state' && m.seats[2].empty && m.you.balance === 10000);
  assert.equal(removed.seats[2].empty, true);
});

test('Hilo: invalid bets, duplicate requests, reconnect and cashout preserve the ledger', { timeout: 10000 }, async (t) => {
  const port = await startServer(t, { paymentsFile: null, promoFile: null });
  const a = connect(port); await once(a.socket, 'open'); t.after(() => a.close());
  a.send({ type: 'auth', name: 'Hilo QA', devId: 'hilo-ledger' });
  const auth = await a.wait(byType('auth_ok'));
  a.send({ type: 'hl_open' }); const initial = await a.wait(byType('hl'));
  a.send({ type: 'hl_start', amount: -100, revision: initial.revision });
  await a.wait(byType('error')); const invalid = await a.wait(byType('hl'));
  assert.strictEqual(invalid.balance, auth.balance);
  a.send({ type: 'hl_start', amount: 100, revision: initial.revision });
  const live = await a.wait(byType('hl'));
  assert.strictEqual(live.balance, auth.balance - 100);
  a.send({ type: 'hl_pick', direction: 'high', revision: live.revision });
  await a.wait(byType('error')); const oldClient = await a.wait(byType('hl'));
  assert.deepStrictEqual(oldClient, live, 'old rules must not silently consume a prediction');
  a.send({ type: 'hl_start', amount: 100, revision: initial.revision });
  await a.wait(byType('error')); const duplicate = await a.wait(byType('hl'));
  assert.strictEqual(duplicate.balance, live.balance);
  const b = connect(port); await once(b.socket, 'open'); t.after(() => b.close());
  b.send({ type: 'auth', name: 'Hilo QA', devId: 'hilo-ledger' }); await b.wait(byType('auth_ok'));
  b.send({ type: 'hl_open' }); const resumed = await b.wait(byType('hl'));
  assert.deepStrictEqual(resumed, live);
  b.send({ type: 'hl_cashout', revision: resumed.revision }); const done = await b.wait(byType('hl'));
  assert.strictEqual(done.balance, auth.balance); assert.strictEqual(done.payout, 100);
  b.send({ type: 'hl_cashout', revision: resumed.revision }); await b.wait(byType('error'));
  assert.strictEqual((await b.wait(byType('hl'))).balance, auth.balance);
});


test('Crash: offline auto-stop and reconnect credit the wallet exactly once over WebSocket', { timeout: 10000 }, async t => {
  const { Accounts } = require('../server/accounts');
  const { CrashGame } = require('../server/crash/game');
  const accounts = new Accounts();
  const account = accounts.ensure({ id: 'dev:crash-network', name: 'Crash QA' });
  const game = new CrashGame({ draw: () => 3 });
  game.start(100, 2, 0, Date.now() - 20000);
  accounts.withdraw(account.id, 100);
  account.crashRound = game.snapshot();
  const port = await startServer(t, { accounts, paymentsFile: null, promoFile: null });
  for (let i = 0; i < 2; i++) {
    const client = connect(port);
    await once(client.socket, 'open');
    t.after(() => client.close());
    client.send({ type: 'auth', name: 'Crash QA', devId: 'crash-network' });
    await client.wait(byType('auth_ok'));
    client.send({ type: 'cr_open' });
    const result = await client.wait(m => m.type === 'cr' && m.phase === 'done');
    assert.equal(result.payout, 200);
    assert.equal(result.balance, 10100);
    assert.equal(result.settled, true);
    assert.equal(result.point, undefined);
    client.send({ type: 'cr_cashout', revision: result.revision });
    await client.wait(byType('error'));
    assert.equal((await client.wait(byType('cr'))).balance, 10100);
    const closed = once(client.socket, 'close');
    client.close(); await closed;
  }
});


test('Catalog: all 15 games complete through WebSocket and credit once', { timeout:20000 }, async t => {
  const port = await startServer(t, { paymentsFile:null, promoFile:null });
  const { games } = require('../public/casino-rules');
  for (const [game, definition] of Object.entries(games)) {
    const client=connect(port); await once(client.socket,'open'); t.after(()=>client.close());
    const receive=()=>client.wait(m=>m.type==='ag'&&m.game===game);
    client.send({type:'auth',name:'Catalog QA',devId:'catalog-network-'+game});
    const auth=await client.wait(byType('auth_ok'));
    client.send({type:'ag_open',game}); let round=await receive();
    const start={type:'ag_start',game,amount:100,options:definition.defaults,revision:round.revision};
    client.send(start); round=await receive();
    assert.equal(round.balance,auth.balance-100+round.payout,game);
    client.send(start); await client.wait(byType('error'));
    const duplicate=await receive(); assert.equal(duplicate.balance,round.balance,game);
    if(definition.series) {
      client.send({type:'ag_cashout',game,revision:round.revision}); round=await receive();
    } else if(game==='videopoker') {
      client.send({type:'ag_pick',game,index:[],revision:round.revision}); round=await receive();
    } else if(game==='scratch') {
      for(let index=0;index<9;index++) {
        client.send({type:'ag_pick',game,index,revision:round.revision}); round=await receive();
      }
    }
    assert.equal(round.phase,'done',game);
    assert.equal(round.balance,auth.balance-100+round.payout,game);
    client.send({type:'ag_open',game}); const reopened=await receive();
    assert.equal(reopened.balance,round.balance,game);
    assert.equal(reopened.revision,round.revision,game);
    const closed=once(client.socket,'close'); client.close(); await closed;
  }
});

test('Arcade: four games route over WebSocket, persist results, reject duplicate starts and unauthenticated requests', { timeout:10000 }, async t => {
  const port=await startServer(t,{paymentsFile:null,promoFile:null});
  const client=connect(port); await once(client.socket,'open');t.after(()=>client.close());
  client.send({type:'ag_open',game:'plinko'});assert.match((await client.wait(byType('error'))).message,/авторизоваться/);
  client.send({type:'auth',name:'Arcade QA',devId:'arcade-network'});const auth=await client.wait(byType('auth_ok'));let balance=auth.balance;
  const opts={plinko:{risk:'medium'},tower:{level:'easy'},keno:{picks:[1,2,3]},dragon:{side:'tie'}};
  for(const game of Object.keys(opts)) {
    client.send({type:'ag_open',game});const initial=await client.wait(m=>m.type==='ag'&&m.game===game);
    assert.ok(initial.config.maxBet>=100);
    const bet={type:'ag_start',game,amount:100,options:opts[game],revision:initial.revision};
    client.send(bet);let next=await client.wait(m=>m.type==='ag'&&m.game===game);
    assert.equal(next.balance,balance-100+next.payout);balance=next.balance;
    client.send(bet);await client.wait(byType('error'));const duplicate=await client.wait(m=>m.type==='ag'&&m.game===game);
    assert.equal(duplicate.balance,balance);assert.equal(duplicate.revision,next.revision);
    if(game==='tower') {
      assert.equal(next.traps,undefined);assert.deepEqual(next.revealed,[]);
      client.send({type:'ag_pick',game,index:0,revision:next.revision});next=await client.wait(m=>m.type==='ag'&&m.game===game);
      if(next.phase==='play') {client.send({type:'ag_cashout',game,revision:next.revision});next=await client.wait(m=>m.type==='ag'&&m.game===game);}
      assert.equal(next.balance,balance+next.payout);balance=next.balance;
    }
    client.send({type:'ag_open',game});const reopened=await client.wait(m=>m.type==='ag'&&m.game===game);
    assert.equal(reopened.balance,balance);assert.equal(reopened.revision,next.revision);
  }
});
