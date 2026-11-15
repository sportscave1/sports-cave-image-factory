"""Local UI acceptance harness. Every mailbox, SMTP, database and audit operation is mocked.

Run: .venv/Scripts/python.exe -m streamlit run tests/fixtures/email_desktop_preview.py --server.port 8503
"""
from pathlib import Path
import sys
import time
import os
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
import streamlit.components.v1 as components
import support_email_provider as provider
import support_email_smtp as smtp
import support_email_store as store
from support_email_compose import default_settings
from support_email_page import get_component, email_shell_styles, rerun_email
from support_email_workspace import Workspace
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp, USER, WORKER, CONFIG, MAILBOX
from tests.test_support_email import order

st.set_page_config(page_title="Email V2.1 · Mock mailbox", layout="wide", initial_sidebar_state="expanded")
fixture_user = WORKER if st.query_params.get("account") == "staff" else USER
st.html('''<style>:root{--sc-topbar-height:64px}header[data-testid="stHeader"]{display:none}
.fixture-topbar{position:fixed;top:0;left:0;right:0;height:64px;padding:22px;z-index:99;background:#fcfbf8;border-bottom:1px solid #ddd;font:12px Arial;letter-spacing:2px}
section[data-testid="stSidebar"]{top:64px !important;height:calc(100dvh - 64px) !important}
</style><div class="fixture-topbar">SPORTS CAVE OS <span style="float:right;color:#888;letter-spacing:0">LOCAL MOCK MAILBOX · no external I/O</span></div>''')
with st.sidebar:
    st.caption("OPERATIONS · FIXTURE NAVIGATION")
    st.text("Home\n\nOrders\n\nFulfilment\n\nEmail\n\nEdition Ops")
email_shell_styles()
# Match the zero-height top-bar/navigation bridges in the actual OS page shell.
components.html('<script>/* fabricated top-bar bridge */</script>', height=0, width=0)


class DesktopMailbox(MailboxFixture):
    """Deliberately slow uncached reads and overflowing panes for local UI checks."""
    def __init__(self):
        super().__init__(75)
        self.folders.extend(provider.parse_folders([
            f'() "/" "Custom folder {n:02}"'.encode() for n in range(24)]))
        self.folders.reverse()  # UI must order INBOX ahead of the server's LIST order.

    def read_message(self, message):
        time.sleep(0.6)
        result = super().read_message(message)
        if message['uid'] == '75':
            result['text'] = result['text'].split('On Sunday,')[0] + '\n\n'.join(
                f'Fixture detail {n}: This longer message checks independent reading-pane scrolling.'
                for n in range(1, 32))
        return result

    def related_headers_many(self, folders, identifiers, limit=100):
        time.sleep(0.35)
        return super().related_headers_many(folders, identifiers, limit)


@st.fragment
def preview():
    if "fixture_mailbox" not in st.session_state:
        st.session_state.fixture_mailbox = DesktopMailbox()
        st.session_state.fixture_smtp = fixture_smtp()
        st.session_state.fixture_registry = smtp.SendRegistry()
        if os.environ.get('EMAIL_TEST_POSTGRES')=='1':
            from support_email_durable import DurableRegistry,MailStore
            from tests.test_email_durable_delivery import Connection
            st.session_state.fixture_registry=DurableRegistry(MailStore(connect=Connection))
        st.session_state.fixture_settings = default_settings()
    with (patch.object(provider.imaplib, "IMAP4_SSL", side_effect=AssertionError("Real IMAP forbidden")),
          patch.object(smtp.smtplib, "SMTP_SSL", side_effect=AssertionError("Real SMTP forbidden")),
          patch.object(store, "load_email_settings", return_value=(st.session_state.fixture_settings,None)),
          patch.object(store, "load_metadata", return_value={}),
          patch.object(store, "load_assignees", return_value=[USER,WORKER]),
          patch.object(store, "load_orders", return_value=[order(email="customer74@example.test")]),
          patch.object(store, "save_workflow"), patch.object(store, "save_email_preference"),
          patch.object(store, "audit"), patch.object(store, "save_email_settings") as save):
        state=st.session_state.setdefault("fixture_workspace",{})
        w=Workspace(state,fixture_user,CONFIG,smtp.SMTPConfiguration(password="fixture-only"),
                    imap=st.session_state.fixture_mailbox,smtp=st.session_state.fixture_smtp,registry=st.session_state.fixture_registry)
        if not state.get("loaded"):
            w.load()
            w.restore_draft()
        event=get_component()(model=w.model(),key="fixture-email",default=None)
        if event and w.handle(event):
            if save.called:
                st.session_state.fixture_settings.update({k:v for k,v in save.call_args.kwargs.items() if k in default_settings()})
            rerun_email()


with st.container(key="support-email-shell"):
    preview()
components.html('<script>/* fabricated navigation-complete bridge */</script>', height=0, width=0)
