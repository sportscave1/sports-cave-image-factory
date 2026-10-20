"""V17 opt-in continuous policy against synthetic identities/native isolated SQL."""
import asyncio,json
from pathlib import Path
from unittest.mock import patch,Mock
import pytest
import auto_editions as ae
import auto_editions_v17 as v17
import auto_editions_status as status
import auto_editions_onboarding_api as api
import auto_editions_runtime as runtime
from auto_editions_store import Preparations
from auto_editions_priority import priority
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID,rows
from tests.test_auto_editions import package
from tests.test_auto_editions_api import request,ADMIN,VA


@pytest.fixture
def continuous(store,monkeypatch):
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','true')
    return store


def mapping(sql,n,total=100):
    pid='gid://shopify/Product/'+str(n);fid='id:source'+str(n)
    sql.execute('INSERT INTO edition_products VALUES(%s,%s,%s,%s,%s,37,true,true)',(pid,str(n),'Art '+str(n),'art-'+str(n),total))
    import psd_directory as psd
    sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual','owner')",(pid,fid,psd.ROOT+'/Art '+str(n)+'.psd'))
    return pid,fid


def test_v17_sales_then_advertisements_then_all_remaining(monkeypatch):
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','true')
    no_sales=dict(active=False,sales=0,outstanding=0,recent=0,advertised=False)
    assert priority(no_sales)[0]==1
    assert priority({**no_sales,'sales':20,'recent':True,'advertised':True})[0]==7
    assert priority({**no_sales,'outstanding':1,'advertised':True})[0]==8
    assert priority({**no_sales,'outstanding':1},10)[0]==8
    assert priority(no_sales,10)[0]==10
    monkeypatch.delenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED');assert priority(no_sales)[0]==0


def test_existing_167_deferred_are_drained_without_remapping_or_allocation(continuous):
    d,sql=continuous
    for n in range(1000,1167):
        pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'owner',newly_linked=False)
    sql.execute("UPDATE auto_edition_onboarding SET priority=0")
    protected=lambda:(rows(sql,'edition_products'),rows(sql,'edition_allocations'),rows(sql,'synthetic_certificates'),rows(sql,'product_psd_mappings'))
    before=protected();seen=set()
    while job:=d.queue.claim('host'):
        assert job['product_gid'] not in seen;seen.add(job['product_gid'])
        # Terminal failure/review must release the queue for the next design.
        d.queue.checkpoint(job['product_gid'],str(job['lease_token']),'host','Blocked','Synthetic design needs review')
    assert len(seen)==167
    assert len(rows(sql,'auto_edition_onboarding'))==167 and protected()==before


def test_new_paid_order_preempts_next_catalogue_job_but_never_active_job(continuous):
    d,sql=continuous
    catalogue=[]
    for n in (1000,1001,1002):
        pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'owner',newly_linked=False);catalogue.append(pid)
    active=d.queue.claim('host');assert active['product_gid']==catalogue[0]
    sql.execute('UPDATE auto_edition_onboarding SET priority=8,updated_at=now() WHERE product_gid=%s',(catalogue[2],))
    sql.execute('UPDATE auto_edition_onboarding SET priority=7 WHERE product_gid=%s',(catalogue[1],))
    assert d.queue.claim('second-host') is None
    d.queue.checkpoint(active['product_gid'],str(active['lease_token']),'host','Blocked','Review')
    urgent=d.queue.claim('host');assert urgent['product_gid']==catalogue[2]
    d.queue.checkpoint(urgent['product_gid'],str(urgent['lease_token']),'host','Blocked','Repair')
    assert d.queue.claim('host')['product_gid']==catalogue[1]


def test_rollback_immediately_pauses_new_catalogue_claims_and_preserves_rows(continuous,monkeypatch):
    d,sql=continuous;pid,fid=mapping(sql,1000);d.queue.enqueue(pid,fid,'owner',newly_linked=False)
    before=rows(sql,'auto_edition_onboarding');assert before[0]['priority']==1
    monkeypatch.delenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED');assert d.queue.claim('host') is None
    assert rows(sql,'auto_edition_onboarding')==before
    monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED','true');assert d.queue.claim('host')['product_gid']==pid


