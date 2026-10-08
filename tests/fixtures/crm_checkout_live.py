"""Local Streamlit fragment and real read cache, synthetic checkout snapshots only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from datetime import timedelta
from time import monotonic,sleep
from unittest.mock import Mock
import streamlit as st
from crm_logic import now,date
import crm_automation_analytics_ui as ui
from crm_flow_page import checkouts

st.set_page_config(layout='wide')
st.session_state['fixture_full_runs']=st.session_state.get('fixture_full_runs',0)+1
st.caption('Full page runs: '+str(st.session_state['fixture_full_runs']))

class Backend:
    def __init__(self):self.started=monotonic();self.calls=0;self.at=now()
    def read(self,store,identity,bounds,key=None,*,page_size=51,after=None,search=''):
        self.calls+=1;sleep(.02)
        sent=monotonic()-self.started>=5
        rows=[{'checkout_key':'checkout-'+str(i),'admin_checkout_id':'fixture-'+str(i),
               'created_at':self.at-timedelta(minutes=i),'activity_at':self.at,'read_at':now(),
               'analytics':{'name':'Customer '+chr(65+i%26)+' '+str(i),'email':f'fixture{i}@example.test','shopify_abandoned':True},
               'automation_status':'ACTIVE','steps':steps,'published_steps':steps,'enrollment_id':'journey-'+str(i),
               'flow_status':'ACTIVE','current_step':1 if sent else 0,
               'next_due_at':self.at+timedelta(seconds=7200 if sent else 600),
               'sends':[{'step':0,'enrollment_id':'journey-'+str(i),'status':'ACCEPTED','provider_id':'fixture-receipt-'+str(i)}] if sent else []}
              for i in range(120)]
        if search:rows=[r for r in rows if search.casefold() in (r['analytics']['name']+' '+r['analytics']['email']).casefold()]
        if after:rows=[r for r in rows if (r['created_at'],r['checkout_key'])<(date(after[0]),after[1])]
        return rows[:page_size]

steps=[{'step_id':str(i),'name':'Published email '+str(i+1),'enabled':True} for i in range(5)]
if 'fixture_live_backend' not in st.session_state:st.session_state['fixture_live_backend']=Backend()
backend=st.session_state['fixture_live_backend']
ui.checkouts=backend.read
store=Mock();store.connect='fixture-live';store.suppressed.return_value=False
row={'id':'fixture-live','status':'ACTIVE','steps':steps,'config':{'published_flow':{'emails':steps}},'trigger_type':'abandoned'}
checkouts(Mock(),store,{'role':'admin'},row)
