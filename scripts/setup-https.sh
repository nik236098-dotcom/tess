#!/usr/bin/env bash
# Настраивает nginx и HTTPS для покерного стола одной командой.
#
#   sudo bash scripts/setup-https.sh pokergena.duckdns.org ваша@почта
#
# Что делает: пишет конфиг nginx с проксированием на localhost:3000
# (включая заголовки для WebSocket), включает его и выпускает сертификат
# Let's Encrypt. Повторный запуск безопасен.

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
APP_PORT="${APP_PORT:-3000}"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  cat <<'USAGE'
Использование:
  sudo bash scripts/setup-https.sh ДОМЕН ПОЧТА

Домен — настоящее имя, A-запись которого указывает на этот сервер.
Бесплатное имя можно за пару минут получить на duckdns.org, например:

  sudo bash scripts/setup-https.sh pokergena.duckdns.org me@example.com
USAGE
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "Запустите через sudo: sudo bash scripts/setup-https.sh $DOMAIN $EMAIL"
  exit 1
fi

echo "→ Проверяю, куда указывает $DOMAIN"
SERVER_IP="$(curl -fsS --max-time 10 ifconfig.me || true)"
DOMAIN_IP="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -n1 || true)"

if [[ -z "$DOMAIN_IP" ]]; then
  echo "  Имя $DOMAIN пока не резолвится. Создайте A-запись на $SERVER_IP и подождите пару минут."
  exit 1
fi
if [[ -n "$SERVER_IP" && "$DOMAIN_IP" != "$SERVER_IP" ]]; then
  echo "  $DOMAIN указывает на $DOMAIN_IP, а сервер имеет адрес $SERVER_IP."
  echo "  Сертификат так не выпустится — поправьте A-запись и повторите."
  exit 1
fi
echo "  Порядок: $DOMAIN → $DOMAIN_IP"

echo "→ Ставлю nginx и certbot, если их нет"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl >/dev/null

echo "→ Пишу конфиг nginx"
cat > /etc/nginx/sites-available/poker <<CONF
server {
    listen 80;
    server_name $DOMAIN;

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

ln -sf /etc/nginx/sites-available/poker /etc/nginx/sites-enabled/poker
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "→ Открываю порты в файрволе"
if command -v ufw >/dev/null; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 'Nginx Full' >/dev/null 2>&1 || true
fi

echo "→ Выпускаю сертификат"
certbot --nginx -d "$DOMAIN" --agree-tos -m "$EMAIL" --redirect --non-interactive

echo "→ Проверяю, отвечает ли приложение"
if curl -fsS --max-time 10 "https://$DOMAIN/health" >/dev/null; then
  echo "  Приложение отвечает по HTTPS"
else
  echo "  HTTPS поднялся, но /health не ответил — проверьте: systemctl status poker"
fi

cat <<DONE

Готово. Что осталось сделать в @BotFather:

  /newapp → выберите бота → Web App URL: https://$DOMAIN
            Short name: poker   (то же значение, что в TELEGRAM_APP_SHORT_NAME)

Ссылка для друзей будет такой: https://t.me/ИМЯ_БОТА/poker
DONE
