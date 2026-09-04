#!/usr/bin/env node
'use strict';

// Проверяет токен и настраивает кнопку меню бота, чтобы она открывала мини-приложение.
//
//   node scripts/setup-bot.js                             — просто проверить токен
//   node scripts/setup-bot.js https://ваш.домен           — ещё и повесить кнопку меню
//   node scripts/setup-bot.js https://ваш.домен --save    — и вписать имя бота в .env
//
// Токен берётся из .env или переменной окружения TELEGRAM_BOT_TOKEN.

const fs = require('fs');
const path = require('path');
const { loadEnv } = require('../server/env');

loadEnv();

const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const args = process.argv.slice(2);
const save = args.includes('--save');
const url = args.find((argument) => !argument.startsWith('--'));

// Правит одну строку в .env, не трогая остальные.
function saveToEnv(key, value) {
  const file = path.join(__dirname, '..', '.env');
  let text = '';
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    console.warn(`  Файл .env не найден — впишите вручную: ${key}=${value}`);
    return;
  }
  const line = `${key}=${value}`;
  const pattern = new RegExp(`^${key}=.*$`, 'm');
  text = pattern.test(text) ? text.replace(pattern, line) : `${text.replace(/\s*$/, '')}\n${line}\n`;
  fs.writeFileSync(file, text);
  console.log(`  В .env записано ${line}`);
}

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
  if (!data.ok) {
    if (response.status === 401) {
      throw new Error(
        'Telegram не признал токен (Unauthorized).\n' +
        '  • В .env всё ещё заглушка из .env.example? Проверьте:\n' +
        "      grep '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2 | cut -d: -f1\n" +
        '    Должен показать номер вашего бота, а не 123456.\n' +
        '  • Токен отзывали в BotFather? Тогда возьмите новый: /mybots → бот → API Token.\n' +
        '  • После правки .env перезапустите сервис: systemctl restart poker'
      );
    }
    throw new Error(`${method}: ${data.description || 'неизвестная ошибка'}`);
  }
  return data.result;
}

(async () => {
  if (!TOKEN) {
    console.error('Не задан TELEGRAM_BOT_TOKEN — положите его в .env');
    process.exit(1);
  }

  const me = await call('getMe');
  console.log(`Токен рабочий. Бот: ${me.first_name} @${me.username} (id ${me.id})`);
  if (save) {
    saveToEnv('TELEGRAM_BOT_USERNAME', me.username);
  } else if (process.env.TELEGRAM_BOT_USERNAME !== me.username) {
    console.log(`Впишите в .env:  TELEGRAM_BOT_USERNAME=${me.username}`);
    console.log('(или запустите эту же команду с ключом --save — впишет сам)');
  }

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
