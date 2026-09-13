'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createDiagnostics } = require('../server/diagnostics');

test('slow diagnostics filter secrets and throttle repeated events', () => {
  let clock = 0; const lines = [];
  const d = createDiagnostics({ now: () => clock, log: line => lines.push(line) });
  const quick = d.begin('accounts.save', 100); clock = 99; quick();
  assert.equal(lines.length, 0);
  const slow = d.begin('accounts.save', 100); clock = 250;
  slow({ rounds: 12, token: 'secret', body: { password: 'secret' } });
  assert.deepEqual(JSON.parse(lines[0].slice(7)), { operation: 'accounts.save', ms: 151, suppressed: 0, rounds: 12 });
  d.report('accounts.save', 200); assert.equal(lines.length, 1);
  clock += 5000; d.report('accounts.save', 300);
  assert.equal(JSON.parse(lines[1].slice(7)).suppressed, 1);
  d.report('https://secret-token', 200);
  assert.equal(JSON.parse(lines[2].slice(7)).operation, 'unknown');
  assert.ok(!lines.join('').includes('secret'));
});

test('diagnostics do not throw on logger failure and can be disabled', () => {
  const d = createDiagnostics({ log: () => { throw new Error('log unavailable'); } });
  assert.doesNotThrow(() => d.report('accounts.save', 500));
  const disabled = createDiagnostics({ enabled: false, log: () => assert.fail('disabled logger called') });
  disabled.report('accounts.save', 500);
});
