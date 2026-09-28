"""Offline regression suite. No application imports, network or service control."""
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from reliability import (Queue, StaleLease, CompletionEvidence, assert_lifecycle_allowed,
    canonical_messages, completion_state, fingerprint, merge_capture, request_payload,
    send_one, session_tail, split_text)


class RequestTests(unittest.TestCase):
    def test_current_system_replaces_checkpoint(self):
        h = [{"role":"system","content":"old"},{"role":"developer","content":"old2"},
             {"role":"user","content":"hello"}]
        self.assertEqual(canonical_messages(h,"current"),[{"role":"system","content":"current"},h[-1]])
    def test_does_not_modify_input(self):
        h=[{"role":"user","content":[{"type":"text","text":"hello"}]}]
        before=copy.deepcopy(h); out=canonical_messages(h,"x")
        out[1]["content"][0]["text"]="changed"
        self.assertEqual(h,before)
    def test_prompt_does_not_grow(self):
        h=[{"role":"user","content":"hello"}]
        first=canonical_messages(h,"fixed")
        for _ in range(200): h=canonical_messages(h,"fixed")
        self.assertEqual(h,first)
    def test_both_request_paths_include_system(self):
        h=[{"role":"user","content":"hello"}]
        for tools in (None,[]):
            self.assertEqual(request_payload("test",h,"fixed",tools=tools)["messages"][0]["role"],"system")
    def test_preserves_tool_call_ids(self):
        h=[{"role":"assistant","content":None,"tool_calls":[{"id":"test1"}]},
           {"role":"tool","tool_call_id":"test1","content":"ok"}]
        self.assertEqual(canonical_messages(h,"s")[1:],h)
    def test_requires_nonempty_system(self):
        with self.assertRaises(ValueError):canonical_messages([]," ")
    def test_rejects_bad_history(self):
        with self.assertRaises(ValueError):canonical_messages(["bad"],"s")
    def test_fingerprint_actual_content(self):
        p=request_payload("test",[],"actual")
        f=fingerprint(p)
        self.assertEqual(f["system_count"],1)
        self.assertEqual(f["system_sha256"],hashlib.sha256(json.dumps(["actual"],ensure_ascii=False).encode()).hexdigest())
        self.assertNotIn("actual",str(f))


