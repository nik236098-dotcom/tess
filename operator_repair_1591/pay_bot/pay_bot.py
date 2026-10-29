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

  Мгновенная «оплата не прошла» (ошибка на стороне Билайна, ДО ввода кода) — бот сам
  жмёт «попробовать ещё раз» и вводит карту заново (до beeline_retry_max раз).

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
    // "code_wait_seconds": 300,
    // "beeline_retry_max": 3   // сколько раз подряд жать «попробовать ещё раз» на мгновенную ошибку Билайна
  }
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.parse
from pathlib import Path

import requests

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except Exception as exc:  # pragma: no cover
    print("Нужен playwright в этом окружении:", exc, file=sys.stderr)
    raise

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("PAY_BOT_CONFIG") or (BASE_DIR / "pay_bot_config.json"))
PAID_PATH = BASE_DIR / "paid_links.json"  # успешные ссылки до выгрузки

# ── слова/признаки страниц (легко подправить) ──────────────────────────────
PAY_BUTTON_WORDS = ("оплатить", "перейти к оплате", "оплата картой", "оплатить картой")
CARD_FORM_HINT = ("номер карты", "новая карта")
CODE_FIELD_HINT = ("код из пуша", "код из смс", "код подтвержд", "введите код", "одноразов",
                   "смс", "sms", "otp", "one-time", "код")
CODE_SUBMIT_WORDS = ("подтвердить", "оплатить", "продолжить", "confirm", "submit", "далее")
WRONG_CODE_WORDS = ("неправильный", "неверн", "проверьте код", "wrong", "incorrect", "ошибка кода")
DECLINE_WORDS = ("отклон", "недостаточно средств", "отказан", "declined")  # без «отмена» — это кнопка, а не отказ
SUCCESS_WORDS = ("оплачен", "оплата прошла", "успешно", "спасибо", "договор", "esim", "qr", "готов")
# PAY_3DS_1591R103: страница «оплата не прошла» со своей кнопкой «попробовать ещё раз» (ошибка Билайна).
PAYMENT_FAILED_WORDS = ("оплата не прошла", "платёж не прошёл", "платеж не прошел",
                        "не удалось оплатить", "не удалось выполнить оплату", "ошибка оплаты",
                        "платёж отклонён", "платеж отклонен", "payment failed")
RETRY_WORDS = ("попробовать ещё раз", "попробовать еще раз", "попробуйте снова", "попробовать снова",
               "повторить попытку", "повторить оплату", "повторить", "try again", "retry")
# PAY_RESEND_1591R103: ссылки/кнопки «отправить код повторно» на 3DS-странице (запросить новую СМС).
RESEND_WORDS = ("отправить код повторно", "выслать код повторно", "запросить код повторно",
                "запросить новый код", "запросить код", "отправить код ещё раз", "отправить код еще раз",
                "отправить повторно", "выслать повторно", "повторная отправка", "повторить отправку",
                "получить новый код", "получить код заново", "отправить смс повторно", "выслать смс",
                "новый код", "resend code", "resend", "send again", "request new code")
# PAY_YOOMONEY_1591R103: YooMoney сначала может просить подтверждение PUSH в приложении банка;
# на странице есть переключение на ввод кода из СМС — эти слова его ищут.
GET_SMS_WORDS = ("код из смс", "код по смс", "ввести код из смс", "получить код по смс", "получить код в смс",
                 "код в смс", "через смс", "по смс", "не приходит пуш", "не приходит push", "ввести код вручную",
                 "получить смс", "отправить смс", "получить код")


# Те же премиум-эмодзи, что в меню beeline: в тексте — сущность custom_emoji,
# на кнопке «Выгрузка» — icon_custom_emoji_id (обычный знак в подписи не оставляем).
EMOJI_IDS = {
    "💳": "5927169041595634481",
    "📤": "5877540355187937244",
    "✅": "5206607081334906820",
    "❌": "5210952531676504517",
    "✖️": "5210952531676504517",
    "⚠️": "5447644880824181073",
    "🔗": "5877465816030515018",
    "🔁": "5877410604225924969",
    "⏳": "5440621591387980068",
    "⌛": "5440621591387980068",
    "➕": "5877219383691972108",
    "🗂": "5875462364110787088",
    "🔢": "5226513232549664618",
    "🧹": "5879896690210639947",
}
_EMOJI_RE = re.compile("|".join(re.escape(k) for k in sorted(EMOJI_IDS, key=len, reverse=True)))
EXPORT_ICON = EMOJI_IDS["📤"]


def emoji_entities(text):
    ents = []
    for m in _EMOJI_RE.finditer(text or ""):
        ents.append({
            "type": "custom_emoji",
            "offset": len(text[:m.start()].encode("utf-16-le")) // 2,
            "length": len(m.group().encode("utf-16-le")) // 2,
            "custom_emoji_id": EMOJI_IDS[m.group()],
        })
    return ents


def load_paid():
    try:
        data = json.loads(PAID_PATH.read_text("utf-8"))
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def save_paid(links):
    PAID_PATH.write_text(json.dumps(list(links), ensure_ascii=False, indent=2) + "\n", "utf-8")
    try:
        os.chmod(PAID_PATH, 0o600)
    except OSError:
        pass


def remember_paid(url):
    links = load_paid()
    links.append(str(url).strip())
    save_paid(links)
    return len(links)


def menu_kb(n=None):
    """Кнопка выгрузки с кастомным эмодзи. Счётчик — в подписи, без обычного значка."""
    if n is None:
        n = len(load_paid())
    return {"inline_keyboard": [[{
        "text": f"Выгрузка · {n}",
        "callback_data": "pay_export",
        "icon_custom_emoji_id": EXPORT_ICON,
    }]]}


def is_export(text):
    t = (text or "").strip().lower()
    return t.startswith("/export") or "выгруз" in t or t.startswith("📤")


