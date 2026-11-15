"""Compile actual navigation functions once; never start app.py or its services."""
import ast
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FUNCTIONS = {
    'inject_styles', 'normalise_app_page', 'page_query_param_value',
    'page_from_query_params', 'page_query_value', '_set_page_query_snapshot',
    'sync_current_page_to_query_params', '_store_current_page',
    '_begin_navigation_transition', '_finish_navigation_transition',
    'get_current_page', 'set_current_page', '_sidebar_route_clicked','_sidebar_route_button',
    '_active_sidebar_group', '_toggle_sidebar_group',
    '_render_sidebar_create_growth', '_render_sidebar_create_reporting', 'render_sidebar',
}
CONSTANTS = {
    'SIDEBAR_ICON_BY_ROUTE', 'SIDEBAR_NAV_LABELS', 'SIDEBAR_OPEN_GROUP_KEY',
    'MENU_OPTIONS', 'HIDDEN_PAGE_OPTIONS', 'ALL_PAGE_OPTIONS', 'PAGE_QUERY_PARAM', 'CURRENT_PAGE_STATE_KEY',
    'LEGACY_PAGE_STATE_KEY', 'CURRENT_PAGE_QUERY_STATE_KEY',
    'NAVIGATION_EPOCH_STATE_KEY', 'NAVIGATION_TRANSITION_STATE_KEY',
    'NAVIGATION_LAST_READY_STATE_KEY', 'NAVIGATION_HISTORY_ROUTE_STATE_KEY',
    'NAVIGATION_CLIENT_ROUTE_STATE_KEY',
}

@lru_cache(maxsize=3)
def navigation_code(path):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if
             isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                                              t.id in CONSTANTS for t in n.targets)]
    return compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec')
