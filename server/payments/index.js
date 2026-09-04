'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const { PaymentError } = require('./common');
const { CryptoBotProvider } = require('./cryptobot');
const { XRocketProvider } = require('./xrocket');

// Пополнение и вывод баланса криптой через Crypto Bot и xRocket.
//
// Баланс игрока хранится в центах (см. money.js). Курс по умолчанию 1:1 —
// 1 USDT даёт $1.00, то есть 100 центов, и обратно так же.
//
// Два правила, на которых всё держится:
//   1. Пополнение зачисляется ровно один раз. Вебхук может прийти дважды,
//      поверх него ещё и опрос из мини-аппа — поэтому у счёта есть отметка
//      о зачислении, и повторный вызов ничего не делает.
//   2. Вывод сначала списывает деньги с баланса и только потом уходит в
//      платёжный сервис. Если сервис ответил внятным отказом — возвращаем.
//      Если ответ не дошёл — НЕ возвращаем: перевод мог состояться.

const CENTS_IN_DOLLAR = 100;
const DEFAULT_USD_PER_UNIT = 1; // 1 USDT = $1
const DEFAULT_PRESETS = [1, 5, 10, 25];
const DEFAULT_MIN_AMOUNT = 0.1;
const DEFAULT_MAX_AMOUNT = 1000;
const DEFAULT_MIN_PAYOUT_CENTS = 100; // $1.00
const INVOICE_TTL_SECONDS = 3600;
const MAX_PENDING_PER_USER = 5;
const KEEP_RECORDS = 5000;
const KEEP_MS = 30 * 24 * 60 * 60 * 1000;
const UNIT_DECIMALS = 6;

// Идентификатор счёта в Telegram — это число. Отладочные входы дают «dev:…»,
// и переводить на них деньги нельзя: такого пользователя в Telegram нет.
const isTelegramId = (userId) => /^\d+$/.test(String(userId));

class Payments {
  constructor({
    providers = [],
    accounts,
    file = null,
    usdPerUnit = DEFAULT_USD_PER_UNIT,
    presets = DEFAULT_PRESETS,
    minAmount = DEFAULT_MIN_AMOUNT,
    maxAmount = DEFAULT_MAX_AMOUNT,
    minPayoutCents = DEFAULT_MIN_PAYOUT_CENTS,
    invoiceTtlSeconds = INVOICE_TTL_SECONDS,
  } = {}) {
    if (!accounts) throw new PaymentError('Пополнению нужен доступ к счетам');
    this.accounts = accounts;
    this.file = file;
    this.usdPerUnit = Number(usdPerUnit) > 0 ? Number(usdPerUnit) : DEFAULT_USD_PER_UNIT;
    this.minAmount = Math.max(0, Number(minAmount) || 0);
    this.maxAmount = Math.max(this.minAmount, Number(maxAmount) || DEFAULT_MAX_AMOUNT);
    this.minPayoutCents = Math.max(1, Math.floor(minPayoutCents));
    this.invoiceTtlSeconds = Math.max(60, Math.floor(invoiceTtlSeconds));
    this.presets = [...new Set(presets.map(Number).filter((n) => Number.isFinite(n) && n > 0))]
      .filter((n) => n >= this.minAmount && n <= this.maxAmount)
      .sort((a, b) => a - b);

    this.providers = new Map();
    for (const provider of providers) this.providers.set(provider.id, provider);

    this.invoices = new Map(); // наш id счёта -> запись о пополнении
    this.payouts = new Map(); // наш id выплаты -> запись о выводе
    this.saveTimer = null;
    this.onCredit = null; // сюда сообщаем, кому и сколько зачислили
    this.onPayout = null; // ...и чей вывод изменил состояние
    if (file) this.load();
  }

  get enabled() {
    return this.providers.size > 0;
  }

  get payoutProviders() {
    return [...this.providers.values()].filter((provider) => provider.supportsPayout);
  }

  get payoutEnabled() {
    return this.payoutProviders.length > 0;
  }

