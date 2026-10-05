"""Synthetic loopback-only Automations visual fixture, never production data."""
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import streamlit as st
import requests
from crm_automation_store import AutomationStore
from crm_automation_definition import email_step
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm_simple_editor import document

st.set_page_config(layout='wide',page_title='Local automation fixture')
os.environ.update(LIVE)
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network forbidden'))
AutomationStore.render_settings=lambda self,env=None:deepcopy(CFG)

@st.cache_resource
def setup(legacy_preview=False):
    store=AutomationStore(connect)
    from crm_logic import now
    store.set_state('shopify_automation_capabilities',{'checked_at':now().isoformat(),'triggers':{k:'AVAILABLE' for k in ('welcome','post_purchase','abandoned','fulfilled')}})
    identities=[]
    for kind,name,state in (('welcome','Welcome series · local fixture','ACTIVE'),('abandoned','Abandoned checkout · local fixture','DRAFT'),('post_purchase','Collector follow-up · local fixture','PAUSED')):
        row=store.create(ADMIN,kind,name);flow=deepcopy(row['config']['draft'])
        flow['emails']=[email_step(document(),0),email_step(document(),86400)]
        if kind=='abandoned':
            from crm_abandoned_checkout import apply_template
            apply_template(flow['emails'][0]['document'])
            if legacy_preview:
                from tests.test_crm_checkout_preview_fallback import LEGACY
                doc=flow['emails'][0]['document'];doc['middle_sections'].pop(1)
                doc['middle_sections'][0]['html']=LEGACY;doc['custom_html']=LEGACY
        row=store.save_flow(ADMIN,row['id'],row['name'],flow,1)
        if state!='DRAFT':row=store.publish(ADMIN,row['id'],row['config']['revision'],env=LIVE)
        if state=='PAUSED':store.lifecycle(ADMIN,row['id'],'pause')
        identities.append(str(row['id']))
    return identities

identities=setup(bool(st.query_params.get('fixture_legacy')))
if st.query_params.get('fixture_checkout') and not st.session_state.get('fixture_selected'):
    st.session_state['automation_selected']=identities[1];st.session_state['fixture_selected']=True
from tests.test_crm_abandoned_checkout import checkout
shop=st.session_state.get('fixture_shop')
if shop is None:shop=Mock();st.session_state['fixture_shop']=shop
fixture_checkout=checkout(identity=2 if st.session_state.get('fixture_new_customer') else 1,items=2)
if st.session_state.get('fixture_new_customer'):
    fixture_checkout['customer']['firstName']='New'
    fixture_checkout['lineItems']['nodes'][0]['title']='New collector product'
shop.abandoned_preview.return_value={'nodes':[fixture_checkout],'pageInfo':{'hasNextPage':False}}
shop.query.return_value={'abandonedCheckouts':{'nodes':[fixture_checkout],'pageInfo':{'hasNextPage':False}}}
shop.checkout.return_value=fixture_checkout
shop.customer_batch.return_value=[fixture_checkout['customer']]
if st.query_params.get('fixture_analytics'):
    from tests.fixtures.crm_checkout_analytics_data import configure
    configure(AutomationStore(connect),shop,identities[1])
if st.query_params.get('fixture_failure'):shop.abandoned_preview.side_effect=RuntimeError('Synthetic provider unavailable')
elif st.query_params.get('fixture_delay'):
    def delayed(**kwargs):
        from time import sleep
        sleep(2)
        return {'nodes':[checkout(items=2)],'pageInfo':{'hasNextPage':False}}
    shop.abandoned_preview.side_effect=delayed
from crm_automation_ui import workspace
if st.query_params.get('fixture_rerun'):
    import crm_checkout_preview as preview_module
    if not hasattr(preview_module,'_fixture_document'):
        preview_module._fixture_document=preview_module.document
        def measured_document(*args,**kwargs):
            st.session_state['fixture_hydrations']=st.session_state.get('fixture_hydrations',0)+1
            return preview_module._fixture_document(*args,**kwargs)
        preview_module.document=measured_document
    if st.button('Synthetic global rerun'):
        from time import sleep
        sleep(2)
    if st.button('Synthetic new checkout'):
        st.session_state['fixture_new_customer']=True
        fresh=checkout(identity=2,items=2)
        fresh['customer']['firstName']='New'
        fresh['lineItems']['nodes'][0]['title']='New collector product'
        shop.abandoned_preview.return_value={'nodes':[fresh],'pageInfo':{'hasNextPage':False}}
    if st.button('Synthetic lookup failure'):
        st.session_state['fixture_lookup_failure']=True
    if st.session_state.get('fixture_lookup_failure'):shop.abandoned_preview.side_effect=RuntimeError('Synthetic failure')
if st.query_params.get('fixture_home_delay'):
    from contextlib import ExitStack
    from unittest.mock import patch
    from time import sleep
    import crm_automation_home as home_module
    def slow(fn):
        def work(*args,**kwargs):
            sleep(3)
            return fn(*args,**kwargs)
        return work
    with ExitStack() as stack:
        for name in ('rows','summary','activity'):
            stack.enter_context(patch.object(home_module,name,slow(getattr(home_module,name))))
        workspace(shop,AutomationStore(connect),SimpleNamespace(user=ADMIN))
else:
    workspace(shop,AutomationStore(connect),SimpleNamespace(user=ADMIN))

if st.query_params.get('fixture_profile'):st.caption('Fixture Shopify requests: '+str(shop.abandoned_preview.call_count))
if st.query_params.get('fixture_rerun'):st.caption('Fixture hydrations: '+str(st.session_state.get('fixture_hydrations',0)))
