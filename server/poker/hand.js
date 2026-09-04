'use strict';

const { freshDeck, shuffle } = require('./cards');
const { bestHand, compareScores } = require('./evaluator');

const PHASES = ['preflop', 'flop', 'turn', 'river', 'showdown'];

// Одна раздача безлимитного техасского холдема.
// Класс не знает ничего про сеть и таймеры — только чистая логика,
// чтобы её было легко покрыть тестами.
class Hand {
  // players: [{ id, stack }] в порядке посадки, только участники раздачи.
  // dealerIndex — индекс баттона внутри этого массива.
  // deck передаётся только в тестах, чтобы разложить конкретную раздачу.
  constructor({ players, dealerIndex, smallBlind, bigBlind, rng = Math.random, deck = null }) {
    if (players.length < 2) throw new Error('Для раздачи нужно минимум два игрока');

    this.smallBlind = smallBlind;
    this.bigBlind = bigBlind;
    this.dealerIndex = dealerIndex % players.length;
    this.players = players.map((p, index) => ({
      id: p.id,
      index,
      stack: p.stack,
      startingStack: p.stack,
      hole: [],
      committed: 0, // поставлено на текущей улице
      total: 0, // поставлено за всю раздачу
      folded: false,
      allIn: false,
      acted: false,
      canRaise: true,
      lastAction: null,
    }));

    this.deck = deck ? deck.slice() : shuffle(freshDeck(), rng);
    this.deckPos = 0;
    this.board = [];
    this.phase = 'preflop';
    this.currentBet = 0;
    this.lastRaiseSize = bigBlind;
    this.actingIndex = null;
    this.complete = false;
    this.result = null;
    this.events = [];
    this.handNumber = 0;

    this._deal();
    this._postBlinds();
    this._openBetting(this._firstToActPreflop());
  }

  // ——— Публичное чтение ———

  get activePlayers() {
    return this.players.filter((p) => !p.folded);
  }

  get actingPlayer() {
    return this.actingIndex === null ? null : this.players[this.actingIndex];
  }

  player(id) {
    return this.players.find((p) => p.id === id) || null;
  }

  // Что именно доступно игроку прямо сейчас.
  legalActions(playerId) {
    const p = this.player(playerId);
    if (!p || this.complete || this.actingPlayer !== p) return null;

    const toCall = Math.min(this.currentBet - p.committed, p.stack);
    const canCheck = this.currentBet === p.committed;
    const minRaiseTo = this.currentBet + this.lastRaiseSize;
    const maxRaiseTo = p.committed + p.stack;
    // Рейз возможен, если фишек хватает хотя бы на олл-ин выше текущей ставки.
    const canRaise = p.canRaise && maxRaiseTo > this.currentBet && this._playersWhoCanStillAct() > 1;

    return {
      canFold: true,
      canCheck,
      canCall: !canCheck && toCall > 0,
      callAmount: toCall,
      canRaise,
      minRaiseTo: Math.min(minRaiseTo, maxRaiseTo),
      maxRaiseTo,
      isAllInRaise: minRaiseTo >= maxRaiseTo,
    };
  }

  // Текущий банк со всеми ставками улицы.
  get totalPot() {
    return this.players.reduce((sum, p) => sum + p.total, 0);
  }

  // ——— Действия ———

