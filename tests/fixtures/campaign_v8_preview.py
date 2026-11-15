"""Synthetic scheduling UI, no credentials, provider or production database."""
from pathlib import Path
import sys,json,importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from unittest.mock import Mock
from crm_campaign_controls import timing_control
from crm_campaign_home import STYLE,row_html
from crm_campaign_progress import summarize
from crm_campaign_countdown import arm
from tests.test_crm_campaign_home import record
from tests.test_crm_campaign_v8 import timing
from crm_campaign_schedule import due
from crm_logic import now
st.set_page_config(layout='wide')
st.html(STYLE)
doc=st.session_state.setdefault('v8-doc',{'market':'AU','send_timing':{'mode':'now'}})
st.markdown('### Campaign scheduling')
if st.query_params.get('before')=='1':
    path=Path('tmp/campaign-v8-before/crm_campaign_controls.py')
    spec=importlib.util.spec_from_file_location('v8_before_controls',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    timing_control=module.timing_control
timing_control(doc,'fixture-')
st.html('<pre id="v8-contract">'+json.dumps(doc['send_timing'])+'</pre>')
row=record();row.update(name='Bathurst Race Feature — local fixture',market='AU',status=st.session_state.get('fixture-status','SCHEDULED'),delivery_status='SCHEDULED')
t=timing(day='2099-10-10');stamp=due(t,t['timezone'])
progress=summarize({'id':row['id'],'name':row['name'],'status':row['status'],'counts':{'PENDING':1085} if row['status']=='SCHEDULED' else {'ACCEPTED':1085},'timing':t,'scheduled_at':stamp,'next_due_at':stamp,'updated_at':now()})
row['progress']=progress
with st.container(key='crm-home-table'):st.html(row_html(row))
arm()
class PendingStore:
    def q(self,*args,**kwargs):return [progress]
    def template(self,*args):
        st.session_state['fixture-snapshot-reads']=st.session_state.get('fixture-snapshot-reads',0)+1
        return {'document':{'market':'AU','send_timing':t}}
    def state(self,key):return st.session_state.get('fixture-amendment',{'timing':t,'operation_id':'fixture-original'})
def fixture_change(store,user,identity,timing,operation_id,**kwargs):
    prior=store.state('')
    if prior.get('operation_id')!=operation_id:
        st.session_state['fixture-amendments']=st.session_state.get('fixture-amendments',0)+1
        st.session_state['fixture-amendment']={'timing':timing,'operation_id':operation_id}
    return store.state('')
import crm_campaign_schedule
crm_campaign_schedule.change_pending=fixture_change
from crm_campaign_timing_ui import pending_controls
from tests.test_crm import ADMIN
pending_controls(PendingStore(),ADMIN,{'id':row['id'],'status':'SCHEDULED','template_id':'fixture','template_version':1})
st.html('<pre id="v8-ui-counters">'+json.dumps({'snapshot_reads':st.session_state.get('fixture-snapshot-reads',0),'amendments':st.session_state.get('fixture-amendments',0)})+'</pre>')
if st.button('Fixture: complete'):
    st.session_state['fixture-status']='SENT';st.rerun()
st.caption('Synthetic fixture. No delivery or database requests.')