  // Описание для клиента. Секретов здесь нет — уходит и в /config.
  describe() {
    const maxPayoutCents = this.centsFor(this.maxAmount);
    return {
      enabled: this.enabled,
      usdPerUnit: this.usdPerUnit,
      centsPerUnit: this.centsFor(1),
      presets: this.presets,
      presetCents: this.presets.map((amount) => this.centsFor(amount)),
      minAmount: this.minAmount,
      maxAmount: this.maxAmount,
      minAmountCents: this.centsFor(this.minAmount),
      maxAmountCents: maxPayoutCents,
      payout: {
        enabled: this.payoutEnabled,
        minCents: this.minPayoutCents,
        maxCents: maxPayoutCents,
        providers: this.payoutProviders.map((provider) => ({
          id: provider.id,
          title: provider.title,
          currency: provider.currency,
        })),
      },
      providers: [...this.providers.values()].map((provider) => ({
        id: provider.id,
        title: provider.title,
        currency: provider.currency,
        payout: Boolean(provider.supportsPayout),
      })),
    };
  }

  // ——— Пересчёт валюты в центы и обратно ———

  centsFor(units) {
    return Math.round(Number(units) * CENTS_IN_DOLLAR * this.usdPerUnit);
  }

  unitsFor(cents) {
    const units = Number(cents) / CENTS_IN_DOLLAR / this.usdPerUnit;
    return Number(units.toFixed(UNIT_DECIMALS));
  }

  // ——— Хранение ———

  load() {
    try {
      const parsed = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      for (const record of parsed.invoices || []) {
        if (record && record.id) this.invoices.set(String(record.id), record);
      }
      for (const record of parsed.payouts || []) {
        if (record && record.id) this.payouts.set(String(record.id), record);
      }
    } catch (error) {
      if (error.code !== 'ENOENT') {
        console.error('Не удалось прочитать историю платежей:', error.message);
      }
    }
  }

