"""Offline latency model: actual get_user methods, simulated PostgreSQL protocol RTT.
Not a production or real database benchmark. No credentials or network access.
"""
import ast
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import os_accounts

class Connection:
    def __init__(self, autocommit=False): self.autocommit=autocommit; self.commands=[]
    def __enter__(self): return self
    def __exit__(self,*args):
        if not self.autocommit: self.roundtrip('COMMIT')
    def roundtrip(self,name): self.commands.append(name); time.sleep(.02)
    def cursor(self): return Cursor(self)
class Cursor:
    def __init__(self,conn): self.conn=conn
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,*args):
        if not self.conn.autocommit:self.conn.roundtrip('BEGIN')
        self.conn.roundtrip('SELECT')
    def fetchone(self): return {'id':'fixture','role':'worker','is_active':True,'_page_permissions':['orders']}

def run(cls):
    samples=[];commands=[]
    store=cls()
    for _ in range(7):
        connections=[]
        def connect(**kwargs):
            time.sleep(.02)  # Separate synthetic connection establishment.
            conn=Connection(**kwargs);connections.append(conn);return conn
        with patch.object(store,'ensure_schema'),patch.object(store,'_connect',side_effect=connect):
            start=time.perf_counter();store.get_user('fixture');samples.append(round((time.perf_counter()-start)*1000,2))
        commands=connections[0].commands
    return {'samples_ms':samples,'median_ms':statistics.median(samples),'min_ms':min(samples),'max_ms':max(samples),'protocol_commands':commands}

if __name__=='__main__':
    # Reproduce the former get_user connection mode, without a checkout dependency.
    tree=ast.parse(Path('os_accounts.py').read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PostgresAccountStore')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='get_user')
    for call in ast.walk(method):
        if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='_connect':
            call.keywords=[kw for kw in call.keywords if kw.arg!='autocommit']
    ns=dict(vars(os_accounts))
    exec(compile(ast.Module(body=[method],type_ignores=[]),'former connection mode','exec'),ns)
    before=type('Before',(os_accounts.PostgresAccountStore,),{'get_user':ns['get_user']})
    result={'model':'20ms connection + 20ms per protocol round trip; no actual DB','before':run(before),'after':run(os_accounts.PostgresAccountStore)}
    Path('.tmp-phase3-results').mkdir(exist_ok=True)
    Path('.tmp-phase3-results/auth-model.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
