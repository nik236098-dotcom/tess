#!/usr/bin/env bash
# Обновление beeline одной командой: git pull → проверка install.py → установка → перезапуск службы.
#
#   sudo bash /root/tess/operator_repair_1591/update.sh
#
#   или без клона на сервере (скрипт сам найдёт /root/tess или ~/tess, иначе склонирует в /root/tess):
#   curl -fsSL https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/update.sh | sudo bash
#
# Сборка выбирается как стоит на сервере: lite (без кода подписи r31), если в /opt/beeline/test_beeline.py
# нет маркера SIGN_ROBUST_1591R31, иначе полная. BUILD=lite или BUILD=full меняют выбор явно.
# Переменные: APP_DIR (/opt/beeline), REPO (путь к клону), BRANCH, CHECK=1 — только проверка, ничего не
#   менять; NO_PULL=1 — не трогать git; NO_RESTART=1 — установить без перезапуска (служба должна быть
#   остановлена, иначе install.py откажется).
# После первого запуска под sudo появляются короткие команды (в /usr/local/bin):
#   sudo beeline-update                 — это же обновление
#   sudo beeline-tariff <ссылка заказа> — тариф и цена заказа до оплаты (tools/order_tariff.py)
#   sudo beeline-order                  — состояние последних заказов на сайте (tools/order_status.py)
#   sudo beeline-links                  — ссылки заказов по строкам из журнала (tools/row_links.py)
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/beeline}"
BRANCH="${BRANCH:-codex/operator-observer-15.87}"
REPO_URL="${REPO_URL:-https://github.com/nik236098-dotcom/tess.git}"
SERVICE="beeline"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

if [[ $EUID -ne 0 && -z "${CHECK:-}" ]]; then
  die "запусти через sudo (или CHECK=1 для проверки без установки)"
fi
[[ -f "$APP_DIR/test_beeline.py" ]] || die "в $APP_DIR нет test_beeline.py — это не установленный бот; для чистого сервера есть fresh_install.sh"

# 1. Репозиторий: REPO, рядом со скриптом, /root/tess, домашние папки; иначе свежий клон в /root/tess.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-/dev/null}")" 2>/dev/null && pwd || true)"
if [[ -z "${REPO:-}" ]]; then
  for candidate in "${SCRIPT_DIR:+$SCRIPT_DIR/..}" /root/tess "${SUDO_USER:+/home/$SUDO_USER/tess}" "$HOME/tess" /home/*/tess; do
    [[ -n "$candidate" && -f "$candidate/operator_repair_1591/fix_package_1591.py" ]] || continue
    REPO="$(cd "$candidate" && pwd)"; break
  done
fi
if [[ -z "${REPO:-}" ]]; then
  [[ -z "${NO_PULL:-}" ]] || die "репозиторий не найден (укажи REPO=/путь/к/tess)"
  REPO=/root/tess
  say "Клонирую $REPO_URL ($BRANCH) в $REPO"
  command -v git >/dev/null || die "нужен git: apt-get install -y git"
  git clone -q -b "$BRANCH" "$REPO_URL" "$REPO"
elif [[ -z "${NO_PULL:-}" ]]; then
  say "Обновляю $REPO ($BRANCH)"
  OWNER="$(stat -c %U "$REPO")"
  git_as_owner() {
    if [[ $EUID -eq 0 && "$OWNER" != root ]]; then sudo -u "$OWNER" git -C "$REPO" "$@"; else git -C "$REPO" -c safe.directory='*' "$@"; fi
  }
  git_as_owner fetch -q origin "$BRANCH" || die "git fetch не прошёл (сеть/прокси?)"
  if [[ "$(git_as_owner rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]]; then
    git_as_owner checkout -q "$BRANCH"
  fi
  git_as_owner merge -q --ff-only "origin/$BRANCH" \
    || die "в $REPO есть свои правки, обновление не сводится; сохрани их или выполни: git -C $REPO reset --hard origin/$BRANCH"
  printf 'Коммит: %s\n' "$(git_as_owner log -1 --format='%h %s')"
fi

# 2. Сборка (lite/full) и последняя папка пакета этой сборки.
if [[ -z "${BUILD:-}" ]]; then
  if grep -q SIGN_ROBUST_1591R31 "$APP_DIR/test_beeline.py"; then BUILD=full; else BUILD=lite; fi
fi
case "$BUILD" in
  lite) PATTERN='_r[0-9]+_lite$' ;;
  full) PATTERN='_r[0-9]+$' ;;
  *) die "BUILD=$BUILD; допустимо lite или full" ;;
esac
PACKAGE="$(ls -d "$REPO"/operator_repair_1591/beeline_integrated_io_15_91_r*/ 2>/dev/null \
  | sed -E 's#/$##' | grep -E "$PATTERN" | sed -E 's#(.*_r)([0-9]+)(_lite)?$#\2 \0#' | sort -n | tail -1 | cut -d' ' -f2-)"
