'use strict';

const { freshDeck, shuffle, rankOf, RANK_CHARS } = require('../poker/cards');

// Одна раздача блекджека на двоих: один игрок ставит, второй держит банк.
// Дилер здесь живой человек, поэтому «добирать до 17» его никто не заставляет —
// он решает сам. Фишки переходят между двумя игроками, ниоткуда не берутся.

const BLACKJACK = 21;

// Достоинство карты: картинки по 10, туз пока считаем за 11.
function cardValue(card) {
  const rank = rankOf(card); // 0 => двойка, 12 => туз
  if (rank === 12) return 11;
  return Math.min(rank + 2, 10);
}

// Сумма руки с учётом тузов: возвращает лучшую неперебранную, если она есть.
function handValue(cards) {
  let total = 0;
  let aces = 0;
  for (const card of cards) {
    const value = cardValue(card);
    total += value;
    if (value === 11) aces += 1;
  }
  // Каждый лишний туз опускаем с 11 до 1, пока не уйдём от перебора.
  let soft = aces > 0;
  while (total > BLACKJACK && aces > 0) {
    total -= 10;
    aces -= 1;
    soft = aces > 0;
  }
  return { total, soft, busted: total > BLACKJACK };
}

function isBlackjack(cards) {
  return cards.length === 2 && handValue(cards).total === BLACKJACK;
}

class BlackjackError extends Error {}

class BlackjackRound {
  // playerId ставит, dealerId держит банк.
  constructor({ playerId, dealerId, bet, playerStack, dealerStack, rng = Math.random, deck = null }) {
    if (playerId === dealerId) throw new BlackjackError('Игрок и дилер — один и тот же человек');

    const maxBet = Math.min(playerStack, dealerStack);
    const amount = Math.floor(Number(bet));
    if (!Number.isFinite(amount) || amount <= 0) throw new BlackjackError('Ставка должна быть больше нуля');
    if (amount > maxBet) throw new BlackjackError(`Такую ставку не потянуть: максимум ${maxBet}`);

    this.playerId = playerId;
    this.dealerId = dealerId;
    this.bet = amount;
    this.playerStack = playerStack;
    this.dealerStack = dealerStack;
    this.doubled = false;

    this.deck = deck ? deck.slice() : shuffle(freshDeck(), rng);
    this.deckPos = 0;
    // Карты идут по кругу, как за живым столом: игроку, дилеру, игроку, дилеру.
    this.playerCards = [];
    this.dealerCards = [];
    this.playerCards.push(this._draw());
    this.dealerCards.push(this._draw());
    this.playerCards.push(this._draw());
    this.dealerCards.push(this._draw());

    this.phase = 'player'; // player -> dealer -> complete
    this.complete = false;
    this.result = null;
    this.events = [];

    this._log({ type: 'deal' });
    this._checkNaturals();
  }

  // ——— Чтение ———

  get actingId() {
    if (this.complete) return null;
    return this.phase === 'player' ? this.playerId : this.dealerId;
  }

  get playerValue() {
    return handValue(this.playerCards);
  }

  get dealerValue() {
    return handValue(this.dealerCards);
  }

  // Пока ходит игрок, вторая карта дилера закрыта.
  visibleDealerCards() {
    if (this.phase === 'player') return [this.dealerCards[0]];
    return this.dealerCards.slice();
  }

  legalActions(id) {
    if (this.complete || id !== this.actingId) return null;
    if (this.phase === 'player') {
      const value = this.playerValue;
      const canDouble = this.playerCards.length === 2
        && !this.doubled
        && this.playerStack >= this.bet * 2
        && this.dealerStack >= this.bet * 2;
      return { canHit: !value.busted && value.total < BLACKJACK, canStand: true, canDouble };
    }
    const value = this.dealerValue;
    return { canHit: !value.busted && value.total < BLACKJACK, canStand: true, canDouble: false };
  }

  // ——— Ходы ———

