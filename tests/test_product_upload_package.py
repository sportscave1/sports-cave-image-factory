from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import uuid
import pytest

from product_upload_package import ORDER, package, view, verified, native_grant


def saved_row():
    key=str(uuid.uuid4())
    source=dict(id='id:source',rev='abcdef123',content_hash='a'*64)
    folder='/Team/04_OUTPUT/product-images/Motorsport Wall Art/product (2)'
    files=[];manifest=[]
    for i,role in enumerate(ORDER):
        name=role+'.webp'
        files.append(dict(relative_path='WEBP/'+name,metadata=dict(id='id:file'+str(i),rev='abcdef12'+str(i),
            content_hash=str(i)*64,size=100+i,name=name,path_display=folder+'/WEBP/'+name)))
        manifest.append(dict(slot_id=role,output_filename=name,display_label=role,sort_position=i+1))
    output=dict(folder=folder,folder_id='id:folder',export_fingerprint='saved',files=files,manifest=manifest)
    return dict(id=key,mode='DRAFT',data=dict(source=source,mockups_exported=True,
        upload_operation=dict(id=key,provider='dropbox',source=deepcopy(source),output=output),
        mockup_saves={'saved':dict(state='Complete',target=folder,manifest=[dict(name=x['relative_path']) for x in files])}))


def test_exact_receipt_order_and_lightweight_urls():
    row=saved_row();result=view(row)
    assert [x['role'] for x in result['items']]==list(ORDER)
    assert result['folder'].endswith('product (2)/WEBP')
    assert all('thumbnail=1' in x['preview'] and 'thumbnail' not in x['original'] for x in result['items'])
    assert all('metadata' not in x for x in result['items'])
    for item, receipt in zip(result['items'], row['data']['upload_operation']['output']['files']):
        assert item['size'] == receipt['metadata']['size']
        assert item['content_hash'] == receipt['metadata']['content_hash']


def test_legacy_package_uses_only_own_unique_complete_receipt():
    row = saved_row()
    output = row['data'].pop('upload_operation')['output']
    row['data']['mockups_context'] = dict(folder=output['folder'],
        images=[dict(role=x['slot_id'], filename=x['output_filename']) for x in output['manifest']])
    saved = row['data']['mockup_saves']['saved']
    saved.pop('manifest')
    saved['receipt'] = dict(destination=output['folder'], successes=output['files'], failures=[])
    before = deepcopy(saved)
    result = package(row)
    assert len(result['items']) == 8 and saved == before
    assert package(row, result['version']) == result
    row['data']['mockup_saves']['ambiguous'] = deepcopy(saved)
    with pytest.raises(ValueError, match='unique'): package(row)
    del row['data']['mockup_saves']['ambiguous']
    saved['receipt']['successes'].pop()
    with pytest.raises(ValueError, match='missing'): package(row)


@pytest.mark.parametrize('change',['source','incomplete','missing','wrong-folder','extra','revision'])
def test_changed_or_incomplete_package_is_rejected(change):
    row=saved_row();old=package(row)['version'];out=row['data']['upload_operation']['output']
    if change=='source':row['data']['source']['rev']='new'
    elif change=='incomplete':row['data']['mockups_exported']=False
    elif change=='missing':out['files'].pop()
    elif change=='wrong-folder':out['files'][0]['metadata']['path_display']='/Team/other/black-frame.webp'
    elif change=='extra':out['files'].append(dict(relative_path='WEBP/extra.webp',metadata={}))
    else:out['files'][0]['metadata']['rev']='changed'
    with pytest.raises(ValueError):package(row,old)


def test_native_grant_accepts_no_client_file_paths_and_pins_all_ids(monkeypatch):
    import files_upload_api as files
    row=saved_row();result=package(row)
    metadata={x['metadata']['id']:x['metadata'] for x in result['items']}
    listing=Mock(side_effect=lambda *a,**k:dict(entries=[dict(x, **{'.tag':'file'}) for x in metadata.values()],has_more=False))
    provider=SimpleNamespace(token='fixture',api=SimpleNamespace(list_folder_page=listing),metadata_if_present=lambda key:
        dict(id='id:webp', **{'.tag':'folder'}) if key==result['folder'] else metadata.get(key))
    record=SimpleNamespace(items=[{} for _ in ORDER])
    create=Mock(return_value=record);monkeypatch.setattr(files.NATIVE_TRANSFER_MANAGER,'create',create)
    granted=native_grant(row,result['version'],provider,{'id':'owner'},dict(root_path='/Team',access_token='fixture'))
    selected=create.call_args.kwargs['selections']
    assert len(selected)==8 and selected[0]['id']=='id:file0'
    assert all(x['path'].startswith('04_OUTPUT/product-images/') and x['revision'] for x in selected)
    assert granted.purpose=='product_upload_webp'
    assert all(x['content_hash']==str(i)*64 for i,x in enumerate(granted.items))
    metadata.pop('id:file2')
    with pytest.raises(ValueError,match='displayed package'):native_grant(row,result['version'],provider,{},dict(root_path='/Team',access_token='fixture'))
    assert create.call_count==1


