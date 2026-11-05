# Дипсик — чат-бот (счётчик QR + собеседник + модерация)

Отдельный бот для рабочего чата eSIM. Со своим токеном, рядом с основным не конфликтует.

## Что умеет
- **Считает** QR (фото + номер в подписи) и реакции: ❤ — в работе, 🔥 — успех, 👎 — не успешно.
- **Статистика** по запросу: за сегодня / за последний час / за неделю / за всё время, по каждому человеку.
- **Общается** (DeepSeek), характер дерзкий, коротко и по-человечески.
- **Модерация**: любой может попросить «дипсик удали дубли» / «удали это» (reply) — бот **спрашивает подтверждение** (Да/Нет) и удаляет только после «Да». Дубль = тот же номер повторно (оставляет первый).
- **Память**: помнит последние реплики диалога на каждый чат.

## Как вызывается
Только если в сообщении есть слово **«дипсик» / «deepseek» / «дип»**, или **@юзернейм бота**, или это **reply** на его сообщение. Внутри начатой ветки (твои reply на него ~3 минуты) слово можно не повторять. На всё остальное — молчит, QR и реакции считает тихо.

## Установка на сервер (Ubuntu)

1. Создай бота у @BotFather → получи **токен**. Отдельный, не от основного бота.
2. У @BotFather: `/setprivacy` → выбери этого бота → **Disable** (чтобы видел все сообщения). 
3. Добавь бота в групповой чат и сделай **админом** с правом **«Удаление сообщений»** (иначе не сможет удалять и видеть реакции).
4. Положи код и конфиг:
   ```
   sudo mkdir -p /opt/chat_bot
   sudo cp chat_bot.py /opt/chat_bot/
   sudo nano /opt/chat_bot/config.json
   ```
   Содержимое `config.json`:
   ```json
   {
     "token": "ТОКЕН_БОТА",
     "proxy": "socks5h://логин:пароль@хост:порт",
     "deepseek_api_key": "sk-...",
     "deepseek_model": "deepseek-chat",
     "deepseek_url": "https://api.deepseek.com/chat/completions",
     "ds_proxy": "direct",
     "triggers": ["дипсик", "deepseek", "дип"],
     "tz_offset_hours": 3
   }
   ```
   - `proxy` — как и у основного бота (или `direct`, если Telegram доступен напрямую).
   - `ds_proxy` — прокси для DeepSeek (часто `direct`); если не указан, берётся `proxy`.
   - `deepseek_model` — модель под твой ключ (`deepseek-chat` по умолчанию).
5. Python и запуск:
   ```
   sudo apt-get install -y python3 python3-venv
   python3 -m venv /opt/chat_bot/venv
   /opt/chat_bot/venv/bin/pip install "requests[socks]"
   ```
6. Служба systemd:
   ```
   sudo tee /etc/systemd/system/chat_bot.service >/dev/null <<EOF
   [Unit]
   Description=Chat bot (QR counter + DeepSeek)
   After=network-online.target
   Wants=network-online.target
   [Service]
   WorkingDirectory=/opt/chat_bot
   ExecStart=/opt/chat_bot/venv/bin/python /opt/chat_bot/chat_bot.py
   Restart=always
   RestartSec=3
   [Install]
   WantedBy=multi-user.target
   EOF
   sudo systemctl daemon-reload
   sudo systemctl enable --now chat_bot
   ```
7. Журнал: `sudo journalctl -u chat_bot -f -o short-iso`

## Важно / ограничения
- Бот считает QR и реакции **с момента, как его добавили** (старую историю боты не читают).
- QR определяется как **фото с номером в подписи**. Если номер идёт отдельным сообщением — такой QR не посчитается.
- Реакции он видит, только если он **админ** (и в группе не анонимные реакции; если анонимные — берёт агрегированные счётчики).
- Удаление возможно только для сообщений, которые Telegram даёт удалить боту (обычно свежие).

## Настройки (env/config)
- `triggers` — слова вызова.
- `tz_offset_hours` — часовой пояс для «сегодня» (3 = МСК).
- Характер задаётся в коде (переменная `PERSONA`) — правится при желании.
