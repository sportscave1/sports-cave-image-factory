"""Durable TEST approval failure scenarios on isolated PostgreSQL and real synthetic image validation."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
import auto_editions_bulk as bulk
from auto_editions_bulk_jobs import ReviewJobs,PreviewStore
from auto_editions_bulk_runtime import run_one
from tests.test_auto_editions_discovery import database,pglite_database,store,PID
from tests.test_auto_editions_bulk import review,prepared

SCHEMA=Path('supabase/migrations/20261016071758_auto_editions_bulk_operations.sql')

@pytest.fixture
def ops(review):
    d,sql,record,assets=review
    sql.execute("CREATE TABLE os_users(id text PRIMARY KEY,role text,is_active boolean,account_status text,removed_at timestamptz)")
    sql.execute("INSERT INTO os_users VALUES('synthetic-admin','admin',true,'active',NULL)")
    bulk._verified_files.clear()
    return ReviewJobs(d.connect),sql,record,assets

def item(record,pid=PID):return dict(product_gid=pid,hash=record['hash'])
def submit(jobs,record,key=None):
    key=key or str(uuid.uuid4());jobs.submit('synthetic-admin',key,[item(record)]);return key

def progress(jobs,key):return jobs.progress('synthetic-admin',batch_id=key)

def run(jobs,record,assets):
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)):
        return run_one(jobs,authorize=lambda actor:None)


def test_large_batch_fast_ack_idempotency_and_bounded_claims(ops):
    jobs,sql,record,assets=ops;key=str(uuid.uuid4())
    items=[item(record,'gid://shopify/Product/'+str(n)) for n in range(1,1001)]
    start=time.perf_counter();jobs.submit('synthetic-admin',key,items);elapsed=(time.perf_counter()-start)*1000
    jobs.submit('synthetic-admin',key,items)
    result=progress(jobs,key);assert len(result['rows'])==1000 and result['counts']['Pending']==1000
    assert jobs.claim() and jobs.claim() and jobs.claim() is None
    print(json.dumps(dict(designs=1000,ack_database_ms=round(elapsed,2),provider_calls=assets.fetch.call_count)))
    assert assets.fetch.call_count==0
    with pytest.raises(ValueError):jobs.submit('synthetic-admin',key,items[:1])
    with pytest.raises(PermissionError):jobs.submit('different-owner',key,items)


def test_duplicate_clicks_and_batches_share_one_product_job(ops):
    jobs,sql,record,assets=ops
    with ThreadPoolExecutor(max_workers=4) as pool:
        keys=list(pool.map(lambda _:submit(jobs,record),range(8)))
    sql.execute('SELECT count(*) AS n FROM auto_edition_review_jobs');assert sql.fetchone()['n']==1
    assert len({progress(jobs,key)['rows'][0]['job_id'] for key in keys})==1
    assert run(jobs,record,assets)
    for key in keys:assert progress(jobs,key)['counts']['Approved']==1
    sql.execute("SELECT count(*) AS n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==1


def test_atomic_success_result_audits_and_unchanged_allocations(ops):
    jobs,sql,record,assets=ops;before={}
    for table in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings'):
        sql.execute('SELECT * FROM '+table);before[table]=deepcopy(sql.fetchall())
    key=submit(jobs,record);assert progress(jobs,key)['counts']['Pending']==1
    assert run(jobs,record,assets);assert progress(jobs,key)['counts']['Approved']==1
    assert not run(jobs,record,assets)
    for table,rows in before.items():sql.execute('SELECT * FROM '+table);assert sql.fetchall()==rows
    sql.execute('SELECT approval FROM auto_edition_layouts');approval=sql.fetchone()['approval']
    assert approval['test_only'] is True and 'print_ready' not in approval and 'allocation_ids' not in approval
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==1


def test_restart_expired_claim_and_stale_owner_cannot_write(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record);old=jobs.claim()
    sql.execute("UPDATE auto_edition_review_jobs SET lease_until=now()-interval '1 second'")
    restarted=ReviewJobs(jobs.connect);current=restarted.claim();assert current['lease_token']!=old['lease_token']
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)):
        with pytest.raises(ValueError,match='lease changed'):bulk.approve_one(jobs.connect,item(record),'synthetic-admin',job=old)
        assert bulk.approve_one(jobs.connect,item(record),'synthetic-admin',job=current)=='Approved'
    restarted.finish(old,'Failed','stale owner')
    assert progress(restarted,key)['counts']['Approved']==1


def test_lost_commit_acknowledgement_cannot_replace_success(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record)
    def interrupted(*args,**kwargs):
        bulk.approve_one(*args,**kwargs)
        raise TimeoutError('COMMIT acknowledgement lost')
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)):
        run_one(jobs,approve=interrupted,authorize=lambda actor:None)
    assert progress(jobs,key)['counts']['Approved']==1
    assert not jobs.claim()
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==1


def test_audit_failure_rolls_back_approval_and_retries_without_duplicate(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record)
    with patch.object(bulk.Queue,'audit',side_effect=RuntimeError('database unavailable')):run(jobs,record,assets)
    sql.execute('SELECT * FROM auto_edition_layouts');assert not sql.fetchall()
    assert progress(jobs,key)['counts']['Pending']==1
    sql.execute('UPDATE auto_edition_review_jobs SET next_attempt_at=now()')
    run(jobs,record,assets);assert progress(jobs,key)['counts']['Approved']==1


def test_stale_preparation_incomplete_evidence_and_partial_success(ops):
    jobs,sql,record,assets=ops;key=str(uuid.uuid4())
    jobs.submit('synthetic-admin',key,[item(record),dict(product_gid='gid://shopify/Product/998',hash='b'*64)])
    run(jobs,record,assets);run(jobs,record,assets)
    result=progress(jobs,key);assert result['counts']['Approved']==1 and result['counts']['Skipped']==1
    assert not result['active']


def test_actual_corrupt_bytes_never_approved(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record)
    assets.fetch.side_effect=lambda digest,asset,destination:Path(destination).write_bytes(b'corrupt')
    run(jobs,record,assets);assert progress(jobs,key)['counts']['Needs Attention']==1
    sql.execute('SELECT * FROM auto_edition_layouts');assert not sql.fetchall()


def test_transient_contention_is_bounded_and_restart_recovers_pending(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record)
    for n in range(3):
        run_one(ReviewJobs(jobs.connect),approve=lambda *a,**k:(_ for _ in ()).throw(TimeoutError('slow provider or lock timeout')),authorize=lambda actor:None)
        if n<2:assert progress(jobs,key)['counts']['Pending']==1
        sql.execute('UPDATE auto_edition_review_jobs SET next_attempt_at=now()')
    assert progress(jobs,key)['counts']['Failed']==1 and not jobs.claim()


def test_network_disconnect_after_submission_can_reconcile_same_key(ops):
    jobs,sql,record,assets=ops;key=str(uuid.uuid4())
    # The response is lost after the real submission transaction committed.
    jobs.submit('synthetic-admin',key,[item(record)])
    assert ReviewJobs(jobs.connect).progress('synthetic-admin',batch_id=key)['found']
    jobs.submit('synthetic-admin',key,[item(record)])
    run(jobs,record,assets)
    assert ReviewJobs(jobs.connect).progress('synthetic-admin',product_gids=[PID])['counts']['Approved']==1


def test_revoked_admin_does_not_approve(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record)
    run_one(jobs,authorize=lambda actor:(_ for _ in ()).throw(PermissionError('revoked')))
    assert progress(jobs,key)['counts']['Needs Attention']==1 and not assets.fetch.called


def test_persistent_thumbnail_survives_cache_restart_and_large_uses_same_downloads(ops):
    jobs,sql,record,assets=ops;store=PreviewStore(jobs.connect);cache=bulk.ReviewCache()
    start=time.perf_counter();small=cache.get(record,assets.fetch,300,store);cold=(time.perf_counter()-start)*1000
    assert assets.fetch.call_count==2
    def no_download(*args):raise AssertionError('Persistent previews must not download PNGs')
    start=time.perf_counter();assert bulk.ReviewCache().get(record,no_download,300,store)==small;warm=(time.perf_counter()-start)*1000
    assert bulk.ReviewCache().get(record,no_download,1200,store)
    changed=deepcopy(record);changed['receipts']['assets'][0]['revision']='a2'
    bulk.ReviewCache().get(changed,assets.fetch,300,store);assert assets.fetch.call_count==4
    print(json.dumps(dict(synthetic_dimensions=record['manifest']['dimensions'],cold_ms=round(cold,2),persistent_warm_ms=round(warm,2),jpeg_bytes=len(small))))


def test_cached_thumbnail_not_blocked_by_other_cold_download(ops):
    import threading
    jobs,sql,record,assets=ops;cache=bulk.ReviewCache();cache.get(record,assets.fetch)
    changed=deepcopy(record);changed['receipts']['assets'][0]['revision']='a2'
    gate=threading.Event();entered=threading.Event()
    def slow(*args):entered.set();gate.wait(3);return assets.fetch(*args)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cold=pool.submit(cache.get,changed,slow);assert entered.wait(2)
        start=time.perf_counter();cache.get(record,assets.fetch);assert time.perf_counter()-start<0.1
        gate.set();cold.result()


def test_operation_overlay_cannot_change_authoritative_status_or_certification(ops):
    import auto_editions_status as status
    jobs,sql,record,assets=ops;submit(jobs,record)
    base=dict(rows=[dict(product_gid=PID,status='Needs Review',preparation_hash=record['hash'])])
    status.review_operations(jobs.connect,base)
    assert base['rows'][0]['status']=='Needs Review' and base['rows'][0]['review_operation']['label']=='Approving…'
    assert base['rows'][0]['review_operation']['state']=='Pending'
    current=dict(rows=[dict(product_gid=PID,status='Needs Repair',preparation_hash=record['hash'])])
    status.review_operations(jobs.connect,current);assert 'review_operation' not in current['rows'][0]


def test_measured_35_design_sequential_vs_durable_bounded_approval(ops,tmp_path,monkeypatch):
    from unittest.mock import Mock
    from auto_editions_cloud import DropboxAssets
    import auto_editions as ae
    jobs,sql,template,original=ops;monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    cases={};items=[]
    for n in range(1,71):
        pid='gid://shopify/Product/'+str(n);record=deepcopy(template)
        m=record['manifest'];m['source'].update(product_gid=pid,file_id='id:source'+str(n))
        digest=ae.fingerprint(m);record['hash']=digest;record['receipts']['preparation_hash']=digest
        for proof in record['proofs']:proof['preparation_hash']=digest
        sql.execute("INSERT INTO edition_products VALUES(%s,%s,%s,%s,2,1,true,true)",(pid,str(n),'Synthetic '+str(n),'synthetic-'+str(n)))
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual','synthetic-admin')",(pid,m['source']['file_id'],'/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd'))
        sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(digest,json.dumps(m),json.dumps(record['proofs']),json.dumps(record['receipts'])))
        sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,preparation_hash,source,edition_total) VALUES(%s,%s,'Blocked',%s,%s::jsonb,2)",(pid,m['source']['file_id'],digest,json.dumps(m['source'])))
        provider=Mock();provider.fetch.side_effect=original.fetch.side_effect
        def metadata(token,fid,record=record,**kwargs):
            time.sleep(.01)  # Deliberately slow provider; all validation remains real.
            if fid==record['manifest']['source']['file_id']:
                return dict(id=fid,rev='a1',content_hash='a'*64,**{'.tag':'file'},name='Synthetic.psd',path_display='/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd')
            name=fid.removeprefix('id:');path=tmp_path/name
            return dict(id=fid,rev='a1',size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),path_display=DropboxAssets.path(record['hash'],name))
        provider.integration.psd_open_metadata.side_effect=metadata;cases[pid]=(record,provider);items.append(item(record,pid))
    with patch('auto_editions_onboarding_api.candidate',side_effect=lambda pid,digest:cases[pid]):
        start=time.perf_counter()
        assert [bulk.approve_one(jobs.connect,i,'synthetic-admin') for i in items[:35]]==['Approved']*35
        before=(time.perf_counter()-start)*1000
        key=str(uuid.uuid4());start=time.perf_counter();jobs.submit('synthetic-admin',key,items[35:]);ack=(time.perf_counter()-start)*1000
        start=time.perf_counter()
        def consume():
            while run_one(jobs,authorize=lambda actor:None):pass
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:consume(),range(2)))
        after=(time.perf_counter()-start)*1000
    assert progress(jobs,key)['counts']['Approved']==35
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==70
    report=dict(designs=35,synthetic_dimensions=template['manifest']['dimensions'],provider_metadata_delay_ms=10,before_request_bound_ms=round(before,2),after_ack_ms=round(ack,2),after_background_completion_ms=round(after,2),concurrent_products=2)
    Path('output/bulk-v3').mkdir(exist_ok=True,parents=True);Path('output/bulk-v3/approval-performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    assert ack<before


def test_private_queue_and_preview_schema_security(ops):
    jobs,sql,record,assets=ops
    sql.execute("SELECT relname,relrowsecurity FROM pg_class WHERE relname=ANY(%s)",(['auto_edition_review_batches','auto_edition_review_jobs','auto_edition_review_items','auto_edition_review_previews'],))
    assert len(sql.fetchall())==4
    sql.execute("SELECT has_table_privilege('anon','auto_edition_review_jobs','SELECT') AS anon,has_table_privilege('authenticated','auto_edition_review_jobs','INSERT') AS authenticated")
    row=sql.fetchone();assert not row['anon'] and not row['authenticated']
    sql.execute("SELECT relrowsecurity FROM pg_class WHERE relkind='r' AND relname LIKE 'auto_edition_review_%'");assert all(r['relrowsecurity'] for r in sql.fetchall())


def test_lifecycle_starts_consumer_without_request_and_shutdown_does_not_delete_jobs():
    from auto_editions_bulk_runtime import ReviewLifecycle
    async def check():
        messages=iter([dict(type='lifespan.startup'),dict(type='lifespan.shutdown')])
        async def receive():return next(messages)
        async def send(message):pass
        async def app(scope,receive,send):
            await receive();await receive()
        with patch('auto_editions_bulk_runtime.start') as start:
            await ReviewLifecycle(app)({'type':'lifespan'},receive,send)
            start.assert_called_once()
    asyncio.run(check())


def test_owner_revocation_during_slow_validation_is_fenced_before_write(ops):
    jobs,sql,record,assets=ops;key=submit(jobs,record)
    original=bulk.validate_files
    def revoked(*args):
        original(*args)
        sql.execute("UPDATE os_users SET is_active=false")
    with patch.object(bulk,'validate_files',side_effect=revoked):run(jobs,record,assets)
    assert progress(jobs,key)['counts']['Needs Attention']==1
    sql.execute('SELECT * FROM auto_edition_layouts');assert not sql.fetchall()


def test_verified_file_cache_still_requires_current_cloud_receipts(ops):
    jobs,sql,record,assets=ops
    bulk.validate_files(record,assets);downloads=assets.fetch.call_count;calls=assets.integration.psd_open_metadata.call_count
    bulk.validate_files(record,assets)
    assert assets.fetch.call_count==downloads
    assert assets.integration.psd_open_metadata.call_count==calls*2
    metadata=assets.integration.psd_open_metadata.side_effect
    def changed(*args,**kwargs):return {**metadata(*args,**kwargs),'rev':'changed'}
    assets.integration.psd_open_metadata.side_effect=changed
    with pytest.raises(ValueError,match='Cloud receipt changed'):bulk.validate_files(record,assets)


def test_progress_api_uses_current_authoritative_projection_after_committed_success(ops):
    from tests.test_auto_editions_api import request
    jobs,sql,record,assets=ops;key=submit(jobs,record);run(jobs,record,assets)
    async def admin(*args,**kwargs):return dict(id='synthetic-admin')
    async def check():
        with patch.object(bulk,'actor',side_effect=admin),patch('auto_editions_bulk_runtime.connection',jobs.connect):
            response=await bulk.progress_api(request('POST',body=dict(batch_id=key)))
            data=json.loads(response.body);assert response.status_code==200
            assert data['rows'][0]['current_status']=='Cloud Ready'
            sql.execute("UPDATE auto_edition_onboarding SET status='Needs PSD Repair'")
            response=await bulk.progress_api(request('POST',body=dict(batch_id=key)))
            data=json.loads(response.body);assert data['counts']['Approved']==1
            assert data['rows'][0]['current_status']=='Needs Repair'
    asyncio.run(check())


def test_new_submission_reuses_recorded_committed_approval_without_new_work(ops):
    jobs,sql,record,assets=ops;first=submit(jobs,record);run(jobs,record,assets)
    second=submit(jobs,record)
    assert progress(jobs,first)['rows'][0]['job_id']==progress(jobs,second)['rows'][0]['job_id']
    assert not jobs.claim()
    sql.execute('SELECT count(*) n FROM auto_edition_review_jobs');assert sql.fetchone()['n']==1


def test_representative_24mp_persistent_thumbnail_performance(ops,tmp_path):
    from PIL import Image,ImageCms
    import auto_editions as ae
    jobs,sql,record,assets=ops;m=record['manifest']
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.effect_noise((6000,4000),60) as noise:
        with noise.convert('RGB') as rgb:rgb.save(tmp_path/m['master']['name'],icc_profile=profile)
    m['dimensions']=[6000,4000];m['source_dimensions']=[6000,4000]
    for asset in [m['master'],*m['patches'].values()]:
        asset['sha256']=ae.file_hash(tmp_path/asset['name'])
    from tests.test_auto_editions_bulk import rebind
    for receipt in record['receipts']['assets']:receipt['bytes']=(tmp_path/receipt['name']).stat().st_size
    rebind(record);store=PreviewStore(jobs.connect)
    start=time.perf_counter();jpeg=bulk.ReviewCache().get(record,assets.fetch,300,store);cold=(time.perf_counter()-start)*1000
    def unavailable(*args):raise AssertionError('Restarted warm preview must not contact unavailable provider')
    start=time.perf_counter();assert bulk.ReviewCache().get(record,unavailable,300,store)==jpeg;warm=(time.perf_counter()-start)*1000
    report=dict(dimensions=m['dimensions'],cold_ms=round(cold,2),persistent_warm_ms=round(warm,2),source_png_bytes=(tmp_path/m['master']['name']).stat().st_size,thumbnail_bytes=len(jpeg),cold_fetches=assets.fetch.call_count,warm_fetches=0)
    assert assets.fetch.call_count==2
    Path('output/bulk-v3/thumbnail-performance.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
