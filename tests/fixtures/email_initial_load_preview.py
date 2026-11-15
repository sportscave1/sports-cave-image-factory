"""Offline navigation fixture. Mail is fabricated; CRM uses loopback PGlite only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import logging
import time
from unittest.mock import patch
import streamlit as st
import crm_page
import support_email_page
from crm_store import Store
from crm_shopify import Shopify
from crm_resend import Config
from support_email_compose import default_settings
from support_email_smtp import SMTPConfiguration
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
from tests.test_crm import ADMIN
from tests.email_v2_fixtures import MailboxFixture,fixture_smtp,CONFIG

logging.basicConfig(level=logging.INFO)
st.set_page_config(layout='wide',page_title='Email initial-load · offline fixture')
st.html('<style>header[data-testid="stHeader"]{display:none}</style>')
st.sidebar.caption('LOCAL FIXTURE · no live data')
route=st.sidebar.radio('Page',['Home','Inbox','Campaigns','Automations'])

class SlowMailbox(MailboxFixture):
    def list_headers(self,*args,**kwargs):
        time.sleep(.5)
        return super().list_headers(*args,**kwargs)
    def read_message(self,message):
        time.sleep(.5)
        return super().read_message(message)

mail=st.session_state.setdefault('fixture_mail',SlowMailbox(8))
store=Store(connect)
if not st.session_state.get('seeded'):
    store.seed();st.session_state['seeded']=True
@st.fragment
def inbox():
    with (patch('support_email_page.load_configuration',return_value=CONFIG),
          patch('support_email_page.load_smtp_configuration',return_value=SMTPConfiguration(password='fixture')),
          patch('support_email_workspace.ImapProvider',return_value=mail),
          patch('support_email_workspace.SMTPProvider',return_value=fixture_smtp()),
          patch('support_email_store.load_email_settings',return_value=(default_settings(),None)),
          patch('support_email_store.load_metadata',return_value={}),
          patch('support_email_store.audit'),
          patch('supabase_backend.connect',side_effect=AssertionError('Production DB forbidden'))):
        support_email_page._render_workspace.__wrapped__(ADMIN)

with (patch('crm_service.audit'),
      patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')),
      patch('supabase_backend.connect',side_effect=AssertionError('Production DB forbidden'))):
    if route=='Home':st.title('Home');st.caption('Offline navigation fixture')
    elif route=='Inbox':
        support_email_page.email_shell_styles()
        with st.container(key='support-email-shell'):inbox()
    else:crm_page.render_page('CRM '+route,ADMIN,shop=Shopify(ShopifyFixture()),store=store,config=Config({}))
