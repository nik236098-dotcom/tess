'use strict';

const test = require('node:test');
const assert = require('node:assert');

const { Accounts } = require('../server/accounts');
const { PromoCodes, PromoError } = require('../server/promo');

const admin = { id: '1', name: 'Админ' };
const player = { id: '42', name: 'Аня', username: 'anya' };

function setup() {
  const accounts = new Accounts({ startingBalance: 0 });
  accounts.ensure(player);
  return { accounts, promo: new PromoCodes({ accounts, file: null }) };
}

test('промокод начисляет деньги на баланс', () => {
  const { promo, accounts } = setup();
  promo.create({ code: 'ЛЕТО2026'.replace(/[^A-Z0-9]/g, 'X'), cents: 500, createdBy: admin.id });
  promo.create({ code: 'BONUS', cents: 500, maxActivations: 10, createdBy: admin.id });

  const result = promo.redeem(player, 'BONUS');

  assert.strictEqual(result.cents, 500);
  assert.strictEqual(accounts.balanceOf('42'), 500);
  assert.match(result.text, /\$5\.00/);
});

test('код нечувствителен к регистру и пробелам', () => {
  const { promo, accounts } = setup();
  promo.create({ code: 'BONUS', cents: 300, maxActivations: 5 });

  promo.redeem(player, '  bonus ');

  assert.strictEqual(accounts.balanceOf('42'), 300);
});

test('один игрок активирует код только раз', () => {
  const { promo, accounts } = setup();
  promo.create({ code: 'BONUS', cents: 500, maxActivations: 10 });

  promo.redeem(player, 'BONUS');
  assert.throws(() => promo.redeem(player, 'BONUS'), /уже активировали/);

  assert.strictEqual(accounts.balanceOf('42'), 500, 'начислено ровно один раз');
});

test('активации кончаются на заданном лимите', () => {
  const { promo, accounts } = setup();
  promo.create({ code: 'TWO', cents: 100, maxActivations: 2 });

  promo.redeem({ id: '10', name: 'Первый' }, 'TWO');
  promo.redeem({ id: '11', name: 'Второй' }, 'TWO');
  assert.throws(() => promo.redeem({ id: '12', name: 'Третий' }, 'TWO'), /разобрали/);

  assert.strictEqual(accounts.balanceOf('10'), 100);
  assert.strictEqual(accounts.balanceOf('11'), 100);
  assert.strictEqual(accounts.balanceOf('12'), 0);
});

test('несуществующий код ничего не начисляет', () => {
  const { promo, accounts } = setup();
  assert.throws(() => promo.redeem(player, 'НЕТТАКОГО'), PromoError);
  assert.strictEqual(accounts.balanceOf('42'), 0);
});

test('нельзя создать два кода с одним именем или код с нулевой суммой', () => {
  const { promo } = setup();
  promo.create({ code: 'BONUS', cents: 100 });

  assert.throws(() => promo.create({ code: 'bonus', cents: 100 }), /уже существует/);
  assert.throws(() => promo.create({ code: 'ZERO', cents: 0 }), /больше нуля/);
  assert.throws(() => promo.create({ code: 'NEG', cents: -500 }), /больше нуля/);
  assert.throws(() => promo.create({ code: 'BAD CODE!', cents: 100 }), /латиниц/);
  assert.throws(() => promo.create({ code: 'X', cents: 100, maxActivations: 0 }), /активаций/);
});

test('список показывает, сколько активаций израсходовано', () => {
  const { promo } = setup();
  promo.create({ code: 'BONUS', cents: 250, maxActivations: 3 });
  promo.redeem(player, 'BONUS');

  const [row] = promo.list();
  assert.strictEqual(row.code, 'BONUS');
  assert.strictEqual(row.used, 1);
  assert.strictEqual(row.maxActivations, 3);
});

test('удалённый код больше не активируется', () => {
  const { promo, accounts } = setup();
  promo.create({ code: 'BONUS', cents: 500, maxActivations: 5 });
  promo.remove('bonus');

  assert.throws(() => promo.redeem(player, 'BONUS'), /нет/);
  assert.strictEqual(accounts.balanceOf('42'), 0);
});