  flush() {
    if (!this.file) return;
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    const payload = JSON.stringify({
      invoices: [...this.invoices.values()],
      payouts: [...this.payouts.values()],
    }, null, 2);
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      const temporary = `${this.file}.tmp`;
      fs.writeFileSync(temporary, payload);
      fs.renameSync(temporary, this.file);
    } catch (error) {
      console.error('Не удалось сохранить историю платежей:', error.message);
    }
  }

  scheduleSave() {
    if (!this.file || this.saveTimer) return;
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.flush();
    }, 400);
    this.saveTimer.unref?.();
  }

  // Выплаты терять нельзя, поэтому их пишем на диск сразу, не дожидаясь
  // отложенного сохранения: между «списали» и «записали» не должно быть окна.
  flushNow() {
    this.flush();
  }

  // ——— Общее ———

  provider(id) {
    const found = this.providers.get(String(id));
    if (!found) throw new PaymentError('Такой способ оплаты не подключён');
    return found;
  }

  normalizeAmount(amount) {
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) throw new PaymentError('Укажите сумму числом');
    const rounded = Number(value.toFixed(UNIT_DECIMALS));
    if (rounded < this.minAmount) throw new PaymentError(`Минимальная сумма пополнения — ${this.minAmount}`);
    if (rounded > this.maxAmount) throw new PaymentError(`Максимальная сумма пополнения — ${this.maxAmount}`);
    if (this.centsFor(rounded) <= 0) throw new PaymentError('Слишком маленькая сумма');
    return rounded;
  }

  // ——— Пополнение ———

  pendingFor(userId) {
    const now = Date.now();
    return [...this.invoices.values()].filter(
      (record) => record.userId === String(userId) && record.status === 'pending' && record.expiresAt > now,
    );
  }

  async createTopUp(user, providerId, amount) {
    const provider = this.provider(providerId);
    const value = this.normalizeAmount(amount);
    const userId = String(user.id);

    if (this.pendingFor(userId).length >= MAX_PENDING_PER_USER) {
      throw new PaymentError('Слишком много неоплаченных счетов. Оплатите или дождитесь, пока они истекут');
    }

    const id = crypto.randomUUID();
    const cents = this.centsFor(value);
    const record = {
      id,
      kind: 'topup',
      userId,
      userName: user.name || null,
      userUsername: user.username || null,
      provider: provider.id,
      amount: value,
      currency: provider.currency,
      cents,
      status: 'pending',
      invoiceId: null,
      url: null,
      createdAt: Date.now(),
      expiresAt: Date.now() + this.invoiceTtlSeconds * 1000,
      creditedAt: null,
      creditedCents: 0,
    };

    const invoice = await provider.createInvoice({
      amount: value,
      description: `Пополнение баланса · ${user.name || 'игрок'}`,
      // payload возвращается нам в вебхуке — по нему и находим, кому зачислять.
      payload: id,
      expiresIn: this.invoiceTtlSeconds,
      hiddenMessage: 'Готово! Деньги уже на балансе.',
    });

    record.invoiceId = invoice.id;
    record.url = invoice.url;
    record.fallbackUrl = invoice.fallbackUrl || null;
    this.invoices.set(id, record);
    this.prune();
    this.scheduleSave();

    return this.invoiceView(record);
  }

  invoiceView(record) {
    return {
      id: record.id,
      kind: 'topup',
      provider: record.provider,
      providerTitle: this.providers.has(record.provider) ? this.providers.get(record.provider).title : record.provider,
      amount: record.amount,
      currency: record.currency,
      cents: record.cents,
      status: record.status,
      url: record.url,
      fallbackUrl: record.fallbackUrl || null,
      expiresAt: record.expiresAt,
      creditedCents: record.creditedCents || 0,
      createdAt: record.createdAt,
    };
  }

  get(recordId) {
    return this.invoices.get(String(recordId)) || null;
  }

  // Счёт ищем сначала по нашему payload, а если его нет — по паре
  // провайдер + номер счёта у провайдера.
  findRecord(providerId, invoice) {
    if (invoice.payload) {
      const byPayload = this.invoices.get(String(invoice.payload));
      if (byPayload && byPayload.provider === providerId) return byPayload;
    }
    return [...this.invoices.values()].find(
      (record) => record.provider === providerId && record.invoiceId && record.invoiceId === String(invoice.id),
    ) || null;
  }

  // Идемпотентно: второй вызов для того же счёта баланс не трогает.
  credit(record, invoice) {
    if (record.creditedAt) return { record, credited: 0, already: true };

    // Сколько реально заплатили, столько и зачисляем: так корректно
    // отработает и переплата.
    const paid = Number.isFinite(Number(invoice.paidAmount)) && Number(invoice.paidAmount) > 0
      ? Number(invoice.paidAmount)
      : record.amount;
    const cents = Math.max(0, Math.min(this.centsFor(paid), this.centsFor(this.maxAmount)));

    record.status = 'paid';
    record.paidAmount = paid;
    record.creditedAt = Date.now();
    record.creditedCents = cents;

    if (cents > 0) {
      // Счёт мог не существовать, если игрок ни разу не заходил после рестарта.
      this.accounts.ensure({ id: record.userId, name: record.userName, username: record.userUsername });
      this.accounts.deposit(record.userId, cents);
    }

    this.scheduleSave();
    if (this.onCredit) this.onCredit(record);
    return { record, credited: cents, already: false };
  }

  // rawBody — именно сырое тело: подпись считается по байтам, повторный
  // JSON.stringify её ломает.
  handleWebhook(providerId, rawBody, signature) {
    const provider = this.provider(providerId);
    if (!provider.verifyWebhook(rawBody, signature)) {
      throw new PaymentError('Подпись вебхука не совпала');
    }

    const invoice = provider.parseWebhook(rawBody);
    if (!invoice) return { handled: false, reason: 'событие не про оплату' };

    const record = this.findRecord(provider.id, invoice);
    if (!record) return { handled: false, reason: 'счёт не наш' };

    const result = this.credit(record, invoice);
    return { handled: true, already: result.already, credited: result.credited, record };
  }

  // Запасной путь: вебхук могли не настроить или он не дошёл.
  async refresh(recordId) {
    const record = this.get(recordId);
    if (!record) throw new PaymentError('Счёт не найден');
    if (record.status === 'paid') return this.invoiceView(record);

    const provider = this.provider(record.provider);
    if (!record.invoiceId) return this.invoiceView(record);

    const invoice = await provider.getInvoice(record.invoiceId);
    if (!invoice) return this.invoiceView(record);

    if (invoice.status === 'paid') {
      this.credit(record, invoice);
    } else if (invoice.status === 'expired' || record.expiresAt < Date.now()) {
      if (record.status === 'pending') {
        record.status = 'expired';
        this.scheduleSave();
      }
    }
    return this.invoiceView(record);
  }

  // ——— Вывод ———

  payoutView(record) {
    return {
      id: record.id,
      kind: 'payout',
      provider: record.provider,
      providerTitle: this.providers.has(record.provider) ? this.providers.get(record.provider).title : record.provider,
      cents: record.cents,
      amount: record.amount,
      currency: record.currency,
      status: record.status, // pending | done | failed | unknown
      error: record.error || null,
      createdAt: record.createdAt,
      finishedAt: record.finishedAt || null,
    };
  }

  getPayout(payoutId) {
    return this.payouts.get(String(payoutId)) || null;
  }

  normalizePayoutCents(cents) {
    const value = Math.floor(Number(cents));
    if (!Number.isFinite(value) || value <= 0) throw new PaymentError('Укажите сумму вывода');
    if (value < this.minPayoutCents) {
      throw new PaymentError(`Минимальная сумма вывода — ${(this.minPayoutCents / CENTS_IN_DOLLAR).toFixed(2)}`);
    }
    if (value > this.centsFor(this.maxAmount)) {
      throw new PaymentError(`Максимальная сумма вывода — ${(this.centsFor(this.maxAmount) / CENTS_IN_DOLLAR).toFixed(2)}`);
    }
    return value;
  }

  async createPayout(user, providerId, cents) {
    const provider = this.provider(providerId);
    if (!provider.supportsPayout) throw new PaymentError('Через этот сервис вывод недоступен');

    const userId = String(user.id);
    // Telegram-перевод уходит по числовому id. Отладочные входы его не имеют.
    if (!isTelegramId(userId)) {
      throw new PaymentError('Вывод доступен только при входе через Telegram');
    }

    const value = this.normalizePayoutCents(cents);
    const units = this.unitsFor(value);
    if (units <= 0) throw new PaymentError('Слишком маленькая сумма вывода');

    // Один вывод за раз: параллельные запросы не должны делить один баланс.
    const busy = [...this.payouts.values()].some(
      (record) => record.userId === userId && record.status === 'pending',
    );
    if (busy) throw new PaymentError('Предыдущий вывод ещё выполняется, подождите');

    // Списываем ДО обращения в сервис: так одну и ту же сумму нельзя вывести
    // дважды, отправив два запроса одновременно. Если сервис откажет —
    // вернём обратно.
    try {
      this.accounts.withdraw(userId, value);
      // Баланс пишем на диск сразу, не дожидаясь отложенного сохранения:
      // иначе падение процесса прямо здесь вернёт игроку уже списанные деньги,
      // а запись о выплате останется — и он получит их дважды.
      this.accounts.flush();
    } catch (error) {
      throw new PaymentError(error.message);
    }

    const record = {
      id: crypto.randomUUID(),
      kind: 'payout',
      userId,
      userName: user.name || null,
      provider: provider.id,
      cents: value,
      amount: units,
      currency: provider.currency,
      status: 'pending',
      transferId: null,
      error: null,
      createdAt: Date.now(),
      finishedAt: null,
    };
    this.payouts.set(record.id, record);
    // Запись о списании должна пережить падение процесса прямо здесь.
    this.flushNow();

    return this.sendPayout(record);
  }

  // Отправляет (или повторяет) перевод. Ключ идемпотентности — id записи,
  // поэтому повтор после неясной ошибки не создаёт второй перевод.
  async sendPayout(record) {
    const provider = this.provider(record.provider);
    try {
      const transfer = await provider.payout({
        userId: record.userId,
        amount: record.amount,
        spendId: record.id,
        comment: 'Вывод выигрыша',
      });
      record.status = 'done';
      record.transferId = transfer.id;
      record.error = null;
      record.finishedAt = Date.now();
      this.flushNow();
      if (this.onPayout) this.onPayout(record);
      return this.payoutView(record);
    } catch (error) {
      const ambiguous = error instanceof PaymentError && error.ambiguous;
      if (ambiguous) {
        // Перевод мог пройти. Возвращать деньги на баланс здесь нельзя —
        // иначе игрок получит их и на кошелёк, и на счёт.
        record.status = 'unknown';
        record.error = error.message;
        this.flushNow();
        if (this.onPayout) this.onPayout(record);
        console.error(`Вывод ${record.id} в неизвестном состоянии: ${error.message}. Повторить: sendPayout с тем же id.`);
        throw new PaymentError(
          'Платёжный сервис не ответил. Деньги списаны, выплата в обработке — она завершится сама или её вернут вручную.',
          { ambiguous: true },
        );
      }

      // Внятный отказ — перевода не было, деньги можно вернуть.
      record.status = 'failed';
      record.error = error.message;
      record.finishedAt = Date.now();
      this.accounts.deposit(record.userId, record.cents);
      this.flushNow();
      if (this.onPayout) this.onPayout(record);
      throw error instanceof PaymentError ? error : new PaymentError(error.message);
    }
  }

  // Повторная попытка для зависших выплат — безопасна благодаря ключу
  // идемпотентности. Вызывается админом.
  async retryPayout(payoutId) {
    const record = this.getPayout(payoutId);
    if (!record) throw new PaymentError('Выплата не найдена');
    if (record.status === 'done') return this.payoutView(record);
    if (record.status === 'failed') throw new PaymentError('Эта выплата уже отменена, деньги возвращены на баланс');
    return this.sendPayout(record);
  }

  stuckPayouts() {
    return [...this.payouts.values()].filter((record) => record.status === 'unknown' || record.status === 'pending');
  }

  // ——— История ———

  historyFor(userId, limit = 30) {
    const id = String(userId);
    const topUps = [...this.invoices.values()]
      .filter((record) => record.userId === id && record.status !== 'pending')
      .map((record) => this.invoiceView(record));
    const payouts = [...this.payouts.values()]
      .filter((record) => record.userId === id)
      .map((record) => this.payoutView(record));
    return [...topUps, ...payouts]
      .sort((a, b) => b.createdAt - a.createdAt)
      .slice(0, limit);
  }

  // ——— Уборка ———

  prune() {
    const now = Date.now();
    for (const record of this.invoices.values()) {
      if (record.status === 'pending' && record.expiresAt < now) record.status = 'expired';
    }
    if (this.invoices.size <= KEEP_RECORDS) {
      for (const [id, record] of this.invoices) {
        if (now - record.createdAt > KEEP_MS) this.invoices.delete(id);
      }
      return;
    }
    const sorted = [...this.invoices.values()].sort((a, b) => a.createdAt - b.createdAt);
    for (const record of sorted.slice(0, this.invoices.size - KEEP_RECORDS)) {
      this.invoices.delete(record.id);
    }
  }
}

