'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const { PaymentError } = require('./common');
const { CryptoBotProvider } = require('./cryptobot');
const { XRocketProvider } = require('./xrocket');

// Пополнение баланса криптой. Деньги приходят в Crypto Bot или xRocket,
// а сюда возвращается только факт оплаты — по вебхуку или по опросу счёта.
//
// Главное правило: фишки начисляются ровно один раз. Вебхук может прийти
// дважды, а поверх него ещё и опрос из мини-аппа — поэтому у каждого счёта
// есть creditedAt, и повторное зачисление просто ничего не делает.

const DEFAULT_CHIPS_PER_UNIT = 1000;
const DEFAULT_PRESETS = [1, 5, 10, 25];
const DEFAULT_MIN_AMOUNT = 0.1;
const DEFAULT_MAX_AMOUNT = 1000;
const INVOICE_TTL_SECONDS = 3600;
const MAX_PENDING_PER_USER = 5;
const KEEP_RECORDS = 5000;
const KEEP_MS = 30 * 24 * 60 * 60 * 1000;
const AMOUNT_DECIMALS = 6;

class Payments {
  constructor({
    providers = [],
    accounts,
    file = null,
    chipsPerUnit = DEFAULT_CHIPS_PER_UNIT,
    presets = DEFAULT_PRESETS,
    minAmount = DEFAULT_MIN_AMOUNT,
    maxAmount = DEFAULT_MAX_AMOUNT,
    invoiceTtlSeconds = INVOICE_TTL_SECONDS,
  } = {}) {
    if (!accounts) throw new PaymentError('Пополнению нужен доступ к счетам');
    this.accounts = accounts;
    this.file = file;
    this.chipsPerUnit = Math.max(1, Math.floor(chipsPerUnit));
    this.minAmount = Math.max(0, Number(minAmount) || 0);
    this.maxAmount = Math.max(this.minAmount, Number(maxAmount) || DEFAULT_MAX_AMOUNT);
    this.invoiceTtlSeconds = Math.max(60, Math.floor(invoiceTtlSeconds));
    this.presets = [...new Set(presets.map(Number).filter((n) => Number.isFinite(n) && n > 0))]
      .filter((n) => n >= this.minAmount && n <= this.maxAmount)
      .sort((a, b) => a - b);

    this.providers = new Map();
    for (const provider of providers) this.providers.set(provider.id, provider);

    this.records = new Map(); // id счёта у нас -> запись
    this.saveTimer = null;
    this.onCredit = null; // сюда сообщаем, кому и сколько начислили
    if (file) this.load();
  }

  get enabled() {
    return this.providers.size > 0;
  }

  // Описание для клиента: что показывать в лобби. Секретов здесь нет.
  describe() {
    return {
      enabled: this.enabled,
      chipsPerUnit: this.chipsPerUnit,
      presets: this.presets,
      minAmount: this.minAmount,
      maxAmount: this.maxAmount,
      providers: [...this.providers.values()].map((provider) => ({
        id: provider.id,
        title: provider.title,
        currency: provider.currency,
      })),
    };
  }

  chipsFor(amount) {
    return Math.floor(Number(amount) * this.chipsPerUnit);
  }

  // ——— Хранение ———

  load() {
    try {
      const parsed = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      for (const record of parsed.invoices || []) {
        if (!record || !record.id) continue;
        this.records.set(String(record.id), record);
      }
    } catch (error) {
      if (error.code !== 'ENOENT') {
        console.error('Не удалось прочитать счета на пополнение:', error.message);
      }
    }
  }

  flush() {
    if (!this.file) return;
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    const payload = JSON.stringify({ invoices: [...this.records.values()] }, null, 2);
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      const temporary = `${this.file}.tmp`;
      fs.writeFileSync(temporary, payload);
      fs.renameSync(temporary, this.file);
    } catch (error) {
      console.error('Не удалось сохранить счета на пополнение:', error.message);
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

  // ——— Счета ———

  provider(id) {
    const found = this.providers.get(String(id));
    if (!found) throw new PaymentError('Такой способ оплаты не подключён');
    return found;
  }

  normalizeAmount(amount) {
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) throw new PaymentError('Укажите сумму числом');
    const rounded = Number(value.toFixed(AMOUNT_DECIMALS));
    if (rounded < this.minAmount) throw new PaymentError(`Минимальная сумма пополнения — ${this.minAmount}`);
    if (rounded > this.maxAmount) throw new PaymentError(`Максимальная сумма пополнения — ${this.maxAmount}`);
    if (this.chipsFor(rounded) <= 0) throw new PaymentError('Такая сумма не даёт ни одной фишки');
    return rounded;
  }

