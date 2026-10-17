"""Loopback-only real editor/route/publication fixture; no application bootstrap."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock,patch
import streamlit as st
import requests
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm_simple_editor import document
from tests.test_crm_lifecycle_publication import LifecyclePublicationTests
from crm_automation_store import AutomationStore
from crm_automation_definition import email_step
from crm_automation_publication import tick
from crm_automation_ui import workspace
from crm_store import StoreUnavailable

if os.getenv('CRM_TEST_POSTGRES')!='1':raise RuntimeError('Local fixture opt-in required')
os.environ.update(LIVE)
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network forbidden'))
AutomationStore.render_settings=lambda self,env=None:deepcopy(CFG)
st.set_page_config(layout='wide',page_title='Synthetic individual publication')

@st.cache_resource
def setup(run,kind,active):
    LifecyclePublicationTests.setUpClass()
    store=AutomationStore(connect)
    from tests.crm_publication_fixture import ready
    ready(store)
    row=store.create(ADMIN,kind,'Welcome Series' if kind=='welcome' else 'Collector follow-up')
    flow=deepcopy(row['config']['draft'])
    flow['emails']=[email_step(document(),i*86400) for i in range(3)]
    for i,step in enumerate(flow['emails']):
        step.update(name='Fixture email '+str(i+1),enabled=active and i==2)
        step['document']['content']['subject']='Fixture subject '+str(i+1)
    row=store.save_flow(ADMIN,row['id'],row['name'],flow,1)
    if active:
        store.request_publish(ADMIN,row['id'],row['config']['revision'])
        tick(store,'fixture-seed',env=LIVE)
    return str(row['id'])

identity=setup(st.query_params.get('run','default'),st.query_params.get('kind','welcome'),st.query_params.get('active')=='1')
store=AutomationStore(connect)
if 'automation' not in st.query_params and 'automation_selected' not in st.session_state:
    st.session_state['automation_selected']=identity
st.html('<div id="fixture-flow-id" data-id="'+identity+'"></div>')
finish,fail=st.columns(2)
if finish.button('Fixture complete publication'):tick(store,'fixture-worker',env=LIVE)
if fail.button('Fixture fail publication'):
    with patch('crm_automation_publication.prepare',side_effect=ValueError('Email tracking validation failed')):
        tick(store,'fixture-worker',env=LIVE)

if not hasattr(AutomationStore,'_individual_fixture_request'):
    AutomationStore._individual_fixture_request=AutomationStore.request_publish
original=AutomationStore._individual_fixture_request
@st.cache_resource
def interrupted():return set()
def request(self,*args,**kwargs):
    if st.query_params.get('validation')=='1':raise ValueError('Review the selected email. '+('Long actionable validation explanation. '*25))
    job=original(self,*args,**kwargs)
    if st.query_params.get('lost')=='1' and str(job['automation_id']) not in interrupted():
        interrupted().add(str(job['automation_id']))
        raise StoreUnavailable('Synthetic response interrupted. Retry the saved request.')
    return job

shop=Mock()
shop.customer.return_value=None
AutomationStore.request_publish=request
# Unrelated audience/analytics/thumbnail panels are deliberately inert. The
# actual route, editor, confirmation, save barrier, sequence and worker run.
with (patch('crm_flow_page.analytics_controls'),patch('crm_flow_page.step_performance'),
      patch('crm_lifecycle_ui.audience'),patch('crm_flow_thumbnail.thumbnail'),
      patch('crm_campaign_send_ui.test_control')):
    workspace(shop,store,SimpleNamespace(user=ADMIN))
