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

# Самая обидная осечка: в команду скопировали «ваша@почта» из инструкции.
if ! [[ "$EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  echo "«$EMAIL» не похоже на адрес почты."
  echo "Подставьте свой настоящий — на него Let's Encrypt пришлёт напоминание об истечении сертификата:"
  echo "  sudo bash scripts/setup-https.sh $DOMAIN me@example.com"
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "Запустите через sudo: sudo bash scripts/setup-https.sh $DOMAIN $EMAIL"
  exit 1
fi

echo "→ Проверяю, куда указывает $DOMAIN"
SERVER_IPV4="$(curl -fsS -4 --max-time 10 ifconfig.me 2>/dev/null || true)"
SERVER_IPV6="$(curl -fsS -6 --max-time 10 ifconfig.me 2>/dev/null || true)"
DOMAIN_IPS="$(getent ahosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)"

if [[ -z "$DOMAIN_IPS" ]]; then
  echo "  Имя $DOMAIN пока не резолвится."
  echo "  Заведите A-запись на $SERVER_IPV4 и подождите пару минут."
  exit 1
fi

echo "  $DOMAIN резолвится в: $(echo "$DOMAIN_IPS" | tr '\n' ' ')"
[[ -n "$SERVER_IPV4" ]] && echo "  IPv4 сервера: $SERVER_IPV4"
[[ -n "$SERVER_IPV6" ]] && echo "  IPv6 сервера: $SERVER_IPV6"

MATCHED=0
for ip in $DOMAIN_IPS; do
  [[ "$ip" == "$SERVER_IPV4" || ( -n "$SERVER_IPV6" && "$ip" == "$SERVER_IPV6" ) ]] && MATCHED=1
done
if [[ "$MATCHED" -eq 0 ]]; then
  echo "  Домен указывает не на этот сервер — сертификат не выпустится."
  echo "  Поправьте запись и повторите."
  exit 1
fi

# Самая частая беда с бесплатными DNS: заполнили поле IPv6 наугад.
# Let's Encrypt предпочитает AAAA, и проверка уходит в никуда.
STRAY_IPV6="$(echo "$DOMAIN_IPS" | grep ':' || true)"
if [[ -n "$STRAY_IPV6" && "$STRAY_IPV6" != "$SERVER_IPV6" ]]; then
  echo
  echo "  ВНИМАНИЕ: у домена есть AAAA-запись $STRAY_IPV6, а сервер по этому адресу недоступен."
  echo "  Let's Encrypt пойдёт именно по IPv6 и получит отказ."
  echo "  На duckdns.org очистите поле ipv6 (или: curl \"https://www.duckdns.org/update?domains=ИМЯ&token=ТОКЕН&ipv6=\")"
  exit 1
fi

echo "→ Ставлю nginx и certbot, если их нет"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl >/dev/null

# Два блока с одним server_name — это «conflicting server name» и мусор в конфиге.
# Чужие конфиги молча не трогаем: на сервере может жить другой сайт.
CONFLICTS="$(grep -rls "server_name[[:space:]].*$DOMAIN" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v '/poker$' || true)"
if [[ -n "$CONFLICTS" ]]; then
  echo "→ Для $DOMAIN уже есть другой конфиг nginx:"
  echo "$CONFLICTS" | sed 's/^/     /'
  echo
  echo "  Два блока на один домен nginx не примет. Выключите лишний и повторите:"
  echo "$CONFLICTS" | sed 's|^|     mv |; s|$| /root/|'
  exit 1
fi

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
systemctl reload nginx 2>/dev/null || systemctl restart nginx
systemctl is-active --quiet nginx || {
  echo "  Nginx не поднялся. Смотрите: journalctl -u nginx -n 20 --no-pager"
  exit 1
}

echo "→ Открываю порты в файрволе"
if command -v ufw >/dev/null; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 'Nginx Full' >/dev/null 2>&1 || true
fi

if [[ -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
  # Сертификат уже выпускали: заново просить не надо (и лимиты Let's Encrypt целее),
  # достаточно прописать его в конфиг nginx. Без --non-interactive certbot
  # показал бы меню и завис бы в ожидании ответа.
  echo "→ Сертификат уже есть, прописываю его в nginx"
  certbot install --cert-name "$DOMAIN" --nginx --redirect --non-interactive
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
  certbot install --cert-name "$DOMAIN" --nginx --redirect --non-interactive
fi
systemctl is-active --quiet nginx || systemctl start nginx

# Certbot умеет завершиться с нулём, не выпустив сертификат, — проверяем результат.
if [[ ! -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
  echo "  Сертификат не появился в /etc/letsencrypt/live/$DOMAIN — HTTPS не заработает."
  exit 1
fi
if ! ss -tln 2>/dev/null | grep -q ':443 '; then
  echo "  Nginx не слушает 443. Посмотрите: nginx -T | grep -n 'listen 443'"
  exit 1
fi
echo "  Сертификат на месте, 443 слушается"

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
