'use strict';
const { randomInt } = require('node:crypto');
const catalog = require('./catalog');
const abyss = require('./abyss');
const { MAX_BALANCE } = require('../accounts');

class ArcadeError extends Error {}
const GAMES = ['plinko', 'tower', 'keno', 'dragon', 'abyss', ...catalog.ids];
const MIN_BET = 10;
const ROWS = 10;
const FLOORS = 9;
const choose = (n, k) => {
  if (k < 0 || k > n) return 0;
  let value = 1;
  for (let i = 1; i <= k; i++) value = value * (n - i + 1) / i;
  return value;
};
const moneyAt = (bet, multiplier) => Math.floor(bet * Math.round(multiplier * 100) / 100);
const plinkoProbabilities = Array.from({ length:ROWS+1 }, (_,k) => choose(ROWS,k)/2**ROWS);
// Stake-style 10-row presets. Values checked against the visible payout tables;
// see docs/ARCADE.md for primary rules and the independent table source.
const PLINKO = {
  low:[8.9,3,1.4,1.1,1,.5,1,1.1,1.4,3,8.9],
  medium:[22,5,2,1.4,.6,.4,.6,1.4,2,5,22],
  high:[76,10,3,.9,.3,.2,.3,.9,3,10,76],
};
// Classic Keno paytable, verified against the visible Stake Analyzer tables.
const KENO = {1:[0,3.96],2:[0,1.9,4.5],3:[0,1,3.1,10.4],4:[0,.8,1.8,5,22.5],5:[0,.25,1.4,4.1,16.5,36],6:[0,0,1,3.68,7,16.5,40],7:[0,0,.47,3,4.5,14,31,60],8:[0,0,0,2.2,4,13,22,55,70],9:[0,0,0,1.55,3,8,15,44,60,85],10:[0,0,0,1.4,2.25,4.5,8,17,50,80,100]};
// Stake Dragon Tower: 9 floors, published egg/tile ratios and 98% RTP.
const LEVELS = { easy:{safe:3,columns:4}, medium:{safe:2,columns:3}, hard:{safe:1,columns:2}, expert:{safe:1,columns:3}, master:{safe:1,columns:4} };
const TOWER = Object.fromEntries(Object.entries(LEVELS).map(([key, {safe,columns}]) =>
  [key, Array.from({ length:FLOORS }, (_,i) => Math.round(.98 * (columns/safe) ** (i+1) * 100) / 100)]));
