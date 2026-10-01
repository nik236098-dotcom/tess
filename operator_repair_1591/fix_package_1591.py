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
import os
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
                         "6852517bf0eadb15f70359ac93b9c49632926cb3aef9f817c712ea099330248b",
                         "747c7f08c994baa104d82ebb5d3302215bc4f1147e238b66629bd5037710c47d",
                         "e0f5748ea3f7c19e6409a1e4f63fc9e00c322f8c38365134af0f13bf4bd8e14f",
                         "04e07acd1a019a943c72237a6c6c61b34134f7b753ce3f3b484c832ce742ae9d",
                         "21772a39422eeae8224f580beecad29171105885101b76f100190f6d64fd3e7c",
                         "1cc1769f3ec9bd04b325be73fed182a4a05f082339820682601c3bd4be7483f6",
                         "3bee3697775d818df6c1fe82c3096574f00a1c289aaf26c7a7e96d2f614b7597",
                         "1ba0e4f3af9dcc2fa8d78e5eee0033ec48489c402f4c49be9d4e799eb1a786ec",  # r17 output
                         "e8f5e036c2f33ab9d8f27a98deceb25356511cd253fc871f929c16d619f45d75",  # r18 output
                         "341513d5df545f6711f9c5f1e0de7d464d586b6c0afe4ac2fc019a27308457ec",  # r19 output
                         "bb57f0437e52c61d801e94020c3d72f9bbca2b2bbef09b63e0d746e5de9a59f2",  # r20 output
                         "90ddb7d43cfbb2d944a1fb23c62aed15cb3a9d3090810864402aa31b5410a1b0",  # r21 output
                         "fd1ed72b18db63993d0c288fa7ad8449e3e7827fa2b2697569dd79a9053ec3dc",  # r22 output
                         "10af519a75ce7a6813dae1b9b7bd95192cb81587e19361325f1e69e5a231269e",  # r23 output
                         "2e81b5bf57f5da86abec14e2b9bcd7961f44d3c87c54689819a2038a43533057",  # r24 output
                         "aac470f2ecd3e0d4d34b399860cda4393a0fa1896b24d206ea2c794558e853a2",  # r25 output
                         "72110535925a3167e91c621a29e2d46d090f7e76b03bb250df9f35530bdcaa5d",  # r26 output
                         "786a170bbe7f1861e225ec19f150c20ca176f5dbb55beeeb02924522cb29a6f3",  # r27 output
                         "6482ff2cfbc544f86587731e6d84a7ba5c9858987ca5700b60032d2ec4a905cf",  # r28 output
                         "e2c48c93641a62328a976b2197be2b3fba0ff0586819709eacc52afd27042e52",  # r29 output
                         "0b6cc34c63b6cfb1eb2f38909d41b05966eb1251b77c52cf1012d7cd4e95c3ab",  # r30 output (prompt only)
                         "bd07c22559bcd89c0244ed2e67e75c1ee1139274af0e627732b0444f58b546c8",  # r31 output
                         "f64ef74d8f4b6b3875c77253e23ede004065f6afcfc342e971c249138f570541",  # r32 lite output (FIX_1591_WITHOUT_R31=1)
                         "5a4c11e2d64d6d32bed1544d8f83ad44bfdb0c64b33f2df9eeda780d1db8b3dd",  # r32 output
                         "92c9cc68e5cfd3a0f8717d4bb53fb247e43f3564dc55dac75f2bd1b6924112f0",  # r33 lite output
                         "8561fef2069ee3c6df376c6060084aca717405e63f009d96bb0b98aa4aa7c1bc",  # r33 output
                         "abd23f11da908dd2e3bf17e7b5321a95505eb7fcf8eb7d41c8b9cb622c51322f",  # r34 lite output
                         "941b2964bf5f0b549047d4776ad830996951d8f6d35619e20dfed6763f4bc7e2",  # r34 output
                         "0544d1e2190d7ac7a2d091fe2370a558f038dbef17dbb775ce973d7a86642643",  # r35 lite output
                         "1a0258ca2f63186b153280b6e546652deebf624e426fdc629e7348560023c5a4",  # r35 output
                         "725adc5426e06707060bd25daa5af8fd4d66e83bfe064869f323177db3d8a12e",  # r36 lite output
                         "655faf868b4a4ace53dc7845617b4b765890d833822eb7c1d5b2d8b61fcbcb2f",  # r36 output
                         "cce2c689b26dd7ea0aa865576071d7b8372768efb7d67ec8dbb1ae23bf0c5738",  # r37 lite output
                         "a31f394aa9d9b708bb9c85c182a871dd0d63b96de78de58429c5746a07babd44",  # r37 output
                         "ef28ef77fbb8cb8afac35e6daaaeffee983e759322ebafb76c06e2d5fcdce6c1",  # r38 lite output
                         "74a466855054bb9f8cf05ae05c66224a519f0c1322ad695316006ae4aad40348",  # r38 output
                         "e37251fe2500cf89471a3e042f2d7a018c8b98748c933e15b965f1ae0333e00f",  # r39 lite output
                         "85d8693a6d059492252969da1f11966aa79c25fbe42c6ae6a3c6aacd7102c57a",  # r39 output
                         "df25464f90f9f73d006d821da6a918b94386631e30990f42524db157159b6e81",  # r40 lite output
                         "a2dd94165ec5926ad1512956706843987b7ca60efc4a91ec25e95a7de83eb604",  # r40 output
                         "500488cc68d96a1cebda5d421ca4ca653329494d798bd2225ce0ef4b330421ef",  # r41 lite output
                         "f05c32d36010b729259267d3f376cd44ae3a7feb12c653f36efee830e10ee8a6",  # r41 output
                         "596d521c36270a13b733832a75c694531910035ba624503e4e0cfd2533305fd9",  # r42 lite output
                         "a20d4ff24cf13165a2d75737a4caddea5a690057b42c9236d7ca242894ae2fc1"}  # r42 output

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
# Revision 12: on the contract/signature screen the name, gender and birth date are plain
# text, not form fields, so capture_contract_details/final_profile_capture_v1583 (which read
# input/select/textarea values only) leave them empty in the SUCCESS record. A text capture
# reads "label: value" pairs from the page and its frames, validates each value by type,
# never overwrites captured values and dumps the page text once per worker for diagnostics.
PROFILE_MARKER = "SUCCESS_PROFILE_TEXT_1591R12"
OLD_CAPTURE_WRAPPER = '''_capture_contract_details_before_v1583 = capture_contract_details
def capture_contract_details(page, worker):
    result = _capture_contract_details_before_v1583(page, worker)
    try:
        final_profile_capture_v1583(page, worker)
    except Exception:
        pass
    return worker.get("success_profile") or result
'''
NEW_CAPTURE_WRAPPER = '''_capture_contract_details_before_v1583 = capture_contract_details
def capture_contract_details(page, worker):
    result = _capture_contract_details_before_v1583(page, worker)
    try:
        final_profile_capture_v1583(page, worker)
    except Exception:
        pass
    try:
        capture_success_profile_text_1591r12(page, worker)  # SUCCESS_PROFILE_TEXT_1591R12
    except Exception:
        pass
    return worker.get("success_profile") or result
'''
PROFILE_TEXT_HELPER_R12 = r'''# SUCCESS_PROFILE_TEXT_1591R12
# The contract screen shows the name, gender and birth date as plain text, not as form
# fields, so the input-based captures above leave them empty. This capture reads
# "label: value" pairs from the page text (main frame and iframes), validates every
# value by type and never overwrites a value that is already captured.
_PROFILE_TEXT_LABELS_1591R12 = {
    "full_name": ("фио", "фамилия имя отчество", "ф и о", "fullname", "full name"),
    "gender": ("пол", "gender"),
    "birth_date": ("дата рождения", "birth date", "birthdate"),
    "passport_series": ("серия паспорта", "серия"),
    "passport_number": ("номер паспорта",),
    "passport_issue_date": ("дата выдачи",),
    "passport_issued_by": ("кем выдан",),
    "country": ("страна",),
    "region": ("область", "регион"),
    "district": ("район",),
    "locality": ("населенный пункт", "город", "г."),
    "street": ("улица", "ул."),
    "house": ("дом", "номер дома", "д."),
    "building": ("корпус", "строение", "корп."),
    "apartment": ("квартира", "кв."),
}
_DATE_RE_1591R12 = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
_FIO_RE_1591R12 = re.compile(
    r"^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}(\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}){1,3}$"
)
_GENDER_RE_1591R12 = re.compile(r"^(мужской|женский|муж|жен|м|ж|male|female)$", re.I)
_PROFILE_TEXT_VALUE_RE_1591R12 = {
    "passport_series": re.compile(r"^\d{2}\s?\d{2}$"),
    "passport_number": re.compile(r"^\d{6}$"),
    "house": re.compile(r"^\d{1,4}[а-яa-z]?(\s*/\s*\d{1,3})?$", re.I),
    "building": re.compile(r"^[\dа-яa-z\-]{1,6}$", re.I),
    "apartment": re.compile(r"^\d{1,5}[а-яa-z]?$", re.I),
}


def _text_label_key_1591r12(label):
    """Profile key for a visible label, or None. Labels are matched whole (or as the first
    word of a longer label), so «номер договора» or «домашний телефон» never match."""
    hay = _norm_label(label).strip(" :;-–—\t.,")
    if not hay or len(hay) > 40:
        return None
    for key, words in _PROFILE_TEXT_LABELS_1591R12.items():
        for word in words:
            word = _norm_label(word)
            if hay == word or hay.startswith(word + " "):
                return key
    return None


def _text_value_ok_1591r12(key, value):
    value = str(value or "").strip().strip(":;,")
    if not value or value in ("—", "-", "–") or len(value) > 160:
        return False
    if key == "full_name":
        return bool(_FIO_RE_1591R12.match(value))
    if key == "gender":
        return bool(_GENDER_RE_1591R12.match(value))
    if key in ("birth_date", "passport_issue_date"):
        return bool(_DATE_RE_1591R12.search(value))
    pattern = _PROFILE_TEXT_VALUE_RE_1591R12.get(key)
    return bool(pattern.match(value)) if pattern else True


_PROFILE_TEXT_JS_1591R12 = r"""
() => {
  const vis = el => {
    try {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    } catch (_) { return false; }
  };
  const txt = el => ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  const pairs = [];
  const seen = new Set();
  const push = (label, value) => {
    label = String(label || '').replace(/\s+/g, ' ').trim().replace(/[:：]\s*$/, '');
    value = String(value || '').replace(/\s+/g, ' ').trim()
      .replace(/^[:：\-–—]\s*/, '').replace(/[;,]\s*$/, '');
    if (!label || !value || label.length > 40 || value.length > 160) return;
    if (value === label) return;
    const k = label + '|' + value;
    if (seen.has(k)) return;
    seen.add(k);
    pairs.push({label: label, value: value});
  };
  const containers = 'tr,dl,li,p,div,section,article,fieldset';
  document.querySelectorAll(
    'dt,th,[class*="label"],[class*="Label"],[class*="title"],[class*="name"]'
  ).forEach(el => {
    if (!vis(el)) return;
    const label = txt(el);
    if (!label || label.length > 40) return;
    let value = '';
    const sib = el.nextElementSibling;
    if (sib && vis(sib)) value = txt(sib);
    if (!value) {
      const row = el.closest(containers);
      if (row) {
        const t = txt(row);
        const i = t.indexOf(label);
        if (i >= 0) value = t.slice(i + label.length);
      }
    }
    push(label, value);
  });
  document.querySelectorAll('span,div,li,p,strong,b,em,small,a,label,dd,td').forEach(el => {
    if (!vis(el) || (el.children && el.children.length)) return;
    const t = txt(el);
    if (!t || t.length > 140) return;
    const m = t.match(/^([^:：]{2,40})[:：]\s*(.+)$/);
    if (m) push(m[1], m[2]);
  });
  let text = '';
  try { text = (document.body && (document.body.innerText || '')) || ''; } catch (_) {}
  return {pairs: pairs, text: text.slice(0, 20000)};
}
"""


def capture_success_profile_text_1591r12(page, worker):
    """Fill missing profile fields from the visible text of the contract screen."""
    targets, collected, texts = [], [], []
    if page is not None:
        targets.append(page)
        try:
            for frame in page.frames:
                if frame not in targets:
                    targets.append(frame)
        except Exception:
            pass
    for target in targets:
        try:
            data = target.evaluate(_PROFILE_TEXT_JS_1591R12)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for item in data.get("pairs") or []:
            if isinstance(item, dict):
                collected.append((item.get("label"), item.get("value")))
        if data.get("text"):
            texts.append(str(data.get("text")))

    profile = dict(worker.get("success_profile") or {})

    def put(key, value):
        if not key or profile.get(key):
            return
        if _text_value_ok_1591r12(key, value):
            profile[key] = str(value).strip().strip(":;,")

    for label, value in collected:
        put(_text_label_key_1591r12(label), value)

    for text in texts:
        lines = [line.strip() for line in re.split(r"[\r\n]+", text)]
        for index, line in enumerate(lines):
            if not line:
                continue
            match = re.match(r"^([^:：]{2,40})[:：]\s*(.+)$", line)
            if match:
                put(_text_label_key_1591r12(match.group(1)), match.group(2))
            elif _text_label_key_1591r12(line) and index + 1 < len(lines):
                following = lines[index + 1]
                if following and not _text_label_key_1591r12(following):
                    put(_text_label_key_1591r12(line), following)

    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    try:
        diagnostic = worker.get("diagnostic")
        if diagnostic and texts and not worker.get("success_text_dump_done"):
            worker["success_text_dump_done"] = True
            diagnostic.write("success_page_text_v1591r12", url=str(getattr(page, "url", "") or ""),
                             text="\n".join(texts)[:20000])
    except Exception:
        pass
    return profile


'''
README_NOTE_R12 = '''

РЕВИЗИЯ 12 (fix_package_1591.py)
Неполный профиль в SUCCESS-сообщении. На экране договора ФИО, пол и дата рождения показаны
обычным текстом, а не полями формы, а оба существующих захвата (capture_contract_details и
final_profile_capture_v1583) читают только value у input/select/textarea, поэтому эти поля
оставались пустыми. Добавлен текстовый захват capture_success_profile_text_1591r12: читает
пары «подпись: значение» из DOM и текста страницы, включая iframe; подписи сопоставляются
целиком («номер договора» или «домашний телефон» не принимаются за номер паспорта и дом);
каждое значение проверяется по типу (ФИО 2–4 слова с заглавных, пол, даты, серия 4 цифры,
номер 6 цифр, дом/корпус/квартира короткие); уже считанные значения не перезаписываются.
Вызывается из той же обёртки capture_contract_details, то есть во всех прежних точках
(post-auth review, sign-wait, finalize_success). Один раз на worker текст страницы
сохраняется в diagnostics (success_page_text_v1591r12) для проверки на реальном договоре.
Маркер: SUCCESS_PROFILE_TEXT_1591R12.
'''
# Revision 13: scheduled graceful restart. Every N minutes (Telegram: /restart 20m, /restart off,
# /restart now, /restart) the runtime enters a drain: each worker finishes its current row to the
# end (confirmation cycle, signing, DeepSeek assist included) and does not take a new one; when
# no worker is left the runtime exits with RESTART_EXIT_CODE and the controller relaunches it.
RESTART_MARKER = "SCHEDULED_RESTART_1591R13"
CONTROLLER_OUTPUT_SHA_R12 = "506a84c41558332c75cbf55abc8e940520a589b3bc754a6845ca1dd7515740e8"
# server_controller.py as produced by revisions 13..20 (unchanged between them); a server on any
# of those must be accepted by the installer now that r21 changed the controller again.
CONTROLLER_OUTPUT_SHA_R13_R20 = "5104af2bf68452b1dcd3b814b35e696699232087b92db87ee7e1e9a6ee1a8bd9"
CONTROLLER_OUTPUT_SHA_R27_R35 = "384e2c06274159c01dae2b9dc8698dff2a93912e5a6bf3de9eb57efce6d256c4"  # controller of r27..r35
CONTROLLER_OUTPUT_SHA_R36_R37 = "f3b36badf1e9d77a1dda6fe287b5210372d42a1846f993a28cf9c1f6aa7abacd"  # controller of r36..r37 (/res)
CONTROLLER_ACCEPTED_SHAS = {CONTROLLER_OUTPUT_SHA_R12, CONTROLLER_OUTPUT_SHA_R13_R20, CONTROLLER_OUTPUT_SHA_R27_R35,
                            CONTROLLER_OUTPUT_SHA_R36_R37}
RESTART_HELPER_R13 = '''# SCHEDULED_RESTART_1591R13
RESTART_POLICY_FILE_NAME = "restart_policy.json"
RESTART_DRAIN_FILE_NAME = "restart_drain.json"
RESTART_EXIT_CODE = 75
_RESTART_SETTING_RE = re.compile(r"^(\\d+)\\s*(m|min|мин|h|ч|hour|час)?$")


def parse_restart_setting(text):
    """'off' -> 0, '20m'/'20' -> 20, '1h' -> 60, otherwise None (1 minute .. 24 hours)."""
    low = str(text or "").strip().lower()
    if low in {"off", "выкл", "0", "stop", "none"}:
        return 0
    match = _RESTART_SETTING_RE.match(low)
    if not match:
        return None
    value = int(match.group(1))
    minutes = value * 60 if (match.group(2) or "m") in {"h", "ч", "hour", "час"} else value
    return minutes if 1 <= minutes <= 24 * 60 else None


def restart_policy_minutes(base_dir):
    try:
        data = json.loads((Path(base_dir) / RESTART_POLICY_FILE_NAME).read_text(encoding="utf-8"))
        return max(0, int(data.get("interval_minutes") or 0))
    except Exception:
        return 0


def write_restart_policy(base_dir, minutes):
    path = Path(base_dir) / RESTART_POLICY_FILE_NAME
    path.write_text(json.dumps({"interval_minutes": int(minutes), "updated_at": time.time()},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def restart_drain_requested(base_dir):
    return (Path(base_dir) / RESTART_DRAIN_FILE_NAME).is_file()


def request_restart_drain(base_dir, reason=""):
    path = Path(base_dir) / RESTART_DRAIN_FILE_NAME
    if not path.is_file():
        path.write_text(json.dumps({"requested_at": time.time(), "reason": str(reason)}, ensure_ascii=False),
                        encoding="utf-8")


def clear_restart_drain(base_dir):
    try:
        (Path(base_dir) / RESTART_DRAIN_FILE_NAME).unlink()
    except FileNotFoundError:
        pass


def _restart_notify(text):
    """Durable Telegram notice; delivered by the controller's sender even across the restart."""
    try:
        chat = str(load_telegram_config().get("chat_id") or "").strip()
        if chat:
            _io1591.enqueue_notice(globals(), chat, str(text))
    except Exception as exc:
        print(f"[RESTART] Уведомление не поставлено в очередь: {type(exc).__name__}: {exc}", flush=True)


'''
OLD_WORKER_GATE = '''            else:
                try:
                    row = rows.get_nowait()
                except Exception:
                    worker["phase"] = "DONE"
'''
NEW_WORKER_GATE = '''            else:
                if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13
                    # The current row was finished to the end above; do not take a new one.
                    worker["phase"] = "RESTART_WAIT"
                    external_heartbeat(worker, "restart_wait")
                    set_tab_status(worker, "♻️", "Строка завершена; жду плановый перезапуск")
                    print(f"[Вкладка {tab_id}] Плановый перезапуск: строка завершена, новую не беру.", flush=True)
                    break
                try:
                    row = rows.get_nowait()
                except Exception:
                    worker["phase"] = "DONE"
'''
OLD_DEAD_SKIP = '''                    "DONE", "SUCCESS_STOP", "MANUAL_STOP",
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",
                } or bool(info.get("success_guard")) or bool(info.get("error_guard")):
'''
NEW_DEAD_SKIP = '''                    "DONE", "SUCCESS_STOP", "MANUAL_STOP", "RESTART_WAIT",
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",
                } or bool(info.get("success_guard")) or bool(info.get("error_guard")):
'''
OLD_CASCADE_HEAD = '''        # Для каждого Chromium свой последовательный cascade.
        while any(front in cascade_next for front in cascade_front.values()):
            ensure_ai_receiver_alive()
'''
NEW_CASCADE_HEAD = '''        # SCHEDULED_RESTART_1591R13: the timer opens a drain; while draining no new slot
        # or replacement worker is started, workers finish their rows and exit, and the
        # runtime then leaves with RESTART_EXIT_CODE for the controller to relaunch it.
        restart_started_at = monotonic()
        restart_notified = False

        def _restart_tick():
            nonlocal restart_notified
            if not restart_drain_requested(base_dir):
                minutes = restart_policy_minutes(base_dir)
                if minutes <= 0 or monotonic() - restart_started_at < minutes * 60:
                    return False
                request_restart_drain(base_dir, f"every {minutes} min")
                print(f"[RESTART] Прошло {minutes} мин: worker дорабатывают строки, новые не берут.", flush=True)
            if not restart_notified:
                restart_notified = True
                _restart_notify(
                    "♻️ Плановый перезапуск: worker дорабатывают текущие строки "
                    "(подтверждение, подпись, разбор DeepSeek), новые не берут; "
                    "когда все закончат, процесс перезапустится."
                )
            return True

        # Для каждого Chromium свой последовательный cascade.
        while any(front in cascade_next for front in cascade_front.values()):
            if _restart_tick():
                break
            ensure_ai_receiver_alive()
'''
OLD_FINAL_LOOP = '''            recover_dead_workers()

            # Успешная страница принадлежит общему Chromium и остаётся открытой.
            # Завершившийся SUCCESS_STOP-процесс заменяем новым процессом/вкладкой,
            # чтобы количество рабочих слотов не уменьшалось.
            replaced_success = False
            for tab_id, proc in list(processes.items()):
                if proc.is_alive():
                    continue
                info = heartbeat.get(str(tab_id)) or {}
                if info.get("phase") == "SUCCESS_STOP":
'''
NEW_FINAL_LOOP = '''            recover_dead_workers()
            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13

            # Успешная страница принадлежит общему Chromium и остаётся открытой.
            # Завершившийся SUCCESS_STOP-процесс заменяем новым процессом/вкладкой,
            # чтобы количество рабочих слотов не уменьшалось.
            replaced_success = False
            for tab_id, proc in list(processes.items()):
                if proc.is_alive():
                    continue
                info = heartbeat.get(str(tab_id)) or {}
                if info.get("phase") == "SUCCESS_STOP" and not draining:
'''
OLD_QUEUE_DONE = '''        for proc in processes.values():
            proc.join(timeout=1)

        print(f"Все {TAB_COUNT} worker-слота завершили обработку очереди.")
'''
NEW_QUEUE_DONE = '''        for proc in processes.values():
            proc.join(timeout=1)

        if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13
            clear_restart_drain(base_dir)
            print("[RESTART] Все worker завершили строки; выхожу для планового перезапуска.", flush=True)
            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            raise SystemExit(RESTART_EXIT_CODE)

        print(f"Все {TAB_COUNT} worker-слота завершили обработку очереди.")
'''
OLD_CTRL_CLASS = "class AutomationProcess:\n"
NEW_CTRL_CLASS = '''# SCHEDULED_RESTART_1591R13
def _restart_command(argument):
    """/restart, /restart off, /restart 20m, /restart 1h, /restart now."""
    argument = str(argument or "").strip().lower()
    if not argument:
        minutes = app.restart_policy_minutes(BASE_DIR)
        state = f"каждые {minutes} мин" if minutes > 0 else "выключен"
        pending = (" Сейчас ожидается перезапуск: worker дорабатывают строки."
                   if app.restart_drain_requested(BASE_DIR) else "")
        return (f"♻️ Плановый перезапуск: {state}.{pending}\\n"
                "Команды: /restart off, /restart 20m, /restart 1h, /restart now")
    if argument == "now":
        app.request_restart_drain(BASE_DIR, "manual")
        return ("♻️ Запрошен перезапуск: worker дорабатывают текущие строки, новые не берут; "
                "затем процесс перезапустится.")
    minutes = app.parse_restart_setting(argument)
    if minutes is None:
        return "Не понял интервал. Примеры: /restart off, /restart 20m, /restart 1h, /restart now"
    app.write_restart_policy(BASE_DIR, minutes)
    if minutes <= 0:
        return "♻️ Плановый перезапуск выключен."
    return (f"♻️ Плановый перезапуск включён: каждые {minutes} мин. Worker дорабатывают строки "
            "до конца (подтверждение, подпись, разбор DeepSeek), затем процесс перезапускается.")


def _restart_after_drain(proc):
    """Relaunch the automation that exited on purpose (RESTART_EXIT_CODE) after its drain."""
    if proc.proc is None or proc.proc.poll() != app.RESTART_EXIT_CODE:
        return False
    proc.proc = None
    ok, answer = proc.start()
    _send(("♻️ Плановый перезапуск выполнен. " if ok else "⚠️ Плановый перезапуск: запуск не удался. ") + answer)
    return True


class AutomationProcess:
'''
OLD_CTRL_SLASH = '''                    # Any slash-command belongs to controller namespace and is
                    # deliberately kept away from DeepSeek.
                    if text.startswith("/"):
'''
NEW_CTRL_SLASH = '''                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13
                        waiting_upload = False
                        _send(_restart_command(text[len("/restart"):]))
                        continue

                    # Any slash-command belongs to controller namespace and is
                    # deliberately kept away from DeepSeek.
                    if text.startswith("/"):
'''
OLD_CTRL_LOOP = "    while True:\n        proc.reap()\n"
OLD_TEST_CTRL_NS = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}',\n"
NEW_TEST_CTRL_NS = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,\n"
NEW_CTRL_LOOP = "    while True:\n        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n        proc.reap()\n"
README_NOTE_R13 = '''

РЕВИЗИЯ 13 (fix_package_1591.py)
Плановый перезапуск. Команды в Telegram: /restart 20m (каждые 20 минут; можно 45, 1h),
/restart off (выключить), /restart now (запросить сейчас), /restart (показать настройку).
Настройка хранится в restart_policy.json и читается runtime на ходу, перезапуск для смены не
нужен. По таймеру runtime открывает «дренаж» (restart_drain.json): каждый worker доводит
текущую строку до конца (циклы подтверждения, подпись договора, разбор DeepSeek на
SUCCESS/ERROR-экране) и перед взятием новой строки останавливается с фазой RESTART_WAIT; новые
слоты и замены после SUCCESS_STOP не создаются. Когда живых worker не осталось, runtime
завершается кодом 75, контроллер видит этот код и запускает процесс заново, о начале и
завершении приходят уведомления. Пока хоть один worker занят строкой или разбором DeepSeek,
перезапуск ждёт. Маркер: SCHEDULED_RESTART_1591R13 (test_beeline.py и server_controller.py).
'''
# Revision 14: /registration/error reached from the post-auth review went to SUCCESS_ASSIST
# ("post-auth error page"), a branch with a success guard and no recovery, so the worker waited
# for ever. It now takes the registration/error policy of revision 5 like the confirmation
# and resend ticks do: analysis, then close, reopen, retry once, skip on repeat.
POSTAUTH_MARKER = "POST_AUTH_ERROR_ROUTE_1591R14"
OLD_POST_AUTH_ERROR = '''    # A real site error is not success, but even here we do NOT destroy/reload
    # the already-confirmed page. DeepSeek gets the page and decides how to help.
    if _post_auth_error_page(page):
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "🧠",
            "Подтверждение уже прошло. На post-auth странице ошибка — DeepSeek помогает."
        )
        external_heartbeat(worker, "success_post_auth_error")
        queue_success_assist(worker, "post-auth error page")
        return
'''
NEW_POST_AUTH_ERROR = '''    # POST_AUTH_ERROR_ROUTE_1591R14: /registration/error after auth is an ERROR under the
    # registration/error policy (revision 5): DeepSeek analyses, then the runtime closes
    # the tab, opens a new one and retries the row once; a repeat skips the row. This
    # used to become SUCCESS_ASSIST, which has no recovery, and the worker waited for ever.
    if _post_auth_error_page(page):
        capture_blackbox(worker, "registration_error_after_auth")
        print(
            f"[Вкладка {worker['id']}] На post-auth странице открылась /registration/error. "
            "Это НЕ success. Сначала DeepSeek анализирует страницу; затем runtime повторит "
            "строку по правилу registration/error.",
            flush=True,
        )
        enter_error_guard(
            worker,
            "после mobile-id-auth открылась /registration/error (post-auth review)",
        )
        return
'''
README_NOTE_R14 = '''

РЕВИЗИЯ 14 (fix_package_1591.py)
Ошибка регистрации на post-auth странице. Если /registration/error открывалась не сразу после
подтверждения, а уже в фазе POST_AUTH_REVIEW (после циклов «отправить снова»), worker уходил в
SUCCESS_ASSIST с пометкой «post-auth error page»: SUCCESS-guard, восстановления нет, worker
ждал бесконечно, а DeepSeek получал повторные платные запросы. Теперь такая страница
обрабатывается по правилу ревизии 5, как и в tick_confirmation/tick_resend: анализ DeepSeek,
затем закрытие вкладки, новая вкладка, один повтор строки, при повторе пропуск.
Маркер: POST_AUTH_ERROR_ROUTE_1591R14. Изменён tick_post_auth_review (переподписан в manifest).
'''
# Revision 15: a deterministic operator refusal on /registration/error (PERSDATA_NOT_MATCH:
# "данные не прошли проверку", "укажите другой свой номер") is skipped at once, without the
# paid DeepSeek analysis and without the retry that could only repeat the same refusal.
PERSDATA_MARKER = "PERSDATA_SKIP_1591R15"
OLD_ENTER_ERROR_GUARD = '''def enter_error_guard(worker, note):
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
NEW_ENTER_ERROR_GUARD = r'''# PERSDATA_SKIP_1591R15
ERROR_FINAL_NEEDLES_1591R15 = (
    ("данные не прошли проверку", "данные не прошли проверку у оператора"),
    ("укажите другой свой номер", "оператор просит указать другой номер"),
    ("persdata_not_match", "PERSDATA_NOT_MATCH"),
    ("не совпадают с данными", "данные не совпадают с базой оператора"),
)


