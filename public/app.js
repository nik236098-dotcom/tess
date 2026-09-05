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
  config: { devLogin: false, botUsername: '', appShortName: '', topup: null },
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
  shownCards: new Set(), // какие карты уже «прилетели» — чтобы не анимировать их снова
  shownHand: null,
  bjBet: 0,
  bjBetTouched: false,
  unread: 0,
  tab: 'home', // главная | игры
  wins: [], // лента последних выигрышей
  topup: {
    config: {
      enabled: false, providers: [], presets: [], presetCents: [],
      centsPerUnit: 100, minAmount: 0, maxAmount: 0,
      payout: { enabled: false, minCents: 0, maxCents: 0, providers: [] },
    },
    provider: null, // id выбранного платёжного сервиса
    invoice: null, // счёт, который сейчас ждёт оплаты
    busy: false,
  },
  payout: { provider: null, busy: false, last: null },
  links: { community: '', support: '' },
};

const $ = (id) => document.getElementById(id);

// Стол живёт на холсте постоянного размера и масштабируется целиком.
// Эти числа обязаны совпадать с --table-w/--table-h и рамкой .rail в CSS:
// от них считаются места, поэтому держим их в одном месте.
const TABLE = {
  // Логический размер холста. Пропорции те же, что у ассета (1086×1448),
  // поэтому картинка ложится в него без искажений.
  width: 450,
  height: 600,
  // Куда «смотрит» место: центр игровой зоны, там же лежат общие карты.
  focusX: 0.4982,
  focusY: 0.4941,
  maxScale: 2.4,
};

// Точки посадки сняты по пунктирным кружкам самого ассета (в долях от
// картинки), по часовой стрелке начиная снизу. Своё место всегда первое,
// поэтому игрок сидит внизу по центру, как в любом покерном клиенте.
// Раскладка мест снята с самого ассета: точка посадки — нарисованный на
// картинке пунктирный кружок. Блок игрока (аватар, имя, стек, карты) стоит
// на этой точке и растёт вниз одним куском. Отдельная доля есть только у
// ставки: это фишка на сукне, она лежит между игроком и банком.
// Всё в долях от картинки, поэтому масштабируется вместе с ней.
// shift — небольшая доводка блока в пикселях холста. Нужна там, где
// кружок ассета стоит вплотную к краю сукна: у боковых мест блок сдвигается
// внутрь, у нижнего — чуть вверх, чтобы карты не сползали на борт.
const SEAT_ANCHORS = [
  { seat: [0.4972, 0.8273], bet: [0.4975, 0.7156], shift: [0, -14] }, // низ по центру
  { seat: [0.2597, 0.7486], bet: [0.3225, 0.6382], shift: [0, 0] },   // низ слева
  { seat: [0.1989, 0.4834], bet: [0.3428, 0.3745], shift: [12, 0] },  // середина слева
  { seat: [0.2652, 0.2348], bet: [0.3509, 0.3940], shift: [0, 0] },   // верх слева
  { seat: [0.4972, 0.1561], bet: [0.4977, 0.3178], shift: [0, 0] },   // верх по центру
  { seat: [0.7348, 0.2348], bet: [0.6476, 0.3935], shift: [0, 0] },   // верх справа
  { seat: [0.7956, 0.4834], bet: [0.6517, 0.3745], shift: [-12, 0] }, // середина справа
  { seat: [0.7348, 0.7486], bet: [0.6726, 0.6380], shift: [0, 0] },   // низ справа
];

// Место номер index из count. Пока мест не больше восьми, они садятся ровно
// на кружки ассета; девятое доводится интерполяцией по тому же контуру.
function seatAnchor(index, count) {
  const total = SEAT_ANCHORS.length;
  if (count <= total) return SEAT_ANCHORS[Math.round((index * total) / count) % total];

  const exact = (index * total) / count;
  const from = SEAT_ANCHORS[Math.floor(exact) % total];
  const to = SEAT_ANCHORS[(Math.floor(exact) + 1) % total];
  const t = exact - Math.floor(exact);
  const mix = (key) => [
    from[key][0] + (to[key][0] - from[key][0]) * t,
    from[key][1] + (to[key][1] - from[key][1]) * t,
  ];
  return { seat: mix('seat'), bet: mix('bet'), shift: [0, 0] };
}

// Иконки берутся из общего спрайта в index.html — эмодзи в интерфейсе не
// используются, чтобы вид не зависел от шрифта конкретной платформы.
const icon = (name, extra = '') => `<svg class="icon ${extra}"><use href="#i-${name}"></use></svg>`;

// Привязка обработчика по id. Если элемента нет — пишем в консоль и живём
// дальше: одна пропавшая кнопка не должна мешать приложению подключиться.
function on(id, event, handler) {
  const element = $(id);
  if (!element) {
    console.warn(`Нет элемента #${id} — обработчик ${event} не повешен`);
    return;
  }
  element.addEventListener(event, handler);
}

// Сервер считает деньги целыми центами (см. server/money.js), а показываем
// мы доллары. Здесь ровно те же правила округления, что и на сервере.
function money(cents) {
  const value = Math.round(Number(cents) || 0);
  const sign = value < 0 ? '-' : '';
  const absolute = Math.abs(value);
  return `${sign}$${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`;
}

