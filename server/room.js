'use strict';

const { EventEmitter } = require('events');
const { Hand, ActionError } = require('./poker/hand');
const { cardToString } = require('./poker/cards');

const SUIT_SYMBOLS = { c: '♣', d: '♦', h: '♥', s: '♠' };

// Для журнала карты приятнее читать со значками мастей: «K♦», а не «Kd».
function prettyCard(card) {
  const text = cardToString(card);
  return text[0] + (SUIT_SYMBOLS[text[1]] || text[1]);
}

const DEFAULT_SETTINGS = {
  smallBlind: 5,
  bigBlind: 10,
  buyIn: 1000,
  maxPlayers: 6,
  turnSeconds: 45,
};

const SETTING_LIMITS = {
  smallBlind: [1, 10000],
  bigBlind: [2, 20000],
  buyIn: [20, 1000000],
  maxPlayers: [2, 9],
  turnSeconds: [10, 180],
};

const SHOWDOWN_PAUSE_MS = 6000;
const FOLD_PAUSE_MS = 2500;
const MAX_LOG = 60;

class Room extends EventEmitter {
  constructor(code, host, settings = {}) {
    super();
    this.code = code;
    this.hostId = host.id;
    this.settings = normalizeSettings(settings);
    this.seats = new Array(this.settings.maxPlayers).fill(null);
    this.members = new Map(); // userId -> { id, name, photoUrl, connected }
    this.status = 'waiting';
    this.hand = null;
    this.dealerSeat = -1;
    this.handNumber = 0;
    this.log = [];
    this.lastResult = null;
    this.createdAt = Date.now();
    this.turnTimer = null;
    this.turnDeadline = null;
    this.nextHandTimer = null;
    this.autoStart = false;

    this.addMember(host);
  }

  // ——— Участники ———

  addMember(user) {
    const existing = this.members.get(user.id);
    if (existing) {
      existing.connected = true;
      existing.name = user.name || existing.name;
      existing.photoUrl = user.photoUrl || existing.photoUrl;
    } else {
      this.members.set(user.id, {
        id: user.id,
        name: user.name,
        photoUrl: user.photoUrl || null,
        connected: true,
      });
      this.pushLog(`${user.name} — за столом`);
    }
    const seat = this.seatOf(user.id);
    if (seat) {
      seat.connected = true;
      // Вернулся в игру — снимаем автоматический «сижу мимо».
      if (seat.autoSitOut) {
        seat.sittingOut = false;
        seat.autoSitOut = false;
      }
    }
    this.touch();
  }

  setDisconnected(userId) {
    const member = this.members.get(userId);
    if (member) member.connected = false;
    const seat = this.seatOf(userId);
    if (seat) {
      seat.connected = false;
      // Пока игрока нет, пропускаем его раздачи, чтобы стол не стоял.
      if (!seat.sittingOut) {
        seat.sittingOut = true;
        seat.autoSitOut = true;
      }
    } else {
      this.members.delete(userId);
    }
    this.touch();
  }

  removeMember(userId) {
    const member = this.members.get(userId);
    this.stand(userId, { silent: true });
    this.members.delete(userId);
    if (member) this.pushLog(`${member.name} покидает стол`);
    if (userId === this.hostId) {
      // Хозяином становится следующий по времени присоединения.
      const next = [...this.members.values()][0];
      if (next) this.hostId = next.id;
    }
    this.touch();
  }

  get isEmpty() {
    return this.members.size === 0;
  }

  seatOf(userId) {
    return this.seats.find((s) => s && s.userId === userId) || null;
  }

  seatIndexOf(userId) {
    return this.seats.findIndex((s) => s && s.userId === userId);
  }

  // ——— Место за столом ———

