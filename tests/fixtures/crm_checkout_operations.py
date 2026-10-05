"""Synthetic isolated UI only. No production store, Shopify, worker or transport."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock,patch
import streamlit as st
from crm_logic import now
from datetime import timedelta
import crm_automation_analytics_ui as ui

st.set_page_config(layout='wide')
row={'id':'fixture','status':'ACTIVE','steps':[{}],'config':{'published':{'abandonment_seconds':1800}},'trigger_type':'abandoned'}
records=st.session_state.setdefault('fixture_rows',[
    {'checkout_key':str(i),'admin_checkout_id':'gid://shopify/AbandonedCheckout/'+str(100+i),
     'created_at':now()-timedelta(days=4),'activity_at':now()-timedelta(days=4),'status':'ABANDONED',
     'customer_id':'gid://shopify/Customer/'+str(i),'analytics':{'name':name,'email':f'fixture{i}@example.test','region':region,'reference':'#'+str(100+i)},
     'sends':[{'step':0,'status':'ACCEPTED','provider_id':'fixture','error':''}] if i==1 else [],
     'order_id':'gid://shopify/Order/99' if i==2 else None,'enrollment_id':None}
    for i,(name,region) in enumerate([('Joanne Lawrence','Australia'),('Brian Albers','United States'),('Guest Collector','Canada')])])
store=Mock();store.connect='fixture';store.suppressed.return_value=False
def add(shop,store,user,identity,checkout_id):
    c=next(c for c in records if c['admin_checkout_id']==checkout_id)
    c['enrollment_id']='persistent-fixture-'+c['checkout_key']
    c.update(flow_status='ACTIVE',next_due_at=now()+timedelta(minutes=78),current_step=0,steps=[{}])
    return {'id':c['enrollment_id']}
@st.dialog('Automation analytics',width='large')
def page():
    with patch.object(ui,'read',return_value=(records,'READY')),patch.object(ui,'add_to_flow',side_effect=add):
        ui.checkout_panel(Mock(),store,{},row,(None,now()),'All time')
page()
