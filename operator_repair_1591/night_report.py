#!/usr/bin/env python3
"""Сводка работы бота за последние часы. Только читает, ничего не меняет.

    sudo python3 /root/tess/operator_repair_1591/night_report.py        # за 14 часов
    sudo python3 /root/tess/operator_repair_1591/night_report.py 24     # за 24 часа

Показывает: ревизию и настройки, сколько строк обработано по часам, чем закончились строки
(results.jsonl), сколько успехов / оплат / неподтверждённых подписей, почему строки
пропускались, перезапуски. Номера и личные данные не печатает.
"""
import collections
import html as _html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

APP = Path(os.environ.get("APP_DIR") or "/opt/beeline")
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].replace(".", "").isdigit() else 14.0
SINCE = time.time() - HOURS * 3600
SINCE_TEXT = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(SINCE))


def hide(text):
    """Numbers and phones out: «+7 905 375 38 08» → N."""
    text = _html.unescape(str(text or "")).replace("\xa0", " ")
    return re.sub(r"\+?\d[\d\s()\-]{6,}\d|\d{4,}", "N", text)


def page_text(html):
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return [hide(t).strip() for t in re.sub(r"<[^>]+>", "\n", html).splitlines() if len(hide(t).strip()) > 3]


def records(name):
    out = []
    try:
        lines = (APP / name).read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if str(rec.get("time") or "") >= SINCE_TEXT:
            out.append(rec)
    return out


def journal():
    try:
        return subprocess.run(["journalctl", "-u", "beeline", "--since", f"-{int(HOURS * 60)}min", "--no-pager", "-o", "short-iso"],
                              capture_output=True, text=True, timeout=120).stdout.splitlines()
    except Exception as exc:
        print(f"journalctl недоступен: {exc}")
        return []