def _error_page_final_reason(page):
    """Reason text when the error page is a deterministic operator refusal, else None."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        return None
    for needle, reason in ERROR_FINAL_NEEDLES_1591R15:
        if needle in body:
            return reason
    return None


def _error_skip_final(worker, reason):
    """Skip the row at once: a retry cannot change the operator's answer.

    Same steps as the second-error skip of ERROR_RECOVERY_1591R5, minus the analysis
    and the retry: fresh page, record in error_skipped_rows.txt, Telegram notice, IDLE.
    """
    key = _error_row_key(worker)
    base_dir = worker.get("base_dir") or Path(__file__).resolve().parent
    try:
        capture_blackbox(worker, "error_final_skip")
    except Exception:
        pass
    print(
        f"[Вкладка {worker['id']}] registration/error: {reason}. Повтор бессмыслен — "
        f"строка {key} пропускается без анализа.",
        flush=True,
    )
    worker["error_guard"] = False
    worker["success_guard"] = False
    worker["error_assist_entered_at"] = None
    worker["auto_assist_state"] = {}
    worker["phase"] = "ERROR_RECOVERY"
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        print(f"[Вкладка {worker['id']}] Новая вкладка не создана; строка {key} будет повторена.", flush=True)
        return False
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
                f"⏭ Вкладка {worker['id']}: строка {key} пропущена без повтора: {reason}. "
                "Worker продолжает со следующей строкой.",
            )
    except Exception:
        pass
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
    external_heartbeat(worker, "error_row_skipped_final")
    return True


def enter_error_guard(worker, note):
    # PERSDATA_SKIP_1591R15: a deterministic refusal is skipped at once, without the paid
    # analysis and without a retry that would only repeat the same answer.
    final = _error_page_final_reason(worker.get("page"))
    if final and _error_skip_final(worker, final):
        return
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
README_NOTE_R15 = '''

РЕВИЗИЯ 15 (fix_package_1591.py)
Отказ оператора без повтора. Если на /registration/error сайт пишет «данные не прошли
проверку» / «укажите другой свой номер» (в network это PERSDATA_NOT_MATCH: паспортные данные
строки не совпали с базой оператора), повтор строки даёт тот же ответ, но стоит новой капчи,
нового подтверждения у клиента и платного анализа DeepSeek. Теперь такая страница
распознаётся в enter_error_guard до постановки анализа в очередь: вкладка закрывается,
открывается новая, строка записывается в error_skipped_rows.txt с причиной, в Telegram уходит
уведомление «пропущена без повтора», worker берёт следующую строку. Все остальные ошибки
регистрации идут по правилу ревизии 5 без изменений. Маркер: PERSDATA_SKIP_1591R15.
'''
# Revision 16: every /registration/error after the confirmation is handled without DeepSeek:
# the tab is replaced and the row is skipped at once (the retry-once of revision 5 is gone).
ERRORSKIP_MARKER = "ERROR_SKIP_ALWAYS_1591R16"
OLD_GUARD_HEAD_R15 = '''def enter_error_guard(worker, note):
    # PERSDATA_SKIP_1591R15: a deterministic refusal is skipped at once, without the paid
    # analysis and without a retry that would only repeat the same answer.
    final = _error_page_final_reason(worker.get("page"))
    if final and _error_skip_final(worker, final):
        return
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
NEW_GUARD_HEAD_R16 = '''def enter_error_guard(worker, note):
    # ERROR_SKIP_ALWAYS_1591R16: every /registration/error after the confirmation is handled
    # without DeepSeek: the tab is replaced and the row is skipped at once. A page that names
    # the cause (PERSDATA_SKIP_1591R15) supplies the precise reason for the record.
    reason = _error_page_final_reason(worker.get("page")) or "registration/error после подтверждения"
    if _error_skip_final(worker, reason):
        return
    # No fresh page yet: the error tick repeats the skip after a short dwell, still without
    # an analysis request (the repeat-error branch of ERROR_RECOVERY_1591R5).
    worker.setdefault("error_retry_counts", {})[_error_row_key(worker)] = ERROR_ROW_MAX_ATTEMPTS - 1
    worker["error_guard"] = True
    worker["success_guard"] = False
    worker["phase"] = "ERROR_ASSIST"
'''
OLD_GUARD_TAIL = '''    set_tab_status(
        worker, "🧠",
        "Registration error — DeepSeek сначала анализирует. Автоперезапуск запрещён."
    )
    external_heartbeat(worker, note)
    queue_error_assist(worker, note, force=True)
'''
NEW_GUARD_TAIL_R16 = '''    set_tab_status(
        worker, "♻️",
        "Registration error — вкладка будет перезапущена, строка пропущена. DeepSeek не вызывается."
    )
    external_heartbeat(worker, note)
'''
OLD_MISSION_R5_TEXT = ("ПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5): /registration/error — не успех, "
    "но и не вечное ожидание. Сначала детальный анализ страницы (DOM, текст ошибки, console/network) "
    "и мини-отчёт. После отчёта error-вкладка закрывается и открывается новая автоматически, без отдельного подтверждения: "
    "runtime делает это сразу после твоего отчёта и повторяет ту же строку один раз. "
    "При повторной ошибке на той же строке строка пропускается без нового анализа, worker берёт "
    "следующую. Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.\"\"\"\n")
NEW_MISSION_R16_TEXT = ("ПРАВИЛО ОШИБКИ РЕГИСТРАЦИИ (ERROR_RECOVERY_1591R5, ERROR_SKIP_ALWAYS_1591R16): "
    "/registration/error — не успех. Runtime обрабатывает её сам, автоматически, без отдельного подтверждения "
    "и без запроса к DeepSeek: error-вкладка закрывается, открывается новая, строка пропускается и записывается "
    "в error_skipped_rows.txt, worker берёт следующую. Анализировать такие страницы не нужно. "
    "Ни одна ошибка не должна приводить к потере worker. Запрет close/restart/reload "
    "остаётся только для SUCCESS_GUARD.\"\"\"\n")
OLD_AGENT_BLOCK_R5 = '''ERROR SUPERVISOR:
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
NEW_AGENT_BLOCK_R16 = '''ERROR SUPERVISOR:
- /registration/error НИКОГДА не является success.
- Такие страницы runtime обрабатывает АВТОМАТИЧЕСКИ, без отдельного подтверждения и без
  твоего анализа: error-вкладка закрывается, открывается новая, строка пропускается
  (error_skipped_rows.txt), worker переходит к следующей.
- Не запрашивай и не проводи анализ /registration/error по своей инициативе.
- Из-за error worker никогда не теряется: слот всегда получает новую вкладку.
- Запрет close/restart/reload/back/navigate действует только на SUCCESS GUARD.
'''
OLD_QUEUE_SENTENCE_R5 = ('        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и повторит строку один раз; "\n'
                         '        "при повторной ошибке строка будет пропущена. Worker при этом не теряется. "\n')
NEW_QUEUE_SENTENCE_R16 = ('        "отдельного подтверждения, закроет эту error-вкладку, откроет новую и пропустит строку без повтора. "\n'
                          '        "Worker при этом не теряется. "\n')
README_NOTE_R16 = '''

РЕВИЗИЯ 16 (fix_package_1591.py)
Ошибка регистрации без DeepSeek. Любая /registration/error после подтверждения теперь
обрабатывается runtime сразу и без анализа: вкладка закрывается, открывается новая, строка
пропускается с записью в error_skipped_rows.txt и уведомлением в Telegram, worker берёт
следующую. Повтор «один раз» из ревизии 5 убран: он стоил новой капчи, нового подтверждения у
клиента и платного анализа, а на волнах ошибок сайта давал те же ошибки. Если новую вкладку
создать не удалось, worker через 15 секунд повторяет пропуск (ветка повторной ошибки r5), тоже
без запроса к DeepSeek. Правило в системных инструкциях DeepSeek обновлено: анализировать такие
страницы не нужно. Причина на странице (r15) по-прежнему записывается в третью колонку.
Маркер: ERROR_SKIP_ALWAYS_1591R16.
'''
# Revision 17: "#успешно" on top of the SUCCESS push (searchable among the DeepSeek reports)
# and four worker tabs per Chromium instead of three.
SUCCESSTAG_MARKER = "SUCCESS_TAG_1591R17"
OLD_SUCCESS_HEAD = '''    return "\\n".join([
        f"✅ УСПЕХ — Вкладка {worker['id']}",
'''
NEW_SUCCESS_HEAD = '''    return "\\n".join([
        "#успешно",  # SUCCESS_TAG_1591R17: searchable among the DeepSeek reports
        f"✅ УСПЕХ — Вкладка {worker['id']}",
'''
OLD_TABS_LINE = "TABS_PER_BROWSER = 3\n"
NEW_TABS_LINE = "TABS_PER_BROWSER = 4  # SUCCESS_TAG_1591R17: four worker tabs\n"
README_NOTE_R17 = '''

РЕВИЗИЯ 17 (fix_package_1591.py)
Тег #успешно первой строкой SUCCESS-сообщения в Telegram, чтобы успехи искались среди
отчётов DeepSeek поиском по чату. Число рабочих вкладок на Chromium увеличено с 3 до 4
(TABS_PER_BROWSER = 4): каскад, статусы, watchdog и промпты DeepSeek берут число из
константы, поэтому больше ничего не менялось. Маркер: SUCCESS_TAG_1591R17.
'''
# Revision 18: a Chromium that stops answering CDP (connect_over_cdp timeouts on every
# watchdog attempt) is replaced as a whole, workers included. Also the literal "\n" in the
# watchdog's Telegram status text becomes a real line break.
BROWSER_MARKER = "BROWSER_HANG_1591R18"
OLD_WAIT_CDP = '''def _wait_cdp(port, timeout=25):
    deadline = monotonic() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    while monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False
'''
BROWSER_HELPERS_R18 = '''

# BROWSER_HANG_1591R18: a Chromium whose CDP socket accepts the connection but never
# answers (connect_over_cdp timeout) blocks every tab of that browser. The watchdog can
# only replace tabs, so after BROWSER_HANG_RESTART_SECONDS of continuous refusals the
# whole browser process is replaced on the same port and its workers are respawned.
BROWSER_HANG_RESTART_SECONDS = 120
_CDP_UNREACHABLE_SINCE = {}


def _note_cdp_result(cdp_url, exc, now=None):
    """Remember since when `cdp_url` refuses CDP commands; `exc=None` means it answered."""
    key = str(cdp_url)
    if exc is None:
        _CDP_UNREACHABLE_SINCE.pop(key, None)
        return
    text = f"{type(exc).__name__}: {exc}"
    if "connect_over_cdp" in text and "Timeout" in text:
        _CDP_UNREACHABLE_SINCE.setdefault(key, now if now is not None else monotonic())


def cdp_unreachable_seconds(cdp_url, now=None):
    since = _CDP_UNREACHABLE_SINCE.get(str(cdp_url))
    if since is None:
        return 0.0
    return (now if now is not None else monotonic()) - since


def _chromium_launch_args(chromium_exe, port, profile):
    """Same flags as args_i in main() (test_update checks that literal list stays there)."""
    return [
        chromium_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "about:blank",
    ]


def _terminate_chromium(instance):
    proc = instance.get("proc")
    try:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    except Exception:
        pass
    if instance.get("profile"):
        shutil.rmtree(str(instance["profile"]), ignore_errors=True)


def _relaunch_chromium(instance, chromium_exe, popen=None, wait_cdp=None, free_port=None):
    """Start a fresh Chromium for `instance`: the old port first (cdp_url stays valid for
    the observers), a free port as the fallback. Returns False when neither came up."""
    popen = popen or subprocess.Popen
    wait_cdp = wait_cdp or _wait_cdp
    free_port = free_port or _free_local_port
    for attempt in range(2):
        port = instance["port"] if attempt == 0 else free_port()
        profile = tempfile.mkdtemp(prefix=f"esim_pw_browser{instance['id']}_")
        instance["proc"] = popen(_chromium_launch_args(chromium_exe, port, profile))
        instance["profile"] = profile
        if wait_cdp(port):
            _CDP_UNREACHABLE_SINCE.pop(str(instance.get("cdp_url")), None)
            instance["port"] = port
            instance["cdp_url"] = f"http://127.0.0.1:{port}"
            _CDP_UNREACHABLE_SINCE.pop(instance["cdp_url"], None)
            return True
        _terminate_chromium(instance)
    return False
'''
OLD_CDP_CONNECT_R6 = '''                browser = p.chromium.connect_over_cdp(
                    cdp_url, timeout=int(timeout * 1000)
                )
'''
NEW_CDP_CONNECT_R18 = OLD_CDP_CONNECT_R6 + '''                _note_cdp_result(cdp_url, None)  # BROWSER_HANG_1591R18: the browser answered
'''
OLD_CDP_EXCEPT_R6 = '''        except Exception as exc:
            print(
                f"[WATCHDOG] Не удалось закрыть {expected_name}: "
'''
NEW_CDP_EXCEPT_R18 = '''        except Exception as exc:
            _note_cdp_result(cdp_url, exc)  # BROWSER_HANG_1591R18
            print(
                f"[WATCHDOG] Не удалось закрыть {expected_name}: "
'''
OLD_EXPERIMENT_LINE = '''    print("ЭКСПЕРИМЕНТ: запускаю 1 Chromium и 3 рабочие вкладки. Общая очередь строк.")
'''
NEW_EXPERIMENT_LINE = '''    print(f"Запускаю {BROWSER_COUNT} Chromium и {TAB_COUNT} рабочие вкладки. Общая очередь строк.")  # BROWSER_HANG_1591R18
'''
OLD_DEAD_HEAD = '''        def recover_dead_workers():
            """Restore capacity when a worker process died unexpectedly."""
'''
RESTART_BROWSER_FN_R18 = '''        def restart_browser_instance(browser_idx, reason):  # BROWSER_HANG_1591R18
            """Chromium stopped answering CDP: replace the browser process and its worker tabs.

            A tab still working a row gets the same row again. A tab under success/error
            guard, or one that already completed its confirm cycle, takes the next row so
            nothing is submitted twice. DONE / MANUAL_STOP / RESTART_WAIT slots stay as they are.
            When no Chromium comes up, the process exits with RESTART_EXIT_CODE and the
            controller relaunches everything.
            """
            instance = browser_instances[browser_idx]
            first_tab = browser_idx * TABS_PER_BROWSER + 1
            tab_ids = [t for t in range(first_tab, first_tab + TABS_PER_BROWSER) if t in processes]
            print(
                f"[BROWSER RESTART] Chromium #{instance['id']}: {reason} "
                f"Перезапускаю браузер и вкладки {tab_ids}.",
                flush=True,
            )
            plans = []
            for tab_id in tab_ids:
                proc = processes.get(tab_id)
                info = dict(heartbeat.get(str(tab_id)) or {})
                phase = str(info.get("phase") or "")
                if phase in {"DONE", "MANUAL_STOP", "RESTART_WAIT"}:
                    continue
                guarded = bool(info.get("success_guard")) or bool(info.get("error_guard")) or phase in {
                    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "SUCCESS_STOP", "ERROR_ASSIST",
                }
                row = None if (guarded or bool(info.get("completed_confirm_cycle"))) else info.get("row")
                plans.append((tab_id, row))
                try:
                    if proc is not None and proc.is_alive():
                        proc.terminate()
                        proc.join(timeout=5)
                        if proc.is_alive():
                            proc.kill()
                            proc.join(timeout=3)
                except Exception:
                    pass
                heartbeat.pop(str(tab_id), None)
                status_map[str(tab_id)] = {
                    "text": (
                        f"♻️ Вкладка {tab_id}\\nChromium перестал отвечать — браузер перезапущен.\\n"
                        + ("Повторяю эту же строку." if row is not None else "Беру следующую строку.")
                    ),
                    "time": time.time(),
                }
            _terminate_chromium(instance)
            if not _relaunch_chromium(instance, chromium_exe):
                print(
                    f"[BROWSER RESTART] Chromium #{instance['id']} не поднял CDP-порт; "
                    "выхожу для перезапуска процесса контроллером.",
                    flush=True,
                )
                _restart_notify(
                    f"⚠️ Chromium #{instance['id']} перестал отвечать ({reason}) и не запустился заново. "
                    "Перезапускаю весь процесс."
                )
                raise SystemExit(RESTART_EXIT_CODE)
            print(f"[BROWSER RESTART] Chromium #{instance['id']} готов: {instance['cdp_url']}", flush=True)
            _restart_notify(
                f"♻️ Chromium #{instance['id']} перестал отвечать ({reason}) Браузер перезапущен, "
                f"вкладки {[t for t, _ in plans]} пересозданы: строки в работе повторяются, "
                "завершённые берут следующую."
            )
            for tab_id, row in plans:
                new_proc, _ = spawn_worker(tab_id, row)
                processes[tab_id] = new_proc

'''
NEW_DEAD_HEAD = RESTART_BROWSER_FN_R18 + OLD_DEAD_HEAD
OLD_CLOSE_FAIL = '''                if not closed_old_tab:
                    print(
                        f"[WATCHDOG] TAB {tab_id}: старую вкладку закрыть не удалось; "
                        "replacement пока не создаю.",
                        flush=True,
                    )
                    continue
'''
NEW_CLOSE_FAIL = '''                if not closed_old_tab:
                    hang = cdp_unreachable_seconds(browser_instances[browser_idx]["cdp_url"])  # BROWSER_HANG_1591R18
                    if hang >= BROWSER_HANG_RESTART_SECONDS:
                        restart_browser_instance(
                            browser_idx,
                            f"CDP не отвечает {int(hang)} сек (вкладка {tab_id}: {reason})",
                        )
                        return True
                    print(
                        f"[WATCHDOG] TAB {tab_id}: старую вкладку закрыть не удалось; "
                        "replacement пока не создаю.",
                        flush=True,
                    )
                    continue
'''
OLD_STATUS_NL = r'''                        f"♻️ Вкладка {tab_id}\\n{reason}\\n"
'''
NEW_STATUS_NL = r'''                        f"♻️ Вкладка {tab_id}\n{reason}\n"  # BROWSER_HANG_1591R18: real line break
'''
README_NOTE_R18 = '''

РЕВИЗИЯ 18 (fix_package_1591.py)
Зависание всего Chromium. Когда браузер принимает CDP-соединение, но не отвечает на
команды (BrowserType.connect_over_cdp: Timeout), watchdog не мог закрыть ни одну вкладку и
крутился по кругу: «старую вкладку закрыть не удалось; replacement пока не создаю».
Теперь _close_cdp_page_for_worker отмечает такие отказы по адресу браузера
(_note_cdp_result / cdp_unreachable_seconds); если они длятся BROWSER_HANG_RESTART_SECONDS
(120 с), restart_browser_instance завершает worker этого браузера, убивает Chromium,
поднимает новый на том же порту (запасной вариант — свободный порт) и пересоздаёт вкладки:
строки в работе повторяются, вкладки под success/error guard и завершившие confirm берут
следующую строку, слоты DONE/MANUAL_STOP/RESTART_WAIT не трогаются. Если Chromium не
поднялся — выход с RESTART_EXIT_CODE, контроллер перезапускает процесс. Флаги запуска
Chromium повторены в _chromium_launch_args. В watchdog-статусе Telegram литеральный «\\n»
заменён настоящим переводом строки. Маркер: BROWSER_HANG_1591R18.
'''
# Revision 19: on the personal-data form the full name, the birth date and the four address
# inputs between «страна» and «дом» carry no label[for], name, id or descriptive placeholder;
# their captions sit in neighbouring elements. final_profile_capture_v1583 matched labels
# only, so those six fields stayed empty in the SUCCESS push. A companion capture records the
# nearest label-like text and the data-/aria-/autocomplete attributes of every control, and
# still-unlabeled fields fall back to value shape (name, birth date) and to position (the
# four address inputs). capture_all_form_fields_v1583 is a preserved handler and is untouched.
PROFILE_LABELS_MARKER = "PROFILE_LABELS_1591R19"
OLD_FINAL_CAPTURE_DEF = '''def final_profile_capture_v1583(page, worker):
    fields = capture_all_form_fields_v1583(page)
'''
PROFILE_LABEL_HELPERS_R19 = r'''# PROFILE_LABELS_1591R19
_FORM_FIELDS_JS_1591R19 = r"""() => {
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  const hasControl = el => !!(el && el.querySelector && el.querySelector('input,select,textarea'));
  const shortText = el => { const t = clean(el && (el.innerText || el.textContent)); return t && t.length <= 80 ? t : ''; };
  const out = [];
  for (const el of document.querySelectorAll('input,select,textarea')) {
    let near = '';
    try {
      // 1. the wrapper of exactly this control that carries a short caption (floating labels)
      let node = el.parentElement;
      for (let depth = 0; depth < 5 && !near && node; depth++) {
        if (node.querySelectorAll('input,select,textarea').length !== 1) break;
        near = shortText(node);
        node = node.parentElement;
      }
      // 2. the caption rendered just before the control or its wrapper; another control
      //    in between means the caption belongs to that other field
      node = el;
      for (let depth = 0; depth < 3 && !near && node; depth++) {
        let sib = node.previousElementSibling;
        while (sib && !near) {
          if (sib.matches('input,select,textarea') || hasControl(sib)) break;
          near = shortText(sib);
          sib = sib.previousElementSibling;
        }
        node = node.parentElement;
      }
    } catch (_) {}
    const attrs = [];
    try {
      for (const a of el.attributes) {
        if (/^(data-|aria-|autocomplete$|title$|role$)/.test(a.name) && a.value) attrs.push(a.name + '=' + a.value);
      }
      const by = el.getAttribute('aria-labelledby');
      if (by) for (const id of by.split(/\s+/)) { const l = document.getElementById(id); if (l) attrs.push('labelledby=' + clean(l.textContent)); }
    } catch (_) {}
    let value = '';
    try {
      value = (el.type === 'checkbox' || el.type === 'radio') ? (el.checked ? 'true' : 'false')
                                                              : String(el.value == null ? '' : el.value);
    } catch (_) {}
    let label = '';
    try {
      if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = clean(l.textContent); }
      if (!label) { const l = el.closest('label'); if (l) label = clean(l.textContent); }
    } catch (_) {}
    out.push({tag: (el.tagName || '').toLowerCase(), type: el.type || '', name: el.name || '', id: el.id || '',
              value, label, placeholder: el.placeholder || '', ariaLabel: el.getAttribute('aria-label') || '',
              near, attrs: attrs.join(' ')});
  }
  return out;
}"""


def capture_form_fields_1591r19(page):
    """capture_all_form_fields_v1583 plus `near` (the closest label-like text around the
    control) and `attrs` (data-/aria-/autocomplete attributes). Read-only."""
    try:
        data = page.evaluate(_FORM_FIELDS_JS_1591R19)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _alias_hit_1591r19(hay, word):
    """Short aliases («пол», «дом», «край», «ул.») must be whole words: «поле», «домашний»
    and «крайний» in a hint next to the field are not labels."""
    word = word.replace("ё", "е")
    if len(word) <= 4:
        return re.search(r"(?<![а-яa-z0-9])" + re.escape(word) + r"(?![а-яa-z0-9])", hay) is not None
    return word in hay


_DATE_FIELD_RE_1591R19 = re.compile(r"^\d{2}[.\-/]\d{2}[.\-/]\d{4}$")
_SKIP_FIELD_TYPES_1591R19 = {"checkbox", "radio", "hidden", "submit", "button", "password", "file"}


def _profile_fallback_1591r19(profile, fields, consumed):
    """Fields with no caption anywhere: the full name and the birth date by value shape, the
    four address inputs between «страна» and «дом» by their position on the form."""
    text_inputs = [(i, f) for i, f in enumerate(fields)
                   if str(f.get("tag") or "input").lower() == "input"
                   and str(f.get("type") or "text").lower() not in _SKIP_FIELD_TYPES_1591R19]
    issue_date = str(profile.get("passport_issue_date") or "").strip()
    for i, f in text_inputs:
        value = str(f.get("value") or "").strip()
        if i in consumed or not value:
            continue
        if not profile.get("full_name") and " " in value and _FIO_RE_1591R12.match(value):
            profile["full_name"] = value
            consumed.add(i)
            continue
        if (not profile.get("birth_date") and _DATE_FIELD_RE_1591R19.match(value) and value != issue_date
                and (_DATE_FIELD_RE_1591R19.match(str(f.get("placeholder") or "").strip())
                     or "рожд" in str(f.get("near") or "").lower())):
            profile["birth_date"] = value
            consumed.add(i)
    ids = [str(f.get("id") or "").lower() for f in fields]
    if "country" in ids and "house" in ids and ids.index("country") < ids.index("house"):
        a, b = ids.index("country"), ids.index("house")
        between = [(i, f) for i, f in text_inputs if a < i < b]
        if len(between) == 4:
            for (i, f), key in zip(between, ("region", "district", "locality", "street")):
                value = str(f.get("value") or "").strip()
                if i not in consumed and len(value) >= 2 and not profile.get(key):
                    profile[key] = value
                    consumed.add(i)
    return profile


'''
NEW_FINAL_CAPTURE_DEF = PROFILE_LABEL_HELPERS_R19 + OLD_FINAL_CAPTURE_DEF
OLD_ALIASES_HEAD = '''        "full_name": ("фио", "фамилия имя отчество", "fullname", "full_name"),
        "gender": ("пол", "gender"),
        "birth_date": ("дата рождения", "birth", "birthday"),
'''
NEW_ALIASES_HEAD = '''        "full_name": ("фио", "фамилия имя отчество", "фамилия", "ф.и.о", "ф. и. о", "fullname", "full_name",
                      "autocomplete=name"),  # PROFILE_LABELS_1591R19
        "gender": ("пол", "gender"),
        "birth_date": ("дата рождения", "дата рожд", "рождения", "birth", "birthday", "bday"),
'''
OLD_ALIASES_ADDRESS = '''        "region": ("область", "регион", "region"),
        "district": ("район", "district"),
        "locality": ("населённый пункт", "город", "city", "locality"),
        "street": ("улица", "street"),
'''
NEW_ALIASES_ADDRESS = '''        "region": ("область", "регион", "край", "республика", "region", "address-level1"),
        "district": ("район", "р-н", "district"),
        "locality": ("населённый пункт", "населенный пункт", "населённый", "населенный", "город", "city",
                     "locality", "address-level2"),
        "street": ("улица", "ул.", "street", "address-line1"),
'''
OLD_MATCH_LOOP = '''    for f in fields:
        value = str(f.get("value") or "").strip()
        if not value:
            continue
        hay = " ".join(str(f.get(k) or "") for k in
                       ("label", "name", "id", "placeholder", "ariaLabel")).lower()
        for key, words in aliases.items():
            if profile.get(key):
                continue
            if any(word in hay for word in words):
                profile[key] = value
                break
    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    return profile, fields
'''
NEW_MATCH_LOOP = '''    extended = capture_form_fields_1591r19(page)  # PROFILE_LABELS_1591R19
    if extended:
        try:
            d = worker.get("diagnostic")
            if d:
                d.write("form_fields_1591r19", fields=extended, url=page.url)
        except Exception:
            pass
    matched = extended or fields
    consumed = set()
    for index, f in enumerate(matched):
        value = str(f.get("value") or "").strip()
        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
        hay = " ".join(str(f.get(k) or "") for k in
                       ("label", "name", "id", "placeholder", "ariaLabel", "near", "attrs")).lower().replace("ё", "е")
        for key, words in aliases.items():
            if profile.get(key):
                continue
            if any(_alias_hit_1591r19(hay, word) for word in words):
                profile[key] = value
                consumed.add(index)
                break
    _profile_fallback_1591r19(profile, matched, consumed)
    worker["success_profile"] = profile
    worker["profile"] = dict(profile)
    return profile, fields
'''
OLD_TEST_PROFILE_NS = """        ns={'_io1591':rt,'capture_all_form_fields_v1583':lambda p:fields}
        extract({'final_profile_capture_v1583'},ns)
