"""Local SQL + source/worker/export doubles. No production credentials or writes."""
import io
import json
import uuid
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from PIL import Image
from tests.test_product_upload_intake import database,env,saved,product,service,ADMIN,psd,digest
from tests.test_auto_editions_colour import psd as colour_psd,icc,approved
from product_upload_render import Renders,identity
from product_upload_services import Dropbox
from product_upload_mockups import bind_export,save


def test_render_claim_is_source_pinned_owner_scoped_and_pause_aware(env):
    store,sql,provider=env;row=saved(env);key=str(row['id']);renders=Renders(store.connect)
    renders.request(key,ADMIN['id']);renders.request(key,ADMIN['id'])
    assert renders.claim('someone-else','host-a') is None
    first=renders.claim(ADMIN['id'],'host-a')
    assert first['source']==identity(row)
    assert renders.claim(ADMIN['id'],'host-a')==first
    assert renders.claim(ADMIN['id'],'host-b') is None
    from worker_health import set_pause
    set_pause(store.connect,True,'test-owner')
    assert renders.claim(ADMIN['id'],'host-a') is None


def test_failed_render_retained_and_no_implicit_native_retry(env):
    store,sql,provider=env;row=saved(env);r=Renders(store.connect);key=str(row['id'])
    r.request(key,ADMIN['id']);job=r.claim(ADMIN['id'])
    with pytest.raises(PermissionError):r.fail(key,ADMIN['id'],'wrong','discard')
    r.fail(key,ADMIN['id'],job['token'],'Missing profile: colour review required')
    with pytest.raises(ValueError,match='colour review'):r.request(key,ADMIN['id'])
    assert r.claim(ADMIN['id']) is None
    assert store.read(key,ADMIN['id'])['data']['source']==row['data']['source']


def test_explicit_render_retry_only_after_safe_cleanup_and_is_bounded(env):
    store,sql,provider=env;row=saved(env);r=Renders(store.connect);key=str(row['id'])
    r.request(key,ADMIN['id']);job=r.claim(ADMIN['id'])
    r.fail(key,ADMIN['id'],job['token'],'Colour review needed',retryable=False)
    with pytest.raises(ValueError):r.request(key,ADMIN['id'],retry=True)
    r.fail(key,ADMIN['id'],job['token'],'Colour review now resolved',retryable=True)
    second=r.request(key,ADMIN['id'],retry=True);assert second['attempt']==2
    job=r.claim(ADMIN['id']);r.fail(key,ADMIN['id'],job['token'],'retryable',retryable=True)
    assert r.request(key,ADMIN['id'],retry=True)['attempt']==3
    job=r.claim(ADMIN['id']);r.fail(key,ADMIN['id'],job['token'],'retryable',retryable=True)
    with pytest.raises(ValueError,match='Three native'):r.request(key,ADMIN['id'],retry=True)


def test_export_binding_requires_full_current_manifest_and_does_not_complete_shopify(env,tmp_path):
    from tests.test_mockup_eight_image_manifest import MockupEightImageManifestTests
    store,sql,provider=env;row=saved(env);key=str(row['id'])
    result=MockupEightImageManifestTests().make_result(tmp_path,8,include_jpg=True)
    result.update(_product_upload_intake=key,_product_upload_source_hash=row['data']['source']['content_hash'])
    bind_export(store.connect,ADMIN['id'],result,'ZIP')
    current=store.read(key,ADMIN['id'])
    assert current['data']['mockups_exported'] and len(current['data']['mockups_context']['images'])==8
    assert all(x['filename'] for x in current['data']['mockups_context']['images'])
    assert not current['data'].get('product_gid')
    result['_product_upload_source_hash']='b'*64
    with pytest.raises(ValueError,match='previous PSD'):bind_export(store.connect,ADMIN['id'],result,'ZIP')


def test_render_completion_verified_and_duplicate_safe(env,tmp_path):
    import auto_editions as ae
    store,sql,provider=env;row=saved(env);key=str(row['id']);r=Renders(store.connect)
    r.request(key,ADMIN['id']);job=r.claim(ADMIN['id'])
    path=tmp_path/'render.png';Image.new('RGBA',(20,10),(0,100,200,100)).save(path,icc_profile=icc())
    receipt=dict(source=identity(row),source_unchanged=True,owned_document_closed=True,native_render=True,colour={'policy':None},render_sha256=ae.file_hash(path))
    provider.save_render=Mock(return_value=dict(id='id:render',rev='r1',content_hash=ae.file_hash(path,dropbox=True)))
    bad={**receipt,'owned_document_closed':False}
    with pytest.raises(ValueError,match='cleanup'):r.finish(key,ADMIN['id'],job['token'],bad,path,provider)
    r.finish(key,ADMIN['id'],job['token'],receipt,path,provider)
    r.finish(key,ADMIN['id'],job['token'],receipt,path,provider)
    assert provider.save_render.call_count==1
    assert store.read(key,ADMIN['id'])['data']['mockup_render']['state']=='Ready'


