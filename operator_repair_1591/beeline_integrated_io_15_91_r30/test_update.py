"""Offline integration/regression tests. No real website, API or service is used."""
from __future__ import annotations
import ast
from contextlib import redirect_stdout, redirect_stderr
import copy
import hashlib
import importlib.util
import io as stdio
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import operator_runtime_io as rt
import install

BASE = Path(__file__).resolve().parent
SOURCE = (BASE/'test_beeline.py').read_text('utf-8')
CONTROL = (BASE/'server_controller.py').read_text('utf-8')
MANIFEST = json.loads((BASE/'manifest.json').read_text('utf-8'))
TREE = ast.parse(SOURCE)


def function(name, source=SOURCE):
    found = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1: raise AssertionError((name,len(found)))
    return found[0]


def extract(names, ns, source=SOURCE):
    nodes = [n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]), '<actual patched functions>', 'exec'), ns)
    return ns


class ClosedConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


def connection(path):
    return sqlite3.connect(str(path),timeout=3,factory=ClosedConnection)


class FakePage:
    url = 'https://example.test/form'
    closed = False
    def __init__(self): self.mutations=[]
    def is_closed(self): return self.closed
    def close(self, *a, **kw): self.mutations.append('close'); self.closed=True
    def evaluate(self, *a): return 'fixture-page'
    def set_default_timeout(self,*a): pass
    def wait_for_timeout(self,*a): pass



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


class SourceIntegrityTests(unittest.TestCase):
    def test_exact_payload_hashes(self):
        for name,meta in MANIFEST['files'].items():
            self.assertEqual(hashlib.sha256((BASE/name).read_bytes()).hexdigest(),meta['output_sha256'])
    def test_python310_syntax_and_compile(self):
        for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py','install.py','symbol_matching.py'):
            text=(BASE/name).read_text();ast.parse(text,feature_version=(3,10));compile(text,name,'exec')
    def test_browser_contract_captcha_handlers_unchanged(self):
        for name,expected in MANIFEST['preserved_ast_sha256'].items():
            actual=handler_hash(function(name))
            self.assertEqual(actual,expected,name)
    def test_real_calls_not_a_disconnected_library(self):
        self.assertIn('_io1591.canonical_messages(messages, system_prompt, user_text)',SOURCE)
        self.assertIn('_io1591.merge_capture(worker.get("success_profile"), worker.get("profile"))',SOURCE)
        self.assertIn('app._io1591.start_sender(vars(app), cfg, MENU_MARKUP)',CONTROL)
        self.assertIn('app._io1591.enqueue_notice(',CONTROL)
    def test_required_chromium_flags_preserved(self):
        main=function('main')
        args=next(n.value for n in ast.walk(main) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='args_i' for t in n.targets))
        literals=[n.value for n in args.elts if isinstance(n,ast.Constant)]
        self.assertIn('--no-sandbox',literals);self.assertIn('--disable-setuid-sandbox',literals)
    def test_main_version_not_claiming_runtime_tests(self):
        self.assertIn('IO_BUILD_VERSION = "15.91-io"',SOURCE)
        self.assertIn('IO_BUILD_VERSION = "15.91-io"',CONTROL)

    def test_complete_modules_import_and_link_without_starting_browser(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d)
            for name in ('test_beeline.py','server_controller.py','operator_runtime_io.py'):
                (stage/name).write_bytes((BASE/name).read_bytes())
            def forbidden(*a,**k):raise AssertionError('Import must not perform runtime/network/browser actions')
            cw=types.ModuleType('console_wait');cw.console_input=forbidden
            lm=types.ModuleType('local_matcher');lm.try_local_captcha=forbidden;lm.configure_matcher_runtime=forbidden
            bs=types.ModuleType('batch_support');bs.load_clients=forbidden;bs.wait_confirmation=forbidden;bs.save_result=forbidden
            pw=types.ModuleType('playwright');ps=types.ModuleType('playwright.sync_api')
            ps.sync_playwright=forbidden;ps.expect=forbidden;ps.TimeoutError=TimeoutError;ps.Error=RuntimeError
            rq=types.ModuleType('requests');rq.get=forbidden;rq.post=forbidden
            modules={'console_wait':cw,'local_matcher':lm,'batch_support':bs,'playwright':pw,
                     'playwright.sync_api':ps,'requests':rq}
            out,err=sys.stdout,sys.stderr
            try:
                with patch.dict(sys.modules,modules):
                    spec=importlib.util.spec_from_file_location('test_beeline',stage/'test_beeline.py')
                    app=importlib.util.module_from_spec(spec)
                    with patch.dict(sys.modules,{'test_beeline':app}):
                        spec.loader.exec_module(app)
                        spec2=importlib.util.spec_from_file_location('fixture_controller',stage/'server_controller.py')
                        ctrl=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(ctrl)
                        self.assertIs(ctrl.app,app)
                        self.assertEqual(ctrl.IO_BUILD_VERSION,app._io1591.VERSION)
            finally:
                sys.stdout,sys.stderr=out,err


