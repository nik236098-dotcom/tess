'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { Accounts } = require('../server/accounts');
const { Payments } = require('../server/payments');
const { Activity } = require('../server/activity');
const { TelegramBot } = require('../server/telegram-bot');
const { createArcadeService } = require('../server/arcade/service');
function setup(file = null) {
  const accounts = new Accounts({ file, admins: ['1'], startingBalance: 100000 });
  const provider = { id: 'cryptobot', title: 'Crypto Bot', currency: 'USDT', supportsPayout: true,
    createInvoice: async () => ({ id: 'invoice', url: 'https://t.me/invoice' }), payout: async () => { throw Error('must not auto-pay'); } };
  const payments = new Payments({ accounts, providers: [provider], manualPayouts: true });
  const activity = new Activity({ accounts, payments, botUsername: 'croco_test' });
  activity.register({ id: '1', name: 'Admin' }); activity.register({ id: '2', name: 'Player' }, 'ref_1');
  activity.register({ id: '3', name: 'Other' });
  const calls = []; const bot = new TelegramBot({ token: 'fake', accounts, payments, activity, appUrl: 'https://example.com', supportUrl: 'https://t.me/support', env: {}, call: async (method, body) => { calls.push({ method, body }); return { message_id: 1 }; } });
  return { accounts, payments, activity, bot, calls };
}
test('referrer binds once on first registration; self links and existing users cannot be rebound', () => {
  const { activity, accounts } = setup(); activity.register({ id: '2' }, 'ref_3'); activity.register({ id: '3' }, 'ref_1'); activity.register({ id: '4' }, 'ref_4');
  assert.equal(accounts.get('2').referrerId, '1'); assert.equal(accounts.get('3').referrerId, undefined); assert.equal(accounts.get('4').referrerId, undefined);
});
test('immediate 10% uses per-referral high watermark; winnings carry forward, claims cannot duplicate', () => {
  const { activity, accounts } = setup();
  const round = (id, bet, payout) => activity.round({ id, userId: '2', game: 'mines', bet, payout });
  round('a', 10000, 0); assert.equal(accounts.get('1').refBalance, 1000);
  activity.claim('1'); assert.equal(accounts.get('1').balance, 101000); assert.throws(() => activity.claim('1'), /Нет доступных/);
  round('b', 10000, 25000); assert.equal(accounts.get('1').refBalance, 0);
  round('c', 20000, 0); assert.equal(accounts.get('1').refBalance, 500);
  assert.equal(round('c', 20000, 0), null); assert.equal(accounts.get('1').refBalance, 500);
  assert.equal(activity.referrals('1').earned, 1500);
});
test('all completed stakes include losses, pushes and separate Plinko balls; poker losses do not become house revenue', () => {
  const { activity, accounts } = setup();
  activity.round({ userId: '2', game: 'holdem', bet: 1000, payout: 0 }); assert.equal(accounts.get('1').refBalance || 0, 0);
  activity.round({ userId: '2', game: 'blackjack', bet: 1000, payout: 1000 });
  const service = createArcadeService({ accounts, noteWin() {}, noteRound: r => activity.round(r), rng: n => 0 });
  accounts.atomic(() => service.handle({ user: { id: '2' }, send() {} }, { type: 'ag_start', game: 'plinko', amount: 100, options: { risk: 'low', count: 3 }, revision: 0 }));
  const rows = activity.history('2').rows; assert.equal(rows.length, 5); assert.equal(rows.filter(r => r.game === 'plinko').length, 3); assert.equal(rows.find(r => r.game === 'blackjack').result, 'push');
});
test('referral transfers, stakes and manual withdrawal decisions survive reload of one atomic wallet file', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'croco-ledger-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'accounts.json'); let h = setup(file);
  h.activity.round({ id: 'round', userId: '2', game: 'nvuti', bet: 1000, payout: 0 }); h.activity.claim('1');
  const payout = await h.payments.createPayout({ id: '2' }, 'cryptobot', 1000); assert.equal(payout.status, 'review');
  h = setup(file); assert.equal(h.accounts.get('2').balance, 99000); assert.equal(h.payments.getPayout(payout.id).status, 'review');
  h.payments.reviewPayout(payout.id, 'failed', '1'); assert.equal(h.accounts.get('2').balance, 100000);
  assert.throws(() => h.payments.reviewPayout(payout.id, 'done', '1'), /уже обработана/);
  h = setup(file); assert.equal(h.payments.getPayout(payout.id).status, 'failed'); assert.equal(h.activity.history('2').rows.length, 1); assert.equal(h.activity.transactions('1').rows[0].kind, 'referral');
});
test('only admin can decide withdrawals; paid status does not trigger another external transfer or refund', async () => {
  const h = setup(); const r = await h.payments.createPayout({ id: '2' }, 'cryptobot', 2500);
  assert.throws(() => h.payments.reviewPayout(r.id, 'done', '2'), /администратор/);
  h.payments.reviewPayout(r.id, 'done', '1'); assert.equal(h.accounts.get('2').balance, 97500);
  assert.throws(() => h.payments.reviewPayout(r.id, 'failed', '1'), /уже обработана/);
  assert.equal((await h.payments.retryPayout(r.id)).status, 'done'); // no second external transfer
});
test('failed persistence rolls back referral claim, payout reservation, rejection and all notifications', async () => {
  const h = setup(); h.activity.round({ userId: '2', game: 'nvuti', bet: 1000, payout: 0 });
  const changed = []; h.accounts.onChange = a => changed.push(a.id);
  const save = h.accounts.flush.bind(h.accounts); h.accounts.flush = () => { throw Error('disk full'); };
  assert.throws(() => h.activity.claim('1'), /disk full/); assert.equal(h.accounts.get('1').refBalance, 100); assert.equal(h.accounts.get('1').balance, 100000); assert.equal(h.activity.data.transfers.length, 0);
  await assert.rejects(() => h.payments.createPayout({ id: '2' }, 'cryptobot', 1000), /disk full/); assert.equal(h.accounts.get('2').balance, 100000); assert.equal(h.payments.payouts.size, 0); assert.deepEqual(changed, []);
  h.accounts.flush = save; const r = await h.payments.createPayout({ id: '2' }, 'cryptobot', 1000); changed.length = 0;
  h.accounts.flush = () => { throw Error('disk full'); };
  assert.throws(() => h.payments.reviewPayout(r.id, 'failed', '1'), /disk full/); assert.equal(h.accounts.get('2').balance, 99000); assert.equal(h.payments.getPayout(r.id).status, 'review'); assert.deepEqual(changed, []);
});
test('deposit webhook credit and marker are committed together and idempotent after restart', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'croco-deposit-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'accounts.json'); let h = setup(file); const i = await h.payments.createTopUp({ id: '2' }, 'cryptobot', 5);
  h.payments.credit(h.payments.get(i.id), { paidAmount: 5 }); h = setup(file);
  assert.equal(h.accounts.get('2').balance, 100500); assert.equal(h.payments.credit(h.payments.get(i.id), { paidAmount: 5 }).already, true); assert.equal(h.accounts.get('2').balance, 100500);
  assert.equal(h.activity.referrals('1').deposits, 500); assert.equal(h.activity.cash().incoming, 500);
});
test('pending payouts and deposits do not count as completed cash movement; revenue differs from cash flow', async () => {
  const h = setup(); await h.payments.createTopUp({ id: '2' }, 'cryptobot', 5); await h.payments.createPayout({ id: '2' }, 'cryptobot', 1000);
  h.activity.round({ userId: '2', game: 'crash', bet: 1000, payout: 0 });
  const report = h.activity.cash(); assert.equal(report.incoming, 0); assert.equal(report.outgoing, 0); assert.equal(report.pending, 1000); assert.equal(report.gameRevenue, 1000); assert.equal(report.result, 900);
});
test('three private slots reject every non-admin action without touching balances', () => {
  const h = setup(), service = createArcadeService({ accounts: h.accounts, noteWin() {} });
  for (const game of ['abyss', 'cryo', 'midnight']) for (const type of ['ag_open', 'ag_start', 'ag_pick', 'ag_cashout']) assert.throws(() => service.handle({ user: { id: '2' }, send() {} }, { type, game, amount: 20, revision: 0 }), /администратору/);
  for (const game of ['abyss', 'cryo', 'midnight']) assert.doesNotThrow(() => service.handle({ user: { id: '1' }, send() {} }, { type: 'ag_open', game }));
  assert.equal(h.accounts.get('2').balance, 100000);
});
test('Telegram rejects forged admin commands and private history callbacks', async () => {
  const h = setup();
  for (const text of ['/stats 1', '/balance 1', '/ref 1', '/kassa']) await h.bot.handle({ message: { from: { id: 2, first_name: 'Player' }, chat: { id: 2, type: 'private' }, text } });
  await h.bot.handle({ callback_query: { id: 'cb', from: { id: 2 }, data: 'stats:1:0', message: { chat: { id: 2, type: 'private' } } } });
  const replies = h.calls.filter(c => c.method === 'sendMessage'); assert.equal(replies.length, 5); assert.ok(replies.every(c => /администратор|Нет доступа/.test(c.body.text)));
});
test('Telegram payout decisions require an admin in the configured channel and change player state exactly once', async () => {
  const h = setup(); h.activity.data.channels.payouts = '-10099'; const r = await h.payments.createPayout({ id: '2' }, 'cryptobot', 1000);
  const callback = (from, chat, status) => ({ callback_query: { id: 'cb', from: { id: from }, data: `pay:${r.id}:${status}`, message: { message_id: 1, chat: { id: chat, type: 'channel' } } } });
  await h.bot.handle(callback(2, '-10099', 'failed')); assert.equal(h.payments.getPayout(r.id).status, 'review');
  await h.bot.handle(callback(1, '-10098', 'failed')); assert.equal(h.payments.getPayout(r.id).status, 'review');
  await h.bot.handle(callback(1, '-10099', 'failed')); assert.equal(h.payments.getPayout(r.id).status, 'failed'); assert.equal(h.accounts.get('2').balance, 100000);
  await h.bot.handle(callback(1, '-10099', 'done')); assert.equal(h.accounts.get('2').balance, 100000);
  assert.ok(h.calls.some(c => c.method === 'editMessageText' && /Отказано/.test(c.body.text)));
});
test('Telegram start includes bundled crocodile photo and profile, referrals, support and play controls', async () => {
  const h = setup(); await h.bot.handle({ message: { from: { id: 4, first_name: 'New' }, chat: { id: 4, type: 'private' }, text: '/start ref_1' } });
  assert.equal(h.accounts.get('4').referrerId, '1'); const photo = h.calls.find(c => c.method === 'sendPhoto'); assert.ok(photo);
  assert.equal(photo.body.reply_markup.inline_keyboard.flat().length, 4);
});
