'use strict';
const { performance } = require('node:perf_hooks');

// Only fixed operation names and numeric metrics: never request bodies or tokens.
function createDiagnostics({ now = () => performance.now(), log = line => console.warn(line), enabled = true } = {}) {
  const recent = new Map();
  function report(operation, ms, threshold = 200, metrics = {}) {
    if (!enabled || !Number.isFinite(ms) || ms < threshold) return;
    const key = /^[a-zA-Z0-9_.:-]{1,80}$/.test(operation) ? operation : 'unknown';
    const at = now(), previous = recent.get(key);
    if (previous && at - previous.at < 5000) { previous.suppressed++; return; }
    const row = { operation: key, ms: Math.round(ms), suppressed: previous?.suppressed || 0 };
    for (const [name, value] of Object.entries(metrics)) {
      if (/^[a-z_]{1,32}$/.test(name) && typeof value === 'number' && Number.isFinite(value)) row[name] = Math.round(value);
    }
    if (recent.size >= 128 && !recent.has(key)) recent.delete(recent.keys().next().value);
    recent.set(key, { at, suppressed: 0 });
    try { log('[perf] ' + JSON.stringify(row)); } catch { /* Diagnostics must not break a transaction. */ }
  }
  function begin(operation, threshold = 200) {
    const start = now();
    return (metrics = {}) => report(operation, now() - start, threshold, metrics);
  }
  function watchLoop() {
    let expected = now() + 1000;
    const timer = setInterval(() => {
      const current = now(); report('event_loop', current - expected); expected = current + 1000;
    }, 1000);
    timer.unref?.();
    return () => clearInterval(timer);
  }
  return { begin, report, watchLoop };
}
module.exports = { createDiagnostics, ...createDiagnostics({ enabled: process.env.PERF_LOG !== '0' }) };
