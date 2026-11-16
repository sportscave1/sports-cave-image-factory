from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import inspect
import pytest
from PIL import Image
from tests.test_product_upload_intake import database,env,saved,ADMIN
from tests.fixtures.product_upload_outputs_provider import Outputs
from product_upload_export import transfer,product_folder,collection_root
from product_upload_lifestyle import compose,scene_texts,INSTRUCTIONS,PER_IMAGE,FILENAMES,ROOMS


def test_master_each_scene_complete_and_custom_selections_stable():
    import image_factory as factory
    import mockup_product_prompts as scenes
    result=dict(run_dir='current-workflow',final_prompt_items=factory.build_lifestyle_prompt_items('Product','Baseball',local_only=True))
    current=lambda name,default:default
    defaults=lambda name,default:default
    first=scene_texts(result,current,defaults)
    assert first==scene_texts(result,current,defaults)
    for i,text in enumerate(first):assert any('Selected room: '+room in text for room in ROOMS[i])
    custom=[x.replace('Selected room:','Selected room: Authored room ') for x in first]
    loaded=lambda filename,default:custom[FILENAMES.index(filename)]
    assert scene_texts(result,loaded,lambda *a:'saved custom')==custom
    master=compose(INSTRUCTIONS,first)
    assert master.count(PER_IMAGE)==3
    for text in ('THREE complete','Immediately generate Card 1','Immediately continue to Card 2 without waiting for approval or another message','original uploaded full-resolution framed product','No collage, triptych or contact sheet','three genuinely different homes or properties','841 × 594 mm','594 × 841 mm','acrylic rather than glass','Reflections match the room lighting','1024 × 1024'):
        assert text in master
    assert all(filename in factory.PRODUCT_PAGE_PROMPT_FILENAMES for filename in FILENAMES)


def make_result(env,tmp_path):
    from tests.test_mockup_eight_image_manifest import MockupEightImageManifestTests
    store,_,_=env;row=saved(env)
    with store.locked(row['id'],ADMIN['id']) as (value,cur):value['data']['mockups_exported']=False
    result=MockupEightImageManifestTests().make_result(tmp_path,8,include_jpg=True)
    result.update(_product_upload_intake=str(row['id']),_product_upload_actor_id=str(ADMIN['id']),
                  _product_upload_source_hash=row['data']['source']['content_hash'],_product_upload_source=deepcopy(row['data']['source']))
    import app
    manifest=app._mockup_dropbox_manifest(result,(app.ASSET_CATEGORY_CORE,app.ASSET_CATEGORY_PRODUCT,app.ASSET_CATEGORY_SOCIAL))
    return row,result,manifest


def test_save_uses_standalone_manifest_partial_retry_lost_ack_and_duplicate(env,tmp_path):
    store,_,_=env;row,result,manifest=make_result(env,tmp_path)
    api=Outputs();provider=SimpleNamespace(api=api,token='fixture')
    api.fail_once=manifest[2]['archive_name'];api.lose_once=manifest[4]['archive_name']
    updates=[]
    def run():return transfer(provider,result,manifest,api.root,api.base+'/Baseball','Current: Product',store.connect,ADMIN['id'],lambda *a:updates.append(a))
    first=run();assert len(first['failures'])==2
    assert not store.read(row['id'],ADMIN['id'])['data'].get('mockups_exported')
    second=run();assert not second['failures'] and len(second['successes'])==8
    assert len(manifest)==8 and all(x['archive_name'].startswith('WEBP/') for x in manifest)
    assert all(not path.casefold().endswith(('.jpg','.jpeg','/jpg')) for path in api.files)
    assert all(total==8 for _,_,total in updates)
    from product_upload_source import current_source,prompt_section
    source=current_source(store.read(row['id'],ADMIN['id']))
    assert source['expected_webp_count']==8 and len(source['files'])==8
    assert all(x['filename'].endswith('.webp') for x in source['files'])
    assert '"expected_webp_count": 8' in prompt_section(source)
    assert second['destination']==first['destination']==api.base+'/Baseball/Current_ Product'
    assert len([x for x in api.calls if x[0]=='folder'])==1
    assert len([x for x in api.calls if x[0]=='upload'])==9 # retry failure only; lost ACK checked by hash
    calls=list(api.calls);assert run()==second and api.calls==calls
    assert all('/WEBP/' in x[1] for x in api.calls if x[0]=='upload')
    assert store.read(row['id'],ADMIN['id'])['data']['mockups_exported']
    assert not store.read(row['id'],ADMIN['id'])['data'].get('product_gid')
    assert any(isinstance(u[1],float) and not u[1].is_integer() for u in updates)


