'use strict';

// Provider requests are asynchronous and serial; no Telegram chat is required.
function createPaymentPoller(payments, { now = Date.now, log = console.warn } = {}) {
  const checked = new Map();
  let stopped = false, timer, busy = false;
  async function tick() {
    if (stopped || busy) return;
    busy = true;
    try {
      const time = now();
      const candidates = [...payments.invoices.values()].filter(r => !r.creditedAt && r.invoiceId
        && payments.providers.has(r.provider) && r.createdAt >= time - 30 * 86400000);
      const ids = new Set(candidates.map(r => r.id));
      for (const id of checked.keys()) if (!ids.has(id)) checked.delete(id);
      // Revisit expired invoices too: payment may have completed during downtime.
      const record = candidates.filter(r => time >= (checked.get(r.id) || 0))
        .sort((a, b) => (checked.get(a.id) || 0) - (checked.get(b.id) || 0))[0];
      if (!record) return;
      checked.set(record.id, time + (record.status === 'expired' ? 300000 : 10000));
      try { await payments.refresh(record.id, { shouldStop: () => stopped }); }
      catch { checked.set(record.id, now() + 60000); log('[payments] Проверка оплаты отложена: ' + record.provider); }
    } finally { busy = false; }
  }
  function start() {
    if (timer) return;
    stopped = false;
    timer = setInterval(() => { void tick(); }, 2000);
    timer.unref?.();
  }
  function stop() { stopped = true; clearInterval(timer); timer = null; }
  return { start, stop, tick };
}
module.exports = { createPaymentPoller };