@pytest.mark.parametrize('tagged,approved_untagged',[(True,False),(False,True),(False,False)])
def test_web_render_reuses_colour_policy_and_preserves_source(tmp_path,tagged,approved_untagged):
    import auto_editions as ae
    from scripts.render_product_upload_psd import render
    source=colour_psd(tmp_path/'original.psd',icc() if tagged else b'')
    original=source.read_bytes();identity=dict(template_id='product-upload:test',file_id='id:original',revision='a1',content_hash=ae.file_hash(source,dropbox=True))
    output=tmp_path/'render'
    def dispatch(script):
        request=json.loads(script.split('var SC_PRODUCT_RENDER = ',1)[1].split(';\n',1)[0])
        # Native Photoshop boundary double, explicitly not native evidence.
        Image.new('RGBA',(20,10),(1,2,3,80)).save(request['output'])
        Path(request['status']).write_text(json.dumps(dict(owned_document_closed=True,dimensions=[20,10])))
        return 'SC_PRODUCT_RENDERED'
    policies=[approved(identity)] if approved_untagged else []
    with patch('auto_editions_colour_policy.load_policies',return_value=policies):
        if not tagged and not approved_untagged:
            with pytest.raises(ValueError,match='approval'):render(source,output,identity,dispatch=dispatch)
            assert not output.exists()
        else:
            path,receipt=render(source,output,identity,dispatch=dispatch)
            assert receipt['source_unchanged'] and receipt['colour']['original_profile_preserved']
            with Image.open(path) as image:assert image.mode=='RGBA' and image.getpixel((0,0))[3]==80 and image.info['icc_profile']
    assert source.read_bytes()==original


def test_web_render_rejects_wrong_source_and_incomplete_native_cleanup(tmp_path):
    import auto_editions as ae
    from scripts.render_product_upload_psd import render
    path=colour_psd(tmp_path/'source.psd',icc());identity=dict(template_id='test',file_id='id:a',revision='r',content_hash='a'*64)
    with pytest.raises(ValueError,match='checksum'):render(path,tmp_path/'a',identity,dispatch=Mock())
    identity['content_hash']=ae.file_hash(path,dropbox=True)
    def dispatch(script):
        request=json.loads(script.split('var SC_PRODUCT_RENDER = ',1)[1].split(';\n',1)[0])
        Path(request['status']).write_text(json.dumps(dict(owned_document_closed=False)))
        return 'SC_PRODUCT_RENDERED'
    with pytest.raises(ValueError,match='cleanup'):render(path,tmp_path/'b',identity,dispatch=dispatch)


def test_shopify_draft_live_completion_and_export_gate(env):
    store,sql,provider=env;row=saved(env);key=str(row['id'])
    with store.locked(key,ADMIN['id']) as (r,cur):r['data']['mockups_exported']=False
    with pytest.raises(ValueError,match='mockup package'):service(env).resolve(key,ADMIN,'New Art')
    assert not store.read(key,ADMIN['id'])['data'].get('product_gid')
    with store.locked(key,ADMIN['id']) as (r,cur):r['data']['mockups_exported']=True
    store.change_mode(key,ADMIN['id'],'LIVE');store.copied(key,ADMIN['id'],'LIVE')
    provider.archive=Mock(wraps=provider.archive)
    with pytest.raises(ValueError,match='live publication'):service(env).resolve(key,ADMIN,'New Art')
    provider.archive.assert_not_called()
    active=product(status='ACTIVE',online_store_url='https://store.myshopify.com/products/new-art')
    result=service(env,active).resolve(key,ADMIN,'New Art')
    assert result['data']['shopify_completion']=='Published live'
    service(env,active).resolve(key,ADMIN,'New Art')
    assert provider.archive.call_count==1


def test_archive_uses_exact_existing_root_preserves_original_identity_and_lost_response():
    import psd_directory
    provider=Dropbox.__new__(Dropbox);provider.api=Mock();provider.token='synthetic';provider.context={'root_path':'/Sportscave Team Folder'}
    root=dict(id='id:root',path_display=psd_directory.ROOT,**{'.tag':'folder'})
    source=dict(id='id:original',rev='r1',content_hash='a'*64)
    moved={**source,'path_display':psd_directory.ROOT+'/product-upload-key.psd'}
    provider.api.get_file_metadata.return_value=root
    provider.metadata_if_present=Mock(side_effect=[None,source])
    provider.api.move_path.return_value=moved
    assert provider.archive('key',source)==moved
    assert provider.api.move_path.call_args.args[1]=='id:original'
    provider.metadata_if_present=Mock(return_value=moved)
    assert provider.archive('key',source)==moved
    assert provider.api.move_path.call_count==1
    provider.metadata_if_present=Mock(return_value={**moved,'id':'id:other'})
    with pytest.raises(ValueError,match='conflict'):provider.archive('key',source)


