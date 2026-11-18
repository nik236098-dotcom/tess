#!/usr/bin/env python3
"""Does the server reach Telegram? Read-only check: it calls getMe through the configured proxy and directly,
three times each, and says which way works. The token and the proxy login/password are never printed.

    sudo /opt/beeline/venv/bin/python /tmp/tg_check.py
"""
import json
import os
import re
import socket
import struct
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    import requests
except ImportError:
    print("Нет модуля requests: запускай через /opt/beeline/venv/bin/python")
    sys.exit(2)

APP = Path(os.environ.get("APP_DIR") or "/opt/beeline")
DIRECT = {"direct", "none", "off", "no", "-"}
TRIES = 3


def hide(text, secrets):
    out = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:  # a one-letter password would blank out the whole message
            out = out.replace(secret, "***")
    return re.sub(r"(://)[^/@\s]+@", r"\1***@", out)


def proxy_of(cfg):
    raw = str(cfg.get("proxy") or os.environ.get("TELEGRAM_PROXY") or "").strip()
    if not raw or raw.lower() in DIRECT:
        return None, ""
    if "://" not in raw:
        raw = "socks5h://" + raw
    elif raw.lower().startswith("socks5://"):
        raw = "socks5h://" + raw[len("socks5://"):]
    return {"http": raw, "https": raw}, raw


def where(raw):
    """scheme and host:port of the proxy, without the login and password."""
    m = re.match(r"^(\w+)://(?:[^@/]*@)?([^/]+)", raw or "")
    return f"{m.group(1)}://{m.group(2)}" if m else "—"


SOCKS_REPLIES = {1: "общая ошибка прокси", 2: "запрещено правилами прокси", 3: "сеть недоступна для прокси",
                 4: "прокси не достучался до хоста", 5: "прокси отказал в соединении", 6: "тайм-аут у прокси",
                 7: "команда не поддерживается", 8: "адрес не поддерживается"}


def _read(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            break
        data += chunk
    return data


def probe_proxy(raw, host="api.telegram.org", port=443):
    """Walks the SOCKS5 handshake step by step and says where it breaks. Returns the printed lines."""
    parts = urlsplit(raw)
    user, password = parts.username or "", parts.password or ""
    lines, sock = [], None
    try:
        started = time.time()
        try:
            sock = socket.create_connection((parts.hostname, parts.port), timeout=10)
        except socket.timeout:
            return ["  1. Соединение с прокси: ❌ нет ответа за 10 с. Исходящий порт закрыт (файрвол сервера или группа безопасности хостинга) "
                    "или прокси не пускает этот IP молча."]
        except ConnectionRefusedError:
            return ["  1. Соединение с прокси: ❌ отказано сразу. Порт закрыт на стороне прокси или он не пускает этот IP."]
        except OSError as exc:
            return [f"  1. Соединение с прокси: ❌ {type(exc).__name__}: {str(exc)[:100]}"]
        lines.append(f"  1. Соединение с прокси: ✅ {int((time.time() - started) * 1000)} мс")
        sock.settimeout(10)
        sock.sendall(b"\x05\x02\x00\x02" if user else b"\x05\x01\x00")
        answer = _read(sock, 2)
        if len(answer) < 2:
            lines.append("  2. Приветствие SOCKS5: ❌ прокси закрыл соединение сразу. Так делают, когда IP сервера не в списке разрешённых.")
            return lines
        if answer[1] == 0xFF:
            lines.append("  2. Приветствие SOCKS5: ❌ " + ("прокси требует логин и пароль, а в настройках их нет." if not user
                                                      else "прокси не принял способ входа."))
            return lines
        lines.append(f"  2. Приветствие SOCKS5: ✅ прокси просит {'логин и пароль' if answer[1] == 2 else 'вход без пароля'}")
        if answer[1] == 2:
            if not user:
                lines.append("  3. Вход: ❌ прокси просит логин и пароль, а в настройках их нет.")
                return lines
            u, p = user.encode(), password.encode()
            sock.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
            answer = _read(sock, 2)
            if len(answer) < 2 or answer[1] != 0:
                lines.append("  3. Вход по логину и паролю: ❌ отклонён (логин/пароль не подошли, закончилась оплата или лимит соединений).")
                return lines
            lines.append("  3. Вход по логину и паролю: ✅")
        name = host.encode()
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + struct.pack(">H", port))
        answer = _read(sock, 4)
        if len(answer) < 4:
            lines.append(f"  4. Соединение с {host}: ❌ прокси закрыл связь.")
        elif answer[1] == 0:
            lines.append(f"  4. Соединение с {host}: ✅ прокси дошёл до Telegram")
        else:
            lines.append(f"  4. Соединение с {host}: ❌ {SOCKS_REPLIES.get(answer[1], 'код ' + str(answer[1]))}")
    except socket.timeout:
        lines.append("  ❌ прокси не ответил за 10 с на очередном шаге.")
    except OSError as exc:
        lines.append(f"  ❌ {type(exc).__name__}: {str(exc)[:100]}")
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    return lines


