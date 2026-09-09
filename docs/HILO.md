# Hilo

Game entry: Games → Hilo. Uses the existing Mines/Nvuti betting panel, balance,
WebSocket authentication and cent-based ledger. No dependencies added.

Cards swap via a 480ms Web Animations transition. Inputs are locked through the
server response and animation; reduced-motion mode replaces cards immediately.
Reconnecting restores the round. The round snapshot and account balance are
written in the same accounts.json payload. Normal shutdown cashes out active
rounds. As with the existing account system, disk write errors are logged.

A is low, K high. Independent uniform draws from 52 cards with replacement.
For ranks 2–Q, both directions include equality. For A, high means strictly
higher (12/13), low means same (1/13). For K, high means same (1/13), low
means strictly lower (12/13). Button labels and symbols follow these rules.

A new sequence applies a 1% edge once: first winning multiplier is 0.99 / p,
subsequent winning multipliers are previous / p. Skip leaves it unchanged.
Payout is floored to cents, compensating only for binary floating-point noise
at whole-cent boundaries. Earned legacy multipliers survive round restoration.
The 10,000× cap and account capacity protection remain project-specific.
Cashout before a prediction returns the stake. Old clients must reload before
making predictions under the new rules (rulesVersion 2).

Public references:
- https://stake.com/casino/games/hilo (A/K exceptions and 99% RTP)
- https://stake.com/blog/how-to-play-hilo-on-stake
- https://stake.com/provably-fair/game-events (independent 52-card outcomes)

This is our implementation of the published gameplay, not Stake's proprietary
server code. We keep the project's cryptographic RNG, payout limits and free
skip behavior; this does not implement Stake's seed verification protocol.
The one-time edge follows the stated sequence RTP mathematically; the full
vendor payout algorithm is not published in these references.

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
