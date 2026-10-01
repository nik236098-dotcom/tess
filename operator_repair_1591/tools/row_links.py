#!/usr/bin/env python3
"""The order link (hash_order) that really belongs to each row, rebuilt from the beeline journal.

    sudo journalctl -u beeline --no-pager -o short-iso --since "-2 days" | python3 row_links.py
    sudo journalctl -u beeline --no-pager -o short-iso --since "-2 days" | python3 row_links.py --all
    ... | python3 row_links.py 538 541          # only these rows

Before revision 36 the Telegram push carried the link of the tab's FIRST row for every later
row. The journal has the truth: each row starts with «Обрабатываю строку N» in its worker
process (python[pid]) and every «продолжить» logs «eSIM offer сохранён: … hash_order=…».
The last capture before the row's outcome is the order that was signed. By default only
rows that were signed (payment step or success) are listed; --all lists every row.
Phone numbers are shown by their last four digits only.
"""
import re
import sys
from collections import OrderedDict

LINE = re.compile(r"^(?P<ts>\S+)\s+\S+\s+python\[(?P<pid>\d+)\]:\s?(?P<msg>.*)$")
START = re.compile(r"\[Вкладка (?P<tab>\d+)\] Обрабатываю строку (?P<row>\d+), номер заканчивается на (?P<tail>\d+)")
OFFER = re.compile(r"eSIM offer сохранён: номер=(?P<num>\S+) \| (?P<url>\S+hash_order=[0-9a-f]+)")
OUTCOMES = [
    ("оплата", re.compile(r"ТРЕБУЕТСЯ ОПЛАТА\. Строка (?P<row>\d+)")),
    ("не подтверждена", re.compile(r"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\. Строка (?P<row>\d+)")),
    ("результат", re.compile(r"Результат строки (?P<row>\d+): (?P<status>\S+)")),
]
SIGNED = re.compile(r"Нажата кнопка «Подписать договор»")


def main(argv):
    only = {a for a in argv[1:] if a.isdigit()}
    show_all = "--all" in argv
    rows = OrderedDict()          # (pid, row) -> info
    current = {}                  # pid -> (pid, row)
    for line in sys.stdin:
        m = LINE.match(line.rstrip("\n"))
        if not m:
            continue
        ts, pid, msg = m.group("ts")[:19].replace("T", " "), m.group("pid"), m.group("msg")
        s = START.search(msg)
        if s:
            key = (pid, s.group("row"))
            rows[key] = {"row": s.group("row"), "tab": s.group("tab"), "tail": s.group("tail"), "start": ts,
                         "offers": [], "signed": False, "outcome": "", "end": ""}
            current[pid] = key
            continue
        key = current.get(pid)
        if key is None:
            continue
        info = rows[key]
        o = OFFER.search(msg)
        if o:
            info["offers"].append((ts, o.group("num"), o.group("url")))
            continue
        if SIGNED.search(msg):
            info["signed"] = True
            continue
        for name, pat in OUTCOMES:
            r = pat.search(msg)
            if r and r.group("row") == info["row"]:
                info["outcome"] = name if name != "результат" else r.group("status")
                info["end"] = ts
                break
    shown = 0
    for info in rows.values():
        if only and info["row"] not in only:
            continue
        interesting = info["signed"] or info["outcome"] in ("оплата", "SUCCESS")
        if not show_all and not interesting:
            continue
        shown += 1
        last = info["offers"][-1] if info["offers"] else None
        print(f"строка {info['row']:>5}  вкладка {info['tab']:>2}  …{info['tail']}  {info['start'][5:16]}  "
              f"исход: {info['outcome'] or ('подписана' if info['signed'] else '—'):<16} захватов: {len(info['offers'])}")
        if last:
            tail = re.sub(r"\D", "", last[1])[-4:]
            print(f"    ссылка: {last[2]}   (eSIM …{tail}, захват {last[0][11:19]})")
            if len(info["offers"]) > 1:
                print(f"    ранние заказы той же строки (без данных): " + ", ".join(x[2].rsplit('=', 1)[1][:8] + "…" for x in info["offers"][:-1]))
        else:
            print("    ссылка: в журнале не найдена")
    if not shown:
        print("Подходящих строк в этом отрезке журнала нет (попробуйте --since раньше или --all).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
