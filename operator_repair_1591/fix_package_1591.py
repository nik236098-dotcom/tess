#!/usr/bin/env python3
"""Revision 2 of the beeline_integrated_io_15_91 package. Run on the EXTRACTED package.

    python3 fix_package_1591.py /path/to/extracted/package

Changes made in place (idempotent, refuses any other package):
1. test_beeline.py: the separate SUCCESS push is no longer cut to 4000 characters.
   It goes through the durable outbox (split into confirmed parts by the 15.91 sender);
   if the queue is unavailable it is sent directly, split, never truncated.
2. test_update.py: the preserved-handler hashes no longer depend on ast.dump(), whose
   text changed in Python 3.13; the installer's preflight failed on Python <= 3.12.
3. install.py: the reviewed package copies are installed after the input checksum
   matches, instead of re-applying edits.json line ranges.
4. test_beeline.py: the proxy login is removed from the code (TELEGRAM_DEFAULT_PROXY = "");
   the runtime already reads telegram_config.json "proxy" first. install.py refuses to
   run until that key exists, so Telegram traffic never silently loses the proxy.
5. test_beeline.py: autonomous SUCCESS/ERROR assist requests get a budget per page
   state (two per unchanged URL, then one per 30 minutes, none while the previous one
   is unanswered) instead of a full agent run and an identical report every 45 seconds.
6. test_beeline.py: registration/error policy. After the analysis report the runtime
   closes the error page, opens a fresh one and retries the row once; a second error on
   the same row skips it (logged, Telegram notice). A worker is never stopped by an error.
   The rule is also written into the DeepSeek system instructions and the task text.
7. test_beeline.py: a portal modal over the basket is dismissed (close button, Escape,
   pointer-events as a last resort) before the tariff buttons and the eSIM radio; the eSIM
   click falls back to force=True and a JS click; CDP page close gets 20 s and one retry.
8. test_beeline.py: the tariff card is found by its title (TARIFF_NAME) and «выбрать» is
   clicked inside it; the old "second button" rule picked the paid tariff after the site
   reordered the cards. The overlay dismisser leaves the dialog we need untouched.
9. test_beeline.py: the parent watchdog counts real page activity as ROW_START progress,
   long registration steps refresh the heartbeat, and the «изменить» retry happens in
   place before any basket reload.
10. test_beeline.py: the parent watchdog samples the CPU time of the worker process (and
   its child solver) from /proc while the protected matcher runs; a matcher still computing
   between stage reports is alive, a blocked or hung one burns no CPU and is caught by the
   unchanged 75 s rule. local_matcher.py is not touched.
11. manifest.json, edits.json, SHA256SUMS.txt, verification.json, test_results.txt are
   regenerated so every checksum the installer verifies is consistent again.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import re

MARKER = "SUCCESS_PUSH_DURABLE_1591R2"
PROXY_MARKER = "PROXY_FROM_CONFIG_1591R3"
EXPECTED_INPUT_OUTPUT_SHA = "9e216a70bb1e931c2e9568687c26564a0132bccd6b748dd42fef4eff9335fa50"
# test_beeline.py of the first build and of revision 2 are both accepted as input.
ACCEPTED_PACKAGE_SHAS = {EXPECTED_INPUT_OUTPUT_SHA,
                         "8f5fc960fc6cc44faebc19eae0709057f3c8c627d623d9219a0c85cff81d3012",
                         "437155a246d1e370a68cc29ec54850944837f0a575600c57c9f30b9849ebdf73",
                         "b835682314ab8958af4500f7176ca660608f14f09bb7bd02827eb503a23597b0",
                         "31cbd8b287f7c1deea89a669fabdcd14fab0bfee631b7ce87c5531493a05265a",
                         "14ada30d264a994bdb675655b495c662217298a6b0327e6ea98dce99e4675433",
                         "ec65b2fa802131dbd7f2e679f422c40ddae10cc842bff784869925e14b16c105",
                         "6023e5266b8317cd0051fbec7988d0f65e30c10f26fc95309d960ebf995997c9",
                         "6852517bf0eadb15f70359ac93b9c49632926cb3aef9f817c712ea099330248b"}

# Revision 5: registration/error policy. After the detailed analysis and its report the
# runtime closes the error page, opens a fresh one and retries the row once; a second
# error on the same row skips it. A worker slot is never stopped because of an error.
ERROR_MARKER = "ERROR_RECOVERY_1591R5"

# Revision 6: a portal modal (role="dialog" aria-modal="true", "подбор номера") started to
# cover the basket page. Playwright clicks on the eSIM radio and the tariff buttons were
# intercepted, every attempt failed and the row looped through same-row restarts forever.
OVERLAY_MARKER = "OVERLAY_DISMISS_1591R6"

# Revision 7: the tariff card was chosen by position (second «выбрать»); the site reordered
# the cards. The card is now found by its title. The overlay dismisser leaves a dialog alone
# when it contains what is about to be clicked (the tariff picker is itself a modal).
TARIFF_MARKER = "TARIFF_BY_NAME_1591R7"

# Revision 8: the parent watchdog judged ROW_START by the last phase publish only, so a
# row busy with real page loading for 120 s was "stalled" and recovered mid-action; the
# «изменить» retry reloaded the basket (losing its state) before trying again in place.
ROWSTART_MARKER = "ROW_START_ACTIVITY_1591R8"
ROW_PROGRESS_HELPER_R8 = '''# ROW_START_ACTIVITY_1591R8
def _row_progress(page, note):
    """Refresh the worker heartbeat from inside a long registration step."""
    publisher = getattr(page, "_publish_worker_phase", None)
    if publisher is None:
        return
    try:
        publisher("ROW_START", note)
    except Exception:
        pass


'''
OLD_WATCHDOG_ROW_START = '''        if phase == "ROW_START":
            if logical_age >= ROW_START_STALL_SECONDS:
                stalled.append((tab_id, proc, info, logical_age))
            continue
'''
NEW_WATCHDOG_ROW_START = '''        if phase == "ROW_START":
            # ROW_START_ACTIVITY_1591R8: real page activity (requests, navigation) is
            # progress too; only a row that is silent on BOTH clocks is stalled.
            activity_age = now - float(info.get("activity_time") or info.get("time") or now)
            if min(logical_age, activity_age) >= ROW_START_STALL_SECONDS:
                stalled.append((tab_id, proc, info, min(logical_age, activity_age)))
            continue
'''
OLD_TARIFF_OPEN = '''        print("Открываю выбор тарифа...")
'''
NEW_TARIFF_OPEN = '''        _row_progress(page, "открываю выбор тарифа")  # ROW_START_ACTIVITY_1591R8
        print("Открываю выбор тарифа...")
'''
OLD_TARIFF_RETRY = '''        except (PlaywrightTimeoutError, AssertionError):
            diagnostic.snapshot("tariff_change_button_not_ready")
            print("Кнопка «изменить» не найдена с первой попытки. Обновляю только эту вкладку...", flush=True)
            page.reload(wait_until="domcontentloaded", timeout=60000)
            click_tariff_change()
'''
NEW_TARIFF_RETRY = '''        except (PlaywrightTimeoutError, AssertionError):
            diagnostic.snapshot("tariff_change_button_not_ready")
            # ROW_START_ACTIVITY_1591R8: a reload resets the basket; retry in place first.
            print("Кнопка «изменить» не нажалась с первой попытки. Повторяю без перезагрузки...", flush=True)
            _row_progress(page, "повтор «изменить» без перезагрузки")
            page.wait_for_timeout(3000)
            try:
                click_tariff_change()
            except (PlaywrightTimeoutError, AssertionError):
                print("Кнопка «изменить» не нажалась повторно. Обновляю только эту вкладку...", flush=True)
                page.reload(wait_until="domcontentloaded", timeout=60000)
                click_tariff_change()
'''
OLD_CHOOSE_PRINT = '''        print("Нажимаю вторую кнопку «выбрать», как в записи...")
'''
NEW_CHOOSE_PRINT = '''        _row_progress(page, "нажимаю «выбрать» в карточке тарифа")  # ROW_START_ACTIVITY_1591R8
        print("Нажимаю «выбрать» в карточке тарифа...")
'''
OLD_ESIM_CALL = '''        select_esim(page)
        field = page.get_by_placeholder("+7 999 999 99")
'''
NEW_ESIM_CALL = '''        _row_progress(page, "выбор eSIM")  # ROW_START_ACTIVITY_1591R8
        select_esim(page)
        field = page.get_by_placeholder("+7 999 999 99")
'''
README_NOTE_R8 = '''

РЕВИЗИЯ 8 (fix_package_1591.py)
Watchdog и ROW_START. Родительский watchdog считал «нет прогресса» только по времени
последней публикации фазы, поэтому строка, которая 120 секунд реально грузила страницы
корзины и тарифа, признавалась зависшей и «восстанавливалась» посреди работы. Теперь
учитывается и реальная активность страницы (запросы, навигация), а длинные шаги
(открытие выбора тарифа, «выбрать», eSIM) сами обновляют heartbeat. Повтор клика по
«изменить» сначала выполняется на месте, без reload корзины; reload остаётся крайним
средством. Маркер: ROW_START_ACTIVITY_1591R8. Изменены parent_watchdog и run_registration.
'''

# Revision 9: the protected matcher reports progress only at stage boundaries, so a solving
# step longer than 75 s looked like a stall and the protected page was closed mid-check.
# The limit stays; the parent now samples the worker's CPU time (plus children) from /proc:
# growing CPU = computing = alive, flat CPU = blocked/hung = silent, the 75 s rule applies.
MATCHER_MARKER = "MATCHER_HEARTBEAT_1591R9"
MATCHER_HELPER_R9 = '''# MATCHER_HEARTBEAT_1591R9
MATCHER_CPU_MIN_RATIO = 0.05  # share of one CPU below which the matcher is not computing
_MATCHER_CPU_STATE = {}


def _process_tree_cpu_seconds(pid):
    \"\"\"CPU time of a process plus its live children (a native solver may be a child).\"\"\"
    try:
        ticks = os.sysconf("SC_CLK_TCK")
    except (AttributeError, ValueError, OSError):
        ticks = 100
    total = 0.0
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "r") as f:
                fields = f.read().rsplit(")", 1)[1].split()
            if int(entry) == int(pid) or int(fields[1]) == int(pid):
                total += (int(fields[11]) + int(fields[12])) / ticks
        except (OSError, IndexError, ValueError):
            continue
    return total


def _matcher_cpu_age(proc, now):
    \"\"\"Seconds since the worker process (or its child solver) was last seen computing.

    Sampled by the parent between watchdog runs. A matcher busy with SHAPE/MATCH work
    keeps this near zero without any stage report; a matcher blocked on the page, a lock
    or the network burns no CPU, so this grows and the 75-second rule applies as before.
    \"\"\"
    pid = getattr(proc, "pid", None)
    if not pid:
        return float("inf")
    cpu = _process_tree_cpu_seconds(pid)
    if cpu is None:
        return float("inf")
    state = _MATCHER_CPU_STATE.get(pid)
    if state is None:
        _MATCHER_CPU_STATE[pid] = {"cpu": cpu, "time": now, "progress_at": now}
        return 0.0
    wall = now - state["time"]
    if wall > 0 and (cpu - state["cpu"]) / wall >= MATCHER_CPU_MIN_RATIO:
        state["progress_at"] = now
    state["cpu"], state["time"] = cpu, now
    return now - state["progress_at"]


'''
OLD_WATCHDOG_MATCHER = '''            if matcher_age >= PROTECTED_MATCHER_STALL_SECONDS:
                stalled.append((tab_id, proc, info, matcher_age))
            continue
'''
NEW_WATCHDOG_MATCHER = '''            # MATCHER_HEARTBEAT_1591R9: a matcher still computing (the worker process or
            # its child solver keeps consuming CPU) is alive between stage reports; a
            # blocked or hung matcher burns no CPU and is caught by the same 75 s rule.
            matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))
            if matcher_age >= PROTECTED_MATCHER_STALL_SECONDS:
                stalled.append((tab_id, proc, info, matcher_age))
            continue
'''
OLD_HEALTH_MATCHER = '''            matcher_age = now - float(
                (info or {}).get("matcher_time")
                or (info or {}).get("time")
                or now
            )
            return phase, logical_age, matcher_age, bool(proc and proc.is_alive())
'''
NEW_HEALTH_MATCHER = '''            matcher_age = now - float(
                (info or {}).get("matcher_time")
                or (info or {}).get("time")
                or now
            )
            if phase == "PROTECTED_CHECK" and proc is not None:
                matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))  # MATCHER_HEARTBEAT_1591R9
            return phase, logical_age, matcher_age, bool(proc and proc.is_alive())
'''
README_NOTE_R9 = '''

РЕВИЗИЯ 9 (fix_package_1591.py)
Heartbeat матчера. Матчер сообщает о прогрессе только на границах этапов (CAPTURE, SPLIT,
MATCH, SUBMIT, SHAPE_NATIVE…), поэтому этап дольше 75 секунд выглядел как зависание, и
защищённая вкладка закрывалась посреди проверки. Лимит 75 секунд не менялся: исправлен
сигнал. Родительский watchdog читает из /proc процессорное время процесса worker (и его
дочернего решателя, если есть): пока оно растёт, матчер считает, и «возраст» матчера
обнуляется; заблокированный или зависший матчер CPU не расходует, поэтому замолкает и
ловится правилом 75 секунд как раньше. Замер идёт в родительском процессе, GIL worker'а
ему не мешает. То же правило применено к проверке «unhealthy» для действий DeepSeek.
Маркер: MATCHER_HEARTBEAT_1591R9. Изменены parent_watchdog и _host_worker_health (в main);
local_matcher.py не трогается.
'''

# Revision 10: the matcher computes the same scores faster. symbol_matching.py 14.0 from the
# server is replaced by 14.1 (matcher_r10/symbol_matching.py): identical thresholds, descriptors,
# rotation steps and assignment logic; shape_costs compares one rotated candidate with all
# references through matrix products, thin() looks the Zhang-Suen decision up in a table over
# the mask's bounding box, each mask is thinned once, the NATIVE and CLEAN passes share one
# rotation sweep, identical threshold masks reuse regions(). local_matcher.py is untouched.
MATCHER_SPEED_MARKER = "MATCHER_SPEED_1591R10"
SYMBOL_MATCHING_SOURCE = Path(__file__).resolve().parent / "matcher_r10" / "symbol_matching.py"
SYMBOL_MATCHING_REFERENCE = Path(__file__).resolve().parent / "matcher_r10" / "symbol_matching_14_0_reference.py"
# sha256 of the server's symbol_matching.py (MATCHER_VERSION 14.0), the only accepted input.
SYMBOL_MATCHING_INPUT_SHA = "915368d66804f64d4d7d7de42d2e474f1ea29ffe5b14c352b67d054ee40c8c35"
OLD_INSTALL_FILES = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py')\n"
NEW_INSTALL_FILES = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py')\n"
OLD_INSTALL_LOOP = "    for name in ('test_beeline.py', 'server_controller.py'):\n        path = app/name\n"
NEW_INSTALL_LOOP = "    for name in ('test_beeline.py', 'server_controller.py', 'symbol_matching.py'):\n        path = app/name\n"
OLD_INSTALL_IMPORT = "'import test_beeline as a; import server_controller as c; '\n"
NEW_INSTALL_IMPORT = "'import test_beeline as a; import server_controller as c; import symbol_matching as s; '\n"
OLD_INSTALL_ASSERT = "'assert a._io1591.VERSION == \"15.91-io\"; print(\"IMPORT OK\")'"
NEW_INSTALL_ASSERT = "'assert a._io1591.VERSION == \"15.91-io\"; assert s.MATCHER_VERSION == \"14.1\"; print(\"IMPORT OK\")'"
OLD_TEST_FIXTURE = ("        self.old={'test_beeline.py':b'old app','server_controller.py':b'old controller'}\n"
                    "        self.new=dict(self.old,**{'test_beeline.py':b'new app','server_controller.py':b'new controller',"
                    "'operator_runtime_io.py':b'helper'})\n")
NEW_TEST_FIXTURE = ("        self.old={'test_beeline.py':b'old app','server_controller.py':b'old controller',"
                    "'symbol_matching.py':b'old matcher'}\n"
                    "        self.new=dict(self.old,**{'test_beeline.py':b'new app','server_controller.py':b'new controller',"
                    "'operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher'})\n")
OLD_TEST_COMPILE_LIST = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py'):"
NEW_TEST_COMPILE_LIST = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py'):"
# Revision 11: the DeepSeek lanes hang in page.evaluate (no timeout in Playwright) when a
# worker tab stops answering; the lane stays in busy_browser and the supervisor never restarts
# it, so Telegram goes silent until the service is restarted. The page collector now runs in
# its own thread with a deadline; on overrun the lane process exits and the parent respawns
# it (releasing its inbox claims). The supervisor also restarts a lane stuck in busy_* beyond
# a hard ceiling.
OBSERVER_MARKER = "OBSERVER_TIMEOUT_1591R11"
OLD_COLLECT_DEF = ('def _observer_collect_pages(cdp_urls, with_screenshots=True):\n'
                   '    """Connects read-only to both Chromium instances and snapshots worker pages."""\n')
NEW_COLLECT_DEF = ('def _observer_collect_pages_unbounded(cdp_urls, with_screenshots=True):\n'
                   '    """Connects read-only to both Chromium instances and snapshots worker pages.\n'
                   '\n'
                   '    Unbounded: call _observer_collect_pages, which adds the deadline.\n'
                   '    """\n')
