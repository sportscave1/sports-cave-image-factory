"""Local production-component recovery preview. All connections are fabricated."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
import streamlit as st
import support_email_provider as provider
import support_email_smtp as smtp
import support_email_store as store
from support_email_compose import default_settings
from support_email_page import get_component, email_shell_styles, rerun_email
from support_email_workspace import Workspace
from tests.test_email_connection_recovery import Wire
from tests.test_support_email import CONFIG, USER
from tests.email_v2_fixtures import fixture_smtp, FOLDER_DATA

st.set_page_config(page_title="Email connection recovery · local fixture", layout="wide")
st.html('<style>[data-testid="stHeader"] {display:none}</style>')
with st.sidebar:
    st.caption("LOCAL FIXTURE · NO EXTERNAL I/O")
    timeout = st.toggle("Simulate server timeout", value=True)

def connect(*args, **kwargs):
    if timeout:
        raise TimeoutError("fixture-only")
    wire = Wire()
    wire.list = lambda: ("OK", FOLDER_DATA)
    return wire

@st.fragment
def mailbox():
    with (patch.object(provider.imaplib, "IMAP4_SSL", side_effect=AssertionError("Real IMAP forbidden")),
          patch.object(smtp.smtplib, "SMTP_SSL", side_effect=AssertionError("Real SMTP forbidden")),
          patch.object(store, "load_email_settings", return_value=(default_settings(), None)),
          patch.object(store, "load_orders", return_value=[]), patch.object(store, "load_metadata", return_value={}),
          patch.object(store, "load_assignees", return_value=[USER]), patch.object(store, "audit")):
        state = st.session_state.setdefault("fixture_workspace", {})
        workspace = Workspace(state, USER, CONFIG, smtp.SMTPConfiguration(),
            imap=provider.ImapProvider(CONFIG, connection_factory=connect), smtp=fixture_smtp())
        if not state.get("loaded"):
            workspace.load()
        event = get_component()(model=workspace.model(), key="fixture-email-recovery", default=None)
        if event and workspace.handle(event):
            rerun_email()

email_shell_styles()
with st.container(key="support-email-shell"):
    mailbox()
