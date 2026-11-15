"""Remounted upload components retain only the exact account-owned selection."""
import sys
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import product_upload_mockups_ui as ui


@pytest.mark.parametrize('active,available', [(None, False), ('selected-upload', True), ('selected-upload', False)])
def test_navigation_rehydrates_exact_selection_without_latest_upload_fallback(monkeypatch, tmp_path, active, available):
    for name in ('mockups_page.css', 'product_upload_page.css'):
        (tmp_path/name).write_text('')
    state={'_product_upload_visit': 'existing-visit'}
    if active:
        state['_product_upload_active']=active
    st=SimpleNamespace(session_state=state, query_params={}, html=Mock(), error=Mock())
    monkeypatch.setattr(ui, 'st', st)
    row={'id': active, 'mode': 'DRAFT', 'data': {}} if available else None
    read=Mock(return_value=row)
    store=Mock(return_value=SimpleNamespace(read=read))
    monkeypatch.setitem(sys.modules, 'product_upload_api', SimpleNamespace(connect=object()))
    monkeypatch.setitem(sys.modules, 'product_upload_intake', SimpleNamespace(Intakes=store))
    component=Mock(return_value=None)
    app=SimpleNamespace(BASE_DIR=tmp_path, current_os_user=lambda:{'id':'fixture-account'},
        get_components_module=lambda:SimpleNamespace(declare_component=Mock(return_value=component)))
    ui.render_page(app)
    args=component.call_args.kwargs
    if available:
        assert (args['id'],args['mode'])==('selected-upload','DRAFT')
    else:
        assert 'id' not in args
    assert state.get('_product_upload_active')==active
    assert all(call.args==(active,'fixture-account') for call in read.call_args_list)
    if not active:
        read.assert_not_called()


@pytest.mark.parametrize('navigation', ['set_current_page', 'get_current_page'])
def test_navigation_keeps_prepared_workflow_and_generated_result(navigation):
    source=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
    function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==navigation)
    prepared={'_product_upload_active':'selected-upload','_product_upload_visit':'same-visit',
              '_product_upload_event':'last-event','_product_upload_manual':False,
              '_product_upload_mockups_result':{'artifact':'preserved'},
              'product-upload-category-selected-upload-id':'football'}
    state={**prepared,'current':'Task Recorder'}
    namespace=dict(st=SimpleNamespace(session_state=state),normalise_app_page=lambda value:value,
        page_query_param_value=lambda:'product_uploads',page_from_query_params=lambda:'Product Uploads',
        page_query_value=lambda value:'product_uploads',_begin_navigation_transition=Mock(),
        _store_current_page=lambda route,**kw:state.update(current=route),sync_current_page_to_query_params=Mock(),
        CURRENT_PAGE_STATE_KEY='current',CURRENT_PAGE_QUERY_STATE_KEY='last-query',
        LEGACY_PAGE_STATE_KEY='legacy',NAVIGATION_CLIENT_ROUTE_STATE_KEY='client',
        NAVIGATION_HISTORY_ROUTE_STATE_KEY='history',
        navigation_runtime=SimpleNamespace(resolve_route=lambda **kw:('Product Uploads','history')),
        os_accounts=SimpleNamespace(crm_navigation=SimpleNamespace(navigation_allowed=lambda *a,**kw:True)))
    exec(compile(ast.Module(body=[function],type_ignores=[]),'app.py','exec'),namespace)
    result=namespace[navigation](*(['Product Uploads'] if navigation=='set_current_page' else []))
    assert result=='Product Uploads'
    assert all(state[key]==value for key,value in prepared.items())
