'use strict';

const { freshDeck, shuffle, rankOf } = require('../poker/cards');

// Блекджек между двумя игроками, без дилера и без банка.
// Оба ставят поровну, карты у обоих открыты, кто ближе к 21 — тот и забрал.

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

class BlackjackDuel {
  // firstId ходит первым (он же назначал ставку), secondId — вторым.
  constructor({ firstId, secondId, bet, firstStack, secondStack, rng = Math.random, deck = null }) {
    if (firstId === secondId) throw new BlackjackError('Нужны два разных игрока');

    const maxBet = Math.min(firstStack, secondStack);
    const amount = Math.floor(Number(bet));
    if (!Number.isFinite(amount) || amount <= 0) throw new BlackjackError('Ставка должна быть больше нуля');
    if (amount > maxBet) throw new BlackjackError(`Такую ставку не потянуть: максимум ${maxBet}`);

    this.firstId = firstId;
    this.secondId = secondId;
    this.bet = amount;
    this.stacks = { [firstId]: firstStack, [secondId]: secondStack };
    this.cards = { [firstId]: [], [secondId]: [] };

    this.deck = deck ? deck.slice() : shuffle(freshDeck(), rng);
    this.deckPos = 0;
    // Карты идут по кругу, как за живым столом.
    for (let round = 0; round < 2; round++) {
      this.cards[firstId].push(this._draw());
      this.cards[secondId].push(this._draw());
    }

    this.phase = 'first'; // first -> second -> complete
    this.complete = false;
    this.result = null;
    this.events = [];

    this._log({ type: 'deal' });
    // Если раздали сразу 21, добирать нечего — ход переходит сам.
    this._skipIfDone();
  }

  // ——— Чтение ———

  get actingId() {
    if (this.complete) return null;
    return this.phase === 'first' ? this.firstId : this.secondId;
  }

  cardsOf(id) {
    return this.cards[id] ? this.cards[id].slice() : [];
  }

  valueOf(id) {
    return handValue(this.cards[id] || []);
  }

  stackOf(id) {
    return this.stacks[id] || 0;
  }

  opponentOf(id) {
    return id === this.firstId ? this.secondId : this.firstId;
  }

  legalActions(id) {
    if (this.complete || id !== this.actingId) return null;
    const value = this.valueOf(id);
    return {
      canHit: !value.busted && value.total < BLACKJACK,
      canStand: true,
    };
  }

  // ——— Ходы ———

  act(id, action) {
    const legal = this.legalActions(id);
    if (!legal) throw new BlackjackError('Сейчас не ваш ход');

    switch (action) {
      case 'hit': {
        if (!legal.canHit) throw new BlackjackError('Брать больше нельзя');
        this.cards[id].push(this._draw());
        this._log({ type: 'hit', playerId: id, card: this.cards[id][this.cards[id].length - 1] });
        this._afterCard(id);
        break;
      }
      case 'stand': {
        this._log({ type: 'stand', playerId: id });
        this._advance();
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

  _afterCard(id) {
    const value = this.valueOf(id);
    // Перебор заканчивает ход, но не раздачу: соперник ходит вслепую
    // и вполне может перебрать следом. Тогда будет ничья.
    if (value.busted || value.total === BLACKJACK) this._advance();
  }

  _advance() {
    if (this.phase === 'first') {
      this.phase = 'second';
      this._skipIfDone();
      return;
    }
    this._compare();
  }

  // Тому, у кого перебор или ровно 21, решать уже нечего.
  _skipIfDone() {
    const id = this.actingId;
    if (!id) return;
    const value = this.valueOf(id);
    if (value.busted || value.total === BLACKJACK) this._advance();
  }

  _compare() {
    const first = this.valueOf(this.firstId);
    const second = this.valueOf(this.secondId);

    if (first.busted && second.busted) {
      this._finish(null, `перебор у обоих: ${first.total} и ${second.total}`);
      return;
    }
    if (first.busted) {
      this._finish(this.secondId, `перебор у соперника (${first.total})`);
      return;
    }
    if (second.busted) {
      this._finish(this.firstId, `перебор у соперника (${second.total})`);
      return;
    }

    if (first.total > second.total) this._finish(this.firstId, this._reason(first, second));
    else if (second.total > first.total) this._finish(this.secondId, this._reason(second, first));
    else this._finish(null, `поровну, ${first.total}`);
  }

  _reason(winner, loser) {
    const natural = winner.total === BLACKJACK ? 'блекджек! ' : '';
    return `${natural}${winner.total} против ${loser.total}`;
  }

  // winnerId === null означает ничью.
  _finish(winnerId, reason) {
    let amount = 0;
    if (winnerId) {
      // Больше, чем есть у проигравшего, не заберёшь.
      amount = Math.min(this.bet, this.stacks[this.opponentOf(winnerId)]);
      this.stacks[winnerId] += amount;
      this.stacks[this.opponentOf(winnerId)] -= amount;
    }

    this.phase = 'complete';
    this.complete = true;
    this.result = {
      winnerId,
      reason,
      bet: this.bet,
      amount,
      totals: {
        [this.firstId]: this.valueOf(this.firstId).total,
        [this.secondId]: this.valueOf(this.secondId).total,
      },
      cards: {
        [this.firstId]: this.cardsOf(this.firstId),
        [this.secondId]: this.cardsOf(this.secondId),
      },
      stacks: { ...this.stacks },
    };
    this._log({ type: 'result', result: this.result });
  }

  _log(event) {
    this.events.push(event);
  }
}

module.exports = { BlackjackDuel, BlackjackError, handValue, isBlackjack, cardValue, BLACKJACK };
