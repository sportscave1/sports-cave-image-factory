"""Synthetic UI, delayed fake persistence/validation. Never connects or sends."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock,patch
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from time import sleep
import streamlit as st
from crm_logic import now
from datetime import timedelta
import crm_automation_analytics_ui as ui
import crm_checkout_enrollment_ui as enrollment_ui

st.set_page_config(layout='wide')
row={'id':'fixture','status':'ACTIVE','steps':[{}],'config':{'published':{'abandonment_seconds':1800}},'trigger_type':'abandoned'}

class Fixture:
    def __init__(self):
        self.lock=RLock();self.pool=ThreadPoolExecutor(max_workers=4);self.results={};self.attempts={}
        names=[('Joanne Lawrence','Australia'),('Brian Albers','United States'),('Guest Collector','Canada')]+[(f'Fixture {i}','Australia') for i in range(3,12)]
        self.records=[{'checkout_key':str(i),'admin_checkout_id':'gid://shopify/AbandonedCheckout/'+str(100+i),
            'created_at':now()-timedelta(days=4),'activity_at':now()-timedelta(days=4),'status':'ABANDONED',
            'customer_id':'gid://shopify/Customer/'+str(i),'analytics':{'name':name,'email':f'fixture{i}@example.test','region':region,'reference':'#'+str(100+i)},
            'sends':[{'step':0,'status':'ACCEPTED','provider_id':'fixture','error':''}] if i==1 else [],
            'order_id':'gid://shopify/Order/99' if i==2 else None,'enrollment_id':None}
            for i,(name,region) in enumerate(names)]
    def request(self,keys):
        sleep(.15)
        with self.lock:
            for k in keys:
                if self.results.get(k,{}).get('state') in ('QUEUED','CHECKING'):continue
                c=self.records[int(k)]
                reason='Recovered' if c['order_id'] else 'Already in flow' if c['enrollment_id'] else None
                self.results[k]={'checkout_key':k,'requested_at':now().isoformat(),'state':'DONE' if reason else 'QUEUED','result':reason or 'Adding…'}
                if not reason:self.pool.submit(self.validate,k)
            return deepcopy([self.results[k] for k in keys])
    def validate(self,k):
        sleep(.1)
        with self.lock:self.results[k].update(state='CHECKING',result='Checking eligibility…')
        sleep(7 if k=='3' else 2.5)
        with self.lock:
            self.attempts[k]=self.attempts.get(k,0)+1
            reason={'5':'Unsubscribed','6':'Suppressed'}.get(k)
            if k=='4' and self.attempts[k]==1:reason='Failed — Shopify unavailable'
            self.results[k].update(state='FAILED' if reason and reason.startswith('Failed') else 'DONE',result=reason or 'Added to flow')
            if not reason:self.records[int(k)].update(enrollment_id='fixture-'+k,flow_status='ACTIVE',next_due_at=now()+timedelta(minutes=78),current_step=0,steps=[{}])
    def read(self,store,key,fn,ttl=180):
        with self.lock:
            if key[0]=='checkout-list':return deepcopy(self.records),'READY'
            return [dict(deepcopy(self.records[int(k)]),request=deepcopy(self.results[k])) for k in key[2] if k in self.results],'READY'

if 'fixture_backend' not in st.session_state:st.session_state['fixture_backend']=Fixture()
fixture=st.session_state['fixture_backend']
store=Mock();store.connect='fixture';store.suppressed.return_value=False
@st.dialog('Automation analytics',width='large')
def page():
    st.session_state['checkout-enrollment-pending']=False
    with patch.object(ui,'read',side_effect=fixture.read),patch.object(enrollment_ui,'submit',side_effect=lambda s,u,i,k:fixture.pool.submit(fixture.request,k)):
        ui.checkout_panel(Mock(),store,{},row,(None,now()),'All time')
    if st.session_state.get('checkout-enrollment-pending'):ui.arm('fixture-enrollment-poll',2)
page()