  act(id, action) {
    const legal = this.legalActions(id);
    if (!legal) throw new BlackjackError('Сейчас не ваш ход');

    switch (action) {
      case 'hit': {
        if (!legal.canHit) throw new BlackjackError('Брать больше нельзя');
        const cards = this.phase === 'player' ? this.playerCards : this.dealerCards;
        cards.push(this._draw());
        this._log({ type: 'hit', playerId: id, card: cards[cards.length - 1] });
        this._afterCard();
        break;
      }
      case 'stand': {
        this._log({ type: 'stand', playerId: id });
        this._advance();
        break;
      }
      case 'double': {
        if (!legal.canDouble) throw new BlackjackError('Удвоить сейчас нельзя');
        this.bet *= 2;
        this.doubled = true;
        this.playerCards.push(this._draw());
        this._log({ type: 'double', playerId: id, card: this.playerCards[this.playerCards.length - 1], bet: this.bet });
        // После удвоения берётся ровно одна карта, дальше ход переходит дилеру.
        if (this.playerValue.busted) this._finish('dealer', 'перебор у игрока');
        else this._advance();
        break;
      }
      default:
        throw new BlackjackError(`Неизвестное действие: ${action}`);
    }
    return this.events;
  }

  // Не успел походить — остаёмся при своих.
  timeout(id) {
    if (this.legalActions(id)) this.act(id, 'stand');
  }

  // ——— Внутреннее ———

  _draw() {
    return this.deck[this.deckPos++];
  }

  _checkNaturals() {
    const playerNatural = isBlackjack(this.playerCards);
    const dealerNatural = isBlackjack(this.dealerCards);
    if (!playerNatural && !dealerNatural) return;

    this.phase = 'dealer'; // карты дилера открываются
    if (playerNatural && dealerNatural) this._finish('push', 'блекджек у обоих');
    else if (playerNatural) this._finish('player', 'блекджек', { natural: true });
    else this._finish('dealer', 'блекджек у дилера');
  }

  _afterCard() {
    const value = this.phase === 'player' ? this.playerValue : this.dealerValue;
    if (value.busted) {
      if (this.phase === 'player') this._finish('dealer', 'перебор у игрока');
      else this._finish('player', 'перебор у дилера');
      return;
    }
    // На 21 добирать нечего — ход переходит сам.
    if (value.total === BLACKJACK) this._advance();
  }

  _advance() {
    if (this.phase === 'player') {
      this.phase = 'dealer';
      this._log({ type: 'reveal', cards: this.dealerCards.slice() });
      // Если дилеру уже нечем ходить, сразу считаем.
      const value = this.dealerValue;
      if (value.busted) this._finish('player', 'перебор у дилера');
      else if (value.total === BLACKJACK) this._compare();
      return;
    }
    this._compare();
  }

  _compare() {
    const player = this.playerValue.total;
    const dealer = this.dealerValue.total;
    if (player > dealer) this._finish('player', `${player} против ${dealer}`);
    else if (dealer > player) this._finish('dealer', `${dealer} против ${player}`);
    else this._finish('push', `поровну, ${player}`);
  }

  _finish(winner, reason, { natural = false } = {}) {
    // Натуральный блекджек платит полторы ставки.
    let delta = 0;
    if (winner === 'player') delta = natural ? Math.floor(this.bet * 1.5) : this.bet;
    else if (winner === 'dealer') delta = -this.bet;

    // Дилер не может заплатить больше, чем у него есть.
    delta = Math.max(-this.dealerStack, Math.min(delta, this.dealerStack));

    this.playerStack += delta;
    this.dealerStack -= delta;
    this.phase = 'complete';
    this.complete = true;
    this.result = {
      winner,
      reason,
      natural,
      bet: this.bet,
      delta,
      playerCards: this.playerCards.slice(),
      dealerCards: this.dealerCards.slice(),
      playerTotal: this.playerValue.total,
      dealerTotal: this.dealerValue.total,
      playerStack: this.playerStack,
      dealerStack: this.dealerStack,
    };
    this._log({ type: 'result', result: this.result });
  }

  _log(event) {
    this.events.push(event);
  }
}

module.exports = { BlackjackRound, BlackjackError, handValue, isBlackjack, cardValue, BLACKJACK, RANK_CHARS };
