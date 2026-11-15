"""Batch acceptance/expiry regression checks against disposable SQL and real JPEGs."""
import asyncio
import ast
from copy import deepcopy
import json
import subprocess
from pathlib import Path
import time
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
import auto_editions as ae
import auto_editions_bulk as bulk
import auto_editions_status as status
from auto_editions_bulk_jobs import ReviewJobs, PreviewStore
from auto_editions_bulk_runtime import run_one
from tests.test_auto_editions_bulk import rebind
from tests.test_auto_editions_bulk_jobs import ops, review, store, database, pglite_database, item, PID
from tests.test_auto_editions_api import request

USER=dict(id='synthetic-admin',role='admin',is_active=True,page_permissions=[])


def historical_baseline():
    # These comparisons measure the release before the reliability fix. HEAD now
    # includes that fix, so using HEAD would compare the fixed code with itself.
    revision='f586cbfa09e9f8e4283796cd9c90f18b861491bc'
    result=subprocess.run(['git','show',revision+':auto_editions_bulk.py'],capture_output=True)
    if result.returncode:
        pytest.skip('Historical benchmark baseline unavailable in this Git checkout: '+revision)
    return ast.parse(result.stdout.decode('utf-8'))


@pytest.fixture
def catalogue(ops,monkeypatch):
    jobs,sql,template,assets=ops;monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    cases={}
    for n in range(1,37):
        pid='gid://shopify/Product/'+str(n);r=deepcopy(template)
        r['manifest']['source'].update(product_gid=pid,file_id='id:source'+str(n));rebind(r)
        sql.execute("INSERT INTO edition_products VALUES(%s,%s,%s,%s,2,1,true,true)",(pid,str(n),'Synthetic '+str(n),'synthetic-'+str(n)))
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual','synthetic-admin')",(pid,r['manifest']['source']['file_id'],'/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd'))
        sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(r['hash'],json.dumps(r['manifest']),json.dumps(r['proofs']),json.dumps(r['receipts'])))
        sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,preparation_hash,source,edition_total) VALUES(%s,%s,'Blocked',%s,%s::jsonb,2)",(pid,r['manifest']['source']['file_id'],r['hash'],json.dumps(r['manifest']['source'])))
        provider=Mock();provider.fetch.side_effect=assets.fetch.side_effect
        def metadata(token,fid,r=r,**kwargs):
            from auto_editions_cloud import DropboxAssets
            if fid==r['manifest']['source']['file_id']:
                return dict(id=fid,rev='a1',content_hash='a'*64,**{'.tag':'file'},name='Synthetic.psd',path_display='/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd')
            value=assets.integration.psd_open_metadata(token,fid,**kwargs)
            value['path_display']=DropboxAssets.path(r['hash'],fid.removeprefix('id:'));return value
        provider.integration.psd_open_metadata.side_effect=metadata;cases[pid]=(r,provider)
    return jobs,sql,cases


def accept(jobs,items,key=None):
    key=key or str(uuid.uuid4())
    with patch.object(bulk,'actor',new=AsyncMock(return_value=USER)),patch('auto_editions_bulk_runtime.connection',jobs.connect):
        response=asyncio.run(bulk.approve_api(request('POST',body=dict(request_id=key,items=items,confirm_visual_quality=True))))
    assert response.status_code==202,response.body
    return key,json.loads(response.body)


