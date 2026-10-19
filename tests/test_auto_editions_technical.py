"""Disposable PostgreSQL + real PNG/ICC bytes. No production connection/Photoshop."""
from copy import deepcopy
import asyncio,json,time
from pathlib import Path
from unittest.mock import patch
import pytest
import auto_editions as ae
import auto_editions_technical as technical
import auto_editions_status as statuses
from auto_editions_store import Preparations
from auto_editions_cloud import DropboxAssets
from tests.test_auto_editions_bulk import prepared
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,asset,PID,rows
from tests.test_auto_editions_api import request,ADMIN


@pytest.fixture
def flow(store,tmp_path,monkeypatch):
    d,sql=store
    monkeypatch.setenv('AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED','true')
    for filename in ('20261016071758_auto_editions_bulk_operations.sql','20261017001547_auto_editions_technical_completion.sql'):
        sql.execute(Path('supabase/migrations',filename).read_text(encoding='utf-8'))
    register(store);tick(store,[asset()])
    record,assets=prepared(tmp_path);assets.timings={};m=record['manifest']
    m.update(original_text='001 / 2',number_layer_name='edition',plaque_layer_name='SC_EDITION_PLAQUE',
        source_inspection=dict(document=dict(width_px=200,height_px=100,profile='sRGB',mode='RGB',bits_per_channel=8),layers=[
            dict(path=[dict(name='edition')],kind='text',text='001 / 2',editable=True,visible=True,fonts=[dict(installed=True)],bounds_px=[70,60,90,70]),
            dict(path=[dict(name='SC_EDITION_PLAQUE')],visible=True,bounds_px=[60,50,100,80])]))
    digest=ae.fingerprint(m);record['hash']=digest
    for proof in record['proofs']:proof['preparation_hash']=digest
    record['receipts']['preparation_hash']=digest
    def metadata(token,fid,**kw):
        if fid=='id:original':return asset()
        name=fid.rsplit('/',1)[-1] if fid.startswith('/') else fid.removeprefix('id:')
        path=tmp_path/name
        return dict(id='id:'+name,rev='a1',size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),path_display=DropboxAssets.path(digest,name))
    assets.integration.psd_open_metadata.side_effect=metadata
    assets.integration.team_space_client.return_value.files_get_metadata.side_effect=lambda path:metadata(None,path)
    assets.integration._metadata_to_dict.side_effect=lambda value:value
    Preparations(d.connect).save(m,record['proofs'],record['receipts'],'owner')
    sql.execute("UPDATE edition_products SET edition_total=2")
    sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',reason='Prepared; visual review required',source=%s::jsonb,preparation_hash=%s,priority=2",(json.dumps(m['source']),digest))
    return d,sql,record,assets,tmp_path


def protected(sql):
    return {t:deepcopy(rows(sql,t)) for t in ('edition_products','edition_allocations','synthetic_certificates','product_psd_mappings')}


def test_automatic_completion_real_files_no_visual_gate_and_no_side_effects(flow):
    d,sql,record,assets,root=flow;before=protected(sql);service=technical.Technical(d.connect)
    assert statuses.batch(d.connect,[PID])['rows'][0]['status']=='Uploading'
    assert service.run_one(assets)=='Cloud Ready'
    row=statuses.batch(d.connect,[PID])['rows'][0]
    assert row['status']=='Cloud Ready' and row['uploaded'] is True
    layout=rows(sql,'auto_edition_layouts')[0]
    assert ae.status(record['manifest'],layout['approval'])=='TEST READY'
    assert layout['approval']['method']==technical.METHOD
    assert not {'visual_approved','human_visual_approved','print_ready'} & layout['approval'].keys()
    assert service.run_one(assets) is None
    assert len(rows(sql,'auto_edition_layouts'))==1 and protected(sql)==before
    assert sum(r['event']=='technical_cloud_ready' for r in rows(sql,'auto_edition_onboarding_audit'))==1
    assert not any(r['event']=='visual_quality_approved' for r in rows(sql,'auto_edition_onboarding_audit'))


