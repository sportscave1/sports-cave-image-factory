"""Loopback-only accepted-send navigation and live Home progress fixture."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch
import time
import streamlit as st
from crm_campaign_send_ui import review_dialog
from crm_campaign_review import identity
from crm_campaign_home import home
from crm_campaign_home_cache import job as cached_job
from crm_logic import now
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from tests.test_crm_send_progress import ID
from tests.test_crm_campaign_home import record

st.set_page_config(layout='wide')
class FixtureStore:
    connect=None
    def __init__(self):self.campaigns={};self.reads=0;self.queue_calls=0
    def progress(self):
        result=[]
        for key,item in self.campaigns.items():
            elapsed=time.monotonic()-item['started']
            processed=0 if elapsed<3 else 100 if elapsed<7 else 500 if elapsed<11 else 1095
            result.append({'id':key,'name':item['name'],'status':'SENT' if processed==1095 else 'SENDING',
                'counts':{'ACCEPTED':processed,'PENDING':1095-processed},'updated_at':now(),
                'last_progress_at':now(),'worker_started_at':now() if processed else None,'send_id':key})
        return result
    def q(self,*args,**kwargs):self.reads+=1;return self.progress()
    def listed(self):
        return [{**record(),'id':r['id'],'name':r['name'],'status':r['status'],'delivery_status':r['status'],
                 'subject':'Offline collector campaign','thumbnail':'','deletable':False,'recipients':1095,
                 'delivered':0,'opens':0,'clicks':0} for r in self.progress()]

@st.cache_resource
def resources():
    store=FixtureStore()
    def queue(shop,unused,user,editor,operation,**kwargs):
        store.queue_calls+=1
        key=str(editor['id'])
        store.campaigns.setdefault(key,{'name':editor['name'],'started':time.monotonic()})
        return {'id':key,'status':'SENDING','already_started':False,'recipients':1095}
    def start(previous,shop,store,user,editor,saved,cfg,audience_job=None):
        f=Future();f.set_result({'counts':{'eligible':1095,'excluded':{}},'blockers':[],
            'snapshot_id':'offline','tracking_ok':True,'email_size':{'html_kb':13.6,'status':'SAFE'}})
        return SimpleNamespace(future=f,closed=False,applied=False,editor=deepcopy(editor),identity=identity(editor))
    def home_job(state,store,key,load):
        def read():
            if key[0]=='table':return store.listed()
            if key[0]=='counts':return {'all_count':len(store.campaigns),'drafts':0,'active':sum(r['status']=='SENDING' for r in store.progress()),'sent':sum(r['status']=='SENT' for r in store.progress()),'archived':0}
            if key[0]=='delivery':return {'sent_emails':sum(r['counts']['ACCEPTED'] for r in store.progress()),'click_rate':None,'bounce_rate':0.}
            return {'orders':0}
        return cached_job(state,store,key,read)
    patches=[patch('crm_campaign_send_ui.queue_campaign',side_effect=queue),
             patch('crm_campaign_review.start_review',side_effect=start),
             patch('crm_campaign_home._job',side_effect=home_job),
             patch('crm_campaign_send_ui.get_resend_marketing_config_status',return_value={'marketing_enabled':True,'sender':'Sports Cave <offline@example.test>','reply_to':'offline@example.test'}),
             patch('crm_preview_cache.preview',return_value={'html':'<h3>Offline collector preview</h3>'}),
             patch('requests.sessions.Session.request',side_effect=AssertionError('No external HTTP'))]
    for item in patches:item.start()
    return store,patches
store,_=resources()
if 'campaign_editor' not in st.session_state and store.campaigns:
    st.session_state['campaign_view']='CAMPAIGNS_HOME'
if st.session_state.get('campaign_view')=='CAMPAIGNS_HOME':
    home(store,{})
    st.caption('Fixture accepted jobs: '+str(store.queue_calls))
else:
    if 'campaign_editor' not in st.session_state:
        doc=document();doc['market']='NZ'
        st.session_state['campaign_editor']={'id':ID,'version':1,'name':'Peter Brock collector edition','document':doc,'archived_at':None,'status':'DRAFT'}
        st.session_state['campaign_saved']=deepcopy(st.session_state['campaign_editor'])
    editor=st.session_state['campaign_editor']
    st.markdown('### '+editor['name'])
    if st.button('Review & send'):review_dialog(None,store,{},editor,'fixture_',CFG)