// "12.34", "$12,34", -5 -> центы. null, если это не сумма.
function toCents(input) {
  const text = String(input ?? '').trim().replace(/\s+/g, '').replace(',', '.').replace(/^\$/, '');
  if (!/^-?\d*\.?\d*$/.test(text) || text === '' || text === '.' || text === '-') return null;
  const value = Number(text);
  if (!Number.isFinite(value)) return null;
  return Math.round(value * 100);
}

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
  // Интерфейс не должен мешать связи: если разметка и скрипт разошлись
  // (например, браузер подсунул старый app.js), играть всё равно можно.
  watchTableSize();
  try {
    bindUi();
  } catch (error) {
    console.error('Не удалось навесить обработчики интерфейса:', error);
    setStatus('Интерфейс обновился — перезапустите приложение');
  }
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
      if (message.links) applyLinks(message.links);
      if (message.topup) applyTopUpConfig(message.topup);
      renderAccount();
      if (state.isAdmin) send({ type: 'admin_accounts' });
      $('dev-login').classList.add('hidden');
      $('lobby-actions').classList.remove('hidden');
      $('bottom-nav').classList.remove('hidden');
      showTab(state.tab);
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
    case 'topup_invoice':
      state.topup.busy = false;
      state.topup.invoice = message.invoice;
      renderTopUpInvoice();
      // Сразу открываем оплату: игрок только что нажал «Выставить счёт»,
      // лишний тап между ним и оплатой никому не нужен.
      openPayLink(message.invoice.url || message.invoice.fallbackUrl);
      startTopUpPolling();
      break;
    case 'topup_status':
      if (state.topup.invoice && message.invoice.id === state.topup.invoice.id) {
        state.topup.invoice = message.invoice;
        renderTopUpInvoice();
        if (message.invoice.status !== 'pending') stopTopUpPolling();
      }
      break;
    case 'topup_paid':
      stopTopUpPolling();
      if (state.topup.invoice && state.topup.invoice.id === message.id) {
        state.topup.invoice = { ...state.topup.invoice, status: 'paid', creditedCents: message.cents };
        renderTopUpInvoice();
      }
      haptic('success');
      break;
    case 'accounts':
      renderAccounts(message.accounts);
      break;
    case 'rooms':
      state.rooms = message.rooms;
      if (message.wins) state.wins = message.wins;
      renderRooms();
      renderWins();
      break;
    case 'leaders':
      renderLeaders(message.leaders);
      break;
    case 'history':
      renderHistory(message.history);
      break;
    case 'promo_ok':
      $('promo-code').value = '';
      $('promo-note').textContent = message.text;
      haptic('success');
      break;
    case 'payout_status':
      state.payout.busy = false;
      state.payout.last = message.payout;
      renderPayout();
      if (message.payout.status === 'done') haptic('success');
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
      state.topup.busy = false;
      state.payout.busy = false;
      renderTopUpControls();
      renderPayoutControls();
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

// Один общий коэффициент по обеим осям: форма стола не может измениться,
// как бы ни менялось окно. Меняется только размер — вместе со всем, что
// лежит на холсте: местами, картами, фишками, аватарами и шрифтами.
function fitTable() {
  const viewport = $('table-viewport');
  const canvas = $('table-canvas');
  if (!viewport || !canvas) return;

  const box = viewport.getBoundingClientRect();
  if (box.width < 2 || box.height < 2) return; // экран стола ещё скрыт

  // Поля по краям: иначе крайние места упираются в границы области и
  // верхнее срезается шапкой.
  const pad = 4;
  const scale = Math.min(
    Math.max(box.width - pad * 2, 1) / TABLE.width,
    Math.max(box.height - pad * 2, 1) / TABLE.height,
    TABLE.maxScale,
  );
  canvas.style.transform = `scale(${scale})`;
  // Ширину стола на экране забирает нижняя панель, чтобы кнопки шли ровно
  // по краям стола, а не расползались на всю ширину монитора.
  document.documentElement.style.setProperty('--table-px', `${Math.round(TABLE.width * scale)}px`);
}

function watchTableSize() {
  const viewport = $('table-viewport');
  if (!viewport) return;
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(fitTable).observe(viewport);
  }
  window.addEventListener('resize', fitTable);
  window.addEventListener('orientationchange', fitTable);
}

function showTable() {
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  closeChipsSheet();
  // Пока экран был скрыт, у области стола не было размеров — считаем сейчас.
  fitTable();
  requestAnimationFrame(fitTable);
}

// Главная и Игры — это две панели одного экрана лобби: столы и лента
// выигрышей приходят одним и тем же сообщением, переключение ничего не грузит.
function showTab(tab) {
  state.tab = tab === 'games' ? 'games' : 'home';
  $('tab-home').classList.toggle('hidden', state.tab !== 'home');
  $('tab-games').classList.toggle('hidden', state.tab !== 'games');
  for (const button of document.querySelectorAll('.nav-btn')) {
    button.classList.toggle('is-active', button.dataset.tab === state.tab);
  }
  const scroller = document.querySelector('.lobby');
  if (scroller) scroller.scrollTop = 0;
}

// Раскрывающиеся разделы главной: открытый ровно один.
const PANELS = ['promo-card', 'topup-card', 'payout-card', 'leaders-card', 'history-card', 'help-card'];