def main():
    src = (APP / "test_beeline.py").read_text("utf-8", errors="replace") if (APP / "test_beeline.py").exists() else ""
    revs = [int(x) for x in re.findall(r"_1591R(\d+)", src)]
    build = "exp8" if "EXPERIMENT_BROWSERS8_1591" in src else ("full" if "SIGN_ROBUST_1591R31" in src else "lite")
    print(f"== Сводка за {HOURS:g} ч (с {SINCE_TEXT[5:16]})")
    print(f"Ревизия: r{max(revs) if revs else '?'} ({build})")
    try:
        env = subprocess.run(["systemctl", "show", "beeline", "-p", "Environment", "-p", "NRestarts", "-p", "ActiveEnterTimestamp"],
                             capture_output=True, text=True, timeout=15).stdout
        for part in re.findall(r"(BEELINE_[A-Z_]+=\S*|NRestarts=\d+|ActiveEnterTimestamp=.*)", env):
            print("  " + part)
    except Exception:
        pass

    results = records("results.jsonl")
    print(f"\n== Строки с результатом: {len(results)}")
    for status, n in collections.Counter(str(r.get("status") or "?") for r in results).most_common():
        print(f"  {n:5d}  {status}")
    per_hour = collections.Counter(str(r.get("time") or "")[11:13] for r in results)
    if per_hour:
        print("  по часам: " + "  ".join(f"{h}ч:{per_hour[h]}" for h in sorted(per_hour)))

    print("\n== Итоги")
    for name, title in (("successful_sims.jsonl", "✅ успех (договор)"), ("payment_required.jsonl", "💳 дошли до оплаты"),
                        ("unverified_signatures.jsonl", "❔ подпись не подтверждена"), ("deferred_rows.jsonl", "↩️ строка отложена")):
        print(f"  {len(records(name)):5d}  {title}")

    lines = [x for x in journal() if "dbus" not in x]
    processed = sum("сохранён как обработанный" in x for x in lines)
    print(f"\n== Журнал: строк журнала {len(lines)}, номеров отмечено обработанными {processed}")
    counters = collections.Counter()
    reasons = collections.Counter()
    for x in lines:
        m = re.search(r"пропущена без повтора: (.*?)\. Worker", x)
        if m:
            reasons[re.sub(r"\d{6,}", "N", m.group(1))[:90]] += 1
        for key, title in (("пропущена после повторной registration/error", "пропущено после registration/error"),
                           ("Ожидаю подтверждение: попытка 1/6", "ждали подтверждения (начало)"),
                           ("6 попыток завершены", "6 попыток подтверждения без ответа"),
                           ("Плановый перезапуск", "плановый перезапуск"),
                           ("automation завершилась", "процесс регистрации завершился"),
                           ("Traceback", "ошибки Python (Traceback)"),
                           ("[AI", "строк от DeepSeek"),
                           ("Переход не состоялся", "переход не состоялся — повтор строки")):
            if key in x:
                counters[title] += 1
    for title, n in counters.most_common():
        print(f"  {n:5d}  {title}")
    if reasons:
        print("  Причины пропуска строк:")
        for reason, n in reasons.most_common(8):
            print(f"  {n:5d}  {reason}")
    # Python errors: the last line of each traceback, grouped (numbers hidden)
    errors = collections.Counter()
    for i, x in enumerate(lines):
        if "Traceback" not in x:
            continue
        for y in lines[i + 1:i + 60]:
            msg = y.split("]: ", 1)[-1].strip()
            if re.match(r"^[\w.]*(Error|Exception|Exit|Interrupt)\b", msg):
                errors[hide(msg)[:150]] += 1
                break
    if errors:
        print("\n== Ошибки Python (самые частые)")
        for msg, n in errors.most_common(10):
            print(f"  {n:5d}  {msg}")

    # What the site wrote on the /registration/error pages the rows were skipped on
    pages = collections.Counter()
    for case in APP.glob("diagnostics/**/blackbox/*error_final_skip*"):
        try:
            if case.stat().st_mtime < SINCE:
                continue
            html = (case / "page.html").read_text("utf-8", errors="replace")
        except OSError:
            continue
        text = page_text(html)
        found = [t for t in text if re.search(r"ошиб|пошло не так|не удал|невозмож|отказ|попробуй|недоступ|провер|не совпад|номер|лимит|уже", t, re.I)]
        key = " | ".join(found[:3]) or " | ".join(text[:3])
        pages[key[:200]] += 1
    if pages:
        print("\n== Что было на странице /registration/error")
        for key, n in pages.most_common(8):
            print(f"  {n:5d}  {key}")

    post_auth(lines)

    last = [x for x in lines if "Результат строки" in x or "Вкладка" in x][-5:]
    if last:
        print("\n== Последние события вкладок")
        for x in last:
            print("  " + x[5:16].replace("T", " ") + "  " + hide(x.split("]: ", 1)[-1])[:180])


