'use strict';

const crypto = require('node:crypto');
const { PaymentError, requestJson, signBody, signaturesMatch } = require('./common');

// xRocket (@xRocket) — xRocket Pay API.
// https://pay.xrocket.tg/api  (спека: /tg-invoices)
//
// Ключ берётся в боте: Rocket Pay → Create App → API token.

const MAINNET = 'https://pay.xrocket.tg';
const TESTNET = 'https://dev-pay.xrocket.tg';

const CURRENT_MAINNET = 'https://pay.api.xrocket.exchange';
const CURRENT_TESTNET = 'https://pay.api.testnet.xrocket.exchange';

const SIGNATURE_HEADER = 'rocket-pay-signature';

class XRocketProvider {
  constructor({ token, testnet = false, baseUrl = null, currency = 'USDT', returnUrl = null, fetchImpl = null, apiVersion = 'auto', webhookToken = '' } = {}) {
    if (!token) throw new PaymentError('Для xRocket нужен API-ключ');
    this.token = String(token).trim().replace(/^Bearer\s+/i, '');
    if (!this.token) throw new PaymentError('Для xRocket нужен API-ключ');
    if (!['auto', 'current', 'legacy'].includes(apiVersion)) throw new PaymentError('XROCKET_API_VERSION: auto, current или legacy');
    this.apiVersion = apiVersion === 'auto' ? (/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(this.token) ? 'current' : 'legacy') : apiVersion;
    this.webhookToken = String(webhookToken || '').trim();
    this.invoiceCache = new Map(); this.budgets = new Map();
    this.baseUrl = (baseUrl || (this.apiVersion === 'current' ? (testnet ? CURRENT_TESTNET : CURRENT_MAINNET) : (testnet ? TESTNET : MAINNET))).replace(/\/+$/, '');
    // У xRocket свои коды монет: TON называется TONCOIN.
    this.currency = String(currency || 'USDT').toUpperCase();
    this.returnUrl = returnUrl || null;
    this.fetchImpl = fetchImpl;
  }

  get id() {
    return 'xrocket';
  }

  get title() {
    return 'xRocket';
  }

  get signatureHeader() {
    return this.apiVersion === 'current' ? 'signature' : SIGNATURE_HEADER;
  }

  // ——— Вызовы API ———

  async call(path, { method = 'GET', body = null } = {}) {
    const { status, data } = await requestJson(`${this.baseUrl}${path}`, {
      method,
      body,
      headers: { 'Rocket-Pay-Key': this.token },
      fetchImpl: this.fetchImpl,
    });

    if (!data || data.success !== true) {
      const error = data && (data.message || (Array.isArray(data.errors) && data.errors.map((e) => e.error || e.message).join(', ')));
      throw new PaymentError(`xRocket отказал: ${error || `HTTP ${status}`}`, { ambiguous: status >= 500 });
    }
    return data.data;
  }

  async currentCall(route, { method = 'GET', body = null } = {}) {
    const key = method + ':' + route.split('?')[0], now = Date.now();
    const recent = (this.budgets.get(key) || []).filter(time => now - time < 60000);
    if (recent.length >= 18) throw new PaymentError('xRocket: лимит запросов, повторите проверку через минуту');
    recent.push(now); this.budgets.set(key, recent);
    const { status, data } = await requestJson(`${this.baseUrl}/api/v1/${route}`, {
      method, body, headers: { Authorization: `Bearer ${this.token}` }, fetchImpl: this.fetchImpl,
    });
    if (status < 200 || status >= 300 || !data || data.type) {
      const code = String(data?.type || data?.title || 'HTTP_' + status).slice(0, 160).split(this.token).join('[скрыто]');
      const error = new PaymentError(`xRocket Pay API: ${code} (HTTP ${status})`, { ambiguous: status >= 500 });
      error.status = status;
      if (status === 429) this.budgets.set(key, Array(18).fill(Date.now()));
      throw error;
    }
    return data;
  }

  async getMe() {
    return this.apiVersion === 'current' ? this.currentCall('app-info') : this.call('/app/info');
  }

  async createInvoice({ amount, description, payload, expiresIn = 3600, hiddenMessage = null }) {
    if (this.apiVersion === 'current') {
      const body = { priceAmount: String(amount), priceCurrency: this.currency,
        payCurrencies: [this.currency], clientInvoiceId: String(payload), description, expiresIn };
      if (this.returnUrl) body.url = { successUrl: this.returnUrl, cancelUrl: this.returnUrl };
      const invoice = await this.currentCall('invoices', { method: 'POST', body });
      const normalized = this.normalizeCurrent(invoice);
      if (!normalized.id || !normalized.url) throw new PaymentError('xRocket не вернул ссылку на счёт', { ambiguous: true });
      return normalized;
    }
    const body = {
      amount: Number(amount),
      numPayments: 1,
      currency: this.currency,
      description,
      payload,
      commentsEnabled: false,
      expiredIn: expiresIn,
    };
    if (hiddenMessage) body.hiddenMessage = hiddenMessage;
    if (this.returnUrl) body.callbackUrl = this.returnUrl;

    const invoice = await this.call('/tg-invoices', { method: 'POST', body });
    return this.normalize(invoice);
  }