function togglePanel(id) {
  const target = $(id);
  const opening = target.classList.contains('hidden');
  for (const panel of PANELS) $(panel).classList.add('hidden');
  if (opening) target.classList.remove('hidden');
  for (const tile of document.querySelectorAll('.tile')) tile.classList.remove('is-active');
  return opening;
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
  $('balance-value').textContent = money(state.balance);
  $('my-id').textContent = state.user ? state.user.id : '—';
  $('admin-card').classList.toggle('hidden', !state.isAdmin);

  renderPayoutControls();

  const avatar = $('avatar');
  const photo = state.user && state.user.photoUrl;
  if (photo && avatar.dataset.photo !== photo) {
    avatar.dataset.photo = photo;
    avatar.innerHTML = `<img src="${escapeHtml(photo)}" alt="" />`;
  }
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
    row.className = 'data-row';
    const nick = account.username ? ` @${account.username}` : '';
    row.innerHTML = `
      <span class="data-row-main">
        <b>${escapeHtml(account.name)}${escapeHtml(nick)}</b>
        <span>${escapeHtml(account.id)}</span>
      </span>
      <span class="data-sum">${money(account.balance)}</span>
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
  const amount = toCents($('admin-amount').value);
  if (!target) {
    toast('Укажите Telegram ID или @ник');
    return;
  }
  if (amount === null || !Number.isFinite(amount)) {
    toast('Укажите сумму в долларах, например 50');
    return;
  }
  send({ type: 'admin_grant', target, amount: mode === 'set' ? amount : sign * Math.abs(amount), mode });
  setTimeout(() => send({ type: 'admin_accounts' }), 200);
}

// Каждый открытый стол виден и в «Активных играх» на главной, и полным
// списком во вкладке «Игры» — данные одни и те же, отличается только вид.
function renderRooms() {
  renderActiveGames();

  const list = $('rooms-list');
  if (!state.rooms.length) {
    list.innerHTML = '<div class="empty-note">Пока никто не создал открытый стол.<br>Создайте свой — друзья увидят его здесь.</div>';
    return;
  }

  list.innerHTML = '';
  for (const room of state.rooms) {
    const row = document.createElement('div');
    row.className = `room-row${room.hasFreeSeat ? '' : ' full'}`;
    const badge = room.running ? '<span class="room-badge">идёт игра</span>' : '';
    const blackjack = room.game === 'blackjack';
    row.innerHTML = `
      <div class="room-main">
        <div class="room-title">${icon(blackjack ? 'club' : 'spade', 'icon-sm')}${escapeHtml(room.title)} ${badge}</div>
        <div class="room-meta">
          ${room.players}/${room.maxPlayers} за столом ·
          ${blackjack
            ? `ставки <span class="gold">${money(room.minBet)}–${money(room.maxBet)}</span>`
            : `блайнды <span class="gold">${money(room.smallBlind)}/${money(room.bigBlind)}</span>`} ·
          вход <span class="gold">${money(room.buyIn)}</span>
        </div>
      </div>
    `;
    const button = document.createElement('button');
    button.className = room.hasFreeSeat ? 'btn btn-outline' : 'btn btn-ghost';
    button.textContent = room.hasFreeSeat ? 'Играть' : 'Смотреть';
    button.addEventListener('click', () => {
      haptic('light');
      send({ type: 'join_room', code: room.code });
    });
    row.appendChild(button);
    list.appendChild(row);
  }
}

// «Активные игры» на главной: те же открытые столы, но плиткой и с банком.
function renderActiveGames() {
  const list = $('home-rooms');
  if (!state.rooms.length) {
    list.innerHTML = '<div class="empty-note">Открытых столов сейчас нет.<br>Создайте свой во вкладке «Игры».</div>';
    return;
  }

  list.innerHTML = '';
  for (const room of state.rooms) {
    const blackjack = room.game === 'blackjack';
    const stake = blackjack
      ? `${money(room.minBet)}–${money(room.maxBet)}`
      : `${money(room.smallBlind)}/${money(room.bigBlind)}`;
    const card = document.createElement('div');
    card.className = 'game-card';
    card.innerHTML = `
      <div class="game-card-top">
        ${icon(blackjack ? 'club' : 'spade', 'icon-sm')}
        <span>${blackjack ? 'Блекджек' : "Texas Hold'em"}</span>
      </div>
      <div class="game-card-title">${escapeHtml(room.title)}</div>
      <div class="game-card-rows">
        <div class="game-card-row"><span>Игроки</span><b>${room.players}/${room.maxPlayers}</b></div>
        <div class="game-card-row"><span>${blackjack ? 'Ставки' : 'Блайнды'}</span><b class="gold">${stake}</b></div>
        <div class="game-card-row"><span>Банк</span><b class="gold">${money(room.pot || 0)}</b></div>
      </div>
    `;
    const button = document.createElement('button');
    button.className = room.hasFreeSeat ? 'btn btn-outline' : 'btn btn-ghost';
    button.textContent = room.hasFreeSeat ? 'Присоединиться' : 'Смотреть';
    button.addEventListener('click', () => {
      haptic('light');
      send({ type: 'join_room', code: room.code });
    });
    card.appendChild(button);
    list.appendChild(card);
  }
}

function renderWins() {
  const card = $('wins-card');
  const list = $('wins-list');
  card.classList.toggle('hidden', !state.wins.length);
  if (!state.wins.length) return;

  list.innerHTML = state.wins.map((win) => `
    <div class="win-card">
      <span class="win-sum">+${money(win.amount)}</span>
      <span class="win-game">${win.game === 'blackjack' ? 'Блекджек' : 'Покер'}</span>
      <span class="win-name">${escapeHtml(win.name)}</span>
    </div>
  `).join('');
}

function renderLeaders(leaders) {
  const list = $('leaders-list');
  if (!leaders || !leaders.length) {
    list.innerHTML = '<p class="hint">Пока пусто.</p>';
    return;
  }
  list.innerHTML = leaders.map((account, index) => `
    <div class="data-row">
      <span class="rank">${index + 1}</span>
      <span class="data-row-main"><b>${escapeHtml(account.name)}</b></span>
      <span class="data-sum">${money(account.balance)}</span>
    </div>
  `).join('');
}

function renderHistory(history) {
  const list = $('history-list');
  if (!history || !history.length) {
    list.innerHTML = '<p class="hint">Операций пока не было.</p>';
    return;
  }

  const titles = {
    paid: 'Пополнение', expired: 'Счёт истёк',
    done: 'Вывод', failed: 'Вывод отменён', unknown: 'Вывод в обработке', pending: 'Вывод',
  };

  list.innerHTML = history.map((item) => {
    const income = item.kind === 'topup';
    const amount = income ? (item.creditedCents || item.cents) : item.cents;
    // Неудачный вывод деньги вернул, истёкший счёт ничего не принёс —
    // такие строки не должны выглядеть как движение денег.
    const nothing = (income && item.status !== 'paid') || item.status === 'failed';
    const tone = nothing ? 'is-bad' : (income ? 'is-in' : '');
    const sign = nothing ? '' : (income ? '+' : '−');
    const when = new Date(item.createdAt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    return `
      <div class="data-row">
        <span class="data-row-main">
          <b>${titles[item.status] || item.status}</b>
          <span>${escapeHtml(item.providerTitle)} · ${when}</span>
        </span>
        <span class="data-sum ${tone}">${sign}${money(amount)}</span>
      </div>
    `;
  }).join('');
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
    ? `Блекджек · ${money(room.settings.minBet)}–${money(room.settings.maxBet)} · ${tail}`
    : `Холдем · ${money(room.settings.smallBlind)}/${money(room.settings.bigBlind)} · ${tail}`;

  renderBoard(room);
  renderSeats(room);
  renderHandBadge(room);
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
      : ` <span class="amount">${money(entry.amount)}</span>`;
    const allIn = entry.allIn ? ' <span class="amount">олл-ин</span>' : '';
    pill.innerHTML = `<b>${escapeHtml(entry.name)}</b> — ${escapeHtml(entry.action)}${amount}${allIn}`;
    feed.appendChild(pill);
  }
}

function renderBoard(room) {
  const board = $('board');
  // В блекджеке общих карт нет — пустые слоты там были бы обманом.
  if (room.game === 'blackjack') {
    board.innerHTML = '';
    board.dataset.cards = '';
    const pot = $('pot');
    if (room.potTotal > 0) {
      pot.classList.remove('hidden');
      $('pot-value').textContent = money(room.potTotal);
    } else {
      pot.classList.add('hidden');
    }
    return;
  }

  const codes = (room.board || []).join(',');
  // Если борд не изменился, не трогаем DOM: иначе карты каждый раз
  // пересоздаются и заново проигрывают анимацию раздачи.
  if (board.dataset.cards !== codes) {
    const known = board.dataset.cards ? board.dataset.cards.split(',') : [];
    const cards = room.board || [];
    board.innerHTML = '';
    // До флопа общих карт нет — и пустых рамок тоже: центр стола должен
    // выглядеть законченным, а не размеченным под будущие карты.
    // Как только приходит флоп, ставим сразу пять слотов: тёрн и ривер
    // занимают готовое место, и стол не дёргается.
    if (cards.length) {
      for (let index = 0; index < 5; index++) {
        const slot = document.createElement('div');
        slot.className = 'card-slot';
        if (cards[index]) {
          slot.classList.add('filled');
          slot.appendChild(cardNode(cards[index], false, known[index] !== cards[index]));
        }
        board.appendChild(slot);
      }
    }
    board.dataset.cards = codes;
  }

  const pot = $('pot');
  if (room.potTotal > 0) {
    pot.classList.remove('hidden');
    pot.querySelector('.pot-label').textContent = 'БАНК';
    $('pot-value').textContent = money(room.potTotal);
  } else {
    pot.classList.add('hidden');
  }
}

function cardNode(code, small = false, animate = true) {
  const node = document.createElement('div');
  node.className = `card-face${small ? ' small' : ''}${animate ? '' : ' no-anim'}`;
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

// Своя комбинация — отдельной пилюлей над столом. Считается на сервере
// только по картам, которые игрок и так видит.
function renderHandBadge(room) {
  const badge = $('hand-badge');
  const seat = room.you.seatIndex !== null ? room.seats[room.you.seatIndex] : null;
  const text = seat && seat.combination;
  badge.classList.toggle('hidden', !text);
  if (text) badge.textContent = text;
}

// Карты игрока. Ключ помнит, что уже лежало на этом месте: новая карта
// прилетает с анимацией, а прежние просто перерисовываются.
function buildSeatCards(seat) {
  const cards = document.createElement('div');
  cards.className = 'seat-cards';
  seat.cards.forEach((card, index) => {
    const key = `${seat.index}:${index}:${card}`;
    const fresh = !state.shownCards.has(key);
    state.shownCards.add(key);
    cards.appendChild(cardNode(card, true, fresh));
  });
  return cards;
}

function renderSeats(room) {
  if (state.shownHand !== room.handNumber) {
    state.shownHand = room.handNumber;
    state.shownCards.clear();
  }

  const container = $('seats');
  container.innerHTML = '';

  const count = room.seats.length;
  const mySeat = room.you.seatIndex;
  // Своё место всегда внизу — так привычнее смотреть на стол.
  const offset = mySeat === null ? 0 : mySeat;

  room.seats.forEach((seat) => {
    const position = ((seat.index - offset) + count) % count;

    // Единственная точка привязки места — кружок, нарисованный на ассете.
    // Карты и ставка живут внутри того же места и смещены от якоря на
    // заранее подобранные величины, а не собственными координатами.
    const anchor = seatAnchor(position, count);
    const node = document.createElement('div');
    node.className = 'seat';
    node.style.left = `${(anchor.seat[0] * 100).toFixed(3)}%`;
    node.style.top = `${(anchor.seat[1] * 100).toFixed(3)}%`;
    // Ставка — фишка на сукне, поэтому у неё своё смещение от того же якоря.
    const betShift = (axis, size) => `${((anchor.bet[axis] - anchor.seat[axis]) * size).toFixed(1)}px`;
    node.style.setProperty('--bet-x', betShift(0, TABLE.width));
    node.style.setProperty('--bet-y', betShift(1, TABLE.height));
    node.style.setProperty('--body-x', `${anchor.shift[0]}px`);
    node.style.setProperty('--body-y', `${anchor.shift[1]}px`);

    const body = document.createElement('div');
    body.className = 'seat-body';
    node.appendChild(body);

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
      body.appendChild(slot);
      container.appendChild(node);
      return;
    }

    if (seat.userId === room.you.userId) node.classList.add('me');
    if (seat.folded) node.classList.add('folded');
    if (seat.isActing) node.classList.add('acting');
    if (!seat.connected || seat.sittingOut) node.classList.add('away');

    body.appendChild(avatarNode(seat));

    const plate = document.createElement('div');
    plate.className = 'seat-plate';
    const stack = seat.allIn
      ? '<div class="seat-stack allin">ALL-IN</div>'
      : `<div class="seat-stack">${money(seat.stack)}</div>`;
    plate.innerHTML = `<div class="seat-name">${escapeHtml(seat.name)}</div>${stack}`;
    if (state.isAdmin) {
      node.classList.add('clickable');
      plate.addEventListener('click', () => openChipsSheet(seat));
    }
    body.appendChild(plate);

    if (seat.combination) {
      const combo = document.createElement('div');
      combo.className = 'seat-combo';
      combo.textContent = seat.combination;
      body.appendChild(combo);
    }

    if (seat.bet <= 0) {
      const status = document.createElement('div');
      status.className = 'seat-status';
      status.textContent = seatStatus(seat);
      body.appendChild(status);
    }

    // Карты — часть блока игрока и идут сразу под табличкой со стеком:
    // аватар → имя → стек → карты. Своих координат у них нет.
    if (seat.cards) body.appendChild(buildSeatCards(seat));
    if (seat.bet > 0) {
      const bet = document.createElement('div');
      bet.className = 'seat-bet';
      bet.textContent = money(seat.bet);
      node.appendChild(bet);
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
  if (seated < 2) {
    node.textContent = 'Нужно минимум два игрока';
  } else if (!room.running) {
    node.textContent = room.you.isHost ? 'Нажмите «Начать игру»' : 'Ждём, когда хозяин начнёт игру';
  } else if (room.you.sittingOut) {
    node.textContent = 'Ждём, пока вы пополните стек';
  } else if (room.nextHandAt) {
    node.textContent = 'Следующая раздача…';
  } else {
    node.textContent = 'Ждём игроков';
  }
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
    const sum = result.winner === 'push' ? '' : `<div class="win-amount">+${money(result.amount)}</div>`;
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
      <div class="win-amount">+${money(winner.amount)}</div>
      <div class="win-note">фишек</div>
    `;
  } else {
    const rows = result.winners
      .map((w) => `<div class="win-combo">${escapeHtml(w.name)} +${money(w.amount)}</div>`)
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
  const startBtn = $('btn-start');

  // Кнопку старта показываем, пока игра не идёт, но гасим, если начинать
  // ещё не с кем — так видно, чего не хватает. Игра идёт — кнопки нет.
  startBtn.disabled = !you.canStart;
  hostBox.classList.toggle('hidden', myTurn || room.running || !you.isHost);

  const sitBtn = $('btn-sit');
  const rebuyBtn = $('btn-rebuy');
  const hasFreeSeat = room.seats.some((s) => s.empty);

  sitBtn.classList.toggle('hidden', seated || !hasFreeSeat);
  rebuyBtn.classList.toggle('hidden', !you.canRebuy);

  const seatBox = $('seat-controls');
  const seatButtonsVisible = [sitBtn, rebuyBtn].some((b) => !b.classList.contains('hidden'));
  seatBox.classList.toggle('hidden', myTurn || !seatButtonsVisible);

  // Пока игрок не за столом, показываем баланс: хватит ли на вход.
  const chip = $('balance-chip');
  const short = !seated && you.balance < room.settings.buyIn;
  chip.classList.toggle('hidden', seated || myTurn);
  chip.innerHTML = short
    ? `На балансе <b>${money(you.balance)}</b> — на вход нужно <b>${money(room.settings.buyIn)}</b>. Пополните баланс на главной`
    : `На балансе <b>${money(you.balance)}</b> · вход <b>${money(room.settings.buyIn)}</b>`;
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
    closeRaisePanel();
    stopTurnTimer();
    return;
  }

  bar.classList.remove('hidden');
  $('btn-fold').classList.toggle('hidden', !legal.canFold);
  $('btn-check').classList.toggle('hidden', !legal.canCheck);

  const callBtn = $('btn-call');
  callBtn.classList.toggle('hidden', !legal.canCall);
  callBtn.textContent = `Колл ${money(legal.callAmount)}`;

  // «Рейз» открывает панель со слайдером, «Олл-ин» ставит всё сразу —
  // так в одну строку помещаются все четыре действия.
  const raiseBtn = $('btn-raise');
  const allInBtn = $('btn-allin');
  raiseBtn.classList.toggle('hidden', !legal.canRaise);
  allInBtn.classList.toggle('hidden', !legal.canRaise);

  if (legal.canRaise) {
    const range = $('raise-range');
    range.min = String(legal.minRaiseTo);
    range.max = String(legal.maxRaiseTo);
    range.step = '1';
    if (!state.raiseTouched) state.raiseTo = legal.minRaiseTo;
    state.raiseTo = clamp(state.raiseTo, legal.minRaiseTo, legal.maxRaiseTo);
    range.value = String(state.raiseTo);
    renderRaiseValue(legal);
  } else {
    closeRaisePanel();
  }

  startTurnTimer(room);
}

