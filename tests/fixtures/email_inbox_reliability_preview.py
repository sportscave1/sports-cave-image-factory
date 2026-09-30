"""Offline Inbox with real async controller and fabricated delayed mail only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import time
import json
from unittest.mock import Mock,patch
import streamlit as st
from support_email_reads import ReadService
from support_email_provider import MailboxError
from support_email_compose import default_settings
from support_email_smtp import SMTPConfiguration
from tests.test_email_inbox_reliability import Provider
from tests.email_v2_fixtures import CONFIG,USER,fixture_smtp
import support_email_page

class SlowMail(Provider):
    def list_headers(self,*a,**kw):
        time.sleep(.5)
        if self.fail:raise MailboxError('Fixture network timeout',code='timeout',retryable=True)
        return super().list_headers(*a,**kw)
    def live_changes(self,*a,**kw):
        time.sleep(.2)
        if self.fail:raise MailboxError('Fixture network timeout',code='timeout',retryable=True)
        return super().live_changes(*a,**kw)
    def read_message(self,*a,**kw):
        time.sleep(.8)
        if self.fail:raise MailboxError('Fixture network timeout',code='timeout',retryable=True)
        return super().read_message(*a,**kw)

@st.cache_resource
def fixture(mode):
    mail=SlowMail(60)
    store=Mock();store.read_index.return_value={}
    reads = ReadService(mail,store)
    if mode == 'Cold persisted outage':
        from support_email_snapshot import encode, decode
        reads.sync()
        store.read_index.return_value = decode(json.loads(encode(reads.value)))
        reads.close()
        reads = ReadService(mail, store)
    mail.fail = mode != 'Healthy'
    return reads

st.set_page_config(layout='wide',page_title='Inbox reliability · offline fixture')
st.html('<style>[data-testid="stHeader"]{display:none}</style>')
st.sidebar.caption('OFFLINE FIXTURE · no live mailbox or database')
mode=st.sidebar.selectbox('Startup fixture', ['Healthy', 'Cold persisted outage', 'Cold empty outage'])
if st.session_state.get('fixture_mode') != mode:
    st.session_state.pop('support_email_workspace', None)
    st.session_state['fixture_mode'] = mode
reads=fixture(mode)
outage=st.sidebar.checkbox('Simulate mailbox outage',value=mode!='Healthy',key='outage-'+mode)
if outage!=reads.provider.fail:
    reads.provider.fail=outage;reads.refresh()
st.sidebar.caption('500 ms headers · 800 ms message body')
for stub in (patch('support_email_reads.service',return_value=reads),
      patch('support_email_page.load_configuration',return_value=CONFIG),
      patch('support_email_page.load_smtp_configuration',return_value=SMTPConfiguration(password='fixture')),
      patch('support_email_workspace.SMTPProvider',return_value=fixture_smtp()),
      patch('support_email_store.load_email_settings',return_value=(default_settings(),None)),
      patch('support_email_store.load_metadata',return_value={}),
      patch('support_email_store.audit'),
      patch('support_email_store.load_orders',return_value=[])):
    stub.start()  # Streamlit fragment reruns execute outside the outer fixture.
support_email_page.render_page(USER)