function maxBet(game, level) {
  if (game === 'tower') return 100000;
  const max = game === 'plinko' ? Math.max(...Object.values(PLINKO).flat())
    : game === 'tower' ? Math.max(...(TOWER[level] || Object.values(TOWER).flat()))
      : game === 'keno' ? Math.max(...Object.values(KENO).flat()) : 12;
  return Math.min(100000, Math.floor(MAX_BALANCE / max));
}
function config(game) {
  if (game === 'abyss') return abyss.config();
  if (catalog.ids.includes(game)) return catalog.config(game);
  if (!GAMES.includes(game)) throw new ArcadeError('Игра не найдена');
  const base = { minBet: game === 'tower' ? 100 : MIN_BET, maxBet: maxBet(game) };
  if (game === 'plinko') return { ...base, rows: ROWS, maxBalls: 25, tables: PLINKO, probabilities: plinkoProbabilities };
  // All five Tower difficulties share the same $1–$1000 range.
  if (game === 'tower') return { ...base, maxBets: Object.fromEntries(Object.keys(LEVELS).map(level => [level, maxBet(game, level)])), floors: FLOORS, levels: LEVELS, tables: TOWER };
  if (game === 'keno') return { ...base, size: 40, drawCount: 10, maxPicks: 10, tables: KENO };
  return { ...base, table: { dragon: 2, tiger: 2, tie: 12 }, tieReturn: .5 };
}
function initial() {
  return { version: 1, revision: 0, phase: 'bet', settled: true, bet: 0, payout: 0, multiplier: 0, result: null, history: [] };
}
function check(round, revision) {
  if (!Number.isSafeInteger(revision) || round.revision !== revision) throw new ArcadeError('Раунд обновился. Повторите действие');
}
function optionsFor(game, options = {}) {
  if (!options || typeof options !== 'object' || Array.isArray(options)) throw new ArcadeError('Некорректные настройки');
  if (game === 'plinko') {
    if (!Object.hasOwn(PLINKO, options.risk)) throw new ArcadeError('Выберите риск');
    const count = options.count ?? 1;
    if (!Number.isInteger(count) || count < 1 || count > 25) throw new ArcadeError('Выберите от 1 до 25 шариков');
    return { risk: options.risk, count };
  }
  if (game === 'tower') {
    if (!Object.hasOwn(TOWER, options.level)) throw new ArcadeError('Выберите сложность');
    return { level: options.level };
  }
  if (game === 'keno') {
    const picks = options.picks;
    if (!Array.isArray(picks) || picks.length < 1 || picks.length > 10 || new Set(picks).size !== picks.length || picks.some(n => !Number.isInteger(n) || n < 1 || n > 40)) throw new ArcadeError('Выберите от 1 до 10 разных чисел');
    return { picks: [...picks].sort((a, b) => a - b) };
  }
  if (!['dragon', 'tiger', 'tie'].includes(options.side)) throw new ArcadeError('Выберите сторону или ничью');
  return { side: options.side };
}
function sample(count, size, rng) {
  const pool = Array.from({ length: size }, (_, i) => i);
  for (let i = 0; i < count; i++) {
    const j = i + rng(size - i);
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, count);
}
function finish(round, multiplier, payout = moneyAt(round.bet, multiplier)) {
  round.phase = 'done'; round.multiplier = multiplier; round.payout = payout;
  round.result = round.payout > round.bet ? 'win' : round.payout === round.bet ? 'push' : 'lose';
  round.revision++;
  round.history = [{ multiplier, payout: round.payout, result: round.result }, ...round.history].slice(0, 15);
}
function start(game, previous, amount, options, revision, rng = randomInt) {
  if (game === 'abyss') return abyss.start(previous, amount, options, revision, rng);
  if (catalog.ids.includes(game)) return catalog.start(game, previous, amount, options, revision, rng);
  config(game); check(previous, revision);
  if (previous.phase === 'play' || !previous.settled) throw new ArcadeError('Сначала завершите предыдущий раунд');
  const selected = optionsFor(game, options);
  const limit = maxBet(game, selected.level);
  if (!Number.isSafeInteger(amount) || amount < config(game).minBet || amount > limit) throw new ArcadeError(`Ставка от $${(config(game).minBet / 100).toFixed(2)} до $${(limit / 100).toFixed(2)}`);
  const round = { ...initial(), revision: previous.revision + 1, phase: 'play', settled: false,
    history: previous.history, bet: amount, options: selected };
  if (game === 'plinko') {
    round.unitBet = amount;
    round.bet = amount * selected.count;
    round.balls = Array.from({length:selected.count}, () => {
      const path = Array.from({length:ROWS}, () => rng(2));
      const slot = path.reduce((sum,n) => sum+n,0), multiplier = PLINKO[selected.risk][slot];
      return {path,slot,multiplier,payout:moneyAt(amount,multiplier)};
    });
    round.path = round.balls[0].path; round.slot = round.balls[0].slot;
    const payout = round.balls.reduce((sum,ball) => sum+ball.payout,0);
    finish(round, payout / round.bet, payout);
  } else if (game === 'keno') {
    round.drawn = sample(10, 40, rng).map(n => n + 1);
    round.hits = round.drawn.filter(n => selected.picks.includes(n));
    finish(round, KENO[selected.picks.length][round.hits.length]);
  } else if (game === 'dragon') {
    round.cards = sample(2, 416, rng).map(n => ({ rank: n % 13 + 1, suit: 'schd'[Math.floor(n / 13) % 4] }));
    const [a, b] = round.cards;
    round.winner = a.rank === b.rank ? 'tie' : a.rank > b.rank ? 'dragon' : 'tiger';
    finish(round, selected.side === round.winner ? (round.winner === 'tie' ? 12 : 2) : round.winner === 'tie' && selected.side !== 'tie' ? .5 : 0);
  } else {
    const {safe,columns} = LEVELS[selected.level];
    round.traps = Array.from({ length: FLOORS }, () => sample(columns-safe,columns,rng));
    round.steps = []; round.floor = 0;
  }
  return round;
}
function actTower(previous, action, index, revision) {
  check(previous, revision);
  if (previous.phase !== 'play' || previous.settled) throw new ArcadeError('Начните новый раунд');
  const round = structuredClone(previous);
  if (action === 'ag_cashout') {
    if (!round.floor) throw new ArcadeError('Сначала пройдите один этаж');
    finish(round, TOWER[round.options.level][round.floor - 1]);
  } else {
    if (!Number.isInteger(index) || index < 0 || index >= LEVELS[round.options.level].columns) throw new ArcadeError('Выберите плитку текущего этажа');
    const safe = !round.traps[round.floor].includes(index);
    round.steps.push({ index, safe });
    if (!safe) finish(round, 0);
    else {
      round.floor++; round.revision++;
      round.multiplier = TOWER[round.options.level][round.floor - 1];
      if (round.floor === FLOORS) finish(round, round.multiplier);
    }
  }
  return round;
}
function publicState(game, round) {
  if (game === 'abyss') return abyss.publicState(round);
  if (catalog.ids.includes(game)) return catalog.publicState(game, round);
  const out = { phase: round.phase, revision: round.revision, settled: round.settled, bet: round.bet,
    payout: round.payout, multiplier: round.multiplier, result: round.result, history: round.history,
    options: round.options || null };
  if (game === 'tower' && round.options) {
    out.floor = round.floor; out.steps = round.steps;
    out.available = round.floor ? moneyAt(round.bet, TOWER[round.options.level][round.floor - 1]) : 0;
    // Future floors stay secret even on a loss; only completed floors may be shown.
    out.revealed = round.traps.slice(0, round.steps.length);
  }
  if (round.phase === 'done') for (const key of ['unitBet', 'balls', 'path', 'slot', 'drawn', 'hits', 'cards', 'winner']) if (round[key] !== undefined) out[key] = round[key];
  return out;
}
function actGame(game, previous, action, index, revision, rng) {
  if (game === 'abyss') return abyss.act(previous, action, index, revision, rng);
  if (game === 'tower') return actTower(previous, action, index, revision);
  return catalog.act(game, previous, action, index, revision, rng);
}
module.exports = { AbyssError: abyss.AbyssError, CatalogError: catalog.CatalogError, actGame, ArcadeError, GAMES, PLINKO, KENO, TOWER, LEVELS, ROWS, FLOORS, config, initial, start, actTower, publicState, choose, moneyAt };
