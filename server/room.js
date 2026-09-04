'use strict';

const { EventEmitter } = require('events');
const { Hand, ActionError } = require('./poker/hand');
const { cardToString, rankOf, RANK_CHARS } = require('./poker/cards');
const { bestHand } = require('./poker/evaluator');

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
  isPublic: true, // стол по умолчанию виден всем в списке
};

const MAX_STACK = 100000000;

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
    this.hostName = host.name;
    this.title = `Стол ${host.name}`;
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
      pendingChips: 0,
      pendingStack: null,
      sittingOut: false,
      autoSitOut: false,
      brokeSitOut: false,
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
    seat.brokeSitOut = false;
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
    seat.brokeSitOut = false;
    this.pushLog(`${seat.name} пополняет стек до ${this.settings.buyIn}`);
    this.maybeStartHand();
    this.touch();
  }

  // Находит место по номеру, имени или части имени — как удобнее набрать в команде.
  findSeat(reference) {
    const query = String(reference || '').trim();
    if (!query) return null;

    const asNumber = Number(query);
    if (Number.isInteger(asNumber) && asNumber >= 1 && asNumber <= this.seats.length) {
      return this.seats[asNumber - 1];
    }

    const lower = query.toLowerCase();
    const seated = this.seats.filter(Boolean);
    const exact = seated.filter((seat) => seat.name.toLowerCase() === lower);
    if (exact.length === 1) return exact[0];
    const partial = seated.filter((seat) => seat.name.toLowerCase().startsWith(lower));
    if (partial.length === 1) return partial[0];
    if (partial.length > 1) throw new RoomError(`Под «${query}» подходит несколько игроков — уточните имя`);
    return null;
  }

  // Хозяин стола выдаёт, забирает или выставляет фишки.
  // mode: 'add' | 'set'.  Фишки игровые, поэтому банк ниоткуда не берётся.
  grantChips(actorId, reference, amount, mode = 'add') {
    if (actorId !== this.hostId) throw new RoomError('Фишки выдаёт только хозяин стола');

    const value = Math.floor(Number(amount));
    if (!Number.isFinite(value)) throw new RoomError('Укажите количество фишек числом');
    if (mode === 'add' && value === 0) throw new RoomError('Ноль фишек выдавать незачем');
    if (mode === 'set' && value < 0) throw new RoomError('Стек не может быть отрицательным');

    const seat = this.findSeat(reference);
    if (!seat) throw new RoomError(`За столом нет игрока «${reference}»`);

    const inHand = Boolean(this.hand && !this.hand.complete && this.hand.player(seat.userId));
    const currentStack = inHand ? this.hand.player(seat.userId).stack : seat.stack;
    const target = mode === 'set' ? value : currentStack + (seat.pendingChips || 0) + value;

    if (target < 0) throw new RoomError(`У игрока ${seat.name} столько фишек нет`);
    if (target > MAX_STACK) throw new RoomError('Слишком большой стек');

    if (inHand) {
      // Посреди раздачи стек трогать нельзя — применим сразу после вскрытия.
      if (mode === 'set') {
        // Точный стек выставляем как есть, не смешивая с итогом раздачи.
        seat.pendingStack = target;
        seat.pendingChips = 0;
      } else {
        seat.pendingStack = null;
        seat.pendingChips = target - currentStack;
      }
      this.pushLog(`${seat.name}: ${describeGrant(target - currentStack, mode, target)} — применим после раздачи`);
      this.touch();
      return { seat, applied: false, target };
    }

    const delta = target - seat.stack;
    seat.stack = target;
    // Кто пропускал раздачи только из-за пустого стека — с фишками снова в игре.
    if (target > 0 && seat.brokeSitOut) {
      seat.sittingOut = false;
      seat.brokeSitOut = false;
    }
    this.pushLog(`${seat.name}: ${describeGrant(delta, mode, target)}`);
    this.maybeStartHand();
    this.touch();
    return { seat, applied: true, target };
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

    // Фишки, выданные хозяином посреди раздачи, применяем теперь.
    for (const seat of this.seats) {
      if (!seat) continue;
      if (seat.pendingStack === null || seat.pendingStack === undefined) {
        if (!seat.pendingChips) continue;
        seat.stack = Math.max(0, seat.stack + seat.pendingChips);
        this.pushLog(`${seat.name}: начислено ${seat.pendingChips > 0 ? '+' : ''}${seat.pendingChips}, стек ${seat.stack}`);
      } else {
        seat.stack = seat.pendingStack;
        this.pushLog(`${seat.name}: стек выставлен на ${seat.stack}`);
        seat.pendingStack = null;
      }
      seat.pendingChips = 0;
      if (seat.stack > 0 && seat.brokeSitOut) {
        seat.sittingOut = false;
        seat.brokeSitOut = false;
      }
    }

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
    if (!clean) return undefined;
    if (clean.startsWith('/')) return this.runCommand(userId, clean);
    this.emit('chat', { userId, name: this.nameOf(userId), text: clean, at: Date.now() });
    return undefined;
  }

  // Команды из чата. Возвращает текст ответа лично автору команды.
  runCommand(userId, line) {
    const tokens = line.slice(1).split(/\s+/).filter(Boolean);
    const command = (tokens.shift() || '').toLowerCase();

    // Последний аргумент — сумма, всё перед ним — имя или номер места.
    const takeTarget = () => {
      if (tokens.length < 2) throw new RoomError('Формат: /дать <имя или место> <сколько>');
      const amount = tokens[tokens.length - 1];
      const reference = tokens.slice(0, -1).join(' ');
      return { reference, amount };
    };

    switch (command) {
      case 'дать':
      case 'выдать':
      case 'give': {
        const { reference, amount } = takeTarget();
        const { seat, applied, target } = this.grantChips(userId, reference, Math.abs(Number(amount)), 'add');
        return applied
          ? `${seat.name}: выдано ${Math.abs(Math.floor(Number(amount)))}, стек ${target}`
          : `${seat.name} получит фишки после раздачи`;
      }
      case 'забрать':
      case 'take': {
        const { reference, amount } = takeTarget();
        const { seat, applied, target } = this.grantChips(userId, reference, -Math.abs(Number(amount)), 'add');
        return applied ? `${seat.name}: стек ${target}` : `Спишем у ${seat.name} после раздачи`;
      }
      case 'стек':
      case 'set': {
        const { reference, amount } = takeTarget();
        const { seat, applied, target } = this.grantChips(userId, reference, Number(amount), 'set');
        return applied ? `${seat.name}: стек ${target}` : `Стек ${seat.name} изменится после раздачи`;
      }
      case 'всем':
      case 'all': {
        if (userId !== this.hostId) throw new RoomError('Фишки выдаёт только хозяин стола');
        if (!tokens.length) throw new RoomError('Формат: /всем <сколько>');
        const amount = Number(tokens[0]);
        const seated = this.seats.filter(Boolean);
        if (!seated.length) throw new RoomError('За столом ещё никого нет');
        for (const seat of seated) {
          this.grantChips(userId, String(this.seatIndexOf(seat.userId) + 1), amount, 'add');
        }
        return `Выдано по ${Math.floor(amount)} каждому за столом`;
      }
      case 'помощь':
      case 'help':
      case '?':
        return COMMAND_HELP;
      default:
        throw new RoomError(`Неизвестная команда «/${command}». Наберите /помощь`);
    }
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

  // Короткая карточка стола для списка открытых игр.
  summary() {
    const seated = this.seats.filter(Boolean);
    return {
      code: this.code,
      title: this.title,
      host: this.nameOf(this.hostId),
      players: seated.length,
      maxPlayers: this.settings.maxPlayers,
      smallBlind: this.settings.smallBlind,
      bigBlind: this.settings.bigBlind,
      buyIn: this.settings.buyIn,
      running: this.autoStart,
      hasFreeSeat: this.seats.some((seat) => !seat),
      watchers: this.members.size,
      isPublic: this.settings.isPublic,
    };
  }

  // ——— Состояние для клиента ———

  stateFor(userId) {
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
    isPublic: settings.isPublic !== false,
  };
}

