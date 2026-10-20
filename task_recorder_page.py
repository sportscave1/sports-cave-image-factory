"""Embedded administrator recorder page; the helper owns task/run state."""
def render_page(user):
    import os_accounts
    import streamlit as st
    if not os_accounts.is_admin(user):
        st.error("Task Recorder is available only to administrators.")
        return
    st.markdown("#### Task Recorder")
    from streamlit.components.v1 import iframe
    iframe("/task-recorder/panel", height=640, scrolling=False)
