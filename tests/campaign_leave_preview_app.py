"""Local leave-dialog fixture: real sidebar guard; no live services."""
from pathlib import Path
from unittest.mock import patch
import streamlit as st
source=(Path(__file__).parent/'sidebar_preview_app.py').read_text(encoding='utf-8')
source=source.replace("def set_current_page(route,**kwargs):st.session_state['route']=route;st.query_params['page']=route", "def set_current_page(route,**kwargs):\n    from crm_navigation import navigation_allowed\n    if navigation_allowed(st.session_state,get_current_page(),route):st.session_state['route']=route;st.query_params['page']=route")
exec(source.replace("st.button('Main content button')",''))
from crm_page import render_page
from crm_store import Store
from crm_shopify import Shopify
from crm_resend import Config
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
from crm_campaign_recovery import flush_current

def stage():
    st.session_state['campaign_editor']['name']+=' — pending'
    st.session_state[st.session_state['campaign_edit_key']+'name']=st.session_state['campaign_editor']['name']
    st.session_state['hold_autosave']=True

def flush(*,force=False):
    if not force and st.session_state.get('hold_autosave'):return False
    return flush_current(force=force)

if get_current_page()=='CRM Campaigns':
    if st.session_state.get('campaign_editor'):st.button('Stage unsaved fixture edit',on_click=stage)
    store=Store(connect);store.seed()
    with patch('requests.sessions.Session.request',side_effect=AssertionError('No external services')),patch('crm_campaign_page.flush_current',side_effect=flush),patch('crm_campaign_recovery.flush_current',side_effect=flush):
        render_page('CRM Campaigns',current_os_user(),navigate=set_current_page,shop=Shopify(ShopifyFixture()),store=store,config=Config({}))
