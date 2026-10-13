"""Isolated synthetic PostgreSQL/Streamlit audience; no production configuration."""
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if os.getenv('EMAIL_V2_BASELINE')=='1':
    baseline=Path(__file__).resolve().parents[2]/'.tmp-email-v2/v1'
    if not (baseline/'crm_flow_recipients.py').is_file():raise RuntimeError('Prepare the V1 baseline described in docs/EMAIL_AUTOMATION_V2_20261014.md')
    sys.path.insert(0,str(baseline))
import streamlit as st
st.set_page_config(layout='wide')
from copy import deepcopy
from datetime import timedelta
from crm_logic import now
from tests.test_crm_post_purchase_audience import OrderAudienceTests
from tests.test_crm import ADMIN
from tests.test_crm_lifecycle_expansion import order
from crm_lifecycle_ui import audience
from tests.crm_ui_profile import instrument
import crm_lifecycle_ui
if st.query_params.get('profile')=='1':instrument(crm_lifecycle_ui,'_audience')

if 'fixture' not in st.session_state:
    case=OrderAudienceTests();case.setUpClass();case.setUp()
    draft,ids=case.orders(55)
    active=draft if st.query_params.get('mode')=='draft' else case.payment_flow()
    customers={};orders={}
    for i,identity in enumerate(ids):
        record=case.store.q('SELECT shopify_customer_id FROM shopify_orders WHERE shopify_order_id=%s',(identity,),True)
        cid=record['shopify_customer_id'];profile=deepcopy(case.customer)
        profile.update(id=cid,email=case.prefix+'-'+str(i)+'@example.test',firstName='Fixture purchaser '+str(i),updatedAt=now().isoformat(),createdAt=(now()-timedelta(days=1)).isoformat())
        customers[cid]=profile
        paid=now()-timedelta(minutes=10,seconds=i)
        value=order(identity=identity);value.update(createdAt=paid.isoformat(),paid_at=paid,customer={'id':cid},name='#Synthetic '+str(i))
        orders[cid]=[value]
        case.store.q('UPDATE shopify_orders SET created_at=%s WHERE shopify_order_id=%s',(paid,identity))
        case.store.webhook('shopify','ui-paid-'+identity.rsplit('/',1)[-1],'orders/paid',identity,cid,paid,
            normalized={'shop':'fixture.myshopify.com','payload_version':'2026-04'})
    case.shop.customer.side_effect=lambda identity,**_:deepcopy(customers.get(identity))
    case.shop.orders.side_effect=lambda identity,**_:dict(nodes=deepcopy(orders.get(identity,[])),pageInfo={'hasNextPage':False})
    from crm_lifecycle_audience import cache_customer
    for cid,profile in list(customers.items())[:5]:cache_customer(case.store,profile,now())
    for i,identity in enumerate(ids):case.store.q('UPDATE shopify_orders SET order_name=%s WHERE shopify_order_id=%s',('#Fixture'+str(3285+i),identity))
    st.session_state['fixture_metrics']={'reads':0,'elapsed_ms':[]}
    original=case.store.q
    def measured(sql,*args,**kwargs):
        from time import perf_counter
        at=perf_counter();result=original(sql,*args,**kwargs)
        if 'WITH audience AS' in sql:
            metrics=measurement
            metrics['reads']+=1;metrics['elapsed_ms'].append(round((perf_counter()-at)*1000,2))
        return result
    measurement=st.session_state['fixture_metrics']
    case.store.q=measured
    st.session_state['fixture']=(case,active)
    st.session_state['lifecycle-'+str(active['id'])+'-search']=case.prefix
case,active=st.session_state['fixture']
audience(case.store,ADMIN,case.store.flow(active['id']))
st.caption('Synthetic local fixture · no production connection or delivery worker')
if st.button('Fixture background order update'):
    case.store.q('UPDATE shopify_orders SET fulfillment_status=%s WHERE customer_email LIKE %s',('FULFILLED',case.prefix+'%'))
import json
@st.fragment(run_every=1)
def metrics():
    with st.container(key='fixture-metrics'):
        st.text(json.dumps(dict(**st.session_state['fixture_metrics'],fragment_ms=st.session_state.get('fixture-fragment-ms',[]))))
metrics()