function renderRaiseValue(legal) {
  $('raise-value').textContent = money(state.raiseTo);
  const confirm = $('raise-confirm');
  const allIn = legal && state.raiseTo >= legal.maxRaiseTo;
  confirm.classList.toggle('is-allin', Boolean(allIn));
  confirm.textContent = allIn ? 'Олл-ин' : `Рейз до ${money(state.raiseTo)}`;
}

function openRaisePanel() {
  const legal = state.room && state.room.you.legal;
  if (!legal || !legal.canRaise) return;
  $('raise-row').classList.remove('hidden');
  renderRaiseValue(legal);
}

function closeRaisePanel() {
  $('raise-row').classList.add('hidden');
  state.raiseTouched = false;
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
    $('bj-bet-value').textContent = money(state.bjBet);
    $('bj-bet').textContent = `Поставить ${money(state.bjBet)}`;
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

// ——— Пополнение баланса ———

function applyTopUpConfig(config) {
  state.topup.config = config;
  const payoutProviders = (config.payout && config.payout.providers) || [];
  if (!payoutProviders.some((provider) => provider.id === state.payout.provider)) {
    state.payout.provider = payoutProviders.length ? payoutProviders[0].id : null;
  }
  if (!config.enabled) {
    state.topup.provider = null;
  } else if (!config.providers.some((provider) => provider.id === state.topup.provider)) {
    // Запоминаем последний выбор игрока, но только если сервис ещё подключён.
    const saved = localStorage.getItem('poker:topupProvider');
    const known = config.providers.some((provider) => provider.id === saved);
    state.topup.provider = known ? saved : config.providers[0].id;
  }
  renderTopUp();
}

// Карточки, ведущие наружу, показываем только когда ссылка настроена:
// кнопка в никуда хуже её отсутствия.
function applyLinks(links) {
  state.links = { community: links.community || '', support: links.support || '' };
  $('other-games').classList.toggle('hidden', !state.links.community);
  $('help-support').classList.toggle('hidden', !state.links.support);
}

function openExternal(url) {
  if (!url) return;
  if (tg && /^https:\/\/t\.me\//i.test(url) && tg.openTelegramLink) tg.openTelegramLink(url);
  else if (tg && tg.openLink) tg.openLink(url);
  else window.open(url, '_blank');
}

function currentProvider() {
  const { config, provider } = state.topup;
  return config.providers.find((item) => item.id === provider) || config.providers[0] || null;
}

function renderTopUp() {
  const { config } = state.topup;
  $('btn-topup').disabled = !config.enabled;
  if (!config.enabled) {
    $('topup-card').classList.add('hidden');
    $('payout-card').classList.add('hidden');
    $('btn-payout').disabled = true;
    return;
  }

  const provider = currentProvider();
  $('topup-rate').textContent = provider
    ? `1 ${provider.currency} = ${money(config.centsPerUnit)}`
    : '';

  // Кнопки сервисов рисуем, только когда их больше одного: с единственным
  // подключённым сервисом выбирать нечего.
  const providers = $('topup-providers');
  providers.classList.toggle('hidden', config.providers.length < 2);
  providers.innerHTML = '';
  if (config.providers.length > 1) {
    for (const item of config.providers) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `game-option${item.id === state.topup.provider ? ' is-active' : ''}`;
      button.innerHTML = `${icon('wallet')}<b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.currency)}</span>`;
      button.addEventListener('click', () => {
        state.topup.provider = item.id;
        localStorage.setItem('poker:topupProvider', item.id);
        renderTopUp();
      });
      providers.appendChild(button);
    }
  }

  const presets = $('topup-presets');
  presets.innerHTML = '';
  const current = Number($('topup-amount').value);
  for (const amount of config.presets) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `chip-btn${amount === current ? ' is-active' : ''}`;
    button.textContent = money(amount * config.centsPerUnit);
    button.addEventListener('click', () => {
      $('topup-amount').value = String(amount);
      renderTopUp();
    });
    presets.appendChild(button);
  }

  $('topup-amount').min = String(config.minAmount);
  $('topup-amount').max = String(config.maxAmount);
  $('topup-amount').placeholder = `от ${config.minAmount} до ${config.maxAmount}`;

  renderTopUpControls();
  renderTopUpInvoice();
  renderPayout();
}

