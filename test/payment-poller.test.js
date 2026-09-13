'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const { createPaymentPoller } = require('../server/payments/poller');
const { Accounts } = require('../server/accounts');
const { Payments, createPayments } = require('../server/payments');

test('background polling credits without client or webhook and never twice', async () => {
  const accounts = new Accounts({ file: null, startingBalance: 0 }); accounts.ensure({ id: '1', name: 'Player' });
  let checks = 0;
  const provider = { id: 'cryptobot', title: 'Crypto Bot', currency: 'USDT', createInvoice: async () => ({ id: 'remote', url: 'https://t.me/pay' }), getInvoice: async () => { checks++; return { status: 'paid', paidAmount: 25 }; } };
  const payments = new Payments({ accounts, providers: [provider] });
  const invoice = await payments.createTopUp({ id: '1' }, 'cryptobot', 25);
  const poller = createPaymentPoller(payments);
  await poller.tick(); await poller.tick();
  assert.equal(accounts.balanceOf('1'), 2500); assert.equal(checks, 1);
  assert.equal(payments.get(invoice.id).status, 'paid'); poller.stop();
});

test('poller serializes work, retries failures and stops before credit on shutdown', async () => {
  let clock = 100000, release, checks = 0;
  const records = new Map([['one', { id: 'one', provider: 'xrocket', invoiceId: 'r', createdAt: clock, status: 'pending' }]]);
  const payments = { invoices: records, providers: new Map([['xrocket', {}]]), refresh: async (_id, { shouldStop }) => { checks++; await new Promise(r => { release = r; }); assert.ok(shouldStop()); } };
  const poller = createPaymentPoller(payments, { now: () => clock });
  const running = poller.tick(); await poller.tick(); assert.equal(checks, 1);
  poller.stop(); release(); await running; await poller.tick(); assert.equal(checks, 1);
  let attempts = 0;
  const retry = createPaymentPoller({ ...payments, refresh: async () => { attempts++; throw Error('offline'); } }, { now: () => clock, log() {} });
  await retry.tick(); await retry.tick(); assert.equal(attempts, 1);
  clock += 60001; await retry.tick(); assert.equal(attempts, 2); retry.stop();
});

test('only provider tokens enable USDT deposits and manual withdrawal requests', () => {
  const accounts = new Accounts({ file: null });
  const payments = createPayments({ accounts, env: { CRYPTOBOT_TOKEN: 'fake-c', XROCKET_TOKEN: 'fake-x' } });
  const config = payments.describe();
  assert.equal(config.enabled, true); assert.equal(config.payout.enabled, true);
  assert.equal(config.providers.length, 2); assert.ok(config.providers.every(p => p.currency === 'USDT'));
  assert.equal(payments.manualPayouts, true); assert.deepEqual(config.presets, [10, 25, 50, 100]);
  assert.ok(!JSON.stringify(config).includes('fake-'));
});
