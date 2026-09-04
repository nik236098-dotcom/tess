#!/usr/bin/env node
'use strict';

// Пересчёт балансов после перехода на деньги.
//
// Раньше баланс считался в игровых фишках, теперь то же число — центы:
// 250000 фишек читаются как $2500.00. Если фишки были условными, а вывод
// включён, эти деньги станут выводимыми по-настоящему. Скрипт позволяет
// уменьшить балансы в N раз или обнулить их до того, как это произойдёт.
//
//   node scripts/rescale-balances.js /var/lib/poker/accounts.json --divide 100
//   node scripts/rescale-balances.js /var/lib/poker/accounts.json --divide 100 --apply
//   node scripts/rescale-balances.js /var/lib/poker/accounts.json --zero --apply
//
// Без --apply ничего не пишется: сначала показывается, что получится.

const fs = require('fs');
const path = require('path');

const { formatMoney } = require(path.join(__dirname, '..', 'server', 'money'));

function parseArgs(argv) {
  const args = { file: null, divide: 1, zero: false, apply: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--apply') args.apply = true;
    else if (arg === '--zero') args.zero = true;
    else if (arg === '--divide') args.divide = Number(argv[++i]);
    else if (!arg.startsWith('--') && !args.file) args.file = arg;
    else {
      console.error(`Непонятный аргумент: ${arg}`);
      process.exit(1);
    }
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));

if (!args.file) {
  console.error('Укажите файл, например: node scripts/rescale-balances.js /var/lib/poker/accounts.json --divide 100');
  process.exit(1);
}
if (!args.zero && !(Number.isFinite(args.divide) && args.divide > 0)) {
  console.error('--divide должен быть положительным числом');
  process.exit(1);
}
if (!args.zero && args.divide === 1) {
  console.error('Делитель 1 ничего не меняет. Укажите --divide N или --zero');
  process.exit(1);
}

let data;
try {
  data = JSON.parse(fs.readFileSync(args.file, 'utf8'));
} catch (error) {
  console.error(`Не удалось прочитать ${args.file}: ${error.message}`);
  process.exit(1);
}

const accounts = Array.isArray(data.accounts) ? data.accounts : [];
if (!accounts.length) {
  console.log('В файле нет счетов — менять нечего.');
  process.exit(0);
}

const convert = (balance) => {
  const value = Math.max(0, Math.floor(Number(balance) || 0));
  if (args.zero) return 0;
  return Math.floor(value / args.divide);
};

let totalBefore = 0;
let totalAfter = 0;
const rows = accounts.map((account) => {
  const before = Math.max(0, Math.floor(Number(account.balance) || 0));
  const after = convert(before);
  totalBefore += before;
  totalAfter += after;
  return { name: account.name || account.id, id: account.id, before, after };
});

rows.sort((a, b) => b.before - a.before);

const width = Math.max(...rows.map((row) => String(row.name).length), 4);
console.log(args.zero ? 'Обнуление балансов' : `Деление балансов на ${args.divide}`);
console.log('');
for (const row of rows.slice(0, 40)) {
  console.log(`  ${String(row.name).padEnd(width)}  ${formatMoney(row.before).padStart(12)}  →  ${formatMoney(row.after).padStart(12)}`);
}
if (rows.length > 40) console.log(`  … и ещё ${rows.length - 40}`);
console.log('');
console.log(`  ИТОГО${' '.repeat(Math.max(0, width - 5))}  ${formatMoney(totalBefore).padStart(12)}  →  ${formatMoney(totalAfter).padStart(12)}`);
console.log('');

if (!args.apply) {
  console.log('Это предварительный просмотр. Чтобы записать, добавьте --apply');
  process.exit(0);
}

// Бэкап рядом с файлом: если что-то пойдёт не так, будет откуда вернуться.
const backup = `${args.file}.bak-${new Date().toISOString().replace(/[:.]/g, '-')}`;
fs.copyFileSync(args.file, backup);

for (const account of accounts) {
  account.balance = convert(account.balance);
}

const temporary = `${args.file}.tmp`;
fs.writeFileSync(temporary, JSON.stringify({ ...data, accounts }, null, 2));
fs.renameSync(temporary, args.file);

console.log(`Готово. Прежний файл сохранён: ${backup}`);
