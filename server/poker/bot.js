'use strict';

// A range-aware, Monte Carlo training opponent, not a solved/GTO strategy.
// The worker receives this allowlisted observation, never a Hand or its deck.
const { bestHand, bestOmahaHand, compareScores } = require('./evaluator');
const { rankOf, suitOf, freshDeck } = require('./cards');

function observe(hand, id, history = []) {
  const hero = hand.player(id);
  if (!hero || !hand.legalActions(id)) return null;
  return {
    id, hole: [...hero.hole], board: [...hand.board], variant: hand.variant,
    phase: hand.phase, dealerIndex: hand.dealerIndex, bigBlind: hand.bigBlind,
    currentBet: hand.currentBet, pot: hand.totalPot,
    legal: { ...hand.legalActions(id) },
    players: hand.players.map(p => ({ id: p.id, index: p.index, stack: p.stack,
      committed: p.committed, total: p.total, folded: p.folded, allIn: p.allIn })),
    history: history.map(e => ({ id: e.id, phase: e.phase, action: e.action, amount: e.amount })),
  };
}

// Smooth preflop ordering used for opening ranges and opponent sampling.
function startingStrength(hole) {
  if (hole.length === 2) {
    const ranks = hole.map(c => rankOf(c) + 2).sort((a, b) => b - a);
    const [hi, lo] = ranks, gap = hi - lo;
    if (hi === lo) return Math.min(.99, .47 + hi * .037);
    return Math.max(.05, Math.min(.96, .06 + hi * .032 + lo * .016
      + (suitOf(hole[0]) === suitOf(hole[1]) ? .085 : 0)
      + (gap === 1 ? .065 : gap === 2 ? .025 : -.018 * Math.min(gap - 2, 5))
      + (hi === 14 ? .055 : 0)));
  }
  const ranks = hole.map(c => rankOf(c) + 2).sort((a, b) => b - a);
  const suits = [0, 0, 0, 0]; hole.forEach(c => suits[suitOf(c)]++);
  const unique = new Set(ranks);
  const aces = ranks.filter(r => r === 14).length;
  const suitedAce = hole.some(c => rankOf(c) === 12 && suits[suitOf(c)] === 2);
  const connections = ranks.slice(1).reduce((n, r, i) => n + (ranks[i] - r === 1 ? 1 : 0), 0);
  return Math.max(.05, Math.min(.99, .13 + ranks.reduce((n, r) => n + r, 0) / 100
    + (aces === 2 ? .18 : 0) + (suitedAce ? .09 : 0)
    + (suits.filter(n => n === 2).length === 2 ? .09 : 0) + connections * .05
    - (unique.size < 3 ? .13 : 0) - (Math.max(...suits) > 2 ? .07 : 0)));
}

function handScore(hole, board, variant) {
  return (variant === 'omaha' ? bestOmahaHand(hole, board) : bestHand([...hole, ...board])).score;
}

function equity(observation, { rng = Math.random, iterations = 650, budgetMs = 500 } = {}) {
  const { hole, board, variant, history, id } = observation;
  const opponents = observation.players.filter(p => p.id !== id && !p.folded);
  if (!opponents.length) return 1;
  const known = new Set([...hole, ...board]);
  const unseen = freshDeck().filter(c => !known.has(c));
  const count = variant === 'omaha' ? 4 : 2;
  const thresholds = opponents.map(p => {
    const pre = history.filter(e => e.id === p.id && e.phase === 'preflop');
    const raises = pre.filter(e => e.action === 'raise' || e.action === 'bet').length;
    return raises > 1 ? .77 : raises ? .60 : pre.some(e => e.action === 'call') ? .43 : .20;
  });
  const start = Date.now();
  let wins = 0, trials = 0;
  // Bounded, sequential sampling without replacement. Folded cards are unknown,
  // so they remain in the unseen pool (correct marginal distribution).
  while (trials < iterations && (trials < 24 || Date.now() - start < budgetMs)) {
    const pool = unseen.slice();
    const draw = n => {
      const cards = [];
      for (let i = 0; i < n; i++) cards.push(pool.splice(Math.floor(rng() * pool.length), 1)[0]);
      return cards;
    };
    const hands = opponents.map((p, i) => {
      let candidate;
      for (let attempt = 0; attempt < 8; attempt++) {
        candidate = draw(count);
        const strength = startingStrength(candidate);
        if (attempt === 7 || rng() < (strength >= thresholds[i] ? 1 : .12)) break;
        pool.push(...candidate);
      }
      return candidate;
    });
    const runout = [...board, ...draw(5 - board.length)];
    const mine = handScore(hole, runout, variant);
    let tied = 1, lost = false;
    for (const other of hands) {
      const comparison = compareScores(mine, handScore(other, runout, variant));
      if (comparison < 0) { lost = true; break; }
      if (comparison === 0) tied++;
    }
    if (!lost) wins += 1 / tied;
    trials++;
  }
  return wins / trials;
}

