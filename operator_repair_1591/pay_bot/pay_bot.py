#!/usr/bin/env python3
"""Отдельный полуавтоматический бот оплаты eSIM (Билайн).

Сценарий (всё в Telegram):
  1. Кидаешь боту одну или несколько ссылок заказа (которые «ждут оплаты»).
  2. Кидаешь карту одним сообщением:  НОМЕР СРОК КОД
     например:  2200000000001036 06/34 123
  3. Для каждой ссылки бот: открывает → жмёт «Оплатить» → вводит карту → жмёт
     «оплатить N ₽» → доходит до страницы банка (3DS) → просит у тебя код из SMS.
     Ты присылаешь код — бот его вводит.
       • неверный код  → бот пишет и просит прислать снова;
       • отказ банка    → бот пишет «оплата не прошла» и переходит к следующей ссылке;
       • успех          → (ПОКА ЗАГЛУШКА) бот шлёт скрин страницы и ссылку; QR добавим позже.

Это ОТДЕЛЬНЫЙ бот, со своим токеном — не трогает основного beeline-бота.
Карта хранится только в памяти процесса (CVV никуда не пишется). /stop — всё сбросить.

Конфиг (pay_bot_config.json рядом со скриптом или путь в PAY_BOT_CONFIG):
  {
    "token": "<токен ЭТОГО бота от @BotFather>",
    "chat_id": "<твой chat_id>",
    "proxy": "socks5h://логин:пароль@хост:порт"   // прокси ДЛЯ TELEGRAM (как у основного бота); "direct" если не нужен
    // необязательно:
    // "browser_proxy": "socks5://логин:пароль@хост:порт"  // прокси ДЛЯ страниц оплаты (по умолчанию без прокси)
    // "headless": true,
    // "code_wait_seconds": 300
  }
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

import requests

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except Exception as exc:  # pragma: no cover
    print("Нужен playwright в этом окружении:", exc, file=sys.stderr)
    raise

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("PAY_BOT_CONFIG") or (BASE_DIR / "pay_bot_config.json"))

# ── слова/признаки страниц (легко подправить) ──────────────────────────────
PAY_BUTTON_WORDS = ("оплатить", "перейти к оплате", "оплата картой", "оплатить картой")
CARD_FORM_HINT = ("номер карты", "новая карта")
CODE_FIELD_HINT = ("код из пуша", "код из смс", "код подтвержд", "введите код", "одноразов",
                   "смс", "sms", "otp", "one-time", "код")
CODE_SUBMIT_WORDS = ("подтвердить", "оплатить", "продолжить", "confirm", "submit", "далее")
WRONG_CODE_WORDS = ("неправильный", "неверн", "проверьте код", "wrong", "incorrect", "ошибка кода")
DECLINE_WORDS = ("отклон", "недостаточно средств", "отказан", "declined", "не удалось", "отмен")
SUCCESS_WORDS = ("оплачен", "оплата прошла", "успешно", "спасибо", "договор", "esim", "qr", "готов")


def log(msg):
    print(f"[PAY] {time.strftime('%H:%M:%S')} {msg}", flush=True)


# ── конфиг ─────────────────────────────────────────────────────────────────
def load_config():
    if not CONFIG_PATH.is_file():
        raise SystemExit(f"нет файла конфига: {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text("utf-8"))
    for key in ("token", "chat_id"):
        if not str(cfg.get(key) or "").strip():
            raise SystemExit(f"в конфиге нет {key}")
    return cfg


# ── Telegram (через прокси, raw API) ───────────────────────────────────────
class Telegram:
    def __init__(self, cfg):
        self.token = str(cfg["token"]).strip()
        self.chat_id = str(cfg["chat_id"]).strip()
        proxy = str(cfg.get("proxy") or "").strip()
        self.session = requests.Session()
        if proxy and proxy.lower() not in ("direct", "none", "off", "no", "-"):
            self.session.proxies = {"https": proxy, "http": proxy}
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.offset = None

    def _call(self, method, **params):
        r = self.session.post(f"{self.base}/{method}", data=params, timeout=60)
        return r.json()

    def send(self, text, reply_markup=None):
        try:
            data = {"chat_id": self.chat_id, "text": str(text)[:4000], "disable_web_page_preview": True}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            self._call("sendMessage", **data)
        except Exception as exc:
            log(f"send error: {type(exc).__name__}: {exc}")

    def send_photo(self, path, caption=""):
        try:
            with open(path, "rb") as f:
                r = self.session.post(f"{self.base}/sendPhoto",
                                      data={"chat_id": self.chat_id, "caption": str(caption)[:1000]},
                                      files={"photo": f}, timeout=120)
            return r.ok
        except Exception as exc:
            log(f"send_photo error: {type(exc).__name__}: {exc}")
            return False

    def get_updates(self, timeout=25):
        """Long-poll; возвращает список текстов от нашего chat_id (по порядку)."""
        params = {"timeout": timeout}
        if self.offset is not None:
            params["offset"] = self.offset
        try:
            data = self.session.get(f"{self.base}/getUpdates", params=params, timeout=timeout + 15).json()
        except Exception as exc:
            log(f"getUpdates error: {type(exc).__name__}: {exc}")
            time.sleep(3)
            return []
        out = []
        for upd in data.get("result", []) or []:
            self.offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = str((msg.get("chat") or {}).get("id") or "")
            text = msg.get("text")
            if text is None:
                continue
            if self.chat_id and chat != self.chat_id:
                continue  # чужой чат — игнор
            out.append(text.strip())
        return out


# ── разбор карты ───────────────────────────────────────────────────────────
def parse_card(text):
    """«2200 0000 0000 1036 06/34 123» или «2200000000001036 06/34 123» → (digits, 'MMYY', 'cvv') или None.

    Разбор по токенам: последнее слово — CVV, предпоследнее — срок, всё до них — номер карты
    (несколько групп номера склеиваются)."""
    tokens = text.strip().split()
    if len(tokens) >= 3:
        cvv = re.sub(r"\D", "", tokens[-1])
        exp = re.sub(r"\D", "", tokens[-2])
        num = "".join(re.sub(r"\D", "", t) for t in tokens[:-2])
        if (13 <= len(num) <= 19 and len(exp) == 4
                and 1 <= int(exp[:2]) <= 12 and 3 <= len(cvv) <= 4):
            return num, exp, cvv
    # запасной разбор: сплошная цепочка цифр, карта считается 16-значной
    digits = re.sub(r"\D", "", text)
    if len(digits) == 16 + 4 + 3 and 1 <= int(digits[16:18]) <= 12:
        return digits[:16], digits[16:20], digits[20:23]
    return None


def mask_card(num):
    return f"**** **** **** {num[-4:]}" if len(num) >= 4 else "****"


def looks_like_card(text):
    return parse_card(text) is not None


def extract_links(text):
    return re.findall(r"https?://\S+", text)


# ── работа со страницами оплаты ────────────────────────────────────────────
def _frames(page):
    try:
        return [page.main_frame] + [f for f in page.frames if f != page.main_frame]
    except Exception:
        return [page.main_frame]


def _visible_inputs(scope):
    out = []
    try:
        for h in scope.locator("input").element_handles():
            try:
                if h.is_visible() and (h.get_attribute("type") or "text").lower() not in ("hidden", "checkbox", "radio", "submit", "button"):
                    out.append(h)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _card_scope(page, deadline):
    """Рамка/страница, где есть форма карты (есть поле «номер карты» / плейсхолдер 0000)."""
    while time.monotonic() < deadline:
        for fr in _frames(page):
            try:
                if fr.locator("input").count() and _visible_inputs(fr):
                    body = ""
                    try:
                        body = (fr.locator("body").inner_text(timeout=800) or "").lower()
                    except Exception:
                        body = ""
                    if any(h in body for h in CARD_FORM_HINT) or fr.locator("input[placeholder*='0000']").count():
                        return fr
            except Exception:
                pass
        page.wait_for_timeout(300)
    return page.main_frame


def _click_by_words(scope, words, timeout_ms=8000):
    """Нажать первый видимый элемент (кнопка/ссылка/любой), чей текст содержит одно из слов."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    rx = re.compile("|".join(re.escape(w) for w in words), re.I)
    while time.monotonic() < deadline:
        for sel in ("button", "[role=button]", "a", "div", "span"):
            try:
                loc = scope.locator(sel).filter(has_text=rx)
                n = min(loc.count(), 8)
                for i in range(n):
                    el = loc.nth(i)
                    try:
                        if el.is_visible() and el.is_enabled():
                            el.scroll_into_view_if_needed(timeout=1500)
                            el.click(timeout=2500)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        scope.wait_for_timeout(300)
    return False


