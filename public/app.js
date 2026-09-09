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
  raiseOpen: false,
  raiseContext: null,
  botSeat: null,
  reconnectDelay: 500,
  chat: [],
  rooms: [],
  balance: 0,
  isAdmin: false,
  chipsSeat: null, // индекс места, которому выдаём фишки
  game: 'holdem', // выбранная в лобби игра
  shownCards: new Map(), // карта -> когда её начали раздавать (см. dealDelay)
  shownHand: null,
  winCards: new Set(), // карты выигравшей комбинации — для подсветки
  // Что стол показывал в прошлый раз: по разнице считаем, чему лететь.
  fx: { hand: null, bets: new Map(), points: new Map(), potPoint: null, winKey: null, seated: new Set() },
  bjBet: 0,
  bjBetTouched: false,
  buyIn: { open: false, mode: 'sit', seat: null, amount: 0, touched: false },
  bj: { view: null, bet: 500, open: false, dealerShown: null, revealing: false, timers: [], shownBalance: null, typing: false, typed: '' },
  rl: { open: false, info: null, amount: 1000, bets: new Map(), spinning: false, angle: 0, shownBalance: null, typing: false, typed: '', raf: null },
  bc: { open: false, info: null, chip: 1000, bets: new Map(), dealing: false, timers: [], shownBalance: null, round: null, pendingHistory: null },
  mn: { open: false, info: null, amount: 100, mines: 3, busy: false, reveal: null, shownBalance: null },
  ag: { game:null, info:null, pending:null, animating:false, token:0, raf:null, options:{ plinko:{risk:"medium"}, tower:{level:"easy"}, keno:{picks:[]}, dragon:{side:"dragon"} } },
  cr: { open:false, info:null, busy:false, receivedAt:0, raf:null },
  hl: { open: false, info: null, amount: 100, busy: false, animating: false, token: 0 },
  nv: { open: false, info: null, amount: 100, target: 75, mode: 'under', busy: false, round: null, shownBalance: null, timer: null },
  unread: 0,
  tab: 'home', // главная | игры | турниры | бонусы | профиль
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
  // Логический холст. Пропорция 4:5 — та же, что у вырезки ассета
  // img/table-purple.webp (1088×1360), поэтому картинка ложится без искажений.
  width: 400,
  height: 500,
  // Центр игровой зоны (ряд общих карт): сюда «смотрят» карты и ставки.
  focusX: 0.49955,
  focusY: 0.4801,
};

// ВСЯ геометрия ниже снята с ассета измерением, а не подобрана:
//   кружки мест   — подбор кольца, покрытие 97%
//   слоты борда   — 5 × 35.9×52.7, y 221.1..273.8, шаг 39.3
//   плашка банка  — x 155.1..244.9, y 281.6..328.9
// Ассет — источник истины: ничего из этого в CSS не перерисовывается.
const SEAT_CIRCLES = [
  // at — центр неонового кольца места, rin/rout — внутренний и внешний
  // радиус его светящейся линии (подбор окружности по пикселям ассета
  // table-purple.webp, полуширина по полувысоте профиля яркости).
  // ring — квадратная вырезка кольца с альфой (img/ring-N.png): размер и
  // сдвиг её центра от центра кольца. badge — вырезка медальона масти
  // (img/badge-N.png): размер и смещение центра от центра кольца (кромка
  // медальона найдена по контрасту, r ≈ 33.75 px ассета, у верхнего 37.25).
  // Всё в логических px холста 400×500 (k = 400/1088).
  { at: [0.49961, 0.87965], rin: 24.63, rout: 25.92, ring: { size: 58.82, dx: 0.15, dy: -0.12 }, badge: { w: 27.94, h: 27.94, dx: 0.52, dy: -25.12 } },  // 0
  { at: [0.21737, 0.76519], rin: 23.99, rout: 25.37, ring: { size: 57.35, dx: -0.18, dy: 0.12 }, badge: { w: 27.94, h: 27.94, dx: -3.12, dy: -26.71 } },  // 1
  { at: [0.11010, 0.52077], rin: 23.9, rout: 25.37, ring: { size: 57.35, dx: 0.08, dy: -0.09 }, badge: { w: 27.94, h: 27.94, dx: 0.08, dy: -26.56 } },  // 2
  { at: [0.21801, 0.25527], rin: 23.35, rout: 25.0, ring: { size: 56.62, dx: -0.07, dy: -0.06 }, badge: { w: 27.94, h: 27.94, dx: -3.38, dy: -29.47 } },  // 3
  { at: [0.49961, 0.14624], rin: 23.62, rout: 24.91, ring: { size: 56.62, dx: 0.15, dy: 0.04 }, badge: { w: 30.88, h: 30.88, dx: 0.15, dy: -34.52 } },  // 4
  { at: [0.78086, 0.25526], rin: 23.62, rout: 24.82, ring: { size: 56.62, dx: 0.15, dy: -0.06 }, badge: { w: 27.94, h: 27.94, dx: 3.83, dy: -29.47 } },  // 5
  { at: [0.88876, 0.52099], rin: 23.9, rout: 25.18, ring: { size: 57.35, dx: 0.01, dy: 0.17 }, badge: { w: 27.94, h: 27.94, dx: 0.38, dy: -26.67 } },  // 6
  { at: [0.78176, 0.76394], rin: 24.91, rout: 25.74, ring: { size: 58.09, dx: 0.16, dy: 0.01 }, badge: { w: 27.94, h: 27.94, dx: 3.1, dy: -26.09 } },  // 7
];

// Смещения в логических пикселях от центра кружка. Карты — на внутренней
// стороне места (к сукну), ставка — дальше, на стороне банка. Значения
// заданы явно, по эталонным макетам, без перебора координат.
const SEAT_LAYOUT = [
  // Ставка стоит на луче от кружка к банку (200, 305) — читается как
  // «фишки сдвинуты к банку». Расстояние подобрано так, чтобы плашка
  // ставки не задевала ни свои карты, ни плашки соседей.
  // У героя своего места сбоку нет: снизу справа и слева сидят соперники,
  // поэтому его фишки идут строго вверх по его оси, между картами и банком.
  // bet — якорь блока ставки от центра кружка; side говорит, какой край
  // блока стоит на якоре: у левых мест левый (стопка ближе к игроку, сумма
  // дальше к банку), у правых — правый и блок зеркален, у верхних/героя —
  // центр. Ставка всегда между игроком и банком, вплотную к своему месту.
  { cards: [0, -62], bet: [0, -104], side: 'center' },  // 0 герой: над картами, к банку (слева и справа стоят ставки соседей)
  { cards: [35, -6], bet: [12, -44], side: 'left' },    // 1 низ слева: выше-правее, не доходя до карт героя
  { cards: [35, -4], bet: [31, 32], side: 'left' },     // 2 середина слева: правее, внутрь
  { cards: [34, 0], bet: [42, 42], side: 'left' },      // 3 верх слева: ниже, внутрь
  { cards: [0, 16], bet: [0, 72], side: 'center' },     // 4 верх: ниже плашки, к центру
  { cards: [-34, 0], bet: [-42, 42], side: 'right' },   // 5 верх справа: ниже, внутрь
  { cards: [-35, -4], bet: [-40, 35], side: 'right' },  // 6 середина справа: левее, внутрь
  { cards: [-35, -6], bet: [-12, -44], side: 'right' }, // 7 низ справа: выше-левее, не доходя до карт героя
];

// Полный размер фишки: диаметр и высота цилиндра (см. .chip в styles.css).
const CHIP_W = 18;

// Какие кружки заняты при каком числе игроков. Новых координат не выдумываем:
// берём подмножество тех же восьми (см. пункт 34 задания).
const SEAT_SETS = {
  2: [0, 4],
  3: [0, 3, 5],
  4: [0, 3, 4, 5],
  5: [0, 1, 3, 5, 7],
  6: [0, 1, 3, 4, 5, 7],
  7: [0, 1, 2, 3, 5, 6, 7],
  8: [0, 1, 2, 3, 4, 5, 6, 7],
};

function seatAnchor(index, count) {
  if (crocActive()) return crocAnchor(index, count);
  const set = SEAT_SETS[count] || SEAT_SETS[8];
  const at = set[index % set.length];
  const circle = SEAT_CIRCLES[at];
  const layout = SEAT_LAYOUT[at];
  return {
    at,
    seat: circle.at,
    avatar: circle.rin * 2,
    cards: layout.cards,
    bet: layout.bet,
    side: layout.side,
    // Центр стопки в долях холста — откуда фишки уезжают в банк. Стопка
    // стоит у якорного края блока, поэтому сдвиг на полфишки от якоря.
    betFrac: [
      circle.at[0] + (layout.bet[0] + (layout.side === 'left' ? CHIP_W / 2 : layout.side === 'right' ? -CHIP_W / 2 : -CHIP_W * 0.7)) / TABLE.width,
      circle.at[1] + layout.bet[1] / TABLE.height,
    ],
  };
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

// Компактная запись комбинации для ярлыка героя: «Пара K», «Тройка 7»,
// «Стрит», «Флеш». Сервер уже даёт короткие ранги, надо убрать хвосты
// «до X» и показать десятку как 10, а не буквой T.
function shortHand(text) {
  if (!text) return '';
  let t = String(text)
    .replace(/\bT\b/g, '10')
    .replace(/^Стрит-флеш до .+$/, 'Стрит-флеш')
    .replace(/^Стрит до .+$/, 'Стрит')
    .replace(/^Флеш до .+$/, 'Флеш')
    .replace(/^Фулл-хаус (\S+) на (\S+)$/, 'Фулл-хаус $1/$2');
  return t;
}

// Фишки по номиналу (пункт 9 задания). Цвет определяется номиналом, а не
// случайно; стопка — компактное представление суммы, точное значение всегда
// написано текстом рядом.
const CHIP_DENOMS = [
  { value: 2500, cls: 'gold' },
  { value: 1000, cls: 'plum' },
  { value: 500, cls: 'black' },
  { value: 100, cls: 'green' },
  { value: 50, cls: 'blue' },
  { value: 10, cls: 'red' },
];

// Стопка — компактное представление, точная сумма всегда написана рядом.
// Обычно 1–3 фишки, максимум четыре, от старшего номинала к младшему.
function chipStack(cents) {
  const box = document.createElement('span');
  box.className = 'chips';
  let left = Math.max(0, Math.round(Number(cents) || 0));
  const picked = [];
  for (const d of CHIP_DENOMS) {
    while (left >= d.value && picked.length < 4) {
      picked.push(d.cls);
      left -= d.value;
    }
    if (picked.length >= 4) break;
  }
  if (!picked.length) picked.push('red');
  picked.forEach((cls, i) => {
    const c = document.createElement('i');
    c.className = `chip chip-${cls}`;
    c.style.setProperty('--i', String(i));
    box.appendChild(c);
  });
  return box;
}

// Открываем сборку стопки для отладочных замеров раскладки.
if (typeof window !== 'undefined') { window.__chipStack = chipStack; window.__state = state; }

// Короткая запись для фишки на сукне: восемь фишек с полными суммами на
// сукно не помещаются, поэтому от сотни долларов показываем «$1.2k».
// Везде, где место есть (баланс, банк, кнопки), остаётся полная запись.
function shortMoney(cents) {
  const value = Math.abs(Math.round(Number(cents) || 0));
  if (value < 10000) return money(cents);          // до $100.00 — как есть
  const sign = cents < 0 ? '-' : '';
  const dollars = value / 100;
  if (dollars < 1000) return `${sign}$${Math.round(dollars)}`;
  const k = dollars / 1000;
  return `${sign}$${k < 10 ? k.toFixed(1) : Math.round(k)}k`;
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
    if (tg.BackButton) tg.BackButton.onClick(() => (state.ag.game ? closeArcade() : state.cr.open ? closeCrash() : state.hl.open ? closeHilo() : state.nv.open ? closeNvuti() : state.mn.open ? closeMines() : state.bc.open ? closeBaccarat() : state.rl.open ? closeRoulette() : state.bj.open ? closeBlackjack() : leaveRoom()));
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
    if(state.ag.game==='darts')DartsGame.stop();
    if (state.hl.open) renderHilo();
    if (state.ag.game) renderArcade();
    if (state.cr.open) renderCrash();
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
      if (state.hl.open) send({ type: 'hl_open' });
      if (state.cr.open) send({type:'cr_open'});
      if (state.ag.game) agOpenRequest();
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
    case 'bj':
      onBlackjackState(message);
      break;
    case 'rl':
      onRouletteState(message);
      break;
    case 'bc':
      onBaccaratState(message);
      break;
    case 'ag':
      onArcadeState(message);
      break;
    case 'cr':
      onCrashState(message);
      break;
    case 'hl':
      onHiloState(message);
      break;
    case 'mn':
      onMinesState(message);
      break;
    case 'nv':
      onNvutiState(message);
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
      if(state.ag.game) { state.ag.pending=null; renderArcade(); }
      state.cr.busy = false;
      if(state.cr.open) renderCrash();
      state.hl.busy = false;
      if (state.hl.open) renderHilo();
      state.mn.busy = false;
      if (state.mn.open) renderMines();
      state.nv.busy = false;
      if (state.nv.open) renderNvuti();
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
  stopArcade();
  if(state.cr.open) send({type:'cr_close'});
  state.cr.open=false; cancelAnimationFrame(state.cr.raf);
  $('screen-cr').classList.add('hidden');
  state.hl.open = false;
  $('screen-hl').classList.add('hidden');
  $('bot-sheet').classList.add('hidden');
  closeRaisePanel();
  $('screen-table').classList.add('hidden');
  $('screen-bj').classList.add('hidden');
  $('screen-rl').classList.add('hidden');
  $('screen-bc').classList.add('hidden');
  $('screen-mn').classList.add('hidden');
  $('screen-nv').classList.add('hidden');
  state.bj.open = false;
  state.rl.open = false;
  state.bc.open = false;
  state.mn.open = false;
  state.nv.open = false;
  $('screen-lobby').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.hide();
  startRoomsPolling();
}

// Стол ЗАФИКСИРОВАН: один масштаб и одно положение на все состояния —
// пустой стол, посадка, раздача, вскрытие, победитель. Масштаб считается
// только от размеров окна (ширина, высота), а не от того, что сейчас
// показано под столом: панель действий и шапка лежат ПОВЕРХ фона и на
// область стола не влияют. Ни посадка, ни начало раздачи стол не двигают.
const STAGE = {
  sidePad: 10,      // поля слева и справа от холста
  panelReserve: 150, // место под панель действий, учитывается всегда
  topGap: 6,
};

function fitTable() {
  syncCrocTheme();
  if (amethystActive()) { fitAmethyst(); return; }
  const viewport = $('table-viewport');
  const canvas = $('table-canvas');
  if (!viewport || !canvas) return;

  const box = viewport.getBoundingClientRect();
  if (box.width < 2 || box.height < 2) return; // экран стола ещё скрыт

  const scale = Math.min(
    Math.max(box.width - STAGE.sidePad * 2, 1) / TABLE.width,
    Math.max(box.height - STAGE.topGap - STAGE.panelReserve, 1) / TABLE.height,
  );
  const tableH = TABLE.height * scale;
  // Стол стоит в верхней части свободной зоны между шапкой и резервом
  // панели; зона не зависит от состояния, поэтому и стол не двигается.
  const free = box.height - STAGE.panelReserve - tableH;
  const top = STAGE.topGap + Math.max(0, Math.min(free - STAGE.topGap, free * 0.42));
  canvas.style.transform = `translate(-50%, 0) scale(${scale})`;
  canvas.style.top = `${top.toFixed(1)}px`;
  document.documentElement.style.setProperty('--table-px', `${Math.round(TABLE.width * scale)}px`);
  document.documentElement.style.setProperty('--table-scale', String(scale));
}

function watchTableSize() {
  const viewport = $('table-viewport');
  if (!viewport) return;
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(fitTable).observe(viewport);
  }
  window.addEventListener('resize', fitTable);
  window.addEventListener('resize', fitLobby);
  window.addEventListener('resize', fitBlackjack);
  window.addEventListener('resize', fitRoulette);
  window.addEventListener('resize', fitBaccarat);
  window.addEventListener('orientationchange', fitTable);
}

function showTable() {
  $('bot-sheet').classList.add('hidden');
  closeRaisePanel();
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.remove('hidden');
  // Новый стол — новая история анимаций: иначе чужие ставки прилетят
  // фишками в первый же кадр.
  state.fx.hand = null;
  state.fx.winKey = null;
  state.fx.potPoint = null;
  state.fx.bets.clear();
  state.fx.seated.clear();
  state.shownCards.clear();
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  closeChipsSheet();
  // Пока экран был скрыт, у области стола не было размеров — считаем сейчас.
  fitTable();
  requestAnimationFrame(fitTable);
}

// ——— Блекджек против дилера ———
// Экран собран по макету на холсте 390×653; холст масштабируется так,
// чтобы закрыть окно целиком (cover), лишнее по краям обрезается.

const BJ_PRESETS = [500, 1000, 2500, 5000, 10000];
const BJ_SUITS = { s: '♠', h: '♥', d: '♦', c: '♣' };

function fitBlackjack() {
  const screen = $('screen-bj');
  if (!screen || screen.classList.contains('hidden')) return;
  const w = screen.clientWidth || window.innerWidth;
  const scale = w / 390;
  $('bj-canvas').style.setProperty('--bj', scale.toFixed(4));
}

