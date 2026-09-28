"""Offline regression tests; no Telegram, DeepSeek, website or real service calls."""
import ast
import copy
import json
import os
from pathlib import Path
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
        source=os.environ.get('OPERATOR_APP_SOURCE')
        controller=os.environ.get('OPERATOR_CONTROLLER_SOURCE')
        if not source or not controller: raise unittest.SkipTest('Set OPERATOR_APP_SOURCE and OPERATOR_CONTROLLER_SOURCE for integration tests')
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
        fn=next(n for n in ast.parse(self.repaired).body if isinstance(n,ast.FunctionDef) and n.name=='final_profile_capture_v1583')
        text=ast.get_source_segment(self.repaired,fn)
        self.assertIn('worker["success_profile"]',text)
        self.assertNotIn('worker["profile"]',text)
        self.assertIn('"passport_issued_by":',text); self.assertIn('"locality":',text)
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
            'load_deepseek_config':lambda:{'api_key':'fake-test-key','model':'fake-test-model'}}
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
