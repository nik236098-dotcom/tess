#!/usr/bin/env bash
# Спрашивает по очереди токен Telegram, id чата, прокси и ключ DeepSeek и записывает их в конфиги бота.
#
#   sudo bash /root/tess/operator_repair_1591/tools/set_secrets.sh          # или: sudo beeline-secrets
#
# Пустой ответ оставляет прежнее значение (если оно было). Для прокси «direct» или пустой ответ без
# прежнего значения означает «без прокси». После записи служба beeline перезапускается, если она есть.
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/beeline}"
[[ $EUID -eq 0 ]] || { echo "запусти через sudo" >&2; exit 1; }
[[ -d "$APP_DIR" ]] || { echo "нет папки $APP_DIR" >&2; exit 1; }
TG="$APP_DIR/telegram_config.json"; DS="$APP_DIR/deepseek_config.json"

current() { python3 - "$1" "$2" <<'PY' 2>/dev/null || true
import json, sys
try:
    print(json.load(open(sys.argv[1])).get(sys.argv[2]) or "")
except Exception:
    print("")
PY
}
mask() { local v="$1"; [[ -z "$v" ]] && { echo "пусто"; return; }; echo "${v:0:4}…${v: -3}"; }
ask() {  # var prompt secret current
  local var="$1" prompt="$2" secret="$3" cur="$4" value
  if [[ -n "$secret" ]]; then
    read -r -s -p "$prompt [сейчас: $(mask "$cur"); Enter — оставить]: " value </dev/tty; echo
  else
    read -r -p "$prompt [сейчас: ${cur:-пусто}; Enter — оставить]: " value </dev/tty
  fi
  printf -v "$var" '%s' "${value:-$cur}"
}

ask TOKEN   "Токен Telegram-бота (из BotFather)" secret "$(current "$TG" token)"
ask CHAT    "ID чата Telegram (цифры, у группы с минусом)" "" "$(current "$TG" chat_id)"
ask PROXY   "Прокси для Telegram socks5h://логин:пароль@хост:порт, или direct" "" "$(current "$TG" proxy)"
ask DSKEY   "Ключ DeepSeek" secret "$(current "$DS" api_key)"
PROXY="${PROXY:-direct}"

[[ -n "$TOKEN" && -n "$CHAT" && -n "$DSKEY" ]] || { echo "ОШИБКА: токен, id чата и ключ DeepSeek обязательны" >&2; exit 1; }
[[ "$TOKEN" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{30,}$ ]] || echo "ВНИМАНИЕ: токен Telegram обычно выглядит как 123456789:AAAA…; проверь, что скопирован целиком"

python3 - "$TG" "$DS" "$TOKEN" "$CHAT" "$PROXY" "$DSKEY" <<'PY'
import json, pathlib, sys
tg, ds, token, chat, proxy, key = sys.argv[1:7]
def load(p):
    try:
        return json.loads(pathlib.Path(p).read_text("utf-8"))
    except Exception:
        return {}
t = load(tg); t.update({"token": token, "chat_id": chat, "proxy": proxy})
d = load(ds); d["api_key"] = key
pathlib.Path(tg).write_text(json.dumps(t, ensure_ascii=False, indent=2), "utf-8")
pathlib.Path(ds).write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
print("Записано:", tg, "и", ds)
PY
chmod 600 "$TG" "$DS"
if command -v systemctl >/dev/null && systemctl list-unit-files beeline.service >/dev/null 2>&1; then
  systemctl restart beeline && echo "Служба beeline перезапущена"
fi