  sit(userId, seatIndex) {
    const member = this.members.get(userId);
    if (!member) throw new RoomError('Вы не в этой комнате');
    if (this.seatOf(userId)) throw new RoomError('Вы уже за столом');
    if (seatIndex < 0 || seatIndex >= this.seats.length) throw new RoomError('Такого места нет');
    if (this.seats[seatIndex]) throw new RoomError('Место занято');

    this.seats[seatIndex] = {
      userId,
      name: member.name,
      photoUrl: member.photoUrl,
      stack: this.settings.buyIn,
      sittingOut: false,
      autoSitOut: false,
      connected: true,
      joinedHand: this.handNumber,
    };
    this.pushLog(`${member.name} занимает место ${seatIndex + 1}, стек ${this.settings.buyIn}`);
    this.maybeStartHand();
    this.touch();
  }

  stand(userId, { silent = false } = {}) {
    const index = this.seatIndexOf(userId);
    if (index < 0) return;
    const seat = this.seats[index];

    if (this.hand && this.hand.player(userId) && !this.hand.player(userId).folded && !this.hand.complete) {
      // Нельзя просто исчезнуть посреди раздачи — сначала пас.
      try {
        this.applyAction(userId, 'fold');
      } catch {
        /* ход уже перешёл дальше */
      }
    }
    this.seats[index] = null;
    if (!silent) this.pushLog(`${seat.name} освобождает место`);
    this.touch();
  }

  setSittingOut(userId, value) {
    const seat = this.seatOf(userId);
    if (!seat) throw new RoomError('Вы не за столом');
    seat.sittingOut = Boolean(value);
    seat.autoSitOut = false;
    this.pushLog(`${seat.name} ${seat.sittingOut ? 'пропускает раздачи' : 'снова в игре'}`);
    if (!seat.sittingOut) this.maybeStartHand();
    this.touch();
  }

  // Фишки игровые, поэтому обнулившийся стек можно пополнить в любой момент между раздачами.
  rebuy(userId) {
    const seat = this.seatOf(userId);
    if (!seat) throw new RoomError('Вы не за столом');
    if (this.hand && !this.hand.complete && this.hand.player(userId)) {
      throw new RoomError('Пополнить стек можно между раздачами');
    }
    if (seat.stack >= this.settings.buyIn) {
      throw new RoomError('Фишек и так достаточно');
    }
    seat.stack = this.settings.buyIn;
    seat.sittingOut = false;
    seat.autoSitOut = false;
    this.pushLog(`${seat.name} пополняет стек до ${this.settings.buyIn}`);
    this.maybeStartHand();
    this.touch();
  }

  updateSettings(userId, patch) {
    if (userId !== this.hostId) throw new RoomError('Настройки меняет только хозяин стола');
    if (this.hand && !this.hand.complete) throw new RoomError('Дождитесь конца раздачи');
    const next = normalizeSettings({ ...this.settings, ...patch });

    if (next.maxPlayers < this.seats.filter(Boolean).length) {
      throw new RoomError('За столом больше игроков, чем новых мест');
    }
    const seats = new Array(next.maxPlayers).fill(null);
    this.seats.slice(0, next.maxPlayers).forEach((seat, i) => {
      seats[i] = seat;
    });
    // Игроков с «отрезанных» мест пересаживаем в начало.
    this.seats.slice(next.maxPlayers).filter(Boolean).forEach((seat) => {
      const free = seats.indexOf(null);
      if (free >= 0) seats[free] = seat;
    });
    this.seats = seats;
    this.settings = next;
    this.pushLog(`Настройки стола обновлены: блайнды ${next.smallBlind}/${next.bigBlind}, вход ${next.buyIn}`);
    this.touch();
  }

  // ——— Раздачи ———

  eligibleSeats() {
    return this.seats
      .map((seat, index) => ({ seat, index }))
      .filter(({ seat }) => seat && !seat.sittingOut && seat.stack > 0);
  }

  start(userId) {
    if (userId !== this.hostId) throw new RoomError('Игру начинает хозяин стола');
    if (this.eligibleSeats().length < 2) throw new RoomError('Нужно минимум два игрока с фишками');
    this.autoStart = true;
    this.pushLog('Игра началась. Удачи!');
    this.maybeStartHand();
    this.touch();
  }

  pause(userId) {
    if (userId !== this.hostId) throw new RoomError('Паузу ставит хозяин стола');
    this.autoStart = false;
    this.clearNextHandTimer();
    this.pushLog('Игра на паузе — новые раздачи не начинаются');
    this.touch();
  }

