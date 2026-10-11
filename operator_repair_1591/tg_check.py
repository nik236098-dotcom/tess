#!/usr/bin/env python3
"""Does the server reach Telegram? Read-only check: it calls getMe through the configured proxy and directly,
three times each, and says which way works. The token and the proxy login/password are never printed.

    sudo /opt/beeline/venv/bin/python /tmp/tg_check.py
"""
import json
import os
import re
import sys
import time
from pathlib import Path

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
        if secret:
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
