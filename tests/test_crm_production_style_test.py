"""Manual TEST delivery, production-native unsubscribe; all transport is mocked."""
from copy import deepcopy
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from crm_test_recipient import test_recipient_url as resolve_url
from crm_campaign_content import render_campaign
from crm_campaign_send import send_test
from crm_campaign_store import CampaignStore
from tests.crm_fixtures import TestRecipientShop, TEST_UNSUBSCRIBE_URL
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document
from tests.test_crm_resend_marketing import ENV
from tests.test_crm_send_flow import CFG
from tests.crm_db_fixture import connect


class RecipientTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock();self.store.suppressed.return_value=False
        self.shop=Mock()
        self.page=TestRecipientShop().customers(query='email:"one@example.test"',fresh=True)
        self.shop.customers.return_value=self.page
    def resolve(self,address='one@example.test'):
        return resolve_url(self.store,address,shop=self.shop)
    def test_exact_default_email_fresh_lookup_once(self):
        self.assertEqual(self.resolve('ONE@example.test'),TEST_UNSUBSCRIBE_URL)
        self.shop.customers.assert_called_once_with(query='email:"one@example.test"',fresh=True)
        self.store.suppressed.assert_called_once()
    def test_missing_customer(self):
        self.page['nodes']=[]
        with self.assertRaisesRegex(ValueError,'customer not found'):self.resolve()
    def test_partial_search_match_is_not_accepted(self):
        self.page['nodes'][0]['email']='someone@example.test'
        with self.assertRaisesRegex(ValueError,'customer not found'):self.resolve()
    def test_ambiguous_or_incomplete_match_is_blocked(self):
        for change in ('duplicate','next_page'):
            with self.subTest(change=change):
                page=deepcopy(self.page)
                if change=='duplicate':page['nodes']*=2
                else:page['pageInfo']['hasNextPage']=True
                self.shop.customers.return_value=page
                with self.assertRaisesRegex(ValueError,'could not be verified'):self.resolve()
    def test_default_mismatch_or_invalid_format(self):
        for key,value in (('emailAddress','other@example.test'),('validFormat',False)):
            with self.subTest(key=key):
                page=deepcopy(self.page);page['nodes'][0]['defaultEmailAddress'][key]=value
                self.shop.customers.return_value=page
                with self.assertRaisesRegex(ValueError,'valid Shopify default'):self.resolve()
    def test_restrictive_consent_from_either_source(self):
        for field in ('defaultEmailAddress','emailMarketingConsent'):
            page=deepcopy(self.page);page['nodes'][0][field]['marketingState']='UNSUBSCRIBED'
            self.shop.customers.return_value=page
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'not subscribed'):self.resolve()
    def test_local_suppression_vetoes_subscription(self):
        self.store.suppressed.return_value=True
        with self.assertRaisesRegex(ValueError,'locally suppressed'):self.resolve()
    def test_missing_or_unsafe_unsubscribe_url(self):
        for url in ('','#','javascript:alert(1)','http://example.test/unsubscribe','https://example.test/\r\nBcc:secret'):
            self.page['nodes'][0]['defaultEmailAddress']['marketingUnsubscribeUrl']=url
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'URL unavailable'):self.resolve()
    def test_invalid_and_multiple_addresses_never_looked_up(self):
        for address in ('bad','one@example.test,two@example.test',['one@example.test']):
            with self.assertRaises(ValueError):self.resolve(address)
        self.shop.customers.assert_not_called()
    def test_lookup_errors_never_log_private_response(self):
        self.shop.customers.side_effect=RuntimeError(TEST_UNSUBSCRIBE_URL)
        with self.assertLogs('crm_test_recipient',level='WARNING') as logs,self.assertRaisesRegex(ValueError,'lookup unavailable') as error:
            self.resolve()
        self.assertNotIn(TEST_UNSUBSCRIBE_URL,str(logs.output)+str(error.exception))
    def test_existing_shopify_query_is_fresh_and_recipient_specific(self):
        from crm_shopify import Shopify, CUSTOMERS
        from tests.crm_fixtures import ShopifyFixture, native_customer
        wire=ShopifyFixture(4);shop=Shopify(wire)
        first=native_customer(wire.customers[0]);second=native_customer(wire.customers[3])
        wire.customers=[first,second]
        url1=resolve_url(self.store,first['email'],shop=shop)
        url2=resolve_url(self.store,second['email'],shop=shop)
        self.assertNotEqual(url1,url2)
        self.assertEqual(len(wire.calls),2)
        self.assertTrue(all(query==CUSTOMERS for query,_ in wire.calls))
        first['defaultEmailAddress']['marketingState']='UNSUBSCRIBED'
        with self.assertRaisesRegex(ValueError,'not subscribed'):
            resolve_url(self.store,first['email'],shop=shop)
        self.assertEqual(len(wire.calls),3)  # No stale cached SUBSCRIBED decision.


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class ProductionStyleTestTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect)
        self.shop=TestRecipientShop()
        self.wire=Mock();self.wire.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
        for p in (patch('crm_test_recipient.Shopify',return_value=self.shop),
                  patch.object(self.store,'render_settings',return_value=deepcopy(CFG)),
                  patch('crm_resend_marketing._audit',return_value=True),
                  patch('requests.sessions.Session.request',side_effect=AssertionError('No real network'))):
            p.start();self.addCleanup(p.stop)
        self.editor={'id':None,'version':None,'name':'Native test '+uuid.uuid4().hex,'document':document(),'archived_at':None}
    def counts(self):
        return {table:self.store.q('SELECT count(*) n FROM '+table,one=True)['n']
                for table in ('crm_campaigns','crm_marketing_sends')}
    def send(self,op=None):
        return send_test(self.store,ADMIN,self.editor,'one@example.test',op or str(uuid.uuid4()),env=ENV,session=self.wire)
    def test_real_render_headers_one_recipient_no_segment_or_production_jobs(self):
        counts=self.counts();op=str(uuid.uuid4())
        with patch('crm_campaign_send.final_audience',side_effect=AssertionError('No segment')) as audience,patch('crm_catalogue.refresh_catalogues',side_effect=AssertionError('No products')):
            self.send(op);self.send(op)
        audience.assert_not_called();self.wire.post.assert_called_once();self.assertEqual(len(self.shop.calls),1)
        payload=self.wire.post.call_args.kwargs['json']
        expected=render_campaign(self.editor['document'],CFG,production=True,test_tracking=True,unsubscribe_url=TEST_UNSUBSCRIBE_URL)
        self.assertEqual(payload['html'],expected['html']);self.assertEqual(payload['text'],expected['text'])
        self.assertEqual(payload['headers'],{'List-Unsubscribe':'<'+TEST_UNSUBSCRIBE_URL+'>'})
        self.assertEqual(payload['to'],['one@example.test']);self.assertIn('[CAMPAIGN TEST]',payload['subject'])
        self.assertNotIn('/crm/unsubscribe/test',payload['html']);self.assertNotIn('{{UNSUBSCRIBE_URL}}',payload['html'])
        self.assertEqual(counts,self.counts())
        saved=self.store.draft(self.editor['id'])
        self.assertEqual(saved['status'],'TESTED');self.assertEqual(saved['document']['counts'],self.editor['document']['counts'])
        history=self.store.q('SELECT after_value FROM crm_campaign_history WHERE campaign_id=%s',(self.editor['id'],))
        self.assertNotIn(TEST_UNSUBSCRIBE_URL,json.dumps(history,default=str))
    def test_blocked_customer_never_reaches_transport_or_queue(self):
        before=self.counts()
        with patch.object(self.shop,'customers',return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}):
            with self.assertRaisesRegex(ValueError,'customer not found'):self.send()
        self.wire.post.assert_not_called();self.assertEqual(before,self.counts())
        self.assertEqual(self.store.draft(self.editor['id'])['status'],'DRAFT')
    def test_preview_stays_safe(self):
        cfg={**CFG,'public_base_url':'https://preview.example.test'}
        preview=render_campaign(self.editor['document'],cfg)
        self.assertNotIn(TEST_UNSUBSCRIBE_URL,preview['html'])
        self.assertNotIn('/account/unsubscribe',preview['html'])
        self.assertEqual(self.shop.calls,[])
    def test_ui_layout_changes_are_not_required(self):
        from pathlib import Path
        source=Path('crm_campaign_send_ui.py').read_text(encoding='utf-8')
        self.assertIn("st.popover('Send test'",source)
        self.assertIn("text_input('Send test email'",source)
        self.assertIn('Send test uses the real Shopify unsubscribe link for this customer.',source)
