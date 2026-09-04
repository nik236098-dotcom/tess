#!/usr/bin/env bash
# Настраивает nginx и HTTPS для покерного стола.
#
#   sudo bash scripts/setup-https.sh ДОМЕН ПОЧТА [ПОРТ]
#
# Порт по умолчанию 443. Если он занят другим сервисом (например VPN),
# укажите свободный, например 8443:
#
#   sudo bash scripts/setup-https.sh pokergena.duckdns.org me@example.com 8443
#
# Скрипт сам пишет конфиг nginx (включая заголовки для WebSocket), получает
# сертификат Let's Encrypt и проверяет результат. Повторный запуск безопасен.

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
PORT="${3:-443}"
APP_PORT="${APP_PORT:-3000}"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  cat <<'USAGE'
Использование:
  sudo bash scripts/setup-https.sh ДОМЕН ПОЧТА [ПОРТ]

Домен — настоящее имя, A-запись которого указывает на этот сервер.
Бесплатное имя можно за пару минут получить на duckdns.org:

  sudo bash scripts/setup-https.sh pokergena.duckdns.org me@example.com
  sudo bash scripts/setup-https.sh pokergena.duckdns.org me@example.com 8443
USAGE
  exit 1
fi

# Самая обидная осечка: в команду скопировали «ваша@почта» из инструкции.
if ! [[ "$EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  echo "«$EMAIL» не похоже на адрес почты. Подставьте свой настоящий:"
  echo "  sudo bash scripts/setup-https.sh $DOMAIN me@example.com $PORT"
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "Запустите через sudo: sudo bash scripts/setup-https.sh $DOMAIN $EMAIL $PORT"
  exit 1
fi

CONF_NAME="poker"
CONF_FILE="/etc/nginx/sites-available/$CONF_NAME"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# ——— Проверяем, куда указывает домен ———

echo "→ Проверяю, куда указывает $DOMAIN"
SERVER_IPV4="$(curl -fsS -4 --max-time 10 ifconfig.me 2>/dev/null || true)"
SERVER_IPV6="$(curl -fsS -6 --max-time 10 ifconfig.me 2>/dev/null || true)"
DOMAIN_IPS="$(getent ahosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)"

if [[ -z "$DOMAIN_IPS" ]]; then
  echo "  Имя $DOMAIN не резолвится. Заведите A-запись на $SERVER_IPV4 и подождите пару минут."
  exit 1
fi
echo "  $DOMAIN → $(echo "$DOMAIN_IPS" | tr '\n' ' ')"

MATCHED=0
for ip in $DOMAIN_IPS; do
  [[ "$ip" == "$SERVER_IPV4" || ( -n "$SERVER_IPV6" && "$ip" == "$SERVER_IPV6" ) ]] && MATCHED=1
done
if [[ "$MATCHED" -eq 0 ]]; then
  echo "  Домен указывает не на этот сервер ($SERVER_IPV4) — сертификат не выпустится."
  exit 1
fi

# Частая беда бесплатных DNS: заполнили поле IPv6 наугад.
# Let's Encrypt предпочитает AAAA и уходит проверять в никуда.
STRAY_IPV6="$(echo "$DOMAIN_IPS" | grep ':' || true)"
if [[ -n "$STRAY_IPV6" && "$STRAY_IPV6" != "$SERVER_IPV6" ]]; then
  echo "  У домена есть AAAA-запись $STRAY_IPV6, а сервер по ней недоступен."
  echo "  Очистите поле ipv6 у DNS-провайдера и повторите."
  exit 1
fi

# ——— Ставим, чего не хватает ———

echo "→ Ставлю nginx и certbot, если их нет"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl >/dev/null

# ——— Ищем чужие конфиги и занятые порты ———

CONFLICTS="$(grep -rls "server_name[[:space:]].*$DOMAIN" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v "/$CONF_NAME\$" || true)"
if [[ -n "$CONFLICTS" ]]; then
  echo "→ Для $DOMAIN уже есть другой конфиг nginx:"
  echo "$CONFLICTS" | sed 's/^/     /'
  echo "  Два блока на один домен nginx не примет. Выключите лишний и повторите:"
  echo "$CONFLICTS" | sed 's|^|     mv |; s|$| /root/|'
  exit 1
fi

# Кто держит нужный порт: чужой сервис на 443 — самая частая причина
# «сайт по HTTPS не отвечает», при том что nginx жив и настроен верно.
PORT_OWNER="$(ss -tlnp 2>/dev/null | awk -v p=":$PORT\$" '$4 ~ p {print $NF}' | head -n1 || true)"
if [[ -n "$PORT_OWNER" && "$PORT_OWNER" != *nginx* ]]; then
  echo "→ Порт $PORT занят не nginx, а вот этим:"
  echo "     $PORT_OWNER"
  echo
  echo "  Такое бывает, когда на сервере уже живёт VPN или панель управления."
  echo "  Поднимите покер на свободном порту, например 8443:"
  echo "     sudo bash scripts/setup-https.sh $DOMAIN $EMAIL 8443"
  exit 1
fi

# ——— Конфиг только на 80: он нужен, чтобы Let's Encrypt проверил домен ———

echo "→ Пишу конфиг nginx"
cat > "$CONF_FILE" <<CONF
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ { root /var/www/html; }

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 3600s;
    }
}
CONF

