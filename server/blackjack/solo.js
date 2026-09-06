'use strict';

// Блекджек один на один с дилером. Стола и мест нет: игрок ставит с
// баланса, выигрыш возвращается на баланс. Правила: дилер добирает до 16
// включительно и останавливается на 17 и выше (мягкие 17 тоже),
// блекджек платит 3 к 2, при равенстве ставка возвращается. Есть удвоение
// на первых двух картах и сплит одинаковых по достоинству карт.

const { freshDeck, shuffle, cardToString, rankOf } = require('../poker/cards');
const { handValue, isBlackjack, BLACKJACK } = require('./round');

const DEALER_STANDS_ON = 17;

class SoloError extends Error {}

// Достоинство для сплита: все десятки-картинки равны между собой.
function splitRank(card) {
  return Math.min(rankOf(card), 8);
}

class SoloBlackjack {
  constructor({ minBet = 100, maxBet = 10000, rng = Math.random, deck = null } = {}) {
    this.minBet = minBet;
    this.maxBet = maxBet;
    this.rng = rng;
    this.presetDeck = deck;
    this.phase = 'bet';     // bet | play | done
    this.bet = minBet;      // последняя ставка — предлагаем её же в следующий раз
    this.hands = [];
    this.active = 0;
    this.dealer = [];
    this.revealed = false;
    this.results = null;
    this.deck = [];
  }

  _draw() {
    if (!this.deck.length) this.deck = shuffle(freshDeck(), this.rng);
    return this.deck.pop();
  }

  // Ставка списывается снаружи (bank), сюда приходит уже проверенная сумма.
  start(bet) {
    if (this.phase === 'play') throw new SoloError('Раздача уже идёт');
    const amount = Math.round(Number(bet));
    if (!Number.isFinite(amount) || amount < this.minBet) throw new SoloError(`Минимальная ставка ${this.minBet}`);
    if (amount > this.maxBet) throw new SoloError(`Максимальная ставка ${this.maxBet}`);

    this.deck = this.presetDeck ? this.presetDeck.slice() : shuffle(freshDeck(), this.rng);
    this.bet = amount;
    this.results = null;
    this.revealed = false;
    this.hands = [{ cards: [], bet: amount, done: false, doubled: false, split: false }];
    this.active = 0;
    this.dealer = [];
    // По одной карте по кругу, как за живым столом.
    this.hands[0].cards.push(this._draw());
    this.dealer.push(this._draw());
    this.hands[0].cards.push(this._draw());
    this.dealer.push(this._draw());
    this.phase = 'play';

    // Блекджек с раздачи у игрока или у дилера — раздача заканчивается сразу.
    if (isBlackjack(this.hands[0].cards) || isBlackjack(this.dealer)) {
      this.hands[0].done = true;
      this._finish();
    }
    return this.state();
  }

  get hand() {
    return this.hands[this.active];
  }

  // Что можно сделать с текущей рукой. extra — сколько ещё фишек может дать банк.
  options(available = Infinity) {
    if (this.phase !== 'play') return { hit: false, stand: false, double: false, split: false };
    const hand = this.hand;
    const two = hand.cards.length === 2;
    return {
      hit: true,
      stand: true,
      double: two && available >= hand.bet,
      split: two && this.hands.length === 1 && splitRank(hand.cards[0]) === splitRank(hand.cards[1]) && available >= hand.bet,
    };
  }

  hit() {
    this._assertPlay();
    const hand = this.hand;
    hand.cards.push(this._draw());
    const { total } = handValue(hand.cards);
    if (total >= BLACKJACK) hand.done = true; // перебор или ровно 21 — дальше брать нечего
    this._advance();
    return this.state();
  }

  stand() {
    this._assertPlay();
    this.hand.done = true;
    this._advance();
    return this.state();
  }

  // Удвоение: ставка ×2, одна карта и стоп. Доплату списывает вызывающий.
  double() {
    this._assertPlay();
    const hand = this.hand;
    if (hand.cards.length !== 2) throw new SoloError('Удвоить можно только на первых двух картах');
    hand.bet *= 2;
    hand.doubled = true;
    hand.cards.push(this._draw());
    hand.done = true;
    this._advance();
    return this.state();
  }

