"""Fail-closed synthetic Home/detail/dialog browser acceptance fixture."""
import sys,importlib.util,os,time
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import Mock
sys.path.insert(0,os.environ.get('CAMPAIGN_SOURCE_ROOT',str(Path(__file__).resolve().parents[2])))
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
# Exercise the seconds display without moving the campaign's business clock.
if st.query_params.get('countdown_probe')=='1':
    import crm_campaign_countdown
    from datetime import timedelta
    from crm_logic import date
    real_markup=crm_campaign_countdown.markup
    # Streamlit reruns reuse imports; keep the original function once.
    original=getattr(crm_campaign_countdown,'_fixture_original_markup',real_markup)
    crm_campaign_countdown._fixture_original_markup=original
    crm_campaign_countdown.markup=lambda instant,server_now=None:original(instant,server_now=date(instant)-timedelta(minutes=5))
else:
    import crm_campaign_countdown
    if hasattr(crm_campaign_countdown,'_fixture_original_markup'):
        crm_campaign_countdown.markup=crm_campaign_countdown._fixture_original_markup
before=st.query_params.get('before') in ('1','hardening')
if before:
    for name in ('crm_campaign_progress_ui','crm_campaign_home'):
        spec=importlib.util.spec_from_file_location(name+'_before',Path('tmp/campaign-hardening-before' if st.query_params.get('before')=='hardening' else 'tmp/campaign-v7-1-baseline')/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if name.endswith('ui'):detail=module
        else:home=module
identity=os.environ.get('CAMPAIGN_TEST_ID','00000000-0000-0000-0000-000000000071')
timing={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-10','time':'17:00'}
receipt=st.session_state.get('fixture-receipt',{'timing':timing,'operation_id':'original'})
timing=receipt['timing'];stamp=receipt.get('due_at',datetime(2099,10,10,6,tzinfo=timezone.utc))
row=record();row.update(id=identity,name='V8 Supercars — Bathurst Race Feature',market='AU',status='SCHEDULED',delivery_status='SCHEDULED',template_id='fixture',template_version=1,recipients=1085)
progress=summarize({**row,'counts':{'PENDING':1085},'timing':timing,'scheduled_at':stamp,'next_due_at':stamp,'started':False,'updated_at':datetime.now(timezone.utc)})
if timing.get('mode')=='now':
    row.update(status='SENDING',delivery_status='SENDING')
    progress=summarize({**progress,'status':'SENDING','timing':timing,'next_due_at':stamp})
row['progress']=progress;row['deletable']=False;row['thumbnail']=''
st.session_state.setdefault('fixture-counts',{'queries':0,'states':0,'templates':0,'amendments':0,'runs':0})
st.session_state['fixture-counts']['runs']+=1
counters=st.session_state['fixture-counts']
from crm_campaign_store import CampaignStore
class Store(CampaignStore):
    def __init__(self):pass
    connect=None
    def state(self,key):
        counters['states']+=1
        return receipt
    def q(self,*args,**kwargs):
        counters['queries']+=1
        time.sleep(float(os.environ.get('CAMPAIGN_QUERY_DELAY','0')))
        sql=args[0]
        if 'crm_workspace_settings' in sql:
            if 'ANY' in sql:return [{'key':'email_default_'+kind,'version':1,'value':{'html':''}} for kind in ('header','footer')]
            return None
        if sql.startswith('SELECT d.*'):return None
        if sql.startswith('SELECT * FROM crm_campaign_drafts'):
            from tests.test_crm_simple_editor import document
            return {**row,'document':document()}
        if sql.startswith(('SELECT c.id,c.name','SELECT * FROM crm_campaigns','SELECT 1 FROM crm_campaigns')):return row
        if kwargs.get('one'):return {'market':'AU','timing':timing}
        return [progress]
    def template(self,*args):
        counters['templates']+=1
        return {'document':{'market':'AU','send_timing':timing},'render_settings':{}}
    def history(self,*args):return []
store=Store()
if os.environ.get('CAMPAIGN_NATIVE_TEST')=='1':
    from tests.campaign_real_postgres import connect
    class NativeStore(CampaignStore):
        def q(self,*args,**kwargs):
            counters['queries']+=1
            return super().q(*args,**kwargs)
    store=NativeStore(connect)
def change(store,user,identity,timing,operation_id,**kwargs):
    st.session_state['fixture-counts']['amendments']+=1
    if timing['mode']=='now':st.session_state['fixture-now']=True
    result={'timing':timing,'operation_id':operation_id,'due_at':schedule.due(timing,'Australia/Sydney').isoformat() if timing['mode']=='schedule' else datetime.now(timezone.utc).isoformat()}
    st.session_state['fixture-receipt']=result
    return result
schedule.change_pending=change
if st.query_params.get('view','detail')=='home' or st.session_state.get('campaign_view')=='CAMPAIGNS_HOME':
    from concurrent.futures import Future
    def fixture_job(state,store,key,load,**kwargs):
        future=Future()
        value=[progress] if key[0]=='progress' else [{**row,'in_page':True}] if key[0]=='table' else dict(all_count=1,drafts=0,active=1,sent=0,archived=0,sent_emails=0,click_rate=0.,bounce_rate=0.,orders=0)
        future.set_result(value)
        state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,future)
        return future
    home._job=fixture_job
    import crm_campaign_home_progress
    crm_campaign_home_progress.job=fixture_job
    home.home(store,ADMIN)
else:
    import crm_email_diagnostics
    crm_email_diagnostics.campaign_status=lambda *args:None
    if st.query_params.get('view')=='workspace':
        from unittest.mock import patch
        from crm_campaign_page import campaign_workspace
        st.query_params['campaign']=identity
        st.session_state['campaign_view']='CAMPAIGN_EDITOR'
        with patch('crm_campaign_page.CampaignStore',return_value=store):
            campaign_workspace(Mock(),store,Mock(user=ADMIN))
    else:detail.operational_view(store,ADMIN,row)

import json
st.html('<pre id=hardening-counts style=display:none>'+json.dumps(st.session_state['fixture-counts'])+'</pre>')
