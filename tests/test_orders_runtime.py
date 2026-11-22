from copy import deepcopy
import json
import pytest
import orders_runtime as runtime
import prodigi_preparation as prep
from test_prodigi_preparation import store,value
from test_auto_editions_jobs import database

@pytest.fixture
def active(store,monkeypatch):
    monkeypatch.setattr(prep,'connect',store)
    v=value();v.update(status='Browser uploading',browser={'token_hash':prep.digest('a'*43),'started':False})
    with store() as c,c.cursor() as q:prep.save(q,v)
    return dict(key='prodigi_prepare:1',token='a'*43,kind='artwork',stage='download',sequence=1,elapsed_ms=0,version='1.7.40',attempt=0,retry_in_ms=0)

def test_progress_is_separate_monotonic_scoped_and_cannot_change_a_permit(active):
    before=prep.read(1)
    assert runtime.progress(active)=={'recorded':True}
    assert runtime.progress(active)=={'recorded':False}
    runtime.progress({**active,'sequence':2,'stage':'transfer','elapsed_ms':125})
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key='orders_runtime:1'");record=q.fetchone()['value']
    assert record['timings']==[{'stage':'download','elapsed_ms':125}]
    assert prep.read(1)==before
    visible=runtime.public(before,record)
    assert visible['stage']=='transfer' and 'claim' not in visible and 'token' not in visible
    changed=deepcopy(before);changed['browser']['token_hash']='other'
    assert runtime.public(changed,record)=={}
    with pytest.raises(PermissionError):runtime.progress({**active,'sequence':3,'token':'b'*43})

def test_telemetry_never_locks_the_workflow_row_needed_by_a_native_permit(active,monkeypatch):
    with prep.connect() as c,c.cursor() as q:cursor_type=type(q)
    original=cursor_type.execute;reads=[];before=prep.read(1)
    def execute(self,sql,args=()):
        if args and args[0]=='prodigi_prepare:1' and sql.lstrip().upper().startswith('SELECT VALUE'):
            reads.append(sql)
            assert 'FOR SHARE' not in sql.upper() and 'FOR UPDATE' not in sql.upper()
        return original(self,sql,args)
    monkeypatch.setattr(cursor_type,'execute',execute)
    assert runtime.progress(active)=={'recorded':True}
    assert reads and prep.read(1)==before

@pytest.mark.parametrize('change',[{'stage':'customer address'},{'kind':[]},{'sequence':False},{'elapsed_ms':-1},
    {'version':'script'},{'key':'product:prodigi_prepare:1'},{'extra':'private'}])
def test_progress_rejects_unbounded_or_foreign_metadata(active,change):
    with pytest.raises((ValueError,PermissionError)):runtime.progress({**active,**change})

def test_completed_or_reset_jobs_reject_late_progress(active):
    v=prep.read(1);v.update(status='Awaiting dashboard QA')
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    with pytest.raises(PermissionError):runtime.progress(active)

def test_runtime_heartbeat_has_a_bounded_version_and_no_workflow_writes(active):
    before=prep.read(1);runtime.record_version('1.7.40');runtime.record_version('not-a-version')
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key='orders_companion_runtime'");saved=q.fetchone()['value']
    assert saved['version']=='1.7.40' and prep.read(1)==before

def test_stale_progress_is_waiting_and_retry_timing_is_bounded(active):
    runtime.progress({**active,'stage':'retrying','attempt':2,'retry_in_ms':2000})
    with prep.connect() as c,c.cursor() as q:
        q.execute("SELECT value FROM app_settings WHERE key='orders_runtime:1'");record=q.fetchone()['value']
    assert runtime.public(prep.read(1),record)['next_retry_at']
    record['seen_at']='2020-01-01T00:00:00+00:00'
    visible=runtime.public(prep.read(1),record)
    assert visible['delayed'] and visible['label'].startswith('Waiting for companion')

def test_progress_endpoint_authenticates_desktop_and_exact_claim(active,monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api
    calls=[]
    monkeypatch.setattr(api,'desktop',lambda token,**kw:calls.append(token))
    client=TestClient(Starlette(routes=[Route('/progress',runtime.endpoint,methods=['POST'])]))
    assert client.post('/progress',json=active).status_code==403 and calls==[]
    assert client.post('/progress',json=active,headers={'Authorization':'Bearer '+'z'*43}).status_code==200
    assert calls==['z'*43]
    assert client.post('/progress',json={**active,'token':'b'*43},headers={'Authorization':'Bearer '+'z'*43}).status_code==403

def test_metrics_are_bounded_aggregate_without_customer_or_order_data(active):
    v=prep.read(1);v['stage_durations']=[{'stage':'Checking dashboard QA','elapsed_ms':i} for i in (100,200,300,400)]
    with prep.connect() as c,c.cursor() as q:prep.save(q,v)
    result=runtime.metrics()
    assert result['sample_limit']==500 and result['sampled_orders']==1
    assert result['stages']['Checking dashboard QA']=={'samples':4,'p50_ms':200,'p95_ms':400}
    assert 'customer' not in json.dumps(result) and 'order_id' not in json.dumps(result) and 'token' not in json.dumps(result)
