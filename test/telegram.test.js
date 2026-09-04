'use strict';

const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const { verifyInitData } = require('../server/telegram');

const BOT_TOKEN = '123456:TEST-TOKEN';

function signInitData(fields) {
  const params = new URLSearchParams(fields);
  const pairs = [...params].map(([k, v]) => `${k}=${v}`).sort();
  const secret = crypto.createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest();
  const hash = crypto.createHmac('sha256', secret).update(pairs.join('\n')).digest('hex');
  params.set('hash', hash);
  return params.toString();
}

const validFields = () => ({
  auth_date: String(Math.floor(Date.now() / 1000)),
  query_id: 'AAA',
  user: JSON.stringify({ id: 42, first_name: 'Аня', last_name: 'П', username: 'anya' }),
});

test('корректная подпись принимается', () => {
  const result = verifyInitData(signInitData(validFields()), BOT_TOKEN);
  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.user.id, '42');
  assert.strictEqual(result.user.name, 'Аня П');
});

test('подделанные данные отклоняются', () => {
  const initData = signInitData(validFields()).replace('%D0%90%D0%BD%D1%8F', 'Eve');
  assert.strictEqual(verifyInitData(initData, BOT_TOKEN).ok, false);
});

test('чужой токен не подходит', () => {
  assert.strictEqual(verifyInitData(signInitData(validFields()), 'другой:токен').ok, false);
});

test('устаревшие данные отклоняются', () => {
  const fields = validFields();
  fields.auth_date = String(Math.floor(Date.now() / 1000) - 90000);
  const result = verifyInitData(signInitData(fields), BOT_TOKEN);
  assert.strictEqual(result.ok, false);
  assert.match(result.error, /устарел/);
});

test('пустой initData отклоняется', () => {
  assert.strictEqual(verifyInitData('', BOT_TOKEN).ok, false);
});
