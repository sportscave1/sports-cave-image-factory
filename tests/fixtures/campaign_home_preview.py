"""Synthetic local visual fixture. No network, production storage or transport."""
from pathlib import Path
import sys
from concurrent.futures import Future
from time import sleep
from crm_campaign_home_cache import job as cached_job
from crm_store import StoreUnavailable
from crm_campaign_home_data import invalidate
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from tests.test_crm_campaign_home import record,ID
from tests.test_crm_simple_editor import document
from tests.test_crm import ADMIN
from crm_campaign_content import settings
from crm_campaign_page import campaign_workspace

fixture=Path(__file__).resolve().parents[1]/'sidebar_preview_app.py'
__file__=str(fixture)
exec(compile(fixture.read_text(encoding='utf-8').split('st.title(get_current_page())')[0],str(fixture),'exec'))
items=[]
for i,(name,status,market) in enumerate((('Ryan Fox Open Championship — Product Spotlight','SENT','NZ'),
  ('Shane Warne Tribute Launch','SENT','AU'),('Father’s Day Collection','DRAFT','NZ'),('The Ashes Collection','DRAFT','AU'))):
    row=record();row.update(id='00000000-0000-0000-0000-'+str(i+1).zfill(12),name=name,market=market,status=status)
    row['thumbnail']='';row['subject']='Local visual fixture · collector campaign'
    if status=='SENT':row.update(delivery_status='SENT',sent_at=row['updated_at'],recipients=4,delivered=4,opens=2,clicks=1,orders=1,revenue={'NZD':'125'},delivery_rate=100.,open_rate=50.,click_rate=25.)
    items.append(row)
store=Mock();store.connect=None;store.q.return_value=None;store.render_settings.return_value=settings({})
store.setting.return_value={'value':{'smart_hours':16}};store.default_sections.return_value=[]
store.draft.side_effect=lambda identity:{'id':identity,'name':next(r['name'] for r in items if r['id']==identity),'document':document(),'status':'DRAFT','version':1,'archived_at':None}
mode=st.query_params.get('mode','normal')
def job(state,store,key,load):
    # Captured test values only; background loaders never access Streamlit state.
    outage=bool(state.get('fixture_delivery_outage'))
    if key[0] in ('counts','delivery','attribution'):
        value=dict(all_count=4,drafts=2,active=0,sent=2,archived=0,sent_emails=8,revenue={'NZD':'250'},orders=2,click_rate=25.)
    else:
        tab,search,market,status,sort=key[1]
        page=[r for r in items if (tab=='All campaigns' or tab==('Sent' if r['status']=='SENT' else 'Drafts')) and search.casefold() in r['name'].casefold() and (market=='All' or market==r['market'])]
        value=[{**r,'in_page':True} for r in page]
    if mode=='slow':
        def read():
            sleep({'counts':.5,'delivery':1.4,'attribution':2.2,'table':.8}[key[0]])
            if outage and key[0]=='delivery':raise StoreUnavailable('Private fixture diagnostic')
            return value
        return cached_job(state,store,key,read)
    f=Future();state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,f)
    f.set_result(value)
    return f
# Fragment reruns occur after the script returns. Fixture dependencies therefore
# stay installed for the lifetime of this dedicated preview process.
import crm_campaign_home,crm_campaign_page,requests
crm_campaign_home._job=job
crm_campaign_page.CampaignStore=lambda _:store
crm_campaign_page.activate=Mock()
requests.sessions.Session.request=Mock(side_effect=AssertionError('No external requests'))
campaign_workspace(Mock(),Mock(),Mock(user=ADMIN))

if mode=='slow' and st.button('Simulate delivery outage',key='fixture_outage'):
    st.session_state['fixture_delivery_outage']=True
    invalidate(st.session_state)
    st.rerun()
