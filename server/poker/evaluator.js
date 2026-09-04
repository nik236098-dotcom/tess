'use strict';

const { rankOf, suitOf, RANK_CHARS } = require('./cards');

const CATEGORY = {
  HIGH_CARD: 0,
  PAIR: 1,
  TWO_PAIR: 2,
  TRIPS: 3,
  STRAIGHT: 4,
  FLUSH: 5,
  FULL_HOUSE: 6,
  QUADS: 7,
  STRAIGHT_FLUSH: 8,
};

const CATEGORY_NAMES = [
  'Старшая карта',
  'Пара',
  'Две пары',
  'Тройка',
  'Стрит',
  'Флеш',
  'Фулл-хаус',
  'Каре',
  'Стрит-флеш',
];

// Оценка ровно пяти карт. Возвращает массив [категория, ...кикеры],
// который сравнивается лексикографически: больше — сильнее.
function evaluate5(cards) {
  const ranks = cards.map(rankOf).sort((a, b) => b - a);
  const suits = cards.map(suitOf);
  const isFlush = suits.every((s) => s === suits[0]);

  const counts = new Map();
  for (const r of ranks) counts.set(r, (counts.get(r) || 0) + 1);
  // Сортируем сначала по количеству, затем по старшинству ранга.
  const groups = [...counts.entries()].sort((a, b) => b[1] - a[1] || b[0] - a[0]);

  const straightHigh = straightHighCard(ranks);

  if (isFlush && straightHigh !== null) return [CATEGORY.STRAIGHT_FLUSH, straightHigh];
  if (groups[0][1] === 4) return [CATEGORY.QUADS, groups[0][0], groups[1][0]];
  if (groups[0][1] === 3 && groups[1][1] === 2) return [CATEGORY.FULL_HOUSE, groups[0][0], groups[1][0]];
  if (isFlush) return [CATEGORY.FLUSH, ...ranks];
  if (straightHigh !== null) return [CATEGORY.STRAIGHT, straightHigh];
  if (groups[0][1] === 3) return [CATEGORY.TRIPS, groups[0][0], groups[1][0], groups[2][0]];
  if (groups[0][1] === 2 && groups[1][1] === 2) {
    return [CATEGORY.TWO_PAIR, groups[0][0], groups[1][0], groups[2][0]];
  }
  if (groups[0][1] === 2) return [CATEGORY.PAIR, groups[0][0], groups[1][0], groups[2][0], groups[3][0]];
  return [CATEGORY.HIGH_CARD, ...ranks];
}

// ranks — по убыванию, ровно 5 штук. Возвращает старшую карту стрита или null.
function straightHighCard(ranks) {
  const uniq = [...new Set(ranks)];
  if (uniq.length !== 5) return null;
  if (uniq[0] - uniq[4] === 4) return uniq[0];
  // Колёсико: A-2-3-4-5, туз играет снизу, старшая карта — пятёрка.
  if (uniq[0] === 12 && uniq[1] === 3 && uniq[2] === 2 && uniq[3] === 1 && uniq[4] === 0) return 3;
  return null;
}

function compareScores(a, b) {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const x = a[i] === undefined ? -1 : a[i];
    const y = b[i] === undefined ? -1 : b[i];
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

const COMBOS_5_OF_7 = buildCombinations(7, 5);

function buildCombinations(n, k) {
  const result = [];
  const current = [];
  (function pick(start) {
    if (current.length === k) {
      result.push(current.slice());
      return;
    }
    for (let i = start; i < n; i++) {
      current.push(i);
      pick(i + 1);
      current.pop();
    }
  })(0);
  return result;
}

// Лучшая пятикарточная комбинация из 5..7 карт.
// Возвращает { score, cards, category, name }.
function bestHand(cards) {
  if (cards.length < 5) throw new Error('Нужно минимум 5 карт для оценки');
  let bestScore = null;
  let bestCards = null;

  if (cards.length === 5) {
    bestScore = evaluate5(cards);
    bestCards = cards.slice();
  } else {
    const combos = cards.length === 7 ? COMBOS_5_OF_7 : buildCombinations(cards.length, 5);
    const hand = new Array(5);
    for (const combo of combos) {
      for (let i = 0; i < 5; i++) hand[i] = cards[combo[i]];
      const score = evaluate5(hand);
      if (bestScore === null || compareScores(score, bestScore) > 0) {
        bestScore = score;
        bestCards = hand.slice();
      }
    }
  }

  return {
    score: bestScore,
    cards: bestCards,
    category: bestScore[0],
    name: describe(bestScore),
  };
}

function describe(score) {
  const [category, ...rest] = score;
  const r = (i) => RANK_CHARS[rest[i]];
  switch (category) {
    case CATEGORY.STRAIGHT_FLUSH:
      return rest[0] === 12 ? 'Флеш-рояль' : `Стрит-флеш до ${r(0)}`;
    case CATEGORY.QUADS:
      return `Каре ${r(0)}`;
    case CATEGORY.FULL_HOUSE:
      return `Фулл-хаус ${r(0)} на ${r(1)}`;
    case CATEGORY.FLUSH:
      return `Флеш до ${r(0)}`;
    case CATEGORY.STRAIGHT:
      return `Стрит до ${r(0)}`;
    case CATEGORY.TRIPS:
      return `Тройка ${r(0)}`;
    case CATEGORY.TWO_PAIR:
      return `Две пары ${r(0)} и ${r(1)}`;
    case CATEGORY.PAIR:
      return `Пара ${r(0)}`;
    default:
      return `Старшая ${r(0)}`;
  }
}

module.exports = { CATEGORY, CATEGORY_NAMES, evaluate5, bestHand, compareScores };