def _type_card(page, card, tg, deadline):
    """Форма «новая карта»: поля появляются по очереди (номер → срок → код)."""
    num, exp, cvv = card
    scope = _card_scope(page, deadline)
    ins = _visible_inputs(scope)
    if not ins:
        raise RuntimeError("форма карты не найдена")
    ins[0].click()
    ins[0].type(num, delay=70)
    # ждём появления поля срока (до общего дедлайна — сайт может тормозить)
    while time.monotonic() < deadline:
        ins = _visible_inputs(scope)
        if len(ins) >= 2:
            break
        page.wait_for_timeout(300)
    if len(ins) < 2:
        raise RuntimeError("поле срока не появилось после номера карты")
    ins[1].click()
    ins[1].type(exp, delay=70)
    # ждём появления поля кода (CVV)
    while time.monotonic() < deadline:
        ins = _visible_inputs(scope)
        if len(ins) >= 3:
            break
        page.wait_for_timeout(300)
    if len(ins) < 3:
        raise RuntimeError("поле кода карты (CVV) не появилось")
    ins[2].click()
    ins[2].type(cvv, delay=70)
    page.wait_for_timeout(500)
    # кнопка «оплатить» может стать активной не сразу — ждём до дедлайна
    left_ms = max(8000, int((deadline - time.monotonic()) * 1000))
    if not _click_by_words(scope, ("оплатить",), timeout_ms=left_ms):
        raise RuntimeError("кнопка «оплатить» не нажалась (возможно, неактивна)")
    return True


