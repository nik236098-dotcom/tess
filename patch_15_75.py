from pathlib import Path

base = Path(__file__).resolve().parent
p = base / "test_beeline.py"
t = p.read_text(encoding="utf-8")

if "Версия 15.75 EXP-3: Telegram control menu + isolated AI routing" not in t:
    start = t.index("def telegram_api(cfg, method, payload):")
    end = t.index("\ndef telegram_logger_process", start)
    new_api = """TELEGRAM_DEFAULT_PROXY = ""


def telegram_http_proxies(cfg):
    proxy = str(
        (cfg or {}).get("proxy")
        or os.environ.get("TELEGRAM_PROXY")
        or TELEGRAM_DEFAULT_PROXY
        or ""
    ).strip()
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = "socks5h://" + proxy
    elif proxy.lower().startswith("socks5://"):
        proxy = "socks5h://" + proxy[len("socks5://"):]
    return {"http": proxy, "https": proxy}


def telegram_api(cfg, method, payload):
    token = str(cfg.get("token", "")).strip()
    if not token:
        return None, "В telegram_config.json отсутствует token"

    proxies = telegram_http_proxies(cfg)

    try:
        import requests
    except ImportError:
        return None, (
            "Не установлен requests. Выполни: "
            "python -m pip install \\"requests[socks]\\""
        )

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            data=payload,
            proxies=proxies,
            timeout=15,
        )
        try:
            obj = r.json()
        except Exception:
            return None, f"HTTP {r.status_code}: {r.text[:300]}"
        if r.ok and obj.get("ok"):
            return obj, None
        return None, (
            f"Telegram API: {obj.get('error_code', r.status_code)} "
            f"{obj.get('description', r.text[:200])}"
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

"""
    t = t[:start] + new_api + t[end+1:]

    old_main = """def main():
    print("Версия 15.74 EXP-3: DeepSeek no task deadline + resume/loop detection")
    base_dir = Path(__file__).resolve().parent
"""
    new_main = """def main():
    print("Версия 15.75 EXP-3: Telegram control menu + isolated AI routing")
    base_dir = Path(__file__).resolve().parent
    external_tg_controller = (
        str(os.environ.get("TG_EXTERNAL_CONTROLLER", "")).strip() == "1"
    )
"""
    if old_main not in t:
        raise RuntimeError("15.75 patch: main anchor not found")
    t = t.replace(old_main, new_main, 1)

    old_spawn = """        ai_receiver_proc = mp.get_context("spawn").Process(
            target=ai_telegram_receiver_process,
            args=(ai_stop, ai_receiver_health),
            name="deepseek-telegram-receiver",
        )
        ai_receiver_proc.start()
        print(
            f"[AI RX] Receiver process PID={ai_receiver_proc.pid}",
            flush=True,
        )
"""
    new_spawn = """        ai_receiver_proc = None
        if external_tg_controller:
            print(
                "[AI RX] getUpdates отключён: Telegram принимает внешний controller.",
                flush=True,
            )
        else:
            ai_receiver_proc = mp.get_context("spawn").Process(
                target=ai_telegram_receiver_process,
                args=(ai_stop, ai_receiver_health),
                name="deepseek-telegram-receiver",
            )
            ai_receiver_proc.start()
            print(
                f"[AI RX] Receiver process PID={ai_receiver_proc.pid}",
                flush=True,
            )
"""
    if old_spawn not in t:
        raise RuntimeError("15.75 patch: AI receiver spawn block not found")
    t = t.replace(old_spawn, new_spawn, 1)

    old_ensure = """        def ensure_ai_receiver_alive():
            nonlocal ai_receiver_proc
            now = monotonic()
            last = float(ai_receiver_health.get("time", now))
            dead = not ai_receiver_proc.is_alive()
"""
    new_ensure = """        def ensure_ai_receiver_alive():
            nonlocal ai_receiver_proc
            if external_tg_controller:
                return
            now = monotonic()
            last = float(ai_receiver_health.get("time", now))
            dead = ai_receiver_proc is None or not ai_receiver_proc.is_alive()
"""
    if old_ensure not in t:
        raise RuntimeError("15.75 patch: receiver watchdog block not found")
    t = t.replace(old_ensure, new_ensure, 1)

    old_shutdown = """        try:
            ai_receiver_proc.join(timeout=8)
            if ai_receiver_proc.is_alive():
                ai_receiver_proc.terminate()
        except Exception:
            pass
"""
    new_shutdown = """        try:
            if ai_receiver_proc is not None:
                ai_receiver_proc.join(timeout=8)
                if ai_receiver_proc.is_alive():
                    ai_receiver_proc.terminate()
        except Exception:
            pass
"""
    if old_shutdown not in t:
        raise RuntimeError("15.75 patch: receiver shutdown block not found")
    t = t.replace(old_shutdown, new_shutdown, 1)

    p.write_text(t, encoding="utf-8")

rules = base / "PROJECT_RULES.md"
if rules.exists():
    r = rules.read_text(encoding="utf-8")
    marker = "## 15.75 Telegram control plane"
    if marker not in r:
        r += """
## 15.75 Telegram control plane
- server_controller.py is the sole Telegram getUpdates consumer on Ubuntu.
- Control buttons and slash commands never enter the DeepSeek inbox.
- Ordinary text only is routed to DeepSeek durable inbox.
- Child test_beeline.py is launched with TG_EXTERNAL_CONTROLLER=1.
"""
        rules.write_text(r, encoding="utf-8")

compile(p.read_text(encoding="utf-8"), str(p), "exec")
print("15.75 patch applied")
