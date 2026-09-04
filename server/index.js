'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const { attachWebSocketServer } = require('./wsserver');
const { verifyInitData } = require('./telegram');
const { Room, RoomError, normalizeSettings } = require('./room');
const { Accounts, AccountError, DEFAULT_START_BALANCE } = require('./accounts');
const { loadEnv } = require('./env');

loadEnv();

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const ROOM_TTL_MS = 30 * 60 * 1000; // пустую комнату держим полчаса
const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // без похожих символов

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
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
  }

  function markEmpty(room) {
    if (room.isEmpty) room.emptyAt = Date.now();
  }

  // Комнату держим, пока в ней кто-то есть на связи: столы с одними
  // отключившимися игроками тоже нужно убирать, иначе они копятся в памяти.
  const sweeper = setInterval(() => {
    const now = Date.now();
    for (const [code, room] of rooms) {
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
      res.end(JSON.stringify({ devLogin, botUsername, appShortName }));
      return;
    }

    serveStatic(url.pathname, res);
  });

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
      case 'list_rooms':
        client.send({ type: 'rooms', rooms: publicRooms() });
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
      .filter((room) => room.settings.isPublic && [...room.members.values()].some((m) => m.connected))
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
        : `${delta > 0 ? '+' : ''}${delta}`;
      client.send({
        type: 'system',
        text: `${account.name} (${account.id}): ${changed}, баланс ${account.balance}`,
      });
      // Получателю говорим отдельно — он мог сидеть в другой комнате.
      const receiver = clientsByUser.get(account.id);
      if (receiver && receiver !== client && delta !== 0) {
        receiver.send({
          type: 'system',
          text: delta > 0
            ? `Админ начислил ${delta} фишек. Баланс: ${account.balance}`
            : `Админ списал ${Math.abs(delta)} фишек. Баланс: ${account.balance}`,
        });
      }
      return account;
    } catch (error) {
      if (error instanceof AccountError) throw new RoomError(error.message);
      throw error;
    }
  }

  const COMMAND_HELP = [
    'Команды:',
    '/баланс — свой баланс',
    '/id — свой Telegram ID',
    '',
    'Для админа (адресат — Telegram ID или @ник):',
    '/дать 123456789 5000 — начислить',
    '/забрать 123456789 1000 — списать',
    '/установить 123456789 10000 — выставить баланс',
    '/баланс 123456789 — посмотреть чужой баланс',
    '/счета — список счетов',
  ].join('\n');

  function runCommand(client, line) {
    const tokens = line.slice(1).split(/\s+/).filter(Boolean);
    const command = (tokens.shift() || '').toLowerCase();

    const target = () => {
      if (!tokens.length) throw new RoomError('Укажите Telegram ID или @ник');
      return tokens[0];
    };
    const amount = () => {
      if (tokens.length < 2) throw new RoomError('Укажите количество фишек');
      const value = Number(tokens[1]);
      if (!Number.isFinite(value)) throw new RoomError('Количество должно быть числом');
      return value;
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
        if (!tokens.length) return `Ваш баланс: ${accounts.balanceOf(client.user.id)} фишек`;
        if (!isAdmin(client.user)) throw new RoomError('Чужой баланс смотрит только админ');
        const account = accounts.find(target());
        if (!account) throw new RoomError(`Игрок «${target()}» не найден`);
        return `${account.name} (${account.id}): ${account.balance} фишек`;
      }

      case 'дать':
      case 'выдать':
      case 'give': {
        const account = grantBalance(client, target(), Math.abs(amount()), 'add');
        return `${account.name}: баланс ${account.balance}`;
      }
      case 'забрать':
      case 'take': {
        const account = grantBalance(client, target(), -Math.abs(amount()), 'add');
        return `${account.name}: баланс ${account.balance}`;
      }
      case 'установить':
      case 'set': {
        const account = grantBalance(client, target(), amount(), 'set');
        return `${account.name}: баланс ${account.balance}`;
      }

      case 'счета':
      case 'accounts': {
        if (!isAdmin(client.user)) throw new RoomError('Команда только для админа');
        const rows = accounts.list(15).map((a) => `${a.id} · ${a.name} — ${a.balance}`);
        return rows.length ? ['Счета:', ...rows].join('\n') : 'Счетов пока нет';
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
    rooms.clear();
    clientsByUser.clear();
  });

  return server;
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
      'Cache-Control': ext === '.html' ? 'no-store' : 'public, max-age=300',
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
      console.warn('TELEGRAM_ADMIN_IDS не задан: выдавать фишки будет некому.');
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