@pytest.mark.parametrize('numbered', [False, True])
def test_core_handoff_retries_then_manual_save_extends_same_folder(env, tmp_path, monkeypatch, numbered):
    from product_upload_chat_handoff import CORE, prepare
    from product_upload_source import current_source
    store, _, _ = env
    row, result, manifest = make_result(env, tmp_path)
    core = [entry for entry in manifest if entry['product_slot_id'] in CORE]
    api = Outputs()
    provider = SimpleNamespace(api=api, token='fixture')
    parent = api.base + '/Baseball'
    category = api.files[parent]['id']
    find = api.get_metadata_if_exists
    monkeypatch.setattr(api, 'get_metadata_if_exists', lambda token, key, **kwargs: find(token, key) or
                        next((dict(value) for value in api.files.values() if value.get('id') == key), None))
    monkeypatch.setattr('prompt_store.get_prompt', lambda _key, default, **kwargs: default)
    progress = []

    def save(entries, **options):
        return transfer(provider, result, entries, api.root, parent, 'Product', store.connect,
                        ADMIN['id'], lambda *event: progress.append(event), category_id=category,
                        **options)

    if numbered:
        unrelated = api.create_folder('fixture', parent, 'Product')
        assert save(core, core_only=True, conflict='cancel')['cancelled']
    # Approved automatic uploads cycle through the same first choice as manual saves
    # and reserve a numbered folder when the original is already owned.
    automatic = dict(core_only=True, conflict='cancel', number_on_conflict=numbered)
    api.fail_once = core[0]['archive_name']
    incomplete = save(core, **automatic)
    with pytest.raises(ValueError):
        prepare(result, row, incomplete, 'Exact original lifestyle prompt.')
    receipt = save(core, **automatic)
    assert len(receipt['successes']) == 5
    assert {total for _, _, total in progress} == {5}
    assert not store.read(row['id'], ADMIN['id'])['data']['mockups_exported']
    manual = prepare(result, row, receipt, 'Exact original lifestyle prompt.')
    assert not manual['automatic']
    handoff = prepare(result, row, dict(receipt, generation_receipt='a' * 32), 'Exact original lifestyle prompt.')
    assert handoff['automatic'] and handoff['companion_id'] == manual['companion_id']
    prompt = handoff['prompt']
    black = next(item['metadata'] for item in receipt['successes']
                 if item['relative_path'] == core[0]['archive_name'])
    assert black['id'] in prompt and black['path_display'] in prompt
    assert 'Exact original lifestyle prompt.' in prompt and 'lossless WebP, method 1' in prompt
    from psd_directory import REVIEW_FOLDER, ROOT
    assert 'Upload to Live' in prompt and 'Create as DRAFT' not in prompt
    assert 'Use ACTIVE from the first Shopify create call' in prompt
    assert 'Online Store publication confirmed' in prompt
    mapping = prompt.split('STEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD', 1)[1]
    assert mapping.index('Wait for the published product') < mapping.index('Move that original master') < mapping.index('Open Add / Attach PSD')
    assert all(value in mapping for value in (REVIEW_FOLDER, ROOT, row['data']['source']['id'],
                                               row['data']['source']['rev'], row['data']['source']['content_hash']))
    assert 'use Add / Attach PSD manually' not in prompt
    assert 'https://www.dropbox.com/home/' in prompt
    assert 'STEP 1 DOWNLOAD EXCEPTION' in prompt
    assert "pasted.txt" in prompt and 'Leave the other four WebPs in Dropbox' in prompt
    assert 'Fetch the temporary download URL directly' in prompt

    # A stale completion record must recover a missing WebP before it can dispatch.
    del api.files[black['path_display']]
    refreshed = save(core, **automatic)
    assert refreshed['destination'] == receipt['destination']
    assert len(refreshed['successes']) == 5 and black['path_display'] in api.files

    full = save(manifest, conflict='cancel', extend_core=receipt['export_fingerprint'])
    assert len(full['successes']) == 8
    assert full['destination'] == receipt['destination']
    assert full['product_folder_id'] == receipt['product_folder_id']
    assert sum(kind == 'upload' for kind, _ in api.calls) == 10  # eight originals, one failed, one recovered
    assert current_source(store.read(row['id'], ADMIN['id']))['expected_webp_count'] == 8
    if numbered:
        assert api.files[parent + '/Product'] == unrelated