function openBlackjack() {
  state.bj.open = true;
  state.bj.dealerShown = null;
  state.bj.shownBalance = null;
  bjShowBalance(state.balance, true);
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.add('hidden');
  $('screen-bj').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  fitBlackjack();
  requestAnimationFrame(fitBlackjack);
  send({ type: 'bj_open' });
  if (state.bj.view) renderBlackjack();
}

function closeBlackjack() {
  closeBjKeypad(false);
  state.bj.open = false;
  $('screen-bj').classList.add('hidden');
  showLobby();
}

function bjCard(code) {
  const node = document.createElement('div');
  if (code === '??') {
    node.className = 'bj-card back';
    node.innerHTML = '<span class="bj-suit">♠</span>';
    return node;
  }
  const rank = code[0] === 'T' ? '10' : code[0];
  const suitChar = code[1];
  const suit = BJ_SUITS[suitChar] || '♠';
  node.className = `bj-card${suitChar === 'h' || suitChar === 'd' ? ' red' : ''}`;
  node.innerHTML = `<span class="bj-rank">${rank}</span><span class="bj-suit-sm">${suit}</span><span class="bj-suit">${suit}</span>`;
  return node;
}

function bjBetRange() {
  const view = state.bj.view;
  const min = view ? view.minBet : 100;
  const max = Math.min(view ? view.maxBet : 10000000, Math.max(min, state.balance));
  return { min, max };
}

// Шаг −/+ всегда один доллар.
function stepBjBet(direction) {
  const view = state.bj.view;
  if (view && view.phase === 'play') return;
  const { min, max } = bjBetRange();
  state.bj.bet = clamp(state.bj.bet + direction * 100, min, max);
  haptic('light');
  renderBlackjack();
}

// Пресеты складываются: $5, потом $10 — получается $15.
function addBjBet(value) {
  const view = state.bj.view;
  if (view && view.phase === 'play') return;
  const { min, max } = bjBetRange();
  state.bj.bet = clamp(state.bj.bet + value, min, max);
  haptic('light');
  renderBlackjack();
}

// ——— Своя панель ввода суммы ———
function openBjKeypad() {
  const view = state.bj.view;
  if (view && view.phase === 'play') return;
  state.bj.typing = true;
  state.bj.typed = '';
  $('bj-keypad').classList.remove('hidden');
  document.querySelector('.bj-bet').classList.add('is-typing');
  renderBlackjack();
}

function bjKey(key) {
  if (!state.bj.typing) return;
  haptic('light');
  if (key === 'ok') { closeBjKeypad(true); return; }
  let typed = state.bj.typed;
  if (key === 'back') typed = typed.slice(0, -1);
  else if (key === '.') { if (!typed.includes('.')) typed = (typed || '0') + '.'; }
  else {
    const [whole = '', frac] = typed.split('.');
    if (frac !== undefined) { if (frac.length >= 2) return; typed += key; }
    else { if (whole.length >= 5) return; typed = whole === '0' ? key : whole + key; }
  }
  state.bj.typed = typed;
  renderBlackjack();
}

function closeBjKeypad(apply) {
  if (!state.bj.typing) return;
  if (apply && state.bj.typed) {
    const parsed = Math.round(Number(state.bj.typed) * 100);
    const { min, max } = bjBetRange();
    if (Number.isFinite(parsed) && parsed > 0) state.bj.bet = clamp(parsed, min, max);
  }
  state.bj.typing = false;
  state.bj.typed = '';
  $('bj-keypad').classList.add('hidden');
  document.querySelector('.bj-bet').classList.remove('is-typing');
  renderBlackjack();
}

// Новое состояние от сервера. Карты дилера открываем по одной: сначала
// переворот закрытой, потом каждая добранная с паузой — как за живым
// столом, а не всё сразу. Итог и баланс показываем после последней.
function onBlackjackState(message) {
  const prev = state.bj.view;
  state.bj.view = message;
  if (message.phase !== 'bet') state.bj.bet = message.bet;
  state.balance = message.balance;
  renderAccount();

  const bj = state.bj;
  bj.timers.forEach(clearTimeout);
  bj.timers = [];
  bj.revealing = false;

  const target = message.dealer.cards;
  const shown = bj.dealerShown || [];
  const needsReveal = message.phase === 'done' && prev && prev.phase === 'play'
    && (shown.length < target.length || shown.some((c, i) => c !== target[i]));
  if (needsReveal) {
    bj.revealing = true;
    // Шаг 1: переворачиваем закрытую карту, дальше — по одной добранной.
    const steps = [];
    steps.push(target.slice(0, Math.max(2, shown.length)));
    for (let n = steps[0].length + 1; n <= target.length; n++) steps.push(target.slice(0, n));
    let delay = 450;
    steps.forEach((cards, i) => {
      bj.timers.push(setTimeout(() => {
        bj.dealerShown = cards;
        if (i === steps.length - 1) bj.revealing = false;
        renderBlackjack();
      }, delay));
      delay += 700;
    });
    // Пока карты не открыты, ставка уже списана, а выигрыш ещё не пришёл.
    renderBlackjack();
    return;
  }
  bj.dealerShown = target.slice();
  if (message.phase === 'bet') bj.dealerShown = [];
  renderBlackjack();
}

// Сумма руки по кодам карт — для плашки дилера во время открытия.
function bjTotal(cards) {
  let total = 0;
  let aces = 0;
  for (const code of cards) {
    if (code === '??') continue;
    const r = code[0];
    if (r === 'A') { total += 11; aces += 1; } else if ('TJQK'.includes(r)) total += 10; else total += Number(r);
  }
  while (total > 21 && aces > 0) { total -= 10; aces -= 1; }
  return total;
}

// Баланс в углу перелистывается к новому значению.
function bjShowBalance(target, immediate = false) {
  const box = $('bj-balance');
  const out = $('bj-balance-value');
  const from = state.bj.shownBalance === null ? target : state.bj.shownBalance;
  state.bj.shownBalance = target;
  if (immediate || from === target || reducedMotion()) {
    out.textContent = money(target);
    return;
  }
  box.classList.remove('is-up', 'is-down');
  box.classList.add(target > from ? 'is-up' : 'is-down');
  const start = performance.now();
  const duration = 750;
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    out.textContent = money(Math.round(from + (target - from) * eased));
    if (t < 1) requestAnimationFrame(tick);
    else setTimeout(() => box.classList.remove('is-up', 'is-down'), 900);
  };
  requestAnimationFrame(tick);
}

// Добавляем только новые карты: старые не перерисовываем и не анимируем заново.
function bjSync(container, cards, flipFirstHidden = false) {
  const existing = Array.from(container.children);
  const samePrefix = existing.length <= cards.length
    && existing.every((node, i) => node.dataset.code === cards[i] || (node.dataset.code === '??' && flipFirstHidden));
  if (!samePrefix) container.innerHTML = '';
  const nodes = Array.from(container.children);
  cards.forEach((code, i) => {
    const node = nodes[i];
    if (node && node.dataset.code === code) return;
    const card = bjCard(code);
    card.dataset.code = code;
    if (node) {
      card.classList.add('flip-in');
      node.replaceWith(card);
    } else {
      card.style.animationDelay = `${(i - nodes.length) * 90}ms`;
      container.appendChild(card);
    }
  });
  container.classList.toggle('is-many', cards.length > 2);
}

function renderBlackjack() {
  const view = state.bj.view;
  if (!view || !state.bj.open) return;
  const phase = view.phase;
  const playing = phase === 'play';
  const done = phase === 'done';

  // Дилер: одна карта открыта, вторая закрыта, пока игрок не закончил;
  // после — карты открываются по одной (state.bj.dealerShown).
  const revealing = state.bj.revealing;
  const dealerCards = state.bj.dealerShown || view.dealer.cards;
  bjSync($('bj-dealer-cards'), dealerCards, true);
  const dealerPill = $('bj-dealer-total');
  dealerPill.classList.toggle('hidden', !dealerCards.length);
  if (dealerCards.length) dealerPill.textContent = String(bjTotal(dealerCards));

  // Руки игрока: обычно одна, после сплита две.
  const hands = $('bj-hands');
  hands.classList.toggle('is-split', view.hands.length > 1);
  if (hands.children.length !== view.hands.length) {
    hands.innerHTML = '';
    view.hands.forEach(() => {
      const node = document.createElement('div');
      node.className = 'bj-hand';
      hands.appendChild(node);
    });
  }
  view.hands.forEach((hand, i) => bjSync(hands.children[i], hand.cards));
  Array.from(hands.children).forEach((node, i) => {
    const hand = view.hands[i];
    if (!hand) return;
    node.classList.toggle('is-active', Boolean(hand.active));
    let tag = node.querySelector('.bj-hand-tag');
    if (view.hands.length > 1) {
      if (!tag) { tag = document.createElement('div'); tag.className = 'bj-hand-tag'; node.appendChild(tag); }
      tag.textContent = `${hand.total}${hand.result ? ' · ' + bjOutcome(hand.result.outcome) : ''}`;
    } else if (tag) tag.remove();
  });
  const active = view.hands[view.active] || view.hands[0];
  const handPill = $('bj-hand-total');
  handPill.classList.toggle('hidden', !active);
  if (active) handPill.textContent = String(active.total);

  // Ставка: во время раздачи заперта, в остальное время — из состояния клиента.
  // Ставка никогда не больше баланса и границ стола — даже если баланс
  // изменился после ввода.
  if (!playing) {
    const range = bjBetRange();
    state.bj.bet = clamp(state.bj.bet, range.min, range.max);
  }
  const bet = $('bj-bet-amount');
  bet.textContent = state.bj.typing ? (state.bj.typed ? `$${state.bj.typed}` : '$') : money(state.bj.bet);
  if (playing && state.bj.typing) closeBjKeypad(false);
  document.querySelector('.bj-bet').classList.toggle('is-locked', playing);
  $('bj-minus').disabled = playing;
  $('bj-plus').disabled = playing;
  const presets = $('bj-presets');
  const { max } = bjBetRange();
  if (!presets.children.length) {
    for (const value of BJ_PRESETS) {
      const button = document.createElement('button');
      button.className = 'bj-preset';
      button.textContent = `$${value / 100}`;
      button.dataset.value = String(value);
      button.addEventListener('click', () => {
        addBjBet(value);
        button.classList.add('is-pressed');
        setTimeout(() => button.classList.remove('is-pressed'), 180);
      });
      presets.appendChild(button);
    }
  }
  for (const button of presets.children) {
    button.disabled = playing || state.bj.bet >= max;
  }

  // Кнопки: во время раздачи — четыре действия, до неё — DEAL, после — NEW HAND.
  const options = view.options || {};
  for (const action of ['hit', 'stand', 'double', 'split']) {
    const button = $(`bj-${action}`);
    button.classList.toggle('hidden', !playing);
    button.disabled = !options[action];
  }
  $('bj-canvas').dataset.phase = phase;
  const deal = $('bj-deal');
  deal.classList.toggle('hidden', phase !== 'bet');
  deal.classList.remove('is-loading');
  const { min } = bjBetRange();
  const short = state.balance < state.bj.bet || state.balance < min;
  deal.disabled = short;
  const sub = $('bj-deal-sub');
  sub.classList.toggle('hidden', phase !== 'bet' || !short);
  sub.textContent = 'Недостаточно средств';
  $('bj-next').classList.toggle('hidden', !done || revealing);

  // Баланс: после ставки сразу, после раздачи — когда дилер открыл карты.
  if (!(done && revealing)) bjShowBalance(view.balance, !done);

  // Итог раздачи — после того, как дилер открыл все карты.
  const result = $('bj-result');
  if (done && view.results && !revealing) {
    const r = view.results;
    result.className = 'bj-result';
    if (r.net > 0) {
      const natural = r.hands.some((h) => h.outcome === 'blackjack');
      result.textContent = `${natural ? 'BLACKJACK!' : 'YOU WIN'} +${money(r.net)}`;
    } else if (r.net === 0) {
      result.textContent = 'PUSH · ставка возвращена';
      result.classList.add('push');
    } else {
      const bust = r.hands.every((h) => h.outcome === 'bust');
      result.textContent = `${bust ? 'BUST' : 'DEALER WINS'} −${money(-r.net)}`;
      result.classList.add('lose');
    }
    result.classList.remove('hidden');
  } else {
    result.classList.add('hidden');
  }
}

function bjOutcome(outcome) {
  return { win: 'WIN', blackjack: 'BLACKJACK', lose: 'LOSE', push: 'PUSH', bust: 'BUST' }[outcome] || '';
}

// ——— Рулетка ———
// Холст 390×653 по макету. Колесо в макете нарисовано в перспективе,
// поэтому вращается только кольцо с числами: слой-эллипс распрямляем по
// Y, поворачиваем и сжимаем обратно. Шарик считаем в «плоских» координатах
// диска и проецируем на эллипс тем же коэффициентом.

// Плоское колесо сверху: единицы макета (941 px ширины), центр (470,512).
// На холсте 390×653 всё умножается на k = 0.41445.
const RL_K = 390 / 941;
const RL_CX = 470 * RL_K;
const RL_CY = (512 - 96) * RL_K;
const RL_ZERO_ANGLE = -90;                 // зеро сверху
const RL_POCKET = 360 / 37;
const RL_ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26];
const RL_RED = new Set([1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]);
const RL_R_TRACK = 270 * RL_K;             // дорожка между кольцом чисел и свечением
const RL_R_POCKET = 174 * RL_K;            // кольцо лунок
const RL_SPIN_MS = 7200;
const RL_PRESETS = [100, 500, 1000, 2500, 10000];

function rlColour(n) {
  return n === 0 ? 'green' : RL_RED.has(n) ? 'red' : 'black';
}

// Колесо — SVG в единицах макета: кольцо чисел r 205..245, лунки r 150..200,
// сердцевина с лучами и втулкой. Вращается группа #rl-rotor.
function buildRouletteWheel() {
  const box = $('rl-wheel');
  if (box.children.length) return;
  const fill = { red: '#b9172c', black: '#14101f', green: '#0f6f47' };
  const deep = { red: '#6d0f1c', black: '#0a0712', green: '#0a4a30' };
  const seg = (r0, r1, a0, a1, colour) => {
    const p = (r, a) => `${(r * Math.cos(a)).toFixed(2)},${(r * Math.sin(a)).toFixed(2)}`;
    return `<path d="M${p(r0, a0)} L${p(r1, a0)} A${r1},${r1} 0 0 1 ${p(r1, a1)} L${p(r0, a1)} A${r0},${r0} 0 0 0 ${p(r0, a0)} Z" fill="${colour}"/>`;
  };
  let rotor = '';
  let labels = '';
  RL_ORDER.forEach((n, i) => {
    const c = RL_ZERO_ANGLE + i * RL_POCKET;
    const a0 = ((c - RL_POCKET / 2) * Math.PI) / 180;
    const a1 = ((c + RL_POCKET / 2) * Math.PI) / 180;
    const col = rlColour(n);
    rotor += seg(205, 245, a0, a1, fill[col]);
    rotor += seg(150, 200, a0, a1, deep[col]);
    const rad = (c * Math.PI) / 180;
    labels += `<text class="num" x="${(225 * Math.cos(rad)).toFixed(2)}" y="${(225 * Math.sin(rad)).toFixed(2)}" text-anchor="middle" dominant-baseline="central" transform="rotate(${(c + 90).toFixed(2)} ${(225 * Math.cos(rad)).toFixed(2)} ${(225 * Math.sin(rad)).toFixed(2)})">${n}</text>`;
  });
  // разделители карманов
  let lines = '';
  for (let i = 0; i < 37; i++) {
    const a = ((RL_ZERO_ANGLE + i * RL_POCKET - RL_POCKET / 2) * Math.PI) / 180;
    lines += `<line x1="${(150 * Math.cos(a)).toFixed(2)}" y1="${(150 * Math.sin(a)).toFixed(2)}" x2="${(245 * Math.cos(a)).toFixed(2)}" y2="${(245 * Math.sin(a)).toFixed(2)}" stroke="rgba(190,150,255,0.55)" stroke-width="1.2"/>`;
  }
  let rays = '';
  for (let i = 0; i < 16; i++) {
    const a = (i * 22.5 * Math.PI) / 180;
    const len = i % 2 ? 95 : 140;
    rays += `<line x1="${(34 * Math.cos(a)).toFixed(2)}" y1="${(34 * Math.sin(a)).toFixed(2)}" x2="${(len * Math.cos(a)).toFixed(2)}" y2="${(len * Math.sin(a)).toFixed(2)}" stroke="rgba(190,150,255,${i % 2 ? 0.16 : 0.3})" stroke-width="${i % 2 ? 1.5 : 2.5}"/>`;
  }
  const pointer = (rot) => `<polygon points="0,-318 -7,-300 7,-300" fill="#cdb0ff" transform="rotate(${rot})"/>`;
  box.innerHTML = `<svg viewBox="-320 -320 640 640" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <filter id="rl-glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>
      <radialGradient id="rl-core" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#1b0d33"/><stop offset="1" stop-color="#0a0514"/></radialGradient>
      <radialGradient id="rl-hub" cx="40%" cy="35%" r="65%"><stop offset="0" stop-color="#b08cff"/><stop offset="0.5" stop-color="#5a2fd0"/><stop offset="1" stop-color="#2a1160"/></radialGradient>
    </defs>
    <circle r="300" fill="none" stroke="#7a3cff" stroke-width="9" opacity="0.9" filter="url(#rl-glow)"/>
    <circle r="300" fill="none" stroke="#b48cff" stroke-width="2.5"/>
    <circle r="270" fill="#0d0718"/>
    <circle r="252" fill="none" stroke="rgba(190,150,255,0.5)" stroke-width="1.5"/>
    ${pointer(0)}${pointer(90)}${pointer(180)}${pointer(270)}
    <g id="rl-rotor">
      <circle r="245" fill="#12091f"/>
      ${rotor}
      <circle r="150" fill="url(#rl-core)"/>
      ${rays}
      <circle r="200" fill="none" stroke="rgba(190,150,255,0.6)" stroke-width="1.5"/>
      <circle r="205" fill="none" stroke="rgba(190,150,255,0.35)" stroke-width="1"/>
      <circle r="150" fill="none" stroke="rgba(190,150,255,0.6)" stroke-width="1.5"/>
      ${lines}
      ${labels}
      <circle r="36" fill="url(#rl-hub)" stroke="#c9adff" stroke-width="2"/>
      <circle r="22" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.5"/>
      <circle r="9" fill="#e6d8ff"/>
    </g>
  </svg>`;
}

