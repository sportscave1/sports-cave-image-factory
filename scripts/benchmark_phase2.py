"""Offline execution benchmarks; 20ms simulated SQL RTT, never production I/O."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import ast
import json
import importlib.util
import os
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import os_accounts
from crm_automation_store import AutomationStore
from crm_automation_definition import FORMAT, new_flow
from crm_automation_home_read import BoundedStore


def auth_functions(source, user, store):
    names = {'_refresh_session_account_if_due', '_session_user_matches_refreshed_user', '_session_version'}
    tree = ast.parse(source)
    state = {'sports_cave_auth_checked_at': 0, 'sports_cave_current_user': user}
    cleared = Mock(side_effect=lambda *a: state.pop('sports_cave_current_user', None))
    def status():
        store.first_admin()
        return {'available': True}
    ns = dict(st=SimpleNamespace(session_state=state), time=time, os_accounts=os_accounts,
              _account_system_status=status, _public_account=lambda u: deepcopy(u),
              _clear_authenticated_session_state=cleared, clear_auth_cookie=Mock(),
              set_activity_actor=Mock(), _activity_actor_for_user=lambda u: '',
              _activity_actor_metadata_for_user=lambda u: {})
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), '<auth benchmark>', 'exec'), ns)
    return ns, cleared


class SchemaConnection:
    def __init__(self): self.calls=0; self.roundtrips=0; self.pipelined=False
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def cursor(self): return self
    def execute(self, *args):
        self.calls += 1
        if not self.pipelined: self.wait()
        return self
    def fetchall(self): return [{'id':'fixture'}]
    def wait(self): self.roundtrips += 1; time.sleep(.02)
    @contextmanager
    def pipeline(self):
        self.pipelined=True
        try: yield
        finally: self.wait(); self.pipelined=False
    def commit(self): self.wait()


def main():
    global os_accounts, AutomationStore, BoundedStore
    baseline = os.environ.get('PHASE2_BASELINE') == '1'
    source_dir = ROOT / '.tmp-phase2-baseline' if baseline else ROOT
    if baseline:
        def module(name):
            spec = importlib.util.spec_from_file_location('phase2_baseline_' + name, source_dir / (name + '.py'))
            loaded = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = loaded
            spec.loader.exec_module(loaded)
            return loaded
        os_accounts = module('os_accounts')
        AutomationStore = module('crm_automation_store').AutomationStore
        BoundedStore = module('crm_automation_home_read').BoundedStore
    result={'sql_rtt_ms_simulated':20}
    user=dict(id='fixture', role='worker', is_active=True, account_status='active', session_version=1)
    store=Mock()
    store.first_admin.side_effect=lambda: time.sleep(.02)
    store.get_user.side_effect=lambda *a: (time.sleep(.02) or deepcopy(user))
    ns,_=auth_functions((source_dir/'app.py').read_text(encoding='utf-8'),user,store)
    start=time.perf_counter()
    with patch.object(os_accounts,'DEFAULT_STORE',store): ns['_refresh_session_account_if_due'](user)
    result['auth_refresh']={'ms':round((time.perf_counter()-start)*1000,2),'account_reads':store.get_user.call_count,'unrelated_admin_reads':store.first_admin.call_count}
    schema=os_accounts.PostgresAccountStore(); conn=SchemaConnection()
    start=time.perf_counter()
    with patch.object(schema,'is_configured',return_value=True),patch.object(schema,'_connect',return_value=conn): schema.ensure_schema()
    result['schema']={'ms':round((time.perf_counter()-start)*1000,2),'statements':conn.calls,'roundtrips':conn.roundtrips}
    conn=SchemaConnection()
    start=time.perf_counter()
    BoundedStore(SimpleNamespace(db=lambda:conn)).q('SELECT id FROM crm_automations')
    result['automation_identity']={'ms':round((time.perf_counter()-start)*1000,2),'statements':conn.calls,'roundtrips':conn.roundtrips}
    identity=str(uuid.uuid4()); row={'id':identity,'name':'Fixture','status':'ACTIVE','config':{'format':FORMAT,'draft':new_flow(),'revision':1,'published_version':1}}
    flow=AutomationStore(); calls=[]
    def read(*a): calls.append(1); time.sleep(.02); return deepcopy(row)
    start=time.perf_counter()
    with patch.object(flow,'get',side_effect=read):
        with flow.display_read_scope() if hasattr(flow,'display_read_scope') else nullcontext():
            for _ in range(4):flow.flow(identity)
    result['flow_definition']={'ms':round((time.perf_counter()-start)*1000,2),'reads':len(calls)}
    print(json.dumps(result))
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__': main()
