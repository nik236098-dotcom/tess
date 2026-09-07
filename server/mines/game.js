'use strict';

// Mines: поле 5×5, игрок сам выбирает число мин, открывает клетки и в любой
// момент после первой безопасной может забрать выигрыш. Игра одиночная и
// целиком живёт на сервере: расположение мин клиент узнаёт только после
// конца раунда, ставки и выплаты — в центах, как во всех играх проекта.

const crypto = require('crypto');

const SIZE = 25;
const MIN_MINES = 1;
const MAX_MINES = 24;
const HOUSE_EDGE = 0.03; // множитель = 97 % от честного

class MinesError extends Error {}

// Честный множитель после `opened` безопасных клеток — произведение
// шансов «не подорваться» на каждом шаге, обратное; срезаем маржу и
// округляем вниз до сотых, как показываем игроку.
function multiplier(mines, opened) {
  if (opened <= 0) return 1;
  let value = 1;
  for (let i = 0; i < opened; i += 1) value *= (SIZE - i) / (SIZE - mines - i);
  return Math.floor(value * (1 - HOUSE_EDGE) * 100) / 100;
}

function secureRandom() {
  return crypto.randomInt(0, 2 ** 48 - 1) / (2 ** 48 - 1);
}

function layoutMines(mines, rng) {
  const cells = Array.from({ length: SIZE }, (_, i) => i);
  for (let i = cells.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [cells[i], cells[j]] = [cells[j], cells[i]];
  }
  return new Set(cells.slice(0, mines));
}

class MinesGame {
  constructor({ minBet, maxBet } = {}) {
    this.minBet = minBet ?? 10;
    this.maxBet = maxBet ?? 1000000;
    this.reset();
  }

  reset() {
    this.phase = 'bet'; // bet | play | done
    this.bet = 0;
    this.mines = 3;
    this.layout = new Set();
    this.opened = new Set();
    this.result = null; // win | lose
    this.payout = 0;
    this.settled = false;
  }

  start(bet, mines, rng = secureRandom) {
    if (this.phase === 'play') throw new MinesError('Раунд уже идёт');
    const amount = Math.round(Number(bet));
    if (!Number.isFinite(amount) || amount < this.minBet) throw new MinesError(`Минимальная ставка ${(this.minBet / 100).toFixed(2)} $`);
    if (amount > this.maxBet) throw new MinesError(`Максимальная ставка ${(this.maxBet / 100).toFixed(2)} $`);
    const count = Math.round(Number(mines));
    if (!Number.isFinite(count) || count < MIN_MINES || count > MAX_MINES) throw new MinesError(`Мин должно быть от ${MIN_MINES} до ${MAX_MINES}`);
    this.reset();
    this.phase = 'play';
    this.bet = amount;
    this.mines = count;
    this.layout = layoutMines(count, rng);
  }

  open(index) {
    if (this.phase !== 'play') throw new MinesError('Сейчас нет раунда');
    const cell = Number(index);
    if (!Number.isInteger(cell) || cell < 0 || cell >= SIZE) throw new MinesError('Нет такой клетки');
    if (this.opened.has(cell)) throw new MinesError('Клетка уже открыта');
    if (this.layout.has(cell)) {
      this.phase = 'done';
      this.result = 'lose';
      this.payout = 0;
      this.boom = cell;
      return;
    }
    this.opened.add(cell);
    // Все безопасные клетки открыты — забирать больше нечего, платим сразу.
    if (this.opened.size === SIZE - this.mines) this.cashout();
  }

  cashout() {
    if (this.phase !== 'play') throw new MinesError('Сейчас нет раунда');
    if (!this.opened.size) throw new MinesError('Сначала откройте хотя бы одну клетку');
    this.phase = 'done';
    this.result = 'win';
    this.payout = Math.floor(this.bet * this.multiplier);
  }

  get multiplier() {
    return multiplier(this.mines, this.opened.size);
  }

  get next() {
    return multiplier(this.mines, this.opened.size + 1);
  }

  state() {
    const done = this.phase === 'done';
    return {
      phase: this.phase,
      bet: this.bet,
      mines: this.mines,
      opened: Array.from(this.opened),
      multiplier: this.multiplier,
      next: this.phase === 'play' ? this.next : null,
      result: this.result,
      payout: this.payout,
      net: done ? this.payout - this.bet : 0,
      boom: done && this.result === 'lose' ? this.boom : null,
      field: done ? Array.from({ length: SIZE }, (_, i) => (this.layout.has(i) ? 'mine' : 'gem')) : null,
    };
  }
}

module.exports = { MinesGame, MinesError, multiplier, layoutMines, SIZE, MIN_MINES, MAX_MINES, HOUSE_EDGE };