def test_save_collision_numbered_no_replace_and_source_fence(env,tmp_path):
    store,_,_=env;row,result,manifest=make_result(env,tmp_path)
    api=Outputs();provider=SimpleNamespace(api=api,token='fixture')
    old=api.create_folder('fixture',api.base+'/Baseball','Product')
    receipt=transfer(provider,result,manifest,api.root,api.base+'/Baseball','Product',store.connect,ADMIN['id'],lambda *a:None)
    assert receipt['destination'].endswith('/Product (2)')
    assert api.files[api.base+'/Baseball/Product']==old
    with store.locked(row['id'],ADMIN['id']) as (value,cur):value['data']['source']['rev']='new-revision'
    with pytest.raises(ValueError,match='revision changed'):
        transfer(provider,result,manifest,api.root,api.base+'/Baseball','Other',store.connect,ADMIN['id'],lambda *a:None)
    with pytest.raises(ValueError):product_folder(api,'  ')
    assert collection_root(api,api.root)==api.base
    with pytest.raises(ValueError,match='sport collection'):
        transfer(provider,result,manifest,api.root,api.base,'Product',store.connect,ADMIN['id'],lambda *a:None)


def test_same_existing_file_with_different_bytes_never_overwritten(env,tmp_path):
    store,_,_=env;_,result,manifest=make_result(env,tmp_path)
    api=Outputs();provider=SimpleNamespace(api=api,token='fixture')
    api.fail_once=manifest[0]['archive_name']
    first=transfer(provider,result,manifest,api.root,api.base+'/Baseball','Product',store.connect,ADMIN['id'],lambda *a:None)
    path=api.join_upload_path(first['destination'],manifest[0]['archive_name'])
    api.files[path]=dict(content_hash='different',size=10)
    calls=len(api.calls)
    second=transfer(provider,result,manifest,api.root,api.base+'/Baseball','Product',store.connect,ADMIN['id'],lambda *a:None)
    assert len(second['failures'])==1 and len(api.calls)==calls
    assert api.files[path]['content_hash']=='different'


def test_original_registry_actor_source_revision_replacement_and_revocation(env,tmp_path,monkeypatch):
    import product_upload_gallery as gallery
    store,_,_=env;row=saved(env)
    monkeypatch.setattr('mockup_storage.safe_temp_path',lambda path:Path(path))
    path=tmp_path/'black.png';Image.new('RGB',(61,43),'navy').save(path)
    result=dict(run_dir=tmp_path,_product_upload_actor_id=str(ADMIN['id']),_product_upload_intake=str(row['id']))
    url=gallery.register(result,dict(key='black'),row['data']['source'],path)
    token=url.split('token=')[1]
    assert gallery.resolve(token,ADMIN['id'],store.read)==path.resolve()
    with pytest.raises(ValueError):gallery.resolve(token,'other actor',store.read)
    with store.locked(row['id'],ADMIN['id']) as (value,cur):value['data']['source']['rev']='changed'
    with pytest.raises(ValueError,match='previous PSD'):gallery.resolve(token,ADMIN['id'],store.read)
    gallery.revoke(row['id'],ADMIN['id'])
    with pytest.raises(ValueError,match='expired'):gallery.resolve(token,ADMIN['id'],store.read)


def test_product_renderer_has_no_zip_controls_and_standalone_unchanged():
    import product_upload_outputs_ui as ui,product_upload_mockups_ui as shell
    text=inspect.getsource(ui)
    assert 'render_final_zip_download' not in text and 'Load Full Resolution' not in text
    assert 'ensure_primary_download_zip' not in inspect.getsource(shell)
    assert 'Copy each prompt' not in text