class PromptTests(unittest.TestCase):
    def test_single_current_system(self):
        old=[{'role':'system','content':'old'},{'role':'developer','content':'old2'}, {'role':'user','content':'hello'}]
        self.assertEqual(rt.canonical_messages(old,'new'),[{'role':'system','content':'new'},old[2]])
    def test_deep_copy_does_not_mutate_checkpoint(self):
        old=[{'role':'user','content':[{'type':'text','text':rt.GENERIC_TASK}]}]
        original=copy.deepcopy(old)
        rt.canonical_messages(old,'new','real task')
        self.assertEqual(old,original)
    def test_request_restored_after_checkpoint(self):
        old=[{'role':'system','content':'task incorrectly stored here'}, {'role':'user','content':[{'type':'text','text':rt.GENERIC_TASK}]}]
        self.assertEqual(rt.canonical_messages(old,'new','real task')[1]['content'][0]['text'],'real task')
    def test_no_recursive_growth(self):
        msg=[{'role':'system','content':'old'}]
        first=rt.canonical_messages(msg,'current','question')
        for _ in range(100):msg=rt.canonical_messages(msg,'current','question')
        self.assertEqual(msg,first)
    def test_tools_images_and_reasoning_history_preserved(self):
        history=[{'role':'assistant','content':None,'reasoning_content':'test','tool_calls':[{'id':'abc'}]},
                 {'role':'tool','tool_call_id':'abc','content':'result'},
                 {'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,AA=='}}]}]
        self.assertEqual(rt.canonical_messages(history,'system')[1:],history)
    def test_no_empty_system(self):
        with self.assertRaises(ValueError):rt.canonical_messages([],'')
    def test_installed_priority_is_reused_not_rewritten(self):
        ns={'_agent_system_prompt':lambda *a:'context', 'OPERATOR_MISSION_1586':'existing priority'}
        self.assertEqual(rt.build_system(ns,{},[],'question'),'existing priority\n\ncontext')
    def test_role_question_excludes_old_console(self):
        ns={'_agent_system_prompt':lambda *a:'rules\nПОСЛЕДНИЕ СТРОКИ PYTHON-КОНСОЛИ:\nold error'}
        self.assertNotIn('old error',rt.build_system(ns,{},[],'Какая у тебя задача?'))
    def test_old_chat_role_text_not_inserted(self):
        ns={'_chat_memory_tail':lambda:'old reply'}
        ctx=json.loads(rt.chat_context(ns,{},[],'Какая у тебя задача?'))
        self.assertEqual(ctx,{'message':'Какая у тебя задача?'})
    def test_actual_chat_http_payload_with_images(self):
        sent=[]
        def post(url,**kw):
            sent.append(copy.deepcopy(kw['json']))
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':{'content':'answer'},'finish_reason':'stop'}]})
        ns={'load_deepseek_config':lambda:{'api_key':'OFFLINE','model':'mock'},'_io1591':rt}
        extract({'deepseek_vision_request'},ns)
        with patch.dict(sys.modules,{'requests':types.SimpleNamespace(post=post)}):
            text,error=ns['deepseek_vision_request']('question',[b'fixture'],system_prompt='CURRENT')
        self.assertIsNone(error);self.assertEqual(text,'answer')
        self.assertEqual(sent[0]['messages'][0],{'role':'system','content':'CURRENT'})
        self.assertEqual(sent[0]['messages'][1]['content'][1]['type'],'image_url')
    def test_api_length_limit_is_not_hidden(self):
        def post(url,**kw):
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':{'content':'partial'},'finish_reason':'length'}]})
        ns={'load_deepseek_config':lambda:{'api_key':'OFFLINE'},'_io1591':rt};extract({'deepseek_vision_request'},ns)
        with patch.dict(sys.modules,{'requests':types.SimpleNamespace(post=post)}):
            text,error=ns['deepseek_vision_request']('q',system_prompt='s')
        self.assertIn('ограничил длину',text);self.assertIsNone(error)
    def test_actual_tools_payload_checkpoint_and_three_rounds(self):
        sent=[]
        def post(url,**kw):
            sent.append(copy.deepcopy(kw['json']))
            if len(sent)<3:
                msg={'content':None,'tool_calls':[{'id':str(len(sent)),'function':{'name':'get_page_state','arguments':'{"tab":1}'}}]}
            else:msg={'content':'done'}
            return types.SimpleNamespace(ok=True,json=lambda:{'choices':[{'message':msg}]})
        with tempfile.TemporaryDirectory() as d:
            ns={'Path':Path,'time':time,'os':os,'json':json,'monotonic':time.monotonic,'_io1591':rt,
                'load_deepseek_config':lambda:{'api_key':'OFFLINE'},
                '_agent_candidate_dir':lambda _:Path(d),'_agent_system_prompt':lambda *a:'fresh rules',
                'OPERATOR_MISSION_1586':'installed priority',
                '_agent_load_checkpoint':lambda *a:{'messages':[{'role':'system','content':'outdated'}, {'role':'user','content':[{'type':'text','text':rt.GENERIC_TASK}]}], 'state':{},'round_no':3},
                '_explicit_code_change_request':lambda _:False,'_explicit_live_action_request':lambda _:False,
                '_agent_tools':lambda:[{'type':'function','function':{'name':'get_page_state'}}],
                '_agent_execute_tool':lambda *a,**kw:{'ok':True,'state':'fixture'},
                '_ai_health_touch':lambda *a,**kw:None,'_agent_save_checkpoint':lambda *a:None,
                '_agent_clear_checkpoint':lambda *a:None,'AI_AGENT_PENDING_FILE':Path(d)/'pending.json'}
            extract({'_run_developer_agent'},ns)
            fake=types.SimpleNamespace(post=post,Timeout=TimeoutError,ConnectionError=ConnectionError)
            with patch.dict(sys.modules,{'requests':fake}):
                plan,error=ns['_run_developer_agent']({},[],'REAL REQUEST',[],[],job_update_id=25)
        self.assertIsNone(error);self.assertEqual(plan['summary'],'done');self.assertEqual(len(sent),3)
        systems=[x['messages'][0]['content'] for x in sent]
        self.assertEqual(systems,['installed priority\n\nfresh rules']*3)
        self.assertEqual(sent[0]['messages'][1]['content'][0]['text'],'REAL REQUEST')
    def test_external_chat_and_standalone_routes(self):
        ns={'os':os};extract({'_ai_message_lane','_operator_needs_tools'},ns)
        with patch.dict(os.environ,{'TG_EXTERNAL_CONTROLLER':'1'}):
            self.assertEqual(ns['_ai_message_lane']('Какая у тебя задача?'),'chat')
            self.assertEqual(ns['_ai_message_lane']('проверь лог'),'fast')
            self.assertEqual(ns['_ai_message_lane']('исправь код'),'dev')
        with patch.dict(os.environ,{'TG_EXTERNAL_CONTROLLER':'0'}):
            self.assertEqual(ns['_ai_message_lane']('привет'),'fast')
    def test_actual_observer_saves_full_reply_without_browser(self):
        stop=threading.Event();saved=[];calls=[]
        def complete(*args):saved.append(args);stop.set()
        def request(*a,**k):calls.append(k);return 'Я🙂'*6000,None
        ns={'os':os,'time':time,'json':json,'monotonic':time.monotonic,'_io1591':rt,
            'load_telegram_config':lambda:{'chat_id':'1'},'_ai_health_touch':lambda *a:None,
            '_ai_db_next_message':lambda **k:{'update_id':7,'chat_id':'1','body':'привет','attempts':1},
            '_observer_collect_pages':lambda *a,**k:(_ for _ in ()).throw(AssertionError('Browser must not be accessed')),
            '_operator_needs_tools':lambda _:False,'_chat_prompt':lambda *a:'question',
            '_agent_system_prompt':lambda *a:'current policy','deepseek_vision_request':request,
            '_ai_db_complete':complete,'AI_AGENT_PENDING_FILE':Path('/not-existing-fixture'),
            '_ai_db_fail':lambda *a:(_ for _ in ()).throw(AssertionError(a))}
        extract({'ai_observer_process'},ns)
        ns['ai_observer_process']({},[],stop,{},None,None,'chat')
        self.assertGreater(len(saved[0][2]),12000)
        self.assertEqual(calls[0]['system_prompt'],'current policy')
    def test_request_audit_does_not_print_secret_prompt(self):
        output=stdio.StringIO()
        with redirect_stdout(output):result=rt.request_audit({'messages':[{'role':'system','content':'SECRET'}]},'chat')
        self.assertNotIn('SECRET',output.getvalue())
        self.assertEqual(result['system_sha256'],hashlib.sha256(b'SECRET').hexdigest())