OBSERVER_HELPER_R11 = '''# OBSERVER_TIMEOUT_1591R11
OBSERVER_COLLECT_TIMEOUT_SECONDS = 45
AI_LANE_BUSY_CEILING_SECONDS = 900


def _observer_collect_pages(cdp_urls, with_screenshots=True, timeout=None):
    """Bounded page collection for the DeepSeek lanes.

    page.evaluate has no timeout in Playwright: on a page that stopped answering (a tab
    being replaced, a hung renderer) it never returns, the lane stays in busy_browser and
    the supervisor leaves it alone. The unbounded collector therefore runs in its own
    thread with its own Playwright instance; if it exceeds the deadline the lane process
    exits and the parent respawns it, releasing its inbox claims.
    """
    import threading
    limit = float(OBSERVER_COLLECT_TIMEOUT_SECONDS if timeout is None else timeout)
    outcome = {}

    def run():
        try:
            outcome["pages"] = _observer_collect_pages_unbounded(cdp_urls, with_screenshots=with_screenshots)
        except BaseException as exc:  # re-raised in the caller
            outcome["error"] = exc

    worker = threading.Thread(target=run, name="observer-collect-1591", daemon=True)
    worker.start()
    worker.join(limit)
    if worker.is_alive():
        print(
            f"[AI] Сбор страниц не завершился за {limit:.0f} с (evaluate завис на неотвечающей "
            "вкладке) — процесс наблюдателя завершается, родитель перезапустит его.",
            flush=True,
        )
        os._exit(3)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("pages", [])


'''
OLD_LANE_STALE = '''            stale = (
                not state.startswith("busy_")
                and (now - last) > idle_limit
            )
'''
NEW_LANE_STALE = '''            # OBSERVER_TIMEOUT_1591R11: a lane stuck in busy_* beyond the hard ceiling is
            # restarted as well; a hung evaluate never comes back on its own.
            stale = (
                (not state.startswith("busy_") and (now - last) > idle_limit)
                or (state.startswith("busy_") and (now - last) > AI_LANE_BUSY_CEILING_SECONDS)
            )
'''
README_NOTE_R11 = '''

РЕВИЗИЯ 11 (fix_package_1591.py)
Молчание DeepSeek до перезапуска. Линии FAST и DEV каждые 5 секунд собирают список
worker-страниц через CDP и ставят на них телеметрию вызовом page.evaluate. У этого вызова в
Playwright нет таймаута: если вкладка перестала отвечать (например, закрывается при
восстановлении), вызов не возвращается никогда, линия остаётся в состоянии busy_browser, а
супервизор такие линии не перезапускает. Сообщения копятся в очереди без claim до перезапуска
службы, после которого разбираются все разом. Теперь сбор страниц идёт в отдельном потоке с
дедлайном 45 секунд; при превышении процесс линии завершается, родитель перезапускает его и
возвращает его сообщения в очередь. Супервизор дополнительно перезапускает линию, которая
дольше 15 минут находится в любом состоянии busy_* (агент разработчика обновляет состояние на
каждом раунде, поэтому легитимная работа под потолок не попадает).
Маркер: OBSERVER_TIMEOUT_1591R11. Изменены _observer_collect_pages и _ensure_ai_lane_alive (в main).
'''
README_NOTE_R10 = '''

РЕВИЗИЯ 10 (fix_package_1591.py)
Скорость матчера. На сервере с ослабленным CPU одна капча занимала около 4 минут: четыре
прохода shape_costs по ~50 секунд. В пакет добавлен symbol_matching.py версии 14.1 —
тот же алгоритм 14.0 (пороги, дескрипторы, 36 поворотов, выбор пар не менялись), но:
shape_costs сравнивает повёрнутого кандидата со всеми образцами матричным произведением,
а не циклом по образцам и пикселям; thin() берёт решение Чжана-Суэня из таблицы 256
окрестностей и работает в рамке маски; каждая маска утончается один раз (native и affine
дескрипторы делят скелет); проходы NATIVE и CLEAN сравнивают одних и тех же кандидатов,
поэтому делят один обход поворотов; одинаковые маски порогов не пересчитывают regions().
Скелеты и области совпадают побитно, стоимости — с точностью float32 (~1e-6), выбранные
пары те же. install.py принимает только серверный symbol_matching.py 14.0 (sha256
915368d6…) или уже установленный 14.1; иначе останавливается, ничего не меняя.
Маркер: MATCHER_SPEED_1591R10. local_matcher.py не трогается.
'''
OVERLAY_HELPER_R7 = r'''# OVERLAY_DISMISS_1591R6 / TARIFF_BY_NAME_1591R7
_MODAL_DIALOG_SELECTOR = '[role="dialog"][aria-modal="true"]'
_CHOOSE_BUTTON_RE = re.compile(r"^\s*выбрать\s*$", re.I)


def _blocking_dialog_indexes(page, keep_text=None, keep_selector=None):
    """Indexes of visible modal dialogs that do NOT contain what we are about to click."""
    return list(page.evaluate("""([keepText, keepSelector]) => {
        const out = [];
        [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].forEach((el, i) => {
            const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            if (!(r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden')) return;
            if (keepSelector && el.querySelector(keepSelector)) return;
            if (keepText && (el.innerText || '').includes(keepText)) return;
            out.push(i);
        });
        return out;
    }""", [keep_text or "", keep_selector or ""]) or [])


def _visible_modal_dialogs(page):
    return len(_blocking_dialog_indexes(page))


def dismiss_blocking_overlays(page, attempts=3, keep_text=None, keep_selector=None):
    """Close a portal modal that intercepts clicks; never the dialog we need.

    Order: a visible close button inside the dialog, then Escape; as a last resort the
    dialog stops intercepting pointer events. The DOM is never removed, the basket is kept.
    A dialog containing keep_text or an element matching keep_selector is left untouched.
    Returns True when no blocking dialog is visible afterwards.
    """
    for _ in range(attempts):
        try:
            blocking = _blocking_dialog_indexes(page, keep_text, keep_selector)
        except Exception:
            return True
        if not blocking:
            return True
        closed = False
        dialog = page.locator(_MODAL_DIALOG_SELECTOR).nth(blocking[-1])
        for close_button in (
            dialog.get_by_role("button", name=re.compile(r"закрыть|close|✕|×", re.I)),
            dialog.locator('button[aria-label*="акрыть" i], button[aria-label*="close" i], [data-testid*="close" i]'),
        ):
            try:
                if close_button.count() > 0:
                    close_button.first.click(timeout=1500, no_wait_after=True)
                    closed = True
                    break
            except Exception:
                pass
        if not closed and not keep_text and not keep_selector:
            # Escape would close the protected dialog too; use it only when nothing is protected.
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass
    try:
        blocking = _blocking_dialog_indexes(page, keep_text, keep_selector)
        if not blocking:
            return True
        page.evaluate("""(indexes) => {
            const all = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
            indexes.forEach(i => { if (all[i]) all[i].style.pointerEvents = 'none'; });
        }""", blocking)
        print("Модальное окно не закрылось; снял перехват кликов, DOM не трогал.", flush=True)
    except Exception:
        pass
    return False


def _tariff_choose_button(page, diagnostic=None, timeout=10000):
    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed."""
    title = page.get_by_text(TARIFF_NAME, exact=True).first
    try:
        title.wait_for(state="visible", timeout=timeout)
        card = title.locator(
            "xpath=ancestor::*[.//button[normalize-space(.)='выбрать' or normalize-space(.)='Выбрать']][1]"
        )
        button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)
        if button.count() > 0:
            return button.first
    except Exception:
        pass
    try:
        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]
        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()
    except Exception:
        titles, choose_count = [], -1
    if diagnostic is not None:
        try:
            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)
        except Exception:
            pass
    print(
        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "
        f"кнопок «выбрать»: {choose_count}",
        flush=True,
    )
    raise RuntimeError(
        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."
    )


'''
OLD_CHOOSE_LOOP_R6 = '''        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            choose_button = page.get_by_role(
                "button", name="выбрать", exact=True
            ).nth(1)
'''
NEW_CHOOSE_LOOP_R7 = '''        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page, keep_text=TARIFF_NAME)  # OVERLAY_DISMISS_1591R6
            choose_button = _tariff_choose_button(page, diagnostic)  # TARIFF_BY_NAME_1591R7
'''
OLD_ESIM_DISMISS_R6 = '''        dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
'''
NEW_ESIM_DISMISS_R7 = '''        dismiss_blocking_overlays(page, keep_selector='input#esim[name="sim"]')  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
'''
README_NOTE_R7 = '''

РЕВИЗИЯ 7 (fix_package_1591.py)
Выбор тарифа по названию. Раньше нажималась ВТОРАЯ кнопка «выбрать» на экране «выберите
тариф»; сайт поменял порядок карточек, и вторая кнопка стала принадлежать платной
«подписка bee HIT», а bee START оказалась первой. Теперь ищется карточка с текстом
TARIFF_NAME («подписка bee START») и нажимается кнопка «выбрать» внутри неё; при
неудаче в лог пишутся реальные названия карточек и число кнопок. Закрыватель модальных
окон из ревизии 6 больше не трогает диалог, в котором находится нужный элемент
(экран выбора тарифа сам является диалогом с крестиком); Escape не нажимается, когда
есть защищаемый диалог. Маркер: TARIFF_BY_NAME_1591R7.
'''
OVERLAY_HELPER_R6 = r'''# OVERLAY_DISMISS_1591R6
_MODAL_DIALOG_SELECTOR = '[role="dialog"][aria-modal="true"]'


def _visible_modal_dialogs(page):
    return int(page.evaluate("""() => [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')]
        .filter(el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; }).length""") or 0)


def dismiss_blocking_overlays(page, attempts=3):
    """Close a portal modal that intercepts clicks on the basket page.

    Order: a visible close button inside the dialog, then Escape; as a last resort the
    dialog stops intercepting pointer events. The DOM is never removed, the basket is kept.
    Returns True when no modal dialog is visible afterwards.
    """
    for _ in range(attempts):
        try:
            if not _visible_modal_dialogs(page):
                return True
        except Exception:
            return True
        closed = False
        dialog = page.locator(_MODAL_DIALOG_SELECTOR).last
        for close_button in (
            dialog.get_by_role("button", name=re.compile(r"закрыть|close|✕|×", re.I)),
            dialog.locator('button[aria-label*="акрыть" i], button[aria-label*="close" i], [data-testid*="close" i]'),
        ):
            try:
                if close_button.count() > 0:
                    close_button.first.click(timeout=1500, no_wait_after=True)
                    closed = True
                    break
            except Exception:
                pass
        if not closed:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass
    try:
        if not _visible_modal_dialogs(page):
            return True
        page.evaluate("""() => document.querySelectorAll('[role="dialog"][aria-modal="true"]')
            .forEach(el => { el.style.pointerEvents = 'none'; })""")
        print("Модальное окно не закрылось; снял перехват кликов, DOM не трогал.", flush=True)
    except Exception:
        pass
    return False


'''
OLD_SELECT_ESIM_ATTEMPT = '''        print(f"Выбор eSIM: попытка {attempt}/3...", flush=True)
        radio = page.locator('input#esim[name="sim"]')
        try:
            radio.wait_for(state="visible", timeout=10000)
            expect(radio).to_be_enabled(timeout=10000)
            # При повторном рендере locator находит актуальный input.
            if not esim_state(page)["selected"]:
                radio.click(timeout=5000)
        except PlaywrightTimeoutError:
            print("Нажатие не подтверждено; проверяю состояние переключателя.")
'''
NEW_SELECT_ESIM_ATTEMPT = '''        print(f"Выбор eSIM: попытка {attempt}/3...", flush=True)
        dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
        radio = page.locator('input#esim[name="sim"]')
        try:
            radio.wait_for(state="visible", timeout=10000)
            expect(radio).to_be_enabled(timeout=10000)
            # При повторном рендере locator находит актуальный input.
            if not esim_state(page)["selected"]:
                radio.click(timeout=5000)
        except PlaywrightTimeoutError:
            print("Нажатие не подтверждено; проверяю состояние переключателя.")
        if not esim_state(page)["selected"]:
            # The pointer may still be intercepted by a portal layer: click through it.
            try:
                radio.click(timeout=3000, force=True, no_wait_after=True)
            except Exception:
                pass
        if not esim_state(page)["selected"]:
            try:
                page.evaluate("""() => {
                    const el = document.querySelector('input#esim[name="sim"]');
                    if (!el) return;
                    const label = el.closest('label');
                    if (label) label.click(); else el.click();
                    if (!el.checked) {
                        el.checked = true;
                        for (const t of ['input', 'change']) el.dispatchEvent(new Event(t, {bubbles: true}));
                    }
                }""")
            except Exception:
                pass
'''
OLD_TARIFF_CLICK = '''            last_error = None
            for candidate in candidates:
                try:
                    expect(candidate.first).to_be_visible(timeout=20000)
                    candidate.first.click(timeout=15000, no_wait_after=True)
                    return
                except (PlaywrightTimeoutError, AssertionError) as exc:
                    last_error = exc
'''
NEW_TARIFF_CLICK = '''            last_error = None
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            for candidate in candidates:
                try:
                    expect(candidate.first).to_be_visible(timeout=20000)
                    try:
                        candidate.first.click(timeout=15000, no_wait_after=True)
                    except PlaywrightTimeoutError:
                        # The button is ready; a portal modal intercepts the pointer.
                        dismiss_blocking_overlays(page)
                        candidate.first.click(timeout=15000, no_wait_after=True, force=True)
                    return
                except (PlaywrightTimeoutError, AssertionError) as exc:
                    last_error = exc
'''
OLD_CHOOSE_LOOP = '''        for choose_attempt in range(1, 4):
            choose_button = page.get_by_role(
                "button", name="выбрать", exact=True
            ).nth(1)
'''
NEW_CHOOSE_LOOP = '''        for choose_attempt in range(1, 4):
            dismiss_blocking_overlays(page)  # OVERLAY_DISMISS_1591R6
            choose_button = page.get_by_role(
                "button", name="выбрать", exact=True
            ).nth(1)
'''
OLD_CDP_DEF = "def _close_cdp_page_for_worker(cdp_url, info, timeout=8):\n"
CDP_HEAD_R6 = '''def _close_cdp_page_for_worker(cdp_url, info, timeout=20, attempts=2):
    """OVERLAY_DISMISS_1591R6: a Chromium busy with orphan pages needs more than 8 s;
    one real close attempt is retried once. Refusals (guard, no window_name) are final.
    The caller already refuses to create a replacement while the old page is open."""
'''
CDP_TAIL_R6 = '''
    if _io1591.guarded(info or {}) or not str((info or {}).get("window_name") or "").strip():
        return _once(cdp_url, info, timeout=timeout)
    import time as _time
    for attempt in range(1, attempts + 1):
        try:
            if _once(cdp_url, info, timeout=timeout):
                return True
        except Exception:
            pass
        if attempt < attempts:
            _time.sleep(2)
    return False
'''
README_NOTE_R6 = '''

РЕВИЗИЯ 6 (fix_package_1591.py)
Портальное модальное окно (role="dialog" aria-modal="true", «подбор номера») стало
перекрывать корзину: клики Playwright по eSIM и кнопкам тарифа перехватывались, и
строка бесконечно уходила в same-row restart. Добавлен dismiss_blocking_overlays():
кнопка закрытия внутри диалога, затем Escape, в крайнем случае снятие перехвата
кликов без удаления DOM. Вызывается перед «изменить», перед каждой попыткой «выбрать»
и перед каждой попыткой выбора eSIM; для eSIM добавлены клик force=True и JS-fallback.
Таймаут закрытия вкладки через CDP увеличен с 8 до 20 с плюс одна повторная попытка.
Маркер: OVERLAY_DISMISS_1591R6. Изменены select_esim, run_registration (только
click_tariff_change и цикл «выбрать») и _close_cdp_page_for_worker (имя и вызовы прежние).
'''
MISSION_RULE_R5 = (
    "\n\nПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5): /registration/error — не успех, "
    "но и не вечное ожидание. Сначала детальный анализ страницы (DOM, текст ошибки, console/network) "
    "и мини-отчёт. После отчёта error-вкладка закрывается и открывается новая автоматически, без отдельного подтверждения: "
    "runtime делает это сразу после твоего отчёта и повторяет ту же строку один раз. "
    "При повторной ошибке на той же строке строка пропускается без нового анализа, worker берёт "
    "следующую. Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.")
