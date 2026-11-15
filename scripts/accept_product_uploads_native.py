"""Explicit, exclusive native acceptance. Synthetic artwork and local providers only.

Run only after the production Companion has normally stopped for maintenance.
Existing documents, journals and the non-stealable processor fence are preserved.
No production credentials, Shopify/Dropbox writes, or installed-host changes.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts/studio')]


def accept(root):
    allowed = {'SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP','COMSPEC',
               'USERPROFILE','APPDATA','LOCALAPPDATA','AUTO_EDITIONS_TEST_PGLITE','PYTHONUTF8'}
    clean = {k:v for k,v in os.environ.items() if k.upper() in allowed}
    os.environ.clear(); os.environ.update(clean)
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    # The disposable PGlite HTTP server closes idle keep-alives while native
    # Photoshop runs. Refresh only this test transport, never production SQL.
    import http.client
    connection = http.client.HTTPConnection
    class TestConnection(connection):
        last_request = 0
        def request(self, *args, **kwargs):
            now = time.monotonic()
            if now-self.last_request > 2: self.close()
            self.last_request = now
            return super().request(*args, **kwargs)
    http.client.HTTPConnection = TestConnection
    from scripts.benchmark_auto_editions_native_v19 import require_admission, processor_lease, cleanup_proven, Sample
    require_admission()  # Before any fixture, lock acquisition or COM call.
    root = Path(root).resolve()
    if root.exists() or not root.is_relative_to(ROOT/'output/v19'):
        raise ValueError('Use a new directory under this task output/v19.')
    if len(str(root))>130:
        raise ValueError('Choose a short output/v19 name within the Windows/Photoshop path budget.')
    root.mkdir(parents=True)
    import hashlib
    import shutil
    import zipfile
    from types import SimpleNamespace
    from unittest.mock import Mock
    import pytest
    import requests
    from PIL import Image
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from scripts.photoshop_dispatch import run
    import auto_editions as ae
    from tests.test_product_upload_intake import database, env, saved, service, ADMIN, PID
    from product_upload_render import Renders
    from product_upload_services import reconcile
    from scripts.render_product_upload_psd import render
    from scripts.prepare_auto_editions import prepare, native_cleanup_uncertain
    from auto_editions_onboarding_store import Queue
    from auto_editions_store import Preparations
    from product_upload_mockups import bind_export
    import image_factory
    import product_upload_api as api
    import auto_editions_setup_api as setup
    import auto_editions_onboarding_api as onboarding
    import auto_editions_review_thumbnails as thumbnails
    import files_upload_api
    from scripts.studio.product_upload_render_local import run_one
    report = dict(real_photoshop=True, providers='Isolated local disk doubles; no production writes', stages={})
    lib = (ROOT/'scripts/photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig').split('if(typeof SC_PSD_INSPECT_REQUEST')[0]
    inventory = lib + '\n(function(){var a=[];for(var i=0;i<app.documents.length;i++){var d=app.documents[i];a.push({id:d.id,name:d.name,saved:d.saved,layers:d.layers.length});}return SCPSDInspector.encode({documents:a,active:app.documents.length?app.activeDocument.id:null});})();'
    journals = Path.home()/'Documents/SportsCaveAutoEditions'
    def journal_hashes():
        return {str(p.relative_to(journals)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in journals.glob('*/job-state.json')}
    before_journals = journal_hashes()
    lease = None; uncertain = False; db = None; patch = pytest.MonkeyPatch()
    original_request = requests.sessions.Session.request
    def local_only(self, method, url, *args, **kwargs):
        from urllib.parse import urlparse
        if urlparse(str(url)).hostname not in ('127.0.0.1','localhost','::1'):
            raise RuntimeError('Native acceptance cannot use external providers.')
        return original_request(self, method, url, *args, **kwargs)
    patch.setattr(requests.sessions.Session, 'request', local_only)
    try:
        lease = processor_lease()
        before = json.loads(run(inventory)); report['documents_before'] = before
        source = root/'synthetic-100.psd'
        fixture = lib+'\nvar SC_V19_FIXTURE_REQUEST='+json.dumps(dict(root=str(root),path=str(source),width=2400,height=1600))+';\n'
        fixture += (ROOT/'scripts/photoshop/benchmark_auto_editions_fixture.jsx').read_text(encoding='utf-8-sig')
        uncertain = True
        try:
            assert run(fixture) == 'V19_SYNTHETIC_FIXTURE_CREATED'
        finally:
            uncertain = not cleanup_proven(root,'fixture-status.json')
        assert not uncertain
        lease.unlink(); lease = None
        source_sha = ae.file_hash(source)
        report['source'] = dict(path=str(source),sha256=source_sha,bytes=source.stat().st_size)
        db = database.__wrapped__(); fixture_db = next(db)
        store, sql, provider = local = env.__wrapped__(fixture_db,root,patch)
        for name in ('20261016071758_auto_editions_bulk_operations.sql','20261017001547_auto_editions_technical_completion.sql'):
            sql.execute((ROOT/'supabase/migrations'/name).read_text(encoding='utf-8'))
        patch.setenv('AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED','true')
        row = saved(local,data=source.read_bytes()); key = str(row['id'])
        renders = Renders(store.connect); renders.request(key,ADMIN['id'])
        patch.setattr(api,'connect',store.connect); patch.setattr(api,'Dropbox',lambda:provider)
        async def actor(request): return ADMIN
        patch.setattr(onboarding,'preparation_actor',actor)
        patch.setattr(onboarding,'host_health',lambda *a:None)
        patch.setattr(files_upload_api,'_dropbox_context',lambda:dict(access_token='isolated',root_path='/Sportscave Team Folder'))
        patch.setattr(files_upload_api.dropbox_integration,'psd_open_metadata',lambda *a,**kw:row['data']['source'])
        patch.setattr(files_upload_api.NATIVE_TRANSFER_MANAGER,'create_psd',lambda **kw:SimpleNamespace(ticket='isolated',secret='isolated'))
        def save_render(k,path):
            target=root/'cloud-render.png';shutil.copyfile(path,target)
            assert ae.file_hash(target)==ae.file_hash(path)
            return dict(id='id:local-render',rev='1',content_hash=ae.file_hash(target,dropbox=True))
        provider.save_render=save_render
        client=TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]))
        config=dict(base_url='http://127.0.0.1',token='isolated-host')
        def host_request(config,path,body):
            if path.endswith('/claim'):body={**body,'health':{'state':'Idle'}}
            response=client.post(path,json=body,headers={'X-Sports-Cave-Preparation-Host':config['token']})
            response.raise_for_status();return response.json()
        claimed=host_request(config,'/api/product-uploads/render/claim',{})['job']
        # Keep native filenames inside Windows/Photoshop's legacy path budget.
        host_root=root/'h';host_root.mkdir()
        retained=host_root/('product-upload-'+key+'-attempt-1');retained.mkdir()
        shutil.copyfile(source,retained/'input.psd')  # Existing verified download cache; native render is real.
        host=SimpleNamespace(HOST_FILE=host_root/'host.dpapi',JOBS={},host_request=host_request,
            processor_lease=processor_lease,atomic_json=lambda p,v:p.write_text(json.dumps(v),encoding='utf-8'))
        def post(url,**kw):
            return client.post(url,content=kw['data'],headers=kw['headers'])
        patch.setattr(requests,'post',post)
        with Sample(retained) as sample:
            assert run_one(config,host)
        report['stages']['native_render']=sample.result()
        current=store.read(key,ADMIN['id']); value=current['data']['mockup_render']
        assert value['state']=='Ready',value
        render_path=root/'cloud-render.png'
        with Image.open(render_path) as im:
            assert im.size==(2000,1333) and im.info.get('icc_profile')
        assert ae.file_hash(source)==source_sha and not host.JOBS
        report['stages']['native_render'].update(bytes=render_path.stat().st_size,dimensions=[2000,1333],receipt=value['receipt'])
        assert renders.claim(ADMIN['id']) is None
        # Real native conversion/alpha plus exact synthetic policy assignment.
        # The approved policy is an in-process fixture, never operator config.
        import struct
        from unittest.mock import patch as scoped_patch
        from PIL import ImageCms
        import io
        from auto_editions_colour_source import inspect_psd, ColourReview
        from tests.test_auto_editions_colour import approved
        def exact_identity(path,label):
            return dict(template_id='synthetic-acceptance:'+label,file_id='id:local-'+label,revision='1',content_hash=ae.file_hash(path,dropbox=True))
        def native_render(path,folder,identity):
            nonlocal lease,uncertain
            lease=processor_lease();uncertain=True
            try:return render(path,folder,identity)
            finally:
                uncertain=(folder/'dispatch-intent.json').exists() and not cleanup_proven(folder)
                if not uncertain:lease.unlink();lease=None
        meta=inspect_psd(source);raw=source.read_bytes()
        blocks=b''.join(block for rid,block in meta['blocks'] if rid not in (1039,1041))
        untagged=root/'synthetic-untagged.psd'
        untagged.write_bytes(raw[:meta['length_offset']]+struct.pack('>I',len(blocks))+blocks+raw[meta['tail_offset']:])
        untagged_sha=ae.file_hash(untagged);untagged_identity=exact_identity(untagged,'untagged')
        with scoped_patch('auto_editions_colour_policy.load_policies',return_value=[]):
            try:render(untagged,root/'unapproved-render',untagged_identity)
            except ColourReview:pass
            else:raise AssertionError('Unknown untagged source was accepted')
        assert not (root/'unapproved-render').exists()
        policy=approved(untagged_identity,meta['icc'])
        with scoped_patch('auto_editions_colour_policy.load_policies',return_value=[policy]):
            assigned_path,assigned_receipt=native_render(untagged,root/'approved-untagged-render',untagged_identity)
        assert ae.file_hash(untagged)==untagged_sha and assigned_receipt['colour']['assignment']['pixels_converted'] is False
        colour_root=root/'adobe-rgb-transparent';colour_root.mkdir();adobe=colour_root/'synthetic.psd'
        script=lib+'\nvar SC_V19_FIXTURE_REQUEST='+json.dumps(dict(root=str(colour_root),path=str(adobe),width=640,height=480))+';\n'
        script+=(ROOT/'scripts/photoshop/benchmark_auto_editions_fixture.jsx').read_text(encoding='utf-8-sig').replace('DocumentFill.WHITE','DocumentFill.TRANSPARENT').replace('"sRGB IEC61966-2.1"','"Adobe RGB (1998)"')
        lease=processor_lease();uncertain=True
        try:assert run(script)=='V19_SYNTHETIC_FIXTURE_CREATED'
        finally:
            uncertain=not cleanup_proven(colour_root,'fixture-status.json')
            if not uncertain:lease.unlink();lease=None
        adobe_sha=ae.file_hash(adobe);adobe_meta=inspect_psd(adobe)
        converted,converted_receipt=native_render(adobe,colour_root/'render',exact_identity(adobe,'adobe-rgb'))
        assert ae.file_hash(adobe)==adobe_sha
        with Image.open(adobe) as original,Image.open(converted) as web:
            rgb=Image.new('RGB',(1,1),original.convert('RGB').getpixel((150,40)))
            expected=ImageCms.profileToProfile(rgb,ImageCms.ImageCmsProfile(io.BytesIO(adobe_meta['icc'])),ImageCms.createProfile('sRGB'),renderingIntent=1).getpixel((0,0))
            actual=web.convert('RGB').getpixel((150,40))
            assert max(abs(a-b) for a,b in zip(actual,expected))<=2,(actual,expected)
            assert web.mode=='RGBA' and web.getpixel((20,450))[3]==0
        report['stages']['native_colour']=dict(unknown_untagged_rejected=True,approved_untagged_assignment=assigned_receipt,
            adobe_rgb_conversion=converted_receipt,transparent_pixels_preserved=True,pixel_actual=actual,pixel_expected=expected)
        started=time.perf_counter()
        # Use the same short managed web-image temp root as the actual UI. The
        # task checkout is too deep for nested Windows lifestyle staging paths.
        result=image_factory.generate_product_images('Native','Basketball',render_path,base_dir=ROOT,output_root=image_factory.create_temp_run_parent())
        assert len(result['assets'])==5
        generated=[]
        for asset in result['assets']:
            path=Path(asset['webp_path'])
            with Image.open(path) as image: image.verify()
            generated.append(dict(label=asset['label'],filename=path.name,bytes=path.stat().st_size))
        report['stages']['core_mockups']=dict(seconds=time.perf_counter()-started,assets=generated)
        # ChatGPT scene generation is external: use the native synthetic PNG as
        # each room's isolated upload, through the actual existing image handling.
        from tests.test_mockup_upload_validation import Upload
        prompts=image_factory.build_lifestyle_prompt_items(result['product_name'],result['sport_category'],local_only=True)
        assert len(prompts)==3
        for spec in image_factory.PRODUCT_IMAGE_SLOT_SPECS:
            if not spec.get('prompt_filename'):continue
            paths=image_factory.save_lifestyle_mockup(result['run_dir'],result['product_slug'],result['sport_slug'],spec['prompt_filename'],Upload(render_path.read_bytes(),'synthetic-lifestyle.png'))
            result['assets'].append(image_factory.build_asset_record(key=spec['asset_key'],label=spec['display_label'],
                asset_group='lifestyle',zip_group=spec['zip_group'],prompt_filename=spec['prompt_filename'],
                webp_path=paths['webp_path'],jpg_path=paths['jpg_path'],export_to_shopify=True,export_to_socials=True))
        result['product_image_manifest']=image_factory.build_product_image_manifest(result['assets'],product_slug=result['product_slug'],sport_slug=result['sport_slug'])
        result['assets']=image_factory.order_assets_by_product_manifest(result['assets'],result['product_image_manifest'])
        archive_images=image_factory.create_complete_pack_zip(result['zip_dir'],result['product_slug'],assets=result['assets'])
        shutil.copyfile(archive_images,root/'images.zip')
        with zipfile.ZipFile(archive_images) as archive: names=archive.namelist()
        assert len(names)==16 and len(set(names))==16
        result.update(_product_upload_intake=key,_product_upload_source_hash=row['data']['source']['content_hash'])
        bind_export(store.connect,ADMIN['id'],result,'ZIP')
        report['stages']['image_export']=dict(lifestyle_prompts=[p['filename'] for p in prompts],zip=str(archive_images),files=names,lifestyle_source='Synthetic native PNG, not generated lifestyle scenes')
        store.copied(key,ADMIN['id'],'DRAFT')
        bound=service(local).resolve(key,ADMIN,'New Art')
        q=Queue(store.connect);claim=q.claim('isolated-native');assert claim and q.claim('second-host') is None
        identity=bound['data']['bound_source']
        q.checkpoint(PID,claim['lease_token'],'isolated-native','Preparing',source=identity,total=100)
        native=root/'native-preparation';lease=processor_lease();uncertain=True
        try:
            with Sample(native) as sample:
                prepared=prepare(source,native,identity,number_layer='SC_EDITION_NUMBER',plaque_layer='SC_EDITION_PLAQUE',total=100,reference_number=1,scale=1)
        finally:
            uncertain=native_cleanup_uncertain(native)
            if not uncertain:lease.unlink();lease=None
        report['stages']['native_preparation']={**sample.result(),**prepared}
        assert prepared['source_unchanged'] and all(p['pixel_exact'] for p in prepared['proofs'])
        class Assets:
            calls=0
            def publish_preparation(self,manifest,folder):
                self.calls+=1;target=root/'cloud-preparation';target.mkdir()
                receipts=[]
                for a in [manifest['master'],*manifest['patches'].values()]:
                    path=target/a['name'];shutil.copyfile(folder/a['name'],path)
                    assert ae.file_hash(path)==a['sha256']
                    receipts.append(dict(name=path.name,file_id='id:local:'+path.name,revision='1',bytes=path.stat().st_size))
                return dict(preparation_hash=ae.fingerprint(manifest),assets=receipts)
        assets=Assets();registry=Preparations(store.connect)
        assets.token='isolated'
        assets.integration=SimpleNamespace(psd_open_metadata=lambda token,key,**kw:provider.metadata_if_present(key))
        grant=dict(actor_id='isolated-native',context=dict(automatic=True,product_gid=PID,lease_token=claim['lease_token'],source=identity,number=1,total=100))
        patch.setattr(setup,'grant_context',lambda request:grant)
        patch.setattr(setup.runtime,'storage',lambda:assets)
        patch.setattr(setup.runtime,'stores',lambda:(registry,None))
        patch.setattr(onboarding,'queue',lambda:q)
        patch.setattr(thumbnails,'schedule_prepared',lambda *a:None)
        patch.setenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED','false')
        archive=root/'native-package.zip'
        manifest=json.loads((native/'manifest.json').read_text(encoding='utf-8'))
        manifest['confirmed_roles']=dict(number='SC_EDITION_NUMBER',plaque='SC_EDITION_PLAQUE')
        (native/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        names=['manifest.json','master.png','original.png']+[p['name'] for p in manifest['patches'].values()]+['reference-1.png','reference-100.png']
        from auto_editions_transport import build_package
        build_package(native,names,archive,compact=True)
        package_client=TestClient(Starlette(routes=[Route('/package',setup.package,methods=['POST'])]))
        with archive.open('rb') as stream:response=package_client.post('/package',content=stream)
        assert response.status_code==200,response.text
        assert response.json()['status']=='Cloud Ready',response.text
        assert reconcile(store.read(key,ADMIN['id']),store.connect)['data']['state']=='Cloud Ready'
        assert assets.calls==1
        sql.execute('SELECT approval FROM auto_edition_layouts')
        certificate=sql.fetchone()['approval'];assert certificate['technical_verified'] is True
        with archive.open('rb') as stream:assert package_client.post('/package',content=stream).status_code==409
        assert assets.calls==1
        report['stages']['handoff']=dict(result=response.json(),verified_receipts=101,duplicate_rejected=True,technical_certificate=certificate)
        report['source_unchanged']=ae.file_hash(source)==source_sha
        lease=processor_lease();after=json.loads(run(inventory));lease.unlink();lease=None
        report['documents_after']=after;assert after==before
        assert journal_hashes()==before_journals
        report.update(passed=True,existing_journals_unchanged=True,existing_journal_count=len(before_journals))
        return report
    except Exception as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error))
        raise
    finally:
        (root/'acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        patch.undo()
        if db:db.close()
        if lease and not uncertain:lease.unlink()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(accept(args.output),indent=2),flush=True)
