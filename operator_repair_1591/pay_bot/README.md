# Бот оплаты eSIM (полуавтомат) — ОТДЕЛЬНЫЙ бот

Отдельный Telegram-бот: кидаешь ему ссылки заказа и карту — он сам открывает,
жмёт «Оплатить», вводит карту и доходит до страницы банка, а код из SMS вводишь ты.
Основного beeline-бота не трогает.

**Важно:** у этого бота должен быть **свой** токен (отдельный бот от @BotFather).
Нельзя использовать токен основного бота — будет конфликт (ошибка 409).

Сейчас готово: ссылка → «Оплатить» → форма карты → оплата → 3DS (код, повтор при неверном,
отчёт при отказе). Страница успеха и автополучение QR — добавим после первого реального
примера (пока бот после успешного кода присылает скрин страницы и ссылку).

---

## Установка (на том же сервере, где beeline)

1. Скачать бота (ветка та же):

```
sudo mkdir -p /opt/pay_bot && sudo curl -fsSL https://raw.githubusercontent.com/nik236098-dotcom/tess/codex/operator-observer-15.87/operator_repair_1591/pay_bot/pay_bot.py -o /opt/pay_bot/pay_bot.py
```

2. Создать конфиг (подставь свой токен ВТОРОГО бота, chat_id и прокси для Telegram):

```
sudo tee /opt/pay_bot/pay_bot_config.json >/dev/null <<'JSON'
{
  "token": "ТОКЕН_ВТОРОГО_БОТА",
  "chat_id": "ТВОЙ_CHAT_ID",
  "proxy": "socks5h://логин:пароль@хост:порт",
  "headless": true,
  "code_wait_seconds": 300,
  "page_wait_seconds": 240
}
JSON
sudo chmod 600 /opt/pay_bot/pay_bot_config.json
```

(`proxy` — тот же, что у Telegram в основном боте; если Telegram открывается напрямую — поставь `"direct"`.
Если страницы оплаты надо открывать через прокси — добавь строку `"browser_proxy": "socks5://..."`.)

3. Запустить как службу (использует venv основного бота — там уже есть playwright и requests):

```
sudo tee /etc/systemd/system/pay_bot.service >/dev/null <<'UNIT'
[Unit]
Description=Beeline eSIM pay bot (semi-auto)
After=network-online.target

[Service]
Type=simple
Environment=PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
ExecStart=/opt/beeline/venv/bin/python /opt/pay_bot/pay_bot.py
WorkingDirectory=/opt/pay_bot
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now pay_bot
```

Если Chromium лежит в другом месте (не `/opt/pw-browsers`), убери строку `Environment=PLAYWRIGHT_BROWSERS_PATH=...`
— playwright найдёт свой стандартный путь. Проверить службу:

```
sudo systemctl status pay_bot --no-pager
sudo journalctl -u pay_bot -f -o cat
```

---

## Как пользоваться

1. Напиши второму боту `/start`.
2. Пришли одну или несколько **ссылок** заказа (которые ждут оплаты) — каждую строкой или в одном сообщении.
3. Пришли **карту** одним сообщением:  `НОМЕР СРОК КОД`
   например: `2200000000001036 06/34 123` (номер можно и группами: `2200 0000 0000 1036 06/34 123`).
4. Бот начнёт оплачивать ссылки по очереди. Когда дойдёт до банка — попросит код; пришли код из SMS/пуша.
   - «код неверный» → пришли код заново;
   - отказ банка → бот пишет «оплата не прошла» и берёт следующую ссылку;
   - успех → бот присылает скрин страницы после оплаты (QR добавим позже).
5. `/stop` — сбросить очередь и карту. Карта и так стирается из памяти после прогона.

Карта хранится только в памяти процесса, в файлы не пишется.

## Что ещё прислать, чтобы доделать QR

После первой реальной оплаты — скрин и HTML страницы успеха, кнопки «Получить QR» и самого QR.
Тогда допишу автополучение QR-кода.