def test_thumbnail_route_never_downloads_and_original_is_revision_pinned(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api
    row=saved_row();result=view(row);meta=row['data']['upload_operation']['output']['files'][0]['metadata']
    async def actor(*a,**k):return {'id':'owner'}
    provider=SimpleNamespace(token='fixture',metadata_if_present=lambda _:meta,
        api=SimpleNamespace(get_thumbnail_bytes=Mock(return_value=b'tiny'),get_psd_file_response=Mock()))
    upstream=SimpleNamespace(iter_content=lambda **_:iter([b'original-webp']),close=Mock())
    provider.api.get_psd_file_response.return_value=(meta,upstream)
    monkeypatch.setattr(api,'actor',actor);monkeypatch.setattr(api,'Dropbox',lambda:provider)
    monkeypatch.setattr(api,'Intakes',lambda _:SimpleNamespace(read=lambda *_:row))
    app=Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES])
    with TestClient(app) as client:
        assert client.get(result['items'][0]['preview']).content==b'tiny'
        provider.api.get_psd_file_response.assert_not_called()
        response=client.get(result['items'][0]['original'])
        assert response.content==b'original-webp' and response.headers['content-type']=='image/webp'
        provider.api.get_psd_file_response.assert_called_once_with('fixture',meta['id'],meta['rev'])
        row['data']['mockups_exported']=False
        assert client.get(result['items'][0]['original']).status_code==409


def test_inline_save_status_requires_current_complete_receipt(tmp_path):
    from streamlit.testing.v1 import AppTest
    asset=tmp_path/'output.webp';asset.write_bytes(b'fixture')
    source='''
from types import SimpleNamespace
from pathlib import Path
import streamlit as st
from product_upload_outputs_ui import save_controls,package_stamp
from product_upload_jobs import JOBS
JOBS.snapshot=lambda *a:None
manifest=[dict(path=Path(PATH),archive_name='WEBP/black.webp')]
row=dict(id='fixture-inline',data=dict(source=dict(id='id:psd',rev='a1')))
st.session_state['product-upload-category-fixture-inline-resolved']=dict(id='id:category',name='Motorsport Wall Art')
stamp=package_stamp(row['data']['source'],'id:category','product',manifest)
result=dict(product_image_readiness=dict(complete=True),product_upload_save_receipt=dict(package_stamp=stamp,successes=[{}],destination='/Team/Motorsport Wall Art/product (2)'))
app=SimpleNamespace(dropbox_integration=SimpleNamespace(sanitize_path_component=lambda name,**k:name),os_accounts=SimpleNamespace(can_access_page=lambda *a:True),_mockup_dropbox_manifest=lambda *a:manifest,ASSET_CATEGORY_CORE='core',ASSET_CATEGORY_PRODUCT='product',ASSET_CATEGORY_SOCIAL='social')
save_controls(app,result,row,dict(id='fixture'),'product')
'''.replace('PATH',repr(str(asset)))
    # Isolated module cache patch restored after the script runs.
    import product_upload_jobs
    snapshot=product_upload_jobs.JOBS.snapshot
    try:
        page=AppTest.from_string(source).run()
        assert not page.exception
        assert any('✓ Saved' in x.value for x in page.markdown)
        assert any('product (2)' in x.value for x in page.caption)
        assert [x.label for x in page.button]==['Save all']
        assert not page.success
    finally:product_upload_jobs.JOBS.snapshot=snapshot


def test_saved_stamp_changes_for_source_category_or_file(tmp_path):
    from product_upload_outputs_ui import package_stamp
    path=tmp_path/'asset.webp';path.write_bytes(b'original')
    manifest=[dict(path=path,archive_name='WEBP/asset.webp')]
    before=package_stamp({'id':'psd'},'category','name',manifest)
    assert package_stamp({'id':'other'},'category','name',manifest)!=before
    assert package_stamp({'id':'psd'},'other','name',manifest)!=before
    path.write_bytes(b'revised bytes')
    assert package_stamp({'id':'psd'},'category','name',manifest)!=before


