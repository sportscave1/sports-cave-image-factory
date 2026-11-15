"""Retired Mockups entry points use the real query-route normalizer, offline."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
import os_accounts
import navigation_runtime

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'app.py').read_text(encoding='utf-8')

@pytest.mark.parametrize('old_url', ['Mockups', 'mockups'])
def test_old_mockups_url_canonicalizes_to_product_uploads(old_url):
    names = {'normalise_app_page', 'page_query_param_value', 'page_from_query_params',
             'page_query_value', 'sync_current_page_to_query_params'}
    nodes = [n for n in ast.parse(SOURCE).body if isinstance(n, ast.FunctionDef) and n.name in names]
    state = SimpleNamespace(query_params={'page': old_url}, session_state={})
    ns = dict(st=state, os_accounts=os_accounts, social_media=SimpleNamespace(LEGACY_REELS_PAGE_KEY='legacy-reels'),
              ALL_PAGE_OPTIONS=[p['route'] for p in os_accounts.PAGE_REGISTRY], PAGE_QUERY_PARAM='page',
              CURRENT_PAGE_QUERY_STATE_KEY='last-query')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), ns)
    route = ns['page_from_query_params']()
    assert route == 'Product Uploads'
    assert ns['sync_current_page_to_query_params'](route)
    assert state.query_params['page'] == 'product_uploads'
    assert os_accounts.can_access_page({'role':'admin','is_active':True}, route)
    assert not os_accounts.can_access_page({'role':'worker','is_active':True}, route)

def test_obsolete_page_is_absent_and_shared_renderer_remains():
    names = {n.name for n in ast.parse(SOURCE).body if isinstance(n, ast.FunctionDef)}
    assert 'render_mockups_page' not in names
    assert 'process_uploaded_artwork_once' not in names
    assert 'render_generation_result' in names
    assert 'build_mockup_final_prompt_items' in names
    assert 'Mockups' not in os_accounts.PAGE_BY_ROUTE
    assert 'mockups' not in os_accounts.PAGE_BY_KEY
    assert '_sidebar_route_button("Mockups"' not in SOURCE
    assert (ROOT / 'mockups_page.css').exists()

def test_image_protection_parent_and_authorization():
    page = os_accounts.PAGE_BY_KEY['image_protection']
    assert page['route'] == 'Image Protection'
    assert page['parent_key'] == 'developer'
    assert page['navigation_child'] and not page['worker_assignable']
    assert navigation_runtime.active_disclosure_group('Image Protection') == 'developer'
    assert os_accounts.can_access_page({'role':'admin','is_active':True}, 'Image Protection')
    assert not os_accounts.can_access_page({'role':'worker','is_active':True,'page_permissions':['image_protection']}, 'Image Protection')


def test_retired_permission_does_not_grant_product_uploads():
    worker = {'role': 'worker', 'is_active': True, 'page_permissions': ['dashboard', 'mockups']}
    assert not os_accounts.can_access_page(worker, 'Product Uploads')
    assert not os_accounts.can_access_page(worker, 'Mockups')
    assert 'Product Uploads' not in os_accounts.allowed_navigation_routes(worker)
    worker['page_permissions'].append('product_uploads')
    assert os_accounts.can_access_page(worker, 'Product Uploads')
    assert os_accounts.can_access_page(worker, 'Mockups')
