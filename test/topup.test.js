'use strict';

const test = require('node:test');
const assert = require('node:assert');
const crypto = require('node:crypto');
const { once } = require('node:events');

// Проверяем пополнение целиком: команда из мини-аппа → счёт → вебхук по HTTP
// → деньги на балансе и сообщение игроку.
const { createApp } = require('../server/index');
const { Accounts } = require('../server/accounts');
const { Payments } = require('../server/payments');
const { CryptoBotProvider } = require('../server/payments/cryptobot');

const TOKEN = '12345:test-token';

function sign(token, rawBody) {
  const secret = crypto.createHash('sha256').update(token).digest();
  return crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
}

async function startServer(t) {
  const accounts = new Accounts({ startingBalance: 0 });

  const fetchImpl = async (url) => ({
    status: 200,
    text: async () => JSON.stringify({
      ok: true,
      result: {
        invoice_id: 555,
        status: 'active',
        asset: 'USDT',
        amount: '5',
        payload: new URL(String(url)).searchParams.get('payload'),
        bot_invoice_url: 'https://t.me/CryptoBot?start=IVoc1',
        mini_app_invoice_url: 'https://t.me/CryptoBot/app?startapp=IVoc1',
      },
    }),
  });

  const payments = new Payments({
    providers: [new CryptoBotProvider({ token: TOKEN, fetchImpl })],
    accounts,
    file: null,
  });

  const server = createApp({ botToken: '', devLogin: true, accountsFile: null, accounts, payments });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.shutdown());
  return { port: server.address().port, accounts, payments };
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

function paidWebhook(recordId) {
  return JSON.stringify({
    update_id: 1,
    update_type: 'invoice_paid',
    request_date: new Date().toISOString(),
    payload: {
      invoice_id: 555,
      status: 'paid',
      asset: 'USDT',
      amount: '5',
      payload: recordId,
      paid_at: new Date().toISOString(),
    },
  });
}

test('игрок пополняет баланс: счёт, вебхук, деньги', { timeout: 10000 }, async (t) => {
  const { port, accounts } = await startServer(t);

  const client = connect(port);
  await once(client.socket, 'open');
  t.after(() => client.close());

  client.send({ type: 'auth', name: 'Аня', devId: 'anya' });
  const auth = await client.wait(byType('auth_ok'));
  assert.strictEqual(auth.topup.enabled, true);
  assert.deepStrictEqual(auth.topup.providers.map((p) => p.id), ['cryptobot']);

  client.send({ type: 'topup_create', provider: 'cryptobot', amount: 5 });
  const { invoice } = await client.wait(byType('topup_invoice'));
  assert.strictEqual(invoice.cents, 500, '5 USDT = $5.00');
  assert.strictEqual(invoice.url, 'https://t.me/CryptoBot/app?startapp=IVoc1');
  assert.strictEqual(accounts.balanceOf(auth.user.id), 0, 'до оплаты баланс не меняется');

  const rawBody = paidWebhook(invoice.id);
  const response = await fetch(`http://127.0.0.1:${port}/pay/cryptobot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'crypto-pay-api-signature': sign(TOKEN, rawBody) },
    body: rawBody,
  });
  assert.strictEqual(response.status, 200);

  const paid = await client.wait(byType('topup_paid'));
  assert.strictEqual(paid.cents, 500);
  const balance = await client.wait(byType('balance'));
  assert.strictEqual(balance.balance, 500);
  assert.strictEqual(accounts.balanceOf(auth.user.id), 500);
});

test('вебхук с неверной подписью отвергается и баланс не растёт', { timeout: 10000 }, async (t) => {
  const { port, accounts } = await startServer(t);

  const client = connect(port);
  await once(client.socket, 'open');
  t.after(() => client.close());

  client.send({ type: 'auth', name: 'Аня', devId: 'anya' });
  const auth = await client.wait(byType('auth_ok'));
  client.send({ type: 'topup_create', provider: 'cryptobot', amount: 5 });
  const { invoice } = await client.wait(byType('topup_invoice'));

  const rawBody = paidWebhook(invoice.id);
  const response = await fetch(`http://127.0.0.1:${port}/pay/cryptobot/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'crypto-pay-api-signature': sign('чужой-токен', rawBody) },
    body: rawBody,
  });

  assert.strictEqual(response.status, 403);
  assert.strictEqual(accounts.balanceOf(auth.user.id), 0);
});