def own_ip():
    try:
        return requests.get("https://api.ipify.org", timeout=8, proxies={"http": None, "https": None}).text.strip()[:45]
    except Exception:
        return "не удалось определить"


def attempt(token, proxies, secrets):
    started = time.time()
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", proxies=proxies, timeout=15)
        ms = int((time.time() - started) * 1000)
        if r.ok and r.json().get("ok"):
            return True, f"ответил за {ms} мс"
        return False, f"HTTP {r.status_code}: {hide(r.text[:120], secrets)}"
    except Exception as exc:
        ms = int((time.time() - started) * 1000)
        return False, f"{type(exc).__name__} через {ms} мс: {hide(str(exc)[:160], secrets)}"


def main():
    try:
        cfg = json.loads((APP / "telegram_config.json").read_text("utf-8"))
    except Exception as exc:
        print(f"Не прочитан {APP}/telegram_config.json: {type(exc).__name__}")
        return 1
    token = str(cfg.get("token") or "").strip()
    if not token:
        print("В telegram_config.json нет token")
        return 1
    proxies, raw = proxy_of(cfg)
    secrets = [token] + [p for p in re.findall(r"://([^@/\s]+)@", raw) if p]
    secrets += [x for p in secrets[1:] for x in p.split(":")]
    print("Прокси Telegram в настройках:", where(raw) if raw else "нет (прямое соединение)")
    print("Внешний IP этого сервера:", own_ip(), "(если прокси работает по списку разрешённых IP, добавьте этот адрес)")
    if raw:
        print("Логин и пароль в настройках прокси:", "есть" if urlsplit(raw).username else "НЕТ")
        print("Шаги подключения к прокси:")
        for line in probe_proxy(raw):
            print(line)
        print()
    results, missing = {}, False
    for name, px in (("через прокси", proxies), ("напрямую", None)):
        if name == "через прокси" and proxies is None:
            continue
        oks = 0
        for i in range(1, TRIES + 1):
            ok, note = attempt(token, px, secrets)
            oks += ok
            missing = missing or "Missing dependencies for SOCKS" in note
            print(f"  {name}, попытка {i}: {'✅' if ok else '❌'} {note}")
        results[name] = oks
    print()
    if missing:
        print("Для проверки нужен питон бота: sudo /opt/beeline/venv/bin/python /tmp/tg_check.py")
        return 2
    if proxies is not None and results.get("через прокси", 0) == TRIES:
        print("Итог: прокси работает. Если бот молчит, дело не в нём.")
    elif results.get("напрямую", 0) == TRIES:
        print("Итог: напрямую Telegram отвечает, а прокси нет. Включите прямое соединение:")
        print("  sudo sed -i 's#\"proxy\": *\"[^\"]*\"#\"proxy\": \"direct\"#' /opt/beeline/telegram_config.json && sudo systemctl restart beeline")
    elif proxies is not None and results.get("через прокси", 0) > 0:
        print("Итог: прокси работает с перебоями (часть попыток упала). Бот будет то отвечать, то молчать: нужен другой прокси.")
    elif results.get("напрямую", 0) > 0:
        print("Итог: напрямую отвечает с перебоями, прокси не работает.")
    else:
        print("Итог: Telegram недоступен ни через прокси, ни напрямую. Нужен рабочий прокси (socks5h://логин:пароль@хост:порт).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