ln -sf "$CONF_FILE" "/etc/nginx/sites-enabled/$CONF_NAME"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx
systemctl is-active --quiet nginx || {
  echo "  Nginx не поднялся. Смотрите: journalctl -u nginx -n 20 --no-pager"
  exit 1
}

# ——— Сертификат ———

if [[ -s "$CERT_DIR/fullchain.pem" ]]; then
  echo "→ Сертификат уже выпущен, заново не прошу"
else
  echo "→ Выпускаю сертификат"
  if ! certbot certonly --nginx -d "$DOMAIN" --agree-tos -m "$EMAIL" --non-interactive; then
    echo
    echo "  Certbot не справился. Частые причины:"
    echo "   • порт 80 закрыт снаружи — проверьте: ufw status"
    echo "   • домен указывает не на этот сервер"
    echo "   • у домена есть AAAA-запись, а по IPv6 сервер недоступен"
    exit 1
  fi
fi

if [[ ! -s "$CERT_DIR/fullchain.pem" ]]; then
  echo "  Сертификат не появился в $CERT_DIR — HTTPS не заработает."
  exit 1
fi

# ——— Итоговый конфиг: 80 редиректит, рабочий порт отдаёт HTTPS ———

REDIRECT_HOST="\$host"
[[ "$PORT" != "443" ]] && REDIRECT_HOST="\$host:$PORT"

cat > "$CONF_FILE" <<CONF
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$REDIRECT_HOST\$request_uri; }
}

server {
    listen $PORT ssl;
    server_name $DOMAIN;

    ssl_certificate     $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;

        # Без этих двух строк не работает WebSocket, а значит и сам стол
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
CONF

nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx

echo "→ Открываю порты в файрволе"
if command -v ufw >/dev/null; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow "$PORT/tcp" >/dev/null 2>&1 || true
fi

# ——— Проверяем, что получилось ———

if ! ss -tln 2>/dev/null | grep -q ":$PORT "; then
  echo "  Nginx не слушает $PORT. Смотрите: nginx -T | grep -n 'listen $PORT'"
  exit 1
fi

URL="https://$DOMAIN"
[[ "$PORT" != "443" ]] && URL="https://$DOMAIN:$PORT"

echo "→ Проверяю, отвечает ли приложение"
if curl -fsS --max-time 10 "$URL/health" >/dev/null; then
  echo "  Приложение отвечает по HTTPS"
else
  echo "  HTTPS поднялся, но /health не ответил."
  echo "  Проверьте: systemctl status poker  и  curl -s localhost:$APP_PORT/health"
fi

cat <<DONE

Готово. Что осталось сделать в @BotFather:

  /newapp → выберите бота → Web App URL: $URL
            Short name: poker   (то же значение, что в TELEGRAM_APP_SHORT_NAME)

DONE