@pytest.mark.parametrize('mode',['DRAFT','LIVE','UPDATE'])
def test_copy_upload_prompt_preserves_mode_and_operation(monkeypatch,mode):
    from contextlib import contextmanager
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api, product_upload_prompts
    from product_upload_identity import tag
    row=saved_row();row['mode']=mode
    row['data'].update(basic_validated=True,name='Exact.psd',workflow_version=3,mockups_context=dict(folder='/exact/saved/WEBP'))
    class Store:
        def __init__(self,*_):pass
        def read(self,*_):return row
        @contextmanager
        def locked(self,*_):yield row,None
    async def actor(*a,**kw):return {'id':'fixture'}
    monkeypatch.setattr(api,'actor',actor);monkeypatch.setattr(api,'Intakes',Store)
    build=Mock(side_effect=lambda m,n:m+' original prompt for '+n);monkeypatch.setattr(product_upload_prompts,'build',build)
    app=Starlette(routes=[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES])
    with TestClient(app) as client:
        response=client.post('/api/product-uploads/prompt',json=dict(id=row['id'],mode=mode))
    assert response.status_code==200
    prompt=response.json()['prompt']
    assert tag(row['id']) in prompt and mode+' original prompt for Exact.psd' in prompt
    assert '/exact/saved/WEBP' in prompt
    build.assert_called_once_with(mode,'Exact.psd')


def test_dropbox_listing_preserves_stable_folder_id_and_cursor(monkeypatch):
    import dropbox_integration as dbx
    client=Mock()
    client.files_list_folder.return_value=SimpleNamespace(entries=[],cursor='next',has_more=True)
    client.files_list_folder_continue.return_value=SimpleNamespace(entries=[],cursor='',has_more=False)
    monkeypatch.setattr(dbx,'team_space_client',lambda token:client)
    first=dbx.list_folder_page('fixture','id:exact-webp')
    assert client.files_list_folder.call_args.args==('id:exact-webp',)
    dbx.list_folder_page('fixture','id:exact-webp',cursor=first['cursor'])
    client.files_list_folder_continue.assert_called_once_with('next')
    with pytest.raises(ValueError):dbx.list_folder_page('fixture','id:../escape')


def test_downloads_keep_exact_product_file_ids_names_and_bytes(monkeypatch):
    from io import BytesIO
    import hashlib
    from PIL import Image
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api
    rows = [saved_row(), saved_row()]
    metadata, payloads = {}, {}
    for product, row in enumerate(rows):
        output = row['data']['upload_operation']['output']
        old_folder = output['folder']
        output['folder'] += '/product-' + str(product)
        row['data']['mockup_saves']['saved']['target'] = output['folder']
        for i, entry in enumerate(output['files']):
            meta = entry['metadata']
            meta['id'] += '-product-' + str(product)
            meta['path_display'] = meta['path_display'].replace(old_folder, output['folder'])
            stream = BytesIO()
            Image.new('RGB', (32, 24), (product * 100, i * 20, 60)).save(stream, 'WEBP')
            data = stream.getvalue()
            meta['size'] = len(data)
            meta['content_hash'] = hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()
            metadata[meta['id']] = meta
            payloads[meta['id']] = data
    calls = []
    def original(token, file_id, revision):
        calls.append((file_id, revision))
        return metadata[file_id], SimpleNamespace(iter_content=lambda **_: iter([payloads[file_id]]), close=lambda: None)
    async def actor(*a, **k): return {'id': 'owner'}
    monkeypatch.setattr(api, 'actor', actor)
    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(token='fixture', metadata_if_present=metadata.get,
        api=SimpleNamespace(get_psd_file_response=original)))
    monkeypatch.setattr(api, 'Intakes', lambda _: SimpleNamespace(read=lambda key, _: next(r for r in rows if str(r['id']) == key)))
    with TestClient(Starlette(routes=[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES])) as client:
        for row in rows:
            for item in view(row)['items']:
                expected = next(x['metadata'] for x in row['data']['upload_operation']['output']['files'] if x['metadata']['name'] == item['name'])
                response = client.get(item['download'])
                assert response.status_code == 200
                assert response.headers['content-type'] == 'image/webp'
                assert response.headers['content-disposition'].startswith('attachment;')
                assert item['name'] in response.headers['content-disposition']
                assert response.content == payloads[expected['id']]
                assert response.content[:4] == b'RIFF' and response.content[8:12] == b'WEBP'
                assert calls[-1] == (expected['id'], expected['rev'])
        # A different product has identical filenames, but a different package identity.
        first = view(rows[0])['items'][0]['download']
        assert client.get(first.replace(str(rows[0]['id']), str(rows[1]['id']))).status_code == 409