def export_paid(tg):
    """Отдать накопленные успешные ссылки текстом в чат и обнулить счётчик."""
    links = load_paid()
    if not links:
        tg.send("📤 Успешных ссылок пока нет.", reply_markup=menu_kb(0))
        return 0
    body = "\n".join(links)
    while body:
        tg.send(body[:3500])
        body = body[3500:]
    save_paid([])
    tg.send(f"📤 Выгружено: {len(links)}. Счётчик обнулён.", reply_markup=menu_kb(0))
    return len(links)


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
            text = str(text)[:4000]
            data = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
            ents = emoji_entities(text)
            if ents:
                data["entities"] = json.dumps(ents, ensure_ascii=False)
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            self._call("sendMessage", **data)
        except Exception as exc:
            log(f"send error: {type(exc).__name__}: {exc}")

    def send_photo(self, path, caption="", reply_markup=None):
        try:
            caption = str(caption)[:1000]
            data = {"chat_id": self.chat_id, "caption": caption}
            ents = emoji_entities(caption)
            if ents:
                data["caption_entities"] = json.dumps(ents, ensure_ascii=False)
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            with open(path, "rb") as f:
                r = self.session.post(f"{self.base}/sendPhoto", data=data, files={"photo": f}, timeout=120)
            return r.ok
        except Exception as exc:
            log(f"send_photo error: {type(exc).__name__}: {exc}")
            return False

    def send_document(self, name, text, caption="", reply_markup=None):
        try:
            caption = str(caption)[:1000]
            data = {"chat_id": self.chat_id, "caption": caption}
            ents = emoji_entities(caption)
            if ents:
                data["caption_entities"] = json.dumps(ents, ensure_ascii=False)
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            r = self.session.post(
                f"{self.base}/sendDocument", data=data,
                files={"document": (name, text.encode("utf-8"), "text/plain")}, timeout=120)
            return bool(r.ok and r.json().get("ok"))
        except Exception as exc:
            log(f"send_document error: {type(exc).__name__}: {exc}")
            return False

    def drop_reply_keyboard(self):
        """Убрать старую нижнюю кнопку, если она осталась от прошлой версии."""
        try:
            res = self._call("sendMessage", chat_id=self.chat_id, text="·",
                             reply_markup=json.dumps({"remove_keyboard": True}))
            mid = ((res or {}).get("result") or {}).get("message_id")
            if mid:
                self._call("deleteMessage", chat_id=self.chat_id, message_id=mid)
        except Exception:
            pass

    def get_updates(self, timeout=25):
        """Long-poll. Список событий от нашего chat_id, по порядку:
        {"kind":"text","text":...} или {"kind":"callback","data":...,"id":...} (нажатие inline-кнопки)."""
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
            cb = upd.get("callback_query")  # PAY_CARD_CHOICE_1591R103: нажатие inline-кнопки
            if cb:
                chat = str(((cb.get("message") or {}).get("chat") or {}).get("id") or "")
                if self.chat_id and chat and chat != self.chat_id:
                    continue
                out.append({"kind": "callback", "data": str(cb.get("data") or ""), "id": cb.get("id")})
                continue
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = str((msg.get("chat") or {}).get("id") or "")
            text = msg.get("text")
            if text is None:
                continue
            if self.chat_id and chat != self.chat_id:
                continue  # чужой чат — игнор
            out.append({"kind": "text", "text": text.strip()})
        return out

    def answer_callback(self, cbid):
        try:
            self._call("answerCallbackQuery", callback_query_id=cbid)
        except Exception:
            pass


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
        for sel in ("button", "[role=button]", "input[type=submit]", "input[type=button]", "a", "div", "span"):
            try:
                loc = scope.locator(sel)
                if not sel.startswith("input"):
                    loc = loc.filter(has_text=rx)
                n = min(loc.count(), 8)
                for i in range(n):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible() or not el.is_enabled():
                            continue
                        blob = ""
                        try:
                            blob = el.inner_text(timeout=400) or ""
                        except Exception:
                            blob = ""
                        if not blob.strip():
                            blob = el.get_attribute("value") or ""
                        if not rx.search(blob):
                            continue
                        el.scroll_into_view_if_needed(timeout=1500)
                        el.click(timeout=2500)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            scope.wait_for_timeout(300)
        except Exception:
            return False
    return False


