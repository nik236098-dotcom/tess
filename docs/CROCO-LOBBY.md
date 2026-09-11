# Croco home and connection screen

The approved home combines Telegram identity, the existing game-format wallet and top-up button, one Nvuti feature banner, four fixed popular game shortcuts, and transaction history. Four bottom destinations: Home, Games, Bonuses, Information. The gear opens the existing account settings/admin controls; it is not a fifth navigation tab. The native Telegram header name must be configured in the bot's settings separately from the HTML title.

Every visit displays Nvuti, Mines, Crash and HiLo and a real empty transaction state once the server returns an empty history. No demo balances, statistics, fabricated transactions or public winners appear. The home does not show recently played games. “Все игры” opens the existing games catalog. Transactions use the existing authenticated `history` response and reload on entry, reconnection, and payment-status events. Pending/failed records are not styled as completed credits/debits. The existing payment configuration still controls whether top-up is enabled.

Loading is visible in the initial HTML, with generated mascot artwork, CSS glow and an indeterminate animated bar. Authentication dismisses it; subsequent reconnects do not cover ongoing games. A slow initial connection exposes retry after 12 seconds. Auth errors show explanatory text. Reduced motion disables the animations.

Built-in image generation supplied the mascot extracted from the approved loading reference and a wide Nvuti scene based on the existing game's artwork. Production WebP encoding retains native dimensions. Files: `public/img/croco/mascot.webp`, `nvuti-banner.webp`; text, controls, history, and navigation remain live HTML. The game's wallet CSS is mirrored deliberately, including its gold balance text.

Verification: local syntax and deployment asset gates, account-separated recents, safe transaction rendering, loading success/error/timeout lifecycle, and real server integration tests. Cloud Browser blocked both localhost and shared-file previews, so an on-device visual check remains necessary; no pixel-perfect rendering claim is made.

Deployment:

```sh
cd /opt/poker/app && sudo -u poker git fetch origin codex/crash && sudo -u poker git show FETCH_HEAD:scripts/crash-update.sh | sudo bash
```

The updater validates the exact fetched revision in a temporary snapshot before stopping the live service. After switching, it waits up to 45 seconds for two consecutive successful local `/config` HTTP responses with the service active. Startup failure or timeout triggers a rollback to the previous checkout and verifies its HTTP response. A restart still causes a brief interruption; this is not a zero-downtime deployment. Concurrent updater runs are locked out.

Deployment lifecycle tests execute the Bash script against command doubles: preflight failure without stopping the old service, slow startup, HTTP timeout rollback, and service-start failure rollback. Asset validation is covered separately by `test/deploy-assets.test.js`.

Popular-game artwork is a generated 2×2 square atlas derived from the approved mockup; CSS selects the corresponding quadrant without baking labels or controls into the artwork. The updated Nvuti hero uses a separate crocodile illustration with live title and play button. Both are encoded as WebP. The bottom navigation uses a rounded dock and a luminous active tile.