[[ -n "$PACKAGE" && -f "$PACKAGE/install.py" ]] || die "в репозитории нет папки пакета для сборки $BUILD"
REVISION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["revision"])' "$PACKAGE/manifest.json")"
say "Пакет: $(basename "$PACKAGE") (ревизия $REVISION, сборка $BUILD)"

# 3. Короткие команды без путей: beeline-update, beeline-tariff, beeline-order (BIN_DIR, по умолчанию /usr/local/bin).
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
if [[ $EUID -eq 0 || -n "${BIN_DIR_FORCE:-}" ]] && mkdir -p "$BIN_DIR" 2>/dev/null; then
  PY="$APP_DIR/venv/bin/python"; [[ -x "$PY" ]] || PY="python3"
  write_wrapper() {  # name, command line (the arguments of the user are appended)
    printf '#!/usr/bin/env bash\n# beeline: создано update.sh, репозиторий %s\nexec %s "$@"\n' "$REPO" "$2" > "$BIN_DIR/$1.tmp" \
      && chmod 0755 "$BIN_DIR/$1.tmp" && mv -f "$BIN_DIR/$1.tmp" "$BIN_DIR/$1"
  }
  write_wrapper beeline-update "bash '$REPO/operator_repair_1591/update.sh'"
  write_wrapper beeline-tariff "'$PY' '$REPO/operator_repair_1591/tools/order_tariff.py'"
  write_wrapper beeline-order "'$PY' '$REPO/operator_repair_1591/tools/order_status.py'"
  write_wrapper beeline-links "'$PY' '$REPO/operator_repair_1591/tools/row_links.py'"
  echo "Команды: sudo beeline-update | sudo beeline-tariff <ссылка> | sudo beeline-order | sudo beeline-links (в $BIN_DIR)"
fi

# 4. Проверка без изменений, затем установка с перезапуском.
say "Проверка"
python3 "$PACKAGE/install.py" --app "$APP_DIR"
if [[ -n "${CHECK:-}" ]]; then
  say "CHECK=1: ничего не менял"
  exit 0
fi
say "Установка"
if [[ -n "${NO_RESTART:-}" ]]; then
  python3 "$PACKAGE/install.py" --app "$APP_DIR" --apply
else
  python3 "$PACKAGE/install.py" --app "$APP_DIR" --apply --restart
fi

# 5. Итог: ревизия на сервере и состояние службы.
INSTALLED="$(python3 - "$APP_DIR/test_beeline.py" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
revs = [int(m) for m in re.findall(r"_1591R(\d+)\b", src)]
print(max(revs) if revs else "?")
PY
)"
say "На сервере ревизия $INSTALLED ($BUILD)"
if command -v systemctl >/dev/null && systemctl list-unit-files "$SERVICE.service" >/dev/null 2>&1; then
  sleep 3
  systemctl is-active "$SERVICE" >/dev/null 2>&1 && echo "Служба $SERVICE: active" || echo "Служба $SERVICE: $(systemctl is-active "$SERVICE" 2>/dev/null || true) — смотри: journalctl -u $SERVICE -n 50"
fi
