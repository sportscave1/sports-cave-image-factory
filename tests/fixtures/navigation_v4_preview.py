"""Production navigation/controller with offline content and no live services.

The destination bodies are explicit test stubs. Their times are never reported
as real Orders/Email/Meta API or page timings.
"""
import ast
import base64
import html
import json
import logging
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import streamlit as st
import streamlit.components.v1 as components
import os_accounts, navigation_runtime, social_media
import seo_navigation as seo_nav
import ads_navigation as ads_nav
import analytics_navigation as analytics_nav
import files_window_launcher, sidebar_theme, top_bar
from tests.fixtures.navigation_v4_support import navigation_code

variant = os.environ.get('SC_NAV_BENCHMARK_VARIANT', 'current')
baseline = variant in {'baseline', 'compact'}
if baseline:
    css_file = 'sidebar_theme.before.py' if variant == 'baseline' else 'sidebar.compact.py'
    css_tree = ast.parse((ROOT/'tmp/navigation-v4'/css_file).read_text())
    sidebar_theme.SIDEBAR_CSS = next(ast.literal_eval(n.value) for n in css_tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                                            t.id == 'SIDEBAR_CSS' for t in n.targets))
    html_file = 'topbar.before.html' if variant == 'baseline' else 'topbar.pre-validation.html'
    top_bar.COMPONENT_PATH = ROOT/'tmp/navigation-v4'/html_file
    top_bar._component_source.cache_clear()
    app_path = ROOT/'tmp/navigation-v4/app.pre-validation.py'
else:
    app_path = ROOT/'app.py'
    top_bar._component_source.cache_clear()

def current_os_user():
    return {'id': 'local-navigation-only', 'role': 'admin', 'is_active': True,
            'display_name': 'Local navigation verification'}
def get_components_module():
    return components
def logout_app():
    st.session_state['fixture_logout_seen'] = True

exec(navigation_code(str(app_path)), globals())
st.set_page_config(layout='wide', initial_sidebar_state='expanded')
start = time.perf_counter()
st.session_state['fixture_full_runs'] = st.session_state.get('fixture_full_runs', 0) + 1
current = get_current_page()
inject_styles()
with patch('top_bar_security.create_top_bar_token', return_value='offline-only'):
    logo = 'data:image/webp;base64,'+base64.b64encode((ROOT/'assets/sports-cave-os-app-icon.webp').read_bytes()).decode()
    config = top_bar.top_bar_config(current_os_user(), logo_src=logo, current_route=current,
        navigation_epoch=st.session_state.get(NAVIGATION_EPOCH_STATE_KEY, 0))
config.update(dailyPlannerEnabled=True, emailEventsUrl='',
              dailyPlannerStatusUrl='', orderStatusUrl='', emailStatusUrl='',
              notificationsUrl='', searchUrl='', repairRequestsUrl='')
if st.query_params.get('badges') == '1':
    config['orderStatusUrl']='data:application/json,{"action_required_count":4,"badge_label":"4"}'
    config['emailStatusUrl']='data:application/json,{"unread_count":125}'
# Install measurement before the controller, retaining it across reruns.
instrument = (ROOT/'tests/fixtures/navigation_v4_instrument.js').read_text(encoding='utf-8')
seed = ''
if st.query_params.get('badges') == '1':
    records = {'orders': {'action_required_count': 4, 'badge_label': '4'},
               'email': {'unread_count': 125, 'checked_at': time.time()},
               'wall': {'wall_unread_count': 99}}
    for kind, payload in records.items():
        cache_key = 'scTopBarStatus:'+config['revision']+':'+kind
        seed += 'window.parent.sessionStorage.setItem('+json.dumps(cache_key)+','+json.dumps(json.dumps({'checked_at': time.time()*1000, 'payload': payload}))+');'
controller_html = top_bar.component_html(config)
if st.query_params.get('width_probe') == 'no-observer':
    controller_html = controller_html.replace('if (sidebar && parentWindow.ResizeObserver) {', 'if (false) {')
components.html('<script>'+seed+instrument+'</script>'+controller_html, height=0, width=0)
sidebar_start = time.perf_counter()
render_sidebar()
sidebar_ms = (time.perf_counter()-sidebar_start)*1000
current = get_current_page()
st.session_state['fixture_page_renders'] = st.session_state.get('fixture_page_renders', 0) + 1
key = os_accounts.page_key_for_route(current)
st.title(current)
st.caption('Actual production navigation; offline destination content. No customer or advertising mutations.')
_finish_navigation_transition(current, status='ready')
server_ms = (time.perf_counter()-start)*1000
st.session_state['fixture_last_server_ms'] = server_ms
st.session_state['fixture_last_sidebar_ms'] = sidebar_ms
st.markdown('<div id="navigation-v4-content" data-route="'+html.escape(key)+'" '
    'data-server-ms="'+str(server_ms)+'" data-sidebar-ms="'+str(sidebar_ms)+'" '
    'data-renders="'+str(st.session_state['fixture_page_renders'])+'"></div>', unsafe_allow_html=True)
top_bar.render_navigation_complete(components, current_route=current,
    navigation_epoch=st.session_state.get(NAVIGATION_EPOCH_STATE_KEY, 0), status='ready')