def test_upload_review_original_completes_with_exact_persisted_upload_proof(flow):
    import uuid
    from product_upload_dropbox import REVIEW
    d,sql,record,assets,root=flow
    sql.execute(Path('supabase/migrations/20261017010350_product_upload_intakes.sql').read_text(encoding='utf-8'))
    original=assets.integration.psd_open_metadata.side_effect
    meta=original(None,'id:original')
    meta=dict(meta,path_display=REVIEW+'/'+meta['name'])
    data=dict(product_gid=PID,source=meta,mockups_exported=True,
              upload_operation=dict(product_id=PID,binding='correlation',source=meta))
    sql.execute('INSERT INTO product_upload_intakes(id,actor_id,mode,data) VALUES(%s,%s,%s,%s::jsonb)',
                (str(uuid.uuid4()),ADMIN['id'],'DRAFT',json.dumps(data)))
    assets.integration.psd_open_metadata.side_effect=lambda token,fid,**kw:deepcopy(meta) if fid=='id:original' else original(token,fid,**kw)
    assert technical.Technical(d.connect).run_one(assets)=='Cloud Ready'


def test_fresh_import_uses_local_verified_assets_without_full_download(flow):
    d,sql,record,assets,root=flow
    assets.fetch.side_effect=AssertionError('No duplicate asset download on import')
    start=time.perf_counter()
    assert technical.Technical(d.connect).run_one(assets,local_root=root)=='Cloud Ready'
    assert assets.fetch.call_count==0
    assert assets.integration.psd_open_metadata.call_count==1
    print('local_import_seconds',round(time.perf_counter()-start,4))


@pytest.mark.parametrize('fault',['font','proof','plaque','source','corrupt','icc','receipt'])
def test_technical_failure_never_becomes_ready(flow,fault):
    d,sql,r,assets,root=flow
    if fault=='source':assets.integration.psd_open_metadata.side_effect=lambda *a,**k:asset(rev='ff')
    elif fault=='corrupt':(root/'number-2.png').write_bytes(b'broken')
    elif fault=='icc':
        from PIL import Image
        with Image.open(root/'number-2.png') as image:image.save(root/'changed.png',icc_profile=None)
        (root/'changed.png').replace(root/'number-2.png')
    elif fault=='receipt':assets.integration.psd_open_metadata.side_effect=ValueError('Cloud receipt changed.')
    else:
        if fault=='font':r['manifest']['source_inspection']['layers'][0]['fonts'][0]['installed']=False
        if fault=='proof':r['proofs'][-1]['preparation_hash']='f'*64
        if fault=='plaque':r['manifest']['plaque_bounds']=[1,1,2,2]
        sql.execute('UPDATE auto_edition_preparations SET manifest=%s::jsonb,proofs=%s::jsonb WHERE hash=%s',(json.dumps(r['manifest']),json.dumps(r['proofs']),r['hash']))
    assert technical.Technical(d.connect).run_one(assets)=='Failed'
    assert not rows(sql,'auto_edition_layouts')
    assert statuses.batch(d.connect,[PID])['rows'][0]['status']=='Failed'


def test_restart_exclusive_claim_expired_owner_fence_and_retry_bound(flow):
    d,sql,r,assets,root=flow;t=technical.Technical(d.connect);t.seed();job=t.claim()
    assert technical.Technical(d.connect).claim() is None
    sql.execute("UPDATE auto_edition_technical_checks SET lease_until=now()-interval '1 second'")
    other=technical.Technical(d.connect).claim();assert other['lease_token']!=job['lease_token']
    assert t.commit(job,r,r,technical.certificate(r))=='Superseded'
    sql.execute("UPDATE auto_edition_technical_checks SET lease_until=now()-interval '1 second',attempts=3")
    assert t.claim() is None
    assert statuses.batch(d.connect,[PID])['rows'][0]['status']=='Failed'
    assert t.retry(PID,'owner') and t.retry(PID,'owner')
    assert rows(sql,'auto_edition_technical_checks')[0]['attempts']==0
    assert sum(x['event']=='technical_retry' for x in rows(sql,'auto_edition_onboarding_audit'))==1
    assert t.run_one(assets)=='Cloud Ready'