def _find_code_field(page):
    """Найти поле ввода 3DS-кода в любой рамке. Возвращает (frame, element) или (None, None)."""
    for fr in _frames(page):
        try:
            body = (fr.locator("body").inner_text(timeout=800) or "").lower()
        except Exception:
            body = ""
        if not any(h in body for h in CODE_FIELD_HINT):
            continue
        for h in _visible_inputs(fr):
            try:
                ph = (h.get_attribute("placeholder") or "").lower()
                name = ((h.get_attribute("name") or "") + (h.get_attribute("id") or "")).lower()
                ml = h.get_attribute("maxlength")
                if (any(w in ph for w in ("код", "смс", "sms", "code", "otp", "пуш"))
                        or any(w in name for w in ("otp", "code", "sms", "pin"))
                        or (ml and ml.isdigit() and int(ml) <= 8)):
                    return fr, h
            except Exception:
                continue
        vis = _visible_inputs(fr)
        if len(vis) == 1:   # на странице один ввод и это явно код
            return fr, vis[0]
    return None, None


def _page_text(page):
    chunks = []
    for fr in _frames(page):
        try:
            chunks.append((fr.locator("body").inner_text(timeout=800) or "").lower())
        except Exception:
            pass
    return "\n".join(chunks)


def _shot(page, name):
    path = str(BASE_DIR / f"shot_{name}_{int(time.time())}.png")
    try:
        page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        try:
            page.screenshot(path=path)
            return path
        except Exception:
            return None