def test_paid_work_wins_over_manual_catalogue_request(continuous):
    d,sql=continuous
    manual,fid=mapping(sql,1000);d.queue.enqueue(manual,fid,'owner');d.queue.prepare_now(manual,'owner')
    paid,fid=mapping(sql,1001);d.queue.enqueue(paid,fid,'owner')
    sql.execute('UPDATE auto_edition_onboarding SET priority=8 WHERE product_gid=%s',(paid,))
    assert d.queue.claim('host')['product_gid']==paid


def test_late_mapping_is_seeded_after_old_bootstrap_finished(continuous):
    d,sql=continuous
    assert d.seed_existing()==0
    pid,fid=mapping(sql,1000)
    assert d.seed_existing()==1 and d.seed_existing()==0
    assert d.queue.claim('host')['product_gid']==pid


def test_new_product_and_late_original_auto_join_without_resume(continuous):
    d,sql=continuous;register(continuous);tick(continuous)
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Waiting for PSD'
    tick(continuous,[asset()]);register(continuous,'duplicate');tick(continuous)
    assert len(rows(sql,'auto_edition_onboarding'))==1
    assert d.queue.claim('host')['product_gid']==PID


def test_invalid_limit_or_changed_mapping_never_stalls_valid_catalogue(continuous):
    d,sql=continuous
    bad,fid=mapping(sql,1000,0);d.queue.enqueue(bad,fid,'owner',newly_linked=False)
    good,fid=mapping(sql,1001);d.queue.enqueue(good,fid,'owner',newly_linked=False)
    assert d.queue.claim('host')['product_gid']==good
    value=status.batch(d.connect,[bad])['rows'][0];assert value['status']=='Needs Repair'


@pytest.fixture
def prepared(continuous,tmp_path):
    d,sql=continuous;register(continuous);tick(continuous,[asset()])
    sql.execute('UPDATE edition_products SET edition_total=2 WHERE shopify_product_gid=%s',(PID,))
    lease=d.queue.claim('owner');manifest=package(tmp_path);manifest['source']=ae.source_identity(PID,asset())
    digest=ae.fingerprint(manifest)
    proofs=[dict(preparation_hash=digest,number=n,pixel_exact=True) for n in (1,2)]+[dict(preparation_hash=digest,outside_number_exact=True)]
    receipts=dict(preparation_hash=digest,assets=[dict(name=name,file_id='id:cloud'+str(i),revision='b1',bytes=(tmp_path/name).stat().st_size) for i,name in enumerate(['master.png','number-1.png','number-2.png'])])
    registry=Preparations(d.connect);registry.save(manifest,proofs,receipts,'owner')
    d.queue.checkpoint(PID,str(lease['lease_token']),'owner','Preparing',source=manifest['source'],total=2)
    d.queue.checkpoint(PID,str(lease['lease_token']),'owner','Blocked','Uploaded; needs review',digest=digest)
    return d,sql,registry,manifest,digest


def test_uploaded_needs_review_then_existing_human_approval_reused(prepared):
    d,sql,registry,manifest,digest=prepared
    first=status.batch(d.connect,[PID])['rows'][0];assert first['status']=='Needs Review' and first['uploaded']
    assert d.queue.claim('host') is None
    registry.approve(digest,dict(shopify_product_gid=PID,shopify_variant_id='*'),'original-owner')
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready' WHERE product_gid=%s",(PID,))
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Cloud Ready'
    assert d.queue.imported_state(PID,digest,manifest['source'])=='Cloud Ready'
    assert d.queue.imported_state(PID,digest,{**manifest['source'],'revision':'changed'})=='Blocked'
    before=rows(sql,'auto_edition_layouts');d.queue.enqueue(PID,'id:original','again')
    assert d.queue.claim('host') is None and rows(sql,'auto_edition_layouts')==before
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,None)),patch.object(runtime,'storage') as remote:
        assert runtime.download_links([dict(id=1,shopify_product_gid=PID,shopify_variant_id='variant')])['1'].endswith('#Download JPG')
    remote.assert_not_called()


def test_incomplete_receipts_cannot_claim_ready_or_serve_approved_jpg(prepared):
    d,sql,registry,manifest,digest=prepared
    registry.approve(digest,dict(shopify_product_gid=PID,shopify_variant_id='*'),'original-owner')
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready' WHERE product_gid=%s",(PID,))
    sql.execute("UPDATE auto_edition_preparations SET receipts=receipts||'{\"assets\":[]}'::jsonb WHERE hash=%s",(digest,))
    row=status.batch(d.connect,[PID])['rows'][0];assert row['status']=='Needs Review' and not row['uploaded']
    assert d.queue.imported_state(PID,digest,manifest['source'])=='Blocked'
    with patch.object(runtime,'enabled',return_value=True),patch.object(runtime,'stores',return_value=(registry,None)):
        assert runtime.download_links([dict(id=1,shopify_product_gid=PID,shopify_variant_id='variant')])['1'].endswith('#Needs Review')


