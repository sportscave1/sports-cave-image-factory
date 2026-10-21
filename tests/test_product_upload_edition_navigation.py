from unittest.mock import Mock
from types import SimpleNamespace
import product_upload_edition_navigation as navigation


def test_existing_picker_selects_id_and_reports_missing_without_attachment(monkeypatch):
    import edition_ops as ops
    row={'shopify_product_gid':'gid://shopify/Product/123','product_title':'Tempted','handle':'tempted'}
    state={}
    def picker(label,options,**kwargs):
        assert label=='Find product'
        return state.get(kwargs['key'], options[0])
    st=SimpleNamespace(session_state=state,query_params={'edition_product':'123','edition_search':'wrong title'},selectbox=picker,info=Mock())
    monkeypatch.setattr(ops,'st',st)
    visible,selected=ops._editor_visible_rows([row])
    assert visible==[row] and selected==ops._stable_row_key(row)
    st.info.assert_not_called()
    st.query_params={'edition_product':'456','edition_search':'Tempted'}
    ops._editor_visible_rows([row])
    assert 'pending / not found' in st.info.call_args.args[0]
    assert navigation.selection([row], '456', 'Tempted')==[]


def test_title_hint_is_only_used_without_stable_id():
    rows=[{'product_title':'Tempted — Conquering Everest','shopify_product_gid':'123'}]
    assert navigation.selection(rows,title='Conquering Everest')==rows
    assert navigation.selection(rows,'456','Conquering Everest')==[]