@pytest.mark.parametrize('change',['mapping','source','reset','defer','total'])
def test_concurrent_changes_fence_atomic_commit(flow,change):
    d,sql,r,assets,root=flow;t=technical.Technical(d.connect);t.seed();job=t.claim()
    if change=='mapping':sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:new'")
    elif change=='source':sql.execute("UPDATE auto_edition_onboarding SET source='{}'")
    elif change=='total':sql.execute('UPDATE edition_products SET edition_total=100')
    elif change=='defer':sql.execute('UPDATE auto_edition_onboarding SET priority=0')
    else:sql.execute("UPDATE auto_edition_onboarding SET preparation_hash=NULL,status='Awaiting preparation'")
    assert t.commit(job,r,r,technical.certificate(r))=='Superseded'
    assert not rows(sql,'auto_edition_layouts')


def test_backlog_is_read_only_protects_passed_deferred_and_active(flow):
    d,sql,r,assets,root=flow;t=technical.Technical(d.connect);before=rows(sql,'auto_edition_onboarding')
    assert technical.backlog(d.connect)[0]['group'].startswith('Candidate')
    assert rows(sql,'auto_edition_onboarding')==before and not rows(sql,'auto_edition_technical_checks')
    for status,priority,group in [('Cloud Ready',2,'Protected Cloud Ready'),('Preparing',2,'Protected active'),('Blocked',0,'Protected deferred/excluded')]:
        sql.execute('UPDATE auto_edition_onboarding SET status=%s,priority=%s',(status,priority))
        assert technical.backlog(d.connect)[0]['group']==group
        assert t.run_one(assets) is None


def test_missing_receipts_are_recovered_from_actual_cloud_bytes(flow):
    d,sql,r,assets,root=flow
    sql.execute("UPDATE auto_edition_preparations SET receipts='{}'")
    assert technical.Technical(d.connect).run_one(assets)=='Cloud Ready'
    assert rows(sql,'auto_edition_preparations')[0]['receipts']==r['receipts']


def test_gallery_read_only_and_admin_retry(flow):
    import auto_editions_bulk as bulk
    import auto_editions_onboarding_api as api
    d,sql,r,assets,root=flow
    with patch.object(bulk,'actor',return_value=ADMIN):
        page=asyncio.run(bulk.page(request()))
    assert b'window.technicalOnly=true' in page.body
    assert bulk.listing(d.connect,[PID],ADMIN)['rows'][0]['eligible'] is False
    before=rows(sql,'auto_edition_onboarding')
    with patch.object(bulk,'actor',return_value=ADMIN):
        response=asyncio.run(bulk.approve_api(request({'items':[]})))
    assert response.status_code>=400 and rows(sql,'auto_edition_onboarding')==before


def test_mapping_queues_once_and_explicit_deferred_preserved(flow):
    from auto_editions_onboarding_store import Queue
    from auto_editions_priority import priority
    d,sql,r,assets,root=flow
    sql.execute('DELETE FROM auto_edition_onboarding');sql.execute('DELETE FROM auto_edition_setup_audit');sql.execute('DELETE FROM auto_edition_preparations')
    q=Queue(d.connect);q.enqueue(PID,'id:original','owner');q.enqueue(PID,'id:original','owner')
    assert len(rows(sql,'auto_edition_onboarding'))==1
    assert q.claim('companion') and q.claim('other') is None
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation',priority=0,lease_token=NULL,lease_until=NULL")
    assert q.claim('companion') is None
    assert priority(dict(outstanding=1),0)[0]==0


