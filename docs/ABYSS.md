# Abyss Protocol

Separate underwater slot (`abyss`), alongside the existing Croc Slots. Ten original WebP symbols, a station scene and an English lobby card. Asset-generation prompts are recorded in `abyss-art-prompts.json`.

## Rules and controls

Five reels, three rows, 20 permanent left-to-right paylines. Three to five matching symbols pay; only the highest-paying interpretation of each line is awarded. Wild substitutes ordinary symbols. Scatter never substitutes. The complete symbol table, paylines, weights and allowed stakes are versioned in `public/abyss-rules.js`.

The large circular button starts one paid spin. Stake presets begin at $0.20, $0.40, $0.60, $0.80 and $1.00; all values divide into 20 whole-cent line bets. A single stake tile opens the preset sheet, which also previews the corresponding Bonus Buy cost. Turbo changes animation duration only. There is no paid autoplay. A synthesized underwater soundtrack and event effects are controlled separately in sound settings.

Three or more Scatter award eight free spins. The bonus starts at 1×; each winning free spin raises the next spin's multiplier by one, up to 10×. Three or more Scatter during the bonus add four spins, with at most 40 awarded spins per feature. Total round payout is capped at 2500 times the selected spin stake.

Bonus Buy costs exactly 100 selected spin stakes, not 100 account balances. The confirmation shows the exact debit. Buying animates a trigger board with exactly three Scatter and no unpaid line wins. After the reels stop, the Scatter highlight for 1.2 seconds, then a centered animated “Вы выиграли” celebration displays the awarded spin count. Free spins start only after the player presses Start. The purchased feature uses the same rules and probability distribution as a naturally triggered feature.

## Settlement and recovery

Production randomness uses `crypto.randomInt` on the server. The client receives only the current board. Buy cost is debited once in `ag_start`; subsequent `ag_pick` free spins have no debit. Wallet, bonus state and final credit are saved together through the existing strict arcade persistence transaction. Failed saves roll back state and wallet. Revisions reject duplicate actions. `unitBet` is the chosen spin stake; `bet` is the actual full round cost (100 unit stakes for a purchase).

The feature pays its cumulative total once at completion. Closing the game or hiding the app stops client auto-advance. Reopening reconstructs the saved grid, remaining spins and multiplier, and requires an explicit resume. Reopening never buys again. Symbol loading must finish before a new paid spin can be sent.

## Slot presentation

The station artwork fills the entire screen; the raised reels blend into it without the old enclosing frame. Equal-width control columns keep the circular spin button exactly centered. Ordinary win, loss and refund outcomes never open the shared mini-game overlay. Small payouts count briefly over the reels without blocking input; symbols and winning lines illuminate. Wins of at least 50 spin stakes get a skippable celebration.

After two Scatter have stopped, the following reels slow down with an anticipation glow until a third Scatter lands or all reels stop. The same presentation applies to paid spins and Bonus Buy, including unsuccessful two-Scatter spins. Reduced-motion mode skips reel animation and disables celebration effects.

Presentation regression checks: `node --test test/abyss-ui.test.js test/abyss.test.js` (11 passing). Chromium service flow and mobile controls verified again at 320×740, 390×844 and 430×932.

## Mathematical audit

Run `node scripts/abyss-math.js 100000`. The deterministic offline audit enumerates the single-line base distribution and simulates 100,000 complete bonus rounds using the production evaluator. Results are recorded in `abyss-math-audit.json`.

For version 1: base-game return estimate 95.71%; Bonus Buy return estimate 96.85% (95% Monte Carlo interval approximately 96.29–97.41%). Exact base line return is 79.8343%; the trigger probability is approximately 0.16395%. The base estimate adds the simulated bonus expectation to the exact line expectation; the shared round cap can reduce it slightly. These are development estimates, not certified RTP or a promised individual return.

## Verification

- Full repository suite: 374 passing tests.
- Eight focused engine/service tests cover stake validation, exact three-Scatter purchase entry, Wild/Scatter evaluation, multiplier and cap, finite retriggers, exact 100-stake debit, duplicate rejection, strict-save rollback and persisted bonus recovery with one final credit.
- Chromium with the actual arcade service: confirmed purchase, stopped three-Scatter board before the entry sheet, two forced winning free spins reaching the cap, one credit, and reopening a second saved purchase without another debit or automatic spin.
- Controls fit 320×740, 390×844 and 430×932 viewports with Telegram safe areas. Generated symbols and entry sheet inspected on the rendered mobile screen.
- `scripts/crash-update.sh` checks new scripts and all symbol/scene/card assets before restarting the server.


## Console and bonus arrangement update

The lower console now has a payout header with one settings menu and three main positions: stake, centered spin, Bonus Buy. Sound, speed and rules are in the menu. During a bonus the side tiles show remaining spins and pause/resume. The feature has its own arpeggiated soundtrack and low rhythmic pulse, with an 800 ms crossfade from/to the calmer base arrangement; the shared music volume controls both. The reel frame and title gain a violet accent during the feature.

Purchased trigger boards place the three guaranteed Scatter on three randomly chosen distinct reels, each with a random row. Rows may repeat naturally. The decorative board still never shows unpaid winning lines. Price, eight initial free spins and feature odds are unchanged. The reproducible Monte Carlo audit was refreshed because drawing the cosmetic positions consumes additional random numbers.

Verified 21 focused tests, including 300 purchases with varied layouts, all reels/rows represented, exact cost, no unpaid line wins, separation of the applied and next multiplier, and capped payout presentation. Reference review now includes a completed feature in the official live Gates of Olympus demo at https://www.pragmaticplay.com/en/games/gates-of-olympus/, plus the official mobile screenshot at https://www.playngo.com/games/rich-wilde-and-the-book-of-dead. Age confirmation succeeded after the user's repeated explicit authorization. Only simulated credits were used; demo audio was not audible through the browser tool.

The feature atmosphere now changes the full-screen background and reel tint after the entry spin settles. The signal caption identifies the current multiplier during a spin and the next multiplier between spins. A winning bonus spin displays base win × applied multiplier = actual win. A capped payout displays the round limit instead of an equation using the uncapped amount; after the feature, the last applied multiplier is identified explicitly.

The cloud browser rejected the local QA URL with ERR_BLOCKED_BY_CLIENT; the latest console and display logic were checked with the DOM harness, not a fresh browser screenshot. Earlier mobile screenshots and full-suite counts above describe their respective prior verification runs.

## Administrator bonus test

Admins see “Тест бонуса · 2500×” beneath the console when no feature is active. Confirmation shows the ordinary 100-stake purchase cost and the exact final payout. The server authorizes `testMax: true` using the same admin predicate as the app; changing the client flag cannot grant access. The test is a saved, explicitly marked purchased feature: three Scatter, eight free spins, rising multipliers and a final capped payout of exactly 2500 unit stakes. It uses normal debit, persistence, revision protection and one-time settlement. Only this round carries the flag; ordinary spins and purchases reset it. Tests cover non-admin rejection, eight resumed spins, duplicate actions, exact settlement, option validation and button visibility.
