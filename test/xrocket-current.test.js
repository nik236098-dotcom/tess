'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { XRocketProvider, CURRENT_MAINNET, CURRENT_TESTNET, MAINNET } = require('../server/payments/xrocket');
const { Accounts } = require('../server/accounts');
const { Payments } = require('../server/payments');
const token = 'eyJhbGciOiJIUzI1NiJ9.eyJhcHBJZCI6ImFwcF90ZXN0In0.signature';
const invoice = { id: 'inv_test', priceAmount: '25.00', priceCurrency: 'USDT', status: 'active', clientInvoiceId: 'local-id', links: { telegramBotLink: 'https://t.me/xRocket?start=inv_test' } };
function response(data, status = 200) { return new Response(JSON.stringify(data), { status }); }

test('current token uses Bearer on production/testnet; legacy credentials retain old protocol', async () => {
  const calls = [];
  const p = new XRocketProvider({ token, fetchImpl: async (url, init) => { calls.push({ url, init }); return response({ id: 'app' }); } });
  await p.getMe(); assert.equal(p.apiVersion, 'current');
  assert.equal(calls[0].url, CURRENT_MAINNET + '/api/v1/app-info');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer ' + token);
  assert.equal(calls[0].init.headers['Rocket-Pay-Key'], undefined);
  assert.equal(new XRocketProvider({ token, testnet: true }).baseUrl, CURRENT_TESTNET);
  assert.equal(new XRocketProvider({ token: 'legacy-key' }).baseUrl, MAINNET);
  assert.equal(new XRocketProvider({ token: 'opaque', apiVersion: 'current' }).baseUrl, CURRENT_MAINNET);
});

test('create invoice uses current field names, decimal strings and unwrapped 201 result', async () => {
  let body;
  const p = new XRocketProvider({ token, returnUrl: 'https://example.com', fetchImpl: async (url, init) => {
    assert.equal(url, CURRENT_MAINNET + '/api/v1/invoices'); assert.equal(init.method, 'POST'); body = JSON.parse(init.body); return response(invoice, 201);
  } });
  const r = await p.createInvoice({ amount: 25, payload: 'local-id', description: 'Top up' });
  assert.equal(body.priceAmount, '25'); assert.equal(body.priceCurrency, 'USDT');
  assert.deepEqual(body.payCurrencies, ['USDT']); assert.equal(body.clientInvoiceId, 'local-id');
  assert.equal(body.expiresIn, 3600); assert.equal(body.url.successUrl, 'https://example.com');
  assert.equal(body.callbackUrl, undefined); assert.equal(body.numPayments, undefined);
  assert.equal(r.url, invoice.links.telegramBotLink); assert.equal(r.amount, 25);
});

test('polling shares identical reads and credits the full fixed invoice once', async () => {
  let reads = 0;
  const p = new XRocketProvider({ token, fetchImpl: async url => {
    assert.ok(url.includes('/api/v1/invoice?invoiceId=inv_test')); reads++; return response({ ...invoice, status: 'paid' });
  } });
  const accounts = new Accounts({ file: null, startingBalance: 0 }); accounts.ensure({ id: '1' });
  const payments = new Payments({ accounts, providers: [p] });
  payments.invoices.set('local-id', { id: 'local-id', invoiceId: 'inv_test', provider: 'xrocket', userId: '1', amount: 25, currency: 'USDT', cents: 2500, status: 'pending', expiresAt: Date.now() + 60000 });
  await Promise.all([payments.refresh('local-id'), payments.refresh('local-id')]);
  assert.equal(reads, 1); assert.equal(accounts.balanceOf('1'), 2500);
  await payments.refresh('local-id'); assert.equal(accounts.balanceOf('1'), 2500);
});

test('current webhooks require dedicated secret, fresh timestamp and exact signature version', () => {
  const p = new XRocketProvider({ token, webhookToken: 'webhook-secret' });
  const raw = Buffer.from(JSON.stringify({ id: 'event', type: 'invoice', data: { event: 'invoice_status_changed', invoice: { ...invoice, status: 'paid' } } }));
  const timestamp = String(Date.now()); const headers = { 'signature-version': 'v1', 'signature-timestamp': timestamp };
  const sign = secret => crypto.createHmac('sha256', secret).update(timestamp + '.').update(raw).digest('hex');
  assert.equal(p.verifyWebhook(raw, sign('webhook-secret'), headers), true);
  assert.equal(p.verifyWebhook(raw, sign(token), headers), false);
  assert.equal(p.verifyWebhook(Buffer.concat([raw, Buffer.from(' ')]), sign('webhook-secret'), headers), false);
  assert.equal(p.verifyWebhook(raw, sign('webhook-secret'), { ...headers, 'signature-version': 'v2' }), false);
  assert.equal(p.verifyWebhook(raw, sign('webhook-secret'), { ...headers, 'signature-timestamp': '1000000000000' }), false);
  assert.equal(new XRocketProvider({ token }).verifyWebhook(raw, sign('webhook-secret'), headers), false);
  assert.equal(p.parseWebhook(raw).status, 'paid');
  assert.equal(p.parseWebhook(JSON.stringify({ type: 'invoice', data: { event: 'payment_status_changed', invoice: { id: 'inv_test', status: 'paid' } } })), null);
});

test('pending payouts are never reported paid and retries query the same client ID first', async () => {
  const calls = []; let phase = 0;
  const p = new XRocketProvider({ token, fetchImpl: async (url, init) => {
    calls.push({ url, init });
    if (url.includes('payout?')) return phase ? response({ payoutId: 'p1', amount: '10', status: 'finished' }) : response({ type: 'not_found' }, 404);
    const body = JSON.parse(init.body); assert.equal(body.targetType, 'telegram_user_id'); assert.equal(body.target, '123'); assert.equal(body.clientPayoutId, 'stable'); assert.equal(body.amount, '10');
    return response({ payoutId: 'p1', amount: '10', status: 'pending' }, 201);
  } });
  await assert.rejects(p.payout({ userId: 123, amount: 10, spendId: 'stable' }), e => e.ambiguous);
  phase = 1;
  const r = await p.payout({ userId: 123, amount: 10, spendId: 'stable' }); assert.equal(r.status, 'completed');
  assert.equal(calls.filter(c => c.init.method === 'POST').length, 1);
});

test('current HTTP errors are rejected without silently falling back to Legacy', async () => {
  let calls = 0;
  const p = new XRocketProvider({ token, fetchImpl: async () => { calls++; return response({ type: 'unauthorized', title: 'Unauthorized' }, 401); } });
  await assert.rejects(p.getMe(), /HTTP 401/); assert.equal(calls, 1);
  const broken = new XRocketProvider({ token, fetchImpl: async () => response({ id: 'inv', status: 'paid' }) });
  await assert.rejects(broken.getInvoice('inv'), /неполный счёт/);
});