def test_actual_package_endpoint_completes_without_artwork_approval(flow):
    import zipfile
    from starlette.requests import Request
    import auto_editions_setup_api as setup
    import auto_editions_onboarding_api as onboarding
    from auto_editions_onboarding_store import Queue
    d,sql,r,assets,root=flow
    sql.execute('UPDATE auto_edition_onboarding SET preparation_hash=NULL')
    sql.execute('DELETE FROM auto_edition_setup_audit');sql.execute('DELETE FROM auto_edition_preparations')
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation'")
    q=Queue(d.connect);job=q.claim('host')
    m=r['manifest']
    for n in (1,2):
        with ae.compose(m,root,n) as image:image.save(root/f'reference-{n}.png')
    with ae.compose(m,root,1) as image:image.save(root/'original.png')
    (root/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    archive=root/'package.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for path in root.glob('*.png'):z.write(path,path.name)
        z.write(root/'manifest.json','manifest.json')
    payload=archive.read_bytes();delivered=False
    async def receive():
        nonlocal delivered
        if delivered:return dict(type='http.request',body=b'',more_body=False)
        delivered=True;return dict(type='http.request',body=payload,more_body=False)
    req=Request(dict(type='http',method='POST',path='/api/auto-editions/package',headers=[],query_string=b''),receive)
    grant=dict(actor_id='host',context=dict(automatic=True,product_gid=PID,lease_token=str(job['lease_token']),source=m['source'],number=1,total=2))
    assets.publish_preparation.return_value=r['receipts']
    with patch.object(setup.api,'failure',side_effect=lambda error: (_ for _ in ()).throw(error)),patch.object(setup,'grant_context',return_value=grant),patch.object(setup.runtime,'storage',return_value=assets),patch.object(setup.runtime,'stores',return_value=(Preparations(d.connect),None)),patch.object(onboarding,'queue',return_value=q),patch('auto_editions_review_thumbnails.schedule_prepared'):
        response=asyncio.run(setup.package(req))
    assert response.status_code==200,response.body
    assert json.loads(response.body)['status']=='Cloud Ready'
    assert statuses.batch(d.connect,[PID])['rows'][0]['status']=='Cloud Ready'
    assert not any(x['event']=='visual_quality_approved' for x in rows(sql,'auto_edition_onboarding_audit'))


def test_supplier_reconciliation_excludes_technical_readiness(flow,monkeypatch):
    from auto_editions_quality_store import Quality
    d,sql,r,assets,root=flow
    assert technical.Technical(d.connect).run_one(assets)=='Cloud Ready'
    sql.execute(Path('supabase/migrations/20261015022631_auto_editions_v16_quality.sql').read_text(encoding='utf-8'))
    monkeypatch.setenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED','true')
    assets.integration.psd_open_metadata.reset_mock()
    assert Quality(d.connect).run_one(assets,records=[]) is False
    assert not rows(sql,'auto_edition_quality_checks')
    assert assets.integration.psd_open_metadata.call_count==0


def test_existing_restricted_layout_is_never_broadened(flow):
    d,sql,r,assets,root=flow
    approval=dict(preparation_hash=r['hash'],actor_id='owner',visual_approved=True,pixel_exact=True,test_only=True,allocation_ids=[42])
    sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'*',%s,%s::jsonb)",(PID,r['hash'],json.dumps(approval)))
    assert technical.Technical(d.connect).run_one(assets)=='Failed'
    assert rows(sql,'auto_edition_layouts')[0]['approval']==approval
    assert rows(sql,'auto_edition_onboarding')[0]['status']=='Blocked'


def test_approved_colour_policy_reused_and_revocation_rejected(flow,monkeypatch):
    from tests.test_auto_editions_colour import approved
    from PIL import Image
    d,sql,r,assets,root=flow;m=r['manifest']
    m['source_inspection']['document']['profile']=None
    digest=ae.fingerprint(m);r['hash']=digest
    for p in r['proofs']:p['preparation_hash']=digest
    r['receipts']['preparation_hash']=digest
    with Image.open(root/'master.png') as image:policy=approved(m['source'],image.info['icc_profile'])
    config=root/'approved-policies.json';config.write_text(json.dumps([policy]),encoding='utf-8')
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_POLICIES_FILE',str(config))
    value=technical.certificate(r)
    assert value['colour_policy']['group']==policy['group'] and technical.current(value,m)
    config.write_text('[]',encoding='utf-8');assert not technical.current(value,m)
    m['source_inspection']['document']['mode']='CMYK'
    config.write_text(json.dumps([policy]),encoding='utf-8')
    r['hash']=ae.fingerprint(m)
    for proof in r['proofs']:proof['preparation_hash']=r['hash']
    r['receipts']['preparation_hash']=r['hash']
    with pytest.raises(ValueError,match='CMYK'):technical.certificate(r)