  // type: 'fold' | 'check' | 'call' | 'raise' | 'allin'
  // amount для 'raise' — это ставка «до» (raise to), а не добавка.
  act(playerId, type, amount) {
    const legal = this.legalActions(playerId);
    if (!legal) throw new ActionError('Сейчас не ваш ход');
    const p = this.player(playerId);

    switch (type) {
      case 'fold': {
        p.folded = true;
        p.acted = true;
        p.lastAction = 'fold';
        this._log({ type: 'action', playerId, action: 'fold' });
        break;
      }
      case 'check': {
        if (!legal.canCheck) throw new ActionError('Чек невозможен, нужно уравнять ставку');
        p.acted = true;
        p.lastAction = 'check';
        this._log({ type: 'action', playerId, action: 'check' });
        break;
      }
      case 'call': {
        if (legal.canCheck) throw new ActionError('Уравнивать нечего — можно чекнуть');
        this._put(p, legal.callAmount);
        p.acted = true;
        p.lastAction = 'call';
        this._log({ type: 'action', playerId, action: 'call', amount: legal.callAmount });
        break;
      }
      case 'allin':
      case 'raise': {
        let raiseTo = type === 'allin' ? legal.maxRaiseTo : Math.floor(Number(amount));
        if (type === 'allin' && !legal.canRaise) {
          // Фишек не хватает даже на минимальный рейз — это просто колл олл-ин.
          this._put(p, Math.min(p.stack, legal.callAmount));
          p.acted = true;
          p.lastAction = 'call';
          this._log({ type: 'action', playerId, action: 'call', amount: p.total, allIn: true });
          break;
        }
        if (!legal.canRaise) throw new ActionError('Рейз сейчас недоступен');
        if (!Number.isFinite(raiseTo)) throw new ActionError('Некорректный размер ставки');
        if (raiseTo > legal.maxRaiseTo) throw new ActionError('Столько фишек нет в стеке');
        if (raiseTo < legal.minRaiseTo && raiseTo < legal.maxRaiseTo) {
          throw new ActionError(`Минимальный рейз — до ${legal.minRaiseTo}`);
        }

        const previousBet = this.currentBet;
        const increase = raiseTo - previousBet;
        this._put(p, raiseTo - p.committed);
        p.acted = true;
        p.lastAction = previousBet === 0 ? 'bet' : 'raise';
        this.currentBet = raiseTo;

        if (increase >= this.lastRaiseSize) {
          // Полноценный рейз: круг открывается заново для всех.
          this.lastRaiseSize = increase;
          for (const other of this.players) {
            if (other !== p && !other.folded && !other.allIn) other.canRaise = true;
          }
        } else {
          // Короткий олл-ин: те, кто уже уравнял, могут только коллировать или пасовать.
          for (const other of this.players) {
            if (other !== p && other.acted && other.committed >= previousBet) other.canRaise = false;
          }
        }
        this._log({ type: 'action', playerId, action: p.lastAction, amount: raiseTo, allIn: p.allIn });
        break;
      }
      default:
        throw new ActionError(`Неизвестное действие: ${type}`);
    }

    this._afterAction();
    return this.events;
  }

  // Игрок не успел походить: фолд, либо чек, если он бесплатный.
  timeout(playerId) {
    const legal = this.legalActions(playerId);
    if (!legal) return;
    this.act(playerId, legal.canCheck ? 'check' : 'fold');
  }

  // ——— Внутренняя кухня ———

  _draw() {
    return this.deck[this.deckPos++];
  }

  _deal() {
    // Раздаём по одной карте по кругу, как за живым столом.
    for (let round = 0; round < 2; round++) {
      for (let i = 1; i <= this.players.length; i++) {
        const p = this.players[(this.dealerIndex + i) % this.players.length];
        p.hole.push(this._draw());
      }
    }
  }

  _postBlinds() {
    const heads = this.players.length === 2;
    const sbIndex = heads ? this.dealerIndex : this._nextIndex(this.dealerIndex);
    const bbIndex = this._nextIndex(sbIndex);

    const sb = this.players[sbIndex];
    const bb = this.players[bbIndex];
    this._put(sb, Math.min(this.smallBlind, sb.stack));
    this._log({ type: 'blind', playerId: sb.id, amount: sb.committed, blind: 'small' });
    this._put(bb, Math.min(this.bigBlind, bb.stack));
    this._log({ type: 'blind', playerId: bb.id, amount: bb.committed, blind: 'big' });

    this.currentBet = Math.max(sb.committed, bb.committed);
    this.lastRaiseSize = this.bigBlind;
    this.sbIndex = sbIndex;
    this.bbIndex = bbIndex;
  }

  _firstToActPreflop() {
    return this.players.length === 2 ? this.dealerIndex : this._nextIndex(this.bbIndex);
  }

  _firstToActPostflop() {
    return this._nextIndex(this.dealerIndex);
  }

  _nextIndex(from) {
    return (from + 1) % this.players.length;
  }

  _put(p, amount) {
    const chips = Math.max(0, Math.min(amount, p.stack));
    p.stack -= chips;
    p.committed += chips;
    p.total += chips;
    if (p.stack === 0) p.allIn = true;
  }

  _playersWhoCanStillAct() {
    return this.players.filter((p) => !p.folded && !p.allIn).length;
  }