AGENT_ERROR_BLOCK_R5 = '''ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Сначала самостоятельно изучи DOM, видимый текст, console/network и последние ответы API.
  Определи конкретную причину и, если это безопасно, попробуй исправить на текущей странице.
- Затем отправь мини-отчёт: причина, что проверил, что попробовал, результат, URL.
- После детального анализа и отчёта error-вкладка закрывается и открывается новая
  АВТОМАТИЧЕСКИ, без отдельного подтверждения: runtime делает это сразу после твоего
  отчёта и повторяет ту же строку один раз. При повторной ошибке на той же строке
  строка пропускается, worker переходит к следующей.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.

'''
QUEUE_ERROR_TEXT_R5 = '''    text = (
        f"[AUTO_ERROR_ASSIST TAB {tab_id}] "
        "После mobile-id-auth открылась /registration/error. Это НЕ success. "
        "Сначала автономно проанализируй текущую physical-вкладку: DOM, видимый текст "
        "ошибки, DevTools console и network, последние запросы/ответы и состояние формы. "
        "Определи конкретную причину и, если это безопасно, попробуй исправить её на этой "
        "странице. Затем ОБЯЗАТЕЛЬНО отправь мини-отчёт: причина, что проверил, что "
        "попробовал, результат, URL. Сразу после твоего отчёта runtime автоматически, без "
        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и повторит строку один раз; "
        "при повторной ошибке строка будет пропущена. Worker при этом не теряется. "
        "Сам вкладку не закрывай: это сделает runtime после отчёта. "
        f"Причина вызова: {reason}. URL: {url}"
    )
'''
TICK_ERROR_R5 = r'''# ERROR_RECOVERY_1591R5
ERROR_ASSIST_MAX_SECONDS = 300
ERROR_SKIP_DWELL_SECONDS = 15
ERROR_ROW_MAX_ATTEMPTS = 2


def _error_row_key(worker):
    row = worker.get("row")
    try:
        return _row_number_value(row) or str(row)
    except Exception:
        return str(row)


def _error_analysis_delivered(worker):
    state = (worker.get("auto_assist_state") or {}).get("ERROR") or {}
    if int(state.get("count") or 0) < 1:
        return False
    try:
        return not _auto_assist_pending("ERROR", worker.get("id") or 0)
    except Exception:
        return True


def _error_recover(base_dir, worker, reason):
    """Close the error page, open a fresh one; retry the row once, then skip it.

    Runs without user permission. A worker slot is never stopped because of an error.
    """
    key = _error_row_key(worker)
    counts = worker.setdefault("error_retry_counts", {})
    counts[key] = int(counts.get(key) or 0) + 1
    attempt = counts[key]
    try:
        capture_blackbox(worker, "error_recovery")
    except Exception:
        pass
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        print(f"[Вкладка {worker['id']}] ERROR RECOVERY: новая вкладка не создана ({reason}).", flush=True)
        return False
    if attempt < ERROR_ROW_MAX_ATTEMPTS:
        set_tab_status(
            worker, "♻️",
            f"registration/error: {reason}. Вкладка закрыта, открыта новая; "
            f"повторяю строку (попытка {attempt + 1}).",
        )
        external_heartbeat(worker, "error_retry_same_row")
        return True
    # Second error on the same row: skip it; the next row starts on the fresh page.
    try:
        with (Path(base_dir) / "error_skipped_rows.txt").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{key}\t{reason}\n")
    except Exception:
        pass
    try:
        chat = str(load_telegram_config().get("chat_id") or "")
        if chat:
            _io1591.enqueue_notice(
                globals(), chat,
                f"⏭ Вкладка {worker['id']}: строка {key} пропущена после повторной "
                f"registration/error ({reason}). Worker продолжает со следующей строкой.",
            )
    except Exception:
        pass
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
    external_heartbeat(worker, "error_row_skipped")
    return True


def tick_error_assist(base_dir, worker):
    page = worker["page"]
    worker["error_guard"] = True
    now = monotonic()
    if not worker.get("error_assist_entered_at"):
        worker["error_assist_entered_at"] = now
    entered = float(worker["error_assist_entered_at"])

    if page.is_closed():
        # A closed error page never costs the worker slot: open a fresh page and go on.
        _error_recover(base_dir, worker, "error-страница закрыта извне")
        return

    # If Operator safely repaired the page and it becomes a real contract page,
    # promote it into the immutable SUCCESS GUARD.
    if _post_auth_contract_page(page) and not _post_auth_error_page(page):
        worker["error_guard"] = False
        worker["error_assist_entered_at"] = None
        enter_success_guard(
            worker,
            "DeepSeek/сайт вывел error-state на страницу договора",
        )
        return

    key = _error_row_key(worker)
    if int((worker.get("error_retry_counts") or {}).get(key) or 0) >= ERROR_ROW_MAX_ATTEMPTS - 1:
        # Repeated error on the same row: no second analysis; skip after a short dwell.
        external_heartbeat(worker, "error_repeat_skip_pending")
        if now - entered >= ERROR_SKIP_DWELL_SECONDS:
            _error_recover(base_dir, worker, "повторная ошибка регистрации на той же строке")
        return

    queue_error_assist(
        worker,
        "registration/error открыта; проанализируй DOM/console/network и отправь отчёт",
    )
    external_heartbeat(worker, "error_assist_observing")
    if _error_analysis_delivered(worker):
        _error_recover(base_dir, worker, "детальный анализ завершён")
    elif now - entered >= ERROR_ASSIST_MAX_SECONDS:
        _error_recover(base_dir, worker, "анализ не получен за отведённое время")
'''
README_NOTE_R5 = '''

РЕВИЗИЯ 5 (fix_package_1591.py)
Правило ошибки регистрации (ERROR_RECOVERY_1591R5). После детального анализа и отчёта
DeepSeek runtime автоматически, без отдельного подтверждения, закрывает error-вкладку, открывает новую и
повторяет ту же строку один раз; при повторной ошибке на той же строке строка
пропускается (без нового анализа, запись в error_skipped_rows.txt и уведомление в
Telegram), worker берёт следующую. Если анализ не пришёл за 5 минут, восстановление
выполняется всё равно. Закрытая извне error-страница тоже больше не останавливает
worker. Правило добавлено в системные инструкции (OPERATOR_MISSION_1586, блок ERROR
SUPERVISOR) и в текст задания AUTO_ERROR_ASSIST. Запрет close/restart остаётся только
для SUCCESS_GUARD. Изменён tick_error_assist; обработчики подписи/страницы не тронуты.
'''