  // Сплит: две одинаковые карты разводим в две руки, к каждой добираем по карте.
  split() {
    this._assertPlay();
    const hand = this.hand;
    if (hand.cards.length !== 2 || this.hands.length !== 1) throw new SoloError('Разделить нельзя');
    if (splitRank(hand.cards[0]) !== splitRank(hand.cards[1])) throw new SoloError('Разделить можно только одинаковые карты');
    const second = { cards: [hand.cards.pop()], bet: hand.bet, done: false, doubled: false, split: true };
    hand.split = true;
    hand.cards.push(this._draw());
    second.cards.push(this._draw());
    this.hands.push(second);
    // 21 на двух картах после сплита — не блекджек, но брать уже нечего.
    if (handValue(hand.cards).total === BLACKJACK) hand.done = true;
    if (handValue(second.cards).total === BLACKJACK) second.done = true;
    this._advance();
    return this.state();
  }

  _assertPlay() {
    if (this.phase !== 'play') throw new SoloError('Сейчас нет раздачи');
  }

  // Переходим к следующей незаконченной руке; руки кончились — ходит дилер.
  _advance() {
    const next = this.hands.findIndex((h) => !h.done);
    if (next >= 0) {
      this.active = next;
      return;
    }
    this._finish();
  }

  _finish() {
    this.revealed = true;
    const anyAlive = this.hands.some((h) => handValue(h.cards).total <= BLACKJACK);
    const playerNatural = this.hands.length === 1 && !this.hands[0].split && isBlackjack(this.hands[0].cards);
    // Дилер добирает, только если есть кого обыгрывать и у игрока не блекджек.
    if (anyAlive && !playerNatural && !isBlackjack(this.dealer)) {
      while (handValue(this.dealer).total < DEALER_STANDS_ON) this.dealer.push(this._draw());
    }
    const dealerTotal = handValue(this.dealer).total;
    const dealerNatural = isBlackjack(this.dealer);
    const dealerBust = dealerTotal > BLACKJACK;

    let payout = 0;
    let stake = 0;
    const results = this.hands.map((hand) => {
      const total = handValue(hand.cards).total;
      const natural = this.hands.length === 1 && !hand.split && isBlackjack(hand.cards);
      stake += hand.bet;
      let outcome;
      let win = 0;
      if (total > BLACKJACK) outcome = 'bust';
      else if (natural && !dealerNatural) { outcome = 'blackjack'; win = hand.bet + Math.floor(hand.bet * 3 / 2); }
      else if (dealerNatural && !natural) outcome = 'lose';
      else if (dealerBust || total > dealerTotal) { outcome = 'win'; win = hand.bet * 2; }
      else if (total === dealerTotal) { outcome = 'push'; win = hand.bet; }
      else outcome = 'lose';
      payout += win;
      return { outcome, total, bet: hand.bet, payout: win };
    });
    this.results = { hands: results, payout, stake, net: payout - stake, dealerTotal, dealerBust };
    this.phase = 'done';
  }

  // Готов к новой ставке; прошлые карты убираем.
  reset() {
    if (this.phase === 'play') throw new SoloError('Раздача ещё идёт');
    this.phase = 'bet';
    this.hands = [];
    this.dealer = [];
    this.results = null;
    this.revealed = false;
    return this.state();
  }

  state(available = Infinity) {
    const dealerShown = this.revealed ? this.dealer : this.dealer.slice(0, 1);
    return {
      phase: this.phase,
      bet: this.bet,
      minBet: this.minBet,
      maxBet: this.maxBet,
      dealer: {
        cards: this.dealer.length
          ? this.dealer.map((c, i) => (this.revealed || i === 0 ? cardToString(c) : '??'))
          : [],
        total: this.dealer.length ? handValue(dealerShown).total : null,
        revealed: this.revealed,
      },
      hands: this.hands.map((hand, index) => {
        const value = handValue(hand.cards);
        return {
          cards: hand.cards.map(cardToString),
          total: value.total,
          soft: value.soft,
          busted: value.total > BLACKJACK,
          bet: hand.bet,
          doubled: hand.doubled,
          active: this.phase === 'play' && index === this.active,
          result: this.results ? this.results.hands[index] : null,
        };
      }),
      active: this.active,
      options: this.options(available),
      results: this.results,
    };
  }
}

module.exports = { SoloBlackjack, SoloError, DEALER_STANDS_ON };
