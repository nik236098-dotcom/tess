#!/usr/bin/env bash
set -euo pipefail
cd /opt/poker/app
app_dir=$PWD
pgit() { sudo -u poker git -C "$app_dir" "$@"; }
# Use the same Node binary as poker.service, not root's optional nvm runtime.
node() { /usr/bin/node "$@"; }
[[ $(id -u) -eq 0 ]] || { echo 'Запустите через sudo'; exit 1; }
for dependency in flock tar curl; do command -v "$dependency" >/dev/null; done
[[ -x /usr/bin/node ]]
exec 9>/run/lock/poker-update.lock
flock -n 9 || { echo 'Другое обновление уже выполняется.' >&2; exit 1; }
[[ -z $(pgit status --porcelain --untracked-files=no) ]] || { echo 'Есть несохранённые изменения. Обновление остановлено.'; exit 1; }
before=$(pgit rev-parse HEAD)
target=$(pgit rev-parse --verify FETCH_HEAD)
pgit cat-file -e "$target:server/crash/game.js"
staging=''
switching=0
ready() {
  local deadline=$((SECONDS + 45))
  local successes=0
  while (( SECONDS < deadline )); do
    if systemctl is-active --quiet poker && curl --fail --silent --connect-timeout 1 --max-time 2 --output /dev/null http://127.0.0.1:3000/config; then
      successes=$((successes + 1))
      if (( successes >= 2 )); then return 0; fi
    else
      successes=0
    fi
    sleep 1
  done
  return 1
}
cleanup() {
  local result=$?
  trap - EXIT INT TERM
  set +e
  if (( switching )); then
    echo 'Новая версия не подтвердила запуск. Возвращаем предыдущую…' >&2
    systemctl stop poker
    if pgit checkout --detach "$before" && systemctl reset-failed poker && systemctl start poker && ready; then
      echo 'Предыдущая версия восстановлена и отвечает по HTTP.' >&2
    else
      echo 'Автоматическое восстановление не подтверждено. Проверьте journalctl -u poker.' >&2
    fi
    result=1
  fi
  if [[ -n "$staging" ]]; then rm -rf -- "$staging"; fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Validate a snapshot of the exact target while the current service keeps serving.
echo 'Проверяем новую версию. Сайт продолжает работать…'
staging=$(mktemp -d /tmp/croco-update.XXXXXXXX)
pgit archive "$target" public server | tar -x -C "$staging"
cd "$staging"
node --check server/index.js
node --check public/app.js
node --check public/croco-lobby.js
node --check public/amethyst.js
node --check public/client-connection.js
node --check public/telegram-display.js
node --check public/crash.js
node --check server/crash/game.js
node --check server/crash/service.js
node --check public/arcade.js
node --check public/abyss-rules.js
node --check public/abyss-ui.js
node --check public/abyss-audio.js
node --check public/abyss-fx.js
node --check server/arcade/abyss.js
node --check public/feature-slots-rules.js
node --check public/feature-slots-ui.js
node --check public/feature-slots-audio.js
node --check server/arcade/feature-slots.js
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
  const path = `public${catalog.artwork(id)}`;
  if (!fs.statSync(path).size) throw new Error(`Empty game artwork: ${path}`);
}
for (const id of [...require('./public/abyss-rules').symbols.map(s=>s.id),'station']) {
  const path = `public/img/abyss/${id}.webp`;
  if (!fs.statSync(path).size) throw new Error(`Empty Abyss artwork: ${path}`);
}
for (const [game, rules] of Object.entries(require('./public/feature-slots-rules'))) {
  for (const id of ['scene-v2', 'symbols-v2']) {
    const path = `public/img/feature-slots/${game}/${id}.webp`;
    if (!fs.statSync(path).size) throw new Error(`Empty slot artwork: ${path}`);
  }
}
for (const path of ['public/img/croco/glass-banner.webp', 'public/img/croco/glass-reference.webp', 'public/img/croco/popular-atlas.webp', 'public/croco-lobby.css', 'public/img/croco/mascot.webp', 'public/img/croco/nvuti-banner.webp', 'public/feature-slots.css', 'public/abyss.css', 'public/game-shell.css', 'public/game-catalog.css', 'public/fishing.css', 'public/duel-games.css', 'public/img/race/car-v2.webp', 'public/tower.css', 'public/andar.css', 'public/img/rps/rock-v2.webp', 'public/img/rps/paper-v2.webp', 'public/img/rps/scissors-v2.webp']) {
  if (!fs.statSync(path).size) throw new Error(`Empty game asset: ${path}`);
}
JS

cd "$app_dir"
# Reject concurrent edits made outside this updater during the preflight.
[[ $(pgit rev-parse HEAD) == "$before" && -z $(pgit status --porcelain --untracked-files=no) ]] || { echo 'Рабочая копия изменилась во время проверки. Обновление остановлено.' >&2; exit 1; }
pgit update-ref refs/croco/last-good "$before"
echo 'Проверки пройдены. Перезапускаем сервис и ждём HTTP-ответ…'
switching=1
systemctl stop poker
pgit checkout --detach "$target"
systemctl reset-failed poker
systemctl start poker
if ! ready; then
  echo 'Приложение не ответило за 45 секунд.' >&2
  exit 1
fi
switching=0
echo "Готово: ${target:0:7}. Приложение отвечает по HTTP. Полностью закройте и откройте мини-приложение."