def _click_labeled(scope, word, timeout_ms=2500):
    """Клик по элементу, у которого свой текст или value ровно это слово, без родителя."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    want = word.strip().lower()
    while time.monotonic() < deadline:
        for sel in ("button", "input[type=submit]", "input[type=button]", "[role=button]", "a", "div", "span"):
            try:
                loc = scope.locator(sel)
                n = min(loc.count(), 40)
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if not el.is_visible() or not el.is_enabled():
                        continue
                    blob = ""
                    try:
                        blob = (el.inner_text(timeout=300) or "").strip()
                    except Exception:
                        blob = ""
                    if not blob:
                        blob = (el.get_attribute("value") or "").strip()
                    if blob.lower() != want:
                        continue
                    el.scroll_into_view_if_needed(timeout=1500)
                    el.click(timeout=2500)
                    return True
                except Exception:
                    continue
        try:
            scope.wait_for_timeout(200)
        except Exception:
            return False
    return False


def _next_empty_card_input(scope, deadline):
    """Следующее НЕЗАПОЛНЕННОЕ видимое поле карты. Поля с уже введённым значением (в т.ч.
    замаскированный номер «*1936») и помеченные нами пропускаем — поэтому не зависим от того,
    сколько полей на форме и как она перерисовывается."""
    while True:
        for h in _visible_inputs(scope):
            try:
                if h.get_attribute("data-pb-filled"):
                    continue
                if (h.input_value() or "").strip():
                    continue
                return h
            except Exception:
                continue
        if time.monotonic() >= deadline:
            return None
        try:
            scope.wait_for_timeout(300)
        except Exception:
            time.sleep(0.3)


def _inputs_debug(scope):
    """Короткое описание всех полей на форме — чтобы понять, чем является «код» (вдруг не <input>)."""
    out = []
    try:
        for h in scope.locator("input").element_handles():
            try:
                out.append("[vis=%s type=%s im=%s ph=%r name=%s val=%s]" % (
                    h.is_visible(), h.get_attribute("type"), h.get_attribute("inputmode"),
                    (h.get_attribute("placeholder") or "")[:16], h.get_attribute("name"),
                    "да" if (h.input_value() or "").strip() else "пусто"))
            except Exception:
                out.append("[?]")
    except Exception:
        pass
    extra = ""
    try:
        extra = " | contenteditable: %d" % scope.locator("[contenteditable=true]").count()
    except Exception:
        pass
    return ("поля: " + (" ".join(out) if out else "НЕТ <input> в этой области")) + extra


def _fill_card_field(h, value):
    h.click()
    h.type(value, delay=70)
    try:
        h.evaluate("e => e.setAttribute('data-pb-filled','1')")
    except Exception:
        pass


def _type_card(page, card, tg, deadline):
    """Форма «новая карта»: поля появляются по очереди (номер → срок → код). Ищем «следующее
    пустое поле», а не «N-е по счёту» — форма перерисовывается, и счёт полей сбивается."""
    num, exp, cvv = card
    scope = _card_scope(page, deadline)
    f = _next_empty_card_input(scope, deadline)
    if f is None:
        raise RuntimeError("форма карты не найдена. " + _inputs_debug(scope))
    _fill_card_field(f, num)
    f = _next_empty_card_input(scope, deadline)
    if f is None:
        raise RuntimeError("поле срока не появилось после номера карты. " + _inputs_debug(scope))
    _fill_card_field(f, exp)
    f = _next_empty_card_input(scope, deadline)
    if f is None:
        raise RuntimeError("поле кода карты (CVV) не появилось. " + _inputs_debug(scope))
    _fill_card_field(f, cvv)
    # увести фокус с CVV — у части форм кнопка «оплатить» загорается только после «потери фокуса»
    try:
        f.press("Tab")
    except Exception:
        pass
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(800)
    # кнопка «оплатить» может стать активной не сразу — ждём до дедлайна
    try:
        tg.send("💳 Карта введена, жму «оплатить» (жду активации кнопки)…")
    except Exception:
        pass
    left_ms = max(8000, int((deadline - time.monotonic()) * 1000))
    if not _click_by_words(scope, ("оплатить",), timeout_ms=left_ms):
        raise RuntimeError("кнопка «оплатить» не нажалась (кнопка осталась неактивной — проверь карту/срок/CVV)")
    return True


def _on_card_form(page):
    """True, пока открыта форма ввода карты (ещё НЕ ушли на страницу банка). Нужно, чтобы не
    принять CVV-поле карты (с подписью «код») за поле кода 3DS."""
    for fr in _frames(page):
        try:
            if fr.locator("input[placeholder*='0000']").count():
                return True
        except Exception:
            pass
        try:
            low = (fr.locator("body").inner_text(timeout=600) or "").lower()
            if "новая карта" in low and "номер карты" in low:
                return True
        except Exception:
            pass
    return False


# PAY_3DS_1591R103: усиленный детект поля кода 3DS — по ПРИЗНАКАМ самого инпута, а не только
# по тексту рядом. Так ловятся формы без подписей и во вложенных iframe банка (ACS).
def _otp_score(h):
    """Насколько поле похоже на ввод 3DS/OTP-кода. Больше — вероятнее. -1 = это точно не код."""
    try:
        if not h.is_visible():
            return -1
        typ = (h.get_attribute("type") or "text").lower()
        if typ in ("hidden", "checkbox", "radio", "submit", "button", "email"):
            return -1
        ac = (h.get_attribute("autocomplete") or "").lower()
        im = (h.get_attribute("inputmode") or "").lower()
        ph = (h.get_attribute("placeholder") or "").lower()
        name = ((h.get_attribute("name") or "") + " " + (h.get_attribute("id") or "")
                + " " + (h.get_attribute("aria-label") or "")).lower()
        if typ == "password" and any(w in name for w in ("cvc", "cvv", "secure")):
            return -1
        ml = h.get_attribute("maxlength") or ""
        score = 1 if typ == "password" else 0
        if "one-time-code" in ac:                       score += 6   # почти стандарт ACS/3DS
        if im == "numeric":                             score += 3
        if typ in ("tel", "number"):                    score += 2
        try:
            if ml and 3 <= int(ml) <= 8:                score += 2
        except ValueError:
            pass
        if any(w in ph for w in ("код", "смс", "sms", "code", "otp", "пуш", "one-time")):   score += 4
        if any(w in name for w in ("otp", "code", "sms", "pin", "код")):                    score += 4
        if (h.input_value() or "").strip():             score -= 3   # уже заполнено — вряд ли то
        return score
    except Exception:
        return -1


def _find_code_field(page):
    """Найти поле ввода 3DS-кода в любой рамке. Возвращает (frame, element) или (None, None).

    PAY_3DS_1591R103: ищем по признакам инпута (autocomplete=one-time-code, inputmode=numeric,
    type tel/number, короткий maxlength, подписи), плюс запас — единственное видимое поле в рамке.
    Больше не требуем, чтобы слово-подсказка было в тексте страницы."""
    if _on_card_form(page):   # пока открыта форма карты — поля 3DS ещё нет, CVV не путаем с кодом
        return None, None
    best = None   # (score, frame, handle)
    for fr in _frames(page):
        vis = _visible_inputs(fr)
        for h in vis:
            s = _otp_score(h)
            if s >= 4 and (best is None or s > best[0]):
                best = (s, fr, h)
        if len(vis) == 1:   # на рамке ровно одно видимое поле — это почти наверняка код
            s = _otp_score(vis[0])
            if s >= 0:
                s += 2
                if best is None or s > best[0]:
                    best = (s, fr, vis[0])
    if best is not None and best[0] >= 2:
        return best[1], best[2]
    # Сбер (acs3.sbrf.ru): большое поле кода часто type=password и без подписи в атрибутах.
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    try:
        low = _page_text(page)
    except Exception:
        low = ""
    if "sbrf.ru" in url or "sberbank" in url or any(w in low for w in (
            "введите код", "отправили код", "код для оплаты", "код из смс", "код из sms",
            "карта цупис", "аутентификация покупки", "введите ваш код")):
        pick = None
        for fr in _frames(page):
            for h in _visible_inputs(fr):
                if _otp_score(h) < 0:
                    continue
                area = 0
                try:
                    box = h.bounding_box()
                    if box:
                        area = box["width"] * box["height"]
                except Exception:
                    area = 0
                if area < 40:
                    continue
                if pick is None or area > pick[0]:
                    pick = (area, fr, h)
        if pick is not None:
            return pick[1], pick[2]
    return None, None


def _page_text(page):
    chunks = []
    for fr in _frames(page):
        try:
            chunks.append((fr.locator("body").inner_text(timeout=800) or "").lower())
        except Exception:
            pass
    return "\n".join(chunks)


def _payment_failed(page):
    """PAY_3DS_1591R103: страница «оплата не прошла» (ошибка Билайна со своей кнопкой «попробовать ещё раз»)."""
    try:
        low = _page_text(page)
    except Exception:
        low = ""
    if any(w in low for w in PAYMENT_FAILED_WORDS):
        return True
    try:
        if "/registration/error" in (page.url or "").lower():
            return True
    except Exception:
        pass
    return False


def _click_retry(page):
    """PAY_3DS_1591R103: нажать «попробовать ещё раз» в любой рамке."""
    for fr in _frames(page):
        if _click_by_words(fr, RETRY_WORDS, timeout_ms=4000):
            return True
    return False


def _click_resend(page):
    """PAY_RESEND_1591R103: нажать «отправить код повторно» на 3DS-странице (во всех фреймах).
    Возвращает 'clicked' (нажали) / 'timer' (есть, но заблокирована отсчётом) / 'notfound' (нет кнопки)."""
    rx = re.compile("|".join(re.escape(w) for w in RESEND_WORDS), re.I)
    found_disabled = False
    for fr in _frames(page):
        for sel in ("button", "[role=button]", "a", "span", "div"):
            try:
                loc = fr.locator(sel).filter(has_text=rx)
                n = min(loc.count(), 8)
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    enabled = True
                    try:
                        enabled = el.is_enabled()
                    except Exception:
                        enabled = True
                    # кнопка/элемент с отсчётом времени в тексте («0:59», «через 59 сек») — ещё нельзя
                    try:
                        etxt = (el.inner_text(timeout=600) or "")
                    except Exception:
                        etxt = ""
                    if re.search(r"\b\d{1,2}:\d{2}\b|через\s+\d|\d+\s*сек", etxt, re.I):
                        found_disabled = True
                        continue
                    if not enabled:
                        found_disabled = True
                        continue
                    el.scroll_into_view_if_needed(timeout=1500)
                    el.click(timeout=2500)
                    return "clicked"
                except Exception:
                    continue
    return "timer" if found_disabled else "notfound"


def _resend_timer_left(page):
    """Остаток отсчёта повтора кода («0:59» или «59 сек»), если виден на странице — для подсказки."""
    try:
        txt = _page_text(page)
    except Exception:
        return ""
    m = re.search(r"\b(\d{1,2}:\d{2})\b", txt) or re.search(r"(\d{1,3})\s*сек", txt)
    return m.group(1) if m else ""


def _is_alfa_app_push(page):
    """Альфа-Банк: пуш в приложение, поля кода ещё нет. Узнаём по ссылке 3DS и по тексту."""
    blob = ""
    try:
        blob += " " + (page.url or "")
    except Exception:
        pass
    for fr in _frames(page):
        try:
            blob += " " + (fr.url or "")
        except Exception:
            pass
    low_url = blob.lower()
    try:
        low = _page_text(page)
    except Exception:
        low = ""
    if "подтвердить другим способом" in low or "откройте мобильное приложение банка" in low:
        return True
    return "alfabank" in low_url


def _click_alfa_other(page):
    """Нажать именно «Подтвердить другим способом», не «Отменить оплату»."""
    for fr in _frames(page):
        if _click_by_words(fr, ("подтвердить другим способом",), timeout_ms=4000):
            return True
    return False


def _is_yoomoney(page):
    """PAY_YOOMONEY_1591R103: это банк YooMoney (по URL или тексту страницы)."""
    try:
        if "yoomoney" in (page.url or "").lower():
            return True
    except Exception:
        pass
    try:
        return "yoomoney" in _page_text(page)
    except Exception:
        return False


def _click_get_sms(page):
    """YooMoney: нажать «получить код по СМС / ввести код из СМС» в любой рамке."""
    for fr in _frames(page):
        if _click_by_words(fr, GET_SMS_WORDS, timeout_ms=3000):
            return True
    return False


def _yoomoney_push_flow(page, tg, cfg):
    """PAY_YOOMONEY_1591R103: YooMoney просит подтверждение PUSH в приложении банка (поля кода нет).
    Шлём пуш + кнопку «📲 Получить код по СМС». Возвращает:
       'code' (появилось поле кода — дальше обычный ввод) / 'success' / 'fail' / 'timeout'."""
    kb = {"inline_keyboard": [[{"text": "📲 Получить код по СМС", "callback_data": "yoo_sms"}]]}
    tg.send("🔔 Банк YooMoney запросил PUSH — подтвердите оплату в приложении своего банка.\n"
            "Если пуш не приходит — нажми «📲 Получить код по СМС», переключу на ввод кода из SMS.",
            reply_markup=kb)
    wait = int(cfg.get("push_wait_seconds") or cfg.get("code_wait_seconds") or 300)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        st = _url_status(page)
        if st == "success":
            return "success"
        if st == "fail" or _payment_failed(page):
            return "fail"
        fr, h = _find_code_field(page)   # пользователь подтвердил пуш или переключил на СМС
        if h is not None:
            return "code"
        for ev in tg.get_updates(timeout=2):
            if ev.get("kind") == "callback":
                tg.answer_callback(ev.get("id"))
                if ev.get("data") == "yoo_sms":
                    if _click_get_sms(page):
                        tg.send("📨 Переключаю на код из СМС — жди СМС и пришли код.")
                    else:
                        tg.send("⚠️ На странице не нашёл переключение на СМС. Подтверди PUSH в банке, "
                                "или пришли «отмена».")
            else:
                t = (ev.get("text") or "").strip().lower()
                if t in ("отмена", "stop", "/stop", "cancel"):
                    return "fail"
                if t in ("смс", "sms", "код по смс", "получить смс", "по смс"):
                    if _click_get_sms(page):
                        tg.send("📨 Переключаю на код из СМС — жди СМС.")
        page.wait_for_timeout(800)
    return "timeout"


def _url_status(page):
    """PAY_STATUS_1591R103: итог оплаты из финальной ссылки — Билайн пишет его в query:
    ...&status=success&...  → оплата прошла;  ...&status=fail&...  → не прошла.
    Возвращает 'success' / 'fail' / '' (ещё не определён)."""
    try:
        q = urllib.parse.urlparse(page.url or "").query
        st = (urllib.parse.parse_qs(q).get("status") or [""])[0].strip().lower()
    except Exception:
        return ""
    if st.startswith("succ"):
        return "success"
    if st.startswith("fail"):
        return "fail"
    return ""


def _esim_ready(page):
    """eSIM уже выпущена. «Установить eSIM» на шагах оплаты само по себе успехом не считается."""
    try:
        low = _page_text(page)
    except Exception:
        return False
    if "вы в билайне" in low:
        return True
    if "осталось установить" in low and "готов" in low:
        return True
    if "на установку esim" in low:
        return True
    return False


def _wait_final_result(page, timeout_s=70):
    """PAY_STATUS_1591R103: после принятого кода страница показывает «ждём ответ от банка» ~20-40 сек,
    затем итог. Читаем status из URL (авторитетно), либо ловим форму «оплата не прошла». Успех по
    тексту НЕ определяем — на промежуточной странице есть и «установить eSIM», и «договора»."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        st = _url_status(page)
        if st:
            return st
        if _esim_ready(page):
            return "success"
        if _payment_failed(page):   # появилась форма «оплата не прошла / попробовать ещё раз»
            return "fail"
        page.wait_for_timeout(1000)
    return "unknown"


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


