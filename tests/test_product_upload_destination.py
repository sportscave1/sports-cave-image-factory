from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import dropbox_integration as api
from product_upload_export import sport_categories


def test_categories_read_all_pages_only_direct_folders(monkeypatch):
    root='/Sportscave Team Folder';base=root+'/04_OUTPUT/product-images'
    def entry(name, tag='folder'):
        return {'.tag':tag,'name':name,'path_display':base+'/'+name}
    pages=Mock(side_effect=[dict(entries=[entry('Zulu'),entry('file.txt','file')],has_more=True,cursor='next'),
                           dict(entries=[entry('Motorsport Wall Art'),entry('Zulu/existing-product'),entry('alpha')],has_more=False)])
    monkeypatch.setattr(api,'list_folder_page',pages)
    options=sport_categories(api,'authenticated-token',root)
    assert [x['name'] for x in options]==['alpha','Motorsport Wall Art','Zulu']
    assert [c.args for c in pages.call_args_list]==[('authenticated-token',base)]*2
    assert [c.kwargs['cursor'] for c in pages.call_args_list]==['','next']


def test_incomplete_listing_fails_closed(monkeypatch):
    monkeypatch.setattr(api,'list_folder_page',lambda *a,**kw:dict(entries=[],has_more=True,cursor='same'))
    with pytest.raises(ValueError,match='incomplete'):sport_categories(api,'token','/Team')


def test_compact_destination_panel(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    script=Path(__file__).parent/'fixtures/product_upload_destination.py'
    test=AppTest.from_file(str(script))
    test.session_state['original_path']=str(tmp_path/'original.webp')
    (tmp_path/'original.webp').write_bytes(b'original-export-not-preview')
    test.run()
    test.button(key='product-upload-save-all-fixture').click().run()
    assert not test.exception
    category=test.selectbox(key='product-upload-save-picker-fixture-category')
    assert category.options==['Cricket','Motorsport Wall Art']
    assert test.button(key='product-upload-save-confirm-fixture').disabled
    category.select('/Team/04_OUTPUT/product-images/Motorsport Wall Art').run()
    assert test.session_state['listing_calls']==['/Team/04_OUTPUT/product-images']
    assert not test.session_state['submissions']
    assert any(c.value=='Motorsport Wall Art / Current_ Product' for c in test.caption)
    test.button(key='product-upload-save-close-fixture').click().run()
    assert not test.error, [e.value for e in test.error]
    assert not test.session_state['product-upload-save-picker-fixture']
    assert not test.selectbox
    assert test.session_state['result']['assets']==['prepared-originals']
    test.button(key='product-upload-save-all-fixture').click().run()
    assert test.selectbox[0].value.endswith('/Motorsport Wall Art')
    test.button(key='product-upload-save-confirm-fixture').click().run()
    assert not test.exception
    assert len(test.session_state['submissions'])==1
    captured=test.session_state['submissions'][0]
    assert captured['parent'].endswith('/Motorsport Wall Art') and captured['folder']=='Current_ Product'
    assert captured['manifest'][0]['path']==tmp_path/'original.webp'
    assert captured['conflict']=='cancel'
    assert test.button(key='product-upload-save-confirm-fixture').disabled
    assert test.button(key='product-upload-save-all-fixture').disabled
    assert test.selectbox[0].disabled
    assert any('Saving' in i.value for i in test.info)


def test_missing_assets_disable_save(tmp_path):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    test=AppTest.from_file(str(Path(__file__).parent/'fixtures/product_upload_destination.py'))
    test.session_state['original_path']=str(tmp_path/'missing.webp')
    test.run().button(key='product-upload-save-all-fixture').click().run()
    test.selectbox[0].select('/Team/04_OUTPUT/product-images/Motorsport Wall Art').run()
    assert test.button(key='product-upload-save-confirm-fixture').disabled
