'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const { attachWebSocketServer } = require('./wsserver');
const { verifyInitData } = require('./telegram');
const { Room, RoomError, normalizeSettings } = require('./room');
const { Accounts, AccountError, DEFAULT_START_BALANCE } = require('./accounts');
const { createPayments, PaymentError } = require('./payments');
const { formatMoney, parseMoney } = require('./money');
const { PromoCodes, PromoError } = require('./promo');
const { loadEnv } = require('./env');

loadEnv();

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const ROOM_TTL_MS = 30 * 60 * 1000; // пустую комнату держим полчаса
const HOUSE_SEAT_GRACE_MS = 90 * 1000; // отвалившийся игрок держит место за столом заведения полторы минуты
const WEBHOOK_PREFIX = '/pay/'; // /pay/<провайдер>/webhook
const MAX_WEBHOOK_BYTES = 64 * 1024; // тело вебхука заведомо меньше
const RECENT_WINS_LIMIT = 12; // лента «Последние выигрыши» на главной
const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // без похожих символов

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
};

// Создаёт независимый экземпляр приложения: свой список комнат и подключений.
function createApp(options = {}) {
  const botToken = options.botToken ?? process.env.TELEGRAM_BOT_TOKEN ?? '';
  // Без токена бота подпись initData проверить нечем — это режим локальной отладки.
  const devLogin = options.devLogin ?? (!botToken || process.env.ALLOW_DEV_LOGIN === '1');
  const botUsername = (options.botUsername ?? process.env.TELEGRAM_BOT_USERNAME ?? '').replace(/^@/, '');
  const appShortName = options.appShortName ?? process.env.TELEGRAM_APP_SHORT_NAME ?? '';
  // Ссылки на чат сообщества и поддержку. Не задано — карточка не появится,
  // чтобы на главной не было кнопок, ведущих в никуда.
  const communityUrl = options.communityUrl ?? process.env.COMMUNITY_URL ?? '';
  const supportUrl = options.supportUrl ?? process.env.SUPPORT_URL ?? '';

  const adminIds = options.adminIds
    ?? String(process.env.TELEGRAM_ADMIN_IDS || '').split(',').map((id) => id.trim()).filter(Boolean);
  // accountsFile: null означает «не сохранять на диск» (так гоняются тесты),
  // поэтому здесь именно проверка на undefined, а не ??.
  const accountsFile = options.accountsFile !== undefined
    ? options.accountsFile
    : path.join(process.env.DATA_DIR || path.join(__dirname, '..', 'data'), 'accounts.json');
  const accounts = options.accounts ?? new Accounts({
    file: accountsFile,
    startingBalance: Number(process.env.START_BALANCE || DEFAULT_START_BALANCE),
    admins: adminIds,
  });
  // Пополнение включается само, как только в окружении есть токен Crypto Bot
  // или xRocket. Нет токенов — раздел просто не показывается в лобби.
  const paymentsFile = options.paymentsFile !== undefined
    ? options.paymentsFile
    : path.join(process.env.DATA_DIR || path.join(__dirname, '..', 'data'), 'payments.json');
  const payments = options.payments ?? createPayments({ accounts, file: paymentsFile });

  const promoFile = options.promoFile !== undefined
    ? options.promoFile
    : path.join(process.env.DATA_DIR || path.join(__dirname, '..', 'data'), 'promo.json');
  const promo = options.promo ?? new PromoCodes({ accounts, file: promoFile });

  // Деньги дошли — говорим об этом владельцу счёта. Сам баланс прилетит
  // отдельным сообщением через accounts.onChange.
  payments.onCredit = (record) => {
    const client = clientsByUser.get(record.userId);
    if (!client) return;
    client.send({
      type: 'topup_paid',
      id: record.id,
      cents: record.creditedCents,
      amount: record.paidAmount ?? record.amount,
      currency: record.currency,
    });
    client.send({ type: 'system', text: `Баланс пополнен на ${formatMoney(record.creditedCents)}` });
  };

  // Вывод сменил состояние — сообщаем владельцу счёта.
  payments.onPayout = (record) => {
    const client = clientsByUser.get(record.userId);
    if (!client) return;
    client.send({ type: 'payout_status', payout: payments.payoutView(record) });
    if (record.status === 'done') {
      client.send({ type: 'system', text: `Выплата ${formatMoney(record.cents)} отправлена в ${record.currency}` });
    }
  };

  // Без токена бота приложение работает локально «для себя» — там админ каждый.
  const devAdmin = options.devAdmin ?? !botToken;
  const isAdmin = (user) => accounts.isAdmin(user.id) || (devAdmin && String(user.id).startsWith('dev:'));

  // Баланс изменился — сразу показываем это владельцу счёта.
  accounts.onChange = (account) => {
    const client = clientsByUser.get(account.id);
    if (!client) return;
    client.send({ type: 'balance', balance: account.balance });
    const room = client.roomCode ? rooms.get(client.roomCode) : null;
    if (room) client.send(room.stateFor(account.id));
  };

  const rooms = new Map(); // код -> Room
  const clientsByUser = new Map(); // id пользователя -> клиент
  // Последние выигрыши для главной. Живут в памяти: это витрина, а не отчёт.
  const recentWins = [];

  // ——— Комнаты ———

  function createRoomCode() {
    for (let attempt = 0; attempt < 50; attempt++) {
      let code = '';
      for (let i = 0; i < 5; i++) code += CODE_ALPHABET[crypto.randomInt(CODE_ALPHABET.length)];
      if (!rooms.has(code)) return code;
    }
    throw new RoomError('Не удалось выделить код комнаты, попробуйте ещё раз');
  }

  function registerRoom(room) {
    rooms.set(room.code, room);
    room.on('update', () => broadcastState(room));
    room.on('chat', (message) => broadcast(room, { type: 'chat', ...message }));
    room.on('win', (win) => {
      if (!win || win.amount <= 0) return;
      recentWins.unshift({ ...win, at: Date.now() });
      recentWins.length = Math.min(recentWins.length, RECENT_WINS_LIMIT);
    });
  }

  // ——— Постоянные столы ———
  // По одному открытому столу на игру: холдем и блекджек. Хозяин — само
  // заведение, поэтому раздачи стартуют сами, как только сели двое, а
  // уборщик такие столы не трогает: «участник» PokerGena всегда на связи.
  const HOUSE = { id: 'house', name: 'PokerGena', photoUrl: null };

  function createHouseTables() {
    const presets = [
      { game: 'holdem', smallBlind: 5, bigBlind: 10, buyIn: 1000, maxPlayers: 8, turnSeconds: 30, isPublic: true },
      { game: 'blackjack', minBet: 10, maxBet: 200, buyIn: 1000, turnSeconds: 30, isPublic: true },
    ];
    for (const preset of presets) {
      const room = new Room(createRoomCode(), HOUSE, preset, { bank: accounts });
      room.house = true;
      room.autoStart = true;
      room.title = preset.game === 'blackjack' ? 'Блекджек PokerGena' : 'Стол PokerGena';
      registerRoom(room);
    }
  }

  function markEmpty(room) {
    if (room.isEmpty) room.emptyAt = Date.now();
  }

  // Комнату держим, пока в ней кто-то есть на связи: столы с одними
  // отключившимися игроками тоже нужно убирать, иначе они копятся в памяти.
  const sweeper = setInterval(() => {
    const now = Date.now();
    for (const [code, room] of rooms) {
      if (room.house) {
        // Постоянный стол не удаляется, но отвалившихся игроков с него
        // снимаем: иначе места забьются «призраками», и сесть будет некуда.
        for (const seat of room.seats) {
          if (!seat || seat.connected || !seat.offlineAt) continue;
          if (now - seat.offlineAt < HOUSE_SEAT_GRACE_MS) continue;
          if (room.inActiveHand(seat.userId)) continue;
          room.removeMember(seat.userId);
        }
        continue;
      }
      const someoneOnline = [...room.members.values()].some((member) => member.connected);
      if (someoneOnline) {
        room.emptyAt = null;
        continue;
      }
      if (!room.emptyAt) room.emptyAt = now;
      if (now - room.emptyAt > ROOM_TTL_MS) {
        room.cashOutAll(); // фишки со стола не должны пропасть вместе с комнатой
        room.dispose();
        rooms.delete(code);
      }
    }
  }, 60 * 1000);
  sweeper.unref?.();

  createHouseTables();

  // ——— Рассылка ———

  function clientsInRoom(room) {
    return [...clientsByUser.values()].filter((client) => client.roomCode === room.code);
  }

  function broadcastState(room) {
    for (const client of clientsInRoom(room)) client.send(room.stateFor(client.user.id));
  }

  function broadcast(room, message) {
    for (const client of clientsInRoom(room)) client.send(message);
  }

  // ——— HTTP ———

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    if (url.pathname === '/health') {
      res.writeHead(200, { 'Content-Type': MIME['.json'] });
      res.end(JSON.stringify({ ok: true, rooms: rooms.size, players: clientsByUser.size }));
      return;
    }

    if (url.pathname === '/config') {
      res.writeHead(200, { 'Content-Type': MIME['.json'], 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({
        devLogin, botUsername, appShortName, communityUrl, supportUrl, topup: payments.describe(),
      }));
      return;
    }

    if (url.pathname.startsWith(WEBHOOK_PREFIX)) {
      handleWebhookRequest(req, res, url.pathname);
      return;
    }

    serveStatic(url.pathname, res);
  });

  // ——— Вебхуки платёжных сервисов ———

  // Crypto Bot и xRocket стучатся сюда сами, когда счёт оплачен.
  // Адрес вебхука прописывается в настройках приложения внутри их ботов:
  //   https://ваш-домен/pay/cryptobot/webhook
  //   https://ваш-домен/pay/xrocket/webhook
  function handleWebhookRequest(req, res, pathname) {
    const match = /^\/pay\/([a-z0-9_-]+)\/webhook\/?$/i.exec(pathname);
    const providerId = match ? match[1].toLowerCase() : null;

    const reply = (code, text) => {
      res.writeHead(code, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end(text);
    };

    if (!providerId || !payments.providers.has(providerId)) {
      reply(404, 'Не найдено');
      return;
    }
    if (req.method !== 'POST') {
      reply(405, 'Только POST');
      return;
    }

    const provider = payments.providers.get(providerId);
    const signature = req.headers[provider.signatureHeader];

    readRequestBody(req, MAX_WEBHOOK_BYTES)
      .then((rawBody) => {
        const result = payments.handleWebhook(providerId, rawBody, signature);
        if (result.handled && !result.already) {
          console.log(`Пополнение через ${providerId}: +${result.credited} фишек игроку ${result.record.userId}`);
        }
        // Что бы мы ни решили дальше, платёжному сервису отвечаем 200 —
        // иначе он будет слать этот же вебхук снова и снова.
        reply(200, 'OK');
      })
      .catch((error) => {
        if (error instanceof PaymentError) {
          // Не совпавшая подпись — единственный случай, когда отвечаем ошибкой:
          // так это видно в панели платёжного сервиса.
          console.warn(`Вебхук ${providerId} отклонён: ${error.message}`);
          reply(403, 'Подпись не совпала');
          return;
        }
        console.error(`Ошибка обработки вебхука ${providerId}:`, error);
        reply(500, 'Внутренняя ошибка');
      });
  }

  // ——— WebSocket ———

  const wss = attachWebSocketServer(server, { path: '/ws' });

  wss.on('connection', (socket) => {
    const client = {
      socket,
      user: null,
      roomCode: null,
      startParam: null,
      send(message) {
        socket.send(JSON.stringify(message));
      },
      fail(message) {
        this.send({ type: 'error', message });
      },
    };

    socket.on('message', (raw) => {
      if (!allowMessage(client)) {
        client.fail('Слишком много запросов, чуть помедленнее');
        return;
      }
      let message;
      try {
        message = JSON.parse(raw);
      } catch {
        client.fail('Некорректное сообщение');
        return;
      }
      try {
        handleMessage(client, message);
      } catch (error) {
        if (error instanceof RoomError) {
          client.fail(error.message);
        } else {
          console.error('Ошибка обработки сообщения:', error);
          client.fail('Внутренняя ошибка сервера');
        }
      }
    });

    socket.on('close', () => {
      if (!client.user) return;
      if (clientsByUser.get(client.user.id) !== client) return;
      clientsByUser.delete(client.user.id);
      const room = client.roomCode ? rooms.get(client.roomCode) : null;
      if (room) {
        room.setDisconnected(client.user.id);
        markEmpty(room);
      }
    });
  });

  // Не больше 40 сообщений за пять секунд с одного соединения.
  function allowMessage(client) {
    const now = Date.now();
    if (!client.windowStart || now - client.windowStart > 5000) {
      client.windowStart = now;
      client.messageCount = 0;
    }
    client.messageCount += 1;
    return client.messageCount <= 40;
  }

  function handleMessage(client, message) {
    if (message.type === 'auth') {
      authenticate(client, message);
      return;
    }
    if (!client.user) {
      client.fail('Сначала нужно авторизоваться');
      return;
    }

    switch (message.type) {
      case 'create_room':
        createRoom(client, message.settings || {});
        break;
      case 'join_room':
        joinRoom(client, String(message.code || '').trim().toUpperCase());
        break;
      case 'leave_room':
        leaveRoom(client);
        break;
      case 'sit':
        withRoom(client, (room) => room.sit(client.user.id, Number(message.seat)));
        break;
      case 'stand':
        withRoom(client, (room) => room.stand(client.user.id));
        break;
      case 'rebuy':
        withRoom(client, (room) => room.rebuy(client.user.id));
        break;
      case 'settings':
        withRoom(client, (room) => room.updateSettings(client.user.id, message.settings || {}));
        break;
      case 'start':
        withRoom(client, (room) => room.start(client.user.id));
        break;
      case 'action':
        withRoom(client, (room) => room.applyAction(client.user.id, message.action, message.amount));
        break;
      case 'chat': {
        const text = String(message.text || '').trim();
        if (text.startsWith('/')) {
          const reply = runCommand(client, text);
          if (reply) client.send({ type: 'system', text: reply });
        } else {
          withRoom(client, (room) => room.chat(client.user.id, text));
        }
        break;
      }
      case 'admin_grant':
        grantBalance(client, message.target, message.amount, message.mode);
        break;
      case 'admin_accounts':
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        client.send({ type: 'accounts', accounts: accounts.list(60) });
        break;
      case 'balance':
        client.send({ type: 'balance', balance: accounts.balanceOf(client.user.id) });
        break;
      case 'topup_create':
        createTopUp(client, message.provider, message.amount);
        break;
      case 'topup_status':
        checkTopUp(client, message.id);
        break;
      case 'payout_create':
        createPayout(client, message.provider, message.cents);
        break;
      case 'history':
        client.send({ type: 'history', history: payments.historyFor(client.user.id) });
        break;
      case 'leaders':
        client.send({ type: 'leaders', leaders: accounts.list(20) });
        break;
      case 'promo_redeem':
        redeemPromo(client, message.code);
        break;
      case 'list_rooms':
        client.send({ type: 'rooms', rooms: publicRooms(), wins: recentWins });
        break;
      case 'ping':
        client.send({ type: 'pong', at: Date.now() });
        break;
      default:
        client.fail(`Неизвестная команда: ${message.type}`);
    }
  }

  // Открытые столы: их видно всем, чтобы друзья заходили без кода.
  function publicRooms() {
    return [...rooms.values()]
      .filter((room) => room.house || (room.settings.isPublic && [...room.members.values()].some((m) => m.connected)))
      .map((room) => room.summary())
      .sort((a, b) => b.players - a.players || a.code.localeCompare(b.code))
      .slice(0, 30);
  }

  // ——— Баланс и команды админа ———

  function grantBalance(client, target, amount, mode) {
    if (!isAdmin(client.user)) throw new RoomError('Фишки выдаёт только админ');
    try {
      const { account, delta } = accounts.grant(String(target || '').trim(), amount, mode === 'set' ? 'set' : 'add');
      const changed = delta === 0
        ? 'без изменений'
        : `${delta > 0 ? '+' : ''}${formatMoney(delta)}`;
      client.send({
        type: 'system',
        text: `${account.name} (${account.id}): ${changed}, баланс ${formatMoney(account.balance)}`,
      });
      // Получателю говорим отдельно — он мог сидеть в другой комнате.
      const receiver = clientsByUser.get(account.id);
      if (receiver && receiver !== client && delta !== 0) {
        receiver.send({
          type: 'system',
          text: delta > 0
            ? `Админ начислил ${formatMoney(delta)}. Баланс: ${formatMoney(account.balance)}`
            : `Админ списал ${formatMoney(Math.abs(delta))}. Баланс: ${formatMoney(account.balance)}`,
        });
      }
      return account;
    } catch (error) {
      if (error instanceof AccountError) throw new RoomError(error.message);
      throw error;
    }
  }

  // ——— Пополнение баланса ———

  // Ответ платёжного сервиса ждём асинхронно, поэтому ошибки ловим здесь сами:
  // общий try/catch вокруг handleMessage до промиса уже не дотянется.
  function createTopUp(client, providerId, amount) {
    if (!payments.enabled) {
      client.fail('Пополнение сейчас не подключено');
      return;
    }
    payments
      .createTopUp(client.user, providerId, amount)
      .then((invoice) => client.send({ type: 'topup_invoice', invoice }))
      .catch((error) => {
        if (error instanceof PaymentError) {
          client.fail(error.message);
          return;
        }
        console.error('Не удалось выставить счёт на пополнение:', error);
        client.fail('Не удалось создать счёт, попробуйте ещё раз');
      });
  }

  // Мини-апп спрашивает статус, пока игрок платит: вебхук могли не настроить,
  // и тогда опрос — единственный способ узнать про оплату.
  function checkTopUp(client, recordId) {
    const record = payments.get(recordId);
    // Чужой счёт не показываем и не трогаем — иначе по чужому id можно было бы
    // узнать сумму и заставить сервер ходить в платёжный сервис.
    if (!record || record.userId !== String(client.user.id)) {
      client.fail('Счёт не найден');
      return;
    }
    payments
      .refresh(recordId)
      .then((invoice) => client.send({ type: 'topup_status', invoice }))
      .catch((error) => {
        if (error instanceof PaymentError) {
          client.fail(error.message);
          return;
        }
        console.error('Не удалось проверить счёт:', error);
        client.fail('Не удалось проверить оплату, попробуйте позже');
      });
  }

  // Вывод: сумма приходит в центах, всё остальное считает сервер.
  function createPayout(client, providerId, cents) {
    if (!payments.payoutEnabled) {
      client.fail('Вывод сейчас не подключён');
      return;
    }
    payments
      .createPayout(client.user, providerId, cents)
      .then((payout) => client.send({ type: 'payout_status', payout }))
      .catch((error) => {
        if (error instanceof PaymentError) {
          client.fail(error.message);
          return;
        }
        console.error('Не удалось выполнить вывод:', error);
        client.fail('Не удалось выполнить вывод, попробуйте позже');
      });
  }

  // Промокод активирует сам игрок; деньги создаёт только код, выданный админом.
  function redeemPromo(client, code) {
    try {
      const result = promo.redeem(client.user, code);
      client.send({ type: 'promo_ok', cents: result.cents, code: result.code, text: result.text });
      client.send({ type: 'system', text: result.text });
    } catch (error) {
      if (error instanceof PromoError) {
        client.fail(error.message);
        return;
      }
      console.error('Ошибка активации промокода:', error);
      client.fail('Не удалось активировать промокод');
    }
  }

  const COMMAND_HELP = [
    'Команды:',
    '/баланс — свой баланс',
    '/id — свой Telegram ID',
    '',
    'Для админа (адресат — Telegram ID или @ник, суммы в долларах):',
    '/дать 123456789 50 — начислить $50.00',
    '/забрать 123456789 10 — списать $10.00',
    '/установить 123456789 100 — выставить баланс $100.00',
    '/баланс 123456789 — посмотреть чужой баланс',
    '/счета — список счетов',
    '/выплаты — зависшие выводы',
    '/промокод ЛЕТО 5 100 — код на $5.00, 100 активаций',
    '/промокоды — список кодов',
    '/удалить-код ЛЕТО — убрать код',
  ].join('\n');

  function runCommand(client, line) {
    const tokens = line.slice(1).split(/\s+/).filter(Boolean);
    const command = (tokens.shift() || '').toLowerCase();

    const target = () => {
      if (!tokens.length) throw new RoomError('Укажите Telegram ID или @ник');
      return tokens[0];
    };
    // Админ пишет сумму в долларах — внутрь она уходит центами.
    const amount = () => {
      if (tokens.length < 2) throw new RoomError('Укажите сумму в долларах, например 50');
      const cents = parseMoney(tokens[1]);
      if (cents === null) throw new RoomError('Сумма должна быть числом, например 50 или 12.34');
      return cents;
    };

    switch (command) {
      case 'помощь':
      case 'help':
      case '?':
        return COMMAND_HELP;

      case 'id':
      case 'кто':
        return `Ваш ID: ${client.user.id}`;

      case 'баланс':
      case 'balance': {
        if (!tokens.length) return `Ваш баланс: ${formatMoney(accounts.balanceOf(client.user.id))}`;
        if (!isAdmin(client.user)) throw new RoomError('Чужой баланс смотрит только админ');
        const account = accounts.find(target());
        if (!account) throw new RoomError(`Игрок «${target()}» не найден`);
        return `${account.name} (${account.id}): ${formatMoney(account.balance)}`;
      }

      case 'дать':
      case 'выдать':
      case 'give': {
        const account = grantBalance(client, target(), Math.abs(amount()), 'add');
        return `${account.name}: баланс ${formatMoney(account.balance)}`;
      }
      case 'забрать':
      case 'take': {
        const account = grantBalance(client, target(), -Math.abs(amount()), 'add');
        return `${account.name}: баланс ${formatMoney(account.balance)}`;
      }
      case 'установить':
      case 'set': {
        const account = grantBalance(client, target(), amount(), 'set');
        return `${account.name}: баланс ${formatMoney(account.balance)}`;
      }

      case 'счета':
      case 'accounts': {
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        const rows = accounts.list(15).map((a) => `${a.id} · ${a.name} — ${formatMoney(a.balance)}`);
        return rows.length ? ['Счета:', ...rows].join('\n') : 'Счетов пока нет';
      }

      // Выплаты, по которым сервис не ответил внятно: деньги списаны, а
      // дошли ли — неизвестно. Их нужно разобрать руками.
      case 'выплаты':
      case 'payouts': {
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        const stuck = payments.stuckPayouts();
        if (!stuck.length) return 'Зависших выплат нет';
        const rows = stuck.map((p) => `${p.id} · ${p.userName || p.userId} — ${formatMoney(p.cents)} (${p.status})`);
        return ['Зависшие выплаты:', ...rows, '', 'Повторить: /повторить <id>'].join('\n');
      }
      // ——— Промокоды ———
      case 'промокод':
      case 'promo': {
        if (!isAdmin(client.user)) throw new RoomError('Промокоды создаёт только админ');
        if (tokens.length < 2) throw new RoomError('Формат: /промокод КОД СУММА [АКТИВАЦИЙ]');
        const cents = parseMoney(tokens[1]);
        if (cents === null) throw new RoomError('Сумма должна быть числом, например 5 или 2.50');
        const activations = tokens.length > 2 ? Number(tokens[2]) : 1;
        try {
          const record = promo.create({
            code: tokens[0],
            cents,
            maxActivations: activations,
            createdBy: client.user.id,
          });
          return `Промокод ${record.code}: ${formatMoney(record.cents)}, активаций ${record.maxActivations}`;
        } catch (error) {
          throw new RoomError(error.message);
        }
      }
      case 'промокоды':
      case 'promos': {
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        const rows = promo.list().map((p) => `${p.code} — ${formatMoney(p.cents)} · ${p.used}/${p.maxActivations}`);
        return rows.length ? ['Промокоды:', ...rows].join('\n') : 'Промокодов пока нет';
      }
      case 'удалить-код':
      case 'promo-delete': {
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        try {
          return `Промокод ${promo.remove(target())} удалён`;
        } catch (error) {
          throw new RoomError(error.message);
        }
      }

      case 'повторить':
      case 'retry': {
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        const payoutId = target();
        payments.retryPayout(payoutId)
          .then((payout) => client.send({ type: 'system', text: `Выплата ${payoutId}: ${payout.status}` }))
          .catch((error) => client.send({ type: 'system', text: `Выплата ${payoutId}: ${error.message}` }));
        return 'Повторяю выплату…';
      }

      default:
        throw new RoomError(`Неизвестная команда «/${command}». Наберите /помощь`);
    }
  }

  function withRoom(client, action) {
    const room = client.roomCode ? rooms.get(client.roomCode) : null;
    if (!room) throw new RoomError('Вы не в комнате');
    action(room);
  }

  function authenticate(client, message) {
    let user;

    if (message.initData) {
      if (!botToken) {
        client.fail('Сервер запущен без TELEGRAM_BOT_TOKEN — проверить подпись невозможно');
        return;
      }
      const verified = verifyInitData(message.initData, botToken);
      if (!verified.ok) {
        // Самая частая причина — в .env токен не того бота, под которым
        // создан мини-апп. Скажем об этом прямо, а не «подпись не совпала».
        const hint = verified.error.includes('не совпала')
          ? `. Приложение запущено с токеном бота №${botToken.split(':')[0]} — проверьте, что мини-апп создан у этого же бота`
          : '';
        console.warn(`Не пустили игрока: ${verified.error}.${hint}`);
        client.fail(verified.error + hint);
        return;
      }
      user = verified.user;
      client.startParam = verified.startParam;
    } else if (devLogin) {
      const name = String(message.name || '').trim().slice(0, 24) || 'Гость';
      const id = String(message.devId || '').trim().slice(0, 40) || crypto.randomUUID();
      user = { id: `dev:${id}`, name, photoUrl: null };
    } else {
      client.fail('Откройте приложение через Telegram');
      return;
    }

    // Одно активное соединение на игрока: старая вкладка отключается.
    const previous = clientsByUser.get(user.id);
    if (previous && previous !== client) {
      previous.send({ type: 'replaced' });
      previous.user = null;
      previous.socket.close(4000, 'Открыта другая вкладка');
    }

    client.user = user;
    clientsByUser.set(user.id, client);
    const account = accounts.ensure(user);
    client.send({
      type: 'auth_ok',
      user,
      balance: account.balance,
      isAdmin: isAdmin(user),
      startingBalance: accounts.startingBalance,
      startParam: client.startParam || null,
      topup: payments.describe(),
      links: { community: communityUrl, support: supportUrl },
    });

    // Если игрок уже сидел за столом — возвращаем его туда же.
    for (const room of rooms.values()) {
      if (!room.members.has(user.id)) continue;
      client.roomCode = room.code;
      room.emptyAt = null;
      room.addMember(user);
      client.send({ type: 'joined', code: room.code });
      client.send(room.stateFor(user.id));
      return;
    }
  }

  function createRoom(client, settings) {
    leaveRoom(client, { silent: true });
    const room = new Room(createRoomCode(), client.user, normalizeSettings(settings), { bank: accounts });
    registerRoom(room);
    client.roomCode = room.code;
    client.send({ type: 'joined', code: room.code });
    client.send(room.stateFor(client.user.id));
  }

  function joinRoom(client, code) {
    const room = rooms.get(code);
    if (!room) throw new RoomError('Комната не найдена — проверьте код');
    if (client.roomCode === code) {
      client.send(room.stateFor(client.user.id));
      return;
    }
    if (room.members.size >= room.settings.maxPlayers + 6) {
      throw new RoomError('За этим столом уже слишком много зрителей');
    }
    leaveRoom(client, { silent: true });
    room.emptyAt = null;
    room.addMember(client.user);
    client.roomCode = code;
    client.send({ type: 'joined', code });
    client.send(room.stateFor(client.user.id));
  }

  function leaveRoom(client, { silent = false } = {}) {
    const room = client.roomCode ? rooms.get(client.roomCode) : null;
    client.roomCode = null;
    if (!room) return;
    room.removeMember(client.user.id);
    markEmpty(room);
    if (!silent) client.send({ type: 'left' });
  }

  // Аккуратное выключение: рвём висящие сокеты, иначе close() будет ждать вечно.
  server.shutdown = () => new Promise((resolve) => {
    for (const connection of [...wss.connections]) connection.destroy();
    server.close(() => resolve());
  });

  server.on('close', () => {
    clearInterval(sweeper);
    wss.stop();
    for (const room of rooms.values()) {
      room.cashOutAll();
      room.dispose();
    }
    accounts.flush();
    payments.flush();
    promo.flush();
    rooms.clear();
    clientsByUser.clear();
  });

  return server;
}