"""
NEW_TEST_PROFILE_NS = """        ns={'_io1591':rt,'capture_all_form_fields_v1583':lambda p:fields,
            'capture_form_fields_1591r19':lambda p:[],'re':__import__('re'),  # PROFILE_LABELS_1591R19
            '_SKIP_FIELD_TYPES_1591R19':{'checkbox','radio','hidden'},
            '_DATE_FIELD_RE_1591R19':__import__('re').compile(r'^\\d{2}[.\\-/]\\d{2}[.\\-/]\\d{4}$'),
            '_FIO_RE_1591R12':__import__('re').compile(r'^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\\-]{0,30}(\\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\\-]{0,30}){1,3}$')}
        extract({'final_profile_capture_v1583','_alias_hit_1591r19','_profile_fallback_1591r19'},ns)
"""
README_NOTE_R19 = '''

РЕВИЗИЯ 19 (fix_package_1591.py)
Данные профиля в SUCCESS-сообщении. Диагностика показала: на форме personal-data-form поля
ФИО, даты рождения и четыре адресных поля между «страна» и «дом» не имеют ни label[for], ни
name, ни id, ни осмысленного placeholder — подпись лежит в соседнем элементе. Захват
final_profile_capture_v1583 узнавал поля только по этим признакам, поэтому паспорт, страна,
дом и квартира попадали в отчёт, а ФИО, дата рождения, область, район, город и улица — нет.
Добавлен capture_form_fields_1591r19: к каждому полю записываются ближайший текст-подпись
(соседние элементы и родители) и data-/aria-/autocomplete-атрибуты; короткие алиасы («пол»,
«дом», «край») сравниваются как целые слова. Поля без подписи распознаются по форме значения
(ФИО, дата рождения с placeholder-датой) и по положению (четыре адресных поля между «страна»
и «дом»). Чекбоксы/radio/hidden в сопоставление не входят. Список полей с подписями пишется в
диагностику событием form_fields_1591r19. Сохранённый handler capture_all_form_fields_v1583
не менялся. Маркер: PROFILE_LABELS_1591R19.
'''
# Revision 20: a server outside Russia reaches Telegram directly. "proxy": "direct" (or none/off)
# in telegram_config.json means "no proxy on purpose": the code goes direct and the installer's
# r3 guard (which refuses an EMPTY proxy so the RU server never loses it by accident) accepts it.
PROXY_DIRECT_MARKER = "PROXY_DIRECT_1591R20"
TELEGRAM_DIRECT_PROXY_VALUES_SOURCE = "TELEGRAM_DIRECT_PROXY_VALUES = {\"direct\", \"none\", \"off\", \"no\", \"-\"}  # PROXY_DIRECT_1591R20: server outside RU\n"
OLD_PROXY_FN_DEF = "def telegram_http_proxies(cfg):\n"
NEW_PROXY_FN_DEF = TELEGRAM_DIRECT_PROXY_VALUES_SOURCE + "\n\n" + OLD_PROXY_FN_DEF
OLD_PROXY_EMPTY_CHECK = '''    ).strip()
    if not proxy:
        return None
    if "://" not in proxy:
'''
NEW_PROXY_EMPTY_CHECK = '''    ).strip()
    if not proxy or proxy.lower() in TELEGRAM_DIRECT_PROXY_VALUES:  # PROXY_DIRECT_1591R20
        return None
    if "://" not in proxy:
'''
README_NOTE_R20 = '''

РЕВИЗИЯ 20 (fix_package_1591.py)
Сервер вне России: Telegram доступен напрямую, прокси не нужен. В telegram_config.json
значение "proxy": "direct" (также none/off) означает «без прокси намеренно»: код идёт напрямую,
а защита установщика из ревизии 3 (пустой прокси по-прежнему отклоняется, чтобы российский
сервер не потерял его случайно) такое значение принимает. fresh_install.sh: на вопрос о прокси
можно ответить direct или просто Enter. Маркер: PROXY_DIRECT_1591R20.
'''
# Revision 21: the scheduled restart never relaunched. The automation exits with
# RESTART_EXIT_CODE (75) but xvfb-run (set -e, EXIT trap) reported 5 to the controller and left
# its Xvfb behind, so _restart_after_drain saw an "ordinary exit" and did nothing. Now the
# runtime writes restart_relaunch.json before exiting (and force-exits after 90 s if the normal
# shutdown hangs on child processes); the controller relaunches on the exit code OR on a fresh
# marker, remembers the last exit code even if reap() ran first, and kills the leftover
# process group (Xvfb) of the finished session.
RESTART_RELAUNCH_MARKER = "RESTART_RELAUNCH_1591R21"
OLD_CLEAR_DRAIN_R13 = """def clear_restart_drain(base_dir):
    try:
        (Path(base_dir) / RESTART_DRAIN_FILE_NAME).unlink()
    except FileNotFoundError:
        pass
"""
NEW_CLEAR_DRAIN_R21 = OLD_CLEAR_DRAIN_R13 + """

# RESTART_RELAUNCH_1591R21
RESTART_RELAUNCH_FILE_NAME = "restart_relaunch.json"
RESTART_EXIT_FORCE_SECONDS = 90


def request_relaunch(base_dir, reason=""):
    \"\"\"Ask the controller to start the automation again after this process exits.

    xvfb-run does not always pass RESTART_EXIT_CODE through, so the controller also looks at
    this marker. The timer forces the exit if the normal shutdown hangs on a child process.
    \"\"\"
    try:
        (Path(base_dir) / RESTART_RELAUNCH_FILE_NAME).write_text(
            json.dumps({"time": time.time(), "reason": str(reason)}, ensure_ascii=False), "utf-8"
        )
    except Exception as exc:
        print(f"[RESTART] Маркер перезапуска не записан: {type(exc).__name__}: {exc}", flush=True)
    import threading
    timer = threading.Timer(RESTART_EXIT_FORCE_SECONDS, lambda: os._exit(RESTART_EXIT_CODE))
    timer.daemon = True
    timer.start()
    return timer
"""
OLD_DRAIN_EXIT_R13 = """            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            raise SystemExit(RESTART_EXIT_CODE)
"""
NEW_DRAIN_EXIT_R21 = """            _restart_notify("♻️ Все worker завершили строки. Перезапускаю процесс.")
            request_relaunch(base_dir, "drain complete")  # RESTART_RELAUNCH_1591R21
            raise SystemExit(RESTART_EXIT_CODE)
"""
OLD_BROWSER_EXIT_R18 = """                    "Перезапускаю весь процесс."
                )
                raise SystemExit(RESTART_EXIT_CODE)
"""
NEW_BROWSER_EXIT_R21 = """                    "Перезапускаю весь процесс."
                )
                request_relaunch(base_dir, "chromium relaunch failed")  # RESTART_RELAUNCH_1591R21
                raise SystemExit(RESTART_EXIT_CODE)
"""
OLD_CTRL_RELAUNCH_R13 = """def _restart_after_drain(proc):
    \"\"\"Relaunch the automation that exited on purpose (RESTART_EXIT_CODE) after its drain.\"\"\"
    if proc.proc is None or proc.proc.poll() != app.RESTART_EXIT_CODE:
        return False
    proc.proc = None
    ok, answer = proc.start()
"""
NEW_CTRL_RELAUNCH_R21 = """RELAUNCH_MARKER_MAX_AGE = 600  # RESTART_RELAUNCH_1591R21: a marker older than this is stale


def _relaunch_marker_fresh(marker):
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    if age <= RELAUNCH_MARKER_MAX_AGE:
        return True
    try:
        marker.unlink()
    except OSError:
        pass
    return False


def _restart_after_drain(proc):
    \"\"\"Relaunch the automation that exited on purpose after its drain.

    RESTART_RELAUNCH_1591R21: the trigger is RESTART_EXIT_CODE from the process, the last code
    reap() recorded, or a fresh restart_relaunch.json written by the runtime before it exited
    (xvfb-run reported 5 instead of 75 on the server). A running process is never touched.
    \"\"\"
    if proc.running():
        return False
    marker = BASE_DIR / getattr(app, "RESTART_RELAUNCH_FILE_NAME", "restart_relaunch.json")
    code = proc.proc.poll() if proc.proc is not None else getattr(proc, "last_code", None)
    if code != app.RESTART_EXIT_CODE and not _relaunch_marker_fresh(marker):
        return False
    proc.reap()
    proc.last_code = None
    try:
        marker.unlink()
    except OSError:
        pass
    ok, answer = proc.start()
"""
OLD_CTRL_REAP = """    def reap(self):
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            self.proc = None
            print(f"[CTRL] automation завершилась code={code}", flush=True)
"""
NEW_CTRL_REAP_R21 = """    def reap(self):
        if self.proc is not None and self.proc.poll() is not None:
            code = self.proc.returncode
            pgid = self.proc.pid
            self.proc = None
            self.last_code = code  # RESTART_RELAUNCH_1591R21: kept for _restart_after_drain
            print(f"[CTRL] automation завершилась code={code}", flush=True)
            try:
                os.killpg(pgid, signal.SIGTERM)  # RESTART_RELAUNCH_1591R21: leftover Xvfb of that session
            except Exception:
                pass
"""
OLD_CTRL_INIT = """class AutomationProcess:
    def __init__(self):
        self.proc = None
"""
NEW_CTRL_INIT_R21 = """class AutomationProcess:
    def __init__(self):
        self.proc = None
        self.last_code = None  # RESTART_RELAUNCH_1591R21
"""
README_NOTE_R21 = """

РЕВИЗИЯ 21 (fix_package_1591.py)
Плановый перезапуск не выполнялся. Бот завершался с кодом RESTART_EXIT_CODE (75), но обёртка
xvfb-run (set -e и EXIT-trap) отдавала контроллеру код 5 и оставляла осиротевший Xvfb, поэтому
_restart_after_drain считал выход обычным и ничего не делал. Теперь перед выходом бот пишет
restart_relaunch.json (request_relaunch) и через 90 с принудительно завершается, если обычное
завершение зависло на дочерних процессах; контроллер перезапускает по коду выхода ИЛИ по
свежему маркеру (не старше 10 мин), помнит последний код даже если reap() сработал раньше, и
после завершения бота убивает остатки его группы процессов (Xvfb). Маркер: RESTART_RELAUNCH_1591R21.
"""
# Revision 22 (DeepSeek error report): (a) INVALID_ROW — the grey «Продолжить» was taken as the
# row's fault and the NEXT row was typed into the same used form (the same aggregateId across
# rows 257/258/259/265): now the row is retried once in a fresh tab, and after a second
# INVALID_ROW the next row also starts in a fresh tab; (b) rows skipped after registration/error
# were written to error_skipped_rows.txt but not to the progress file, so every scheduled
# restart put them back into the queue: both skip paths now record the row as processed.
ROW_SKIP_MARKER = "ROW_SKIP_PERSIST_1591R22"
OLD_RESET_STATE_DEF = "def reset_runtime_state(worker):\n"
INVALID_ROW_HELPERS_R22 = '''# ROW_SKIP_PERSIST_1591R22
INVALID_ROW_MAX_ATTEMPTS = 2


def _invalid_row_retry_1591r22(worker):
    """A grey «Продолжить» can be the form's stale state rather than the row's data (the same
    aggregateId was seen across many rows). Retry the row once in a fresh tab."""
    key = _error_row_key(worker)
    counts = worker.setdefault("invalid_row_counts", {})
    counts[key] = int(counts.get(key) or 0) + 1
    if counts[key] >= INVALID_ROW_MAX_ATTEMPTS:
        return False
    print(
        f"[Вкладка {worker['id']}] Строка {key}: «Продолжить» серая — повторяю её один раз в новой вкладке.",
        flush=True,
    )
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    set_tab_status(worker, "♻️", f"Строка {key}: форма не приняла данные; повтор в новой вкладке.")
    external_heartbeat(worker, "invalid_row_retry")
    return True


def _fresh_tab_for_next_row_1591r22(worker):
    """Skip the row; the next one starts in a fresh tab, never in the used form."""
    restart_same_row_in_new_page(worker)
    if worker.get("phase") != "RESTART_ROW_READY":
        return False
    reset_runtime_state(worker)
    worker["form_ready"] = False
    worker["phase"] = "IDLE"
    external_heartbeat(worker, "invalid_row_skipped")
    return True


'''
NEW_RESET_STATE_DEF = INVALID_ROW_HELPERS_R22 + OLD_RESET_STATE_DEF
OLD_FINISH_HEAD = '''    """Фиксирует результат и решает, можно ли этой вкладке брать следующую строку."""
    save_worker_result(base_dir, worker, status)

    if status == "INVALID_ROW":
        remember_processed_number(base_dir, worker.get("row"))
        worker["form_ready"] = True
        reset_runtime_state(worker)
        worker["phase"] = "IDLE"
        return
'''
NEW_FINISH_HEAD_R22 = '''    """Фиксирует результат и решает, можно ли этой вкладке брать следующую строку."""
    if status == "INVALID_ROW" and _invalid_row_retry_1591r22(worker):  # ROW_SKIP_PERSIST_1591R22
        return
    save_worker_result(base_dir, worker, status)

    if status == "INVALID_ROW":
        remember_processed_number(base_dir, worker.get("row"))
        if _fresh_tab_for_next_row_1591r22(worker):
            return
        worker["form_ready"] = True
        reset_runtime_state(worker)
        worker["phase"] = "IDLE"
        return
'''
OLD_R5_SKIP_TAIL = '''    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
'''
NEW_R5_SKIP_TAIL_R22 = '''    remember_processed_number(base_dir, worker.get("row"))  # ROW_SKIP_PERSIST_1591R22: not back after a restart
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена после повторной registration/error. Беру следующую.")
'''
OLD_R15_SKIP_TAIL = '''    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
'''
NEW_R15_SKIP_TAIL_R22 = '''    remember_processed_number(base_dir, worker.get("row"))  # ROW_SKIP_PERSIST_1591R22: not back after a restart
    worker["row"] = None
    worker["phase"] = "IDLE"
    set_tab_status(worker, "⏭", f"Строка {key} пропущена: {reason}. Беру следующую.")
'''
README_NOTE_R22 = '''

РЕВИЗИЯ 22 (fix_package_1591.py)
По отчёту DeepSeek об ошибках. (а) INVALID_ROW: серая кнопка «Продолжить» считалась виной
строки, а следующая строка вводилась в ту же использованную форму (один aggregateId у строк
257/258/259/265). Теперь строка один раз повторяется в новой вкладке (_invalid_row_retry_1591r22);
после второго INVALID_ROW она пропускается, и следующая строка тоже начинается в новой вкладке
(_fresh_tab_for_next_row_1591r22). (б) Строки, пропущенные после registration/error, писались в
error_skipped_rows.txt, но не в файл прогресса, и каждый плановый перезапуск возвращал их в
очередь: оба пути пропуска теперь вызывают remember_processed_number. Маркер: ROW_SKIP_PERSIST_1591R22.
'''
# Revision 23: the SUCCESS record and push carry only the frozen eSIM-offer URL, which the
# site redirects to its start page outside the original browser session. The page the worker
# is on when the success is recorded (the signed contract) is now saved too — its URL and its
# document-like links (contract, PDF, QR, download) — as "final_url"/"final_links" in
# successful_sims.jsonl and as extra lines of the #успешно push. Diagnostics keep 40 sessions
# instead of 5: with a restart every 20 minutes, 5 sessions covered only a few hours.
FINAL_PAGE_MARKER = "FINAL_PAGE_1591R23"
OLD_DIAG_KEEP = "DIAGNOSTIC_SESSIONS_TO_KEEP = 5\n"
NEW_DIAG_KEEP = "DIAGNOSTIC_SESSIONS_TO_KEEP = 40  # FINAL_PAGE_1591R23: restarts every 20 min made 5 sessions a few hours\n"
OLD_WRITE_SUCCESS_HEAD = '''def write_success_record(base_dir, worker):
    n,a,b=row_parts(worker.get("row"))
    rec={
'''
FINAL_PAGE_HELPERS_R23 = r'''# FINAL_PAGE_1591R23
_FINAL_LINKS_JS_1591R23 = r"""() => {
  const out = [];
  const seen = new Set();
  const want = /договор|pdf|скачать|qr|esim|e-sim|загруз|документ|contract|download|профил|оплат|pay/i;
  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
  for (const el of document.querySelectorAll('a[href], [data-href], button[formaction]')) {
    const href = el.href || el.getAttribute('data-href') || el.getAttribute('formaction') || '';
    const text = clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('download'));
    if (!href || href.startsWith('javascript:') || seen.has(href)) continue;
    if (!(want.test(text) || want.test(href))) continue;
    seen.add(href);
    out.push({text: text.slice(0, 80), href: href.slice(0, 500)});
    if (out.length >= 8) break;
  }
  for (const img of document.querySelectorAll('img')) {
    const alt = clean(img.alt), src = String(img.src || '');
    if (!(/qr/i.test(alt) || /qr/i.test(src))) continue;
    out.push(src.startsWith('data:') ? {text: 'QR-код на странице (встроенное изображение)', href: ''}
                                     : {text: 'QR-код: ' + (alt || 'изображение'), href: src.slice(0, 500)});
    if (out.length >= 10) break;
  }
  let text = '';
  try { text = String((document.body && document.body.innerText) || ''); } catch (_) {}
  return {links: out, title: String(document.title || ''), text: text.slice(0, 20000)};
}"""


def capture_final_page_1591r23(page, worker=None):
    """URL of the page the worker is on when the success is recorded (the signed contract)
    plus its document-like links: contract, PDF, QR, download. Read-only."""
    result = {"url": "", "title": "", "links": []}
    if page is None:
        return result
    try:
        result["url"] = str(page.url or "")
    except Exception:
        pass
    text = ""
    try:
        data = page.evaluate(_FINAL_LINKS_JS_1591R23)
        if isinstance(data, dict):
            result["links"] = [x for x in (data.get("links") or []) if isinstance(x, dict)][:10]
            result["title"] = str(data.get("title") or "")[:200]
            text = str(data.get("text") or "")
    except Exception:
        pass
    if worker is not None:
        worker["final_url"] = result["url"]
        worker["final_title"] = result["title"]
        worker["final_links"] = result["links"]
        try:
            diagnostic = worker.get("diagnostic")
            if diagnostic:
                diagnostic.write("final_page_1591r23", url=result["url"], title=result["title"],
                                 links=result["links"], text=text[:20000])
        except Exception:
            pass
    return result


def _final_links_lines_1591r23(links):
    out = []
    for item in (links or [])[:10]:
        text = str((item or {}).get("text") or "").strip() or "документ"
        href = str((item or {}).get("href") or "").strip()
        out.append(f"{text}: {href}" if href else text)
    return out


'''
NEW_WRITE_SUCCESS_HEAD = FINAL_PAGE_HELPERS_R23 + '''def write_success_record(base_dir, worker):
    n,a,b=row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)  # FINAL_PAGE_1591R23
    rec={
'''
OLD_REC_PROFILE = '''        "profile":dict(worker.get("success_profile") or {}),
    }
'''
NEW_REC_PROFILE = '''        "profile":dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "",  # FINAL_PAGE_1591R23
        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
    }
'''
OLD_SUCCESS_TAIL = '''        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
    ])
'''
NEW_SUCCESS_TAIL = '''        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        f"Страница договора: {rec.get('final_url') or '—'}",  # FINAL_PAGE_1591R23
        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
    ])
'''
README_NOTE_R23 = '''

РЕВИЗИЯ 23 (fix_package_1591.py)
Ссылка в записи об успехе — намеренно замороженный адрес страницы предложения eSIM, который вне
исходной сессии браузера сайт перенаправляет на начальную страницу. Теперь при фиксации успеха
сохраняется и страница, на которой стоит worker (подписанный договор): её адрес и ссылки на
документы (договор, PDF, QR, скачивание) — поля final_url/final_links в successful_sims.jsonl и
строки «Страница договора: …» и список документов в сообщении #успешно
(capture_final_page_1591r23); заголовок и текст финальной страницы пишутся в диагностику событием
final_page_1591r23, чтобы отличить подписанный договор от начальной страницы сайта.
Число хранимых сессий диагностики увеличено с 5 до 40: при
перезапуске каждые 20 минут 5 сессий покрывали лишь несколько часов. Маркер: FINAL_PAGE_1591R23.
'''
# Revision 24: a vanished «Подписать договор» button was the only success criterion, so a
# failed second signing attempt (button gone, TimeoutError) was recorded as a success within
# the same second (rows 5 and 134 on the second server; the eSIM links led to the start page).
# Success now needs positive evidence on the page (URL, text or a document link); without it
# the tab is held for UNVERIFIED_HOLD_SECONDS with DeepSeek asked to inspect, then recorded
# as UNVERIFIED: unverified_signatures.jsonl, a #неподтверждено push, the tab left open, the
# number NOT marked as processed.
SIGNED_MARKER = "SIGNED_EVIDENCE_1591R24"
OLD_SIGN_WAIT_DEF = "def tick_sign_wait(base_dir, worker):\n"
SIGNED_HELPERS_R24 = '''# SIGNED_EVIDENCE_1591R24
SIGNED_URL_HINTS_1591R24 = ("success", "complete", "done", "thank", "activation", "signed", "esim/ready")
SIGNED_TEXT_NEEDLES_1591R24 = (
    "договор подписан", "успешно подписан", "подписание завершено", "договор успешно",
    "договор отправлен", "спасибо за", "esim готова", "esim активирована", "qr-код", "скачать договор",
)
UNVERIFIED_HOLD_SECONDS = 180


def _signed_evidence_1591r24(page):
    """A positive sign of a signed contract on the page; a vanished button is not one."""
    try:
        url = str(page.url or "").lower()
    except Exception:
        url = ""
    if "personal-data" in url or "mobile-id" in url:
        return ""
    for hint in SIGNED_URL_HINTS_1591R24:
        if hint in url:
            return f"url:{hint}"
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "").lower()
    except Exception:
        body = ""
    for needle in SIGNED_TEXT_NEEDLES_1591R24:
        if needle in body:
            return f"text:{needle}"
    try:
        if page.locator("a[href$='.pdf'], a[download]").count():
            return "link:document"
    except Exception:
        pass
    return ""


def _unverified_message_1591r24(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    return "\\n".join([
        "#неподтверждено",
        f"⚠️ ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        f"Причина: {rec.get('reason') or '—'}",
        f"Страница: {rec.get('final_url') or '—'}",
        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        "",
        *_success_profile_lines(rec.get("profile")),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        "Номер НЕ помечен обработанным; вкладка оставлена открытой для проверки.",
    ])


def _finish_unverified_1591r24(base_dir, worker, reason):
    """The signing could not be confirmed: record it apart from the successes and stop the tab."""
    n, a, b = row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)
    rec = {
        "tab": worker["id"], "row": n, "active_digits": a, "second_value": b,
        "sim_number": worker.get("reserved_sim_number"), "sim_url": worker.get("reserved_sim_url"),
        "profile": dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "", "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with (Path(base_dir) / "unverified_signatures.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    except Exception as exc:
        print(f"[Вкладка {worker['id']}] unverified_signatures.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    worker["phase"] = "SUCCESS_STOP"
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_unverified_message_1591r24(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить UNVERIFIED в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(
        worker, "⚠️",
        f"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\\n{reason}\\nСтраница: {rec['final_url'] or '—'}\\n"
        "Вкладка оставлена открытой. Для очереди будет создана новая.",
    )
    external_heartbeat(worker, "success_unverified_stop")
    print(
        f"\\n[Вкладка {worker['id']}] ⚠️ ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА. Строка {n}: {reason}. "
        "Номер не помечен обработанным; вкладка оставлена открытой.\\n",
        flush=True,
    )
    worker["stopped"] = True
    return rec


def settle_success_1591r24(base_dir, worker):
    """Called where the code used to declare success because no contract controls remained.

    With positive evidence the success is final (finalize_success). Without it the tab is
    held in SUCCESS_ASSIST for UNVERIFIED_HOLD_SECONDS (DeepSeek inspects, the button may
    reappear and be signed again), then the row is recorded as UNVERIFIED.
    """
    page = worker.get("page")
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
        worker["success_evidence"] = evidence
        finalize_success(base_dir, worker)
        return True
    now = monotonic()
    since = worker.get("success_unverified_since")
    url = ""
    try:
        url = str(page.url or "") if page is not None else ""
    except Exception:
        pass
    if since is None:
        worker["success_unverified_since"] = now
        try:
            capture_blackbox(worker, "success_unverified")
        except Exception:
            pass
        worker["phase"] = "SUCCESS_ASSIST"
        set_tab_status(
            worker, "⚠️",
            "Кнопка «Подписать договор» пропала, но признаков подписанного договора нет. "
            f"Держу вкладку {UNVERIFIED_HOLD_SECONDS // 60} мин, DeepSeek проверяет.",
        )
        external_heartbeat(worker, "success_unverified_hold")
        queue_success_assist(
            worker,
            "кнопка «Подписать договор» исчезла, но страница не похожа на подписанный договор: "
            f"проверь, подписан ли он, и что показано вместо кнопки (URL: {url})",
            force=True,
        )
        return False
    if now - since < UNVERIFIED_HOLD_SECONDS:
        worker["phase"] = "SUCCESS_ASSIST"
        return False
    _finish_unverified_1591r24(
        base_dir, worker,
        f"после «Подписать договор» страница {UNVERIFIED_HOLD_SECONDS // 60} мин не показала признаков подписания (URL: {url or '—'})",
    )
    return False


'''
NEW_SIGN_WAIT_DEF = SIGNED_HELPERS_R24 + OLD_SIGN_WAIT_DEF
OLD_SIGN_WAIT_FINAL = '''        if now - gone_since >= 1.2:
            finalize_success(base_dir, worker)
        return
'''
NEW_SIGN_WAIT_FINAL = '''        if now - gone_since >= 1.2:
            settle_success_1591r24(base_dir, worker)  # SIGNED_EVIDENCE_1591R24
        return
'''
OLD_REVIEW_FINAL = '''    # If we are post-auth and no contract controls remain, settle as success.
    finalize_success(base_dir, worker)
'''
NEW_REVIEW_FINAL = '''    # If we are post-auth and no contract controls remain, settle as success — only with
    # positive evidence of the signed contract (SIGNED_EVIDENCE_1591R24).
    settle_success_1591r24(base_dir, worker)
'''
README_NOTE_R24 = '''

РЕВИЗИЯ 24 (fix_package_1591.py)
Ложный успех подписи. Единственным признаком успеха было исчезновение кнопки «Подписать
договор»: на втором сервере строки 5 и 134 после неудачной второй попытки подписи (кнопка
пропала, TimeoutError) в ту же секунду записывались как успех, а ссылки eSIM вели на начальную
страницу. Теперь успех требует положительного признака на странице (_signed_evidence_1591r24:
адрес, текст или ссылка на документ). Без него settle_success_1591r24 держит вкладку
UNVERIFIED_HOLD_SECONDS (3 мин) в SUCCESS_ASSIST со снимком и задачей DeepSeek, затем пишет
строку в unverified_signatures.jsonl, шлёт в Telegram #неподтверждено с адресом, заголовком и
ссылками финальной страницы, оставляет вкладку открытой и НЕ помечает номер обработанным.
Заменены оба места фиксации успеха: tick_sign_wait и tick_post_auth_review. Маркер:
SIGNED_EVIDENCE_1591R24.
'''
# Revision 25: WHY the signing does not happen is not recorded anywhere — the click on
# «Подписать договор» leaves no trace of the server's answer. Around the click the page's
# responses (status, JSON/error bodies), failed requests and console errors are now collected
# for SIGN_TRACE_SECONDS, written to diagnostics (sign_click_trace_1591r25, plus a blackbox
# snapshot after the click), summarised into the success / unverified records and shown in
# the #неподтверждено push. Also: profile values without a letter or digit (a lone «.») are
# no longer accepted by the label matcher (the «Область: .» case).
SIGN_TRACE_MARKER = "SIGN_TRACE_1591R25"
OLD_SIGN_CALL_R14 = '''            capture_contract_details(page, worker)
            fill_signature_and_submit(page, worker.get("diagnostic"))
            worker["phase"] = "SIGN_WAIT"
'''
NEW_SIGN_CALL_R25 = '''            capture_contract_details(page, worker)
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["phase"] = "SIGN_WAIT"
'''
OLD_SIGN_WAIT_DEF_R24 = "# SIGNED_EVIDENCE_1591R24\nSIGNED_URL_HINTS_1591R24 = "
SIGN_TRACE_HELPERS_R25 = '''# SIGN_TRACE_1591R25
SIGN_TRACE_SECONDS = 8
_SIGN_TRACE_SKIP_RE_1591R25 = re.compile(
    r"\\.(png|jpe?g|gif|svg|webp|css|js|woff2?|ttf|ico)(\\?|$)|metrika|analytics|google|flocktory|yandex|gtm",
    re.I,
)


def _sign_trace_begin_1591r25(page, worker):
    """Start collecting what the page does right after «Подписать договор» is clicked."""
    trace = {"started": time.time(), "url_before": "", "responses": [], "failed": [], "console": [],
             "_pending": [], "_handlers": {}}
    try:
        trace["url_before"] = str(page.url or "")
    except Exception:
        pass

    def on_response(resp):
        try:
            url = str(resp.url or "")
            if _SIGN_TRACE_SKIP_RE_1591R25.search(url) or len(trace["responses"]) >= 40:
                return
            item = {"t": round(time.time() - trace["started"], 2), "method": str(resp.request.method),
                    "status": int(resp.status), "url": url[:300]}
            trace["responses"].append(item)
            ctype = str(resp.headers.get("content-type", "") or "")
            if "json" in ctype or item["status"] >= 400 or item["method"] in ("POST", "PUT", "PATCH"):
                trace["_pending"].append((resp, item))
        except Exception:
            pass

    def on_failed(req):
        try:
            if len(trace["failed"]) < 20 and not _SIGN_TRACE_SKIP_RE_1591R25.search(str(req.url or "")):
                trace["failed"].append({"t": round(time.time() - trace["started"], 2), "url": str(req.url)[:300],
                                        "error": str(req.failure or "")[:200]})
        except Exception:
            pass

    def on_console(msg):
        try:
            if msg.type in ("error", "warning") and len(trace["console"]) < 30:
                trace["console"].append({"t": round(time.time() - trace["started"], 2), "type": str(msg.type),
                                         "text": str(msg.text)[:300]})
        except Exception:
            pass

    for event, fn in (("response", on_response), ("requestfailed", on_failed), ("console", on_console)):
        try:
            page.on(event, fn)
            trace["_handlers"][event] = fn
        except Exception:
            pass
    worker["sign_trace"] = trace
    return trace


def _sign_trace_end_1591r25(page, worker, note=""):
    """Wait SIGN_TRACE_SECONDS after the click, read the bodies, record the trace."""
    trace = worker.get("sign_trace")
    if not trace or "_handlers" not in trace:
        return trace
    deadline = monotonic() + SIGN_TRACE_SECONDS
    while monotonic() < deadline:
        try:
            page.wait_for_timeout(250)
        except Exception:
            break
    for event, fn in (trace.pop("_handlers", None) or {}).items():
        try:
            page.remove_listener(event, fn)
        except Exception:
            pass
    for resp, item in trace.pop("_pending", None) or []:
        try:
            item["body"] = re.sub(r"\\s+", " ", str(resp.text() or ""))[:1500]
        except Exception as exc:
            item["body_error"] = f"{type(exc).__name__}"
    try:
        trace["url_after"] = str(page.url or "")
    except Exception:
        trace["url_after"] = ""
    trace["note"] = str(note or "")
    try:
        diagnostic = worker.get("diagnostic")
        if diagnostic:
            diagnostic.write("sign_click_trace_1591r25", **{k: v for k, v in trace.items() if not k.startswith("_")})
    except Exception:
        pass
    try:
        capture_blackbox(worker, "after_sign_click")
    except Exception:
        pass
    print(
        f"[Вкладка {worker.get('id')}] SIGN TRACE: {trace['url_before']} -> {trace['url_after']}; "
        f"ответов {len(trace['responses'])}, сбоев сети {len(trace['failed'])}, console {len(trace['console'])}",
        flush=True,
    )
    return trace


def _sign_trace_summary_1591r25(trace):
    if not trace:
        return None
    keep = [r for r in trace.get("responses") or []
            if int(r.get("status") or 0) >= 400 or "body" in r or r.get("method") in ("POST", "PUT", "PATCH")]
    return {"url_before": trace.get("url_before") or "", "url_after": trace.get("url_after") or "",
            "responses": keep[:12], "failed": (trace.get("failed") or [])[:10], "console": (trace.get("console") or [])[:10]}


def _sign_trace_lines_1591r25(summary):
    if not summary:
        return []
    out = [f"Подпись: {summary.get('url_before') or '—'} → {summary.get('url_after') or '—'}"]
    for r in (summary.get("responses") or [])[:6]:
        line = f"  {r.get('method')} {r.get('url')} → {r.get('status')}"
        if r.get("body"):
            line += " " + str(r["body"])[:160]
        out.append(line)
    for f in (summary.get("failed") or [])[:3]:
        out.append(f"  сеть: {f.get('url')} — {f.get('error')}")
    for c in (summary.get("console") or [])[:3]:
        out.append(f"  console {c.get('type')}: {c.get('text')}")
    return out


'''
NEW_SIGN_WAIT_DEF_R25 = SIGN_TRACE_HELPERS_R25 + OLD_SIGN_WAIT_DEF_R24
OLD_UNVERIFIED_REC_R24 = '''        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
'''
NEW_UNVERIFIED_REC_R25 = '''        "final_links": list(final.get("links") or []), "reason": str(reason or ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),  # SIGN_TRACE_1591R25
    }
'''
OLD_UNVERIFIED_MSG_R24 = '''        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        "",
        *_success_profile_lines(rec.get("profile")),
'''
NEW_UNVERIFIED_MSG_R25 = '''        f"Заголовок страницы: {rec.get('final_title') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        *_sign_trace_lines_1591r25(rec.get("sign_trace")),  # SIGN_TRACE_1591R25
        "",
        *_success_profile_lines(rec.get("profile")),
'''
OLD_SUCCESS_REC_R23 = '''        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
    }
'''
NEW_SUCCESS_REC_R25 = '''        "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),  # SIGN_TRACE_1591R25
    }
'''
OLD_MATCH_SKIP_R19 = '''        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
'''
NEW_MATCH_SKIP_R25 = '''        if not value or str(f.get("type") or "").lower() in _SKIP_FIELD_TYPES_1591R19:
            continue
        if not re.search(r"[0-9a-zа-яё]", value.lower()):  # SIGN_TRACE_1591R25: a lone «.» is not a value
            continue
'''
README_NOTE_R25 = '''

РЕВИЗИЯ 25 (fix_package_1591.py)
Почему подпись не проходит, было нечем установить: нажатие «Подписать договор» не оставляло
следа ответа сервера. Теперь вокруг нажатия SIGN_TRACE_SECONDS (8 с) собираются ответы страницы
(метод, статус, тела JSON и ошибок), сбои сети и ошибки console; всё пишется в диагностику
событием sign_click_trace_1591r25 и снимком after_sign_click, краткая выжимка попадает в записи
successful_sims.jsonl / unverified_signatures.jsonl (поле sign_trace) и в сообщение
#неподтверждено строками «Подпись: адрес → адрес» и ответами сервера. Строка
«[Вкладка N] SIGN TRACE: …» в журнале читается tools/sign_timeline.py. Значения профиля без
буквы или цифры (одиночная точка) больше не принимаются. Маркер: SIGN_TRACE_1591R25.
'''
# Revision 26: the "false successes" were the site's PAYMENT step. After «Подписать договор»
# the signature is accepted (checksignature 200, sendpassportdata… 202) and the page becomes
# «порядок, идём дальше → теперь пора оплатить eSIM … оплатите картой → дождитесь регистрации
# договора». The contract is registered only after payment; the runtime never knew the step
# and recorded a success. The payment page is now its own outcome: payment_required.jsonl,
# a #оплата push, the tab left open, the number marked as processed (no second order).
PAYMENT_MARKER = "PAYMENT_STEP_1591R26"
OLD_SETTLE_DEF_R24 = '''def settle_success_1591r24(base_dir, worker):
    """Called where the code used to declare success because no contract controls remained.