// Клетки поля в px холста: зеро, три ряда 1-4-7 / 2-5-8 / 3-6-9, «2 to 1»,
// шесть внешних ставок. Координаты сняты с макета.
function rlCells() {
  const X = (x) => x * RL_K;
  const Y = (y) => (y - 96) * RL_K;
  const cells = [];
  const rows = [833, 898, 963, 1028];
  const col0 = 100;
  const colW = (830 - 100) / 12;
  cells.push({ key: 'straight:0', type: 'straight', value: 0, x: X(35), y: Y(rows[0]), w: X(col0) - X(35), h: Y(rows[3]) - Y(rows[0]), label: '0', cls: 'green' });
  for (let c = 0; c < 12; c++) {
    for (let r = 0; r < 3; r++) {
      const n = 3 * c + (r + 1);
      cells.push({ key: `straight:${n}`, type: 'straight', value: n, x: X(col0 + c * colW), y: Y(rows[r]), w: X(colW), h: Y(rows[r + 1]) - Y(rows[r]), label: String(n), cls: rlColour(n) });
    }
  }
  [1, 2, 3].forEach((column, r) => {
    cells.push({ key: `column:${column}`, type: 'column', value: column, x: X(830), y: Y(rows[r]), w: X(905) - X(830), h: Y(rows[r + 1]) - Y(rows[r]), label: '2 to 1', cls: 'dark small' });
  });
  const outside = [
    ['low', 35, 183, '1 – 18'], ['even', 183, 327, 'Even'], ['red', 327, 470, '<svg class="diamond" viewBox="0 0 22 12"><path d="M11 0 L22 6 L11 12 L0 6 Z" fill="#d9243b"/></svg>'],
    ['black', 470, 613, '<svg class="diamond" viewBox="0 0 22 12"><path d="M11 0.8 L20.5 6 L11 11.2 L1.5 6 Z" fill="#0d0814" stroke="#cbb8f0" stroke-width="1"/></svg>'],
    ['odd', 613, 757, 'Odd'], ['high', 757, 905, '19 – 36'],
  ];
  for (const [type, a, b, label] of outside) {
    cells.push({ key: `${type}:`, type, value: null, x: X(a), y: Y(1043), w: X(b) - X(a), h: Y(1152) - Y(1043), label, cls: 'dark outside' });
  }
  return cells;
}

function fitRoulette() {
  const screen = $('screen-rl');
  if (!screen || screen.classList.contains('hidden')) return;
  const w = screen.clientWidth || window.innerWidth;
  $('rl-canvas').style.setProperty('--bj', (w / 390).toFixed(4));
}

function openRoulette() {
  state.rl.open = true;
  state.rl.shownBalance = null;
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.add('hidden');
  $('screen-bj').classList.add('hidden');
  $('screen-rl').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  fitRoulette();
  requestAnimationFrame(fitRoulette);
  buildRouletteWheel();
  buildRouletteCells();
  send({ type: 'rl_open' });
  renderRoulette();
}

function closeRoulette() {
  closeRlKeypad(false);
  if (state.rl.raf) cancelAnimationFrame(state.rl.raf);
  state.rl.raf = null;
  state.rl.spinning = false;
  state.rl.open = false;
  $('screen-rl').classList.add('hidden');
  showLobby();
}

function buildRouletteCells() {
  const box = $('rl-cells');
  if (box.children.length) return;
  const X = (x) => x * RL_K;
  const Y = (y) => (y - 96) * RL_K;
  for (const [x0, x1, y0, y1] of [[35, 905, 833, 1028], [35, 905, 1043, 1152]]) {
    const frame = document.createElement('div');
    frame.className = 'rl-frame';
    frame.style.cssText = `left:${X(x0).toFixed(2)}px;top:${Y(y0).toFixed(2)}px;width:${(X(x1) - X(x0)).toFixed(2)}px;height:${(Y(y1) - Y(y0)).toFixed(2)}px`;
    box.appendChild(frame);
  }
  for (const cell of rlCells()) {
    const node = document.createElement('div');
    node.className = `rl-cell ${cell.cls}`;
    node.dataset.key = cell.key;
    node.style.left = `${cell.x.toFixed(2)}px`;
    node.style.top = `${cell.y.toFixed(2)}px`;
    node.style.width = `${cell.w.toFixed(2)}px`;
    node.style.height = `${cell.h.toFixed(2)}px`;
    node.innerHTML = `<span class="rl-cell-label">${cell.label}</span>`;
    node.addEventListener('click', () => placeRlBet(cell, node));
    box.appendChild(node);
  }
}

function rlRange() {
  const info = state.rl.info;
  const min = info ? info.minBet : 100;
  const max = Math.min(info ? info.maxBet : 10000000, Math.max(min, state.balance));
  return { min, max };
}

function rlTotal() {
  let total = 0;
  for (const bet of state.rl.bets.values()) total += bet.amount;
  return total;
}

function placeRlBet(cell, node) {
  if (state.rl.spinning) return;
  const { min } = rlRange();
  const amount = Math.max(min, state.rl.amount);
  if (rlTotal() + amount > state.balance) {
    toast('Недостаточно средств');
    haptic('error');
    return;
  }
  const current = state.rl.bets.get(cell.key);
  state.rl.bets.set(cell.key, { type: cell.type, value: cell.value, amount: (current ? current.amount : 0) + amount });
  node.classList.add('is-hit');
  setTimeout(() => node.classList.remove('is-hit'), 160);
  haptic('light');
  renderRoulette();
}

function stepRlAmount(direction) {
  if (state.rl.spinning) return;
  const { min, max } = rlRange();
  state.rl.amount = clamp(state.rl.amount + direction * 100, min, max);
  haptic('light');
  renderRoulette();
}

function addRlAmount(value) {
  if (state.rl.spinning) return;
  const { min, max } = rlRange();
  state.rl.amount = clamp(state.rl.amount + value, min, max);
  haptic('light');
  renderRoulette();
}

function openRlKeypad() {
  if (state.rl.spinning) return;
  state.rl.typing = true;
  state.rl.typed = '';
  $('rl-keypad').classList.remove('hidden');
  document.querySelector('.rl-bet').classList.add('is-typing');
  renderRoulette();
}

function rlKey(key) {
  if (!state.rl.typing) return;
  haptic('light');
  if (key === 'ok') { closeRlKeypad(true); return; }
  let typed = state.rl.typed;
  if (key === 'back') typed = typed.slice(0, -1);
  else if (key === '.') { if (!typed.includes('.')) typed = (typed || '0') + '.'; }
  else {
    const [whole = '', frac] = typed.split('.');
    if (frac !== undefined) { if (frac.length >= 2) return; typed += key; }
    else { if (whole.length >= 5) return; typed = whole === '0' ? key : whole + key; }
  }
  state.rl.typed = typed;
  renderRoulette();
}

function closeRlKeypad(apply) {
  if (!state.rl.typing) return;
  if (apply && state.rl.typed) {
    const parsed = Math.round(Number(state.rl.typed) * 100);
    const { min, max } = rlRange();
    if (Number.isFinite(parsed) && parsed > 0) state.rl.amount = clamp(parsed, min, max);
  }
  state.rl.typing = false;
  state.rl.typed = '';
  $('rl-keypad').classList.add('hidden');
  document.querySelector('.rl-bet').classList.remove('is-typing');
  renderRoulette();
}

function rlShowBalance(target, immediate = false) {
  const box = $('rl-balance');
  const out = $('rl-balance-value');
  const from = state.rl.shownBalance === null ? target : state.rl.shownBalance;
  state.rl.shownBalance = target;
  if (immediate || from === target || reducedMotion()) { out.textContent = money(target); return; }
  box.classList.remove('is-up', 'is-down');
  box.classList.add(target > from ? 'is-up' : 'is-down');
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / 750);
    const eased = 1 - Math.pow(1 - t, 3);
    out.textContent = money(Math.round(from + (target - from) * eased));
    if (t < 1) requestAnimationFrame(tick);
    else setTimeout(() => box.classList.remove('is-up', 'is-down'), 900);
  };
  requestAnimationFrame(tick);
}

function onRouletteState(message) {
  state.rl.info = message;
  state.balance = message.balance;
  renderAccount();
  if (message.spin) {
    startRouletteSpin(message.spin);
    return;
  }
  rlShowBalance(message.balance, true);
  renderRoulette();
}

// Угол кармана с числом n на распрямлённом диске (0 — вверх, по часовой).
function rlPocketAngle(n) {
  const index = RL_ORDER.indexOf(n);
  return RL_ZERO_ANGLE + index * RL_POCKET;
}

function rlBallAt(angleDeg, r) {
  const a = (angleDeg * Math.PI) / 180;
  const ball = $('rl-ball');
  ball.style.left = `${(RL_CX + r * Math.cos(a)).toFixed(2)}px`;
  ball.style.top = `${(RL_CY + r * Math.sin(a)).toFixed(2)}px`;
}

// Запуск: число уже известно. Колесо крутится по часовой и тормозит,
// шарик бежит против часовой по внешней дорожке, затем сваливается в
// карман и дальше едет вместе с колесом.
function startRouletteSpin(spin) {
  const rl = state.rl;
  if (rl.raf) cancelAnimationFrame(rl.raf);
  rl.spinning = true;
  rl.result = null;
  $('rl-canvas').classList.add('is-spinning');
  $('rl-result').classList.add('hidden');
  // Баланс: ставки уже списаны — показываем сразу, выигрыш придёт после остановки.
  rlShowBalance(state.balance - (spin.payout || 0));
  renderRoulette();

  const startAngle = rl.angle;
  const wheelTurns = 4 + Math.random() * 1.5;
  const endAngle = startAngle + wheelTurns * 360 + Math.random() * 360;
  const ballTurns = 7 + Math.random() * 2;
  const ballStart = endAngle + rlPocketAngle(spin.number) + ballTurns * 360; // против часовой → угол убывает
  const t0 = performance.now();
  const ball = $('rl-ball');
  ball.classList.remove('hidden');
  const ease = (t) => 1 - Math.pow(1 - t, 3);

  const frame = (now) => {
    const t = Math.min(1, (now - t0) / RL_SPIN_MS);
    const wheel = startAngle + (endAngle - startAngle) * ease(t);
    const rotor = document.getElementById('rl-rotor');
    if (rotor) rotor.setAttribute('transform', `rotate(${wheel.toFixed(2)})`);
    // Свободный бег шарика: тормозит раньше колеса.
    const tb = Math.min(1, t / 0.86);
    const free = ballStart - (ballStart - (endAngle + rlPocketAngle(spin.number))) * ease(tb);
    const locked = wheel + rlPocketAngle(spin.number);
    let angle = free;
    let r = RL_R_TRACK;
    if (t >= 0.72) {
      const k = Math.min(1, (t - 0.72) / 0.14);
      angle = free * (1 - k) + locked * k;
      const drop = k < 0.7 ? k / 0.7 : 1 - 0.12 * Math.sin(((k - 0.7) / 0.3) * Math.PI); // маленький подскок
      r = RL_R_TRACK + (RL_R_POCKET - RL_R_TRACK) * drop;
    }
    rlBallAt(angle, r);
    if (t < 1) {
      rl.raf = requestAnimationFrame(frame);
      return;
    }
    rl.raf = null;
    rl.angle = endAngle % 360;
    finishRouletteSpin(spin);
  };
  rl.raf = requestAnimationFrame(frame);
}

function finishRouletteSpin(spin) {
  const rl = state.rl;
  rl.spinning = false;
  rl.result = spin;
  $('rl-canvas').classList.remove('is-spinning');
  haptic(spin.net > 0 ? 'success' : 'light');
  const result = $('rl-result');
  const colour = spin.colour;
  const label = spin.net > 0 ? `WIN +${money(spin.net)}` : spin.net === 0 ? 'PUSH' : `LOSE −${money(-spin.net)}`;
  result.className = `rl-result${spin.net < 0 ? ' lose' : ''}`;
  result.innerHTML = `<span class="rl-num ${colour}">${spin.number}</span><span>${label}</span>`;
  result.classList.remove('hidden');
  rlShowBalance(state.balance);
  // Подсветка выигравших клеток, фишки убираем.
  const winners = new Set(spin.bets.filter((b) => b.won).map((b) => `${b.type}:${b.value === null ? '' : b.value}`));
  for (const node of $('rl-cells').children) node.classList.toggle('is-win', winners.has(node.dataset.key));
  setTimeout(() => { for (const node of $('rl-cells').children) node.classList.remove('is-win'); }, 2600);
  rl.bets.clear();
  renderRoulette();
}

// Подпись на фишке: коротко, без лишних нулей ($5, $12.5, $1.2k).
function rlChipText(cents) {
  const dollars = cents / 100;
  if (dollars >= 1000) return `$${(dollars / 1000).toFixed(dollars % 1000 ? 1 : 0)}k`;
  if (dollars >= 100) return `$${Math.round(dollars)}`;
  return `$${Number.isInteger(dollars) ? dollars : dollars.toFixed(2).replace(/0$/, '')}`;
}

function renderRoulette() {
  if (!state.rl.open) return;
  const rl = state.rl;
  const spinning = rl.spinning;
  const amount = $('rl-amount');
  if (!spinning) {
    const { min, max } = rlRange();
    rl.amount = clamp(rl.amount, min, max);
  }
  amount.textContent = rl.typing ? (rl.typed ? `$${rl.typed}` : '$') : money(rl.amount);
  $('rl-minus').disabled = spinning;
  $('rl-plus').disabled = spinning;
  const presets = $('rl-presets');
  if (!presets.children.length) {
    for (const value of RL_PRESETS) {
      const button = document.createElement('button');
      button.className = 'bj-preset';
      button.textContent = `$${value / 100}`;
      button.addEventListener('click', () => {
        addRlAmount(value);
        button.classList.add('is-pressed');
        setTimeout(() => button.classList.remove('is-pressed'), 180);
      });
      presets.appendChild(button);
    }
  }
  for (const button of presets.children) button.disabled = spinning;

  // Фишки на клетках.
  for (const node of $('rl-cells').children) {
    const bet = rl.bets.get(node.dataset.key);
    let chip = node.querySelector('.rl-chip');
    if (!bet) { if (chip) chip.remove(); continue; }
    if (!chip) { chip = document.createElement('i'); chip.className = 'rl-chip'; node.appendChild(chip); }
    const text = rlChipText(bet.amount);
    if (chip.textContent !== text) chip.textContent = text;
    chip.classList.toggle('is-long', text.length === 4);
    chip.classList.toggle('is-xlong', text.length >= 5);
  }

  const total = rlTotal();
  $('rl-total').textContent = `На столе ${money(total)}`;
  $('rl-clear').classList.toggle('hidden', !total || spinning);
  const spinBtn = $('rl-spin');
  spinBtn.classList.remove('is-loading');
  spinBtn.disabled = spinning || !total || total > state.balance;
}

// ——— Баккара ———
// Фон — присланный макет (img/bc-bg.webp), холст 390×598.5, k = 390/941,
// шапка Telegram (228 px макета) обрезана. Поверх нарисованного — только
// живое. Карты летят из колоды и переворачиваются в полёте: P1, B1, P2,
// B2, затем третьи — порядок игрок-банкир, игрок-банкир.

const BC_K = 390 / 941;
const BC_TOP = 228; // обрезанная шапка макета
// Лента фишек: шесть номиналов с шагом 104 по макету (серая $1 добавлена
// к пяти нарисованным). Спрайты вырезаны из макета, цифры поверх — текстом.
const BC_CHIPS = [
  { value: 100, name: '1', label: '1', cx: 207 },
  { value: 500, name: '5', label: '5', cx: 311 },
  { value: 1000, name: '10', label: '10', cx: 415 },
  { value: 5000, name: '50', label: '50', cx: 519 },
  { value: 10000, name: '100', label: '100', cx: 623 },
  { value: 100000, name: '1k', label: '1K', cx: 727 },
];
const BC_STACK_MAX = 6; // башенка не выше шести фишек
const BC_DECK = { x: 478, y: 440 }; // центр колоды на макете
const BC_HAND_X = { player: 175, banker: 575 }; // первая карта руки
const BC_HAND_Y = 452;
const BC_CARD_STEP = { x: 42, y: 17 };
const BC_HISTORY_COLS = 19;
const BC_HISTORY_ROWS = 6;

