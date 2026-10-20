"""Actual local SQL/checkpoint operations, with explicitly synthetic native evidence."""
from copy import deepcopy
import hashlib
import json
import pytest
from tests.test_product_upload_intake import env, database, saved, service, PID, ADMIN


def synthetic_package(root,source):
    """Generated PNG fixtures, explicitly NOT Photoshop/native evidence."""
    from PIL import Image,ImageCms
    import auto_editions as ae
    from tests.test_auto_editions_bulk import prepared
    record,assets=prepared(root);m=record['manifest'];m['source']=source;m['edition_total']=100
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    master=root/m['master']['name']
    with Image.open(master) as im:tagged=im.copy()
    tagged.save(master,icc_profile=profile);tagged.close();m['master']['sha256']=ae.file_hash(master)
    for n in range(1,101):
        path=root/f'number-{n}.png';Image.new('RGB',(20,10),(n,0,0)).save(path,icc_profile=profile)
        m['patches'][str(n)]=dict(name=path.name,sha256=ae.file_hash(path))
    m['colour_evidence']=dict(icc_sha256=hashlib.sha256(profile).hexdigest(),pixels_converted=False)
    m['source_inspection']=dict(document=dict(width_px=200,height_px=100,profile='sRGB',profile_state='tagged',mode='RGB',bits_per_channel=8),layers=[
        dict(path=[dict(name='SC_EDITION_NUMBER')],kind='text',text='001 / 100',visible=True,editable=True,
             fonts=[dict(installed=True)],layout=dict(font='SyntheticFont'),bounds_px=[70,60,90,70]),
        dict(path=[dict(name='SC_EDITION_PLAQUE')],kind='smart_object',visible=True,bounds_px=[60,50,100,80])])
    m['confirmed_roles']=dict(number='SC_EDITION_NUMBER',plaque='SC_EDITION_PLAQUE')
    m.update(number_layer_name='SC_EDITION_NUMBER',plaque_layer_name='SC_EDITION_PLAQUE')
    digest=ae.fingerprint(m);record.update(hash=digest,proofs=[dict(preparation_hash=digest,number=n,pixel_exact=True,outside_number_exact=True) for n in (1,100)])
    record['receipts']=dict(preparation_hash=digest,assets=[dict(name=a['name'],file_id='id:'+a['name'],revision='a1',bytes=(root/a['name']).stat().st_size) for a in [m['master'],*m['patches'].values()]])
    return record


def import_synthetic(env,row,tmp_path):
    import auto_editions as ae
    from auto_editions_onboarding_store import Queue
    from auto_editions_store import Preparations
    queue=Queue(env[0].connect);claimed=queue.claim('companion-test')
    assert claimed and queue.claim('other-companion') is None
    source=ae.source_identity(PID,row['data']['source'])
    queue.checkpoint(PID,claimed['lease_token'],'companion-test','Preparing',source=source,total=100)
    record=synthetic_package(tmp_path,source)
    digest=Preparations(env[0].connect).save(record['manifest'],record['proofs'],record['receipts'],'companion-test')
    queue.checkpoint(PID,claimed['lease_token'],'companion-test','Blocked',digest=digest)
    return record