def post_auth(lines):
    """Rows that passed the confirmation («🔒 SUCCESS GUARD») and how each ended: a success, payment or
    unverified record of the same tab after it, or lost — with the tab's last notable line."""
    stamp = lambda x: x[:19].replace("T", " ")
    finals = []
    for name, title in (("successful_sims.jsonl", "✅ успех"), ("payment_required.jsonl", "💳 оплата"),
                        ("unverified_signatures.jsonl", "❔ подпись не подтверждена")):
        for rec in records(name):
            finals.append((str(rec.get("time") or ""), str(rec.get("tab")), title))
    episodes = []  # [tab, start, end, notable lines]
    open_ep = {}
    restarts = []
    for x in lines:
        m = re.search(r"\[Вкладка (\d+)\]", x)
        if "automation завершилась" in x or "Плановый перезапуск" in x or "BROWSER RESTART" in x:
            restarts.append((stamp(x), hide(x.split("]: ", 1)[-1])[:120]))
        if not m:
            continue
        tab, msg = m.group(1), hide(x.split("]: ", 1)[-1])
        if "SUCCESS GUARD" in x:
            if tab in open_ep:
                open_ep[tab][2] = stamp(x)
            open_ep[tab] = [tab, stamp(x), None, []]
            episodes.append(open_ep[tab])
            continue
        ep = open_ep.get(tab)
        if ep is None:
            continue
        if "Экран подтверждения открыт" in x or "Открываю корзину" in x or "Новая physical-вкладка готова" in x:
            ep[2] = stamp(x)
            open_ep.pop(tab, None)
            continue
        if re.search(r"error|ошиб|не удал|закрыт|перезапуск|таймаут|timeout|пропуска|не найден|не подтвержд|подпис|договор|оплат", msg, re.I):
            ep[3].append(msg)
    if not episodes:
        print("\n== После подтверждения: ни одна строка не прошла подтверждение")
        return
    used = set()
    outcome = collections.Counter()
    lost = []
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for tab, start, end, notes in episodes:
        hit = next((f for f in finals if f not in used and f[1] == tab and start <= f[0] <= (end or now)), None)
        if hit:
            used.add(hit)
            outcome[hit[2]] += 1
            continue
        if end is None and time.time() - time.mktime(time.strptime(start, "%Y-%m-%d %H:%M:%S")) < 900:
            outcome["⏳ ещё в работе"] += 1
            continue
        cause = next((r[1] for r in restarts if start <= r[0] <= (end or now)), "")
        lost.append((start, tab, cause or (notes[-1] if notes else "вкладка взяла следующую строку без записи об итоге")))
    print(f"\n== После подтверждения клиентом: {len(episodes)} строк")
    for title, n in outcome.most_common():
        print(f"  {n:5d}  {title}")
    print(f"  {len(lost):5d}  ❌ потеряно (нет записи об итоге)")
    for start, tab, why in lost[-15:]:
        print(f"         {start[5:16]} вкладка {tab}: {why[:140]}")


def error_page(pattern="введите данные снова"):
    """The newest error page with `pattern`: its buttons, links, fields and what the tab did before."""
    cases = []
    for case in APP.glob("diagnostics/**/blackbox/*error*"):
        try:
            html = (case / "page.html").read_text("utf-8", errors="replace")
        except OSError:
            continue
        if pattern in _html.unescape(html).replace("\xa0", " ").lower():
            cases.append((case.stat().st_mtime, case, html))
    print(f"== Страниц ошибки с «{pattern}»: {len(cases)}")
    if not cases:
        return
    stats = collections.Counter()
    ages = collections.Counter()
    rows = collections.Counter()
    for _, case_i, _ in cases:
        try:
            meta_i = json.loads((case_i / "meta.json").read_text("utf-8"))
        except Exception:
            continue
        stats[f"фаза {meta_i.get('phase')}, попытка подтверждения {meta_i.get('confirm_attempt')}"] += 1
        age = float(meta_i.get("last_progress_age_seconds") or 0)
        bucket = "до 10 с" if age < 10 else "10–30 с" if age < 30 else "30–65 с" if age < 65 else "больше 65 с"
        ages[f"{meta_i.get('last_progress_label')}: {bucket}"] += 1
        rows[str(meta_i.get("row_no"))] += 1
    print("\n-- На каком шаге (все случаи)")
    for key, n in stats.most_common(10):
        print(f"  {n:5d}  {key}")
    print("-- Последний шаг бота перед ошибкой и сколько секунд назад")
    for key, n in ages.most_common(10):
        print(f"  {n:5d}  {key}")
    print(f"-- Разных строк: {len(rows)}, строк с ошибкой 2+ раз: {sum(1 for v in rows.values() if v > 1)}")
    mtime, case, html = max(cases, key=lambda c: c[0])
    try:
        meta = json.loads((case / "meta.json").read_text("utf-8"))
    except Exception:
        meta = {}
    print(f"Последняя: {time.strftime('%d.%m %H:%M:%S', time.localtime(mtime))}, вкладка {meta.get('tab')}, фаза {meta.get('phase')}")
    print("URL: " + re.sub(r"\?.*", "?…", str(meta.get("url") or "")))
    print("Заголовок: " + hide(meta.get("title")))
    print("\n-- Текст страницы")
    for line in page_text(html)[:25]:
        print("  " + line[:160])
    print("\n-- Кнопки и ссылки")
    for tag, attrs, inner in re.findall(r"(?is)<(button|a)\b([^>]*)>(.*?)</\1>", html):
        label = " ".join(page_text(inner)) or ""
        href = re.search(r'href="([^"]*)"', attrs)
        kind = re.search(r'type="([^"]*)"', attrs)
        print(f"  <{tag}> «{label[:60]}»" + (f" href={re.sub(r'[?#].*', '', href.group(1))[:80]}" if href else "")
              + (f" type={kind.group(1)}" if kind else ""))
    print("\n-- Поля")
    for attrs in re.findall(r"(?is)<(?:input|select|textarea)\b([^>]*)>", html):
        name = re.search(r'name="([^"]*)"', attrs)
        kind = re.search(r'type="([^"]*)"', attrs)
        print(f"  name={name.group(1) if name else '-'} type={kind.group(1) if kind else '-'}")
    tab, when = meta.get("tab"), str(meta.get("time") or "")
    if tab and when:
        print(f"\n-- Что делала вкладка {tab} за 4 минуты до ошибки")
        try:
            start = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.mktime(time.strptime(when, "%Y-%m-%d %H:%M:%S")) - 240))
            out = subprocess.run(["journalctl", "-u", "beeline", "--since", start, "--until", when, "--no-pager", "-o", "cat"],
                                 capture_output=True, text=True, timeout=60).stdout.splitlines()
        except Exception as exc:
            out = [f"journalctl: {exc}"]
        mine = [x for x in out if f"[Вкладка {tab}]" in x or f"TAB {tab}" in x or f"tab{tab}" in x.lower()]
        for x in mine[-40:]:
            print("  " + hide(x)[:180])


