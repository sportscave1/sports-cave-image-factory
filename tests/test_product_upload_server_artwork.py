"""Real PSD decoding and shared Mockups engine, no Companion or cloud writes."""
import hashlib
import json
from pathlib import Path
import struct
from time import perf_counter
import uuid
from unittest.mock import Mock
import pytest
from PIL import Image
from tests.test_product_upload_intake import database,env,ADMIN
from tests.test_product_upload_dropbox import provider_fixture
from tests.test_auto_editions_colour import icc,resource,approved
from product_upload_dropbox import select,status,REVIEW
import product_upload_artwork as artwork


def real_psd(path, colour=(220,35,60), tagged=True, width=640,height=480, rle=False):
    resources=resource(1039,icc()) if tagged else b''
    pixels=b'\0\0'+b''.join(bytes([c])*(width*height) for c in colour)
    if rle:
        rows=[]
        for c in colour:
            row=b''.join(bytes([257-min(128,width-at),c]) if width-at>1 else bytes([0,c]) for at in range(0,width,128))
            rows.extend([row]*height)
        pixels=b'\0\1'+b''.join(struct.pack('>H',len(row)) for row in rows)+b''.join(rows)
    path.write_bytes(b'8BPS\0\1'+b'\0'*6+struct.pack('>HIIHH',len(colour),height,width,8,3)
        +struct.pack('>I',0)+struct.pack('>I',len(resources))+resources
        +struct.pack('>I',0)+pixels)
    return path


def source_fixture(env,tmp_path,monkeypatch,tagged=True):
    store,sql,provider=env;add=provider_fixture(provider)
    psd=real_psd(tmp_path/'isolated.psd',tagged=tagged)
    from auto_editions import file_hash
    meta=add();meta.update(content_hash=file_hash(psd,dropbox=True),size=psd.stat().st_size)
    provider.files[meta['id']]=meta;provider.files[meta['path_display']]=meta
    provider.download=Mock(side_effect=lambda metadata,destination:Path(destination).write_bytes(psd.read_bytes()))
    monkeypatch.setenv('SPORTS_CAVE_TEMP_DIR',str(tmp_path/'server'))
    monkeypatch.setattr('product_upload_render.Renders.claim',Mock(side_effect=AssertionError('Companion must not be contacted')))
    row=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],meta['rev'])
    return row,meta,psd


def test_disconnected_companion_selection_full_resolution_preview_and_shared_generation(env,tmp_path,monkeypatch):
    store,sql,provider=env;started=perf_counter();row,meta,original=source_fixture(env,tmp_path,monkeypatch)
    before=original.read_bytes();row=artwork.prepare(store.connect,provider,str(row['id']),ADMIN['id'])
    selection_to_ready=(perf_counter()-started)*1000
    folder=artwork.ready(row,store.connect,provider)
    with Image.open(folder/'artwork.png') as image:
        assert image.size==(640,480) and image.getpixel((300,200))==(220,35,60)
        assert image.info['icc_profile']
    with Image.open(folder/'preview.webp') as preview:
        assert preview.size==(640,480) and preview.getpixel((300,200))[0]>200
    # Actual shared generation, using isolated scene templates and local prompts.
    templates=tmp_path/'base/templates';templates.mkdir(parents=True)
    for name in ('black-frame-template.jpg','oak-frame-template.jpg','white-frame-template.jpg','unframed-template.jpg','size-guide-template.jpg'):
        Image.new('RGB',(1000,1800),'white').save(templates/name)
    import image_factory
    monkeypatch.setattr(image_factory.prompt_store,'get_prompt',lambda key,default='',**kwargs:default)
    monkeypatch.setattr(image_factory.prompt_store,'get_cached_prompt',lambda key,default='',**kwargs:default)
    started=perf_counter()
    result=image_factory.generate_product_images('Offline Test','Football',folder/'artwork.png',base_dir=templates.parent,output_root=tmp_path/'generated')
    assert len(result['assets'])>=5
    assert original.read_bytes()==before and not provider.api.move_path.called
    assert 'mockup_render' not in row['data'] and status(row,store.connect)['data']['state']=='Ready'
    assert not row['data'].get('companion_connected')
    out=Path(__file__).resolve().parents[1]/'output/product-upload-server-correction';out.mkdir(parents=True,exist_ok=True)
    (out/'offline-timings.json').write_text(json.dumps(dict(source='Synthetic 640x480 RGB8 PSD; real Pillow decoder, ICC conversion, shared Mockups engine; isolated Dropbox stream/templates; no Companion',selection_to_artwork_ready_ms=round(selection_to_ready,2),mockup_generation_ms=round((perf_counter()-started)*1000,2)),indent=2),encoding='utf-8')