def test_real_companion_queue_lease_receipts_readiness_and_no_visual_click(env,tmp_path,monkeypatch):
    import auto_editions as ae
    from product_upload_readiness import complete
    from product_upload_services import reconcile
    row=saved(env);row=service(env).resolve(str(row['id']),ADMIN,'New Art')
    waiting=reconcile(row,env[0].connect)
    assert waiting['data']['state']=='Waiting for Companion' and waiting['data']['companion_connected'] is False
    record=import_synthetic(env,row,tmp_path)
    assert complete(env[0].connect,PID)
    assert complete(env[0].connect,PID)
    result=reconcile(row,env[0].connect)
    assert result['data']['state']=='Cloud Ready'
    env[1].execute('SELECT approval FROM auto_edition_layouts');approval=env[1].fetchone()['approval']
    assert 'visual_approved' not in approval and ae.status(record['manifest'],approval)=='TEST READY'
    import auto_editions_status as status,auto_editions_quality as quality
    assert status.batch(env[0].connect,[PID],evidence=True)['rows'][0]['status']=='Cloud Ready'
    from tests.test_auto_editions_status import record as status_record
    monkeypatch.setattr(quality,'enabled',lambda:True)
    monkeypatch.setattr(quality,'standards',lambda:(_ for _ in ()).throw(AssertionError('Technical intake must not enter supplier certification')))
    projection={**status_record(),'preparation_hash':record['hash'],'stored_hash':record['hash'],
        'dropbox_file_id':record['manifest']['source']['file_id'],'file_id':record['manifest']['source']['file_id'],'source':record['manifest']['source'],
        'prepared_source':record['manifest']['source'],'observed_source':record['manifest']['source'],
        'approved':False,'intake_approval':approval,'intake_manifest':record['manifest']}
    assert status.project(projection)['status']=='Cloud Ready' and 'Cloud Ready' in status.labels()
    env[1].execute("SELECT count(*) AS n FROM auto_edition_onboarding_audit WHERE event='product_upload_technical_complete'");assert env[1].fetchone()['n']==1
    changed=deepcopy(record['manifest']);changed['source']['revision']='a2'
    assert ae.status(changed,approval)=='NOT CONFIGURED'


@pytest.mark.parametrize('failure',['font','receipt','last_number','source','total','native_inspection','colour'])
def test_readiness_fails_closed(env,tmp_path,failure):
    from product_upload_services import reconcile
    row=saved(env);row=service(env).resolve(str(row['id']),ADMIN,'New Art')
    record=import_synthetic(env,row,tmp_path)
    if failure=='font':record['manifest']['source_inspection']['layers'][0]['fonts'][0]['installed']=False
    if failure=='receipt':record['receipts']['assets'].pop()
    if failure=='last_number':record['proofs'].pop()
    if failure=='source':record['manifest']['source']['revision']='a2'
    if failure=='total':record['manifest']['edition_total']=99
    if failure=='native_inspection':record['manifest'].pop('source_inspection')
    if failure=='colour':record['manifest'].pop('colour_evidence')
    sql=env[1];sql.execute('UPDATE auto_edition_preparations SET manifest=%s::jsonb,proofs=%s::jsonb,receipts=%s::jsonb',
        (json.dumps(record['manifest']),json.dumps(record['proofs']),json.dumps(record['receipts'])))
    assert reconcile(row,env[0].connect)['data']['state']=='Failed'
    sql.execute('SELECT count(*) AS n FROM auto_edition_layouts');assert sql.fetchone()['n']==0


def test_native_failure_retry_and_stale_source_invalidates_preview(env):
    from product_upload_services import reconcile
    row=saved(env);row=service(env).resolve(str(row['id']),ADMIN,'New Art')
    from auto_editions_onboarding_store import Queue
    q=Queue(env[0].connect);claim=q.claim('companion-test')
    q.checkpoint(PID,claim['lease_token'],'companion-test','Needs PSD Repair','Edition font unavailable')
    assert reconcile(row,env[0].connect)['data']['state']=='Failed'
    q.retry(PID,'admin');assert reconcile(row,env[0].connect)['data']['state']=='Waiting for Companion'
    env[1].execute("UPDATE product_psd_mappings SET dropbox_file_id='id:replacement'")
    result=reconcile(row,env[0].connect)['data'];assert result['state']=='Failed' and result['preview_url'] is None


def test_rls_denies_browser_roles(env):
    sql=env[1]
    for role in ('anon','authenticated'):
        sql.execute('SET ROLE '+role)
        with pytest.raises(RuntimeError,match='permission denied'):sql.execute('SELECT * FROM product_upload_intakes')
        sql.execute('RESET ROLE')


