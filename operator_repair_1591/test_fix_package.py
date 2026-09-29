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
        if any(m not in source for m in (fix.MARKER, fix.PROXY_MARKER, fix.ASSIST_MARKER, fix.ERROR_MARKER, fix.OVERLAY_MARKER, fix.TARIFF_MARKER)):
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
    def _check(self, src, proxy):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)
            for name in ("test_beeline.py", "server_controller.py"):
                shutil.copy2(src / name, app / name)
            if proxy:
                (app / "telegram_config.json").write_text(json.dumps({"proxy": "socks5h://u:p@h:1"}))
            return subprocess.run([sys.executable, str(self.pkg / "install.py"), "--app", str(app)],
                                  capture_output=True, text=True, timeout=300)
    def test_installer_check_accepts_first_1591_build_and_itself(self):
        manifest = json.loads((self.pkg / "manifest.json").read_text())
        for variant, src in (("first-build", Path(PACKAGE)), ("revision-7", self.pkg)):
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
        self.assertIn("повторит строку один раз", queue)
        self.assertNotIn("НЕ делай автоматический retry", queue)

    def test_upgrade_from_revision_2_package(self):
        with tempfile.TemporaryDirectory() as d:
            r2 = Path(d) / "r2"
            shutil.copytree(self.pkg, r2, ignore=shutil.ignore_patterns("__pycache__"))
            run = subprocess.run([sys.executable, fix.__file__, str(r2)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("Already revision 7", run.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
