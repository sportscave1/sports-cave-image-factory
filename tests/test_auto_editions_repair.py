"""Repair queue contracts on disposable Postgres; no provider or Codex calls."""
import json
import uuid
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
import auto_editions_repair as repair
from tests.test_auto_editions_discovery import database,store,pglite_database,PID,register,tick,asset,rows

@pytest.fixture
def broken(store):
    d,sql=store
    sql.execute("ALTER TABLE auto_edition_onboarding ADD COLUMN IF NOT EXISTS replacement jsonb; ALTER TABLE auto_edition_onboarding ADD COLUMN IF NOT EXISTS reset_cancellation jsonb")
    sql.execute(Path('supabase/migrations/20261017001547_auto_editions_technical_completion.sql').read_text())
    register(store);tick(store,[asset()])
    sql.execute("CREATE TABLE edition_orders(id int,shopify_product_gid text,status text,allocation_valid boolean,identity_enforced boolean,invalidated_at timestamptz)")
    sql.execute("UPDATE auto_edition_onboarding SET status='Needs PSD Repair',reason='Exactly one visible, editable edition-number layer is required.' WHERE product_gid=%s",(PID,))
    return d,sql

def test_request_duplicate_is_durable_and_preserves_all_artwork_and_ledger(broken):
    d,sql=broken
    protected={t:deepcopy(rows(sql,t)) for t in ('edition_products','product_psd_mappings','auto_edition_onboarding','auto_edition_preparations','auto_edition_layouts')}
    first=repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    second=repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    assert second['duplicate'] and second['request_id']==first['request_id']
    assert len([r for r in rows(sql,'auto_edition_onboarding_audit') if r['event']==repair.EVENT])==1
    for t,before in protected.items():assert rows(sql,t)==before

def test_request_refuses_wrong_mapping_and_anonymous_actor(broken):
    d,sql=broken
    with pytest.raises(PermissionError):repair.request(d.connect,PID,'',str(uuid.uuid4()))
    sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:different'")
    with pytest.raises(ValueError,match='mapping'):repair.request(d.connect,PID,'admin',str(uuid.uuid4()))

def test_structural_failure_handoff_is_claimed_once_and_fenced(broken):
    d,sql=broken;requested=repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    metadata=asset()
    from types import SimpleNamespace
    assets=SimpleNamespace(token='synthetic',integration=SimpleNamespace(psd_open_metadata=lambda *a,**k:metadata))
    with patch('auto_editions_runtime.storage',return_value=assets):assert repair.run_one(d.connect)
    claimed=repair.claim(d.connect)
    assert claimed['request_id']==requested['request_id'] and repair.claim(d.connect) is None
    assert 'Edge' in claimed['prompt'] and 'Do not commit' in claimed['prompt']
    assert '<edition_repair_data>' in claimed['prompt']
    with pytest.raises(ValueError,match='ownership'):repair.returned(d.connect,PID,claimed['request_id'],'wrong',True)
    repair.returned(d.connect,PID,claimed['request_id'],claimed['handoff_token'],False)
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Needs help'

def test_status_never_infers_success_and_hides_handoff_capability():
    view=dict(status='Failed',reason='bad source',actions=['retry'])
    result=repair.display(view,dict(state='Codex repairing',handoff_token='private'),writable=True)
    assert result['status']=='Repairing' and result['actions']==[] and 'handoff_token' not in result['repair']
    assert repair.display(view,None,writable=False)['actions']==[]
    assert repair.display(view,None,writable=True)['actions']==['repair']
    assert repair.display(dict(status='Cloud Ready'),dict(state='Complete'))['status']=='Cloud Ready'

def test_changed_mapping_stops_cloud_worker_without_retry(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:changed'")
    with patch('worker_health_queue.submit') as submit:
        repair.run_one(d.connect);submit.assert_not_called()
    assert repair.claim(d.connect) is None
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Needs help'

def test_queue_request_identity_cannot_cross_products_or_actors(broken):
    d,sql=broken;key=str(uuid.uuid4());repair.request(d.connect,PID,'admin',key)
    with pytest.raises(ValueError,match='another selection'):repair.request(d.connect,PID,'another-admin',key)

def test_repair_receipt_cannot_reopen_completed_request(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Codex queued',prompt='scoped synthetic request')
    claim=repair.claim(d.connect)
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Complete','Real JPG verified')
    repair.returned(d.connect,PID,claim['request_id'],claim['handoff_token'],True)
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Complete'

def test_order_links_use_repair_and_repairing_without_enqueuing():
    import auto_editions_runtime as runtime
    from auto_editions_store import LayoutIndex
    from types import SimpleNamespace
    index=LayoutIndex();index.reasons[PID]='Needs PSD Repair'
    registry=SimpleNamespace(index=lambda **k:index)
    order=dict(id=42,shopify_product_gid=PID,shopify_variant_id='1')
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,None)):
        url=runtime.download_links([order])['42']
        assert 'repair=1' in url and url.endswith('#Repair')
        index.reasons[PID]='Repairing'
        url=runtime.download_links([order])['42']
        assert 'repair=1' not in url and url.endswith('#Repairing')

