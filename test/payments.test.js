'use strict';

const test = require('node:test');
const assert = require('node:assert');
const crypto = require('node:crypto');

const { Accounts } = require('../server/accounts');
const { Payments, PaymentError } = require('../server/payments');
const { CryptoBotProvider } = require('../server/payments/cryptobot');
const { XRocketProvider } = require('../server/payments/xrocket');

const CRYPTOBOT_TOKEN = '12345:test-cryptobot-token';
const XROCKET_TOKEN = 'test-xrocket-key';

// Подпись вебхука у обоих сервисов считается одинаково: HMAC-SHA256 по сырому
// телу, ключ — SHA-256 от токена приложения.
function sign(token, rawBody) {
  const secret = crypto.createHash('sha256').update(token).digest();
  return crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
}

// Подставной fetch: отдаёт заранее заготовленные ответы и запоминает запросы.
function fakeFetch(responses) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const handler = responses.find((item) => String(url).includes(item.match));
    if (!handler) throw new Error(`Нет заготовленного ответа для ${url}`);
    const body = typeof handler.body === 'function' ? handler.body(String(url), init) : handler.body;
    return {
      status: handler.status || 200,
      text: async () => JSON.stringify(body),
    };
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

function cryptoBotInvoice(payload, overrides = {}) {
  return {
    ok: true,
    result: {
      invoice_id: 555,
      status: 'active',
      hash: 'IVoc1abc',
      asset: 'USDT',
      amount: '5',
      payload,
      currency_type: 'crypto',
      bot_invoice_url: 'https://t.me/CryptoBot?start=IVoc1abc',
      mini_app_invoice_url: 'https://t.me/CryptoBot/app?startapp=IVoc1abc',
      created_at: new Date().toISOString(),
      allow_comments: false,
      allow_anonymous: false,
      ...overrides,
    },
  };
}

function xrocketInvoice(payload, overrides = {}) {
  return {
    success: true,
    data: {
      id: 777,
      amount: 5,
      minPayment: 5,
      totalActivations: 1,
      activationsLeft: 1,
      payload,
      currency: 'USDT',
      created: new Date().toISOString(),
      status: 'active',
      expiredIn: 3600,
      link: 'https://t.me/xrocket?start=inv_777',
      ...overrides,
    },
  };
}

// Собирает связку «счета + пополнение» с одним подставным провайдером.
function setup({ provider = 'cryptobot', responses = [], options = {} } = {}) {
  const accounts = new Accounts({ startingBalance: 0 });
  accounts.ensure({ id: '42', name: 'Аня', username: 'anya' });

  const fetchImpl = fakeFetch(responses);
  const instance = provider === 'cryptobot'
    ? new CryptoBotProvider({ token: CRYPTOBOT_TOKEN, fetchImpl })
    : new XRocketProvider({ token: XROCKET_TOKEN, fetchImpl });

  const payments = new Payments({ providers: [instance], accounts, file: null, ...options });
  return { accounts, payments, fetchImpl, provider: instance };
}

const user = { id: '42', name: 'Аня', username: 'anya' };

// ——— Создание счёта ———

test('Crypto Bot: счёт создаётся и в payload уходит наш идентификатор', async () => {
  let seenPayload = null;
  const { payments, fetchImpl } = setup({
    responses: [{
      match: 'createInvoice',
      body: (url) => {
        seenPayload = new URL(url).searchParams.get('payload');
        return cryptoBotInvoice(seenPayload);
      },
    }],
  });

  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  assert.strictEqual(invoice.amount, 5);
  assert.strictEqual(invoice.chips, 5000);
  assert.strictEqual(invoice.status, 'pending');
  assert.strictEqual(invoice.url, 'https://t.me/CryptoBot/app?startapp=IVoc1abc');
  assert.strictEqual(seenPayload, invoice.id, 'в payload должен уйти id нашей записи');

  const request = fetchImpl.calls[0];
  assert.strictEqual(request.init.headers['Crypto-Pay-API-Token'], CRYPTOBOT_TOKEN);
  assert.strictEqual(new URL(request.url).searchParams.get('asset'), 'USDT');
});

test('xRocket: счёт создаётся через POST /tg-invoices', async () => {
  const { payments, fetchImpl } = setup({
    provider: 'xrocket',
    responses: [{ match: '/tg-invoices', body: (url, init) => xrocketInvoice(JSON.parse(init.body).payload) }],
  });

  const invoice = await payments.createTopUp(user, 'xrocket', 5);

  assert.strictEqual(invoice.url, 'https://t.me/xrocket?start=inv_777');
  assert.strictEqual(invoice.chips, 5000);

  const request = fetchImpl.calls[0];
  assert.strictEqual(request.init.method, 'POST');
  assert.strictEqual(request.init.headers['Rocket-Pay-Key'], XROCKET_TOKEN);
  assert.strictEqual(JSON.parse(request.init.body).numPayments, 1);
});