class StateTests(unittest.TestCase):
    def test_protected_destructive_actions_denied(self):
        for action in ("close","reload","restart","navigate","back","forward"):
            with self.assertRaises(PermissionError):assert_lifecycle_allowed(action,True)
    def test_unprotected_restart_allowed(self):
        assert_lifecycle_allowed("restart",False)
    def test_observation_allowed(self):
        assert_lifecycle_allowed("observe",True)
    def test_error_not_success(self):
        self.assertEqual(completion_state("a",has_error=True),"ERROR")
    def test_no_evidence_not_success(self):
        self.assertEqual(completion_state("a"),"UNCERTAIN")
    def test_wrong_operation_not_success(self):
        self.assertEqual(completion_state("a",evidence=CompletionEvidence("b","r",True)),"UNCERTAIN")
    def test_untrusted_evidence_not_success(self):
        self.assertEqual(completion_state("a",evidence=CompletionEvidence("a","r",False)),"UNCERTAIN")
    def test_error_overrides_receipt(self):
        self.assertEqual(completion_state("a",has_error=True,evidence=CompletionEvidence("a","r",True)),"ERROR")
    def test_correlated_evidence(self):
        self.assertEqual(completion_state("a",evidence=CompletionEvidence("a","r",True)),"CONFIRMED")
    def test_merge_preserves_values(self):
        before={"count":0,"flag":False,"name":"old","empty":""}
        got=merge_capture(before,{"count":7,"flag":True,"name":"new","empty":"filled"})
        self.assertEqual(got,{"count":0,"flag":False,"name":"old","empty":"filled"})
    def test_merge_explicit_alias_only(self):
        self.assertEqual(merge_capture({}, {"short":"v"},{"short":"canonical"}),{"canonical":"v"})
    def test_merge_does_not_invent_values(self):
        self.assertEqual(merge_capture({}, {"missing":None,"blank":" "}),{})
    def test_session_excludes_past_and_future(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"log"
            p.write_text("old\n=== SESSION a ===\ncurrent\n=== SESSION b ===\nfuture\n")
            self.assertEqual(session_tail(p,"a"),"current")
    def test_missing_session_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"log";p.write_text("historical failure")
            self.assertEqual(session_tail(p,"a"),"CURRENT_SESSION_UNAVAILABLE")


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"new.sqlite"
        self.now=100.0;self.q=Queue(self.path,clock=lambda:self.now)
    def tearDown(self):self.tmp.cleanup()
    def test_unicode_complete(self):
        body="🙂Русский текст\r\n"*1000+"END"
        pieces=split_text(body)
        self.assertEqual("".join(pieces),body)
        self.assertTrue(all(len(s.encode("utf-16-le"))//2<=3500 for s in pieces))
    def test_empty_or_bad_surrogate_rejected(self):
        for text in (" ","\ud800"):
            with self.assertRaises((ValueError,UnicodeError)):split_text(text)
    def test_ingest_atomic_offset(self):
        self.assertEqual(self.q.ingest([{"update_id":8,"message":"a"},{"update_id":10,"message":"b"}]),11)
        self.assertEqual(self.q.offset(),11)
    def test_bad_batch_does_not_advance(self):
        with self.assertRaises(ValueError):self.q.ingest([{"update_id":1},{"update_id":"bad"}])
        self.assertEqual(self.q.offset(),0)
        with self.q.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM inbound").fetchone()[0],0)
    def test_conflicting_batch_rolls_back(self):
        self.q.ingest([{"update_id":1,"message":"old"}])
        with self.assertRaises(ValueError):self.q.ingest([{"update_id":2},{"update_id":1,"message":"new"}])
        self.assertEqual(self.q.offset(),2)
        with self.q.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM inbound").fetchone()[0],1)
    def test_duplicate_inbound_keeps_offset(self):
        update={"update_id":1}
        self.q.ingest([update]);self.q.ingest([update])
        self.assertEqual(self.q.offset(),2)
    def test_enqueue_whole_answer(self):
        body="a"*9000;self.q.enqueue("x","chat",body)
        with self.q.db() as c:
            self.assertEqual(c.execute("SELECT body FROM messages").fetchone()[0],body)
            self.assertEqual("".join(r[0] for r in c.execute("SELECT text FROM parts ORDER BY n")),body)
    def test_reenqueue_cannot_replace_delivered(self):
        self.q.enqueue("x","chat","hello");p=self.q.claim();self.q.ack(p,{"ok":True,"result":{"message_id":1}})
        self.q.enqueue("x","chat","hello")
        with self.assertRaises(ValueError):self.q.enqueue("x","chat","changed")
        self.assertTrue(self.q.status("x")["delivered"])
    def test_lease_survives_reopen(self):
        self.q.enqueue("x","chat","hello");self.q.claim()
        q2=Queue(self.path,clock=lambda:self.now)
        self.assertIsNone(q2.claim())
    def test_stale_ack_refused(self):
        self.q.enqueue("x","chat","hello");old=self.q.claim(10);self.now+=11;new=self.q.claim()
        with self.assertRaises(StaleLease):self.q.ack(old,{"ok":True,"result":{"message_id":1}})
        self.q.ack(new,{"ok":True,"result":{"message_id":2}})
    def test_concurrent_claims_single_winner(self):
        self.q.enqueue("x","chat","hello")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            claims=list(pool.map(lambda _:self.q.claim(),range(4)))
        self.assertEqual(sum(p is not None for p in claims),1)
    def test_missing_message_id_retained(self):
        self.q.enqueue("x","chat","hello")
        self.assertEqual(send_one(self.q,lambda _: {"ok":True,"result":{}}),"retry")
        self.assertFalse(self.q.status("x")["delivered"])
    def test_bool_message_id_not_accepted(self):
        self.q.enqueue("x","chat","hello");p=self.q.claim()
        with self.assertRaises(ValueError):self.q.ack(p,{"ok":True,"result":{"message_id":True}})
    def test_network_failure_retry(self):
        self.q.enqueue("x","chat","hello")
        def fail(_):raise TimeoutError("secret URL")
        self.assertEqual(send_one(self.q,fail),"retry")
        self.assertIsNone(self.q.claim());self.now+=2
        self.assertIsNotNone(self.q.claim())
        self.assertNotIn("secret",str(self.q.status("x")))
    def test_rate_limit_respected(self):
        self.q.enqueue("x","chat","hello")
        send_one(self.q,lambda _: {"ok":False,"error_code":429,"parameters":{"retry_after":60}})
        self.now+=59;self.assertIsNone(self.q.claim());self.now+=1;self.assertIsNotNone(self.q.claim())
    def test_permanent_error_retained_for_repair(self):
        self.q.enqueue("x","chat","hello")
        self.assertEqual(send_one(self.q,lambda _: {"ok":False,"error_code":403}),"blocked")
        self.now+=1000;self.assertIsNone(self.q.claim())
        self.q.unblock("x");self.assertIsNotNone(self.q.claim())
    def test_multipart_ack_resume(self):
        body="a"*8000;self.q.enqueue("x","chat",body);sent=[]
        def good(payload):
            sent.append(payload["text"]);return {"ok":True,"result":{"message_id":len(sent)}}
        send_one(self.q,good)
        self.assertFalse(self.q.status("x")["delivered"])
        q2=Queue(self.path,clock=lambda:self.now)
        send_one(q2,good);send_one(q2,good)
        self.assertEqual("".join(sent),body);self.assertTrue(q2.status("x")["delivered"])
    def test_next_part_waits_for_previous_ack(self):
        self.q.enqueue("x","chat","a"*8000);self.q.claim()
        self.assertIsNone(self.q.claim())
    def test_bad_retry_delay_preserves_lease(self):
        self.q.enqueue("x","chat","hello");part=self.q.claim()
        with self.assertRaises(ValueError):self.q.fail(part,"bad",retry_after=float("nan"))
        self.q.ack(part,{"ok":True,"result":{"message_id":1}})
    def test_secrets_not_saved_as_error(self):
        self.q.enqueue("x","chat","hello");part=self.q.claim()
        self.q.fail(part,"https://secret:test@example.test")
        self.assertNotIn("secret",str(self.q.status("x")))
    def test_refuses_existing_foreign_database(self):
        other=self.path.with_name("foreign.sqlite")
        c=sqlite3.connect(other);c.execute("CREATE TABLE foreign_data(x)");c.commit();c.close()
        before=other.read_bytes()
        with self.assertRaises(ValueError):Queue(other)
        self.assertEqual(other.read_bytes(),before)
    def test_stale_failure_does_not_change_new_claim(self):
        self.q.enqueue("x","chat","hello");old=self.q.claim(5);self.now+=6;new=self.q.claim()
        with self.assertRaises(StaleLease):self.q.fail(old,"timeout")
        self.q.ack(new,{"ok":True,"result":{"message_id":9}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