def test_automatic_save_uses_second_half_and_waits_for_confirmed_receipt(monkeypatch):
    import product_upload_outputs_ui as ui
    from product_upload_jobs import JOBS

    key = 'upload'
    token = 'save'
    state = {'_product_upload_active': key}
    receipt = {'core_only': True, 'successes': [{}] * 5}
    result = {'_product_upload_intake': key, 'product_upload_core_receipt': receipt}
    app = SimpleNamespace(_mockups_result=lambda: result)
    job = dict(state='Running', total=5, completed=0, stage='Saving WebPs', token=token)
    observed = []
    monkeypatch.setattr(ui.st, 'session_state', state)
    monkeypatch.setattr(ui.st, 'progress', lambda value, *, text: observed.append(value))
    monkeypatch.setattr(JOBS, 'snapshot', lambda *args: job)
    monkeypatch.setattr(JOBS, 'result', lambda *args: receipt)

    ui.save_progress.__wrapped__(app, key, 'actor', core=True)
    job['completed'] = 5
    ui.save_progress.__wrapped__(app, key, 'actor', core=True)
    assert observed == [.5, .99]
    job['state'] = 'Ready'
    state['product-upload-save-applied-' + key] = token
    ui.save_progress.__wrapped__(app, key, 'actor', core=True)
    assert observed[-1] == 1.


def test_retain_uploaded_original_without_export_resize(tmp_path):
    import io
    from product_upload_gallery import retain_upload_original
    image=io.BytesIO();Image.new('RGB',(2000,1200),'navy').save(image,format='PNG')
    image.name='original.png'
    result=retain_upload_original(dict(run_dir=tmp_path),FILENAMES[0],image,'sig')
    original=Path(result['product_upload_originals'][FILENAMES[0]]['path'])
    assert original.read_bytes()==image.getvalue()
    with Image.open(original) as retained:assert retained.size==(2000,1200)
    stamp=original.stat().st_mtime_ns
    retain_upload_original(result,FILENAMES[0],image,'sig')
    assert original.stat().st_mtime_ns==stamp


def test_explicit_collision_cancel_then_numbered_retry(env,tmp_path):
    store,_,_=env;row,result,manifest=make_result(env,tmp_path)
    api=Outputs();provider=SimpleNamespace(api=api,token='fixture')
    parent=api.base+'/Cricket';target=parent+'/Product'
    api.files[target]={'.tag':'folder','id':'unrelated-folder'}
    cancelled=transfer(provider,result,manifest,api.root,parent,'Product',store.connect,ADMIN['id'],lambda *a:None,conflict='cancel')
    assert cancelled['cancelled'] and api.calls==[]
    api.fail_once=manifest[0]['archive_name']
    first=transfer(provider,result,manifest,api.root,parent,'Product',store.connect,ADMIN['id'],lambda *a:None,conflict='numbered')
    assert first['destination']==target+' (2)' and first['failures']
    second=transfer(provider,result,manifest,api.root,parent,'Product',store.connect,ADMIN['id'],lambda *a:None,conflict='numbered')
    assert not second['failures'] and second['destination']==first['destination']
    assert len([c for c in api.calls if c[0]=='folder'])==1
    assert api.files[target]['id']=='unrelated-folder'


def test_category_id_rename_retries_same_owned_product_folder(env,tmp_path):
    store,_,_=env;row,result,manifest=make_result(env,tmp_path)
    api=Outputs();provider=SimpleNamespace(api=api,token='fixture')
    parent=api.base+'/Cricket'
    api.files[parent]['id']='id:category'
    # Metadata-by-ID and returned paths model the real team-space SDK.
    def metadata(token,path):
        for current,value in api.files.items():
            if current==path or value.get('id')==path:return dict(value,path_display=current)
        return None
    api.get_metadata_if_exists=metadata
    api.fail_once=manifest[0]['archive_name']
    first=transfer(provider,result,manifest,api.root,parent,'Product',store.connect,ADMIN['id'],lambda *a:None,category_id='id:category')
    assert first['failures']
    new_parent=api.base+'/Cricket Wall Art'
    api.files={path.replace(parent,new_parent,1) if path==parent or path.startswith(parent+'/') else path:value for path,value in api.files.items()}
    second=transfer(provider,result,manifest,api.root,new_parent,'Product',store.connect,ADMIN['id'],lambda *a:None,category_id='id:category')
    assert not second['failures'] and second['destination']==new_parent+'/Product'
    assert len([c for c in api.calls if c[0]=='folder'])==1


