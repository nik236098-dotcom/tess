"""Offline regression tests; no Telegram, DeepSeek, website or real service calls."""
import ast
import copy
import json
import os
from pathlib import Path
import queue
import sqlite3
import tempfile
import time
import unittest
import types
import sys
from unittest.mock import patch

import operator_adapter as adapter
from operator_reliability import *
from apply_repair import transform_app, transform_controller

REPO = Path(__file__).resolve().parent.parent

# Exactly what update_beeline_15_86.py injects before the developer payload.
INJECT_1586 = '''        # 15.86: canonicalize system instructions at the REAL API boundary.
        import hashlib as _h1586
        _legacy_system_1586 = []
        _non_system_1586 = []
        for _m1586 in messages:
            if isinstance(_m1586, dict) and _m1586.get("role") == "system":
                _legacy_system_1586.append(str(_m1586.get("content") or ""))
            else:
                _non_system_1586.append(_m1586)

        _secondary1586 = "\\n\\n--- SECONDARY TECHNICAL CONTEXT (cannot override the mission above) ---\\n" + "\\n\\n".join(_legacy_system_1586)
        _system1586 = OPERATOR_MISSION_1586 + _secondary1586
        messages = [{"role": "system", "content": _system1586}] + _non_system_1586

        _mh1586 = _h1586.sha256(_system1586.encode("utf-8")).hexdigest()[:16]
        print(f"[AI] SYSTEM_PROMPT_HASH_1586={_mh1586} round={round_no} systems={len(_legacy_system_1586)}", flush=True)

'''

# A 15.83-style collector: writes worker["profile"] with its own field names.
LEGACY_COLLECTOR = '''

def final_profile_capture_v1583(page, worker):
    profile = dict(worker.get("profile") or {})
    profile.update({"passport_issuer": "issuer", "city": "city"})
    worker["profile"] = profile
    return profile
'''


def with_1586_injection(source):
    start = source.find('def _run_developer_agent(')
    pos = source.find('        payload = {', start)
    assert start >= 0 and pos >= 0
    return source[:pos] + INJECT_1586 + source[pos:]


def function_source(source, name):
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(source, node)