def lost_pages():
    """Error pages saved after the confirmation (the tab was past CONFIRM/RESEND): time, step, text, buttons."""
    before_auth = {"CONFIRM", "RESEND", "AUTH_WAIT", "FILL", "IDLE", "RESTART_ROW_READY", "ERROR_ASSIST", "ERROR_RECOVERY", "None", ""}
    seen = set()
    shown = 0
    for case in sorted(APP.glob("diagnostics/**/blackbox/*error*"), key=lambda c: c.stat().st_mtime):
        try:
            if case.stat().st_mtime < SINCE:
                continue
            meta = json.loads((case / "meta.json").read_text("utf-8"))
            html = (case / "page.html").read_text("utf-8", errors="replace")
        except Exception:
            continue
        if str(meta.get("phase")) in before_auth:
            continue
        key = (meta.get("tab"), str(meta.get("time"))[:16])
        if key in seen:
            continue
        seen.add(key)
        shown += 1
        print(f"\n== {str(meta.get('time'))[5:16]}  вкладка {meta.get('tab')}  шаг {meta.get('phase')}  ({case.name.split('_row')[-1].split('_', 1)[-1]})")
        print("URL: " + re.sub(r"\?.*", "?…", str(meta.get("url") or "")))
        for line in page_text(html)[:14]:
            print("  " + line[:160])
        buttons = [" ".join(page_text(inner)) for _, _, inner in re.findall(r"(?is)<(button|a)\b([^>]*)>(.*?)</\1>", html)]
        buttons = [b for b in buttons if b]
        if buttons:
            print("  Кнопки: " + " | ".join(dict.fromkeys(buttons))[:200])
    if not shown:
        print("Страниц ошибки после подтверждения за это время нет.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "lost":
        HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 24.0
        SINCE = time.time() - HOURS * 3600
        lost_pages()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "page":
        HOURS = 0
        error_page(" ".join(sys.argv[2:]) or "введите данные снова")
    else:
        main()