const COMMAND_HELP = [
  'Команды хозяина стола:',
  '/дать <имя или место> <сколько> — выдать фишки',
  '/забрать <имя или место> <сколько> — списать фишки',
  '/стек <имя или место> <сколько> — выставить стек',
  '/всем <сколько> — выдать всем за столом',
  'Вместо имени можно указать номер места: /дать 3 500',
].join('\n');

// Подсказка «что у меня собралось». Считается только по картам,
// которые смотрящий и так видит, поэтому подсмотреть чужую руку через неё нельзя.
function describeCombination(hole, board) {
  if (!hole || hole.length < 2) return null;
  if (hole.length + board.length >= 5) return bestHand([...hole, ...board]).name;
  // До флопа подсказываем только карманную пару — остальное было бы шумом.
  if (rankOf(hole[0]) === rankOf(hole[1])) return `Пара ${RANK_CHARS[rankOf(hole[0])]}`;
  return null;
}

function describeGrant(delta, mode, target) {
  if (mode === 'set') return `стек выставлен на ${target}`;
  if (delta > 0) return `выдано ${delta} фишек, стек ${target}`;
  return `списано ${Math.abs(delta)} фишек, стек ${target}`;
}

class RoomError extends Error {}

module.exports = { Room, RoomError, DEFAULT_SETTINGS, normalizeSettings, describeCombination };
