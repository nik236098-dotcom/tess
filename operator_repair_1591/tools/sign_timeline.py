#!/usr/bin/env python3
"""Per-row timeline of the confirmation and signing steps, from the beeline journal.

    sudo journalctl -u beeline --no-pager -o short-iso | python3 sign_timeline.py
    sudo journalctl -u beeline --no-pager -o short-iso --since "2 days ago" | python3 sign_timeline.py

For every row that reached the confirmation screen it prints: when the row started, how
long the mobile-id confirmation took and how many «отправить снова» it needed, when the
signature was drawn/clicked, signing errors, and the outcome (success / unverified /
timeout / error / restart). Digits of phone numbers are not printed.
"""
import re
import sys
from collections import OrderedDict

LINE = re.compile(r"^(?P<ts>\S+)\s+\S+\s+python\[(?P<pid>\d+)\]:\s?(?P<msg>.*)$")
PATTERNS = [
    ("start", re.compile(r"Обрабатываю строку (?P<row>\d+)")),
    ("captcha", re.compile(r"Нажаты все 6 символов")),
    ("confirm", re.compile(r"Экран подтверждения открыт")),
    ("resend", re.compile(r"нажата «отправить снова»", re.I)),
    ("confirmed", re.compile(r"SUCCESS GUARD: mobile-id подтверждение прошло")),
    ("draw", re.compile(r"Тестовая подпись нарисована")),
    ("click", re.compile(r"Нажата кнопка «Подписать договор»")),
    ("signerr", re.compile(r"Ошибка подписи: (?P<err>.{0,80})")),
    ("trace", re.compile(r"SIGN TRACE: (?P<trace>.{0,160})")),
    ("success", re.compile(r"ПОДТВЕРЖДЕНО УСПЕШНО\. Строка (?P<row>\d+)")),
    ("unverified", re.compile(r"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\. Строка (?P<row>\d+)")),
    ("timeout", re.compile(r"После 6 попыток|CONFIRM_TIMEOUT")),
    ("error", re.compile(r"registration/error")),
    ("restart", re.compile(r"Плановый перезапуск: строка завершена")),
]


def parse(stream):
    rows = OrderedDict()   # (pid, row) -> events
    current = {}           # pid -> row
    for raw in stream:
        m = LINE.match(raw.rstrip("\n"))
        if not m:
            continue
        ts, pid, msg = m.group("ts")[:19].replace("T", " "), m.group("pid"), m.group("msg")
        for name, pat in PATTERNS:
            hit = pat.search(msg)
            if not hit:
                continue
            if name == "start":
                current[pid] = hit.group("row")
                rows[(pid, hit.group("row"))] = [("start", ts, "")]
                break
            row = current.get(pid)
            if row is None:
                break
            detail = hit.groupdict().get("err") or hit.groupdict().get("trace") or ""
            rows[(pid, row)].append((name, ts, detail))
            break
    return rows


def hms(a, b):
    from datetime import datetime
    try:
        d = datetime.strptime(b, "%Y-%m-%d %H:%M:%S") - datetime.strptime(a, "%Y-%m-%d %H:%M:%S")
        return f"{int(d.total_seconds()) // 60}м{int(d.total_seconds()) % 60:02d}с"
    except Exception:
        return "?"


def main():
    rows = parse(sys.stdin)
    print(f"{'строка':>6} {'старт':19} {'подтв. за':>9} {'снова':>5} {'подпись':>8} {'клики':>5} {'итог':12} детали")
    for (pid, row), events in rows.items():
        names = [e[0] for e in events]
        if "confirm" not in names:
            continue
        start = events[0][1]
        confirm = next(e[1] for e in events if e[0] == "confirm")
        confirmed = next((e[1] for e in events if e[0] == "confirmed"), None)
        resends = names.count("resend")
        draws, clicks = names.count("draw"), names.count("click")
        errs = [e[2] for e in events if e[0] == "signerr"]
        traces = [e[2] for e in events if e[0] == "trace"]
        if "success" in names:
            outcome = "УСПЕХ"
        elif "unverified" in names:
            outcome = "НЕ ПОДТВ."
        elif "error" in names and confirmed:
            outcome = "ошибка сайта"
        elif "timeout" in names or (not confirmed and resends >= 5):
            outcome = "нет подтв."
        elif "restart" in names:
            outcome = "перезапуск"
        else:
            outcome = "?"
        sign_at = next((e[1][11:19] for e in events if e[0] == "click"), "—")
        details = []
        if confirmed and clicks:
            first_click = next(e[1] for e in events if e[0] == "click")
            details.append(f"подпись через {hms(confirmed, first_click)} после подтв.")
        if errs:
            details.append("ошибка подписи: " + errs[-1].strip())
        if traces:
            details.append("trace: " + traces[-1].strip())
        print(f"{row:>6} {start:19} {hms(confirm, confirmed) if confirmed else '—':>9} {resends:>5} {sign_at:>8} {clicks:>5} {outcome:12} " + "; ".join(details))


if __name__ == "__main__":
    main()