def _send_shot(tg, page, name, caption, reply_markup=None):
    shot = _shot(page, name)
    if shot:
        tg.send_photo(shot, caption=caption, reply_markup=reply_markup)
        try:
            os.unlink(shot)
        except OSError:
            pass
    else:
        tg.send(caption, reply_markup=reply_markup)


# ── ввод 3DS-кода (вызывается, когда поле кода уже найдено) ─────────────────
def _wait_code_or_resend(tg, timeout_seconds):
    """PAY_RESEND_1591R103: ждём код (текст), кнопку «повторить СМС» или «отмена». Возвращает
       ('code', код) | ('resend', None) | ('cancel', None) | ('timeout', None)."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for ev in tg.get_updates(timeout=25):
            if ev.get("kind") == "callback":
                if ev.get("id"):
                    tg.answer_callback(ev.get("id"))
                if ev.get("data") == "resend_sms":
                    return ("resend", None)
                if ev.get("data") in ("op_leave", "ai_cancel", "sess_finish"):
                    return ("cancel", None)
                continue
            t = (ev.get("text") or "").strip()
            if not t:
                continue
            low = t.lower()
            if low in ("отмена", "stop", "/stop", "cancel"):
                return ("cancel", None)
            if low in ("повтор", "повтор смс", "повторить смс", "ещё смс", "еще смс", "новый код", "ещё код", "еще код"):
                return ("resend", None)
            return ("code", t)
    return ("timeout", None)


def _enter_3ds_code(page, tg, cfg, page_wait, code_wait):
    """Цикл ввода кода из SMS/пуша. Возвращает один из вердиктов:
       accepted / declined / wrong_exhausted / timeout / cancelled / lost.
    На каждом шаге есть кнопка «📨 Повторить СМС» (PAY_RESEND_1591R103)."""
    resend_kb = {"inline_keyboard": [[{"text": "📨 Повторить СМС (запросить код заново)",
                                       "callback_data": "resend_sms"}]]}
    for attempt in range(1, 6):
        fr = h = None
        field_deadline = time.monotonic() + page_wait
        while time.monotonic() < field_deadline:   # ждём появления поля кода
            if _payment_failed(page) or _url_status(page) == "fail" or any(w in _page_text(page) for w in DECLINE_WORDS):
                return "declined"
            fr, h = _find_code_field(page)
            if h is not None:
                break
            page.wait_for_timeout(500)
        if h is None:
            return "lost"

        tg.send(f"🔢 Пришли код из SMS/пуша (попытка {attempt}/5). Кнопка ниже — запросить код заново. "
                "Или «отмена».", reply_markup=resend_kb)
        code = None
        while code is None:
            kind, value = _wait_code_or_resend(tg, code_wait)
            if kind == "timeout":
                tg.send("⌛ Код не пришёл вовремя — отменяю эту ссылку.")
                return "timeout"
            if kind == "cancel":
                tg.send("✖️ Отменил эту ссылку.")
                return "cancelled"
            if kind == "resend":
                res = _click_resend(page)
                if res == "clicked":
                    tg.send("📨 Запросил код заново — жди новую СМС и пришли код сюда.")
                elif res == "timer":
                    left = _resend_timer_left(page)
                    tg.send("⏳ Повтор кода пока недоступен" + (f" (осталось ~{left})" if left else "") +
                            " — на странице идёт отсчёт. Подожди и нажми «📨 Повторить СМС» снова.")
                else:
                    tg.send("⚠️ Кнопку повтора кода на странице не нашёл. Если код не приходит — пришли «отмена», "
                            "или дождись СМС и введи код.")
                continue   # ждём код/повтор дальше
            code = value   # kind == 'code'

        # после повтора СМС поле могло перерисоваться — перечитаем его
        fr, h = _find_code_field(page)
        if h is None:
            return "lost"
        try:
            before = _page_text(page)
        except Exception:
            before = ""
        try:
            h.click()
            try:
                h.fill("")
            except Exception:
                pass
            h.type(re.sub(r"\D", "", code), delay=90)
        except Exception as exc:
            tg.send(f"⚠️ Не смог вписать код: {type(exc).__name__}. Пробую снова.")
            continue
        page.wait_for_timeout(700)
        # ЦУПИС: поле «Ваш код» и зелёная «Подтвердить». Серую «Отправить код еще раз» не жмём.
        clicked = False
        try:
            low = _page_text(page)
        except Exception:
            low = ""
        if "карта цупис" in low or "аутентификация покупки" in low or "введите ваш код" in low:
            for fr2 in _frames(page):
                if _click_labeled(fr2, "подтвердить", timeout_ms=2000):
                    clicked = True
                    break
        if not clicked:
            try:
                _click_by_words(fr, CODE_SUBMIT_WORDS, timeout_ms=3000)
            except Exception:
                pass

        def _wrong_hits(text):
            return sum(text.count(w) for w in WRONG_CODE_WORDS)

        # Подсказка «если код неверный» часто есть на странице сразу. Это не отказ.
        # Отказ — только если таких слов стало больше после отправки.
        before_hits = _wrong_hits(before)
        react_deadline = time.monotonic() + 90
        missing_since = None
        while time.monotonic() < react_deadline:
            if _url_status(page) == "success":
                return "accepted"
            try:
                low = _page_text(page)
            except Exception:
                low = ""
            try:
                _fr2, h2 = _find_code_field(page)
            except Exception:
                return "accepted"
            if h2 is None:
                if missing_since is None:
                    missing_since = time.monotonic()
                elif time.monotonic() - missing_since > 2:
                    return "accepted"
            else:
                missing_since = None
                if _wrong_hits(low) > before_hits:
                    tg.send("↩️ Банк: код неверный. Пришли код заново (или «📨 Повторить СМС»).")
                    break
            if _payment_failed(page) or _url_status(page) == "fail" or any(w in low for w in DECLINE_WORDS):
                return "declined"
            try:
                page.wait_for_timeout(500)
            except Exception:
                return "accepted"
        else:
            tg.send("⏳ Банк пока не ответил на код. Пришли новый код, «📨 Повторить СМС» или «отмена».")
    return "wrong_exhausted"


# ── обработка одной ссылки ─────────────────────────────────────────────────
def process_link(pw_browser, link, card, tg, cfg):
    code_wait = int(cfg.get("code_wait_seconds") or 300)
    # Билайн сейчас может грузить форму/поле оплаты по 2-3 минуты — ждём терпеливо.
    page_wait = int(cfg.get("page_wait_seconds") or 240)   # сек на появление кнопки/формы/кода
    max_beeline_retries = int(cfg.get("beeline_retry_max") or 3)   # PAY_3DS_1591R103
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
            log("кнопку «оплатить» не нашёл на первой странице — пробую сразу форму карты")
        page.wait_for_timeout(2000)

        beeline_retries = 0        # PAY_3DS_1591R103: подряд пойманные мгновенные ошибки Билайна
        reached_bank = False       # дошли до страницы банка (3DS) — дальше ошибка = проблема карты

        while True:   # каждая итерация — одна попытка ввести карту
            # A) мгновенная «оплата не прошла» ДО банка (текст ИЛИ status=fail в URL) → сбой Билайна, авто-ретрай
            if (_payment_failed(page) or _url_status(page) == "fail") and not reached_bank:
                beeline_retries += 1
                tg.send(f"⚠️ Оплата не прошла моментально — ошибка на стороне Билайна, пробую ещё раз "
                        f"({beeline_retries}/{max_beeline_retries}).")
                if beeline_retries > max_beeline_retries:
                    tg.send("❌ Билайн подряд отдаёт «оплата не прошла». Пропускаю ссылку — попробуй позже.")
                    return "beeline_fail"
                if not _click_retry(page):
                    tg.send("⚠️ Не нашёл кнопку «попробовать ещё раз» — пропускаю ссылку.")
                    return "error"
                page.wait_for_timeout(3000)
                continue   # загрузилась новая форма карты → по кругу

            # B) ввод карты
            tg.send(f"💳 Ввожу карту {mask_card(card[0])} (жду загрузку формы, это может занять минуты)…")
            deadline = time.monotonic() + page_wait
            try:
                _type_card(page, card, tg, deadline)
            except RuntimeError as exc:
                if (_payment_failed(page) or _url_status(page) == "fail") and not reached_bank:
                    continue   # вместо формы вылезла мгновенная ошибка — на ретрай сверху
                raise
            page.wait_for_timeout(3000)

            # C) ждём: страница банка (поле 3DS) / мгновенная ошибка / отказ до кода / YooMoney-PUSH
            tg.send("⏳ Оплата отправлена, жду страницу банка (3DS)…")
            nav_deadline = time.monotonic() + page_wait
            c_start = time.monotonic()
            branch = "wait"
            while time.monotonic() < nav_deadline:
                if (_payment_failed(page) or _url_status(page) == "fail") and not reached_bank:
                    branch = "instant_fail"
                    break
                if _url_status(page) == "success":
                    branch = "success_direct"
                    break
                low = _page_text(page)
                if any(w in low for w in DECLINE_WORDS):
                    branch = "declined_precode"
                    break
                fr, h = _find_code_field(page)
                if h is not None:
                    branch = "code"
                    break
                # PAY_YOOMONEY_1591R103: YooMoney без поля кода дольше ~8с → ждёт PUSH в приложении банка
                if _is_yoomoney(page) and (time.monotonic() - c_start) > 8:
                    branch = "yoomoney"
                    break
                page.wait_for_timeout(500)

            if branch == "instant_fail":
                continue   # верх цикла сделает пуш и ретрай
            if branch == "declined_precode":
                tg.send("❌ Оплата не прошла — банк отклонил ещё до ввода кода. Перехожу к следующей ссылке.")
                return "declined"
            if branch == "wait":
                _send_shot(tg, page, "no_code",
                           "⚠️ Поле кода (3DS) не появилось за отведённое время. Оплату НЕ подтверждаю — "
                           "возможно, страница ещё грузилась или банк не прислал код. Вот что на экране:")
                return "no_code"

            # D) дошли до банка
            reached_bank = True
            verdict = None
            final = None

            if branch == "success_direct":
                final = "success"
            elif branch == "yoomoney":
                # PAY_YOOMONEY_1591R103: сперва PUSH в приложении банка (+ кнопка «получить код по СМС»)
                yoo = _yoomoney_push_flow(page, tg, cfg)
                if yoo == "success":
                    final = "success"
                elif yoo == "fail":
                    final = "fail"
                elif yoo == "timeout":
                    tg.send("⌛ YooMoney: подтверждение PUSH не завершено вовремя.")
                    final = "fail"
                else:   # 'code' — появилось поле кода, вводим как обычно
                    verdict = _enter_3ds_code(page, tg, cfg, page_wait, code_wait)
            else:   # branch == "code"
                verdict = _enter_3ds_code(page, tg, cfg, page_wait, code_wait)

            if verdict is not None:
                if verdict == "cancelled":
                    return "cancelled"
                if verdict == "timeout":
                    return "timeout"
                if verdict == "declined":
                    final = "fail"   # банк отклонил прямо на этапе кода
                elif verdict in ("wrong_exhausted", "lost"):
                    # PAY_CARD_CHOICE_1591R103: код не подтверждён — ссылку НЕ пропускаем, ведём как обычный
                    # fail: ждём страницу результата, дальше кнопки «та же / новая карта».
                    tg.send("⏳ Код не подтверждён — жду страницу результата…")
                    final = _wait_final_result(page, timeout_s=int(cfg.get("final_wait_seconds") or 70))
                    if final == "unknown":
                        final = "fail"
                else:
                    # verdict == accepted → ждём реальный ответ банка («ждём ответ от банка» ~20-40 сек)
                    tg.send("⏳ Код принят, ждём ответ от банка (обычно 20-40 сек)…")
                    final = _wait_final_result(page, timeout_s=int(cfg.get("final_wait_seconds") or 70))
            try:
                cur = page.url
            except Exception:
                cur = link

            if final == "success":
                saved = cur if str(cur).startswith("http") else link
                n = remember_paid(saved)
                _send_shot(tg, page, "result",
                           f"✅ Оплата ПРОШЛА успешно (status=success).\nURL: {cur}\n"
                           f"📤 К выгрузке: {n}.\n\n"
                           "Дальше — страница установки eSIM / QR. Автополучение QR пока не настроено: пришли "
                           "скрин+HTML страницы с QR и кнопкой «Получить QR», добавлю.",
                           reply_markup=menu_kb(n))
                return "paid"
            if final == "unknown":
                _send_shot(tg, page, "unknown",
                           f"⚠️ Код принят, но итог от банка не определился за отведённое время "
                           f"(в URL нет status=success/fail). Посмотри вручную.\nURL: {cur}")
                return "unknown"

            # final == "fail" → оплата не прошла ПОСЛЕ кода: спрашиваем кнопками «та же / новая карта»
            # PAY_CARD_CHOICE_1591R103
            choice, newcard = _ask_fail_choice(tg, cur, cfg)
            if choice == "same":
                tg.send("🔁 Повторяю этой же картой…")
            elif choice == "new":
                card = newcard
                tg.send(f"💳 Беру новую карту {mask_card(card[0])}, повторяю…")
            else:   # cancel / timeout
                tg.send("✖️ Оставляю эту ссылку неоплаченной, иду дальше.")
                return "declined"
            if not _click_retry(page):
                tg.send("⚠️ Не нашёл кнопку «попробовать ещё раз» на странице — пропускаю ссылку.")
                return "declined"
            reached_bank = False   # новая попытка — снова с нуля до банка
            beeline_retries = 0
            page.wait_for_timeout(3000)
            continue
    except PWTimeout as exc:
        tg.send(f"⚠️ Таймаут на странице: {exc}")
        _send_shot(tg, page, "timeout", "Где застряло (таймаут).")
        return "error"
    except Exception as exc:
        log("process_link error:\n" + traceback.format_exc())
        tg.send(f"⚠️ Ошибка: {type(exc).__name__}: {exc}")
        _send_shot(tg, page, "error", "Где застряло (ошибка).")
        return "error"
    finally:
        try:
            context.close()
        except Exception:
            pass


# глобальная ссылка на Telegram для ожидания кода внутри обработки
_TG = None


def _wait_user_code(tg, timeout_seconds):
    """Ждём следующее текстовое сообщение пользователя (код). Нажатия кнопок игнорируем."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for ev in tg.get_updates(timeout=25):
            if ev.get("kind") == "callback":
                if ev.get("data") == "pay_export":
                    tg.answer_callback(ev.get("id"))
                    export_paid(tg)
                    continue
                tg.answer_callback(ev.get("id"))
                continue
            t = ev.get("text")
            if t:
                if is_export(t):
                    export_paid(tg)
                    continue
                return t.strip()
    return None


