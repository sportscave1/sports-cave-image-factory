"""Deterministic offline send UX. Memory-only worker simulation; no external I/O."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch
import time
import uuid
import streamlit as st
from crm_campaign_send_ui import review_dialog
from crm_campaign_progress_ui import status_tray
from crm_campaign_page import recent_campaigns
from crm_campaign_review import identity
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from tests.test_crm_send_progress import ID

st.set_page_config(layout='wide')


class FixtureStore:
    def __init__(self): self.campaigns={};self.reads=0
    def rows(self):
        result=[]
        for key,item in self.campaigns.items():
            processed=min(4,int((time.monotonic()-item['started'])/5))
            result.append({'id':key,'name':item['name'],'status':'SENT' if processed==4 else 'SENDING',
                           'counts':{'ACCEPTED':processed,'PENDING':4-processed}})
        return result
    def q(self,*args,**kwargs): self.reads+=1;return self.rows()
    def history_counts(self):
        rows=self.rows();sent=sum(r['status']=='SENT' for r in rows)
        return {'active':len(rows)-sent,'sent':sent,'polling_active':sent<len(rows)}
    def list_drafts(self,*args,**kwargs):
        return [{'id':r['id'],'name':r['name'],'version':1,'status':'DRAFT','archived_at':None,
                 'last_tested_at':None,'delivery_status':r['status'],'schedule_error':None,
                 'document':{'market':'NZ'},'activity_at':'2026-10-01T10:00:00Z'}
                for r in self.rows() if r['status']!='SENT']


@st.cache_resource
def resources():
    store=FixtureStore()
    def queue(shop,unused,user,editor,operation,**kwargs):
        key=str(editor['id'])
        store.campaigns.setdefault(key,{'name':editor['name'],'started':time.monotonic()})
        return {'id':key,'status':'SENDING','already_started':False,'recipients':4}
    def start(previous,shop,store,user,editor,saved,cfg):
        f=Future();f.set_result({'counts':{'eligible':4,'excluded':{}},'blockers':[],
            'snapshot_id':'offline','tracking_ok':True,'email_size':{'html_kb':13.6,'status':'SAFE'}})
        return SimpleNamespace(future=f,closed=False,applied=False,editor=deepcopy(editor),identity=identity(editor))
    patches=[patch('crm_campaign_send_ui.queue_campaign',side_effect=queue),
             patch('crm_campaign_review.start_review',side_effect=start),
             patch('crm_campaign_send_ui.get_resend_marketing_config_status',return_value={'marketing_enabled':True,'sender':'Sports Cave <offline@example.test>','reply_to':'offline@example.test'}),
             patch('crm_preview_cache.preview',return_value={'html':'<body style="background:#faf7ed;padding:16px;font-family:Arial"><h2>SPORTS CAVE</h2><h3>Collector edition</h3><p>Deterministic offline preview</p></body>'}),
             patch('crm_campaign_analytics_ui._sent_table',side_effect=lambda *a:st.caption('Sent · '+str(store.history_counts()['sent'])+' campaign(s)')),
             patch('requests.sessions.Session.request',side_effect=AssertionError('No external HTTP allowed'))]
    for item in patches:item.start()
    return store,patches

store,_=resources()
if 'campaign_editor' not in st.session_state:
    doc=document();doc['market']='NZ'
    st.session_state['campaign_editor']={'id':ID,'version':1,'name':'Ryan Fox — collector spotlight','document':doc,'archived_at':None,'status':'DRAFT'}
    st.session_state['campaign_saved']=deepcopy(st.session_state['campaign_editor'])
st.session_state['composer_runs']=st.session_state.get('composer_runs',0)+1
editor=st.session_state['campaign_editor']
st.markdown('### '+('New Campaign · DRAFT' if not editor['id'] else editor['name']))
editor['document']['content']['subject']=st.text_input('Subject',editor['document']['content']['subject'])
st.caption('Composer renders: '+str(st.session_state['composer_runs']))
if st.button('Review & send'):
    if editor['id'] is None:
        editor['id']=str(uuid.uuid4());editor['version']=1
        editor['name']='Second collector campaign'
    review_dialog(None,store,{},editor,'fixture_'+str(editor['id'])+'_',CFG)
recent_campaigns(store,'fixture_',{})
status_tray(store)
