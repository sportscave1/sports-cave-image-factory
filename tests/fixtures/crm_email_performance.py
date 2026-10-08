"""Synthetic email workspace with query counters; never production services."""
import os,json,threading
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import streamlit as st
import requests
if os.getenv('EMAIL_PROFILE_BASELINE')=='1':
    import subprocess,sys,types
    if not getattr(sys,'_email_profile_baseline',False):
        for name in ('crm_preview_cache','crm_html_workspace','crm_campaign_home_data','crm_campaign_home','crm_campaign_recovery','crm_recovery_ui','crm_campaign_page','crm_email_size_ui'):
            source=subprocess.check_output(['git','show','2f6adbd:'+name+'.py'],text=True,encoding='utf-8')
            module=types.ModuleType(name);module.__file__=os.path.abspath(name+'.py');sys.modules[name]=module
            exec(compile(source,module.__file__,'exec'),module.__dict__)
        sys._email_profile_baseline=True
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from crm_campaign_store import CampaignStore
from crm_campaign_page import campaign_workspace

st.set_page_config(layout='wide')
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External I/O forbidden'))
CampaignStore.render_settings=lambda self,env=None:{**deepcopy(CFG),'email_defaults':self.default_sections(CFG)}

@st.cache_resource
def setup():
    store=CampaignStore(connect);store.seed()
    doc=document();doc['custom_html']='<p>Collector artwork</p>'*1500
    from crm_middle_sections import middle_sections,commit_middle
    commit_middle(doc,middle_sections(doc))
    if not store.q("SELECT id FROM crm_campaign_drafts WHERE created_by='email-performance-fixture' LIMIT 1"):
        store.q('''INSERT INTO crm_campaign_drafts(name,document,status,created_by)
          SELECT 'Performance campaign '||i,%s::jsonb,'DRAFT','email-performance-fixture' FROM generate_series(1,120) i''',(json.dumps(doc),))
    metrics={'queries':0,'defaults':0,'renders':0};lock=threading.Lock()
    from crm_store import Store
    original=Store.q
    def query(self,*args,**kwargs):
        with lock:metrics['queries']+=1
        return original(self,*args,**kwargs)
    Store.q=query
    original_defaults=CampaignStore.default_sections
    def defaults(self,*args,**kwargs):
        with lock:metrics['defaults']+=1
        return original_defaults(self,*args,**kwargs)
    CampaignStore.default_sections=defaults
    import crm_preview_cache
    original_render=crm_preview_cache.render_campaign
    def render(*args,**kwargs):
        with lock:metrics['renders']+=1
        return original_render(*args,**kwargs)
    crm_preview_cache.render_campaign=render
    return metrics

metrics=setup()
shop=Mock();shop.namespace='local-performance';shop.campaign_members.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
shop.segment_members.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
campaign_workspace(shop,CampaignStore(connect),SimpleNamespace(user=ADMIN))

@st.fragment
def counters():
    st.button('Profile snapshot')
    st.session_state['profile_tick']=st.session_state.get('profile_tick',0)+1
    st.html('<pre id="email-profile" style="white-space:pre-wrap;overflow-wrap:anywhere">'+json.dumps({**metrics,'snapshot':st.session_state['profile_tick']})+'</pre>')
counters()