def test_revision_and_settings_cache_reuse_and_corruption_rejection(env,tmp_path,monkeypatch):
    store,sql,provider=env;row,meta,original=source_fixture(env,tmp_path,monkeypatch)
    first=artwork.prepare(store.connect,provider,str(row['id']),ADMIN['id'])
    second=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],meta['rev'])
    reused=artwork.prepare(store.connect,provider,str(second['id']),ADMIN['id'])
    assert reused['data']['server_artwork']['reused'] and provider.download.call_count==1
    folder=artwork.ready(reused,store.connect,provider);(folder/'artwork.png').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='Prepare'):artwork.ready(reused,store.connect,provider)
    repaired=artwork.prepare(store.connect,provider,str(second['id']),ADMIN['id'])
    assert not repaired['data']['server_artwork']['reused'] and provider.download.call_count==2
    provider.files[meta['id']]['rev']='a2'
    with pytest.raises(ValueError,match='revision changed'):artwork.ready(first,store.connect,provider)
    newer=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],'a2')
    assert not artwork.prepare(store.connect,provider,str(newer['id']),ADMIN['id'])['data']['server_artwork']['reused']
    monkeypatch.setattr(artwork,'settings',lambda connect:'changed-settings')
    assert not artwork.prepare(store.connect,provider,str(newer['id']),ADMIN['id'])['data']['server_artwork']['reused']


def test_source_changes_during_transfer_cannot_complete_other_selection(env,tmp_path,monkeypatch):
    store,sql,provider=env;row,meta,original=source_fixture(env,tmp_path,monkeypatch)
    original_download=provider.download.side_effect
    def changed(metadata,destination):
        original_download(metadata,destination);provider.files[meta['id']]['rev']='a2'
    provider.download.side_effect=changed
    with pytest.raises(ValueError,match='revision changed'):artwork.prepare(store.connect,provider,str(row['id']),ADMIN['id'])
    assert store.read(str(row['id']),ADMIN['id'])['data']['server_artwork']['state']=='Failed'
    newer=select(store.connect,provider,str(uuid.uuid4()),ADMIN['id'],'DRAFT',meta['id'],'a2')
    assert newer['data']['server_artwork']['state']=='Selected'


def test_missing_profile_requires_approved_recovery_and_truncated_composite_rejected(env,tmp_path,monkeypatch):
    store,sql,provider=env;row,meta,original=source_fixture(env,tmp_path,monkeypatch,tagged=False)
    monkeypatch.setattr('auto_editions_colour_store.configuration',lambda connect:dict(policies=[],memberships=[],default_group=''))
    with pytest.raises(ValueError,match='approval'):artwork.prepare(store.connect,provider,str(row['id']),ADMIN['id'])
    policy=approved(artwork.source(row))
    monkeypatch.setattr('auto_editions_colour_store.configuration',lambda connect:dict(policies=[policy],memberships=[],default_group=''))
    assert artwork.prepare(store.connect,provider,str(row['id']),ADMIN['id'])['data']['server_artwork']['state']=='Ready'
    truncated=real_psd(tmp_path/'truncated.psd');truncated.write_bytes(truncated.read_bytes()[:-50])
    with pytest.raises(ValueError,match='truncated'):artwork.decode(truncated,tmp_path/'never.png',row,store.connect)