  maybeStartHand() {
    if (!this.autoStart) return;
    if (this.hand && !this.hand.complete) return;
    if (this.nextHandTimer) return;
    const eligible = this.eligibleSeats();
    if (eligible.length < 2) {
      this.status = 'waiting';
      return;
    }
    this.startHand();
  }

  startHand() {
    this.clearTurnTimer();
    this.clearNextHandTimer();
    this.lastResult = null;

    const eligible = this.eligibleSeats();
    if (eligible.length < 2) {
      this.status = 'waiting';
      this.hand = null;
      this.touch();
      return;
    }

    // Баттон переходит к следующему занятому месту по кругу.
    this.dealerSeat = nextOccupiedSeat(eligible.map((e) => e.index), this.dealerSeat, this.seats.length);
    const dealerIndex = eligible.findIndex((e) => e.index === this.dealerSeat);

    this.handNumber += 1;
    this.hand = new Hand({
      players: eligible.map(({ seat, index }) => ({ id: seat.userId, stack: seat.stack, seatIndex: index })),
      dealerIndex: dealerIndex < 0 ? 0 : dealerIndex,
      smallBlind: this.settings.smallBlind,
      bigBlind: this.settings.bigBlind,
    });
    this.hand.handNumber = this.handNumber;
    this.status = 'playing';

    this.pushLog(`Раздача №${this.handNumber} началась`);
    this.logHandEvents();
    this.armTurnTimer();
    this.touch();
  }

  applyAction(userId, action, amount) {
    if (!this.hand || this.hand.complete) throw new RoomError('Сейчас нет активной раздачи');
    const actor = this.hand.actingPlayer;
    if (!actor || actor.id !== userId) throw new RoomError('Сейчас не ваш ход');
    try {
      this.hand.act(userId, action, amount);
    } catch (error) {
      if (error instanceof ActionError) throw new RoomError(error.message);
      throw error;
    }
    this.afterHandProgress();
  }

  afterHandProgress() {
    this.logHandEvents();
    if (this.hand.complete) {
      this.finishHand();
    } else {
      this.armTurnTimer();
    }
    this.touch();
  }

  finishHand() {
    this.clearTurnTimer();
    const result = this.hand.result;

    // Переносим стеки обратно на места.
    for (const p of result.players) {
      const seat = this.seatOf(p.id);
      if (seat) seat.stack = p.stack;
    }

    this.lastResult = {
      showdown: result.showdown,
      board: result.board.map(cardToString),
      winners: result.winners.map((w) => ({
        userId: w.id,
        name: this.nameOf(w.id),
        amount: w.amount,
        hand: w.hand ? { name: w.hand.name, cards: w.hand.cards.map(cardToString) } : null,
      })),
      hands: (result.hands || []).map((h) => ({
        userId: h.id,
        name: this.nameOf(h.id),
        hole: h.hole.map(cardToString),
        combination: h.name,
        cards: h.cards.map(cardToString),
      })),
    };

    for (const winner of this.lastResult.winners) {
      const combo = winner.hand ? ` (${winner.hand.name})` : '';
      this.pushLog(`${winner.name} выигрывает ${winner.amount}${combo}`);
    }

    // Кто остался без фишек — уходит в «сижу мимо» до пополнения.
    for (const seat of this.seats) {
      if (seat && seat.stack === 0) {
        seat.sittingOut = true;
        seat.autoSitOut = false;
      }
    }

    this.status = 'waiting';
    const delay = result.showdown ? SHOWDOWN_PAUSE_MS : FOLD_PAUSE_MS;
    this.nextHandTimer = setTimeout(() => {
      this.nextHandTimer = null;
      this.maybeStartHand();
      this.touch();
    }, delay);
    this.nextHandTimer.unref?.();
    this.nextHandAt = Date.now() + delay;
  }

  // ——— Таймер хода ———

