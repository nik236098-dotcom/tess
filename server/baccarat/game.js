'use strict';

// Баккара (пунто банко) против заведения. Игрок ставит на PLAYER, BANKER
// или TIE, карты раздаются по фиксированным правилам третьей карты.
// Выплаты по макету: PLAYER 1:1, BANKER 0.95:1 (комиссия казино), TIE 8:1;
// при ничьей ставки на PLAYER/BANKER возвращаются. Плюс пары (11:1) и
// Perfect Pair (50:1, те же две карты — совпадают и ранг, и масть).

const { shuffle, cardToString, rankOf } = require('../poker/cards');

class BaccaratError extends Error {}

// Сколько стандартных 52-карточных колод в башмаке. Perfect Pair (две
// совершенно одинаковые карты подряд) физически невозможен из одной
// колоды — нужен многоколодный башмак, как в настоящей баккаре.
const DECKS = 8;

// Выплаты по макету: PLAYER 1:1, BANKER 0.95:1 (5% комиссия), ничья 8:1,
// обычная пара (совпадение только ранга) 11:1, Perfect Pair (совпадение
// ранга и масти) 50:1 — бонусные ставки друг другу не мешают.
const ZONES = {
  player: 1,
  banker: 0.95,
  tie: 8,
  playerPair: 11,
  bankerPair: 11,
  playerPerfectPair: 50,
  bankerPerfectPair: 50,
};

function freshShoe(decks = DECKS) {
  const shoe = [];
  for (let d = 0; d < decks; d += 1) for (let card = 0; card < 52; card += 1) shoe.push(card);
  return shoe;
}

// Достоинство: туз 1, двойка–девятка по номиналу, десятки и картинки 0.
function cardPoints(card) {
  const rank = rankOf(card); // 0 => двойка, 12 => туз
  if (rank === 12) return 1;
  if (rank >= 8) return 0;
  return rank + 2;
}

function total(cards) {
  return cards.reduce((sum, c) => sum + cardPoints(c), 0) % 10;
}

// Нужна ли банкиру третья карта: зависит от его суммы и третьей карты игрока.
function bankerDraws(bankerTotal, playerThird) {
  if (playerThird === null) return bankerTotal <= 5;
  const v = cardPoints(playerThird);
  if (bankerTotal <= 2) return true;
  if (bankerTotal === 3) return v !== 8;
  if (bankerTotal === 4) return v >= 2 && v <= 7;
  if (bankerTotal === 5) return v >= 4 && v <= 7;
  if (bankerTotal === 6) return v === 6 || v === 7;
  return false;
}

function isPair(cards) {
  return cards.length >= 2 && rankOf(cards[0]) === rankOf(cards[1]);
}

// Perfect Pair: первые две карты стороны — буквально одна и та же карта
// (совпадают и ранг, и масть). Возможно только из многоколодного башмака.
function isPerfectPair(cards) {
  return cards.length >= 2 && cards[0] === cards[1];
}

// Ставки списком: { zone, amount }. Одна и та же зона может встречаться
// один раз — клиент складывает фишки сам.
function normalizeBets(raw, { minBet, maxBet, maxTotal }) {
  if (!Array.isArray(raw) || raw.length === 0) throw new BaccaratError('Выберите PLAYER, TIE или BANKER');
  const seen = new Set();
  let total = 0;
  const bets = raw.map((item) => {
    const zone = item && ZONES[item.zone] ? item.zone : null;
    if (!zone) throw new BaccaratError('Неизвестная ставка');
    if (seen.has(zone)) throw new BaccaratError('Ставка на зону повторяется');
    seen.add(zone);
    const amount = Math.round(Number(item.amount));
    if (!Number.isFinite(amount) || amount < minBet) throw new BaccaratError(`Минимальная ставка ${minBet}`);
    if (amount > maxBet) throw new BaccaratError(`Максимальная ставка ${maxBet}`);
    total += amount;
    return { zone, amount };
  });
  if (total > maxTotal) throw new BaccaratError('Недостаточно средств');
  return { bets, total };
}

// Раздача: карты обеих сторон, итог и расчёт каждой ставки.
function deal({ bets, zone, amount, deck = null, rng = Math.random }) {
  const list = bets || [{ zone, amount }];
  for (const b of list) if (!ZONES[b.zone]) throw new BaccaratError('Неизвестная ставка');
  const shoe = deck ? deck.slice() : shuffle(freshShoe(), rng);
  const draw = () => shoe.pop();
  const player = [draw()];
  const banker = [draw()];
  player.push(draw());
  banker.push(draw());

  let playerThird = null;
  const natural = total(player) >= 8 || total(banker) >= 8;
  if (!natural) {
    if (total(player) <= 5) {
      playerThird = draw();
      player.push(playerThird);
    }
    if (bankerDraws(total(banker), playerThird)) banker.push(draw());
  }

  const p = total(player);
  const b = total(banker);
  const winner = p > b ? 'player' : b > p ? 'banker' : 'tie';
  const playerPair = isPair(player);
  const bankerPair = isPair(banker);
  const playerPerfectPair = isPerfectPair(player);
  const bankerPerfectPair = isPerfectPair(banker);
  const wins = {
    player: winner === 'player',
    banker: winner === 'banker',
    tie: winner === 'tie',
    playerPair,
    bankerPair,
    playerPerfectPair,
    bankerPerfectPair,
  };

  let payout = 0;
  let stake = 0;
  const results = list.map((bet) => {
    let win = 0;
    if (wins[bet.zone]) win = Math.round(bet.amount * (ZONES[bet.zone] + 1));
    else if (winner === 'tie' && (bet.zone === 'player' || bet.zone === 'banker')) win = bet.amount; // ничья возвращает ставки на стороны
    payout += win;
    stake += bet.amount;
    return { ...bet, won: Boolean(wins[bet.zone]), payout: win };
  });
  return {
    player: player.map(cardToString),
    banker: banker.map(cardToString),
    playerTotal: p,
    bankerTotal: b,
    winner,
    natural,
    playerPair,
    bankerPair,
    playerPerfectPair,
    bankerPerfectPair,
    bets: results,
    payout,
    stake,
    net: payout - stake,
    // для одной ставки — как раньше
    zone: list.length === 1 ? list[0].zone : null,
    amount: list.length === 1 ? list[0].amount : stake,
  };
}

module.exports = { deal, total, cardPoints, bankerDraws, normalizeBets, isPair, isPerfectPair, freshShoe, BaccaratError, ZONES, DECKS };
