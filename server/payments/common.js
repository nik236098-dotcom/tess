'use strict';

const crypto = require('crypto');

// Общее для обоих платёжных провайдеров: ошибки, HTTP-запрос и проверка подписи.
// Внешних зависимостей нет — как и во всём остальном проекте.

// ambiguous = мы не знаем, выполнил ли сервис операцию: связь оборвалась,
// вышло время или пришёл 5xx. Для вывода денег это принципиально: вернуть
// сумму на баланс после такой ошибки — значит рискнуть выплатить дважды.
class PaymentError extends Error {
  constructor(message, { ambiguous = false } = {}) {
    super(message);
    this.ambiguous = ambiguous;
  }
}

const DEFAULT_TIMEOUT_MS = 15000;

// Тонкая обёртка над fetch: свой таймаут (иначе запрос может висеть вечно)
// и разбор JSON с понятной ошибкой вместо «Unexpected token < in JSON».
async function requestJson(url, { method = 'GET', headers = {}, body = null, timeoutMs = DEFAULT_TIMEOUT_MS, fetchImpl = null } = {}) {
  const call = fetchImpl || globalThis.fetch;
  if (typeof call !== 'function') {
    throw new PaymentError('В этой версии Node нет fetch — нужен Node 18 или новее');
  }

  const init = { method, headers };
  if (body !== null && body !== undefined) {
    init.body = typeof body === 'string' ? body : JSON.stringify(body);
    init.headers = { 'Content-Type': 'application/json', ...headers };
  }
  // AbortSignal.timeout есть с Node 17.3; если его почему-то нет — идём без таймаута.
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    init.signal = AbortSignal.timeout(timeoutMs);
  }

  let response;
  try {
    response = await call(url, init);
  } catch (error) {
    const reason = error && (error.name === 'TimeoutError' || error.name === 'AbortError')
      ? 'превышено время ожидания'
      : error.message;
    // Запрос мог дойти и выполниться — ответ просто не вернулся.
    throw new PaymentError(`Платёжный сервис недоступен: ${reason}`, { ambiguous: true });
  }

  const text = await response.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new PaymentError(`Платёжный сервис ответил не JSON (HTTP ${response.status})`, { ambiguous: true });
  }
  return { status: response.status, data: parsed };
}

// Секрет для подписи вебхука у обоих сервисов считается одинаково:
// SHA-256 от API-токена, а сам подпись — HMAC-SHA256 по сырому телу запроса.
function webhookSecret(token) {
  return crypto.createHash('sha256').update(String(token)).digest();
}

function signBody(token, rawBody) {
  return crypto.createHmac('sha256', webhookSecret(token)).update(rawBody).digest('hex');
}

// Сравнение подписей за постоянное время: обычное === утекает информацию
// о том, сколько символов совпало, и позволяет подобрать подпись побайтово.
function signaturesMatch(expectedHex, receivedHex) {
  if (typeof receivedHex !== 'string' || !/^[0-9a-fA-F]+$/.test(receivedHex)) return false;
  const expected = Buffer.from(expectedHex, 'hex');
  const received = Buffer.from(receivedHex.toLowerCase(), 'hex');
  if (expected.length !== received.length) return false;
  return crypto.timingSafeEqual(expected, received);
}

module.exports = { PaymentError, requestJson, signBody, signaturesMatch, webhookSecret };
