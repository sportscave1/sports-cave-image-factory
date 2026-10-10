"""Actual page dispatcher/renderers with controlled read-only data boundaries.

Email and Reporting are populated synthetic workloads. Other routes use their
real unconfigured/offline behavior; those are NOT populated production timings.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.fixtures.navigation_v5_sources import (ROOT, block_external_sources,
    app_definitions, variant_module, Sources, install_email_sources, install_reporting_sources, install_operational_sources)
block_external_sources()
import streamlit as st
import streamlit.components.v1 as components
import time, html, json, base64, os
from unittest.mock import patch

st.set_page_config(layout='wide', initial_sidebar_state='expanded')
before = os.environ.get('SC_V5_VARIANT', 'after') == 'before'
source = Sources(st.session_state)
namespace = {'__file__': str(ROOT / 'app.py'), '__name__': 'navigation_v5_app'}
st.session_state['v5_attempts'] = st.session_state.get('v5_attempts', 0) + 1
exec(app_definitions(before), namespace)
user = {'id': 'v5-local-admin', 'role': 'admin', 'is_active': True,
    'display_name': 'Controlled local validation', 'timezone': 'Australia/Sydney',
    'email': 'owner@sportscave.test', 'page_permissions': ['reporting', 'view_activity_log'], 'session_version': 1}
os.environ['SPORTS_CAVE_REPORTING_OWNER_EMAIL'] = user['email']
namespace['current_os_user'] = lambda: user
namespace['BASE_DIR'] = ROOT
namespace['logout_app'] = lambda: None
namespace['init_session_state']()
st.session_state['sports_cave_current_user'] = user
namespace['inject_styles']()

email = variant_module('support_email_page', before)
reports = variant_module('reporting_store', before)
report_page = variant_module('reporting_page', before)
config = install_email_sources(email, st.session_state, source)
install_reporting_sources(report_page, reports, source)
install_operational_sources(st.session_state, source)
if os.environ.get('SC_V5_CRM_SQL') == '1':
    # Actual CRM renderers/stores against disposable loopback SQL, sending disabled.
    import crm_page, crm_service
    from crm_store import Store
    from crm_resend import Config
    from crm_shopify import Shopify
    from tests.crm_db_fixture import connect
    from tests.crm_fixtures import ShopifyFixture
    os.environ['CRM_FIXTURE_SQL_PORT'] = '8997'
    crm_store = Store(connect)
    if not st.session_state.get('v5_crm_seeded'):
        crm_store.seed()
        from crm_automation_store import AutomationStore
        local = AutomationStore(connect)
        if not local.q("SELECT id FROM crm_automations WHERE name=%s", ('V5 Synthetic Flow',)):
            local.create(user, 'welcome', 'V5 Synthetic Flow')
        st.session_state['v5_crm_seeded'] = True
    shop = Shopify(st.session_state.setdefault('v5_shop', ShopifyFixture()))
    crm_service.audit = lambda *a, **k: None
    if not hasattr(crm_page, '_v5_actual_render'):
        crm_page._v5_actual_render = crm_page.render_page
    crm_page.render_page = lambda route, user, navigate: crm_page._v5_actual_render(
        route, user, navigate, shop=shop, store=crm_store, config=Config({}))
namespace['get_support_email_page'] = lambda: email
namespace['get_reporting_page'] = lambda: report_page
# All imported data boundaries fail closed; workers cannot make external calls.
# Keep selected-page logic and real widgets/components intact.

start = time.perf_counter()
read_start = len(st.session_state.get('v5_reads', []))
route = namespace['get_current_page']()
top_bar = namespace['top_bar']
with patch('top_bar_security.create_top_bar_token', return_value='offline-v5'):
    bar = top_bar.top_bar_config(user, current_route=route,
        logo_src='data:image/webp;base64,' + base64.b64encode((ROOT/'assets/sports-cave-os-app-icon.webp').read_bytes()).decode(),
        navigation_epoch=st.session_state.get('navigation_epoch', 0))
bar.update(dailyPlannerEnabled=False, dailyPlannerStatusUrl='', notificationsUrl='',
    orderStatusUrl='', emailStatusUrl='', searchUrl='', repairRequestsUrl='', emailEventsUrl='')
instrument = (ROOT/'tests/fixtures/navigation_v4_instrument.js').read_text()
components.html('<script>'+instrument+'</script>'+top_bar.component_html(bar), height=0)
sidebar_start = time.perf_counter()
namespace['render_sidebar']()
sidebar_ms = (time.perf_counter()-sidebar_start)*1000
route = namespace['get_current_page']()
st.session_state['v5_full_runs'] = st.session_state.get('v5_full_runs', 0) + 1
namespace['ensure_current_page_access'](route)
route = namespace['get_current_page']()
init_started = time.perf_counter()
if route == 'Email' and not st.session_state.get('v5_mailbox_seeded'):
    # Explicit controlled cold load makes complete data comparable. Browser
    # handoff to load_initial_mailbox is separately excluded, not timed as zero.
    state = st.session_state.setdefault('support_email_workspace', {})
    st.session_state['support_email_scope'] = (config.scope, user['id'])
    email.Workspace(state, user, config, email.load_smtp_configuration()).load(defer_body=True)
    st.session_state['v5_mailbox_seeded'] = True
failure = ''
try:
    namespace['render_selected_page'](route)
except Exception as error:
    failure = type(error).__name__
    st.error('Isolated destination could not render: '+failure)
init_ms = (time.perf_counter()-init_started)*1000
page_status = 'error' if failure else namespace.get('_navigation_page_status', lambda route: 'ready')(route)
namespace['_finish_navigation_transition'](route, status=page_status)
server_ms = (time.perf_counter()-start)*1000
reads = st.session_state.get('v5_reads', [])[read_start:]
sample = {'route': route, 'page_init_ms': init_ms, 'server_ms': server_ms,
    'sidebar_ms': sidebar_ms, 'reads': reads, 'failure': failure,
    'attempts': st.session_state['v5_attempts'], 'variant': 'before' if before else 'after', 'runs': st.session_state['v5_full_runs']}
samples = st.session_state.setdefault('v5_samples', [])
samples.append(sample)
key = namespace['os_accounts'].page_key_for_route(route)
st.markdown('<div id="navigation-v4-content" data-route="'+html.escape(key)+'" '
    'data-server-ms="'+str(server_ms)+'" data-sidebar-ms="'+str(sidebar_ms)+'" '
    'data-renders="'+str(sample['runs'])+'"></div>', unsafe_allow_html=True)
st.html('<div id="v5-evidence" data-samples="'+html.escape(json.dumps(samples), quote=True)+'"></div>')
top_bar.render_navigation_complete(components, current_route=route,
    navigation_epoch=st.session_state.get('navigation_epoch',0),status=page_status)