def _wait_fail_choice(tg, timeout_seconds):
    """PAY_CARD_CHOICE_1591R103: после fail-после-кода ждём выбор. Возвращает:
       'same' | 'new_wait' | ('new', card) | 'cancel' | 'timeout'."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for ev in tg.get_updates(timeout=25):
            if ev.get("kind") == "callback":
                tg.answer_callback(ev.get("id"))
                if ev.get("data") == "pay_export":
                    export_paid(tg)
                    continue
                if ev.get("data") == "pay_same":
                    return "same"
                if ev.get("data") == "pay_new":
                    return "new_wait"
                continue
            t = (ev.get("text") or "").strip()
            if is_export(t):
                export_paid(tg)
                continue
            low = t.lower()
            if low in ("отмена", "stop", "/stop", "cancel", "пропустить", "дальше"):
                return "cancel"
            if low in ("ещё раз", "еще раз", "повторить", "та же", "той же", "ещераз"):
                return "same"
            c = parse_card(t)
            if c:
                return ("new", c)
    return "timeout"


def _wait_new_card(tg, timeout_seconds):
    """Ждём новую карту (или «отмена»). Возвращает card-tuple или None."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for ev in tg.get_updates(timeout=25):
            if ev.get("kind") == "callback":
                if ev.get("data") == "pay_export":
                    tg.answer_callback(ev.get("id"))
                    export_paid(tg)
                    continue
                tg.answer_callback(ev.get("id"))
                continue
            t = (ev.get("text") or "").strip()
            if is_export(t):
                export_paid(tg)
                continue
            if t.lower() in ("отмена", "stop", "/stop", "cancel"):
                return None
            c = parse_card(t)
            if c:
                return c
    return None


