'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

test('deployment preflight runs all checks from its actual isolated Git archive', { timeout: 60000 }, () => {
  const root = path.resolve(__dirname, '..');
  const script = fs.readFileSync(path.join(root, 'scripts/crash-update.sh'), 'utf8');
  const start = script.indexOf('pgit archive ');
  const end = script.indexOf('\ncd "$app_dir"', start);
  assert.ok(start > 0 && end > start, 'preflight boundaries must remain identifiable');
  const staging = fs.mkdtempSync(path.join(os.tmpdir(), 'croco-preflight-test-'));
  try {
    // Execute the deployer's real archive extraction and verification block.
    // There is no systemctl, checkout, ref mutation or network in this block.
    const result = spawnSync('bash', ['-c', 'set -euo pipefail\npgit() { git -C "$PREFLIGHT_REPO" "$@"; }\ntarget=HEAD\nstaging="$PREFLIGHT_STAGE"\n' + script.slice(start, end)], {
      cwd: root, env: { ...process.env, PREFLIGHT_REPO: root, PREFLIGHT_STAGE: staging }, encoding: 'utf8', timeout: 55000,
    });
    assert.equal(result.status, 0, result.stderr || result.error?.message || result.stdout);
    assert.ok(fs.existsSync(path.join(staging, 'scripts/check-payments.js')));
  } finally { fs.rmSync(staging, { recursive: true, force: true }); }
});