@pytest.mark.parametrize('reservation', ['deleted', 'replaced', 'path-only', 'id-without-path', 'moved'])
def test_approved_core_save_recovers_stale_folder_reservation(env, tmp_path, monkeypatch, reservation):
    from product_upload_chat_handoff import CORE, prepare

    store, _, _ = env
    row, result, manifest = make_result(env, tmp_path)
    core = [item for item in manifest if item['product_slot_id'] in CORE]
    api = Outputs()
    provider = SimpleNamespace(api=api, token='fixture')
    parent = api.base + '/Baseball'
    category_id = api.files[parent]['id']
    lookup_overrides = {}

    def metadata(token, key, *, missing_only=False):
        if key in lookup_overrides:
            return deepcopy(lookup_overrides[key])
        return deepcopy(api.files.get(key) or next((item for item in api.files.values()
                                                   if item['id'] == key), None))

    monkeypatch.setattr(api, 'get_metadata_if_exists', metadata)
    monkeypatch.setattr('prompt_store.get_prompt', lambda _key, default, **kwargs: default)

    def save():
        return transfer(provider, result, core, api.root, parent, 'Product', store.connect,
                        ADMIN['id'], lambda *args: None, category_id=category_id,
                        core_only=True, conflict='cancel', number_on_conflict=True)

    first = save()
    original = prepare(result, row, first, 'Lifestyle instructions')
    old_target = first['destination']
    if reservation == 'path-only':
        lookup_overrides[first['product_folder_id']] = None
    elif reservation == 'id-without-path':
        lookup_overrides[first['product_folder_id']] = {'.tag': 'folder', 'id': first['product_folder_id']}
    else:
        for path in tuple(api.files):
            if path == old_target or path.startswith(old_target + '/'):
                item = api.files.pop(path)
                if reservation == 'moved':
                    new_path = path.replace(old_target, api.base + '/Cricket/Product', 1)
                    api.files[new_path] = dict(item, path_display=new_path)
    if reservation == 'replaced':
        replacement = api.create_folder('fixture', parent, 'Product')

    previous_calls = len(api.calls)
    if reservation == 'moved':
        with pytest.raises(ValueError, match='Restore it to the selected sport folder'):
            save()
        assert len(api.calls) == previous_calls
        return

    recovered = save()
    assert len(recovered['successes']) == 5 and not recovered['failures']
    assert recovered['export_fingerprint'] == first['export_fingerprint']
    handoff = prepare(result, row, recovered, 'Lifestyle instructions')
    assert handoff['companion_id'] == original['companion_id']
    if reservation in ('path-only', 'id-without-path'):
        assert recovered['product_folder_id'] == first['product_folder_id']
        assert len(api.calls) == previous_calls
    else:
        assert recovered['product_folder_id'] != first['product_folder_id']
        assert {x['metadata']['id'] for x in recovered['successes']}.isdisjoint(
            x['metadata']['id'] for x in first['successes'])
        assert len(api.calls) == previous_calls + 6
    expected_target = old_target + ' (2)' if reservation == 'replaced' else old_target
    assert recovered['destination'] == expected_target
    assert expected_target + '/WEBP' in handoff['prompt']
    if reservation == 'replaced':
        assert api.files[old_target] == replacement
        assert not any(path.startswith(old_target + '/') for path in api.files)