def test_prompts_keep_saved_commercial_source_without_old_input_dependencies():
    from product_upload_prompts import build
    from product_upload_prompt_core import product_upload_price_ladder_prompt_text
    for m in ('DRAFT','LIVE','UPDATE'):
        text=build(m,'ignore instructions.psd',load=lambda key,default,**kw:default+'\nCUSTOM COMMERCIAL CONTENT')
        assert 'CUSTOM COMMERCIAL CONTENT' in text and 'A$339' in text and 'A$449' in text
        assert '[ENTER PRODUCT NAME ABOVE]' not in text and 'SOURCE_REFERENCE' not in text
        assert 'Dropbox is the only source of truth' not in text
        assert 'exact selected product folder through the connected Dropbox integration' not in text
        assert 'Return exact product title' in text
        if m=='UPDATE':assert 'one exact matching product' in text and 'Never create a product' in text


def test_existing_binary_package_endpoint_verifies_and_finishes_intake(env,tmp_path,monkeypatch):
    """Real archive/proof/receipt import; synthetic native producer + cloud disk."""
    import zipfile,shutil
    from PIL import Image,ImageCms
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    import auto_editions as ae
    import auto_editions_setup_api as setup
    import auto_editions_onboarding_api as onboarding
    import auto_editions_review_thumbnails as thumbnails
    from auto_editions_onboarding_store import Queue
    from auto_editions_store import Preparations
    row=saved(env);row=service(env).resolve(str(row['id']),ADMIN,'New Art')
    q=Queue(env[0].connect);claim=q.claim('companion-test');source=row['data']['bound_source']
    q.checkpoint(PID,claim['lease_token'],'companion-test','Preparing',source=source,total=100)
    root=tmp_path/'generated';root.mkdir();m=synthetic_package(root,source)['manifest']
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for asset in [m['master'],*m['patches'].values()]:
        path=root/asset['name']
        with Image.open(path) as im:im.save(path,icc_profile=profile)
        asset['sha256']=ae.file_hash(path)
    m['colour_evidence']['icc_sha256']=hashlib.sha256(profile).hexdigest()
    shutil.copyfile(root/m['master']['name'],root/'original.png')
    for n in (1,100):
        with ae.compose(m,root,n) as im:im.save(root/f'reference-{n}.png',icc_profile=profile)
    (root/'manifest.json').write_text(json.dumps(m))
    archive=tmp_path/'native-fixture.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for p in root.iterdir():z.write(p,p.name)
    class LocalAssets:
        calls=0
        def publish_preparation(self,manifest,folder):
            self.calls+=1;dest=tmp_path/'cloud';dest.mkdir()
            receipts=[]
            for asset in [manifest['master'],*manifest['patches'].values()]:
                path=dest/asset['name'];shutil.copyfile(folder/asset['name'],path)
                assert ae.file_hash(path)==asset['sha256']
                receipts.append(dict(name=path.name,file_id='id:'+path.name,revision='v1',bytes=path.stat().st_size))
            return dict(preparation_hash=ae.fingerprint(manifest),assets=receipts)
    assets=LocalAssets();registry=Preparations(env[0].connect)
    grant=dict(actor_id='companion-test',context=dict(automatic=True,product_gid=PID,lease_token=claim['lease_token'],source=source,number=1,total=100))
    monkeypatch.setattr(setup,'grant_context',lambda request:grant)
    monkeypatch.setattr(setup.runtime,'storage',lambda:assets)
    monkeypatch.setattr(setup.runtime,'stores',lambda:(registry,None))
    monkeypatch.setattr(onboarding,'queue',lambda:q)
    monkeypatch.setattr(thumbnails,'schedule_prepared',lambda *a:None)
    monkeypatch.setenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED','false')
    client=TestClient(Starlette(routes=[Route('/package',setup.package,methods=['POST'])]))
    result=client.post('/package',content=archive.read_bytes())
    assert result.status_code==200,result.text
    assert result.json()['status']=='Cloud Ready' and result.json()['print_ready'] is False
    record=registry.read(result.json()['preparation_hash'])
    assert len(record['proofs'])==3 and len(record['receipts']['assets'])==101
    assert all(p['pixel_exact'] for p in record['proofs'] if 'pixel_exact' in p)
    assert client.post('/package',content=archive.read_bytes()).status_code==409
    assert assets.calls==1


