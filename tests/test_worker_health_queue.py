"""Worker Health actions on disposable SQL; no live worker, PSD or provider access."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import time
import uuid
import os
import socket
import subprocess
import threading
from unittest.mock import patch

import pytest
import worker_health as health
import worker_health_api as api
import worker_health_queue as queue
from worker_health_cache import invalidate
from tests.test_worker_health import telemetry,continuous,store,database,pglite_database,mapping,rows
from tests.test_auto_editions_api import ADMIN,VA,request


@pytest.fixture
def operations(telemetry):
    d,sql=telemetry
    sql.execute(Path('supabase/migrations/20261016071758_auto_editions_bulk_operations.sql').read_text(encoding='utf-8'))
    return d,sql


def failed(d,sql,n=1000,repair=False):
    pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'fixture',newly_linked=False)
    sql.execute("UPDATE auto_edition_onboarding SET status=%s,attempts=3,priority=8,reason=%s WHERE product_gid=%s",('Needs PSD Repair' if repair else 'Blocked','Missing font' if repair else 'Download interrupted',pid))
    return pid


def test_retry_duplicate_click_priority_attempt_history_and_protected_data(operations):
    d,sql=operations;pid=failed(d,sql)
    protected={t:deepcopy(rows(sql,t)) for t in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings','auto_edition_layouts')}
    key=str(uuid.uuid4());start=time.perf_counter();first=queue.submit(d.connect,pid,'admin',key);elapsed=(time.perf_counter()-start)*1000
    assert first['accepted'] and first['status']=='Pending'
    assert queue.submit(d.connect,pid,'admin',key)['duplicate']
    q=rows(sql,'auto_edition_onboarding')[0];assert q['priority']==8 and q['attempts']==0
    audits=[r for r in rows(sql,'auto_edition_onboarding_audit') if r['event']=='worker_health_queue_request']
    assert len(audits)==1 and audits[0]['detail']['previous_attempts']==3 and audits[0]['detail']['previous_error']=='Download interrupted'
    for t,before in protected.items():assert rows(sql,t)==before
    with pytest.raises(ValueError):queue.submit(d.connect,pid,'other',key)
    assert health.Health(d.connect).snapshot()['jobs'][0]['status']=='Pending'
    print(json.dumps(dict(retry_ack_ms=round(elapsed,2),scope='Actual durable queue adapter, disposable SQL; no provider latency')))


def test_active_owned_checkpoint_and_completed_protection(operations):
    d,sql=operations;pid=failed(d,sql);queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    active=d.queue.claim('synthetic-host');assert active['product_gid']==pid
    with pytest.raises(ValueError,match='lease'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    d.queue.checkpoint(pid,str(active['lease_token']),'synthetic-host','Blocked','Upload interrupted')
    health.record_heartbeat(d.connect,'Companion','fixture',dict(state='Recovering',stage='Uploading',product_gid=pid,checkpoint_pending=True))
    with pytest.raises(ValueError,match='retained checkpoint'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    sql.execute('DELETE FROM auto_edition_worker_heartbeats')
    sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,'{}','[]','{}','fixture',now())",('c'*64,))
    sql.execute("UPDATE auto_edition_onboarding SET preparation_hash=%s WHERE product_gid=%s",('c'*64,pid))
    with pytest.raises(ValueError,match='protected'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))


def test_repair_confirmation_then_all_normal_validation_still_required(operations):
    d,sql=operations;pid=failed(d,sql,repair=True)
    with pytest.raises(ValueError,match='Correct'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    result=queue.search(d.connect,'Art 1000')['rows'][0];assert not result['eligible'] and result['eligible_after_repair']
    queue.submit(d.connect,pid,'admin',str(uuid.uuid4()),True)
    active=d.queue.claim('fixture');assert active['attempts']==1
    # An uncorrected PSD is still rejected by the existing worker's checkpoint path.
    d.queue.checkpoint(pid,str(active['lease_token']),'fixture','Needs PSD Repair','Missing font',diagnostic=dict(code='FONT_MISSING',stage='Photoshop'))
    value=health.Health(d.connect).snapshot()['jobs'][0]
    assert value['status']=='Needs Repair' and value['stage']=='Photoshop'
    assert value['diagnostic']['manual_repair'] and not value['diagnostic']['retry_may_help']
    assert not rows(sql,'auto_edition_layouts')


def test_terminal_owned_lease_requires_fresh_safe_companion_checkpoint(operations):
    d,sql=operations;pid=failed(d,sql)
    queue.submit(d.connect,pid,'admin',str(uuid.uuid4()));active=d.queue.claim('fixture')
    d.queue.checkpoint(pid,str(active['lease_token']),'fixture','Blocked','Download interrupted')
    with pytest.raises(ValueError,match='owned lease'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    health.record_heartbeat(d.connect,'Companion','fixture',dict(state='Idle',checkpoint_pending=False,processor_lock=False))
    sql.execute("UPDATE auto_edition_worker_heartbeats SET seen_at=now()-interval '5 minutes'")
    with pytest.raises(ValueError,match='owned lease'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    health.record_heartbeat(d.connect,'Companion','fixture',dict(state='Idle',checkpoint_pending=False,processor_lock=False))
    assert queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))['accepted']
    assert queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))['duplicate']
    assert len(rows(sql,'auto_edition_onboarding'))==1


def test_busy_queue_has_actionable_retry_response():
    class Busy(Exception):sqlstate='55P03'
    response=api.failure(Busy())
    assert response.status_code==503 and 'retry the same request' in json.loads(response.body)['error']


def test_search_offers_failed_replacement_correction_without_bypassing_submit_guards():
    row=dict(product_count=1,dropbox_file_id='id:original',file_path='/Original.psd',edition_total=100,
        status='Blocked',reviewing=False,approved=True,preparation_hash='a'*64,retained=True,
        replacement=dict(stage='Failed',attempts=0,expected_source={'file_id':'id:original'}))
    assert 'confirm' in queue.eligibility(row)
    assert not queue.eligibility(row,True)
    row['replacement']['attempts']=3
    assert 'separate review' in queue.eligibility(row,True)
    row['replacement'].update(attempts=0,manual_required=True)
    assert 'manual' in queue.eligibility(row,True)
    row['replacement']=None
    assert 'protected' in queue.eligibility(row,True)


def test_search_mapping_add_and_manual_reset_deferred_restrictions(operations,monkeypatch):
    d,sql=operations;pid,fid=mapping(sql,1000)
    result=queue.search(d.connect,'1000')['rows'][0];assert result['eligible'] and result['status']=='Not queued'
    queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    assert len(rows(sql,'auto_edition_onboarding'))==1
    result=queue.search(d.connect,'1000')['rows'][0];assert not result['eligible'] and 'Already queued' in result['reason']
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','false')
    with pytest.raises(ValueError,match='deferred'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))
    sql.execute('DELETE FROM product_psd_mappings WHERE shopify_product_gid=%s',(pid,))
    assert 'mapping' in queue.search(d.connect,'1000')['rows'][0]['reason']
    with pytest.raises(ValueError,match='mapping'):queue.submit(d.connect,pid,'admin',str(uuid.uuid4()))


def seed(sql,count,total=100):
    sql.execute("""INSERT INTO edition_products SELECT 'gid://shopify/Product/'||n,n::text,'Art '||n,'art-'||n,%s,37,true,true FROM generate_series(10000,%s)n""",(total,9999+count))
    sql.execute("""INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id)
        SELECT shopify_product_gid,'id:source'||shopify_product_id,'/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Art '||shopify_product_id||'.psd','manual','fixture' FROM edition_products WHERE shopify_product_id::int>=10000""")
    sql.execute("""INSERT INTO auto_edition_onboarding(product_gid,file_id,status,priority,attempts,reason)
        SELECT shopify_product_gid,dropbox_file_id,'Blocked',8,2,'Download interrupted' FROM product_psd_mappings""")


def test_continuous_285_and_live_filter_reconciliation_without_duplicates(operations):
    d,sql=operations;seed(sql,285);service=health.Health(d.connect);cursor='';seen=[];start=time.perf_counter()
    first=queue.page(service);first_ms=(time.perf_counter()-start)*1000
    while True:
        value=queue.page(service,cursor=cursor);assert len(value['jobs'])<=50;seen.extend(j['id'] for j in value['jobs'])
        if value['next_cursor'] is None:break
        cursor=value['next_cursor']
    assert len(seen)==len(set(seen))==285
    failed_page=queue.page(service,'Failed');known={j['id']:j['version'] for j in failed_page['jobs']}
    pid=failed_page['jobs'][0]['id'];queue.submit(d.connect,pid,'admin',str(uuid.uuid4()));invalidate(d.connect)
    changes=queue.changes(service,'Failed',known,failed_page['scanned_to']);assert pid in changes['removed']
    again=queue.page(service,'Queued');assert again['jobs'][0]['status']=='Pending'
    report=dict(jobs=285,first_50_ms=round(first_ms,2),first_page_rows=len(first['jobs']),total_http_batches=6,scope='Actual read model and cursor batches; disposable SQL; no network latency')
    out=Path('output/worker-health-queue');out.mkdir(parents=True,exist_ok=True);(out/'backend-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


def test_beyond_old_1000_bound_and_missing_mapping_remains_visible(operations):
    d,sql=operations;seed(sql,1005)
    sql.execute("DELETE FROM product_psd_mappings WHERE shopify_product_gid='gid://shopify/Product/10000'")
    result=health.Health(d.connect).snapshot();assert len(result['jobs'])==1005
    assert not next(j for j in result['jobs'] if j['id']=='gid://shopify/Product/10000')['retry_eligible']


def test_details_on_demand_redaction_and_no_invented_stage(operations):
    d,sql=operations;pid=failed(d,sql)
    sql.execute("UPDATE auto_edition_onboarding SET reason='opaque failure token=private' WHERE product_gid=%s",(pid,))
    result=health.Health(d.connect).snapshot()['jobs'][0]
    assert result['stage']=='Stage unavailable' and result['diagnostic']['code']=='CAUSE_UNDETERMINED'
    value=queue.details(d.connect,pid)
    assert 'private' not in value['technical_error'] and '[redacted]' in value['technical_error']


@pytest.mark.parametrize('endpoint',[api.jobs,api.updates,api.search,api.enqueue,api.details])
def test_permissions_reject_before_any_database_action(endpoint):
    with patch('files_upload_api._request_user',return_value=VA),patch.object(api,'store',side_effect=AssertionError('No database access')):
        response=asyncio.run(endpoint(request('POST')))
    assert response.status_code==403


def test_new_queue_endpoint_origin_and_idempotent_ack(operations):
    d,sql=operations;pid=failed(d,sql);key=str(uuid.uuid4());body=dict(product_gid=pid,request_id=key,repair_confirmed=False)
    with patch('files_upload_api._request_user',return_value=ADMIN),patch.object(api,'store',return_value=health.Health(d.connect)):
        assert asyncio.run(api.enqueue(request('POST',body=body,origin=''))).status_code==403
        response=asyncio.run(api.enqueue(request('POST',body=body)));assert response.status_code==202
        assert json.loads(response.body)['status']=='Pending'
        assert json.loads(asyncio.run(api.enqueue(request('POST',body=body))).body)['duplicate']


def test_actual_http_desktop_queue_with_285_jobs_and_recovery(operations,tmp_path):
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    import auto_editions as ae
    from auto_editions_store import Preparations
    from tests.test_auto_editions_bulk import prepared,rebind
    d,sql=operations;seed(sql,285,total=2);service=health.Health(d.connect)
    state=dict(active=None,requests={},fail_list=False)
    protected={t:deepcopy(rows(sql,t)) for t in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings','auto_edition_layouts')}
    async def transition(req):
        body=await req.json();stage=body['stage']
        if stage=='fail-list':state['fail_list']=True
        elif stage=='claim':state['active']=d.queue.claim('synthetic-browser-host')
        elif stage=='Photoshop':
            j=state['active'];d.queue.heartbeat(j['product_gid'],str(j['lease_token']),'synthetic-browser-host','Photoshop')
        elif stage=='fail':
            j=state['active'];d.queue.checkpoint(j['product_gid'],str(j['lease_token']),'synthetic-browser-host','Needs PSD Repair','Missing font',diagnostic=dict(code='FONT_MISSING',stage='Photoshop'))
            health.record_heartbeat(d.connect,'Companion','synthetic-browser-host',dict(state='Idle',stage='Unknown',checkpoint_pending=False,processor_lock=False))
        elif stage=='complete':
            j=state['active'];record,_=prepared(tmp_path);record['manifest']['source']=ae.source_identity(j['product_gid'],dict(id=j['file_id'],rev='a1',content_hash='a'*64));rebind(record)
            Preparations(d.connect).save(record['manifest'],record['proofs'],record['receipts'],'synthetic-browser-host')
            d.queue.checkpoint(j['product_gid'],str(j['lease_token']),'synthetic-browser-host','Preparing',source=record['manifest']['source'],total=2)
            d.queue.checkpoint(j['product_gid'],str(j['lease_token']),'synthetic-browser-host','Blocked','Uploaded; needs review',digest=record['hash'])
        invalidate(d.connect)
        return JSONResponse(dict(ok=True))
    class Observe:
        def __init__(self,app):self.app=app
        async def __call__(self,scope,receive,send):
            path=scope.get('path','');state['requests'][path]=state['requests'].get(path,0)+1
            if path=='/api/worker-health/jobs' and state['fail_list']:
                state['fail_list']=False
                return await JSONResponse(dict(error='Temporary list failure. Retry.'),status_code=503)(scope,receive,send)
            return await self.app(scope,receive,send)
    app=Observe(Starlette(routes=[Route(path,fn,methods=list(methods)) for path,fn,methods in api.ROUTES]+[Route('/fixture/transition',transition,methods=['POST'])]))
    sock=socket.socket();sock.bind(('127.0.0.1',0));url='http://127.0.0.1:'+str(sock.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    with patch('files_upload_api._request_user',return_value=ADMIN),patch.object(api,'store',return_value=service):
        thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started:
                assert time.monotonic()<deadline;time.sleep(.01)
            env={**os.environ,'NODE_PATH':r'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules','WORKER_QUEUE_FIXTURE':url}
            result=subprocess.run(['node','tests/test_worker_health_queue_ui.cjs'],env=env,capture_output=True,text=True,encoding='utf-8',timeout=150)
            assert result.returncode==0,result.stdout+result.stderr
            print(result.stdout)
            assert state['requests'].get('/api/worker-health/jobs',0)>=6
            for t,before in protected.items():assert rows(sql,t)==before
        finally:server.should_exit=True;thread.join(timeout=10);sock.close()
