#!/usr/bin/env node
'use strict';
// Read-only credential check: never creates invoices or sends money.
const { loadEnv } = require('../server/env');
const { Accounts } = require('../server/accounts');
const { createPayments } = require('../server/payments');
loadEnv();
(async () => {
  const payments = createPayments({ accounts: new Accounts({ file: null }), file: null });
  if (!payments.enabled) { console.error('Добавьте CRYPTOBOT_TOKEN и/или XROCKET_TOKEN в .env'); process.exitCode = 1; return; }
  for (const provider of payments.providers.values()) {
    try { await provider.getMe(); console.log(`✅ ${provider.title}: токен принят · ${provider.currency}`); }
    catch { console.error(`❌ ${provider.title}: проверка не прошла. Проверьте токен, сеть провайдера и доступность API.`); process.exitCode = 1; }
  }
  console.log(payments.manualPayouts ? 'Выводы: ручное подтверждение администратором.' : 'Выводы: автоматический режим из .env.');
})();
