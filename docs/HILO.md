# Hilo

Game entry: Games → Hilo. Uses the existing Mines/Nvuti betting panel, balance,
WebSocket authentication and cent-based ledger. No dependencies added.

Cards swap via a 480ms Web Animations transition. Inputs are locked through the
server response and animation; reduced-motion mode replaces cards immediately.
Reconnecting restores the round. The round snapshot and account balance are
written in the same accounts.json payload. Normal shutdown cashes out active
rounds. As with the existing account system, disk write errors are logged.

A is low, K high. Independent uniform draws from 52 cards with replacement.
Ties win in both directions. Directions with probability 1 are disabled.
The next multiplier is previous × 0.97 / probability, rounded down to six decimals;
payout is rounded down to whole cents. Maximum multiplier 10,000× cashes out
automatically. A prediction that could overflow the existing account balance limit is rejected before drawing; a cashout that cannot fit remains saved. Skipping is free. Cashing out before a prediction returns the bet.

Amounts: 10–10,000,000 cents. Revisions reject duplicate/stale commands.

## Installation

Run on the existing server:

```sh
cd /opt/poker/app && sudo -u poker git fetch origin codex/hilo && sudo -u poker git show FETCH_HEAD:scripts/hilo-update.sh | sudo bash
```

Rollback:

```sh
sudo bash /opt/poker/app/scripts/hilo-update.sh rollback
```

The installer refuses tracked local modifications, stores the previous commit in
backup/pre-hilo, stops the service before switching code, and restarts the previous
version if the update fails. The last pre-install commit is retained for rollback.
Runtime data and credentials are never reset.

## Validation

`node --test test/hilo.test.js test/integration.test.js test/accounts.test.js test/mines.test.js test/nvuti.test.js`

Browser preview was blocked by ERR_BLOCKED_BY_CLIENT in the current tool session;
mobile visual and real-device animation validation is still required.
