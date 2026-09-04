'use strict';

// Карта кодируется числом 0..51: card = rank * 4 + suit
// rank: 0 => двойка, 12 => туз;  suit: 0 => ♣, 1 => ♦, 2 => ♥, 3 => ♠

const RANK_CHARS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'];
const SUIT_CHARS = ['c', 'd', 'h', 's'];

function rankOf(card) {
  return card >> 2;
}

function suitOf(card) {
  return card & 3;
}

function cardToString(card) {
  return RANK_CHARS[rankOf(card)] + SUIT_CHARS[suitOf(card)];
}

function stringToCard(str) {
  const rank = RANK_CHARS.indexOf(str[0].toUpperCase());
  const suit = SUIT_CHARS.indexOf(str[1].toLowerCase());
  if (rank < 0 || suit < 0) throw new Error(`Неизвестная карта: ${str}`);
  return rank * 4 + suit;
}

function freshDeck() {
  const deck = new Array(52);
  for (let i = 0; i < 52; i++) deck[i] = i;
  return deck;
}

// Тасование Фишера–Йетса. rng() должен возвращать число в [0, 1).
function shuffle(deck, rng) {
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = deck[i];
    deck[i] = deck[j];
    deck[j] = tmp;
  }
  return deck;
}

module.exports = {
  RANK_CHARS,
  SUIT_CHARS,
  rankOf,
  suitOf,
  cardToString,
  stringToCard,
  freshDeck,
  shuffle,
};