// ——— Сборка из переменных окружения ———

function parseList(value, fallback) {
  const items = String(value || '')
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item) && item > 0);
  return items.length ? items : fallback;
}

const truthy = (value) => value === '1' || String(value).toLowerCase() === 'true';

// Провайдер включается сам, как только у него появился токен.
function createPayments({ accounts, file = null, env = process.env, fetchImpl = null } = {}) {
  const providers = [];
  const returnUrl = env.TOPUP_RETURN_URL || null;

  const cryptoBotToken = env.CRYPTOBOT_TOKEN || env.CRYPTO_PAY_TOKEN || '';
  if (cryptoBotToken) {
    providers.push(new CryptoBotProvider({
      token: cryptoBotToken,
      testnet: truthy(env.CRYPTOBOT_TESTNET),
      currency: env.CRYPTOBOT_CURRENCY || env.TOPUP_CURRENCY || 'USDT',
      currencyType: env.CRYPTOBOT_CURRENCY_TYPE || 'crypto',
      returnUrl,
      fetchImpl,
    }));
  }

  const xrocketToken = env.XROCKET_TOKEN || env.XROCKET_API_KEY || '';
  if (xrocketToken) {
    providers.push(new XRocketProvider({
      token: xrocketToken,
      testnet: truthy(env.XROCKET_TESTNET),
      currency: env.XROCKET_CURRENCY || env.TOPUP_CURRENCY || 'USDT',
      returnUrl,
      fetchImpl,
    }));
  }

  return new Payments({
    providers,
    accounts,
    file,
    usdPerUnit: Number(env.TOPUP_USD_PER_UNIT || DEFAULT_USD_PER_UNIT),
    presets: parseList(env.TOPUP_PRESETS, DEFAULT_PRESETS),
    minAmount: Number(env.TOPUP_MIN_AMOUNT || DEFAULT_MIN_AMOUNT),
    maxAmount: Number(env.TOPUP_MAX_AMOUNT || DEFAULT_MAX_AMOUNT),
    minPayoutCents: Math.round(Number(env.WITHDRAW_MIN_AMOUNT || 1) * CENTS_IN_DOLLAR),
  });
}

module.exports = { Payments, createPayments, PaymentError, CryptoBotProvider, XRocketProvider };