# ── обработка одной ссылки ─────────────────────────────────────────────────
def process_link(pw_browser, link, card, tg, cfg):
    code_wait = int(cfg.get("code_wait_seconds") or 300)
    # Билайн сейчас может грузить форму/поле оплаты по 2-3 минуты — ждём терпеливо.
    page_wait = int(cfg.get("page_wait_seconds") or 240)   # сек на появление кнопки/формы/кода
    ctx_kwargs = {"locale": "ru-RU"}
    bproxy = str(cfg.get("browser_proxy") or "").strip()
    if bproxy and bproxy.lower() not in ("direct", "none", "off", "no", "-"):
        ctx_kwargs["proxy"] = {"server": bproxy}
    context = pw_browser.new_context(**ctx_kwargs)
    page = context.new_page()
    page.set_default_timeout(60000)
    try:
        tg.send(f"🔗 Открываю ссылку…\n{link}")
        page.goto(link, wait_until="domcontentloaded", timeout=max(90000, page_wait * 1000))
        page.wait_for_timeout(2500)

        # 1) страница «ждёт оплаты» — единственная кнопка «Оплатить» (ждём терпеливо, сайт лагает)
        tg.send("⏳ Жду кнопку «Оплатить» (сайт может грузиться до нескольких минут)…")
        if not _click_by_words(page.main_frame, PAY_BUTTON_WORDS, timeout_ms=page_wait * 1000):
            # возможно, форма карты уже открыта сразу
            log("кнопку «оплатить» не нашёл на первой странице — пробую сразу форму карты")
        page.wait_for_timeout(2000)

        # 2) форма карты (поле может грузиться минуты — ждём до page_wait)
        tg.send(f"💳 Ввожу карту {mask_card(card[0])} (жду загрузку формы, это может занять минуты)…")
        deadline = time.monotonic() + page_wait
        _type_card(page, card, tg, deadline)
        page.wait_for_timeout(3000)

        # 3) 3DS — ждём поле кода ИЛИ сразу результат
        tg.send("⏳ Жду страницу банка (код из SMS)…")
        code_ok = False
        for attempt in range(1, 6):
            fr = h = None
            step_deadline = time.monotonic() + page_wait
            while time.monotonic() < step_deadline:   # ждём появления поля кода / результата (до page_wait)
                low = _page_text(page)
                if any(w in low for w in DECLINE_WORDS) and not any(w in low for w in CODE_FIELD_HINT):
                    tg.send("❌ Оплата не прошла (банк отклонил). Перехожу к следующей ссылке.")
                    return "declined"
                fr, h = _find_code_field(page)
                if h is not None:
                    break
                if any(w in low for w in SUCCESS_WORDS) and "qr" in low:
                    break
                page.wait_for_timeout(500)
            if h is None:
                # нет поля кода — возможно уже успех/редирект
                break

            # просим код у пользователя
            tg.send(f"🔢 Пришли код из SMS/пуша (попытка {attempt}). Или напиши «отмена».")
            code = _wait_user_code(tg, code_wait)
            if code is None:
                tg.send("⌛ Код не пришёл вовремя — отменяю эту ссылку.")
                return "timeout"
            if code.lower() in ("отмена", "stop", "/stop", "cancel"):
                tg.send("✖️ Отменил эту ссылку.")
                return "cancelled"

            try:
                h.click()
                h.fill("")
                h.type(re.sub(r"\D", "", code), delay=90)
            except Exception as exc:
                tg.send(f"⚠️ Не смог вписать код: {type(exc).__name__}. Пробую снова.")
                continue
            page.wait_for_timeout(600)
            # у части банков есть кнопка подтверждения, у Т-Банка нет (автоотправка)
            _click_by_words(fr, CODE_SUBMIT_WORDS, timeout_ms=2500)
            # ждём реакции
            for _ in range(40):
                low = _page_text(page)
                if any(w in low for w in WRONG_CODE_WORDS):
                    tg.send("↩️ Банк: код неверный. Пришли код заново.")
                    break
                if any(w in low for w in DECLINE_WORDS):
                    tg.send("❌ Оплата не прошла (банк отклонил).")
                    return "declined"
                # поле кода исчезло → код принят
                fr2, h2 = _find_code_field(page)
                if h2 is None:
                    code_ok = True
                    break
                page.wait_for_timeout(500)
            if code_ok:
                break
        else:
            tg.send("⚠️ Не удалось подтвердить код за 5 попыток.")
            return "code_failed"

        # 4) результат / успех (ЗАГЛУШКА до твоего примера страницы успеха+QR)
        page.wait_for_timeout(4000)
        low = _page_text(page)
        if any(w in low for w in DECLINE_WORDS):
            tg.send("❌ Похоже, оплата не прошла.")
            return "declined"
        shot = _shot(page, "result")
        try:
            cur = page.url
        except Exception:
            cur = link
        if shot:
            tg.send_photo(shot, caption=f"✅ Код принят. Вот страница после оплаты.\nURL: {cur}\n\n"
                                        "⚠️ Автополучение QR пока не настроено — пришли мне скрин+HTML этой "
                                        "страницы и кнопки «Получить QR», добавлю.")
            try:
                os.unlink(shot)
            except OSError:
                pass
        else:
            tg.send(f"✅ Код принят. URL: {cur}\n(QR добавим позже по твоему примеру.)")
        return "paid"
    except PWTimeout as exc:
        tg.send(f"⚠️ Таймаут на странице: {exc}")
        shot = _shot(page, "timeout")
        if shot:
            tg.send_photo(shot, caption="Где застряло (таймаут).")
            try: os.unlink(shot)
            except OSError: pass
        return "error"
    except Exception as exc:
        log("process_link error:\n" + traceback.format_exc())
        tg.send(f"⚠️ Ошибка: {type(exc).__name__}: {exc}")
        shot = _shot(page, "error")
        if shot:
            tg.send_photo(shot, caption="Где застряло (ошибка).")
            try: os.unlink(shot)
            except OSError: pass
        return "error"
    finally:
        try:
            context.close()
        except Exception:
            pass


