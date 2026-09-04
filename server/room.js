'use strict';

const { EventEmitter } = require('events');
const { Hand, ActionError } = require('./poker/hand');
const { BlackjackDuel, BlackjackError, handValue } = require('./blackjack/round');
const { cardToString, rankOf, RANK_CHARS } = require('./poker/cards');
const { bestHand } = require('./poker/evaluator');

const SUIT_SYMBOLS = { c: '♣', d: '♦', h: '♥', s: '♠' };

// Для журнала карты приятнее читать со значками мастей: «K♦», а не «Kd».
function prettyCard(card) {
  return prettyText(cardToString(card));
}

// То же самое, но для карты, уже приведённой к строке вида «Kd».
function prettyText(text) {
  const rank = text[0] === 'T' ? '10' : text[0];
  return rank + (SUIT_SYMBOLS[text[1]] || text[1]);
}

const DEFAULT_SETTINGS = {
  game: 'holdem', // holdem | blackjack
  smallBlind: 5,
  bigBlind: 10,
  minBet: 10, // для блекджека
  maxBet: 500,
  buyIn: 1000,
  maxPlayers: 6,
  turnSeconds: 45,
  isPublic: true, // стол по умолчанию виден всем в списке
};

const GAME_NAMES = { holdem: 'Холдем', blackjack: 'Блекджек' };

const SETTING_LIMITS = {
  smallBlind: [1, 10000],
  bigBlind: [2, 20000],
  minBet: [1, 100000],
  maxBet: [1, 1000000],
  buyIn: [20, 1000000],
  maxPlayers: [2, 9],
  turnSeconds: [10, 180],
};

const SHOWDOWN_PAUSE_MS = 6000;
const FOLD_PAUSE_MS = 2500;
const MAX_LOG = 60;

