'use strict';

/* Клиент мини-аппа: тонкий слой поверх состояния, которое присылает сервер.
   Вся игровая логика живёт на сервере — здесь только отрисовка и ввод. */

const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

const SUITS = {
  s: { symbol: '♠', red: false },
  c: { symbol: '♣', red: false },
  h: { symbol: '♥', red: true },
  d: { symbol: '♦', red: true },
};

const state = {
  socket: null,
  connected: false,
  user: null,
  room: null,
  config: { devLogin: false, botUsername: '', appShortName: '' },
  pendingRoom: null,
  raiseTo: 0,
  raiseTouched: false,
  reconnectDelay: 500,
  chat: [],
  rooms: [],
  balance: 0,
  isAdmin: false,
  chipsSeat: null, // индекс места, которому выдаём фишки
  game: 'holdem', // выбранная в лобби игра
  bjBet: 0,
  bjBetTouched: false,
  unread: 0,
};

const $ = (id) => document.getElementById(id);

// ——— Запуск ———

async function boot() {
  if (tg) {
    tg.ready();
    tg.expand();
    applyTelegramTheme();
    tg.onEvent('themeChanged', applyTelegramTheme);
    // Обработчик системной кнопки «назад» регистрируем один раз.
    if (tg.BackButton) tg.BackButton.onClick(leaveRoom);
  }

  try {
    const response = await fetch('/config');
    state.config = await response.json();
  } catch {
    /* конфиг не критичен — работаем со значениями по умолчанию */
  }

  state.pendingRoom = readRoomFromLaunch();
  bindUi();
  connect();
}