const bcX = (x) => x * BC_K;
const bcY = (y) => (y - BC_TOP) * BC_K;

function fitBaccarat() {
  const screen = $('screen-bc');
  if (!screen || screen.classList.contains('hidden')) return;
  const w = screen.clientWidth || window.innerWidth;
  $('bc-canvas').style.setProperty('--bj', (w / 390).toFixed(4));
}

function openBaccarat() {
  state.bc.open = true;
  state.bc.shownBalance = null;
  state.bc.round = null;
  state.bc.pendingHistory = null;
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.add('hidden');
  $('screen-bj').classList.add('hidden');
  $('screen-rl').classList.add('hidden');
  $('screen-mn').classList.add('hidden');
  $('screen-nv').classList.add('hidden');
  $('screen-bc').classList.remove('hidden');
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  fitBaccarat();
  requestAnimationFrame(fitBaccarat);
  buildBaccaratChips();
  bcClearTable();
  send({ type: 'bc_open' });
  renderBaccarat();
}

function closeBaccarat() {
  state.bc.timers.forEach(clearTimeout);
  state.bc.timers = [];
  state.bc.dealing = false;
  state.bc.open = false;
  $('screen-bc').classList.add('hidden');
  showLobby();
}

// Лента фишек: кнопки со спрайтами по центрам макета.
function buildBaccaratChips() {
  const row = $('bc-chip-row');
  if (row.children.length) return;
  for (const chip of BC_CHIPS) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'bc-chip';
    button.dataset.value = String(chip.value);
    button.dataset.chip = chip.name;
    button.style.left = `${bcX(chip.cx).toFixed(1)}px`;
    button.innerHTML = `<b>${chip.label}</b>`;
    button.setAttribute('aria-label', `Фишка ${money(chip.value)}`);
    button.addEventListener('click', () => {
      if (state.bc.dealing) return;
      state.bc.chip = chip.value;
      haptic('light');
      renderBaccarat();
    });
    row.appendChild(button);
  }
  const history = $('bc-history');
  if (!history.children.length) {
    for (let r = 0; r < BC_HISTORY_ROWS; r += 1) {
      for (let c = 0; c < BC_HISTORY_COLS; c += 1) {
        const dot = document.createElement('i');
        dot.style.setProperty('--c', String(c));
        dot.style.setProperty('--r', String(r));
        history.appendChild(dot);
      }
    }
  }
}

function bcTotalStaked() {
  let total = 0;
  for (const amount of state.bc.bets.values()) total += amount;
  return total;
}

// Тап по зоне кладёт туда фишку текущего номинала (или добавляет к уже
// стоящей): сумма регулируется выбором фишки внизу.
function placeBcBet(zone, node) {
  if (state.bc.dealing) return;
  const amount = state.bc.chip;
  if (bcTotalStaked() + amount > state.balance) {
    toast('Недостаточно средств');
    haptic('error');
    return;
  }
  state.bc.bets.set(zone, (state.bc.bets.get(zone) || 0) + amount);
  haptic('light');
  renderBaccarat();
}

function bcShowBalance(target, immediate = false) {
  const box = $('bc-balance');
  const out = $('bc-balance-value');
  const from = state.bc.shownBalance === null ? target : state.bc.shownBalance;
  state.bc.shownBalance = target;
  if (immediate || from === target || reducedMotion()) { out.textContent = money(target); return; }
  box.classList.remove('is-up', 'is-down');
  box.classList.add(target > from ? 'is-up' : 'is-down');
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / 750);
    const eased = 1 - Math.pow(1 - t, 3);
    out.textContent = money(Math.round(from + (target - from) * eased));
    if (t < 1) requestAnimationFrame(tick);
    else setTimeout(() => box.classList.remove('is-up', 'is-down'), 900);
  };
  requestAnimationFrame(tick);
}

function bcClearTable() {
  $('bc-cards').innerHTML = '';
  for (const side of ['player', 'banker']) {
    const total = $(`bc-${side}-total`);
    total.textContent = '';
    total.classList.remove('is-on');
  }
  const result = $('bc-result');
  result.className = 'bc-result';
  result.innerHTML = '';
  $('bc-zones').classList.remove('is-locked');
  // Пока раунда нет — на столе только нарисованная колода, без подписей.
  $('bc-table').classList.add('is-idle');
}

// Карта с двумя гранями: летит из колоды к своему месту в руке и
// переворачивается на лету. Места — как на макете: первая карта руки,
// каждая следующая правее на 42 и ниже на 9 (в px макета).
function bcDealCard(side, index, code) {
  const rank = code[0] === 'T' ? '10' : code[0];
  const suitChar = code[1];
  const suit = BJ_SUITS[suitChar] || '♠';
  const card = document.createElement('div');
  card.className = 'bc-card';
  card.dataset.side = side;
  const x = bcX(BC_HAND_X[side] + BC_CARD_STEP.x * index);
  const y = bcY(BC_HAND_Y + BC_CARD_STEP.y * index);
  card.style.setProperty('--x', `${x.toFixed(1)}px`);
  card.style.setProperty('--y', `${y.toFixed(1)}px`);
  card.innerHTML = `<div class="bc-face front${suitChar === 'h' || suitChar === 'd' ? ' red' : ''}"><span class="bj-rank">${rank}</span><span class="bj-suit-sm">${suit}</span><span class="bj-suit">${suit}</span></div><div class="bc-face back"></div>`;
  $('bc-cards').appendChild(card);
  if (reducedMotion() || typeof card.animate !== 'function') return;
  const dx = bcX(BC_DECK.x) - (x + 41.4 / 2);
  const dy = bcY(BC_DECK.y) - (y + 59.7 / 2);
  card.animate([
    { transform: `translate(${(x + dx).toFixed(1)}px, ${(y + dy).toFixed(1)}px) scale(0.8) rotateY(180deg)`, offset: 0 },
    { transform: `translate(${(x + dx * 0.45).toFixed(1)}px, ${(y + dy * 0.45 - 14).toFixed(1)}px) scale(1.06) rotateY(95deg)`, offset: 0.55 },
    { transform: `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) scale(1) rotateY(0deg)`, offset: 1 },
  ], { duration: 640, easing: 'cubic-bezier(0.22, 0.8, 0.3, 1)', fill: 'both' });
}

function bcTotal(codes) {
  let sum = 0;
  for (const code of codes) {
    const r = code[0];
    sum += r === 'A' ? 1 : 'TJQK'.includes(r) ? 0 : Number(r);
  }
  return sum % 10;
}

// Дорожка: точки нарисованы на фоне, поверх — цвет исхода; старые слева,
// новые правее, по рядам сверху вниз.
function bcRenderHistory(history) {
  const dots = $('bc-history').children;
  if (!dots.length) return;
  const ordered = history.slice().reverse();
  for (let i = 0; i < dots.length; i += 1) dots[i].className = ordered[i] || '';
}

function onBaccaratState(message) {
  state.bc.info = message;
  state.balance = message.balance;
  renderAccount();
  if (message.round) {
    // Точка в дорожке появляется только после того, как карты сыграли:
    // историю с результатом придерживаем до конца раздачи.
    state.bc.pendingHistory = message.history || [];
    startBaccaratDeal(message.round);
    return;
  }
  bcRenderHistory(message.history || []);
  bcShowBalance(message.balance, true);
  renderBaccarat();
}

function startBaccaratDeal(round) {
  const bc = state.bc;
  bc.timers.forEach(clearTimeout);
  bc.timers = [];
  bc.dealing = true;
  bc.round = round;
  bcClearTable();
  $('bc-table').classList.remove('is-idle');
  $('bc-zones').classList.add('is-locked');
  $('bc-canvas').classList.add('is-dealing');
  bcShowBalance(state.balance - round.payout);
  renderBaccarat();
  const steps = [['player', 0], ['banker', 0], ['player', 1], ['banker', 1]];
  if (round.player[2]) steps.push(['player', 2]);
  if (round.banker[2]) steps.push(['banker', 2]);
  let delay = 300;
  steps.forEach(([side, index], i) => {
    bc.timers.push(setTimeout(() => {
      bcDealCard(side, index, round[side][index]);
      haptic('light');
      // Очки обновляются, когда карта легла (после переворота).
      bc.timers.push(setTimeout(() => {
        const total = $(`bc-${side}-total`);
        total.textContent = String(bcTotal(round[side].slice(0, index + 1)));
        total.classList.add('is-on');
      }, 480));
      if (i === steps.length - 1) bc.timers.push(setTimeout(() => finishBaccaratDeal(round), 900));
    }, delay));
    delay += 560;
  });
}

function bcResultView(round) {
  const { stake, payout, net, winner } = round;
  if (net > 0) {
    const mult = stake > 0 ? payout / stake : 0;
    return { cls: 'win', line1: `${mult.toFixed(2)}x`, line2: money(payout) };
  }
  const label = winner === 'tie' ? 'TIE' : `${winner === 'player' ? 'PLAYER' : 'BANKER'} WINS`;
  if (net === 0 && payout > 0) return { cls: 'push', line1: label, line2: 'Возврат' };
  return { cls: 'lose', line1: label, line2: money(payout) };
}

function finishBaccaratDeal(round) {
  const bc = state.bc;
  bc.dealing = false;
  $('bc-zones').classList.remove('is-locked');
  $('bc-canvas').classList.remove('is-dealing');
  if (bc.pendingHistory) {
    bcRenderHistory(bc.pendingHistory);
    bc.pendingHistory = null;
  }
  const result = $('bc-result');
  const view = bcResultView(round);
  result.className = `bc-result is-visible ${view.cls}`;
  result.innerHTML = `<b>${view.line1}</b><span>${view.line2}</span>`;
  // Карты выигравшей раздачу стороны обводим в цвет исхода — как на макете.
  if (round.winner === 'player' || round.winner === 'banker') {
    document.querySelectorAll(`.bc-card[data-side="${round.winner}"]`).forEach((c) => c.classList.add(`is-glow-${view.cls}`));
  }
  bc.timers.push(setTimeout(() => result.classList.remove('is-visible'), 3200));
  haptic(round.net > 0 ? 'success' : 'light');
  bcShowBalance(state.balance);
  bc.bets.clear();
  renderBaccarat();
}

// Башенка: сумма ставки раскладывается по номиналам от крупного к мелкому
// (50+50 становится одной фишкой 100), снизу крупные. Выше шести фишек не
// растёт — лишние мелкие просто не показываем, сумма написана на верхней.
function bcStackChips(amount) {
  const chips = [];
  let rest = amount;
  for (const chip of [...BC_CHIPS].reverse()) {
    while (rest >= chip.value) { chips.push(chip.name); rest -= chip.value; }
  }
  return chips.slice(0, BC_STACK_MAX);
}

// Подпись на фишке: 5, 50, 1K, 1.5K — без знака доллара, как на ленте.
function bcChipLabel(cents) {
  const dollars = cents / 100;
  if (dollars >= 1000) {
    const k = dollars / 1000;
    return `${k >= 100 ? Math.round(k) : String(Math.round(k * 10) / 10)}K`;
  }
  return String(Math.round(dollars));
}

function renderBaccarat() {
  if (!state.bc.open) return;
  const bc = state.bc;
  const active = BC_CHIPS.find((c) => c.value === bc.chip) || BC_CHIPS[1];
  $('bc-chip-frame').style.left = `${bcX(active.cx).toFixed(1)}px`;
  for (const button of $('bc-chip-row').children) button.disabled = bc.dealing;
  for (const zoneEl of document.querySelectorAll('.bc-zone')) {
    const amount = bc.bets.get(zoneEl.dataset.zone) || 0;
    let stack = zoneEl.querySelector('.bc-stack');
    if (!amount) { if (stack) stack.remove(); continue; }
    if (stack && Number(stack.dataset.amount) === amount) continue;
    if (!stack) { stack = document.createElement('i'); stack.className = 'bc-stack'; zoneEl.appendChild(stack); }
    stack.dataset.amount = String(amount);
    const chips = bcStackChips(amount);
    stack.style.setProperty('--n', String(chips.length));
    stack.innerHTML = chips.map((name, i) => `<b data-chip="${name}" style="--i:${i}"></b>`).join('')
      + `<span>${bcChipLabel(amount)}</span>`;
  }
  const total = bcTotalStaked();
  $('bc-clear').disabled = !total || bc.dealing;
  const place = $('bc-place');
  place.classList.remove('is-loading');
  place.disabled = bc.dealing || !total || total > state.balance;
}

// ——— Mines ———
// Экран обычный (не холст): поле сверху, параметры ставки ниже, страница
// прокручивается. Раунд целиком на сервере: клиент шлёт ставку, клик по
// клетке и «забрать», а показывает то, что вернулось.
const MN_SIZE = 25;
const MN_GEM = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"><path d="M6.5 4h11l4 5.5L12 20.5 2.5 9.5 6.5 4Z"/><path d="M2.5 9.5h19M9 4l-2.5 5.5L12 20.5 15.5 9.5 15 4M9 4l3 5.5 3-5.5"/></svg>';
const MN_BOMB = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="14" r="7" fill="currentColor"/><circle cx="8.2" cy="11.6" r="1.6" fill="rgba(255,255,255,0.35)"/><path d="M14.5 8.5 17 6c1.2-1.2 3-1 4 .3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="21.5" cy="5.5" r="1.6" fill="#ffb347"/></svg>';

function buildMinesBoard() {
  const board = $('mn-board');
  if (board.children.length) return;
  for (let i = 0; i < MN_SIZE; i += 1) {
    const cell = document.createElement('button');
    cell.className = 'mn-cell';
    cell.type = 'button';
    cell.dataset.index = String(i);
    cell.setAttribute('aria-label', `Клетка ${i + 1}`);
    cell.addEventListener('click', () => pickMinesCell(i));
    board.appendChild(cell);
  }
  const select = $('mn-mines');
  for (let n = 1; n <= 24; n += 1) {
    const option = document.createElement('option');
    option.value = String(n);
    option.textContent = String(n);
    select.appendChild(option);
  }
  select.value = String(state.mn.mines);
}

function openMines() {
  state.mn.open = true;
  state.mn.busy = false;
  state.mn.reveal = null;
  state.mn.shownBalance = null;
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.add('hidden');
  $('screen-bj').classList.add('hidden');
  $('screen-rl').classList.add('hidden');
  $('screen-bc').classList.add('hidden');
  $('screen-mn').classList.remove('hidden');
  $('screen-mn').scrollTop = 0;
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  buildMinesBoard();
  mnWriteAmount();
  send({ type: 'mn_open' });
  renderMines();
}

function closeMines() {
  state.mn.open = false;
  state.mn.busy = false;
  $('screen-mn').classList.add('hidden');
  showLobby();
}

function mnRange() {
  const info = state.mn.info;
  const min = info ? info.minBet : 10;
  const max = Math.min(info ? info.maxBet : 10000000, Math.max(min, state.balance));
  return { min, max };
}

// Сумма в поле — как пишет игрок; в state — центы (или null, если не число).
function mnReadAmount() {
  const input = $('mn-amount');
  const cents = toCents(input.value);
  state.mn.amount = cents !== null && cents > 0 ? cents : null;
  renderMines();
}

function mnWriteAmount() {
  const input = $('mn-amount');
  if (state.mn.amount === null) return;
  input.value = (state.mn.amount / 100).toFixed(2).replace('.', ',');
  input.closest('.mn-input').classList.remove('is-bad');
}

function mnAdjust(change) {
  if (mnPhase() === 'play') return;
  const { min, max } = mnRange();
  const current = state.mn.amount ?? min;
  state.mn.amount = clamp(Math.round(change(current)), min, max);
  haptic('light');
  mnWriteAmount();
  renderMines();
}

function mnPhase() {
  const info = state.mn.info;
  if (!info) return 'bet';
  if (info.phase === 'done' && !state.mn.reveal) return 'bet';
  return info.phase;
}

function onMinesMain() {
  const mn = state.mn;
  if (mn.busy) return;
  const phase = mnPhase();
  if (phase === 'play') {
    if (!mn.info.opened.length) return;
    mn.busy = true;
    haptic('light');
    send({ type: 'mn_cashout' });
  } else {
    const { min, max } = mnRange();
    if (mn.amount === null || mn.amount < min) { toast(`Минимальная ставка ${money(min)}`); return; }
    if (mn.amount > state.balance) { toast('Недостаточно средств'); haptic('error'); return; }
    if (mn.amount > max) { toast(`Максимальная ставка ${money(max)}`); return; }
    mn.busy = true;
    mn.reveal = null;
    haptic('light');
    send({ type: 'mn_start', amount: mn.amount, mines: mn.mines });
  }
  renderMines();
}

function pickMinesCell(index) {
  const mn = state.mn;
  if (mn.busy || mnPhase() !== 'play') return;
  if (mn.info.opened.includes(index)) return;
  mn.busy = true;
  haptic('light');
  send({ type: 'mn_pick', index });
  renderMines();
}

