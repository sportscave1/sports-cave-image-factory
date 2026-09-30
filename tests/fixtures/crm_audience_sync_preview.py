"""Offline real Campaign editor; synthetic Shopify + disposable loopback SQL only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
import streamlit as st
from crm_page import render_page
from crm_shopify import Shopify
from crm_store import Store
from crm_resend import Config
from crm_webhooks import receive_shopify
from crm_logic import now
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
from tests.test_crm import ADMIN
from tests.test_crm_campaign_v2 import profile

st.set_page_config(layout='wide',page_title='CRM audience sync · offline fixture')
st.sidebar.caption('Offline fixture · no live data or delivery')
wire=st.session_state.setdefault('wire',ShopifyFixture(0))
if not wire.customers:wire.customers=[profile(1),profile(2,'US'),profile(3,'GB')]
shop=st.session_state.setdefault('shop',Shopify(wire,namespace='browser-sync-fixture'))
store=Store(connect)
if st.sidebar.button('Simulate AU subscriber'):
    identity=len(wire.customers)+1
    customer=profile(identity,'');customer['tags']=['SC_COUNTRY_AU'];wire.customers.append(customer)
    receive_shopify(store,'customers/update','browser-'+str(identity),{'id':identity},now())
st.sidebar.caption('Synthetic subscribed customers: '+str(len(wire.customers)))
with (patch('crm_service.audit'),
      patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')),
      patch('supabase_backend.connect',side_effect=AssertionError('Production DB forbidden'))):
    render_page('CRM Campaigns',ADMIN,shop=shop,store=store,config=Config({}))
