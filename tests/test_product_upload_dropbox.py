"""Disposable PostgreSQL and provider doubles; never original artwork or Shopify."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import uuid
import pytest
from tests.test_product_upload_intake import database, env, ADMIN, product, service
from product_upload_dropbox import REVIEW, ROOTS, select, browse, status
from product_upload_render import Renders, identity
from product_upload_lifecycle import handoff, filename, run_one


def provider_fixture(provider):
    for name,path in ROOTS.items():
        meta = dict(id='id:'+name,name=path.rsplit('/',1)[1],path_display=path,**{'.tag':'folder'})
        provider.files[path]=meta;provider.files[meta['id']]=meta
    def add(fid='id:chosen', name='Same.psd', rev='a1', parent=REVIEW):
        meta=dict(id=fid,name=name,rev=rev,content_hash='a'*64,size=128,path_display=parent+'/'+name,**{'.tag':'file'})
        provider.files[fid]=meta;provider.files[meta['path_display']]=meta
        return deepcopy(meta)
    provider.token='isolated';provider.context=dict(root_path='/Sportscave Team Folder');provider.api=Mock()
    def move(token,fid,path,**kwargs):
        old=provider.files[fid];provider.files.pop(old['path_display'],None)
        meta={**old,'path_display':path,'name':path.rsplit('/',1)[1],'rev':old['rev']+'a'}
        provider.files[fid]=meta;provider.files[path]=meta;return deepcopy(meta)
    provider.api.move_path.side_effect=move
    return add


def selected(env, **kwargs):
    store,sql,provider=env;add=provider_fixture(provider);meta=add(**kwargs)
    row=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],meta['rev'])
    return row,meta


def test_exact_selection_same_names_never_match_and_no_psd_transfer(env):
    store,sql,provider=env;row,meta=selected(env)
    add=provider_fixture(provider);other=add('id:other')
    second=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',other['id'],other['rev'])
    assert row['data']['source']['id'] != second['data']['source']['id']
    assert row['data']['source']==meta and not provider.sessions
    assert identity(row)['file_id']==meta['id']
    assert row['data']['server_artwork']['state']=='Selected'
    with pytest.raises(ValueError,match='changed'):select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],'wrong')
    assert not provider.calls


def test_folder_browser_reuses_files_pagination_filters_psd_without_download(env,monkeypatch):
    store,sql,provider=env;add=provider_fixture(provider);meta=add()
    rows=[meta,{**meta,'name':'not.jpg','path_display':REVIEW+'/not.jpg'},dict(name='Subfolder',path_display=REVIEW+'/Subfolder',**{'.tag':'folder'})]
    page=Mock(return_value=dict(entries=rows,page_token='next',has_more=True))
    monkeypatch.setattr('files_upload_api._directory_page',page)
    result=browse(provider,ADMIN['id'],search='same')
    assert [x['id'] for x in result['items']]==[meta['id']] and result['next_page']=='next'
    assert page.call_args.kwargs['limit']==100 and not provider.calls
    provider.files['id:review']['path_display']='/wrong'
    with pytest.raises(ValueError,match='identity changed'):browse(provider,ADMIN['id'])


def test_revision_or_settings_change_forces_new_preparation(env):
    store,sql,provider=env;row,meta=selected(env)
    provider.files[meta['id']]['rev']='a2'
    newer=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],'a2')
    assert newer['data']['server_artwork']['state']=='Selected'
    assert identity(newer)!=identity(row)


def lifecycle_row(meta):
    return dict(id=str(uuid.uuid4()),data=dict(source=deepcopy(meta),mockups_exported=True,
        mockups_context=dict(images=[dict(role=str(i)) for i in range(8)]),
        lifecycle=dict(state='Queued',expected_source=deepcopy(meta),history=[])))


def intent(row,product,parent):
    row['data']['lifecycle']['intent']=dict(source=deepcopy(row['data']['lifecycle']['expected_source']),to=parent+'/'+filename(product['title']))


def live_product(**kwargs):
    return product(status='ACTIVE',online_store_url='https://isolated/products/art',images=[dict(id=str(i),url='https://isolated/'+str(i)) for i in range(8)],**kwargs)


@pytest.mark.parametrize('published,media,expected',[(False,False,'review'),(True,False,'review'),(True,True,'live')])
def test_draft_and_publication_media_gates(env,published,media,expected):
    store,sql,provider=env;meta=provider_fixture(provider)();row=lifecycle_row(meta)
    p=live_product() if published else product();p['images']=p.get('images',[]) if media else []
    intent(row,p,ROOTS[expected]);moved=handoff(row,provider,p)
    assert moved['path_display']==ROOTS[expected]+'/New Art.psd'
    assert moved['id']==meta['id']
    assert row['data']['lifecycle']['state']==('Complete' if expected=='live' else 'Waiting for publication/media')
    assert row['data']['lifecycle']['history'][0]['old_path']==meta['path_display']


def test_later_publication_same_identity_completes_handoff_and_live_never_moves_back(env):
    store,sql,provider=env;meta=provider_fixture(provider)();row=lifecycle_row(meta);draft=product()
    intent(row,draft,REVIEW);first=handoff(row,provider,draft)
    p=live_product();intent(row,p,ROOTS['live']);live=handoff(row,provider,p)
    assert live['id']==first['id'] and row['data']['lifecycle']['state']=='Complete'
    intent(row,draft,ROOTS['live']);assert handoff(row,provider,draft)['path_display'].startswith(ROOTS['live']+'/New Art')


def test_retry_lost_provider_response_recovers_exact_id_without_second_move(env):
    store,sql,provider=env;meta=provider_fixture(provider)();row=lifecycle_row(meta);p=live_product()
    intent(row,p,ROOTS['live']);retained=deepcopy(row)
    handoff(row,provider,p)
    assert handoff(retained,provider,p)['id']==meta['id']
    assert provider.api.move_path.call_count==1


def test_destination_conflict_and_changed_revision_recoverable_no_overwrite(env):
    store,sql,provider=env;add=provider_fixture(provider);meta=add();row=lifecycle_row(meta);p=live_product()
    intent(row,p,ROOTS['live']);add('id:other','New Art.psd',parent=ROOTS['live'])
    with pytest.raises(ValueError,match='conflict'):handoff(row,provider,p)
    provider.api.move_path.assert_not_called()
    provider.files[meta['id']]['rev']='edited'
    with pytest.raises(ValueError,match='revision changed'):handoff(row,provider,p)
    provider.api.move_path.assert_not_called()


def test_confirmed_mapping_persisted_before_file_handoff_and_duplicate_link_safe(env):
    store,sql,provider=env;row,meta=selected(env);key=str(row['id']);s=service(env)
    with store.locked(key,ADMIN['id']) as (current,cur):
        current['data'].update(copied=True,mockups_exported=True,choices=[dict(id=product()['shopify_product_id'],title='New Art')])
    first=s.link(key,ADMIN,product()['shopify_product_id'])
    assert first['data']['lifecycle']['state']=='Queued' and first['data']['bound_source']['file_id']==meta['id']
    assert s.link(key,ADMIN,product()['shopify_product_id'])['data']['product_gid']==first['data']['product_gid']
    provider.api.move_path.assert_not_called()
    s.shopify.fetch_product_by_shopify_id.assert_called_once()


def test_companion_offline_state_is_explicit_and_fresh_state_has_no_latest_selection(env):
    store,sql,provider=env;row,meta=selected(env)
    assert status(row,store.connect)['data']['state']=='Selected'
    assert 'companion_connected' not in row['data']
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.routing import Route
    import product_upload_api as api
    async def actor(*args,**kwargs):return ADMIN
    from unittest.mock import patch
    with patch.object(api,'actor',actor),patch.object(api,'connect',store.connect):
        client=TestClient(Starlette(routes=[Route('/state',api.state)]))
        assert client.get('/state').json()['upload'] is None


def test_synced_copy_verified_without_touching_original_and_stale_bytes_rejected(tmp_path):
    import auto_editions as ae
    from product_upload_local_source import reuse_synced
    root=tmp_path/'synced';source=root/'Team/Review/art.psd';source.parent.mkdir(parents=True);source.write_bytes(b'isolated PSD bytes')
    meta=dict(path_display='/Team/Review/art.psd',content_hash=ae.file_hash(source,dropbox=True),size=source.stat().st_size)
    destination=tmp_path/'owned/input.psd';destination.parent.mkdir()
    assert reuse_synced(meta,destination,[root]) and source.read_bytes()==destination.read_bytes()
    assert reuse_synced({**meta,'content_hash':'a'*64},tmp_path/'wrong.psd',[root]) is None
    assert not (tmp_path/'wrong.psd').exists()


@pytest.mark.parametrize('title,expected',[('Name / Test:*','Name _ Test__.psd'),('CON','_CON.psd'),('Art.psd','Art.psd')])
def test_filename_sanitisation(title,expected):assert filename(title)==expected


def confirm_selected(env):
    store,sql,provider=env;row,meta=selected(env);key=str(row['id']);s=service(env)
    with store.locked(key,ADMIN['id']) as (current,cur):
        current['data'].update(copied=True,mockups_exported=True,mockups_context=dict(images=[dict(role=str(i)) for i in range(8)]),choices=[dict(id=product()['shopify_product_id'],title='New Art')])
    s.link(key,ADMIN,product()['shopify_product_id'])
    return key,meta,s


def due(store,key):
    with store.locked(key,ADMIN['id']) as (row,cur):row['data']['lifecycle']['checked_at']=None


def test_companion_draft_poll_then_later_publication_retains_canonical_mapping(env,monkeypatch):
    store,sql,provider=env;key,meta,s=confirm_selected(env)
    lookup=Mock(return_value=product());monkeypatch.setattr('shopify_sync.fetch_product_by_shopify_id',lookup)
    assert run_one(store.connect,provider,ADMIN['id'])
    first=store.read(key,ADMIN['id'])
    assert first['data']['source']['path_display']==REVIEW+'/New Art.psd'
    assert first['data']['lifecycle']['state']=='Waiting for publication/media'
    assert s.mappings.read()=={}
    due(store,key);assert run_one(store.connect,provider,ADMIN['id'])
    assert provider.api.move_path.call_count==1
    assert len(store.read(key,ADMIN['id'])['data']['lifecycle']['history'])==1
    due(store,key);lookup.return_value=live_product()
    assert run_one(store.connect,provider,ADMIN['id'])
    final=store.read(key,ADMIN['id'])
    assert final['data']['lifecycle']['state']=='Complete',final['data']['lifecycle']
    assert s.mappings.read()[product()['shopify_product_id']]['dropbox_file_id']==meta['id']
    assert final['data']['source']['path_display']==ROOTS['live']+'/New Art.psd'
    assert not run_one(store.connect,provider,ADMIN['id'])
    assert provider.api.move_path.call_count==2


def test_file_failure_durable_and_retry_does_not_recreate_or_republish_product(env,monkeypatch):
    store,sql,provider=env;key,meta,s=confirm_selected(env)
    lookup=Mock(return_value=product());monkeypatch.setattr('shopify_sync.fetch_product_by_shopify_id',lookup)
    actual=provider.api.move_path.side_effect
    provider.api.move_path.side_effect=RuntimeError('isolated provider outage')
    assert run_one(store.connect,provider,ADMIN['id'])
    failed=store.read(key,ADMIN['id']);assert failed['data']['lifecycle']['state']=='Error'
    assert failed['data']['product_gid']==product()['shopify_product_id']
    assert s.link(key,ADMIN,product()['shopify_product_id'])['data']['product_gid']==failed['data']['product_gid']
    s.shopify.fetch_product_by_shopify_id.assert_called_once()
    due(store,key);provider.api.move_path.side_effect=actual
    assert run_one(store.connect,provider,ADMIN['id'])
    assert store.read(key,ADMIN['id'])['data']['lifecycle']['state']=='Waiting for publication/media'


def test_pause_and_active_render_prevent_rename(env,monkeypatch):
    store,sql,provider=env;key,meta,s=confirm_selected(env)
    monkeypatch.setattr('shopify_sync.fetch_product_by_shopify_id',lambda pid:product())
    from worker_health import set_pause
    set_pause(store.connect,True,'isolated')
    assert not run_one(store.connect,provider,ADMIN['id']);provider.api.move_path.assert_not_called()
    set_pause(store.connect,False,'isolated')
    due(store,key)
    with store.locked(key,ADMIN['id']) as (row,cur):row['data']['server_artwork']['state']='Preparing'
    assert not run_one(store.connect,provider,ADMIN['id']);provider.api.move_path.assert_not_called()


def test_companion_preserves_rgb8_layer_and_pixel_validation(tmp_path):
    from tests.test_product_upload_intake import psd
    from product_upload_dropbox import validate_structure
    path=tmp_path/'isolated.psd';path.write_bytes(psd())
    assert validate_structure(path)['colour']=='RGB'
    path.write_bytes(psd(depth=16))
    with pytest.raises(ValueError,match='RGB'):validate_structure(path)
    path.write_bytes(psd()[:36]+b'\0'*4+psd()[40:])
    with pytest.raises(ValueError,match='layer'):validate_structure(path)


def test_review_native_grant_is_explicit_and_does_not_expand_master_access(env):
    store,sql,provider=env;row,meta=selected(env)
    import files_upload_api as files
    manager=files.NativeTransferManager()
    with pytest.raises(files.FilesUploadError):manager.create_psd(access_token='isolated',root_path='/Sportscave Team Folder',user=ADMIN,metadata=meta)
    grant=manager.create_psd(access_token='isolated',root_path='/Sportscave Team Folder',user=ADMIN,metadata=meta,product_upload=True)
    assert grant.items[0]['dropbox_id']==meta['id'] and grant.items[0]['revision']==meta['rev']


def test_bounded_folder_page_ignores_whole_folder_cache(monkeypatch):
    import files_upload_api as files
    from product_upload_dropbox import REVIEW
    monkeypatch.setattr(files,'_directory_cache_payload',lambda *a:[dict(name='whole-cache')]*5000)
    page=Mock(return_value=dict(entries=[dict(name='one.psd')],has_more=False,cursor=''))
    monkeypatch.setattr(files.dropbox_integration,'list_folder_page',page)
    result=files._directory_page('isolated',REVIEW,root_path='/Sportscave Team Folder',user_id='bounded-fixture',limit=100,bounded=True)
    assert len(result['entries'])==1 and page.call_args.kwargs['limit']==100