@pytest.mark.parametrize('switch_selection',[False,True])
def test_product_upload_generate_button_uses_server_artwork_and_original_engine(env,tmp_path,monkeypatch,switch_selection):
    import ast
    from contextlib import nullcontext
    from types import SimpleNamespace
    import product_upload_api as api
    import image_factory
    store,sql,provider=env;row,meta,original=source_fixture(env,tmp_path,monkeypatch);key=str(row['id'])
    monkeypatch.setattr(api,'connect',store.connect);monkeypatch.setattr(api,'Dropbox',lambda:provider)
    monkeypatch.setattr('product_upload_render.Renders.request',Mock(side_effect=AssertionError('No native render request allowed')))
    state={'_product_upload_active':key};held={}
    st=SimpleNamespace(session_state=state,subheader=lambda *a,**k:None,text_input=lambda *a,**k:k.get('value',''),
        selectbox=lambda *a,**k:'Football',button=lambda label,**k:label=='Generate Core Shopify Images',
        status=lambda *a,**k:nullcontext(),info=lambda *a:None,error=lambda message:(_ for _ in ()).throw(AssertionError(message)))
    app=SimpleNamespace(_mockups_result=lambda:held.get('result'),_set_mockups_result=lambda result:held.update(result=result),
        alphabetize_options=lambda values,**k:values,SPORT_OPTIONS=['Football'],get_sport_category=lambda a,b:a,
        MOCKUPS_GENERATION_SEMAPHORE=__import__('threading').Semaphore(1),BASE_DIR=tmp_path,
        build_mockup_final_prompt_items=lambda *a:[],normalize_generation_result=lambda r:r,render_generation_result=lambda r:None)
    row=artwork.prepare(store.connect,provider,key,ADMIN['id'])
    generate=Mock(return_value=dict(product_name='Same',sport_category='Football'))
    if switch_selection:
        def changed(**kwargs):
            state['_product_upload_active']='newer-selection'
            return dict(product_name='Same',sport_category='Football')
        generate.side_effect=changed
    discarded=Mock();monkeypatch.setattr('product_upload_mockups.release_transient',discarded)
    monkeypatch.setattr(image_factory,'generate_product_images',generate)
    tree=ast.parse((Path(__file__).resolve().parents[1]/'product_upload_mockups_ui.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_design')
    scope=dict(st=st,Path=Path,poll_render=lambda *a:None)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'isolated-render-design','exec'),scope)
    scope['render_design'](app,row,ADMIN)
    generate.assert_called_once()
    with Image.open(generate.call_args.kwargs['artwork_file_path']) as image:assert image.size==(640,480)
    if switch_selection:
        assert not held.get('result');discarded.assert_called_once();return
    assert held['result']['_product_upload_intake']==key
    assert held['result']['_product_upload_source_hash']==meta['content_hash']
    assert store.read(key,ADMIN['id'])['data']['server_artwork']['state']=='Ready'


def test_rle_composite_preserves_alpha_and_memory_admission_fails_clearly(env,tmp_path,monkeypatch):
    store,sql,provider=env;row,meta,original=source_fixture(env,tmp_path,monkeypatch)
    path=real_psd(tmp_path/'alpha.psd',colour=(123,44,210,128),width=64,height=32,rle=True)
    output=tmp_path/'alpha.png';artwork.decode(path,output,row,store.connect)
    with Image.open(output) as image:assert image.mode=='RGBA' and image.getpixel((30,20))==(123,44,210,128)
    import image_factory
    monkeypatch.setattr(image_factory,'validate_processing_memory',lambda *a:(_ for _ in ()).throw(image_factory.MemoryLimitExceededError('Insufficient server memory for artwork.')))
    with pytest.raises(ValueError,match='server memory'):artwork.prepare(store.connect,provider,str(row['id']),ADMIN['id'])
    assert 'server memory' in store.read(str(row['id']),ADMIN['id'])['data']['server_artwork']['reason']


def test_prepare_without_selection_never_restores_latest_product():
    connect=Mock(side_effect=AssertionError('No latest-account lookup allowed'))
    with pytest.raises(ValueError,match='exact Dropbox'):artwork.prepare(connect,Mock(),None,ADMIN['id'])
    connect.assert_not_called()
