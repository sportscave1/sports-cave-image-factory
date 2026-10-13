"""Actual shared Flow/composer, isolated PostgreSQL, fabricated customers only."""
import os,sys,json,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if os.getenv('LIFECYCLE_BASELINE')=='1':
    from tests.lifecycle_baseline import install
    install()
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import requests,streamlit as st
from crm_automation_store import AutomationStore
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import CFG
from crm_logic import now

st.set_page_config(layout='wide',page_title='Local lifecycle acceptance fixture')
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network forbidden'))
AutomationStore.render_settings=lambda self,env=None:deepcopy(CFG)

@st.cache_resource
def setup():
    store=AutomationStore(connect);rows={}
    if os.getenv('LIFECYCLE_BASELINE')!='1':
        from tests.test_crm_lifecycle_expansion import DatabaseTests,CUSTOMER
        from crm_lifecycle_audience import cache_customer
        DatabaseTests.setUpClass()
        for i in range(120):
            c=deepcopy(CUSTOMER);at=now()-timedelta(days=i)
            c.update(id='gid://shopify/Customer/'+str(800000+i),email=f'collector{i}@example.test',firstName='Fixture',lastName=f'Collector {i}',updatedAt=at.isoformat())
            c['emailMarketingConsent']['consentUpdatedAt']=at.isoformat()
            cache_customer(store,c,now())
            if i>=10:
                oid='gid://shopify/Order/'+str(900000+i)
                store.q('''INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,order_name,financial_status,
                  fulfillment_status,total_price,currency,created_at,raw_json)
                  VALUES(%s,%s,%s,'PAID','FULFILLED','120','AUD',%s,%s::jsonb) ON CONFLICT DO NOTHING''',
                  (oid,c['id'],'#'+str(1000+i),at-timedelta(days=100),json.dumps({'fulfillments':[{'status':'SUCCESS','createdAt':(at-timedelta(days=95)).isoformat()}], 'lineItems':{'nodes':[{'title':'Fabricated test artwork'}]}})))
                store.webhook('shopify','fixture-paid-'+str(i),'orders/paid',oid,c['id'],at-timedelta(days=100))
    for kind in ('abandoned','welcome','post_purchase','win_back','fulfilled'):
        args={} if kind in ('abandoned','fulfilled') or os.getenv('LIFECYCLE_BASELINE')=='1' else {'lifecycle':True}
        rows[kind]=store.create(ADMIN,kind,{'abandoned':'Abandoned Cart','welcome':'Welcome Series','post_purchase':'Post Purchase','win_back':'Win Back','fulfilled':'Fulfilment Follow-up'}[kind],**args)
    # Prewarm only synthetic thumbnails, so timing excludes browser-install jobs.
    from crm_thumbnail_cache import cache_dir,selection
    from tests.test_crm_flow_v4 import webp
    for row in rows.values():
        for step in row['config']['draft']['emails']:cache_dir().joinpath(selection(row,step)[0]+'.webp').write_bytes(webp())
    return {kind:str(row['id']) for kind,row in rows.items()}

ids=setup()
from crm_automation_ui import workspace,request_route
with st.container(horizontal=True):
    for kind,identity in ids.items():
        if st.button(kind,key='fixture-nav-'+kind):request_route(identity);st.rerun()
if not st.session_state.get('fixture-open'):
    st.session_state['automation_selected']=ids[st.query_params.get('flow','abandoned')]
    st.session_state['fixture-open']=True
shop=Mock();shop.namespace='lifecycle-offline-fixture'
shop.abandoned_preview.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
shop.customers.side_effect=AssertionError('Audience pages must not query Shopify')
shop.orders.side_effect=AssertionError('Audience pages must not query Shopify')
workspace(shop,AutomationStore(connect),SimpleNamespace(user=ADMIN))
