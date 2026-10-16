"""Local queue boundaries, persistent cached previews and real loopback latency checks."""
import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
import pytest
from PIL import Image
import auto_editions as ae
import auto_editions_bulk as bulk
from auto_editions_bulk_jobs import ReviewJobs,PreviewStore
from auto_editions_bulk_runtime import run_one
from tests.test_auto_editions_bulk_jobs import ops,review,store,database,pglite_database,PID,item,submit,run,progress
from tests.test_auto_editions_bulk import rebind
from tests.test_auto_editions_api import ADMIN,request


def test_pending_and_processing_filtered_before_manifest_reads_then_failure_restored(ops):
    jobs,sql,record,assets=ops
    assert bulk.listing(jobs.connect,[PID],ADMIN)['rows'][0]['eligible']
    key=submit(jobs,record)
    with patch.object(bulk,'records',side_effect=AssertionError('Queued jobs must not load manifests')):
        assert bulk.listing(jobs.connect,[PID],ADMIN)['rows']==[]
    job=jobs.claim()
    assert bulk.listing(jobs.connect,[PID],ADMIN)['rows']==[]
    jobs.finish(job,'Failed','Temporary provider failure after bounded retries.')
    rows=bulk.listing(jobs.connect,[PID],ADMIN)['rows']
    assert len(rows)==1 and rows[0]['eligible'] and 'Temporary provider failure' in rows[0]['reason']
    # Repeated submission still cannot create a second concurrent product job.
    again=submit(jobs,record);duplicate=submit(jobs,record)
    assert progress(jobs,again)['rows'][0]['job_id']==progress(jobs,duplicate)['rows'][0]['job_id']


def test_real_committed_approval_excluded_after_snapshot_cache_and_store_restart(ops):
    jobs,sql,record,assets=ops;submit(jobs,record);run(jobs,record,assets)
    bulk.snapshots.clear();bulk.thumbnails.entries.clear()
    assert bulk.listing(ReviewJobs(jobs.connect).connect,[PID],ADMIN)['rows']==[]
    sql.execute('SELECT next_edition_number FROM edition_products');assert sql.fetchone()['next_edition_number']==37
    sql.execute('SELECT * FROM synthetic_certificates');assert sql.fetchall()


def test_partial_failure_retains_only_failed_design_for_retry(ops,tmp_path,monkeypatch):
    from auto_editions_cloud import DropboxAssets
    jobs,sql,record,assets=ops;monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    pid='gid://shopify/Product/999';failed=deepcopy(record);failed['manifest']['source'].update(product_gid=pid,file_id='id:second');rebind(failed)
    sql.execute("INSERT INTO edition_products VALUES(%s,'999','Retry Art','retry-art',2,1,true,true)",(pid,))
    sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,'id:second','/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd','manual','synthetic-admin')",(pid,))
    sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(failed['hash'],json.dumps(failed['manifest']),json.dumps(failed['proofs']),json.dumps(failed['receipts'])))
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,preparation_hash,source,edition_total) VALUES(%s,'id:second','Blocked',%s,%s::jsonb,2)",(pid,failed['hash'],json.dumps(failed['manifest']['source'])))
    broken=Mock();broken.fetch.side_effect=lambda digest,asset,destination:Path(destination).write_bytes(b'corrupt')
    original_metadata=assets.integration.psd_open_metadata.side_effect
    def metadata(token,file_id,**kwargs):
        result=original_metadata(token,file_id,**kwargs)
        if file_id!='id:original':result['path_display']=DropboxAssets.path(failed['hash'],file_id.removeprefix('id:'))
        return result
    broken.integration.psd_open_metadata.side_effect=metadata
    key=str(uuid.uuid4());jobs.submit('synthetic-admin',key,[item(record),item(failed,pid)])
    with patch('auto_editions_onboarding_api.candidate',side_effect=lambda product,digest:(record,assets) if product==PID else (failed,broken)):
        run_one(jobs,authorize=lambda actor:None);run_one(jobs,authorize=lambda actor:None)
    outcome=progress(jobs,key);assert outcome['counts']['Approved']==1 and outcome['counts']['Needs Attention']==1
    rows=bulk.listing(jobs.connect,[PID,pid],ADMIN)['rows'];assert [r['product_gid'] for r in rows]==[pid]
    assert 'Previous approval: Needs Attention' in rows[0]['reason']
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==1


def preview_cases(record,count):
    result=[]
    for n in range(count):
        clone=deepcopy(record);pid='gid://shopify/Product/'+str(n+1);clone['manifest']['source']['product_gid']=pid;rebind(clone)
        result.append((pid,clone['hash'],clone))
    return result