def test_batched_policy_read_does_not_query_per_row(flow,monkeypatch):
    d,sql,r,assets,root=flow
    assert technical.Technical(d.connect).run_one(assets)=='Cloud Ready'
    monkeypatch.setenv('AUTO_EDITIONS_COLOUR_POLICY_BACKEND','audit')
    with patch('auto_editions_colour_store.configuration',return_value=dict(policies=[],memberships=[],default_group='')) as config:
        result=statuses.batch(d.connect,[PID])
    assert result['rows'][0]['status']=='Cloud Ready' and config.call_count==1 and result['query_count']==2


@pytest.mark.parametrize('role',['anon','authenticated'])
def test_technical_jobs_not_publicly_readable_or_writable(flow,role):
    d,sql,r,assets,root=flow
    try:
        sql.execute('SET ROLE '+role)
        with pytest.raises(RuntimeError,match='permission denied'):
            sql.execute('SELECT * FROM auto_edition_technical_checks')
        with pytest.raises(RuntimeError,match='permission denied'):
            sql.execute("INSERT INTO auto_edition_technical_checks(product_gid,preparation_hash) VALUES(%s,%s)",(PID,r['hash']))
    finally:sql.execute('RESET ROLE')


def test_worker_health_retries_verification_only_and_protects_completed(flow):
    import uuid
    import worker_health_queue as health_queue
    d,sql,r,assets,root=flow;t=technical.Technical(d.connect)
    t.seed();job=t.claim();t.fail(job,'Download interrupted',False)
    before=protected(sql);key=str(uuid.uuid4())
    assert health_queue.submit(d.connect,PID,'owner',key)['status']=='Uploading'
    assert health_queue.submit(d.connect,PID,'owner',key)['duplicate'] is True
    assert len(rows(sql,'auto_edition_technical_checks'))==1
    assert rows(sql,'auto_edition_technical_checks')[0]['state']=='Pending'
    assert t.run_one(assets)=='Cloud Ready'
    with pytest.raises(ValueError,match='protected'):
        health_queue.submit(d.connect,PID,'owner',str(uuid.uuid4()))
    assert protected(sql)==before


def test_worker_health_distinguishes_queued_uploading_from_active_validation(flow):
    from worker_health import Health
    d,sql,r,assets,root=flow;t=technical.Technical(d.connect)
    job=Health(d.connect).snapshot()['jobs'][0]
    assert job['status']=='Uploading' and job['category']=='Queued'
    t.seed();claimed=t.claim()
    job=Health(d.connect).snapshot()['jobs'][0]
    assert job['status']=='Uploading' and job['category']=='Active' and job['stage']=='Verifying'
    t.fail(claimed,'Cloud receipt changed.')
    job=Health(d.connect).snapshot()['jobs'][0]
    assert job['status']=='Failed' and job['retry_eligible']


def test_retained_checkpoint_recovers_without_regenerating_psd(flow):
    d,sql,r,assets,root=flow
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation'")
    assert d.queue.claim('companion') is None
    assert technical.Technical(d.connect).run_one(assets)=='Cloud Ready'
    assert len(rows(sql,'auto_edition_onboarding'))==1


def test_same_hash_new_reset_generation_cannot_accept_old_result(flow):
    d,sql,r,assets,root=flow;t=technical.Technical(d.connect);t.seed();old=t.claim()
    # A reset/remap may produce identical bytes. Its new checkpoint still has
    # separate operation identity and must not accept an old completion.
    sql.execute("UPDATE auto_edition_onboarding SET updated_at=now()+interval '1 second'")
    t.seed();new=t.claim()
    assert old['checkpoint_at']!=new['checkpoint_at']
    assert t.commit(old,r,r,technical.certificate(r))=='Superseded'
    assert t.commit(new,r,r,technical.certificate(r))=='Cloud Ready'
    assert sorted(x['state'] for x in rows(sql,'auto_edition_technical_checks'))==['Succeeded','Superseded']


