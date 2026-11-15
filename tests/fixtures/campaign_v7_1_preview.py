"""Fail-closed synthetic Home/detail/dialog browser acceptance fixture."""
import sys,importlib.util
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from tests.test_crm import ADMIN
from tests.test_crm_campaign_home import record
from crm_campaign_progress import summarize
import crm_campaign_progress_ui as detail
import crm_campaign_home as home
import crm_campaign_schedule as schedule
import requests
requests.sessions.Session.request=Mock(side_effect=AssertionError('External requests forbidden'))
fixture=Path('tests/sidebar_preview_app.py').resolve()
__file__=str(fixture)
exec(compile(fixture.read_text(encoding='utf-8').split('st.title(get_current_page())')[0],str(fixture),'exec'))
before=st.query_params.get('before')=='1'
if before:
    for name in ('crm_campaign_progress_ui','crm_campaign_home'):
        spec=importlib.util.spec_from_file_location(name+'_before',Path('tmp/campaign-v7-1-baseline')/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if name.endswith('ui'):detail=module
        else:home=module
identity='00000000-0000-0000-0000-000000000071'
timing={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-10','time':'17:00'}
receipt=st.session_state.get('fixture-receipt',{'timing':timing,'operation_id':'original'})
timing=receipt['timing'];stamp=receipt.get('due_at',datetime(2099,10,10,6,tzinfo=timezone.utc))
row=record();row.update(id=identity,name='V8 Supercars — Bathurst Race Feature',market='AU',status='SCHEDULED',delivery_status='SCHEDULED',template_id='fixture',template_version=1,recipients=1085)
progress=summarize({**row,'counts':{'PENDING':1085},'timing':timing,'scheduled_at':stamp,'next_due_at':stamp,'started':False,'updated_at':datetime.now(timezone.utc)})
if timing.get('mode')=='now':
    row.update(status='SENDING',delivery_status='SENDING')
    progress=summarize({**progress,'status':'SENDING','timing':timing,'next_due_at':stamp})
row['progress']=progress;row['deletable']=False;row['thumbnail']=''
class Store:
    connect=None
    def state(self,key):return receipt
    def q(self,*args,**kwargs):
        if kwargs.get('one'):return {'market':'AU','timing':timing}
        return [progress]
    def template(self,*args):return {'document':{'market':'AU','send_timing':timing},'render_settings':{}}
    def history(self,*args):return []
store=Store()
def change(store,user,identity,timing,operation_id,**kwargs):
    if timing['mode']=='now':st.session_state['fixture-now']=True
    result={'timing':timing,'operation_id':operation_id,'due_at':schedule.due(timing,'Australia/Sydney').isoformat() if timing['mode']=='schedule' else datetime.now(timezone.utc).isoformat()}
    st.session_state['fixture-receipt']=result
    return result
schedule.change_pending=change
if st.query_params.get('view','detail')=='home' or st.session_state.get('campaign_view')=='CAMPAIGNS_HOME':
    from concurrent.futures import Future
    def fixture_job(state,store,key,load):
        future=Future()
        value=[{**row,'in_page':True}] if key[0]=='table' else dict(all_count=1,drafts=0,active=1,sent=0,archived=0,sent_emails=0,click_rate=0.,bounce_rate=0.,orders=0)
        future.set_result(value)
        state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,future)
        return future
    home._job=fixture_job
    home.home(store,ADMIN)
else:
    import crm_email_diagnostics
    crm_email_diagnostics.campaign_status=lambda *args:None
    detail.operational_view(store,ADMIN,row)
