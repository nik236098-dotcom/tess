'use strict';

// Деньги везде внутри сервера — целые центы.
//
// Дробные доллары во float складывать нельзя: 0.1 + 0.2 !== 0.3, а покерный
// движок делит банк, считает сайд-поты и возвращает непокрытые ставки. Одна
// потерянная сотая — и банк не сойдётся. Поэтому наружу центы превращаются
// в «$12.34» только при показе, а внутрь приходят обратно целыми.

const CENTS_IN_DOLLAR = 100;

// 1234 -> "$12.34"
function formatMoney(cents) {
  const value = Math.round(Number(cents) || 0);
  const sign = value < 0 ? '-' : '';
  const absolute = Math.abs(value);
  return `${sign}$${Math.floor(absolute / CENTS_IN_DOLLAR)}.${String(absolute % CENTS_IN_DOLLAR).padStart(2, '0')}`;
}

// "12.34", "12,34", "$12.34", 12.34 -> 1234. null, если это не сумма.
function parseMoney(input) {
  if (typeof input === 'number') {
    if (!Number.isFinite(input)) return null;
    return Math.round(input * CENTS_IN_DOLLAR);
  }
  const text = String(input ?? '').trim().replace(/\s+/g, '').replace(',', '.').replace(/^\$/, '');
  if (!/^-?\d*\.?\d*$/.test(text) || text === '' || text === '.' || text === '-') return null;
  const value = Number(text);
  if (!Number.isFinite(value)) return null;
  return Math.round(value * CENTS_IN_DOLLAR);
}

const toDollars = (cents) => Math.round(Number(cents) || 0) / CENTS_IN_DOLLAR;
const toCents = (dollars) => Math.round(Number(dollars) * CENTS_IN_DOLLAR);

module.exports = { formatMoney, parseMoney, toDollars, toCents, CENTS_IN_DOLLAR };