def test_ready_jpg_is_required_before_repair_completion(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready'")
    with d.connect() as c,c.cursor() as cur:
        record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Waiting',allocation_id=42)
    from types import SimpleNamespace
    jobs=SimpleNamespace(connect=d.connect,enqueue=lambda *a:dict(status='Queued'))
    with patch('auto_editions_runtime.job_for',return_value=(dict(identity=dict(source=dict(product_gid=PID))),None)),patch('auto_editions_runtime.stores',return_value=(None,jobs)),patch('auto_editions_runtime.start_worker'):
        repair.run_one(d.connect)
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Waiting'

def test_newly_uploaded_package_waits_for_technical_seed_instead_of_codex(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Waiting','Native preparation running')
    row=dict(product_gid=PID,dropbox_file_id='id:original',status='Blocked',priority=10,
        preparation_hash='b'*64,technical_state=None,replacement=None)
    with patch.object(repair,'snapshot',return_value=row),patch('auto_editions_technical.Technical.seed') as seed:
        repair.run_one(d.connect);seed.assert_called_once()
    assert repair.claim(d.connect) is None
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Waiting'
    # Invalid/stale evidence must not be kept waiting forever by repeated seeds.
    sql.execute("UPDATE auto_edition_onboarding_audit SET detail=detail-'next_check' WHERE event=%s",(repair.EVENT,))
    with patch.object(repair,'snapshot',return_value=row),patch('auto_editions_technical.Technical.seed') as seed:
        repair.run_one(d.connect);seed.assert_not_called()
    assert repair.claim(d.connect) is not None


def test_backlog_admission_is_bounded_idempotent_and_respects_leases(broken):
    d,sql=broken
    sql.execute("UPDATE auto_edition_onboarding SET priority=10,lease_until=now()-interval '1 minute'")
    assert repair.admit(d.connect)==1
    assert repair.admit(d.connect)==0
    assert len([r for r in rows(sql,'auto_edition_onboarding_audit') if r['event']==repair.EVENT])==1


def test_repair_enqueues_all_valid_orders_and_isolates_blocked_unit(broken):
    from types import SimpleNamespace
    d,sql=broken
    sql.execute("INSERT INTO edition_orders SELECT n,%s,'assigned',true,true,NULL FROM generate_series(1,3) n",(PID,))
    repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready'")
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Waiting',jpg_ready=[1,3],jpg_preparation_hash='old-package')
    calls=[]
    def resolver(i):
        if i==2:raise ValueError('Variant needs review')
        return dict(id=str(i),identity=dict(source=dict(product_gid=PID))),None
    def enqueue(job,actor):
        calls.append(job['id']);return dict(status='Ready')
    with patch('auto_editions_runtime.job_for',side_effect=resolver),patch('auto_editions_runtime.stores',return_value=(None,SimpleNamespace(enqueue=enqueue))):
        repair.run_one(d.connect)
    assert calls==['1','3']
    with d.connect() as c,c.cursor() as cur:detail=repair.latest(cur,PID)['detail']
    assert detail['state']=='Needs help' and detail['jpg_ready']==[1,3] and '2' in detail['jpg_blocked']


def test_preparing_product_is_never_claimed_for_codex(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Codex queued',prompt='scoped source repair')
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation',reason='Approved colour interpretation'")
    assert repair.claim(d.connect) is None
    repair.run_one(d.connect)
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Waiting'


def test_failed_handoff_cannot_stop_a_resumed_native_queue(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Codex queued',prompt='scoped source repair')
    receipt=repair.claim(d.connect)
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation'")
    repair.returned(d.connect,PID,receipt['request_id'],receipt['handoff_token'],False)
    with d.connect() as c,c.cursor() as cur:assert repair.latest(cur,PID)['detail']['state']=='Waiting'