function mnShowBalance(value, silent) {
  const mn = state.mn;
  const node = $('mn-balance');
  $('mn-balance-value').textContent = money(value);
  if (!silent && mn.shownBalance !== null && value !== mn.shownBalance) {
    node.classList.remove('is-up', 'is-down');
    void node.offsetWidth;
    node.classList.add(value > mn.shownBalance ? 'is-up' : 'is-down');
    setTimeout(() => node.classList.remove('is-up', 'is-down'), 1400);
  }
  mn.shownBalance = value;
}

function onMinesState(message) {
  const mn = state.mn;
  const previous = mn.info;
  mn.info = message;
  mn.busy = false;
  state.balance = message.balance;
  renderAccount();
  if (message.phase === 'done' && previous && previous.phase === 'play') {
    // Раунд только что закончился — показываем итог поверх поля.
    mn.reveal = message;
    haptic(message.result === 'win' ? 'success' : 'error');
  } else if (message.phase !== 'done') {
    mn.reveal = null;
  }
  renderMines();
  mnShowBalance(message.balance, !previous);
}

function renderMines() {
  const mn = state.mn;
  if (!mn.open) return;
  const info = mn.info;
  const phase = mnPhase();
  const live = phase === 'play';
  const board = $('mn-board');
  const opened = new Set(info ? info.opened : []);
  const reveal = mn.reveal;
  board.classList.toggle('is-live', live && !mn.busy);
  board.classList.toggle('is-done', Boolean(reveal));
  for (const cell of board.children) {
    const index = Number(cell.dataset.index);
    let kind = '';
    if (reveal) {
      if (reveal.boom === index) kind = 'boom';
      else if (opened.has(index)) kind = 'open';
      else kind = reveal.field[index] === 'mine' ? 'mine' : 'gem';
    } else if (live && opened.has(index)) {
      kind = 'open';
    }
    const html = kind === 'open' || kind === 'gem' ? MN_GEM : kind === 'mine' || kind === 'boom' ? MN_BOMB : '';
    if (cell.dataset.kind !== kind) {
      cell.dataset.kind = kind;
      cell.innerHTML = html;
      cell.classList.toggle('is-open', kind === 'open');
      cell.classList.toggle('is-gem', kind === 'gem');
      cell.classList.toggle('is-mine', kind === 'mine');
      cell.classList.toggle('is-boom', kind === 'boom');
    }
    cell.disabled = !live || mn.busy || kind !== '';
  }

  const overlay = $('mn-overlay');
  if (reveal && reveal.result === 'win') {
    overlay.className = 'mn-overlay is-win';
    overlay.innerHTML = `<svg class="icon mn-suit-l"><use href="#i-spade"></use></svg><svg class="icon mn-suit-r"><use href="#i-club"></use></svg><i class="mn-spark mn-spark-1">✦</i><i class="mn-spark mn-spark-2">✦</i><b>x${reveal.multiplier.toFixed(2)}</b><span><i class="mn-coin">$</i>${money(reveal.payout).slice(1)}</span>`;
  } else if (reveal) {
    overlay.className = 'mn-overlay is-lose';
    overlay.innerHTML = '<svg class="icon mn-suit-l"><use href="#i-spade"></use></svg><svg class="icon mn-suit-r"><use href="#i-club"></use></svg><b>Неудачно</b><span>Удачи в следующий раз!</span><button type="button" class="mn-again">Играть снова</button>';
    overlay.querySelector('.mn-again').addEventListener('click', () => { mn.reveal = null; haptic('light'); renderMines(); });
  } else {
    overlay.className = 'mn-overlay hidden';
    overlay.innerHTML = '';
  }

  const main = $('mn-main');
  main.classList.toggle('is-cash', live);
  if (live) {
    const count = info.opened.length;
    if (count) {
      const payout = Math.floor(info.bet * info.multiplier);
      main.innerHTML = `Забрать ${money(payout)} <small>x${info.multiplier.toFixed(2)}</small>`;
      main.disabled = mn.busy;
    } else {
      main.innerHTML = `Откройте клетку <small>след. x${info.next.toFixed(2)}</small>`;
      main.disabled = true;
    }
  } else {
    main.textContent = 'Ставка';
    const { min } = mnRange();
    main.disabled = mn.busy || mn.amount === null || mn.amount < min || mn.amount > state.balance;
  }
  const bad = mn.amount === null || mn.amount > state.balance;
  $('mn-amount').closest('.mn-input').classList.toggle('is-bad', !live && bad);
  $('mn-amount').disabled = live;
  for (const id of ['mn-half', 'mn-double', 'mn-max']) $(id).disabled = live;
  const select = $('mn-mines');
  select.disabled = live;
  if (live && String(info.mines) !== select.value) select.value = String(info.mines);
  else if (!live && select.value !== String(mn.mines)) select.value = String(mn.mines);
}

// ——— Nvuti ———
// Экран и панель ставки — те же компоненты, что у Mines. Своё — шкала
// 1–100: курсор цели тянется пальцем, после броска к выпавшему числу
// подъезжает маркер результата. Розыгрыш мгновенный, на сервере.
const NV_MIN_TARGET = 5;
const NV_MAX_TARGET = 95;

function nvPos(value) {
  return ((value - 1) / 99) * 100; // позиция на шкале, %
}

function nvChance() {
  return state.nv.mode === 'under' ? state.nv.target : 100 - state.nv.target;
}

function nvMultiplier() {
  return Math.floor((97 / nvChance()) * 100 + 1e-9) / 100;
}

function buildNvutiScale() {
  const ticks = $('nv-ticks');
  if (ticks.children.length) return;
  for (let v = 1; v <= 100; v += 3) {
    const tick = document.createElement('i');
    const major = v === 1 || v === 25 || v === 49 || v === 73 || v === 100;
    if (major) tick.className = 'major';
    tick.style.left = `${nvPos(v)}%`;
    ticks.appendChild(tick);
  }
}

function bindNvutiScale() {
  const scale = $('nv-scale');
  let dragging = false;
  const valueAt = (clientX) => {
    const rect = $('nv-scale').querySelector('.nv-track').getBoundingClientRect();
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
    return clamp(Math.round(1 + ratio * 99), NV_MIN_TARGET, NV_MAX_TARGET);
  };
  scale.addEventListener('pointerdown', (event) => {
    if (state.nv.busy) return;
    if (event.target.closest('.nv-marker')) return;
    dragging = true;
    scale.classList.add('is-dragging');
    scale.setPointerCapture(event.pointerId);
    nvSetTarget(valueAt(event.clientX));
    event.preventDefault();
  });
  scale.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    nvSetTarget(valueAt(event.clientX));
  });
  const stop = () => { if (!dragging) return; dragging = false; scale.classList.remove('is-dragging'); };
  scale.addEventListener('pointerup', stop);
  scale.addEventListener('pointercancel', stop);
}

function nvSetTarget(value) {
  if (value === state.nv.target) return;
  state.nv.target = value;
  renderNvuti();
}

function nvSetMode(mode) {
  if (state.nv.busy || (mode !== 'under' && mode !== 'over')) return;
  state.nv.mode = mode;
  haptic('light');
  renderNvuti();
}

function openNvuti() {
  const nv = state.nv;
  nv.open = true;
  nv.busy = false;
  nv.round = null;
  nv.shownBalance = null;
  $('screen-lobby').classList.add('hidden');
  $('screen-table').classList.add('hidden');
  $('screen-bj').classList.add('hidden');
  $('screen-rl').classList.add('hidden');
  $('screen-bc').classList.add('hidden');
  $('screen-mn').classList.add('hidden');
  $('screen-nv').classList.remove('hidden');
  $('screen-nv').scrollTop = 0;
  if (tg && tg.BackButton) tg.BackButton.show();
  stopRoomsPolling();
  buildNvutiScale();
  $('nv-marker').classList.add('hidden');
  $('nv-outcome').classList.add('hidden');
  nvWriteAmount();
  send({ type: 'nv_open' });
  renderNvuti();
}

function closeNvuti() {
  clearTimeout(state.nv.timer);
  state.nv.open = false;
  state.nv.busy = false;
  $('screen-nv').classList.add('hidden');
  showLobby();
}

function nvRange() {
  const info = state.nv.info;
  const min = info ? info.minBet : 10;
  const max = Math.min(info ? info.maxBet : 10000000, Math.max(min, state.balance));
  return { min, max };
}

function nvReadAmount() {
  const cents = toCents($('nv-amount').value);
  state.nv.amount = cents !== null && cents > 0 ? cents : null;
  renderNvuti();
}

function nvWriteAmount() {
  if (state.nv.amount === null) return;
  const input = $('nv-amount');
  input.value = (state.nv.amount / 100).toFixed(2).replace('.', ',');
  input.closest('.mn-input').classList.remove('is-bad');
}

function nvAdjust(change) {
  if (state.nv.busy) return;
  const { min, max } = nvRange();
  const current = state.nv.amount ?? min;
  state.nv.amount = clamp(Math.round(change(current)), min, max);
  haptic('light');
  nvWriteAmount();
  renderNvuti();
}

function onNvutiMain() {
  const nv = state.nv;
  if (nv.busy) return;
  const { min, max } = nvRange();
  if (nv.amount === null || nv.amount < min) { toast(`Минимальная ставка ${money(min)}`); return; }
  if (nv.amount > state.balance) { toast('Недостаточно средств'); haptic('error'); return; }
  if (nv.amount > max) { toast(`Максимальная ставка ${money(max)}`); return; }
  nv.busy = true;
  haptic('light');
  send({ type: 'nv_bet', amount: nv.amount, target: nv.target, mode: nv.mode });
  renderNvuti();
}

function nvShowBalance(value, silent) {
  const nv = state.nv;
  const node = $('nv-balance');
  $('nv-balance-value').textContent = money(value);
  if (!silent && nv.shownBalance !== null && value !== nv.shownBalance) {
    node.classList.remove('is-up', 'is-down');
    void node.offsetWidth;
    node.classList.add(value > nv.shownBalance ? 'is-up' : 'is-down');
    setTimeout(() => node.classList.remove('is-up', 'is-down'), 1400);
  }
  nv.shownBalance = value;
}

function onNvutiState(message) {
  const nv = state.nv;
  const first = !nv.info;
  nv.info = message;
  state.balance = message.balance;
  renderAccount();
  if (message.round) {
    nvPlayRound(message.round);
    return;
  }
  nv.busy = false;
  renderNvuti();
  nvShowBalance(message.balance, first);
}

// Маркер выезжает к выпавшему числу; итог и баланс показываем, когда доехал.
function nvPlayRound(round) {
  const nv = state.nv;
  nv.round = round;
  const marker = $('nv-marker');
  const outcome = $('nv-outcome');
  outcome.classList.add('hidden');
  marker.className = 'nv-marker';
  $('nv-marker-value').textContent = String(round.roll);
  const from = marker.dataset.at ? Number(marker.dataset.at) : (round.mode === 'under' ? 100 : 1);
  marker.style.setProperty('--p', nvPos(from).toFixed(2));
  void marker.offsetWidth;
  marker.style.setProperty('--p', nvPos(round.roll).toFixed(2));
  marker.dataset.at = String(round.roll);
  nvShowBalance(state.balance - round.payout, true);
  clearTimeout(nv.timer);
  nv.timer = setTimeout(() => {
    marker.classList.add(round.won ? 'is-win' : 'is-lose');
    outcome.className = `nv-outcome ${round.won ? 'is-win' : 'is-lose'}`;
    outcome.textContent = round.won ? `Выпало ${round.roll} · +${money(round.net)}` : `Выпало ${round.roll} · −${money(round.bet)}`;
    haptic(round.won ? 'success' : 'error');
    nvShowBalance(state.balance);
    nv.busy = false;
    renderNvuti();
  }, 950);
}

function renderNvuti() {
  const nv = state.nv;
  if (!nv.open) return;
  const under = nv.mode === 'under';
  const chance = nvChance();
  const multiplier = nvMultiplier();
  $('nv-thumb').style.setProperty('--p', nvPos(nv.target).toFixed(2));
  $('nv-thumb-value').textContent = String(nv.target);
  const fill = $('nv-fill');
  fill.style.setProperty('--from', under ? '0' : nvPos(nv.target).toFixed(2));
  fill.style.setProperty('--to', under ? nvPos(nv.target).toFixed(2) : '100');
  $('nv-mult').textContent = multiplier.toFixed(2);
  $('nv-target').textContent = String(nv.target);
  $('nv-mode-label').textContent = under ? 'Ролл ниже' : 'Ролл выше';
  $('nv-chance').textContent = chance.toFixed(2);
  $('nv-swap').disabled = nv.busy;
  const select = $('nv-mode');
  if (select.value !== nv.mode) select.value = nv.mode;
  select.disabled = nv.busy;
  const main = $('nv-main');
  const { min } = nvRange();
  main.textContent = nv.busy ? 'Бросок…' : 'Сделать ставку';
  main.disabled = nv.busy || nv.amount === null || nv.amount < min || nv.amount > state.balance;
  const bad = nv.amount === null || nv.amount > state.balance;
  $('nv-amount').closest('.mn-input').classList.toggle('is-bad', bad);
  $('nv-amount').disabled = nv.busy;
  for (const id of ['nv-half', 'nv-double', 'nv-max']) $(id).disabled = nv.busy;
}

// Главная и Игры — это две панели одного экрана лобби: столы и лента
// выигрышей приходят одним и тем же сообщением, переключение ничего не грузит.
const TABS = ['home', 'games', 'tournaments', 'bonuses', 'profile'];

function fitLobby() {
  // Холст главной свёрстан на 390 css px по макету; масштабируем под ширину.
  const width = document.querySelector('.lobby')?.clientWidth || window.innerWidth;
  document.documentElement.style.setProperty('--mk', (Math.min(width, 480) / 390).toFixed(4));
}

function showTab(tab) {
  state.tab = TABS.includes(tab) ? tab : 'home';
  document.body.dataset.tab = state.tab;
  fitLobby();
  for (const name of TABS) $(`tab-${name}`).classList.toggle('hidden', state.tab !== name);
  for (const button of document.querySelectorAll('.nav-btn')) {
    button.classList.toggle('is-active', button.dataset.tab === state.tab);
  }
  const scroller = document.querySelector('.lobby');
  if (scroller) scroller.scrollTop = 0;
}

// Раскрывающиеся разделы главной: открытый ровно один.
const PANELS = ['topup-card', 'payout-card', 'leaders-card', 'history-card', 'help-card'];

