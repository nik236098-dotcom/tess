# Midnight Express and Cryo Vault

Two independent server-persisted slots, accessed from the existing arcade catalog. The original Abyss rules and audio remain unchanged. Artwork is bespoke SVG illustration inspired by the preview concepts, not a pixel-identical export of generated reference images.

Shared: 5 reels × 3 rows, 20 left-to-right paylines, discrete stakes starting at 20 cents, purchase for 100 stakes, 8 starting free spins. Purchased entry shows three Scatter in randomly chosen distinct columns and random rows, with no unpaid line combination. Three Scatter retrigger 3 spins, at most 32 awarded. Round payout capped at 2500 unit stakes. The integer-cent spin total is rounded down once after summing paylines. One best match per line. State persists independently per game and the existing atomic account service settles once.

Cryo: Wild positions freeze during free spins. Repeated Wild at that position increases 1 → 2 → 3 → 5. Multipliers of Wilds used in a winning line add, rather than multiply. A frozen position replaces its new symbol, including Scatter. Frozen overlays do not travel with the reel strip. Paid base spins clear the overlay and bonus state.

Midnight: each Conductor Wild adds a key during free spins. At 3/6/9 keys the payout multiplier becomes 2/3/5, applied to that spin and later spins. Wilds themselves do not persist. Retriggers keep the keys.

Controls: centered spin, discrete stake modal, adjustable Bonus Buy price, external Turbo and settings. Ordinary wins use brief in-reel effects; large wins and bonus totals use the existing tap-to-finish counter, with the multiplier hidden until counting finishes. No altered-probability admin mode is exposed in these slots.

Audio: locally synthesized Web Audio, no paid generation or remote audio requests. Separate chord arrangements for the ice chamber and ghost train, bonus rhythm layer, continuous low flywheel, five cushioned stop cues, individual Scatter, Wild, line hit, upgrades, feature entry and tiered celebration cues. Audio stops on exit/hidden tab, volumes and mute persist. No device text-to-speech.

Verification: server state/settlement/cap/retrigger tests, UI timing and purchase tests, audio lifecycle tests. `node scripts/feature-slot-math.js 20000` generates the checked-in Monte Carlo bonus audit. The measured returns are sample estimates for Bonus Buy only, not certified RTP or a promised payout. Browser access to the local preview was blocked by the browser environment; an on-device visual/audio check is still needed after deployment.

Deploy on the existing server:

```sh
cd /opt/poker/app && sudo -u poker git fetch origin codex/crash && sudo -u poker git show FETCH_HEAD:scripts/crash-update.sh | sudo bash
```
