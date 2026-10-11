#!/usr/bin/env python3
"""Сводка работы бота за последние часы. Только читает, ничего не меняет.

    sudo python3 /root/tess/operator_repair_1591/night_report.py        # за 14 часов
    sudo python3 /root/tess/operator_repair_1591/night_report.py 24     # за 24 часа

Показывает: ревизию и настройки, сколько строк обработано по часам, чем закончились строки
(results.jsonl), сколько успехов / оплат / неподтверждённых подписей, почему строки
пропускались, перезапуски. Номера и личные данные не печатает.
"""
import collections
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

APP = Path(os.environ.get("APP_DIR") or "/opt/beeline")
HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 14.0
SINCE = time.time() - HOURS * 3600
SINCE_TEXT = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(SINCE))


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
    last = [x for x in lines if "Результат строки" in x or "Вкладка" in x][-5:]
    if last:
        print("\n== Последние события вкладок")
        for x in last:
            print("  " + re.sub(r"\d{10,}", "N", x)[:200])


if __name__ == "__main__":
    main()