function togglePanel(id) {
  const target = $(id);
  const opening = target.classList.contains('hidden');
  for (const panel of PANELS) $(panel).classList.add('hidden');
  if (opening) {
    target.classList.remove('hidden');
    // Панели лежат под всеми вкладками; пусть открытая будет на виду.
    requestAnimationFrame(() => target.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
  }
  for (const tile of document.querySelectorAll('.tile, .lb-row')) tile.classList.remove('is-active');
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
  $('profile-balance').textContent = money(state.balance);
  $('my-id').textContent = state.user ? state.user.id : '—';
  $('profile-id').textContent = `Telegram ID: ${state.user ? state.user.id : '—'}`;
  $('profile-name').textContent = state.user ? (state.user.name || 'Игрок') : '—';
  $('admin-card').classList.toggle('hidden', !state.isAdmin);

  renderPayoutControls();

  const photo = state.user && state.user.photoUrl;
  const initial = state.user && state.user.name ? state.user.name.trim()[0].toUpperCase() : '♠';
  for (const id of ['avatar', 'profile-avatar']) {
    const avatar = $(id);
    if (!avatar) continue;
    if (photo) {
      if (avatar.dataset.photo !== photo) {
        avatar.dataset.photo = photo;
        avatar.innerHTML = `<img src="${escapeHtml(photo)}" alt="" />`;
      }
    } else if (!avatar.dataset.photo) {
      avatar.textContent = initial;
    }
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

  // Списка столов во вкладке «Игры» больше нет: там две кнопки постоянных
  // столов заведения. Оставляем отрисовку только если элемент существует.
  const list = $('rooms-list');
  if (!list) return;
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

// Сколько людей сейчас за столами каждой игры — для карточек игр.
function renderOnline() {
  const count = { holdem: 0, omaha: 0, blackjack: 0 };
  for (const room of state.rooms) count[room.game === 'blackjack' ? 'blackjack' : room.game === 'omaha' ? 'omaha' : 'holdem'] += room.players || 0;
  for (const game of Object.keys(count)) {
    const text = count[game] >= 1000 ? `${(count[game] / 1000).toFixed(1)}K` : String(count[game]);
    for (const node of document.querySelectorAll(`[data-online="${game}"]`)) node.textContent = text;
    const node = $(`online-${game}`);
    if (node) node.textContent = count[game] ? `${count[game]} онлайн` : 'ждёт игроков';
  }
}

// «Столы онлайн» на главной: те же открытые столы, но плиткой и с банком.
function renderActiveGames() {
  renderOnline();
  const list = $('home-rooms');
  if (!list) return; // на главной по макету списка столов нет
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
  if (card) card.classList.toggle('hidden', !state.wins.length);
  if (!list) return;
  if (!state.wins.length) { list.innerHTML = ''; return; }

  const icons = { holdem: 0, blackjack: 1 };
  list.innerHTML = state.wins.slice(0, 8).map((win, index) => {
    const blackjack = win.game === 'blackjack';
    const icon = icons[blackjack ? 'blackjack' : 'holdem'];
    const label = { ...Object.fromEntries(Object.entries(CasinoRules.games).map(([id,g])=>[id,g.name])), plinko:'Plinko', tower:'Башня', keno:'Кено', dragon:'Дракон и Тигр', crash: 'Crash', hilo: 'Hilo', blackjack: 'Blackjack', roulette: 'Roulette', baccarat: 'Baccarat', mines: 'Mines', nvuti: 'Nvuti', omaha: 'Omaha' }[win.game] || 'Poker';
    return `
    <div class="mk-win" style="--i:${index}">
      <span class="mk-win-icon" style="background-image:url('/img/lobby/win-${icon}.png')"></span>
      <span class="mk-win-sum">${money(win.amount)}</span>
      <span class="mk-win-game">${label}</span>
      <span class="mk-win-time">${win.at ? timeAgo(win.at) : escapeHtml(win.name)}</span>
    </div>`;
  }).join('');
}

// «2 мин назад» для ленты выигрышей.
function timeAgo(at) {
  const sec = Math.max(0, Math.round((Date.now() - at) / 1000));
  if (sec < 60) return 'только что';
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} мин назад`;
  const hours = Math.round(min / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.round(hours / 24)} д назад`;
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
  syncCrocTheme();
  const room = state.room;
  if (!room) return;

  $('room-title').textContent = room.title || `Стол ${room.code}`;
  // В омахе по четыре карты на руках — карты героя и соперников ужимаются.
  $('screen-table').classList.toggle('is-omaha', room.game === 'omaha');

  const blackjack = room.game === 'blackjack';
  const phases = blackjack
    ? { first: 'Ход первого', second: 'Ход второго', complete: 'Итог' }
    : { preflop: 'Префлоп', flop: 'Флоп', turn: 'Тёрн', river: 'Ривер', showdown: 'Вскрытие', complete: 'Вскрытие' };

  // Пока идёт раздача показываем этап, между раздачами — код стола.
  let tail = `код ${room.code}`;
  if (room.status === 'betting') tail = 'Ставка';
  else if (room.status === 'playing' && phases[room.phase]) tail = phases[room.phase];

  const pokerName = room.game === 'omaha' ? 'Омаха' : 'Холдем';
  $('room-subtitle').textContent = blackjack
    ? `Блекджек · ${money(room.settings.minBet)}–${money(room.settings.maxBet)} · ${tail}`
    : `${pokerName} · ${money(room.settings.smallBlind)}/${money(room.settings.bigBlind)} · ${tail}`;

  // Комбинацию победителя считаем до отрисовки: её подсвечивают и борд,
  // и карманные карты.
  state.winCards = computeWinCards(room);

  renderBoard(room);
  renderSeats(room);
  renderHandBadge(room);
  renderFeed(room);
  renderMessage(room);
  renderControls(room);
  renderResult(room);
  renderLog();

  // Векторы прилёта меряем сразу после сборки DOM, до первой отрисовки:
  // так карта не успевает мигнуть на своём месте.
  if (!amethystActive()) { primeDealAnimations(); runTableFx(room); }
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
    pot.classList.remove('hidden');
    $('pot-value').textContent = money(room.potTotal);
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
      // Флоп, тёрн и ривер выкладываются по очереди: каждая новая карта
      // переворачивается со своей задержкой, старые лежат как лежали.
      let fresh = 0;
      for (let index = 0; index < 5; index++) {
        const slot = document.createElement('div');
        slot.className = 'card-slot';
        if (cards[index]) {
          slot.classList.add('filled');
          const isNew = known[index] !== cards[index];
          const face = cardNode(cards[index], false, isNew);
          if (isNew) {
            // Общие карты уже лежат в центре — им нужен переворот, а не перелёт.
            face.classList.remove('deal-in', 'is-priming');
            face.classList.add('flip-in');
            face.style.setProperty('--deal-delay', `${fresh * 90}ms`);
            fresh += 1;
          }
          slot.appendChild(face);
        }
        board.appendChild(slot);
      }
    }
    board.dataset.cards = codes;
  }

  // Подсветка выигравшей комбинации живёт отдельно от сборки борда:
  // карты те же самые, меняется только выделение.
  const wins = state.winCards;
  board.classList.toggle('has-win', wins.size > 0);
  (room.board || []).forEach((card, index) => {
    const slot = board.children[index];
    if (slot) slot.classList.toggle('is-win', wins.has(card));
  });

  // Плашка «БАНК» нарисована на ассете, сумма в ней — наша: показываем
  // всегда, как в ассете ($0.00 на пустом столе).
  const pot = $('pot');
  pot.classList.remove('hidden');
  $('pot-value').textContent = money(room.potTotal);
}

function cardNode(code, small = false, animate = true) {
  const node = document.createElement('div');
  node.dataset.card = code;
  node.dataset.rank = code[0];
  // deal-in — карта прилетает из центра стола; вектор и очередь проставит
  // primeDealAnimations() после того, как всё окажется в DOM.
  if (amethystActive()) animate = false;
  node.className = `card-face${small ? ' small' : ''}${animate ? ' deal-in is-priming' : ' no-anim'}`;
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
  const symbol = document.createElement('span');
  symbol.className = 'croc-card-symbol';
  symbol.textContent = suit.symbol;
  node.appendChild(symbol);
  return node;
}

// Своя комбинация — отдельной пилюлей над столом. Считается на сервере
// только по картам, которые игрок и так видит.
function renderHandBadge() {
  // Комбинация показывается одним местом — плашкой под ником героя
  // (.hand-label в renderSeats). Пилюля над бордом больше не нужна.
  $('hand-badge').classList.add('hidden');
}

// Карты игрока. Раздаём как за живым столом: круг за кругом, по одной
// карте каждому.
// Место собирается заново на каждом состоянии, а состояний в начале
// раздачи приходит несколько подряд — поэтому помним не «показывали или
// нет», а момент начала. Пересобранная на лету карта получает
// отрицательную задержку и продолжает полёт с того же кадра.
const DEAL_STEP = 26;   // шаг очереди между картами
const DEAL_LIFE = 700;  // сколько миллисекунд карта считается «ещё в полёте»

function dealDelay(key, order) {
  const now = performance.now();
  let start = state.shownCards.get(key);
  if (start === undefined) {
    start = now;
    state.shownCards.set(key, now);
  }
  if (now - start > DEAL_LIFE) return null; // давно лежит — без анимации
  return start + Math.min(order * DEAL_STEP, 300) - now;
}

function buildSeatCards(seat, position, count) {
  const cards = document.createElement('div');
  cards.className = 'seat-cards';
  seat.cards.forEach((card, index) => {
    const key = `${seat.index}:${index}:${card}`;
    const delay = dealDelay(key, index * count + position);
    const face = cardNode(card, true, delay !== null);
    if (delay !== null) face.style.setProperty('--deal-delay', `${Math.round(delay)}ms`);
    if (state.winCards.has(card)) face.classList.add('is-win');
    cards.appendChild(face);
  });
  return cards;
}

function renderSeats(room) {
  if (amethystActive()) { renderAmethystSeats(room); return; }
  if (state.shownHand !== room.handNumber) {
    state.shownHand = room.handNumber;
    state.shownCards.clear();
  }

  const container = $('seats');
  container.innerHTML = '';
  // Точки мест в координатах холста — по ним потом летят фишки.
  state.fx.points.clear();

  const count = room.seats.length;
  const winnerIds = winnerIdSet(room);
  const mySeat = room.you.seatIndex;
  // Кто сидит сейчас: новых анимируем, ушедших забываем.
  const seatedNow = new Set(room.seats.filter((s) => !s.empty).map((s) => s.userId));
  // Своё место всегда внизу — так привычнее смотреть на стол.
  const offset = mySeat === null ? 0 : mySeat;

  room.seats.forEach((seat) => {
    const position = ((seat.index - offset) + count) % count;
    const anchor = seatAnchor(position, count);
    const isHero = !seat.empty && seat.userId === room.you.userId;

    // Место — только точка привязки к нарисованному кружку. Все части
    // (аватар, плашка, карты, ставка) висят на своих смещениях от неё,
    // у каждой своя зона: они не выстраиваются в общую колонку и не
    // толкают друг друга.
    const node = document.createElement('div');
    node.className = 'seat';
    node.dataset.anchor = String(anchor.at);
    node.style.left = `${(anchor.seat[0] * 100).toFixed(3)}%`;
    node.style.top = `${(anchor.seat[1] * 100).toFixed(3)}%`;
    node.style.setProperty('--av', `${anchor.avatar}px`);
    node.style.setProperty('--cx', `${anchor.cards[0]}px`);
    node.style.setProperty('--cy', `${anchor.cards[1]}px`);
    node.style.setProperty('--bx', `${anchor.bet[0]}px`);
    node.style.setProperty('--by', `${anchor.bet[1]}px`);
    node.style.setProperty('--ax', anchor.side === 'left' ? '0%' : anchor.side === 'right' ? '-100%' : '-50%');
    node.dataset.betSide = anchor.side;
    // Появление ставки: стопка подъезжает на 12 px от игрока к банку.
    {
      const dx = TABLE.width * TABLE.focusX - anchor.seat[0] * TABLE.width;
      const dy = TABLE.height * TABLE.focusY - anchor.seat[1] * TABLE.height;
      const len = Math.hypot(dx, dy) || 1;
      node.style.setProperty('--bdx', `${(dx / len * 12).toFixed(1)}px`);
      node.style.setProperty('--bdy', `${(dy / len * 12).toFixed(1)}px`);
    }

    state.fx.points.set(seat.index, {
      seat: { x: anchor.seat[0] * TABLE.width, y: anchor.seat[1] * TABLE.height },
      bet: { x: anchor.betFrac[0] * TABLE.width, y: anchor.betFrac[1] * TABLE.height },
    });

    if (seat.empty) {
      // Кружок с плюсом уже нарисован на ассете — своего не рисуем,
      // кладём только прозрачную область нажатия ровно по нему.
      node.classList.add('empty');
      const free = room.you.seatIndex === null || state.isAdmin;
      if (free) node.classList.add('joinable');
      const slot = document.createElement('div');
      slot.className = 'seat-empty-slot';
      if (free) {
        slot.addEventListener('click', () => {
          haptic('light');
          if (state.isAdmin) openBotSheet(seat.index); else openBuyIn(seat.index);
        });
      }
      node.appendChild(slot);
      container.appendChild(node);
      return;
    }

    // ЭТАЛОННЫЙ БЛОК: собираем заново только среднее левое место (кружок 2)
    // по замерам с эталонного макета. Остальные семь пока живут по-старому.
    // Один блок на все места. Геометрия — от диаметра нарисованного кружка:
    // аватар, оправа, плашка и значок считаются от --d, а карты и ставка
    // зеркалятся по стороне стола (data-side).
    {
      const circle = SEAT_CIRCLES[anchor.at];
      const d = circle.rout * 2 - 3;
      node.style.setProperty('--d', `${d.toFixed(2)}px`);
      node.style.setProperty('--rin', `${circle.rin}px`);
      node.style.setProperty('--rout', `${circle.rout}px`);
      node.dataset.side = anchor.at === 0 ? 'hero' : anchor.at === 4 ? 'top' : anchor.at <= 3 ? 'left' : 'right';
      // Значок масти нарисован на ассете и потому лежит ПОД аватаром. Кладём
      // поверх его копию с альфой (img/badge-N.png): вырезана из ассета по
      // положению, найденному корреляцией с шаблоном, поэтому ложится
      // пиксель в пиксель на нарисованный.
      node.style.setProperty('--bw', `${circle.badge.w}px`);
      node.style.setProperty('--bh', `${circle.badge.h}px`);
      node.style.setProperty('--bdx', `${circle.badge.dx}px`);
      node.style.setProperty('--bdy', `${circle.badge.dy}px`);
      node.style.setProperty('--badge-img', `url('/img/badge-${anchor.at}.png')`);
      // Оправа — вырезка неонового кольца из того же ассета (img/ring-N.png),
      // ложится пиксель в пиксель на нарисованное, но ПОВЕРХ аватара.
      node.style.setProperty('--ring-img', `url('/img/ring-${anchor.at}.png')`);
      node.style.setProperty('--ring-size', `${circle.ring.size}px`);
      node.style.setProperty('--rdx', `${circle.ring.dx}px`);
      node.style.setProperty('--rdy', `${circle.ring.dy}px`);
      const badge = document.createElement('i');
      badge.className = 'seat-badge';
      node.appendChild(badge);
      // Золотая оправа поверх аватара: у нарисованного кольца правая половина
      // тёмная, и фото её закрывало. Порядок: аватар → оправа → карты.
      const ring = document.createElement('i');
      ring.className = 'seat-ring';
      node.appendChild(ring);
    }

    if (isHero) node.classList.add('me');
    // Только что сел — анимируем появление содержимого места, один раз.
    if (!state.fx.seated.has(seat.userId)) node.classList.add('is-new');
    if (seat.folded) node.classList.add('folded');
    if (seat.isActing) node.classList.add('acting');
    if (!seat.connected || seat.sittingOut) node.classList.add('away');
    if (!seat.connected) node.classList.add('offline');
    else if (seat.sittingOut) node.classList.add('sitting-out');
    if (seat.allIn) node.classList.add('allin');
    if (seat.inHand && !seat.folded && !seat.isActing && seat.lastAction) node.classList.add('acted');
    if (winnerIds.has(seat.userId)) node.classList.add('winner');

    room.__rout = crocActive() ? 17 : SEAT_CIRCLES[anchor.at].rout;
    const avatarEl = avatarNode(seat, room);
    node.appendChild(avatarEl);
    if (avatarEl.__turnRing) node.appendChild(avatarEl.__turnRing);
    for (const mark of avatarEl.__marks || []) node.appendChild(mark);

    const plate = document.createElement('div');
    plate.className = 'seat-plate';
    const stack = seat.allIn
      ? '<div class="seat-stack allin">ALL-IN</div>'
      : `<div class="seat-stack">${money(seat.stack)}</div>`;
    plate.innerHTML = `<div class="seat-name">${escapeHtml(seat.name)}</div>${stack}`;
    if (state.isAdmin) {
      node.classList.add('clickable');
      plate.addEventListener('click', () => seat.isBot ? openBotSheet(seat.index) : openChipsSheet(seat));
    }
    node.appendChild(plate);

    if (seat.cards) node.appendChild(buildSeatCards(seat, position, count));

    // Ярлык силы руки — только у героя и только один на весь экран.
    if (isHero && seat.combination) {
      const label = document.createElement('div');
      label.className = 'hand-label';
      label.textContent = shortHand(seat.combination);
      node.appendChild(label);
    }

    if (seat.bet > 0) {
      const bet = document.createElement('div');
      bet.className = 'seat-bet';
      if (state.fx.bets.get(seat.index) !== seat.bet) bet.classList.add('is-new');
      bet.appendChild(chipStack(seat.bet));
      const sum = document.createElement('b');
      sum.textContent = shortMoney(seat.bet);
      bet.appendChild(sum);
      node.appendChild(bet);
    }

    container.appendChild(node);
  });
  state.fx.seated = seatedNow;
}