class StateTests(unittest.TestCase):
    def test_assist_phases_are_really_tickable(self):
        n=next(n for n in ast.walk(function('_tab_process')) if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='tickable_phases' for t in n.targets))
        self.assertTrue({'SUCCESS_ASSIST','ERROR_ASSIST'}<=ast.literal_eval(n.value))
    def test_runtime_tick_invoked_instead_of_restart(self):
        for phase in ('SUCCESS_ASSIST','ERROR_ASSIST'):
            page=FakePage();worker={};calls=[]
            browser=types.SimpleNamespace(contexts=[types.SimpleNamespace(new_page=lambda:page)],version='fixture')
            class PW:
                def __enter__(self):return types.SimpleNamespace(chromium=types.SimpleNamespace(connect_over_cdp=lambda u:browser))
                def __exit__(self,*a):pass
            def make(tab,page,**kw):worker.update(id=tab,page=page,phase='IDLE',stopped=False,**kw);return worker
            def start(*a):worker['phase']=phase
            def tick(*a):calls.append(phase);worker['stopped']=True
            ns={'Path':Path,'sync_playwright':PW,'make_worker':make,'_worker_window_name':lambda *a:'fixture',
                'install_page_activity_tracker':lambda *a:None,'configure_matcher_runtime':lambda *a,**k:None,
                'start_row_in_worker':start,'tick_worker':tick,
                'restart_same_row_in_new_page':lambda *a:(_ for _ in ()).throw(AssertionError('restart')),
                'capture_blackbox':lambda *a:(_ for _ in ()).throw(AssertionError('unexpected phase'))}
            extract({'_tab_process'},ns)
            ns['_tab_process'](1,'mock',None,'.',None,initial_row=('test',))
            self.assertEqual(calls,[phase]);self.assertEqual(page.mutations,[])
    def test_guarded_restart_cannot_close(self):
        ns={'_io1591':rt};extract({'restart_same_row_in_new_page'},ns)
        p=FakePage();worker={'page':p,'phase':'SUCCESS_ASSIST','generation':1}
        self.assertFalse(ns['restart_same_row_in_new_page'](worker))
        self.assertEqual(p.mutations,[]);self.assertEqual(worker['generation'],1)
    def test_guarded_cancel_cannot_change_generation(self):
        ns={'_io1591':rt};extract({'begin_worker_cancel'},ns)
        worker={'error_guard':True,'generation':2}
        self.assertFalse(ns['begin_worker_cancel'](worker,'fixture'))
        self.assertEqual(worker['generation'],2)
    def test_cdp_close_checks_guard_before_connecting(self):
        ns={'_io1591':rt};extract({'_close_cdp_page_for_worker'},ns)
        self.assertFalse(ns['_close_cdp_page_for_worker']('mock',{'success_guard':True}))
    def test_heartbeat_preserves_both_guards_and_matcher_clock(self):
        ns={'_io1591':rt,'os':os,'monotonic':time.monotonic,'mark_worker_progress':lambda *a:None,
            '_read_page_window_name':lambda p:'fixture'}
        extract({'external_heartbeat'},ns)
        worker={'id':1,'phase':'POST_AUTH_REVIEW','success_guard':True,'error_guard':True,
                'heartbeat':{'1':{'matcher_time':100}}}
        ns['external_heartbeat'](worker,'fixture')
        hb=worker['heartbeat']['1']
        self.assertTrue(hb['success_guard']);self.assertTrue(hb['error_guard']);self.assertEqual(hb['matcher_time'],100)
    def test_guard_priority_even_when_phase_is_wrong(self):
        ns={'_io1591':rt,'monotonic':lambda:10000,'ROW_START_STALL_SECONDS':1,
            'PROTECTED_MATCHER_STALL_SECONDS':1,'DEFAULT_EXTERNAL_STALL_SECONDS':1}
        extract({'parent_watchdog'},ns)
        proc=types.SimpleNamespace(is_alive=lambda:True)
        self.assertEqual(ns['parent_watchdog']({1:proc},{'1':{'phase':'ROW_START','time':1,'success_guard':True}}),[])
    def test_merge_zero_and_false_are_not_empty(self):
        self.assertEqual(rt.merge_capture({'a':0,'b':False},{'a':9,'b':True}),{'a':0,'b':False})
    def test_aliases_and_existing_data(self):
        self.assertEqual(rt.merge_capture({'locality':'A','house':'7'},{'city':'B','passport_issuer':'Issuer'}),
                         {'locality':'A','house':'7','passport_issued_by':'Issuer'})
    def test_actual_capture_writes_sender_field(self):
        fields=[{'label':'Город','value':'Fixture city'}, {'label':'Кем выдан','value':'Fixture issuer'}]
        ns={'_io1591':rt,'capture_all_form_fields_v1583':lambda p:fields,
            'capture_form_fields_1591r19':lambda p:[],'re':__import__('re'),  # PROFILE_LABELS_1591R19
            '_SKIP_FIELD_TYPES_1591R19':{'checkbox','radio','hidden'},
            '_DATE_FIELD_RE_1591R19':__import__('re').compile(r'^\d{2}[.\-/]\d{2}[.\-/]\d{4}$'),
            '_FIO_RE_1591R12':__import__('re').compile(r'^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}(\s+[А-ЯЁA-Z][А-Яа-яЁёA-Za-z.\-]{0,30}){1,3}$')}
        extract({'final_profile_capture_v1583','_alias_hit_1591r19','_profile_fallback_1591r19'},ns)
        worker={'success_profile':{'house':'7'}}
        profile,raw=ns['final_profile_capture_v1583'](FakePage(),worker)
        self.assertEqual(worker['success_profile']['locality'],'Fixture city')
        self.assertEqual(worker['success_profile']['passport_issued_by'],'Fixture issuer')
        self.assertEqual(worker['success_profile']['house'],'7');self.assertEqual(raw,fields)
        self.assertEqual(profile,worker['profile'])


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'queue.db'
        self.ns={'time':time,'os':os,'json':json,'_io1591':rt,'AI_TELEGRAM_DB':self.path,
                 '_ai_db_connect':lambda:connection(self.path), '_ai_message_lane':lambda x:'chat',
                 '_ai_message_priority':lambda x:10}
        names={'_ai_db_init','_ai_db_store_telegram_update','_ai_db_next_message','_ai_db_complete','_ai_db_fail',
               '_ai_db_next_outbox','_ai_db_outbox_fail','_ai_db_outbox_sent'}
        extract(names,self.ns);self.ns['_ai_db_init']()
    def tearDown(self):self.temp.cleanup()
    def add(self,text='message',uid=1):
        self.ns['_ai_db_complete'](uid,'chat',text)
        return self.ns['_ai_db_next_outbox']()
    def advance(self):
        with connection(self.path) as c:
            c.execute('UPDATE outbox SET next_attempt_at=0')
            c.execute('UPDATE io1591_rate SET next_at=0')
    def test_initialization_preserves_live_claim(self):
        with connection(self.path) as c:
            c.execute('INSERT INTO inbox(update_id,chat_id,body,received_at,lane,claimed_by,claim_until) VALUES(1,?,?,0,?,?,?)',
                      ('c','q','fast','consumer',time.time()+100))
        self.ns['_ai_db_init']()
        with connection(self.path) as c:row=c.execute('SELECT lane,claimed_by FROM inbox').fetchone()
        self.assertEqual(row,('fast','consumer'))
    def test_initialization_does_not_reroute_internal_tasks(self):
        with connection(self.path) as c:c.execute("INSERT INTO inbox(update_id,chat_id,body,received_at,lane) VALUES(-1,'c','fixture',0,'fast')")
        self.ns['_ai_db_init']()
        with connection(self.path) as c:lane=c.execute('SELECT lane FROM inbox').fetchone()[0]
        self.assertEqual(lane,'fast')
    def test_failed_inbox_transaction_does_not_advance_offset(self):
        with connection(self.path) as c:
            c.execute("INSERT INTO meta VALUES('telegram_offset','5')")
            c.execute("CREATE TRIGGER fixture_abort BEFORE INSERT ON inbox BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ns['_ai_db_store_telegram_update']({'update_id':9,'message':{'chat':{'id':'chat'},'text':'q'}},'chat')
        with connection(self.path) as c:offset=c.execute("SELECT value FROM meta WHERE key='telegram_offset'").fetchone()[0]
        self.assertEqual(offset,'5')
    def test_full_response_survives_reopen(self):
        full='Я🙂'*10000;self.add(full)
        self.assertEqual(self.ns['_ai_db_next_outbox']()['body'],full)
    def test_recompletion_does_not_replace_delivered_text(self):
        self.add('original');self.ns['_ai_db_outbox_sent'](1);self.ns['_ai_db_complete'](1,'chat','replacement')
        with connection(self.path) as c:row=c.execute('SELECT body,sent_at FROM outbox').fetchone()
        self.assertEqual(row[0],'original');self.assertIsNotNone(row[1])
    def test_late_job_failure_does_not_overwrite_response(self):
        self.add('original')
        with connection(self.path) as c:c.execute("INSERT INTO inbox(update_id,chat_id,body,received_at) VALUES(1,'chat','q',0)")
        self.ns['_ai_db_fail'](1,'late error',3)
        with connection(self.path) as c:self.assertEqual(c.execute('SELECT body FROM outbox').fetchone()[0],'original')
    def test_outbox_is_creation_order_not_negative_id_order(self):
        self.add('older',1);self.ns['_ai_db_complete'](-999,'chat','newer')
        self.assertEqual(self.ns['_ai_db_next_outbox']()['update_id'],1)
    def test_unicode_split_reassembles_exactly(self):
        text=('Я🙂\n'*5000)+'END';parts=rt.split_text(text)
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(p.encode('utf-16-le'))//2<=3500 for p in parts))
    def test_delivery_waits_for_all_parts(self):
        item=self.add('X'*8000);sent=[]
        self.ns['telegram_api']=lambda c,m,p:(sent.append(p['text']) or {'ok':True,'result':{'message_id':len(sent)}},None)
        self.assertEqual(rt.send_part(self.ns,item,{}),'pending');self.advance()
        self.assertEqual(rt.send_part(self.ns,item,{}),'pending');self.advance()
        self.assertEqual(rt.send_part(self.ns,item,{}),'delivered')
        self.assertEqual(''.join(x.split('\n',1)[1] for x in sent),'X'*8000)
        self.assertIsNone(self.ns['_ai_db_next_outbox']())
    def test_resume_sends_only_unconfirmed_parts(self):
        item=self.add('X'*8000);sent=[]
        self.ns['telegram_api']=lambda c,m,p:(sent.append(p['text']) or {'ok':True,'result':{'message_id':1}},None)
        rt.send_part(self.ns,item,{})
        self.ns['telegram_api']=lambda *a:(None,'Timeout')
        self.advance();self.assertEqual(rt.send_part(self.ns,item,{}),'retry')
        self.ns['telegram_api']=lambda c,m,p:(sent.append(p['text']) or {'ok':True,'result':{'message_id':len(sent)}},None)
        self.advance();rt.send_part(self.ns,item,{});self.advance();rt.send_part(self.ns,item,{})
        self.assertEqual([s[:5] for s in sent],['[1/3]','[2/3]','[3/3]'])
    def test_ok_without_message_id_is_not_ack(self):
        item=self.add();self.ns['telegram_api']=lambda *a:({'ok':True,'result':{}},None)
        self.assertEqual(rt.send_part(self.ns,item,{}),'retry')
        with connection(self.path) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM io1591_parts').fetchone()[0],0)
            self.assertIsNone(c.execute('SELECT sent_at FROM outbox').fetchone()[0])
    def test_retry_after_is_respected(self):
        item=self.add();self.ns['telegram_api']=lambda *a:(None,rt.TelegramFailure('rate limit',429,60))
        now=time.time();rt.send_part(self.ns,item,{})
        with connection(self.path) as c:when=c.execute('SELECT next_attempt_at FROM outbox').fetchone()[0]
        self.assertGreaterEqual(when,now+60)
    def test_two_senders_cannot_deliver_same_chunk_simultaneously(self):
        item=self.add();entered=threading.Event();release=threading.Event();sent=[];results=[]
        def api(c,m,p):entered.set();release.wait(5);sent.append(p);return {'ok':True,'result':{'message_id':1}},None
        self.ns['telegram_api']=api
        thread=threading.Thread(target=lambda:results.append(rt.send_part(self.ns,item,{})))
        thread.start();self.assertTrue(entered.wait(5))
        self.assertEqual(rt.send_part(self.ns,item,{}),'busy')
        release.set();thread.join(5)
        self.assertEqual(len(sent),1);self.assertEqual(results,['delivered'])
    def test_replaying_sent_item_has_no_network_call(self):
        item=self.add();self.ns['_ai_db_outbox_sent'](1)
        self.ns['telegram_api']=lambda *a:(_ for _ in ()).throw(AssertionError('no send'))
        self.assertEqual(rt.send_part(self.ns,item,{}),'already_sent')
    def test_notification_is_really_queued_by_controller_send(self):
        ns={'app':types.SimpleNamespace(**self.ns),'_chat_id':lambda:'chat','MENU_MARKUP':'{}'}
        ns['app']._io1591=rt
        extract({'_send'},ns,CONTROL)
        uid=ns['_send']('N'*9000)
        self.assertLess(uid,-2**62)
        with connection(self.path) as c:self.assertEqual(len(c.execute('SELECT body FROM outbox').fetchone()[0]),9000)
    def test_storage_connection_is_closed(self):
        con=connection(self.path);ns=dict(self.ns,_ai_db_connect=lambda:con)
        with rt.db(ns) as c:c.execute('SELECT 1')
        with self.assertRaises(sqlite3.ProgrammingError):con.execute('SELECT 1')
    def test_error_text_redacts_credentials(self):
        token='12345678:'+'A'*32
        text=rt.redact('https://api.telegram.org/bot'+token+'/sendMessage socks5h://u:p@host:1')
        self.assertNotIn(token,text);self.assertNotIn('u:p',text)


class ControllerTests(unittest.TestCase):
    def run_main(self,fail_storage=False):
        class EndLoop(BaseException):pass
        saves=[];stored=[];polls=[];started=[]
        api=lambda c,m,p: ({'ok':True,'result':[{'update_id':7,'message':{'chat':{'id':'chat'},'text':'hello'}}]} if m=='getUpdates' else {'ok':True,'result':{}},None)
        def store(*a):
            stored.append(7)
            if fail_storage:raise OSError('fixture write failure')
        helper=types.SimpleNamespace(init_delivery=lambda *a:None,start_chat=lambda *a:started.append('chat'),
                                    start_sender=lambda *a:started.append('sender'),redact=rt.redact)
        app=types.SimpleNamespace(_io1591=helper,_ai_db_init=lambda:None,telegram_api=api,
                                  _ai_db_store_telegram_update=store)
        proc=types.SimpleNamespace(reap=lambda:None,status=lambda:'fixture',running=lambda:False)
        with tempfile.TemporaryDirectory() as d:
            ns={'os':os,'sys':sys,'json':json,'app':app,'_cfg':lambda:{'chat_id':'chat'},'_chat_id':lambda:'chat',
                '_purge_control_messages_from_ai':lambda:None,'CLIENTS_FILE':Path(d)/'clients.txt',
                'AutomationProcess':lambda:proc,'_load_offset':lambda:5,'_save_offset':lambda x:saves.append(x),
                '_send':lambda *a:None,'_typing':lambda:None,'MENU_MARKUP':'{}','_restart_after_drain':lambda p:False,
                'BTN_START':'start','BTN_STOP':'stop','BTN_RESTART':'restart','BTN_UPLOAD':'upload',
                'time':types.SimpleNamespace(sleep=lambda t:None if t==2 else (_ for _ in ()).throw(EndLoop()))}
            extract({'main'},ns,CONTROL)
            with self.assertRaises(EndLoop):ns['main']()
        return saves,stored,started
    def test_failed_input_is_not_acknowledged(self):
        saves,stored,_=self.run_main(True)
        self.assertEqual(stored,[7]);self.assertEqual(saves,[])
    def test_successful_input_commits_next_offset(self):
        saves,stored,started=self.run_main()
        self.assertEqual(saves,[8]);self.assertEqual(stored,[7]);self.assertEqual(started,['chat','sender'])
    def test_control_keys_not_sent_to_model(self):
        # Preserve the actual source ordering: all controls precede AI storage.
        code=ast.get_source_segment(CONTROL,function('main',CONTROL))
        self.assertLess(code.index('if text == BTN_STOP:'),code.index('app._ai_db_store_telegram_update'))
        self.assertLess(code.index('if text.startswith("/"):'),code.index('app._ai_db_store_telegram_update'))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.capture_out=redirect_stdout(stdio.StringIO());self.capture_out.__enter__()
        self.capture_err=redirect_stderr(stdio.StringIO());self.capture_err.__enter__()
        self.tmp=tempfile.TemporaryDirectory();self.app=Path(self.tmp.name)
        self.old={'test_beeline.py':b'old app','server_controller.py':b'old controller','symbol_matching.py':b'old matcher'}
        self.new=dict(self.old,**{'test_beeline.py':b'new app','server_controller.py':b'new controller','operator_runtime_io.py':b'helper','symbol_matching.py':b'new matcher'})
        for name,raw in self.old.items():(self.app/name).write_bytes(raw)
        (self.app/'clients.txt').write_bytes(b'PRIVATE DATA')
        (self.app/'progress.sqlite3').write_bytes(b'UNCHANGED')
        self.actions=[]
        self.svc=types.SimpleNamespace(status=lambda:{'ActiveState':'active'},stop=lambda:self.actions.append('stop'),
             start=lambda:self.actions.append('start'),healthy=lambda:True)
    def tearDown(self):
        self.tmp.cleanup()
        self.capture_err.__exit__(None,None,None);self.capture_out.__exit__(None,None,None)
    def test_running_service_requires_explicit_restart(self):
        with self.assertRaises(RuntimeError):install.apply_bundle(self.app,self.old,self.new,self.svc,import_check=lambda p:None)
        self.assertEqual(self.actions,[])
    def test_apply_installs_connected_files_and_preserves_data(self):
        backup=install.apply_bundle(self.app,self.old,self.new,self.svc,True,lambda p:None)
        self.assertEqual(self.actions,['stop','start'])
        for name,raw in self.new.items():self.assertEqual((self.app/name).read_bytes(),raw)
        self.assertEqual((self.app/'clients.txt').read_bytes(),b'PRIVATE DATA')
        self.assertEqual((backup/'test_beeline.py').read_bytes(),b'old app')
    def test_import_failure_restores_original_code(self):
        def failed(_):raise ImportError('fixture')
        with self.assertRaises(ImportError):install.apply_bundle(self.app,self.old,self.new,self.svc,True,failed)
        for name,raw in self.old.items():self.assertEqual((self.app/name).read_bytes(),raw)
        self.assertFalse((self.app/'operator_runtime_io.py').exists())
        self.assertEqual((self.app/'progress.sqlite3').read_bytes(),b'UNCHANGED')
    def test_startup_failure_restores_code(self):
        self.svc.healthy=lambda:False
        with self.assertRaises(RuntimeError):install.apply_bundle(self.app,self.old,self.new,self.svc,True,lambda p:None)
        self.assertEqual((self.app/'test_beeline.py').read_bytes(),b'old app')
        self.assertEqual(self.actions,['stop','start','stop','start'])
    def test_changed_source_refused_before_stop(self):
        (self.app/'test_beeline.py').write_bytes(b'changed externally')
        with self.assertRaises(RuntimeError):install.apply_bundle(self.app,self.old,self.new,self.svc,True,lambda p:None)
        self.assertEqual(self.actions,[])
        self.assertEqual((self.app/'test_beeline.py').read_bytes(),b'changed externally')
    def test_reapply_does_not_restart(self):
        for n,b in self.new.items():(self.app/n).write_bytes(b)
        result=install.apply_bundle(self.app,{k:self.new[k] for k in self.old},self.new,self.svc,True,lambda p:None)
        self.assertIsNone(result);self.assertEqual(self.actions,[])


if __name__=='__main__':
    unittest.main(verbosity=2)