  // Ставит ход на первого игрока, который вообще может действовать.
  _openBetting(startIndex) {
    if (this._playersWhoCanStillAct() === 0) {
      this.actingIndex = null;
      return;
    }
    let index = startIndex;
    for (let i = 0; i < this.players.length; i++) {
      const p = this.players[index];
      if (!p.folded && !p.allIn) {
        this.actingIndex = index;
        return;
      }
      index = this._nextIndex(index);
    }
    this.actingIndex = null;
  }

  _afterAction() {
    if (this.activePlayers.length === 1) {
      this._finishWithoutShowdown();
      return;
    }
    if (this._bettingRoundComplete()) {
      this._advancePhase();
      return;
    }
    // Передаём ход следующему, кто ещё в игре и не в олл-ине.
    let index = this._nextIndex(this.actingIndex);
    for (let i = 0; i < this.players.length; i++) {
      const p = this.players[index];
      if (!p.folded && !p.allIn) {
        this.actingIndex = index;
        return;
      }
      index = this._nextIndex(index);
    }
    this.actingIndex = null;
  }

  _bettingRoundComplete() {
    const contenders = this.players.filter((p) => !p.folded && !p.allIn);
    if (contenders.length === 0) return true;
    if (contenders.length === 1) {
      // Одному игроку не с кем торговаться, если он уже уравнял всё.
      const solo = contenders[0];
      const maxCommitted = Math.max(...this.players.filter((p) => !p.folded).map((p) => p.committed));
      return solo.acted && solo.committed >= maxCommitted;
    }
    return contenders.every((p) => p.acted && p.committed === this.currentBet);
  }

  _collectBets() {
    for (const p of this.players) p.committed = 0;
    this.currentBet = 0;
    this.lastRaiseSize = this.bigBlind;
    for (const p of this.players) {
      p.acted = false;
      p.canRaise = true;
      if (p.lastAction !== 'fold') p.lastAction = null;
    }
  }

  _advancePhase() {
    this._collectBets();

    const phaseIndex = PHASES.indexOf(this.phase);
    const next = PHASES[phaseIndex + 1];

    if (next === 'showdown') {
      this._showdown();
      return;
    }

    this._draw(); // сжигаем карту, как в живой игре
    const count = next === 'flop' ? 3 : 1;
    for (let i = 0; i < count; i++) this.board.push(this._draw());
    this.phase = next;
    this._log({ type: 'street', street: next, board: this.board.slice() });

    if (this._playersWhoCanStillAct() <= 1) {
      // Все в олл-ине — просто докручиваем борд до ривера.
      this.actingIndex = null;
      this._advancePhase();
      return;
    }
    this._openBetting(this._firstToActPostflop());
  }

  // Раздача закончилась пасами всех, кроме одного.
  _finishWithoutShowdown() {
    const winner = this.activePlayers[0];
    const refunded = this._refundUncalled();
    const pot = this.totalPot;
    winner.stack += pot;
    this.actingIndex = null;
    this.complete = true;
    this.phase = 'complete';
    this.result = {
      showdown: false,
      board: this.board.slice(),
      pots: [{ amount: pot, winners: [winner.id] }],
      refunded,
      winners: [{ id: winner.id, amount: pot, hand: null }],
      players: this._playerResults(),
    };
    this._log({ type: 'win', playerId: winner.id, amount: pot, showdown: false });
  }

  // Возвращает переставленные фишки, которые никто не смог уравнять.
  _refundUncalled() {
    const totals = this.players.map((p) => p.total).sort((a, b) => b - a);
    const max = totals[0];
    const second = totals[1] || 0;
    if (max <= second) return null;
    const p = this.players.find((x) => x.total === max);
    const back = max - second;
    p.total -= back;
    p.stack += back;
    if (p.stack > 0) p.allIn = false;
    this._log({ type: 'refund', playerId: p.id, amount: back });
    return { playerId: p.id, amount: back };
  }

