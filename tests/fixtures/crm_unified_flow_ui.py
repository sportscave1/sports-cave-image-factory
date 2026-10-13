"""Synthetic loopback-only UI. No application bootstrap, credentials or providers."""
import sys,os,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
if os.getenv('UNIFIED_FLOW_BASELINE')=='1':
    for name in ('crm_automation_analytics_ui','crm_flow_page','crm_lifecycle_ui'):
        spec=importlib.util.spec_from_file_location(name,ROOT/'.tmp-unified-flow'/f'{name}.py')
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
import streamlit as st
from datetime import timedelta
from time import sleep,perf_counter
from unittest.mock import Mock
from crm_logic import now,date
from crm_lifecycle_definition import expanded_flow
from crm_automation_definition import new_flow
import crm_lifecycle_ui as lifecycle
import crm_automation_analytics_ui as checkout
from crm_flow_page import checkouts
import crm_flow_page
crm_flow_page.checkout_panel=checkout.checkout_panel.__wrapped__

st.set_page_config(layout='wide')
kind=st.query_params.get('flow','welcome')
class Backend:
    def __init__(self):self.calls=0;self.samples=[];self.at=now();self.delay=float(st.query_params.get('delay','.02'));self.fail=st.query_params.get('fail')=='1'
    def rows(self,store,row=None,*,search='',page=0,after=None,page_size=51,**kwargs):
        start=perf_counter();self.calls+=1;sleep(self.delay)
        if self.fail:raise RuntimeError('Synthetic read failure')
        values=[]
        for i in range(120):
            cid='gid://shopify/Customer/'+str(i)
            if kind=='abandoned':
                r=dict(checkout_key='row-'+str(i),admin_checkout_id='fixture-'+str(i),
                    created_at=self.at-timedelta(minutes=i),activity_at=self.at,read_at=now(),
                    analytics={'name':'Fixture customer '+str(i),'email':f'fixture{i}@example.test','shopify_abandoned':True},
                    automation_status='ACTIVE',steps=steps,published_steps=steps,enrollment_id='journey-'+str(i),
                    flow_status='ACTIVE',current_step=0,next_due_at=self.at+timedelta(hours=1),sends=[])
            else:
                r=dict(key='row-'+str(i),customer_id=cid,name='Fixture customer '+str(i),email=f'fixture{i}@example.test',
                    consent='SUBSCRIBED',verified_at=self.at,source='Synthetic subscriber',audience_at=self.at-timedelta(minutes=i),
                    last_paid_at=self.at-timedelta(days=120),order_count=1,lifetime_value=100,currency='AUD',suppressed=False,
                    flow_state=None,enrollment_id=None,stage=None,last_email=None,next_due_at=None,order_name='#Fixture'+str(i),
                    financial_status='PAID',fulfillment_status='UNFULFILLED',sends=[],steps=[],reference='#Fixture'+str(i))
            values.append(r)
        if search:values=[r for r in values if search.lower() in str(r).lower()]
        if after:values=[r for r in values if (r['created_at'],r['checkout_key'])<(date(after[0]),after[1])]
        if kwargs.get('start') and kwargs['start']>self.at:values=[]
        self.samples.append(round((perf_counter()-start)*1000,2))
        return values[page*50:page*50+page_size]
if 'fixture-backend' not in st.session_state:st.session_state['fixture-backend']=Backend()
backend=st.session_state['fixture-backend']
flow=new_flow(kind) if kind in ('abandoned','fulfilled') else expanded_flow(kind)
steps=flow['emails']
row=dict(id='fixture-'+kind,name=kind,trigger_type=kind,status='ACTIVE',updated_at=1,
    config=dict(draft=flow,published_flow=flow,published_version=1))
store=Mock();store.connect='synthetic-'+kind
store.q.return_value=[];store.suppressed.return_value=False
store.send.side_effect=AssertionError('Delivery forbidden')
store.request_publish.side_effect=AssertionError('Activation forbidden')
store.retry_delivery.side_effect=AssertionError('Delivery forbidden')
checkout.checkouts=lambda store,identity,bounds,**kw:backend.rows(store,**kw)
lifecycle.listing=backend.rows
import crm_native_audience
crm_native_audience.listing=backend.rows
lifecycle.customer_preview=lambda *a,**k:dict(eligible=False,reason='Synthetic detail only',stages=[],orders=[])
if kind=='abandoned':checkouts(Mock(),store,{'role':'admin'},row)
else:lifecycle.audience(store,{'role':'admin'},row)
@st.fragment(run_every=1)
def counters():
    import json
    st.text('FIXTURE_METRICS '+json.dumps(dict(reads=backend.calls,samples=backend.samples,state={k:str(v) for k,v in st.session_state.items() if 'search' in k})))
counters()

if st.query_params.get('fail')=='1' and st.button('Restore fixture reads'):backend.fail=False
