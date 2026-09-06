'use strict';

// Европейская рулетка: одно зеро, 37 карманов. Ставки принимаются
// списком, выплаты по классическим коэффициентам: число 35:1, колонка и
// дюжина 2:1, красное/чёрное, чёт/нечет, 1–18/19–36 — 1:1.

// Порядок карманов на колесе по часовой стрелке, начиная с зеро.
const WHEEL_ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);

class RouletteError extends Error {}

function colourOf(number) {
  if (number === 0) return 'green';
  return RED.has(number) ? 'red' : 'black';
}

// Ставка: { type, value, amount }. value — число для straight, 1..3 для
// column/dozen, для остальных не нужен.
const BET_TYPES = {
  straight: { payout: 35, wins: (n, v) => n === v, valid: (v) => Number.isInteger(v) && v >= 0 && v <= 36 },
  column: { payout: 2, wins: (n, v) => n !== 0 && ((n - 1) % 3) + 1 === v, valid: (v) => [1, 2, 3].includes(v) },
  dozen: { payout: 2, wins: (n, v) => n !== 0 && Math.ceil(n / 12) === v, valid: (v) => [1, 2, 3].includes(v) },
  red: { payout: 1, wins: (n) => colourOf(n) === 'red' },
  black: { payout: 1, wins: (n) => colourOf(n) === 'black' },
  even: { payout: 1, wins: (n) => n !== 0 && n % 2 === 0 },
  odd: { payout: 1, wins: (n) => n % 2 === 1 },
  low: { payout: 1, wins: (n) => n >= 1 && n <= 18 },
  high: { payout: 1, wins: (n) => n >= 19 && n <= 36 },
};

function normalizeBets(raw, { minBet, maxBet, maxTotal }) {
  if (!Array.isArray(raw) || raw.length === 0) throw new RouletteError('Сделайте хотя бы одну ставку');
  if (raw.length > 60) throw new RouletteError('Слишком много ставок');
  const bets = [];
  let total = 0;
  for (const item of raw) {
    const type = item && BET_TYPES[item.type] ? item.type : null;
    if (!type) throw new RouletteError('Неизвестный тип ставки');
    const rule = BET_TYPES[type];
    const value = item.value === undefined || item.value === null ? null : Number(item.value);
    if (rule.valid && !rule.valid(value)) throw new RouletteError('Некорректная ставка');
    const amount = Math.round(Number(item.amount));
    if (!Number.isFinite(amount) || amount < minBet) throw new RouletteError(`Минимальная ставка ${minBet}`);
    if (amount > maxBet) throw new RouletteError(`Максимальная ставка ${maxBet}`);
    total += amount;
    bets.push({ type, value: rule.valid ? value : null, amount });
  }
  if (total > maxTotal) throw new RouletteError('Недостаточно средств');
  return { bets, total };
}

// Розыгрыш: число выбирается rng, каждая ставка рассчитывается отдельно.
function spin(bets, rng = Math.random) {
  const number = Math.min(36, Math.floor(rng() * 37));
  return settle(bets, number);
}

function settle(bets, number) {
  let payout = 0;
  let stake = 0;
  const results = bets.map((bet) => {
    const rule = BET_TYPES[bet.type];
    const won = rule.wins(number, bet.value);
    const win = won ? bet.amount * (rule.payout + 1) : 0;
    payout += win;
    stake += bet.amount;
    return { ...bet, won, payout: win };
  });
  return { number, colour: colourOf(number), bets: results, payout, stake, net: payout - stake };
}

module.exports = { WHEEL_ORDER, RED, BET_TYPES, RouletteError, colourOf, normalizeBets, spin, settle };
