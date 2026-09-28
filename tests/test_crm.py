"""Run explicitly: unittest tests.test_crm (offline, no external credentials)."""
import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock,patch
import uuid
from crm_cache import DisplayCache
from crm_shopify import Shopify,CapabilityUnavailable,gid,CUSTOMER,CUSTOMERS,MEMBERS
from crm_logic import *
from crm_resend import Config,MarketingDisabled,Resend,verify_resend
from crm_service import Actions
from crm_engine import Engine
from crm_templates import seeds,render,validate
from crm_webhooks import receive_shopify,receive_resend,unsubscribe
from tests.crm_fixtures import ShopifyFixture,ResendFixture

ROOT=Path(__file__).resolve().parents[1]
ADMIN={'id':'synthetic-admin','role':'admin','is_active':True,'page_permissions':[]}
WORKER={'id':'synthetic-staff','role':'worker','is_active':True,'page_permissions':['crm_customers_view']}
def config(enabled=True):return Config({'CRM_MARKETING_ENABLED':str(enabled).lower(),'CRM_MARKETING_SEND_ENABLED':str(enabled).lower(),'CRM_MARKETING_TEST_ENABLED':'true','RESEND_MARKETING_API_KEY':'fixture-only','RESEND_FROM_NAME':'Sports Cave','RESEND_FROM_EMAIL':'fixture@example.test','RESEND_REPLY_TO':'reply@example.test', 'CRM_UNSUBSCRIBE_SECRET':'fixture-secret'*4,'CRM_PUBLIC_BASE_URL':'https://example.test'})

