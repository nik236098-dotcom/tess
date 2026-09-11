# Croco home and connection screen

The approved home combines Telegram identity, the existing game-format wallet and top-up button, one Nvuti feature banner, account-specific recent game shortcuts, and transaction history. Four bottom destinations: Home, Games, Bonuses, Information. The gear opens the existing account settings/admin controls; it is not a fifth navigation tab. The native Telegram header name must be configured in the bot's settings separately from the HTML title.

First visit displays four starting games and a real empty transaction state once the server returns an empty history. No demo balances, statistics, fabricated transactions or public winners appear. Later visits use up to eight recently opened games, stored separately per account on that device. Transactions use the existing authenticated `history` response and reload on entry, reconnection, and payment-status events. Pending/failed records are not styled as completed credits/debits. The existing payment configuration still controls whether top-up is enabled.

Loading is visible in the initial HTML, with generated mascot artwork, CSS glow and an indeterminate animated bar. Authentication dismisses it; subsequent reconnects do not cover ongoing games. A slow initial connection exposes retry after 12 seconds. Auth errors show explanatory text. Reduced motion disables the animations.

Built-in image generation supplied the mascot extracted from the approved loading reference and a wide Nvuti scene based on the existing game's artwork. Production WebP encoding retains native dimensions. Files: `public/img/croco/mascot.webp`, `nvuti-banner.webp`; text, controls, history, and navigation remain live HTML. The game's wallet CSS is mirrored deliberately, including its gold balance text.

Verification: local syntax and deployment asset gates, account-separated recents, safe transaction rendering, loading success/error/timeout lifecycle, and real server integration tests. Cloud Browser blocked both localhost and shared-file previews, so an on-device visual check remains necessary; no pixel-perfect rendering claim is made.

Deployment:

```sh
cd /opt/poker/app && sudo -u poker git fetch origin codex/crash && sudo -u poker git show FETCH_HEAD:scripts/crash-update.sh | sudo bash
```