// Тело запроса читаем сами: у вебхука подпись считается по сырым байтам,
// поэтому важно не пересобирать JSON и не дать прислать что-то огромное.
function readRequestBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new Error('Тело запроса слишком большое'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function serveStatic(pathname, res) {
  const relative = pathname === '/' ? 'index.html' : decodeURIComponent(pathname).replace(/^\/+/, '');
  const filePath = path.join(PUBLIC_DIR, relative);
  // Защита от выхода за пределы public/
  if (filePath !== PUBLIC_DIR && !filePath.startsWith(PUBLIC_DIR + path.sep)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Доступ запрещён');
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Не найдено');
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      // no-cache — не «не кэшировать», а «каждый раз спрашивать сервер».
      // Пятиминутный max-age приводил к тому, что после обновления браузер
      // отдавал новый index.html вместе со старым app.js, и приложение
      // падало на первой же исчезнувшей кнопке.
      'Cache-Control': ext === '.html' ? 'no-store' : 'no-cache',
    });
    res.end(data);
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3000);
  const host = process.env.HOST || '0.0.0.0';
  const server = createApp();

  server.listen(port, host, () => {
    console.log(`Покерный стол поднят на http://${host}:${port}`);
    if (!process.env.TELEGRAM_BOT_TOKEN) {
      console.warn('TELEGRAM_BOT_TOKEN не задан: включён режим отладки, вход по имени без проверки подписи.');
      console.warn('Для боевого запуска обязательно задайте TELEGRAM_BOT_TOKEN.');
    }
    if (!String(process.env.TELEGRAM_ADMIN_IDS || '').trim()) {
      console.warn('TELEGRAM_ADMIN_IDS не задан: выдавать деньги будет некому.');
      console.warn('Укажите свой Telegram ID, например TELEGRAM_ADMIN_IDS=123456789');
    }
  });

  // Балансы и фишки со столов не должны потеряться при перезапуске.
  const shutdown = (signal) => {
    console.log(`Получен ${signal}, аккуратно выключаемся…`);
    server.shutdown().then(() => process.exit(0));
    setTimeout(() => process.exit(0), 5000).unref();
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

module.exports = { createApp };
