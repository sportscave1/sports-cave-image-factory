"""Cross-module acceptance with real disposable SQL and synthetic pixels only."""
import asyncio
import json
import shutil
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from PIL import Image
from starlette.requests import Request
import auto_editions as ae
import auto_editions_cloud as cloud
import auto_editions_onboarding_api as onboarding
import auto_editions_setup_api as setup
import auto_editions_status as status
from auto_editions_store import Preparations
from auto_editions_jobs import Jobs
from tests.test_auto_editions_discovery import database,store,pglite_database,PID,asset,tick,register,rows
from tests.test_auto_editions_api import request,ADMIN
from tests.test_auto_editions import package


def test_late_psd_to_review_approval_and_existing_allocated_test_jpg(store,tmp_path):
    discovery,sql=store
    protected=lambda:(rows(sql,'edition_products'),rows(sql,'edition_allocations'),rows(sql,'synthetic_certificates'))
    before=protected()
    original=tmp_path/'original.psd';original.write_bytes(b'synthetic source never modified')
    archived=tmp_path/'archived.jpg';archived.write_bytes(b'existing archived JPG never modified')
    register(store);tick(store)
    assert rows(sql,'auto_edition_discovery')[0]['status']=='Waiting for PSD'
    tick(store,[asset()]);register(store,'duplicate');tick(store)
    assert status.batch(discovery.connect,[PID])['rows'][0]['status']=='Queued'
    lease=discovery.queue.claim('admin')
    lease['lease_token']=str(lease['lease_token'])  # Wire context serializes UUIDs.
    source=ae.source_identity(PID,asset())
    discovery.queue.checkpoint(PID,lease['lease_token'],'admin','Preparing',source=source,total=100)
    assert status.batch(discovery.connect,[PID])['rows'][0]['status']=='Preparing'
    prepared=tmp_path/'prepared';prepared.mkdir();manifest=package(prepared)
    manifest.update(source=source,edition_total=100)
    for n in range(3,101):
        name=f'number-{n}.png';Image.new('RGB',(20,10),(n,0,0)).save(prepared/name)
        manifest['patches'][str(n)]={'name':name,'sha256':ae.file_hash(prepared/name)}
    (prepared/'manifest.json').write_text(json.dumps(manifest))
    shutil.copyfile(prepared/'master.png',prepared/'original.png')
    for n in (1,100):
        with ae.compose(manifest,prepared,n) as im:im.save(prepared/f'reference-{n}.png')
    archive=tmp_path/'package.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for file in prepared.iterdir():z.write(file,file.name)
    registry=Preparations(discovery.connect);metadata={};uploads=[]
    def upload(token,path,file,**kwargs):
        assert kwargs['conflict']=='cancel' and path not in metadata
        metadata[path]=dict(id='id:prepared-'+file.stem,rev='b1',name=file.name,path_display=path,
                            size=file.stat().st_size,content_hash=ae.file_hash(file,dropbox=True))
        uploads.append(path);return metadata[path]
    integration=SimpleNamespace(ensure_folder_path=lambda *a,**k:None,
        get_metadata_if_exists=lambda token,path:metadata.get(path),upload_local_file=upload,
        psd_open_metadata=lambda *a,**k:asset())
    class Assets(cloud.DropboxAssets):
        def fetch(self,digest,item,destination):
            shutil.copyfile(prepared/item['name'],destination)
            assert ae.file_hash(destination)==item['sha256']
        def publish_output(self,job,path):
            target=tmp_path/(job['id']+'.jpg')
            with target.open('xb') as out:out.write(path.read_bytes())
            return {'sha256':ae.file_hash(target),'file_id':'id:synthetic-test-jpg'}
    assets=Assets('synthetic-token',integration)
    ctx={'automatic':True,'product_gid':PID,'lease_token':lease['lease_token'],'source':source,'number':1,'total':100}
    grant={'context':ctx,'actor_id':'admin'}
    body=archive.read_bytes()
    async def receive():return {'type':'http.request','body':body,'more_body':False}
    req=Request({'type':'http','method':'POST','path':'/','headers':[],'query_string':b''},receive)
    with patch.object(setup,'grant_context',return_value=grant),patch.object(setup.runtime,'storage',return_value=assets),\
            patch.object(setup.runtime,'stores',return_value=(registry,None)),patch.object(onboarding,'queue',return_value=discovery.queue):
        response=asyncio.run(setup.package(req))
    assert response.status_code==200,response.body
    digest=json.loads(response.body)['preparation_hash']
    assert len(uploads)==101 and digest==ae.fingerprint(manifest)
    assert status.batch(discovery.connect,[PID])['rows'][0]['status']=='Review'
    assert discovery.queue.completed_receipt(PID,lease['lease_token'],'admin')['preparation_hash']==digest
    # Interrupted transfer resumes by verified immutable identities, no overwrites.
    assets.publish_preparation(manifest,prepared);assert len(uploads)==101
    with patch.object(onboarding,'queue',return_value=discovery.queue),\
            patch.object(onboarding.runtime,'stores',return_value=(registry,None)),\
            patch.object(onboarding.runtime,'storage',return_value=assets),\
            patch.object(onboarding.api,'actor',new=AsyncMock(return_value=ADMIN)):
        approval=asyncio.run(onboarding.approve(request('POST',body={'product_gid':PID,'hash':digest,'confirm_visual_quality':True})))
    assert approval.status_code==200,approval.body
    assert status.batch(discovery.connect,[PID])['rows'][0]['status']=='Cloud Ready'
    unit=dict(id=1,allocation_valid=True,identity_enforced=True,status='completed',edition_number=36,
              edition_total=100,allocation_index=1,shopify_variant_id='variant-test',shopify_order_id='order-test',
              shopify_line_item_id='line-test',shopify_product_gid=PID)
    # Existing synthetic ledger row supplies number 36. No allocation creation API.
    assert rows(sql,'edition_allocations')[0]['number']==unit['edition_number']
    mapping={'verified':True,'state':'Linked','dropbox_file_id':'id:original'}
    job=cloud.confirmed_job(unit,mapping,asset(),registry.for_unit(unit))
    jobs=Jobs(discovery.connect);jobs.enqueue(job,'admin');jobs.enqueue(job,'admin')
    claimed=jobs.claim();assert claimed and jobs.claim() is None
    output=cloud.execute(job,assets)
    jobs.finish(job['id'],claimed['lease_token'],result=output)
    assert output['test_only'] is True and output['print_ready'] is False
    assert len(rows(sql,'auto_edition_jobs'))==1 and protected()==before
    assert original.read_bytes()==b'synthetic source never modified'
    assert archived.read_bytes()==b'existing archived JPG never modified'
    assert ae.fingerprint(manifest)==digest