def _ask_fail_choice(tg, cur, cfg):
    """PAY_CARD_CHOICE_1591R103: оплата не прошла после кода — предлагаем кнопки «та же / новая карта».
       Возвращает ('same', None) | ('new', card) | ('cancel'|'timeout', None)."""
    kb = {"inline_keyboard": [
        [{"text": "🔁 Повторить этой картой", "callback_data": "pay_same"}],
        [{"text": "💳 Ввести новую карту", "callback_data": "pay_new"}],
    ]}
    tg.send("❌ Оплата НЕ прошла (status=fail).\n"
            "Возможно, недостаточно средств либо карта заблокирована. ⚠️ Если этой картой уже оплачивали "
            "Билайн более 3 раз — сервис может её блокировать.\n"
            f"URL: {cur}\n\nЧто делаем? Нажми кнопку, пришли новую карту (НОМЕР СРОК КОД) или «отмена».",
            reply_markup=kb)
    choice = _wait_fail_choice(tg, int(cfg.get("choice_wait_seconds") or 300))
    if isinstance(choice, tuple) and choice[0] == "new":
        return ("new", choice[1])
    if choice == "new_wait":
        tg.send("💳 Пришли новую карту одним сообщением: НОМЕР СРОК КОД.")
        card = _wait_new_card(tg, int(cfg.get("code_wait_seconds") or 300))
        return ("new", card) if card else ("timeout", None)
    if choice == "same":
        return ("same", None)
    return (choice if choice in ("cancel", "timeout") else "cancel", None)