def test_eight_persistent_previews_one_read_zero_provider_calls(ops):
    jobs,sql,record,assets=ops;store=PreviewStore(jobs.connect);cache=bulk.ReviewCache()
    data=cache.get(record,assets.fetch);cases=preview_cases(record,8)
    for pid,digest,current in cases:store.put(ae.fingerprint(cache.key(current)),data)
    bulk.thumbnails.entries.clear()
    with patch.object(store,'get_many',wraps=store.get_many) as reads,patch.object(bulk.runtime,'storage',side_effect=AssertionError('No provider access')):
        rows=bulk.cached_previews(cases,store)
    assert len(rows)==8 and all(r['jpeg'] for r in rows);reads.assert_called_once()
    # The memory path subsequently needs no cache connection at all.
    assert all(r['jpeg'] for r in bulk.cached_previews(cases,Mock(get_many=Mock(side_effect=AssertionError('Warm memory read')))))


def test_cache_batch_miss_never_starts_cold_generation(ops):
    jobs,sql,record,assets=ops;bulk.thumbnails.entries.clear()
    with patch.object(bulk.thumbnails,'get',side_effect=AssertionError('Cold decoder must not run inside cached batch')):
        assert bulk.cached_previews([(PID,record['hash'],record)],PreviewStore(jobs.connect))[0]['jpeg'] is None


def test_persisted_hit_bypasses_occupied_build_stripe(ops):
    jobs,sql,record,assets=ops;store=PreviewStore(jobs.connect);cache=bulk.ReviewCache();cache.get(record,assets.fetch,300,store)
    cache=bulk.ReviewCache();stripe=cache.build_locks[int(cache.key(record)[0][:8],16)%64]
    with ThreadPoolExecutor(max_workers=1) as pool:
        stripe.acquire()
        try:
            data=pool.submit(cache.get,record,lambda *args:(_ for _ in ()).throw(AssertionError('No download')),300,store).result(timeout=1)
            assert data
        finally:stripe.release()


def test_cached_preview_endpoint_auth_limits_and_actor_snapshot_scope(ops):
    jobs,sql,record,assets=ops
    async def admin(*args,**kwargs):return ADMIN
    async def check():
        bulk.snapshots.clear();body=dict(items=[item(record)])
        with patch.object(bulk,'actor',side_effect=admin),patch('auto_editions_bulk_runtime.connection',jobs.connect):
            assert (await bulk.previews_api(request('POST',body=body))).status_code==409
            bulk.listing(jobs.connect,[PID],ADMIN)
            assert (await bulk.previews_api(request('POST',body=body))).status_code==200
            assert (await bulk.previews_api(request('POST',body=dict(items=[item(record)]*9)))).status_code==409
            bulk.snapshots.clear()
    asyncio.run(check())