test('вебхук неизвестного провайдера — 404, GET на вебхук — 405', { timeout: 10000 }, async (t) => {
  const { port } = await startServer(t);

  const unknown = await fetch(`http://127.0.0.1:${port}/pay/сбербанк/webhook`, { method: 'POST', body: '{}' });
  assert.strictEqual(unknown.status, 404);

  const wrongMethod = await fetch(`http://127.0.0.1:${port}/pay/cryptobot/webhook`);
  assert.strictEqual(wrongMethod.status, 405);
});

test('чужой счёт по его id не посмотреть', { timeout: 10000 }, async (t) => {
  const { port } = await startServer(t);

  const anya = connect(port);
  const boris = connect(port);
  await Promise.all([once(anya.socket, 'open'), once(boris.socket, 'open')]);
  t.after(() => {
    anya.close();
    boris.close();
  });

  anya.send({ type: 'auth', name: 'Аня', devId: 'anya' });
  boris.send({ type: 'auth', name: 'Борис', devId: 'boris' });
  await Promise.all([anya.wait(byType('auth_ok')), boris.wait(byType('auth_ok'))]);

  anya.send({ type: 'topup_create', provider: 'cryptobot', amount: 5 });
  const { invoice } = await anya.wait(byType('topup_invoice'));

  boris.send({ type: 'topup_status', id: invoice.id });
  const error = await boris.wait(byType('error'));
  assert.match(error.message, /не найден/i);
});

test('настройки пополнения отдаются в /config', { timeout: 10000 }, async (t) => {
  const { port } = await startServer(t);
  const config = await (await fetch(`http://127.0.0.1:${port}/config`)).json();

  assert.strictEqual(config.topup.enabled, true);
  assert.strictEqual(config.topup.centsPerUnit, 100, '1 USDT = $1.00');
  assert.ok(Array.isArray(config.topup.presets));
  // Токенов и прочих секретов в публичном конфиге быть не должно.
  assert.ok(!JSON.stringify(config).includes(TOKEN));
});

test('без токенов провайдеров пополнение выключено и раздела нет', { timeout: 10000 }, async (t) => {
  const accounts = new Accounts({ startingBalance: 0 });
  const payments = new Payments({ providers: [], accounts, file: null });
  const server = createApp({ botToken: '', devLogin: true, accountsFile: null, accounts, payments });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => server.shutdown());
  const port = server.address().port;

  const config = await (await fetch(`http://127.0.0.1:${port}/config`)).json();
  assert.strictEqual(config.topup.enabled, false);

  const client = connect(port);
  await once(client.socket, 'open');
  t.after(() => client.close());
  client.send({ type: 'auth', name: 'Аня', devId: 'anya' });
  await client.wait(byType('auth_ok'));

  client.send({ type: 'topup_create', provider: 'cryptobot', amount: 5 });
  const error = await client.wait(byType('error'));
  assert.match(error.message, /не подключено/i);
});

test('статика отдаётся с ревалидацией, чтобы обновление доходило сразу', { timeout: 10000 }, async (t) => {
  const { port } = await startServer(t);

  const page = await fetch(`http://127.0.0.1:${port}/index.html`);
  const script = await fetch(`http://127.0.0.1:${port}/app.js`);

  // Пятиминутный max-age приводил к тому, что браузер брал новый index.html
  // и старый app.js: привязка к исчезнувшей кнопке роняла запуск.
  assert.strictEqual(page.headers.get('cache-control'), 'no-store');
  assert.strictEqual(script.headers.get('cache-control'), 'no-cache');
});
