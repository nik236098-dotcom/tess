#!/usr/bin/env python3
"""Which tariff an eSIM order carries, read from the order (payment) link itself, before any payment.

    sudo /opt/beeline/venv/bin/python order_tariff.py https://s.beeline.ru/registration/esim?hash_order=47180f97
    sudo /opt/beeline/venv/bin/python order_tariff.py 47180f97 ba031a19          # hashes alone are fine
    sudo /opt/beeline/venv/bin/python order_tariff.py                             # the last 10 links of payment_required.jsonl
    sudo /opt/beeline/venv/bin/python order_tariff.py --all <link>                # every JSON answer of the page, not only tariff-like keys

Opens every link in its own headless Chromium (not the bot's browser, nothing of the bot is touched),
waits for the page to settle and prints, per link: the tariff-like values found in the site's JSON
answers (keys named tariff/soc/plan/name/title/price/amount… and any string mentioning bee/смарт/
часов/подписк/тариф) and the lines of the visible page that mention a tariff or a price in ₽.
Read-only: nothing is clicked, typed or paid. Digit runs of 10 and more are masked in printed values.
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

LINK_RE = re.compile(r"https?://\S*hash_order=[0-9a-f]+", re.I)
HASH_RE = re.compile(r"^[0-9a-f]{6,32}$", re.I)
DEFAULT_LINK = "https://s.beeline.ru/registration/esim?hash_order={}"
TARIFF_WORDS = re.compile(r"\bbee(?!line)\s*\w+|смарт|часов|подписк|тариф", re.I)  # bee START/HIT, not beeline
KEY_WORDS = re.compile(r"tarif|tariff|soc\b|plan|price|amount|sum\b|cost|total|product|offer|rate", re.I)
# static dictionaries of the site (texts of errors and hints), not the order: skipped unless --all
STATIC_URL = re.compile(r"selfregcontent|/content/|dictionar|i18n|translation|static\.|chatwidget|analytics|metrika", re.I)
PRICE_LINE = re.compile(r"₽|руб", re.I)
MASK_RE = re.compile(r"\d{10,}")


def mask(value):
    return MASK_RE.sub(lambda m: "X" * len(m.group(0)), str(value))


def links_from_args(args):
    out = []
    for arg in args:
        m = LINK_RE.search(arg)
        if m:
            out.append(m.group(0))
        elif HASH_RE.match(arg):
            out.append(DEFAULT_LINK.format(arg))
        elif arg.startswith("http"):
            out.append(arg)
    return list(dict.fromkeys(out))


def links_from_records(limit=10, base=Path("/opt/beeline")):
    out = []
    for name in ("payment_required.jsonl", "unverified_signatures.jsonl", "successes.jsonl"):
        path = base / name
        if not path.is_file():
            continue
        for line in path.read_text("utf-8", errors="replace").splitlines()[-limit * 3:]:
            out.extend(m.group(0).rstrip('"\\') for m in LINK_RE.finditer(line))
    return list(dict.fromkeys(out))[-limit:]


def walk(node, path=""):
    """(path, value) for every scalar of a JSON document."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node[:50]):
            yield from walk(value, f"{path}[{index}]")
    else:
        yield path, node


def tariff_hits(payloads, everything=False):
    """Lines worth reading from the captured JSON answers: tariff-like keys and tariff-like strings."""
    lines = []
    for url, data in payloads:
        if STATIC_URL.search(url) and not everything:
            continue
        short_url = re.sub(r"^https?://[^/]+", "", url)[:90]
        per_payload = 0
        for path, value in walk(data):
            if per_payload >= 40:
                break
            text = str(value)
            key = path.rsplit(".", 1)[-1]
            wanted = everything or (KEY_WORDS.search(key) and value not in (None, "", [], {})) \
                or (isinstance(value, str) and TARIFF_WORDS.search(value))
            if wanted and len(text) <= 160:
                lines.append(f"    {short_url}  {path} = {mask(text)}")
                per_payload += 1
    return lines[:120]


