"""Focused reset/redo contracts with synthetic identities and isolated SQL only."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import zipfile

import pytest
import auto_editions as ae
import auto_editions_onboarding_api as api
import auto_editions_status as status
from auto_editions_reset import Reset,snapshot
from auto_editions_store import Preparations
from tests.test_auto_editions_discovery import database,store,pglite_database,register,tick,rows,asset,PID,due
from tests.test_auto_editions import package
from tests.test_auto_editions_api import request,ADMIN,VA

ROOT=Path(__file__).parents[1]


@pytest.fixture
def design(store,tmp_path):
    d,sql=store
    sql.execute((ROOT/'supabase/migrations/20261015024929_auto_editions_reset_design.sql').read_text())
    register(store);tick(store,[asset()])
    manifest=package(tmp_path);manifest['source']=ae.source_identity(PID,asset());digest=ae.fingerprint(manifest)
    registry=Preparations(d.connect)
    registry.save(manifest,[dict(preparation_hash=digest,pixel_exact=True,outside_number_exact=True)],{},'original-owner')
    registry.approve(digest,dict(shopify_product_gid=PID,shopify_variant_id='*'),'original-owner')
    sql.execute('UPDATE edition_products SET edition_total=2')
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready',source=%s::jsonb,edition_total=2,preparation_hash=%s",(json.dumps(manifest['source']),digest))
    sql.execute("""INSERT INTO auto_edition_onboarding(product_gid,file_id,priority)
        SELECT 'gid://shopify/Product/'||n,'id:deferred-'||n,0 FROM generate_series(1000,1166)n""")
    return d,sql,Reset(d.connect),manifest


def selected(sql):
    sql.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s',(PID,));return dict(sql.fetchone())


def protected(sql):
    result={}
    for table in ('product_psd_mappings','auto_edition_layouts','edition_allocations','synthetic_certificates'):
        result[table]=rows(sql,table)
    sql.execute('SELECT next_edition_number FROM edition_products WHERE shopify_product_gid=%s',(PID,))
    result['next']=sql.fetchone()['next_edition_number']
    sql.execute("SELECT jsonb_agg(to_jsonb(q) ORDER BY product_gid) AS data FROM auto_edition_onboarding q WHERE priority=0")
    result['deferred']=sql.fetchone()['data'];assert len(result['deferred'])==167
    return result


def discover(design,metadata=None,entries=None):
    d,sql,reset,_=design;due(sql)
    d.tick(lambda cursor:dict(entries=entries if entries is not None else [asset()],cursor='new-delta',has_more=False),
           lambda fid:metadata or asset())
    return selected(sql)['replacement']


def complete(design,token,tmp_path):
    d,sql,reset,old=design
    pending=selected(sql)['replacement'];root=tmp_path/'redo';root.mkdir()
    manifest=package(root);manifest.update(source=pending['source'],reset_request_id=pending['id'])
    digest=ae.fingerprint(manifest)
    Preparations(d.connect).save(manifest,[dict(preparation_hash=digest,pixel_exact=True,outside_number_exact=True)],{},'host')
    d.queue.checkpoint(PID,str(token),'host','Blocked','Prepared and pixel-verified; visual quality review required before Cloud Ready.',digest=digest,metrics={'total_seconds':1})
    return manifest


def test_same_file_id_fresh_reset_atomic_switch_and_all_history_preserved(design,tmp_path):
    d,sql,reset,old=design;before=protected(sql);active=snapshot(selected(sql));rid=str(uuid.uuid4())
    assert reset.request(PID,rid,'admin')=='Discovering'
    assert reset.request(PID,rid,'admin')=='Discovering'
    assert snapshot(selected(sql))==active and protected(sql)==before
    with pytest.raises(ValueError,match='already processing'):reset.request(PID,str(uuid.uuid4()),'admin')
    assert discover(design)['stage']=='Queued'
    assert protected(sql)==before and snapshot(selected(sql))==active
    job=d.queue.claim('host');assert job['file_id']==old['source']['file_id']
    assert snapshot(selected(sql))==active and d.queue.claim('another-host') is None
    assert d.queue.completed_receipt(PID,str(job['lease_token']),'host') is None
    with patch.object(api,'queue',return_value=d.queue),patch.object(api.runtime,'storage',return_value=SimpleNamespace(
            integration=SimpleNamespace(psd_open_metadata=lambda *a,**kw:asset()),token='synthetic')):
        context=api.product_context(PID,str(job['lease_token']))
    assert context['reset_id']==rid and context['source']==old['source']
    new=complete(design,job['lease_token'],tmp_path)
    assert ae.fingerprint(new)!=ae.fingerprint(old)
    assert selected(sql)['preparation_hash']==ae.fingerprint(new)
    assert selected(sql)['replacement']['stage']=='Complete'
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Review'
    assert protected(sql)==before # unchanged mapping ID does not get rewritten
    assert reset.request(PID,rid,'admin')=='Complete' # lost response cannot enqueue again
    assert d.queue.completed_receipt(PID,str(job['lease_token']),'host')['preparation_hash']==ae.fingerprint(new)
    sql.execute('SELECT count(*) n FROM auto_edition_preparations');assert sql.fetchone()['n']==2
    newer=str(uuid.uuid4());reset.request(PID,newer,'admin')
    assert reset.request(PID,rid,'admin')=='Complete'
    assert selected(sql)['replacement']['id']==newer # delayed historical request cannot reset again


@pytest.mark.parametrize('failure',['ambiguous','missing','unapproved','unowned','network'])
def test_failed_discovery_retains_original_working_design(design,failure):
    d,sql,reset,old=design;before=protected(sql);active=snapshot(selected(sql))
    reset.request(PID,str(uuid.uuid4()),'admin')
    entries=[asset()];fresh=asset()
    if failure=='ambiguous':
        sql.execute("UPDATE edition_products SET product_title='New: Art'")
        entries=[asset(name='New_ Art.psd',path_display=asset()['path_display'].replace('New Art','New_ Art')),
                 asset(id='id:other',name='New - Art.psd',path_display=asset()['path_display'].replace('New Art','New - Art'))]
    if failure=='missing':entries=[dict(**{'.tag':'deleted'},path_lower=asset()['path_display'].lower())]
    if failure=='unapproved':fresh=asset(path_display='/Prepared/Masters/New Art.psd')
    if failure=='unowned':
        sql.execute("INSERT INTO product_psd_mappings VALUES('gid://shopify/Product/888','id:other',%s,'','manual','another-owner',now(),now())",(asset()['path_display'],))
        entries=[dict(**{'.tag':'deleted'},path_lower=asset()['path_display'].lower()),asset(id='id:other')]
        before=protected(sql)
    if failure=='network':
        due(sql)
        d.tick(lambda cursor:dict(entries=entries,cursor='delta',has_more=False),lambda fid:(_ for _ in ()).throw(OSError('synthetic disconnect')))
    else:discover(design,fresh,entries)
    assert selected(sql)['replacement']['stage']=='Failed'
    assert snapshot(selected(sql))==active and protected(sql)==before
    value=status.batch(d.connect,[PID],writable=True)['rows'][0]
    assert value['status']=='Failed' and value['reset_allowed'] is True
    assert d.queue.claim('host') is None


def test_new_original_id_only_becomes_active_after_verified_success(design,tmp_path):
    d,sql,reset,old=design;before=protected(sql)
    reset.request(PID,str(uuid.uuid4()),'admin')
    fresh=asset(id='id:new-original',rev='a2',content_hash='b'*64)
    pending=discover(design,fresh,[dict(**{'.tag':'deleted'},path_lower=asset()['path_display'].lower()),fresh])
    assert pending['source']==ae.source_identity(PID,fresh)
    assert protected(sql)==before
    job=d.queue.claim('host');assert job['file_id']=='id:new-original'
    new=complete(design,job['lease_token'],tmp_path)
    after=protected(sql)
    assert after['product_psd_mappings'][0]['dropbox_file_id']=='id:new-original'
    after.pop('product_psd_mappings');before.pop('product_psd_mappings');assert after==before
    sql.execute("SELECT action FROM product_psd_mapping_audit ORDER BY id DESC LIMIT 1");assert sql.fetchone()['action']=='replace'


def test_latest_revision_same_id_and_failure_does_not_switch_active_state(design):
    d,sql,reset,old=design;before=protected(sql);active=snapshot(selected(sql))
    reset.request(PID,str(uuid.uuid4()),'admin')
    fresh=asset(rev='a2',content_hash='b'*64)
    assert discover(design,fresh)['source']==ae.source_identity(PID,fresh)
    job=d.queue.claim('host')
    d.queue.checkpoint(PID,str(job['lease_token']),'host','Needs PSD Repair','Original fonts need repair.')
    assert selected(sql)['replacement']['stage']=='Failed'
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Needs Repair'
    assert snapshot(selected(sql))==active and protected(sql)==before


def test_active_job_and_uncertain_expired_processing_cannot_be_reset(design):
    d,sql,reset,old=design
    for lease in ("now()+interval '30 minutes'","now()-interval '1 minute'"):
        sql.execute("UPDATE auto_edition_onboarding SET status='Preparing',lease_until="+lease+" WHERE product_gid=%s",(PID,))
        with pytest.raises(ValueError,match='already processing'):reset.request(PID,str(uuid.uuid4()),'admin')
        assert not selected(sql)['replacement']


def test_previous_completed_upload_can_acknowledge_before_replacement_is_claimed(design):
    d,sql,reset,old=design;token=str(uuid.uuid4())
    sql.execute("UPDATE auto_edition_onboarding SET lease_token=%s,lease_until=now()+interval '45 minutes' WHERE product_gid=%s",(token,PID))
    with d.connect() as conn,conn.cursor() as cur:d.queue.audit(cur,PID,'previous-host','claimed',{'lease':token})
    reset.request(PID,str(uuid.uuid4()),'admin')
    assert d.queue.completed_receipt(PID,token,'previous-host')['preparation_hash']==ae.fingerprint(old)
    discover(design)
    assert d.queue.completed_receipt(PID,token,'previous-host')['preparation_hash']==ae.fingerprint(old)
    new=d.queue.claim('host')
    assert d.queue.completed_receipt(PID,token,'previous-host') is None
    assert d.queue.completed_receipt(PID,str(new['lease_token']),'host') is None


def test_expired_replacement_lease_recovers_without_stealing_old_owner(design,tmp_path):
    d,sql,reset,old=design;before=protected(sql)
    reset.request(PID,str(uuid.uuid4()),'admin');discover(design)
    first=d.queue.claim('host')
    sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 minute' WHERE product_gid=%s",(PID,))
    second=d.queue.claim('host');assert first['lease_token']!=second['lease_token']
    with pytest.raises(ValueError,match='lease'):d.queue.checkpoint(PID,str(first['lease_token']),'host','Blocked','Late old worker')
    assert protected(sql)==before
    complete(design,second['lease_token'],tmp_path)
    assert selected(sql)['replacement']['attempts']==2


def test_inflight_inventory_is_not_used_for_a_later_reset_request(design):
    d,sql,reset,old=design;due(sql);claim=d.claim()
    d.page(claim['lease_token'],dict(entries=[asset()],cursor='pre-reset',has_more=False))
    reset.request(PID,str(uuid.uuid4()),'admin')
    assert reset.discover(claim['lease_token'],lambda fid:asset())==0
    assert selected(sql)['replacement']['stage']=='Discovering'
    d.finish(claim['lease_token']);assert discover(design)['stage']=='Queued'


def test_three_interrupted_attempts_fail_without_resetting_other_work(design):
    d,sql,reset,old=design;before=protected(sql);active=snapshot(selected(sql))
    reset.request(PID,str(uuid.uuid4()),'admin');discover(design)
    for _ in range(3):
        assert d.queue.claim('host')
        sql.execute("UPDATE auto_edition_onboarding SET lease_until=now()-interval '1 minute' WHERE product_gid=%s",(PID,))
    assert d.queue.claim('host') is None
    assert selected(sql)['replacement']['stage']=='Failed'
    assert snapshot(selected(sql))==active and protected(sql)==before


def test_not_connected_product_uses_same_safe_discovery_and_queue(store,tmp_path):
    d,sql=store
    sql.execute((ROOT/'supabase/migrations/20261015024929_auto_editions_reset_design.sql').read_text())
    sql.execute('UPDATE edition_products SET edition_total=2')
    reset=Reset(d.connect);reset.request(PID,str(uuid.uuid4()),'admin')
    assert rows(sql,'product_psd_mappings')==[]
    due(sql);d.tick(lambda c:dict(entries=[asset()],cursor='first',has_more=False),lambda fid:asset())
    assert selected(sql)['replacement']['stage']=='Queued' and rows(sql,'product_psd_mappings')==[]
    job=d.queue.claim('host')
    complete((d,sql,reset,None),job['lease_token'],tmp_path)
    assert rows(sql,'product_psd_mappings')[0]['dropbox_file_id']=='id:original'
    assert status.batch(d.connect,[PID])['rows'][0]['status']=='Review'


def test_authorised_manual_add_can_supersede_a_pending_reset_without_hanging_queue(design):
    d,sql,reset,old=design
    reset.request(PID,str(uuid.uuid4()),'admin');discover(design);old_lease=d.queue.claim('host')
    # Existing Add/Save may explicitly replace this mapping in its own transaction.
    sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:manual-new'")
    d.queue.enqueue(PID,'id:manual-new','admin')
    assert selected(sql)['replacement']['stage']=='Failed'
    next_job=d.queue.claim('host');assert next_job['file_id']=='id:manual-new'
    assert not selected(sql)['replacement']
    with pytest.raises(ValueError):d.queue.checkpoint(PID,str(old_lease['lease_token']),'host','Blocked','Late reset worker')


def test_public_reset_route_permissions_and_strict_scope(design):
    d,sql,reset,old=design
    import files_upload_api as files
    body={'product_gid':PID,'request_id':str(uuid.uuid4())}
    with patch.object(status.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=VA):
        assert asyncio.run(status.reset_action(request('POST',body=body))).status_code==403
    with patch.object(status,'actor',return_value=ADMIN),patch('supabase_backend.connect',d.connect):
        assert asyncio.run(status.reset_action(request('POST',body={**body,'edition_number':999}))).status_code==409
        assert asyncio.run(status.reset_action(request('POST',body=body))).status_code==200
    assert status.project({'product_gid':PID},writable=False)['reset_allowed'] is False


def test_pending_reset_details_remain_private_and_discovery_gate_is_respected(design,monkeypatch):
    d,sql,reset,old=design;rid=str(uuid.uuid4())
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    with pytest.raises(ValueError,match='disabled'):reset.request(PID,rid,'admin')
    assert not selected(sql)['replacement']
    monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','true');reset.request(PID,rid,'admin')
    public=status.batch(d.connect,[PID],writable=True)
    text=json.dumps(public)
    assert rid not in text and 'mapping_before' not in text and 'replacement' not in text and 'file_path' not in text
    assert public['rows'][0]['reset_allowed'] is False
    sql.execute("SELECT has_column_privilege('authenticated','auto_edition_onboarding','replacement','SELECT') AS allowed")
    assert not sql.fetchone()['allowed']


def test_reset_never_reuses_a_package_from_before_this_request(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'scripts/studio'));import auto_editions_local as local
    root=tmp_path/'jobs';folder=root/'old';folder.mkdir(parents=True)
    source=ae.source_identity(PID,asset());rid=str(uuid.uuid4())
    manifest=dict(source=source,edition_total=2,dimensions=[11340,8016],source_dimensions=[2835,2004],
                  preparation_geometry={'scale':4})
    ctx=dict(automatic=True,source=source,total=2,reset_id=rid)
    def write():
        with zipfile.ZipFile(folder/'prepared.zip','w') as z:z.writestr('manifest.json',json.dumps(manifest))
    with patch.object(local,'HOST_FILE',root/'host.dpapi'):
        write();assert local.find_reusable_package(ctx) is None
        manifest['reset_request_id']=rid;write()
        assert local.find_reusable_package(ctx)==folder/'prepared.zip' # same-reset transfer recovery only


@pytest.mark.parametrize('mode',['success','outdated_companion','interrupted_upload'])
def test_existing_import_upload_and_checkpoint_path_is_reused(design,tmp_path,mode):
    import shutil
    from starlette.requests import Request
    import auto_editions_setup_api as setup
    import auto_editions_cloud as cloud
    d,sql,reset,old=design;before=protected(sql);active=snapshot(selected(sql))
    reset.request(PID,str(uuid.uuid4()),'admin');pending=discover(design);job=d.queue.claim('host')
    source=pending['source'];folder=tmp_path/'generated';folder.mkdir()
    manifest=package(folder);manifest['source']=source
    if mode!='outdated_companion':manifest['reset_request_id']=pending['id']
    (folder/'manifest.json').write_text(json.dumps(manifest))
    shutil.copyfile(folder/'master.png',folder/'original.png')
    for number in (1,2):
        with ae.compose(manifest,folder,number) as image:image.save(folder/f'reference-{number}.png')
    archive=tmp_path/'redo.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for file in folder.iterdir():z.write(file,file.name)
    metadata={'retained-original':{'identity':'must not change'}};uploads=[];fail=[mode=='interrupted_upload']
    def upload(token,path,file,**kw):
        assert kw['conflict']=='cancel'
        if fail[0]:fail[0]=False;raise OSError('synthetic network loss')
        value=dict(id='id:redo-'+file.stem,rev='b1',name=file.name,path_display=path,size=file.stat().st_size,content_hash=ae.file_hash(file,dropbox=True))
        metadata[path]=value;uploads.append(path);return value
    integration=SimpleNamespace(ensure_folder_path=lambda *a,**kw:None,
        get_metadata_if_exists=lambda token,path:metadata.get(path),upload_local_file=upload)
    assets=cloud.DropboxAssets('synthetic',integration);registry=Preparations(d.connect)
    grant=dict(context=dict(automatic=True,product_gid=PID,lease_token=str(job['lease_token']),source=source,
                            number=1,total=2,reset_id=pending['id']),actor_id='host')
    body=archive.read_bytes()
    async def receive():return dict(type='http.request',body=body,more_body=False)
    def send():
        req=Request(dict(type='http',method='POST',path='/',headers=[],query_string=b''),receive)
        return asyncio.run(setup.package(req))
    with patch.object(setup,'grant_context',return_value=grant),patch.object(setup.runtime,'storage',return_value=assets),\
            patch.object(setup.runtime,'stores',return_value=(registry,None)),patch.object(api,'queue',return_value=d.queue):
        response=send()
        if mode=='interrupted_upload':
            assert response.status_code==503
            assert selected(sql)['replacement']['stage']=='Preparing'
            assert snapshot(selected(sql))==active and protected(sql)==before
            response=send()
    assert metadata['retained-original']=={'identity':'must not change'}
    assert protected(sql)==before
    if mode=='outdated_companion':
        assert response.status_code==409 and uploads==[]
        assert selected(sql)['replacement']['stage']=='Failed' and snapshot(selected(sql))==active
    else:
        assert response.status_code==200,response.body
        assert len(uploads)==3 and selected(sql)['replacement']['stage']=='Complete'
        assert selected(sql)['preparation_hash']==ae.fingerprint(manifest)
        assert status.batch(d.connect,[PID])['rows'][0]['status']=='Review'


def test_334_product_reset_status_performance_against_verified_baseline(store):
    import subprocess,types,statistics,tracemalloc
    d,sql=store
    sql.execute((ROOT/'supabase/migrations/20261015024929_auto_editions_reset_design.sql').read_text())
    sql.execute('DELETE FROM edition_products')
    sql.execute("""INSERT INTO edition_products SELECT 'gid://shopify/Product/'||n,n::text,
        'Synthetic Art '||n,'art-'||n,100,37,true,true FROM generate_series(1,334)n""")
    sql.execute("""INSERT INTO product_psd_mappings SELECT shopify_product_gid,'id:'||shopify_product_id,
        %s||'/Art '||shopify_product_id||'.psd','','manual','synthetic-admin',now(),now() FROM edition_products""",(asset()['path_display'].rsplit('/',1)[0],))
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,priority) SELECT shopify_product_gid,dropbox_file_id,2 FROM product_psd_mappings")
    source=subprocess.check_output(['git','show','607d10cb743694f5b94b1567897adad8280dd159:auto_editions_status.py'],text=True)
    baseline=types.ModuleType('synthetic_baseline_status');exec(compile(source,'verified_baseline_status.py','exec'),baseline.__dict__)
    ids=['gid://shopify/Product/'+str(n) for n in range(1,335)];metrics={}
    for name,module in (('verified_baseline',baseline),('with_reset',status)):
        times=[];tracemalloc.start()
        for _ in range(7):
            response=module.batch(d.connect,ids);times.append(response['duration_ms'])
            assert len(response['rows'])==334 and response['query_count']==1
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        metrics[name]=dict(median_ms=round(statistics.median(times),2),python_peak_bytes=peak,
                           response_bytes=len(json.dumps(response)),queries=1,dropbox_calls=0)
    target=ROOT/'output/reset/performance.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(metrics,indent=2))