function renderTopUpControls() {
  const { config, busy } = state.topup;
  if (!config.enabled) return;
  const provider = currentProvider();
  const amount = Number($('topup-amount').value);
  const cents = Number.isFinite(amount) && amount > 0 ? Math.round(amount * config.centsPerUnit) : 0;

  $('topup-chips').innerHTML = cents > 0 && provider
    ? `${amount} ${escapeHtml(provider.currency)} → <b>${money(cents)}</b>`
    : '&nbsp;';
  $('topup-create').disabled = busy || cents <= 0;
  $('topup-create').textContent = busy ? 'Создаём счёт…' : 'Выставить счёт';
}

function renderTopUpInvoice() {
  const box = $('topup-invoice');
  const invoice = state.topup.invoice;
  box.classList.toggle('hidden', !invoice);
  if (!invoice) return;

  $('topup-invoice-sum').textContent = `${invoice.amount} ${invoice.currency} → ${money(invoice.cents)}`;

  const label = $('topup-invoice-state');
  label.classList.toggle('is-paid', invoice.status === 'paid');
  label.classList.toggle('is-expired', invoice.status === 'expired');
  if (invoice.status === 'paid') {
    label.textContent = `Оплачено · +${money(invoice.creditedCents || invoice.cents)}`;
  } else if (invoice.status === 'expired') {
    label.textContent = 'Счёт истёк';
  } else {
    label.textContent = `Ждём оплату в ${invoice.providerTitle}…`;
  }

  const paid = invoice.status !== 'pending';
  $('topup-pay').classList.toggle('hidden', paid);
  $('topup-check').classList.toggle('hidden', paid);
  $('topup-cancel').textContent = paid ? 'Закрыть' : 'Отмена';
}

