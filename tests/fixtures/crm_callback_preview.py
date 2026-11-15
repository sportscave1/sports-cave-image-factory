"""Loopback-only real SQL callback-to-Campaigns proof. No delivering transport."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uuid
import threading
import os
import streamlit as st
from crm_campaign_home import home
from crm_campaign_dispatch import dispatch
from crm_logic import now
from crm_webhooks import receive_resend
from crm_resend_event_worker import run_once
from tests.test_crm_batch_dispatch import DispatchTests
from tests.test_crm import ADMIN

if os.getenv('CRM_CALLBACK_BASELINE')=='1':
    import subprocess
    baseline={'__name__':'crm_callback_home_baseline'}
    exec(compile(subprocess.check_output(['git','show','HEAD:crm_campaign_home.py']).decode(),'<released-home>','exec'),baseline)
    home=baseline['home']

st.set_page_config(layout='wide')
@st.cache_resource
def resources():
    fixture=DispatchTests();fixture.setUp()
    identity=fixture.queue(1);dispatch(fixture.engine)
    fixture.store.q("UPDATE crm_campaigns SET status='SENT',sent_at=now() WHERE id=%s",(identity,))
    campaign=fixture.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
    return fixture,campaign,fixture.sends(identity)[0]['provider_email_id']

fixture,campaign,provider=resources()
st.session_state.setdefault('campaign_home_search',campaign['name'])
if st.button('Receive simulated delivered callback'):
    def arrive():
        receive_resend(fixture.store,'evt_'+uuid.uuid4().hex,{'type':'email.delivered',
            'created_at':now().isoformat(),'data':{'email_id':provider}},defer=True)
        assert run_once(fixture.store)==1
    # Receipt occurs after this interaction's render, proving passive polling.
    timer=threading.Timer(3,arrive);timer.daemon=True;timer.start()
home(fixture.store,ADMIN)