# Revision 4: autonomous SUCCESS/ERROR assist requests get a budget per page state.
# Before: every tick in SUCCESS_ASSIST re-queued a full developer-agent run every 45 s
# while the page did not change, and each run posted an identical report.
ASSIST_MARKER = "AUTO_ASSIST_BUDGET_1591R4"
RESIGNED_HANDLERS = {"queue_success_assist", "queue_error_assist", "tick_error_assist", "run_registration", "main"}
OLD_SUCCESS_THROTTLE = '''    now = monotonic()
    last = float(worker.get("success_ai_last_at") or 0)
    if not force and now - last < 45:
        return False

    worker["success_ai_last_at"] = now
    tab_id = int(worker.get("id") or 0)
'''
NEW_SUCCESS_THROTTLE = '''    if not _auto_assist_allowed(worker, "SUCCESS", force):
        return False
    tab_id = int(worker.get("id") or 0)
'''
OLD_ERROR_THROTTLE = '''    now = monotonic()
    last = float(worker.get("error_ai_last_at") or 0)
    if not force and now - last < 45:
        return False
    worker["error_ai_last_at"] = now

    tab_id = int(worker.get("id") or 0)
'''
NEW_ERROR_THROTTLE = '''    if not _auto_assist_allowed(worker, "ERROR", force):
        return False

    tab_id = int(worker.get("id") or 0)
'''
QUEUE_ERROR_DEF = "def queue_error_assist(worker, reason, force=False):\n"
ASSIST_HELPER = '''# AUTO_ASSIST_BUDGET_1591R4
AUTO_ASSIST_MIN_GAP_SECONDS = 45
AUTO_ASSIST_REPORTS_PER_STATE = 2
AUTO_ASSIST_REPEAT_SECONDS = 1800


def _auto_assist_pending(kind, tab_id):
    """True while an unanswered [AUTO_<kind>_ASSIST TAB n] job is still in the inbox."""
    conn = _ai_db_connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM inbox WHERE done_at IS NULL AND body LIKE ? LIMIT 1",
            (f"[AUTO_{kind}_ASSIST TAB {int(tab_id)}]%",),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _auto_assist_allowed(worker, kind, force=False):
    """Budget for autonomous assist requests: the page state, not the clock, decides.

    Per unchanged page URL at most AUTO_ASSIST_REPORTS_PER_STATE requests (the second
    one no sooner than AUTO_ASSIST_MIN_GAP_SECONDS after the first), then one every
    AUTO_ASSIST_REPEAT_SECONDS. A new URL starts a new budget. A request is never
    queued while the previous one for this tab has not been answered yet. `force`
    only waives the minimum gap.
    """
    now = monotonic()
    try:
        url = str(worker.get("page").url or "")
    except Exception:
        url = ""
    states = worker.setdefault("auto_assist_state", {})
    state = states.get(kind)
    if not state or state.get("url") != url:
        state = {"url": url, "count": 0, "last": 0.0}
        states[kind] = state
    try:
        if _auto_assist_pending(kind, worker.get("id") or 0):
            return False
    except Exception:
        pass
    since_last = now - float(state.get("last") or 0)
    if state["count"] >= AUTO_ASSIST_REPORTS_PER_STATE:
        if since_last < AUTO_ASSIST_REPEAT_SECONDS:
            return False
    elif state["count"] > 0 and not force and since_last < AUTO_ASSIST_MIN_GAP_SECONDS:
        return False
    state["count"] += 1
    state["last"] = now
    worker[f"{kind.lower()}_ai_last_at"] = now
    return True


'''
README_NOTE_R4 = '''

РЕВИЗИЯ 4 (fix_package_1591.py)
Бюджет автономных запросов SUCCESS_ASSIST/ERROR_ASSIST. Раньше каждый тик в фазе
SUCCESS_ASSIST ставил в очередь новый полный прогон агента каждые 45 секунд, пока
страница не менялась, и каждый прогон присылал одинаковый отчёт (8 одинаковых
сообщений за 8 минут, лишние токены). Теперь на одну неизменную страницу (URL)
не более двух запросов (второй не раньше чем через 45 с), затем один раз в 30 минут;
новый URL начинает новый бюджет; пока предыдущий запрос по этой вкладке не отвечен,
новый не ставится. Изменены только queue_success_assist и queue_error_assist;
обработчики страницы/подписи не тронуты. Маркер: AUTO_ASSIST_BUDGET_1591R4.
'''

