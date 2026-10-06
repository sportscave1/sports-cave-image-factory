"""Signed fixtures and disposable loopback Postgres; no live store or email."""
from copy import deepcopy
from datetime import timedelta
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from crm_http import router
from crm_logic import now
from crm_webhooks import receive_shopify
from crm_shopify_automation_events import checkout_key,facts,recover
from crm_automation_capabilities import verify,require,activate_pixel,PIXEL,CREATE_PIXEL
from crm_shopify_pixel import record,validate_settings,EVENTS
from tests import test_crm_native_automations as native_fixture

SHOP='fixture.myshopify.com'
SETTINGS={'endpoint':'https://fixture.example/shopify/customer-events','shop':SHOP,'ingestionId':'a'*32}


class CapabilitiesTests(unittest.TestCase):
    def test_rule_facts_are_bounded_and_fail_closed(self):
        from crm_automation_rule_facts import order_facts
        from crm_automation_definition import qualifies,validate,new_flow
        shop=Mock();order={'id':'gid://shopify/Order/1','totalPriceSet':{'shopMoney':{'amount':'100.00','currencyCode':'AUD'}},'lineItems':{'nodes':[{'product':{'id':'gid://shopify/Product/12'}}],'pageInfo':{'hasNextPage':False}}}
        rules=[{'field':'product_purchased','condition':'is','value':'gid://shopify/Product/12'},{'field':'order_value','condition':'at_least','value':'AUD 100'}]
        flow=new_flow('post_purchase');flow['rules']=rules;validate(flow)
        facts=order_facts(shop,order,rules)
        self.assertTrue(qualifies(flow,{},facts));shop.line_page.assert_not_called();shop.products.assert_not_called()
        self.assertFalse(qualifies(flow,{},dict(facts,order_value={'amount':'1000','currencyCode':'USD'})))
        order['lineItems']['pageInfo']={'hasNextPage':True,'endCursor':None}
        with self.assertRaises(ValueError):order_facts(shop,order,rules)
    def shop(self):
        shop=Mock()
        canonical='9f3e6f021262ad99ece4c3ac987d1c4c'
        def query(doc,*args):
            if doc==PIXEL:return {'webPixel':None}
            return {'shop':{'id':'gid://shopify/Shop/1'},'currentAppInstallation':{'app':{'apiKey':canonical},'accessScopes':[{'handle':s} for s in ('read_customers','read_orders','write_pixels','read_customer_events','write_marketing_events')]}}
        shop.query.side_effect=query
        return shop
    def test_actual_app_identity_scope_and_callback_version_gates(self):
        from crm_automation_capabilities import TOPICS
        shop=self.shop();store=Mock();hooks=[{'topic':t,'apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':'https://fixture.example/webhooks/shopify/crm'}} for t in {x for ts in TOPICS.values() for x in ts}]
        with patch('crm_tracking_health.subscriptions',return_value=hooks):
            result=verify(shop,store,{'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example','SHOPIFY_WEBHOOK_SECRET':'fixture-secret'})
        self.assertTrue(all(v=='AVAILABLE' for v in result['triggers'].values()))
        self.assertEqual(result['scope_checks']['write_pixels'],'VERIFIED')
        hooks[0]['apiVersion']['handle']='2025-10'
        with patch('crm_tracking_health.subscriptions',return_value=hooks):result=verify(shop,store,{'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example','SHOPIFY_WEBHOOK_SECRET':'fixture-secret'})
        self.assertIn('UNAVAILABLE',result['triggers'].values())
        shop.query.side_effect=RuntimeError('credential-secret')
        result=verify(shop,store);self.assertNotIn('credential-secret',json.dumps(result));self.assertTrue(all(v=='UNVERIFIED' for v in result['triggers'].values()))
    def test_missing_or_stale_capability_blocks(self):
        store=Mock();store.state.return_value={}
        with self.assertRaises(ValueError):require(store,'welcome')
        store.state.return_value={'checked_at':(now()-timedelta(hours=1)).isoformat(),'triggers':{'welcome':'AVAILABLE'}}
        with self.assertRaises(ValueError):require(store,'welcome')
    def test_idempotent_pixel_creation_and_settings_preserved(self):
        shop=Mock();store=Mock();pixel={'id':'gid://shopify/WebPixel/1','settings':SETTINGS}
        shop.query.side_effect=[{'webPixel':None},{'webPixelCreate':{'webPixel':pixel,'userErrors':[]}}]
        with patch('crm_automation_capabilities.verify',return_value={'scopes':['write_pixels','read_customer_events']}):
            self.assertEqual(activate_pixel(shop,store,SETTINGS),pixel)
            shop.query.side_effect=None;shop.query.return_value={'webPixel':pixel};shop.query.reset_mock()
            self.assertEqual(activate_pixel(shop,store,SETTINGS),pixel)
        self.assertEqual(shop.query.call_count,1)
        self.assertEqual(store.set_state.call_args.args[1]['customer_events_verified'],False)
    def test_pixel_lookup_failure_cannot_create_duplicate(self):
        shop=Mock();shop.query.side_effect=RuntimeError('offline')
        with patch('crm_automation_capabilities.verify',return_value={'scopes':['write_pixels','read_customer_events']}),self.assertRaises(RuntimeError):activate_pixel(shop,Mock(),SETTINGS)
        self.assertEqual(shop.query.call_count,1)
    def test_registration_reuses_existing_topics_without_duplicates(self):
        import contextlib,io
        from scripts.register_crm_webhooks import main
        from crm_automation_capabilities import TOPICS
        rows=[{'id':'gid://shopify/WebhookSubscription/'+str(i),'topic':topic,'apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':'https://fixture.example/webhooks/shopify/crm'}} for i,topic in enumerate({t for ts in TOPICS.values() for t in ts})]
        with patch.dict(os.environ,{'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example','SHOPIFY_API_VERSION':'2026-04'}),patch('shopify_sync.graphql_request',side_effect=[(self.shop().query('',{}),{}),({'webhookSubscriptions':{'nodes':rows,'pageInfo':{'hasNextPage':False}}},{})]) as query,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--automation-only','--apply']),0)
        self.assertEqual(query.call_count,2)
        self.assertNotIn('mutation',str(query.call_args_list));self.assertEqual(output.getvalue().count('registered'),6)
    def test_settings_invalid_and_no_secrets(self):
        for change in ({'endpoint':'http://localhost/shopify/customer-events'},{'shop':'other.example'},{'ingestionId':'secret'}):
            with self.assertRaises(ValueError):validate_settings({**SETTINGS,**change})


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable Postgres required')
class TriggerTests(unittest.TestCase):
    published=native_fixture.NativeAutomationTests.published
    def setUp(self):
        native_fixture.NativeAutomationTests.setUp(self)
        self.shop_env=patch.dict(os.environ,{'SHOPIFY_STORE_DOMAIN':SHOP});self.shop_env.start();self.addCleanup(self.shop_env.stop)
        self.token=uuid.uuid4().hex;self.key=checkout_key(self.token,SHOP)
    def event(self,topic,payload,at=None):
        identity=uuid.uuid4().hex
        receive_shopify(self.store,topic,identity,payload,at or self.clock)
        return self.store.q('SELECT * FROM crm_webhook_events WHERE event_id=%s',(identity,),True)
    def test_token_only_normalization_small_inbox_no_pii(self):
        event=self.event('checkouts/create',{'token':self.token,'id':999,'customer':{'id':self.customer['id']},'email':'private@example.test','line_items':[{'product_id':12,'title':'private'}]})
        self.assertEqual(event['object_id'],'checkout:'+self.key)
        self.assertEqual(event['normalized']['product_ids'],['gid://shopify/Product/12'])
        self.assertNotIn('private',json.dumps(event,default=str));self.assertNotIn(self.token,json.dumps(event,default=str))
        self.assertFalse(receive_shopify(self.store,'checkouts/create',event['event_id'],{'token':self.token},self.clock))
        with self.assertRaises(ValueError):self.event('checkouts/create',{'id':999,'cart_token':'unsafe'})
    def test_actual_subscribed_consent_version_only_once(self):
        from crm_automation_runtime import process_event
        a=self.published();self.clock=now()+timedelta(seconds=1);self.customer['emailMarketingConsent']['consentUpdatedAt']=self.clock.isoformat()
        payload={'customer_id':self.customer['id'],'email_marketing_consent':{'state':'subscribed','consent_updated_at':self.clock.isoformat()}}
        e=self.event('customers_email_marketing_consent/update',payload)
        process_event(self.engine,e,[a]);process_event(self.engine,self.event('customers_email_marketing_consent/update',payload),[a])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)
    def test_pending_and_unsubscribe_never_welcome(self):
        from crm_automation_runtime import process_event
        a=self.published();self.clock=now()+timedelta(seconds=1);self.customer['emailMarketingConsent']['consentUpdatedAt']=self.clock.isoformat()
        for state in ('pending','unsubscribed','not_subscribed'):
            e=self.event('customers_email_marketing_consent/update',{'customer_id':self.customer['id'],'email_marketing_consent':{'state':state}})
            process_event(self.engine,e,[a])
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
    def test_unchanged_subscribed_state_cannot_enter_new_flow(self):
        from crm_automation_runtime import process_event
        self.clock=now()+timedelta(seconds=1)
        initial={'customer_id':self.customer['id'],'email_marketing_consent':{'state':'subscribed','consent_updated_at':self.clock.isoformat()}}
        self.event('customers_email_marketing_consent/update',initial)
        a=self.published();self.clock=now()+timedelta(seconds=2);self.customer['emailMarketingConsent']['consentUpdatedAt']=self.clock.isoformat()
        later=deepcopy(initial);later['email_marketing_consent']['consent_updated_at']=self.clock.isoformat()
        event=self.event('customers_email_marketing_consent/update',later)
        self.assertTrue(event['normalized']['consent_unchanged']);process_event(self.engine,event,[a])
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
    def test_paid_and_fulfilled_sources_are_distinct_and_idempotent(self):
        from crm_automation_runtime import process_event
        a=self.published('post_purchase');b=self.published('fulfilled');self.clock=now()+timedelta(seconds=1)
        self.shop.order.return_value={'id':'gid://shopify/Order/456','createdAt':self.clock.isoformat(),'customer':{'id':self.customer['id']},'fullyPaid':True,'displayFulfillmentStatus':'FULFILLED'}
        for topic in ('orders/create','orders/paid','orders/paid','orders/fulfilled','orders/fulfilled'):
            process_event(self.engine,self.event(topic,{'id':456,'customer':{'id':self.customer['id']}}),[a,b])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=ANY(%s::uuid[])',([a['id'],b['id']],),True)['n'],2)
    def test_matching_order_recovers_and_blocks_pending_steps(self):
        from crm_automation_runtime import enter,advance
        a=self.published('abandoned');self.clock=now()+timedelta(seconds=1)
        self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']}})
        j=enter(self.engine,a,self.customer['id'],'gid://shopify/AbandonedCheckout/123','checkout:'+self.key,self.clock,checkout_key=self.key)
        self.store.enqueue('automation:'+str(j['id'])+':0',self.customer['id'],__import__('crm_logic').recipient_hash(self.customer['email']),{'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=0)
        self.event('orders/create',{'id':456,'checkout_token':self.token,'customer':{'id':self.customer['id']}})
        # Immediately persisted completion gate holds before async cancellation.
        self.assertEqual(self.engine.validate(self.customer['id'],j)[2],'recovered')
        recover(self.store,self.key)
        self.assertEqual(self.store.q('SELECT status,stop_reason FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True),{'status':'RECOVERED','stop_reason':'CHECKOUT_RECOVERED'})
        self.assertEqual(self.store.q('SELECT status FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)['status'],'BLOCKED')
        self.provider.send.assert_not_called()
    def test_late_checkout_update_cannot_undo_completion(self):
        self.event('orders/create',{'id':456,'checkout_token':self.token})
        self.event('checkouts/update',{'token':self.token})
        self.assertEqual(self.store.q('SELECT status FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)['status'],'RECOVERED')
    def test_recovery_after_claim_blocks_submission_boundary(self):
        from crm_automation_runtime import enter
        from crm_logic import recipient_hash
        a=self.published('abandoned');self.clock=now()+timedelta(seconds=1)
        self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']}})
        j=enter(self.engine,a,self.customer['id'],'gid://shopify/AbandonedCheckout/123','checkout:'+self.key,self.clock,checkout_key=self.key)
        self.store.enqueue('automation:'+str(j['id'])+':0',self.customer['id'],recipient_hash(self.customer['email']),{'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=0)
        self.store.q("UPDATE crm_automation_enrollments SET next_due_at=now()-interval '1 minute' WHERE id=%s",(j['id'],))
        self.store.q("UPDATE crm_marketing_sends SET due_at=now()-interval '1 minute' WHERE enrollment_id=%s",(j['id'],))
        row=self.store.claim_send();self.assertIsNotNone(row)
        self.event('orders/create',{'id':456,'checkout_token':self.token})
        self.assertIsNone(self.store.begin_send(row,'request-hash',recipient_hash(self.customer['email'])))
        self.provider.send.assert_not_called()
    def test_no_historical_checkout_enrollment_without_new_activity(self):
        from crm_automation_runtime import reconcile
        a=self.published('abandoned');self.clock=now()+timedelta(hours=2)
        # Shopify Admin is already the authoritative abandonment source. The old
        # fixture was created AFTER publication (clock + 59m), so it described a
        # new eligible abandon, not historical backlog. Both dates must be old.
        historical=(now()-timedelta(days=1)).isoformat()
        self.shop.checkouts.return_value={'nodes':[{'id':'gid://shopify/AbandonedCheckout/123','createdAt':historical,'updatedAt':historical,'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/'+self.token+'/recover','customer':{'id':self.customer['id']},'completedAt':None}],'pageInfo':{'hasNextPage':False}}
        reconcile(self.engine,a)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        # Signed but created before publication must not become a new audience.
        self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']},'created_at':(now()-timedelta(days=1)).isoformat()},now()-timedelta(hours=2))
        self.store.set_state('reconcile:native:'+str(a['id'])+':'+str(a['config']['published_version'])+':'+str(a['activated_at']),{})
        reconcile(self.engine,a)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
    def test_safe_logs_contain_hashes_not_tokens_or_payload(self):
        with self.assertLogs('crm_shopify_automation_events',level='INFO') as logs:
            self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']},'email':'private@example.test','note':'secret-payload'})
        text=' '.join(logs.output)
        self.assertIn(self.key,text)
        for private in (self.token,'private@example.test','secret-payload'):self.assertNotIn(private,text)
    def test_pixel_six_events_anonymous_no_journey_or_send(self):
        self.store.set_state('shopify_automation_pixel',{'id':'gid://shopify/WebPixel/1','settings':SETTINGS,'activated_at':(now()-timedelta(minutes=1)).isoformat()})
        before=self.store.q('SELECT count(*) n FROM crm_automation_enrollments',one=True)['n']
        for name in EVENTS:
            event={'event_id':uuid.uuid4().hex,'event_name':name,'client_id':'anonymous-client','product_id':'gid://shopify/Product/12','occurred_at':now().isoformat(),'shop':SHOP,'ingestionId':'a'*32,'analytics_allowed':True,'marketing_allowed':True}
            self.assertTrue(record(self.store,event));self.assertFalse(record(self.store,event))
            with self.assertRaises(ValueError):record(self.store,{**event,'email':'private@example.test'})
            with self.assertRaises(ValueError):record(self.store,{**event,'marketing_allowed':False})
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments',one=True)['n'],before);self.provider.send.assert_not_called()


class HttpTriggerTests(unittest.TestCase):
    def test_pixel_endpoint_context_validation_and_no_email_path(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        store=Mock();store.state.return_value={'id':'gid://shopify/WebPixel/1','settings':SETTINGS,'activated_at':now().isoformat(),'origins':['null']}
        with patch('crm_store.Store',return_value=store),patch('crm_shopify_pixel.record',return_value=True) as ingest:
            headers={'Origin':'null','Content-Type':'application/json'}
            self.assertEqual(client.options('/shopify/customer-events',headers=headers).status_code,204)
            self.assertEqual(client.post('/shopify/customer-events',json={'event_name':'product_viewed'},headers=headers).status_code,202)
            self.assertEqual(client.post('/shopify/customer-events',json={},headers={**headers,'Origin':'https://evil.example'}).status_code,403)
            self.assertEqual(client.post('/shopify/customer-events',content=b'x'*4097,headers=headers).status_code,400)
            self.assertEqual(ingest.call_count,1);store.enqueue.assert_not_called()
    def test_signed_token_webhook_ack_only_persists_no_external_io(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        raw=json.dumps({'token':'valid-checkout-token','customer':{'id':123}}).encode()
        headers={'x-shopify-topic':'checkouts/create','x-shopify-webhook-id':'event-1','x-shopify-shop-domain':SHOP,'x-shopify-triggered-at':now().isoformat(),'x-shopify-hmac-sha256':base64.b64encode(hmac.new(b'fixture-secret',raw,hashlib.sha256).digest()).decode()}
        with patch.dict(os.environ,{'SHOPIFY_WEBHOOK_SECRET':'fixture-secret','SHOPIFY_STORE_DOMAIN':SHOP},clear=True),patch('crm_store.Store'),patch('crm_shopify_automation_events.persist',return_value=True) as persist,patch('requests.sessions.Session.request',side_effect=AssertionError('External request')):
            self.assertEqual(client.post('/webhooks/shopify/crm',content=raw,headers=headers).status_code,200)
            self.assertEqual(client.post('/webhooks/shopify/crm',content=raw+b' ',headers=headers).status_code,401)
            self.assertEqual(persist.call_count,1)
            self.assertEqual(persist.call_args.args[3],'checkout:'+checkout_key('valid-checkout-token',SHOP))
