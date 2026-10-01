"""Offline tests for fix_package_1591.py. Set PACKAGE_1591_DIR to an extracted package for the full run."""
import ast
import hashlib
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
        if (any(m not in source for m in (fix.MARKER, fix.PROXY_MARKER, fix.ASSIST_MARKER, fix.ERROR_MARKER, fix.OVERLAY_MARKER, fix.TARIFF_MARKER, fix.ROWSTART_MARKER, fix.MATCHER_MARKER, fix.OBSERVER_MARKER, fix.PROFILE_MARKER, fix.RESTART_MARKER, fix.POSTAUTH_MARKER, fix.PERSDATA_MARKER, fix.ERRORSKIP_MARKER, fix.SUCCESSTAG_MARKER, fix.BROWSER_MARKER, fix.PROFILE_LABELS_MARKER, fix.PROXY_DIRECT_MARKER, fix.RESTART_RELAUNCH_MARKER, fix.ROW_SKIP_MARKER, fix.FINAL_PAGE_MARKER, fix.SIGNED_MARKER, fix.SIGN_TRACE_MARKER, fix.PAYMENT_MARKER, fix.TG_RATE_MARKER, fix.TWO_BROWSERS_MARKER, fix.STALE_DRAIN_MARKER, fix.AI_VERDICT_MARKER, fix.SIGN_ROBUST_MARKER, fix.TARIFF_SCOPE_MARKER, fix.TARIFF_CHANGE_MARKER, fix.BROWSER_ENV_MARKER, fix.TRACE_COMPACT_MARKER, fix.SIM_URL_MARKER))
                or not speed.is_file() or fix.MATCHER_SPEED_MARKER not in speed.read_text("utf-8")):
            subprocess.run([sys.executable, fix.__file__, str(cls.pkg)], check=True, capture_output=True, text=True)
        cls.source = (cls.pkg / "test_beeline.py").read_text("utf-8")
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _logger(self, enqueue, telegram_api=None, status_map=None, rounds=1, tmp=None):
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
        def default_api(cfg, method, payload):
            sent.append((method, payload))
            return {"ok": True, "result": {"message_id": len(sent)}}, None
        api = telegram_api or default_api
        def counting_api(cfg, method, payload):
            r = api(cfg, method, payload)
            if api is not default_api: sent.append((method, payload))
            return r
        io = types.SimpleNamespace(
            enqueue_notice=lambda ns, chat, text, markup=None: queued.append((chat, text)) if enqueue else (_ for _ in ()).throw(RuntimeError("no outbox")),
            split_text=lambda text, limit=3500: [text[i:i + limit] for i in range(0, len(text), limit)],
            redact=str)
        class StopAfter(Stop):
            def __init__(self, n): super().__init__(); self.limit = n
            def is_set(self):
                self.n += 1
                return self.n > self.limit
        ns = {"load_telegram_config": lambda: {"chat_id": "42"}, "telegram_api": counting_api, "_io1591": io,
              "time": __import__("time"), "json": json, "Path": Path, "TAB_COUNT": 1, "print": lambda *a, **k: None,
              "TG_MIN_CALL_GAP_1591R27": 0.0, "TG_STATUS_MIN_EDIT_GAP_1591R27": 0.0,
              "TELEGRAM_CONFIG_FILE": Path(tmp or tempfile.mkdtemp()) / "telegram_config.json"}
        exec_functions(self.source, ["telegram_logger_process", "_tg_status_file_1591r27", "_tg_call_1591r27",
                                     "_tg_status_messages_load_1591r27", "_tg_status_messages_save_1591r27",
                                     "_tg_status_sync_1591r27"], ns)
        ns["telegram_logger_process"](status_map if status_map is not None else {}, Q(["S" * 9000]), StopAfter(rounds))
        return sent, queued


    def test_status_logger_respects_429_and_reuses_messages_across_restarts(self):
        class Failure(str):
            def __new__(cls, text, retry_after=None):
                obj = str.__new__(cls, text); obj.retry_after = retry_after; return obj
        with tempfile.TemporaryDirectory() as d:
            # Run 1: Telegram answers 429 on the first send — no further calls in that run.
            calls = []
            def banned(cfg, method, payload):
                calls.append(method)
                return None, Failure("Telegram API: 429 Too Many Requests: retry after 16000", retry_after=16000)
            sent, _ = self._logger(enqueue=True, telegram_api=banned, status_map={"1": {"text": "A", "time": 1}}, rounds=3, tmp=d)
            self.assertEqual(calls, ["getMe"], "after a 429 on getMe nothing else is attempted")
            # Run 2: messages are created once, edited only when the text changes, ids persisted.
            texts = {"1": {"text": "A", "time": 1}}
            sent, _ = self._logger(enqueue=True, telegram_api=None, status_map=texts, rounds=2, tmp=d)
            methods = [m for m, _ in sent]
            self.assertEqual(methods.count("sendMessage"), 1); self.assertEqual(methods.count("editMessageText"), 1)
            saved = json.loads((Path(d) / "telegram_status_messages.json").read_text("utf-8"))
            self.assertEqual(saved["chat"], "42"); self.assertIn("1", saved["mids"])
            # Run 3 (a restart): the saved message is reused — an edit, no new sendMessage.
            sent, _ = self._logger(enqueue=True, telegram_api=None, status_map={"1": {"text": "B", "time": 2}}, rounds=2, tmp=d)
            methods = [m for m, _ in sent]
            self.assertEqual(methods.count("sendMessage"), 0); self.assertGreaterEqual(methods.count("editMessageText"), 2)
            self.assertTrue(any(p.get("text") == "B" for m, p in sent if m == "editMessageText"))
            # Run 4: Telegram says the saved message is gone — it is recreated and re-saved.
            def gone(cfg, method, payload):
                if method == "editMessageText" and payload.get("message_id") == saved["mids"]["1"]:
                    return None, Failure("Telegram API: 400 Bad Request: message to edit not found")
                return {"ok": True, "result": {"message_id": 777}}, None
            sent, _ = self._logger(enqueue=True, telegram_api=gone, status_map={"1": {"text": "C", "time": 3}}, rounds=3, tmp=d)
            self.assertIn("sendMessage", [m for m, _ in sent])
            self.assertEqual(json.loads((Path(d) / "telegram_status_messages.json").read_text("utf-8"))["mids"]["1"], 777)


    def test_signing_is_coordinated_with_deepseek_and_retried_once(self):
        src = self.source
        for needle in ("VERDICT: SIGNED", "VERDICT: PAYMENT", "VERDICT: NOT_SIGNED"):
            self.assertIn(needle, src[src.index("def queue_success_assist"):src.index("def queue_success_assist") + 4000])
            self.assertIn(needle, src[src.index("SUCCESS SUPERVISOR:"):src.index("ERROR SUPERVISOR:")])
        review = src[src.index("def tick_post_auth_review"):src.index("def tick_success_assist")]
        self.assertLess(review.index("_ai_busy_1591r30(worker)"), review.index("enabled = button.is_enabled()"))
        self.assertLess(review.index("_sign_prepare_1591r30(page, worker)"), review.index("_sign_trace_begin_1591r25(page, worker)"))
        self.assertIn("_sign_retry_if_unsent_1591r30(page, worker)", review)
        observer = src[src.index("def ai_observer_process"):src.index("def ai_observer_process") + 9000]
        self.assertIn("_ai_mark_busy_1591r30(status_map, latest, update_id)", observer)
        self.assertLess(observer.index("_ai_success_verdict_1591r30(status_map, latest, response_text)"), observer.index("_ai_db_complete("))
        clock = [1000.0]
        ns = {"re": __import__("re"), "time": types.SimpleNamespace(time=lambda: clock[0]), "print": lambda *a, **k: None,
              "AI_BUSY_MAX_SECONDS": 150, "AI_YIELD_MAX_SECONDS": 120, "AI_VERDICT_MAX_AGE": 900}
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id in ("SIGN_SENT_RE_1591R30", "_SIGNATURE_CANVAS_FILLED_JS_1591R30") for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(src, ["_ai_busy_1591r30", "_ai_verdict_1591r30", "_ai_mark_busy_1591r30", "_ai_success_verdict_1591r30",
                             "_sign_request_sent_1591r30", "_sign_retry_if_unsent_1591r30", "_sign_prepare_1591r30",
                             "_signature_canvas_filled_1591r30"], ns)
        sm = {}
        req = "[AUTO_SUCCESS_ASSIST TAB 3] Это твоя главная обязанность …"
        self.assertEqual(ns["_ai_mark_busy_1591r30"](sm, req, 77), 3); self.assertIn("ai_busy:3", sm)
        worker = {"id": 3, "status_map": sm}
        self.assertTrue(ns["_ai_busy_1591r30"](worker), "the local code yields while DeepSeek works on the tab")
        clock[0] += 130
        self.assertFalse(ns["_ai_busy_1591r30"](worker), "but never longer than AI_YIELD_MAX_SECONDS")
        clock[0] = 1000.0; sm.clear(); ns["_ai_mark_busy_1591r30"](sm, req, 78); worker.pop("ai_yield_since", None)
        self.assertTrue(ns["_ai_busy_1591r30"](worker))
        self.assertEqual(ns["_ai_success_verdict_1591r30"](sm, req, "…отчёт…\nVERDICT: SIGNED"), "SIGNED")
        self.assertNotIn("ai_busy:3", sm); self.assertFalse(ns["_ai_busy_1591r30"](worker))
        worker["sign_clicked_at"] = 900.0
        self.assertEqual(ns["_ai_verdict_1591r30"](worker), "SIGNED")
        worker["sign_clicked_at"] = 2000.0
        self.assertEqual(ns["_ai_verdict_1591r30"](worker), "", "a verdict given before the click does not count")
        self.assertIsNone(ns["_ai_success_verdict_1591r30"](sm, req, "нет вердикта"))
        self.assertIsNone(ns["_ai_success_verdict_1591r30"](sm, "[AUTO_ERROR_ASSIST TAB 3] x", "VERDICT: SIGNED"))
        self.assertEqual(ns["_ai_success_verdict_1591r30"](sm, req, "VERDICT: NOT_SIGNED — кнопка серая"), "NOT_SIGNED")
        # the retry: only when nothing was sent and the button is still there, and only once
        sent = ns["_sign_request_sent_1591r30"]
        self.assertTrue(sent({"responses": [{"url": "https://x/v1/esim-selfreg/checksignature/", "method": "POST", "status": 200}]}))
        self.assertTrue(sent({"responses": [{"url": "https://x/v1/esim-selfreg/v2/sendpassportdata/", "method": "POST", "status": 202}]}))
        self.assertFalse(sent({"responses": [{"url": "https://x/api/ping", "method": "GET", "status": 200}]})); self.assertFalse(sent(None))
        calls = []
        ns.update({"_signature_button_locator": lambda page: "btn", "dismiss_blocking_overlays": lambda page, **k: calls.append("overlays"),
                   "_sign_trace_begin_1591r25": lambda page, w: calls.append("trace_begin"),
                   "_sign_trace_end_1591r25": lambda page, w, note="": calls.append(("trace_end", note)),
                   "fill_signature_and_submit": lambda page, diag: calls.append("sign")})
        page = types.SimpleNamespace(evaluate=lambda js: False)
        w = {"id": 2, "sign_trace": {"responses": []}}
        self.assertTrue(ns["_sign_retry_if_unsent_1591r30"](page, w))
        self.assertEqual(calls, ["overlays", "trace_begin", "sign", ("trace_end", "retry")]); self.assertEqual(w["sign_retries"], 1)
        calls.clear()
        self.assertFalse(ns["_sign_retry_if_unsent_1591r30"](page, w), "never a second retry"); self.assertEqual(calls, [])
        w2 = {"id": 2, "sign_trace": {"responses": [{"url": "https://x/checksignature/", "method": "POST", "status": 200}]}}
        self.assertFalse(ns["_sign_retry_if_unsent_1591r30"](page, w2), "the request went out: no retry")
        ns["_signature_button_locator"] = lambda page: None
        self.assertFalse(ns["_sign_retry_if_unsent_1591r30"](page, {"id": 2, "sign_trace": {"responses": []}}), "button gone: nothing to click")

    def test_prompt_only_revision_30_builds_and_upgrades_to_36(self):
        with tempfile.TemporaryDirectory() as d:
            r30 = Path(d) / "r30"
            shutil.copytree(PACKAGE, r30, ignore=shutil.ignore_patterns("__pycache__"))
            env = dict(os.environ, FIX_1591_MAX_REVISION="30")
            run = subprocess.run([sys.executable, fix.__file__, str(r30)], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr); self.assertIn("Revision 30 applied", run.stdout)
            src = (r30 / "test_beeline.py").read_text("utf-8")
            self.assertIn("AI_VERDICT_1591R30", src); self.assertNotIn("SIGN_ROBUST_1591R31", src); self.assertNotIn("TARIFF_SCOPE_1591R32", src); self.assertNotIn("TARIFF_CHANGE_BUTTON_1591R33", src); self.assertNotIn("BROWSER_COUNT_ENV_1591R34", src); self.assertNotIn("TRACE_COMPACT_1591R35", src); self.assertNotIn("SIM_URL_PER_ROW_1591R36", src)
            self.assertIn("VERDICT: SIGNED", src); self.assertNotIn("_sign_retry_if_unsent_1591r30", src)
            self.assertEqual(json.loads((r30 / "manifest.json").read_text("utf-8"))["revision"], 30)
            run = subprocess.run([sys.executable, fix.__file__, str(r30)], env=env, capture_output=True, text=True)
            self.assertIn("Already revision 30", run.stdout)
            # a server on the prompt-only build is accepted by the full (r36) installer
            self.assertIn(hashlib.sha256((r30 / "test_beeline.py").read_bytes()).hexdigest(), fix.ACCEPTED_PACKAGE_SHAS)
            app = Path(d) / "app"; app.mkdir()
            for name in ("test_beeline.py", "server_controller.py", "symbol_matching.py", "operator_runtime_io.py", "install.py", "test_update.py"):
                shutil.copy(r30 / name, app / name)
            (app / "telegram_config.json").write_text(json.dumps({"proxy": "socks5h://u:p@h:1"}))
            run = subprocess.run([sys.executable, str(self.pkg / "install.py"), "--app", str(app)], capture_output=True, text=True, timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr); self.assertIn("CHECK OK", run.stdout)

    def test_signature_canvas_check_in_a_browser(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        ns = {}
        for node in ast.parse(self.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "_SIGNATURE_CANVAS_FILLED_JS_1591R30" for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(self.source, ["_signature_canvas_filled_1591r30"], ns)
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
                page = browser.new_page()
                page.set_content("<canvas id='c' width='400' height='200' style='width:400px;height:200px'></canvas>")
                blank = ns["_signature_canvas_filled_1591r30"](page)
                page.evaluate("() => { const x = document.getElementById('c').getContext('2d'); x.lineWidth = 3; x.beginPath(); x.moveTo(10, 10); x.lineTo(300, 150); x.stroke(); }")
                drawn = ns["_signature_canvas_filled_1591r30"](page)
                page.set_content("<p>no canvas</p>")
                none = ns["_signature_canvas_filled_1591r30"](page)
                browser.close()
        except Exception as exc:
            self.skipTest(f"chromium not available: {type(exc).__name__}")
        self.assertIs(blank, False); self.assertIs(drawn, True); self.assertIsNone(none)

    def test_tariff_card_is_found_inside_the_picker_next_to_the_basket(self):
        """The basket already holds bee START (chosen by an earlier row in the same Chromium): the
        same title appears twice, first with «изменить» and no «выбрать» (the page of tab 8, row 55)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        import re as _re
        ns = {"re": _re, "TARIFF_NAME": "подписка bee START", "monotonic": __import__("time").monotonic,
              "_CHOOSE_BUTTON_RE": _re.compile(r"^\s*выбрать\s*$", _re.I)}
        for node in ast.parse(self.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id in ("_TARIFF_PICKER_HEADER_RE_1591R32", "_TARIFF_TITLE_RE_1591R32", "_TARIFF_BASKET_BUTTON_RE_1591R32") for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(self.source, ["_tariff_choose_button", "_tariff_card_button_1591r32"], ns)
        card = lambda name, price, metric: (f"<div class='card'><div><p>{name}</p></div><div><p>{price}</p>"
                                           f"<button data-metric-name='{metric}'><p>выбрать</p></button></div></div>")
        basket = ("<div id='basket'><div><p>подписка bee START</p></div><div><button>изменить</button>"
                  "<button aria-label='Удалить тариф'></button></div><p>1 гб, ∞ звонки</p>"
                  "<div class='option'><p>защита от спама</p><button><span>выбрать</span></button></div></div>")
        picker = ("<div id='picker'><p>выберите тариф</p><div class='row'>" + card("подписка bee START", "0 ₽/месяц", "start")
                  + card("подписка bee HIT", "500 ₽/месяц", "hit") + card("подписка bee SUPER START", "300 ₽", "superstart") + "</div></div>")
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
                page = browser.new_page()
                page.set_content(basket + picker)
                got_with_basket = ns["_tariff_choose_button"](page, None, timeout=1500).get_attribute("data-metric-name")
                page.set_content(picker)                              # the usual page: picker only
                got_plain = ns["_tariff_choose_button"](page, None, timeout=1500).get_attribute("data-metric-name")
                page.set_content("<div class='row'>" + card("подписка bee HIT", "500", "hit") + card("подписка bee START", "0", "start2") + "</div>")
                got_no_header = ns["_tariff_choose_button"](page, None, timeout=1500).get_attribute("data-metric-name")
                page.set_content(basket)                              # basket only: nothing to choose
                with self.assertRaises(RuntimeError) as ctx:
                    ns["_tariff_choose_button"](page, None, timeout=800)
                browser.close()
        except (RuntimeError, AssertionError):
            raise
        except Exception as exc:
            self.skipTest(f"chromium not available: {type(exc).__name__}")
        self.assertEqual(got_with_basket, "start"); self.assertEqual(got_plain, "start"); self.assertEqual(got_no_header, "start2")
        self.assertIn("RECOVERABLE_RESTART_ROW", str(ctx.exception))

    def test_same_row_restarts_are_capped_and_the_row_goes_back(self):
        import time as _t
        with tempfile.TemporaryDirectory() as d:
            statuses, beats = [], []
            ns = {"json": json, "Path": Path, "time": _t, "ROW_RESTART_MAX": 3, "ROW_DEFER_MAX_PER_RUN": 2,
                  "DEFERRED_ROWS_FILE_NAME": "deferred_rows.jsonl",
                  "set_tab_status": lambda w, icon, text: statuses.append(text), "external_heartbeat": lambda w, why: beats.append(why)}
            exec_functions(self.source, ["_row_restart_exhausted_1591r32", "_row_number_value", "row_parts", "reset_runtime_state"], ns)
            class Q:
                def __init__(self): self.items = []
                def put(self, row): self.items.append(row)
            rows, q = {"row_no": 55, "active_digits": "9601234567", "second_value": "1234"}, Q()
            w = {"id": 8, "base_dir": d, "phase": "RESTART_ROW_READY", "row": rows}
            self.assertEqual([ns["_row_restart_exhausted_1591r32"](w, rows, q) for _ in range(3)], [False, False, False])
            self.assertTrue(ns["_row_restart_exhausted_1591r32"](w, rows, q), "the 4th restart of the same row gives it up")
            self.assertEqual(w["phase"], "IDLE"); self.assertIsNone(w["row"]); self.assertIs(w["form_ready"], False)
            self.assertEqual(q.items, [rows]); self.assertEqual(rows["_deferred_1591r32"], 1); self.assertEqual(beats[-1], "row_deferred")
            self.assertIn("вернул в конец очереди", statuses[-1])
            other = {"row_no": 56, "active_digits": "9607654321"}
            self.assertFalse(ns["_row_restart_exhausted_1591r32"](w, other, q), "a new row starts its own count")
            self.assertEqual(w["row_restarts_1591r32"], {"9607654321": 1})
            w.update({"phase": "RESTART_ROW_READY", "row": rows})
            for _ in range(3): ns["_row_restart_exhausted_1591r32"](w, rows, q)
            self.assertTrue(ns["_row_restart_exhausted_1591r32"](w, rows, q)); self.assertEqual(len(q.items), 2)
            for _ in range(3): ns["_row_restart_exhausted_1591r32"](w, rows, q)
            self.assertTrue(ns["_row_restart_exhausted_1591r32"](w, rows, q))
            self.assertEqual(len(q.items), 2, "a row goes back at most twice per launch"); self.assertIn("следующего запуска", statuses[-1])
            lines = [json.loads(x) for x in Path(d, "deferred_rows.jsonl").read_text("utf-8").splitlines()]
            self.assertEqual([(x["row"], x["restarts"], x["requeued"]) for x in lines], [(55, 3, True), (55, 3, True), (55, 3, False)])
        loop = self.source[self.source.index("        while not worker[\"stopped\"]:\n            if pending_initial_row is not None:"):]
        loop = loop[:loop.index("print(f\"[Вкладка {tab_id}] Воркер завершил очередь.\"")]
        self.assertIn("if _row_restart_exhausted_1591r32(worker, row, rows):  # ROW_RESTART_LIMIT_1591R32\n                        break", loop)

    def test_drain_has_a_deadline_but_waits_for_confirmation(self):
        import time as _t
        with tempfile.TemporaryDirectory() as d:
            ns = {"json": json, "Path": Path, "time": _t, "RESTART_DRAIN_FILE_NAME": "restart_drain.json",
                  "DRAIN_SOFT_MAX_SECONDS": 900, "DRAIN_HARD_MAX_SECONDS": 2400,
                  "DRAIN_PROTECTED_PHASES": {"POST_CONTINUE", "AUTH_WAIT", "CONFIRM", "RESEND", "PROTECTED_CHECK", "POST_AUTH_REVIEW", "SIGN_WAIT", "SUCCESS_ASSIST", "ERROR_ASSIST"}}
            exec_functions(self.source, ["_drain_age_1591r32", "_drain_deadline_1591r32", "row_parts"], ns)
            class P:
                def __init__(self, alive=True): self.alive = alive; self.terminated = 0
                def is_alive(self): return self.alive
                def terminate(self): self.terminated += 1; self.alive = False
                def join(self, timeout=None): pass
            def drain(age):
                Path(d, "restart_drain.json").write_text(json.dumps({"requested_at": _t.time() - age, "reason": "every 60 min"}))
            procs = {1: P(), 2: P(), 3: P(), 4: P(False)}
            hb = {"1": {"phase": "ROW_START", "row": {"row_no": 55}}, "2": {"phase": "CONFIRM", "row": {"row_no": 56}},
                  "3": {"phase": "SIGN_WAIT", "success_guard": True}, "4": {"phase": "RESTART_WAIT"}}
            self.assertEqual(ns["_drain_age_1591r32"](d), 0.0, "no drain file: no age")
            drain(600)
            self.assertEqual(ns["_drain_deadline_1591r32"](d, procs, hb), [], "10 minutes: everyone keeps working")
            drain(1000)
            self.assertEqual(ns["_drain_deadline_1591r32"](d, procs, hb), [1], "16 minutes: only the row-start worker is stopped")
            self.assertEqual(procs[1].terminated, 1); self.assertEqual(hb["1"]["phase"], "RESTART_WAIT")
            self.assertEqual(procs[2].terminated, 0); self.assertEqual(procs[3].terminated, 0)
            self.assertEqual(ns["_drain_deadline_1591r32"](d, procs, hb), [], "a stopped worker is not stopped twice")
            drain(2500)
            self.assertEqual(ns["_drain_deadline_1591r32"](d, procs, hb), [2, 3], "40 minutes: the rest as well")
        final = self.source[self.source.index("        while True:\n            ensure_ai_receiver_alive()"):]
        self.assertIn("draining = _restart_tick()  # SCHEDULED_RESTART_1591R13\n            if draining:\n                _drain_deadline_1591r32(base_dir, processes, heartbeat)", final[:600])

    def test_worker_replacement_with_the_same_row_is_capped(self):
        with tempfile.TemporaryDirectory() as d:
            import time as _t
            ns = {"json": json, "Path": Path, "time": _t, "ROW_RESPAWN_MAX": 3, "_ROW_RESPAWNS_1591R32": {},
                  "DEFERRED_ROWS_FILE_NAME": "deferred_rows.jsonl"}
            exec_functions(self.source, ["_row_for_respawn_1591r32", "_row_number_value", "row_parts"], ns)
            row = {"row_no": 55, "active_digits": "9601234567"}
            got = [ns["_row_for_respawn_1591r32"](row, 6, d, "watchdog") for _ in range(3)]
            self.assertEqual(got, [row, row, row], "three replacements keep the row")
            self.assertIsNone(ns["_row_for_respawn_1591r32"](row, 6, d, "dead recovery"), "the fourth gives it up")
            self.assertIsNone(ns["_row_for_respawn_1591r32"](None, 6, d, "watchdog"))
            other = {"row_no": 56, "active_digits": "9607654321"}
            self.assertIs(ns["_row_for_respawn_1591r32"](other, 7, d, "watchdog"), other, "another row has its own count")
            lines = [json.loads(x) for x in Path(d, "deferred_rows.jsonl").read_text("utf-8").splitlines()]
            self.assertEqual([(x["row"], x["respawns"], x["requeued"], x["why"]) for x in lines], [(55, 3, False, "dead recovery")])
        for who in ("dead recovery", "watchdog"):
            self.assertIn(f'None if completed else _row_for_respawn_1591r32(saved_row, tab_id, base_dir, "{who}"),  # ROW_RESTART_LIMIT_1591R32', self.source)
        self.assertNotIn("None if completed else saved_row,", self.source)

    def test_lite_build_is_revision_36_without_the_signing_code(self):
        with tempfile.TemporaryDirectory() as d:
            lite = Path(d) / "lite"
            shutil.copytree(PACKAGE, lite, ignore=shutil.ignore_patterns("__pycache__"))
            env = dict(os.environ, FIX_1591_WITHOUT_R31="1")
            run = subprocess.run([sys.executable, fix.__file__, str(lite)], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr); self.assertIn("Revision 36 applied", run.stdout)
            src = (lite / "test_beeline.py").read_text("utf-8")
            for marker in ("AI_VERDICT_1591R30", "TARIFF_SCOPE_1591R32", "ROW_RESTART_LIMIT_1591R32", "DRAIN_DEADLINE_1591R32", "TARIFF_CHANGE_BUTTON_1591R33", "BROWSER_COUNT_ENV_1591R34", "TRACE_COMPACT_1591R35", "SIM_URL_PER_ROW_1591R36"):
                self.assertIn(marker, src)
            self.assertNotIn("SIGN_ROBUST_1591R31", src); self.assertNotIn("_sign_retry_if_unsent_1591r30", src)
            self.assertNotIn("РЕВИЗИЯ 31", (lite / "README.txt").read_text("utf-8"))
            run = subprocess.run([sys.executable, fix.__file__, str(lite)], env=env, capture_output=True, text=True)
            self.assertIn("Already revision 36", run.stdout)
            # the lite build is a reviewed input of the full build and upgrades to exactly it
            self.assertIn(hashlib.sha256((lite / "test_beeline.py").read_bytes()).hexdigest(), fix.ACCEPTED_PACKAGE_SHAS)
            run = subprocess.run([sys.executable, fix.__file__, str(lite)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr); self.assertIn("Revision 36 applied", run.stdout)
            self.assertEqual((lite / "test_beeline.py").read_text("utf-8"), self.source)

    def test_tariff_change_button_is_the_tariff_one_not_the_region_one(self):
        """The basket of row 105: buttons «Саратов», «изменить» (region), «изменить» (tariff), «идём дальше»."""
        try:
            from playwright.sync_api import sync_playwright, expect
        except ImportError:
            self.skipTest("playwright not installed")
        import re as _re
        ns = {"re": _re, "expect": expect, "_TARIFF_TITLE_RE_1591R32": _re.compile(r"^\s*подписка bee\b", _re.I)}
        for node in ast.parse(self.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "_TARIFF_CHANGE_METRIC_1591R33" for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(self.source, ["_tariff_change_button_1591r33"], ns)
        region = "<div id='region'><p>регион</p><button>Саратов</button><button id='r'>изменить</button></div>"
        tariff = lambda marked: ("<div id='tariff'><div><p>подписка bee START</p></div><div><button id='t'"
                                 + (" data-metric-name='basketMetric:handleClickChangeTariffButton'" if marked else "")
                                 + "><span>изменить</span></button><button aria-label='Удалить тариф'></button></div></div>")
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
                page = browser.new_page()
                page.set_content(region + tariff(True) + "<button>идём дальше</button>")
                marked = ns["_tariff_change_button_1591r33"](page).first.get_attribute("id")
                page.set_content(region + tariff(False))
                by_title = ns["_tariff_change_button_1591r33"](page).first.get_attribute("id")
                page.set_content(region)                                   # no tariff block at all: the old behaviour
                only = ns["_tariff_change_button_1591r33"](page).first.get_attribute("id")
                browser.close()
        except Exception as exc:
            self.skipTest(f"chromium not available: {type(exc).__name__}")
        self.assertEqual((marked, by_title, only), ("t", "t", "r"))
        head = self.source[self.source.index("        def click_tariff_change():"):][:600]
        self.assertIn("_tariff_change_button_1591r33(page),\n                page.get_by_role(\"button\", name=\"изменить\", exact=True),", head)

    def test_pushed_order_link_belongs_to_the_current_row(self):
        """Row 538 of tab 2 was pushed with the hash_order of the tab's earlier row: the worker's
        link was copied only when empty and never cleared between rows."""
        ns = {}
        exec_functions(self.source, ["reset_runtime_state"], ns)
        w = {"row": {"row_no": 1}, "diagnostic": None, "reserved_sim_url": "https://x/?hash_order=aaa", "reserved_sim_number": "+7999",
             "post_retries": 0, "confirm_attempt": 0}
        ns["reset_runtime_state"](w)
        self.assertIsNone(w["reserved_sim_url"]); self.assertIsNone(w["reserved_sim_number"]); self.assertIsNone(w["row"])
        pending = self.source[self.source.index('    if status == "PENDING_CONFIRM":'):][:900]
        self.assertIn('if cached_url and (getattr(page, "_reserved_sim_url_locked", False) or not worker.get("reserved_sim_url")):\n'
                      '            worker["reserved_sim_url"] = cached_url', pending)
        self.assertNotIn('if cached_url and not worker.get("reserved_sim_url"):', self.source)
        # the same-row restart keeps the worker dict: a new page's locked capture must win
        import textwrap
        src = pending.replace("    if status == \"PENDING_CONFIRM\":\n", "")
        body = textwrap.dedent("\n".join(src.splitlines()[:7]))  # two captures, three comment lines, if, assignment
        page = types.SimpleNamespace(_reserved_sim_url="https://x/?hash_order=new", _reserved_sim_number="+7111", _reserved_sim_url_locked=True)
        worker = {"reserved_sim_url": "https://x/?hash_order=old"}
        exec(compile(body, "pending", "exec"), {"getattr": getattr}, {"page": page, "worker": worker})
        self.assertEqual(worker["reserved_sim_url"], "https://x/?hash_order=new"); self.assertEqual(worker["reserved_sim_number"], "+7111")
        page.__dict__["_reserved_sim_url_locked"] = False; page.__dict__["_reserved_sim_url"] = "https://x/registration/esim/mobile-id-auth"
        exec(compile(body, "pending", "exec"), {"getattr": getattr}, {"page": page, "worker": worker})
        self.assertEqual(worker["reserved_sim_url"], "https://x/?hash_order=new", "an unlocked later URL never replaces the offer link")

    def test_res_command_answers_with_the_rows_real_order_link(self):
        ctrl = (self.pkg / "server_controller.py").read_text("utf-8")
        self.assertIn("import re\n", ctrl)
        self.assertLess(ctrl.index('if text.startswith("/restart"):'), ctrl.index('if text.startswith("/res"):'), "/restart is matched before /res")
        journal = (
            "2026-10-01T02:30:00+0000 h python[415717]: [Вкладка 2] Обрабатываю строку 530, номер заканчивается на 1111.\n"
            "2026-10-01T02:30:10+0000 h python[415717]: eSIM offer сохранён: номер=+79620000001 | https://s.beeline.ru/registration/esim?hash_order=ba031a19\n"
            "2026-10-01T02:35:00+0000 h python[415717]: [Вкладка 2] Результат строки 530: CONFIRM_TIMEOUT\n"
            "2026-10-01T02:41:27+0000 h python[415717]: [Вкладка 2] Обрабатываю строку 538, номер заканчивается на 9929.\n"
            "2026-10-01T02:41:43+0000 h python[415717]: eSIM offer сохранён: номер=+79626158923 | https://s.beeline.ru/registration/esim?hash_order=47180f97\n"
            "2026-10-01T02:49:12+0000 h python[415717]: Нажата кнопка «Подписать договор».\n"
            "2026-10-01T02:49:24+0000 h python[415717]: [Вкладка 2] 💳 ТРЕБУЕТСЯ ОПЛАТА. Строка 538: подпись принята.\n"
            "2026-10-01T03:28:00+0000 h python[421427]: [Вкладка 3] Обрабатываю строку 540, номер заканчивается на 2222.\n"
            "2026-10-01T03:28:20+0000 h python[421427]: eSIM offer сохранён: номер=+79053802755 | https://s.beeline.ru/registration/esim?hash_order=8b03e9a8\n"
            "2026-10-01T03:28:46+0000 h python[421427]: eSIM offer сохранён: номер=+79648785843 | https://s.beeline.ru/registration/esim?hash_order=0f125838\n"
        )
        import re as _re
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd); return types.SimpleNamespace(stdout=journal)
        ns = {"re": _re, "subprocess": types.SimpleNamespace(run=fake_run)}
        for node in ast.parse(ctrl).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id.startswith("_RL_") for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "ctrl", "exec"), ns)
        exec_functions(ctrl, ["_rows_from_journal_1591r36", "_row_link_command"], ns)
        answer = ns["_row_link_command"](" 79626158923")
        self.assertIn("Строка 538", answer); self.assertIn("hash_order=47180f97", answer); self.assertNotIn("ba031a19", answer)
        self.assertIn("исход: оплата", answer); self.assertEqual(calls[0][:2], ["journalctl", "-u"])
        self.assertIn("hash_order=47180f97", ns["_row_link_command"]("8923"), "the last digits of the eSIM are enough")
        self.assertIn("hash_order=47180f97", ns["_row_link_command"]("538"), "or the row number")
        by_row = ns["_row_link_command"]("540")
        self.assertIn("hash_order=0f125838", by_row); self.assertIn("ранних заказов этой строки без данных: 1", by_row)
        self.assertIn("нет строки или номера", ns["_row_link_command"]("0000009"))
        self.assertIn("Формат", ns["_row_link_command"](""))
        self.assertIn("'_row_link_command':lambda a:''", (self.pkg / "test_update.py").read_text("utf-8"))
        manifest = json.loads((self.pkg / "manifest.json").read_text("utf-8"))
        self.assertIn(fix.CONTROLLER_OUTPUT_SHA_R27_R35, manifest["files"]["server_controller.py"]["previous_output_sha256"])

    def test_stale_drain_file_is_discarded_at_start(self):
        src = self.source
        head = src[src.index("restart_started_at = monotonic()"):src.index("def _restart_tick():")]
        self.assertIn("if restart_drain_requested(base_dir):  # STALE_DRAIN_RESET_1591R29", head)
        self.assertIn("clear_restart_drain(base_dir)", head)
        self.assertLess(head.index("restart_notified = False"), head.index("clear_restart_drain(base_dir)"))

    def test_two_browsers_and_captchas_do_not_pile_up(self):
        src = self.source
        self.assertIn("BROWSER_COUNT = _browser_count_1591r34()", src); self.assertIn("TABS_PER_BROWSER = 4", src)
        ns = {"os": types.SimpleNamespace(environ={})}
        exec_functions(src, ["_browser_count_1591r34"], ns)
        self.assertEqual(ns["_browser_count_1591r34"](), 2, "default stays two Chromium (r28)")
        for value, expected in (("1", 1), (" 2 ", 2), ("0", 1), ("9", 4), ("abc", 2), ("", 2)):
            ns["os"].environ["BEELINE_BROWSERS"] = value
            self.assertEqual(ns["_browser_count_1591r34"](), expected, value)
        self.assertIn('"captcha_gate": captcha_gate,', src); self.assertIn("captcha_gate = ctx.Semaphore(CAPTCHA_PARALLEL_MAX)", src)
        self.assertIn("success_queue=None, captcha_gate=None)", src[src.index("def _tab_process"):src.index("def _tab_process") + 400])
        calls = []
        class Gate:
            def __init__(self, fail_first): self.fail = fail_first; self.held = 0
            def acquire(self, timeout=None):
                calls.append(("acquire", timeout))
                if self.fail > 0:
                    self.fail -= 1; return False
                self.held += 1; return True
            def release(self): self.held -= 1; calls.append(("release", None))
        import types as _t, sys as _sys
        fake_matcher = _t.ModuleType("local_matcher"); fake_matcher.matcher_progress = lambda stage: calls.append(("progress", stage))
        clock = [0.0]
        ns = {"monotonic": lambda: clock[0], "_try_local_captcha_unlocked": lambda page, frame=None: calls.append(("solve", page)) or "OK",
              "CAPTCHA_GATE_WAIT_SECONDS": 180, "_CAPTCHA_GATE": None}
        exec_functions(src, ["try_local_captcha"], ns)
        old = _sys.modules.get("local_matcher"); _sys.modules["local_matcher"] = fake_matcher
        try:
            self.assertEqual(ns["try_local_captcha"]("p0"), "OK"); self.assertEqual(calls, [("solve", "p0")], "no gate: solve at once")
            calls.clear(); gate = Gate(fail_first=2); ns["_CAPTCHA_GATE"] = gate
            self.assertEqual(ns["try_local_captcha"]("p1"), "OK")
            self.assertEqual([c for c in calls if c[0] == "progress"], [("progress", "CAPTCHA_WAIT")] * 2, "the wait is reported to the watchdog")
            self.assertEqual(calls[-2:], [("solve", "p1"), ("release", None)]); self.assertEqual(gate.held, 0)
            calls.clear(); gate = Gate(fail_first=10 ** 6); ns["_CAPTCHA_GATE"] = gate
            def tick(timeout=None):
                clock[0] += 5; return Gate.acquire(gate, timeout)
            gate.acquire = tick
            self.assertEqual(ns["try_local_captcha"]("p2"), "OK", "after CAPTCHA_GATE_WAIT_SECONDS the tab solves without a slot")
            self.assertNotIn(("release", None), calls); self.assertIn(("solve", "p2"), calls)
        finally:
            if old is not None: _sys.modules["local_matcher"] = old
            else: _sys.modules.pop("local_matcher", None)

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
        for variant, src in (("first-build", Path(PACKAGE)), ("revision-36", self.pkg)):
            run = self._check(src, proxy=True)
            self.assertEqual(run.returncode, 0, variant + "\n" + run.stdout + run.stderr)
            self.assertIn("CHECK OK", run.stdout, variant)
        self.assertIn(fix.EXPECTED_INPUT_OUTPUT_SHA, manifest["files"]["test_beeline.py"]["previous_output_sha256"])
        # A server on any of revisions 13..20 (controller unchanged between them) must still upgrade.
        ctrl_prev = manifest["files"]["server_controller.py"]["previous_output_sha256"]
        self.assertIn(fix.CONTROLLER_OUTPUT_SHA_R12, ctrl_prev); self.assertIn(fix.CONTROLLER_OUTPUT_SHA_R13_R20, ctrl_prev)
    def test_installer_refuses_without_configured_proxy(self):
        run = self._check(Path(PACKAGE), proxy=False)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('telegram_config.json has no "proxy"', run.stdout + run.stderr)

    def test_direct_proxy_means_no_proxy_for_code_and_installer(self):
        ns = {"os": os, "TELEGRAM_DEFAULT_PROXY": ""}
        for node in ast.parse(self.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "TELEGRAM_DIRECT_PROXY_VALUES" for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(self.source, ["telegram_http_proxies"], ns)
        fn = ns["telegram_http_proxies"]
        self.assertIsNone(fn({"proxy": "direct"})); self.assertIsNone(fn({"proxy": "NONE"})); self.assertIsNone(fn({"proxy": ""}))
        self.assertEqual(fn({"proxy": "socks5://u:p@h:1"}), {"http": "socks5h://u:p@h:1", "https": "socks5h://u:p@h:1"})
        with tempfile.TemporaryDirectory() as d:
            app = Path(d) / "app"; shutil.copytree(self.pkg, app, ignore=shutil.ignore_patterns("__pycache__"))
            (app / "telegram_config.json").write_text(json.dumps({"proxy": "direct"}))
            run = subprocess.run([sys.executable, str(self.pkg / "install.py"), "--app", str(app)],
                                 capture_output=True, text=True, timeout=300)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr); self.assertIn("CHECK OK", run.stdout)
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
              "ERROR_ASSIST_MAX_SECONDS": 300, "ERROR_SKIP_DWELL_SECONDS": 15, "ERROR_ROW_MAX_ATTEMPTS": 2,
              "remember_processed_number": lambda base, row: events.append(("processed", row))}
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
            self.assertIn("Already revision 36", run.stdout)

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
        self.assertEqual(manifest["revision"], 36)
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
            ns = {"app": app, "BASE_DIR": Path(d), "_send": sent.append, "time": __import__("time"),
                  "RELAUNCH_MARKER_MAX_AGE": 600}
            exec_functions(control, ["_restart_command", "_restart_after_drain", "_relaunch_marker_fresh"], ns)
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
                def __init__(self, code, last_code=None):
                    self.proc = FakePopen(code) if code != "gone" else None
                    self.started = 0; self.last_code = last_code
                def running(self): return self.proc is not None and self.proc.poll() is None
                def reap(self):
                    if self.proc is not None and self.proc.poll() is not None:
                        self.last_code = self.proc.poll(); self.proc = None
                def start(self):
                    self.started += 1
                    return True, "▶️ Запущено. PID 1."
            marker = Path(d) / "restart_relaunch.json"
            running = FakeProc(None)
            self.assertFalse(ns["_restart_after_drain"](running)); self.assertEqual(running.started, 0)
            crashed = FakeProc(1)
            self.assertFalse(ns["_restart_after_drain"](crashed), "an ordinary exit is left to reap(), not relaunched")
            drained = FakeProc(75)
            self.assertTrue(ns["_restart_after_drain"](drained)); self.assertEqual(drained.started, 1)
            self.assertIn("Плановый перезапуск выполнен", sent[-1])
            # RESTART_RELAUNCH_1591R21: xvfb-run reported 5 — the fresh marker relaunches and is consumed.
            marker.write_text("{}")
            lost = FakeProc(5)
            self.assertTrue(ns["_restart_after_drain"](lost)); self.assertEqual(lost.started, 1); self.assertFalse(marker.exists())
            # reap() already consumed the exit code: last_code still triggers exactly one relaunch.
            reaped = FakeProc("gone", last_code=75)
            self.assertTrue(ns["_restart_after_drain"](reaped)); self.assertEqual(reaped.started, 1)
            self.assertFalse(ns["_restart_after_drain"](reaped)); self.assertEqual(reaped.started, 1)
            # A running process is never touched even with a marker; a stale marker is ignored and removed.
            marker.write_text("{}"); alive = FakeProc(None)
            self.assertFalse(ns["_restart_after_drain"](alive)); self.assertTrue(marker.exists())
            os.utime(marker, (1, 1)); stale = FakeProc(5)
            self.assertFalse(ns["_restart_after_drain"](stale)); self.assertFalse(marker.exists())
            self.assertIn("os.killpg(pgid, signal.SIGTERM)", control); self.assertIn("self.last_code = code", control)
            # Runtime side: the marker is written before the exit, the force-exit timer is a daemon.
            rns = {"Path": Path, "json": json, "time": __import__("time"), "os": os, "print": lambda *a, **k: None,
                   "RESTART_RELAUNCH_FILE_NAME": "restart_relaunch.json", "RESTART_EXIT_FORCE_SECONDS": 3600,
                   "RESTART_EXIT_CODE": 75}
            exec_functions(self.source, ["request_relaunch"], rns)
            timer = rns["request_relaunch"](d, "drain complete")
            try:
                self.assertTrue(timer.daemon); self.assertEqual(json.loads(marker.read_text())["reason"], "drain complete")
            finally:
                timer.cancel()
            src_tail = self.source[self.source.index("[RESTART] Все worker завершили строки; выхожу для планового перезапуска."):]
            self.assertIn('request_relaunch(base_dir, "drain complete")', src_tail[:400])
            self.assertIn('request_relaunch(base_dir, "chromium relaunch failed")', self.source)

    def test_invalid_row_is_retried_once_in_a_fresh_tab_and_skips_are_remembered(self):
        events = []
        def restart(worker):
            events.append("new_tab"); worker["phase"] = "RESTART_ROW_READY"; worker["form_ready"] = False
        ns = {"print": lambda *a, **k: None, "INVALID_ROW_MAX_ATTEMPTS": 2, "_row_number_value": lambda row: str(row[1]),
              "restart_same_row_in_new_page": restart, "set_tab_status": lambda *a: None,
              "external_heartbeat": lambda w, label: events.append(("hb", label)),
              "save_worker_result": lambda base, w, status: events.append(("saved", status)),
              "remember_processed_number": lambda base, row: events.append(("processed", row))}
        exec_functions(self.source, ["finish_worker_row", "reset_runtime_state", "_error_row_key",
                                     "_invalid_row_retry_1591r22", "_fresh_tab_for_next_row_1591r22"], ns)
        worker = {"id": 2, "row": (7, "79990000000", "1"), "phase": "ROW_START", "form_ready": True}
        ns["finish_worker_row"](Path("/tmp"), worker, "INVALID_ROW")
        self.assertEqual(worker["phase"], "RESTART_ROW_READY"); self.assertEqual(worker["row"], (7, "79990000000", "1"))
        self.assertNotIn(("saved", "INVALID_ROW"), events); self.assertEqual(events.count("new_tab"), 1)
        ns["finish_worker_row"](Path("/tmp"), worker, "INVALID_ROW")
        self.assertEqual(worker["phase"], "IDLE"); self.assertIsNone(worker["row"]); self.assertFalse(worker["form_ready"])
        self.assertEqual(events.count(("saved", "INVALID_ROW")), 1); self.assertIn(("processed", (7, "79990000000", "1")), events)
        self.assertEqual(events.count("new_tab"), 2, "the next row must start in a fresh tab, not in the used form")
        # r15/r16 final skip and the r5 second-error skip both record the row as processed.
        src = self.source
        skip_final = src[src.index("def _error_skip_final"):src.index("def enter_error_guard")]
        self.assertIn('remember_processed_number(base_dir, worker.get("row"))', skip_final)
        recover = src[src.index("def _error_recover"):src.index("def tick_error_assist")]
        self.assertIn('remember_processed_number(base_dir, worker.get("row"))', recover)


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
              "remember_processed_number": lambda base, row: calls.append(("processed", row)),
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
        exec_functions(self.source, ["_success_message", "_final_links_lines_1591r23"], ns)
        text = ns["_success_message"]({"id": 2, "row": (5, "79990000000", "1234"), "total_rows": 10},
                                      {"profile": {}, "sim_number": "89", "sim_url": "u"})
        lines = text.split("\n")
        self.assertEqual(lines[0], "#успешно"); self.assertTrue(lines[1].startswith("✅ УСПЕХ — Вкладка 2"))
        self.assertIn("Строка: 5/10", text); self.assertIn("eSIM: 89", text)
        self.assertIn("Страница договора: —", text)  # FINAL_PAGE_1591R23

    def test_success_record_and_push_carry_the_contract_page(self):
        self.assertIn("DIAGNOSTIC_SESSIONS_TO_KEEP = 40", self.source)
        ns = {"row_parts": lambda row: (row[0], row[1], row[2]), "_success_profile_lines": lambda profile: ["ФИО: X"],
              "json": json, "Path": Path}
        for node in ast.parse(self.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "_FINAL_LINKS_JS_1591R23" for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        ns["_sign_trace_summary_1591r25"] = lambda trace: None
        exec_functions(self.source, ["_success_message", "write_success_record", "capture_final_page_1591r23",
                                     "_final_links_lines_1591r23"], ns)
        class Page:
            url = "https://saratov.beeline.ru/registration/esim/contract?id=42"
            def evaluate(self, js): return {"links": [{"text": "Скачать договор", "href": "https://x/contract.pdf"},
                                                      {"text": "QR-код на странице (встроенное изображение)", "href": ""}],
                                            "title": "Договор подписан", "text": "Договор подписан. Спасибо!"}
        class Diag:
            def __init__(self): self.events = []
            def write(self, event, **data): self.events.append((event, data))
        with tempfile.TemporaryDirectory() as d:
            worker = {"id": 3, "row": (5, "79990000000", "1234"), "total_rows": 10, "page": Page(), "diagnostic": Diag(),
                      "reserved_sim_number": "89", "reserved_sim_url": "u", "success_profile": {"full_name": "A B"}}
            rec = ns["write_success_record"](Path(d), worker)
            saved = json.loads((Path(d) / "successful_sims.jsonl").read_text("utf-8").splitlines()[-1])
        self.assertEqual(rec["final_url"], Page.url); self.assertEqual(saved["final_url"], Page.url)
        self.assertEqual(saved["final_title"], "Договор подписан")
        event = next(e for e in worker["diagnostic"].events if e[0] == "final_page_1591r23")
        self.assertEqual(event[1]["text"], "Договор подписан. Спасибо!"); self.assertEqual(event[1]["url"], Page.url)
        self.assertEqual(saved["final_links"][0]["href"], "https://x/contract.pdf"); self.assertEqual(saved["sim_url"], "u")
        text = ns["_success_message"](worker, rec)
        self.assertIn("Страница договора: https://saratov.beeline.ru/registration/esim/contract?id=42", text)
        self.assertIn("Скачать договор: https://x/contract.pdf", text); self.assertIn("QR-код на странице (встроенное изображение)", text)
        self.assertIn("Заголовок страницы: Договор подписан", text)
        self.assertTrue(text.index("Ссылка eSIM: u") < text.index("Страница договора"))
        # No page (or a page that fails): the record is still written, fields stay empty.
        class Broken:
            @property
            def url(self): raise RuntimeError("closed")
            def evaluate(self, js): raise RuntimeError("closed")
        self.assertEqual(ns["capture_final_page_1591r23"](Broken()), {"url": "", "title": "", "links": []})
        self.assertEqual(ns["capture_final_page_1591r23"](None), {"url": "", "title": "", "links": []})
        self.assertEqual(ns["_final_links_lines_1591r23"](None), [])

    def test_final_page_links_are_collected_in_a_browser(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        ns = {}
        for node in ast.parse(self.source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "_FINAL_LINKS_JS_1591R23" for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(self.source, ["capture_final_page_1591r23"], ns)
        html = ("<title>Билайн — договор</title><h1>Договор подписан</h1><a href='/docs/contract-42.pdf'>Скачать договор</a>"
                "<a href='/pay/order/42'>Оплатить картой</a>"
                "<a href='/'>На главную</a><a href='/help'>Помощь</a>"
                "<a href='/esim/qr?order=42' aria-label='QR-код eSIM'></a>"
                "<img alt='QR код' src='data:image/png;base64,iVBORw0KGgo='>"
                "<a href='javascript:void(0)'>Договор (всплывающее окно)</a>")
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
                page = browser.new_page(); page.set_content(html)
                worker = {}
                result = ns["capture_final_page_1591r23"](page, worker)
                browser.close()
        except Exception as exc:
            self.skipTest(f"chromium not available: {type(exc).__name__}")
        hrefs = [x["href"] for x in result["links"]]
        self.assertTrue(any(h.endswith("/docs/contract-42.pdf") for h in hrefs)); self.assertTrue(any("/esim/qr?order=42" in h for h in hrefs))
        self.assertFalse(any(h.endswith("/help") for h in hrefs)); self.assertFalse(any(h.startswith("javascript:") for h in hrefs))
        self.assertTrue(any(h.endswith("/pay/order/42") for h in hrefs), "payment links are kept for the #оплата push")
        self.assertIn({"text": "QR-код на странице (встроенное изображение)", "href": ""}, result["links"])
        self.assertEqual(worker["final_links"], result["links"]); self.assertTrue(worker["final_url"].startswith("about:"))
        self.assertEqual(result["title"], "Билайн — договор"); self.assertEqual(worker["final_title"], "Билайн — договор")

    def test_success_needs_evidence_otherwise_the_row_is_unverified(self):
        src = self.source
        self.assertEqual(src.count("finalize_success(base_dir, worker)"), 2, "only settle_success_1591r24 and the failed-restart path")
        wait_fn = src[src.index("def tick_sign_wait"):src.index("def tick_sign_wait") + 3000]
        self.assertIn("settle_success_1591r24(base_dir, worker)", wait_fn); self.assertNotIn("finalize_success(", wait_fn)
        review_fn = src[src.index("def tick_post_auth_review"):src.index("def tick_success_assist")]
        self.assertIn("settle_success_1591r24(base_dir, worker)", review_fn); self.assertNotIn("finalize_success(base_dir, worker)", review_fn)
        clock = [1000.0]; events = []; pushed = []
        class Q:
            def put(self, text): pushed.append(text)
        class Page:
            def __init__(self, url, body="", pdf=0): self.url, self.body, self.pdf = url, body, pdf
            def locator(self, sel):
                page = self
                class L:
                    def inner_text(self, timeout=None): return page.body
                    def count(self): return page.pdf if "pdf" in sel else 0
                return L()
        ns = {"monotonic": lambda: clock[0], "time": __import__("time"), "json": json, "Path": Path, "print": lambda *a, **k: None,
              "re": __import__("re"), "row_parts": lambda row: (row[0], row[1], row[2]), "_success_profile_lines": lambda p: ["ФИО: X"],
              "capture_final_page_1591r23": lambda page, worker=None: {"url": page.url, "title": "Билайн", "links": []},
              "_final_links_lines_1591r23": lambda links: [], "set_tab_status": lambda *a: None,
              "external_heartbeat": lambda w, label: events.append(("hb", label)),
              "capture_blackbox": lambda w, r, exc=None: events.append(("blackbox", r)),
              "queue_success_assist": lambda w, note, force=False: events.append(("assist", force)),
              "_sign_trace_summary_1591r25": lambda trace: None, "_sign_trace_lines_1591r25": lambda summary: [],
              "remember_processed_number": lambda base, row: events.append(("processed", row)),
              "_ai_verdict_1591r30": lambda w: w.get("_verdict", ""),
              "finalize_success": lambda base, w: events.append("finalize")}
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id.endswith("_1591R24") or (isinstance(x, ast.Name) and x.id == "UNVERIFIED_HOLD_SECONDS") for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "PAYMENT_NEEDLES_1591R26" for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(src, ["_signed_evidence_1591r24", "_unverified_message_1591r24", "_finish_unverified_1591r24",
                             "settle_success_1591r24", "_payment_page_1591r26", "_payment_message_1591r26",
                             "_finish_payment_required_1591r26"], ns)
        ev = ns["_signed_evidence_1591r24"]
        self.assertEqual(ev(Page("https://saratov.beeline.ru/registration/esim/personal-data-form", "договор подписан")), "", "still the form")
        self.assertEqual(ev(Page("https://saratov.beeline.ru/registration/esim?hash_order=1", "Оформите eSIM")), "", "start page is not a success")
        self.assertTrue(ev(Page("https://saratov.beeline.ru/registration/esim/success")).startswith("url:"))
        self.assertTrue(ev(Page("https://saratov.beeline.ru/x", "Ваш договор подписан. Спасибо!")).startswith("text:"))
        self.assertEqual(ev(Page("https://saratov.beeline.ru/x", "", pdf=1)), "link:document")
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            ok = {"id": 2, "row": (7, "79990000000", "1"), "page": Page("https://saratov.beeline.ru/registration/esim/complete"), "success_queue": Q()}
            self.assertTrue(ns["settle_success_1591r24"](base, ok)); self.assertIn("finalize", events); self.assertTrue(ok["success_evidence"].startswith("url:"))
            events.clear()
            bad = {"id": 3, "row": (8, "79990000001", "2"), "total_rows": 10, "page": Page("https://saratov.beeline.ru/", "Главная"),
                   "success_queue": Q(), "reserved_sim_number": "89", "reserved_sim_url": "u", "success_profile": {"full_name": "A B"}}
            self.assertFalse(ns["settle_success_1591r24"](base, bad))
            self.assertEqual(bad["phase"], "SUCCESS_ASSIST"); self.assertIn(("blackbox", "success_unverified"), events); self.assertIn(("assist", True), events)
            self.assertNotIn("finalize", events)
            clock[0] += 100
            self.assertFalse(ns["settle_success_1591r24"](base, bad)); self.assertEqual(bad["phase"], "SUCCESS_ASSIST"); self.assertFalse(pushed)
            clock[0] += 100
            self.assertFalse(ns["settle_success_1591r24"](base, bad))
            self.assertEqual(bad["phase"], "SUCCESS_STOP"); self.assertTrue(bad["stopped"]); self.assertNotIn("finalize", events)
            saved = json.loads((base / "unverified_signatures.jsonl").read_text("utf-8").splitlines()[-1])
            self.assertEqual(saved["row"], 8); self.assertEqual(saved["final_url"], "https://saratov.beeline.ru/"); self.assertIn("признаков подписания", saved["reason"])
            self.assertFalse((base / "successful_sims.jsonl").exists()); self.assertFalse((base / "processed_numbers.txt").exists())
            self.assertEqual(pushed[-1].split("\n")[0], "#неподтверждено"); self.assertIn("ПОДПИСЬ НЕ ПОДТВЕРЖДЕНА — Вкладка 3", pushed[-1])
            self.assertIn("Номер НЕ помечен обработанным", pushed[-1]); self.assertIn("ФИО: X", pushed[-1])
            self.assertNotIn(("processed", (8, "79990000001", "2")), events)
            # PAYMENT_STEP_1591R26: the site's payment step is its own outcome, recorded at once.
            events.clear(); pushed.clear()
            pay = {"id": 4, "row": (9, "79990000002", "3"), "total_rows": 10, "success_queue": Q(),
                   "page": Page("https://saratov.beeline.ru/registration/esim",
                                "порядок, идём дальше\nтеперь пора оплатить eSIM\nподтвердите данные → оплатите картой → дождитесь регистрации договора\nоплатить картой"),
                   "reserved_sim_number": "90", "reserved_sim_url": "u2", "success_profile": {"full_name": "C D"}}
            self.assertFalse(ns["settle_success_1591r24"](base, pay))
            self.assertEqual(pay["phase"], "SUCCESS_STOP"); self.assertTrue(pay["stopped"]); self.assertNotIn("finalize", events)
            self.assertIn(("processed", (9, "79990000002", "3")), events)
            saved = json.loads((base / "payment_required.jsonl").read_text("utf-8").splitlines()[-1])
            self.assertEqual(saved["row"], 9); self.assertIn("пора оплатить", saved["payment_text"].lower())
            self.assertFalse((base / "successful_sims.jsonl").exists())
            self.assertEqual(pushed[-1].split("\n")[0], "#оплата"); self.assertIn("ТРЕБУЕТСЯ ОПЛАТА eSIM — Вкладка 4", pushed[-1])
            self.assertIn("оплатите картой", pushed[-1]); self.assertIn("Номер помечен обработанным", pushed[-1])
            self.assertEqual(ns["_payment_page_1591r26"](Page("https://x", "Договор подписан. Спасибо!")), "")
            # AI_VERDICT_1591R30: DeepSeek's verdict counts as evidence (SIGNED) or as the payment step.
            events.clear()
            by_ai = {"id": 5, "row": (10, "79990000003", "4"), "page": Page("https://saratov.beeline.ru/", "Главная"), "success_queue": Q(), "_verdict": "SIGNED"}
            self.assertTrue(ns["settle_success_1591r24"](base, by_ai)); self.assertIn("finalize", events); self.assertEqual(by_ai["success_evidence"], "ai:verdict_signed")
            events.clear(); pushed.clear()
            pay_ai = {"id": 6, "row": (11, "79990000004", "5"), "total_rows": 10, "page": Page("https://saratov.beeline.ru/", "Главная"), "success_queue": Q(),
                      "reserved_sim_number": "91", "reserved_sim_url": "u3", "success_profile": {}, "_verdict": "PAYMENT"}
            self.assertFalse(ns["settle_success_1591r24"](base, pay_ai)); self.assertEqual(pay_ai["phase"], "SUCCESS_STOP")
            self.assertEqual(pushed[-1].split("\n")[0], "#оплата"); self.assertIn("по вердикту DeepSeek", pushed[-1])

    def test_sign_click_trace_records_server_answers_and_reaches_the_unverified_push(self):
        src = self.source
        review = src[src.index("def tick_post_auth_review"):src.index("def tick_success_assist")]
        self.assertIn("_sign_trace_begin_1591r25(page, worker)", review); self.assertIn("_sign_trace_end_1591r25(page, worker)", review)
        self.assertLess(review.index("_sign_trace_begin_1591r25"), review.index("fill_signature_and_submit(page"))
        clock = [0.0]; events = []
        ns = {"re": __import__("re"), "time": types.SimpleNamespace(time=lambda: clock[0], strftime=__import__("time").strftime),
              "monotonic": lambda: clock[0], "print": lambda *a, **k: events.append(("print", a[0] if a else "")),
              "capture_blackbox": lambda w, r, exc=None: events.append(("blackbox", r))}
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and (x.id == "SIGN_TRACE_SECONDS" or x.id == "_SIGN_TRACE_SKIP_RE_1591R25") for x in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "pkg", "exec"), ns)
        exec_functions(src, ["_sign_trace_begin_1591r25", "_sign_trace_end_1591r25", "_sign_trace_summary_1591r25",
                             "_sign_trace_lines_1591r25"], ns)
        class Resp:
            def __init__(self, url, status, method, ctype, body):
                self.url, self.status, self.headers, self._body = url, status, {"content-type": ctype}, body
                self.request = types.SimpleNamespace(method=method)
            def text(self): return self._body
        class Page:
            def __init__(self):
                self.url = "https://saratov.beeline.ru/registration/esim/personal-data-form"; self.handlers = {}; self.removed = []
            def on(self, event, fn): self.handlers[event] = fn
            def remove_listener(self, event, fn): self.removed.append(event)
            def wait_for_timeout(self, ms): clock[0] += ms / 1000.0
        class Diag:
            def __init__(self): self.events = []
            def write(self, event, **data): self.events.append((event, data))
        page, worker = Page(), {"id": 2, "diagnostic": Diag()}
        ns["_sign_trace_begin_1591r25"](page, worker)
        self.assertEqual(set(page.handlers), {"response", "requestfailed", "console"})
        page.handlers["response"](Resp("https://saratov.beeline.ru/api/sign", 400, "POST", "application/json", '{"error":"session expired"}'))
        page.handlers["response"](Resp("https://saratov.beeline.ru/static/app.js", 200, "GET", "text/javascript", "x"))
        page.handlers["response"](Resp("https://saratov.beeline.ru/registration/esim", 200, "GET", "text/html", "<html>"))
        page.handlers["requestfailed"](types.SimpleNamespace(url="https://saratov.beeline.ru/api/ping", failure="net::ERR_ABORTED"))
        page.handlers["console"](types.SimpleNamespace(type="error", text="Uncaught TypeError"))
        page.handlers["console"](types.SimpleNamespace(type="log", text="noise"))
        page.url = "https://saratov.beeline.ru/registration/esim"
        trace = ns["_sign_trace_end_1591r25"](page, worker)
        self.assertGreaterEqual(clock[0], ns["SIGN_TRACE_SECONDS"]); self.assertEqual(sorted(page.removed), ["console", "requestfailed", "response"])
        self.assertEqual(trace["url_after"], "https://saratov.beeline.ru/registration/esim")
        urls = [r["url"] for r in trace["responses"]]; self.assertNotIn("https://saratov.beeline.ru/static/app.js", urls)
        sign = next(r for r in trace["responses"] if r["url"].endswith("/api/sign"))
        self.assertEqual(sign["body"], '{"error":"session expired"}'); self.assertEqual(len(trace["console"]), 1)
        event = next(e for e in worker["diagnostic"].events if e[0] == "sign_click_trace_1591r25")
        self.assertNotIn("_handlers", event[1]); self.assertEqual(event[1]["failed"][0]["error"], "net::ERR_ABORTED")
        self.assertIn(("blackbox", "after_sign_click"), events)
        summary = ns["_sign_trace_summary_1591r25"](trace)
        self.assertEqual([r["url"] for r in summary["responses"]], ["https://saratov.beeline.ru/api/sign"])
        lines = ns["_sign_trace_lines_1591r25"](summary)
        self.assertEqual(lines[0], "Подпись (сеть): ответов 1")  # TRACE_COMPACT_1591R35: no url line
        self.assertIn("POST https://saratov.beeline.ru/api/sign → 400", lines[1]); self.assertIn("session expired", lines[1])
        # the paid/unverified message of a signed row: one line, no polling GETs, no 2xx bodies
        ok = {"url_before": "a", "url_after": "b", "failed": [], "console": [], "responses": [
            {"method": "POST", "url": "https://saratov.beeline.ru/v1/esim-selfreg/checksignature/", "status": 200, "body": '{"isSucceeded":true}'},
            {"method": "POST", "url": "https://saratov.beeline.ru/v1/esim-selfreg/v2/sendpassportdataexistingsubscriber/?aggregateId=x", "status": 202, "body": "{...}"},
            *[{"method": "GET", "url": "https://saratov.beeline.ru/v1/esim-selfreg/v2/getselfregstatus/?aggregateId=x", "status": 200, "body": "{...}"} for _ in range(4)]]}
        self.assertEqual(ns["_sign_trace_lines_1591r25"](ok), ["Подпись (сеть): подпись → 200, паспортные данные → 202"])
        self.assertEqual(ns["_sign_trace_lines_1591r25"]({"responses": [], "failed": [], "console": []}), ["Подпись (сеть): запрос подписи в сети не замечен"])
        self.assertTrue(any("net::ERR_ABORTED" in x for x in lines)); self.assertTrue(any("Uncaught TypeError" in x for x in lines))
        self.assertEqual(ns["_sign_trace_lines_1591r25"](None), []); self.assertIsNone(ns["_sign_trace_summary_1591r25"](None))
        self.assertIsNone(ns["_sign_trace_end_1591r25"](page, {"id": 1}))
        # profile matcher: a value without a letter or digit is not a value
        loop = src[src.index("def final_profile_capture_v1583"):src.index("def finalize_success")]
        self.assertIn('if not re.search(r"[0-9a-zа-яё]", value.lower()):', loop)

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

    def _form_ns(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("rt_1591", self.pkg / "operator_runtime_io.py")
        rt = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt)
        names = ["capture_all_form_fields_v1583", "capture_form_fields_1591r19", "_alias_hit_1591r19",
                 "_profile_fallback_1591r19", "final_profile_capture_v1583"]
        tree = ast.parse(self.source)
        nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names) or (
            isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and (x.id.endswith("_1591R12") or x.id.endswith("_1591R19"))
                                              for x in n.targets))]
        ns = {"re": __import__("re"), "_io1591": rt}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "pkg", "exec"), ns)
        return ns

    def test_profile_aliases_are_whole_words_and_fallbacks_fill_unlabeled_fields(self):
        ns = self._form_ns()
        hit = ns["_alias_hit_1591r19"]
        self.assertTrue(hit("пол", "пол")); self.assertFalse(hit("обязательное поле", "пол"))
        self.assertFalse(hit("домашний телефон", "дом")); self.assertTrue(hit("дом 12", "дом"))
        self.assertTrue(hit("населенный пункт", "населённый пункт"), "ё-insensitive")
        # The exact shape of the server dump: six inputs without label/name/id/placeholder caption.
        fields = [{"tag": "input", "type": "text", "value": "Иванов Иван Иванович"},
                  {"tag": "input", "type": "text", "placeholder": "18.09.2001", "value": "01.02.1990"},
                  {"tag": "input", "type": "text", "label": "серия", "id": "passportSeries", "value": "1234"},
                  {"tag": "input", "type": "text", "label": "дата выдачи", "id": "docIssueDate", "value": "10.10.2010"},
                  {"tag": "input", "type": "text", "label": "страна", "id": "country", "value": "Россия"},
                  {"tag": "input", "type": "text", "value": "Саратовская область"},
                  {"tag": "input", "type": "text", "value": ""},
                  {"tag": "input", "type": "text", "value": "Саратов"},
                  {"tag": "input", "type": "text", "value": "Московская"},
                  {"tag": "input", "type": "text", "label": "дом", "id": "house", "value": "12"},
                  {"tag": "input", "type": "checkbox", "near": "Согласен на обработку данных региона", "value": "true"}]
        worker = {"success_profile": {}}
        ns["capture_all_form_fields_v1583"] = lambda page: []
        ns["capture_form_fields_1591r19"] = lambda page: fields
        profile, _ = ns["final_profile_capture_v1583"](types.SimpleNamespace(url="x"), worker)
        self.assertEqual(profile["full_name"], "Иванов Иван Иванович"); self.assertEqual(profile["birth_date"], "01.02.1990")
        self.assertEqual(profile["passport_issue_date"], "10.10.2010"); self.assertEqual(profile["passport_series"], "1234")
        self.assertEqual(profile["region"], "Саратовская область"); self.assertNotIn("district", profile)
        self.assertEqual(profile["locality"], "Саратов"); self.assertEqual(profile["street"], "Московская")
        self.assertEqual(profile["house"], "12"); self.assertNotIn("true", profile.values())

    def test_profile_capture_reads_captions_next_to_the_inputs_in_a_browser(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        ns = self._form_ns()
        html = """<form>
<div class="section"><h3>Персональные данные</h3></div>
<div class="field"><div class="caption">ФИО</div><div class="ctrl"><input type="text" value="Петров Пётр Петрович"></div></div>
<div class="field"><div class="ctrl"><input type="text" placeholder="18.09.2001" value="03.04.1985"></div><div class="caption">Дата рождения</div></div>
<div class="row"><div class="field"><label for="passportSeries">серия</label><input id="passportSeries" value="1234"></div>
<div class="field"><label for="passportNumber">номер</label><input id="passportNumber" value="567890"></div></div>
<div class="field"><label for="docIssueDate">дата выдачи</label><input id="docIssueDate" value="10.10.2010"></div>
<div class="field"><label for="docIssuer">кем выдан</label><input id="docIssuer" value="ОУФМС России по Саратовской области"></div>
<div class="field"><label for="country">страна</label><input id="country" value="Россия"></div>
<div class="field"><span class="caption">Регион</span><div class="ctrl"><input type="text" value="Саратовская область"></div><small>Обязательное поле</small></div>
<div class="field"><div class="ctrl"><input type="text" value=""></div></div>
<div class="field"><div class="ctrl"><input type="text" value="Саратов"></div></div>
<div class="field"><div class="ctrl"><input type="text" value="Московская"></div></div>
<div class="field"><label for="house">дом</label><input id="house" value="12"></div>
<div class="field"><label for="building">корпус</label><input id="building" value=""></div>
<div class="field"><label for="flat">квартира</label><input id="flat" value="34"></div>
<label><input type="checkbox" checked> Согласен на обработку данных региона и города проживания</label>
<div class="field"><label for="contactNumber">номер телефона</label><input id="contactNumber" name="contactNumber" placeholder="+7 960 000 00 00" value=""></div>
</form>"""
        class Diag:
            def __init__(self): self.events = []
            def write(self, event, **data): self.events.append((event, data))
        worker = {"success_profile": {"gender": "мужской"}, "diagnostic": Diag()}
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
                page = browser.new_page(); page.set_content(html)
                extended = ns["capture_form_fields_1591r19"](page)
                profile, raw = ns["final_profile_capture_v1583"](page, worker)
                browser.close()
        except Exception as exc:
            self.skipTest(f"chromium not available: {type(exc).__name__}")
        by_value = {f["value"]: f for f in extended if f.get("value")}
        self.assertEqual(by_value["Петров Пётр Петрович"]["near"], "ФИО")
        self.assertEqual(by_value["03.04.1985"]["near"], "Дата рождения")
        self.assertIn("Регион", by_value["Саратовская область"]["near"])
        self.assertEqual(by_value["1234"]["label"], "серия")
        self.assertEqual(profile["full_name"], "Петров Пётр Петрович"); self.assertEqual(profile["birth_date"], "03.04.1985")
        self.assertEqual(profile["passport_issue_date"], "10.10.2010"); self.assertEqual(profile["passport_number"], "567890")
        self.assertEqual(profile["region"], "Саратовская область"); self.assertEqual(profile["locality"], "Саратов")
        self.assertEqual(profile["street"], "Московская"); self.assertNotIn("district", profile)
        self.assertEqual(profile["house"], "12"); self.assertEqual(profile["apartment"], "34")
        self.assertEqual(profile["gender"], "мужской"); self.assertNotIn("true", profile.values())
        self.assertEqual(len(raw), len(extended)); self.assertIn("form_fields_1591r19", [e for e, _ in worker["diagnostic"].events])


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
        with tempfile.TemporaryDirectory() as d:  # PROXY_DIRECT_1591R20: no proxy outside Russia
            app = Path(d) / "app"
            run = self._run(app, DEEPSEEK_API_KEY="k", TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="1", TELEGRAM_PROXY="")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr); self.assertIn("CHECK OK", run.stdout)
            self.assertEqual(json.loads((app / "telegram_config.json").read_text())["proxy"], "direct")
        with tempfile.TemporaryDirectory() as d:
            app = Path(d) / "app"
            run = self._run(app, DEEPSEEK_API_KEY="k", TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="1",
                            TELEGRAM_PROXY="socks5h://u:p@h:1")
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            for name in self.CODE:
                self.assertTrue((app / name).is_file(), name)
            package = max((x for x in Path(__file__).resolve().parent.glob("beeline_integrated_io_15_91_r*")
                           if x.name.rsplit("r", 1)[1].isdigit()),          # the full package, not *_lite
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
