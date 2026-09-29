"""Offline tests for fix_package_1591.py. Set PACKAGE_1591_DIR to an extracted package for the full run."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fix_package_1591 as fix

PACKAGE = os.environ.get("PACKAGE_1591_DIR")


def exec_functions(source, names, ns):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names), (names, [n.name for n in nodes])
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "package-source", "exec"), ns)
    return ns


class SignatureTests(unittest.TestCase):
    def test_signature_ignores_positions_and_empty_fields(self):
        a = ast.parse("def f(x):\n    return x\n").body[0]
        b = ast.parse("\n\ndef f(x):\n\n    return   x\n").body[0]
        self.assertEqual(fix.handler_hash(a), fix.handler_hash(b))
        self.assertNotIn("None", repr(fix.ast_signature(a)))
    def test_signature_sees_real_changes(self):
        a = ast.parse("def f(x):\n    return x\n").body[0]
        b = ast.parse("def f(x):\n    return x + 1\n").body[0]
        self.assertNotEqual(fix.handler_hash(a), fix.handler_hash(b))


class EditMappingTests(unittest.TestCase):
    def test_new_edit_uses_input_line_numbers(self):
        original = "".join(f"line{i}\n" for i in range(20))
        edits = [{"start": 2, "end": 2, "replacement": ["ins-a\n", "ins-b\n"]},
                 {"start": 5, "end": 7, "replacement": ["repl\n"]}]
        lines = original.splitlines(keepends=True)
        for change in reversed(edits):
            lines[change["start"]:change["end"]] = change["replacement"]
        output = "".join(lines)
        fix.add_edit(edits, output, "line12\nline13\n", "new12\nnew13\nnew14\n")
        lines = original.splitlines(keepends=True)
        for change in reversed(edits):
            lines[change["start"]:change["end"]] = change["replacement"]
        self.assertEqual("".join(lines), output.replace("line12\nline13\n", "new12\nnew13\nnew14\n"))


@unittest.skipUnless(PACKAGE and Path(PACKAGE, "test_beeline.py").is_file(), "PACKAGE_1591_DIR not set")
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pkg = Path(cls.tmp.name) / "pkg"
        shutil.copytree(PACKAGE, cls.pkg, ignore=shutil.ignore_patterns("__pycache__"))
        source = (cls.pkg / "test_beeline.py").read_text("utf-8")
        speed = cls.pkg / "symbol_matching.py"
        if (any(m not in source for m in (fix.MARKER, fix.PROXY_MARKER, fix.ASSIST_MARKER, fix.ERROR_MARKER, fix.OVERLAY_MARKER, fix.TARIFF_MARKER, fix.ROWSTART_MARKER, fix.MATCHER_MARKER, fix.OBSERVER_MARKER, fix.PROFILE_MARKER, fix.RESTART_MARKER, fix.POSTAUTH_MARKER, fix.PERSDATA_MARKER, fix.ERRORSKIP_MARKER, fix.SUCCESSTAG_MARKER, fix.BROWSER_MARKER))
                or not speed.is_file() or fix.MATCHER_SPEED_MARKER not in speed.read_text("utf-8")):
            subprocess.run([sys.executable, fix.__file__, str(cls.pkg)], check=True, capture_output=True, text=True)
        cls.source = (cls.pkg / "test_beeline.py").read_text("utf-8")
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _logger(self, enqueue):
        node = next(n for n in ast.parse(self.source).body if isinstance(n, ast.FunctionDef)
                    and n.name == "telegram_logger_process")
        sent, queued = [], []
        class Q:
            def __init__(self, items): self.items = list(items)
            def get_nowait(self):
                if not self.items: raise Exception("empty")
                return self.items.pop(0)
        class Stop:
            def __init__(self): self.n = 0
            def is_set(self):
                self.n += 1
                return self.n > 1
        def telegram_api(cfg, method, payload):
            sent.append((method, payload))
            return {"ok": True, "result": {"message_id": len(sent)}}, None
        io = types.SimpleNamespace(
            enqueue_notice=lambda ns, chat, text, markup=None: queued.append((chat, text)) if enqueue else (_ for _ in ()).throw(RuntimeError("no outbox")),
            split_text=lambda text, limit=3500: [text[i:i + limit] for i in range(0, len(text), limit)],
            redact=str)
        ns = {"load_telegram_config": lambda: {"chat_id": "42"}, "telegram_api": telegram_api, "_io1591": io,
              "time": __import__("time"), "TAB_COUNT": 1, "print": lambda *a, **k: None}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        ns["telegram_logger_process"]({}, Q(["S" * 9000]), Stop())
        return sent, queued

    def test_success_push_is_queued_untruncated(self):
        sent, queued = self._logger(enqueue=True)
        self.assertEqual(queued, [("42", "S" * 9000)])
        self.assertFalse([p for m, p in sent if m == "sendMessage" and "S" in p.get("text", "")])
    def test_success_push_fallback_is_split_not_cut(self):
        sent, queued = self._logger(enqueue=False)
        # The logger also creates the ten slot-status messages; keep only the SUCCESS push parts.
        pushes = [p["text"] for m, p in sent if m == "sendMessage" and set(p["text"]) == {"S"}]
        self.assertEqual("".join(pushes), "S" * 9000)
        self.assertTrue(all(len(x) <= 3500 for x in pushes))
    def test_package_suite_and_checksums(self):
        run = subprocess.run([sys.executable, "-m", "unittest", "-q", "test_update"], cwd=self.pkg,
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        sums = subprocess.run(["sha256sum", "-c", "SHA256SUMS.txt"], cwd=self.pkg, capture_output=True, text=True)
        self.assertEqual(sums.returncode, 0, sums.stdout)
    def _check(self, src, proxy, matcher=None):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)
            for name in ("test_beeline.py", "server_controller.py"):
                shutil.copy2(src / name, app / name)
            # The server runs symbol_matching.py 14.0 (the reference copy) unless a test says otherwise.
            (app / "symbol_matching.py").write_bytes(matcher if matcher is not None
                                                     else fix.SYMBOL_MATCHING_REFERENCE.read_bytes())
            if proxy:
                (app / "telegram_config.json").write_text(json.dumps({"proxy": "socks5h://u:p@h:1"}))
            return subprocess.run([sys.executable, str(self.pkg / "install.py"), "--app", str(app)],
                                  capture_output=True, text=True, timeout=300)
    def test_installer_check_accepts_first_1591_build_and_itself(self):
        manifest = json.loads((self.pkg / "manifest.json").read_text())
        for variant, src in (("first-build", Path(PACKAGE)), ("revision-18", self.pkg)):
            run = self._check(src, proxy=True)
            self.assertEqual(run.returncode, 0, variant + "\n" + run.stdout + run.stderr)
            self.assertIn("CHECK OK", run.stdout, variant)
        self.assertIn(fix.EXPECTED_INPUT_OUTPUT_SHA, manifest["files"]["test_beeline.py"]["previous_output_sha256"])
    def test_installer_refuses_without_configured_proxy(self):
        run = self._check(Path(PACKAGE), proxy=False)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('telegram_config.json has no "proxy"', run.stdout + run.stderr)
    def test_package_source_has_no_embedded_login(self):
        import re
        for name in ("test_beeline.py", "server_controller.py", "operator_runtime_io.py"):
            text = (self.pkg / name).read_text("utf-8")
            self.assertFalse(re.search(r"://[^/@\s'\"]+:[^/@\s'\"]+@", text), name)
        self.assertIn('TELEGRAM_DEFAULT_PROXY = ""', self.source)
    def _assist_harness(self, source):
        import sqlite3
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.execute("CREATE TABLE inbox(update_id INTEGER PRIMARY KEY, body TEXT, done_at REAL)")
        class Conn:
            def execute(self, *a): return db.execute(*a)
            def close(self): pass
        clock = [1000.0]; queued = []
        page = types.SimpleNamespace(url="https://example.test/personal-data-form")
        worker = {"id": 3, "page": page}
        def enqueue(text, lane="fast", priority=100):
            queued.append(text); db.execute("INSERT INTO inbox(body,done_at) VALUES(?,NULL)", (text,)); return -1
        names = ["queue_success_assist"] + (["_auto_assist_pending", "_auto_assist_allowed"] if fix.ASSIST_MARKER in source else [])
        ns = {"monotonic": lambda: clock[0], "_ai_db_connect": lambda: Conn(), "_ai_db_enqueue_internal": enqueue,
              "print": lambda *a, **k: None, "AUTO_ASSIST_MIN_GAP_SECONDS": 45, "AUTO_ASSIST_REPORTS_PER_STATE": 2,
              "AUTO_ASSIST_REPEAT_SECONDS": 1800}
        exec_functions(source, names, ns)
        answered = lambda: db.execute("UPDATE inbox SET done_at=1 WHERE done_at IS NULL")
        return ns["queue_success_assist"], worker, queued, clock, answered, page

    def test_unrepaired_build_requests_a_report_every_45_seconds(self):
        queue, worker, queued, clock, answered, page = self._assist_harness(Path(PACKAGE, "test_beeline.py").read_text("utf-8"))
        for t in range(0, 480, 10):
            clock[0] = 1000.0 + t; queue(worker, "интерфейс договора требует наблюдения"); answered()
        self.assertGreaterEqual(len(queued), 8)

    def test_assist_budget_two_per_page_state_then_every_30_minutes(self):
        queue, worker, queued, clock, answered, page = self._assist_harness(self.source)
        for t in range(0, 480, 10):
            clock[0] = 1000.0 + t; queue(worker, "интерфейс договора требует наблюдения"); answered()
        self.assertEqual(len(queued), 2)
        # The second request was queued at t=50 (first tick after the 45-second gap).
        clock[0] = 1000.0 + 50 + 1800 - 1; queue(worker, "x"); answered(); self.assertEqual(len(queued), 2)
        clock[0] = 1000.0 + 50 + 1800; queue(worker, "x"); answered(); self.assertEqual(len(queued), 3)
        page.url = "https://example.test/registration/complete"
        clock[0] += 1; queue(worker, "новая страница"); self.assertEqual(len(queued), 4)

    def test_assist_not_requeued_while_previous_unanswered(self):
        queue, worker, queued, clock, answered, page = self._assist_harness(self.source)
        self.assertTrue(queue(worker, "a", force=True))
        clock[0] += 100
        self.assertFalse(queue(worker, "b", force=True), "previous request still unanswered")
        answered()
        self.assertTrue(queue(worker, "b", force=True))
        answered(); clock[0] += 100
        self.assertFalse(queue(worker, "c", force=True), "force cannot exceed the per-state budget")

    def _error_harness(self, analysis_pending=True, retried_before=False, page_closed=False):
        events = []; notices = []
        class Page:
            url = "https://example.test/registration/error"
            def __init__(self): self.closed = page_closed
            def is_closed(self): return self.closed
        page = Page(); clock = [5000.0]
        worker = {"id": 2, "page": page, "phase": "ERROR_ASSIST", "row": ("7", "ROW-A", "x"), "stopped": False}
        if retried_before:
            worker["error_retry_counts"] = {"ROW-A": 1}
        pending = [analysis_pending]
        def restart(w):
            events.append("restart"); w["page"] = Page(); w["phase"] = "RESTART_ROW_READY"; return True
        def queue_error(w, reason, force=False):
            events.append("queue"); w.setdefault("auto_assist_state", {})["ERROR"] = {"count": 1, "url": page.url}; return True
        io = types.SimpleNamespace(enqueue_notice=lambda ns, chat, text, markup=None: notices.append(text))
        ns = {"monotonic": lambda: clock[0], "time": __import__("time"), "Path": Path, "print": lambda *a, **k: None,
              "_post_auth_contract_page": lambda p: False, "_post_auth_error_page": lambda p: True,
              "queue_error_assist": queue_error, "_auto_assist_pending": lambda kind, tab: pending[0],
              "restart_same_row_in_new_page": restart, "enter_success_guard": lambda w, n: events.append("success_guard"),
              "set_tab_status": lambda *a: None, "external_heartbeat": lambda *a: None,
              "capture_blackbox": lambda *a, **k: events.append("blackbox"),
              "_row_number_value": lambda row: str(row[1]),
              "load_telegram_config": lambda: {"chat_id": "1"}, "_io1591": io,
              "ERROR_ASSIST_MAX_SECONDS": 300, "ERROR_SKIP_DWELL_SECONDS": 15, "ERROR_ROW_MAX_ATTEMPTS": 2}
        exec_functions(self.source, ["tick_error_assist", "_error_recover", "_error_row_key", "_error_analysis_delivered"], ns)
        return ns["tick_error_assist"], worker, events, notices, clock, pending

    def test_error_page_is_held_until_the_analysis_report_then_retried_once(self):
        with tempfile.TemporaryDirectory() as d:
            tick, worker, events, notices, clock, pending = self._error_harness()
            for _ in range(5):
                clock[0] += 10; tick(d, worker)
            self.assertNotIn("restart", events, "no recovery while the analysis is unanswered")
            self.assertEqual(worker["phase"], "ERROR_ASSIST")
            pending[0] = False  # the analysis report has been delivered
            clock[0] += 1; tick(d, worker)
            self.assertIn("restart", events)
            self.assertEqual(worker["phase"], "RESTART_ROW_READY", "same row is retried on a fresh page")
            self.assertFalse(worker["error_guard"]); self.assertEqual(worker["error_retry_counts"], {"ROW-A": 1})
            self.assertEqual(notices, [])

    def test_second_error_on_same_row_skips_without_new_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            tick, worker, events, notices, clock, pending = self._error_harness(retried_before=True)
            tick(d, worker); clock[0] += 14; tick(d, worker)
            self.assertNotIn("queue", events); self.assertNotIn("restart", events)
            clock[0] += 2; tick(d, worker)
            self.assertIn("restart", events); self.assertEqual(worker["phase"], "IDLE"); self.assertIsNone(worker["row"])
            self.assertEqual(len(notices), 1); self.assertIn("ROW-A", notices[0])
            self.assertIn("ROW-A", (Path(d) / "error_skipped_rows.txt").read_text("utf-8"))

    def test_error_recovery_happens_even_if_analysis_never_arrives(self):
        with tempfile.TemporaryDirectory() as d:
            tick, worker, events, notices, clock, pending = self._error_harness()
            tick(d, worker); clock[0] += 299; tick(d, worker)
            self.assertNotIn("restart", events)
            clock[0] += 2; tick(d, worker)
            self.assertIn("restart", events); self.assertEqual(worker["phase"], "RESTART_ROW_READY")

    def test_externally_closed_error_page_does_not_stop_the_worker(self):
        with tempfile.TemporaryDirectory() as d:
            tick, worker, events, notices, clock, pending = self._error_harness(page_closed=True)
            tick(d, worker)
            self.assertFalse(worker["stopped"]); self.assertNotEqual(worker["phase"], "MANUAL_STOP")
            self.assertIn("restart", events)

    def test_unrepaired_build_stops_worker_on_closed_error_page(self):
        original = Path(PACKAGE, "test_beeline.py").read_text("utf-8")
        class Page:
            url = "x"
            def is_closed(self): return True
        worker = {"id": 2, "page": Page(), "phase": "ERROR_ASSIST", "stopped": False}
        ns = {"set_tab_status": lambda *a: None}
        exec_functions(original, ["tick_error_assist"], ns)
        ns["tick_error_assist"]("/tmp", worker)
        self.assertTrue(worker["stopped"]); self.assertEqual(worker["phase"], "MANUAL_STOP")

    def test_error_rule_is_in_every_prompt_layer(self):
        self.assertIn("ERROR_RECOVERY_1591R5", self.source.split("OPERATOR_MISSION_1586 = ", 1)[1].split('"""')[1])
        agent = self.source.split("def _agent_system_prompt(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("АВТОМАТИЧЕСКИ, без отдельного подтверждения", agent)
        self.assertNotIn("Destructive recovery без анализа запрещён", agent)
        queue = self.source.split("def queue_error_assist(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("пропустит строку без повтора", queue)
        self.assertNotIn("повторит строку один раз", queue)
        self.assertNotIn("НЕ делай автоматический retry", queue)
        self.assertIn("без запроса к DeepSeek", self.source.split("OPERATOR_MISSION_1586 = ", 1)[1].split('"""')[1])
        self.assertIn("Не запрашивай и не проводи анализ /registration/error", agent)

    def test_upgrade_from_revision_2_package(self):
        with tempfile.TemporaryDirectory() as d:
            r2 = Path(d) / "r2"
            shutil.copytree(self.pkg, r2, ignore=shutil.ignore_patterns("__pycache__"))
            run = subprocess.run([sys.executable, fix.__file__, str(r2)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("Already revision 18", run.stdout)

    def test_matcher_cpu_age_tracks_a_computing_child_process(self):
        import time as _t
        ns = {"os": os, "MATCHER_CPU_MIN_RATIO": 0.05, "_MATCHER_CPU_STATE": {}}
        exec_functions(self.source, ["_process_tree_cpu_seconds", "_matcher_cpu_age"], ns)
        child = subprocess.Popen([sys.executable, "-c",
            "import time\nt=time.monotonic()\nwhile time.monotonic()<t+1.5: sum(i*i for i in range(20000))\ntime.sleep(3)"])
        try:
            proc = types.SimpleNamespace(pid=child.pid)
            ns["_matcher_cpu_age"](proc, _t.monotonic()); _t.sleep(0.5)
            busy_age = ns["_matcher_cpu_age"](proc, _t.monotonic())
            self.assertLess(busy_age, 0.2, "a computing matcher must look alive")
            _t.sleep(1.6)
            ns["_matcher_cpu_age"](proc, _t.monotonic()); _t.sleep(1.0)
            idle_age = ns["_matcher_cpu_age"](proc, _t.monotonic())
            self.assertGreater(idle_age, 0.8, "a blocked matcher must go silent so the 75 s rule applies")
        finally:
            child.terminate(); child.wait()
        self.assertIn("if matcher_age >= PROTECTED_MATCHER_STALL_SECONDS:", self.source, "the 75 s rule stays")
        self.assertIn("matcher_age = min(matcher_age, _matcher_cpu_age(proc, now))", self.source)

    def test_installer_refuses_an_unknown_symbol_matching(self):
        run = self._check(Path(PACKAGE), proxy=True, matcher=b"MATCHER_VERSION = '13.0'\n")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("symbol_matching.py: installed source is different", run.stdout + run.stderr)

    def test_package_carries_the_fast_matcher_with_checksums(self):
        import hashlib
        manifest = json.loads((self.pkg / "manifest.json").read_text())
        meta = manifest["files"]["symbol_matching.py"]
        self.assertEqual(meta["input_sha256"], fix.SYMBOL_MATCHING_INPUT_SHA)
        self.assertEqual(meta["input_sha256"], hashlib.sha256(fix.SYMBOL_MATCHING_REFERENCE.read_bytes()).hexdigest())
        self.assertEqual(meta["output_sha256"], hashlib.sha256((self.pkg / "symbol_matching.py").read_bytes()).hexdigest())
        self.assertEqual(manifest["revision"], 18)
        install = (self.pkg / "install.py").read_text("utf-8")
        self.assertIn("'server_controller.py', 'symbol_matching.py')", install)
        self.assertIn('assert s.MATCHER_VERSION == "14.1"', install)
        self.assertIn("symbol_matching.py", (self.pkg / "SHA256SUMS.txt").read_text("utf-8"))
        self.assertEqual(fix.MATCHER_SPEED_MARKER in (self.pkg / "symbol_matching.py").read_text("utf-8"), True)


    def _collect(self, hang_seconds, timeout, raise_error=False):
        import time as _t
        exits = []
        def fake_unbounded(cdp_urls, with_screenshots=True):
            _t.sleep(hang_seconds)
            if raise_error:
                raise RuntimeError("cdp failure")
            return [{"tab_id": 1, "url": "u"}]
        def _exit(code):
            exits.append(code)
            raise SystemExit(code)
        ns = {"os": types.SimpleNamespace(_exit=_exit), "OBSERVER_COLLECT_TIMEOUT_SECONDS": 45,
              "_observer_collect_pages_unbounded": fake_unbounded, "print": lambda *a, **k: None}
        exec_functions(self.source, ["_observer_collect_pages"], ns)
        try:
            return ns["_observer_collect_pages"](["http://cdp"], with_screenshots=False, timeout=timeout), exits
        except SystemExit:
            return "exited", exits

    def test_observer_collect_is_bounded_and_restarts_the_lane_on_hang(self):
        result, exits = self._collect(hang_seconds=0.0, timeout=2)
        self.assertEqual(result, [{"tab_id": 1, "url": "u"}]); self.assertEqual(exits, [])
        result, exits = self._collect(hang_seconds=3.0, timeout=0.5)
        self.assertEqual(result, "exited"); self.assertEqual(exits, [3], "a hung collector must end the lane process")
        with self.assertRaises(RuntimeError):
            self._collect(hang_seconds=0.0, timeout=2, raise_error=True)
        self.assertIn("AI_LANE_BUSY_CEILING_SECONDS)", self.source, "the supervisor must restart lanes stuck in busy_*")
        self.assertIn('(not state.startswith("busy_") and (now - last) > idle_limit)', self.source, "idle rule stays")
        self.assertEqual(self.source.count("_observer_collect_pages_unbounded("), 2, "definition plus the one call in the wrapper")


    def _profile_ns(self):
        names = ["_norm_label", "_text_label_key_1591r12", "_text_value_ok_1591r12", "capture_success_profile_text_1591r12"]
        tree = ast.parse(self.source)
        nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names) or (
            isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id.endswith("_1591R12") for x in n.targets))]
        ns = {"re": __import__("re")}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pkg", "exec"), ns)
        return ns

    def test_profile_text_capture_fills_missing_fields_without_overwriting(self):
        ns = self._profile_ns()
        key = ns["_text_label_key_1591r12"]
        self.assertEqual(key("ФИО:"), "full_name"); self.assertEqual(key("Пол"), "gender")
        self.assertEqual(key("Населённый пункт"), "locality", "ё in the label must still match")
        self.assertIsNone(key("Номер договора")); self.assertIsNone(key("Домашний телефон")); self.assertIsNone(key("Полный адрес"))
        ok = ns["_text_value_ok_1591r12"]
        self.assertTrue(ok("full_name", "Иванов Иван Иванович")); self.assertFalse(ok("full_name", "договор №5"))
        self.assertTrue(ok("passport_number", "123456")); self.assertFalse(ok("passport_number", "987654321"))
        self.assertTrue(ok("house", "12а")); self.assertFalse(ok("house", "Культуры"))
        class Page:
            url = "https://saratov.beeline.ru/registration/contract"
            frames = []
            def evaluate(self, js):
                return {"pairs": [{"label": "ФИО", "value": "Иванов Иван Иванович"}, {"label": "Пол", "value": "Мужской"},
                                  {"label": "Номер договора", "value": "987654321"}, {"label": "Дом", "value": "Культуры"}],
                        "text": "Дата рождения\n01.02.1990\nСерия: 63 21\nГород: Саратов\n"}
        class Diag:
            def __init__(self): self.calls = []
            def write(self, *a, **k): self.calls.append((a, k))
        worker = {"success_profile": {"passport_number": "111111", "full_name": "Уже Есть Значение"}, "diagnostic": Diag()}
        profile = ns["capture_success_profile_text_1591r12"](Page(), worker)
        self.assertEqual(profile["full_name"], "Уже Есть Значение", "captured values are never overwritten")
        self.assertEqual(profile["gender"], "Мужской"); self.assertEqual(profile["birth_date"], "01.02.1990")
        self.assertEqual(profile["passport_series"], "63 21"); self.assertEqual(profile["locality"], "Саратов")
        self.assertEqual(profile["passport_number"], "111111"); self.assertNotIn("house", profile)
        self.assertEqual(worker["profile"], profile)
        ns["capture_success_profile_text_1591r12"](Page(), worker)
        self.assertEqual(len(worker["diagnostic"].calls), 1, "the page text is dumped once per worker")
        self.assertEqual(worker["diagnostic"].calls[0][0][0], "success_page_text_v1591r12")
        wrapper = self.source.split("_capture_contract_details_before_v1583 = capture_contract_details", 1)[1].split("\ndef ", 2)[1]
        self.assertIn("capture_success_profile_text_1591r12(page, worker)", wrapper, "the text capture runs from the shared wrapper")

    def test_profile_text_capture_reads_a_real_contract_page(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        ns = self._profile_ns()
        html = ("<h1>Договор об оказании услуг связи</h1>"
                "<div><span class='label'>Номер договора:</span><span>987654321</span></div>"
                "<dl><dt>ФИО</dt><dd>Иванов Иван Иванович</dd><dt>Пол</dt><dd>Мужской</dd>"
                "<dt>Дата рождения</dt><dd>01.02.1990</dd></dl>"
                "<p>Домашний телефон: 12</p><p>Город: Саратов</p><div><span>Дом: 12а</span></div>"
                "<label for='pn'>Номер паспорта</label><input id='pn' value='123456'>"
                "<div style='display:none'>ФИО: Скрытый Текст Невидимый</div>")
        class Diag:
            def write(self, *a, **k): pass
        worker = {"success_profile": {"passport_number": "123456"}, "diagnostic": Diag()}
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
                page = browser.new_page(); page.set_content(html)
                profile = ns["capture_success_profile_text_1591r12"](page, worker)
                browser.close()
        except Exception as exc:
            self.skipTest(f"chromium not available: {type(exc).__name__}")
        self.assertEqual(profile["full_name"], "Иванов Иван Иванович"); self.assertEqual(profile["gender"], "Мужской")
        self.assertEqual(profile["birth_date"], "01.02.1990"); self.assertEqual(profile["locality"], "Саратов")
        self.assertEqual(profile["house"], "12а"); self.assertEqual(profile["passport_number"], "123456")
        self.assertNotIn("987654321", profile.values()); self.assertNotIn("Скрытый Текст Невидимый", profile.values())


    def _restart_ns(self, base):
        ns = {"re": __import__("re"), "json": json, "time": __import__("time"), "Path": Path,
              "print": lambda *a, **k: None, "load_telegram_config": lambda: {"chat_id": "42"},
              "_io1591": types.SimpleNamespace(enqueue_notice=lambda ns_, chat, text, markup=None: None)}
        exec_functions(self.source, ["parse_restart_setting", "restart_policy_minutes", "write_restart_policy",
                                     "restart_drain_requested", "request_restart_drain", "clear_restart_drain"], ns)
        for name in ("RESTART_POLICY_FILE_NAME", "RESTART_DRAIN_FILE_NAME", "RESTART_EXIT_CODE"):
            ns[name] = getattr(types.SimpleNamespace(RESTART_POLICY_FILE_NAME="restart_policy.json",
                                                     RESTART_DRAIN_FILE_NAME="restart_drain.json", RESTART_EXIT_CODE=75), name)
        import re as _re
        ns["_RESTART_SETTING_RE"] = _re.compile(r"^(\d+)\s*(m|min|мин|h|ч|hour|час)?$")
        return ns

    def test_scheduled_restart_settings_and_drain_files(self):
        with tempfile.TemporaryDirectory() as d:
            ns = self._restart_ns(d)
            parse = ns["parse_restart_setting"]
            self.assertEqual(parse("off"), 0); self.assertEqual(parse("0"), 0)
            self.assertEqual(parse("20m"), 20); self.assertEqual(parse("20"), 20); self.assertEqual(parse("1h"), 60)
            self.assertEqual(parse("45 мин"), 45); self.assertIsNone(parse("abc")); self.assertIsNone(parse("0m")); self.assertIsNone(parse("48h"))
            self.assertEqual(ns["restart_policy_minutes"](d), 0, "no file means off")
            ns["write_restart_policy"](d, 20)
            self.assertEqual(ns["restart_policy_minutes"](d), 20)
            self.assertFalse(ns["restart_drain_requested"](d))
            ns["request_restart_drain"](d, "test"); ns["request_restart_drain"](d, "again")
            self.assertTrue(ns["restart_drain_requested"](d))
            self.assertEqual(json.loads((Path(d) / "restart_drain.json").read_text())["reason"], "test", "first request wins")
            ns["clear_restart_drain"](d); ns["clear_restart_drain"](d)
            self.assertFalse(ns["restart_drain_requested"](d))
        self.assertEqual(self.source.count("if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13"), 2, "worker gate and the exit check")
        self.assertIn('worker["phase"] = "RESTART_WAIT"', self.source)
        self.assertIn('"DONE", "SUCCESS_STOP", "MANUAL_STOP", "RESTART_WAIT",', self.source, "a RESTART_WAIT worker is not respawned")
        self.assertIn('if info.get("phase") == "SUCCESS_STOP" and not draining:', self.source, "no replacement slot while draining")
        self.assertIn("raise SystemExit(RESTART_EXIT_CODE)", self.source)
        gate = self.source.index("if restart_drain_requested(base_dir):  # SCHEDULED_RESTART_1591R13")
        self.assertLess(gate, self.source.index("row = rows.get_nowait()"), "the gate runs before a new row is taken")

    def test_controller_restart_command_and_relaunch(self):
        control = (self.pkg / "server_controller.py").read_text("utf-8")
        self.assertIn("_restart_after_drain(proc)  # SCHEDULED_RESTART_1591R13", control)
        self.assertIn('if text.startswith("/restart"):', control)
        with tempfile.TemporaryDirectory() as d:
            helpers = self._restart_ns(d)
            app = types.SimpleNamespace(RESTART_EXIT_CODE=75, **{k: helpers[k] for k in (
                "parse_restart_setting", "restart_policy_minutes", "write_restart_policy",
                "restart_drain_requested", "request_restart_drain")})
            sent = []
            ns = {"app": app, "BASE_DIR": Path(d), "_send": sent.append}
            exec_functions(control, ["_restart_command", "_restart_after_drain"], ns)
            self.assertIn("выключен", ns["_restart_command"](""))
            self.assertIn("каждые 20 мин", ns["_restart_command"](" 20m"))
            self.assertEqual(helpers["restart_policy_minutes"](d), 20)
            self.assertIn("каждые 20 мин", ns["_restart_command"](""))
            self.assertIn("Не понял", ns["_restart_command"]("soon"))
            self.assertIn("выключен", ns["_restart_command"]("off")); self.assertEqual(helpers["restart_policy_minutes"](d), 0)
            self.assertIn("Запрошен", ns["_restart_command"]("now")); self.assertTrue(helpers["restart_drain_requested"](d))
            self.assertIn("ожидается перезапуск", ns["_restart_command"](""))
            class FakePopen:
                def __init__(self, code): self.code = code
                def poll(self): return self.code
            class FakeProc:
                def __init__(self, code):
                    self.proc = FakePopen(code); self.started = 0
                def start(self):
                    self.started += 1
                    return True, "▶️ Запущено. PID 1."
            running = FakeProc(None)
            self.assertFalse(ns["_restart_after_drain"](running)); self.assertEqual(running.started, 0)
            crashed = FakeProc(1)
            self.assertFalse(ns["_restart_after_drain"](crashed), "an ordinary exit is left to reap(), not relaunched")
            drained = FakeProc(75)
            self.assertTrue(ns["_restart_after_drain"](drained)); self.assertEqual(drained.started, 1)
            self.assertIn("Плановый перезапуск выполнен", sent[-1])


    def test_post_auth_error_page_follows_the_error_policy(self):
        self.assertNotIn('queue_success_assist(worker, "post-auth error page")', self.source)
        calls = []
        class Page:
            url = "https://saratov.beeline.ru/registration/error"
            def is_closed(self): return False
        ns = {"monotonic": lambda: 0.0, "capture_contract_details": lambda p, w: None,
              "_post_auth_error_page": lambda p: True, "capture_blackbox": lambda w, r, exc=None: calls.append(("blackbox", r)),
              "enter_error_guard": lambda w, note: (calls.append(("error_guard", note)), w.__setitem__("phase", "ERROR_ASSIST"),
                                                    w.__setitem__("success_guard", False), w.__setitem__("error_guard", True)),
              "set_tab_status": lambda *a: None, "external_heartbeat": lambda *a: None,
              "queue_success_assist": lambda *a, **k: calls.append(("success_assist", a[1])), "print": lambda *a, **k: None}
        exec_functions(self.source, ["tick_post_auth_review"], ns)
        worker = {"id": 3, "page": Page(), "success_guard": True}
        ns["tick_post_auth_review"](Path("/tmp"), worker)
        self.assertEqual(worker["phase"], "ERROR_ASSIST"); self.assertFalse(worker["success_guard"]); self.assertTrue(worker["error_guard"])
        self.assertEqual([c[0] for c in calls], ["blackbox", "error_guard"], "no SUCCESS_ASSIST for an error page")
        manifest = json.loads((self.pkg / "manifest.json").read_text())
        self.assertEqual(manifest["preserved_ast_sha256"]["tick_post_auth_review"], fix.handler_hash(
            next(n for n in ast.parse(self.source).body if isinstance(n, ast.FunctionDef) and n.name == "tick_post_auth_review")))


    def _error_guard_run(self, page_text, base, new_page_works=True):
        tree = ast.parse(self.source)
        nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in (
            "enter_error_guard", "_error_page_final_reason", "_error_skip_final", "_error_row_key")) or (
            isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "ERROR_FINAL_NEEDLES_1591R15" for x in n.targets))]
        calls, notices = [], []
        class Body:
            def inner_text(self, timeout=None): return page_text
        class Page:
            url = "https://saratov.beeline.ru/registration/error"
            def locator(self, sel): return Body()
        def new_page(worker):
            calls.append("new_page")
            if new_page_works:
                worker["page"] = Page(); worker["phase"] = "RESTART_ROW_READY"
        ns = {"Path": Path, "time": __import__("time"), "print": lambda *a, **k: None, "ERROR_ROW_MAX_ATTEMPTS": 2,
              "_row_number_value": lambda row: row[0], "capture_blackbox": lambda w, r, exc=None: calls.append(("blackbox", r)),
              "restart_same_row_in_new_page": new_page, "set_tab_status": lambda *a: None,
              "external_heartbeat": lambda w, label: calls.append(("hb", label)),
              "queue_error_assist": lambda w, note, force=False: calls.append(("error_assist", note)),
              "load_telegram_config": lambda: {"chat_id": "42"},
              "_io1591": types.SimpleNamespace(enqueue_notice=lambda ns_, chat, text, markup=None: notices.append(text))}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pkg", "exec"), ns)
        worker = {"id": 3, "page": Page(), "row": (11, "79059522766", "5015441725"), "base_dir": base, "success_guard": True}
        ns["enter_error_guard"](worker, "после mobile-id-auth открылась /registration/error")
        return worker, calls, notices

    def test_operator_refusal_is_skipped_without_analysis_or_retry(self):
        with tempfile.TemporaryDirectory() as d:
            worker, calls, notices = self._error_guard_run(
                "Данные не прошли проверку. Укажите другой свой номер или выберите способ регистрации", d)
            self.assertEqual(worker["phase"], "IDLE"); self.assertIsNone(worker["row"])
            self.assertFalse(worker["error_guard"]); self.assertFalse(worker["success_guard"])
            self.assertNotIn(("error_assist", "после mobile-id-auth открылась /registration/error"), calls, "no paid analysis")
            self.assertIn("new_page", calls); self.assertIn(("hb", "error_row_skipped_final"), calls)
            line = (Path(d) / "error_skipped_rows.txt").read_text("utf-8").strip()
            self.assertIn("\t11\t", line); self.assertIn("данные не прошли проверку у оператора", line)
            self.assertEqual(len(notices), 1); self.assertIn("строка 11 пропущена без повтора", notices[0])
            # revision 16: any other error page is skipped at once as well, still without DeepSeek
            worker, calls, notices = self._error_guard_run("Что-то пошло не так. Попробовать ещё раз", d)
            self.assertEqual(worker["phase"], "IDLE"); self.assertIsNone(worker["row"])
            self.assertFalse(any(c[0] == "error_assist" for c in calls), "no analysis request for an error page")
            self.assertEqual(len(notices), 1); self.assertIn("registration/error после подтверждения", notices[0])
            self.assertEqual((Path(d) / "error_skipped_rows.txt").read_text("utf-8").count("\n"), 2)
            # no fresh page yet: the worker parks in ERROR_ASSIST on the repeat-skip branch, no analysis
            worker, calls, notices = self._error_guard_run("Что-то пошло не так", d, new_page_works=False)
            self.assertEqual(worker["phase"], "ERROR_ASSIST"); self.assertTrue(worker["error_guard"])
            self.assertEqual(worker["error_retry_counts"], {11: 1}, "the error tick skips after the dwell instead of analysing")
            self.assertFalse(any(c[0] == "error_assist" for c in calls)); self.assertEqual(notices, [])


    def test_success_push_is_tagged_and_four_tabs_are_configured(self):
        self.assertIn("TABS_PER_BROWSER = 4", self.source)
        self.assertNotIn("TABS_PER_BROWSER = 3", self.source)
        ns = {"row_parts": lambda row: (row[0], row[1], row[2]), "_success_profile_lines": lambda profile: ["ФИО: X"]}
        exec_functions(self.source, ["_success_message"], ns)
        text = ns["_success_message"]({"id": 2, "row": (5, "79990000000", "1234"), "total_rows": 10},
                                      {"profile": {}, "sim_number": "89", "sim_url": "u"})
        lines = text.split("\n")
        self.assertEqual(lines[0], "#успешно"); self.assertTrue(lines[1].startswith("✅ УСПЕХ — Вкладка 2"))
        self.assertIn("Строка: 5/10", text); self.assertIn("eSIM: 89", text)

    def test_browser_hang_restarts_the_whole_chromium(self):
        src = self.source
        self.assertEqual(src.count("BROWSER_HANG_1591R18"), 7)
        self.assertIn("BROWSER_HANG_RESTART_SECONDS = 120", src)
        # Watchdog: a browser that keeps refusing CDP is restarted instead of retried forever.
        fail_branch = src[src.index("if not closed_old_tab:"):src.index("replacement пока не создаю")]
        self.assertIn("cdp_unreachable_seconds(browser_instances[browser_idx][\"cdp_url\"])", fail_branch)
        self.assertIn("restart_browser_instance(", fail_branch)
        self.assertIn("def restart_browser_instance(browser_idx, reason):", src)
        self.assertIn("raise SystemExit(RESTART_EXIT_CODE)", src[src.index("def restart_browser_instance"):src.index("def recover_dead_workers")])
        # The literal "\\n" in the watchdog status became a real line break.
        self.assertIn('f"♻️ Вкладка {tab_id}\\n{reason}\\n"', src)
        self.assertNotIn('f"♻️ Вкладка {tab_id}\\\\n{reason}\\\\n"', src)
        self.assertNotIn("ЭКСПЕРИМЕНТ: запускаю 1 Chromium и 3 рабочие вкладки", src)
        # _close_cdp_page_for_worker records connect timeouts per browser and clears them on success.
        cdp_fn = src[src.index("def _close_cdp_page_for_worker"):src.index("def _once(") + 400]
        self.assertIn("_note_cdp_result(cdp_url, None)", src[src.index("def _close_cdp_page_for_worker"):src.index("import time as _time")])
        self.assertIn("_note_cdp_result(cdp_url, exc)", src[src.index("def _close_cdp_page_for_worker"):src.index("import time as _time")])
        import subprocess as _sp, tempfile as _tf, shutil as _sh
        ns = {"_CDP_UNREACHABLE_SINCE": {}, "monotonic": lambda: 1000.0, "subprocess": _sp,
              "tempfile": _tf, "shutil": _sh, "_free_local_port": lambda: 45999, "_wait_cdp": lambda port: False}
        exec_functions(src, ["_note_cdp_result", "cdp_unreachable_seconds", "_chromium_launch_args",
                             "_terminate_chromium", "_relaunch_chromium"], ns)
        class Timeout(Exception):
            pass
        url = "http://127.0.0.1:52495"
        ns["_note_cdp_result"](url, RuntimeError("Target closed"), now=10.0)
        self.assertEqual(ns["cdp_unreachable_seconds"](url, now=50.0), 0.0)
        ns["_note_cdp_result"](url, Timeout("BrowserType.connect_over_cdp: Timeout 20000ms exceeded."), now=10.0)
        ns["_note_cdp_result"](url, Timeout("BrowserType.connect_over_cdp: Timeout 20000ms exceeded."), now=40.0)
        self.assertEqual(ns["cdp_unreachable_seconds"](url, now=140.0), 130.0)
        ns["_note_cdp_result"](url, None)
        self.assertEqual(ns["cdp_unreachable_seconds"](url, now=200.0), 0.0)
        args = ns["_chromium_launch_args"]("/bin/chromium", 52495, "/tmp/prof")
        self.assertIn("--no-sandbox", args); self.assertIn("--remote-debugging-port=52495", args)
        self.assertEqual(args[-1], "about:blank")
        launched, made = [], []
        class FakeProc:
            def poll(self): return None
            def terminate(self): launched.append("terminate")
            def wait(self, timeout=None): return 0
            def kill(self): pass
        def popen(argv):
            made.append(argv); return FakeProc()
        ns["_CDP_UNREACHABLE_SINCE"][url] = 5.0
        inst = {"id": 1, "port": 52495, "profile": "", "proc": None, "cdp_url": url}
        # First attempt on the old port succeeds: cdp_url unchanged, hang record cleared.
        self.assertTrue(ns["_relaunch_chromium"](inst, "/bin/chromium", popen=popen, wait_cdp=lambda p: True))
        self.assertEqual(inst["cdp_url"], url); self.assertEqual(inst["port"], 52495)
        self.assertIn("--remote-debugging-port=52495", made[-1]); self.assertNotIn(url, ns["_CDP_UNREACHABLE_SINCE"])
        _sh.rmtree(inst["profile"], ignore_errors=True)
        # Old port dead: the fallback port is used and the old Chromium attempt is terminated.
        inst = {"id": 1, "port": 52495, "profile": "", "proc": None, "cdp_url": url}
        seen = []
        self.assertTrue(ns["_relaunch_chromium"](inst, "/bin/chromium", popen=popen,
                                                 wait_cdp=lambda p: seen.append(p) or p == 45999, free_port=lambda: 45999))
        self.assertEqual(seen, [52495, 45999]); self.assertEqual(inst["cdp_url"], "http://127.0.0.1:45999")
        self.assertIn("terminate", launched)
        _sh.rmtree(inst["profile"], ignore_errors=True)
        inst = {"id": 1, "port": 52495, "profile": "", "proc": None, "cdp_url": url}
        self.assertFalse(ns["_relaunch_chromium"](inst, "/bin/chromium", popen=popen, wait_cdp=lambda p: False, free_port=lambda: 45999))
        _sh.rmtree(inst["profile"], ignore_errors=True)