def answers_summary(payloads):
    """One line per JSON answer: path, size and the top-level keys, so an unexpected endpoint is visible."""
    out = []
    for url, data in payloads:
        short_url = re.sub(r"^https?://[^/]+", "", url)[:100]
        body = data.get("data", data) if isinstance(data, dict) else data
        keys = ", ".join(list(body.keys())[:12]) if isinstance(body, dict) else type(body).__name__
        tag = "  (словарь текстов сайта)" if STATIC_URL.search(url) else ""
        out.append(f"    {short_url}  ключи: {mask(keys)[:150]}{tag}")
    return out


def first_lines(text, limit=14):
    out = []
    for raw in (text or "").splitlines():
        line = " ".join(raw.split())
        if line:
            out.append("    " + mask(line)[:160])
    return out[:limit]


def page_lines(text):
    out = []
    for raw in (text or "").splitlines():
        line = " ".join(raw.split())
        if line and (TARIFF_WORDS.search(line) or PRICE_LINE.search(line)) and len(line) <= 200:
            out.append("    " + mask(line))
    return list(dict.fromkeys(out))[:25]


def inspect(browser, link, everything=False, settle_ms=4000):
    host = urllib.parse.urlsplit(link).netloc.split(":")[0].split(".")[-2:]  # beeline.ru
    payloads = []

    def on_response(response):
        try:
            netloc = urllib.parse.urlsplit(response.url).netloc.split(":")[0].split(".")[-2:]
            if netloc != host:
                return
            if "json" not in (response.headers.get("content-type") or ""):
                return
            body = response.text()
            if len(body) > 400_000:
                return
            payloads.append((response.url, json.loads(body)))
        except Exception:
            pass

    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ru-RU")
    page = context.new_page()
    page.on("response", on_response)
    status = None
    try:
        main = page.goto(link, wait_until="domcontentloaded", timeout=45000)
        status = main.status if main else None
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(settle_ms)
        title = page.title()
        text = page.evaluate("() => document.body ? document.body.innerText : ''")
        final_url = page.url
    finally:
        context.close()
    return {"status": status, "final_url": final_url, "title": title,
            "json_lines": tariff_hits(payloads, everything), "page_lines": page_lines(text),
            "answers": answers_summary(payloads), "first_lines": first_lines(text)}


def launch_headless(p):
    """Headless Chromium of this Playwright; the full browser (as the bot uses) when the headless shell is absent."""
    args = ["--no-sandbox", "--disable-dev-shm-usage"]
    errors = []
    for kwargs in ({}, {"channel": "chromium"}, {"executable_path": "/opt/pw-browsers/chromium"}):
        try:
            return p.chromium.launch(headless=True, args=args, **kwargs)
        except Exception as exc:
            errors.append(f"{kwargs or 'default'}: {str(exc).splitlines()[0][:120]}")
    raise SystemExit("Chromium не запустился:\n  " + "\n  ".join(errors) + "\n  Поставьте браузер: /opt/beeline/venv/bin/python -m playwright install chromium")


def main(argv):
    args = argv[1:]
    everything = "--all" in args
    args = [a for a in args if a != "--all"]
    links = links_from_args(args) or links_from_records()
    if not links:
        raise SystemExit("Нет ссылок: передайте ссылку заказа (hash_order=…) или её хвост аргументом")
    with sync_playwright() as p:
        browser = launch_headless(p)
        try:
            for link in links:
                print("=" * 78 + f"\n{link}")
                try:
                    info = inspect(browser, link, everything)
                except Exception as exc:
                    print(f"  не открылась: {type(exc).__name__}: {str(exc)[:160]}")
                    continue
                print(f"  HTTP {info['status']}  → {info['final_url'][:110]}\n  Заголовок: {info['title'][:100]}")
                print(f"  Ответов сайта в JSON: {len(info['answers'])}")
                print("\n".join(info["answers"]))
                print("  Тариф и цена в ответах сайта:" if info["json_lines"] else "  В ответах сайта (кроме словарей) тариф не назван.")
                print("\n".join(info["json_lines"]))
                print("  На странице:" if info["page_lines"] else "  На странице нет строк с тарифом или ценой.")
                print("\n".join(info["page_lines"]))
                print("  Первые строки страницы:")
                print("\n".join(info["first_lines"]) or "    (пусто)")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
