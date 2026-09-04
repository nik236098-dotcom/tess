'use strict';

const { PaymentError, requestJson, signBody, signaturesMatch } = require('./common');

// xRocket (@xRocket) — xRocket Pay API.
// https://pay.xrocket.tg/api  (спека: /tg-invoices)
//
// Ключ берётся в боте: Rocket Pay → Create App → API token.

const MAINNET = 'https://pay.xrocket.tg';
const TESTNET = 'https://dev-pay.xrocket.tg';

const SIGNATURE_HEADER = 'rocket-pay-signature';

class XRocketProvider {
  constructor({ token, testnet = false, baseUrl = null, currency = 'USDT', returnUrl = null, fetchImpl = null } = {}) {
    if (!token) throw new PaymentError('Для xRocket нужен API-ключ');
    this.token = String(token);
    this.baseUrl = (baseUrl || (testnet ? TESTNET : MAINNET)).replace(/\/+$/, '');
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
    return SIGNATURE_HEADER;
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

  async getMe() {
    return this.call('/app/info');
  }

  async createInvoice({ amount, description, payload, expiresIn = 3600, hiddenMessage = null }) {
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
    const invoice = await this.call(`/tg-invoices/${encodeURIComponent(invoiceId)}`);
    return invoice ? this.normalize(invoice) : null;
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

  verifyWebhook(rawBody, signature) {
    return signaturesMatch(signBody(this.token, rawBody), signature);
  }

  parseWebhook(rawBody) {
    let update;
    try {
      update = JSON.parse(rawBody);
    } catch {
      throw new PaymentError('Вебхук xRocket прислал не JSON');
    }
    if (!update || update.type !== 'invoicePay' || !update.data) return null;

    const invoice = this.normalize(update.data, update.data.payment || null);
    if (invoice.status !== 'paid') return null;
    return invoice;
  }
}

module.exports = { XRocketProvider, MAINNET, TESTNET };