def test_export_save_reserves_numbered_target_once_and_recovers_partial(env,tmp_path):
    store,sql,provider=env;row=saved(env);key=str(row['id'])
    path=tmp_path/'image.webp';path.write_bytes(b'fixture-content')
    result=dict(_product_upload_intake=key,_product_upload_source_hash=row['data']['source']['content_hash'])
    manifest=[dict(path=path,archive_name='WEBP/art-black.webp')]
    provider.api=Mock();provider.token='synthetic'
    provider.api.sanitize_path_component.return_value='art';provider.api.join_upload_path.return_value='/root/art'
    provider.api.get_metadata_if_exists.return_value={'.tag':'folder'};provider.api.numbered_path.return_value='/root/art (2)'
    perform=Mock(side_effect=[RuntimeError('response lost'),dict(destination='/root/art (2)',successes=[{'relative_path':'WEBP/art-black.webp'}],failures=[])])
    with pytest.raises(RuntimeError):save(store.connect,ADMIN['id'],result,manifest,provider,'/root','art','numbered',perform)
    receipt=save(store.connect,ADMIN['id'],result,manifest,provider,'/root','art','numbered',perform)
    assert save(store.connect,ADMIN['id'],result,manifest,provider,'/root','art','numbered',perform)==receipt
    assert perform.call_count==2 and all(c.args==('/root/art (2)',) for c in perform.call_args_list)
    assert provider.api.numbered_path.call_count==1
    assert not store.read(key,ADMIN['id'])['data'].get('product_gid')


def test_fresh_state_never_reads_latest_account_intake(env,monkeypatch):
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    import product_upload_api as api,files_upload_api as files
    saved(env)
    monkeypatch.setattr(api,'connect',env[0].connect)
    monkeypatch.setattr(files,'_request_user',lambda *a,**k:ADMIN)
    client=TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]))
    assert client.get('/api/product-uploads/state').json()['upload'] is None
    assert env[0].read(None,ADMIN['id']) is not None


def test_render_http_accepts_existing_host_claim_health_envelope(env,monkeypatch):
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    import product_upload_api as api,files_upload_api as files,auto_editions_onboarding_api as onboarding
    from types import SimpleNamespace
    store,sql,provider=env;row=saved(env);key=str(row['id']);Renders(store.connect).request(key,ADMIN['id'])
    monkeypatch.setattr(api,'connect',store.connect)
    async def actor(request):return ADMIN
    monkeypatch.setattr(onboarding,'preparation_actor',actor)
    health=Mock();monkeypatch.setattr(onboarding,'host_health',health)
    monkeypatch.setattr(files,'_dropbox_context',lambda:dict(access_token='synthetic',root_path='/Sportscave Team Folder'))
    monkeypatch.setattr(files.dropbox_integration,'psd_open_metadata',lambda *a,**k:row['data']['source'])
    monkeypatch.setattr(files.NATIVE_TRANSFER_MANAGER,'create_psd',lambda **k:SimpleNamespace(ticket='synthetic-ticket',secret='synthetic-secret'))
    client=TestClient(Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]))
    assert client.post('/api/product-uploads/render/claim',json={}).status_code==403
    response=client.post('/api/product-uploads/render/claim',json={'health':{'state':'Idle'}},headers={'X-Sports-Cave-Preparation-Host':'synthetic'})
    assert response.status_code==200,response.text
    assert response.json()['job']['id']==key
    assert health.call_args.args[1]=={'state':'Idle'}