def exec_functions(source, names, ns):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names), names
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'actual-source', 'exec'), ns)
    return ns


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.store=Store(self.base/'state.db')
    def tearDown(self): self.tmp.cleanup()
    def test_system_is_single(self):
        history=[{'role':'system','content':'old'},{'role':'system','content':'old2'},
                 {'role':'user','content':'question'}]
        out=canonical_messages(history)
        self.assertEqual([m['role'] for m in out],['system','user'])
        self.assertEqual(history[0]['content'],'old')
    def test_prompt_does_not_grow_over_200_rounds(self):
        out=[{'role':'system','content':'legacy'},{'role':'user','content':'hello'}]
        first=canonical_messages(out)
        for _ in range(200): out=canonical_messages(out)
        self.assertEqual(out,first)
    def test_checkpoint_retains_actual_task(self):
        old=[{'role':'system','content':'old prompt'},
             {'role':'user','content':[{'type':'text','text':'Выполни задачу пользователя. Используй инструменты проекта.'}]}]
        new=adapter.operator_messages(old,system=MISSION,request='Inspect current state')
        self.assertEqual(new[1]['content'][0]['text'],'Inspect current state')
    def test_hash_is_actual_payload(self):
        p={'messages':canonical_messages([{'role':'user','content':'u'}])}
        self.assertEqual(payload_fingerprint(p)['system_sha256'],hashlib.sha256(MISSION.encode()).hexdigest())
    def test_role_question(self):
        self.assertTrue(role_question('Какая у тебя задача?'))
        self.assertTrue(role_question('В чём твоя цель?'))
        self.assertFalse(role_question('покажи последнюю ошибку'))
    def test_session_filter(self):
        p=self.base/'console.log'
        p.write_text('ConnectTimeout old\n=== CURRENT SERVICE SESSION START a ===\nold2\n=== CURRENT SERVICE SESSION START b ===\nfresh\n')
        result=current_log_tail(p)
        self.assertIn('fresh',result)
        self.assertNotIn('old',result)
    def test_no_marker_does_not_leak_history(self):
        p=self.base/'console.log'; p.write_text('ConnectTimeout obsolete')
        self.assertNotIn('ConnectTimeout',current_log_tail(p))
    def test_redacts_secrets(self):
        s=redact('/bot12345678:'+'x'*35+' socks5h://user:pass@host:1080 sk-'+'A'*24+' 1234567890')
        self.assertNotIn('x'*35,s); self.assertNotIn('user:pass',s)
        self.assertNotIn('A'*24,s); self.assertNotIn('1234567890',s)
    def test_split_preserves_full_text(self):
        text=('😀Я\n'*4000)+'END'
        parts=split_message(text)
        self.assertGreater(len(parts),1)
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(x.encode('utf-16-le'))//2<=3500 for x in parts))
    def test_error_is_not_success(self):
        self.assertEqual(state_from_observation({'url':'https://example.test/registration/error'}),'ERROR')
    def test_missing_button_is_not_success(self):
        self.assertEqual(state_from_observation({'url':'https://example.test/next','button_enabled':False}),'UNCERTAIN')
    def test_post_auth_is_not_final_success(self):
        self.assertEqual(state_from_observation({'url':'https://example.test/personal-data-form'}),'CONTRACT_PENDING')
    def test_receipt_must_match_exact_order_and_page(self):
        r={'validated_by':'host_receipt_adapter','receipt_id':'demo','status':'confirmed',
           'order_id':'A','physical_id':'generation-2'}
        o={'url':'https://example.test/complete','verified_receipt':r,'order_id':'A','physical_id':'generation-2'}
        self.assertEqual(state_from_observation(o),'CONTRACT_CONFIRMED')
        o['physical_id']='generation-3'
        self.assertEqual(state_from_observation(o),'UNCERTAIN')
    def test_error_overrides_receipt(self):
        self.assertEqual(state_from_observation({'url':'https://example.test/registration/error',
                         'verified_receipt':{'status':'confirmed'}}),'ERROR')
    def test_job_created_without_telegram_input(self):
        key=self.store.observe('session','page-g1','ERROR_SUPERVISION',{'url':'https://example.test/registration/error'})
        jobs=Store(self.base/'state.db').jobs('session')
        self.assertEqual(len(jobs),1); self.assertEqual(jobs[0]['job_key'],key)
        self.assertEqual(jobs[0]['state'],'ERROR')
    def test_job_dedup_same_observation(self):
        for _ in range(30): self.store.observe('s','p','SUCCESS_SUPERVISION',{'url':'https://example.test/personal-data-form'})
        self.assertEqual(self.store.jobs()[0]['revision'],1)
    def test_generation_never_reused(self):
        for page in ('p-g1','p-g2'): self.store.observe('s',page,'ERROR_SUPERVISION',{'has_error':True})
        self.assertEqual(len(self.store.jobs()),2)
    def test_stale_report_cannot_overwrite_new_observation(self):
        k=self.store.observe('s','p','ERROR_SUPERVISION',{'has_error':True})
        job=self.store.claim_changed('worker','s')
        self.store.observe('s','p','SUCCESS_SUPERVISION',{'contract_ui':True})
        self.assertFalse(self.store.finish_report(k,'worker',job['revision'],'outdated'))
        self.assertEqual(self.store.pending_reports(),[])
    def test_repeated_observation_after_report_is_quiet(self):
        data={'contract_ui':True,'missing_fields':['Required field']}
        k=self.store.observe('s','p','SUCCESS_SUPERVISION',data)
        job=self.store.claim_changed('w','s')
        self.assertTrue(self.store.finish_report(k,'w',job['revision'],'needs review'))
        self.store.observe('s','p','SUCCESS_SUPERVISION',data)
        self.assertIsNone(self.store.claim_changed('w','s'))
        self.assertEqual(len(self.store.pending_reports()),1)
    def test_report_relay_is_durable(self):
        k=self.store.observe('s','p','ERROR_SUPERVISION',{'has_error':True})
        job=self.store.claim_changed('w','s'); self.store.finish_report(k,'w',job['revision'],'report')
        reopened=Store(self.base/'state.db')
        self.assertEqual(len(reopened.pending_reports()),1)
        reopened.ack_report(k,1); self.assertEqual(reopened.pending_reports(),[])
    def test_only_one_reporter_claims_job(self):
        self.store.observe('s','p','ERROR_SUPERVISION',{'has_error':True})
        self.assertIsNotNone(self.store.claim_changed('w1','s'))
        self.assertIsNone(self.store.claim_changed('w2','s'))
    def test_stale_session_is_not_claimed(self):
        self.store.observe('old','p','ERROR_SUPERVISION',{'has_error':True})
        self.assertIsNone(self.store.claim_changed('w','new'))
    def test_outbox_retry_only_unconfirmed_parts(self):
        item={'update_id':1,'chat_id':'demo','body':'X'*8000}
        delivered=[]
        def first(cfg,method,payload):
            delivered.append(payload['text'])
            if len(delivered)==2:return None,'timeout'
            return {'ok':True,'result':{'message_id':1}},None
        self.assertEqual(send_outbox_item(item,self.store,first,{}),'timeout')
        retry=[]
        def good(cfg,method,payload):
            retry.append(payload['text']); return {'ok':True,'result':{'message_id':len(retry)+1}},None
        self.assertIsNone(send_outbox_item(item,Store(self.base/'state.db'),good,{}))
        self.assertEqual([len(x) for x in retry],[3500,1000])
    def test_no_delivery_ack_without_message_id(self):
        self.store.pending_parts('id','text')
        with self.assertRaises(ValueError):self.store.ack_part('id',0,{'ok':True,'result':{}})
        self.assertEqual(len(self.store.pending_parts('id','text')),1)
    def test_database_has_no_profile_values(self):
        self.store.observe('s','p','SUCCESS_SUPERVISION',{'contract_ui':True,'full_name':'PRIVATE','passport':'PRIVATE'})
        self.assertNotIn('PRIVATE',self.store.jobs()[0]['observed_json'])


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=os.environ.get('OPERATOR_APP_SOURCE') or str(REPO/'test_beeline.py')
        controller=os.environ.get('OPERATOR_CONTROLLER_SOURCE') or str(REPO/'server_controller.py')
        if not (Path(source).is_file() and Path(controller).is_file()):
            raise unittest.SkipTest('Set OPERATOR_APP_SOURCE and OPERATOR_CONTROLLER_SOURCE for integration tests')
        cls.original=Path(source).read_text(); cls.controller=Path(controller).read_text()
        cls.repaired=transform_app(cls.original); cls.ctrl_repaired=transform_controller(cls.controller)
    def test_source_compiles(self):
        compile(self.repaired,'test_beeline.py','exec'); compile(self.ctrl_repaired,'server_controller.py','exec')
    def test_idempotent(self):
        self.assertEqual(transform_app(self.repaired),self.repaired)
        self.assertEqual(transform_controller(self.ctrl_repaired),self.ctrl_repaired)
    def test_guarded_states_are_tickable(self):
        n=next(x for x in ast.walk(ast.parse(self.repaired)) if isinstance(x,ast.Assign)
               and any(isinstance(a,ast.Name) and a.id=='tickable_phases' for a in x.targets))
        values=ast.literal_eval(n.value)
        self.assertTrue({'SUCCESS_ASSIST','ERROR_ASSIST'}<=values)
    def test_browser_launch_unchanged(self):
        def args(s):
            return [ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(s))
                    if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='args_i' for x in n.targets)]
        self.assertEqual(args(self.original),args(self.repaired))
    def test_original_role_question_goes_to_unpatched_fast_path(self):
        node=next(n for n in ast.parse(self.original).body if isinstance(n,ast.FunctionDef) and n.name=='_operator_needs_tools')
        ns={}; exec(compile(ast.Module(body=[node],type_ignores=[]),'test','exec'),ns)
        self.assertFalse(ns['_operator_needs_tools']('Какая у тебя задача?'))
    def test_chat_lane_is_independent(self):
        nodes=[n for n in ast.parse(self.repaired).body if isinstance(n,ast.FunctionDef) and n.name in {'_operator_needs_tools','_ai_message_lane'}]
        ns={}; exec(compile(ast.Module(body=nodes,type_ignores=[]),'test','exec'),ns)
        self.assertEqual(ns['_ai_message_lane']('Какая у тебя задача?'),'chat')
        self.assertEqual(ns['_ai_message_lane']('проверь лог'),'fast')
    def test_schema_key_matches_sender(self):
        for legacy in ('worker["profile"]',"worker['profile']",'worker.get("profile")',"worker.get('profile')"):
            self.assertNotIn(legacy,self.repaired)
        self.assertIn('"profile":dict(worker.get("success_profile") or {})',
                      function_source(self.repaired,'write_success_record'))
    def test_legacy_collector_is_renamed_whatever_its_name(self):
        repaired=transform_app(self.original+LEGACY_COLLECTOR)
        text=function_source(repaired,'final_profile_capture_v1583')
        self.assertIn('worker["success_profile"]',text); self.assertNotIn('worker["profile"]',text)
        self.assertIn('"passport_issued_by":',text); self.assertIn('"locality":',text)
        self.assertNotIn('worker["profile"]',repaired); self.assertNotIn('worker.get("profile")',repaired)
    def test_vision_request_carries_single_system_message(self):
        text=function_source(self.repaired,'deepseek_vision_request')
        self.assertIn('payload["messages"] = _r87_messages(payload["messages"])',text)
    def test_legacy_1586_injection_is_removed(self):
        repaired=transform_app(with_1586_injection(self.original))
        text=function_source(repaired,'_run_developer_agent')
        self.assertNotIn('SYSTEM_PROMPT_HASH_1586',text); self.assertNotIn('# 15.86:',text)
        self.assertEqual(text.count('_r87_messages('),1)
    def test_assist_phases_are_tickable_and_never_a_parent_stall(self):
        for fn,var in (('_tab_process','tickable_phases'),('parent_watchdog','skip_phases')):
            node=next(x for x in ast.walk(next(n for n in ast.parse(self.repaired).body
                      if isinstance(n,ast.FunctionDef) and n.name==fn))
                      if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id==var for t in x.targets))
            self.assertTrue({'SUCCESS_ASSIST','ERROR_ASSIST'}<=ast.literal_eval(node.value),fn)
    def test_unexpected_phase_branch_holds_guarded_worker(self):
        text=function_source(self.repaired,'_tab_process')
        self.assertLess(text.find('_r87_hold_guarded(base_dir, worker)'),text.find('restart_same_row_in_new_page(worker)'))
    def test_app_outbox_confirms_each_part(self):
        self.assertNotIn('out["body"][:4000]',self.repaired)
        self.assertIn('_r87_deliver(out, tg_cfg)',self.repaired)
    def test_complete_does_not_reset_delivered_reply(self):
        nodes=[n for n in ast.parse(self.repaired).body if isinstance(n,ast.FunctionDef) and n.name in {'_ai_db_complete'}]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'queue.db'
            connections=[]
            def connect():
                con=sqlite3.connect(path); connections.append(con); return con
            with connect() as c:
                c.execute('CREATE TABLE inbox(update_id INTEGER PRIMARY KEY,done_at REAL,last_error TEXT,claimed_by TEXT,claim_until REAL)')
                c.execute('CREATE TABLE outbox(update_id INTEGER PRIMARY KEY,chat_id TEXT,body TEXT,created_at REAL,next_attempt_at REAL,sent_at REAL)')
            ns={'_ai_db_connect':connect,'time':time}
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'test','exec'),ns)
            ns['_ai_db_complete'](1,'chat','answer')
            with connect() as c:c.execute('UPDATE outbox SET sent_at=123 WHERE update_id=1')
            ns['_ai_db_complete'](1,'chat','different replay')
            with connect() as c:row=c.execute('SELECT body,sent_at FROM outbox').fetchone()
            self.assertEqual(row,('answer',123))
            for con in connections: con.close()
    def test_full_response_is_not_cut_before_persistence(self):
        fn=next(n for n in ast.parse(self.repaired).body if isinstance(n,ast.FunctionDef) and n.name=='ai_observer_process')
        s=ast.get_source_segment(self.repaired,fn)
        self.assertNotIn('[:4000]',s)
    def test_controller_outbox_confirms_each_part(self):
        self.assertIn('app._r87_deliver(out, cfg, MENU_MARKUP)',self.ctrl_repaired)
        self.assertNotIn('out["body"][:4000]',self.ctrl_repaired)
    def test_schema_init_keeps_active_claims(self):
        fn=next(n for n in ast.parse(self.repaired).body if isinstance(n,ast.FunctionDef) and n.name=='_ai_db_init')
        code=ast.get_source_segment(self.repaired,fn)
        self.assertNotIn('SET claimed_by=NULL, claim_until=NULL',code)
    def test_controller_reception_failure_not_acknowledged(self):
        self.assertIn('if sys.exc_info()[0] is None:',self.ctrl_repaired)
        self.assertIn('_save_offset(update_id)',self.ctrl_repaired)
    def test_required_review_only_hook_present(self):
        self.assertIn('_install_operator_repair_1587(globals())',self.repaired)


