"""Local PostgreSQL only; production-shaped home and synthetic publication."""
from pathlib import Path
import sys,json,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from unittest.mock import Mock
from crm_store import Store
from contextlib import contextmanager
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from crm_automation_home import home,accepted_publication
from crm_automation_ui import changed
counters=st.session_state.setdefault('fixture_counters',{'queries':0})
failure=st.query_params.get('failure','')
class CountedStore(Store):
    @contextmanager
    def db(self):
        counters['queries']+=1
        with super().db() as connection:yield connection
    def q(self,sql,args=(),one=False):
        if (failure=='activity' and 'UNION ALL' in sql) or (failure=='counts' and 'count(*) AS all_count' in sql) or (failure=='metrics' and 'WITH page AS' in sql):
            raise ValueError('Synthetic private diagnostic')
        return super().q(sql,args,one)
store=CountedStore(connect)
identity='76784f53-7878-40cc-85e4-ba60c2ea835a'
case=st.query_params.get('case','Live')
if not st.session_state.get('seeded'):
    if case!='Existing':store.q('DELETE FROM crm_automations')
    if case not in ('Empty','Existing'):
        status='ACTIVE' if case=='Live' else 'DRAFT'
        config={'format':'automation_flow_v1','revision':39,'published_version':1,'published':{'flow':{'trigger':'abandoned'}}}
        if case in ('Publishing','Failed'):config['publication']={'job_id':'fixture-job','revision':39,'state':'PUBLISHING' if case=='Publishing' else 'FAILED','error':'Review the email HTML.'}
        store.q("INSERT INTO crm_automations(id,automation_key,name,status,trigger_type,config,steps) VALUES(%s,'loading-fixture','Abandoned Checkout — Reminder 1',%s,'abandoned',%s::jsonb,'[]'::jsonb)",(identity,status,json.dumps(config)))
    st.session_state['seeded']=True
if st.button('Fixture leave Automations'):st.session_state['fixture_away']=True
if st.session_state.get('fixture_away'):
    st.title('Lightweight fixture page')
    if st.button('Fixture return Automations'):
        st.session_state['fixture_away']=False;st.rerun()
    st.stop()
st.html('<div id="sc-os-search-results" role="listbox" hidden></div>')
if st.button('Fixture publish first automation'):
    job_id=str(uuid.uuid4())
    config={'format':'automation_flow_v1','revision':39,'publication':{'job_id':job_id,'revision':39,'state':'PUBLISHING'}}
    store.q("INSERT INTO crm_automations(id,automation_key,name,status,trigger_type,config,steps) VALUES(%s,'loading-fixture','Abandoned Checkout — Reminder 1','DRAFT','abandoned',%s::jsonb,'[]'::jsonb) ON CONFLICT(id) DO UPDATE SET config=excluded.config",(identity,json.dumps(config)))
    accepted_publication({'id':job_id,'automation_id':identity,'revision':39,'publication_version':1,'state':'QUEUED','snapshot':{'name':'Abandoned Checkout — Reminder 1','flow':{'trigger':'abandoned'}}})
    changed();st.rerun()
if st.button('Fixture complete publication'):
    store.q("UPDATE crm_automations SET status='ACTIVE',config=jsonb_set(config,'{publication,state}','\"LIVE\"') WHERE id=%s",(identity,))
if st.button('Fixture fail publication'):
    store.q("UPDATE crm_automations SET config=jsonb_set(config,'{publication,state}','\"FAILED\"') WHERE id=%s",(identity,))
home(Mock(),store,ADMIN)
st.caption('Fixture remains interactive')
from crm_automation_ui import home_state
state=home_state()
st.html('<pre id="fixture-publication">'+json.dumps({k:state.get(k) for k in ('publication_updates','publish_handoff','activity','visible_status_rows')},default=str)+'</pre>')
@st.fragment
def sample_counters():
    st.button('Fixture sample counters')
    st.html('<pre id="fixture-counters">'+json.dumps({**counters,'futures':len(state.get('campaign_home_cache',{})),'pending':sum(not e[1].done() for e in state.get('campaign_home_cache',{}).values())})+'</pre>')
sample_counters()
