"""Lazy OS page: the sidebar never loads worker data."""
def render_page(user):
    import os_accounts,streamlit as st
    if not os_accounts.can_access_page(user,'Worker Health'):
        st.error('Worker Health requires an authorised administrator.');return
    st.html('''<style>.st-key-worker-health-workspace iframe{height:calc(100dvh - var(--sc-topbar-height,68px) - 38px)!important;min-height:480px;width:100%}
    .st-key-worker-health-workspace{margin:0!important}</style>''')
    from streamlit.components.v1 import iframe
    with st.container(key='worker-health-workspace'):iframe('/worker-health',height=650,scrolling=True)