  pendingFor(userId) {
    const now = Date.now();
    return [...this.records.values()].filter(
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
    const chips = this.chipsFor(value);
    const record = {
      id,
      userId,
      userName: user.name || null,
      userUsername: user.username || null,
      provider: provider.id,
      amount: value,
      currency: provider.currency,
      chips,
      status: 'pending',
      invoiceId: null,
      url: null,
      createdAt: Date.now(),
      expiresAt: Date.now() + this.invoiceTtlSeconds * 1000,
      creditedAt: null,
      creditedChips: 0,
    };

    const invoice = await provider.createInvoice({
      amount: value,
      description: `${chips} фишек · ${user.name || 'игрок'}`,
      // payload возвращается нам в вебхуке — по нему и находим, кому начислять.
      payload: id,
      expiresIn: this.invoiceTtlSeconds,
      hiddenMessage: `Готово! ${chips} фишек уже на балансе.`,
    });

    record.invoiceId = invoice.id;
    record.url = invoice.url;
    record.fallbackUrl = invoice.fallbackUrl || null;
    this.records.set(id, record);
    this.prune();
    this.scheduleSave();

    return this.publicView(record);
  }

  publicView(record) {
    return {
      id: record.id,
      provider: record.provider,
      providerTitle: this.providers.has(record.provider) ? this.providers.get(record.provider).title : record.provider,
      amount: record.amount,
      currency: record.currency,
      chips: record.chips,
      status: record.status,
      url: record.url,
      fallbackUrl: record.fallbackUrl || null,
      expiresAt: record.expiresAt,
      creditedChips: record.creditedChips || 0,
    };
  }

  get(recordId) {
    return this.records.get(String(recordId)) || null;
  }

  // Запись ищем сначала по нашему payload, а если его нет (счёт мог быть
  // создан вручную или payload потерялся) — по паре провайдер + номер счёта.
  findRecord(providerId, invoice) {
    if (invoice.payload) {
      const byPayload = this.records.get(String(invoice.payload));
      if (byPayload && byPayload.provider === providerId) return byPayload;
    }
    return [...this.records.values()].find(
      (record) => record.provider === providerId && record.invoiceId && record.invoiceId === String(invoice.id),
    ) || null;
  }

  // ——— Зачисление ———

  // Идемпотентно: второй вызов для того же счёта возвращает already = true
  // и баланс не трогает.
  credit(record, invoice) {
    if (record.creditedAt) {
      return { record, credited: 0, already: true };
    }

    // Сколько реально заплатили, столько фишек и даём: так корректно
    // отработают и переплата, и оплата счёта другой монетой по курсу.
    const paid = Number.isFinite(Number(invoice.paidAmount)) && Number(invoice.paidAmount) > 0
      ? Number(invoice.paidAmount)
      : record.amount;
    const chips = Math.max(0, Math.min(this.chipsFor(paid), this.chipsFor(this.maxAmount)));

    record.status = 'paid';
    record.paidAmount = paid;
    record.creditedAt = Date.now();
    record.creditedChips = chips;

    if (chips > 0) {
      // Счёт мог не существовать, если игрок ни разу не заходил после рестарта.
      this.accounts.ensure({ id: record.userId, name: record.userName, username: record.userUsername });
      this.accounts.deposit(record.userId, chips);
    }

    this.scheduleSave();
    if (this.onCredit) this.onCredit(record);
    return { record, credited: chips, already: false };
  }

  // ——— Вебхук ———

  // Вызывается из HTTP-обработчика. rawBody — именно сырое тело: подпись
  // считается по байтам, повторный JSON.stringify её ломает.
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

  // ——— Опрос ———

  // Запасной путь: вебхук могли не настроить или он не дошёл. Мини-апп сам
  // спрашивает статус, пока ждёт оплату.
  async refresh(recordId) {
    const record = this.get(recordId);
    if (!record) throw new PaymentError('Счёт не найден');
    if (record.status === 'paid') return this.publicView(record);

    const provider = this.provider(record.provider);
    if (!record.invoiceId) return this.publicView(record);

    const invoice = await provider.getInvoice(record.invoiceId);
    if (!invoice) return this.publicView(record);

    if (invoice.status === 'paid') {
      this.credit(record, invoice);
    } else if (invoice.status === 'expired' || record.expiresAt < Date.now()) {
      if (record.status === 'pending') {
        record.status = 'expired';
        this.scheduleSave();
      }
    }
    return this.publicView(record);
  }

  // ——— Уборка ———

  prune() {
    const now = Date.now();
    for (const record of this.records.values()) {
      if (record.status === 'pending' && record.expiresAt < now) record.status = 'expired';
    }
    if (this.records.size <= KEEP_RECORDS) {
      // Даже без переполнения выкидываем совсем старое, чтобы файл не рос вечно.
      for (const [id, record] of this.records) {
        if (now - record.createdAt > KEEP_MS) this.records.delete(id);
      }
      return;
    }
    const sorted = [...this.records.values()].sort((a, b) => a.createdAt - b.createdAt);
    for (const record of sorted.slice(0, this.records.size - KEEP_RECORDS)) {
      this.records.delete(record.id);
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
    chipsPerUnit: Number(env.TOPUP_CHIPS_PER_UNIT || DEFAULT_CHIPS_PER_UNIT),
    presets: parseList(env.TOPUP_PRESETS, DEFAULT_PRESETS),
    minAmount: Number(env.TOPUP_MIN_AMOUNT || DEFAULT_MIN_AMOUNT),
    maxAmount: Number(env.TOPUP_MAX_AMOUNT || DEFAULT_MAX_AMOUNT),
  });
}

module.exports = { Payments, createPayments, PaymentError, CryptoBotProvider, XRocketProvider };