def test_native_rpc_failure_retains_owned_lock_and_marks_intake_failed(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from scripts.studio.product_upload_render_local import run_one
    home=tmp_path/'home';base=home/'Documents/SportsCaveAutoEditions';base.mkdir(parents=True)
    lock=home/'Documents/SportsCavePrintJobs/processor.lock';lock.parent.mkdir();lock.write_text('preserved-owner')
    job=dict(id=str(uuid.uuid4()),source={'content_hash':'a'*64},metadata={'size':100},token='lease',attempt=1)
    folder=base/('product-upload-'+job['id']+'-attempt-1');folder.mkdir();(folder/'input.psd').write_bytes(b'preserve original')
    host=SimpleNamespace(HOST_FILE=base/'host.dpapi',JOBS={},atomic_json=lambda path,value:path.write_text(json.dumps(value)),processor_lease=Mock(return_value=SimpleNamespace(unlink=Mock())))
    calls=[]
    def request(config,path,body):
        calls.append((path,body));return {'job':job} if path.endswith('/claim') else {'ok':True}
    host.host_request=request
    def native(source,output,identity):
        output.mkdir();(output/'dispatch-intent.json').write_text('{}');(output/'native-status.json').write_text('{"owned_document_closed":false}')
        raise RuntimeError('RPC interrupted')
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:home))
    monkeypatch.setattr('scripts.render_product_upload_psd.render',native)
    assert run_one({},host)
    assert lock.read_text()=='preserved-owner'
    host.processor_lease.return_value.unlink.assert_not_called()
    assert calls[-1][0].endswith('/fail') and calls[-1][1]['retryable'] is False
    assert (folder/'failure-detail.json').exists() and not host.JOBS


def test_native_upload_reconnect_uses_verified_cache_without_rerender(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import auto_editions as ae,requests
    from scripts.studio.product_upload_render_local import run_one
    base=tmp_path/'cache';base.mkdir()
    job=dict(id=str(uuid.uuid4()),source={'content_hash':'a'*64},metadata={'size':100},token='lease',attempt=1)
    folder=base/('product-upload-'+job['id']+'-attempt-1');folder.mkdir()
    source=folder/'input.psd';source.write_bytes(b'preserve original')
    output=folder/'render-v1';output.mkdir();Image.new('RGB',(20,10)).save(output/'render.png',icc_profile=icc())
    receipt=dict(source=job['source'],source_sha256=ae.file_hash(source))
    (output/'receipt.json').write_text(json.dumps(receipt))
    host=SimpleNamespace(HOST_FILE=base/'host.dpapi',JOBS={},host_request=lambda *a:{'job':job},atomic_json=lambda path,value:path.write_text(json.dumps(value)),processor_lease=Mock())
    render=Mock(side_effect=AssertionError('Successful native work must not run again'))
    monkeypatch.setattr('scripts.render_product_upload_psd.render',render)
    post=Mock(side_effect=[requests.ConnectionError('offline'),SimpleNamespace(raise_for_status=lambda:None)])
    monkeypatch.setattr(requests,'post',post)
    with pytest.raises(requests.ConnectionError):run_one({'base_url':'https://synthetic','token':'host'},host)
    assert run_one({'base_url':'https://synthetic','token':'host'},host)
    render.assert_not_called();host.processor_lease.assert_not_called()
    assert (folder/'completed.json').exists() and not host.JOBS


def test_long_render_heartbeats_without_claiming_or_renewing_product_jobs(monkeypatch):
    import threading
    from types import SimpleNamespace
    import scripts.studio.product_upload_render_local as worker
    stop=threading.Event();observed=threading.Event();calls=[]
    def request(config,path,body):
        calls.append((path,body));observed.set()
    monkeypatch.setattr(worker,'HEARTBEAT_SECONDS',0.01)
    thread=threading.Thread(target=worker.render_heartbeat,args=(stop,{},SimpleNamespace(host_request=request)))
    thread.start()
    try:assert observed.wait(2)
    finally:stop.set();thread.join(2)
    assert not thread.is_alive()
    assert calls and all(path.endswith('/heartbeat') and body=={} for path,body in calls)


def test_archive_move_uses_stable_id_after_verifying_shared_root(monkeypatch):
    import dropbox_integration as dropbox
    metadata=dict(id='id:stable',path_display='/Team/staging/source.psd',**{'.tag':'file'})
    client=Mock();client.files_move_v2.return_value=object()
    monkeypatch.setattr(dropbox,'get_file_metadata',lambda *a:metadata)
    monkeypatch.setattr(dropbox,'team_space_client',lambda *a:client)
    monkeypatch.setattr(dropbox,'_metadata_to_dict',lambda value:metadata)
    assert dropbox.move_path('isolated','id:stable','/Team/live/source.psd',root_path='/Team')==metadata
    assert client.files_move_v2.call_args.args==('id:stable','/Team/live/source.psd')
    client.reset_mock();metadata['path_display']='/Unrelated/source.psd'
    with pytest.raises(ValueError,match='outside'):dropbox.move_path('isolated','id:stable','/Team/live/source.psd',root_path='/Team')
    client.files_move_v2.assert_not_called()
    metadata['path_display']='/Team/staging/source.psd';metadata['id']='id:different'
    with pytest.raises(ValueError,match='exact'):dropbox.move_path('isolated','id:stable','/Team/live/source.psd',root_path='/Team')
    client.files_move_v2.assert_not_called()