# Revision 3: the proxy login is not embedded in the code any more. The runtime already
# prefers telegram_config.json "proxy" and the TELEGRAM_PROXY variable over this constant.
PROXY_LINE_RE = re.compile(r'^TELEGRAM_DEFAULT_PROXY = "(?:socks5h?|https?)://[^"\n]*"[ \t]*$', re.M)
NEW_PROXY_LINE = ('TELEGRAM_DEFAULT_PROXY = ""  # ' + PROXY_MARKER
                  + ': set "proxy" in telegram_config.json (or TELEGRAM_PROXY)')
OLD_MAIN_RECONSTRUCT = "    original, output = reconstruct(app, package)\n"
NEW_MAIN_RECONSTRUCT = ("    original, output = reconstruct(app, package)\n"
                        "    ensure_proxy_configured(app)\n")
PROXY_GUARD_SOURCE = '''

def ensure_proxy_configured(app):
    """r3: the code no longer embeds the Telegram proxy; it must be in telegram_config.json."""
    try:
        cfg = json.loads((app/'telegram_config.json').read_text('utf-8'))
    except (OSError, ValueError):
        cfg = {}
    if not str((cfg or {}).get('proxy') or '').strip():
        raise RuntimeError('telegram_config.json has no "proxy". Add "proxy": "socks5h://user:password@host:port" '
                           '(the value that was TELEGRAM_DEFAULT_PROXY in the old code) before installing; '
                           'this build does not embed it and would otherwise reach Telegram without the proxy.')
'''

