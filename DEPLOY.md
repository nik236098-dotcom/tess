# Установка на свой сервер

Инструкция для чистой Ubuntu 22.04/24.04. Всё делается по SSH, копируйте команды по блокам.
Telegram открывает мини-приложения **только по HTTPS с валидным сертификатом**, поэтому нужен домен.
Если домена нет — в конце есть вариант с туннелем Cloudflare.

## 0. Что понадобится

- сервер с root или sudo;
- домен (например `poker.example.com`), A-запись которого указывает на IP сервера;
- токен бота из [@BotFather](https://t.me/BotFather);
- ваш Telegram ID (узнать: напишите [@userinfobot](https://t.me/userinfobot)).

## 1. Подключиться и обновить систему

```bash
ssh root@IP_СЕРВЕРА

apt update && apt upgrade -y
apt install -y curl git nginx ufw
```

## 2. Поставить Node.js 22

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs
node -v      # должно показать v22.x
```

## 3. Отдельный пользователь и код

```bash
adduser --system --group --home /opt/poker poker
mkdir -p /opt/poker /var/lib/poker
chown -R poker:poker /opt/poker /var/lib/poker

sudo -u poker git clone https://github.com/nik236098-dotcom/tess.git /opt/poker/app
cd /opt/poker/app
sudo -u poker git checkout claude/telegram-poker-miniapp-tot7jh
```

Если репозиторий приватный, вместо пароля укажите personal access token с правом `repo`
(GitHub → Settings → Developer settings → Personal access tokens).

Зависимостей у приложения нет — `npm install` не нужен. Проверить, что всё на месте:

```bash
sudo -u poker npm test
```

## 4. Настройки

```bash
sudo -u poker cp /opt/poker/app/.env.example /opt/poker/app/.env
sudo -u poker nano /opt/poker/app/.env
```

Заполните:

```
TELEGRAM_BOT_TOKEN=ваш_токен_из_BotFather
TELEGRAM_BOT_USERNAME=имя_бота_без_собаки
TELEGRAM_APP_SHORT_NAME=poker
TELEGRAM_ADMIN_IDS=ваш_telegram_id
START_BALANCE=10000
PORT=3000
DATA_DIR=/var/lib/poker
```

Файл с токеном не должен читать кто попало:

```bash
chmod 600 /opt/poker/app/.env
chown poker:poker /opt/poker/app/.env
```

## 5. Автозапуск через systemd

```bash
cat > /etc/systemd/system/poker.service <<'UNIT'
[Unit]
Description=Покер с друзьями (Telegram Mini App)
After=network.target

[Service]
Type=simple
User=poker
Group=poker
WorkingDirectory=/opt/poker/app
ExecStart=/usr/bin/node server/index.js
Restart=always
RestartSec=3
Environment=NODE_ENV=production

# Немного изоляции
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/poker

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now poker
systemctl status poker --no-pager
```

Проверка, что сервер отвечает локально:

```bash
curl -s localhost:3000/health
# {"ok":true,"rooms":0,"players":0}
```

## 6. Nginx и HTTPS

```bash
cat > /etc/nginx/sites-available/poker <<'CONF'
server {
    listen 80;
    server_name poker.example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;

        # Обязательно для WebSocket — без этих строк стол не оживёт
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }
}
CONF

# подставьте свой домен вместо poker.example.com
sed -i 's/poker.example.com/ВАШ_ДОМЕН/' /etc/nginx/sites-available/poker

ln -sf /etc/nginx/sites-available/poker /etc/nginx/sites-enabled/poker
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

Сертификат Let's Encrypt:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d ВАШ_ДОМЕН --agree-tos -m ваша@почта --redirect
```

Certbot сам продлевает сертификат, проверить можно так: `certbot renew --dry-run`.

## 7. Файрвол

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status
```

Порт 3000 наружу открывать не нужно — в него ходит только nginx.

## 8. Бот и мини-приложение в BotFather

1. `/newbot` — если бота ещё нет. Токен положите в `.env`.
2. `/newapp` → выберите бота:
   - **Title**: Покер с друзьями
   - **Description**: Холдем на игровые фишки
   - **Photo**: картинка 640×360
   - **Web App URL**: `https://ВАШ_ДОМЕН`
   - **Short name**: `poker` (то же значение, что в `TELEGRAM_APP_SHORT_NAME`)
3. Ссылка на приложение получится вида `https://t.me/ИМЯ_БОТА/poker`.

Полезно ещё `/setmenubutton` — тогда приложение откроется кнопкой в чате бота.

## 9. Первый запуск

Откройте `https://t.me/ИМЯ_БОТА/poker`. В лобби будет написан ваш Telegram ID —
убедитесь, что он совпадает с `TELEGRAM_ADMIN_IDS`, тогда появится карточка «Админ: фишки».

## Обслуживание

```bash
journalctl -u poker -f              # логи
systemctl restart poker             # перезапуск
```

Обновить до свежей версии:

```bash
cd /opt/poker/app
sudo -u poker git pull
sudo -u poker npm test
systemctl restart poker
```

Балансы лежат в `/var/lib/poker/accounts.json`. Бэкап:

```bash
cp /var/lib/poker/accounts.json /root/accounts-$(date +%F).json
```

## Если домена нет

Для разовых посиделок хватит туннеля Cloudflare — он выдаёт временный HTTPS-адрес:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
dpkg -i cloudflared.deb
cloudflared tunnel --url http://localhost:3000
```

Полученный адрес вида `https://что-то.trycloudflare.com` вставьте в BotFather как Web App URL.
Адрес живёт, пока запущен `cloudflared`, и после перезапуска меняется — для постоянной игры лучше домен.

## Вариант с Docker

```bash
cd /opt/poker/app
docker build -t poker-friends .
docker run -d --name poker --restart unless-stopped \
  -p 127.0.0.1:3000:3000 \
  -v /var/lib/poker:/data \
  --env-file .env -e DATA_DIR=/data \
  poker-friends
```

Nginx и сертификат настраиваются так же, как в шагах 6–7.
