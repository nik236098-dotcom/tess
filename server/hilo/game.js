'use strict';
const { randomInt } = require('node:crypto');
class HiloError extends Error {}
const EDGE = 0.03;
const MAX_MULTIPLIER = 10000;
function draw() { const n = randomInt(52); return { rank: n % 13 + 1, suit: ['s', 'h', 'c', 'd'][Math.floor(n / 13)] }; }
class HiloGame {
  constructor({ rng = draw } = {}) {
    this.rng = rng;
    this.card = rng();
    this.revision = 0;
    this.reset();
  }
  snapshot() {
    return { version: 1, ...this.state(), steps: this.steps, settled: this.settled };
  }
  restore(saved) {
    if (!saved || saved.version !== 1) return;
    for (const key of ['phase', 'revision', 'card', 'bet', 'multiplier', 'steps', 'history', 'payout', 'result', 'settled']) this[key] = saved[key];
  }
  reset() {
    this.phase = 'bet'; this.bet = 0; this.multiplier = 1; this.steps = 0;
    this.history = []; this.payout = 0; this.result = null; this.settled = false;
  }
  check(revision) {
    if (revision !== this.revision) throw new HiloError('Состояние обновилось. Повторите действие');
  }
  start(amount, revision) {
    this.check(revision);
    if (this.phase === 'play') throw new HiloError('Раунд уже идёт');
    if (!Number.isSafeInteger(amount) || amount < 10 || amount > 10000000) throw new HiloError('Ставка от $0.10 до $100 000');
    this.reset(); this.bet = amount; this.phase = 'play'; this.revision++;
    this.history.push({ card: this.card, direction: 'start', multiplier: 1 });
  }
  odds(direction) { return (direction === 'high' ? 14 - this.card.rank : this.card.rank) / 13; }
  skip(revision) {
    this.check(revision);
    if (this.phase === 'done') this.reset();
    this.card = this.rng(); this.revision++;
    if (this.phase === 'play') this.record('skip');
  }
  record(direction, won = true) {
    this.history.push({ card: this.card, direction, won, multiplier: this.multiplier });
    this.history = this.history.slice(-20);
  }
  pick(direction, revision) {
    this.check(revision);
    if (this.phase !== 'play') throw new HiloError('Сначала сделайте ставку');
    if (!['high', 'low'].includes(direction)) throw new HiloError('Выберите выше или ниже');
    const probability = this.odds(direction);
    if (probability === 1) throw new HiloError('Выберите другое направление или пропустите карту');
    const next = this.rng();
    const won = direction === 'high' ? next.rank >= this.card.rank : next.rank <= this.card.rank;
    this.card = next; this.revision++;
    if (won) {
      this.steps++;
      this.multiplier = Math.min(MAX_MULTIPLIER, Math.floor(this.multiplier * (1 - EDGE) / probability * 1000000) / 1000000);
    } else { this.phase = 'done'; this.result = 'lose'; }
    this.record(direction, won);
    if (won && this.multiplier === MAX_MULTIPLIER) this.cashout(this.revision);
  }
  cashout(revision) {
    this.check(revision);
    if (this.phase !== 'play') throw new HiloError('Сейчас нет раунда');
    this.phase = 'done'; this.result = 'win'; this.payout = Math.floor(this.bet * this.multiplier); this.revision++;
  }
  state() {
    return { phase: this.phase, revision: this.revision, card: this.card, bet: this.bet, multiplier: this.multiplier,
      payout: this.payout, available: this.phase === 'play' ? Math.floor(this.bet * this.multiplier) : this.payout,
      result: this.result, history: this.history, high: this.odds('high'), low: this.odds('low'),
      minBet: 10, maxBet: 10000000, maxMultiplier: MAX_MULTIPLIER };
  }
}
module.exports = { HiloGame, HiloError };