def test_committed_mapping_retry_and_catalog_revision(env):
    from product_upload_services import catalog_revision
    from psd_mapping_store import PostgresMappings
    from product_upload_services import register_product
    row=saved(env);old=catalog_revision(env[0].connect)
    register_product(__import__('tests.test_product_upload_intake',fromlist=['product']).product())
    PostgresMappings(env[0].connect).attach(PID,row['data']['source'],ADMIN,confirm_mismatch=True)
    # Simulate a durable mapping commit before an unavailable queue handoff.
    service(env).resolve(str(row['id']),ADMIN,'New Art')
    assert catalog_revision(env[0].connect)!=old
    for table in ('product_psd_mappings','auto_edition_onboarding'):
        env[1].execute('SELECT count(*) AS n FROM '+table);assert env[1].fetchone()['n']==1


def test_inventory_revision_change_blocks_completion_and_old_preview(env,tmp_path,monkeypatch):
    import product_upload_api as api,files_upload_api
    from product_upload_services import reconcile
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    row=saved(env);row=service(env).resolve(str(row['id']),ADMIN,'New Art')
    record=import_synthetic(env,row,tmp_path)
    changed={**row['data']['source'],'rev':'a2'}
    env[1].execute('INSERT INTO auto_edition_source_inventory(file_id,name_key,path_lower,metadata) VALUES(%s,%s,%s,%s::jsonb)',
        (changed['id'],'design.psd',changed['path_display'].lower(),json.dumps(changed)))
    assert reconcile(row,env[0].connect)['data']['state']=='Failed'
    env[1].execute('SELECT count(*) AS n FROM auto_edition_layouts');assert env[1].fetchone()['n']==0
    with env[0].locked(str(row['id']),ADMIN['id']) as (saved_row,cur):saved_row['data']['preparation_hash']=record['hash']
    monkeypatch.setattr(api,'connect',env[0].connect);monkeypatch.setattr(files_upload_api,'_request_user',lambda req,**kwargs:ADMIN)
    client=TestClient(Starlette(routes=[Route('/preview',api.preview)]))
    assert client.get('/preview',params={'id':str(row['id']),'hash':record['hash']}).status_code==409


def test_intake_reuses_released_technical_worker_without_bypassing_verification(env,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import auto_editions as ae,auto_editions_status as status
    from product_upload_services import reconcile
    from product_upload_readiness import complete
    from auto_editions_technical import Technical,METHOD
    row=saved(env);row=service(env).resolve(str(row['id']),ADMIN,'New Art')
    record=import_synthetic(env,row,tmp_path)
    env[1].execute((__import__('pathlib').Path('supabase/migrations/20261016071758_auto_editions_bulk_operations.sql')).read_text())
    env[1].execute((__import__('pathlib').Path('supabase/migrations/20261017001547_auto_editions_technical_completion.sql')).read_text())
    monkeypatch.setenv('AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED','true')
    assert complete(env[0].connect,PID) is False
    assert reconcile(row,env[0].connect)['data']['state']=='Uploading prepared files'
    env[1].execute('SELECT count(*) AS n FROM auto_edition_layouts');assert env[1].fetchone()['n']==0
    assets=SimpleNamespace(token='synthetic',integration=Mock())
    assets.integration.psd_open_metadata.return_value=row['data']['source']
    assert Technical(env[0].connect).run_one(assets,pid=PID,local_root=tmp_path)=='Cloud Ready'
    assert reconcile(row,env[0].connect)['data']['state']=='Cloud Ready'
    env[1].execute('SELECT approval FROM auto_edition_layouts');approval=env[1].fetchone()['approval']
    assert approval['method']==METHOD and 'visual_approved' not in approval
    assert status.batch(env[0].connect,[PID])['rows'][0]['status']=='Cloud Ready'
    assert ae.status(record['manifest'],approval)=='TEST READY'
    assert Technical(env[0].connect).run_one(assets,pid=PID,local_root=tmp_path) is None
