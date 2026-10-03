#!/usr/bin/env python3
"""Current state of eSIM orders as the site itself reports it, asked from inside the bot's own
Chromium session (same cookies as the order), read-only: nothing is clicked or changed.

    sudo /opt/beeline/venv/bin/python order_status.py 08ee8923-bade-5bee-a2dd-2bab52f1b552 [more ids]
    sudo /opt/beeline/venv/bin/python order_status.py            # the last 10 orders of payment_required.jsonl

For every aggregateId it prints GET /v1/esim-selfreg/v2/getselfregstatus/ (selfregStatus,
errorCode, type, tryAfter) and which open tab answered. Every Chromium of the service is tried
(the journal lists one «Chromium #N готов» line per browser). Digits of URLs are kept: an
aggregateId is an order id, not personal data; nothing else of the page is printed.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

STATUS_PATH = "/v1/esim-selfreg/v2/getselfregstatus/?aggregateId="
FETCH_JS = """async (u) => {
  try {
    const r = await fetch(u, {credentials: 'include', headers: {'accept': 'application/json'}});
    return {status: r.status, text: (await r.text()).slice(0, 1200)};
  } catch (e) { return {status: -1, text: String(e)}; }
}"""


def cdp_urls_from_journal():
    try:
        log = subprocess.run(["journalctl", "-u", "beeline", "-b", "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception as exc:
        raise SystemExit(f"journalctl недоступен ({exc}); укажите порты через --cdp 9222,9223")
    # the newest launch wins: take the lines after the last «Запускаю N Chromium»
    tail = log.rsplit("Запускаю ", 1)[-1]
    urls = re.findall(r"Chromium #\d+ готов: (http://127\.0\.0\.1:\d+)", tail)
    if not urls:
        urls = re.findall(r"Chromium #\d+ готов: (http://127\.0\.0\.1:\d+)", log)[-2:]
    if not urls:
        raise SystemExit("Порт CDP не найден в журнале; укажите --cdp 9222,9223")
    return list(dict.fromkeys(urls))


def ids_from_records(limit=10):
    out = []
    for name in ("payment_required.jsonl", "unverified_signatures.jsonl"):
        path = Path("/opt/beeline") / name
        if not path.is_file():
            continue
        for line in path.read_text("utf-8", errors="replace").splitlines()[-limit:]:
            for m in re.finditer(r"aggregateId=([0-9a-f-]{36})", line):
                out.append(m.group(1))
    return list(dict.fromkeys(out))[-limit:]


def main(argv):
    args = argv[1:]
    cdp = None
    if "--cdp" in args:
        i = args.index("--cdp")
        cdp = [f"http://127.0.0.1:{p.strip()}" for p in args[i + 1].split(",")]
        args = args[:i] + args[i + 2:]
    ids = [a for a in args if re.fullmatch(r"[0-9a-f-]{36}", a)] or ids_from_records()
    if not ids:
        raise SystemExit("Нет aggregateId: передайте его аргументом (из строки sendpassportdata… в пуше)")
    cdp = cdp or cdp_urls_from_journal()
    print("CDP:", ", ".join(cdp))
    with sync_playwright() as p:
        tabs = []
        for url in cdp:
            try:
                browser = p.chromium.connect_over_cdp(url, timeout=20000)
            except Exception as exc:
                print(f"{url}: не подключился ({type(exc).__name__})")
                continue
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    if "beeline.ru" in pg.url:
                        tabs.append((url, pg))
        print(f"Вкладок beeline.ru: {len(tabs)}")
        for url, pg in tabs:
            try:
                name = pg.evaluate("() => window.name") or ""
            except Exception:
                name = ""
            print(f"  {url.rsplit(':', 1)[1]}  {name:28s} {pg.url[:110]}")
        if not tabs:
            raise SystemExit("Нет открытой вкладки beeline.ru, спросить сайт не из чего")
        for aid in ids:
            print("\n" + "=" * 78 + f"\naggregateId {aid}")
            answered = False
            for url, pg in tabs:
                host = re.match(r"https?://[^/]+", pg.url)
                if not host:
                    continue
                try:
                    res = pg.evaluate(FETCH_JS, host.group(0) + STATUS_PATH + aid)
                except Exception as exc:
                    print(f"  вкладка {pg.url[:60]}: evaluate не удался: {type(exc).__name__}")
                    continue
                text = res.get("text") or ""
                try:
                    data = json.loads(text).get("data") or {}
                    short = {k: data.get(k) for k in ("selfregStatus", "errorCode", "errorMessage", "tryAfter", "type")}
                except Exception:
                    short = text[:300]
                print(f"  HTTP {res.get('status')} через {host.group(0)}: {short}")
                answered = True
                break
            if not answered:
                print("  ни одна вкладка не ответила")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