def test_measured_actual_loopback_http_preview_batch_vs_individual_requests(ops):
    import socket
    import urllib.request
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route
    jobs,sql,record,assets=ops;store=PreviewStore(jobs.connect);cases=preview_cases(record,24)
    data=bulk.ReviewCache().get(record,assets.fetch)
    for pid,digest,current in cases:
        store.put(ae.fingerprint(bulk.thumbnails.key(current)),data)
        bulk.snapshots[(str(ADMIN['id']),pid,digest)]=(time.monotonic()+900,current)
    auth_calls=[]
    async def auth(*args,**kwargs):
        auth_calls.append(1);await asyncio.sleep(.08);return ADMIN
    app=Starlette(routes=[Route('/api/auto-editions/bulk/image',bulk.image_api),Route('/api/auto-editions/bulk/previews',bulk.previews_api,methods=['POST'])])
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    from urllib.parse import urlencode
    with patch.object(bulk,'actor',side_effect=auth),patch('auto_editions_bulk_runtime.connection',jobs.connect),patch.object(bulk.runtime,'storage',side_effect=AssertionError('No provider should be used')):
        thread.start()
        while not server.started:time.sleep(.01)
        try:
            def individual(case):
                pid,digest,_=case
                with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/api/auto-editions/bulk/image?'+urlencode(dict(product_gid=pid,hash=digest))) as response:return response.read()
            start=time.perf_counter()
            with ThreadPoolExecutor(max_workers=3) as pool:assert all(pool.map(individual,cases))
            before=(time.perf_counter()-start)*1000;before_auth=len(auth_calls);auth_calls.clear();bulk.thumbnails.entries.clear()
            def grouped(group):
                request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/auto-editions/bulk/previews',data=json.dumps(dict(items=[dict(product_gid=p,hash=h) for p,h,_ in group])).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as response:return json.loads(response.read())
            start=time.perf_counter()
            with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(grouped,[cases[n:n+8] for n in range(0,24,8)]))
            after=(time.perf_counter()-start)*1000
            assert sum(len(r['rows']) for r in responses)==24 and all(row['jpeg'] for r in responses for row in r['rows'])
            assert before_auth==24 and len(auth_calls)==3
            report=dict(designs=24,before_individual_http_ms=round(before,2),after_batched_http_ms=round(after,2),account_read_latency_model_ms=80,before_auth_reads=before_auth,after_auth_reads=len(auth_calls),provider_calls=0,transport='real loopback HTTP; simulated account-read latency; isolated PostgreSQL; no production data')
            Path('output/bulk-handoff').mkdir(parents=True,exist_ok=True)
            Path('output/bulk-handoff/http-performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        finally:server.should_exit=True;thread.join(5);sock.close()


def test_gallery_recovery_omits_completed_history_without_reprojecting_catalogue(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record);run(jobs,record,assets)
    async def admin(*args,**kwargs):return ADMIN
    async def check():
        with patch.object(bulk,'actor',side_effect=admin),patch('auto_editions_bulk_runtime.connection',jobs.connect),patch.object(bulk.statuses,'batch',side_effect=AssertionError('Gallery must not reproject completed history')):
            response=await bulk.progress_api(request('POST',body=dict(product_gids=[PID])))
            assert response.status_code==200 and json.loads(response.body)['rows']==[]
        assert progress(jobs,key)['counts']['Approved']==1
    asyncio.run(check())


def test_measured_mixed_300_design_catalogue_filters_before_pagination(ops,monkeypatch):
    import ast
    jobs,sql,template,assets=ops;monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false');ids=[];items=[]
    for n in range(1,301):
        pid='gid://shopify/Product/'+str(n);record=deepcopy(template)
        record['manifest']['source'].update(product_gid=pid,file_id='id:source'+str(n));rebind(record);m=record['manifest'];ids.append(pid);items.append(item(record,pid))
        sql.execute("INSERT INTO edition_products VALUES(%s,%s,%s,%s,2,1,true,true)",(pid,str(n),'Synthetic '+str(n),'synthetic-'+str(n)))
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,'/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd','manual','synthetic-admin')",(pid,m['source']['file_id']))
        sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(record['hash'],json.dumps(m),json.dumps(record['proofs']),json.dumps(record['receipts'])))
        sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,preparation_hash,source,edition_total) VALUES(%s,%s,'Blocked',%s,%s::jsonb,2)",(pid,m['source']['file_id'],record['hash'],json.dumps(m['source'])))
    jobs.submit('synthetic-admin',str(uuid.uuid4()),items[:270])
    # Execute the prior shipped listing function/SQL against the identical isolated database.
    baseline=Path('output/bulk-handoff/before-auto_editions_bulk.py')
    if not baseline.exists():
        cursor=0;rows=[];pages=0
        while cursor is not None:
            page=bulk.listing(jobs.connect,ids,ADMIN,cursor);rows.extend(page['rows']);cursor=page['next_cursor'];pages+=1
        assert len(rows)==30 and pages==2
        return  # Timing replay is local evidence, never a dependency for regression checks.
    before=ast.parse(baseline.read_text(encoding='utf-8'))
    old_page=next(ast.literal_eval(n.value) for n in before.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PAGE_SQL' for t in n.targets))
    old_listing=next(n for n in before.body if isinstance(n,ast.FunctionDef) and n.name=='listing')
    namespace={**bulk.__dict__,'PAGE_SQL':old_page};exec(compile(ast.Module(body=[old_listing],type_ignores=[]),'prior-listing','exec'),namespace)
    def scan(function):
        cursor=0;rows=[];pages=0;start=time.perf_counter()
        while cursor is not None:
            data=function(jobs.connect,ids,ADMIN,cursor);rows.extend(data['rows']);cursor=data['next_cursor'];pages+=1
        return rows,pages,round((time.perf_counter()-start)*1000,2)
    with patch.object(bulk.runtime,'storage',side_effect=AssertionError('No provider/worker access')):
        old,old_pages,old_ms=scan(namespace['listing']);new,new_pages,new_ms=scan(bulk.listing)
    assert len(old)==300 and len(new)==30 and old_pages==15 and new_pages==2
    report=dict(catalogue=300,persisted_pending=270,before_metadata_pages=old_pages,after_metadata_pages=new_pages,before_manifests=300,after_manifests=30,before_listing_ms=old_ms,after_listing_ms=new_ms,provider_calls=0,source='Prior shipped listing versus local fix on identical isolated PostgreSQL; no live records')
    Path('output/bulk-handoff').mkdir(parents=True,exist_ok=True)
    Path('output/bulk-handoff/catalogue-performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
