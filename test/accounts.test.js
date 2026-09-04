'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Accounts, AccountError } = require('../server/accounts');

const user = (id, name, username) => ({ id, name, username });

test('новому игроку заводится счёт со стартовым балансом', () => {
  const bank = new Accounts({ startingBalance: 5000 });
  const account = bank.ensure(user('42', 'Аня'));
  assert.strictEqual(account.balance, 5000);
  assert.strictEqual(bank.balanceOf('42'), 5000);
});

test('повторный вход не обнуляет баланс, но обновляет имя', () => {
  const bank = new Accounts({ startingBalance: 5000 });
  bank.ensure(user('42', 'Аня'));
  bank.withdraw('42', 1000);
  const again = bank.ensure(user('42', 'Аня П.'));
  assert.strictEqual(again.balance, 4000);
  assert.strictEqual(again.name, 'Аня П.');
});

test('нельзя снять больше, чем есть', () => {
  const bank = new Accounts({ startingBalance: 100 });
  bank.ensure(user('1', 'Кто-то'));
  assert.throws(() => bank.withdraw('1', 500), AccountError);
  assert.strictEqual(bank.balanceOf('1'), 100);
});

test('поиск идёт по Telegram ID и по @нику, но не по имени', () => {
  const bank = new Accounts({ startingBalance: 100 });
  bank.ensure(user('777', 'Боря', 'borya'));
  assert.strictEqual(bank.find('777').id, '777');
  assert.strictEqual(bank.find('@borya').id, '777');
  assert.strictEqual(bank.find('@BORYA').id, '777', 'ник ищется без учёта регистра');
  assert.strictEqual(bank.find('Боря'), null, 'по имени не ищем — имена повторяются');
});

test('одинаковые имена не мешают адресовать выдачу', () => {
  const bank = new Accounts({ startingBalance: 1000 });
  bank.ensure(user('111', 'Саша'));
  bank.ensure(user('222', 'Саша'));

  bank.grant('222', 5000, 'add');
  assert.strictEqual(bank.balanceOf('111'), 1000, 'первый Саша не тронут');
  assert.strictEqual(bank.balanceOf('222'), 6000);
});

test('админ выдаёт, списывает и выставляет баланс', () => {
  const bank = new Accounts({ startingBalance: 1000 });
  bank.ensure(user('5', 'Игрок'));

  assert.strictEqual(bank.grant('5', 500, 'add').account.balance, 1500);
  assert.strictEqual(bank.grant('5', -200, 'add').account.balance, 1300);
  assert.strictEqual(bank.grant('5', 42, 'set').account.balance, 42);
  assert.throws(() => bank.grant('5', -100, 'add'), /столько фишек нет/);
  assert.throws(() => bank.grant('999', 100, 'add'), /не найден/);
});

test('права админа берутся из списка', () => {
  const bank = new Accounts({ admins: ['8552698215'] });
  assert.strictEqual(bank.isAdmin('8552698215'), true);
  assert.strictEqual(bank.isAdmin(8552698215), true, 'число и строка — одно и то же');
  assert.strictEqual(bank.isAdmin('1'), false);
});

test('балансы переживают перезапуск', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'poker-'));
  const file = path.join(dir, 'accounts.json');
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));

  const first = new Accounts({ file, startingBalance: 1000 });
  first.ensure(user('7', 'Вика', 'vika'));
  first.grant('7', 2500, 'add');
  first.flush();

  const second = new Accounts({ file, startingBalance: 1000 });
  assert.strictEqual(second.balanceOf('7'), 3500);
  assert.strictEqual(second.find('@vika').name, 'Вика');
});

test('об изменении баланса сообщается подписчику', () => {
  const bank = new Accounts({ startingBalance: 100 });
  bank.ensure(user('3', 'Гриша'));
  const seen = [];
  bank.onChange = (account) => seen.push(account.balance);

  bank.deposit('3', 50);
  bank.withdraw('3', 20);
  assert.deepStrictEqual(seen, [150, 130]);
});
