"""Actual OS navigation and CRM destination bodies; disposable SQL only.

Extract the production shell functions without running unrelated app startup
services. Authentication and transport boundaries are fabricated; CRM rendering,
SQL, permissions, sidebar, top bar and query routing are production code.
"""
import ast, base64, html, json, logging, os, sys, time
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import streamlit as st
import streamlit.components.v1 as components
import requests
import os_accounts, navigation_runtime, social_media, sidebar_theme, top_bar
import seo_navigation as seo_nav
import ads_navigation as ads_nav
import analytics_navigation as analytics_nav
import files_window_launcher
from tests.fixtures.navigation_v4_support import navigation_code
from tests.test_crm import ADMIN, config as local_config
from tests.crm_db_fixture import connect as sql_connect
from tests.test_crm_send_flow import CFG, LIVE
from tests.test_crm_simple_editor import document

if os.getenv('AUTOMATIONS_V5_BASELINE')=='1':
    import types
    for name in ('crm_automation_store','crm_automation_toolbar','crm_automation_ui','crm_automation_home','crm_page','crm_flow_page'):
        module=types.ModuleType(name);module.__file__=str(ROOT/(name+'.py'))
        sys.modules[name]=module
        source=(ROOT/'tmp/automations-v5-before'/(name+'.py')).read_text(encoding='utf-8-sig')
        exec(compile(source,module.__file__,'exec'),module.__dict__)
from crm_automation_store import AutomationStore
from crm_automation_definition import email_step
from crm_page import render_page
from crm_store import Store
os.environ.update(LIVE)
requests.sessions.Session.request=lambda *a,**k: (_ for _ in ()).throw(AssertionError('External transport forbidden'))
AutomationStore.render_settings=lambda self,env=None:deepcopy(CFG)

@st.cache_resource
def setup(steps):
    store=AutomationStore(sql_connect)
    ids=[]
    for kind in ('welcome','post_purchase','abandoned'):
        row=store.create(ADMIN,kind,'V5 '+kind+' '+str(steps)+' stages')
        flow=deepcopy(row['config']['draft'])
        flow['emails']=[email_step(document(),i*3600) for i in range(steps)]
        row=store.save_flow(ADMIN,row['id'],row['name'],flow,1)
        ids.append(str(row['id']))
    return ids

def current_os_user():return ADMIN
def get_components_module():return components
def logout_app():pass
exec(navigation_code(str(ROOT/'app.py')),globals())
st.set_page_config(layout='wide',initial_sidebar_state='expanded')
setup(int(st.query_params.get('fixture_steps',3)))
st.session_state['v5_runs']=st.session_state.get('v5_runs',0)+1
logging.warning('V5_APP_RUN number=%s',st.session_state['v5_runs'])
started=time.perf_counter();current=get_current_page();inject_styles()
with patch('top_bar_security.create_top_bar_token',return_value='offline'):
    logo='data:image/webp;base64,'+base64.b64encode((ROOT/'assets/sports-cave-os-app-icon.webp').read_bytes()).decode()
    cfg=top_bar.top_bar_config(ADMIN,logo_src=logo,current_route=current,
        navigation_epoch=st.session_state.get(NAVIGATION_EPOCH_STATE_KEY,0))
cfg.update(emailEventsUrl='',dailyPlannerStatusUrl='',orderStatusUrl='',emailStatusUrl='',notificationsUrl='',searchUrl='',repairRequestsUrl='')
components.html(top_bar.component_html(cfg),height=0,width=0)
render_sidebar();current=get_current_page()
from tests.fixtures.automation_v5_sql import connect,configure
configure(latency_ms=int(st.query_params.get('fixture_latency_ms',0)),fail_identity=bool(st.query_params.get('fixture_fail_identity')),fail_save=bool(st.query_params.get('fixture_fail_save')),fail_definition=bool(st.query_params.get('fixture_fail_definition')))
shop=Mock();shop.namespace='local-v5';shop.abandoned_preview.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
if current=='CRM Automations':
    render_page(current,ADMIN,navigate=set_current_page,shop=shop,store=Store(connect),config=local_config())
else:
    st.title(current)
    st.caption('Local shell destination. Automations uses its actual production page body.')
_finish_navigation_transition(current,status='ready')
st.session_state['v5_completed_runs']=st.session_state.get('v5_completed_runs',0)+1
st.html('<span id="v5-render" data-runs="'+str(st.session_state['v5_runs'])+'" data-completed-runs="'+str(st.session_state['v5_completed_runs'])+'" data-server-ms="'+str((time.perf_counter()-started)*1000)+'"></span>')
top_bar.render_navigation_complete(components,current_route=current,
    navigation_epoch=st.session_state.get(NAVIGATION_EPOCH_STATE_KEY,0),status='ready')