  armTurnTimer() {
    this.clearTurnTimer();
    if (!this.hand || this.hand.complete || !this.hand.actingPlayer) return;
    const playerId = this.hand.actingPlayer.id;
    const seat = this.seatOf(playerId);
    // Отключившимся даём меньше времени, чтобы стол не простаивал.
    const seconds = seat && !seat.connected ? Math.min(10, this.settings.turnSeconds) : this.settings.turnSeconds;
    this.turnDeadline = Date.now() + seconds * 1000;
    this.turnTimer = setTimeout(() => {
      this.turnTimer = null;
      if (!this.hand || this.hand.complete) return;
      const current = this.hand.actingPlayer;
      if (!current || current.id !== playerId) return;
      const legal = this.hand.legalActions(playerId);
      this.hand.timeout(playerId);
      this.pushLog(`${this.nameOf(playerId)} не успевает походить — ${legal && legal.canCheck ? 'чек' : 'пас'}`);
      this.afterHandProgress();
    }, seconds * 1000);
    this.turnTimer.unref?.();
  }

  clearTurnTimer() {
    if (this.turnTimer) clearTimeout(this.turnTimer);
    this.turnTimer = null;
    this.turnDeadline = null;
  }

  clearNextHandTimer() {
    if (this.nextHandTimer) clearTimeout(this.nextHandTimer);
    this.nextHandTimer = null;
    this.nextHandAt = null;
  }

  dispose() {
    this.clearTurnTimer();
    this.clearNextHandTimer();
  }

  // ——— Журнал и события ———

  nameOf(userId) {
    const seat = this.seatOf(userId);
    if (seat) return seat.name;
    return this.members.get(userId)?.name || 'Игрок';
  }

  pushLog(text) {
    this.log.push({ id: this.log.length + 1, text, at: Date.now() });
    if (this.log.length > MAX_LOG) this.log.splice(0, this.log.length - MAX_LOG);
  }

  chat(userId, text) {
    const clean = String(text || '').slice(0, 200).trim();
    if (!clean) return;
    this.emit('chat', { userId, name: this.nameOf(userId), text: clean, at: Date.now() });
  }

  // Превращает события движка в понятные строки журнала.
  logHandEvents() {
    if (!this.hand) return;
    const events = this.hand.events.splice(0);
    for (const event of events) {
      if (event.type === 'action') {
        const name = this.nameOf(event.playerId);
        const words = {
          fold: 'пас',
          check: 'чек',
          call: `колл ${event.amount ?? ''}`.trim(),
          bet: `ставка ${event.amount}`,
          raise: `рейз до ${event.amount}`,
        };
        this.pushLog(`${name}: ${words[event.action] || event.action}${event.allIn ? ' (олл-ин)' : ''}`);
      } else if (event.type === 'street') {
        const names = { flop: 'Флоп', turn: 'Тёрн', river: 'Ривер' };
        this.pushLog(`${names[event.street]}: ${event.board.map(prettyCard).join(' ')}`);
      } else if (event.type === 'refund') {
        this.pushLog(`${this.nameOf(event.playerId)} получает назад ${event.amount}`);
      }
    }
  }

  touch() {
    this.emit('update');
  }

  // ——— Состояние для клиента ———

