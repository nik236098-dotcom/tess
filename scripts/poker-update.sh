#!/usr/bin/env bash
set -euo pipefail
# Run as root on the user's existing installation. No balances, tokens or other
# runtime data are copied or reset. The first pre-experiment commit is retained.
cd /opt/poker/app
pgit() { sudo -u poker git "$@"; }
mode=${1:-install}
backup_ref=refs/heads/backup/pre-amethyst
if [[ $(id -u) -ne 0 ]]; then
  echo 'Запустите команду через sudo.' >&2; exit 1
fi
if [[ -n $(pgit status --porcelain --untracked-files=no) ]]; then
  echo 'На сервере есть несохранённые изменения кода. Установка остановлена, ваши изменения сохранены на месте.' >&2; exit 1
fi
before=$(pgit rev-parse HEAD)
if [[ "$mode" == rollback ]]; then
  target=$(pgit rev-parse --verify "$backup_ref")
elif [[ "$mode" == install ]]; then
  target=$(pgit rev-parse --verify FETCH_HEAD)
  pgit cat-file -e "$target:public/amethyst.js"
  pgit cat-file -e "$target:server/poker/bot.js"
  if ! pgit show-ref --verify --quiet "$backup_ref"; then
    pgit update-ref "$backup_ref" "$before"
  fi
else
  echo 'Допустимы install или rollback.' >&2; exit 1
fi
systemctl stop poker
recover() {
  trap - ERR
  echo 'Не удалось запустить обновление. Возвращаю предыдущую версию.' >&2
  pgit checkout --detach "$before"
  systemctl start poker
  exit 1
}
trap recover ERR
pgit checkout --detach "$target"
node --check server/index.js
node --check public/app.js
systemctl start poker
systemctl is-active --quiet poker
trap - ERR
if [[ "$mode" == rollback ]]; then
  echo 'Прежняя версия восстановлена.'
else
  echo 'Покер обновлён. Перезапустите мини-приложение Telegram.'
fi
