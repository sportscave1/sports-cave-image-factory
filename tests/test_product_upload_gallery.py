import base64
import io
from pathlib import Path
from types import SimpleNamespace
from PIL import Image


def test_preview_reuses_standalone_encoder_and_invalidates_replacement(tmp_path):
    import image_factory as factory
    from product_upload_gallery import preview_item,_preview_data
    original=tmp_path/'original.png';Image.new('RGB',(2000,1200),'navy').save(original)
    preview=factory.create_preview_file(original,tmp_path/'previews','preview.webp')
    item=preview_item(preview,'/original-not-fetched','Fixture')
    raw=base64.b64decode(item['preview'].split(',',1)[1])
    assert raw==preview.read_bytes()
    with Image.open(io.BytesIO(raw)) as image:assert image.size==(900,540) and image.format=='WEBP'
    assert factory.MAX_PREVIEW_EDGE==900 and factory.PREVIEW_WEBP_QUALITY==70 and factory.PREVIEW_WEBP_METHOD==4
    hits=_preview_data.cache_info().hits
    assert preview_item(preview,'/original-not-fetched','Fixture')==item
    assert _preview_data.cache_info().hits==hits+1
    Image.new('RGB',(700,400),'gold').save(preview,format='WEBP')
    assert preview_item(preview,'/original-not-fetched','Fixture')['preview']!=item['preview']


def test_core_row_order_and_metadata_only_original_availability(tmp_path,monkeypatch):
    import product_upload_outputs_ui as ui
    import product_upload_gallery as gallery
    assets=[]
    for key in ('size-guide','white','black','unframed','oak'):
        preview=tmp_path/(key+'.webp');Image.new('RGB',(90,60),'navy').save(preview,format='WEBP')
        assets.append(dict(key=key,label=key,asset_group='generated',preview_path=preview))
    lookups=[]
    monkeypatch.setattr(gallery,'register',lambda result,asset,source,path:lookups.append(asset['key']) or '/original/'+asset['key'])
    items=ui.core_preview_items(SimpleNamespace(get_asset_full_resolution_path=lambda asset:tmp_path/'original-not-read.png'),dict(assets=assets),{'rev':'one'})
    assert [item['label'] for item in items]==['black','oak','white','unframed','size-guide']
    assert lookups==['black','oak','white','unframed','size-guide']
    assert all(item['preview'].startswith('data:image/webp;base64,') for item in items)


def test_keyed_component_payload_has_only_previews_and_no_editors(tmp_path,monkeypatch):
    import streamlit.components.v1 as components
    import product_upload_gallery as gallery
    import product_upload_outputs_ui as ui
    import inspect
    calls=[]
    monkeypatch.setattr(components,'declare_component',lambda name,**kwargs:lambda **args:calls.append(args))
    gallery.render(key='one',mode='actions',original='/api/original',prompt='resolved master')
    assert calls==[dict(mode='actions',items=[],original='/api/original',prompt='resolved master',key='one',default=None)]
    source=inspect.getsource(ui)
    assert 'prompt_editing_allowed' not in source and 'render_mockup_prompt_editor' not in source and 'Edit master prompt' not in source
    assert "mode='gallery'" in source
