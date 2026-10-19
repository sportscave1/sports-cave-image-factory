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


def fixture_app(tmp_path):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    test=AppTest.from_file(str(Path(__file__).parent/'fixtures/product_upload_destination.py'))
    original=tmp_path/'original.webp';original.write_bytes(b'original-export-not-preview')
    test.session_state['original_path']=str(original)
    test.run()
    return test,original


def test_one_top_selection_drives_sport_and_save(tmp_path):
    test,original=fixture_app(tmp_path)
    assert len(test.selectbox)==1
    assert test.selectbox[0].options==['Football Wall Art','Motorsport Wall Art','Soccer Wall Art','V8 Supercars Wall Art']
    assert test.button(key='product-upload-save-all-fixture').disabled
    test.selectbox[0].select('id:motor').run()
    assert not test.exception and not test.error
    assert test.session_state['listing_calls']==['/Team/04_OUTPUT/product-images']
    assert not test.session_state['submissions']
    assert test.session_state['result']['sport_category']=='Motorsport'
    test.selectbox[0].select('id:v8').run()
    result=test.session_state['result']
    assert result['sport_category']=='V8 Supercars'
    assert result['assets'][0]['webp_path']==original
    assert result['lifestyle_mockup_paths']=={'uploaded':'retained'}
    assert any(c.value=='Saving to: V8 Supercars Wall Art / Current_ Product' for c in test.caption)
    assert not any(b.label=='Save' for b in test.button)
    test.button(key='product-upload-save-all-fixture').click().run()
    assert not test.exception and not test.error
    captured=test.session_state['submissions'][0]
    assert captured['parent'].endswith('/V8 Supercars Wall Art') and captured['folder']=='Current_ Product'
    assert captured['category_id']=='id:v8' and captured['result']['sport_category']=='V8 Supercars'
    assert captured['manifest'][0]['path']==original
    assert 'v8-supercars' in captured['manifest'][0]['archive_name']
    assert original.read_bytes()==b'original-export-not-preview'
    assert captured['conflict']=='cancel'
    assert test.button(key='product-upload-save-all-fixture').disabled and test.selectbox[0].disabled
    assert len(test.session_state['submissions'])==1


def test_id_rename_refresh_and_missing_folder_never_fallback(tmp_path):
    test,_=fixture_app(tmp_path)
    test.selectbox[0].select('id:motor').run()
    test.session_state['renamed']=True
    test.run()
    assert test.selectbox[0].value=='id:motor'
    assert 'Motor Racing Wall Art' in test.selectbox[0].options
    test.button(key='product-upload-save-all-fixture').click().run()
    captured=test.session_state['submissions'][0]
    assert captured['parent'].endswith('/Motor Racing Wall Art')
    test.session_state['job']=None
    test.session_state['missing']=True
    test.run()
    assert test.error
    assert test.selectbox[0].value is None
    assert test.button(key='product-upload-save-all-fixture').disabled
    assert len(test.session_state['submissions'])==1


def test_new_upload_clears_selection_without_default(tmp_path):
    test,_=fixture_app(tmp_path)
    test.selectbox[0].select('id:soccer').run()
    assert test.session_state['result']['sport_category']=='Soccer'
    test.selectbox[0].select('id:football').run()
    assert test.session_state['result']['sport_category']=='Football'
    test.button[ -1 ].click().run()
    assert test.session_state['product-upload-category-fixture-resolved'] is None
    assert test.button(key='product-upload-save-all-fixture').disabled


def test_missing_original_disables_save(tmp_path):
    test,original=fixture_app(tmp_path)
    original.unlink()
    test.selectbox[0].select('id:motor').run()
    assert test.button(key='product-upload-save-all-fixture').disabled


def test_resolve_rejects_moved_folder_and_uses_id(monkeypatch):
    from product_upload_export import resolve_category
    meta=Mock(return_value={'.tag':'folder','id':'id:motor','name':'Motor','path_display':'/Team/elsewhere/Motor'})
    monkeypatch.setattr(api,'get_metadata_if_exists',meta)
    with pytest.raises(ValueError,match='no longer directly'):resolve_category(api,'token','/Team','id:motor')
    meta.assert_called_once_with('token','id:motor')