def test_entire_selection_receipted_before_any_worker_claim_and_refresh(catalogue):
    jobs,sql,cases=catalogue;items=[item(r,pid) for pid,(r,_) in cases.items()]
    start=time.perf_counter();key,result=accept(jobs,items);ack=(time.perf_counter()-start)*1000
    assert len(result['rows'])==36 and result['counts']['Pending']==36
    assert {r['acceptance'] for r in result['rows']}=={'accepted'}
    jobs.claim();jobs.claim();assert jobs.claim() is None
    # Reproduce the shipped projection on the same durably queued records.
    baseline=ast.parse(subprocess.check_output(['git','show','HEAD:auto_editions_status.py']).decode('utf-8'))
    function=next(n for n in baseline.body if isinstance(n,ast.FunctionDef) and n.name=='review_operations')
    namespace=dict(status.__dict__);exec(compile(ast.Module(body=[function],type_ignores=[]),'shipped-status','exec'),namespace)
    before=namespace['review_operations'](jobs.connect,status.batch(jobs.connect,list(cases),writable=True))
    before_spinners=sum(r.get('review_operation',{}).get('label')=='Approving\u2026' for r in before['rows'])
    current=status.review_operations(jobs.connect,status.batch(jobs.connect,list(cases),writable=True))
    assert len(current['rows'])==36 and all(r['review_operation']['label']=='Approving\u2026' for r in current['rows'])
    restarted=ReviewJobs(jobs.connect);restored=restarted.progress(USER['id'],product_gids=list(cases))
    assert restored['counts']['Pending']==34 and restored['counts']['Processing']==2
    _,duplicate=accept(jobs,items,key);assert {r['job_id'] for r in result['rows']}=={r['job_id'] for r in duplicate['rows']}
    _,again=accept(jobs,items);assert {r['acceptance'] for r in again['rows']}=={'already_processing'}
    sql.execute('SELECT count(*) n FROM auto_edition_review_jobs');assert sql.fetchone()['n']==36
    assert all(provider.fetch.call_count==0 for _,provider in cases.values())
    print(json.dumps(dict(measurement='current actual approval handler, disposable SQL, no provider latency',selected=36,accepted=36,ack_ms=round(ack,2),processing=2,pending=34,shipped_approving_rows=before_spinners,current_approving_rows=36)))


def test_partial_admission_results_and_retry_only_failures_preserve_numbering(catalogue):
    jobs,sql,cases=catalogue;items=[item(r,pid) for pid,(r,_) in cases.items()]
    protected={}
    for table in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings'):
        sql.execute('SELECT * FROM '+table);protected[table]=deepcopy(sql.fetchall())
    sql.execute('UPDATE auto_edition_preparations SET proofs=\'[]\'::jsonb WHERE hash=%s',(items[-1]['hash'],))
    key,result=accept(jobs,items)
    assert result['counts']['Pending']==35 and result['counts']['Needs Attention']==1
    bad=[r for r in result['rows'] if r['acceptance']=='failed'];assert len(bad)==1 and bad[0]['reason']
    assert bad[0]['product_gid']==items[-1]['product_gid']
    # Real validation/atomic commits for every accepted product, never a fake success.
    with patch('auto_editions_onboarding_api.candidate',side_effect=lambda pid,digest:cases[pid]):
        while run_one(jobs,authorize=lambda actor:None):pass
    final=ReviewJobs(jobs.connect).progress(USER['id'],batch_id=key)
    assert final['counts']['Approved']==35 and final['counts']['Needs Attention']==1
    _,retry=accept(jobs,[items[-1]])
    assert retry['counts']['Needs Attention']==1 and not retry['active']
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==35
    for table,value in protected.items():sql.execute('SELECT * FROM '+table);assert sql.fetchall()==value


def test_expired_preview_batch_renews_once_and_isolates_changed_identity(catalogue):
    jobs,sql,cases=catalogue;group=list(cases.items())[:8];cache=PreviewStore(jobs.connect)
    sample=bulk.ReviewCache().get(group[0][1][0],group[0][1][1].fetch)
    for pid,(record,_) in group:
        cache.put(ae.fingerprint(bulk.thumbnails.key(record)),sample)
        bulk.snapshots[(USER['id'],pid,record['hash'])]=(time.monotonic()-1,record)
    items=[item(r,pid) for pid,(r,_) in group];items[-1]['hash']='e'*64
    with patch.object(bulk,'actor',new=AsyncMock(return_value=USER)),patch('auto_editions_bulk_runtime.connection',jobs.connect),patch('supabase_backend.read_connection',jobs.connect),patch.object(bulk,'listing',wraps=bulk.listing) as renew,patch.object(bulk.runtime,'storage',side_effect=AssertionError('No full image downloads')):
        response=asyncio.run(bulk.previews_api(request('POST',body=dict(items=items))))
        assert response.status_code==200;rows=json.loads(response.body)['rows']
        assert sum(bool(r['jpeg']) for r in rows)==7
        assert rows[-1]['state']=='Unavailable' and 'changed' in rows[-1]['error']
        renew.assert_called_once();assert len(renew.call_args.args[1])==8
        response=asyncio.run(bulk.previews_api(request('POST',body=dict(items=items[:7]))))
        assert response.status_code==200 and all(r['jpeg'] for r in json.loads(response.body)['rows'])
        assert renew.call_count==1


