"""Lazy desktop mail workspace using the OS's existing custom-component pattern."""
import html
import logging
from pathlib import Path
from threading import Lock

import streamlit as st
import streamlit.components.v1 as components

import os_accounts
from support_email_provider import load_configuration
from support_email_smtp import load_smtp_configuration
from support_email_workspace import Workspace

LOGGER = logging.getLogger(__name__)
_COMPONENT = None
_LOCK = Lock()


def get_component():
    global _COMPONENT
    if _COMPONENT is None:
        with _LOCK:
            if _COMPONENT is None:
                _COMPONENT = components.declare_component("support_email_desktop", path=str(Path(__file__).parent / "components" / "support_email"))
    return _COMPONENT


def _safe_text(value, *, note=False):
    st.html(f'<div style="white-space:pre-wrap">{html.escape(str(value))}</div>')


def render_page(user):
    if not os_accounts.can_access_page(user, "Email"):
        st.info("Your OS account does not have Email access.")
        return
    # Only the Email shell removes Streamlit's trailing page padding; the iframe fills
    # the viewport below the existing navigation and owns its internal scroll areas.
    st.html("""<style>
    [data-testid="stMainBlockContainer"]:has(.st-key-support-email-shell) {
        padding-bottom: 0 !important;
    }
    .st-key-support-email-shell { min-height: 0; }
    </style>""")
    with st.container(key="support-email-shell"):
        _render_workspace(user)


@st.fragment
def _render_workspace(user):
    config, smtp = load_configuration(), load_smtp_configuration()
    scope = (config.scope, str(user.get("id")))
    if st.session_state.get("support_email_scope") != scope:
        st.session_state["support_email_scope"] = scope
        st.session_state["support_email_workspace"] = {}
    state = st.session_state.setdefault("support_email_workspace", {})
    workspace = Workspace(state, user, config, smtp)
    try:
        epoch = st.session_state.get("navigation_epoch", 0)
        if not state.get("loaded") or state.get("navigation_epoch") != epoch:
            workspace.load(force=bool(state.get("loaded")))
            state["navigation_epoch"] = epoch
        event = get_component()(model=workspace.model(), key="support-email-desktop", default=None)
        if event and workspace.handle(event):
            st.rerun(scope="fragment")
    except Exception as error:
        LOGGER.warning("Email workspace unavailable (%s)", type(error).__name__)
        st.warning("Email is temporarily unavailable. Refresh Email to reconnect.")