def retained_pinned_import(flow,fault=None):
    import uuid
    from auto_editions_reset import Reset
    d,sql,original,assets,root=flow
    sql.execute(Path('supabase/migrations/20261015024929_auto_editions_reset_design.sql').read_text())
    reset=Reset(d.connect);request_id=str(uuid.uuid4());reset.request(PID,request_id,'admin')
    sql.execute("UPDATE edition_products SET product_title='Reviewed original with different display title'")
    record=deepcopy(original);record['manifest']['reset_request_id']=request_id
    if fault=='source':record['manifest']['source']['content_hash']='b'*64
    if fault=='font':record['manifest']['source_inspection']['layers'][0]['fonts'][0]['installed']=False
    if fault=='colour':record['manifest']['source_inspection']['document']['profile']=''
    record['hash']=ae.fingerprint(record['manifest'])
    for proof in record['proofs']:proof['preparation_hash']=record['hash']
    record['receipts']['preparation_hash']=record['hash']
    if fault=='proof':record['proofs'][0]['pixel_exact']=False
    if fault=='receipt':record['receipts']['assets']=record['receipts']['assets'][:-1]
    Preparations(d.connect).save(record['manifest'],record['proofs'],record['receipts'],'host')
    pending=dict(expected_source=original['manifest']['source'],source=original['manifest']['source'],
        file_id='id:original',stage='Failed',attempts=1,
        reason='Original PSD matching is now ambiguous. The working design is retained.')
    sql.execute("UPDATE auto_edition_onboarding SET replacement=replacement || %s::jsonb",(json.dumps(pending),))
    def metadata(token,fid,**kw):
        if fid=='id:original':return asset()
        name=fid.rsplit('/',1)[-1] if fid.startswith('/') else fid.removeprefix('id:')
        path=root/name
        return dict(id='id:'+name,rev='a1',size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),path_display=DropboxAssets.path(record['hash'],name))
    assets.integration.psd_open_metadata.side_effect=metadata
    assets.integration.team_space_client.return_value.files_get_metadata.side_effect=lambda path:metadata(None,path)
    return record,reset


def test_pinned_uploaded_checkpoint_resumes_without_native_claim_or_duplicate_upload(flow):
    import uuid
    import worker_health_queue as queue
    d,sql,original,assets,root=flow;record,reset=retained_pinned_import(flow);before=protected(sql)
    request_id=str(uuid.uuid4())
    assert queue.submit(d.connect,PID,'admin',request_id,True)['accepted']
    assert queue.submit(d.connect,PID,'admin',request_id,True)['duplicate']
    q=rows(sql,'auto_edition_onboarding')[0]
    assert q['preparation_hash']==record['hash'] and q['status']=='Blocked'
    assert q['replacement']['stage']=='Complete' and q['replacement']['attempts']==1
    assert d.queue.claim('unnecessary-native-host') is None
    assert not rows(sql,'auto_edition_layouts')
    assert len(rows(sql,'auto_edition_preparations'))==2
    assert technical.Technical(d.connect).run_one(assets,pid=PID)=='Cloud Ready'
    assert protected(sql)==before
    assert sum(a['event']=='reset_checkpoint_resumed' for a in rows(sql,'auto_edition_onboarding_audit'))==1
    assert sum(a['event']=='technical_cloud_ready' for a in rows(sql,'auto_edition_onboarding_audit'))==1
    assets.publish_preparation.assert_not_called()


@pytest.mark.parametrize('fault',['source','font','colour','proof','receipt'])
def test_retained_checkpoint_resume_rejects_incomplete_or_unapproved_evidence(flow,fault):
    d,sql,original,assets,root=flow;record,reset=retained_pinned_import(flow,fault)
    before=deepcopy(rows(sql,'auto_edition_onboarding'))
    with pytest.raises(ValueError):reset.retry_failed(PID,'admin')
    assert rows(sql,'auto_edition_onboarding')==before
    assert not rows(sql,'auto_edition_layouts')
