# Crocodile theme experiment

The poker screen loads the new theme by default. Use **Дизайн: новый / Дизайн: прежний** above the controls to switch immediately; the choice is saved on that device. Switching does not send game actions or reload the connection.

Scope: purple table, smaller seats, upright cards, compact glossy bets, crocodile K/Q/J art and spade ace, purple emblem back. All ranks and suits are rendered from game data. Non-spade aces and numbered cards retain clear conventional suit symbols. Other games keep their current card styles.

Run: `npm start`. Tests: `npm test` (171 passed).

This branch is based on afe3d62, the version used for the design review. Do not replace a newer production checkout wholesale. Apply/review the theme commit against the deployed branch first.

Rollback on a device: press **Дизайн: новый** so it changes to **Дизайн: прежний**. Full source rollback: revert the isolated theme commit. No server, database or game rules changed.
