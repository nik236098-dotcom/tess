'use strict';

const { PaymentError, requestJson, signBody, signaturesMatch } = require('./common');

// Crypto Bot (@CryptoBot) — Crypto Pay API.
// https://help.crypt.bot/crypto-pay-api
//
// Токен берётся в самом боте: Crypto Pay → My Apps → Create App → API Token.

const MAINNET = 'https://pay.crypt.bot';
const TESTNET = 'https://testnet-pay.crypt.bot'; // работает с @CryptoTestnetBot

const SIGNATURE_HEADER = 'crypto-pay-api-signature';

class CryptoBotProvider {
  constructor({ token, testnet = false, baseUrl = null, currency = 'USDT', currencyType = 'crypto', returnUrl = null, fetchImpl = null } = {}) {
    if (!token) throw new PaymentError('Для Crypto Bot нужен API-токен');
    this.token = String(token);
    this.baseUrl = (baseUrl || (testnet ? TESTNET : MAINNET)).replace(/\/+$/, '');
    this.currency = String(currency || 'USDT').toUpperCase();
    this.currencyType = currencyType === 'fiat' ? 'fiat' : 'crypto';
    this.returnUrl = returnUrl || null;
    this.fetchImpl = fetchImpl;
  }

  get id() {
    return 'cryptobot';
  }

  get title() {
    return 'Crypto Bot';
  }

  get signatureHeader() {
    return SIGNATURE_HEADER;
  }

  // ——— Вызовы API ———

  async call(method, params = {}) {
    const url = new URL(`/api/${method}`, this.baseUrl);
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue;
      url.searchParams.set(key, String(value));
    }

    const { status, data } = await requestJson(url.toString(), {
      headers: { 'Crypto-Pay-API-Token': this.token },
      fetchImpl: this.fetchImpl,
    });

    if (!data || data.ok !== true) {
      const error = data && data.error ? (data.error.name || JSON.stringify(data.error)) : `HTTP ${status}`;
      // 5xx — сервис мог принять запрос и упасть уже после этого, поэтому
      // такой отказ считаем неопределённым; осмысленный 4xx — это отказ.
      throw new PaymentError(`Crypto Bot отказал: ${error}`, { ambiguous: status >= 500 });
    }
    return data.result;
  }

  // Проверка токена при старте: заодно видно, что не перепутана сеть.
  async getMe() {
    return this.call('getMe');
  }

  async createInvoice({ amount, description, payload, expiresIn = 3600, hiddenMessage = null }) {
    const params = {
      currency_type: this.currencyType,
      amount: String(amount),
      description,
      payload,
      hidden_message: hiddenMessage,
      expires_in: expiresIn,
      allow_comments: false,
      allow_anonymous: false,
    };
    if (this.currencyType === 'fiat') params.fiat = this.currency;
    else params.asset = this.currency;
    if (this.returnUrl) {
      params.paid_btn_name = 'callback';
      params.paid_btn_url = this.returnUrl;
    }

    const invoice = await this.call('createInvoice', params);
    return this.normalize(invoice);
  }

  async getInvoice(invoiceId) {
    const result = await this.call('getInvoices', { invoice_ids: String(invoiceId) });
    const items = (result && result.items) || [];
    if (!items.length) return null;
    return this.normalize(items[0]);
  }

  // Приводим ответ Crypto Bot к виду, одинаковому для всех провайдеров.
  normalize(invoice) {
    return {
      id: String(invoice.invoice_id),
      status: invoice.status, // active | paid | expired
      amount: Number(invoice.amount),
      // У счёта в фиате paid_amount — это сумма в крипте, которой расплатились,
      // а цену мы называем в фиате. Смешивать их нельзя, поэтому оплаченной
      // суммой считаем сумму счёта; paid_amount берём только у крипто-счетов,
      // где обе величины в одной монете и переплата имеет смысл.
      paidAmount: invoice.currency_type !== 'fiat' && invoice.paid_amount !== undefined
        ? Number(invoice.paid_amount)
        : Number(invoice.amount),
      currency: invoice.asset || invoice.fiat || this.currency,
      payload: invoice.payload || null,
      // mini_app_invoice_url открывается прямо внутри Telegram поверх мини-аппа,
      // поэтому он и основной; bot_invoice_url — запасной для старых клиентов.
      url: invoice.mini_app_invoice_url || invoice.bot_invoice_url || invoice.pay_url || null,
      fallbackUrl: invoice.bot_invoice_url || null,
      paidAt: invoice.paid_at || null,
    };
  }

  // ——— Выплата ———

  // Переводы возможны только в криптоактиве: счёт в фиате — это цена,
  // а перевести «10 рублей» через Crypto Bot нельзя.
  get supportsPayout() {
    return this.currencyType === 'crypto';
  }

  // spendId делает запрос идемпотентным: с одним и тем же spend_id Crypto Bot
  // выполнит перевод ровно один раз, сколько бы раз мы ни повторили запрос.
  async payout({ userId, amount, spendId, comment = null }) {
    const transfer = await this.call('transfer', {
      user_id: userId,
      asset: this.currency,
      amount: String(amount),
      spend_id: spendId,
      comment,
    });
    return {
      id: String(transfer.transfer_id),
      status: transfer.status || 'completed',
      amount: Number(transfer.amount),
    };
  }

  // ——— Вебхук ———

  verifyWebhook(rawBody, signature) {
    return signaturesMatch(signBody(this.token, rawBody), signature);
  }

  // Возвращает событие об оплате или null, если апдейт нам неинтересен.
  parseWebhook(rawBody) {
    let update;
    try {
      update = JSON.parse(rawBody);
    } catch {
      throw new PaymentError('Вебхук Crypto Bot прислал не JSON');
    }
    if (!update || update.update_type !== 'invoice_paid' || !update.payload) return null;

    const invoice = this.normalize(update.payload);
    if (invoice.status !== 'paid') return null;
    return invoice;
  }
}

module.exports = { CryptoBotProvider, MAINNET, TESTNET };