def _load_module(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_captcha(seed, letters="AKMSTZ", size=(210, 360), distractors=6):
    """Captcha-like picture: saturated, shaded, anti-aliased strokes on a tinted background."""
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    h, w = size
    yy, xx = np.mgrid[0:h, 0:w]
    hsv = np.zeros((h, w, 3), np.uint8)
    hsv[..., 0] = (20 + 40 * xx / w).astype(np.uint8)
    hsv[..., 1] = (60 + 70 * rng.random((h, w))).astype(np.uint8)
    hsv[..., 2] = (170 + 70 * rng.random((h, w))).astype(np.uint8)
    picture = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    hues = [0, 60, 120]

    def paint(alpha, hue, k):
        shade = (140 + 110 * (0.5 + 0.5 * np.sin(xx / 17.0 + k) * np.cos(yy / 13.0))).astype(np.uint8)
        sat = (150 + 100 * (0.5 + 0.5 * np.cos(yy / 11.0 + k))).astype(np.uint8)
        layer = np.zeros((h, w, 3), np.uint8)
        layer[..., 0], layer[..., 1], layer[..., 2] = hue, sat, shade
        layer = cv2.cvtColor(layer, cv2.COLOR_HSV2BGR)
        a = (alpha.astype(np.float32) / 255)[..., None]
        return (picture * (1 - a) + layer * a).astype(np.uint8)

    refs = []
    for k, ch in enumerate(letters):
        x, y = 22 + (k % 3) * 112 + int(rng.integers(0, 14)), 70 + (k // 3) * 95 + int(rng.integers(0, 12))
        canvas = np.zeros((h, w), np.uint8)
        cv2.putText(canvas, ch, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.35 + 0.35 * rng.random(), 255,
                    int(rng.integers(2, 5)), cv2.LINE_AA)
        matrix = cv2.getRotationMatrix2D((x + 15, y - 15), float(rng.uniform(-45, 45)), 1)
        picture = paint(cv2.warpAffine(canvas, matrix, (w, h), flags=cv2.INTER_LINEAR), hues[k % 3], k)
        ref = np.zeros((48, 48), np.uint8)
        cv2.putText(ref, ch, (6, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.3, 255, 2)
        refs.append(ref)
    for d in range(distractors):
        alpha = np.zeros((h, w), np.uint8)
        cv2.ellipse(alpha, (int(rng.integers(10, w - 10)), int(rng.integers(10, h - 10))),
                    (int(rng.integers(6, 18)), int(rng.integers(4, 12))), float(rng.uniform(0, 180)), 0,
                    int(rng.integers(90, 300)), 255, int(rng.integers(1, 4)), cv2.LINE_AA)
        picture = paint(alpha, hues[d % 3], d + 10)
    return cv2.GaussianBlur(picture, (3, 3), 0), refs


def _cv2_available():
    try:
        import cv2, numpy  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_cv2_available(), "cv2/numpy not installed")
class MatcherEquivalenceTests(unittest.TestCase):
    """symbol_matching.py 14.1 (matcher_r10) must reproduce the 14.0 reference results."""
    @classmethod
    def setUpClass(cls):
        cls.old = _load_module("symbol_matching_14_0", fix.SYMBOL_MATCHING_REFERENCE)
        cls.new = _load_module("symbol_matching_14_1", fix.SYMBOL_MATCHING_SOURCE)

    def test_versions_and_marker(self):
        self.assertEqual(self.old.MATCHER_VERSION, "14.0")
        self.assertEqual(self.new.MATCHER_VERSION, "14.1")
        self.assertIn(fix.MATCHER_SPEED_MARKER, fix.SYMBOL_MATCHING_SOURCE.read_text("utf-8"))
        for name in ("MAX_SHAPE_COST", "MIN_MATCH_MARGIN"):
            self.assertEqual(getattr(self.old, name), getattr(self.new, name), name)

    def test_thin_and_compact_are_bit_identical(self):
        import cv2
        import numpy as np
        rng = np.random.default_rng(7)
        masks = []
        for _ in range(80):
            h, w = int(rng.integers(5, 70)), int(rng.integers(5, 70))
            m = np.zeros((h, w), np.uint8)
            for _ in range(int(rng.integers(1, 5))):
                cv2.line(m, tuple(int(v) for v in rng.integers(0, (w, h))),
                         tuple(int(v) for v in rng.integers(0, (w, h))), 255, int(rng.integers(1, 6)))
            if rng.random() < .3:
                cv2.circle(m, (w // 2, h // 2), min(h, w) // 3, 255, int(rng.integers(1, 5)))
            masks.append(m)
        masks += [np.zeros((10, 10), np.uint8), np.full((12, 9), 255, np.uint8),
                  (rng.random((40, 40)) > .5).astype(np.uint8) * 255]
        masks += [self.old.compact(m) for m in masks[:30]]
        for m in masks:
            self.assertTrue(np.array_equal(self.old.thin(m), self.new.thin(m)))
            self.assertTrue(np.array_equal(self.old.compact(m), self.new.compact(m)))
            self.assertTrue(np.array_equal(self.old.descriptor(m), self.new.descriptor(m)))
            self.assertTrue(np.array_equal(self.old.scaled_descriptor(m), self.new.scaled_descriptor(m)))
            self.assertTrue(np.array_equal(self.old.affine_descriptor(m), self.new.affine_descriptor(m)))
            self.assertTrue(np.array_equal(self.old.affine_descriptor(m),
                                           self.new.affine_descriptor(m, skeleton=self.new.thin(m))))

    def test_shape_costs_and_matches_agree_and_are_faster(self):
        import time
        import numpy as np
        totals = {"old": 0.0, "new": 0.0}
        for seed in (1, 2):
            picture, refs = _synthetic_captcha(seed)
            old_groups, new_groups = list(self.old.families(picture)), list(self.new.families(picture))
            self.assertEqual([c for c, _ in old_groups], [c for c, _ in new_groups])
            for (_, a), (_, b) in zip(old_groups, new_groups):
                self.assertEqual([(x.bounds, x.mask.tobytes()) for x in a], [(x.bounds, x.mask.tobytes()) for x in b])
            pool = [c for _, cs in old_groups for c in cs][:120]
            self.assertGreater(len(pool), 60, "the synthetic picture must yield a real candidate pool")
            native = [self.old.descriptor(c.mask) for c in pool]
            ref_desc = [self.old.descriptor(r) for r in refs]
            t = time.perf_counter(); c_old = self.old.shape_costs(ref_desc, native); totals["old"] += time.perf_counter() - t
            t = time.perf_counter(); c_new = self.new.shape_costs(ref_desc, native); totals["new"] += time.perf_counter() - t
            finite = np.isfinite(c_old)
            self.assertTrue(np.array_equal(finite, np.isfinite(c_new)))
            self.assertLess(float(np.abs(c_old[finite] - c_new[finite]).max()), 1e-4)
            m_old, m_new = self.old.match_symbols(picture, refs), self.new.match_symbols(picture, refs)
            self.assertEqual(len(m_old), len(refs))
            for a, b in zip(m_old, m_new):
                self.assertEqual(a.reason, b.reason)
                self.assertEqual(a.candidate.bounds if a.candidate else None, b.candidate.bounds if b.candidate else None)
                self.assertAlmostEqual(a.distance, b.distance, places=4)
                if np.isfinite(a.margin) or np.isfinite(b.margin):
                    self.assertAlmostEqual(a.margin, b.margin, places=4)
        self.assertLess(totals["new"], totals["old"], "the 14.1 shape_costs must not be slower than 14.0")


class FreshInstallTests(unittest.TestCase):
    """fresh_install.sh builds a server from the repository alone (offline mode: no apt, venv, systemd)."""
    SCRIPT = Path(__file__).resolve().parent / "fresh_install.sh"
    CODE = ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "symbol_matching.py",
            "local_matcher.py", "batch_support.py", "console_wait.py", "PROJECT_RULES.md")

    def _run(self, app, **env):
        full = dict(os.environ, APP_DIR=str(app), SKIP_APT="1", SKIP_VENV="1", NO_SERVICE="1", **env)
        return subprocess.run(["bash", str(self.SCRIPT)], env=full, capture_output=True, text=True, timeout=600)

    def test_fresh_install_from_repository(self):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d) / "app"
            run = self._run(app, DEEPSEEK_API_KEY="k", TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="1",
                            TELEGRAM_PROXY="socks5h://u:p@h:1")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("CHECK OK", run.stdout)
            for name in self.CODE:
                self.assertTrue((app / name).is_file(), name)
            package = max(Path(__file__).resolve().parent.glob("beeline_integrated_io_15_91_r*"),
                          key=lambda x: int(x.name.rsplit("r", 1)[1]))
            for name in ("test_beeline.py", "server_controller.py", "operator_runtime_io.py", "symbol_matching.py"):
                self.assertEqual((app / name).read_bytes(), (package / name).read_bytes(), name)
            self.assertEqual((app / "local_matcher.py").read_bytes(),
                             (Path(__file__).resolve().parent.parent / "local_matcher.py").read_bytes())
            self.assertIn("def wait_confirmation", (app / "batch_support.py").read_text("utf-8"))
            for name in ("telegram_config.json", "deepseek_config.json"):
                self.assertEqual((app / name).stat().st_mode & 0o777, 0o600, name)
            self.assertEqual(json.loads((app / "telegram_config.json").read_text())["proxy"], "socks5h://u:p@h:1")
            self.assertTrue((app / "clients.txt").exists())

    def test_fresh_install_refuses_without_secrets_when_not_interactive(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._run(Path(d) / "app", DEEPSEEK_API_KEY="k")
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("TELEGRAM_BOT_TOKEN", run.stdout + run.stderr)

    @unittest.skipUnless(shutil.which("rsync"), "rsync not installed")
    def test_migration_keeps_data_and_replaces_code(self):
        with tempfile.TemporaryDirectory() as d:
            old, app = Path(d) / "old", Path(d) / "app"
            for sub in ("venv", "__pycache__", "last_match", "results"):
                (old / sub).mkdir(parents=True)
            (old / "test_beeline.py").write_text("OLD CODE")
            (old / "symbol_matching.py").write_text("OLD MATCHER")
            (old / "PROJECT_RULES.md").write_text("custom rules")
            (old / "batch_support.py").write_text("# custom batch\ndef load_clients(p): return []\ndef wait_confirmation(*a, **k): return None\ndef save_result(*a, **k): return None\n")
            (old / "telegram_config.json").write_text(json.dumps({"token": "T", "chat_id": "C", "proxy": "socks5h://u:p@h:1"}))
            (old / "deepseek_config.json").write_text(json.dumps({"api_key": "K"}))
            (old / "clients.txt").write_text("79990000000\tIvanov\n")
            (old / "progress.sqlite3").write_text("progress")
            (old / "results" / "2026.jsonl").write_text("res")
            (old / "venv" / "x").write_text("junk"); (old / "last_match" / "x").write_text("junk")
            run = self._run(app, MIGRATE_FROM=str(old))
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("CHECK OK", run.stdout)
            # data and customised files travel, code is the package copy, junk stays behind
            self.assertEqual((app / "clients.txt").read_text(), "79990000000\tIvanov\n")
            self.assertEqual((app / "progress.sqlite3").read_text(), "progress")
            self.assertEqual((app / "results" / "2026.jsonl").read_text(), "res")
            self.assertEqual((app / "PROJECT_RULES.md").read_text(), "custom rules")
            self.assertTrue((app / "batch_support.py").read_text().startswith("# custom batch"))
            self.assertEqual(json.loads((app / "telegram_config.json").read_text())["token"], "T")
            self.assertIn(fix.MATCHER_SPEED_MARKER, (app / "symbol_matching.py").read_text("utf-8"))
            self.assertIn(fix.MATCHER_MARKER, (app / "test_beeline.py").read_text("utf-8"))
            self.assertFalse((app / "venv").exists()); self.assertFalse((app / "last_match").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