OLD_PUSH = '''            r, err = telegram_api(
                cfg,
                "sendMessage",
                {
                    "chat_id": chat,
                    "text": str(success_text)[:4000],
                    "disable_web_page_preview": "true",
                },
            )
            if not r:
                print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''
NEW_PUSH = '''            # SUCCESS_PUSH_DURABLE_1591R2: the whole text is queued and delivered in
            # confirmed parts by the durable sender; it is never cut to 4000 characters.
            success_text = str(success_text)
            if not success_text.strip():
                continue
            try:
                _io1591.enqueue_notice(globals(), chat, success_text)
                continue
            except Exception as exc:
                print(
                    "[Telegram] SUCCESS push не поставлен в очередь, отправляю напрямую: "
                    f"{_io1591.redact(exc)}",
                    flush=True,
                )
            for piece in _io1591.split_text(success_text):
                r, err = telegram_api(
                    cfg,
                    "sendMessage",
                    {
                        "chat_id": chat,
                        "text": piece,
                        "disable_web_page_preview": "true",
                    },
                )
                if not r:
                    print(f"[Telegram] ОШИБКА отдельного SUCCESS push: {err}", flush=True)
'''

# Version-independent structural hash: fields that are None or [] are omitted, which is
# what ast.dump() started doing by default in Python 3.13. Attributes are never included.
SIGNATURE_SOURCE = '''
def ast_signature(node):
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            if value is None or (isinstance(value, list) and not value):
                continue
            fields.append((name, ast_signature(value)))
        return (type(node).__name__, tuple(fields))
    if isinstance(node, list):
        return tuple(ast_signature(x) for x in node)
    return repr(node)


def handler_hash(node):
    return hashlib.sha256(repr(ast_signature(node)).encode()).hexdigest()
'''
_ns: dict = {"ast": ast, "hashlib": hashlib}
exec(SIGNATURE_SOURCE, _ns)
ast_signature, handler_hash = _ns["ast_signature"], _ns["handler_hash"]

OLD_TEST_HASH = "            actual=hashlib.sha256(ast.dump(function(name),include_attributes=False).encode()).hexdigest()\n"
NEW_TEST_HASH = "            actual=handler_hash(function(name))\n"

OLD_INPUT_CHECK = '''        if digest(raw) != meta['input_sha256']:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
NEW_INPUT_CHECK = '''        accepted = {meta['input_sha256'], *meta.get('previous_output_sha256', [])}
        if digest(raw) not in accepted:
            raise RuntimeError(f'{name}: installed source is different; no code changed. Actual SHA256={digest(raw)}')
'''
OLD_RECONSTRUCT = '''        lines = raw.decode('utf-8').splitlines(keepends=True)
        for change in reversed(edits[name]):
            lines[change['start']:change['end']] = change['replacement']
        updated = ''.join(lines).encode('utf-8')
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: reconstruction checksum failed')
        result[name] = updated
'''
NEW_RECONSTRUCT = '''        # r2: the reviewed package copy is installed once the input checksum matched.
        updated = (package/name).read_bytes()
        if digest(updated) != meta['output_sha256']:
            raise RuntimeError(f'{name}: package copy checksum failed')
        result[name] = updated
'''

README_NOTE_R3 = '''

РЕВИЗИЯ 3 (fix_package_1591.py)
Логин и пароль прокси убраны из кода: TELEGRAM_DEFAULT_PROXY = "". Код и раньше
брал прокси сначала из telegram_config.json ("proxy"), затем из переменной
TELEGRAM_PROXY и только потом из константы. Перед установкой добавьте в
/opt/beeline/telegram_config.json ключ "proxy" со старым значением константы;
install.py отказывается продолжать, пока ключа нет. Маркер: PROXY_FROM_CONFIG_1591R3.
Значение из старого кода на сервере:  grep -o 'socks5h://[^"]*' /opt/beeline/test_beeline.py
'''

