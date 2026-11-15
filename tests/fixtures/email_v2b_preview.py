"""Local browser proof: real controller/component + disposable SQL + fabricated IMAP/SMTP."""
import sys, os, uuid
from pathlib import Path
from unittest.mock import patch, Mock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
if os.getenv('EMAIL_V2B_BASELINE')=='1':sys.path.insert(0,str(ROOT/'tmp/email-v2b-before'))
import streamlit as st
from tests.test_email_inbox_reliability import Provider
from tests.email_v2_fixtures import CONFIG, USER, fixture_smtp
from tests.test_email_durable_delivery import Connection
from support_email_reads import ReadService, AsyncInbox
from support_email_workspace import Workspace
from support_email_durable import MailStore, DurableRegistry
from support_email_compose import default_settings
from support_email_smtp import SMTPConfiguration
import support_email_page as page

class PrivacyProvider(Provider):
    def read_message(self, message):
        body=super().read_message(message)
        uid=message['uid']
        origin='https://127.0.0.1:8844'
        body['html']=f'''<h2>Private synthetic message {uid}</h2><p>Safe text, link and inline logo.</p>
        <img src="cid:logo" alt="Inline logo"><img src="{origin}/image/{uid}" alt="Product image">
        <img src="{origin}/pixel/{uid}" width="1" height="1" alt="">
        <img srcset="{origin}/responsive/{uid} 1x, {origin}/unwanted/{uid} 2x" alt="Responsive image">
        <div style="background:url({origin}/css/{uid});color:#123">Styled text</div>
        <link rel="stylesheet" href="{origin}/stylesheet/{uid}"><style>@import url({origin}/import/{uid});</style>
        <svg><image href="{origin}/svg/{uid}"/></svg><video poster="{origin}/poster/{uid}"></video>
        <iframe src="{origin}/frame/{uid}"></iframe><object data="{origin}/object/{uid}"></object>
        <script>fetch('{origin}/script/{uid}')</script><img src="http://127.0.0.1:8843/insecure/{uid}">
        <a href="{origin}/link/{uid}" ping="{origin}/ping/{uid}">Deliberate link</a>'''
        body['inline_images']={'logo':'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII='}
        return body

class DraftStore(MailStore):
    def save_draft(self, mailbox, actor, draft):
        if draft.get('subject')=='SIMULATED SAVE FAILURE':raise OSError('Synthetic storage interruption')
        return super().save_draft(mailbox,actor,draft)

st.set_page_config(layout='wide',page_title='Phase 2B synthetic verification')
@st.cache_resource
def reads():
    store=Mock();store.read_index.return_value={}
    return ReadService(PrivacyProvider(75),store)
if 'v2a_user' not in st.session_state:
    st.session_state.v2a_user=dict(USER,id=str(st.query_params.get('actor') or uuid.uuid4()))
def factory(state,user,cfg,smtp):
    return Workspace(state,user,cfg,smtp,imap=AsyncInbox(cfg,reads()),smtp=fixture_smtp(),
        registry=DurableRegistry(DraftStore(connect=Connection)))
for p in (patch.object(page,'Workspace',factory),patch.object(page,'load_configuration',return_value=CONFIG),
          patch.object(page,'load_smtp_configuration',return_value=SMTPConfiguration(password='fixture')),
          patch('support_email_store.load_email_settings',return_value=(default_settings(),None)),
          patch('support_email_store.audit'),patch('support_email_store.load_metadata',return_value={}),
          patch('supabase_backend.connect',side_effect=AssertionError('Production database blocked')),
          patch('support_email_provider.imaplib.IMAP4_SSL',side_effect=AssertionError('Real IMAP blocked')),
          patch('support_email_smtp.smtplib.SMTP_SSL',side_effect=AssertionError('Real SMTP blocked'))):p.start()
st.session_state.current_page='Email'
page.render_page(st.session_state.v2a_user)
