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
st.html('''<span id="fixture-client-timings"></span><script>
(()=>{
  window.fixtureAcceptanceTimings??={};const t=window.fixtureAcceptanceTimings;
  const publish=()=>document.querySelector('#fixture-client-timings')?.setAttribute('data-timings',JSON.stringify(t));
  if(!window.fixtureAcceptanceObserver){
    document.addEventListener('click',e=>{
      const b=e.target.closest('button');if(!b)return;
      if(b.innerText==='Review & send')t.reviewClick=performance.now();
      if(b.closest('.st-key-crm-review-submit'))t.confirmClick=performance.now();publish();
    },true);
    window.fixtureAcceptanceObserver=new MutationObserver(()=>{
      const at=performance.now();
      if(document.querySelector('[role="dialog"]'))t.reviewVisible??=at;
      const submit=document.querySelector('.st-key-crm-review-submit button');
      if(submit&&!submit.disabled)t.reviewReady??=at;
      if(submit?.getAttribute('aria-busy')==='true')t.feedback??=at;
      if(t.confirmClick&&document.querySelector('.st-key-crm-home-table'))t.homeVisible??=at;
      if(t.confirmClick&&document.querySelector('.sc-col-status .sc-home-pill'))t.statusVisible??=at;
      publish();
    });
    window.fixtureAcceptanceObserver.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['aria-busy','disabled']});
  }publish();
})();</script>''',unsafe_allow_javascript=True)
class FixtureStore:
    connect=None
    def __init__(self):self.campaigns={};self.reads=0;self.queue_calls=0
    def progress(self):
        result=[]
        for key,item in self.campaigns.items():
            elapsed=time.monotonic()-item['started']
            processed=0 if elapsed<3 else 100 if elapsed<7 else 500 if elapsed<11 else 1095
            scheduled=item['timing'].get('mode')=='schedule'
            if scheduled:processed=0
            result.append({'id':key,'name':item['name'],'status':'PREPARING' if elapsed<3 else 'SCHEDULED' if scheduled else 'SENT' if processed==1095 else 'SENDING',
                'counts':{} if elapsed<3 else {'ACCEPTED':processed,'PENDING':1095-processed},'reviewed_total':1095,'updated_at':now(),
                'timing':item['timing'],'scheduled_at':item['due'],'next_due_at':item['due'],'server_now':now(),
                'last_progress_at':now(),'worker_started_at':now() if processed else None,'send_id':key})
        return result
    def q(self,*args,**kwargs):self.reads+=1;return self.progress()
    def listed(self):
        return [{**record(),'id':r['id'],'name':r['name'],'status':r['status'],'delivery_status':r['status'],
                 'subject':'Offline collector campaign','thumbnail':'','deletable':False,'recipients':1095,
                 'delivered':0,'opens':0,'clicks':0} for r in self.progress()]

@st.cache_resource
def resources(scope):
    store=FixtureStore()
    def queue(unused,user,editor,operation,**kwargs):
        store.queue_calls+=1
        key=str(editor['id'])
        from crm_campaign_schedule import due
        timing=editor['document'].get('send_timing',{'mode':'now'})
        instant=due(timing,timing.get('timezone') or 'Pacific/Auckland') if timing.get('mode')=='schedule' else None
        store.campaigns.setdefault(key,{'name':editor['name'],'started':time.monotonic(),'timing':deepcopy(timing),'due':instant})
        return {'id':key,'status':'PREPARING','already_started':False,'recipients':1095,'operation_id':operation}
    def start(previous,shop,store,user,editor,saved,cfg,audience_job=None):
        f=Future();f.set_result({'counts':{'eligible':1095,'excluded':{}},'blockers':[],
            'snapshot_id':'offline','tracking_ok':True,'email_size':{'html_kb':13.6,'status':'SAFE'}})
        return SimpleNamespace(future=f,closed=False,applied=False,editor=deepcopy(editor),identity=identity(editor))
    def home_job(state,store,key,load):
        def read():
            if key[0]=='table':return store.listed()
            if key[0]=='counts':return {'all_count':len(store.campaigns),'drafts':0,'active':sum(r['status'] in ('PREPARING','SENDING','SCHEDULED') for r in store.progress()),'sent':sum(r['status']=='SENT' for r in store.progress()),'archived':0}
            if key[0]=='delivery':return {'sent_emails':sum(r['counts'].get('ACCEPTED',0) for r in store.progress()),'click_rate':None,'bounce_rate':0.}
            return {'orders':0}
        return cached_job(state,store,key,read)
    patches=[patch('crm_campaign_preparation.accept',side_effect=queue),
             patch('crm_campaign_review.start_review',side_effect=start),
             patch('crm_campaign_home._job',side_effect=home_job),
             patch('crm_campaign_send_ui.get_resend_marketing_config_status',return_value={'marketing_enabled':True,'sender':'Sports Cave <offline@example.test>','reply_to':'offline@example.test'}),
             patch('crm_preview_cache.preview',return_value={'html':'<h3>Offline collector preview</h3>'}),
             patch('requests.sessions.Session.request',side_effect=AssertionError('No external HTTP'))]
    for item in patches:item.start()
    return store,patches
store,_=resources(st.query_params.get('case','default'))
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
    from crm_campaign_controls import timing_control
    timing_control(editor['document'],'fixture-timing-')
    st.session_state['campaign_saved']=deepcopy(editor)
    if st.button('Review & send'):review_dialog(None,store,{},editor,'fixture_',CFG)
