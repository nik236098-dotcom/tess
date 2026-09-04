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
node -v            # должно показать v22.x
command -v node    # должно показать /usr/bin/node
```

Если `command -v node` показал другой путь (например `/snap/bin/node` или что-то
внутри `~/.nvm`), запомните его — он понадобится в шаге 5, и команды `sudo -u poker node`
придётся писать с полным путём. Проще всего поставить Node именно из NodeSource,
как выше: тогда он окажется в `/usr/bin/node` и всё сойдётся само.

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

Путь к Node подставляется автоматически — юнит собирается тем же `command -v node`:

```bash
NODE_BIN="$(command -v node)"
cat > /etc/systemd/system/poker.service <<UNIT
[Unit]
Description=Покер с друзьями (Telegram Mini App)
After=network.target

[Service]
Type=simple
User=poker
Group=poker
WorkingDirectory=/opt/poker/app
ExecStart=$NODE_BIN server/index.js
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

grep ExecStart /etc/systemd/system/poker.service   # проверьте, что путь не пустой

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

Всё ниже делается одной командой — скрипт сам напишет конфиг, проверит DNS,
откроет порты и выпустит сертификат:

```bash
cd /opt/poker/app
sudo bash scripts/setup-https.sh ВАШ_ДОМЕН ваша@почта
```

Если на сервере уже живёт другой сервис на 443 (VPN, панель управления),
поднимите покер на свободном порту — третьим аргументом:

```bash
sudo bash scripts/setup-https.sh ВАШ_ДОМЕН ваша@почта 8443
```

Тогда Web App URL в BotFather будет `https://ВАШ_ДОМЕН:8443`.

Если хотите сделать руками или разобраться, что происходит, — дальше то же самое по шагам.

### Вручную

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

## 9. Проверить токен и повесить кнопку меню

```bash
cd /opt/poker/app
NODE_BIN="$(command -v node)"
sudo -u poker "$NODE_BIN" scripts/setup-bot.js                           # проверит токен, скажет имя бота
sudo -u poker "$NODE_BIN" scripts/setup-bot.js https://ВАШ_ДОМЕН --save  # кнопка «Играть» + имя бота в .env
```

Ключ `--save` сам впишет `TELEGRAM_BOT_USERNAME` в `.env` — не придётся копировать руками.
После него перезапустите сервис: `systemctl restart poker`.

Первая строка вывода называет бота, которому принадлежит токен — **проверьте её**.
Если там оказался не тот бот, верните ему кнопку меню:

```bash
sudo -u poker "$NODE_BIN" scripts/setup-bot.js --reset-menu
```

Полный путь здесь не для красоты: `sudo` ищет программы по своему короткому списку
каталогов, и `node`, поставленный не в `/usr/bin`, там не найдётся — будет
`sudo: node: command not found`.

Имя бота нужно для кнопки «позвать друзей»: с `--save` оно попадёт в `.env` само,
без ключа — скрипт просто напечатает строку, которую надо вписать.

## 10. Первый запуск

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

`ВАШ_ДОМЕН` в шаге 6 — это настоящее имя, A-запись которого указывает на IP сервера.
На голый IP сертификат не выдают, а без HTTPS Telegram приложение не откроет.
Есть два бесплатных выхода.

### Вариант А: бесплатный поддомен DuckDNS (постоянный, рекомендую)