class Room extends EventEmitter {
  // bank — интерфейс балансов: { balanceOf, withdraw, deposit }.
  // Комната сама фишки не создаёт: они приходят с баланса и уходят обратно.
  constructor(code, host, settings = {}, { bank = null } = {}) {
    super();
    this.bank = bank;
    this.code = code;
    this.hostId = host.id;
    this.hostName = host.name;
    this.settings = normalizeSettings(settings);
    this.title = `${this.settings.game === 'blackjack' ? 'Блекджек' : 'Стол'} ${host.name}`;
    this.seats = new Array(this.settings.maxPlayers).fill(null);
    this.members = new Map(); // userId -> { id, name, photoUrl, connected }
    this.status = 'waiting';
    this.hand = null;
    this.round = null; // раздача блекджека
    this.dealerSeat = -1;
    this.handNumber = 0;
    this.log = [];
    this.feed = []; // последние действия для плашек над столом
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

  // Участвует ли игрок прямо сейчас в незавершённой раздаче.
  inActiveHand(userId) {
    if (this.isBlackjack) {
      if (this.status === 'betting') return true;
      return Boolean(this.round && !this.round.complete
        && (this.round.firstId === userId || this.round.secondId === userId));
    }
    return Boolean(this.hand && !this.hand.complete && this.hand.player(userId));
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

    const buyIn = this.settings.buyIn;
    if (this.bank) {
      try {
        this.bank.withdraw(userId, buyIn);
      } catch (error) {
        throw new RoomError(error.message);
      }
    }

    this.seats[seatIndex] = {
      userId,
      name: member.name,
      photoUrl: member.photoUrl,
      stack: buyIn,
      sittingOut: false,
      autoSitOut: false,
      brokeSitOut: false,
      leaveAfterHand: false,
      connected: true,
      joinedHand: this.handNumber,
    };
    this.pushLog(`${member.name} занимает место ${seatIndex + 1}, стек ${buyIn}`);
    this.maybeStartHand();
    this.touch();
  }

  stand(userId, { silent = false } = {}) {
    const index = this.seatIndexOf(userId);
    if (index < 0) return;
    const seat = this.seats[index];

    if (this.isBlackjack && this.inActiveHand(userId)) {
      // Посреди блекджековой раздачи место держим до её конца.
      seat.leaveAfterHand = true;
      if (!silent) this.pushLog(`${seat.name} уходит после раздачи`);
      this.touch();
      return;
    }

    const inHand = this.hand && !this.hand.complete && this.hand.player(userId);
    if (inHand && !inHand.folded) {
      // Нельзя просто исчезнуть посреди раздачи — сначала пас.
      try {
        this.applyAction(userId, 'fold');
      } catch {
        /* ход уже перешёл дальше */
      }
    }

    if (this.hand && !this.hand.complete && this.hand.player(userId)) {
      // Фишки ещё в раздаче: место освободим и вернём остаток после вскрытия.
      seat.leaveAfterHand = true;
      if (!silent) this.pushLog(`${seat.name} уходит после раздачи`);
      this.touch();
      return;
    }

    this.releaseSeat(index, { silent });
  }

  // Убирает игрока с места и возвращает его стек на баланс.
  releaseSeat(index, { silent = false } = {}) {
    const seat = this.seats[index];
    if (!seat) return;
    this.seats[index] = null;
    if (this.bank && seat.stack > 0) this.bank.deposit(seat.userId, seat.stack);
    if (!silent) {
      this.pushLog(`${seat.name} освобождает место, ${seat.stack} фишек ушли на баланс`);
    }
    this.touch();
  }

  // Все встают из-за стола: комнату закрывают или сервер выключается.
  cashOutAll() {
    this.seats.forEach((seat, index) => {
      if (seat) this.releaseSeat(index, { silent: true });
    });
  }

  setSittingOut(userId, value) {
    const seat = this.seatOf(userId);
    if (!seat) throw new RoomError('Вы не за столом');
    seat.sittingOut = Boolean(value);
    seat.autoSitOut = false;
    seat.brokeSitOut = false;
    this.pushLog(`${seat.name} ${seat.sittingOut ? 'пропускает раздачи' : 'снова в игре'}`);
    if (!seat.sittingOut) this.maybeStartHand();
    this.touch();
  }

  // Пополнение стека до размера входа — фишки берутся с баланса игрока.
  rebuy(userId) {
    const seat = this.seatOf(userId);
    if (!seat) throw new RoomError('Вы не за столом');
    if (this.inActiveHand(userId)) throw new RoomError('Пополнить стек можно между раздачами');
    if (seat.stack >= this.settings.buyIn) throw new RoomError('Фишек и так достаточно');

    const needed = this.settings.buyIn - seat.stack;
    const available = this.bank ? this.bank.balanceOf(userId) : needed;
    const amount = Math.min(needed, available);
    if (amount <= 0) throw new RoomError('На балансе нет фишек — попросите админа выдать');

    if (this.bank) {
      try {
        this.bank.withdraw(userId, amount);
      } catch (error) {
        throw new RoomError(error.message);
      }
    }
    seat.stack += amount;
    seat.sittingOut = false;
    seat.autoSitOut = false;
    seat.brokeSitOut = false;
    this.pushLog(`${seat.name} пополняет стек на ${amount}, теперь ${seat.stack}`);
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
    if (this.isBlackjack && (this.status === 'betting' || (this.round && !this.round.complete))) return;
    if (this.nextHandTimer) return;
    const eligible = this.eligibleSeats();
    if (eligible.length < 2) {
      this.status = 'waiting';
      return;
    }
    this.startHand();
  }

  get isBlackjack() {
    return this.settings.game === 'blackjack';
  }

  startHand() {
    if (this.isBlackjack) {
      this.startRound();
      return;
    }
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

    this.feed = [];
    this.pushLog(`Раздача №${this.handNumber} началась`);
    this.logHandEvents();
    this.armTurnTimer();
    this.touch();
  }

  // ——— Блекджек ———

  // Очередь начинать переходит по кругу: кто в прошлый раз ходил вторым,
  // теперь назначает ставку и ходит первым.
  startRound() {
    this.clearTurnTimer();
    this.clearNextHandTimer();
    this.lastResult = null;
    this.round = null;

    const eligible = this.eligibleSeats();
    if (eligible.length < 2) {
      this.status = 'waiting';
      this.touch();
      return;
    }

    this.openerSeat = nextOccupiedSeat(eligible.map((e) => e.index), this.openerSeat ?? -1, this.seats.length);
    this.secondSeat = eligible.find((e) => e.index !== this.openerSeat).index;
    this.handNumber += 1;
    this.status = 'betting';

    this.feed = [];
    this.pushLog(`Раздача №${this.handNumber}: ставку назначает ${this.seats[this.openerSeat].name}`);
    this.armBetTimer();
    this.touch();
  }

  // Ставят оба поровну, поэтому потолок — меньший из двух стеков.
  get maxBet() {
    if (this.openerSeat === undefined || this.secondSeat === undefined) return 0;
    const opener = this.seats[this.openerSeat];
    const second = this.seats[this.secondSeat];
    if (!opener || !second) return 0;
    return Math.min(this.settings.maxBet, opener.stack, second.stack);
  }

  placeBet(userId, amount) {
    if (!this.isBlackjack) throw new RoomError('Ставки делаются иначе');
    if (this.status !== 'betting') throw new RoomError('Сейчас не время ставить');
    if (this.seatIndexOf(userId) !== this.openerSeat) {
      throw new RoomError('В этой раздаче ставку назначает соперник');
    }

    const opener = this.seats[this.openerSeat];
    const second = this.seats[this.secondSeat];
    const value = Math.floor(Number(amount));
    if (!Number.isFinite(value)) throw new RoomError('Ставка должна быть числом');
    if (value < this.settings.minBet) throw new RoomError(`Минимальная ставка — ${this.settings.minBet}`);
    if (value > this.maxBet) throw new RoomError(`Максимальная ставка сейчас — ${this.maxBet}`);

    try {
      this.round = new BlackjackDuel({
        firstId: opener.userId,
        secondId: second.userId,
        bet: value,
        firstStack: opener.stack,
        secondStack: second.stack,
      });
    } catch (error) {
      throw new RoomError(error.message);
    }

    this.status = 'playing';
    this.pushLog(`Играют по ${value} с каждого`);
    this.logRoundEvents();
    if (this.round.complete) this.finishRound();
    else this.armTurnTimer();
    this.touch();
  }

  applyRoundAction(userId, action) {
    if (!this.round || this.round.complete) throw new RoomError('Сейчас нет активной раздачи');
    try {
      this.round.act(userId, action);
    } catch (error) {
      if (error instanceof BlackjackError) throw new RoomError(error.message);
      throw error;
    }
    this.logRoundEvents();
    if (this.round.complete) this.finishRound();
    else this.armTurnTimer();
    this.touch();
  }

  finishRound() {
    this.clearTurnTimer();
    const result = this.round.result;

    for (const seat of this.seats) {
      if (seat && result.stacks[seat.userId] !== undefined) seat.stack = result.stacks[seat.userId];
    }

    const winnerName = result.winnerId ? this.nameOf(result.winnerId) : null;
    this.lastResult = {
      game: 'blackjack',
      winner: result.winnerId ? 'player' : 'push',
      winnerName,
      reason: result.reason,
      amount: result.amount,
      players: [this.openerSeat, this.secondSeat]
        .map((index) => this.seats[index])
        .filter(Boolean)
        .map((seat) => ({
          name: seat.name,
          total: result.totals[seat.userId],
          cards: (result.cards[seat.userId] || []).map(cardToString),
        })),
    };

    for (const player of this.lastResult.players) {
      this.pushLog(`${player.name}: ${player.cards.map(prettyText).join(' ')} — ${player.total}`);
    }
    if (!winnerName) this.pushLog(`Ничья: ${result.reason}`);
    else this.pushLog(`${winnerName} забирает ${result.amount} (${result.reason})`);

    for (const seat of this.seats) {
      if (seat && seat.stack === 0) {
        seat.sittingOut = true;
        seat.brokeSitOut = true;
      }
    }

    this.seats.forEach((seat, index) => {
      if (seat && seat.leaveAfterHand) this.releaseSeat(index, { silent: false });
    });

    this.status = 'waiting';
    this.nextHandTimer = setTimeout(() => {
      this.nextHandTimer = null;
      this.maybeStartHand();
      this.touch();
    }, SHOWDOWN_PAUSE_MS);
    this.nextHandTimer.unref?.();
    this.nextHandAt = Date.now() + SHOWDOWN_PAUSE_MS;
  }

  // Не назначил ставку вовремя — ставим минимум, чтобы стол не стоял.
  armBetTimer() {
    this.clearTurnTimer();
    const seconds = this.settings.turnSeconds;
    this.turnDeadline = Date.now() + seconds * 1000;
    this.turnTimer = setTimeout(() => {
      this.turnTimer = null;
      if (this.status !== 'betting') return;
      const opener = this.seats[this.openerSeat];
      if (!opener) return;
      try {
        this.placeBet(opener.userId, Math.min(this.settings.minBet, this.maxBet));
        this.pushLog(`${opener.name} не успел выбрать ставку — поставили минимум`);
      } catch {
        this.status = 'waiting';
        this.touch();
      }
    }, seconds * 1000);
    this.turnTimer.unref?.();
  }

  logRoundEvents() {
    if (!this.round) return;
    const events = this.round.events.splice(0);
    for (const event of events) {
      if (event.type === 'hit') {
        // Достоинство карты не пишем: журнал видят оба, а руки закрыты.
        this.pushLog(`${this.nameOf(event.playerId)} берёт карту`);
      } else if (event.type === 'stand') {
        this.pushLog(`${this.nameOf(event.playerId)} останавливается`);
      }

      const words = { hit: 'берёт карту', stand: 'останавливается' };
      if (words[event.type]) {
        this.pushFeed({ name: this.nameOf(event.playerId), action: words[event.type], amount: null, allIn: false });
      }
    }
  }

  applyAction(userId, action, amount) {
    if (this.isBlackjack) {
      if (action === 'bet') this.placeBet(userId, amount);
      else this.applyRoundAction(userId, action);
      return;
    }
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

    // Кто просил встать посреди раздачи — уходит теперь, с остатком на баланс.
    this.seats.forEach((seat, index) => {
      if (seat && seat.leaveAfterHand) this.releaseSeat(index, { silent: false });
    });

    // Кто остался без фишек — уходит в «сижу мимо» до пополнения.
    for (const seat of this.seats) {
      if (seat && seat.stack === 0) {
        seat.sittingOut = true;
        seat.brokeSitOut = true;
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
    if (this.isBlackjack) {
      this.armRoundTimer();
      return;
    }
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

  // В блекджеке просрочивший ход просто останавливается.
  armRoundTimer() {
    this.clearTurnTimer();
    if (!this.round || this.round.complete || !this.round.actingId) return;
    const playerId = this.round.actingId;
    const seat = this.seatOf(playerId);
    const seconds = seat && !seat.connected ? Math.min(10, this.settings.turnSeconds) : this.settings.turnSeconds;
    this.turnDeadline = Date.now() + seconds * 1000;
    this.turnTimer = setTimeout(() => {
      this.turnTimer = null;
      if (!this.round || this.round.complete || this.round.actingId !== playerId) return;
      this.round.timeout(playerId);
      this.pushLog(`${this.nameOf(playerId)} не успел походить — останавливается`);
      this.logRoundEvents();
      if (this.round.complete) this.finishRound();
      else this.armTurnTimer();
      this.touch();
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

  // Плашки живут недолго и показывают только последние ходы.
  pushFeed(entry) {
    this.feed.push({ id: `${this.handNumber}-${this.feed.length}`, at: Date.now(), ...entry });
    if (this.feed.length > 4) this.feed.splice(0, this.feed.length - 4);
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
          fold: 'фолд',
          check: 'чек',
          call: `колл ${event.amount ?? ''}`.trim(),
          bet: `ставка ${event.amount}`,
          raise: `рейз до ${event.amount}`,
        };
        this.pushLog(`${name}: ${words[event.action] || event.action}${event.allIn ? ' (олл-ин)' : ''}`);
        this.pushFeed({
          name,
          action: ACTION_WORDS[event.action] || event.action,
          amount: event.action === 'fold' || event.action === 'check' ? null : event.amount ?? null,
          allIn: Boolean(event.allIn),
        });
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

  // Состояние блекджекового стола. Карты соперника закрыты до конца раздачи:
  // иначе, видя чужую руку, легко решить за него — брать ещё или хватит.
  blackjackStateFor(userId) {
    const round = this.round;
    const revealed = Boolean(round && round.complete);

    const seats = this.seats.map((seat, index) => {
      if (!seat) return { index, empty: true };

      const isOpener = index === this.openerSeat;
      const isMe = seat.userId === userId;
      const playing = Boolean(round);
      const open = isMe || revealed;

      let cards = null;
      let total = null;
      if (playing) {
        const own = round.cardsOf(seat.userId);
        cards = open ? own.map(cardToString) : own.map(() => '??');
        total = open ? round.valueOf(seat.userId).total : null;
      }

      return {
        index,
        empty: false,
        userId: seat.userId,
        name: seat.name,
        photoUrl: seat.photoUrl,
        stack: round && !round.complete ? round.stackOf(seat.userId) : seat.stack,
        sittingOut: seat.sittingOut,
        connected: seat.connected,
        isHost: seat.userId === this.hostId,
        isActing: Boolean(round && !round.complete && round.actingId === seat.userId),
        cards: cards && cards.length ? cards : null,
        total,
        busted: total !== null && total > 21,
        combination: total === null
          ? (playing ? `${cards.length} карты` : null)
          : `Очки: ${total}`,
        roleLabel: this.status === 'waiting' && !round ? null : (isOpener ? 'ходит первым' : 'ходит вторым'),
        lastAction: null,
        bet: round ? round.bet : 0,
        isDealer: false,
      };
    });

    const mySeatIndex = this.seatIndexOf(userId);
    const myTurn = Boolean(round && !round.complete && round.actingId === userId);
    const myBetTurn = this.status === 'betting' && mySeatIndex === this.openerSeat;

    return {
      type: 'state',
      game: 'blackjack',
      code: this.code,
      title: this.title,
      hostId: this.hostId,
      status: this.status,
      running: this.autoStart,
      settings: this.settings,
      handNumber: this.handNumber,
      phase: round ? round.phase : null,
      // В банке лежат обе ставки.
      pot: round ? round.bet * 2 : 0,
      potTotal: round ? round.bet * 2 : 0,
      board: [],
      seats,
      dealerSeat: -1,
      openerSeat: this.openerSeat === undefined ? null : this.openerSeat,
      turnDeadline: this.turnDeadline,
      nextHandAt: this.nextHandAt || null,
      lastResult: this.lastResult,
      log: this.log.slice(-25),
      feed: this.feed.slice(-3),
      spectators: [...this.members.values()]
        .filter((m) => this.seatIndexOf(m.id) < 0)
        .map((m) => ({ userId: m.id, name: m.name, photoUrl: m.photoUrl })),
      you: {
        userId,
        seatIndex: mySeatIndex < 0 ? null : mySeatIndex,
        isHost: userId === this.hostId,
        ...this.controlsFor(userId),
        stack: mySeatIndex >= 0 ? seats[mySeatIndex].stack : 0,
        balance: this.bank ? this.bank.balanceOf(userId) : 0,
        sittingOut: mySeatIndex >= 0 ? this.seats[mySeatIndex].sittingOut : false,
        canRebuy: mySeatIndex >= 0
          && this.seats[mySeatIndex].stack < this.settings.buyIn / 2
          && (this.bank ? this.bank.balanceOf(userId) > 0 : true)
          && !this.inActiveHand(userId),
        betTurn: myBetTurn
          ? { min: Math.min(this.settings.minBet, this.maxBet), max: this.maxBet }
          : null,
        legal: myTurn ? round.legalActions(userId) : null,
      },
    };
  }

  // Кнопки управления столом: показываем их только когда есть что нажимать.
  controlsFor(userId) {
    const seatIndex = this.seatIndexOf(userId);
    const seat = seatIndex >= 0 ? this.seats[seatIndex] : null;
    const ready = this.eligibleSeats().length;
    return {
      canStart: userId === this.hostId && !this.autoStart && ready >= 2,
      canPause: userId === this.hostId && this.autoStart,
      // Пропускать имеет смысл, только если раздачи идут и есть с кем играть;
      // тому, кто уже пропускает, кнопка нужна, чтобы вернуться.
      canSitOut: Boolean(seat) && this.autoStart && (seat.sittingOut || ready >= 2),
      paused: !this.autoStart && this.handNumber > 0,
    };
  }

  // Короткая карточка стола для списка открытых игр.
  summary() {
    const seated = this.seats.filter(Boolean);
    return {
      code: this.code,
      title: this.title,
      host: this.nameOf(this.hostId),
      players: seated.length,
      maxPlayers: this.settings.maxPlayers,
      game: this.settings.game,
      smallBlind: this.settings.smallBlind,
      bigBlind: this.settings.bigBlind,
      minBet: this.settings.minBet,
      maxBet: this.settings.maxBet,
      buyIn: this.settings.buyIn,
      running: this.autoStart,
      hasFreeSeat: this.seats.some((seat) => !seat),
      watchers: this.members.size,
      isPublic: this.settings.isPublic,
    };
  }

  // ——— Состояние для клиента ———

  stateFor(userId) {
    if (this.isBlackjack) return this.blackjackStateFor(userId);
    const hand = this.hand;
    const showdown = this.lastResult && this.lastResult.showdown ? this.lastResult : null;
    const revealed = new Map();
    const revealedCombination = new Map();
    if (showdown) {
      for (const h of showdown.hands) {
        revealed.set(h.userId, h.hole);
        revealedCombination.set(h.userId, h.combination);
      }
    }

    const streetBets = hand && !hand.complete
      ? hand.players.reduce((sum, p) => sum + p.committed, 0)
      : 0;
    const potTotal = hand ? hand.totalPot : 0;

    // Кто на блайндах — нужно для бейджей SB/BB на аватарах.
    const blindSeat = (index) => {
      if (!hand || index === undefined || !hand.players[index]) return -1;
      return this.seatIndexOf(hand.players[index].id);
    };
    const sbSeat = blindSeat(hand ? hand.sbIndex : undefined);
    const bbSeat = blindSeat(hand ? hand.bbIndex : undefined);

    const seats = this.seats.map((seat, index) => {
      if (!seat) return { index, empty: true };
      const inHand = hand ? hand.player(seat.userId) : null;
      const isMe = seat.userId === userId;
      let cards = null;
      let combination = null;
      if (inHand && inHand.hole.length) {
        if (isMe) {
          cards = inHand.hole.map(cardToString);
          if (!inHand.folded) combination = describeCombination(inHand.hole, hand.board);
        } else if (revealed.has(seat.userId)) {
          cards = revealed.get(seat.userId);
          combination = revealedCombination.get(seat.userId) || null;
        } else {
          cards = ['??', '??'];
        }
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
        combination,
        isDealer: index === this.dealerSeat,
        isSmallBlind: index === sbSeat,
        isBigBlind: index === bbSeat,
        isActing: Boolean(inHand && hand && !hand.complete && hand.actingPlayer && hand.actingPlayer.id === seat.userId),
      };
    });

    const mySeatIndex = this.seatIndexOf(userId);
    const legal = hand && !hand.complete ? hand.legalActions(userId) : null;

    return {
      type: 'state',
      code: this.code,
      title: this.title,
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
      feed: this.feed.slice(-3),
      spectators: [...this.members.values()]
        .filter((m) => this.seatIndexOf(m.id) < 0)
        .map((m) => ({ userId: m.id, name: m.name, photoUrl: m.photoUrl })),
      you: {
        userId,
        seatIndex: mySeatIndex < 0 ? null : mySeatIndex,
        isHost: userId === this.hostId,
        ...this.controlsFor(userId),
        stack: mySeatIndex >= 0 ? (hand && hand.player(userId) ? hand.player(userId).stack : this.seats[mySeatIndex].stack) : 0,
        sittingOut: mySeatIndex >= 0 ? this.seats[mySeatIndex].sittingOut : false,
        balance: this.bank ? this.bank.balanceOf(userId) : 0,
        canRebuy: mySeatIndex >= 0
          && this.seats[mySeatIndex].stack < this.settings.buyIn / 2
          && (this.bank ? this.bank.balanceOf(userId) > 0 : true)
          && !this.inActiveHand(userId),
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
  const game = settings.game === 'blackjack' ? 'blackjack' : 'holdem';
  if (game === 'blackjack') {
    // Блекджек у нас строго на двоих: один ставит, второй держит банк.
    settings.maxPlayers = 2;
    if (settings.maxBet < settings.minBet) settings.maxBet = settings.minBet * 10;
    if (settings.buyIn < settings.minBet * 2) settings.buyIn = settings.minBet * 20;
  }

  return {
    game,
    smallBlind: settings.smallBlind,
    bigBlind: settings.bigBlind,
    minBet: settings.minBet,
    maxBet: settings.maxBet,
    buyIn: settings.buyIn,
    maxPlayers: settings.maxPlayers,
    turnSeconds: settings.turnSeconds,
    isPublic: settings.isPublic !== false,
  };
}

const ACTION_WORDS = {
  fold: 'фолд',
  check: 'чек',
  call: 'колл',
  bet: 'ставка',
  raise: 'рейз',
};

// Подсказка «что у меня собралось». Считается только по картам,
// которые смотрящий и так видит, поэтому подсмотреть чужую руку через неё нельзя.
function describeCombination(hole, board) {
  if (!hole || hole.length < 2) return null;
  if (hole.length + board.length >= 5) return bestHand([...hole, ...board]).name;
  // До флопа подсказываем только карманную пару — остальное было бы шумом.
  if (rankOf(hole[0]) === rankOf(hole[1])) return `Пара ${RANK_CHARS[rankOf(hole[0])]}`;
  return null;
}

class RoomError extends Error {}

module.exports = { Room, RoomError, DEFAULT_SETTINGS, normalizeSettings, describeCombination };
