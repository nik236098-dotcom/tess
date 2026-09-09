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
node --check public/client-connection.js
node --check public/crash.js
node --check server/crash/game.js
node --check server/crash/service.js
node --check public/arcade.js
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
systemctl start poker
systemctl is-active --quiet poker
trap - ERR
echo 'Готово. Полностью закройте и откройте мини-приложение.'
