"""Shopify-native opt-out integration: synthetic URLs, mocked transports only."""
from copy import deepcopy
from html import escape
import unittest
from unittest.mock import Mock,patch
import uuid
from crm_native_unsubscribe import native_unsubscribe_url
from crm_shopify import Shopify,CUSTOMERS,CUSTOMER,CUSTOMER_BATCH,CAMPAIGN_SUBSCRIBERS
from crm_logic import eligibility,recipient_hash
from crm_campaign_markets import calculate
from crm_campaign_send import verified_native_audience
from crm_campaign_content import render_campaign,settings
from crm_resend import Config,Resend,MarketingDisabled
from crm_engine import Engine
from tests.crm_fixtures import ShopifyFixture,native_customer
from tests.test_crm_campaign_sections import sectioned

ENV={'CRM_MARKETING_ENABLED':'false','RESEND_MARKETING_API_KEY':'fixture',
     'RESEND_FROM_EMAIL':'sender@example.test','RESEND_FROM_NAME':'Sports Cave','RESEND_REPLY_TO':'reply@example.test',
     'CRM_PUBLIC_BASE_URL':'https://hooks.example.test'}

class NativeUnsubscribeTests(unittest.TestCase):
    def customer(self,i=1):
        c=ShopifyFixture(4).customers[i-1]
        c['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        return native_customer(c)

    def test_all_existing_customer_queries_include_fields(self):
        for query in (CUSTOMERS,CUSTOMER,CUSTOMER_BATCH,CAMPAIGN_SUBSCRIBERS):
            self.assertIn('defaultEmailAddress { emailAddress marketingState marketingUnsubscribeUrl validFormat }',query)

    def test_two_production_renders_use_own_native_urls_without_secret(self):
        urls=[]
        for i in (1,2):
            c=self.customer(i);url=native_unsubscribe_url(c);urls.append(url)
            rendered=render_campaign(sectioned(),settings(ENV),unsubscribe_url=url,production=True)
            self.assertIn('href="'+escape(url,quote=True)+'"',rendered['html'])
            self.assertNotIn('{{UNSUBSCRIBE_URL}}',rendered['html'])
            self.assertNotIn('/crm/unsubscribe?token=',rendered['html'])
        self.assertNotEqual(*urls)
        self.assertEqual(Config(ENV).secret,'')
        self.assertFalse(Config(ENV).enabled)

    def test_signed_native_url_is_never_rewritten_as_tracking(self):
        doc=sectioned()
        url=native_unsubscribe_url(self.customer())+'&utm_source=sports_cave&utm_campaign='+doc['campaign_key']+'&sc_test=1'
        rendered=render_campaign(doc,settings(ENV),unsubscribe_url=url,production=True)
        self.assertIn('href="'+escape(url,quote=True)+'"',rendered['html'])

    def test_preview_and_test_have_only_safe_route(self):
        preview=render_campaign(sectioned(),settings(ENV))
        self.assertIn('/crm/unsubscribe/test',preview['html'])
        self.assertNotIn('token=fixture-',preview['html'])

    def test_missing_unsafe_or_mismatched_url_fails_closed(self):
        for bad in ('','#','javascript:bad','http://unsafe.test','https://127.0.0.1/u','https://good.test/u\r\nBcc:bad','https://good.test/u>'):
            c=self.customer();c['defaultEmailAddress']['marketingUnsubscribeUrl']=bad
            self.assertEqual(native_unsubscribe_url(c),'')
            with self.assertRaisesRegex(ValueError,'Missing Shopify'):
                verified_native_audience({'recipients':[{'id':c['id']}],'profiles':{c['id']:c}})
        c=self.customer();c['defaultEmailAddress']['emailAddress']='other@example.test'
        self.assertFalse(native_unsubscribe_url(c));self.assertFalse(eligibility(c)[0])

    def test_restrictive_consent_and_local_suppression(self):
        c=self.customer();self.assertFalse(eligibility(c,True)[0])
        for field in ('defaultEmailAddress','emailMarketingConsent'):
            bad=deepcopy(c);bad[field]['marketingState']='UNSUBSCRIBED'
            self.assertEqual(eligibility(bad),(False,'consent_unsubscribed'))

    def test_all_markets_see_native_optout_with_one_profile_pass(self):
        wire=ShopifyFixture(4)
        for i,code in enumerate(('AU','US','GB','NZ'),1):
            c=self.customer(i);c['defaultAddress']={'countryCodeV2':code}
            wire.customers[i-1]=c
        shop=Shopify(wire);store=Mock();store.state.return_value={};store.active_suppression_hashes.return_value=(set(),set());store.recent_marketing_hashes.return_value=set()
        before=calculate(shop,store)
        self.assertEqual(before['Global']['eligible'],4)
        from crm_shopify import CAMPAIGN_SUBSCRIBERS
        self.assertEqual(sum(doc==CAMPAIGN_SUBSCRIBERS for doc,_ in wire.calls),1)
        for c in wire.customers:c['defaultEmailAddress']['marketingState']='UNSUBSCRIBED'
        after=calculate(shop,store)
        self.assertEqual(sum(doc==CAMPAIGN_SUBSCRIBERS for doc,_ in wire.calls),2)
        for market in ('AU','US','UK','Global'):self.assertEqual(after[market]['eligible'],0)

    def worker(self,customer):
        # Enable only a synthetic Config object; process/deployment flags are untouched.
        cfg=Config({**ENV,'CRM_MARKETING_ENABLED':'true','CRM_MARKETING_SEND_ENABLED':'true'})
        row={'id':str(uuid.uuid4()),'test_send':False,'enrollment_id':None,'shopify_customer_id':customer['id'],
             'recipient_hash':recipient_hash(customer['email']),'template_id':'fixture','template_version':1,'idempotency_key':'fixture','campaign_id':str(uuid.uuid4())}
        store=Mock();store.connect=None;store.claim_send.return_value=row;store.suppressed.return_value=False;store.begin_send.return_value=True
        from crm_tracking import send_identity
        store.q.return_value={'campaign_send_id':send_identity(row['campaign_id'])}
        store.template.return_value={'format':'campaign_delivery_v1','document':sectioned(),'render_settings':settings(ENV)}
        shop=Mock();shop.customer.return_value=customer
        delivery=Mock();delivery.suppressed.return_value=False;delivery.send.return_value='mock-message'
        with patch('crm_campaign_send.production_checks',return_value={'ready':True}),patch('crm_workspace_store.WorkspaceRecords.frequency_blocked',return_value=False):
            Engine(store,shop,delivery,cfg).send_one()
        return store,shop,delivery,row

    def test_worker_reuses_fresh_customer_read_and_native_url(self):
        c=self.customer();store,shop,delivery,row=self.worker(c)
        shop.customer.assert_called_once_with(c['id'],fresh=True)
        delivery.send.assert_called_once()
        message=delivery.send.call_args.args[1]
        self.assertEqual(message['unsubscribe_url'],native_unsubscribe_url(c))
        self.assertFalse(message['unsubscribe_one_click'])
        store.finish_send.assert_called_once_with(row,'ACCEPTED',provider_id='mock-message')

    def test_worker_records_missing_url_without_provider_submission(self):
        c=self.customer();c['defaultEmailAddress']['marketingUnsubscribeUrl']=''
        store,shop,delivery,row=self.worker(c)
        delivery.send.assert_not_called();delivery.suppressed.assert_not_called()
        store.finish_send.assert_called_once_with(row,'BLOCKED','missing_shopify_marketing_unsubscribe_url')

    def test_native_header_omits_unverified_one_click_post(self):
        cfg=Config({**ENV,'CRM_MARKETING_ENABLED':'true','CRM_MARKETING_SEND_ENABLED':'true','CRM_PUBLIC_BASE_URL':''})
        cfg.require_send()  # No HMAC secret or custom public endpoint dependency.
        url=native_unsubscribe_url(self.customer())
        message=render_campaign(sectioned(),settings(ENV),unsubscribe_url=url,production=True)
        message.update(unsubscribe_url=url,unsubscribe_one_click=False)
        session=Mock();session.post.return_value=Mock(status_code=200,json=lambda:{'id':'mock-only'})
        with patch('crm_resend.pace'):Resend(cfg,session).send('synthetic@example.test',message,'fixture')
        headers=session.post.call_args.kwargs['json']['headers']
        self.assertEqual(headers,{'List-Unsubscribe':'<'+url+'>'})
        with self.assertRaises(MarketingDisabled):Config(ENV).require_send()
