"""Synthetic local bytes and disposable SQL. Never contacts a provider."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import shutil
import time
from unittest.mock import Mock,patch

import pytest
from PIL import Image,ImageCms
import auto_editions as ae
import auto_editions_bulk as bulk
from auto_editions_cloud import DropboxAssets
from tests.test_auto_editions import package
from tests.test_auto_editions_discovery import database,store,pglite_database,PID,register,tick,asset
from tests.test_auto_editions_api import request,ADMIN,VA


def prepared(root):
    m=package(root)
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for a in [m['master'],*m['patches'].values()]:
        path=root/a['name']
        with Image.open(path) as im:im.save(root/('new-'+a['name']),icc_profile=profile)
        (root/('new-'+a['name'])).replace(path);a['sha256']=ae.file_hash(path)
    m.update(source=ae.source_identity(PID,dict(id='id:original',rev='a1',content_hash='a'*64)),plaque_bounds=[60,50,100,80],source_modified=False)
    digest=ae.fingerprint(m)
    proofs=[dict(preparation_hash=digest,number=n,pixel_exact=True,outside_number_exact=True) for n in (1,2)]
    receipts=dict(preparation_hash=digest,assets=[dict(name=a['name'],file_id='id:'+a['name'],revision='a1',bytes=(root/a['name']).stat().st_size) for a in [m['master'],*m['patches'].values()]])
    record=dict(hash=digest,manifest=m,proofs=proofs,receipts=receipts)
    assets=Mock()
    assets.fetch.side_effect=lambda digest,a,dest:shutil.copyfile(root/a['name'],dest)
    def metadata(token,fid,**kwargs):
        if fid=='id:original':return dict(id=fid,rev='a1',content_hash='a'*64,**{'.tag':'file'},name='Synthetic.psd',path_display='/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd')
        name=fid.removeprefix('id:');path=root/name
        return dict(id=fid,rev='a1',size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),path_display=DropboxAssets.path(digest,name))
    assets.integration.psd_open_metadata.side_effect=metadata
    return record,assets


@pytest.mark.parametrize('choice',list(bulk.SORTS))
def test_sort_is_stable_preserves_every_identity_and_original_order(choice):
    rows=[dict(id=str(n)) for n in range(1000)]
    states=['Failed','Not Connected','Connect','Queued','Deferred','Needs Review','Review','Cloud Ready','Production Ready','Preparing']
    values={r['id']:dict(status=states[i%len(states)]) for i,r in enumerate(rows)}
    result=bulk.sorted_rows(rows,values,choice,lambda r:r['id'])
    preferred=bulk.SORTS[choice]
    assert result==[r for r in rows if values[r['id']]['status'] in preferred]+[r for r in rows if values[r['id']]['status'] not in preferred]
    assert rows[0]['id']=='0' and len({r['id'] for r in result})==1000


def test_small_cache_uses_verified_assets_once_and_detects_corruption(tmp_path):
    record,assets=prepared(tmp_path);cache=bulk.ReviewCache()
    with patch.object(ae,'render_jpg',side_effect=AssertionError('No full JPG rendering')):
        a=cache.get(record,assets.fetch);assert a==cache.get(record,assets.fetch)
        assert assets.fetch.call_count==2
    import io
    with Image.open(io.BytesIO(a)) as im:assert im.format=='JPEG' and im.width<=300
    assert len(a)<10000
    (tmp_path/'master.png').write_bytes(b'changed')
    with pytest.raises(ValueError):bulk.ReviewCache().get(record,assets.fetch)


@pytest.mark.parametrize('change',['proof','last','receipt','plaque','source','hash'])
def test_missing_or_ambiguous_evidence_is_ineligible(tmp_path,change):
    record,_=prepared(tmp_path)
    if change=='proof':record['proofs'][0]['preparation_hash']='b'*64
    if change=='last':record['proofs'].pop()
    if change=='receipt':record['receipts']['assets'].pop()
    if change=='plaque':record['manifest']['plaque_bounds']=[1,1,2,2]
    if change=='source':record['manifest']['source_modified']=True
    if change=='hash':record['hash']='b'*64
    with pytest.raises(ValueError):bulk.evidence(record)


@pytest.fixture
def review(store,tmp_path):
    d,sql=store;register(store);tick(store,[asset()]);record,assets=prepared(tmp_path)
    sql.execute('UPDATE edition_products SET edition_total=2')
    sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(record['hash'],json.dumps(record['manifest']),json.dumps(record['proofs']),json.dumps(record['receipts'])))
    sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',preparation_hash=%s,source=%s::jsonb,edition_total=2 WHERE product_gid=%s",(record['hash'],json.dumps(record['manifest']['source']),PID))
    return d,sql,record,assets


def test_batch_listing_two_queries_no_provider_reads(review):
    d,sql,record,assets=review
    with patch.object(bulk.runtime,'storage',side_effect=AssertionError('Listing must not resolve provider')):
        result=bulk.listing(d.connect,[PID],ADMIN)
    assert result['rows'][0]['eligible'] is True
    assert result['rows'][0]['title']=='New Art' and result['metadata_queries']==2


def test_atomic_idempotent_test_approval_preserves_allocations_and_certificates(review):
    d,sql,record,assets=review;item=dict(product_gid=PID,hash=record['hash'])
    before={}
    for table in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings'):
        sql.execute('SELECT * FROM '+table);before[table]=deepcopy(sql.fetchall())
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)):
        assert bulk.approve_one(d.connect,item,'synthetic-admin')=='Approved'
        assert bulk.approve_one(d.connect,item,'synthetic-admin')=='Skipped'
    sql.execute('SELECT * FROM auto_edition_layouts');layouts=sql.fetchall()
    assert len(layouts)==1 and layouts[0]['approval']['test_only'] is True
    assert 'print_ready' not in layouts[0]['approval']
    sql.execute("SELECT * FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert len(sql.fetchall())==1
    for table,rows in before.items():
        sql.execute('SELECT * FROM '+table);assert sql.fetchall()==rows


@pytest.mark.parametrize('changed',['mapping','total','checkpoint','source','proof','conflict','failure'])
def test_changes_during_validation_never_approve(review,changed):
    d,sql,record,assets=review
    def validate(*args):
        if changed=='mapping':sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:changed'")
        if changed=='total':sql.execute('UPDATE edition_products SET edition_total=99')
        if changed=='checkpoint':sql.execute("UPDATE auto_edition_onboarding SET preparation_hash=NULL")
        if changed=='source':assets.integration.psd_open_metadata.side_effect=lambda *a,**k:dict(id='id:original',rev='a2',content_hash='a'*64)
        if changed=='proof':sql.execute("UPDATE auto_edition_preparations SET proofs='[]'")
        if changed=='conflict':
            sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,'{}','[]','{}','admin',now())",('b'*64,))
            sql.execute("INSERT INTO auto_edition_layouts VALUES(%s,'123',%s,'{}',now())",(PID,'b'*64))
        if changed=='failure':sql.execute("UPDATE auto_edition_onboarding SET status='Needs PSD Repair'")
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)),patch.object(bulk,'validate_files',side_effect=validate):
        assert bulk.approve_one(d.connect,dict(product_gid=PID,hash=record['hash']),'admin') in ('Skipped','Needs Attention')
    sql.execute("SELECT * FROM auto_edition_layouts WHERE variant_id='*'");assert not sql.fetchall()


def test_audit_failure_rolls_back_both_approval_and_checkpoint(review):
    d,sql,record,assets=review
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)),patch.object(bulk.Queue,'audit',side_effect=RuntimeError('audit unavailable')):
        with pytest.raises(RuntimeError):bulk.approve_one(d.connect,dict(product_gid=PID,hash=record['hash']),'admin')
    sql.execute('SELECT * FROM auto_edition_layouts');assert not sql.fetchall()
    sql.execute('SELECT status FROM auto_edition_onboarding');assert sql.fetchone()['status']=='Blocked'


def test_concurrent_requests_only_audit_one_approval(review):
    from concurrent.futures import ThreadPoolExecutor
    d,sql,record,assets=review
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)),ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:bulk.approve_one(d.connect,dict(product_gid=PID,hash=record['hash']),'admin'),range(2)))
    assert sorted(results)==['Approved','Skipped']
    sql.execute("SELECT count(*) n FROM auto_edition_setup_audit WHERE event='approved_test_layout'");assert sql.fetchone()['n']==1


def test_failing_quality_evidence_cannot_be_bypassed_during_validation(review,monkeypatch):
    d,sql,record,assets=review
    schema=Path('supabase/migrations/20261015022631_auto_editions_v16_quality.sql').read_text()
    sql.execute(schema)
    # Change the quality result after the initial eligibility snapshot.
    def assess(*args):
        monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
        sql.execute('''INSERT INTO auto_edition_quality_checks(preparation_hash,product_gid,policy_hash,assessment,source,status)
            VALUES(%s,%s,%s,%s::jsonb,'{}','Failed')''',(record['hash'],PID,'a'*64,json.dumps(dict(status='Failed'))))
    with patch('auto_editions_onboarding_api.candidate',return_value=(record,assets)),patch.object(bulk,'validate_files',side_effect=assess):
        assert bulk.approve_one(d.connect,dict(product_gid=PID,hash=record['hash']),'admin')=='Needs Attention'
    sql.execute('SELECT * FROM auto_edition_layouts');assert not sql.fetchall()


def test_bulk_api_admin_origin_confirmation_and_partial_results():
    import files_upload_api as files
    async def run():
        with patch.object(bulk.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=VA):
            assert (await bulk.approve_api(request('POST',body={}))).status_code==403
        with patch.object(bulk.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=ADMIN):
            assert (await bulk.approve_api(request('POST',origin='',body={}))).status_code==403
            assert (await bulk.approve_api(request('POST',body={'items':[],'confirm_visual_quality':False}))).status_code==409
            items=[dict(product_gid=f'gid://shopify/Product/{n}',hash='a'*64) for n in (1,2,3,1)]
            with patch.object(bulk,'approve_one',side_effect=['Approved','Skipped',ValueError('source changed')]) as approve:
                result=await bulk.approve_api(request('POST',body=dict(items=items,confirm_visual_quality=True)))
            assert result.status_code==200
            assert json.loads(result.body)['counts']=={'Approved':1,'Skipped':1,'Needs Attention':1}
            assert approve.call_count==3
    asyncio.run(run())


def test_synthetic_performance(tmp_path):
    record,assets=prepared(tmp_path);cache=bulk.ReviewCache();started=time.perf_counter();data=cache.get(record,assets.fetch);cold=(time.perf_counter()-started)*1000
    started=time.perf_counter()
    for _ in range(100):cache.get(record,assets.fetch)
    warm=(time.perf_counter()-started)*10
    print(json.dumps(dict(synthetic_dimensions=record['manifest']['dimensions'],cold_thumbnail_ms=round(cold,3),warm_thumbnail_mean_ms=round(warm,3),jpeg_bytes=len(data))))


def test_local_48_design_metadata_and_approval_performance(store,tmp_path,monkeypatch):
    d,sql=store;monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    template,assets=prepared(tmp_path);cases={};items=[]
    # Real SQL operations; tiny synthetic artwork and injected provider only.
    for n in range(1,49):
        pid='gid://shopify/Product/'+str(n);record=deepcopy(template);m=record['manifest'];m['source'].update(product_gid=pid,file_id='id:source'+str(n))
        digest=ae.fingerprint(m);record['hash']=digest;record['receipts']['preparation_hash']=digest
        for p in record['proofs']:p['preparation_hash']=digest
        sql.execute("INSERT INTO edition_products VALUES(%s,%s,%s,%s,2,1,true,true)",(pid,str(n),'Synthetic '+str(n),'synthetic-'+str(n)))
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual','synthetic-admin')",(pid,m['source']['file_id'],'/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic '+str(n)+'.psd'))
        sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(digest,json.dumps(m),json.dumps(record['proofs']),json.dumps(record['receipts'])))
        sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,preparation_hash,source,edition_total) VALUES(%s,%s,'Blocked',%s,%s::jsonb,2)",(pid,m['source']['file_id'],digest,json.dumps(m['source'])))
        provider=Mock();provider.fetch.side_effect=assets.fetch.side_effect
        def metadata(token,fid,record=record,**kwargs):
            if fid==record['manifest']['source']['file_id']:return dict(id=fid,rev='a1',content_hash='a'*64,**{'.tag':'file'},name='Synthetic.psd',path_display='/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Synthetic.psd')
            name=fid.removeprefix('id:');path=tmp_path/name
            return dict(id=fid,rev='a1',size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),path_display=DropboxAssets.path(record['hash'],name))
        provider.integration.psd_open_metadata.side_effect=metadata;cases[pid]=(record,provider);items.append(dict(product_gid=pid,hash=digest))
    started=time.perf_counter();listing=bulk.listing(d.connect,list(cases),ADMIN);metadata_ms=(time.perf_counter()-started)*1000
    assert len(listing['rows'])==48 and all(r['eligible'] for r in listing['rows'])
    with patch('auto_editions_onboarding_api.candidate',side_effect=lambda pid,digest:cases[pid]):
        started=time.perf_counter();results=[bulk.approve_one(d.connect,item,'synthetic-admin') for item in items];approval_ms=(time.perf_counter()-started)*1000
    assert results==['Approved']*48
    report=dict(designs=48,dimensions=[200,100],edition_total=2,metadata_queries=2,metadata_ms=round(metadata_ms,3),approval_ms=round(approval_ms,3),provider='injected local bytes; no network latency',database='disposable PGlite')
    Path('output/bulk-review').mkdir(parents=True,exist_ok=True);Path('output/bulk-review/backend-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


def test_4k_thumbnail_performance(tmp_path):
    record,assets=prepared(tmp_path);m=record['manifest'];profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    m.update(dimensions=[3840,2160],source_dimensions=[3840,2160],number_region=[1300,1500,1500,1600],plaque_bounds=[1200,1450,1700,1700])
    for a in [m['master'],*m['patches'].values()]:
        with Image.new('RGB',(3840,2160) if a==m['master'] else (200,100),'navy') as im:im.save(tmp_path/a['name'],icc_profile=profile)
        a['sha256']=ae.file_hash(tmp_path/a['name'])
    digest=ae.fingerprint(m);record['hash']=digest;record['receipts']['preparation_hash']=digest
    for p in record['proofs']:p['preparation_hash']=digest
    for r in record['receipts']['assets']:r['bytes']=(tmp_path/r['name']).stat().st_size
    cache=bulk.ReviewCache();started=time.perf_counter();data=cache.get(record,assets.fetch);cold=(time.perf_counter()-started)*1000
    started=time.perf_counter()
    for _ in range(100):cache.get(record,assets.fetch)
    warm=(time.perf_counter()-started)*10
    report=dict(dimensions=m['dimensions'],cold_thumbnail_ms=round(cold,3),warm_thumbnail_mean_ms=round(warm,3),jpeg_bytes=len(data),provider='local fixture only')
    Path('output/bulk-review').mkdir(parents=True,exist_ok=True);Path('output/bulk-review/thumbnail-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