def test_category_move_during_transfer_stops_before_more_uploads(env,tmp_path):
    store,_,_=env;row,result,manifest=make_result(env,tmp_path)
    api=Outputs();provider=SimpleNamespace(api=api,token='fixture');parent=api.base+'/Cricket'
    original=api.get_metadata_if_exists
    moved=[False]
    def metadata(token,path):
        if path=='id:category':return {'.tag':'folder','id':path,'name':'Cricket','path_display':parent+'/nested' if moved[0] else parent}
        return original(token,path)
    api.get_metadata_if_exists=metadata
    def progress(stage,completed,total):
        if completed==1:moved[0]=True
    with pytest.raises(ValueError,match='no longer directly'):
        transfer(provider,result,manifest,api.root,parent,'Product',store.connect,ADMIN['id'],progress,category_id='id:category')
    assert len([c for c in api.calls if c[0]=='upload'])==1


def test_save_encoder_and_manifest_exactly_match_standalone(env,tmp_path,monkeypatch,request):
    import app,image_factory as factory,io
    import tempfile
    short=tempfile.TemporaryDirectory(prefix='sc-out-');request.addfinalizer(short.cleanup)
    tmp_path=Path(short.name)
    from unittest.mock import Mock
    from tests.test_auto_editions_colour import icc
    original=tmp_path/'art.png';Image.new('RGB',(500,350),(23,57,92)).save(original,icc_profile=icc())
    result=factory.generate_product_images('Actual encoder fixture','Cricket',original,
        base_dir=Path(__file__).resolve().parents[1],output_root=tmp_path/'runs')
    for filename in FILENAMES:
        image=io.BytesIO();Image.new('RGB',(2000,1200),(60,100,150)).save(image,format='PNG');image.seek(0)
        paths=factory.save_lifestyle_mockup(result['run_dir'],result['product_slug'],result['sport_slug'],filename,image)
        result=app.upsert_result_asset(result,app.build_lifestyle_asset(Path(filename),paths))
    result=app.normalize_generation_result(result)
    manifest=app._mockup_dropbox_manifest(result,(app.ASSET_CATEGORY_CORE,app.ASSET_CATEGORY_PRODUCT,app.ASSET_CATEGORY_SOCIAL))
    # Shared standalone implementation hands the exact same original paths/bytes
    # to upload_batch. No Product Upload encoder, cropper or thumbnail conversion.
    standalone=Outputs();received=[]
    def batch(token,target,items,**kwargs):
        received.extend(dict(i) for i in items)
        assert kwargs['simple_limit']==0 and kwargs['chunk_size']==1024*1024
        return standalone.upload_batch(token,target,items,**kwargs)
    for name,value in [('get_metadata_if_exists',standalone.get_metadata_if_exists),('upload_batch',batch),
                       ('ensure_folder_path',lambda *a,**kw:None)]:monkeypatch.setattr(app.dropbox_integration,name,value)
    for name in ('_files_save_upload_metadata','_files_clear_directory_cache','record_activity_log'):monkeypatch.setattr(app,name,Mock())
    monkeypatch.setattr(app.st,'progress',Mock())
    app._save_mockups_to_dropbox_impl('fixture',ADMIN,result,manifest,standalone.root,standalone.base+'/Cricket','Fixture','cancel')
    assert [(i['relative_path'],i['local_path'],i['size']) for i in received]==[(e['archive_name'],e['path'],e['byte_length']) for e in manifest]
    import auto_editions as ae
    expected={e['archive_name']:(ae.file_hash(e['path'],dropbox=True),Image.open(e['path']).size) for e in manifest}
    row=saved(env);store=env[0]
    result.update(_product_upload_intake=str(row['id']),_product_upload_actor_id=str(ADMIN['id']),_product_upload_source_hash=row['data']['source']['content_hash'],_product_upload_source=row['data']['source'])
    provider=SimpleNamespace(api=Outputs(),token='fixture')
    receipt=transfer(provider,result,manifest,provider.api.root,provider.api.base+'/Cricket','Fixture',store.connect,ADMIN['id'],lambda *a:None)
    assert not receipt['failures'] and len(receipt['successes'])==8
    for item in receipt['successes']:
        assert item['metadata']['content_hash']==expected[item['relative_path']][0]
    assert all(expected[e['archive_name']][1]==(1600,960) for e in manifest if e.get('category')==factory.ASSET_CATEGORY_PRODUCT)
    assert factory.EXPORT_WEBP_QUALITY==82 and factory.EXPORT_WEBP_METHOD==4 and factory.EXPORT_JPG_QUALITY==92