README_NOTE = '''

РЕВИЗИЯ 2 (fix_package_1591.py)
1. Отдельный SUCCESS push больше не обрезается до 4000 символов: текст целиком
   ставится в durable-очередь и доставляется частями с подтверждением; при
   недоступной очереди отправляется напрямую частями. Маркер в коде:
   SUCCESS_PUSH_DURABLE_1591R2. Редактируемые статусные сообщения (editMessageText)
   по-прежнему ограничены 4000 символами: часть edit-сообщения разделить нельзя.
2. Хэши защищённых обработчиков в test_update.py считаются по структуре AST без
   полей None/[] и не зависят от версии Python. Прежний ast.dump() давал другой
   текст на Python <= 3.12, из-за чего preflight установщика падал.
3. install.py ставит проверенные копии из пакета после совпадения входного хэша;
   edits.json сохранён как описание изменений. Сервер с уже установленной первой
   сборкой 15.91-io обновляется тем же путём.
Проверка после установки:
grep -c SUCCESS_PUSH_DURABLE_1591R2 /opt/beeline/test_beeline.py   # ожидается 1
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def node_range(source: str, node) -> tuple:
    """Character offsets of the whole lines a top-level node occupies."""
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[:node.lineno - 1])), sum(map(len, lines[:node.end_lineno]))


def only_function(source: str, name: str):
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise SystemExit(f"Expected one {name}; found {len(nodes)}. Source unchanged.")
    return nodes[0]


def replace_once(text: str, old: str, new: str, what: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{what}: expected exactly one occurrence, found {text.count(old)}; nothing changed")
    return text.replace(old, new, 1)


def add_edit(edits: list, output_before: str, old_block: str, new_block: str, reflected=None) -> None:
    """Record the new change in edits.json using the ORIGINAL (input) line numbers.

    `reflected` are the edits already applied in output_before (default: all of `edits`);
    edits appended during the same run are not part of output_before and must not shift
    lines. An earlier edit that lies completely inside old_block is absorbed: its effect
    is already part of old_block, so the new entry replaces it. Partial overlaps are refused.
    """
    reflected = edits if reflected is None else reflected
    out_lines = output_before.splitlines(keepends=True)
    old_lines = old_block.splitlines(keepends=True)
    starts = [i for i in range(len(out_lines)) if out_lines[i:i + len(old_lines)] == old_lines]
    if len(starts) != 1:
        raise SystemExit(f"edits.json: block not unique in the package output ({len(starts)} matches): {old_lines[0][:60]!r}")
    out_start = starts[0]
    out_end = out_start + len(old_lines)

    # A block that lies inside the replacement text of an earlier edit is a change to that
    # edit, not a new one: rewrite its replacement in place.
    delta = 0
    for change in sorted(reflected, key=lambda c: c["start"]):
        out_s = change["start"] + delta
        out_e = out_s + len(change["replacement"])
        if out_s <= out_start and out_end <= out_e:
            joined = "".join(change["replacement"])
            if joined.count(old_block) != 1:
                raise SystemExit("edits.json: block ambiguous inside an earlier edit; source unchanged")
            target = change.get("_orig") or next((c for c in edits if c is change), None)
            if target is None:
                raise SystemExit("edits.json: earlier edit not found; source unchanged")
            target["replacement"] = joined.replace(old_block, new_block, 1).splitlines(keepends=True)
            return
        delta += len(change["replacement"]) - (change["end"] - change["start"])

    def to_input(x):
        delta = 0
        for change in sorted(reflected, key=lambda c: c["start"]):
            shift = len(change["replacement"]) - (change["end"] - change["start"])
            out_s = change["start"] + delta
            out_e = out_s + len(change["replacement"])
            if out_e <= x:
                delta += shift
            elif out_s < x < out_e:
                raise SystemExit("edits.json: the new block cuts through an earlier edit; source unchanged")
        return x - delta

    in_start, in_end = to_input(out_start), to_input(out_end)
    absorbed = [c for c in reflected if in_start <= c["start"] and c["end"] <= in_end
                and c["start"] + 0 >= in_start]
    for a in absorbed:
        orig = a.get("_orig", a)
        if any(orig is c for c in edits):
            edits.remove(orig)
    edits.append({"start": in_start, "end": in_end, "replacement": new_block.splitlines(keepends=True)})
    edits.sort(key=lambda c: c["start"])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    package = Path(argv[1]).resolve()
    app = package / "test_beeline.py"
    for name in ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "install.py",
                 "test_update.py", "manifest.json", "edits.json", "SHA256SUMS.txt", "README.txt"):
        if not (package / name).is_file():
            raise SystemExit(f"{package / name}: missing; this is not the extracted 15.91 package")
    source = app.read_text("utf-8")
    speed_file = package / "symbol_matching.py"
    speed_done = speed_file.is_file() and MATCHER_SPEED_MARKER in speed_file.read_text("utf-8")
    if speed_done and all(m in source for m in (MARKER, PROXY_MARKER, ASSIST_MARKER, ERROR_MARKER, OVERLAY_MARKER,
                                                TARIFF_MARKER, ROWSTART_MARKER, MATCHER_MARKER, OBSERVER_MARKER)):
        print("Already revision 11; nothing changed.")
        return 0
    if sha(app) not in ACCEPTED_PACKAGE_SHAS:
        raise SystemExit(f"test_beeline.py SHA256 {sha(app)} is not a reviewed 15.91-io build; nothing changed")
    manifest = json.loads((package / "manifest.json").read_text("utf-8"))
    edits = json.loads((package / "edits.json").read_text("utf-8"))
    # Edits already present in `source`, as snapshots (their replacement lengths must stay
    # those of `source`) linked to the live entries they describe.
    reflected = []
    for entry in edits["test_beeline.py"]:
        snapshot = dict(entry)
        snapshot["_orig"] = entry
        reflected.append(snapshot)
    new_source = source
    test_src = (package / "test_update.py").read_text("utf-8")
    install_src = (package / "install.py").read_text("utf-8")

    if MARKER not in source:
        # 1. SUCCESS push
        new_source = replace_once(new_source, OLD_PUSH, NEW_PUSH, "test_beeline.py SUCCESS push")
        add_edit(edits["test_beeline.py"], source, OLD_PUSH, NEW_PUSH, reflected)

        # 2. Version-independent handler hashes
        test_src = replace_once(test_src, OLD_TEST_HASH, NEW_TEST_HASH, "test_update.py hash line")
        test_src = replace_once(test_src, "\nclass SourceIntegrityTests(unittest.TestCase):\n",
                                "\n" + SIGNATURE_SOURCE + "\n\nclass SourceIntegrityTests(unittest.TestCase):\n",
                                "test_update.py SourceIntegrityTests")

        # 3. Installer uses the package copies
        install_src = replace_once(install_src, OLD_INPUT_CHECK, NEW_INPUT_CHECK, "install.py input check")
        install_src = replace_once(install_src, OLD_RECONSTRUCT, NEW_RECONSTRUCT, "install.py reconstruct")

    if PROXY_MARKER not in source:
        # 4 (r3). Proxy login out of the code; installer insists on telegram_config.json "proxy".
        matches = PROXY_LINE_RE.findall(new_source)
        if len(matches) != 1:
            raise SystemExit(f"TELEGRAM_DEFAULT_PROXY literal: expected one line, found {len(matches)}; nothing changed")
        old_proxy_line = PROXY_LINE_RE.search(new_source).group(0)
        new_source = new_source.replace(old_proxy_line, NEW_PROXY_LINE, 1)
        add_edit(edits["test_beeline.py"], source, old_proxy_line + "\n", NEW_PROXY_LINE + "\n", reflected)
        install_src = replace_once(install_src, OLD_MAIN_RECONSTRUCT, NEW_MAIN_RECONSTRUCT, "install.py main")
        install_src = replace_once(install_src, "\n\ndef main():\n", PROXY_GUARD_SOURCE + "\n\ndef main():\n",
                                   "install.py proxy guard")

    # 5 (r4). Budget for autonomous assist requests.
    if ASSIST_MARKER not in source:
        new_source = replace_once(new_source, OLD_SUCCESS_THROTTLE, NEW_SUCCESS_THROTTLE, "queue_success_assist throttle")
        new_source = replace_once(new_source, OLD_ERROR_THROTTLE, NEW_ERROR_THROTTLE, "queue_error_assist throttle")
        new_source = replace_once(new_source, QUEUE_ERROR_DEF, ASSIST_HELPER + QUEUE_ERROR_DEF, "assist helper insertion")
        add_edit(edits["test_beeline.py"], source, OLD_SUCCESS_THROTTLE, NEW_SUCCESS_THROTTLE, reflected)
        add_edit(edits["test_beeline.py"], source, OLD_ERROR_THROTTLE, NEW_ERROR_THROTTLE, reflected)
        add_edit(edits["test_beeline.py"], source, QUEUE_ERROR_DEF, ASSIST_HELPER + QUEUE_ERROR_DEF, reflected)
    # 6 (r5). registration/error: analyse, report, then close/reopen, retry once, skip.
    if ERROR_MARKER not in source:
        if ASSIST_MARKER not in new_source:
            raise SystemExit("revision 5 needs the revision 4 assist budget; nothing changed")
        # a) runtime: replace tick_error_assist and add the recovery helpers before it
        fn = only_function(new_source, "tick_error_assist")
        a, b = node_range(new_source, fn)
        old_tick = new_source[a:b]
        new_source = new_source[:a] + TICK_ERROR_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_tick, TICK_ERROR_R5, reflected)
        # b) AUTO_ERROR_ASSIST task text
        fn = only_function(new_source, "queue_error_assist")
        assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "text" for t in n.targets)]
        if len(assigns) != 1:
            raise SystemExit("queue_error_assist: text assignment not unambiguous")
        a, b = node_range(new_source, assigns[0])
        old_text = new_source[a:b]
        new_source = new_source[:a] + QUEUE_ERROR_TEXT_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_text, QUEUE_ERROR_TEXT_R5, reflected)
        # c) ERROR SUPERVISOR block of the agent system prompt
        a = new_source.index("ERROR SUPERVISOR:\n")
        b = new_source.index("Правила действий:\n", a)
        old_block = new_source[a:b]
        new_source = new_source[:a] + AGENT_ERROR_BLOCK_R5 + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_block, AGENT_ERROR_BLOCK_R5, reflected)
        # d) the priority mission constant
        missions = [n for n in ast.parse(new_source).body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "OPERATOR_MISSION_1586" for t in n.targets)]
        if len(missions) != 1:
            raise SystemExit("OPERATOR_MISSION_1586 not unambiguous")
        a, b = node_range(new_source, missions[0])
        old_mission = new_source[a:b]
        if not old_mission.rstrip("\n").endswith('"""'):
            raise SystemExit("OPERATOR_MISSION_1586 is not a triple-quoted literal")
        new_mission = old_mission.rstrip("\n")[:-3] + MISSION_RULE_R5 + '"""\n'
        new_source = new_source[:a] + new_mission + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_mission, new_mission, reflected)

    # 7 (r6). Portal modal over the basket: dismiss it, click through it, longer CDP close.
    if OVERLAY_MARKER not in source:
        anchor = "def esim_state(page):\n"
        new_source = replace_once(new_source, anchor, OVERLAY_HELPER_R6 + anchor, "esim_state anchor")
        add_edit(edits["test_beeline.py"], source, anchor, OVERLAY_HELPER_R6 + anchor, reflected)
        for old, new, what in ((OLD_SELECT_ESIM_ATTEMPT, NEW_SELECT_ESIM_ATTEMPT, "select_esim attempt"),
                               (OLD_TARIFF_CLICK, NEW_TARIFF_CLICK, "click_tariff_change loop"),
                               (OLD_CHOOSE_LOOP, NEW_CHOOSE_LOOP, "second choose loop")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        # CDP close: the original body becomes the nested _once(); the same top-level name
        # gains a 20 s timeout and one retry. Tests that extract the function by name still work.
        fn = only_function(new_source, "_close_cdp_page_for_worker")
        a, b = node_range(new_source, fn)
        old_fn = new_source[a:b]
        if not old_fn.startswith(OLD_CDP_DEF):
            raise SystemExit("_close_cdp_page_for_worker signature differs; source unchanged")
        nested = "".join(("    " + line if line.strip() else line) for line in old_fn.splitlines(keepends=True))
        nested = nested.replace("    " + OLD_CDP_DEF, "    def _once(cdp_url, info, timeout=20):\n", 1)
        new_fn = CDP_HEAD_R6 + nested + CDP_TAIL_R6
        new_source = new_source[:a] + new_fn + new_source[b:]
        add_edit(edits["test_beeline.py"], source, old_fn, new_fn, reflected)

    # 8 (r7). Tariff card by name; the overlay dismisser protects the dialog we need.
    if TARIFF_MARKER not in source:
        for old, new, what in ((OVERLAY_HELPER_R6, OVERLAY_HELPER_R7, "overlay helper"),
                               (OLD_CHOOSE_LOOP_R6, NEW_CHOOSE_LOOP_R7, "choose loop by name"),
                               (OLD_ESIM_DISMISS_R6, NEW_ESIM_DISMISS_R7, "esim dismiss keep")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                # Built from a pre-r6 package in this run: fold r7 into the r6 entry just recorded.
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: r6 entry for {what} not found")

    # 9 (r8). Activity-aware ROW_START watchdog; heartbeat from long steps; retry in place.
    if ROWSTART_MARKER not in source:
        anchor = "def esim_state(page):\n"
        for old, new, what in ((anchor, ROW_PROGRESS_HELPER_R8 + anchor, "row progress helper"),
                               (OLD_WATCHDOG_ROW_START, NEW_WATCHDOG_ROW_START, "watchdog ROW_START"),
                               (OLD_TARIFF_OPEN, NEW_TARIFF_OPEN, "tariff open progress"),
                               (OLD_TARIFF_RETRY, NEW_TARIFF_RETRY, "tariff retry in place"),
                               (OLD_CHOOSE_PRINT, NEW_CHOOSE_PRINT, "choose progress"),
                               (OLD_ESIM_CALL, NEW_ESIM_CALL, "esim progress")):
            new_source = replace_once(new_source, old, new, what)
            if old in source:
                add_edit(edits["test_beeline.py"], source, old, new, reflected)
            else:
                for change in edits["test_beeline.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 10 (r9). CPU-based matcher liveness in the parent; the 75 s rule is untouched.
    if MATCHER_MARKER not in source:
        anchor = "def parent_watchdog(processes, heartbeat):\n"
        for old, new, what in ((anchor, MATCHER_HELPER_R9 + anchor, "matcher helper"),
                               (OLD_WATCHDOG_MATCHER, NEW_WATCHDOG_MATCHER, "watchdog matcher branch"),
                               (OLD_HEALTH_MATCHER, NEW_HEALTH_MATCHER, "host worker health")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 11 (r10). Faster matcher: symbol_matching.py 14.1 joins the package; the installer
    # replaces the server's 14.0 copy (checksum-verified) and imports the new module.
    if not speed_done:
        if not SYMBOL_MATCHING_SOURCE.is_file():
            raise SystemExit(f"{SYMBOL_MATCHING_SOURCE}: missing; nothing changed")
        speed_source = SYMBOL_MATCHING_SOURCE.read_text("utf-8")
        if MATCHER_SPEED_MARKER not in speed_source or "MATCHER_VERSION = '14.1'" not in speed_source:
            raise SystemExit("matcher_r10/symbol_matching.py is not the revision 10 matcher; nothing changed")
        compile(speed_source, "symbol_matching.py", "exec")
        speed_file.write_text(speed_source, "utf-8")
        manifest["files"]["symbol_matching.py"] = {
            "input_sha256": SYMBOL_MATCHING_INPUT_SHA,
            "output_sha256": hashlib.sha256(speed_source.encode("utf-8")).hexdigest(),
            "previous_output_sha256": [],
        }
        for old, new, what in ((OLD_INSTALL_FILES, NEW_INSTALL_FILES, "install.py FILES"),
                               (OLD_INSTALL_LOOP, NEW_INSTALL_LOOP, "install.py reconstruct loop"),
                               (OLD_INSTALL_IMPORT, NEW_INSTALL_IMPORT, "install.py import check"),
                               (OLD_INSTALL_ASSERT, NEW_INSTALL_ASSERT, "install.py version assert")):
            install_src = replace_once(install_src, old, new, what)
        test_src = replace_once(test_src, OLD_TEST_COMPILE_LIST, NEW_TEST_COMPILE_LIST, "test_update.py compile list")
        test_src = replace_once(test_src, OLD_TEST_FIXTURE, NEW_TEST_FIXTURE, "test_update.py installer fixture")

    # 12 (r11). Bounded page collection in the DeepSeek lanes; busy ceiling in the supervisor.
    if OBSERVER_MARKER not in source:
        for old, new, what in ((OLD_COLLECT_DEF, OBSERVER_HELPER_R11 + NEW_COLLECT_DEF, "observer collect wrapper"),
                               (OLD_LANE_STALE, NEW_LANE_STALE, "lane busy ceiling")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    compile(new_source, "test_beeline.py", "exec")
    compile(test_src, "test_update.py", "exec")
    compile(install_src, "install.py", "exec")

    # 4. Manifest and checksums
    tree = ast.parse(new_source)
    for name in manifest["preserved_handlers"]:
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1:
            raise SystemExit(f"preserved handler {name}: found {len(nodes)}")
        manifest["preserved_ast_sha256"][name] = handler_hash(nodes[0])
    old_hashes = {n: handler_hash(next(x for x in ast.parse(source).body
                                        if isinstance(x, ast.FunctionDef) and x.name == n))
                  for n in manifest["preserved_handlers"]}
    changed = {n for n in old_hashes if old_hashes[n] != manifest["preserved_ast_sha256"][n]}
    if changed - RESIGNED_HANDLERS:
        raise SystemExit(f"Preserved handlers changed unexpectedly: {sorted(changed - RESIGNED_HANDLERS)}")
    # A server that already runs the first 15.91 build is upgraded in place as well.
    manifest["files"]["test_beeline.py"]["previous_output_sha256"] = sorted(ACCEPTED_PACKAGE_SHAS)
    manifest["files"]["test_beeline.py"]["output_sha256"] = hashlib.sha256(new_source.encode("utf-8")).hexdigest()
    manifest["revision"] = 11

    app.write_text(new_source, "utf-8")
    (package / "test_update.py").write_text(test_src, "utf-8")
    (package / "install.py").write_text(install_src, "utf-8")
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    (package / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=2), "utf-8")
    readme = package / "README.txt"
    for heading, note in (("РЕВИЗИЯ 2", README_NOTE), ("РЕВИЗИЯ 3", README_NOTE_R3), ("РЕВИЗИЯ 4", README_NOTE_R4),
                          ("РЕВИЗИЯ 5", README_NOTE_R5), ("РЕВИЗИЯ 6", README_NOTE_R6),
                          ("РЕВИЗИЯ 7", README_NOTE_R7), ("РЕВИЗИЯ 8", README_NOTE_R8),
                          ("РЕВИЗИЯ 9", README_NOTE_R9), ("РЕВИЗИЯ 10", README_NOTE_R10),
                          ("РЕВИЗИЯ 11", README_NOTE_R11)):
        if heading not in readme.read_text("utf-8"):
            readme.write_text(readme.read_text("utf-8").rstrip("\n") + note, "utf-8")

    # Prove the package's own suite passes here, then record it.
    run = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_update"], cwd=package,
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    (package / "test_results.txt").write_text(run.stdout, "utf-8")
    if run.returncode:
        print(run.stdout)
        raise SystemExit("Package tests failed after the fix; review test_results.txt")
    ran = next((line for line in run.stdout.splitlines() if line.startswith("Ran ")), "")
    verification = json.loads((package / "verification.json").read_text("utf-8"))
    verification.update({"python": sys.version, "revision": 11, "result": "OK",
                         "tests": int(ran.split()[1]) if ran else None,
                         "exact_input_sha256": manifest["files"]})
    (package / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), "utf-8")

    sums = [f"{sha(package / name)}  {name}" for name in
            ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "symbol_matching.py", "install.py",
             "test_update.py", "manifest.json", "edits.json", "README.txt", "verification.json", "test_results.txt",
             "install_preflight_results.txt") if (package / name).is_file()]
    (package / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    for line in ("__pycache__",):
        for cache in package.glob(line):
            for f in cache.iterdir():
                f.unlink()
            cache.rmdir()
    print(ran + " — OK")
    print("Revision 11 applied to", package)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