class ProviderTests(unittest.TestCase):
    def setUp(self):self.wire=ShopifyFixture();self.cache=DisplayCache();self.shop=Shopify(self.wire,self.cache)
    def test_pagination_and_search(self):
        a=self.shop.customers();b=self.shop.customers(a['pageInfo']['endCursor'])
        self.assertEqual(len(a['nodes']),50);self.assertEqual(len(b['nodes']),23)
        self.assertEqual(self.shop.customers(query='id:12')['nodes'][0]['id'],gid(12))
    def test_customer_cache_and_fresh_consent(self):
        self.shop.customer(1);self.wire.customers[0]['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        self.assertEqual(consent(self.shop.customer(1)),'SUBSCRIBED')
        self.assertEqual(consent(self.shop.customer(1,fresh=True)),'UNSUBSCRIBED')
        self.assertEqual(len(self.wire.calls),2)
    def test_cache_ttl_lru_bytes_and_mutation(self):
        t=[0];cache=DisplayCache(limit=2,byte_limit=100,clock=lambda:t[0]);cache.put('a',{'x':1},2)
        cache.get('a')['x']=3;self.assertEqual(cache.get('a')['x'],1)
        t[0]=3;self.assertIsNone(cache.get('a'));self.assertEqual(cache.bytes,0)
        cache.put('a',1,10);cache.put('b',2,10);cache.put('c',3,10);self.assertIsNone(cache.get('a'))
        cache.invalidate('v');self.assertEqual(cache.bytes,0)
    def test_native_segment_batch_no_per_row_requests(self):
        rows=self.shop.members(gid(1,'Segment'));self.assertGreater(len(rows['nodes']),10)
        self.assertEqual(len(self.wire.calls),2)
        self.assertEqual(self.shop.memberships(gid(1),[gid(1,'Segment')]),{gid(1,'Segment')})
    def test_order_checkout_product_relations(self):
        c=self.shop.customer(1);self.assertEqual(c['numberOfOrders'],'1')
        facts=LiveFacts(self.shop,c);self.assertEqual(facts.purchases()['interest'],{'Motorsport'})
        before=len(self.wire.calls);facts.purchases();self.assertEqual(len(self.wire.calls),before)
        checkout=self.shop.checkout(1);self.assertTrue(checkout['abandonedCheckoutUrl'].startswith('https://'))
    def test_cache_failure_is_not_data_or_secret(self):
        self.wire.fail=RuntimeError('private-secret')
        with self.assertRaises(CapabilityUnavailable) as result:self.shop.customers()
        self.assertNotIn('private-secret',str(result.exception));self.assertEqual(len(self.cache.rows),0)
    def test_no_network_on_import(self):
        code="import socket; socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(AssertionError()); import crm_navigation,crm_shopify,crm_store,crm_engine,crm_resend,crm_worker; print('ok')"
        self.assertEqual(subprocess.check_output([sys.executable,'-c',code],text=True).strip(),'ok')

class LogicTests(unittest.TestCase):
    def setUp(self):self.c=ShopifyFixture(1).customers[0]
    def test_all_consent_states(self):
        for state in ('SUBSCRIBED','UNSUBSCRIBED','PENDING','NOT_SUBSCRIBED','REDACTED','INVALID'):
            self.c['emailMarketingConsent']['marketingState']=state
            self.assertEqual(eligibility(self.c)[0],state=='SUBSCRIBED')
    def test_suppressions_and_missing_address(self):
        self.assertFalse(eligibility(self.c,True)[0]);self.assertFalse(eligibility(self.c,False,True)[0]);self.c['email']='';self.assertEqual(consent(self.c),'INVALID')
    def test_definitions_and_or(self):
        facts=LiveFacts(None,self.c)
        self.assertTrue(matches({'any':[rule('orders',99),rule('consent','SUBSCRIBED')]},facts))
        self.assertFalse(matches({'all':[rule('orders',99),rule('consent','SUBSCRIBED')]},facts))
        self.assertEqual(len(segment_seeds()),17)
        for row in segment_seeds():validate_rules(row['rules'])
    def test_invalid_rules_fail_closed(self):
        for rules in ({'field':'sql','op':'eq','value':'x'},{'any':[]},rule('orders',-1)):
            with self.assertRaises(ValueError):validate_rules(rules)
    def test_automation_defaults(self):
        rows=automation_seeds();self.assertEqual(len(rows),4)
        self.assertEqual([s['hours'] for s in rows[0]['steps'] if s['type']=='delay'],[1,23,48])
        for row in rows:validate_steps(row['steps'])
    def test_html_escaping_unsubscribe_and_branding(self):
        for t in seeds():
            message=render(t['content'],{'first_name':'<script>x</script>','checkout_url':'https://example.test/cart','store_url':'https://example.test'},'https://example.test/u','https://example.test/logo.png','campaign-1')
            self.assertNotIn('<script>',message['html']);self.assertIn('Unsubscribe',message['text']);self.assertIn('utm_source=sportscave',message['html'])
            self.assertNotIn('Nathan',message['html']);self.assertNotIn('Maria',message['html'])
    def test_unsafe_template_and_unknown_placeholder(self):
        c=seeds()[0]['content'];c['cta_url']='javascript:bad'
        with self.assertRaises(ValueError):validate(c)
        c=seeds()[0]['content'];c['body']='{{secret}}'
        with self.assertRaises(ValueError):validate(c)
    def test_permissions_and_gate(self):
        import os_accounts
        self.assertTrue(os_accounts.can_access_page(WORKER,'CRM Customers'));self.assertFalse(os_accounts.can_access_page(WORKER,'CRM Campaigns'))
        with self.assertRaises(PermissionError):Actions(Mock(),WORKER).campaign('x',{})
        with self.assertRaises(MarketingDisabled):Actions(Mock(),ADMIN,Config({})).schedule({'id':'1'},now()+timedelta(days=1))
    def test_unsubscribe_token_and_svix(self):
        c=config();identity=str(uuid.uuid4());token=c.unsubscribe_url(identity).split('token=')[1]
        self.assertEqual(c.verify_token(token),identity);self.assertIsNone(c.verify_token(token+'x'))
        raw=b'{"type":"email.sent"}';key=b'x'*32;timestamp='1700000000';headers={'svix-id':'evt1','svix-timestamp':timestamp}
        headers['svix-signature']='v1,'+base64.b64encode(hmac.new(key,b'evt1.'+timestamp.encode()+b'.'+raw,hashlib.sha256).digest()).decode()
        self.assertTrue(verify_resend(raw,headers,'whsec_'+base64.b64encode(key).decode(),lambda:1700000000))
        self.assertFalse(verify_resend(raw+b' ',headers,'whsec_'+base64.b64encode(key).decode(),lambda:1700000000))
        self.assertFalse(verify_resend(raw,headers,'whsec_'+base64.b64encode(key).decode(),lambda:1700001000))
    def test_webhooks_only_minimal_metadata(self):
        store=Mock();receive_shopify(store,'customers_email_marketing_consent/update','e',{'customer_id':1,'email_address':'private@example.test','note':'private body'},now())
        self.assertNotIn('private',str(store.method_calls));self.assertEqual(store.webhook.call_args.args[4],gid(1))
    def test_schema_no_customer_replicas_and_rls(self):
        sql=(ROOT/'migrations/20260927093818_crm_marketing_v1.sql').read_text()
        for forbidden in ('crm_customers','crm_orders','crm_products','crm_segment_members','crm_abandoned_checkouts'):
            self.assertNotIn('CREATE TABLE IF NOT EXISTS '+forbidden,sql)
        self.assertIn('ENABLE ROW LEVEL SECURITY',sql);self.assertIn('REVOKE ALL',sql)
    def test_email_sources_not_imported_by_crm(self):
        for path in ROOT.glob('crm_*.py'):
            self.assertNotIn('import support_email',path.read_text(encoding='utf-8-sig'))

if __name__=='__main__':unittest.main()