function readRoomFromLaunch() {
  const fromTelegram = tg && tg.initDataUnsafe ? tg.initDataUnsafe.start_param : null;
  const fromUrl = new URLSearchParams(location.search).get('room');
  const code = (fromTelegram || fromUrl || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  return code.length === 5 ? code : null;
}

function applyTelegramTheme() {
  const params = tg.themeParams || {};
  const root = document.documentElement.style;
  if (params.bg_color) root.setProperty('--bg', params.bg_color);
  if (params.secondary_bg_color) root.setProperty('--surface', params.secondary_bg_color);
  if (params.text_color) root.setProperty('--text', params.text_color);
  if (params.hint_color) root.setProperty('--muted', params.hint_color);
  if (params.button_color) root.setProperty('--accent', params.button_color);
  try {
    tg.setHeaderColor(params.secondary_bg_color || '#171b21');
  } catch {
    /* старые версии клиента не поддерживают */
  }
}

// ——— Соединение ———

function connect() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${location.host}/ws`);
  state.socket = socket;

  socket.addEventListener('open', () => {
    state.connected = true;
    state.reconnectDelay = 500;
    setStatus('Авторизуемся…');
    authenticate();
  });

  socket.addEventListener('message', (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    handleMessage(message);
  });

  socket.addEventListener('close', () => {
    state.connected = false;
    setStatus('Соединение потеряно, переподключаемся…');
    // Экспоненциальная пауза, чтобы не долбить сервер при обрыве связи.
    setTimeout(connect, state.reconnectDelay);
    state.reconnectDelay = Math.min(state.reconnectDelay * 2, 10000);
  });
}

function send(message) {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify(message));
  }
}

function authenticate() {
  if (tg && tg.initData) {
    send({ type: 'auth', initData: tg.initData });
    return;
  }
  if (!state.config.devLogin) {
    setStatus('Откройте приложение через Telegram');
    return;
  }
  const saved = localStorage.getItem('poker:devName');
  if (saved) {
    send({ type: 'auth', name: saved, devId: deviceId() });
  } else {
    setStatus('Представьтесь, чтобы сесть за стол');
    $('dev-login').classList.remove('hidden');
  }
}

function deviceId() {
  let id = localStorage.getItem('poker:devId');
  if (!id) {
    id = Math.random().toString(36).slice(2, 12);
    localStorage.setItem('poker:devId', id);
  }
  return id;
}

function handleMessage(message) {
  switch (message.type) {
    case 'auth_ok':
      state.user = message.user;
      state.balance = message.balance || 0;
      state.isAdmin = Boolean(message.isAdmin);
      renderAccount();
      if (state.isAdmin) send({ type: 'admin_accounts' });
      $('dev-login').classList.add('hidden');
      $('lobby-actions').classList.remove('hidden');
      setStatus(`Вы вошли как ${message.user.name}`);
      startRoomsPolling();
      if (message.startParam) state.pendingRoom = normalizeCode(message.startParam);
      if (state.pendingRoom) {
        send({ type: 'join_room', code: state.pendingRoom });
        state.pendingRoom = null;
      }
      break;
    case 'joined':
      showTable();
      break;
    case 'left':
      state.room = null;
      showLobby();
      break;
    case 'state':
      state.room = message;
      renderTable();
      break;
    case 'balance':
      state.balance = message.balance;
      renderAccount();
      break;
    case 'accounts':
      renderAccounts(message.accounts);
      break;
    case 'rooms':
      state.rooms = message.rooms;
      renderRooms();
      break;
    case 'system':
      state.chat.push({ name: 'Стол', text: message.text, at: Date.now(), system: true });
      renderLog();
      toast(message.text);
      break;
    case 'chat':
      state.chat.push(message);
      if (state.chat.length > 50) state.chat.shift();
      if ($('log-panel').classList.contains('hidden')) {
        state.unread += 1;
        renderUnread();
      }
      renderLog();
      if (message.userId !== (state.user && state.user.id)) {
        toast(`${message.name}: ${message.text}`);
      }
      break;
    case 'error':
      toast(message.message);
      haptic('error');
      break;
    case 'replaced':
      toast('Игра открыта в другом окне');
      break;
    default:
      break;
  }
}

// ——— Экраны ———

function showLobby() {
  $('screen-table').classList.add('hidden');
  $('screen-lobby').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.hide();
  startRoomsPolling();
}

function showTable() {
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  closeChipsSheet();
}

// ——— Открытые столы ———

let roomsTimer = null;

function startRoomsPolling() {
  if (!state.user) return;
  send({ type: 'list_rooms' });
  if (roomsTimer) return;
  roomsTimer = setInterval(() => {
    if (state.socket && state.socket.readyState === WebSocket.OPEN) send({ type: 'list_rooms' });
  }, 5000);
}

function stopRoomsPolling() {
  if (roomsTimer) clearInterval(roomsTimer);
  roomsTimer = null;
}

// ——— Баланс и админ-панель ———

function renderAccount() {
  $('balance-value').textContent = String(state.balance);
  $('my-id').textContent = state.user ? state.user.id : '—';
  $('admin-card').classList.toggle('hidden', !state.isAdmin);
}

function renderAccounts(accounts) {
  const list = $('admin-accounts');
  if (!accounts || !accounts.length) {
    list.innerHTML = '<p class="hint">Счетов пока нет.</p>';
    return;
  }
  list.innerHTML = '';
  for (const account of accounts) {
    const row = document.createElement('div');
    row.className = 'account-row';
    const nick = account.username ? ` @${account.username}` : '';
    row.innerHTML = `
      <div class="account-name">
        ${escapeHtml(account.name)}${escapeHtml(nick)}
        <div class="account-id">${escapeHtml(account.id)}</div>
      </div>
      <div class="account-balance">${account.balance}</div>
    `;
    // Тап по строке подставляет игрока в поле выдачи.
    row.addEventListener('click', () => {
      $('admin-target').value = account.id;
      $('admin-amount').focus();
    });
    list.appendChild(row);
  }
}

function adminGrant(mode, sign = 1) {
  const target = $('admin-target').value.trim();
  const amount = Number($('admin-amount').value);
  if (!target) {
    toast('Укажите Telegram ID или @ник');
    return;
  }
  if (!Number.isFinite(amount)) {
    toast('Укажите количество фишек');
    return;
  }
  send({ type: 'admin_grant', target, amount: mode === 'set' ? amount : sign * Math.abs(amount), mode });
  setTimeout(() => send({ type: 'admin_accounts' }), 200);
}

function renderRooms() {
  const list = $('rooms-list');
  if (!state.rooms.length) {
    list.innerHTML = '<p class="hint">Пока никто не создал открытый стол. Создайте свой — друзья увидят его здесь.</p>';
    return;
  }

  list.innerHTML = '';
  for (const room of state.rooms) {
    const row = document.createElement('div');
    row.className = `room-row${room.hasFreeSeat ? '' : ' full'}`;
    const badge = room.running ? '<span class="room-badge">идёт игра</span>' : '';
    row.innerHTML = `
      <div class="room-main">
        <div class="room-title">${escapeHtml(room.title)} ${badge}</div>
        <div class="room-meta">
          ${room.game === 'blackjack' ? 'Блекджек' : 'Холдем'} · ${room.players}/${room.maxPlayers} за столом ·
          ${room.game === 'blackjack'
            ? `ставки ${room.minBet}–${room.maxBet}`
            : `блайнды ${room.smallBlind}/${room.bigBlind}`} · вход ${room.buyIn}
        </div>
      </div>
    `;
    const button = document.createElement('button');
    button.className = 'btn btn-primary';
    button.textContent = room.hasFreeSeat ? 'Играть' : 'Смотреть';
    button.addEventListener('click', () => {
      haptic('light');
      send({ type: 'join_room', code: room.code });
    });
    row.appendChild(button);
    list.appendChild(row);
  }
}

function setStatus(text) {
  $('lobby-status').textContent = text;
}

let toastTimer = null;
function toast(text) {
  const node = $('toast');
  node.textContent = text;
  node.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.add('hidden'), 2600);
}

function haptic(kind) {
  if (!tg || !tg.HapticFeedback) return;
  try {
    if (kind === 'error') tg.HapticFeedback.notificationOccurred('error');
    else if (kind === 'success') tg.HapticFeedback.notificationOccurred('success');
    else tg.HapticFeedback.impactOccurred('light');
  } catch {
    /* не критично */
  }
}

const normalizeCode = (value) => String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 5);

// ——— Отрисовка стола ———

function renderTable() {
  const room = state.room;
  if (!room) return;

  $('room-title').textContent = room.title || `Стол ${room.code}`;

  const blackjack = room.game === 'blackjack';
  const phases = blackjack
    ? { first: 'Ход первого', second: 'Ход второго', complete: 'Итог' }
    : { preflop: 'Префлоп', flop: 'Флоп', turn: 'Тёрн', river: 'Ривер', showdown: 'Вскрытие', complete: 'Вскрытие' };

  // Пока идёт раздача показываем этап, между раздачами — код стола.
  let tail = `код ${room.code}`;
  if (room.status === 'betting') tail = 'Ставка';
  else if (room.status === 'playing' && phases[room.phase]) tail = phases[room.phase];

  $('room-subtitle').textContent = blackjack
    ? `Блекджек · ${room.settings.minBet}–${room.settings.maxBet} · ${tail}`
    : `Холдем · ${room.settings.smallBlind}/${room.settings.bigBlind} · ${tail}`;

  renderBoard(room);
  renderSeats(room);
  renderFeed(room);
  renderMessage(room);
  renderControls(room);
  renderResult(room);
  renderLog();
}

function renderFeed(room) {
  const feed = $('feed');
  feed.innerHTML = '';
  if (room.status !== 'playing') return;
  for (const entry of room.feed || []) {
    const pill = document.createElement('div');
    pill.className = 'feed-pill';
    const amount = entry.amount === null || entry.amount === undefined
      ? ''
      : ` <span class="amount">${entry.amount}</span>`;
    const allIn = entry.allIn ? ' <span class="amount">олл-ин</span>' : '';
    pill.innerHTML = `<b>${escapeHtml(entry.name)}</b> — ${escapeHtml(entry.action)}${amount}${allIn}`;
    feed.appendChild(pill);
  }
}

function renderBoard(room) {
  const board = $('board');
  board.innerHTML = '';
  for (const card of room.board || []) board.appendChild(cardNode(card));

  const pot = $('pot');
  if (room.potTotal > 0) {
    pot.classList.remove('hidden');
    pot.querySelector('.pot-label').textContent = 'БАНК';
    $('pot-value').textContent = room.potTotal;
  } else {
    pot.classList.add('hidden');
  }
}

function cardNode(code, small = false) {
  const node = document.createElement('div');
  node.className = `card-face${small ? ' small' : ''}`;
  if (code === '??') {
    node.classList.add('back');
    return node;
  }
  const suit = SUITS[code[1]] || SUITS.s;
  if (suit.red) node.classList.add('red');
  // Десятку привычнее видеть как «10», а не как «T».
  const rank = code[0] === 'T' ? '10' : code[0];
  if (rank === '10') node.classList.add('ten');
  // Два угла, как на настоящей карте: второй перевёрнут.
  const corner = (position) => `<span class="corner ${position}"><b>${rank}</b><i>${suit.symbol}</i></span>`;
  node.innerHTML = corner('tl') + corner('br');
  return node;
}

function renderSeats(room) {
  const container = $('seats');
  container.innerHTML = '';

  const count = room.seats.length;
  const mySeat = room.you.seatIndex;
  // Своё место всегда внизу — так привычнее смотреть на стол.
  const offset = mySeat === null ? 0 : mySeat;

  room.seats.forEach((seat) => {
    const position = ((seat.index - offset) + count) % count;
    const angle = (90 + (position * 360) / count) * (Math.PI / 180);
    const node = document.createElement('div');
    node.className = 'seat';
    node.style.left = `${50 + 46 * Math.cos(angle)}%`;
    node.style.top = `${49 + 34 * Math.sin(angle)}%`;

    if (seat.empty) {
      node.classList.add('empty');
      const free = room.you.seatIndex === null;
      if (free) node.classList.add('joinable');
      const slot = document.createElement('div');
      slot.className = 'seat-empty-slot';
      slot.textContent = '+';
      if (free) {
        slot.addEventListener('click', () => {
          haptic('light');
          send({ type: 'sit', seat: seat.index });
        });
      }
      node.appendChild(slot);
      container.appendChild(node);
      return;
    }

    if (seat.userId === room.you.userId) node.classList.add('me');
    if (seat.folded) node.classList.add('folded');
    if (seat.isActing) node.classList.add('acting');
    if (!seat.connected || seat.sittingOut) node.classList.add('away');

    node.appendChild(avatarNode(seat));

    const plate = document.createElement('div');
    plate.className = 'seat-plate';
    const stack = seat.allIn
      ? '<div class="seat-stack allin">ALL-IN</div>'
      : `<div class="seat-stack">${seat.stack}</div>`;
    plate.innerHTML = `<div class="seat-name">${escapeHtml(seat.name)}</div>${stack}`;
    if (state.isAdmin) {
      node.classList.add('clickable');
      plate.addEventListener('click', () => openChipsSheet(seat));
    }
    node.appendChild(plate);

    if (seat.cards) {
      const cards = document.createElement('div');
      cards.className = 'seat-cards';
      for (const card of seat.cards) cards.appendChild(cardNode(card, true));
      node.appendChild(cards);
    }

    if (seat.combination) {
      const combo = document.createElement('div');
      combo.className = 'seat-combo';
      combo.textContent = seat.combination;
      node.appendChild(combo);
    }

    if (seat.bet > 0) {
      const bet = document.createElement('div');
      bet.className = 'seat-bet';
      bet.textContent = seat.bet;
      node.appendChild(bet);
    } else {
      const status = document.createElement('div');
      status.className = 'seat-status';
      status.textContent = seatStatus(seat);
      node.appendChild(status);
    }

    container.appendChild(node);
  });
}

function avatarNode(seat) {
  const avatar = document.createElement('div');
  avatar.className = 'seat-avatar';
  if (seat.photoUrl) {
    const img = document.createElement('img');
    img.src = seat.photoUrl;
    img.alt = '';
    avatar.appendChild(img);
  } else {
    avatar.textContent = (seat.name || '?').trim()[0].toUpperCase();
  }

  // Блайнды и баттон — бейджами на аватаре, как за живым столом.
  if (seat.isBigBlind) avatar.appendChild(badge('bb', 'BB'));
  else if (seat.isSmallBlind) avatar.appendChild(badge('sb', 'SB'));
  if (seat.isDealer) avatar.appendChild(badge('d', 'D'));
  return avatar;
}

function badge(kind, text) {
  const node = document.createElement('span');
  node.className = `pos-badge ${kind}`;
  node.textContent = text;
  return node;
}

function seatStatus(seat) {
  if (!seat.connected) return 'офлайн';
  if (seat.sittingOut) return 'пропускает';
  if (seat.roleLabel) return seat.roleLabel;
  return actionWord(seat.lastAction);
}

function actionWord(action) {
  return { fold: 'фолд', check: 'чек', call: 'колл', bet: 'ставка', raise: 'рейз' }[action] || '';
}

function renderMessage(room) {
  const node = $('table-message');
  const seated = room.seats.filter((s) => !s.empty).length;

  // Подсказка «сядьте за стол» — отдельной плашкой под столом.
  const canSit = room.you.seatIndex === null && room.seats.some((s) => s.empty);
  $('seat-hint').classList.toggle('hidden', !canSit);

  if (room.status === 'playing') {
    node.textContent = '';
    return;
  }
  if (room.status === 'betting') {
    const opener = room.seats[room.openerSeat];
    node.textContent = room.you.betTurn
      ? 'Назначьте ставку'
      : `Ставку назначает ${opener ? opener.name : 'соперник'}`;
    return;
  }
  if (seated < 2) node.textContent = 'Нужно минимум два игрока';
  else if (!room.running) {
    node.textContent = room.you.isHost ? 'Нажмите «Начать игру»' : 'Ждём, когда хозяин начнёт игру';
  } else if (room.nextHandAt) node.textContent = 'Следующая раздача…';
  else node.textContent = 'Ждём игроков';
}

function renderResult(room) {
  const pop = $('winner-pop');
  const result = room.lastResult;
  if (!result || room.status === 'playing' || room.status === 'betting'
      || (result.game !== 'blackjack' && !result.winners.length)) {
    pop.classList.add('hidden');
    return;
  }

  // В блекджеке игроки сидят сверху и снизу — поп-ап ставим по центру,
  // иначе он закрывает карты банкира.
  pop.classList.toggle('center', result.game === 'blackjack');

  if (result.game === 'blackjack') {
    const title = result.winner === 'push'
      ? 'Ничья'
      : `Выигрывает ${escapeHtml(result.winnerName)}`;
    const sum = result.winner === 'push' ? '' : `<div class="win-amount">+${result.amount}</div>`;
    const totals = (result.players || [])
      .map((player) => `${escapeHtml(player.name)} ${player.total}`)
      .join(' · ');
    pop.innerHTML = `
      <div class="win-title">${title}</div>
      <div class="win-combo">${escapeHtml(result.reason)}</div>
      ${sum}
      <div class="win-note">${totals}</div>
    `;
    pop.classList.remove('hidden');
    return;
  }

  if (result.winners.length === 1) {
    const winner = result.winners[0];
    const combo = winner.hand ? `<div class="win-combo">${escapeHtml(winner.hand.name)}</div>` : '';
    pop.innerHTML = `
      <div class="win-avatar">${escapeHtml((winner.name || '?').trim()[0].toUpperCase())}</div>
      <div class="win-title">Выигрывает ${escapeHtml(winner.name)}</div>
      ${combo}
      <div class="win-amount">+${winner.amount}</div>
      <div class="win-note">фишек</div>
    `;
  } else {
    const rows = result.winners
      .map((w) => `<div class="win-combo">${escapeHtml(w.name)} +${w.amount}</div>`)
      .join('');
    pop.innerHTML = `<div class="win-title">Банк разделён</div>${rows}`;
  }
  pop.classList.remove('hidden');
}

function renderControls(room) {
  const you = room.you;
  if (typeof you.balance === 'number') {
    state.balance = you.balance;
    renderAccount();
  }
  const seated = you.seatIndex !== null;
  // Свой ход — это и ход картами, и момент, когда надо назначить ставку.
  const myTurn = Boolean(you.legal) || Boolean(you.betTurn);

  // Пока идёт свой ход, служебные кнопки убираем — на экране только действия.
  const hostBox = $('host-controls');
  hostBox.classList.toggle('hidden', !you.isHost || myTurn);
  $('btn-start').classList.toggle('hidden', room.running);
  $('btn-pause').classList.toggle('hidden', !room.running);

  const sitBtn = $('btn-sit');
  const rebuyBtn = $('btn-rebuy');
  const sitoutBtn = $('btn-sitout');
  const hasFreeSeat = room.seats.some((s) => s.empty);

  sitBtn.classList.toggle('hidden', seated || !hasFreeSeat);
  rebuyBtn.classList.toggle('hidden', !you.canRebuy);
  // Пропускать раздачи имеет смысл только когда игра идёт.
  sitoutBtn.classList.toggle('hidden', !seated || !room.running);
  sitoutBtn.textContent = you.sittingOut ? 'Вернуться в игру' : 'Пропустить раздачу';

  const seatBox = $('seat-controls');
  const seatButtonsVisible = [sitBtn, rebuyBtn, sitoutBtn].some((b) => !b.classList.contains('hidden'));
  seatBox.classList.toggle('hidden', myTurn || !seatButtonsVisible);

  // Пока игрок не за столом, показываем баланс: хватит ли на вход.
  const chip = $('balance-chip');
  const short = !seated && you.balance < room.settings.buyIn;
  chip.classList.toggle('hidden', seated || myTurn);
  chip.innerHTML = short
    ? `На балансе <b>${you.balance}</b> — на вход нужно <b>${room.settings.buyIn}</b>. Попросите админа выдать фишки`
    : `На балансе <b>${you.balance}</b> фишек · вход <b>${room.settings.buyIn}</b>`;
  if (short) sitBtn.classList.add('hidden');

  if (room.game === 'blackjack') {
    renderBlackjackControls(room);
    return;
  }
  $('bj-bar').classList.add('hidden');

  // Панель действий появляется только на своём ходу.
  const legal = you.legal;
  const bar = $('action-bar');
  if (!legal) {
    bar.classList.add('hidden');
    state.raiseTouched = false;
    stopTurnTimer();
    return;
  }

  bar.classList.remove('hidden');
  $('btn-fold').classList.toggle('hidden', !legal.canFold);
  $('btn-check').classList.toggle('hidden', !legal.canCheck);

  const callBtn = $('btn-call');
  callBtn.classList.toggle('hidden', !legal.canCall);
  callBtn.textContent = `Колл ${legal.callAmount}`;

  const raiseBtn = $('btn-raise');
  raiseBtn.classList.toggle('hidden', !legal.canRaise);

  const raiseRow = $('raise-row');
  raiseRow.classList.toggle('hidden', !legal.canRaise);

  if (legal.canRaise) {
    const range = $('raise-range');
    range.min = String(legal.minRaiseTo);
    range.max = String(legal.maxRaiseTo);
    range.step = '1';
    if (!state.raiseTouched) state.raiseTo = legal.minRaiseTo;
    state.raiseTo = clamp(state.raiseTo, legal.minRaiseTo, legal.maxRaiseTo);
    range.value = String(state.raiseTo);
    $('raise-value').textContent = String(state.raiseTo);
    raiseBtn.textContent = state.raiseTo >= legal.maxRaiseTo ? 'Олл-ин' : `Рейз ${state.raiseTo}`;
  }

  startTurnTimer(room);
}

function renderBlackjackControls(room) {
  const you = room.you;
  $('action-bar').classList.add('hidden');

  const bar = $('bj-bar');
  const betRow = $('bj-bet-row');
  const actions = $('bj-actions');
  const betTurn = you.betTurn;
  const legal = you.legal;

  if (!betTurn && !legal) {
    bar.classList.add('hidden');
    state.bjBetTouched = false;
    stopTurnTimer();
    return;
  }
  bar.classList.remove('hidden');

  betRow.classList.toggle('hidden', !betTurn);
  actions.classList.toggle('hidden', !legal);

  if (betTurn) {
    const range = $('bj-range');
    range.min = String(betTurn.min);
    range.max = String(betTurn.max);
    range.step = '1';
    if (!state.bjBetTouched) state.bjBet = betTurn.min;
    state.bjBet = clamp(state.bjBet, betTurn.min, betTurn.max);
    range.value = String(state.bjBet);
    $('bj-bet-value').textContent = String(state.bjBet);
    $('bj-bet').textContent = `Поставить ${state.bjBet}`;
  }

  if (legal) {
    $('bj-hit').classList.toggle('hidden', !legal.canHit);
    $('bj-stand').classList.remove('hidden');
  }

  startTurnTimer(room, $('bj-timer').firstElementChild);
}

// ——— Таймер хода ———

let turnTimerHandle = null;
function startTurnTimer(room, target = null) {
  stopTurnTimer();
  if (!room.turnDeadline) return;
  const total = room.settings.turnSeconds * 1000;
  const bar = target || $('turn-timer').firstElementChild;
  const tick = () => {
    const left = room.turnDeadline - Date.now();
    const ratio = clamp(left / total, 0, 1);
    bar.style.width = `${ratio * 100}%`;
    if (left <= 0) stopTurnTimer();
  };
  tick();
  turnTimerHandle = setInterval(tick, 250);
}

function stopTurnTimer() {
  if (turnTimerHandle) clearInterval(turnTimerHandle);
  turnTimerHandle = null;
}

// ——— История и чат ———

function renderUnread() {
  const badge = $('chat-badge');
  badge.textContent = String(state.unread);
  badge.classList.toggle('hidden', state.unread === 0);
}

function renderLog() {
  const room = state.room;
  if (!room) return;
  const list = $('log-list');
  const entries = [
    ...room.log.map((line) => ({ at: line.at, html: `<div class="log-line">${escapeHtml(line.text)}</div>` })),
    ...state.chat.map((line) => ({
      at: line.at,
      html: line.system
        ? `<div class="log-line system">${escapeHtml(line.text)}</div>`
        : `<div class="log-line chat"><b>${escapeHtml(line.name)}</b>: ${escapeHtml(line.text)}</div>`,
    })),
  ].sort((a, b) => a.at - b.at);

  list.innerHTML = entries.map((e) => e.html).join('');
  list.scrollTop = list.scrollHeight;
}

// ——— Ввод ———

function bindUi() {
  $('dev-enter').addEventListener('click', () => {
    const name = $('dev-name').value.trim();
    if (!name) {
      toast('Введите имя');
      return;
    }
    localStorage.setItem('poker:devName', name);
    send({ type: 'auth', name, devId: deviceId() });
  });

  $('create-btn').addEventListener('click', () => {
    const common = {
      game: state.game,
      buyIn: Number($('set-buyin').value),
      turnSeconds: Number($('set-turn').value),
      isPublic: $('set-public').checked,
    };
    const settings = state.game === 'blackjack'
      ? { ...common, minBet: Number($('set-minbet').value), maxBet: Number($('set-maxbet').value) }
      : {
        ...common,
        smallBlind: Number($('set-sb').value),
        bigBlind: Number($('set-bb').value),
        maxPlayers: Number($('set-seats').value),
      };
    send({ type: 'create_room', settings });
  });

  $('join-code').addEventListener('input', (event) => {
    event.target.value = normalizeCode(event.target.value);
  });
  $('join-btn').addEventListener('click', () => {
    const code = normalizeCode($('join-code').value);
    if (code.length !== 5) {
      toast('Код состоит из пяти символов');
      return;
    }
    send({ type: 'join_room', code });
  });

  $('rooms-refresh').addEventListener('click', () => send({ type: 'list_rooms' }));
  $('admin-refresh').addEventListener('click', () => send({ type: 'admin_accounts' }));
  $('admin-give').addEventListener('click', () => adminGrant('add', 1));
  $('admin-take').addEventListener('click', () => adminGrant('add', -1));
  $('admin-set').addEventListener('click', () => adminGrant('set'));
  $('btn-my-id').addEventListener('click', () => {
    if (!state.user) return;
    if (navigator.clipboard) navigator.clipboard.writeText(state.user.id).catch(() => {});
    toast(`ID ${state.user.id} скопирован`);
  });

  $('chips-close').addEventListener('click', closeChipsSheet);
  $('chips-sheet').addEventListener('click', (event) => {
    if (event.target === $('chips-sheet')) closeChipsSheet();
  });
  document.querySelectorAll('[data-chips]').forEach((button) => {
    button.addEventListener('click', () => grantChips(button.dataset.chips, 'add'));
  });
  $('chips-give').addEventListener('click', () => grantChips($('chips-amount').value, 'add'));
  $('chips-take').addEventListener('click', () => grantChips(-Math.abs(Number($('chips-amount').value)), 'add'));
  $('chips-set').addEventListener('click', () => grantChips($('chips-amount').value, 'set'));

  $('btn-leave').addEventListener('click', leaveRoom);
  $('btn-code').addEventListener('click', copyCode);
  $('btn-invite').addEventListener('click', invite);
  $('btn-log').addEventListener('click', () => {
    $('log-panel').classList.remove('hidden');
    state.unread = 0;
    renderUnread();
  });
  $('btn-close').addEventListener('click', leaveRoom);
  $('btn-log-close').addEventListener('click', () => $('log-panel').classList.add('hidden'));

  $('btn-start').addEventListener('click', () => send({ type: 'start' }));
  $('btn-pause').addEventListener('click', () => send({ type: 'pause' }));
  $('btn-sit').addEventListener('click', () => {
    const free = state.room && state.room.seats.find((s) => s.empty);
    if (free) send({ type: 'sit', seat: free.index });
    else toast('Свободных мест нет');
  });
  $('btn-rebuy').addEventListener('click', () => send({ type: 'rebuy' }));
  $('btn-sitout').addEventListener('click', () => {
    send({ type: 'sit_out', value: !state.room.you.sittingOut });
  });

  document.querySelectorAll('[data-game]').forEach((button) => {
    button.addEventListener('click', () => {
      state.game = button.dataset.game;
      document.querySelectorAll('[data-game]').forEach((other) => {
        other.classList.toggle('is-active', other === button);
      });
      $('holdem-settings').classList.toggle('hidden', state.game !== 'holdem');
      $('blackjack-settings').classList.toggle('hidden', state.game !== 'blackjack');
    });
  });

  $('bj-hit').addEventListener('click', () => act('hit'));
  $('bj-stand').addEventListener('click', () => act('stand'));
  $('bj-bet').addEventListener('click', () => {
    haptic('success');
    state.bjBetTouched = false;
    send({ type: 'action', action: 'bet', amount: state.bjBet });
    $('bj-bar').classList.add('hidden');
  });
  $('bj-range').addEventListener('input', (event) => {
    state.bjBetTouched = true;
    state.bjBet = Number(event.target.value);
    $('bj-bet-value').textContent = String(state.bjBet);
    $('bj-bet').textContent = `Поставить ${state.bjBet}`;
  });
  document.querySelectorAll('[data-bj-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const betTurn = state.room && state.room.you.betTurn;
      if (!betTurn) return;
      const preset = button.dataset.bjPreset;
      const value = preset === 'min' ? betTurn.min
        : preset === 'max' ? betTurn.max
          : Math.floor((betTurn.min + betTurn.max) / 2);
      state.bjBetTouched = true;
      state.bjBet = clamp(value, betTurn.min, betTurn.max);
      $('bj-range').value = String(state.bjBet);
      $('bj-bet-value').textContent = String(state.bjBet);
      $('bj-bet').textContent = `Поставить ${state.bjBet}`;
      haptic('light');
    });
  });

  $('btn-fold').addEventListener('click', () => act('fold'));
  $('btn-check').addEventListener('click', () => act('check'));
  $('btn-call').addEventListener('click', () => act('call'));
  $('btn-raise').addEventListener('click', () => act('raise', state.raiseTo));

  $('raise-range').addEventListener('input', (event) => {
    state.raiseTouched = true;
    state.raiseTo = Number(event.target.value);
    $('raise-value').textContent = String(state.raiseTo);
    const legal = state.room && state.room.you.legal;
    if (legal) {
      $('btn-raise').textContent = state.raiseTo >= legal.maxRaiseTo ? 'Олл-ин' : `Рейз ${state.raiseTo}`;
    }
  });

  document.querySelectorAll('[data-preset]').forEach((button) => {
    button.addEventListener('click', () => applyPreset(button.dataset.preset));
  });

  $('chat-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('chat-input');
    const text = input.value.trim();
    if (!text) return;
    send({ type: 'chat', text });
    input.value = '';
  });

  // Не даём экрану засыпать посреди раздачи.
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.socket && state.socket.readyState === WebSocket.OPEN) {
      send({ type: 'ping' });
    }
  });
}

// ——— Выдача фишек ———

function openChipsSheet(seat) {
  // Адресуем по Telegram ID: имена за столом могут совпадать.
  state.chipsSeat = seat.userId;
  $('chips-title').textContent = `Баланс: ${seat.name}`;
  $('chips-stack').textContent = `ID ${seat.userId} · в стеке за столом ${seat.stack}`;
  $('chips-amount').value = '';
  $('chips-sheet').classList.remove('hidden');
  haptic('light');
}

function closeChipsSheet() {
  state.chipsSeat = null;
  $('chips-sheet').classList.add('hidden');
}

function grantChips(amount, mode = 'add') {
  if (!state.chipsSeat) return;
  const value = Math.floor(Number(amount));
  if (!Number.isFinite(value) || (mode === 'add' && value === 0)) {
    toast('Введите количество фишек');
    return;
  }
  send({ type: 'admin_grant', target: state.chipsSeat, amount: value, mode });
  closeChipsSheet();
}

function applyPreset(preset) {
  const room = state.room;
  const legal = room && room.you.legal;
  if (!legal || !legal.canRaise) return;

  const mySeat = room.seats[room.you.seatIndex];
  const myBet = mySeat ? mySeat.bet : 0;
  // Банк после уравнивания — от него и считаем «половину» и «банк».
  const potAfterCall = room.potTotal + legal.callAmount;

  let value;
  if (preset === 'min') value = legal.minRaiseTo;
  else if (preset === 'max') value = legal.maxRaiseTo;
  else if (preset === 'half') value = myBet + legal.callAmount + Math.floor(potAfterCall / 2);
  else value = myBet + legal.callAmount + potAfterCall;

  state.raiseTouched = true;
  state.raiseTo = clamp(value, legal.minRaiseTo, legal.maxRaiseTo);
  $('raise-range').value = String(state.raiseTo);
  $('raise-value').textContent = String(state.raiseTo);
  $('btn-raise').textContent = state.raiseTo >= legal.maxRaiseTo ? 'Олл-ин' : `Рейз ${state.raiseTo}`;
  haptic('light');
}

function act(action, amount) {
  haptic(action === 'fold' ? 'light' : 'success');
  state.raiseTouched = false;
  send({ type: 'action', action, amount });
  $('action-bar').classList.add('hidden');
}

function leaveRoom() {
  send({ type: 'leave_room' });
  state.room = null;
  showLobby();
}

function copyCode() {
  const room = state.room;
  if (!room) return;
  const text = room.code;
  if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
  toast(`Код стола ${text} скопирован`);
}

function invite() {
  const room = state.room;
  if (!room) return;
  const { botUsername, appShortName } = state.config;

  if (tg && botUsername && appShortName) {
    const link = `https://t.me/${botUsername}/${appShortName}?startapp=${room.code}`;
    const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent('Заходи играть в покер на фишки!')}`;
    tg.openTelegramLink(share);
    return;
  }
  copyCode();
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

boot();
