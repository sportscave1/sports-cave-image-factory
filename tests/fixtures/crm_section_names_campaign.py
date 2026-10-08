"""Existing campaign composer with synthetic Shopify and loopback SQL only."""
import streamlit as st
from tests.test_crm_ui import SCRIPT
st.set_page_config(layout='wide')
st.session_state['route']='CRM Campaigns'
exec(SCRIPT)