test('сумма вне разрешённых границ до платёжного сервиса не доходит', async () => {
  const { payments, fetchImpl } = setup({
    options: { minAmount: 1, maxAmount: 100 },
    responses: [{ match: 'createInvoice', body: cryptoBotInvoice('x') }],
  });

  await assert.rejects(() => payments.createTopUp(user, 'cryptobot', 0.5), PaymentError);
  await assert.rejects(() => payments.createTopUp(user, 'cryptobot', 1000), PaymentError);
  await assert.rejects(() => payments.createTopUp(user, 'cryptobot', 'много'), PaymentError);
  assert.strictEqual(fetchImpl.calls.length, 0, 'ни одного запроса наружу быть не должно');
});

test('неподключённый способ оплаты отвергается', async () => {
  const { payments } = setup();
  await assert.rejects(() => payments.createTopUp(user, 'xrocket', 5), PaymentError);
});

// ——— Вебхуки ———

test('Crypto Bot: вебхук с верной подписью начисляет фишки', async () => {
  const { payments, accounts } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });
  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  const rawBody = JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    request_date: new Date().toISOString(),
    payload: { invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', payload: invoice.id, paid_at: new Date().toISOString() },
  });

  const result = payments.handleWebhook('cryptobot', rawBody, sign(CRYPTOBOT_TOKEN, rawBody));

  assert.strictEqual(result.handled, true);
  assert.strictEqual(result.credited, 5000);
  assert.strictEqual(accounts.balanceOf('42'), 5000);
});

test('xRocket: вебхук с верной подписью начисляет фишки', async () => {
  const { payments, accounts } = setup({
    provider: 'xrocket',
    responses: [{ match: '/tg-invoices', body: (url, init) => xrocketInvoice(JSON.parse(init.body).payload) }],
  });
  const invoice = await payments.createTopUp(user, 'xrocket', 5);

  const rawBody = JSON.stringify({
    type: 'invoicePay',
    timestamp: new Date().toISOString(),
    data: {
      id: 777,
      amount: 5,
      currency: 'USDT',
      status: 'paid',
      payload: invoice.id,
      link: 'https://t.me/xrocket?start=inv_777',
      payment: { userId: 42, paymentNum: 1, paymentAmount: 5, paymentAmountReceived: 4.85, comment: '', paid: new Date().toISOString() },
    },
  });

  const result = payments.handleWebhook('xrocket', rawBody, sign(XROCKET_TOKEN, rawBody));

  assert.strictEqual(result.handled, true);
  assert.strictEqual(result.credited, 5000);
  assert.strictEqual(accounts.balanceOf('42'), 5000);
});

test('вебхук с чужой подписью ничего не начисляет', async () => {
  const { payments, accounts } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });
  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  const rawBody = JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    payload: { invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', payload: invoice.id },
  });

  assert.throws(() => payments.handleWebhook('cryptobot', rawBody, sign('чужой-токен', rawBody)), PaymentError);
  assert.throws(() => payments.handleWebhook('cryptobot', rawBody, 'не-подпись-вовсе'), PaymentError);
  assert.throws(() => payments.handleWebhook('cryptobot', rawBody, undefined), PaymentError);
  assert.strictEqual(accounts.balanceOf('42'), 0);
});

test('подменённое тело вебхука ломает подпись', async () => {
  const { payments, accounts } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });
  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  const honest = JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    payload: { invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', payload: invoice.id },
  });
  const signature = sign(CRYPTOBOT_TOKEN, honest);
  const tampered = honest.replace('"amount":"5"', '"amount":"5000"');

  assert.throws(() => payments.handleWebhook('cryptobot', tampered, signature), PaymentError);
  assert.strictEqual(accounts.balanceOf('42'), 0);
});

test('повторный вебхук не начисляет фишки второй раз', async () => {
  const { payments, accounts } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });
  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  const rawBody = JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    payload: { invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', payload: invoice.id },
  });
  const signature = sign(CRYPTOBOT_TOKEN, rawBody);

  const first = payments.handleWebhook('cryptobot', rawBody, signature);
  const second = payments.handleWebhook('cryptobot', rawBody, signature);

  assert.strictEqual(first.already, false);
  assert.strictEqual(second.already, true);
  assert.strictEqual(second.credited, 0);
  assert.strictEqual(accounts.balanceOf('42'), 5000, 'баланс вырос ровно один раз');
});

