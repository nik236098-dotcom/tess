'use strict';

// Nvuti: игрок выбирает число на шкале 1–100 и режим «меньше» или «больше»;
// сервер бросает случайное число 1–100. «Меньше N» выигрывает при броске
// ≤ N (шанс N %), «больше N» — при броске > N (шанс 100 − N %). Выплата —
// 97 % от честной. Раунд мгновенный и без состояния, как в рулетке.

const crypto = require('crypto');

const MIN_TARGET = 5; // шанс не меньше 5 % и не больше 95 % в любом режиме
const MAX_TARGET = 95;
const HOUSE_EDGE = 0.03;
const MODES = ['under', 'over'];

class NvutiError extends Error {}

function chanceOf(target, mode) {
  return mode === 'under' ? target : 100 - target;
}

// Множитель для шанса в процентах: 97 / chance, вниз до сотых.
function multiplierFor(chance) {
  return Math.floor(((1 - HOUSE_EDGE) * 100 / chance) * 100 + 1e-9) / 100; // 1e-9 — против 19.399999
}

function normalize(target, mode) {
  const value = Math.round(Number(target));
  if (!Number.isFinite(value) || value < MIN_TARGET || value > MAX_TARGET) {
    throw new NvutiError(`Число должно быть от ${MIN_TARGET} до ${MAX_TARGET}`);
  }
  if (!MODES.includes(mode)) throw new NvutiError('Неизвестный режим');
  return { target: value, mode };
}

function rollNumber() {
  return crypto.randomInt(1, 101);
}

function play({ bet, target, mode, roll = rollNumber() }) {
  const amount = Math.round(Number(bet));
  if (!Number.isFinite(amount) || amount <= 0) throw new NvutiError('Некорректная ставка');
  const pick = normalize(target, mode);
  const chance = chanceOf(pick.target, pick.mode);
  const multiplier = multiplierFor(chance);
  const won = pick.mode === 'under' ? roll <= pick.target : roll > pick.target;
  const payout = won ? Math.floor(amount * multiplier) : 0;
  return { roll, target: pick.target, mode: pick.mode, chance, multiplier, won, bet: amount, payout, net: payout - amount };
}

module.exports = { play, normalize, chanceOf, multiplierFor, NvutiError, MIN_TARGET, MAX_TARGET, HOUSE_EDGE, MODES };
