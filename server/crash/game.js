'use strict';
const { randomInt } = require('node:crypto');
const RATE = 0.09;
const MAX = 1000000;
class CrashError extends Error {}
function samplePoint() {
  const u = randomInt(1, 2 ** 48) / 2 ** 48;
  return Math.max(1, Math.min(MAX, Math.floor(0.99 / u * 100) / 100));
}
const floorMoney = value => Math.floor(value + Number.EPSILON * 8 * Math.max(1, value));
class CrashGame {
  constructor({ draw = samplePoint } = {}) {
    this.draw = draw; this.phase = 'bet'; this.revision = 0; this.history = [];
    this.bet = 0; this.payout = 0; this.multiplier = 1; this.settled = true;
    this.autoStop = null; this.startedAt = 0; this.result = null;
  }
  check(revision) {
    if (revision !== this.revision) throw new CrashError('Состояние обновилось. Повторите действие');
  }
  validate(amount, autoStop) {
    if (this.phase === 'play' || !this.settled) throw new CrashError('Предыдущий раунд ещё не завершён');
    if (!Number.isSafeInteger(amount) || amount < 10 || amount > 10000000) throw new CrashError('Ставка от $0.10 до $100 000');
    if (autoStop !== null && (!Number.isFinite(autoStop) || autoStop < 1.01 || autoStop > MAX || Math.abs(autoStop * 100 - Math.round(autoStop * 100)) > 1e-6)) throw new CrashError('Автостоп: от 1.01× до 1 000 000×, не более двух знаков после точки');
  }
  start(amount, autoStop, revision, now = Date.now()) {
    this.check(revision); this.validate(amount, autoStop);
    const point = this.draw();
    if (!Number.isFinite(point) || point < 1 || point > MAX) throw new CrashError('Не удалось начать раунд');
    this.phase = 'play'; this.bet = amount; this.autoStop = autoStop; this.point = point;
    this.startedAt = now; this.multiplier = 1; this.payout = 0; this.result = null; this.settled = false; this.revision++;
  }
  at(multiplier) { return this.startedAt + Math.log(multiplier) / RATE * 1000; }
  current(now) { return Math.max(1, Math.min(MAX, Math.exp(RATE * Math.max(0, now - this.startedAt) / 1000))); }
  advance(now = Date.now()) {
    if (this.phase !== 'play') return;
    // Resolve events by their scheduled times, even after a delayed timer/restart.
    if (this.autoStop !== null && this.autoStop <= this.point && now >= this.at(this.autoStop)) this.finish('win', this.autoStop);
    else if (now >= this.at(this.point)) this.finish(this.point === MAX ? 'win' : 'lose', this.point);
  }
  cashout(revision, now = Date.now()) {
    this.check(revision); this.advance(now);
    if (this.phase !== 'play') throw new CrashError('Раунд уже завершён');
    this.finish('win', Math.floor(this.current(now) * 100) / 100);
  }
  finish(result, multiplier) {
    this.phase = 'done'; this.result = result; this.multiplier = multiplier;
    this.payout = result === 'win' ? floorMoney(this.bet * multiplier) : 0;
    this.revision++;
    this.history = [{ multiplier, result }, ...this.history].slice(0, 20);
  }
  snapshot() {
    const { draw, ...saved } = this;
    return { version: 1, ...saved };
  }
  restore(saved) {
    if (!saved || saved.version !== 1) return;
    for (const key of ['phase','revision','history','bet','payout','multiplier','settled','autoStop','startedAt','result','point']) this[key] = saved[key];
  }
  state(now = Date.now()) {
    const multiplier = this.phase === 'play' ? Math.floor(this.current(now) * 100) / 100 : this.multiplier;
    // Do not expose the preselected crash point or its time during play.
    return { phase:this.phase, revision:this.revision, bet:this.bet, autoStop:this.autoStop,
      multiplier, payout:this.payout, available:this.phase==='play'?floorMoney(this.bet*multiplier):this.payout,
      settled:this.settled, result:this.result, history:this.history, startedAt:this.startedAt,
      serverNow:now, rate:RATE, minBet:10, maxBet:10000000, minAuto:1.01, maxAuto:MAX };
  }
}
module.exports = { CrashGame, CrashError, RATE, MAX };
