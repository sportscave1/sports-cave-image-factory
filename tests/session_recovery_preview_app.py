"""Local-only actual sidebar/composer with disposable SQL and synthetic services."""
from pathlib import Path
from unittest.mock import patch
import streamlit as st

source=(Path(__file__).parent/'sidebar_preview_app.py').read_text(encoding='utf-8')
exec(source.replace("st.button('Main content button')",''))
import session_recovery
session_recovery.install(st)
from crm_page import render_page
from crm_shopify import Shopify
from crm_store import Store
from crm_resend import Config
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
from crm_campaign_markets import MARKET_LABELS
from tests.test_crm_modular_catalogue import service, node

def catalogue_fixture(*args,**kwargs):
    result=service()
    result.collections=lambda:{"rows":[]}
    result.search=lambda *a:{"rows":result.resolve([node(i)["id"] for i in range(1,6)]),"more":False}
    return result

if st.button('Simulate new server session'):
    st.session_state.clear();st.rerun()
store=Store(connect);store.seed()
if get_current_page()=='CRM Campaigns':
    with patch('crm_section_ui.Catalogue',side_effect=catalogue_fixture),patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')),patch('crm_segment_counts.COUNTS.display',return_value={'counts':dict.fromkeys(MARKET_LABELS,0),'error':False}):
        render_page('CRM Campaigns',current_os_user(),shop=Shopify(ShopifyFixture()),store=store,config=Config({}))
