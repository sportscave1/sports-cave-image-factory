"""Disposable Trash UI harness. All transports/storage are mocked; reload resets mail."""
from contextlib import ExitStack
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
import support_email_provider as provider
import support_email_smtp as smtp
import support_email_store as store
from support_email_compose import default_settings
from support_email_page import get_component, email_shell_styles, rerun_email
from support_email_workspace import Workspace
from tests.test_email_trash_delete import TrashMailbox
from tests.email_v2_fixtures import fixture_smtp, USER, CONFIG

st.set_page_config(page_title='Trash deletion · Disposable test mailbox', layout='wide')
st.html('<style>header[data-testid="stHeader"]{display:none}</style>')
st.caption('LOCAL DISPOSABLE MAILBOX · no external I/O · reload restores fixture messages')
email_shell_styles()


@st.fragment
def preview():
    if 'trash_fixture' not in st.session_state:
        mailbox = TrashMailbox()
        if st.query_params.get('scenario') == 'failure':
            mailbox.delete_error = RuntimeError('fixture-private-error')
        st.session_state.trash_fixture = mailbox
        st.session_state.trash_transport = fixture_smtp()
    with ExitStack() as stack:
        stack.enter_context(patch.object(provider.imaplib, 'IMAP4_SSL', side_effect=AssertionError('No real IMAP')))
        stack.enter_context(patch.object(smtp.smtplib, 'SMTP_SSL', side_effect=AssertionError('No real SMTP')))
        stack.enter_context(patch.object(store, 'load_email_settings', return_value=(default_settings(), None)))
        for name, value in [('load_metadata', {}), ('load_orders', []), ('load_assignees', []), ('audit', None)]:
            stack.enter_context(patch.object(store, name, return_value=value))
        state = st.session_state.setdefault('trash_workspace', {'folder': 'Trash'})
        w = Workspace(state, USER, CONFIG, smtp.SMTPConfiguration(password='fixture'),
                      imap=st.session_state.trash_fixture, smtp=st.session_state.trash_transport)
        if not state.get('loaded'):
            w.load()
        event = get_component()(model=w.model(), key='trash-fixture', default=None)
        if event and w.handle(event):
            rerun_email()


with st.container(key='support-email-shell'):
    preview()