1. Зайдите на [duckdns.org](https://www.duckdns.org) и войдите (Google, GitHub — что удобнее).
2. Придумайте имя, например `pokergena`, и нажмите **add domain**. Получится `pokergena.duckdns.org`.
3. На странице DuckDNS два поля адреса — **current ip** и **current ipv6**.
   Заполняйте только первое, IPv6 оставьте пустым: если вписать туда лишнее,
   у домена появится AAAA-запись, Let's Encrypt пойдёт проверять именно по ней
   и получит отказ, хотя по IPv4 всё работает.

   Адреса сервера узнаются так:

```bash
curl -s -4 ifconfig.me    # IPv4 — этот адрес и вписывайте
curl -s -6 ifconfig.me    # IPv6 — если пусто или ошибка, поле ipv6 не трогайте
```

4. Либо не заполняйте форму руками, а привяжите домен командой с сервера:

```bash
# подставьте своё имя и токен; IP подставится сам
curl "https://www.duckdns.org/update?domains=pokergena&token=ВАШ_ТОКЕН&ip=$(curl -s -4 ifconfig.me)&ipv6="
# в ответ должно прийти: OK
```

   Пустой `ipv6=` в конце заодно вычищает случайно проставленную AAAA-запись.

5. Проверьте, что имя резолвится в ваш IPv4 и никуда больше:

```bash
getent ahosts pokergena.duckdns.org
```

6. Дальше идите по шагу 6, подставляя `pokergena.duckdns.org` вместо `ВАШ_ДОМЕН`:

```bash
sed -i 's/poker.example.com/pokergena.duckdns.org/' /etc/nginx/sites-available/poker
ln -sf /etc/nginx/sites-available/poker /etc/nginx/sites-enabled/poker
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

apt install -y certbot python3-certbot-nginx
certbot --nginx -d pokergena.duckdns.org --agree-tos -m ваша@почта --redirect
```

Web App URL в BotFather: `https://pokergena.duckdns.org`.

### Вариант Б: туннель Cloudflare (без сервера и домена, но временный)

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
dpkg -i cloudflared.deb
cloudflared tunnel --url http://localhost:3000
```

Адрес вида `https://что-то.trycloudflare.com` вставьте в BotFather как Web App URL.
Он живёт, пока запущен `cloudflared`, и после перезапуска меняется — каждый раз придётся
менять URL в BotFather. Для постоянной игры берите вариант А.

## Если что-то не поднялось

Сначала запустите диагностику — она пройдёт по всей цепочке и скажет, где обрыв:

```bash
cd /opt/poker/app
sudo bash scripts/doctor.sh
```

Она проверяет Node, `.env`, сервис, ответ приложения внутри сервера, DNS, nginx,
кто занял порт, сертификат и доступ снаружи, а в конце печатает список того,
что чинить. Секреты не показывает — от токена только номер бота.

Ручные команды, если нужны подробности:

```bash
systemctl status poker --no-pager     # запущено ли приложение
journalctl -u poker -n 50 --no-pager  # его логи
curl -s localhost:3000/health         # отвечает ли сервер локально
nginx -t                              # синтаксис конфига nginx
tail -n 30 /var/log/nginx/error.log   # ошибки nginx
ss -tlnp | grep -E ':(80|443|3000)'   # кто слушает порты
```

Частые причины:

- **`sudo: node: command not found`** — Node стоит не в `/usr/bin`. Посмотрите путь
  через `command -v node` и подставляйте его целиком:
  `sudo -u poker "$(command -v node)" scripts/setup-bot.js`.
  Если команда ничего не вывела, Node просто не установлен — вернитесь к шагу 2.
- **certbot ругается на домен** — A-запись ещё не разошлась или указывает не на этот сервер.
  Проверьте `dig +short ВАШ_ДОМЕН` и сравните с `curl -s ifconfig.me`.
- **Стол открывается, но игроки не появляются** — в конфиге nginx нет строк
  `proxy_set_header Upgrade $http_upgrade;` и `Connection "upgrade";`. Без них WebSocket не работает.
- **Сайт открывается по http, а Telegram пишет «неподдерживаемый протокол»** —
  сертификата нет, nginx не слушает 443. Проверьте и повторите выпуск:

```bash
ss -tln | grep ':443 '                    # пусто = HTTPS не поднят
ls /etc/letsencrypt/live/                 # пусто = сертификата нет
certbot --nginx -d ВАШ_ДОМЕН --agree-tos -m ваша@почта --redirect
```

  Обратите внимание: `ваша@почта` надо заменить на настоящий адрес, иначе certbot откажет.

  Если certbot предлагает меню «Attempt to reinstall this existing certificate» —
  сертификат уже выпущен, его надо просто прописать в nginx, без обращения к Let's Encrypt:

```bash
certbot install --cert-name ВАШ_ДОМЕН --nginx --redirect
systemctl reload nginx
```
- **HTTPS не отвечает, хотя nginx жив и настроен верно** — порт 443 занят другим
  сервисом. Посмотрите, кем: `ss -tlnp | grep ':443'`. Если это VPN или панель,
  поднимите покер на другом порту: `sudo bash scripts/setup-https.sh ДОМЕН ПОЧТА 8443`.
- **`conflicting server name` и `invalid PID number "" in "/run/nginx.pid"`** —
  на один домен заведено два конфига, а сам nginx не запущен (перезагружать нечего).
  Лечится так:

```bash
grep -rls "server_name.*ВАШ_ДОМЕН" /etc/nginx/sites-enabled/   # кто дублируется
mv /etc/nginx/sites-enabled/ВАШ_ДОМЕН /root/                   # выключаем лишний
nginx -t && systemctl start nginx
certbot install --cert-name ВАШ_ДОМЕН --nginx --redirect
systemctl reload nginx
```

- **Telegram пишет, что приложение недоступно** — в BotFather указан `http://`,
  голый IP или адрес с самоподписанным сертификатом.
- **«Откройте приложение через Telegram» в браузере** — так и задумано: с заданным
  токеном вход возможен только из Telegram.
- **«Подпись initData не совпала»** — в `.env` токен одного бота, а мини-апп создан
  у другого. Сообщение называет номер бота, чей токен сейчас у приложения; сверьте
  его с тем, у которого делали `/newapp`:

```bash
sudo -u poker "$(command -v node)" scripts/setup-bot.js   # скажет, чей это токен
```

  Свежий токен нужного бота берётся в @BotFather: `/mybots` → бот → **API Token**.
  После правки `.env` обязательно `systemctl restart poker`.

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