# глобальная ссылка на Telegram для ожидания кода внутри обработки
_TG = None


def _wait_user_code(tg, timeout_seconds):
    """Ждём следующее текстовое сообщение пользователя (код)."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for text in tg.get_updates(timeout=25):
            if text:
                return text.strip()
    return None


def main():
    cfg = load_config()
    tg = Telegram(cfg)
    headless = cfg.get("headless", True)
    tg.send("💳 Бот оплаты запущен.\n\nКак пользоваться:\n1) пришли ссылку(и) заказа\n"
            "2) пришли карту одним сообщением: НОМЕР СРОК КОД (напр. 2200000000001036 06/34 123)\n"
            "3) когда банк спросит — пришлёшь код из SMS\n\n/stop — сбросить очередь и карту.")
    pending = []          # очередь ссылок
    card = None           # (num, exp, cvv) в памяти
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            while True:
                for text in tg.get_updates(timeout=25):
                    low = text.lower().strip()
                    if low in ("/stop", "стоп", "сброс"):
                        pending.clear(); card = None
                        tg.send("🧹 Очередь и карта сброшены.")
                        continue
                    if low in ("/start", "/help", "старт", "помощь"):
                        tg.send("Пришли ссылку(и), потом карту «НОМЕР СРОК КОД». /stop — сброс.")
                        continue
                    if low in ("/links", "очередь"):
                        tg.send(f"В очереди ссылок: {len(pending)}" + ("\n" + "\n".join(pending) if pending else ""))
                        continue
                    links = extract_links(text)
                    if links:
                        pending.extend(links)
                        tg.send(f"➕ Добавлено ссылок: {len(links)} (в очереди {len(pending)}).\n"
                                "Теперь пришли карту: НОМЕР СРОК КОД.")
                        continue
                    if looks_like_card(text):
                        card = parse_card(text)
                        if not pending:
                            tg.send(f"🗂 Карта принята ({mask_card(card[0])}), но очередь пуста. Пришли ссылку(и).")
                            continue
                        tg.send(f"🚀 Карта {mask_card(card[0])}. Начинаю оплату {len(pending)} ссылок по очереди.")
                        queue = list(pending); pending.clear()
                        done = {"paid": 0, "declined": 0, "error": 0, "other": 0}
                        for idx, link in enumerate(queue, 1):
                            tg.send(f"— [{idx}/{len(queue)}] —")
                            res = process_link(browser, link, card, tg, cfg)
                            done[res if res in done else "other"] = done.get(res if res in done else "other", 0) + 1
                        card = None   # карту из памяти убираем после прогона
                        tg.send(f"🏁 Готово. Оплачено: {done['paid']}, отклонено: {done['declined']}, "
                                f"ошибок: {done['error']}, прочее: {done['other']}.\nКарта очищена из памяти.")
                        continue
                    tg.send("Не понял. Пришли ссылку (http...) или карту «НОМЕР СРОК КОД». /help")
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
