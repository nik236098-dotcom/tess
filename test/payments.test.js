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
    // Обрыв связи: ответа нет вообще, и что стало с запросом — неизвестно.
    if (handler.throws) throw handler.throws;
    // await — чтобы заготовка могла быть асинхронной и придержать ответ.
    const body = typeof handler.body === 'function' ? await handler.body(String(url), init) : handler.body;
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
  assert.strictEqual(invoice.cents, 500, '5 USDT = $5.00');
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
  assert.strictEqual(invoice.cents, 500, '5 USDT = $5.00');

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

test('Crypto Bot: вебхук с верной подписью зачисляет деньги', async () => {
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
  assert.strictEqual(result.credited, 500);
  assert.strictEqual(accounts.balanceOf('42'), 500);
});

test('xRocket: вебхук с верной подписью зачисляет деньги', async () => {
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
  assert.strictEqual(result.credited, 500);
  assert.strictEqual(accounts.balanceOf('42'), 500);
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

test('повторный вебхук не зачисляет деньги второй раз', async () => {
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
  assert.strictEqual(accounts.balanceOf('42'), 500, 'баланс вырос ровно один раз');
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
  assert.strictEqual(accounts.balanceOf('42'), 500);
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

  assert.strictEqual(accounts.balanceOf('42'), 500);
});

test('зачисляем по фактически оплаченной сумме', async () => {
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

  assert.strictEqual(accounts.balanceOf('42'), 750, '7.5 USDT = $7.50');
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

  assert.strictEqual(accounts.balanceOf('777'), 500);
});

// ——— Вывод средств ———
//
// Здесь ошибка стоит настоящих денег, поэтому проверяем обе развилки:
// внятный отказ сервиса (деньги вернуть) и оборванную связь (не возвращать).

const networkError = () => Object.assign(new Error('socket hang up'), { name: 'TypeError' });

function payoutSetup({ responses = [], balance = 10000, options = {} } = {}) {
  const kit = setup({ responses, options });
  kit.accounts.deposit('42', balance);
  return kit;
}

test('вывод списывает деньги и уходит в платёжный сервис', async () => {
  const { payments, accounts, fetchImpl } = payoutSetup({
    responses: [{ match: 'transfer', body: { ok: true, result: { transfer_id: 9001, status: 'completed', amount: '25' } } }],
  });

  const payout = await payments.createPayout(user, 'cryptobot', 2500);

  assert.strictEqual(payout.status, 'done');
  assert.strictEqual(payout.cents, 2500);
  assert.strictEqual(payout.amount, 25, '$25.00 = 25 USDT при курсе 1:1');
  assert.strictEqual(accounts.balanceOf('42'), 7500);

  const params = new URL(fetchImpl.calls[0].url).searchParams;
  assert.strictEqual(params.get('user_id'), '42');
  assert.strictEqual(params.get('asset'), 'USDT');
  assert.strictEqual(params.get('amount'), '25');
  assert.strictEqual(params.get('spend_id'), payout.id, 'spend_id делает повтор безопасным');
});

test('внятный отказ сервиса возвращает деньги на баланс', async () => {
  const { payments, accounts } = payoutSetup({
    responses: [{ match: 'transfer', status: 400, body: { ok: false, error: { code: 400, name: 'NOT_ENOUGH_COINS' } } }],
  });

  await assert.rejects(() => payments.createPayout(user, 'cryptobot', 2500), /NOT_ENOUGH_COINS/);
  assert.strictEqual(accounts.balanceOf('42'), 10000, 'деньги вернулись целиком');

  const stuck = payments.stuckPayouts();
  assert.strictEqual(stuck.length, 0, 'отменённая выплата не считается зависшей');
});

test('оборванная связь НЕ возвращает деньги: перевод мог пройти', async () => {
  const { payments, accounts } = payoutSetup({
    responses: [{ match: 'transfer', throws: networkError() }],
  });

  await assert.rejects(() => payments.createPayout(user, 'cryptobot', 2500), /в обработке/);

  // Это главное в тесте: автоматический возврат здесь означал бы выплату дважды.
  assert.strictEqual(accounts.balanceOf('42'), 7500, 'деньги остаются списанными');
  const stuck = payments.stuckPayouts();
  assert.strictEqual(stuck.length, 1);
  assert.strictEqual(stuck[0].status, 'unknown');
});

test('повтор зависшей выплаты идёт с тем же ключом идемпотентности', async () => {
  let attempt = 0;
  const { payments, accounts, fetchImpl } = payoutSetup({
    responses: [{
      match: 'transfer',
      body: () => {
        attempt += 1;
        if (attempt === 1) throw networkError();
        return { ok: true, result: { transfer_id: 9002, status: 'completed', amount: '25' } };
      },
    }],
  });

  await assert.rejects(() => payments.createPayout(user, 'cryptobot', 2500));
  const stuck = payments.stuckPayouts()[0];

  const resolved = await payments.retryPayout(stuck.id);

  assert.strictEqual(resolved.status, 'done');
  assert.strictEqual(accounts.balanceOf('42'), 7500, 'повтор не списывает второй раз');
  const keys = fetchImpl.calls.map((call) => new URL(call.url).searchParams.get('spend_id'));
  assert.strictEqual(keys[0], keys[1], 'оба запроса с одним spend_id — сервис выполнит перевод один раз');
});

test('больше баланса не вывести', async () => {
  const { payments, accounts, fetchImpl } = payoutSetup({
    balance: 500,
    responses: [{ match: 'transfer', body: { ok: true, result: { transfer_id: 1, status: 'completed', amount: '25' } } }],
  });

  await assert.rejects(() => payments.createPayout(user, 'cryptobot', 2500), /не хватает/);
  assert.strictEqual(accounts.balanceOf('42'), 500);
  assert.strictEqual(fetchImpl.calls.length, 0, 'до сервиса запрос не дошёл');
});

test('сумма ниже минимума не выводится', async () => {
  const { payments, fetchImpl } = payoutSetup({ options: { minPayoutCents: 100 } });
  await assert.rejects(() => payments.createPayout(user, 'cryptobot', 50), /Минимальная сумма вывода/);
  assert.strictEqual(fetchImpl.calls.length, 0);
});

test('на отладочный вход вывод не работает: такого пользователя в Telegram нет', async () => {
  const { payments, accounts, fetchImpl } = payoutSetup();
  accounts.ensure({ id: 'dev:tester', name: 'Тестер' });
  accounts.deposit('dev:tester', 10000);

  await assert.rejects(
    () => payments.createPayout({ id: 'dev:tester', name: 'Тестер' }, 'cryptobot', 2500),
    /только при входе через Telegram/,
  );
  assert.strictEqual(accounts.balanceOf('dev:tester'), 10000);
  assert.strictEqual(fetchImpl.calls.length, 0);
});

test('второй вывод не запускается, пока идёт первый', async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const { payments, accounts } = payoutSetup({
    responses: [{
      match: 'transfer',
      body: async () => {
        await gate;
        return { ok: true, result: { transfer_id: 3, status: 'completed', amount: '25' } };
      },
    }],
  });

  const first = payments.createPayout(user, 'cryptobot', 2500);
  await assert.rejects(() => payments.createPayout(user, 'cryptobot', 2500), /ещё выполняется/);

  release();
  await first;
  assert.strictEqual(accounts.balanceOf('42'), 7500, 'списание ровно одно');
});

test('xRocket: вывод уходит с ключом идемпотентности transferId', async () => {
  const { payments, fetchImpl } = payoutSetup({});
  const xrocket = new XRocketProvider({
    token: XROCKET_TOKEN,
    fetchImpl: fakeFetch([{ match: '/app/transfer', body: { success: true, data: { id: 42, tgUserId: 42, currency: 'USDT', amount: 25 } } }]),
  });
  payments.providers.set('xrocket', xrocket);

  const payout = await payments.createPayout(user, 'xrocket', 2500);

  assert.strictEqual(payout.status, 'done');
  const sent = JSON.parse(xrocket.fetchImpl.calls[0].init.body);
  assert.strictEqual(sent.transferId, payout.id);
  assert.strictEqual(sent.tgUserId, 42);
  assert.strictEqual(sent.amount, 25);
});
