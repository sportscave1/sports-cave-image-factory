"""Lazy local-only Developer entry; no runner or browser on the app server."""
import os


def render_page(user):
    import os_accounts
    import streamlit as st
    if not os_accounts.is_admin(user):
        st.error("Task Recorder is available only to administrators.")
        return
    st.markdown("#### Task Recorder · Local V1")
    st.caption("Start Task Recorder.cmd on your Windows PC. The browser and saved tasks stay on that PC.")
    st.link_button("Open local Task Recorder", "http://127.0.0.1:18931/")
    if os.environ.get("RENDER"):
        st.info("Hosted pairing is not implemented in V1. Use the authenticated console opened by the Windows launcher. This server cannot control your PC through its own localhost.")
        return
    from streamlit.components.v1 import iframe
    iframe("http://127.0.0.1:18931/", height=650, scrolling=True)