  async getInvoice(invoiceId) {
    if (this.apiVersion === 'current') {
      const key = String(invoiceId), cached = this.invoiceCache.get(key);
      if (cached && Date.now() - cached.at < 10000) return cached.promise;
      if (this.invoiceCache.size >= 1000) this.invoiceCache.delete(this.invoiceCache.keys().next().value);
      const promise = this.currentCall('invoice?invoiceId=' + encodeURIComponent(key)).then(invoice => this.normalizeCurrent(invoice));
      const entry = { at: Date.now(), promise }; this.invoiceCache.set(key, entry);
      try { return await promise; } catch (error) { if (this.invoiceCache.get(key) === entry) this.invoiceCache.delete(key); throw error; }
    }
    const invoice = await this.call(`/tg-invoices/${encodeURIComponent(invoiceId)}`);
    return invoice ? this.normalize(invoice) : null;
  }

  normalizeCurrent(invoice) {
    const amount = Number(invoice.priceAmount);
    if (!invoice.id || !Number.isFinite(amount) || amount <= 0 || !invoice.priceCurrency) {
      throw new PaymentError('xRocket вернул неполный счёт', { ambiguous: true });
    }
    return { id: String(invoice.id), status: invoice.status === 'cancelled' ? 'expired' : invoice.status,
      amount, paidAmount: amount, currency: invoice.priceCurrency,
      payload: invoice.clientInvoiceId || null,
      url: invoice.links?.telegramBotLink || null, fallbackUrl: null, paidAt: null };
  }

  // Приводим ответ xRocket к общему виду. Оплаченную сумму берём из payments:
  // счёт может быть закрыт платежом чуть больше или меньше запрошенного.
  normalize(invoice, payment = null) {
    const fact = payment
      || (Array.isArray(invoice.payments) && invoice.payments.length ? invoice.payments[invoice.payments.length - 1] : null);
    return {
      id: String(invoice.id),
      status: invoice.status, // active | paid | expired
      amount: Number(invoice.amount),
      paidAmount: fact && fact.paymentAmount !== undefined ? Number(fact.paymentAmount) : Number(invoice.amount),
      currency: invoice.currency || this.currency,
      payload: invoice.payload || null,
      url: invoice.link || null,
      fallbackUrl: null,
      paidAt: (fact && fact.paid) || invoice.paid || null,
    };
  }

  // ——— Выплата ———

  get supportsPayout() {
    return true;
  }

  // transferId — ключ идемпотентности: повтор с тем же ключом не создаёт
  // второй перевод, поэтому запрос можно безопасно повторить.
  async payout({ userId, amount, spendId, comment = null }) {
    if (this.apiVersion === 'current') {
      // A timed-out POST can already have paid. Always look up the same client id
      // before retrying, and never mark a merely pending response as successful.
      let result;
      try { result = await this.currentCall('payout?clientPayoutId=' + encodeURIComponent(spendId)); }
      catch (error) { if (error.status !== 404) throw new PaymentError(error.message, { ambiguous: true }); }
      if (!result) result = await this.currentCall('payouts', { method: 'POST', body: {
        target: String(userId), targetType: 'telegram_user_id', asset: this.currency,
        amount: String(amount), clientPayoutId: spendId, ...(comment ? { description: comment } : {}),
      } });
      if (result.status === 'failed') throw new PaymentError('xRocket отклонил выплату');
      if (result.status !== 'finished' || !result.payoutId) throw new PaymentError('xRocket обрабатывает выплату', { ambiguous: true });
      return { id: String(result.payoutId), status: 'completed', amount: Number(result.amount) };
    }
    const transfer = await this.call('/app/transfer', {
      method: 'POST',
      body: {
        tgUserId: Number(userId),
        currency: this.currency,
        amount: Number(amount),
        transferId: spendId,
        description: comment || undefined,
      },
    });
    return {
      id: String(transfer.id),
      status: 'completed',
      amount: Number(transfer.amount),
    };
  }

  // ——— Вебхук ———

  verifyWebhook(rawBody, signature, headers = {}) {
    if (this.apiVersion === 'current') {
      const timestamp = headers['signature-timestamp'];
      if (!this.webhookToken || headers['signature-version'] !== 'v1' || !/^\d{13}$/.test(String(timestamp || ''))
        || Math.abs(Date.now() - Number(timestamp)) > 300000) return false;
      const expected = crypto.createHmac('sha256', this.webhookToken).update(String(timestamp) + '.').update(rawBody).digest('hex');
      return signaturesMatch(expected, signature);
    }
    return signaturesMatch(signBody(this.token, rawBody), signature);
  }

  parseWebhook(rawBody) {
    let update;
    try {
      update = JSON.parse(rawBody);
    } catch {
      throw new PaymentError('Вебхук xRocket прислал не JSON');
    }
    if (this.apiVersion === 'current') {
      if (update?.type !== 'invoice' || update.data?.event !== 'invoice_status_changed' || update.data.invoice?.status !== 'paid') return null;
      return this.normalizeCurrent(update.data.invoice);
    }
    if (!update || update.type !== 'invoicePay' || !update.data) return null;

    const invoice = this.normalize(update.data, update.data.payment || null);
    if (invoice.status !== 'paid') return null;
    return invoice;
  }
}

module.exports = { XRocketProvider, MAINNET, TESTNET, CURRENT_MAINNET, CURRENT_TESTNET };
