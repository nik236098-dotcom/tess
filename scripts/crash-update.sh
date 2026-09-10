#!/usr/bin/env bash
set -euo pipefail
cd /opt/poker/app
pgit() { sudo -u poker git "$@"; }
[[ $(id -u) -eq 0 ]] || { echo 'Запустите через sudo'; exit 1; }
[[ -z $(pgit status --porcelain --untracked-files=no) ]] || { echo 'Есть несохранённые изменения. Обновление остановлено.'; exit 1; }
before=$(pgit rev-parse HEAD)
target=$(pgit rev-parse --verify FETCH_HEAD)
pgit cat-file -e "$target:server/crash/game.js"
systemctl stop poker
recover() {
  trap - ERR
  pgit checkout --detach "$before"
  systemctl start poker
  echo 'Ошибка запуска. Предыдущая версия возвращена.' >&2
  exit 1
}
trap recover ERR
pgit checkout --detach "$target"
node --check server/index.js
node --check public/app.js
node --check public/amethyst.js
node --check public/client-connection.js
node --check public/telegram-display.js
node --check public/crash.js
node --check server/crash/game.js
node --check server/crash/service.js
node --check public/arcade.js
node --check public/abyss-rules.js
node --check public/abyss-ui.js
node --check server/arcade/abyss.js
node --check public/plinko-motion.js
node --check server/arcade/game.js
node --check server/arcade/service.js
node --check server/arcade/catalog.js
node --check public/casino-rules.js
node --check public/casino-art.js
node --check public/casino-ui.js
node --check public/casino-motion.js
node --check public/chicken-scene.js
node --check public/darts-rules.js
node --check public/darts-scene.js
node --check public/darts-audio.js
node --check public/darts-game.js
node --check public/bowling-physics.js
node --check public/bowling-scene.js
node --check public/balloon-scene.js
node --check public/race-scene.js
node --check public/race-renderer.js
node --check public/fishing-scene.js
node --check public/duel-art.js
node --check public/game-catalog.js
node --check public/game-layout.js
node --check public/game-result.js
node --check public/classic-cards.js
node --check public/blackjack-deal.js
node --check public/roulette-view.js
node --check server/accounts.js
node - <<'JS'
const fs = require('node:fs');
const catalog = require('./public/game-catalog');
for (const id of Object.keys(catalog.names)) {
  const path = `public/img/game-cards/${catalog.file(id)}.webp`;
  if (!fs.statSync(path).size) throw new Error(`Empty game artwork: ${path}`);
}
for (const id of [...require('./public/abyss-rules').symbols.map(s=>s.id),'station']) {
  const path = `public/img/abyss/${id}.webp`;
  if (!fs.statSync(path).size) throw new Error(`Empty Abyss artwork: ${path}`);
}
for (const path of ['public/abyss.css', 'public/game-shell.css', 'public/game-catalog.css', 'public/fishing.css', 'public/duel-games.css', 'public/img/race/car-v2.webp', 'public/tower.css', 'public/andar.css', 'public/img/rps/rock-v2.webp', 'public/img/rps/paper-v2.webp', 'public/img/rps/scissors-v2.webp']) {
  if (!fs.statSync(path).size) throw new Error(`Empty game asset: ${path}`);
}
JS
systemctl start poker
systemctl is-active --quiet poker
trap - ERR
echo 'Готово. Полностью закройте и откройте мини-приложение.'
