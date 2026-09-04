#!/usr/bin/env node
'use strict';

// Проверяет токен и настраивает кнопку меню бота, чтобы она открывала мини-приложение.
//
//   node scripts/setup-bot.js                      — просто проверить токен
//   node scripts/setup-bot.js https://ваш.домен    — ещё и повесить кнопку меню
//
// Токен берётся из .env или переменной окружения TELEGRAM_BOT_TOKEN.

const { loadEnv } = require('../server/env');

loadEnv();

const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const url = process.argv[2];

async function call(method, body) {
  let response;
  try {
    response = await fetch(`https://api.telegram.org/bot${TOKEN}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
  } catch (error) {
    throw new Error(`сеть недоступна (${error.message}). Проверьте выход в интернет с сервера`);
  }

  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    // Так отвечают прокси и фильтры трафика — покажем, что именно пришло.
    throw new Error(`api.telegram.org ответил не по-телеграмному (HTTP ${response.status}): ${text.slice(0, 120)}`);
  }
  if (!data.ok) throw new Error(`${method}: ${data.description || 'неизвестная ошибка'}`);
  return data.result;
}

(async () => {
  if (!TOKEN) {
    console.error('Не задан TELEGRAM_BOT_TOKEN — положите его в .env');
    process.exit(1);
  }

  const me = await call('getMe');
  console.log(`Токен рабочий. Бот: ${me.first_name} @${me.username} (id ${me.id})`);
  console.log(`Впишите в .env:  TELEGRAM_BOT_USERNAME=${me.username}`);

  if (!url) {
    console.log('\nЧтобы кнопка меню открывала стол, запустите:');
    console.log('  node scripts/setup-bot.js https://ваш.домен');
    return;
  }

  if (!url.startsWith('https://')) {
    console.error('Адрес должен начинаться с https:// — Telegram открывает мини-приложения только так');
    process.exit(1);
  }

  await call('setChatMenuButton', {
    menu_button: { type: 'web_app', text: 'Играть', web_app: { url } },
  });
  console.log(`Кнопка меню теперь открывает ${url}`);

  const admins = String(process.env.TELEGRAM_ADMIN_IDS || '').split(',').map((id) => id.trim()).filter(Boolean);
  if (!admins.length) {
    console.warn('\nВнимание: TELEGRAM_ADMIN_IDS пуст — выдавать фишки будет некому.');
  } else {
    console.log(`Админы: ${admins.join(', ')}`);
  }
})().catch((error) => {
  console.error('Не получилось:', error.message);
  process.exit(1);
});