test('вебхук про неизвестный счёт не трогает чужие балансы', async () => {
  const { payments, accounts } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });
  await payments.createTopUp(user, 'cryptobot', 5);

  const rawBody = JSON.stringify({
    update_id: 9,
    update_type: 'invoice_paid',
    payload: { invoice_id: 999999, status: 'paid', asset: 'USDT', amount: '1000', payload: 'счёт-из-другого-приложения' },
  });

  const result = payments.handleWebhook('cryptobot', rawBody, sign(CRYPTOBOT_TOKEN, rawBody));

  assert.strictEqual(result.handled, false);
  assert.strictEqual(accounts.balanceOf('42'), 0);
});

test('события не про оплату пропускаются молча', async () => {
  const { payments } = setup();
  const rawBody = JSON.stringify({ update_id: 2, update_type: 'invoice_expired', payload: { invoice_id: 1 } });
  const result = payments.handleWebhook('cryptobot', rawBody, sign(CRYPTOBOT_TOKEN, rawBody));
  assert.strictEqual(result.handled, false);
});

// ——— Опрос как запасной путь ———

test('счёт закрывается опросом, если вебхук не дошёл', async () => {
  const { payments, accounts } = setup({
    responses: [
      { match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) },
      {
        match: 'getInvoices',
        body: () => ({ ok: true, result: { items: [{ invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', paid_at: new Date().toISOString() }] } }),
      },
    ],
  });
  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  const refreshed = await payments.refresh(invoice.id);

  assert.strictEqual(refreshed.status, 'paid');
  assert.strictEqual(accounts.balanceOf('42'), 5000);
});

test('опрос после вебхука не начисляет повторно', async () => {
  const { payments, accounts } = setup({
    responses: [
      { match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) },
      {
        match: 'getInvoices',
        body: () => ({ ok: true, result: { items: [{ invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5' }] } }),
      },
    ],
  });
  const invoice = await payments.createTopUp(user, 'cryptobot', 5);

  const rawBody = JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    payload: { invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', payload: invoice.id },
  });
  payments.handleWebhook('cryptobot', rawBody, sign(CRYPTOBOT_TOKEN, rawBody));
  await payments.refresh(invoice.id);

  assert.strictEqual(accounts.balanceOf('42'), 5000);
});

test('фишки считаются по фактически оплаченной сумме', async () => {
  const { payments, accounts } = setup({
    provider: 'xrocket',
    responses: [{ match: '/tg-invoices', body: (url, init) => xrocketInvoice(JSON.parse(init.body).payload) }],
  });
  const invoice = await payments.createTopUp(user, 'xrocket', 5);

  // Игрок отправил больше, чем просили: начисляем по факту, а не по счёту.
  const rawBody = JSON.stringify({
    type: 'invoicePay',
    timestamp: new Date().toISOString(),
    data: {
      id: 777,
      amount: 5,
      currency: 'USDT',
      status: 'paid',
      payload: invoice.id,
      payment: { userId: 42, paymentNum: 1, paymentAmount: 7.5, paymentAmountReceived: 7.3, paid: new Date().toISOString() },
    },
  });

  payments.handleWebhook('xrocket', rawBody, sign(XROCKET_TOKEN, rawBody));

  assert.strictEqual(accounts.balanceOf('42'), 7500);
});

test('больше пяти неоплаченных счетов игроку не выдаётся', async () => {
  const { payments } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });

  for (let i = 0; i < 5; i++) await payments.createTopUp(user, 'cryptobot', 1);
  await assert.rejects(() => payments.createTopUp(user, 'cryptobot', 1), PaymentError);
});

test('счёт заводится даже игроку, которого ещё нет в списке счетов', async () => {
  const { payments, accounts } = setup({
    responses: [{ match: 'createInvoice', body: (url) => cryptoBotInvoice(new URL(url).searchParams.get('payload')) }],
  });
  const newcomer = { id: '777', name: 'Новичок', username: null };
  const invoice = await payments.createTopUp(newcomer, 'cryptobot', 5);

  const rawBody = JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    payload: { invoice_id: 555, status: 'paid', asset: 'USDT', amount: '5', payload: invoice.id },
  });
  payments.handleWebhook('cryptobot', rawBody, sign(CRYPTOBOT_TOKEN, rawBody));

  assert.strictEqual(accounts.balanceOf('777'), 5000);
});
