"""Offline Campaigns V2 browser fixture. All records use disposable loopback SQL."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
from unittest.mock import patch
import uuid
from threading import Timer
import streamlit as st
from crm_campaign_store import CampaignStore
from crm_campaign_send import review,queue_campaign
from crm_campaign_page import open_editor
from crm_campaign_attribution import record
from crm_page import render_page
from crm_resend import Config
from crm_logic import now
from crm_webhooks import receive_resend
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG,ENV,LIVE
from tests.test_crm_campaign_v2 import authority,profile
from tests.test_crm_production_v2 import order_fixture

@st.cache_resource
def isolate_fixture_process():
    # Fragment reruns execute after the script's context managers have exited.
    # Keep outbound I/O blocked and fixture settings stable for that entire process.
    guards=[patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')),
            patch('supabase_backend.connect',side_effect=AssertionError('Production DB forbidden')),
            patch('crm_service.audit'),patch.object(CampaignStore,'render_settings',return_value=deepcopy(CFG)),
            patch.dict('os.environ',{**ENV,'CRM_MARKETING_ENABLED':'false','CRM_MARKETING_SEND_ENABLED':'false'})]
    for guard in guards:guard.start()
    return guards

isolate_fixture_process()

@st.cache_resource
def preview_shop():
    shop=authority([profile(8801),profile(8802),profile(8803)])
    shop.campaign_segment_counts.return_value={'AU':3,'Global':3,'US':0,'UK':0,'CA':0,'NZ':0}
    return shop

st.set_page_config(layout='wide',page_title='Campaigns V2 · offline fixture')
st.sidebar.caption('Offline fixtures · no live delivery or Shopify writes')
store=CampaignStore(connect)
shop=preview_shop()
if st.sidebar.button('Simulate subscriber in 15 seconds'):
    def subscribe():
        from crm_webhooks import receive_shopify
        counts=dict(shop.campaign_segment_counts.return_value)
        counts['AU']+=1;counts['Global']+=1
        shop.campaign_segment_counts.return_value=counts
        receive_shopify(store,'customers/update','fixture-'+uuid.uuid4().hex,{'id':8804},now())
    timer=Timer(15,subscribe);timer.daemon=True;timer.start()
with (patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')),
      patch('supabase_backend.connect',side_effect=AssertionError('Production DB forbidden')),
      patch('crm_service.audit'),patch.object(CampaignStore,'render_settings',return_value=deepcopy(CFG)),
      patch.dict('os.environ',{**ENV,'CRM_MARKETING_ENABLED':'false','CRM_MARKETING_SEND_ENABLED':'false'})):
    if not st.session_state.get('v2_seeded'):
        store.seed()
        for name in ('Australia · Collector launch','Australia · New arrivals'):
            base=int(str(uuid.uuid4().int)[:10]);seed_shop=authority([profile(base+i) for i in range(3)])
            doc=document();doc['market_audience']=True
            row=store.save(ADMIN,name,doc)
            snapshot=review(seed_shop,store,row,LIVE)
            queue_campaign(seed_shop,store,ADMIN,row,str(uuid.uuid4()),env=LIVE,snapshot_id=snapshot['snapshot_id'])
            sends=store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(row['id'],))
            for i,send in enumerate(sends):
                provider=str(uuid.uuid4())
                store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',provider_email_id=%s,first_submitted_at=now() WHERE id=%s",(provider,send['id']))
                for event in (['email.sent','email.delivered','email.opened','email.clicked'] if i==0 else ['email.sent','email.delivered']):
                    receive_resend(store,'fixture_'+uuid.uuid4().hex,{'type':event,'created_at':now().isoformat(),'data':{'email_id':provider}})
            store.q("UPDATE crm_campaigns SET status='SENT',sent_at=now() WHERE id=%s",(row['id'],))
            from crm_tracking import send_identity
            record(store,order_fixture(send_identity(row['id']),sends[0]['shopify_customer_id']))
        draft=store.save(ADMIN,'Australia · Spring collectors',document())
        st.session_state['v2_draft']=draft;st.session_state['v2_seeded']=True
        open_editor(draft)
    render_page('CRM Campaigns',ADMIN,shop=shop,store=store,config=Config({}))
