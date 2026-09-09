#!/usr/bin/env bash
set -euo pipefail
cd /opt/poker/app
pgit() { sudo -u poker git "$@"; }
[[ $(id -u) -eq 0 ]] || { echo 'Запустите через sudo'; exit 1; }
[[ -z $(pgit status --porcelain --untracked-files=no) ]] || { echo 'Есть несохранённые изменения. Обновление остановлено.'; exit 1; }
mode=${1:-install}
before=$(pgit rev-parse HEAD)
if [[ "$mode" == rollback ]]; then
  target=$(pgit rev-parse --verify refs/heads/backup/pre-hilo)
elif [[ "$mode" == install ]]; then
  target=$(pgit rev-parse --verify FETCH_HEAD)
  pgit cat-file -e "$target:server/hilo/game.js"
  pgit update-ref refs/heads/backup/pre-hilo "$before"
else
  echo 'Допустимы install или rollback'; exit 1
fi
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
systemctl start poker
systemctl is-active --quiet poker
trap - ERR
echo 'Готово. Полностью закройте и откройте мини-приложение.'