function avatarNode(seat, room) {
  const avatar = document.createElement('div');
  avatar.className = 'seat-avatar';
  if (seat.photoUrl) {
    const img = document.createElement('img');
    img.addEventListener('error', () => {
      img.remove();
      avatar.textContent = (seat.name || '?').trim()[0].toUpperCase();
    }, { once: true });
    img.src = seat.photoUrl;
    img.alt = '';
    avatar.appendChild(img);
  } else {
    avatar.textContent = (seat.name || '?').trim()[0].toUpperCase();
  }

  // Кольцо-прогресс — после буквы: textContent затирает всех детей,
  // поэтому раньше него класть нельзя. Бейджи идут следом и остаются сверху.
  if (seat.isActing && room && room.turnDeadline) {
    const ring = turnRing(room, room.__rout || 26);
    if (ring) avatar.__turnRing = ring;
  }

  // Блайнды и баттон — бейджами на аватаре, как за живым столом.
  // Фишки дилера и блайндов вешаем на узел места, а не внутрь аватара:
  // у аватара overflow:hidden, и они резались кружком в золотые «обмылки».
  const marks = [];
  if (seat.isBigBlind) marks.push(badge('bb', 'BB'));
  else if (seat.isSmallBlind) marks.push(badge('sb', 'SB'));
  if (seat.isDealer) marks.push(badge('d', 'D'));
  avatar.__marks = marks;
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

// ——— Анимации стола ———
// Всё, что двигается на сукне: прилёт карт, фишки к банку и обратно,
// кольцо-таймер на аватаре. Держится на transform/opacity и на разнице
// между прошлым и новым состоянием, которое прислал сервер.

function reducedMotion() {
  return Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

// Слой для летящих фишек. Создаём из скрипта, чтобы не трогать разметку;
// собственного transform у слоя нет — координаты холста остаются прежними.
function fxLayer() {
  const canvas = $('table-canvas');
  if (!canvas) return null;
  let layer = canvas.querySelector('.fx-layer');
  if (!layer) {
    layer = document.createElement('div');
    layer.className = 'fx-layer';
    canvas.appendChild(layer);
  }
  return layer;
}

// Масштаб холста: getBoundingClientRect отдаёт экранные пиксели, а внутри
// холста мы считаем в его собственных, до scale().
function canvasScale(rect) {
  return rect && rect.width ? rect.width / TABLE.width : 0;
}

// Точка банка в координатах холста. Пока банк не показан, помним прошлую.
function potPoint() {
  const canvas = $('table-canvas');
  const pot = $('pot');
  const fallback = state.fx.potPoint
    || { x: TABLE.width * TABLE.focusX, y: TABLE.height * TABLE.focusY };
  if (!canvas || !pot || pot.classList.contains('hidden')) return fallback;
  const box = canvas.getBoundingClientRect();
  const scale = canvasScale(box);
  if (!scale) return fallback;
  const rect = pot.getBoundingClientRect();
  const point = {
    x: (rect.left + rect.width / 2 - box.left) / scale,
    y: (rect.top + rect.height / 2 - box.top) / scale,
  };
  state.fx.potPoint = point;
  return point;
}

// Летящая фишка: живёт ровно столько, сколько идёт анимация.
function flyChip(from, to, options = {}) {
  if (!from || !to || reducedMotion()) return;
  const layer = fxLayer();
  if (!layer) return;
  const duration = options.duration || 260;
  const delay = options.delay || 0;
  const chip = document.createElement('div');
  chip.className = `fx-chip${options.kind ? ` ${options.kind}` : ''}${options.chip ? ' coin' : ''}`;
  if (options.chip) {
    // Летит одна фишка старшего номинала — представитель стопки.
    const stack = chipStack(options.chip);
    while (stack.children.length > 1) stack.lastChild.remove();
    chip.appendChild(stack);
  } else if (options.text) {
    chip.textContent = options.text;
  }
  chip.style.setProperty('--fx-x0', `${from.x.toFixed(1)}px`);
  chip.style.setProperty('--fx-y0', `${from.y.toFixed(1)}px`);
  chip.style.setProperty('--fx-x1', `${to.x.toFixed(1)}px`);
  chip.style.setProperty('--fx-y1', `${to.y.toFixed(1)}px`);
  chip.style.setProperty('--fx-dur', `${duration}ms`);
  chip.style.setProperty('--fx-delay', `${delay}ms`);
  layer.appendChild(chip);
  const remove = () => chip.remove();
  chip.addEventListener('animationend', remove);
  // Во вкладке в фоне animationend может не прийти — подстраховываемся.
  setTimeout(remove, duration + delay + 500);
}

// Короткий толчок банка, когда фишки долетели.
function bumpPot(delay = 0) {
  const pot = $('pot');
  if (!pot || reducedMotion()) return;
  setTimeout(() => {
    if (pot.classList.contains('hidden')) return;
    pot.classList.remove('is-bump');
    void pot.offsetWidth; // перезапуск анимации
    pot.classList.add('is-bump');
  }, delay);
}

// Кольцо-прогресс вокруг аватара того, чей ход. Сервер присылает
// turnDeadline и settings.turnSeconds, поэтому таймер настоящий:
// один переход stroke-dashoffset на весь остаток времени, без таймеров в JS.
// Кольцо-таймер лежит СНАРУЖИ золотой оправы места и концентрично ей:
// радиус берётся из подгонки кольца (rout) плюс зазор, а не из константы —
// иначе на кружках разного диаметра оно съезжало с оправы.
function turnRing(room, rout = 26) {
  const total = (room.settings && room.settings.turnSeconds) * 1000;
  const left = room.turnDeadline - Date.now();
  if (!total || left <= 0) return null;
  const RING_RADIUS = rout + 2.1;
  const RING_LENGTH = 2 * Math.PI * RING_RADIUS;
  const SIZE = Math.ceil(RING_RADIUS * 2 + 8);
  const ratio = clamp(left / total, 0, 1);

  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('class', `turn-ring${ratio < 0.25 ? ' is-low' : ''}`);
  svg.setAttribute('viewBox', `0 0 ${SIZE} ${SIZE}`);
  svg.style.width = `${SIZE}px`;
  svg.style.height = `${SIZE}px`;
  for (const kind of ['track', 'bar']) {
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('class', kind);
    circle.setAttribute('cx', String(SIZE / 2));
    circle.setAttribute('cy', String(SIZE / 2));
    circle.setAttribute('r', String(RING_RADIUS));
    if (kind === 'bar') {
      circle.style.strokeDasharray = String(RING_LENGTH);
      circle.style.strokeDashoffset = String(RING_LENGTH * (1 - ratio));
      if (!reducedMotion()) {
        requestAnimationFrame(() => {
          circle.style.transition = `stroke-dashoffset ${Math.round(left)}ms linear`;
          circle.style.strokeDashoffset = String(RING_LENGTH);
        });
      }
    }
    svg.appendChild(circle);
  }
  return svg;
}

// Карты выигравшей комбинации — только после вскрытия, когда сервер их
// действительно показал.
function computeWinCards(room) {
  const cards = new Set();
  const result = room.lastResult;
  if (!result || !result.showdown || room.status === 'playing' || room.status === 'betting') return cards;
  for (const winner of result.winners || []) {
    for (const card of (winner.hand && winner.hand.cards) || []) cards.add(card);
  }
  return cards;
}

function winnerIdSet(room) {
  const ids = new Set();
  const result = room.lastResult;
  if (!result || room.status === 'playing' || room.status === 'betting') return ids;
  for (const winner of result.winners || []) ids.add(winner.userId);
  return ids;
}

// Кто победил, в местах: для холдема по userId, для блекджека — по имени
// (в его результате id победителя не приходит).
function winnerSeats(room) {
  const result = room.lastResult;
  if (!result || room.status === 'playing' || room.status === 'betting') return [];
  if (result.game === 'blackjack') {
    if (!result.winnerName) return [];
    const seat = room.seats.find((s) => !s.empty && s.name === result.winnerName);
    return seat ? [{ index: seat.index, amount: result.amount }] : [];
  }
  return (result.winners || [])
    .map((winner) => {
      const seat = room.seats.find((s) => !s.empty && s.userId === winner.userId);
      return seat ? { index: seat.index, amount: winner.amount } : null;
    })
    .filter(Boolean);
}

// Главная точка входа: сравниваем новое состояние с прошлым и запускаем то,
// что произошло между ними.
function runTableFx(room) {
  const fx = state.fx;
  const firstSight = fx.hand === null;
  if (fx.hand !== room.handNumber) {
    fx.hand = room.handNumber;
    fx.winKey = null;
    fx.bets.clear();
  }

  const bets = new Map();
  for (const seat of room.seats) {
    if (!seat.empty) bets.set(seat.index, seat.bet || 0);
  }

  // Пришли в комнату посреди раздачи — просто запоминаем, что видим.
  if (firstSight || reducedMotion()) {
    fx.bets = bets;
    return;
  }

  const pot = potPoint();
  let wasBet = 0;
  let nowBet = 0;
  for (const value of fx.bets.values()) wasBet += value;
  for (const value of bets.values()) nowBet += value;

  // 1. Игрок поставил — стопка появляется у места и чуть подъезжает к
  //    банку (анимация bet-pop на самом блоке ставки, см. styles.css).
  //    Отдельного полёта от аватара нет: две анимации одной ставки
  //    читались как две ставки.

  // 2. Улица закрылась — фишки уезжают со своих якорей в банк, по одной
  //    представительной фишке старшего номинала от каждого, с шагом 40 мс.
  if (wasBet > 0 && nowBet === 0) {
    let order = 0;
    for (const [index, value] of fx.bets) {
      const point = fx.points.get(index);
      if (!point || value <= 0) continue;
      flyChip(point.bet, pot, { chip: value, duration: 300, delay: order * 40 });
      order += 1;
    }
    if (order) bumpPot(220 + order * 40);
  }

  fx.bets = bets;

  // 3. Раздача закончилась — банк уезжает к победителям.
  const winners = winnerSeats(room);
  const winKey = winners.length ? `${room.handNumber}:${winners.map((w) => `${w.index}/${w.amount}`).join(',')}` : null;
  if (winKey && winKey !== fx.winKey) {
    fx.winKey = winKey;
    winners.forEach((winner, index) => {
      const point = fx.points.get(winner.index);
      if (!point) return;
      flyChip(pot, point.seat, {
        text: `+${money(winner.amount)}`,
        kind: 'win',
        duration: 320,
        delay: 260 + index * 70,
      });
    });
  }
}

// Вектор прилёта карты: от центра стола до её места. Меряем до того, как
// анимация стартует (класс is-priming её придерживает), иначе прочитаем
// уже сдвинутый прямоугольник.
function primeDealAnimations() {
  const canvas = $('table-canvas');
  if (!canvas) return;
  const nodes = canvas.querySelectorAll('.card-face.is-priming');
  if (!nodes.length) return;

  const box = canvas.getBoundingClientRect();
  const scale = canvasScale(box);
  if (!scale) {
    for (const node of nodes) node.classList.remove('is-priming');
    return;
  }

  const fromX = box.left + box.width * TABLE.focusX;
  const fromY = box.top + box.height * TABLE.focusY;
  // Сначала все замеры, потом все записи: так layout считается один раз.
  const measured = [];
  for (const node of nodes) {
    const rect = node.getBoundingClientRect();
    measured.push([
      node,
      (fromX - rect.left - rect.width / 2) / scale,
      (fromY - rect.top - rect.height / 2) / scale,
    ]);
  }
  for (const [node, dx, dy] of measured) {
    node.style.setProperty('--deal-x', `${dx.toFixed(1)}px`);
    node.style.setProperty('--deal-y', `${dy.toFixed(1)}px`);
    node.classList.remove('is-priming');
  }
}

function renderMessage(room) {
  const node = $('table-message');
  const seated = room.seats.filter((s) => !s.empty).length;

  // Подсказка «сядьте за стол» — отдельной плашкой под столом.
  const canSit = room.you.seatIndex === null && room.seats.some((s) => s.empty) && !state.buyIn.open;
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
    // Сидящему герою про это говорит строка «Ожидаем игроков» внизу.
    node.textContent = room.you.seatIndex === null ? 'Нужно минимум два игрока' : '';
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
  // Пришло новое состояние — значит, сервер ответил: колечки гасим.
  clearBusy();
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

  // Панель выбора суммы (посадка или пополнение) — вместо кнопок и баланса.
  const picker = state.buyIn.open && you.buyIn && !myTurn
    && (state.buyIn.mode === 'rebuy' ? (seated && you.canRebuy) : !seated);
  if (!picker) state.buyIn.open = false;
  renderBuyIn(room, Boolean(picker));
  if (picker) { sitBtn.classList.add('hidden'); rebuyBtn.classList.add('hidden'); }

  const seatBox = $('seat-controls');
  const seatButtonsVisible = [sitBtn, rebuyBtn].some((b) => !b.classList.contains('hidden'));
  seatBox.classList.toggle('hidden', myTurn || !seatButtonsVisible);

  // Сел и ждёт соперников — строка внизу вместо текста на столе.
  const alone = seated && room.status === 'waiting' && room.seats.filter((s) => !s.empty).length < 2;
  $('wait-line').classList.toggle('hidden', !alone);

  // Пока игрок не за столом, показываем баланс: хватит ли на вход.
  const chip = $('balance-chip');
  const minBuy = (you.buyIn && you.buyIn.min) || room.settings.minBuyIn || room.settings.buyIn;
  const short = !seated && you.balance < minBuy;
  chip.classList.toggle('hidden', seated || myTurn || Boolean(picker));
  chip.innerHTML = short
    ? `Недостаточно средств: на балансе <b>${money(you.balance)}</b>, вход от <b>${money(minBuy)}</b>. Пополните баланс на главной`
    : `На балансе <b>${money(you.balance)}</b> · вход от <b>${money(minBuy)}</b>`;
  if (short) sitBtn.classList.add('hidden');

  if (room.game === 'blackjack') {
    renderBlackjackControls(room);
    return;
  }

  // Панель действий появляется только на своём ходу.
  const legal = you.legal;
  const bar = $('action-bar');
  if (!legal) {
    bar.classList.add('hidden');
    closeRaisePanel();
    stopTurnTimer();
    syncControls();
    return;
  }

  bar.classList.remove('hidden');
  $('btn-fold').classList.toggle('hidden', !legal.canFold);
  $('btn-check').classList.toggle('hidden', !legal.canCheck);

  const callBtn = $('btn-call');
  callBtn.classList.toggle('hidden', !legal.canCall);
  $('call-amount').textContent = money(legal.callAmount);

  const context = `${room.code}:${room.handNumber}:${room.phase}:${room.turnDeadline}`;
  if (state.raiseContext !== context) closeRaisePanel();
  state.raiseContext = context;
  $('btn-raise').classList.remove('hidden');
  $('btn-raise').disabled = !legal.canRaise;
  $('btn-allin').classList.remove('hidden');
  $('btn-allin').disabled = !legal.canAllIn;
  $('allin-amount').textContent = money(you.stack);
  if (legal.canRaise) {
    const range = $('raise-range');
    range.min = String(legal.minRaiseTo);
    range.max = String(legal.maxRaiseTo);
    range.step = '1';
    if (!state.raiseTouched) state.raiseTo = legal.minRaiseTo;
    state.raiseTo = clamp(state.raiseTo, legal.minRaiseTo, legal.maxRaiseTo);
    range.value = String(state.raiseTo);
    renderRaiseValue(legal);
  } else closeRaisePanel();
  $('bet-row').classList.toggle('hidden', !state.raiseOpen || !legal.canRaise);
  $('btn-raise').setAttribute('aria-expanded', String(state.raiseOpen));

  startTurnTimer(room);
  syncControls();
}

// ——— Выбор суммы входа ———

const BUYIN_PRESETS = [500, 1000, 2500, 5000];

function openBuyIn(seatIndex, mode = 'sit') {
  const room = state.room;
  if (!room) return;
  if (mode === 'sit' && room.you.seatIndex !== null) return;
  if (mode === 'rebuy' && !room.you.canRebuy) return;
  const range = room.you.buyIn;
  if (range && !range.enough) {
    toast('Недостаточно средств');
    haptic('error');
  }
  state.buyIn.open = true;
  state.buyIn.mode = mode;
  state.buyIn.seat = seatIndex;
  state.buyIn.touched = false;
  renderControls(room);
}

function closeBuyIn() {
  state.buyIn.open = false;
  if (state.room) renderControls(state.room);
}

function renderBuyIn(room, open) {
  const panel = $('buyin-panel');
  panel.classList.toggle('hidden', !open);
  if (!open) return;
  const range = room.you.buyIn;
  const rebuy = state.buyIn.mode === 'rebuy';
  panel.querySelector('.buyin-head span').textContent = rebuy ? 'На сколько пополнить стек' : 'С какой суммой сесть';
  $('buyin-balance').textContent = `Баланс ${money(room.you.balance)}`;
  const enough = Boolean(range && range.enough);
  $('buyin-short').classList.toggle('hidden', enough);
  $('buyin-slider').classList.toggle('hidden', !enough);
  $('buyin-presets').classList.toggle('hidden', !enough);
  $('buyin-confirm').classList.toggle('hidden', !enough);
  if (!enough) return;

  const input = $('buyin-range');
  input.min = String(range.min);
  input.max = String(range.max);
  input.step = String(Math.max(1, Math.min(50, Math.floor((range.max - range.min) / 20) || 1)));
  if (!state.buyIn.touched) state.buyIn.amount = range.default;
  state.buyIn.amount = clamp(state.buyIn.amount, range.min, range.max);
  input.value = String(state.buyIn.amount);

  const presets = $('buyin-presets');
  presets.innerHTML = '';
  for (const value of BUYIN_PRESETS.filter((v) => v >= range.min && v <= range.max)) {
    const button = document.createElement('button');
    button.className = 'ab-preset';
    button.textContent = `$${value / 100}`;
    button.dataset.buyin = String(value);
    button.addEventListener('click', () => setBuyIn(value));
    presets.appendChild(button);
  }
  const max = document.createElement('button');
  max.className = 'ab-preset';
  max.textContent = 'MAX';
  max.dataset.buyin = String(range.max);
  max.addEventListener('click', () => setBuyIn(range.max));
  presets.appendChild(max);
  renderBuyInValue();
}

function setBuyIn(value) {
  const range = state.room && state.room.you.buyIn;
  if (!range) return;
  state.buyIn.touched = true;
  state.buyIn.amount = clamp(value, range.min, range.max);
  $('buyin-range').value = String(state.buyIn.amount);
  renderBuyInValue();
  haptic('light');
}

function stepBuyIn(direction) {
  const range = state.room && state.room.you.buyIn;
  if (!range) return;
  setBuyIn(state.buyIn.amount + direction * 100);
}

function renderBuyInValue() {
  const range = state.room && state.room.you.buyIn;
  if (!range) return;
  const value = money(state.buyIn.amount);
  $('buyin-value').textContent = value;
  $('buyin-confirm').textContent = state.buyIn.mode === 'rebuy' ? `Пополнить на ${value}` : `Сесть с ${value}`;
  const t = range.max > range.min ? (state.buyIn.amount - range.min) / (range.max - range.min) : 0;
  $('buyin-slider').style.setProperty('--t', t.toFixed(4));
  for (const button of $('buyin-presets').querySelectorAll('[data-buyin]')) {
    button.classList.toggle('is-active', Number(button.dataset.buyin) === state.buyIn.amount);
  }
}

// Подвал прячем целиком, когда в нём нечего показывать: иначе под столом
// висит пустая полоса, а фон казино должен продолжаться до низа экрана.
function syncControls() {
  const box = document.querySelector('#screen-table .controls');
  if (!box) return;
  const visible = Array.from(box.children).some((el) => !el.classList.contains('hidden'));
  box.classList.toggle('is-empty', !visible);
}

function renderRaiseValue(legal) {
  if (!legal) return;
  $('raise-confirm').disabled = false;
  $('raise-value').textContent = money(state.raiseTo);
  $('raise-confirm').textContent = `Рейз до ${money(state.raiseTo)}`;
  $('raise-label').textContent = 'Raise';
  if (document.activeElement !== $('raise-input')) $('raise-input').value = (state.raiseTo / 100).toFixed(2);
  const lo = legal.minRaiseTo, hi = legal.maxRaiseTo;
  $('bet-slider').style.setProperty('--t', String(hi > lo ? (state.raiseTo - lo) / (hi - lo) : 0));
  for (const button of document.querySelectorAll('[data-preset]')) {
    button.classList.toggle('is-active', button.dataset.preset === state.raisePreset);
    const label = button.querySelector('strong');
    if (label) label.textContent = money(presetRaiseTo(button.dataset.preset));
  }
}

function closeRaisePanel() {
  state.raiseOpen = false;
  state.raiseTouched = false;
  state.raisePreset = null;
  $('bet-row').classList.add('hidden');
  $('btn-raise').setAttribute('aria-expanded', 'false');
}

// Шаг кнопок −/+ — большой блайнд.
function stepRaise(direction) {
  const room = state.room;
  const legal = room && room.you.legal;
  if (!legal || !legal.canRaise) return;
  const step = Math.max(1, room.settings.bigBlind || 1);
  state.raiseTouched = true;
  state.raisePreset = null;
  state.raiseTo = clamp(state.raiseTo + direction * step, legal.minRaiseTo, legal.maxRaiseTo);
  $('raise-range').value = String(state.raiseTo);
  renderRaiseValue(legal);
  haptic('light');
}

function renderBlackjackControls() {
  // Табличного блекджека больше нет — он одиночный (см. renderBlackjack).
  $('action-bar').classList.add('hidden');
  stopTurnTimer();
  syncControls();
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
  bindHilo();
  bindCrash();
  bindArcade();
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

  // Главная и «Игры»: столы заведения всегда открыты — садимся сразу.
  const openGame = (game) => {
    const room = state.rooms.find((r) => r.house && r.game === game);
    if (room) {
      send({ type: 'join_room', code: room.code });
      return;
    }
    send({ type: 'list_rooms' });
    toast('Стол открывается — секунду');
  };
  on('play-holdem', 'click', () => { haptic('light'); openGame('holdem'); });
  on('play-omaha', 'click', () => { haptic('light'); openGame('omaha'); });
  on('play-blackjack', 'click', () => { haptic('light'); openBlackjack(); });
  on('play-roulette', 'click', () => { haptic('light'); openRoulette(); });
  on('play-baccarat', 'click', () => { haptic('light'); openBaccarat(); });
  on('play-mines', 'click', () => { haptic('light'); openMines(); });
  on('play-nvuti', 'click', () => { haptic('light'); openNvuti(); });
  on('nv-back', 'click', closeNvuti);
  on('nv-main', 'click', onNvutiMain);
  on('nv-swap', 'click', () => nvSetMode(state.nv.mode === 'under' ? 'over' : 'under'));
  on('nv-half', 'click', () => nvAdjust((amount) => Math.floor(amount / 2)));
  on('nv-double', 'click', () => nvAdjust((amount) => amount * 2));
  on('nv-max', 'click', () => nvAdjust(() => Infinity));
  $('nv-amount').addEventListener('input', () => nvReadAmount());
  $('nv-amount').addEventListener('blur', () => { nvReadAmount(); nvWriteAmount(); });
  $('nv-amount').addEventListener('keydown', (event) => { if (event.key === 'Enter') event.currentTarget.blur(); });
  $('nv-mode').addEventListener('change', (event) => nvSetMode(event.currentTarget.value));
  bindNvutiScale();
  on('mn-back', 'click', closeMines);
  on('mn-main', 'click', onMinesMain);
  on('mn-half', 'click', () => mnAdjust((amount) => Math.floor(amount / 2)));
  on('mn-double', 'click', () => mnAdjust((amount) => amount * 2));
  on('mn-max', 'click', () => mnAdjust(() => Infinity));
  $('mn-amount').addEventListener('input', () => mnReadAmount());
  $('mn-amount').addEventListener('blur', () => { mnReadAmount(); mnWriteAmount(); });
  $('mn-amount').addEventListener('keydown', (event) => { if (event.key === 'Enter') event.currentTarget.blur(); });
  $('mn-mines').addEventListener('change', (event) => { state.mn.mines = Number(event.currentTarget.value); renderMines(); });
  on('bc-back', 'click', closeBaccarat);
  on('bc-clear', 'click', () => { if (state.bc.dealing) return; state.bc.bets.clear(); haptic('light'); renderBaccarat(); });
  document.querySelectorAll('.bc-zone').forEach((zone) => {
    zone.addEventListener('click', () => placeBcBet(zone.dataset.zone, zone));
  });
  on('bc-place', 'click', (event) => {
    if (state.bc.dealing || !state.bc.bets.size) return;
    markBusy(event.currentTarget);
    send({ type: 'bc_bet', bets: Array.from(state.bc.bets, ([zone, amount]) => ({ zone, amount })) });
  });
  on('rl-back', 'click', closeRoulette);
  on('rl-minus', 'click', () => stepRlAmount(-1));
  on('rl-plus', 'click', () => stepRlAmount(1));
  on('rl-amount', 'click', () => openRlKeypad());
  document.querySelectorAll('#rl-keypad [data-key]').forEach((button) => {
    button.addEventListener('click', (event) => { event.stopPropagation(); rlKey(button.dataset.key); });
  });
  $('screen-rl').addEventListener('pointerdown', (event) => {
    if (!state.rl.typing) return;
    if (event.target.closest('#rl-keypad') || event.target.closest('#rl-amount')) return;
    closeRlKeypad(true);
  });
  on('rl-spin', 'click', (event) => {
    if (state.rl.spinning || !state.rl.bets.size) return;
    markBusy(event.currentTarget);
    send({ type: 'rl_spin', bets: Array.from(state.rl.bets.values()).map((b) => ({ type: b.type, value: b.value, amount: b.amount })) });
  });
  on('rl-clear', 'click', () => { state.rl.bets.clear(); haptic('light'); renderRoulette(); });
  on('bj-back', 'click', closeBlackjack);
  on('bj-minus', 'click', () => stepBjBet(-1));
  on('bj-plus', 'click', () => stepBjBet(1));
  // Сумму можно написать руками: тап по полю открывает свою панель цифр.
  on('bj-bet-amount', 'click', () => openBjKeypad());
  document.querySelectorAll('#bj-keypad [data-key]').forEach((button) => {
    button.addEventListener('click', (event) => { event.stopPropagation(); bjKey(button.dataset.key); });
  });
  // Тап мимо панели — применяем набранное и закрываем.
  $('screen-bj').addEventListener('pointerdown', (event) => {
    if (!state.bj.typing) return;
    if (event.target.closest('#bj-keypad') || event.target.closest('#bj-bet-amount')) return;
    closeBjKeypad(true);
  });
  on('bj-deal', 'click', (event) => {
    markBusy(event.currentTarget);
    send({ type: 'bj_bet', amount: state.bj.bet });
  });
  on('bj-next', 'click', () => {
    state.bj.dealerShown = [];
    $('bj-dealer-cards').innerHTML = '';
    send({ type: 'bj_next' });
  });
  document.querySelectorAll('.bj-act[data-action]').forEach((button) => {
    button.addEventListener('click', () => {
      haptic('light');
      send({ type: 'bj_action', action: button.dataset.action });
    });
  });
  on('profile-topup', 'click', () => $('btn-topup').click());
  on('profile-payout', 'click', () => $('btn-payout').click());
  on('hero-play', 'click', () => { haptic('light'); openGame('holdem'); });
  on('games-all', 'click', () => showTab('games'));
  for (const card of document.querySelectorAll('.mk-game[data-soon]')) {
    card.addEventListener('click', () => toast(`${card.dataset.soon} — скоро`));
  }
  on('wins-all', 'click', () => toast('Полная лента выигрышей — скоро'));
  for (const card of document.querySelectorAll('.lb-game[data-open], .mk-game[data-open]')) {
    card.addEventListener('click', () => { haptic('light'); openGame(card.dataset.open); });
  }
  on('tour-more', 'click', () => showTab('tournaments'));
  on('tour-to-games', 'click', () => showTab('games'));
  on('profile-history', 'click', () => {
    if (togglePanel('history-card')) send({ type: 'history' });
  });
  on('profile-help', 'click', () => togglePanel('help-card'));
  on('profile-copy', 'click', () => $('btn-my-id').click());
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

  on('btn-start', 'click', (event) => {
    markBusy(event.currentTarget);
    send({ type: 'start' });
  });
  on('btn-sit', 'click', () => {
    const free = state.room && state.room.seats.find((s) => s.empty);
    if (free) openBuyIn(free.index);
    else toast('Свободных мест нет');
  });
  on('buyin-cancel', 'click', closeBuyIn);
  on('buyin-confirm', 'click', (event) => {
    const range = state.room && state.room.you.buyIn;
    if (!range || !range.enough) return;
    markBusy(event.currentTarget);
    if (state.buyIn.mode === 'rebuy') send({ type: 'rebuy', amount: state.buyIn.amount });
    else send({ type: 'sit', seat: state.buyIn.seat, amount: state.buyIn.amount });
    state.buyIn.open = false;
  });
  on('buyin-range', 'input', (event) => {
    state.buyIn.touched = true;
    state.buyIn.amount = Number(event.target.value);
    renderBuyInValue();
  });
  on('buyin-minus', 'click', () => stepBuyIn(-1));
  on('buyin-plus', 'click', () => stepBuyIn(1));
  on('btn-rebuy', 'click', () => openBuyIn(null, 'rebuy'));

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

  on('btn-fold', 'click', (event) => act('fold', undefined, event.currentTarget));
  on('btn-check', 'click', (event) => act('check', undefined, event.currentTarget));
  on('btn-call', 'click', (event) => act('call', undefined, event.currentTarget));
  on('btn-raise', 'click', (event) => {
    const legal = state.room && state.room.you.legal;
    if (!legal?.canRaise) return;
    state.raiseOpen = !state.raiseOpen;
    renderControls(state.room);
    haptic('light');
  });
  on('raise-minus', 'click', () => stepRaise(-1));
  on('raise-plus', 'click', () => stepRaise(1));
  on('raise-cancel', 'click', closeRaisePanel);
  on('raise-confirm', 'click', event => {
    if (state.raiseOpen && state.room?.you.legal?.canRaise) act('raise', state.raiseTo, event.currentTarget);
  });
  on('btn-allin', 'click', event => {
    if (state.room?.you.legal?.canAllIn) act('allin', undefined, event.currentTarget);
  });
  on('raise-input', 'input', event => {
    const legal = state.room?.you.legal;
    const raw = event.target.value.trim().replace(',', '.');
    if (!legal?.canRaise) return;
    const valid = /^\d+(?:\.\d{0,2})?$/.test(raw);
    $('raise-confirm').disabled = !valid;
    if (!valid) return;
    state.raiseTouched = true;
    state.raisePreset = null;
    state.raiseTo = clamp(Math.round(Number(raw) * 100), legal.minRaiseTo, legal.maxRaiseTo);
    $('raise-range').value = String(state.raiseTo);
    renderRaiseValue(legal);
  });
  on('raise-input', 'blur', () => { $('raise-input').value = (state.raiseTo / 100).toFixed(2); $('raise-confirm').disabled = false; });
  bindBotControls();

  on('raise-range', 'input', (event) => {
    state.raiseTouched = true;
    state.raisePreset = null;
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

function presetRaiseTo(preset) {
  const room = state.room;
  const legal = room && room.you.legal;
  if (!legal || !legal.canRaise) return 0;

  const mySeat = room.seats[room.you.seatIndex];
  const myBet = mySeat ? mySeat.bet : 0;
  // Банк после уравнивания — от него и считаем «половину» и «банк».
  const potAfterCall = room.potTotal + legal.callAmount;

  let value;
  if (preset === 'min') value = legal.minRaiseTo;
  else if (preset === 'max') value = legal.maxRaiseTo;
  else if (preset === 'half') value = myBet + legal.callAmount + Math.floor(potAfterCall / 2);
  else if (preset === 'twothirds') value = myBet + legal.callAmount + Math.floor(potAfterCall * 2 / 3);
  else if (preset === 'double') value = myBet + legal.callAmount + potAfterCall * 2;
  else value = myBet + legal.callAmount + potAfterCall;

  return clamp(value, legal.minRaiseTo, legal.maxRaiseTo);
}

function applyPreset(preset) {
  const legal = state.room?.you.legal;
  if (!legal?.canRaise) return;
  const value = presetRaiseTo(preset);
  state.raiseTouched = true;
  state.raisePreset = preset;
  state.raiseTo = clamp(value, legal.minRaiseTo, legal.maxRaiseTo);
  $('raise-range').value = String(state.raiseTo);
  renderRaiseValue(legal);
  for (const button of document.querySelectorAll('[data-preset]')) {
    button.classList.toggle('is-active', button.dataset.preset === preset);
  }
  haptic('light');
}

// button — кнопка, которую нажали: на время ожидания ответа она крутит
// колечко, а вся панель перестаёт принимать нажатия. Панель прячем не
// мгновенно, а после короткой паузы, иначе состояние «отправляем» никто
// не успевает увидеть.
function act(action, amount, button) {
  if ($('action-bar').classList.contains('is-sending')) return;
  closeRaisePanel();
  haptic(action === 'fold' ? 'light' : 'success');
  state.raiseTouched = false;
  const bar = (button && button.closest('.action-bar')) || $('action-bar');
  bar.classList.add('is-sending');
  if (button) button.classList.add('is-loading');
  send({ type: 'action', action, amount });
  setTimeout(() => {
    bar.classList.remove('is-sending');
    if (button) button.classList.remove('is-loading');
    // Если сервер уже прислал состояние и ход снова наш — панель нужна.
    const you = state.room && state.room.you;
    if (!you || (!you.legal && !you.betTurn)) bar.classList.add('hidden');
  }, 180);
}

// Кнопка ждёт ответа сервера. Снимается на следующем состоянии стола.
function markBusy(button) {
  if (!button) return;
  button.classList.add('is-loading');
}

function clearBusy() {
  for (const button of document.querySelectorAll('.btn.is-loading')) {
    button.classList.remove('is-loading');
  }
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

// Isolated visual experiment. No server/game state is changed by this toggle.
const crocOriginalTable = {...TABLE};
const crocOriginalStage = {...STAGE};
let crocEnabled = true;
try { crocEnabled = localStorage.getItem('poker-croc-theme-v1') !== 'off'; } catch {}
function crocActive() {
  return crocEnabled && (!state.room || ['holdem','omaha'].includes(state.room.game));
}
function syncCrocTheme() {
  const enabled = crocActive() && !amethystActive();
  syncAmethyst();
  $('screen-table').classList.toggle('croc-theme', enabled);
  Object.assign(TABLE, amethystActive() ? {width:768,height:1536,focusX:.5,focusY:.42} : enabled ? {width:390,height:600,focusX:.5,focusY:248.5/600} : crocOriginalTable);
  Object.assign(STAGE, enabled ? {sidePad:0,panelReserve:120,topGap:6} : crocOriginalStage);
  const button=$('btn-croc-theme');
  if(button){button.textContent=amethystActive()?'Прежний дизайн':'Новый дизайн';button.setAttribute('aria-pressed',String(amethystActive()));}
}
function crocAnchor(index,count) {
  const at=(SEAT_SETS[count]||SEAT_SETS[8])[index % (SEAT_SETS[count]||SEAT_SETS[8]).length];
  const centers=[[195,477],[69,416],[35,277],[69,125],[195,42],[321,125],[355,277],[321,416]];
  const bets=[[195,368],[103,379],[112,310],[139,168],[195,148],[251,168],[278,310],[287,379]];
  const [x,y]=centers[at], [bx,by]=bets[at];
  return {at,seat:[x/390,y/600],avatar:34,cards:[0,at===0?-53.5:67],bet:[bx-x,by-y],side:'center',betFrac:[bx/390,by/600]};
}
const crocButton=document.createElement('button');
crocButton.id='btn-croc-theme';crocButton.type='button';
crocButton.addEventListener('click',()=>{
  amethystEnabled=!amethystEnabled;
  try {localStorage.setItem('poker-amethyst-v1',amethystEnabled?'on':'off');}catch{}
  $('board').dataset.cards = '__theme_changed__';
  syncCrocTheme();
  if(state.room) renderTable();
  fitTable();
});
$('screen-table').appendChild(crocButton);
syncCrocTheme();

boot();