'''
PAYMENT_HELPERS_R26 = '''# PAYMENT_STEP_1591R26
PAYMENT_NEEDLES_1591R26 = (
    "пора оплатить", "оплатить картой", "оплатите картой", "дождитесь регистрации договора",
    "оплата esim", "оплатить esim", "к оплате",
)


def _payment_page_1591r26(page):
    """Text of the payment step when the site asks to pay for the eSIM after the signature."""
    try:
        body = (page.locator("body").inner_text(timeout=1500) or "")
    except Exception:
        return ""
    low = body.lower()
    for needle in PAYMENT_NEEDLES_1591R26:
        if needle in low:
            start = max(0, low.index(needle) - 120)
            return re.sub(r"\\s+", " ", body[start:start + 360]).strip()
    return ""


def _payment_message_1591r26(worker, rec):
    row_no, active_value, second_value = row_parts(worker.get("row"))
    return "\\n".join([
        "#оплата",
        f"💳 ТРЕБУЕТСЯ ОПЛАТА eSIM — Вкладка {worker['id']}",
        f"Строка: {row_no}/{worker.get('total_rows') or '?'}",
        f"Исходные данные: {active_value} | {second_value}",
        "Подпись принята сайтом; договор регистрируется только после оплаты картой.",
        f"Текст шага: {rec.get('payment_text') or '—'}",
        f"Страница: {rec.get('final_url') or '—'}",
        *_final_links_lines_1591r23(rec.get("final_links")),
        *_sign_trace_lines_1591r25(rec.get("sign_trace")),
        "",
        *_success_profile_lines(rec.get("profile")),
        "",
        f"eSIM: {rec.get('sim_number') or '—'}",
        f"Ссылка eSIM: {rec.get('sim_url') or '—'}",
        "Номер помечен обработанным (повтор создал бы второй заказ); вкладка оставлена открытой.",
    ])


def _finish_payment_required_1591r26(base_dir, worker, payment_text):
    """The site wants the eSIM paid: record it apart from the successes and stop the tab."""
    n, a, b = row_parts(worker.get("row"))
    final = capture_final_page_1591r23(worker.get("page"), worker)
    rec = {
        "tab": worker["id"], "row": n, "active_digits": a, "second_value": b,
        "sim_number": worker.get("reserved_sim_number"), "sim_url": worker.get("reserved_sim_url"),
        "profile": dict(worker.get("success_profile") or {}),
        "final_url": final.get("url") or "", "final_title": final.get("title") or "",
        "final_links": list(final.get("links") or []), "payment_text": str(payment_text or ""),
        "sign_trace": _sign_trace_summary_1591r25(worker.get("sign_trace")),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with (Path(base_dir) / "payment_required.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    except Exception as exc:
        print(f"[Вкладка {worker['id']}] payment_required.jsonl не записан: {type(exc).__name__}: {exc}", flush=True)
    remember_processed_number(base_dir, worker.get("row"))
    worker["phase"] = "SUCCESS_STOP"
    success_queue = worker.get("success_queue")
    if success_queue is not None:
        try:
            success_queue.put(_payment_message_1591r26(worker, rec))
        except Exception as exc:
            print(f"[Telegram] Не удалось поставить PAYMENT в очередь: {type(exc).__name__}: {exc}", flush=True)
    set_tab_status(
        worker, "💳",
        f"ТРЕБУЕТСЯ ОПЛАТА eSIM\\n{rec['payment_text'][:160]}\\nСтраница: {rec['final_url'] or '—'}\\n"
        "Вкладка оставлена открытой. Для очереди будет создана новая.",
    )
    external_heartbeat(worker, "payment_required_stop")
    print(
        f"\\n[Вкладка {worker['id']}] 💳 ТРЕБУЕТСЯ ОПЛАТА. Строка {n}: подпись принята, договор регистрируется "
        "после оплаты картой. Номер помечен обработанным; вкладка оставлена открытой.\\n",
        flush=True,
    )
    worker["stopped"] = True
    return rec


'''
NEW_SETTLE_DEF_R26 = PAYMENT_HELPERS_R26 + OLD_SETTLE_DEF_R24
OLD_SETTLE_HEAD_R24 = '''    page = worker.get("page")
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
'''
NEW_SETTLE_HEAD_R26 = '''    page = worker.get("page")
    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26
    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
'''
README_NOTE_R26 = '''

РЕВИЗИЯ 26 (fix_package_1591.py)
«Ложные успехи» оказались шагом оплаты сайта. После «Подписать договор» подпись принимается
(checksignature 200, sendpassportdata… 202), а страница становится «порядок, идём дальше → теперь
пора оплатить eSIM … оплатите картой → дождитесь регистрации договора»: договор регистрируется
только после оплаты, код этого шага не знал и записывал успех. Теперь страница оплаты — отдельный
исход (_payment_page_1591r26 / _finish_payment_required_1591r26): запись в payment_required.jsonl,
сообщение #оплата с текстом шага, адресом, ссылками, ответами сервера и профилем, вкладка остаётся
открытой, номер помечается обработанным (повтор создал бы второй заказ). Проверяется до признаков
успеха в settle_success_1591r24. Маркер: PAYMENT_STEP_1591R26.
'''
# Revision 27: Telegram banned the bot for hours (429, retry after 16123 s). The status logger
# edited four tab messages as often as every second, ignored retry_after and kept retrying
# every second (which is how the ban grew), and every scheduled restart created four new
# messages. Now: one global gap between Bot API calls, at most one edit per tab per
# TG_STATUS_MIN_EDIT_GAP, a full stop for retry_after, status messages reused across restarts
# (telegram_status_messages.json), and the logger keeps running instead of giving up when the
# messages cannot be created at start.
TG_RATE_MARKER = "TG_RATE_1591R27"
OLD_LOGGER_DEF = "def telegram_logger_process(status_map, success_queue, stop_event):\n"
TG_RATE_HELPERS_R27 = '''# TG_RATE_1591R27
TG_MIN_CALL_GAP_1591R27 = 1.5
TG_STATUS_MIN_EDIT_GAP_1591R27 = 6.0


def _tg_status_file_1591r27():
    return TELEGRAM_CONFIG_FILE.with_name("telegram_status_messages.json")


def _tg_call_1591r27(cfg, method, payload, state):
    """One rate-limited Bot API call of the status logger: a global gap between calls and a
    full stop for retry_after when Telegram answers 429 (retrying every second grew the ban)."""
    now = time.time()
    if now < float(state.get("pause_until") or 0):
        return None, "paused"
    gap = TG_MIN_CALL_GAP_1591R27 - (now - float(state.get("last_call") or 0))
    if gap > 0:
        time.sleep(gap)
    state["last_call"] = time.time()
    r, err = telegram_api(cfg, method, payload)
    retry_after = getattr(err, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        state["pause_until"] = time.time() + float(retry_after) + 1
        print(f"[Telegram] 429: Telegram просит паузу {int(retry_after)} с — статусы не трогаю до её конца.", flush=True)
    return r, err


def _tg_status_messages_load_1591r27(chat):
    try:
        data = json.loads(_tg_status_file_1591r27().read_text("utf-8"))
        if str(data.get("chat")) == str(chat):
            return {int(k): int(v) for k, v in (data.get("mids") or {}).items()}
    except Exception:
        pass
    return {}


def _tg_status_messages_save_1591r27(chat, mids):
    try:
        _tg_status_file_1591r27().write_text(
            json.dumps({"chat": str(chat), "mids": {str(k): v for k, v in mids.items()}}), "utf-8"
        )
    except Exception:
        pass


def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):
    """Create the missing status messages and push the changed texts, within the limits."""
    changed = False
    for i in range(1, TAB_COUNT + 1):
        if i in mids:
            continue
        r, err = _tg_call_1591r27(
            cfg, "sendMessage",
            {"chat_id": chat, "text": f"⏳ Вкладка {i}\\nСтатус: запуск...", "disable_web_page_preview": "true"},
            state,
        )
        if r:
            mids[i] = r["result"]["message_id"]
            last[i] = ""
            changed = True
            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)
        else:
            if err != "paused":
                print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)
            break
    if changed:
        _tg_status_messages_save_1591r27(chat, mids)
    now = time.time()
    for i, mid in list(mids.items()):
        info = status_map.get(str(i))
        t = str((info or {}).get("text", ""))
        if not t or t == last.get(i) or now - float(edited_at.get(i) or 0) < TG_STATUS_MIN_EDIT_GAP_1591R27:
            continue
        r, err = _tg_call_1591r27(
            cfg, "editMessageText",
            {"chat_id": chat, "message_id": mid, "text": t[:4000], "disable_web_page_preview": "true"},
            state,
        )
        edited_at[i] = time.time()
        if r:
            last[i] = t
            continue
        if err == "paused":
            break
        low = str(err).lower()
        if "message is not modified" in low:
            last[i] = t
        elif "not found" in low or "can't be edited" in low or "message_id_invalid" in low:
            mids.pop(i, None)
            _tg_status_messages_save_1591r27(chat, mids)
            print(f"[Telegram] Сообщение вкладки {i} исчезло — создам новое.", flush=True)
        else:
            print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)


'''
NEW_LOGGER_DEF = TG_RATE_HELPERS_R27 + OLD_LOGGER_DEF
OLD_LOGGER_STATE = '''    mids, last = {}, {}

    print("[Telegram] Логгер запущен.", flush=True)
'''
NEW_LOGGER_STATE = '''    mids, last = {}, {}
    state, edited_at = {"pause_until": 0.0, "last_call": 0.0}, {}  # TG_RATE_1591R27

    print("[Telegram] Логгер запущен.", flush=True)
'''
OLD_LOGGER_CREATE = '''    for i in range(1, TAB_COUNT + 1):
        t = f"⏳ Вкладка {i}\\nСтатус: запуск..."
        r, err = telegram_api(
            cfg, "sendMessage",
            {"chat_id": chat, "text": t, "disable_web_page_preview": "true"},
        )
        if r:
            mids[i] = r["result"]["message_id"]
            last[i] = t
            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)
        else:
            print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)

    if not mids:
        print(
            "[Telegram] Не удалось создать ни одного сообщения. "
            "Основной сценарий продолжит работать без Telegram.",
            flush=True,
        )
        return

'''
NEW_LOGGER_CREATE = '''    # TG_RATE_1591R27: reuse the status messages of the previous run instead of four new ones
    # per restart; each is verified by an edit and recreated only when Telegram says it is gone.
    for i, mid in _tg_status_messages_load_1591r27(chat).items():
        r, err = _tg_call_1591r27(
            cfg, "editMessageText",
            {"chat_id": chat, "message_id": mid, "text": f"⏳ Вкладка {i}\\nСтатус: перезапуск...",
             "disable_web_page_preview": "true"},
            state,
        )
        if r or err == "paused" or "not modified" in str(err or "").lower():
            mids[i] = mid
            last[i] = ""
    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)
    if not mids:
        print(
            "[Telegram] Статусные сообщения пока не созданы (лимит Telegram) — попробую позже; "
            "основной сценарий работает.",
            flush=True,
        )

'''
OLD_LOGGER_EDIT = '''        for i, mid in list(mids.items()):
            info = status_map.get(str(i))
            t = str((info or {}).get("text", ""))
            if t and t != last.get(i):
                r, err = telegram_api(
                    cfg, "editMessageText",
                    {
                        "chat_id": chat,
                        "message_id": mid,
                        "text": t[:4000],
                        "disable_web_page_preview": "true",
                    },
                )
                if r:
                    last[i] = t
                elif err and "message is not modified" not in err.lower():
                    print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)
        time.sleep(1)
'''
NEW_LOGGER_EDIT = '''        _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)  # TG_RATE_1591R27
        time.sleep(1)
'''
README_NOTE_R27 = '''

РЕВИЗИЯ 27 (fix_package_1591.py)
Telegram заблокировал бота на часы (429 Too Many Requests, retry after 16123 с). Логгер статусов
редактировал четыре сообщения вкладок хоть каждую секунду, не учитывал retry_after и продолжал
долбить каждую секунду (так штраф и вырос), а каждый плановый перезапуск создавал четыре новых
сообщения. Теперь: общий интервал между вызовами Bot API (TG_MIN_CALL_GAP_1591R27 = 1,5 с), не
чаще одной правки на вкладку в TG_STATUS_MIN_EDIT_GAP_1591R27 (6 с), полная пауза на retry_after,
статусные сообщения переиспользуются между перезапусками (telegram_status_messages.json), а если
их не удалось создать на старте, логгер не сдаётся и пробует позже. Маркер: TG_RATE_1591R27.
'''
# Revision 28: two Chromium instances with four tabs each (8 worker tabs). While four tabs
# wait up to 6.5 minutes for a mobile-id confirmation the other four keep the pipeline busy;
# a hung Chromium (r18) or a crash now takes down half the tabs, not all. Captchas of
# different tabs no longer pile up on the CPU: at most CAPTCHA_PARALLEL_MAX are solved at the
# same time, the other tabs wait for a slot and report CAPTCHA_WAIT so the watchdog does not
# take the wait for a stall.
TWO_BROWSERS_MARKER = "TWO_BROWSERS_1591R28"
OLD_BROWSER_COUNT = "BROWSER_COUNT = 1\n"
NEW_BROWSER_COUNT = '''# TWO_BROWSERS_1591R28
CAPTCHA_PARALLEL_MAX = 2            # captchas solved at the same time across all tabs
CAPTCHA_GATE_WAIT_SECONDS = 180     # longest wait for a slot; then the tab solves anyway
_CAPTCHA_GATE = None                # multiprocessing semaphore, set in each worker process

_try_local_captcha_unlocked = try_local_captcha


def try_local_captcha(page, frame_box=None):
    """Captchas of different tabs overlap at most CAPTCHA_PARALLEL_MAX at a time: a tab waits
    for a slot and reports CAPTCHA_WAIT to the watchdog meanwhile."""
    gate = _CAPTCHA_GATE
    if gate is None:
        return _try_local_captcha_unlocked(page, frame_box)
    from local_matcher import matcher_progress as _matcher_progress
    acquired = False
    deadline = monotonic() + CAPTCHA_GATE_WAIT_SECONDS
    try:
        while not acquired and monotonic() < deadline:
            acquired = bool(gate.acquire(timeout=5))
            if not acquired:
                try:
                    _matcher_progress("CAPTCHA_WAIT")
                except Exception:
                    pass
        return _try_local_captcha_unlocked(page, frame_box)
    finally:
        if acquired:
            try:
                gate.release()
            except Exception:
                pass


BROWSER_COUNT = 2  # TWO_BROWSERS_1591R28: two Chromium instances, TABS_PER_BROWSER tabs each
'''
OLD_TAB_PROCESS_DEF = "def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None):\n"
NEW_TAB_PROCESS_DEF = "def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28\n"
OLD_CONFIGURE_MATCHER = "        configure_matcher_runtime(tab_id=tab_id, heartbeat=heartbeat)\n"
NEW_CONFIGURE_MATCHER = '''        configure_matcher_runtime(tab_id=tab_id, heartbeat=heartbeat)
        global _CAPTCHA_GATE
        _CAPTCHA_GATE = captcha_gate  # TWO_BROWSERS_1591R28
'''
OLD_PROCESSES_INIT = '''        processes = {}
        launch_events = [ctx.Event() for _ in range(TAB_COUNT)]
'''
NEW_PROCESSES_INIT = '''        processes = {}
        launch_events = [ctx.Event() for _ in range(TAB_COUNT)]
        captcha_gate = ctx.Semaphore(CAPTCHA_PARALLEL_MAX)  # TWO_BROWSERS_1591R28
'''
OLD_SPAWN_KWARGS = '''                    "diagnostic_session_dir": str(diagnostic_session_dir),
                    "success_queue": success_queue,
                },
                name=f"esim-tab-{tab_id}",
'''
NEW_SPAWN_KWARGS = '''                    "diagnostic_session_dir": str(diagnostic_session_dir),
                    "success_queue": success_queue,
                    "captcha_gate": captcha_gate,  # TWO_BROWSERS_1591R28
                },
                name=f"esim-tab-{tab_id}",
'''
README_NOTE_R28 = '''