function chooseAction(o, options = {}) {
  const rng = options.rng || Math.random;
  const legal = o.legal;
  const hero = o.players.find(p => p.id === o.id);
  const opponents = o.players.filter(p => p.id !== o.id && !p.folded);
  const n = opponents.length;
  const order = o.players.filter(p => !p.folded && !p.allIn)
    .sort((a, b) => ((a.index - o.dealerIndex - 1 + o.players.length) % o.players.length)
      - ((b.index - o.dealerIndex - 1 + o.players.length) % o.players.length));
  const inPosition = order.at(-1)?.id === o.id;
  const late = ((o.dealerIndex - hero.index + o.players.length) % o.players.length) <= 1;
  const pre = o.phase === 'preflop';
  const strength = startingStrength(o.hole);
  const bb = o.bigBlind;
  const canOpen = o.currentBet <= bb;
  const fallback = () => ({ action: legal.canCheck ? 'check' : 'fold' });
  const raise = amount => ({ action: 'raise', amount: Math.max(legal.minRaiseTo, Math.min(legal.maxRaiseTo, Math.round(amount))) });

  // Discard weak, dominated starting hands before doing expensive simulations.
  const openThreshold = n <= 1 ? .36 : late ? .46 : n >= 5 ? .62 : .54;
  if (pre && !legal.canCheck && strength < (canOpen ? openThreshold : .57)) return fallback();
  const eq = equity(o, options);
  const cap = hero.total + legal.callAmount;
  const contestablePot = o.players.reduce((sum, p) => sum + Math.min(p.total, cap), 0);
  const odds = legal.callAmount / Math.max(1, contestablePot + legal.callAmount);
  const realization = pre ? (inPosition || late ? .96 : .85) : inPosition ? .99 : .94;
  const effectiveEq = eq * realization;
  const equityEdge = effectiveEq - odds;
  const effectiveStack = Math.min(hero.stack, Math.max(...opponents.map(p => p.stack + p.committed - hero.committed), 0));
  const pot = Math.max(bb, o.pot);

  if (pre) {
    if (legal.canRaise && canOpen && strength >= openThreshold && (eq > 1 / (n + 1) + .06 || strength > .83)) {
      const limpers = o.history.filter(e => e.phase === 'preflop' && e.action === 'call').length;
      return raise(bb * (2.5 + Math.min(limpers, 4)));
    }
    // Premium value 3-bets, with occasional suited ace blocker semi-bluffs.
    const premium = strength >= .87 && equityEdge > .15;
    const blocker = o.variant === 'holdem' && o.hole.some(c => rankOf(c) === 12)
      && suitOf(o.hole[0]) === suitOf(o.hole[1]) && late && n <= 2 && rng() < .08;
    if (legal.canRaise && !canOpen && (premium || blocker)) {
      if (effectiveStack < pot * 1.5 && eq > .65) return raise(legal.maxRaiseTo);
      return raise(o.currentBet * (inPosition ? 3 : 3.5));
    }
  } else {
    const score = handScore(o.hole, o.board, o.variant);
    const made = score[0];
    const value = eq > (n === 1 ? .67 : .73) && (made >= 1 || eq > .88);
    // Bluff only occasionally into small fields; never random pot-sized calls.
    const nutBlocker = o.hole.some(c => rankOf(c) === 12 && o.board.filter(b => suitOf(b) === suitOf(c)).length >= 2);
    const semiBluff = o.board.length < 5 && eq > .28 && eq < .57;
    const bluff = n <= 2 && inPosition && (semiBluff || nutBlocker) && rng() < (n === 1 ? .14 : .05);
    if (legal.canRaise && (value || (legal.canCheck && bluff))) {
      const fraction = eq > .88 ? .75 : n > 1 ? .66 : .50;
      const amount = hero.committed + legal.callAmount + (pot + legal.callAmount) * fraction;
      if (value && eq > .82 && effectiveStack < pot * 1.4) return raise(legal.maxRaiseTo);
      return raise(amount);
    }
  }
  if (legal.canCheck) return { action: 'check' };
  if (legal.canCall && equityEdge >= (pre ? .035 : .02)) return { action: 'call' };
  return fallback();
}

module.exports = { observe, startingStrength, equity, chooseAction };
