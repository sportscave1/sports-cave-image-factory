"""Local SMTP/IMAP send UX scenarios, no external I/O. Streamlit port 8506."""
from pathlib import Path
import sys
import time
import uuid
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
import support_email_provider as provider
import support_email_smtp as smtp
import support_email_store as store
from support_email_compose import default_settings
from support_email_workspace import Workspace
from support_email_durable import DurableRegistry, MailStore
from tests.test_email_durable_delivery import Connection
from support_email_page import get_component, email_shell_styles, rerun_email
from tests.email_v2_fixtures import MailboxFixture, CONFIG, USER, WORKER


class SendMailbox(MailboxFixture):
    def __init__(self,scenario):
        super().__init__(3)
        self.scenario=scenario;self.accepted_at=0;self.message_id=''
        self.submissions=0;self.copy_attempts=0;self.raw=None

    def find_message_id(self,folder,message_id):
        self.calls.append(('verify',folder,message_id))
        if self.scenario in {'server','delayed'} and self.raw and not self.appended:
            delay=7 if self.scenario=='delayed' else 0
            if time.monotonic()-self.accepted_at>=delay:
                super().append_message(folder,self.raw)
        return super().find_message_id(folder,message_id)

    def append_message(self,folder,raw,**kwargs):
        self.copy_attempts+=1
        time.sleep(.4)
        if self.scenario=='copy_failure' and self.copy_attempts==1:
            raise provider.MailboxError('Fixture copy rejected',code='append_rejected')
        return super().append_message(folder,raw,**kwargs)

    def connection(self,*args,**kwargs):
        time.sleep(.3)
        mailbox=self
        class Connection:
            esmtp_features={}
            def set_debuglevel(self,value):pass
            def ehlo(self):return 250,b'ok'
            def login(self,*args):time.sleep(.3)
            def mail(self,*args,**kwargs):return 250,b'ok'
            def rcpt(self,*args):return 250,b'ok'
            def data(self,raw):
                mailbox.submissions+=1
                time.sleep(.5)
                if mailbox.scenario=='rejected':return 550,b'fixture refusal'
                if mailbox.scenario=='unknown':raise ConnectionResetError('fixture disconnect')
                mailbox.message_id=str(BytesParser(policy=policy.default).parsebytes(raw)['Message-ID'])
                mailbox.accepted_at=time.monotonic()
                mailbox.raw=raw
                return 250,b'accepted'
            def quit(self):pass
            def close(self):pass
        return Connection()


st.set_page_config(page_title='Email send UX · fixtures only',layout='wide')
email_shell_styles()
st.html('<style>[data-testid="stHeader"]{display:none}</style>')

@st.fragment
def preview():
    scenario=st.query_params.get('scenario','success')
    user=WORKER if st.query_params.get('account')=='staff' else USER
    state=st.session_state.setdefault('send_fixture',{})
    mailbox=st.session_state.setdefault('send_mailbox',SendMailbox(scenario))
    registry=st.session_state.setdefault('send_registry',DurableRegistry(MailStore(connect=Connection)))
    cfg=smtp.SMTPConfiguration(password='fixture-only')
    settings=default_settings()
    if scenario in {'server','delayed'}:settings['sent_policy']='server'
    with (patch.object(provider.imaplib,'IMAP4_SSL',side_effect=AssertionError('Real IMAP forbidden')),
          patch.object(smtp.smtplib,'SMTP_SSL',side_effect=AssertionError('Real SMTP forbidden')),
          patch.object(store,'load_email_settings',return_value=(settings,None)),
          patch.object(store,'load_metadata',return_value={}),patch.object(store,'load_orders',return_value=[]),
          patch.object(store,'load_assignees',return_value=[USER,WORKER]),patch.object(store,'audit')):
        w=Workspace(state,user,CONFIG,cfg,imap=mailbox,smtp=smtp.SMTPProvider(cfg,connection_factory=mailbox.connection),registry=registry)
        if not state.get('loaded'):
            w.load();w.handle({'id':str(uuid.uuid4()),'action':'compose','mode':'new'})
            state['draft'].update(to='john@example.test',subject='Local '+scenario+' send fixture',html='<p>Hi John,</p><p>This is a fabricated send verification.</p>')
        event=get_component()(model=w.model(),key='send-fixture',default=None)
        if event and w.handle(event):rerun_email()
        st.html(f'<div class="fixture-metrics" data-submissions="{mailbox.submissions}" data-copies="{mailbox.copy_attempts}"></div>')

with st.container(key='support-email-shell'):preview()