  _showdown() {
    this._refundUncalled();
    this.phase = 'showdown';

    const evaluated = new Map();
    for (const p of this.activePlayers) {
      evaluated.set(p.id, bestHand([...p.hole, ...this.board]));
    }

    const pots = this._buildPots();
    const payouts = new Map();
    const refunds = new Map();

    for (const pot of pots) {
      const contenders = pot.eligible.filter((id) => evaluated.has(id));
      if (contenders.length === 0) {
        // За этот пот бороться некому: все его вкладчики спасовали, а остальные
        // игроки не доставали до этого уровня ставок. Живьём так не бывает
        // (последний оставшийся просто забирает банк), но фишки должны
        // вернуться тем, кто их поставил, — как невостребованная ставка.
        this._share(pot.amount, pot.contributors, refunds);
        pot.winners = [];
        pot.refunded = true;
        continue;
      }
      let best = null;
      let winners = [];
      for (const id of contenders) {
        const score = evaluated.get(id).score;
        const cmp = best === null ? 1 : compareScores(score, best);
        if (cmp > 0) {
          best = score;
          winners = [id];
        } else if (cmp === 0) {
          winners.push(id);
        }
      }
      this._share(pot.amount, winners, payouts);
      pot.winners = winners;
    }

    for (const [id, amount] of payouts) this.player(id).stack += amount;
    for (const [id, amount] of refunds) {
      this.player(id).stack += amount;
      this._log({ type: 'refund', playerId: id, amount });
    }

    this.actingIndex = null;
    this.complete = true;
    this.result = {
      showdown: true,
      board: this.board.slice(),
      pots: pots.map((p) => ({ amount: p.amount, winners: p.winners || [], refunded: Boolean(p.refunded) })),
      refunds: [...refunds.entries()].map(([id, amount]) => ({ id, amount })),
      winners: [...payouts.entries()].map(([id, amount]) => ({
        id,
        amount,
        hand: evaluated.get(id) ? { name: evaluated.get(id).name, cards: evaluated.get(id).cards } : null,
      })),
      hands: this.activePlayers.map((p) => ({
        id: p.id,
        hole: p.hole.slice(),
        name: evaluated.get(p.id).name,
        cards: evaluated.get(p.id).cards,
      })),
      players: this._playerResults(),
    };
    this.phase = 'complete';
    this._log({ type: 'showdown', result: this.result });
  }

  // Делит сумму между игроками; нечётные фишки уходят ближайшему
  // к баттону слева — как по правилам живой игры.
  _share(amount, ids, into) {
    const share = Math.floor(amount / ids.length);
    let remainder = amount - share * ids.length;
    for (const id of this._orderFromDealer(ids)) {
      let value = share;
      if (remainder > 0) {
        value += 1;
        remainder -= 1;
      }
      into.set(id, (into.get(id) || 0) + value);
    }
  }

  // Основной банк и сайд-поты по уровням вложений.
  _buildPots() {
    const levels = [...new Set(this.players.map((p) => p.total).filter((t) => t > 0))].sort((a, b) => a - b);
    const pots = [];
    let previous = 0;
    for (const level of levels) {
      const contributors = this.players.filter((p) => p.total >= level);
      const amount = (level - previous) * contributors.length;
      const eligible = contributors.filter((p) => !p.folded).map((p) => p.id);
      if (amount > 0) {
        const last = pots[pots.length - 1];
        const ids = contributors.map((p) => p.id);
        // Схлопываем соседние поты с одинаковым составом претендентов.
        // Поты без претендентов не сливаем: для них важен состав вкладчиков.
        if (last && eligible.length > 0 && sameMembers(last.eligible, eligible)) {
          last.amount += amount;
          last.contributors = [...new Set([...last.contributors, ...ids])];
        } else {
          pots.push({ amount, eligible, contributors: ids });
        }
      }
      previous = level;
    }
    return pots;
  }

  _orderFromDealer(ids) {
    const order = [];
    for (let i = 1; i <= this.players.length; i++) {
      const p = this.players[(this.dealerIndex + i) % this.players.length];
      if (ids.includes(p.id)) order.push(p.id);
    }
    return order;
  }

  _playerResults() {
    return this.players.map((p) => ({
      id: p.id,
      stack: p.stack,
      delta: p.stack - p.startingStack,
      folded: p.folded,
      hole: p.hole.slice(),
    }));
  }

  _log(event) {
    this.events.push(event);
  }
}

function sameMembers(a, b) {
  return a.length === b.length && a.every((x) => b.includes(x));
}

class ActionError extends Error {}

module.exports = { Hand, ActionError, PHASES };
