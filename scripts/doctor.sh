#!/usr/bin/env bash
# Проверяет всю цепочку: Node → приложение → nginx → сертификат → внешний доступ.
#
#   sudo bash scripts/doctor.sh [ДОМЕН] [ПОРТ]
#
# Домен и порт можно не указывать — возьмутся из конфига nginx.
# Секреты не печатаются: от токена показывается только номер бота.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="/etc/nginx/sites-available/poker"

DOMAIN="${1:-$(grep -m1 -oP 'server_name\s+\K[^;]+' "$CONF" 2>/dev/null | tr -d ' ')}"
PORT="${2:-$(grep -m1 -oP 'listen\s+\K\d+(?=\s+ssl)' "$CONF" 2>/dev/null)}"
PORT="${PORT:-443}"

ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$1"; PROBLEMS+=("$1"); }
warn() { printf '  \033[33m•\033[0m %s\n' "$1"; }
head2() { printf '\n\033[1m%s\033[0m\n' "$1"; }

PROBLEMS=()

head2 "Node"
if NODE_BIN="$(command -v node)"; then
  ok "$NODE_BIN $(node -v)"
else
  bad "Node не установлен: curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt install -y nodejs"
fi

head2 "Настройки (.env)"
ENV_FILE="$APP_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  ok "файл есть: $ENV_FILE"
  get() { grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2-; }
  TOKEN="$(get TELEGRAM_BOT_TOKEN)"
  if [[ -z "$TOKEN" ]]; then
    bad "TELEGRAM_BOT_TOKEN пуст"
  elif [[ "$TOKEN" == 123456:* ]]; then
    bad "TELEGRAM_BOT_TOKEN — заглушка из .env.example, впишите настоящий"
  else
    ok "токен бота №${TOKEN%%:*}"
  fi
  [[ -n "$(get TELEGRAM_ADMIN_IDS)" ]] && ok "админы: $(get TELEGRAM_ADMIN_IDS)" || bad "TELEGRAM_ADMIN_IDS пуст — выдавать фишки будет некому"
  [[ -n "$(get TELEGRAM_BOT_USERNAME)" ]] && ok "имя бота: $(get TELEGRAM_BOT_USERNAME)" || warn "TELEGRAM_BOT_USERNAME пуст — кнопка «позвать друзей» будет копировать код"
  APP_PORT="$(get PORT)"; APP_PORT="${APP_PORT:-3000}"
  ok "порт приложения: $APP_PORT"
else
  bad "нет файла $ENV_FILE — скопируйте .env.example и впишите токен"
  APP_PORT=3000
fi

head2 "Сервис poker"
if systemctl list-unit-files 2>/dev/null | grep -q '^poker\.service'; then
  if systemctl is-active --quiet poker; then
    ok "запущен ($(systemctl show -p ActiveEnterTimestamp --value poker))"
  else
    bad "сервис есть, но не запущен: systemctl start poker; journalctl -u poker -n 30"
  fi
  EXEC="$(systemctl show -p ExecStart --value poker | grep -oP 'path=\K[^ ;]+' | head -1)"
  [[ -n "$EXEC" && -x "$EXEC" ]] && ok "ExecStart: $EXEC" || bad "ExecStart указывает в никуда: $EXEC"
else
  bad "юнит poker.service не создан — см. DEPLOY.md, шаг 5"
fi

head2 "Приложение внутри сервера"
if curl -fsS --max-time 5 "http://127.0.0.1:$APP_PORT/health" >/dev/null 2>&1; then
  ok "http://127.0.0.1:$APP_PORT/health отвечает"
else
  bad "приложение не отвечает на 127.0.0.1:$APP_PORT — смотрите journalctl -u poker -n 30"
fi

head2 "Домен"
if [[ -z "$DOMAIN" ]]; then
  bad "не удалось определить домен, передайте его аргументом: bash scripts/doctor.sh ваш.домен"
else
  ok "домен: $DOMAIN, порт HTTPS: $PORT"
  SERVER_IP="$(curl -fsS -4 --max-time 8 ifconfig.me 2>/dev/null)"
  DOMAIN_IPS="$(getent ahosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')"
  if [[ -z "$DOMAIN_IPS" ]]; then
    bad "домен не резолвится"
  elif [[ -z "$SERVER_IP" ]]; then
    warn "не удалось узнать внешний IP сервера, сверьте сами: домен → $DOMAIN_IPS"
  elif [[ " $DOMAIN_IPS " == *" $SERVER_IP "* ]]; then
    ok "указывает на этот сервер ($SERVER_IP)"
  else
    bad "указывает на $DOMAIN_IPS, а сервер — $SERVER_IP"
  fi
fi

head2 "Nginx"
if systemctl is-active --quiet nginx; then
  ok "запущен"
else
  bad "не запущен: systemctl start nginx; journalctl -u nginx -n 20"
fi
if nginx -t >/dev/null 2>&1; then
  ok "конфиг валиден"
else
  bad "конфиг с ошибкой — подробности: nginx -t"
fi
DUPES="$(grep -rls "server_name[[:space:]].*$DOMAIN" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v '/poker$')"
[[ -n "$DUPES" ]] && bad "на этот домен есть ещё конфиг: $DUPES (уберите лишний)" || ok "дублирующих конфигов нет"

head2 "Порт $PORT"
OWNER="$(ss -tlnp 2>/dev/null | awk -v p=":$PORT " '$4 ~ p {print $NF}' | head -1)"
if [[ -z "$OWNER" ]]; then
  bad "порт $PORT никто не слушает"
elif [[ "$OWNER" == *nginx* ]]; then
  ok "слушает nginx"
else
  bad "порт занят не nginx: $OWNER — поднимите покер на другом порту: sudo bash scripts/setup-https.sh $DOMAIN почта 8443"
fi

head2 "Сертификат"
CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
if [[ -s "$CERT" ]]; then
  ok "есть, годен до $(openssl x509 -enddate -noout -in "$CERT" 2>/dev/null | cut -d= -f2)"
else
  bad "нет сертификата для $DOMAIN — sudo bash scripts/setup-https.sh $DOMAIN ваша@почта $PORT"
fi

head2 "Снаружи"
URL="https://$DOMAIN"; [[ "$PORT" != "443" ]] && URL="https://$DOMAIN:$PORT"
CODE="$(curl -so /dev/null -w '%{http_code}' --max-time 10 "$URL/health" 2>/dev/null)"
if [[ "$CODE" == "200" ]]; then
  ok "$URL/health отвечает 200 — можно идти в BotFather"
else
  bad "$URL/health не отвечает (код: ${CODE:-нет соединения})"
fi

echo
if [[ ${#PROBLEMS[@]} -eq 0 ]]; then
  printf '\033[32mВсё в порядке.\033[0m В BotFather: /newapp → Web App URL: %s, Short name: poker\n' "$URL"
else
  printf '\033[1mЧинить по порядку:\033[0m\n'
  printf '  %s\n' "${PROBLEMS[@]}"
fi