def test_summary_counts_are_authoritative_and_do_not_expose_capabilities(prepared):
    d,sql,registry,manifest,digest=prepared
    with patch.object(api,'queue',return_value=d.queue),patch.object(api.api,'actor',return_value=ADMIN):
        response=asyncio.run(api.summary(request('GET')))
    assert response.status_code==200,response.body
    body=json.loads(response.body);assert body['continuous_enabled']
    assert body['counts']['Total mapped']==1 and body['counts']['Needs Review']==1 and body['counts']['Uploaded']==1 and body['counts']['Remaining']==1
    assert 'lease_token' not in response.body.decode() and 'secret' not in response.body.decode()


def test_failed_upload_recovery_does_not_monopolise_catalogue(tmp_path,monkeypatch):
    import sys,requests
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'));import auto_editions_local as local
    from companion_transfer import Controller
    controller=Controller();controller.configure({'mode':'Maximum speed'})
    monkeypatch.setattr(local,'transfer_controller',lambda:controller)
    package=tmp_path/'prepared.zip';package.write_bytes(b'preserved')
    row=dict(context={'automatic':True},folder=tmp_path,grant={'base_url':'https://sports-cave-image-factory.onrender.com','ticket':'a','secret':'b'},status='Working',recovery_failures=2)
    with patch.object(local,'cancellation_check',return_value=False),patch.object(local,'JOBS',{'job':row}),patch('requests.Session.send',side_effect=requests.ConnectionError()),patch.object(local,'reconnect'),patch.object(local,'report_failure') as report:
        local.upload_prepared('job',package)
    assert row['status']=='Blocked' and package.read_bytes()==b'preserved';report.assert_called_once()


def test_334_row_enabled_status_cost_and_permissions(prepared,monkeypatch):
    import statistics,tracemalloc
    d,sql,*_=prepared
    for n in range(1000,1284):
        pid,fid=mapping(sql,n);d.queue.enqueue(pid,fid,'fixture',newly_linked=False)
    ids=[PID]+['gid://shopify/Product/'+str(n) for n in range(1000,1333)]
    results={}
    for name,flag in [('continuous_off','false'),('continuous_on','true')]:
        monkeypatch.setenv('AUTO_EDITIONS_V17_CONTINUOUS_ENABLED',flag)
        times=[];tracemalloc.start()
        for _ in range(7):
            result=status.batch(d.connect,ids);times.append(result['duration_ms'])
            assert result['query_count']==1 and len(result['rows'])==334
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        results[name]=dict(median_ms=statistics.median(times),peak_bytes=peak,response_bytes=len(json.dumps(result).encode()),queries=1,dropbox_calls=0)
        assert results[name]['median_ms']<1000
    out=Path(__file__).parents[1]/'output/v17/performance.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(results,indent=2))
    with patch.object(api.api,'actor',side_effect=PermissionError('Administrator required.')),patch.object(api,'queue') as forbidden:
        assert asyncio.run(api.summary(request('GET'))).status_code==403
    forbidden.assert_not_called()


def test_recovery_rotates_past_twenty_completed_packages(tmp_path,monkeypatch):
    import os,sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/studio'));import auto_editions_local as local
    monkeypatch.setattr(local,'HOST_FILE',tmp_path/'host.dpapi');monkeypatch.setattr(local,'RECOVERY_CURSOR',0)
    ctx=dict(automatic=True,product_gid=PID,lease_token='owned',source={'revision':'a1'})
    for n in range(25):
        folder=tmp_path/str(n);folder.mkdir();path=folder/'job-state.json'
        path.write_text(json.dumps(dict(context=ctx,status='Prepared' if n else 'Working')))
        os.utime(path,(n+1,n+1))
    with patch.object(local,'host_request',return_value={'grant':{'owned':True}}) as remote,patch.object(local,'start') as start:
        assert local.recover_retained({}) is False;remote.assert_not_called()
        assert local.recover_retained({}) is True;start.assert_called_once()
        assert start.call_args.kwargs['resume_folder']==tmp_path/'0'