def main():
    cfg = load_config()
    tg = Telegram(cfg)
    headless = cfg.get("headless", True)
    pending = []          # очередь ссылок
    card = None           # (num, exp, cvv) в памяти
    with sync_playwright() as pw:
        # PAY_3DS_1591R103: сначала поднимаем браузер, и только после успеха шлём «запущен» —
        # иначе при отсутствии Chromium бот спамил бы «запущен» на каждом рестарте systemd.
        try:
            browser = pw.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as exc:
            log("chromium launch failed:\n" + traceback.format_exc())
            tg.send("⚠️ Бот оплаты не смог запустить Chromium — браузер не установлен.\n"
                    "Выполни на сервере одной строкой:\n"
                    "sudo PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers /opt/beeline/venv/bin/python -m playwright install chromium\n"
                    "потом: sudo systemctl restart pay_bot\n\n"
                    f"Ошибка: {str(exc)[:300]}")
            time.sleep(60)   # не спамить рестартами каждые 10 сек, пока не починят браузер
            raise
        n = len(load_paid())
        tg.send(f"📤 Успешных к выгрузке: {n}", reply_markup=menu_kb(n))
        try:
            while True:
                for ev in tg.get_updates(timeout=25):
                    if ev.get("kind") == "callback":
                        if ev.get("data") == "pay_export":
                            tg.answer_callback(ev.get("id"))
                            export_paid(tg)
                        else:
                            tg.answer_callback(ev.get("id"))
                        continue
                    text = ev.get("text") or ""
                    low = text.lower().strip()
                    if is_export(text):
                        export_paid(tg)
                        continue
                    if low in ("/stop", "стоп", "сброс"):
                        pending.clear(); card = None
                        tg.send("🧹 Очередь и карта сброшены.", reply_markup=menu_kb())
                        continue
                    if low in ("/start", "/help", "старт", "помощь"):
                        n = len(load_paid())
                        tg.send(f"Пришли ссылку(и), потом карту «НОМЕР СРОК КОД». /stop — сброс.\n"
                                f"📤 Успешных к выгрузке: {n}.", reply_markup=menu_kb(n))
                        continue
                    if low in ("/links", "очередь"):
                        tg.send(f"В очереди ссылок: {len(pending)}"
                                + ("\n" + "\n".join(pending) if pending else "")
                                + f"\n📤 Успешных к выгрузке: {len(load_paid())}.",
                                reply_markup=menu_kb())
                        continue
                    links = extract_links(text)
                    if links:
                        pending.extend(links)
                        tg.send(f"➕ Добавлено ссылок: {len(links)} (в очереди {len(pending)}).\n"
                                "Теперь пришли карту: НОМЕР СРОК КОД.", reply_markup=menu_kb())
                        continue
                    if looks_like_card(text):
                        card = parse_card(text)
                        if not pending:
                            tg.send(f"🗂 Карта принята ({mask_card(card[0])}), но очередь пуста. Пришли ссылку(и).",
                                    reply_markup=menu_kb())
                            continue
                        tg.send(f"🚀 Карта {mask_card(card[0])}. Начинаю оплату {len(pending)} ссылок по очереди.")
                        queue = list(pending); pending.clear()
                        done = {"paid": 0, "declined": 0, "error": 0, "other": 0}
                        for idx, link in enumerate(queue, 1):
                            tg.send(f"— [{idx}/{len(queue)}] —")
                            res = process_link(browser, link, card, tg, cfg)
                            done[res if res in done else "other"] = done.get(res if res in done else "other", 0) + 1
                        card = None   # карту из памяти убираем после прогона
                        n = len(load_paid())
                        tg.send(f"🏁 Готово. Оплачено: {done['paid']}, отклонено: {done['declined']}, "
                                f"ошибок: {done['error']}, прочее: {done['other']}.\n"
                                f"📤 Успешных к выгрузке: {n}.\nКарта очищена из памяти.",
                                reply_markup=menu_kb(n))
                        continue
                    tg.send("Не понял. Пришли ссылку (http...) или карту «НОМЕР СРОК КОД». /help",
                            reply_markup=menu_kb())
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