  stateFor(userId) {
    const hand = this.hand;
    const showdown = this.lastResult && this.lastResult.showdown ? this.lastResult : null;
    const revealed = new Map();
    if (showdown) {
      for (const h of showdown.hands) revealed.set(h.userId, h.hole);
    }

    const streetBets = hand && !hand.complete
      ? hand.players.reduce((sum, p) => sum + p.committed, 0)
      : 0;
    const potTotal = hand ? hand.totalPot : 0;

    const seats = this.seats.map((seat, index) => {
      if (!seat) return { index, empty: true };
      const inHand = hand ? hand.player(seat.userId) : null;
      const isMe = seat.userId === userId;
      let cards = null;
      if (inHand && inHand.hole.length) {
        if (isMe) cards = inHand.hole.map(cardToString);
        else if (revealed.has(seat.userId)) cards = revealed.get(seat.userId);
        else cards = ['??', '??'];
      }
      return {
        index,
        empty: false,
        userId: seat.userId,
        name: seat.name,
        photoUrl: seat.photoUrl,
        // Во время раздачи актуальный стек живёт в движке.
        stack: inHand ? inHand.stack : seat.stack,
        sittingOut: seat.sittingOut,
        connected: seat.connected,
        isHost: seat.userId === this.hostId,
        inHand: Boolean(inHand),
        folded: inHand ? inHand.folded : false,
        allIn: inHand ? inHand.allIn : false,
        bet: inHand ? inHand.committed : 0,
        lastAction: inHand ? inHand.lastAction : null,
        cards,
        isDealer: index === this.dealerSeat,
        isActing: Boolean(inHand && hand && !hand.complete && hand.actingPlayer && hand.actingPlayer.id === seat.userId),
      };
    });

    const mySeatIndex = this.seatIndexOf(userId);
    const legal = hand && !hand.complete ? hand.legalActions(userId) : null;

    return {
      type: 'state',
      code: this.code,
      hostId: this.hostId,
      status: this.status,
      running: this.autoStart,
      settings: this.settings,
      handNumber: this.handNumber,
      phase: hand ? hand.phase : null,
      board: hand ? hand.board.map(cardToString) : (this.lastResult ? this.lastResult.board : []),
      pot: potTotal - streetBets,
      potTotal,
      seats,
      dealerSeat: this.dealerSeat,
      turnDeadline: this.turnDeadline,
      nextHandAt: this.nextHandAt || null,
      lastResult: this.lastResult,
      log: this.log.slice(-25),
      spectators: [...this.members.values()]
        .filter((m) => this.seatIndexOf(m.id) < 0)
        .map((m) => ({ userId: m.id, name: m.name, photoUrl: m.photoUrl })),
      you: {
        userId,
        seatIndex: mySeatIndex < 0 ? null : mySeatIndex,
        isHost: userId === this.hostId,
        stack: mySeatIndex >= 0 ? (hand && hand.player(userId) ? hand.player(userId).stack : this.seats[mySeatIndex].stack) : 0,
        sittingOut: mySeatIndex >= 0 ? this.seats[mySeatIndex].sittingOut : false,
        canRebuy: mySeatIndex >= 0
          && this.seats[mySeatIndex].stack < this.settings.buyIn
          && !(hand && !hand.complete && hand.player(userId)),
        legal: legal && {
          canFold: legal.canFold,
          canCheck: legal.canCheck,
          canCall: legal.canCall,
          callAmount: legal.callAmount,
          canRaise: legal.canRaise,
          minRaiseTo: legal.minRaiseTo,
          maxRaiseTo: legal.maxRaiseTo,
          isAllInRaise: legal.isAllInRaise,
        },
      },
    };
  }
}

function nextOccupiedSeat(occupiedIndexes, from, seatCount) {
  for (let step = 1; step <= seatCount; step++) {
    const candidate = (from + step + seatCount) % seatCount;
    if (occupiedIndexes.includes(candidate)) return candidate;
  }
  return occupiedIndexes[0] ?? -1;
}

function normalizeSettings(raw) {
  const settings = { ...DEFAULT_SETTINGS, ...raw };
  for (const [key, [min, max]] of Object.entries(SETTING_LIMITS)) {
    const value = Math.floor(Number(settings[key]));
    if (!Number.isFinite(value)) throw new RoomError(`Некорректное значение настройки «${key}»`);
    settings[key] = Math.min(max, Math.max(min, value));
  }
  if (settings.bigBlind <= settings.smallBlind) settings.bigBlind = settings.smallBlind * 2;
  if (settings.buyIn < settings.bigBlind * 2) settings.buyIn = settings.bigBlind * 20;
  return {
    smallBlind: settings.smallBlind,
    bigBlind: settings.bigBlind,
    buyIn: settings.buyIn,
    maxPlayers: settings.maxPlayers,
    turnSeconds: settings.turnSeconds,
  };
}

class RoomError extends Error {}

module.exports = { Room, RoomError, DEFAULT_SETTINGS, normalizeSettings };