РЕВИЗИЯ 28 (fix_package_1591.py)
Два Chromium по четыре вкладки (BROWSER_COUNT = 2, всего 8 рабочих вкладок): пока четыре вкладки
до 6,5 минуты ждут подтверждение mobile-id, другие четыре занимают конвейер; зависание или падение
браузера (ревизия 18) теперь задевает половину вкладок, а не все. Капчи разных вкладок больше не
накладываются: одновременно решаются не больше CAPTCHA_PARALLEL_MAX (2), остальные ждут слот
(семафор передаётся worker'ам, обёртка try_local_captcha) и на время ожидания шлют CAPTCHA_WAIT
в heartbeat, чтобы watchdog не считал это зависанием; после CAPTCHA_GATE_WAIT_SECONDS (180 с)
вкладка решает без слота. Маркер: TWO_BROWSERS_1591R28.
'''
# Revision 29: a drain file left by a run that was killed mid-drain (systemctl restart, crash)
# made the next run drain from its first second: every tab finished one row and waited for a
# restart. A drain belongs to the process that requested it, so a leftover file is discarded
# at start.
STALE_DRAIN_MARKER = "STALE_DRAIN_RESET_1591R29"
OLD_RESTART_TIMER_R13 = '''        restart_started_at = monotonic()
        restart_notified = False
'''
NEW_RESTART_TIMER_R29 = '''        restart_started_at = monotonic()
        restart_notified = False
        if restart_drain_requested(base_dir):  # STALE_DRAIN_RESET_1591R29
            clear_restart_drain(base_dir)
            print("[RESTART] Найден незавершённый drain прошлого запуска — сброшен, работаю как обычно.", flush=True)
'''
README_NOTE_R29 = '''

РЕВИЗИЯ 29 (fix_package_1591.py)
Файл restart_drain.json, оставшийся от процесса, убитого посреди планового перезапуска
(systemctl restart, падение), заставлял следующий запуск с первой секунды «дорабатывать строки
и ждать перезапуск»: каждая вкладка делала одну строку и вставала. Drain принадлежит
запросившему его процессу, поэтому при старте оставшийся файл сбрасывается с записью в журнал.
Маркер: STALE_DRAIN_RESET_1591R29.
'''
# Revision 30: the signing step made deterministic and coordinated with DeepSeek.
# (a) Before the local signing the portal overlays are dismissed (r6 helper, so far used for
#     tariff/eSIM only); after the click the r25 trace is checked for the signing request
#     (checksignature / POST) and, when nothing was sent and the button is still there, the
#     signature is redrawn and the button clicked ONCE more.
# (b) While a DeepSeek SUCCESS_ASSIST session works on the tab (ai_busy:<tab> in status_map,
#     set by the observer) the local code does not sign, for at most AI_YIELD_MAX_SECONDS.
# (c) DeepSeek's mandate: when the runtime's click did not go through it must dismiss overlays,
#     redraw, click once, verify the network answer and end its report with
#     «VERDICT: SIGNED | PAYMENT | NOT_SIGNED». The observer stores the verdict in status_map
#     (verdict:<tab>); settle_success uses SIGNED as evidence and PAYMENT as the payment step.
AI_VERDICT_MARKER = "AI_VERDICT_1591R30"
SIGN_ROBUST_MARKER = "SIGN_ROBUST_1591R31"  # the code part (r31); r30 is the prompt only
OLD_POST_AUTH_DEF = "def tick_post_auth_review(base_dir, worker):\n"
AI_VERDICT_HELPERS_R30 = r'''# SIGN_ROBUST_1591R31
AI_BUSY_MAX_SECONDS = 150      # a DeepSeek session older than this no longer blocks the local signing
AI_YIELD_MAX_SECONDS = 120     # the local code yields to DeepSeek at most this long per row
AI_VERDICT_MAX_AGE = 900
SIGN_SENT_RE_1591R30 = re.compile(r"checksignature|/sign", re.I)


def _ai_busy_1591r30(worker):
    """True while a DeepSeek SUCCESS_ASSIST session is working on this tab (bounded)."""
    sm = worker.get("status_map")
    if sm is None:
        return False
    try:
        info = sm.get(f"ai_busy:{worker.get('id')}") or {}
    except Exception:
        return False
    now = time.time()
    if not info or now - float(info.get("time") or 0) > AI_BUSY_MAX_SECONDS:
        worker["ai_yield_since"] = None
        return False
    since = worker.get("ai_yield_since")
    if since is None:
        worker["ai_yield_since"] = now
        return True
    return now - float(since) < AI_YIELD_MAX_SECONDS


def _ai_verdict_1591r30(worker):
    """DeepSeek's VERDICT for this tab, if given after the local click and still fresh."""
    sm = worker.get("status_map")
    if sm is None:
        return ""
    try:
        info = sm.get(f"verdict:{worker.get('id')}") or {}
    except Exception:
        return ""
    when = float(info.get("time") or 0)
    if not info or time.time() - when > AI_VERDICT_MAX_AGE:
        return ""
    if when < float(worker.get("sign_clicked_at") or 0):
        return ""
    return str(info.get("verdict") or "").upper()


def _ai_mark_busy_1591r30(status_map, request_text, update_id):
    """Observer side: this SUCCESS_ASSIST request is being worked on — the tab's local code yields."""
    m = re.search(r"\[AUTO_SUCCESS_ASSIST TAB (\d+)\]", str(request_text or ""))
    if not m or status_map is None:
        return None
    tab = int(m.group(1))
    try:
        status_map[f"ai_busy:{tab}"] = {"time": time.time(), "update": update_id}
    except Exception:
        pass
    return tab


def _ai_success_verdict_1591r30(status_map, request_text, response_text):
    """Observer side: record DeepSeek's VERDICT for the tab named in the request; clear busy."""
    m = re.search(r"\[AUTO_SUCCESS_ASSIST TAB (\d+)\]", str(request_text or ""))
    if not m or status_map is None:
        return None
    tab = int(m.group(1))
    try:
        status_map.pop(f"ai_busy:{tab}", None)
    except Exception:
        pass
    v = re.search(r"VERDICT:\s*(SIGNED|PAYMENT|NOT_SIGNED)", str(response_text or ""), re.I)
    if not v:
        return None
    verdict = v.group(1).upper()
    try:
        status_map[f"verdict:{tab}"] = {"verdict": verdict, "time": time.time(),
                                        "text": str(response_text or "")[-300:]}
    except Exception:
        pass
    print(f"[AI VERDICT] TAB {tab}: {verdict}", flush=True)
    return verdict


_SIGNATURE_CANVAS_FILLED_JS_1591R30 = r"""() => {
  const list = [...document.querySelectorAll('canvas')].filter(c => {
    const r = c.getBoundingClientRect(); return r.width >= 250 && r.height >= 120;
  });
  if (!list.length) return null;
  const c = list[0];
  try {
    const blank = document.createElement('canvas'); blank.width = c.width; blank.height = c.height;
    return c.toDataURL() !== blank.toDataURL();
  } catch (e) { return null; }
}"""


def _signature_canvas_filled_1591r30(page):
    """True/False when the signature pad is/is not drawn on; None when unknown."""
    try:
        return page.evaluate(_SIGNATURE_CANVAS_FILLED_JS_1591R30)
    except Exception:
        return None


def _sign_prepare_1591r30(page, worker):
    """Before the local signing: no portal modal may intercept the click."""
    try:
        dismiss_blocking_overlays(page, keep_text="подписать")
    except Exception:
        pass


def _sign_request_sent_1591r30(trace):
    for r in (trace or {}).get("responses") or []:
        url = str(r.get("url") or "")
        if SIGN_SENT_RE_1591R30.search(url):
            return True
        if str(r.get("method")) in ("POST", "PUT", "PATCH") and int(r.get("status") or 0) < 400 and "esim" in url.lower():
            return True
    return False


def _sign_retry_if_unsent_1591r30(page, worker):
    """The click sent nothing and the button is still there: overlays away, redraw, ONE more click."""
    trace = worker.get("sign_trace") or {}
    if _sign_request_sent_1591r30(trace) or int(worker.get("sign_retries") or 0) >= 1:
        return False
    try:
        if _signature_button_locator(page) is None:
            return False
    except Exception:
        return False
    worker["sign_retries"] = int(worker.get("sign_retries") or 0) + 1
    filled = _signature_canvas_filled_1591r30(page)
    canvas = "пуст" if filled is False else ("не пуст" if filled else "?")
    print(
        f"[Вкладка {worker.get('id')}] Подпись: запрос на сервер не ушёл (холст {canvas}) — "
        "снимаю оверлеи и повторяю один раз.",
        flush=True,
    )
    _sign_prepare_1591r30(page, worker)
    _sign_trace_begin_1591r25(page, worker)
    try:
        fill_signature_and_submit(page, worker.get("diagnostic"))
        worker["sign_clicked_at"] = time.time()
        return True
    except Exception as exc:
        print(f"[Вкладка {worker.get('id')}] Повтор подписи не удался: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        return False
    finally:
        _sign_trace_end_1591r25(page, worker, note="retry")


'''
NEW_POST_AUTH_DEF = AI_VERDICT_HELPERS_R30 + OLD_POST_AUTH_DEF
OLD_BUTTON_BLOCK = '''    button = _signature_button_locator(page)
    if button is not None:
        try:
            enabled = button.is_enabled()
'''
NEW_BUTTON_BLOCK_R30 = '''    button = _signature_button_locator(page)
    if button is not None and _ai_busy_1591r30(worker):  # SIGN_ROBUST_1591R31: DeepSeek is on this tab
        set_tab_status(worker, "🧠", "Подтверждение успешно. DeepSeek работает с вкладкой — подпись отложена.")
        external_heartbeat(worker, "sign_yield_to_ai")
        return
    if button is not None:
        try:
            enabled = button.is_enabled()
'''
OLD_SIGN_CALL_R25 = '''            capture_contract_details(page, worker)
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["phase"] = "SIGN_WAIT"
'''
NEW_SIGN_CALL_R30 = '''            capture_contract_details(page, worker)
            _sign_prepare_1591r30(page, worker)  # SIGN_ROBUST_1591R31: overlays away first
            _sign_trace_begin_1591r25(page, worker)  # SIGN_TRACE_1591R25
            try:
                fill_signature_and_submit(page, worker.get("diagnostic"))
            finally:
                _sign_trace_end_1591r25(page, worker)
            worker["sign_clicked_at"] = time.time()
            try:
                _sign_retry_if_unsent_1591r30(page, worker)  # nothing sent + button still there → one retry
            except Exception as exc:
                print(f"[Вкладка {worker['id']}] Проверка отправки подписи: {type(exc).__name__}: {exc}", flush=True)
            worker["phase"] = "SIGN_WAIT"
'''
OLD_OBSERVER_PRINT = '''        print(
            f"[AI {lane.upper()}] Обрабатываю update {update_id}: {latest[:120]}",
            flush=True,
        )
'''
NEW_OBSERVER_PRINT = '''        print(
            f"[AI {lane.upper()}] Обрабатываю update {update_id}: {latest[:120]}",
            flush=True,
        )
        _ai_mark_busy_1591r30(status_map, latest, update_id)  # SIGN_ROBUST_1591R31
'''
OLD_OBSERVER_COMPLETE = '''            # Mark complete and queue the response in one local durable store.
            _ai_db_complete(
'''
NEW_OBSERVER_COMPLETE = '''            _ai_success_verdict_1591r30(status_map, latest, response_text)  # SIGN_ROBUST_1591R31
            # Mark complete and queue the response in one local durable store.
            _ai_db_complete(
'''
OLD_OBSERVER_FAIL = '''            _ai_db_fail(update_id, err, job.get("attempts", 1))
'''
NEW_OBSERVER_FAIL = '''            _ai_db_fail(update_id, err, job.get("attempts", 1))
            _ai_success_verdict_1591r30(status_map, latest, "")  # SIGN_ROBUST_1591R31: busy flag off
'''
OLD_SETTLE_PAYMENT_R26 = '''    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if evidence:
'''
NEW_SETTLE_PAYMENT_R30 = '''    if payment_text:
        _finish_payment_required_1591r26(base_dir, worker, payment_text)
        return False
    verdict = _ai_verdict_1591r30(worker)  # SIGN_ROBUST_1591R31
    if verdict == "PAYMENT":
        _finish_payment_required_1591r26(base_dir, worker, "по вердикту DeepSeek: сайт требует оплату eSIM")
        return False
    evidence = _signed_evidence_1591r24(page) if page is not None else ""
    if not evidence and verdict == "SIGNED":
        evidence = "ai:verdict_signed"
    if evidence:
'''
OLD_ASSIST_TAIL = '''        "Подписание прошло успешно. Вкладка осталась на …». "
        f"Причина вызова: {reason}. Текущий URL: {url}"
    )
'''
NEW_ASSIST_TAIL_R30 = '''        "Подписание прошло успешно. Вкладка осталась на …». "
        "ЕСЛИ RUNTIME УЖЕ НАЖАЛ «Подписать договор», а страница не изменилась или кнопка осталась: "  # AI_VERDICT_1591R30
        "сними всплывающие окна, перерисуй подпись, нажми кнопку ОДИН раз и проверь в network ответ "
        "/checksignature/. Пока статус вкладки ✍️ (runtime сам рисует и нажимает) — не кликай. "
        "ПОСЛЕДНЯЯ СТРОКА ОТЧЁТА СТРОГО одна из: «VERDICT: SIGNED» (checksignature 200 или экран после "
        "подписи), «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина». "
        f"Причина вызова: {reason}. Текущий URL: {url}"
    )
'''
OLD_MISSION_BULLET = "- После нажатия снова наблюдай страницу/console/network и проверь фактический результат.\n"
NEW_MISSION_BULLET_R30 = '''- После нажатия снова наблюдай страницу/console/network и проверь фактический результат.
- Если runtime уже нажал «Подписать договор», а страница не изменилась или кнопка осталась:
  сними всплывающие окна, перерисуй подпись, нажми кнопку ОДИН раз, проверь ответ
  /checksignature/ в network. Пока статус вкладки ✍️ — runtime сам рисует и нажимает, не кликай.
- Последняя строка каждого отчёта SUCCESS SUPERVISOR СТРОГО одна из: «VERDICT: SIGNED»,
  «VERDICT: PAYMENT» (экран «пора оплатить eSIM»), «VERDICT: NOT_SIGNED — причина».
  Runtime читает эту строку: SIGNED фиксирует успех, PAYMENT — шаг оплаты, NOT_SIGNED —
  вкладка удерживается и уходит на проверку пользователю.
'''
OLD_TEST_OBSERVER_NS = "            '_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a))}\n"
NEW_TEST_OBSERVER_NS = ("            '_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a)),\n"
                        "            '_ai_mark_busy_1591r30':lambda *a:None,'_ai_success_verdict_1591r30':lambda *a:None}  # SIGN_ROBUST_1591R31\n")
README_NOTE_R30 = '''

РЕВИЗИЯ 30 (fix_package_1591.py)
Только промпт DeepSeek (код сценария не менялся). Мандат SUCCESS SUPERVISOR: если runtime уже нажал
«Подписать договор», а страница не изменилась или кнопка осталась — снять всплывающие окна,
перерисовать подпись, нажать кнопку ОДИН раз, проверить ответ /checksignature/ в network; пока
статус вкладки ✍️ — не кликать. Последняя строка каждого отчёта строго «VERDICT: SIGNED |
PAYMENT | NOT_SIGNED». Маркер: AI_VERDICT_1591R30.
'''
README_NOTE_R31 = '''

РЕВИЗИЯ 31 (fix_package_1591.py)
Код подписи. (а) Перед локальной подписью снимаются оверлеи сайта (помощник ревизии 6, раньше
только для тарифа и eSIM); после клика по следу ревизии 25 проверяется, ушёл ли запрос подписи
(checksignature / POST), и если нет, а кнопка на месте — подпись перерисовывается и кнопка
нажимается ещё ОДИН раз (_sign_retry_if_unsent_1591r30, холст _signature_canvas_filled_1591r30).
(б) Пока сессия DeepSeek SUCCESS_ASSIST работает с вкладкой (ai_busy:<tab> в status_map, ставит
наблюдатель), локальный код не подписывает, не дольше AI_YIELD_MAX_SECONDS (120 с). (в) Наблюдатель
пишет вердикт DeepSeek в status_map (verdict:<tab>); settle_success считает SIGNED признаком успеха,
PAYMENT — шагом оплаты. Собирается по умолчанию; FIX_1591_MAX_REVISION=30 собирает пакет без этой
части. Маркер: SIGN_ROBUST_1591R31.
'''
# ---- revision 32 ----
# Revision 32: (a) the tariff card is looked for inside the «выберите тариф» picker and a card must
#     hold exactly one tariff title with a visible «выбрать» (the shared basket already showing
#     TARIFF_NAME made every tab of that Chromium fail with RECOVERABLE_RESTART_ROW forever);
#     (b) same-row restarts are capped and the row goes to the back of the queue; (c) a drain
#     has a deadline, so half the tabs can no longer wait forever for a looping worker.
TARIFF_SCOPE_MARKER = "TARIFF_SCOPE_1591R32"
ROW_RESTART_LIMIT_MARKER = "ROW_RESTART_LIMIT_1591R32"
DRAIN_DEADLINE_MARKER = "DRAIN_DEADLINE_1591R32"
OLD_TARIFF_FINDER_R32 = 'def _tariff_choose_button(page, diagnostic=None, timeout=10000):\n    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed."""\n    title = page.get_by_text(TARIFF_NAME, exact=True).first\n    try:\n        title.wait_for(state="visible", timeout=timeout)\n        card = title.locator(\n            "xpath=ancestor::*[.//button[normalize-space(.)=\'выбрать\' or normalize-space(.)=\'Выбрать\']][1]"\n        )\n        button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n        if button.count() > 0:\n            return button.first\n    except Exception:\n        pass\n    try:\n        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]\n        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()\n    except Exception:\n        titles, choose_count = [], -1\n    if diagnostic is not None:\n        try:\n            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)\n        except Exception:\n            pass\n    print(\n        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "\n        f"кнопок «выбрать»: {choose_count}",\n        flush=True,\n    )\n    raise RuntimeError(\n        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."\n    )\n'
NEW_TARIFF_FINDER_R32 = 'def _tariff_choose_button(page, diagnostic=None, timeout=10000):\n    """«выбрать» inside the card titled TARIFF_NAME; the card order is never assumed.\n\n    TARIFF_SCOPE_1591R32: the basket already holding TARIFF_NAME (chosen by an earlier row in the\n    same Chromium: the basket is shared by its tabs) shows the same title with «изменить» and no\n    «выбрать»; the tariff is looked for inside the «выберите тариф» picker first, and a card is only\n    the element around the title that holds exactly one tariff title and a visible «выбрать».\n    """\n    scopes = []\n    try:\n        header = page.get_by_text(_TARIFF_PICKER_HEADER_RE_1591R32).first\n        if header.count() > 0:\n            picker = header.locator(\n                "xpath=ancestor::*[.//*[normalize-space(.)=\'" + TARIFF_NAME + "\']][1]"\n            )\n            if picker.count() > 0:\n                scopes.append(picker)\n    except Exception:\n        pass\n    scopes.append(page)\n    deadline = monotonic() + timeout / 1000.0\n    while True:\n        for scope in scopes:\n            try:\n                button = _tariff_card_button_1591r32(scope)\n            except Exception:\n                button = None\n            if button is not None:\n                return button\n        if monotonic() >= deadline:\n            break\n        page.wait_for_timeout(300)\n    try:\n        titles = page.locator("text=/подписка/i").all_inner_texts()[:10]\n        choose_count = page.get_by_role("button", name=_CHOOSE_BUTTON_RE).count()\n    except Exception:\n        titles, choose_count = [], -1\n    if diagnostic is not None:\n        try:\n            diagnostic.write("tariff_card_not_found", tariff=TARIFF_NAME, titles=titles, choose_buttons=choose_count)\n        except Exception:\n            pass\n    print(\n        f"Карточка «{TARIFF_NAME}» с кнопкой «выбрать» не найдена; на экране: {titles}, "\n        f"кнопок «выбрать»: {choose_count}",\n        flush=True,\n    )\n    raise RuntimeError(\n        f"RECOVERABLE_RESTART_ROW: карточка тарифа «{TARIFF_NAME}» с кнопкой «выбрать» не найдена."\n    )\n\n\n# TARIFF_SCOPE_1591R32\n_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\\s*выберите тариф\\s*$", re.I)\n_TARIFF_TITLE_RE_1591R32 = re.compile(r"^\\s*подписка bee\\b", re.I)\n_TARIFF_BASKET_BUTTON_RE_1591R32 = re.compile(r"^\\s*(изменить|удалить тариф)\\s*$", re.I)\n\n\ndef _tariff_card_button_1591r32(scope):\n    """The visible «выбрать» of the one card titled TARIFF_NAME inside `scope`, else None."""\n    titles = scope.get_by_text(TARIFF_NAME, exact=True)\n    for index in range(min(titles.count(), 8)):\n        title = titles.nth(index)\n        try:\n            if not title.is_visible():\n                continue\n            card = title.locator(\n                "xpath=ancestor::*[.//button[normalize-space(.)=\'выбрать\' or normalize-space(.)=\'Выбрать\']][1]"\n            )\n            if card.count() == 0:\n                continue\n            if card.get_by_text(_TARIFF_TITLE_RE_1591R32).count() != 1:\n                continue  # a container of several cards (or the basket plus the picker), not a card\n            if card.get_by_role("button", name=_TARIFF_BASKET_BUTTON_RE_1591R32).count() > 0:\n                continue  # the basket card («изменить» / «Удалить тариф»): its «выбрать» belong to options\n            button = card.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n            if button.count() > 0 and button.first.is_visible():\n                return button.first\n        except Exception:\n            continue\n    return None\n'
OLD_ROW_READY_R32 = '                if worker["phase"] == "RESTART_ROW_READY":\n                    print(\n                        f"[Вкладка {tab_id}] Новая physical-вкладка готова. "\n                        "Повторяю ту же строку с начала.",\n                        flush=True,\n                    )\n                    continue\n'
NEW_ROW_READY_R32 = '                if worker["phase"] == "RESTART_ROW_READY":\n                    if _row_restart_exhausted_1591r32(worker, row, rows):  # ROW_RESTART_LIMIT_1591R32\n                        break\n                    print(\n                        f"[Вкладка {tab_id}] Новая physical-вкладка готова. "\n                        "Повторяю ту же строку с начала.",\n                        flush=True,\n                    )\n                    continue\n'
OLD_RESET_DEF_R32 = 'def reset_runtime_state(worker):\n'
NEW_RESET_DEF_R32 = '# ROW_RESTART_LIMIT_1591R32\nROW_RESTART_MAX = 3            # same-row restarts (new tab, same row) before the row is put back\nROW_DEFER_MAX_PER_RUN = 2      # a row is put back at most this many times per process launch\nDEFERRED_ROWS_FILE_NAME = "deferred_rows.jsonl"\n\n\ndef _row_restart_exhausted_1591r32(worker, row, rows):\n    """Count same-row restarts; past ROW_RESTART_MAX the row goes to the back of the queue\n    and the slot (already on a fresh page) takes the next one. The number is not marked\n    processed, so the row is tried again later in this run or at the next launch."""\n    key = _row_number_value(row) if row is not None else ""\n    counter = worker.get("row_restarts_1591r32") or {}\n    attempts = int(counter.get(key) or 0) + 1\n    worker["row_restarts_1591r32"] = {key: attempts}\n    if attempts <= ROW_RESTART_MAX:\n        return False\n    tab_id = worker.get("id")\n    line_number, active_digits, _ = row_parts(row)\n    deferred = int(row.get("_deferred_1591r32") or 0) + 1 if isinstance(row, dict) else 1\n    requeued = False\n    if isinstance(row, dict) and deferred <= ROW_DEFER_MAX_PER_RUN and rows is not None:\n        row["_deferred_1591r32"] = deferred\n        try:\n            rows.put(row)\n            requeued = True\n        except Exception as exc:\n            print(f"[Вкладка {tab_id}] Строка {line_number} не вернулась в очередь: {type(exc).__name__}: {exc}", flush=True)\n    note = ("вернул в конец очереди" if requeued\n            else "оставил до следующего запуска (номер не помечен обработанным)")\n    print(\n        f"[Вкладка {tab_id}] Строка {line_number}: {ROW_RESTART_MAX} перезапуска подряд не помогли; "\n        f"{note}, беру следующую.",\n        flush=True,\n    )\n    try:\n        base_dir = worker.get("base_dir")\n        if base_dir:\n            with open(Path(base_dir) / DEFERRED_ROWS_FILE_NAME, "a", encoding="utf-8") as handle:\n                handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_id,\n                                         "row": line_number, "number": active_digits,\n                                         "restarts": attempts - 1, "requeued": requeued},\n                                        ensure_ascii=False) + "\\n")\n    except Exception:\n        pass\n    worker["row_restarts_1591r32"] = {}\n    set_tab_status(worker, "⏭", f"Строка {line_number}: перезапуски исчерпаны, {note}")\n    reset_runtime_state(worker)\n    worker["form_ready"] = False\n    worker["phase"] = "IDLE"\n    external_heartbeat(worker, "row_deferred")\n    return True\n\n\ndef reset_runtime_state(worker):\n'
OLD_DRAIN_TICK_R32 = '            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13\n'
NEW_DRAIN_TICK_R32 = '            draining = _restart_tick()  # SCHEDULED_RESTART_1591R13\n            if draining:\n                _drain_deadline_1591r32(base_dir, processes, heartbeat)  # DRAIN_DEADLINE_1591R32\n'
OLD_LOAD_PROCESSED_R32 = 'def load_processed_numbers(base_dir):\n'
NEW_LOAD_PROCESSED_R32 = '# ROW_RESTART_LIMIT_1591R32 (parent side)\nROW_RESPAWN_MAX = 3            # replacements of a worker with the same row per launch\n_ROW_RESPAWNS_1591R32 = {}\n\n\ndef _row_for_respawn_1591r32(saved_row, tab_id, base_dir, why):\n    """The row a replacement worker starts with: the same row up to ROW_RESPAWN_MAX times per\n    launch (DEAD RECOVERY and the watchdog together), then None: the row stays unprocessed for\n    the next launch and the new worker takes the next one. Without this a row that always\n    hangs the tab (CANCELLING -> watchdog -> same row) looped forever."""\n    if saved_row is None:\n        return None\n    try:\n        key = _row_number_value(saved_row)\n    except Exception:\n        key = str(saved_row)\n    count = _ROW_RESPAWNS_1591R32.get(key, 0) + 1\n    _ROW_RESPAWNS_1591R32[key] = count\n    if count <= ROW_RESPAWN_MAX:\n        return saved_row\n    line_number, active_digits, _ = row_parts(saved_row)\n    print(\n        f"[Вкладка {tab_id}] Строка {line_number}: worker заменялся с этой строкой уже {count - 1} раз "\n        f"({why}); оставляю её до следующего запуска (номер не помечен обработанным), "\n        "новый worker берёт следующую.",\n        flush=True,\n    )\n    try:\n        with open(Path(base_dir) / DEFERRED_ROWS_FILE_NAME, "a", encoding="utf-8") as handle:\n            handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": tab_id,\n                                     "row": line_number, "number": active_digits,\n                                     "respawns": count - 1, "requeued": False, "why": why},\n                                    ensure_ascii=False) + "\\n")\n    except Exception:\n        pass\n    return None\n\n\n# DRAIN_DEADLINE_1591R32\nDRAIN_SOFT_MAX_SECONDS = 15 * 60   # then workers still at the start of a row are stopped\nDRAIN_HARD_MAX_SECONDS = 40 * 60   # then every remaining worker is stopped\nDRAIN_PROTECTED_PHASES = {\n    "POST_CONTINUE", "AUTH_WAIT", "CONFIRM", "RESEND", "PROTECTED_CHECK",\n    "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST",\n}\n\n\ndef _drain_age_1591r32(base_dir):\n    try:\n        data = json.loads((Path(base_dir) / RESTART_DRAIN_FILE_NAME).read_text(encoding="utf-8"))\n        return max(0.0, time.time() - float(data.get("requested_at") or 0.0))\n    except Exception:\n        return 0.0\n\n\ndef _drain_deadline_1591r32(base_dir, processes, heartbeat):\n    """A drain must end. After DRAIN_SOFT_MAX_SECONDS a worker that is still at the start of\n    a row (tariff, eSIM, form: nothing sent to the subscriber yet) is stopped; its row is not\n    marked processed and is taken again at the next launch. Confirmation, signing and DeepSeek\n    review are waited for until DRAIN_HARD_MAX_SECONDS. Returns the stopped tab ids."""\n    age = _drain_age_1591r32(base_dir)\n    if age < DRAIN_SOFT_MAX_SECONDS:\n        return []\n    stopped = []\n    for tab_id, proc in list(processes.items()):\n        if proc is None or not proc.is_alive():\n            continue\n        info = dict(heartbeat.get(str(tab_id)) or {})\n        phase = str(info.get("phase") or "")\n        protected = (phase in DRAIN_PROTECTED_PHASES or bool(info.get("success_guard"))\n                     or bool(info.get("error_guard")))\n        if protected and age < DRAIN_HARD_MAX_SECONDS:\n            continue\n        line_number = row_parts(info.get("row"))[0] if info.get("row") is not None else "?"\n        print(\n            f"[RESTART] Дренаж идёт {int(age // 60)} мин: вкладка {tab_id} на этапе {phase or \'unknown\'} "\n            f"(строка {line_number}) остановлена; номер не помечен обработанным и вернётся в очередь "\n            "при новом запуске.",\n            flush=True,\n        )\n        try:\n            proc.terminate()\n            proc.join(timeout=5)\n        except Exception:\n            pass\n        info["phase"] = "RESTART_WAIT"   # neither DEAD RECOVERY nor the watchdog replaces it\n        try:\n            heartbeat[str(tab_id)] = info\n        except Exception:\n            pass\n        stopped.append(tab_id)\n    return stopped\n\n\ndef load_processed_numbers(base_dir):\n'
README_NOTE_R32 = '\n\nРЕВИЗИЯ 32 (fix_package_1591.py)\n(а) Карточка тарифа. Корзина общая для вкладок одного Chromium: когда прошлая строка уже выбрала\n«подписка bee START», на странице два одинаковых заголовка — в корзине (с «изменить», без\n«выбрать») и в окне «выберите тариф». Прежний поиск брал первый заголовок и падал с\nRECOVERABLE_RESTART_ROW; теперь тариф ищется в окне «выберите тариф», карточкой считается\nэлемент вокруг заголовка ровно с одним названием тарифа и видимой «выбрать»\n(_tariff_card_button_1591r32). (б) Предел перезапусков строки: после ROW_RESTART_MAX (3)\nперезапусков одной строки в новой вкладке строка возвращается в конец очереди (не более двух раз\nза запуск, затем остаётся до следующего запуска), номер не помечается обработанным, слот берёт\nследующую; запись в deferred_rows.jsonl. Тот же предел (ROW_RESPAWN_MAX = 3) на стороне watchdog и\nDEAD RECOVERY: worker, зависший в CANCELLING, заменялся новым с той же строкой бесконечно. (в) Срок дренажа: через DRAIN_SOFT_MAX_SECONDS (15 мин)\nпосле начала планового перезапуска вкладки, всё ещё на старте строки, останавливаются (строка\nвернётся при новом запуске); подтверждение, подпись, разбор DeepSeek ждутся до\nDRAIN_HARD_MAX_SECONDS (40 мин). Маркеры: TARIFF_SCOPE_1591R32, ROW_RESTART_LIMIT_1591R32,\nDRAIN_DEADLINE_1591R32.\n'
OLD_DEAD_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else saved_row,\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        def recover_stalled_workers():\n'
NEW_DEAD_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "dead recovery"),  # ROW_RESTART_LIMIT_1591R32\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        def recover_stalled_workers():\n'
OLD_STALL_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else saved_row,\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        last_ai_restart_at = {}\n'
NEW_STALL_SPAWN_R32 = '                heartbeat.pop(str(tab_id), None)\n                new_proc, _ = spawn_worker(\n                    tab_id,\n                    None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "watchdog"),  # ROW_RESTART_LIMIT_1591R32\n                )\n                processes[tab_id] = new_proc\n                recovered = True\n            return recovered\n\n\n        last_ai_restart_at = {}\n'
# Revision 33: the basket shows several «изменить»; the tariff one is clicked, not the region one.
TARIFF_CHANGE_MARKER = "TARIFF_CHANGE_BUTTON_1591R33"
OLD_TARIFF_CHANGE_R33 = '            candidates = [\n                page.get_by_role("button", name="изменить", exact=True),\n                page.locator("button").filter(has_text=re.compile(r"^\\s*изменить\\s*$", re.I)),\n            ]\n'
NEW_TARIFF_CHANGE_R33 = '            candidates = [  # TARIFF_CHANGE_BUTTON_1591R33: the tariff «изменить», not the region one\n                _tariff_change_button_1591r33(page),\n                page.get_by_role("button", name="изменить", exact=True),\n                page.locator("button").filter(has_text=re.compile(r"^\\s*изменить\\s*$", re.I)),\n            ]\n'
OLD_TARIFF_HELPER_ANCHOR_R33 = '# TARIFF_SCOPE_1591R32\n_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\\s*выберите тариф\\s*$", re.I)\n'
NEW_TARIFF_HELPER_R33 = '# TARIFF_CHANGE_BUTTON_1591R33\n_TARIFF_CHANGE_METRIC_1591R33 = \'button[data-metric-name="basketMetric:handleClickChangeTariffButton"]\'\n\n\ndef _tariff_change_button_1591r33(page):\n    """Locator of the tariff block\'s «изменить». The basket can show several «изменить» (the region\n    block «Саратов • изменить» comes first) and the first one opened the region picker, not the\n    tariff picker. Preference: the site\'s own tariff-change button when it is marked, else the\n    «изменить» nearest to a tariff title («подписка bee …»), else every «изменить» (the caller\n    clicks the first). Any «изменить» is waited for first, so a late render does not fall through."""\n    generic = page.get_by_role("button", name="изменить", exact=True)\n    try:\n        expect(generic.first).to_be_visible(timeout=20000)\n    except Exception:\n        return generic\n    try:\n        marked = page.locator(_TARIFF_CHANGE_METRIC_1591R33)\n        if marked.count() > 0:\n            return marked\n    except Exception:\n        pass\n    try:\n        titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)\n        for index in range(min(titles.count(), 4)):\n            near = titles.nth(index).locator(\n                "xpath=ancestor::*[.//button[normalize-space(.)=\'изменить\']][1]"\n            ).get_by_role("button", name="изменить", exact=True)\n            if near.count() > 0:\n                return near\n    except Exception:\n        pass\n    return generic\n\n\n# TARIFF_SCOPE_1591R32\n_TARIFF_PICKER_HEADER_RE_1591R32 = re.compile(r"^\\s*выберите тариф\\s*$", re.I)\n'
README_NOTE_R33 = '\n\nРЕВИЗИЯ 33 (fix_package_1591.py)\nКнопка «изменить» тарифа. В корзине бывает несколько «изменить» (первая — у региона «Саратов»);\nкод нажимал первую, открывался выбор региона, а не тарифов, и карточка тарифа «не находилась»,\nпока строка не отдавалась (ревизия 32, 3 попытки). Теперь берётся кнопка смены тарифа сайта\n(data-metric-name basketMetric:handleClickChangeTariffButton), иначе «изменить» рядом с названием\nтарифа «подписка bee …», иначе первая «изменить». Маркер: TARIFF_CHANGE_BUTTON_1591R33.\n'
# Revision 34: the number of Chromium instances comes from BEELINE_BROWSERS (default 2).
BROWSER_ENV_MARKER = "BROWSER_COUNT_ENV_1591R34"
OLD_BROWSER_COUNT_R34 = 'BROWSER_COUNT = 2  # TWO_BROWSERS_1591R28: two Chromium instances, TABS_PER_BROWSER tabs each\n'
NEW_BROWSER_COUNT_R34 = '# BROWSER_COUNT_ENV_1591R34: BEELINE_BROWSERS=1 in the systemd unit runs one Chromium on a small\n# server (4 vCPU / 8 GB ran two at load average 20: every click and wait timed out). Default 2 (r28).\ndef _browser_count_1591r34(default=2):\n    try:\n        value = int(str(os.environ.get("BEELINE_BROWSERS") or default).strip())\n    except ValueError:\n        value = default\n    return min(max(value, 1), 4)\n\n\nBROWSER_COUNT = _browser_count_1591r34()  # TWO_BROWSERS_1591R28: Chromium instances, TABS_PER_BROWSER tabs each\n'
README_NOTE_R34 = '\n\nРЕВИЗИЯ 34 (fix_package_1591.py)\nЧисло Chromium задаётся переменной окружения BEELINE_BROWSERS (по умолчанию 2, как в ревизии 28;\nдопустимо 1–4), вкладок по-прежнему 4 на браузер. На сервере 4 vCPU / 8 ГБ два Chromium дали load\naverage 20 и нехватку памяти: клики и ожидания не укладывались в таймауты, строки падали на тарифе.\nТам ставится 1: drop-in /etc/systemd/system/beeline.service.d/browsers.conf с\n[Service] Environment=BEELINE_BROWSERS=1, затем systemctl daemon-reload и restart.\nМаркер: BROWSER_COUNT_ENV_1591R34.\n'
# Revision 35: the sign trace in Telegram is one line; the jsonl record keeps the full trace.
TRACE_COMPACT_MARKER = "TRACE_COMPACT_1591R35"
OLD_TRACE_LINES_R35 = 'def _sign_trace_lines_1591r25(summary):\n    if not summary:\n        return []\n    out = [f"Подпись: {summary.get(\'url_before\') or \'—\'} → {summary.get(\'url_after\') or \'—\'}"]\n    for r in (summary.get("responses") or [])[:6]:\n        line = f"  {r.get(\'method\')} {r.get(\'url\')} → {r.get(\'status\')}"\n        if r.get("body"):\n            line += " " + str(r["body"])[:160]\n        out.append(line)\n    for f in (summary.get("failed") or [])[:3]:\n        out.append(f"  сеть: {f.get(\'url\')} — {f.get(\'error\')}")\n    for c in (summary.get("console") or [])[:3]:\n        out.append(f"  console {c.get(\'type\')}: {c.get(\'text\')}")\n    return out\n'
NEW_TRACE_LINES_R35 = 'def _sign_trace_lines_1591r25(summary):\n    """TRACE_COMPACT_1591R35: one line in Telegram (the full trace stays in the jsonl record and\n    the journal); HTTP errors, network failures and console errors are still listed."""\n    if not summary:\n        return []\n    responses = summary.get("responses") or []\n\n    def _status(response):\n        try:\n            return int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            return 0\n\n    signed = [r for r in responses if "checksignature" in str(r.get("url") or "").lower()]\n    passport = [r for r in responses if "sendpassportdata" in str(r.get("url") or "").lower()]\n    parts = []\n    if signed:\n        parts.append(f"подпись → {_status(signed[-1])}")\n    if passport:\n        parts.append(f"паспортные данные → {_status(passport[-1])}")\n    if not parts:\n        parts.append("запрос подписи в сети не замечен" if not responses else f"ответов {len(responses)}")\n    out = ["Подпись (сеть): " + ", ".join(parts)]\n    for r in [r for r in responses if _status(r) >= 400][:3]:\n        line = f"  {r.get(\'method\')} {r.get(\'url\')} → {r.get(\'status\')}"\n        if r.get("body"):\n            line += " " + str(r["body"])[:160]\n        out.append(line)\n    for f in (summary.get("failed") or [])[:3]:\n        out.append(f"  сеть: {f.get(\'url\')} — {f.get(\'error\')}")\n    for c in (summary.get("console") or [])[:3]:\n        out.append(f"  console {c.get(\'type\')}: {c.get(\'text\')}")\n    return out\n'
README_NOTE_R35 = '\n\nРЕВИЗИЯ 35 (fix_package_1591.py)\nСообщения #оплата и #неподтверждено без сетевого следа подписи ревизии 25 построчно: вместо списка\nзапросов одна строка «Подпись (сеть): подпись → 200, паспортные данные → 202». Ошибки HTTP (>= 400),\nсбои сети и ошибки console по-прежнему перечисляются. Полный след остаётся в записи jsonl и в\nжурнале. Маркер: TRACE_COMPACT_1591R35.\n'
# Revision 36: the pushed hash_order link belongs to the current row, never to an earlier one of the tab.
SIM_URL_MARKER = "SIM_URL_PER_ROW_1591R36"
OLD_PENDING_URL_R36 = '        cached_url = getattr(page, "_reserved_sim_url", None)\n        cached_number = getattr(page, "_reserved_sim_number", None)\n        if cached_url and not worker.get("reserved_sim_url"):\n            worker["reserved_sim_url"] = cached_url\n'
NEW_PENDING_URL_R36 = '        cached_url = getattr(page, "_reserved_sim_url", None)\n        cached_number = getattr(page, "_reserved_sim_number", None)\n        # SIM_URL_PER_ROW_1591R36: the offer URL captured for THIS row (locked by\n        # capture_esim_offer_page) replaces whatever the worker remembered; the old rule\n        # "only when empty" kept the first row\'s link for every later row of the tab.\n        if cached_url and (getattr(page, "_reserved_sim_url_locked", False) or not worker.get("reserved_sim_url")):\n            worker["reserved_sim_url"] = cached_url\n'
OLD_RESET_STATE_R36 = '    worker["diagnostic"] = None\n    worker["post_retry_deadline"] = None\n'
NEW_RESET_STATE_R36 = '    worker["diagnostic"] = None\n    worker["reserved_sim_url"] = None     # SIM_URL_PER_ROW_1591R36: a row never inherits the\n    worker["reserved_sim_number"] = None  # previous row\'s order link or reserved number\n    worker["post_retry_deadline"] = None\n'
README_NOTE_R36 = '\n\nРЕВИЗИЯ 36 (fix_package_1591.py)\nСсылка eSIM в пуше принадлежала не той строке. Ссылка заказа (hash_order) копировалась в память\nвкладки только когда там пусто, а между строками память не очищалась: первая строка вкладки\nполучала свою ссылку, все следующие — ссылку первой (номер eSIM при этом перезаписывался и был\nверным). По такой ссылке сайт показывал чужой заказ без данных («введите данные заново»). Теперь\nссылка берётся из захвата текущей строки (замок capture_esim_offer_page), а reset_runtime_state\nочищает ссылку и номер между строками. Команда Telegram /res <номер eSIM из пуша или номер строки>\nотвечает ссылкой заказа, который реально подписан в этой строке (по журналу за 3 дня).\nМаркер: SIM_URL_PER_ROW_1591R36.\n'
OLD_CTRL_IMPORT_R36 = 'import os\nimport signal\n'
NEW_CTRL_IMPORT_R36 = 'import os\nimport re\nimport signal\n'
OLD_CTRL_RESTART_BRANCH_R36 = '                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13\n                        waiting_upload = False\n                        _send(_restart_command(text[len("/restart"):]))\n                        continue\n'
NEW_CTRL_RESTART_BRANCH_R36 = '                    if text.startswith("/restart"):  # SCHEDULED_RESTART_1591R13\n                        waiting_upload = False\n                        _send(_restart_command(text[len("/restart"):]))\n                        continue\n\n                    if text.startswith("/res"):  # SIM_URL_PER_ROW_1591R36: the row\'s real order link\n                        waiting_upload = False\n                        _send(_row_link_command(text[len("/res"):]))\n                        continue\n'
OLD_CTRL_RELAUNCH_DEF_R36 = 'def _restart_after_drain(proc):\n'
NEW_CTRL_ROWLINK_R36 = '# SIM_URL_PER_ROW_1591R36\n_RL_LINE = re.compile(r"^(?P<ts>\\S+)\\s+\\S+\\s+python\\[(?P<pid>\\d+)\\]:\\s?(?P<msg>.*)$")\n_RL_START = re.compile(r"\\[Вкладка (?P<tab>\\d+)\\] Обрабатываю строку (?P<row>\\d+), номер заканчивается на (?P<tail>\\d+)")\n_RL_OFFER = re.compile(r"eSIM offer сохранён: номер=(?P<num>\\S+) \\| (?P<url>\\S+hash_order=[0-9a-f]+)")\n_RL_OUTCOMES = (\n    ("оплата", re.compile(r"ТРЕБУЕТСЯ ОПЛАТА\\. Строка (?P<row>\\d+)")),\n    ("не подтверждена", re.compile(r"ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА\\. Строка (?P<row>\\d+)")),\n    ("результат", re.compile(r"Результат строки (?P<row>\\d+): (?P<status>\\S+)")),\n)\n\n\ndef _rows_from_journal_1591r36(log):\n    """Rows as the journal saw them: start line, every «продолжить» offer capture, outcome."""\n    rows, current = [], {}\n    for line in log.splitlines():\n        m = _RL_LINE.match(line)\n        if not m:\n            continue\n        ts, pid, msg = m.group("ts")[:19].replace("T", " "), m.group("pid"), m.group("msg")\n        s = _RL_START.search(msg)\n        if s:\n            info = {"row": s.group("row"), "tab": s.group("tab"), "tail": s.group("tail"), "start": ts,\n                    "offers": [], "signed": False, "outcome": ""}\n            rows.append(info)\n            current[pid] = info\n            continue\n        info = current.get(pid)\n        if info is None:\n            continue\n        o = _RL_OFFER.search(msg)\n        if o:\n            info["offers"].append((ts, o.group("num"), o.group("url")))\n            continue\n        if "Нажата кнопка «Подписать договор»" in msg:\n            info["signed"] = True\n            continue\n        for name, pat in _RL_OUTCOMES:\n            r = pat.search(msg)\n            if r and r.group("row") == info["row"]:\n                info["outcome"] = name if name != "результат" else r.group("status")\n                break\n    return rows\n\n\ndef _row_link_command(argument):\n    """/res <номер eSIM из пуша, хотя бы 4 последние цифры> или /res <номер строки>.\n\n    Before revision 36 the push could carry the link of the tab\'s earlier row; the journal\n    keeps the real one: the last offer captured for the row is the order that was signed."""\n    key = re.sub(r"\\D", "", argument or "")\n    if len(key) < 3:\n        return ("Формат: /res <номер eSIM из пуша> (можно последние 4–6 цифр) или /res <номер строки>. "\n                "Отвечу ссылкой заказа, который реально подписан в этой строке.")\n    try:\n        log = subprocess.run(["journalctl", "-u", "beeline", "--no-pager", "-o", "short-iso", "--since", "-3 days"],\n                             capture_output=True, text=True, timeout=120).stdout\n    except Exception as exc:\n        return f"Журнал недоступен: {type(exc).__name__}: {exc}"\n    rows = _rows_from_journal_1591r36(log)\n    by_row = [r for r in rows if r["row"] == key] if len(key) <= 5 else []\n    by_number = [r for r in rows if any(re.sub(r"\\D", "", num).endswith(key) for _, num, _ in r["offers"])\n                 or r["tail"] == key]\n    hits = (by_row + [r for r in by_number if r not in by_row])[-5:]\n    if not hits:\n        return f"В журнале за 3 дня нет строки или номера eSIM, оканчивающегося на …{key[-6:]}."\n    out = []\n    for r in hits:\n        outcome = r["outcome"] or ("подписана" if r["signed"] else "не завершена")\n        head = f"Строка {r[\'row\']} (вкладка {r[\'tab\']}, …{r[\'tail\']}, {r[\'start\'][5:16]}), исход: {outcome}"\n        if not r["offers"]:\n            out.append(head + "\\nСсылка в журнале не найдена.")\n            continue\n        ts, num, url = r["offers"][-1]\n        text = head + f"\\neSIM {num}\\nСсылка заказа: {url}"\n        if len(r["offers"]) > 1:\n            text += f"\\n(ранних заказов этой строки без данных: {len(r[\'offers\']) - 1})"\n        out.append(text)\n    return "\\n\\n".join(out)\n\n\ndef _restart_after_drain(proc):\n'
OLD_TEST_CTRL_NS_R36 = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,\n"
NEW_TEST_CTRL_NS_R36 = "'_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,'_row_link_command':lambda a:'',\n"
# Revision 37: DeepSeek is asked for help only when the signature did not go through.
AI_SIGN_FAIL_MARKER = "AI_ON_SIGN_FAIL_1591R37"
OLD_GUARD_ASSIST_R37 = '    publish_worker_phase(worker, "POST_AUTH_REVIEW", note)\n    queue_success_assist(worker, note, force=True)\n'
NEW_GUARD_ASSIST_R37 = '    publish_worker_phase(worker, "POST_AUTH_REVIEW", note)\n    # AI_ON_SIGN_FAIL_1591R37: DeepSeek is no longer summoned on every confirmed row. The runtime\n    # signs by itself; DeepSeek is asked only when the signature does not go through (disabled\n    # button, missing region, signing error, request not seen in the network, error page,\n    # unverified page). The push with the network trace is the report for the rest.\n    print(\n        f"[Вкладка {worker[\'id\']}] DeepSeek на подпись не вызываю: runtime подписывает сам; "\n        "вызов только при сбое подписи.",\n        flush=True,\n    )\n'
OLD_AFTER_CLICK_R37 = '            external_heartbeat(worker, "signature_submitted_success_guard")\n            queue_success_assist(worker, "подпись отправлена; наблюдай результат")\n            return\n'
NEW_AFTER_CLICK_R37 = '            external_heartbeat(worker, "signature_submitted_success_guard")\n            if _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n                print(\n                    f"[Вкладка {worker[\'id\']}] Запрос подписи ушёл и принят сайтом (след сети); "\n                    "DeepSeek не вызываю.",\n                    flush=True,\n                )\n            else:\n                queue_success_assist(\n                    worker,\n                    "подпись нажата, но запроса подписи в сети не видно; проверь ошибки/обязательные поля",\n                    force=True,\n                )\n            return\n'
OLD_GUARD_DEF_R37 = 'def enter_success_guard(worker, note):\n'
NEW_GUARD_DEF_R37 = '# AI_ON_SIGN_FAIL_1591R37\nSIGN_OK_RE_1591R37 = re.compile(r"checksignature|/sign\\b", re.I)\n\n\ndef _sign_went_through_1591r37(worker):\n    """True when the trace of the sign click (revision 25) holds a successful answer (status\n    2xx/3xx) to the signing request: the site accepted the signature, DeepSeek is not needed."""\n    trace = (worker or {}).get("sign_trace") or {}\n    for response in trace.get("responses") or []:\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if SIGN_OK_RE_1591R37.search(str(response.get("url") or "")) and 200 <= status < 400:\n            return True\n    return False\n\n\ndef enter_success_guard(worker, note):\n'
README_NOTE_R37 = '\n\nРЕВИЗИЯ 37 (fix_package_1591.py)\nDeepSeek только при сбое подписи. Раньше SUCCESS_ASSIST ставился на каждую строку, прошедшую\nподтверждение (enter_success_guard), и ещё раз после клика «Подписать договор»; на успешных строках\nэто были запросы со скриншотами и отчёт в 2–4 сообщения Telegram впустую. Теперь при входе в\npost-auth DeepSeek не вызывается, а после клика — только если в следе сети (ревизия 25) нет\nуспешного ответа на запрос подписи (_sign_went_through_1591r37). Вызовы при неактивной кнопке,\nотсутствующей области, ошибке подписи, странице ошибки, оставшейся кнопке и неподтверждённой\nстранице сохранены. registration/error после клика записывается как #неподтверждено сразу, без DeepSeek\n(дописывать там нечего); принятый сайтом запрос подписи (2xx) считается доказательством подписания в\nsettle_success. Маркер: AI_ON_SIGN_FAIL_1591R37.\n'
OLD_SIGN_ERROR_R37 = '    if _post_auth_error_page(page):\n        worker["phase"] = "SUCCESS_ASSIST"\n        set_tab_status(\n            worker, "🧠",\n            "После подписи сайт показал ошибку — DeepSeek анализирует. Страницу не трогаю."\n        )\n        external_heartbeat(worker, "success_sign_error")\n        queue_success_assist(worker, "ошибка после попытки подписи")\n        return\n'
NEW_SIGN_ERROR_R37 = '    if _post_auth_error_page(page):\n        # AI_ON_SIGN_FAIL_1591R37: registration/error after the click has no field DeepSeek could\n        # fill; the row is recorded as unverified (number not processed, tab kept open) at once.\n        external_heartbeat(worker, "success_sign_error")\n        accepted = _sign_went_through_1591r37(worker)\n        _finish_unverified_1591r24(\n            base_dir, worker,\n            "после «Подписать договор» сайт показал registration/error"\n            + (" (запрос подписи при этом был принят сайтом)" if accepted else ""),\n        )\n        return\n'
OLD_EVIDENCE_R37 = '    evidence = _signed_evidence_1591r24(page) if page is not None else ""\n'
NEW_EVIDENCE_R37 = '    evidence = _signed_evidence_1591r24(page) if page is not None else ""\n    if not evidence and _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n        evidence = "network:signature_accepted"  # the site answered the signing request with 2xx\n'
# A lite package (r37 without r31) already carries the r37 evidence lines inside the settle block
# that the r31 step rewrites; both application orders give the same text.
OLD_SETTLE_PAYMENT_R26_WITH_R37 = OLD_SETTLE_PAYMENT_R26.replace(OLD_EVIDENCE_R37, NEW_EVIDENCE_R37)
NEW_SETTLE_PAYMENT_R30_WITH_R37 = NEW_SETTLE_PAYMENT_R30.replace(OLD_EVIDENCE_R37, NEW_EVIDENCE_R37)
# Revision 38: the inline menu of the bot (telegram_menu.py) replaces the bottom keyboard and the
# eight edited status messages; short success/payment pushes; DeepSeek only via its button.
TELEGRAM_MENU_SOURCE = Path(__file__).resolve().parent / "telegram_menu.py"
TELEGRAM_MENU_MARKER = 'TELEGRAM_MENU_1591R38'
OLD_STATUS_SYNC_R38 = 'def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):\n    """Create the missing status messages and push the changed texts, within the limits."""\n    changed = False\n    for i in range(1, TAB_COUNT + 1):\n        if i in mids:\n            continue\n        r, err = _tg_call_1591r27(\n            cfg, "sendMessage",\n            {"chat_id": chat, "text": f"⏳ Вкладка {i}\\nСтатус: запуск...", "disable_web_page_preview": "true"},\n            state,\n        )\n        if r:\n            mids[i] = r["result"]["message_id"]\n            last[i] = ""\n            changed = True\n            print(f"[Telegram] Сообщение вкладки {i} создано.", flush=True)\n        else:\n            if err != "paused":\n                print(f"[Telegram] ОШИБКА отправки вкладки {i}: {err}", flush=True)\n            break\n    if changed:\n        _tg_status_messages_save_1591r27(chat, mids)\n    now = time.time()\n    for i, mid in list(mids.items()):\n        info = status_map.get(str(i))\n        t = str((info or {}).get("text", ""))\n        if not t or t == last.get(i) or now - float(edited_at.get(i) or 0) < TG_STATUS_MIN_EDIT_GAP_1591R27:\n            continue\n        r, err = _tg_call_1591r27(\n            cfg, "editMessageText",\n            {"chat_id": chat, "message_id": mid, "text": t[:4000], "disable_web_page_preview": "true"},\n            state,\n        )\n        edited_at[i] = time.time()\n        if r:\n            last[i] = t\n            continue\n        if err == "paused":\n            break\n        low = str(err).lower()\n        if "message is not modified" in low:\n            last[i] = t\n        elif "not found" in low or "can\'t be edited" in low or "message_id_invalid" in low:\n            mids.pop(i, None)\n            _tg_status_messages_save_1591r27(chat, mids)\n            print(f"[Telegram] Сообщение вкладки {i} исчезло — создам новое.", flush=True)\n        else:\n            print(f"[Telegram] ОШИБКА обновления вкладки {i}: {err}", flush=True)\n'
NEW_STATUS_SYNC_R38 = 'def _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at):\n    """TELEGRAM_MENU_1591R38: the tab statuses go to status_snapshot.json for the bot\'s menu\n    (its «Статус» view edits one panel while it is open). The eight status messages and their\n    background edits of revision 27 are gone, so nothing is sent to Telegram here."""\n    tabs = {}\n    for i in range(1, TAB_COUNT + 1):\n        info = status_map.get(str(i))\n        if info:\n            tabs[str(i)] = {"text": str(info.get("text", ""))[:1500], "time": float(info.get("time") or 0)}\n    key = json.dumps(tabs, ensure_ascii=False, sort_keys=True)\n    if key == last.get("_snapshot"):\n        return\n    last["_snapshot"] = key\n    path = _tg_status_file_1591r27().with_name("status_snapshot.json")\n    try:\n        tmp = path.with_suffix(".tmp")\n        tmp.write_text(json.dumps({"updated": time.time(), "tabs": tabs}, ensure_ascii=False), "utf-8")\n        tmp.replace(path)\n    except Exception as exc:\n        print(f"[Telegram] status_snapshot.json не записан: {type(exc).__name__}: {exc}", flush=True)\n'
OLD_LOGGER_START_R38 = '    # TG_RATE_1591R27: reuse the status messages of the previous run instead of four new ones\n    # per restart; each is verified by an edit and recreated only when Telegram says it is gone.\n    for i, mid in _tg_status_messages_load_1591r27(chat).items():\n        r, err = _tg_call_1591r27(\n            cfg, "editMessageText",\n            {"chat_id": chat, "message_id": mid, "text": f"⏳ Вкладка {i}\\nСтатус: перезапуск...",\n             "disable_web_page_preview": "true"},\n            state,\n        )\n        if r or err == "paused" or "not modified" in str(err or "").lower():\n            mids[i] = mid\n            last[i] = ""\n    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)\n    if not mids:\n        print(\n            "[Telegram] Статусные сообщения пока не созданы (лимит Telegram) — попробую позже; "\n            "основной сценарий работает.",\n            flush=True,\n        )\n\n'
NEW_LOGGER_START_R38 = '    # TELEGRAM_MENU_1591R38: statuses are written to status_snapshot.json and shown by the\n    # bot\'s menu on request; no status messages are created or edited here any more.\n    print("[Telegram] Статус вкладок пишется в status_snapshot.json; показ — через меню бота.", flush=True)\n    _tg_status_sync_1591r27(cfg, chat, status_map, mids, last, state, edited_at)\n\n'
OLD_SUCCESS_MSG_R38 = 'def _success_message(worker, rec):\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
NEW_SUCCESS_MSG_R38 = 'def _pretty_phone_1591r38(value):\n    d = re.sub(r"\\D", "", str(value or ""))\n    if len(d) == 11 and d[0] in "78":\n        return f"+7 {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:]}"\n    return str(value or "—")\n\n\ndef _short_push_1591r38(worker, rec, tag, outcome):\n    """TELEGRAM_MENU_1591R38: the push is a short card; the full record (profile, links,\n    network trace) is in the bot\'s menu, «Мои eSIM», and in the jsonl files."""\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n    profile = rec.get("profile") or {}\n    lines = [\n        f"🆕 Новая eSIM · {tag}",\n        f"📱 {_pretty_phone_1591r38(rec.get(\'sim_number\'))}",\n        f"👤 {profile.get(\'full_name\') or \'—\'} · 🎂 {profile.get(\'birth_date\') or \'—\'}",\n        f"📄 Строка {row_no}/{worker.get(\'total_rows\') or \'?\'} · {active_value} | {second_value}",\n        outcome,\n    ]\n    if tag == "#оплата" and rec.get("sim_url"):\n        lines.append(f"🔗 {rec[\'sim_url\']}")\n    lines.append("🗂 Карточка и отметки: меню бота → 📱 Мои eSIM")\n    return "\\n".join(lines)\n\n\ndef _success_message(worker, rec):\n    return _short_push_1591r38(worker, rec, "#успешно", "✅ Договор оформлен")  # TELEGRAM_MENU_1591R38\n\n\ndef _success_message_full_1591r17(worker, rec):\n    """The former long push; kept for reference, the menu card renders the same fields."""\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
OLD_PAYMENT_MSG_R38 = 'def _payment_message_1591r26(worker, rec):\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
NEW_PAYMENT_MSG_R38 = 'def _payment_message_1591r26(worker, rec):\n    return _short_push_1591r38(worker, rec, "#оплата", "💳 Подпись принята, нужна оплата картой; номер помечен обработанным")  # TELEGRAM_MENU_1591R38\n\n\ndef _payment_message_full_1591r26(worker, rec):\n    row_no, active_value, second_value = row_parts(worker.get("row"))\n'
OLD_REC_TIME_R38 = '        "profile":dict(worker.get("success_profile") or {}),\n'
NEW_REC_TIME_R38 = '        "time": time.strftime("%Y-%m-%d %H:%M:%S"),  # TELEGRAM_MENU_1591R38: order in «Мои eSIM»\n        "profile":dict(worker.get("success_profile") or {}),\n'
OLD_C_IMPORT_R38 = 'import test_beeline as app\n'
NEW_C_IMPORT_R38 = 'import test_beeline as app\nimport telegram_menu as _menu_mod  # TELEGRAM_MENU_1591R38\n'
OLD_C_MARKUP_R38 = 'MENU_MARKUP = json.dumps(\n    {\n        "keyboard": [\n            [{"text": BTN_START}, {"text": BTN_STOP}],\n            [{"text": BTN_RESTART}],\n            [{"text": BTN_UPLOAD}],\n        ],\n        "resize_keyboard": True,\n        "is_persistent": True,\n        "input_field_placeholder": "Команда или сообщение DeepSeek",\n    },\n    ensure_ascii=False,\n)\n'
NEW_C_MARKUP_R38 = '# TELEGRAM_MENU_1591R38: the bottom keyboard is gone; every notice removes it once, the\n# inline menu (telegram_menu.py) is the control surface.\nMENU_MARKUP = json.dumps({"remove_keyboard": True})\n'
OLD_C_PROC_R38 = '    proc = AutomationProcess()\n    waiting_upload = False\n'
NEW_C_PROC_R38 = '    proc = AutomationProcess()\n    waiting_upload = False\n    # TELEGRAM_MENU_1591R38: one panel message with inline buttons; the eight status messages\n    # of earlier revisions are retired once.\n    menu = _menu_mod.TelegramMenu(app, BASE_DIR, proc, link_resolver=_row_link_command)\n    try:\n        menu.retire_status_messages(BASE_DIR / "telegram_status_messages.json")\n    except Exception as exc:\n        print(f"[CTRL] старые статусные сообщения не обновлены: {exc}", flush=True)\n'
OLD_C_HELLO_R38 = '    _send(\n        "🎛 Управление софтом\\n\\n"\n        f"Состояние: {proc.status()}\\n"\n        "Кнопки управления обрабатываются локально и НЕ отправляются DeepSeek."\n    )\n'
NEW_C_HELLO_R38 = '    try:\n        menu.show_menu(fresh=True)  # TELEGRAM_MENU_1591R38\n    except Exception as exc:\n        print(f"[CTRL] меню не показано: {exc}", flush=True)\n'
OLD_C_LOOP_R38 = '        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n        proc.reap()\n'
NEW_C_LOOP_R38 = '        _restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13\n        proc.reap()\n        try:\n            menu.tick()  # TELEGRAM_MENU_1591R38: live status only while its view is open\n        except Exception as exc:\n            print(f"[CTRL] меню: {exc}", flush=True)\n'
OLD_C_ALLOWED_R38 = '                "allowed_updates": json.dumps(["message"]),\n'
NEW_C_ALLOWED_R38 = '                "allowed_updates": json.dumps(["message", "callback_query"]),  # TELEGRAM_MENU_1591R38\n'
OLD_C_MSG_R38 = '                try:\n                    msg = upd.get("message") or {}\n                    msg_chat = str((msg.get("chat") or {}).get("id") or "")\n'
NEW_C_MSG_R38 = '                try:\n                    callback = upd.get("callback_query")  # TELEGRAM_MENU_1591R38: inline buttons\n                    if callback:\n                        cb_chat = str(((callback.get("message") or {}).get("chat") or {}).get("id") or "")\n                        if cb_chat == chat and menu.handle_callback(callback) == "upload":\n                            waiting_upload = True\n                        continue\n                    msg = upd.get("message") or {}\n                    msg_chat = str((msg.get("chat") or {}).get("id") or "")\n'
OLD_C_START_R38 = '                    if text in {"/start", "/menu"}:\n                        waiting_upload = False\n                        _send(\n                            "🎛 Управление софтом\\n\\n"\n                            f"Состояние: {proc.status()}"\n                        )\n                        continue\n\n                    if text == "/status":\n                        _send(f"Состояние: {proc.status()}")\n                        continue\n'
NEW_C_START_R38 = '                    if text in {"/start", "/menu"}:\n                        waiting_upload = False\n                        menu.show_menu(fresh=True)  # TELEGRAM_MENU_1591R38\n                        continue\n\n                    if text == "/status":\n                        menu.show_menu(fresh=True)\n                        menu.show_status()\n                        continue\n'
OLD_C_UNKNOWN_R38 = '                        _send("Неизвестная команда. Используй кнопки меню.")\n'
NEW_C_UNKNOWN_R38 = '                        menu.show_menu(fresh=True, note="Неизвестная команда — вот меню.")  # TELEGRAM_MENU_1591R38\n'
OLD_C_AI_R38 = '                    if text:\n                        app._ai_db_store_telegram_update(upd, chat)\n                        print(\n                            f"[CTRL→AI] update={update_id}: {text[:120]}",\n                            flush=True,\n                        )\n                        _typing()\n'
NEW_C_AI_R38 = '                    if text:\n                        # TELEGRAM_MENU_1591R38: DeepSeek gets a message only after «Спросить\n                        # DeepSeek»; any other text (a word, a letter, a symbol) opens the menu.\n                        if not menu.text_is_for_ai():\n                            menu.show_menu(fresh=True)\n                            continue\n                        app._ai_db_store_telegram_update(upd, chat)\n                        print(\n                            f"[CTRL→AI] update={update_id}: {text[:120]}",\n                            flush=True,\n                        )\n                        _typing()\n                        menu.ai_sent()\n'
OLD_I_FILES_R38 = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py')\n"
NEW_I_FILES_R38 = "FILES = ('operator_runtime_io.py', 'test_beeline.py', 'server_controller.py', 'symbol_matching.py', 'telegram_menu.py')\n"
OLD_I_SUPPORT_R38 = "    raw = (package/'operator_runtime_io.py').read_bytes()\n    if digest(raw) != manifest['files']['operator_runtime_io.py']['output_sha256']:\n        raise RuntimeError('Support module checksum failed')\n    result['operator_runtime_io.py'] = raw\n"
NEW_I_SUPPORT_R38 = "    raw = (package/'operator_runtime_io.py').read_bytes()\n    if digest(raw) != manifest['files']['operator_runtime_io.py']['output_sha256']:\n        raise RuntimeError('Support module checksum failed')\n    result['operator_runtime_io.py'] = raw\n    # TELEGRAM_MENU_1591R38: a support module like operator_runtime_io.py (no original on the server).\n    raw = (package/'telegram_menu.py').read_bytes()\n    if digest(raw) != manifest['files']['telegram_menu.py']['output_sha256']:\n        raise RuntimeError('Menu module checksum failed')\n    result['telegram_menu.py'] = raw\n"
OLD_I_IMPORT_R38 = "'import test_beeline as a; import server_controller as c; import symbol_matching as s; '\n"
NEW_I_IMPORT_R38 = "'import test_beeline as a; import server_controller as c; import symbol_matching as s; import telegram_menu as m; '\n"
OLD_I_ASSERT_R38 = '\'assert a._io1591.VERSION == "15.91-io"; assert s.MATCHER_VERSION == "14.1"; print("IMPORT OK")\''
NEW_I_ASSERT_R38 = '\'assert a._io1591.VERSION == "15.91-io"; assert s.MATCHER_VERSION == "14.1"; assert m.MENU_VERSION == "1591r38"; print("IMPORT OK")\''
OLD_T_FIX_R38 = "'operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher'})\n"
NEW_T_FIX_R38 = "'operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher','telegram_menu.py':b'menu'})\n"
OLD_T_CTRL_R38 = "'_restart_after_drain':lambda p:False,'_row_link_command':lambda a:'',\n"
NEW_T_CTRL_R38 = "'_restart_after_drain':lambda p:False,'_row_link_command':lambda a:'',\n                '_menu_mod':types.SimpleNamespace(TelegramMenu=lambda *a,**k:types.SimpleNamespace(show_menu=lambda *a,**k:None,show_status=lambda:None,tick=lambda:None,handle_callback=lambda cb:None,text_is_for_ai=lambda:True,ai_sent=lambda:None,retire_status_messages=lambda *a:0)),'BASE_DIR':Path(d),\n"
OLD_T_COMPILE_R38 = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py'):"
NEW_T_COMPILE_R38 = "for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py','telegram_menu.py'):"
README_NOTE_R38 = '\n\nРЕВИЗИЯ 38 (fix_package_1591.py)\nМеню бота (telegram_menu.py). Одно сообщение-панель с inline-кнопками: 📊 Статус (правится на месте\nтолько пока открыт, сам закрывается через час), 📱 Мои eSIM (последние оформленные eSIM по 10 на\nстраницу, карточка как прежний полный пуш, отметки 🆕/✅/❌, ссылка из журнала), 📜 Логи (события из\nжурнала за 2 дня постранично), 🤖 Спросить DeepSeek (следующее сообщение уходит DeepSeek, кнопка\nотмены), ▶️ ⏹ 🔄 📥 управление. Нижняя клавиатура убрана. Любое сообщение, кроме команд\n(/restart, /res), открывает меню; к DeepSeek попадает только текст после кнопки «Спросить».\nСтатус вкладок пишется runtime в status_snapshot.json, восемь редактируемых статусных сообщений\nревизии 27 отменены (при первом запуске они один раз переправляются на «статус в меню»).\nПуши об успехе и оплате стали короткими: номер eSIM, ФИО, дата рождения, строка и исходные данные,\nисход (для оплаты — ссылка заказа); полная карточка — в «Мои eSIM». Маркер: TELEGRAM_MENU_1591R38.\n'
# Revision 39: a 4xx on the selfreg requests after the click is a rejection; tabs per Chromium from env.
SIGN_REJECTED_MARKER = "SIGN_REJECTED_1591R39"
OLD_WENT_R39 = 'def _sign_went_through_1591r37(worker):\n    """True when the trace of the sign click (revision 25) holds a successful answer (status\n    2xx/3xx) to the signing request: the site accepted the signature, DeepSeek is not needed."""\n    trace = (worker or {}).get("sign_trace") or {}\n    for response in trace.get("responses") or []:\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if SIGN_OK_RE_1591R37.search(str(response.get("url") or "")) and 200 <= status < 400:\n            return True\n    return False\n'
NEW_WENT_R39 = 'def _sign_went_through_1591r37(worker):\n    """True when the site accepted the WHOLE signing step: a 2xx/3xx answer to the signing\n    request and no 4xx/5xx on any selfreg request of the click (SIGN_REJECTED_1591R39: a\n    checksignature 200 followed by sendpassportdata 412 is a rejection, not a success)."""\n    trace = (worker or {}).get("sign_trace") or {}\n    accepted = False\n    for response in trace.get("responses") or []:\n        url = str(response.get("url") or "")\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if SELFREG_RE_1591R39.search(url) and status >= 400:\n            return False\n        if SIGN_OK_RE_1591R37.search(url) and 200 <= status < 400:\n            accepted = True\n    return accepted\n\n\n# SIGN_REJECTED_1591R39\nSELFREG_RE_1591R39 = re.compile(r"esim-selfreg|checksignature|sendpassportdata|/sign\\b", re.I)\n\n\ndef _sign_rejected_1591r39(worker):\n    """The site\'s refusal after the click, as «412 PERSONAL_TOKEN_ERROR», or "" when none:\n    the first 4xx/5xx answer to a selfreg request in the trace of the sign click."""\n    trace = (worker or {}).get("sign_trace") or {}\n    for response in trace.get("responses") or []:\n        url = str(response.get("url") or "")\n        try:\n            status = int(response.get("status") or 0)\n        except (TypeError, ValueError):\n            status = 0\n        if status < 400 or not SELFREG_RE_1591R39.search(url):\n            continue\n        code = ""\n        m = re.search(r\'"codeValue"\\s*:\\s*"([A-Z_0-9]+)"\', str(response.get("body") or ""))\n        if m:\n            code = m.group(1)\n        step = "паспортные данные" if "sendpassportdata" in url.lower() else ("подпись" if SIGN_OK_RE_1591R37.search(url) else url.rsplit("/", 2)[-2][:30])\n        return f"{status} {code}".strip() + f" ({step})"\n    return ""\n'
OLD_SETTLE_HEAD_R39 = '    page = worker.get("page")\n    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26\n'
NEW_SETTLE_HEAD_R39 = '    page = worker.get("page")\n    rejected = _sign_rejected_1591r39(worker)  # SIGN_REJECTED_1591R39: the site refused the data\n    if rejected:\n        _finish_unverified_1591r24(base_dir, worker, f"сайт отверг данные после подписи: {rejected}")\n        return False\n    payment_text = _payment_page_1591r26(page) if page is not None else ""  # PAYMENT_STEP_1591R26\n'
OLD_AFTER_R39 = '            if _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n                print(\n                    f"[Вкладка {worker[\'id\']}] Запрос подписи ушёл и принят сайтом (след сети); "\n                    "DeepSeek не вызываю.",\n                    flush=True,\n                )\n            else:\n'
NEW_AFTER_R39 = '            rejected = _sign_rejected_1591r39(worker)  # SIGN_REJECTED_1591R39\n            if rejected:\n                print(\n                    f"[Вкладка {worker[\'id\']}] Сайт отверг данные после подписи ({rejected}); "\n                    "строка не подтверждена, DeepSeek не вызываю.",\n                    flush=True,\n                )\n                _finish_unverified_1591r24(base_dir, worker, f"сайт отверг данные после подписи: {rejected}")\n                return\n            if _sign_went_through_1591r37(worker):  # AI_ON_SIGN_FAIL_1591R37\n                print(\n                    f"[Вкладка {worker[\'id\']}] Запрос подписи ушёл и принят сайтом (след сети); "\n                    "DeepSeek не вызываю.",\n                    flush=True,\n                )\n            else:\n'
OLD_ERR_R39 = '        accepted = _sign_went_through_1591r37(worker)\n        _finish_unverified_1591r24(\n            base_dir, worker,\n            "после «Подписать договор» сайт показал registration/error"\n            + (" (запрос подписи при этом был принят сайтом)" if accepted else ""),\n        )\n'
NEW_ERR_R39 = '        rejected = _sign_rejected_1591r39(worker)  # SIGN_REJECTED_1591R39\n        accepted = _sign_went_through_1591r37(worker)\n        _finish_unverified_1591r24(\n            base_dir, worker,\n            "после «Подписать договор» сайт показал registration/error"\n            + (f": {rejected}" if rejected else (" (запрос подписи при этом был принят сайтом)" if accepted else "")),\n        )\n'
OLD_TABS_R39 = 'TABS_PER_BROWSER = 4  # SUCCESS_TAG_1591R17: four worker tabs\n'
NEW_TABS_R39 = '# SIGN_REJECTED_1591R39: BEELINE_TABS_PER_BROWSER=1 with BEELINE_BROWSERS=8 gives every tab its\n# own Chromium (own cookies, basket and mobile-id token: tabs of one Chromium overwrote each\n# other\'s personal token, 412 PERSONAL_TOKEN_ERROR on the passport data). Default 4 (r17).\ndef _tabs_per_browser_1591r39(default=4):\n    try:\n        value = int(str(os.environ.get("BEELINE_TABS_PER_BROWSER") or default).strip())\n    except ValueError:\n        value = default\n    return min(max(value, 1), 4)\n\n\nTABS_PER_BROWSER = _tabs_per_browser_1591r39()  # SUCCESS_TAG_1591R17: worker tabs per Chromium\n'
README_NOTE_R39 = '\n\nРЕВИЗИЯ 39 (fix_package_1591.py)\n(а) Отказ сайта после подписи. Вкладки одного Chromium делят cookies и localStorage, и персональный\nтокен mobile-id одной вкладки перезаписывался запросом SMS соседней: подпись принималась\n(checksignature 200), а паспортные данные отвергались (sendpassportdata 412 PERSONAL_TOKEN_ERROR).\nКод считал такую строку подписанной по одному checksignature 200. Теперь подпись принята только\nбез 4xx/5xx на запросах selfreg; при отказе строка сразу записывается как #неподтверждено с кодом\nсайта (без DeepSeek и без трёх минут ожидания), номер не помечается обработанным.\n(б) BEELINE_TABS_PER_BROWSER (1–4, по умолчанию 4): с BEELINE_BROWSERS=8 и\nBEELINE_TABS_PER_BROWSER=1 у каждой вкладки свой Chromium, как при ручном оформлении.\nМаркер: SIGN_REJECTED_1591R39.\n'
# Revision 40: an own browser context per worker tab inside the shared Chromium.
ISOLATED_CONTEXT_MARKER = "ISOLATED_CONTEXT_1591R40"
OLD_TAB_CONTEXT_R40 = '        browser = p.chromium.connect_over_cdp(cdp_url)\n        if not browser.contexts:\n            raise RuntimeError("Chromium не вернул общий контекст через CDP.")\n\n        context = browser.contexts[0]\n        page = context.new_page()\n'
NEW_TAB_CONTEXT_R40 = '        browser = p.chromium.connect_over_cdp(cdp_url)\n        if not browser.contexts:\n            raise RuntimeError("Chromium не вернул общий контекст через CDP.")\n\n        # ISOLATED_CONTEXT_1591R40: every worker gets its own browser context inside the shared\n        # Chromium: own cookies, localStorage, basket and mobile-id personal token, like a\n        # separate browser at the memory cost of one tab (tabs of one context overwrote each\n        # other\'s token: 412 PERSONAL_TOKEN_ERROR). Chromium disposes the context when this\n        # process ends; the parent still sees and closes its pages over CDP.\n        context = _isolated_context_1591r40(browser, tab_id)\n        page = context.new_page()\n'
OLD_TAB_DEF_R40 = 'def _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28\n'
NEW_TAB_DEF_R40 = '# ISOLATED_CONTEXT_1591R40\nISOLATED_CONTEXTS = str(os.environ.get("BEELINE_ISOLATED_CONTEXTS") or "1").strip().lower() not in {"0", "off", "no", "false"}\n\n\ndef _isolated_context_1591r40(browser, tab_id):\n    """A browser context of this worker\'s own (no viewport emulation: the real window size, as\n    the shared context had); the shared context when disabled or when Chromium refuses."""\n    if not ISOLATED_CONTEXTS:\n        return browser.contexts[0]\n    try:\n        context = browser.new_context(no_viewport=True)\n        print(f"[Вкладка {tab_id}] Отдельный контекст браузера создан (свои cookies и хранилище).", flush=True)\n        return context\n    except Exception as exc:\n        print(\n            f"[Вкладка {tab_id}] Отдельный контекст не создан ({type(exc).__name__}: {exc}); "\n            "работаю в общем контексте.",\n            flush=True,\n        )\n        return browser.contexts[0]\n\n\ndef _tab_process(tab_id, cdp_url, rows, base_dir_text, launch_ready_event, heartbeat=None, status_map=None, initial_row=None, total_rows=None, diagnostic_session_dir=None, success_queue=None, captcha_gate=None):  # TWO_BROWSERS_1591R28\n'
README_NOTE_R40 = '\n\nРЕВИЗИЯ 40 (fix_package_1591.py)\nСвой контекст браузера каждой вкладке внутри общего Chromium (browser.new_context через CDP):\nсвои cookies, localStorage, корзина и персональный токен mobile-id, как у отдельного браузера, а по\nпамяти как одна вкладка. Закрывает перезапись токена соседней вкладкой (412 PERSONAL_TOKEN_ERROR,\nревизия 39) и общую корзину (ревизии 32–33) без восьми Chromium. Chromium удаляет контекст, когда\nпроцесс вкладки завершается, поэтому вкладка успеха/оплаты не остаётся открытой после завершения\nworker (снимки blackbox и записи jsonl сохраняются). Выключить: BEELINE_ISOLATED_CONTEXTS=0.\nМаркер: ISOLATED_CONTEXT_1591R40.\n'
OLD_TEST_TAB_NS_R40 = "                'capture_blackbox':lambda *a:(_ for _ in ()).throw(AssertionError('unexpected phase'))}\n            extract({'_tab_process'},ns)\n"
NEW_TEST_TAB_NS_R40 = "                'capture_blackbox':lambda *a:(_ for _ in ()).throw(AssertionError('unexpected phase')),\n                '_isolated_context_1591r40':lambda b,t:b.contexts[0]}  # ISOLATED_CONTEXT_1591R40\n            extract({'_tab_process'},ns)\n"
# Revision 41: the tariff from the environment; a tariff configurator is confirmed with its defaults.
TARIFF_CONFIG_MARKER = "TARIFF_CONFIG_1591R41"
OLD_TARIFF_NAME_R41 = 'TARIFF_NAME = "подписка bee START"\n'
NEW_TARIFF_NAME_R41 = '# TARIFF_CONFIG_1591R41: BEELINE_TARIFF in the systemd unit picks another card of the picker\n# («для смарт часов», «подписка bee HIT»…), spelled exactly as on the site; default bee START.\nTARIFF_NAME = (os.environ.get("BEELINE_TARIFF") or "").strip() or "подписка bee START"\n'
OLD_CHOOSE_BREAK_R41 = '            if choose_clicked:\n                break\n\n            print(\n                f"После «выбрать» переход пока не подтверждён "\n'
NEW_CHOOSE_BREAK_R41 = '            if choose_clicked and page.locator(\'input#esim[name="sim"]\').count() == 0:\n                # TARIFF_CONFIG_1591R41: some tariffs open a configurator (GB, minutes, options)\n                # after the card\'s «выбрать»; confirm it with the defaults.\n                _confirm_tariff_configurator_1591r41(page, diagnostic)\n            if choose_clicked:\n                break\n\n            print(\n                f"После «выбрать» переход пока не подтверждён "\n'
OLD_CARD_DEF_R41 = 'def _tariff_card_button_1591r32(scope):\n'
NEW_CARD_DEF_R41 = '# TARIFF_CONFIG_1591R41\ndef _confirm_tariff_configurator_1591r41(page, diagnostic=None, timeout=8000):\n    """Some tariffs («для смарт часов») open a configurator after the card\'s «выбрать»: GB,\n    minutes, options and one «выбрать» with the price. Confirm it with the defaults; True when\n    the eSIM control appeared afterwards. Tariffs without a configurator (bee START) never get here\n    with a candidate: the picker holds many «выбрать», the basket page none."""\n    candidates = []\n    try:\n        dialogs = page.locator(\'[role="dialog"], [aria-modal="true"]\')\n        for index in range(min(dialogs.count(), 6)):\n            dialog = dialogs.nth(index)\n            try:\n                if not dialog.is_visible():\n                    continue\n                buttons = dialog.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n                if buttons.count() == 1 and buttons.first.is_visible():\n                    candidates.append(buttons.first)\n            except Exception:\n                continue\n    except Exception:\n        pass\n    if not candidates:\n        try:\n            buttons = page.get_by_role("button", name=_CHOOSE_BUTTON_RE)\n            visible = [buttons.nth(i) for i in range(min(buttons.count(), 30)) if buttons.nth(i).is_visible()]\n            if len(visible) == 1:\n                candidates.append(visible[0])\n        except Exception:\n            pass\n    if not candidates:\n        return False\n    print("Тариф с окном параметров: подтверждаю выбор с настройками по умолчанию...", flush=True)\n    if diagnostic is not None:\n        try:\n            diagnostic.write("tariff_configurator_confirm", tariff=TARIFF_NAME)\n        except Exception:\n            pass\n    try:\n        candidates[0].click(timeout=7000, no_wait_after=True)\n    except Exception as exc:\n        print(f"Кнопка подтверждения тарифа не нажалась: {type(exc).__name__}", flush=True)\n        return False\n    try:\n        page.locator(\'input#esim[name="sim"]\').wait_for(state="attached", timeout=timeout)\n        return True\n    except Exception:\n        return False\n\n\ndef _tariff_card_button_1591r32(scope):\n'
OLD_CARD_RULE_R41 = '            if card.get_by_text(_TARIFF_TITLE_RE_1591R32).count() != 1:\n                continue  # a container of several cards (or the basket plus the picker), not a card\n'
NEW_CARD_RULE_R41 = '            if card.get_by_role("button", name=_CHOOSE_BUTTON_RE).count() != 1:\n                continue  # a container of several cards (or the basket plus the picker), not a card (TARIFF_CONFIG_1591R41: any title)\n'
OLD_CHANGE_TITLES_R41 = '        titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)\n        for index in range(min(titles.count(), 4)):\n'
NEW_CHANGE_TITLES_R41 = '        titles = page.get_by_text(TARIFF_NAME, exact=True)  # TARIFF_CONFIG_1591R41: any tariff name\n        if titles.count() == 0:\n            titles = page.get_by_text(_TARIFF_TITLE_RE_1591R32)\n        for index in range(min(titles.count(), 4)):\n'
README_NOTE_R41 = '\n\nРЕВИЗИЯ 41 (fix_package_1591.py)\nТариф по настройке. BEELINE_TARIFF в окружении службы задаёт карточку окна «выберите тариф» (точно\nкак на сайте: «для смарт часов», «подписка bee HIT»…), по умолчанию «подписка bee START». У части\nтарифов после «выбрать» на карточке открывается окно параметров (гигабайты, минуты, опции) с одной\nкнопкой «выбрать» и ценой: бот подтверждает его с настройками по умолчанию и дальше идёт как обычно.\nПоиск карточки и кнопки «изменить» больше не требует названия вида «подписка bee …».\nМаркер: TARIFF_CONFIG_1591R41.\n'

# Revision 42: the journal names the tariff it really waits for. «На странице найдено название
# bee START» and «Точный текст bee START пока не появился» were literal strings since 15.91 while the
# check itself used TARIFF_NAME; with BEELINE_TARIFF=для смарт часов the journal still said bee START.
# The startup line now prints the tariff and where it came from.
TARIFF_LOG_MARKER = "TARIFF_LOG_1591R42"
OLD_TARIFF_SEEN_R42 = '            print("На странице найдено название bee START. Выбираю eSIM...")\n'
NEW_TARIFF_SEEN_R42 = '            print(f"На странице найдено название «{TARIFF_NAME}». Выбираю eSIM...")  # TARIFF_LOG_1591R42\n'
OLD_TARIFF_WAIT_R42 = '                "Точный текст bee START пока не появился; "\n                "проверяю фактические элементы оформления.",\n'
NEW_TARIFF_WAIT_R42 = '                f"Точный текст «{TARIFF_NAME}» пока не появился; "  # TARIFF_LOG_1591R42\n                "проверяю фактические элементы оформления.",\n'
OLD_TARIFF_START_R42 = '    print(f"Запускаю {BROWSER_COUNT} Chromium и {TAB_COUNT} рабочие вкладки. Общая очередь строк.")  # BROWSER_HANG_1591R18\n'
NEW_TARIFF_START_R42 = OLD_TARIFF_START_R42 + '    print(f"Тариф: «{TARIFF_NAME}»" + (" (BEELINE_TARIFF из окружения службы)" if (os.environ.get("BEELINE_TARIFF") or "").strip() else " (по умолчанию)"), flush=True)  # TARIFF_LOG_1591R42\n'
README_NOTE_R42 = '\n\nРЕВИЗИЯ 42 (fix_package_1591.py)\nЖурнал называет настоящий тариф. Строки «На странице найдено название bee START» и «Точный текст\nbee START пока не появился» были зашиты в код как есть, хотя проверка шла по TARIFF_NAME: при\nBEELINE_TARIFF=для смарт часов журнал всё равно писал про bee START. Теперь в них подставляется\nTARIFF_NAME, а при старте печатается «Тариф: «…» (BEELINE_TARIFF из окружения службы | по умолчанию)».\nМаркер: TARIFF_LOG_1591R42.\n'
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
RESIGNED_HANDLERS = {"queue_success_assist", "queue_error_assist", "tick_error_assist", "run_registration", "main",
                     "tick_post_auth_review", "tick_sign_wait"}
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
    proxy = str((cfg or {}).get('proxy') or '').strip()
    if proxy.lower() in ('direct', 'none', 'off', 'no', '-'):  # PROXY_DIRECT_1591R20: server outside RU, no proxy on purpose
        return
    if not proxy:
        raise RuntimeError('telegram_config.json has no "proxy". Add "proxy": "socks5h://user:password@host:port" '
                           '(the value that was TELEGRAM_DEFAULT_PROXY in the old code) before installing, '
                           'or "proxy": "direct" for a server outside Russia that reaches Telegram directly; '
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


MAX_REVISION = int(os.environ.get("FIX_1591_MAX_REVISION") or 99)  # build an older revision on purpose
WITHOUT_R31 = os.environ.get("FIX_1591_WITHOUT_R31") == "1"  # r32 without the r31 signing code (lite build)


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


def revision_of(source: str) -> int:
    """Revision of a test_beeline.py that carries every marker up to r30."""
    if TARIFF_LOG_MARKER in source:
        return 42   # the lite build (FIX_1591_WITHOUT_R31=1) is the same revision without the r31 signing code
    if TARIFF_CONFIG_MARKER in source:
        return 41
    if ISOLATED_CONTEXT_MARKER in source:
        return 40
    if SIGN_REJECTED_MARKER in source:
        return 39
    if TELEGRAM_MENU_MARKER in source:
        return 38
    if AI_SIGN_FAIL_MARKER in source:
        return 37
    if SIM_URL_MARKER in source:
        return 36
    if TRACE_COMPACT_MARKER in source:
        return 35
    if BROWSER_ENV_MARKER in source:
        return 34
    if TARIFF_CHANGE_MARKER in source:
        return 33
    if TARIFF_SCOPE_MARKER in source:
        return 32
    return 31 if SIGN_ROBUST_MARKER in source else 30


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
                                                TARIFF_MARKER, ROWSTART_MARKER, MATCHER_MARKER, OBSERVER_MARKER,
                                                PROFILE_MARKER, RESTART_MARKER, POSTAUTH_MARKER, PERSDATA_MARKER,
                                                ERRORSKIP_MARKER, SUCCESSTAG_MARKER, BROWSER_MARKER,
                                                PROFILE_LABELS_MARKER, PROXY_DIRECT_MARKER,
                                                RESTART_RELAUNCH_MARKER, ROW_SKIP_MARKER,
                                                FINAL_PAGE_MARKER, SIGNED_MARKER, SIGN_TRACE_MARKER,
                                                PAYMENT_MARKER, TG_RATE_MARKER, TWO_BROWSERS_MARKER,
                                                STALE_DRAIN_MARKER, AI_VERDICT_MARKER))\
            and (MAX_REVISION < 31 or WITHOUT_R31 or SIGN_ROBUST_MARKER in source)\
            and (MAX_REVISION < 32 or TARIFF_SCOPE_MARKER in source)\
            and (MAX_REVISION < 33 or TARIFF_CHANGE_MARKER in source)\
            and (MAX_REVISION < 34 or BROWSER_ENV_MARKER in source)\
            and (MAX_REVISION < 35 or TRACE_COMPACT_MARKER in source)\
            and (MAX_REVISION < 36 or SIM_URL_MARKER in source)\
            and (MAX_REVISION < 37 or AI_SIGN_FAIL_MARKER in source)\
            and (MAX_REVISION < 38 or TELEGRAM_MENU_MARKER in source)\
            and (MAX_REVISION < 39 or SIGN_REJECTED_MARKER in source)\
            and (MAX_REVISION < 40 or ISOLATED_CONTEXT_MARKER in source)\
            and (MAX_REVISION < 41 or TARIFF_CONFIG_MARKER in source)\
            and (MAX_REVISION < 42 or TARIFF_LOG_MARKER in source):
        print(f"Already revision {revision_of(source)}; nothing changed.")
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
    ctrl_source = (package / "server_controller.py").read_text("utf-8")
    ctrl_reflected = []
    for entry in edits["server_controller.py"]:
        snapshot = dict(entry)
        snapshot["_orig"] = entry
        ctrl_reflected.append(snapshot)
    new_ctrl = ctrl_source

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

    # 13 (r12). Text capture of the contract screen for the SUCCESS profile.
    if PROFILE_MARKER not in source:
        new_source = replace_once(new_source, OLD_CAPTURE_WRAPPER, PROFILE_TEXT_HELPER_R12 + NEW_CAPTURE_WRAPPER,
                                  "contract capture wrapper")
        add_edit(edits["test_beeline.py"], source, OLD_CAPTURE_WRAPPER, PROFILE_TEXT_HELPER_R12 + NEW_CAPTURE_WRAPPER,
                 reflected)

    # 14 (r13). Scheduled graceful restart: runtime drain + controller command and relaunch.
    if RESTART_MARKER not in source:
        anchor = "def parent_watchdog(processes, heartbeat):\n"
        for old, new, what in ((anchor, RESTART_HELPER_R13 + anchor, "restart helpers"),
                               (OLD_WORKER_GATE, NEW_WORKER_GATE, "worker restart gate"),
                               (OLD_DEAD_SKIP, NEW_DEAD_SKIP, "dead recovery skip"),
                               (OLD_CASCADE_HEAD, NEW_CASCADE_HEAD, "restart timer"),
                               (OLD_FINAL_LOOP, NEW_FINAL_LOOP, "no replacement while draining"),
                               (OLD_QUEUE_DONE, NEW_QUEUE_DONE, "restart exit")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        for old, new, what in ((OLD_CTRL_CLASS, NEW_CTRL_CLASS, "controller restart helpers"),
                               (OLD_CTRL_SLASH, NEW_CTRL_SLASH, "controller /restart"),
                               (OLD_CTRL_LOOP, NEW_CTRL_LOOP, "controller relaunch")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
        test_src = replace_once(test_src, OLD_TEST_CTRL_NS, NEW_TEST_CTRL_NS, "test_update.py controller fixture")

    # 15 (r14). /registration/error in the post-auth review follows the error policy.
    if POSTAUTH_MARKER not in source:
        new_source = replace_once(new_source, OLD_POST_AUTH_ERROR, NEW_POST_AUTH_ERROR, "post-auth error route")
        add_edit(edits["test_beeline.py"], source, OLD_POST_AUTH_ERROR, NEW_POST_AUTH_ERROR, reflected)

    # 16 (r15). Deterministic operator refusal: skip the row without analysis or retry.
    if PERSDATA_MARKER not in source:
        new_source = replace_once(new_source, OLD_ENTER_ERROR_GUARD, NEW_ENTER_ERROR_GUARD, "enter_error_guard")
        add_edit(edits["test_beeline.py"], source, OLD_ENTER_ERROR_GUARD, NEW_ENTER_ERROR_GUARD, reflected)

    # 17 (r16). Every registration error: replace the tab and skip the row, no DeepSeek.
    if ERRORSKIP_MARKER not in source:
        for old, new, what in ((OLD_GUARD_HEAD_R15, NEW_GUARD_HEAD_R16, "enter_error_guard head r16"),
                               (OLD_GUARD_TAIL, NEW_GUARD_TAIL_R16, "enter_error_guard tail r16"),
                               (OLD_MISSION_R5_TEXT, NEW_MISSION_R16_TEXT, "mission rule r16"),
                               (OLD_AGENT_BLOCK_R5, NEW_AGENT_BLOCK_R16, "agent error block r16"),
                               (OLD_QUEUE_SENTENCE_R5, NEW_QUEUE_SENTENCE_R16, "queue_error_assist text r16")):
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

    # 18 (r17). #успешно on the SUCCESS push; four tabs per Chromium.
    if SUCCESSTAG_MARKER not in source:
        for old, new, what in ((OLD_SUCCESS_HEAD, NEW_SUCCESS_HEAD, "success message tag"),
                               (OLD_TABS_LINE, NEW_TABS_LINE, "four tabs")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 19 (r18). Whole-browser restart when Chromium stops answering CDP; real "\n" in the status.
    if BROWSER_MARKER not in source:
        for old, new, what in ((OLD_WAIT_CDP, OLD_WAIT_CDP + BROWSER_HELPERS_R18, "browser hang helpers"),
                               (OLD_CDP_CONNECT_R6, NEW_CDP_CONNECT_R18, "cdp connect note"),
                               (OLD_CDP_EXCEPT_R6, NEW_CDP_EXCEPT_R18, "cdp except note"),
                               (OLD_EXPERIMENT_LINE, NEW_EXPERIMENT_LINE, "startup banner"),
                               (OLD_DEAD_HEAD, NEW_DEAD_HEAD, "restart_browser_instance"),
                               (OLD_CLOSE_FAIL, NEW_CLOSE_FAIL, "watchdog browser hang trigger"),
                               (OLD_STATUS_NL, NEW_STATUS_NL, "watchdog status line break")):
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

    # 20 (r19). Profile fields on the personal-data form that carry no label of their own.
    if PROFILE_LABELS_MARKER not in source:
        for old, new, what in ((OLD_FINAL_CAPTURE_DEF, NEW_FINAL_CAPTURE_DEF, "profile label helpers"),
                               (OLD_ALIASES_HEAD, NEW_ALIASES_HEAD, "profile aliases head"),
                               (OLD_ALIASES_ADDRESS, NEW_ALIASES_ADDRESS, "profile aliases address"),
                               (OLD_MATCH_LOOP, NEW_MATCH_LOOP, "profile match loop")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)
        test_src = replace_once(test_src, OLD_TEST_PROFILE_NS, NEW_TEST_PROFILE_NS, "test_update.py profile fixture")

    # 21 (r20). "proxy": "direct" — a server outside Russia talks to Telegram without a proxy.
    if PROXY_DIRECT_MARKER not in source:
        for old, new, what in ((OLD_PROXY_FN_DEF, NEW_PROXY_FN_DEF, "direct proxy values"),
                               (OLD_PROXY_EMPTY_CHECK, NEW_PROXY_EMPTY_CHECK, "direct proxy check")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 22 (r21). Relaunch after the drain by marker, not only by the exit code xvfb-run may lose.
    if RESTART_RELAUNCH_MARKER not in source:
        for old, new, what in ((OLD_CLEAR_DRAIN_R13, NEW_CLEAR_DRAIN_R21, "relaunch helper"),
                               (OLD_DRAIN_EXIT_R13, NEW_DRAIN_EXIT_R21, "drain exit marker"),
                               (OLD_BROWSER_EXIT_R18, NEW_BROWSER_EXIT_R21, "browser exit marker")):
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
        for old, new, what in ((OLD_CTRL_RELAUNCH_R13, NEW_CTRL_RELAUNCH_R21, "controller relaunch by marker"),
                               (OLD_CTRL_REAP, NEW_CTRL_REAP_R21, "controller reap"),
                               (OLD_CTRL_INIT, NEW_CTRL_INIT_R21, "controller last_code")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            if old in ctrl_source:
                add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
            else:
                for change in edits["server_controller.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 23 (r22). INVALID_ROW retried once in a fresh tab; skipped rows recorded as processed.
    if ROW_SKIP_MARKER not in source:
        for old, new, what in ((OLD_RESET_STATE_DEF, NEW_RESET_STATE_DEF, "invalid row helpers"),
                               (OLD_FINISH_HEAD, NEW_FINISH_HEAD_R22, "finish_worker_row invalid row"),
                               (OLD_R5_SKIP_TAIL, NEW_R5_SKIP_TAIL_R22, "r5 skip remembers the row"),
                               (OLD_R15_SKIP_TAIL, NEW_R15_SKIP_TAIL_R22, "r15 skip remembers the row")):
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

    # 24 (r23). Final (contract) page URL and document links in the success record and push.
    if FINAL_PAGE_MARKER not in source:
        for old, new, what in ((OLD_DIAG_KEEP, NEW_DIAG_KEEP, "diagnostic sessions to keep"),
                               (OLD_WRITE_SUCCESS_HEAD, NEW_WRITE_SUCCESS_HEAD, "final page helpers"),
                               (OLD_REC_PROFILE, NEW_REC_PROFILE, "success record final page"),
                               (OLD_SUCCESS_TAIL, NEW_SUCCESS_TAIL, "success message final page")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 25 (r24). Success needs positive evidence of the signed contract; otherwise UNVERIFIED.
    if SIGNED_MARKER not in source:
        for old, new, what in ((OLD_SIGN_WAIT_DEF, NEW_SIGN_WAIT_DEF, "signed evidence helpers"),
                               (OLD_SIGN_WAIT_FINAL, NEW_SIGN_WAIT_FINAL, "sign wait settle"),
                               (OLD_REVIEW_FINAL, NEW_REVIEW_FINAL, "post-auth review settle")):
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

    # 26 (r25). Trace of the server's answers around the «Подписать договор» click.
    if SIGN_TRACE_MARKER not in source:
        for old, new, what in ((OLD_SIGN_WAIT_DEF_R24, NEW_SIGN_WAIT_DEF_R25, "sign trace helpers"),
                               (OLD_SIGN_CALL_R14, NEW_SIGN_CALL_R25, "sign call trace"),
                               (OLD_UNVERIFIED_REC_R24, NEW_UNVERIFIED_REC_R25, "unverified record trace"),
                               (OLD_UNVERIFIED_MSG_R24, NEW_UNVERIFIED_MSG_R25, "unverified message trace"),
                               (OLD_SUCCESS_REC_R23, NEW_SUCCESS_REC_R25, "success record trace"),
                               (OLD_MATCH_SKIP_R19, NEW_MATCH_SKIP_R25, "profile junk values")):
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

    # 27 (r26). The payment step after the signature is its own outcome, not a success.
    if PAYMENT_MARKER not in source:
        for old, new, what in ((OLD_SETTLE_DEF_R24, NEW_SETTLE_DEF_R26, "payment helpers"),
                               (OLD_SETTLE_HEAD_R24, NEW_SETTLE_HEAD_R26, "settle payment check")):
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

    # 28 (r27). Telegram status logger within the Bot API limits; messages reused across restarts.
    if TG_RATE_MARKER not in source:
        for old, new, what in ((OLD_LOGGER_DEF, NEW_LOGGER_DEF, "tg rate helpers"),
                               (OLD_LOGGER_STATE, NEW_LOGGER_STATE, "logger state"),
                               (OLD_LOGGER_CREATE, NEW_LOGGER_CREATE, "logger message reuse"),
                               (OLD_LOGGER_EDIT, NEW_LOGGER_EDIT, "logger rate-limited edits")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 29 (r28). Two Chromium instances; captchas of different tabs do not pile up.
    if TWO_BROWSERS_MARKER not in source:
        for old, new, what in ((OLD_BROWSER_COUNT, NEW_BROWSER_COUNT, "two browsers + captcha gate"),
                               (OLD_TAB_PROCESS_DEF, NEW_TAB_PROCESS_DEF, "tab process captcha gate arg"),
                               (OLD_CONFIGURE_MATCHER, NEW_CONFIGURE_MATCHER, "tab process captcha gate set"),
                               (OLD_PROCESSES_INIT, NEW_PROCESSES_INIT, "captcha gate semaphore"),
                               (OLD_SPAWN_KWARGS, NEW_SPAWN_KWARGS, "spawn captcha gate")):
            new_source = replace_once(new_source, old, new, what)
            add_edit(edits["test_beeline.py"], source, old, new, reflected)

    # 30 (r29). A drain file left by a killed run is discarded at start.
    if STALE_DRAIN_MARKER not in source:
        old, new, what = OLD_RESTART_TIMER_R13, NEW_RESTART_TIMER_R29, "stale drain reset"
        new_source = replace_once(new_source, old, new, what)
        for change in edits["test_beeline.py"]:
            joined = "".join(change["replacement"])
            if old in joined:
                change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                break
        else:
            raise SystemExit(f"edits.json: earlier entry for {what} not found")

    # 31 (r30). DeepSeek's mandate and VERDICT line (prompt only; the code part is r31).
    if AI_VERDICT_MARKER not in source:
        for old, new, what in ((OLD_ASSIST_TAIL, NEW_ASSIST_TAIL_R30, "assist mandate"),
                               (OLD_MISSION_BULLET, NEW_MISSION_BULLET_R30, "mission verdict")):
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

    # 32 (r31). Deterministic signing, DeepSeek/runtime coordination, the verdict read by the code.
    if SIGN_ROBUST_MARKER not in source and MAX_REVISION >= 31 and not WITHOUT_R31:
        for old, new, what in ((OLD_POST_AUTH_DEF, NEW_POST_AUTH_DEF, "sign robust helpers"),
                               (OLD_BUTTON_BLOCK, NEW_BUTTON_BLOCK_R30, "yield to deepseek"),
                               (OLD_SIGN_CALL_R25, NEW_SIGN_CALL_R30, "sign prepare + retry"),
                               (OLD_OBSERVER_PRINT, NEW_OBSERVER_PRINT, "observer busy flag"),
                               (OLD_OBSERVER_COMPLETE, NEW_OBSERVER_COMPLETE, "observer verdict"),
                               (OLD_OBSERVER_FAIL, NEW_OBSERVER_FAIL, "observer busy off"),
                               *(((OLD_SETTLE_PAYMENT_R26, NEW_SETTLE_PAYMENT_R30, "settle verdict"),)
                                 if OLD_SETTLE_PAYMENT_R26 in new_source else
                                 ((OLD_SETTLE_PAYMENT_R26_WITH_R37, NEW_SETTLE_PAYMENT_R30_WITH_R37, "settle verdict (lite upgrade)"),))):
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
        test_src = replace_once(test_src, OLD_TEST_OBSERVER_NS, NEW_TEST_OBSERVER_NS, "test_update.py observer fixture")

    # 33 (r32). Tariff card inside the picker, same-row restart cap, drain deadline.
    if TARIFF_SCOPE_MARKER not in source and MAX_REVISION >= 32:
        for old, new, what in ((OLD_TARIFF_FINDER_R32, NEW_TARIFF_FINDER_R32, "tariff card in picker"),
                               (OLD_ROW_READY_R32, NEW_ROW_READY_R32, "same-row restart cap"),
                               (OLD_RESET_DEF_R32, NEW_RESET_DEF_R32, "row restart helpers"),
                               (OLD_DRAIN_TICK_R32, NEW_DRAIN_TICK_R32, "drain deadline tick"),
                               (OLD_LOAD_PROCESSED_R32, NEW_LOAD_PROCESSED_R32, "drain deadline helpers"),
                               (OLD_DEAD_SPAWN_R32, NEW_DEAD_SPAWN_R32, "respawn cap (dead recovery)"),
                               (OLD_STALL_SPAWN_R32, NEW_STALL_SPAWN_R32, "respawn cap (watchdog)")):
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

    # 34 (r33). The tariff «изменить», not the region one.
    if TARIFF_CHANGE_MARKER not in source and MAX_REVISION >= 33:
        for old, new, what in ((OLD_TARIFF_CHANGE_R33, NEW_TARIFF_CHANGE_R33, "tariff change button"),
                               (OLD_TARIFF_HELPER_ANCHOR_R33, NEW_TARIFF_HELPER_R33, "tariff change helper")):
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

    # 35 (r34). BROWSER_COUNT from BEELINE_BROWSERS.
    if BROWSER_ENV_MARKER not in source and MAX_REVISION >= 34:
        old, new, what = OLD_BROWSER_COUNT_R34, NEW_BROWSER_COUNT_R34, "browser count from env"
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

    # 36 (r35). Compact sign trace in Telegram.
    if TRACE_COMPACT_MARKER not in source and MAX_REVISION >= 35:
        old, new, what = OLD_TRACE_LINES_R35, NEW_TRACE_LINES_R35, "compact sign trace"
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

    # 37 (r36). The pushed order link is the current row's.
    if SIM_URL_MARKER not in source and MAX_REVISION >= 36:
        for old, new, what in ((OLD_PENDING_URL_R36, NEW_PENDING_URL_R36, "offer url per row"),
                               (OLD_RESET_STATE_R36, NEW_RESET_STATE_R36, "reset offer memory")):
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
        # /res <номер eSIM | строка>: the controller answers with the row's real order link.
        for old, new, what in ((OLD_CTRL_IMPORT_R36, NEW_CTRL_IMPORT_R36, "controller import re"),
                               (OLD_CTRL_RESTART_BRANCH_R36, NEW_CTRL_RESTART_BRANCH_R36, "controller /res branch"),
                               (OLD_CTRL_RELAUNCH_DEF_R36, NEW_CTRL_ROWLINK_R36, "controller /res command")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            if old in ctrl_source:
                add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
            else:
                for change in edits["server_controller.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        test_src = replace_once(test_src, OLD_TEST_CTRL_NS_R36, NEW_TEST_CTRL_NS_R36, "test_update.py controller fixture (/res)")

    # 38 (r37). DeepSeek only when the signature did not go through.
    if AI_SIGN_FAIL_MARKER not in source and MAX_REVISION >= 37:
        for old, new, what in ((OLD_GUARD_DEF_R37, NEW_GUARD_DEF_R37, "sign went through helper"),
                               (OLD_GUARD_ASSIST_R37, NEW_GUARD_ASSIST_R37, "no assist at guard entry"),
                               (OLD_AFTER_CLICK_R37, NEW_AFTER_CLICK_R37, "assist only when unsent"),
                               (OLD_SIGN_ERROR_R37, NEW_SIGN_ERROR_R37, "error after sign: unverified, no assist"),
                               (OLD_EVIDENCE_R37, NEW_EVIDENCE_R37, "network acceptance as evidence")):
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

    # 39 (r38). The inline menu: module, controller routing, installer, status snapshot, short pushes.
    if TELEGRAM_MENU_MARKER not in source and MAX_REVISION >= 38:
        if not TELEGRAM_MENU_SOURCE.is_file():
            raise SystemExit(f"{TELEGRAM_MENU_SOURCE}: missing; nothing changed")
        menu_source = TELEGRAM_MENU_SOURCE.read_text("utf-8")
        if 'MENU_VERSION = "1591r38"' not in menu_source:
            raise SystemExit("telegram_menu.py is not the revision 38 module; nothing changed")
        compile(menu_source, "telegram_menu.py", "exec")
        (package / "telegram_menu.py").write_text(menu_source, "utf-8")
        manifest["files"]["telegram_menu.py"] = {
            "output_sha256": hashlib.sha256(menu_source.encode("utf-8")).hexdigest(),
        }
        for old, new, what in ((OLD_STATUS_SYNC_R38, NEW_STATUS_SYNC_R38, "status snapshot"),
                               (OLD_LOGGER_START_R38, NEW_LOGGER_START_R38, "logger without status messages"),
                               (OLD_SUCCESS_MSG_R38, NEW_SUCCESS_MSG_R38, "short success push"),
                               (OLD_PAYMENT_MSG_R38, NEW_PAYMENT_MSG_R38, "short payment push"),
                               (OLD_REC_TIME_R38, NEW_REC_TIME_R38, "success record time")):
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
        for old, new, what in ((OLD_C_IMPORT_R38, NEW_C_IMPORT_R38, "controller menu import"),
                               (OLD_C_MARKUP_R38, NEW_C_MARKUP_R38, "controller keyboard removed"),
                               (OLD_C_PROC_R38, NEW_C_PROC_R38, "controller menu object"),
                               (OLD_C_HELLO_R38, NEW_C_HELLO_R38, "controller greeting"),
                               (OLD_C_LOOP_R38, NEW_C_LOOP_R38, "controller menu tick"),
                               (OLD_C_ALLOWED_R38, NEW_C_ALLOWED_R38, "controller callback updates"),
                               (OLD_C_MSG_R38, NEW_C_MSG_R38, "controller callback routing"),
                               (OLD_C_START_R38, NEW_C_START_R38, "controller /start"),
                               (OLD_C_UNKNOWN_R38, NEW_C_UNKNOWN_R38, "controller unknown command"),
                               (OLD_C_AI_R38, NEW_C_AI_R38, "controller ai gate")):
            new_ctrl = replace_once(new_ctrl, old, new, what)
            if old in ctrl_source:
                add_edit(edits["server_controller.py"], ctrl_source, old, new, ctrl_reflected)
            else:
                for change in edits["server_controller.py"]:
                    joined = "".join(change["replacement"])
                    if old in joined:
                        change["replacement"] = joined.replace(old, new, 1).splitlines(keepends=True)
                        break
                else:
                    raise SystemExit(f"edits.json: earlier controller entry for {what} not found")
        for old, new, what in ((OLD_I_FILES_R38, NEW_I_FILES_R38, "install.py FILES (menu)"),
                               (OLD_I_SUPPORT_R38, NEW_I_SUPPORT_R38, "install.py menu module"),
                               (OLD_I_IMPORT_R38, NEW_I_IMPORT_R38, "install.py import (menu)"),
                               (OLD_I_ASSERT_R38, NEW_I_ASSERT_R38, "install.py version assert (menu)")):
            install_src = replace_once(install_src, old, new, what)
        for old, new, what in ((OLD_T_FIX_R38, NEW_T_FIX_R38, "test_update.py installer fixture (menu)"),
                               (OLD_T_CTRL_R38, NEW_T_CTRL_R38, "test_update.py controller fixture (menu)"),
                               (OLD_T_COMPILE_R38, NEW_T_COMPILE_R38, "test_update.py compile list (menu)")):
            test_src = replace_once(test_src, old, new, what)

    # 40 (r39). A site refusal after the click is a rejection; tabs per Chromium from the environment.
    if SIGN_REJECTED_MARKER not in source and MAX_REVISION >= 39:
        for old, new, what in ((OLD_WENT_R39, NEW_WENT_R39, "strict acceptance + rejection helper"),
                               (OLD_SETTLE_HEAD_R39, NEW_SETTLE_HEAD_R39, "settle: rejection first"),
                               (OLD_AFTER_R39, NEW_AFTER_R39, "after click: rejection"),
                               (OLD_ERR_R39, NEW_ERR_R39, "error page: rejection code"),
                               (OLD_TABS_R39, NEW_TABS_R39, "tabs per browser from env")):
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

    # 41 (r40). An own browser context per worker tab.
    if ISOLATED_CONTEXT_MARKER not in source and MAX_REVISION >= 40:
        for old, new, what in ((OLD_TAB_DEF_R40, NEW_TAB_DEF_R40, "isolated context helper"),
                               (OLD_TAB_CONTEXT_R40, NEW_TAB_CONTEXT_R40, "worker uses its own context")):
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
        test_src = replace_once(test_src, OLD_TEST_TAB_NS_R40, NEW_TEST_TAB_NS_R40, "test_update.py _tab_process fixture (context)")

    # 42 (r41). The tariff from the environment; a configurator after the card is confirmed.
    if TARIFF_CONFIG_MARKER not in source and MAX_REVISION >= 41:
        for old, new, what in ((OLD_TARIFF_NAME_R41, NEW_TARIFF_NAME_R41, "tariff from env"),
                               (OLD_CHOOSE_BREAK_R41, NEW_CHOOSE_BREAK_R41, "configurator confirm call"),
                               (OLD_CARD_DEF_R41, NEW_CARD_DEF_R41, "configurator confirm helper"),
                               (OLD_CARD_RULE_R41, NEW_CARD_RULE_R41, "card rule: one choose button"),
                               (OLD_CHANGE_TITLES_R41, NEW_CHANGE_TITLES_R41, "change button near any tariff name")):
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

    # 43 (r42). The journal names the configured tariff instead of the literal bee START.
    if TARIFF_LOG_MARKER not in source and MAX_REVISION >= 42:
        for old, new, what in ((OLD_TARIFF_SEEN_R42, NEW_TARIFF_SEEN_R42, "tariff seen message"),
                               (OLD_TARIFF_WAIT_R42, NEW_TARIFF_WAIT_R42, "tariff wait message"),
                               (OLD_TARIFF_START_R42, NEW_TARIFF_START_R42, "tariff at startup")):
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

    built_revision = revision_of(new_source)
    compile(new_source, "test_beeline.py", "exec")
    compile(new_ctrl, "server_controller.py", "exec")
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
    ctrl_meta = manifest["files"]["server_controller.py"]
    previous_ctrl = set(ctrl_meta.get("previous_output_sha256", [])) | CONTROLLER_ACCEPTED_SHAS
    ctrl_meta["previous_output_sha256"] = sorted(previous_ctrl)
    ctrl_meta["output_sha256"] = hashlib.sha256(new_ctrl.encode("utf-8")).hexdigest()
    manifest["revision"] = built_revision

    app.write_text(new_source, "utf-8")
    (package / "server_controller.py").write_text(new_ctrl, "utf-8")
    (package / "test_update.py").write_text(test_src, "utf-8")
    (package / "install.py").write_text(install_src, "utf-8")
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    (package / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=2), "utf-8")
    readme = package / "README.txt"
    for heading, note in (("РЕВИЗИЯ 2", README_NOTE), ("РЕВИЗИЯ 3", README_NOTE_R3), ("РЕВИЗИЯ 4", README_NOTE_R4),
                          ("РЕВИЗИЯ 5", README_NOTE_R5), ("РЕВИЗИЯ 6", README_NOTE_R6),
                          ("РЕВИЗИЯ 7", README_NOTE_R7), ("РЕВИЗИЯ 8", README_NOTE_R8),
                          ("РЕВИЗИЯ 9", README_NOTE_R9), ("РЕВИЗИЯ 10", README_NOTE_R10),
                          ("РЕВИЗИЯ 11", README_NOTE_R11), ("РЕВИЗИЯ 12", README_NOTE_R12),
                          ("РЕВИЗИЯ 13", README_NOTE_R13), ("РЕВИЗИЯ 14", README_NOTE_R14),
                          ("РЕВИЗИЯ 15", README_NOTE_R15), ("РЕВИЗИЯ 16", README_NOTE_R16),
                          ("РЕВИЗИЯ 17", README_NOTE_R17), ("РЕВИЗИЯ 18", README_NOTE_R18),
                          ("РЕВИЗИЯ 19", README_NOTE_R19),
                          ("РЕВИЗИЯ 20", README_NOTE_R20),
                          ("РЕВИЗИЯ 21", README_NOTE_R21),
                          ("РЕВИЗИЯ 22", README_NOTE_R22),
                          ("РЕВИЗИЯ 23", README_NOTE_R23),
                          ("РЕВИЗИЯ 24", README_NOTE_R24),
                          ("РЕВИЗИЯ 25", README_NOTE_R25),
                          ("РЕВИЗИЯ 26", README_NOTE_R26),
                          ("РЕВИЗИЯ 27", README_NOTE_R27),
                          ("РЕВИЗИЯ 28", README_NOTE_R28),
                          ("РЕВИЗИЯ 29", README_NOTE_R29),
                          ("РЕВИЗИЯ 30", README_NOTE_R30),
                          *((("РЕВИЗИЯ 31", README_NOTE_R31),) if SIGN_ROBUST_MARKER in new_source else ()),
                          *((("РЕВИЗИЯ 32", README_NOTE_R32),) if built_revision >= 32 else ()),
                          *((("РЕВИЗИЯ 33", README_NOTE_R33),) if built_revision >= 33 else ()),
                          *((("РЕВИЗИЯ 34", README_NOTE_R34),) if built_revision >= 34 else ()),
                          *((("РЕВИЗИЯ 35", README_NOTE_R35),) if built_revision >= 35 else ()),
                          *((("РЕВИЗИЯ 36", README_NOTE_R36),) if built_revision >= 36 else ()),
                          *((("РЕВИЗИЯ 37", README_NOTE_R37),) if built_revision >= 37 else ()),
                          *((("РЕВИЗИЯ 38", README_NOTE_R38),) if built_revision >= 38 else ()),
                          *((("РЕВИЗИЯ 39", README_NOTE_R39),) if built_revision >= 39 else ()),
                          *((("РЕВИЗИЯ 40", README_NOTE_R40),) if built_revision >= 40 else ()),
                          *((("РЕВИЗИЯ 41", README_NOTE_R41),) if built_revision >= 41 else ()),
                          *((("РЕВИЗИЯ 42", README_NOTE_R42),) if built_revision >= 42 else ())):
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
    verification.update({"python": sys.version, "revision": built_revision, "result": "OK",
                         "tests": int(ran.split()[1]) if ran else None,
                         "exact_input_sha256": manifest["files"]})
    (package / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), "utf-8")

    sums = [f"{sha(package / name)}  {name}" for name in
            ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "symbol_matching.py", "telegram_menu.py",
             "install.py", "test_update.py", "manifest.json", "edits.json", "README.txt", "verification.json",
             "test_results.txt", "install_preflight_results.txt") if (package / name).is_file()]
    (package / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", "utf-8")
    for line in ("__pycache__",):
        for cache in package.glob(line):
            for f in cache.iterdir():
                f.unlink()
            cache.rmdir()
    print(ran + " — OK")
    print(f"Revision {built_revision} applied to", package)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
