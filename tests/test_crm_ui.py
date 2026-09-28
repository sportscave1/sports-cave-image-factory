"""Real Streamlit page tests against synthetic authority and disposable PostgreSQL."""
import os
import unittest
from streamlit.testing.v1 import AppTest

SCRIPT='''
from unittest.mock import patch
import streamlit as st
from crm_page import render_page,profile
from crm_navigation import PAGES
from crm_shopify import Shopify,gid
from crm_store import Store
from crm_resend import Config
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
wire=st.session_state.setdefault('wire',ShopifyFixture())
store=Store(connect);store.seed()
user={'id':'fixture','role':'worker','is_active':True,'page_permissions':[p[0] for p in PAGES]+['email']}
with patch('crm_service.audit'),patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden')):
    if st.session_state.get('profile'):
        profile(Shopify(wire),store,gid(1),lambda _:None,user)
    else:
        render_page(st.session_state.get('route','CRM Customers'),user,shop=Shopify(wire),store=store,config=Config({}))
'''

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Start isolated PostgreSQL fixture explicitly.')
class UiTests(unittest.TestCase):
    def app(self,route):
        at=AppTest.from_string(SCRIPT);at.session_state['route']=route;return at.run(timeout=20)
    def test_six_pages_load_with_gated_delivery(self):
        for route in ('CRM Customers','CRM Segments','CRM Automations','CRM Campaigns','CRM Templates','CRM Reports'):
            with self.subTest(route=route):
                at=self.app(route);self.assertFalse(at.exception)
                if route!='CRM Campaigns':self.assertFalse(at.warning)
                else:self.assertTrue(any('LIVE MARKETING DELIVERY: DISABLED' in w.value for w in at.warning))
                if route=='CRM Campaigns':self.assertFalse(any(b.label=='Send campaign' for b in at.button))
    def test_customer_pagination_and_search(self):
        at=self.app('CRM Customers');self.assertEqual(len(at.dataframe[0].value),50)
        at.button(key='crm_customer_cursor_next').click().run();self.assertEqual(len(at.dataframe[0].value),23)
        at.text_input[0].set_value('12');next(b for b in at.button if b.label=='Search').click().run()
        self.assertEqual(len(at.dataframe[0].value),1);self.assertFalse(at.exception)
    def test_profile_loads_live_value_order_and_context(self):
        at=AppTest.from_string(SCRIPT);at.session_state['profile']=True;at.run(timeout=20)
        self.assertFalse(at.exception);self.assertEqual(at.metric[1].value,'1')
        at.button(key='facts_gid://shopify/Customer/1').click().run()
        self.assertFalse(at.exception);self.assertTrue(any('Motorsport' in x.value for x in at.markdown))
    def test_native_preview_survives_rerun(self):
        at=self.app('CRM Segments');next(b for b in at.button if b.label=='Load current members').click().run()
        self.assertTrue(any('live members' in c.value for c in at.caption));at.run()
        self.assertTrue(any('live members' in c.value for c in at.caption));self.assertFalse(at.exception)
    def test_audience_count_is_complete_and_session_only(self):
        at=self.app('CRM Campaigns');next(b for b in at.button if b.label=='+ New Campaign').click().run()
        next(r for r in at.radio if r.label=='Campaign editor').set_value('2 · Audience').run()
        next(b for b in at.button if b.label=='Recalculate eligibility').click().run()
        next(b for b in at.button if b.label=='Continue calculation').click().run()
        self.assertTrue(any(c.value.startswith('Complete') for c in at.caption));self.assertFalse(at.exception)
    def test_automation_activation_fails_closed(self):
        at=self.app('CRM Automations');next(s for s in at.selectbox if s.label=='Status').set_value('ACTIVE')
        next(b for b in at.button if b.label=='Save workflow').click().run()
        self.assertTrue(any('disabled' in w.value for w in at.warning));self.assertFalse(at.exception)

if __name__=='__main__':unittest.main()