function createTopUp() {
  const { config } = state.topup;
  const provider = currentProvider();
  const amount = Number($('topup-amount').value);
  if (!provider) return;
  if (!Number.isFinite(amount) || amount <= 0) {
    toast('Введите сумму');
    return;
  }
  if (amount < config.minAmount || amount > config.maxAmount) {
    toast(`Сумма должна быть от ${config.minAmount} до ${config.maxAmount}`);
    return;
  }
  state.topup.busy = true;
  renderTopUpControls();
  send({ type: 'topup_create', provider: provider.id, amount });
}

// Ссылки обоих сервисов ведут в Telegram, поэтому внутри мини-аппа их надо
// открывать именно openTelegramLink — обычный openLink уводит в браузер.
function openPayLink(url) {
  if (!url) return;
  if (tg && /^https:\/\/t\.me\//i.test(url) && tg.openTelegramLink) tg.openTelegramLink(url);
  else if (tg && tg.openLink) tg.openLink(url);
  else window.open(url, '_blank');
}

// ——— Вывод ———

function payoutProvider() {
  const { providers } = state.topup.config.payout;
  return providers.find((item) => item.id === state.payout.provider) || providers[0] || null;
}

function renderPayout() {
  const payout = state.topup.config.payout;
  if (!payout.enabled) {
    $('btn-payout').disabled = true;
    return;
  }
  $('btn-payout').disabled = false;

  const provider = payoutProvider();
  $('payout-rate').textContent = provider
    ? `${money(state.topup.config.centsPerUnit)} = 1 ${provider.currency}`
    : '';

  // Кнопки сервисов показываем, только если их правда несколько.
  const box = $('payout-providers');
  box.classList.toggle('hidden', payout.providers.length < 2);
  box.innerHTML = '';
  if (payout.providers.length > 1) {
    for (const item of payout.providers) {
      const button = document.createElement('button');
      button.type = 'button';
      const active = provider && item.id === provider.id;
      button.className = `game-option${active ? ' is-active' : ''}`;
      button.innerHTML = `${icon('wallet')}<b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.currency)}</span>`;
      button.addEventListener('click', () => {
        state.payout.provider = item.id;
        renderPayout();
      });
      box.appendChild(button);
    }
  }

  $('payout-amount').min = String(payout.minCents / 100);
  $('payout-amount').max = String(Math.min(payout.maxCents, state.balance) / 100);
  $('payout-amount').placeholder = `от ${money(payout.minCents).slice(1)}`;

  renderPayoutControls();
  renderPayoutState();
}

function renderPayoutControls() {
  const payout = state.topup.config.payout;
  if (!payout.enabled) return;
  const cents = toCents($('payout-amount').value);
  const enough = cents !== null && cents > 0 && cents <= state.balance && cents >= payout.minCents;

  $('payout-note').innerHTML = cents && cents > 0
    ? `${money(cents)} · на балансе ${money(state.balance)}`
    : `Минимум ${money(payout.minCents)} · на балансе ${money(state.balance)}`;
  $('payout-send').disabled = state.payout.busy || !enough;
  $('payout-send').textContent = state.payout.busy ? 'Отправляем…' : 'Вывести';
}

function renderPayoutState() {
  const box = $('payout-state');
  const last = state.payout.last;
  box.classList.toggle('hidden', !last);
  if (!last) return;

  $('payout-state-sum').textContent = `${money(last.cents)} → ${last.amount} ${last.currency}`;
  const label = $('payout-state-text');
  label.classList.toggle('is-paid', last.status === 'done');
  label.classList.toggle('is-expired', last.status === 'failed' || last.status === 'unknown');
  label.textContent = {
    done: 'Отправлено',
    pending: 'Отправляем…',
    failed: `Не вышло: ${last.error || 'сервис отказал'}`,
    unknown: 'В обработке — сервис не ответил, деньги не потеряны',
  }[last.status] || last.status;
}

function redeemPromo() {
  const code = $('promo-code').value.trim();
  if (!code) {
    toast('Введите промокод');
    return;
  }
  send({ type: 'promo_redeem', code });
}

function createPayout() {
  const payout = state.topup.config.payout;
  const provider = payoutProvider();
  const cents = toCents($('payout-amount').value);
  if (!provider) return;
  if (cents === null || cents <= 0) {
    toast('Введите сумму');
    return;
  }
  if (cents < payout.minCents) {
    toast(`Минимальная сумма вывода — ${money(payout.minCents)}`);
    return;
  }
  if (cents > state.balance) {
    toast(`На балансе только ${money(state.balance)}`);
    return;
  }
  state.payout.busy = true;
  renderPayoutControls();
  send({ type: 'payout_create', provider: provider.id, cents });
}

let topupTimer = null;

// Вебхук может быть не настроен (или не дойти) — поэтому пока счёт висит,
// спрашиваем статус сами. Опрос сам себя останавливает, когда счёт закрыт.
function startTopUpPolling() {
  stopTopUpPolling();
  topupTimer = setInterval(() => {
    const invoice = state.topup.invoice;
    if (!invoice || invoice.status !== 'pending' || invoice.expiresAt < Date.now()) {
      stopTopUpPolling();
      return;
    }
    if (state.socket && state.socket.readyState === WebSocket.OPEN) {
      send({ type: 'topup_status', id: invoice.id });
    }
  }, 3000);
}

function stopTopUpPolling() {
  if (topupTimer) clearInterval(topupTimer);
  topupTimer = null;
}

// ——— Ввод ———

function bindUi() {
  on('dev-enter', 'click', () => {
    const name = $('dev-name').value.trim();
    if (!name) {
      toast('Введите имя');
      return;
    }
    localStorage.setItem('poker:devName', name);
    send({ type: 'auth', name, devId: deviceId() });
  });

  on('create-btn', 'click', () => {
    // Настройки стола игрок задаёт в долларах, сервер считает в центах.
    const common = {
      game: state.game,
      buyIn: toCents($('set-buyin').value),
      turnSeconds: Number($('set-turn').value),
      isPublic: $('set-public').checked,
    };
    const settings = state.game === 'blackjack'
      ? { ...common, minBet: toCents($('set-minbet').value), maxBet: toCents($('set-maxbet').value) }
      : {
        ...common,
        smallBlind: toCents($('set-sb').value),
        bigBlind: toCents($('set-bb').value),
        maxPlayers: Number($('set-seats').value),
      };
    send({ type: 'create_room', settings });
  });

  on('join-code', 'input', (event) => {
    event.target.value = normalizeCode(event.target.value);
  });
  on('join-btn', 'click', () => {
    const code = normalizeCode($('join-code').value);
    if (code.length !== 5) {
      toast('Код состоит из пяти символов');
      return;
    }
    send({ type: 'join_room', code });
  });

  // Нижняя навигация
  for (const button of document.querySelectorAll('.nav-btn')) {
    button.addEventListener('click', () => {
      haptic('light');
      showTab(button.dataset.tab);
    });
  }

  // Кнопки денег и плитки главной
  on('btn-topup', 'click', () => {
    if (togglePanel('topup-card')) renderTopUp();
  });
  on('btn-payout', 'click', () => {
    if (togglePanel('payout-card')) renderPayout();
  });
  on('tile-friends', 'click', inviteFriends);
  on('tile-leaders', 'click', () => {
    if (togglePanel('leaders-card')) {
      $('tile-leaders').classList.add('is-active');
      send({ type: 'leaders' });
    }
  });
  on('tile-promo', 'click', () => {
    if (togglePanel('promo-card')) {
      $('tile-promo').classList.add('is-active');
      $('promo-code').focus();
    }
  });
  on('promo-send', 'click', redeemPromo);
  on('promo-code', 'keydown', (event) => {
    if (event.key === 'Enter') redeemPromo();
  });

  // «Помощь» собирает всё справочное: правила, историю операций, поддержку.
  const openHelp = () => {
    if (togglePanel('help-card')) $('help-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  on('help-link', 'click', openHelp);
  on('btn-menu', 'click', openHelp);
  on('help-support', 'click', () => openExternal(state.links.support));
  on('help-history', 'click', () => {
    if (togglePanel('history-card')) send({ type: 'history' });
  });
  on('help-rules', 'click', () => {
    showTab('games');
    const rules = $('rules-card');
    rules.open = true;
    rules.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  on('other-games', 'click', () => openExternal(state.links.community));
  on('leaders-refresh', 'click', () => send({ type: 'leaders' }));
  on('history-refresh', 'click', () => send({ type: 'history' }));

  on('payout-amount', 'input', renderPayoutControls);
  on('payout-send', 'click', createPayout);

  on('topup-amount', 'input', renderTopUp);
  on('topup-create', 'click', createTopUp);
  on('topup-pay', 'click', () => {
    const invoice = state.topup.invoice;
    if (invoice) openPayLink(invoice.url || invoice.fallbackUrl);
  });
  on('topup-check', 'click', () => {
    const invoice = state.topup.invoice;
    if (invoice) send({ type: 'topup_status', id: invoice.id });
  });
  on('topup-cancel', 'click', () => {
    stopTopUpPolling();
    state.topup.invoice = null;
    renderTopUpInvoice();
  });

  on('rooms-refresh', 'click', () => send({ type: 'list_rooms' }));
  on('rooms-refresh-games', 'click', () => send({ type: 'list_rooms' }));
  on('admin-refresh', 'click', () => send({ type: 'admin_accounts' }));
  on('admin-give', 'click', () => adminGrant('add', 1));
  on('admin-take', 'click', () => adminGrant('add', -1));
  on('admin-set', 'click', () => adminGrant('set'));
  on('btn-my-id', 'click', () => {
    if (!state.user) return;
    if (navigator.clipboard) navigator.clipboard.writeText(state.user.id).catch(() => {});
    toast(`ID ${state.user.id} скопирован`);
  });

  on('chips-close', 'click', closeChipsSheet);
  on('chips-sheet', 'click', (event) => {
    if (event.target === $('chips-sheet')) closeChipsSheet();
  });
  document.querySelectorAll('[data-chips]').forEach((button) => {
    button.addEventListener('click', () => grantChips(button.dataset.chips, 'add'));
  });
  on('chips-give', 'click', () => grantChips($('chips-amount').value, 'add'));
  on('chips-take', 'click', () => grantChips(-Math.abs(Number($('chips-amount').value) || 0), 'add'));
  on('chips-set', 'click', () => grantChips($('chips-amount').value, 'set'));

  on('btn-leave', 'click', leaveRoom);
  on('btn-code', 'click', copyCode);
  on('btn-invite', 'click', invite);
  on('btn-log', 'click', () => {
    $('log-panel').classList.remove('hidden');
    state.unread = 0;
    renderUnread();
  });
  on('btn-close', 'click', leaveRoom);
  on('btn-log-close', 'click', () => $('log-panel').classList.add('hidden'));

  on('btn-start', 'click', () => send({ type: 'start' }));
  on('btn-sit', 'click', () => {
    const free = state.room && state.room.seats.find((s) => s.empty);
    if (free) send({ type: 'sit', seat: free.index });
    else toast('Свободных мест нет');
  });
  on('btn-rebuy', 'click', () => send({ type: 'rebuy' }));

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

  on('bj-hit', 'click', () => act('hit'));
  on('bj-stand', 'click', () => act('stand'));
  on('bj-bet', 'click', () => {
    haptic('success');
    state.bjBetTouched = false;
    send({ type: 'action', action: 'bet', amount: state.bjBet });
    $('bj-bar').classList.add('hidden');
  });
  on('bj-range', 'input', (event) => {
    state.bjBetTouched = true;
    state.bjBet = Number(event.target.value);
    $('bj-bet-value').textContent = money(state.bjBet);
    $('bj-bet').textContent = `Поставить ${money(state.bjBet)}`;
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
      $('bj-bet-value').textContent = money(state.bjBet);
      $('bj-bet').textContent = `Поставить ${money(state.bjBet)}`;
      haptic('light');
    });
  });

  on('btn-fold', 'click', () => act('fold'));
  on('btn-check', 'click', () => act('check'));
  on('btn-call', 'click', () => act('call'));
  on('btn-raise', 'click', () => {
    haptic('light');
    const row = $('raise-row');
    if (row.classList.contains('hidden')) openRaisePanel();
    else closeRaisePanel();
  });
  on('raise-cancel', 'click', closeRaisePanel);
  on('raise-confirm', 'click', () => act('raise', state.raiseTo));
  on('btn-allin', 'click', () => {
    const legal = state.room && state.room.you.legal;
    if (legal && legal.canRaise) act('raise', legal.maxRaiseTo);
  });

  on('raise-range', 'input', (event) => {
    state.raiseTouched = true;
    state.raiseTo = Number(event.target.value);
    renderRaiseValue(state.room && state.room.you.legal);
  });

  document.querySelectorAll('[data-preset]').forEach((button) => {
    button.addEventListener('click', () => applyPreset(button.dataset.preset));
  });

  on('chat-form', 'submit', (event) => {
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
  $('chips-stack').textContent = `ID ${seat.userId} · в стеке за столом ${money(seat.stack)}`;
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
  const value = toCents(amount);
  if (value === null || !Number.isFinite(value) || (mode === 'add' && value === 0)) {
    toast('Введите сумму в долларах');
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
  else if (preset === 'double') value = myBet + legal.callAmount + potAfterCall * 2;
  else value = myBet + legal.callAmount + potAfterCall;

  state.raiseTouched = true;
  state.raiseTo = clamp(value, legal.minRaiseTo, legal.maxRaiseTo);
  $('raise-range').value = String(state.raiseTo);
  renderRaiseValue(legal);
  for (const button of document.querySelectorAll('[data-preset]')) {
    button.classList.toggle('is-active', button.dataset.preset === preset);
  }
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

// Приглашение в приложение вообще, без привязки к столу: это лобби, а не стол.
function inviteFriends() {
  const { botUsername, appShortName } = state.config;
  if (tg && botUsername && appShortName) {
    const link = `https://t.me/${botUsername}/${appShortName}`;
    const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent('Заходи играть — покер и блекджек прямо в Telegram')}`;
    tg.openTelegramLink(share);
    return;
  }
  if (navigator.clipboard) navigator.clipboard.writeText(location.origin).catch(() => {});
  toast('Ссылка скопирована');
}

function invite() {
  const room = state.room;
  if (!room) return;
  const { botUsername, appShortName } = state.config;

  if (tg && botUsername && appShortName) {
    const link = `https://t.me/${botUsername}/${appShortName}?startapp=${room.code}`;
    const share = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent('Заходи за стол — покер и блекджек в Telegram')}`;
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
