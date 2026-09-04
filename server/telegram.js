'use strict';

const crypto = require('crypto');

// Проверка initData из Telegram Mini App.
// https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
function verifyInitData(initData, botToken, { maxAgeSeconds = 86400 } = {}) {
  if (!initData || typeof initData !== 'string') {
    return { ok: false, error: 'initData отсутствует' };
  }

  const params = new URLSearchParams(initData);
  const hash = params.get('hash');
  if (!hash) return { ok: false, error: 'В initData нет подписи' };

  // Из строки подписи исключается только hash. Поле signature (его присылают
  // современные клиенты) нужно исключать лишь при сторонней проверке по Ed25519,
  // а при проверке токеном бота оно участвует наравне с остальными.
  const pairs = [];
  for (const [key, value] of params) {
    if (key === 'hash') continue;
    pairs.push(`${key}=${value}`);
  }
  pairs.sort();
  const dataCheckString = pairs.join('\n');

  const secretKey = crypto.createHmac('sha256', 'WebAppData').update(botToken).digest();
  const computed = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest('hex');

  const expected = Buffer.from(computed, 'hex');
  const received = Buffer.from(hash, 'hex');
  if (expected.length !== received.length || !crypto.timingSafeEqual(expected, received)) {
    return { ok: false, error: 'Подпись initData не совпала' };
  }

  const authDate = Number(params.get('auth_date'));
  if (!Number.isFinite(authDate)) return { ok: false, error: 'Некорректная дата авторизации' };
  const age = Math.floor(Date.now() / 1000) - authDate;
  if (maxAgeSeconds > 0 && age > maxAgeSeconds) {
    return { ok: false, error: 'Данные авторизации устарели, перезапустите приложение' };
  }

  let user = null;
  try {
    user = JSON.parse(params.get('user') || 'null');
  } catch {
    return { ok: false, error: 'Не удалось разобрать данные пользователя' };
  }
  if (!user || !user.id) return { ok: false, error: 'В initData нет пользователя' };

  return {
    ok: true,
    user: {
      id: String(user.id),
      name: displayName(user),
      username: user.username || null,
      photoUrl: user.photo_url || null,
    },
    startParam: params.get('start_param') || null,
  };
}

function displayName(user) {
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
  return name || user.username || `Игрок ${user.id}`;
}

module.exports = { verifyInitData };