def test_build_wait_does_not_requery_persistent_thumbnail_cache(ops):
    from concurrent.futures import Future
    jobs,sql,record,assets=ops;future=Future();key=bulk.thumbnails.key(record)
    builds=bulk.PreviewBuilds();builds.pending[key[0]]=(future,time.monotonic())
    try:
        with patch.object(bulk,'thumbnails',bulk.ReviewCache()),patch.object(bulk,'preview_builds',builds):
            persistent=PreviewStore(jobs.connect)
            baseline=historical_baseline()
            function=next(n for n in baseline.body if isinstance(n,ast.FunctionDef) and n.name=='cached_previews')
            namespace=dict(bulk.__dict__);exec(compile(ast.Module(body=[function],type_ignores=[]),'shipped-cache','exec'),namespace)
            with patch.object(persistent,'get_many',wraps=persistent.get_many) as reads:
                start=time.perf_counter()
                for _ in range(5):assert namespace['cached_previews']([(PID,record['hash'],record)],persistent,raw=True)[0]['state']=='Loading'
                before=(time.perf_counter()-start)*1000;assert reads.call_count==5;reads.reset_mock()
                start=time.perf_counter()
                for _ in range(5):assert bulk.cached_previews([(PID,record['hash'],record)],persistent,raw=True)[0]['state']=='Loading'
                after=(time.perf_counter()-start)*1000;assert reads.call_count==0
            report=dict(scope='Five in-progress preview polls, actual disposable SQL transport',shipped_cache_reads=5,current_cache_reads=0,shipped_ms=round(before,2),current_ms=round(after,2))
            out=Path('output/bulk-reliability');out.mkdir(parents=True,exist_ok=True);(out/'build-wait-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    finally:future.set_result(None);builds.pool.shutdown(wait=True)


def test_measured_shipped_and_current_submission_ack(catalogue):
    jobs,sql,cases=catalogue;items=[item(r,pid) for pid,(r,_) in cases.items()]
    baseline=historical_baseline()
    function=next(n for n in baseline.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='approve_api')
    with patch.object(bulk,'actor',new=AsyncMock(return_value=USER)),patch('auto_editions_bulk_runtime.connection',jobs.connect):
        namespace=dict(bulk.__dict__);exec(compile(ast.Module(body=[function],type_ignores=[]),'shipped-submit','exec'),namespace)
        body=dict(request_id=str(uuid.uuid4()),items=items[:18],confirm_visual_quality=True)
        start=time.perf_counter();old=asyncio.run(namespace['approve_api'](request('POST',body=body)));before=(time.perf_counter()-start)*1000
        body.update(request_id=str(uuid.uuid4()),items=items[18:])
        start=time.perf_counter();new=asyncio.run(bulk.approve_api(request('POST',body=body)));after=(time.perf_counter()-start)*1000
    assert old.status_code==new.status_code==202
    result=json.loads(new.body);assert len(result['rows'])==18 and result['counts']['Pending']==18
    report=dict(scope='Actual shipped/current request handlers; disposable SQL; synthetic prepared evidence; no provider latency',selected_per_request=18,shipped_ack_ms=round(before,2),current_ack_ms=round(after,2),shipped_per_item_receipts=0,current_per_item_receipts=18)
    out=Path('output/bulk-reliability');out.mkdir(parents=True,exist_ok=True);(out/'submission-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


def test_watched_completion_is_retrieved_without_loading_catalogue_history(ops):
    from tests.test_auto_editions_bulk_jobs import submit,run
    jobs,sql,record,assets=ops;key=submit(jobs,record);run(jobs,record,assets)
    assert jobs.progress(USER['id'],product_gids=[PID],active_review_only=True)['rows']==[]
    result=jobs.progress(USER['id'],product_gids=[PID],watch=[PID],active_review_only=True)
    assert result['counts']['Approved']==1 and not result['active']
    with pytest.raises(ValueError):jobs.progress(USER['id'],product_gids=[PID],watch=['gid://shopify/Product/1'],active_review_only=True)


def test_current_admission_rejection_cannot_be_masked_by_historical_success(ops):
    from tests.test_auto_editions_bulk_jobs import submit,run
    jobs,sql,record,assets=ops;submit(jobs,record);run(jobs,record,assets)
    key=str(uuid.uuid4())
    jobs.submit(USER['id'],key,[item(record)],lambda conn,selected:{PID:'Current source requires repair.'})
    result=jobs.progress(USER['id'],batch_id=key)
    assert result['counts']['Needs Attention']==1 and result['counts']['Approved']==0
    assert result['rows'][0]['acceptance']=='failed'
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==1


def test_existing_different_preparation_is_not_reported_as_new_acceptance(ops):
    from tests.test_auto_editions_bulk_jobs import submit
    jobs,sql,record,assets=ops;original=submit(jobs,record)
    _,result=accept(jobs,[dict(product_gid=PID,hash='e'*64)])
    assert result['counts']['Needs Attention']==1 and result['rows'][0]['acceptance']=='failed'
    assert 'different preparation' in result['rows'][0]['reason']
    assert jobs.progress(USER['id'],batch_id=original)['counts']['Pending']==1
    sql.execute("SELECT count(*) n FROM auto_edition_review_jobs WHERE state IN ('Pending','Processing')");assert sql.fetchone()['n']==1


def test_measured_expired_binary_preview_recovery(catalogue):
    jobs,sql,cases=catalogue;group=list(cases.items())[:8];cache=PreviewStore(jobs.connect)
    jpeg=bulk.ReviewCache().get(group[0][1][0],group[0][1][1].fetch)
    bulk.thumbnails.entries.clear()
    for pid,(record,_) in group:
        cache.put(ae.fingerprint(bulk.thumbnails.key(record)),jpeg)
        bulk.snapshots[(USER['id'],pid,record['hash'])]=(time.monotonic()-1,record)
    body=dict(items=[item(record,pid) for pid,(record,_) in group],binary=True)
    baseline=historical_baseline()
    function=next(n for n in baseline.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='previews_api')
    with patch.object(bulk,'actor',new=AsyncMock(return_value=USER)),patch('auto_editions_bulk_runtime.connection',jobs.connect),patch('supabase_backend.read_connection',jobs.connect),patch.object(bulk.runtime,'storage',side_effect=AssertionError('No master downloads')):
        namespace=dict(bulk.__dict__);exec(compile(ast.Module(body=[function],type_ignores=[]),'shipped-preview','exec'),namespace)
        start=time.perf_counter();old=asyncio.run(namespace['previews_api'](request('POST',body=body)));before=(time.perf_counter()-start)*1000
        start=time.perf_counter();new=asyncio.run(bulk.previews_api(request('POST',body=body)));after=(time.perf_counter()-start)*1000
        start=time.perf_counter();warm=asyncio.run(bulk.previews_api(request('POST',body=body)));warm_ms=(time.perf_counter()-start)*1000
    assert old.status_code==409 and new.status_code==warm.status_code==200
    assert new.headers['content-type'].startswith('multipart/form-data')
    assert new.body.count(b'Content-Type: image/jpeg')==8
    report=dict(scope='Actual shipped/current handlers, expired actor snapshots, persistent real JPEG cache, disposable SQL; no provider latency',designs=8,shipped_status=409,current_status=200,shipped_ms=round(before,2),renewed_batch_ms=round(after,2),warm_batch_ms=round(warm_ms,2),jpeg_bytes_each=len(jpeg),binary_response_bytes=len(new.body),provider_calls=0)
    out=Path('output/bulk-reliability');out.mkdir(parents=True,exist_ok=True);(out/'expired-preview-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
