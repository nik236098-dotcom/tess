'use strict';

// Баккара (пунто банко) против заведения. Игрок ставит на PLAYER, BANKER
// или TIE, карты раздаются по фиксированным правилам третьей карты.
// Выплаты по макету: PLAYER 1:1, BANKER 1:1, TIE 8:1; при ничьей ставки
// на PLAYER/BANKER возвращаются.

const { freshDeck, shuffle, cardToString, rankOf } = require('../poker/cards');

class BaccaratError extends Error {}

const ZONES = { player: 1, banker: 1, tie: 8 };

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

// Раздача: возвращает карты обеих сторон, итог и выплату по ставке.
function deal({ zone, amount, deck = null, rng = Math.random }) {
  if (!ZONES[zone]) throw new BaccaratError('Неизвестная ставка');
  const shoe = deck ? deck.slice() : shuffle(freshDeck(), rng);
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
  let payout = 0;
  if (winner === zone) payout = amount * (ZONES[zone] + 1);
  else if (winner === 'tie') payout = amount; // ничья возвращает ставки на стороны
  return {
    player: player.map(cardToString),
    banker: banker.map(cardToString),
    playerTotal: p,
    bankerTotal: b,
    winner,
    natural,
    zone,
    amount,
    payout,
    net: payout - amount,
  };
}

module.exports = { deal, total, cardPoints, bankerDraws, BaccaratError, ZONES };