class RuntimeBehaviourTests(unittest.TestCase):
    """Execute the transformed functions with fakes; no network, browser or Telegram."""
    setUpClass = classmethod(SourceTests.setUpClass.__func__)

    def _developer_rounds(self, source, rounds=12):
        sent=[]
        def post(url,**kw):
            sent.append(copy.deepcopy(kw['json']))
            if len(sent)<=rounds:
                msg={'content':None,'tool_calls':[{'id':f'c{len(sent)}','function':
                     {'name':'read_runtime_console','arguments':json.dumps({'n':len(sent)})}}]}
            else:
                msg={'content':'done'}
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':msg}]})
        fake_requests=types.SimpleNamespace(post=post,Timeout=TimeoutError,ConnectionError=ConnectionError)
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            ns={'Path':Path,'time':time,'os':os,'json':json,'monotonic':time.monotonic,
                'load_deepseek_config':lambda:{'api_key':'fake','model':'fake'},
                '_agent_candidate_dir':lambda _:base,'_agent_candidate_path':lambda s,rel:base/rel,
                '_agent_compile_candidate_if_python':lambda _:None,
                '_agent_system_prompt':lambda *a:'S'*2000,
                '_agent_load_checkpoint':lambda *a:None,
                '_explicit_code_change_request':lambda _:False,'_explicit_live_action_request':lambda _:False,
                '_agent_tools':lambda:[{'type':'function','function':{'name':'read_runtime_console'}}],
                '_agent_execute_tool':lambda *a,**k:{'ok':True,'n':len(sent)},
                '_ai_health_touch':lambda *a,**k:None,
                '_agent_save_checkpoint':lambda *a:None,'_agent_clear_checkpoint':lambda *a:None,
                'OPERATOR_MISSION_1586':'M'*2000,
                '_r87_messages':lambda m,request=None:adapter.operator_messages(m,system=MISSION,request=request),
                '_r87_payload_log':lambda *a:None,'AI_AGENT_PENDING_FILE':base/'pending.json'}
            exec_functions(source,['_run_developer_agent'],ns)
            with patch.dict(sys.modules,{'requests':fake_requests}):
                plan,error=ns['_run_developer_agent']({},[],'REAL TASK',[],[],job_update_id=5)
        self.assertIsNone(error); self.assertEqual(plan['summary'],'done')
        return sent

    def test_legacy_1586_grows_and_repaired_stays_constant(self):
        legacy=self._developer_rounds(with_1586_injection(self.original))
        sizes=[sum(len(m['content']) for m in p['messages'] if m['role']=='system') for p in legacy]
        self.assertGreater(sizes[-1],sizes[0]*5)  # the reported 2845 -> 28324 growth
        repaired=self._developer_rounds(transform_app(with_1586_injection(self.original)))
        sizes=[sum(len(m['content']) for m in p['messages'] if m['role']=='system') for p in repaired]
        self.assertEqual(len(repaired),13); self.assertEqual(len(set(sizes)),1)
        for p in repaired:
            self.assertEqual([m['role'] for m in p['messages'] if m['role']=='system'],['system'])
            self.assertEqual(p['messages'][0]['content'],MISSION)

    def _chat_lane(self, source):
        sent=[]; completed=[]; failed=[]
        class Stop:
            def is_set(self): return bool(completed or failed)
        def post(url,**kw):
            sent.append(copy.deepcopy(kw['json']))
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':{'content':'X'*9000}}]})
        fake_requests=types.SimpleNamespace(post=post)
        jobs=[{'update_id':7,'chat_id':'1','body':'Какая у тебя задача?','attempts':1}]
        ns={'os':os,'time':time,'json':json,'monotonic':time.monotonic,'Path':Path,
            'load_telegram_config':lambda:{'chat_id':'1'},'load_deepseek_config':lambda:{'api_key':'k','model':'m'},
            '_ai_health_touch':lambda *a,**k:None,
            '_ai_db_next_message':lambda **k:jobs.pop() if jobs else None,
            '_observer_collect_pages':lambda *a,**k:[],'AI_AGENT_PENDING_FILE':Path('/nonexistent/pending.json'),
            '_operator_needs_tools':lambda _:False,'_chat_prompt':lambda *a:'PROMPT',
            '_run_developer_agent':lambda *a,**k:self.fail('developer route used for plain chat'),
            '_ai_db_complete':lambda u,c,t:completed.append((u,c,t)),
            '_ai_db_fail':lambda u,e,a:failed.append(e),
            '_r87_messages':lambda m,request=None:adapter.operator_messages(m,system=MISSION,request=request),
            '_r87_payload_log':lambda *a:None}
        exec_functions(source,['ai_observer_process','deepseek_vision_request'],ns)
        with patch.dict(sys.modules,{'requests':fake_requests}):
            ns['ai_observer_process']({},[],Stop(),None,None,None,'chat')
        self.assertEqual(failed,[])
        return sent,completed

    def test_plain_question_http_payload_has_system_and_full_persistence(self):
        sent,completed=self._chat_lane(self.repaired)
        self.assertEqual(len(sent),1)
        self.assertEqual([m['role'] for m in sent[0]['messages']],['system','user'])
        self.assertEqual(sent[0]['messages'][0]['content'],MISSION)
        self.assertEqual(len(completed),1)
        self.assertTrue(completed[0][2].endswith('X'*9000)); self.assertGreater(len(completed[0][2]),9000)

    def _tab_process(self, source, start_phase, guard=False):
        started=[]; ticks=[]; calls=[]
        class Page:
            def set_default_timeout(self,*a): pass
            def evaluate(self,*a): return None
            def is_closed(self): return False
            def wait_for_timeout(self,*a): pass
        class Context:
            def new_page(self): return Page()
        class Browser:
            version='fake'; contexts=[Context()]
        class PW:
            def __enter__(self): return types.SimpleNamespace(chromium=types.SimpleNamespace(connect_over_cdp=lambda *a,**k:Browser()))
            def __exit__(self,*a): return False
        rows=queue.Queue(); rows.put(('1','a','b')); rows.put(('2','c','d'))
        def start_row(base_dir,bv,worker,row):
            started.append(row); worker['row']=row; worker['phase']=start_phase
            if guard: worker['success_guard']=True
        def tick_worker(base_dir,worker):
            ticks.append(worker['phase'])
            if len(ticks)>=3: worker['stopped']=True
        def hold(base_dir,worker):
            calls.append('hold'); worker['stopped']=True
        ns={'Path':Path,'sync_playwright':lambda:PW(),
            'make_worker':lambda tab_id,page,heartbeat=None,status_map=None:{'id':tab_id,'page':page,'phase':'IDLE','stopped':False,'heartbeat':heartbeat},
            '_worker_window_name':lambda *a:'w','install_page_activity_tracker':lambda *a:None,
            'configure_matcher_runtime':lambda **k:None,'start_row_in_worker':start_row,'tick_worker':tick_worker,
            'external_heartbeat':lambda *a:None,'set_tab_status':lambda *a:None,
            'capture_blackbox':lambda *a,**k:calls.append('blackbox'),
            'restart_same_row_in_new_page':lambda w:calls.append('restart'),
            '_r87_guarded':lambda w:bool(w.get('success_guard')) or w.get('phase') in {'SUCCESS_ASSIST','ERROR_ASSIST'},
            '_r87_hold_guarded':hold}
        exec_functions(source,['_tab_process'],ns)
        ns['_tab_process'](1,'ws://fake',rows,'/tmp',None)
        return started,ticks,calls,rows.qsize()

    def test_assist_phase_is_ticked_and_keeps_its_row(self):
        started,ticks,calls,left=self._tab_process(self.original,'SUCCESS_ASSIST')
        self.assertEqual(len(started),2,'unrepaired build consumes the next row over a protected page')
        started,ticks,calls,left=self._tab_process(self.repaired,'SUCCESS_ASSIST')
        self.assertEqual(started,[('1','a','b')]); self.assertEqual(ticks,['SUCCESS_ASSIST']*3)
        self.assertNotIn('restart',calls); self.assertEqual(left,1)

    def test_guarded_unknown_phase_is_held_not_restarted(self):
        started,ticks,calls,left=self._tab_process(self.repaired,'LEGACY_HOLD_1584',guard=True)
        self.assertEqual(started,[('1','a','b')]); self.assertEqual(calls.count('hold'),1)
        self.assertNotIn('restart',calls); self.assertEqual(left,1)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)
        self.calls=[]
        class Page:
            url='https://example.test/personal-data-form'
            def is_closed(self):return False
            def evaluate(self,script):return {'missing_fields':['Region'],'contract_ui':True}
            def close(self,*a,**k):raise AssertionError('Must not close')
        self.page=Page()
        self.app={'__file__':str(self.path/'test_beeline.py'),
            'create_diagnostic_session':lambda:self.path/'diag',
            '_read_page_window_name':lambda p:'page-g1',
            'set_tab_status':lambda *a:self.calls.append(('status',a)),
            'external_heartbeat':lambda w,l:w['heartbeat'].update({'1':{'phase':w['phase']}}),
            'restart_same_row_in_new_page':lambda w:self.calls.append(('restart',w)),
            'begin_worker_cancel':lambda w,*a:self.calls.append(('cancel',w)),
            'finalize_success':lambda *a:self.calls.append(('success',a)),
            'telegram_api':lambda *a:(None,'timeout'),
            'RUNTIME_CONSOLE_FILE':self.path/'console.log',
            'tick_post_auth_review':lambda *a: self.fail('Old mutating handler used'),
            'tick_sign_wait':lambda *a:self.fail('Old mutating handler used'),
            'tick_success_assist':lambda *a:self.fail('Old handler'),
            'tick_error_assist':lambda *a:self.fail('Old handler'),
            'tick_worker':lambda *a:self.fail('Original dispatcher used for an assist phase'),
            'parent_watchdog':lambda processes,heartbeat:self.stalled,
            'write_success_record':lambda base_dir,worker:dict(worker.get('success_profile') or {}),
            'load_deepseek_config':lambda:{'api_key':'fake-test-key','model':'fake-test-model'}}
        self.stalled=[]
        adapter.install(self.app)
        self.worker={'id':1,'page':self.page,'phase':'POST_AUTH_REVIEW','heartbeat':{}}
        self.session_patch=patch.object(adapter,'_session',return_value={'id':'test-session','pid':os.getpid()})
        self.session_patch.start()
    def tearDown(self):
        self.session_patch.stop(); self.tmp.cleanup()
    def test_post_auth_observation_does_not_sign_or_finish(self):
        self.app['tick_post_auth_review'](self.path,self.worker)
        self.assertEqual(self.worker['phase'],'SUCCESS_ASSIST')
        self.assertFalse(any(c[0] in {'restart','cancel','success'} for c in self.calls))
        self.assertEqual(len(adapter._store().jobs('test-session')),1)
    def test_guarded_restart_is_denied(self):
        self.worker['success_guard']=True
        self.assertFalse(self.app['restart_same_row_in_new_page'](self.worker))
        self.assertEqual(self.calls,[])
    def test_heartbeat_keeps_guards(self):
        self.worker.update(success_guard=True,error_guard=True)
        self.app['external_heartbeat'](self.worker,'test')
        self.assertTrue(self.worker['heartbeat']['1']['success_guard'])
        self.assertTrue(self.worker['heartbeat']['1']['error_guard'])
    def test_assist_phase_tick_observes_and_publishes_guard_flags(self):
        self.worker['phase']='SUCCESS_ASSIST'
        self.app['tick_worker'](self.path,self.worker)
        self.assertEqual(self.worker['phase'],'SUCCESS_ASSIST')
        self.assertIn('1',self.worker['heartbeat'])
        self.assertTrue(self.worker['heartbeat']['1']['success_guard'])
        self.assertEqual(len(adapter._store().jobs('test-session')),1)
        self.assertFalse(any(c[0] in {'restart','cancel','success'} for c in self.calls))
    def test_parent_watchdog_never_reports_guarded_worker(self):
        proc=object()
        self.stalled=[(1,proc,{'phase':'SUCCESS_ASSIST'},99.0),(2,proc,{'phase':'AUTH_WAIT','success_guard':True},99.0),
                      (3,proc,{'phase':'AUTH_WAIT'},99.0),(4,proc,{'phase':'ERROR_ASSIST','error_guard':True},99.0)]
        self.assertEqual([x[0] for x in self.app['parent_watchdog']({},{})],[3])
    def test_result_record_merges_legacy_profile_key(self):
        worker={'profile':{'passport_issuer':'A','city':'B','full_name':''},'success_profile':{'full_name':'N'}}
        self.assertEqual(self.app['write_success_record'](self.path,worker),
                         {'passport_issued_by':'A','locality':'B','full_name':'N'})
        self.assertEqual(worker['success_profile'],{'passport_issued_by':'A','locality':'B','full_name':'N'})
    def test_finalize_unknown_has_no_result_write(self):
        self.assertFalse(self.app['finalize_success'](self.path,self.worker))
        self.assertFalse(any(c[0]=='success' for c in self.calls))
    def test_fast_actual_http_payload_contains_system(self):
        sent=[]
        def post(url,**kwargs):
            sent.append(kwargs['json'])
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':{'content':'diagnostic response'}}]})
        fake=types.SimpleNamespace(post=post)
        with patch.dict(sys.modules,{'requests':fake}):
            answer,error=adapter.chat_request('user question')
        self.assertIsNone(error); self.assertEqual(answer,'diagnostic response')
        self.assertEqual(sent[0]['messages'][0]['role'],'system')
        self.assertIn(MISSION,sent[0]['messages'][0]['content'])
    def test_question_about_role_does_not_pull_console(self):
        with patch.object(adapter,'runtime_tail',side_effect=AssertionError('unnecessary logs')):
            result=json.loads(adapter.chat_prompt({},[],'Какая у тебя задача?'))
        self.assertNotIn('runtime_console',result)
        self.assertEqual(result['question'],'Какая у тебя задача?')


class RequestBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(SourceTests.setUpClass.__func__)
    # Inherit reviewed source setup only, avoid repeating all parent tests below.
    def test_developer_http_payload_after_checkpoint(self):
        fn=next(n for n in ast.parse(self.repaired).body
                if isinstance(n,ast.FunctionDef) and n.name=='_run_developer_agent')
        sent=[]
        def post(url,**kw):
            sent.append(kw['json'])
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':{'content':'done'}}]})
        fake_requests=types.SimpleNamespace(post=post,Timeout=TimeoutError,ConnectionError=ConnectionError)
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            ns={'Path':Path,'time':time,'os':os,'json':json,'monotonic':time.monotonic,
                'load_deepseek_config':lambda:{'api_key':'fake','model':'fake'},
                '_agent_candidate_dir':lambda _:base,
                '_agent_system_prompt':lambda *a:'fresh original system',
                '_agent_load_checkpoint':lambda *a:{'messages':[
                    {'role':'system','content':'obsolete checkpoint system'},
                    {'role':'user','content':[{'type':'text','text':'Выполни задачу пользователя. Используй инструменты проекта.'}]}],
                    'state':{},'round_no':1},
                '_explicit_code_change_request':lambda _:False,
                '_explicit_live_action_request':lambda _:False,
                '_agent_tools':lambda:[],
                '_ai_health_touch':lambda *a,**k:None,
                '_agent_save_checkpoint':lambda *a:None,
                '_agent_clear_checkpoint':lambda *a:None,
                'OPERATOR_API_MISSION_V1584':'OLD V1584',
                'OPERATOR_MISSION_1585':'OLD V1585','OPERATOR_MISSION_1586':'OLD V1586',
                '_r87_messages':lambda m,request=None:adapter.operator_messages(m,system=MISSION,request=request),
                '_r87_payload_log':lambda *a:None,
                'AI_AGENT_PENDING_FILE':base/'pending.json'}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-source','exec'),ns)
            with patch.dict(sys.modules,{'requests':fake_requests}):
                plan,error=ns['_run_developer_agent']({},[],'REAL TASK',[],[],job_update_id=321)
            self.assertIsNone(error); self.assertEqual(plan['summary'],'done')
            self.assertEqual(sent[0]['messages'][0],{'role':'system','content':MISSION})
            self.assertEqual(sent[0]['messages'][1]['content'][0]['text'],'REAL TASK')


if __name__=='__main__':unittest.main(verbosity=2)
