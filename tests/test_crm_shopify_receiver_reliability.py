"""Local signed fixtures only: no live subscriptions, allocations or emails."""
import base64
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from crm_shopify_webhook_config import base_url, callbacks, hmac_configuration, receiver_readiness, CANONICAL_BASE
from crm_shopify_webhook_config import receiver_callback_status
from tests import test_crm_automation_diagnostics as diagnostics_fixture
from tests import test_crm_shopify_automation_triggers as trigger_fixture


class ReceiverTests(unittest.TestCase):
    def test_shared_secret_prefix_is_not_an_admin_token(self):
        import webhook_server as server
        raw=b'{"token":"checkout-token-only"}'
        for name in ('SHOPIFY_WEBHOOK_SECRET','SHOPIFY_CLIENT_SECRET','SHOPIFY_SHARED_SECRET'):
            secret='shpss_real-app-secret-fixture'
            headers={'X-Shopify-Hmac-Sha256':base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()}
            with patch.dict(os.environ,{name:secret},clear=True):
                self.assertEqual(hmac_configuration(),'CONFIGURED')
                self.assertTrue(server.verify_shopify_webhook_hmac(raw,headers)['ok'])
                self.assertFalse(server.verify_shopify_webhook_hmac(raw+b' ',headers)['ok'])
                self.assertFalse(server.verify_shopify_webhook_hmac(raw,{})['ok'])
                self.assertFalse(server.verify_shopify_webhook_hmac(raw,{'X-Shopify-Hmac-Sha256':'invalid'})['ok'])
                self.assertFalse(server.verify_shopify_webhook_hmac(raw,{'X-Shopify-Hmac-Sha256':'é'})['ok'])
                from shopify_sync import verify_shopify_webhook_hmac as standalone
                self.assertTrue(standalone(raw,headers['X-Shopify-Hmac-Sha256'],secret))
                self.assertFalse(standalone(raw,'é',secret))

    def test_admin_access_tokens_never_verify_even_if_signature_matches(self):
        from webhook_server import verify_shopify_webhook_hmac
        for prefix in ('shpat_','shpca_','shppa_'):
            secret=prefix+'invalid-signing-key';raw=b'{}'
            signature=base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()
            with patch.dict(os.environ,{'SHOPIFY_WEBHOOK_SECRET':secret},clear=True):
                self.assertIn('MALFORMED',hmac_configuration())
                self.assertFalse(verify_shopify_webhook_hmac(raw,{'X-Shopify-Hmac-Sha256':signature})['ok'])
                from shopify_sync import verify_shopify_webhook_hmac as standalone
                self.assertFalse(standalone(raw,signature,secret))

    def test_valid_shared_fallback_survives_malformed_preferred_value(self):
        with patch.dict(os.environ,{'SHOPIFY_WEBHOOK_SECRET':'shpat_not-a-secret','SHOPIFY_SHARED_SECRET':'shared-secret'},clear=True):
            self.assertEqual(hmac_configuration(),'CONFIGURED')

    def test_base_precedence_and_production_service_default(self):
        self.assertEqual(base_url({'RENDER':'true'}),CANONICAL_BASE)
        self.assertEqual(base_url({'RENDER_EXTERNAL_URL':'https://ui.example'}),'')
        self.assertEqual(base_url({'SPORTS_CAVE_WEBHOOK_BASE_URL':' https://receiver.example/ ', 'CRM_PUBLIC_BASE_URL':'https://fallback.example'}),'https://receiver.example')
        self.assertEqual(base_url({'CRM_PUBLIC_BASE_URL':'https://fallback.example'}),'https://fallback.example')
        for value in ('http://localhost','https://receiver.example/path','https://receiver.example?secret=x','https://u:p@receiver.example','https://127.0.0.1','https://[broken'):
            self.assertEqual(base_url({'SPORTS_CAVE_WEBHOOK_BASE_URL':value,'RENDER':'true'}),'')

    def test_public_receiver_report_has_no_secrets_or_external_work(self):
        import webhook_server as server
        env={'RENDER':'true','SHOPIFY_WEBHOOK_SECRET':'shpss_private','SHOPIFY_SHARED_SECRET':'different-private','SHOPIFY_ADMIN_ACCESS_TOKEN':'shpat_private'}
        with patch.dict(os.environ,env,clear=True),patch.object(server,'_SHOPIFY_HMAC_VERIFIED',False),patch('crm_store.Store',side_effect=AssertionError('No DB')),patch('requests.get',side_effect=AssertionError('No network')):
            response=TestClient(server.app).get('/webhooks/shopify/readiness')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            report=response.json();self.assertEqual(report['hmac_status'],'CONFIGURED')
            self.assertTrue(report['routes_ready']);self.assertEqual(report['base_url'],CANONICAL_BASE)
            for secret in env.values():
                if secret.startswith(('shpss_','shpat_','different-')):self.assertNotIn(secret,response.text)
            with patch.object(server,'_SHOPIFY_HMAC_VERIFIED',True):
                self.assertEqual(TestClient(server.app).get('/webhooks/shopify/readiness').json()['hmac_status'],'VERIFIED')

    def report(self):
        return {'service':'sports-cave-os-webhooks','base_url':CANONICAL_BASE,
                'callbacks':callbacks({'RENDER':'true'}),'api_version':'2026-04',
                'routes_ready':True,'hmac_status':'CONFIGURED'}

    def test_remote_readiness_bounded_no_redirect_and_schema_validation(self):
        good=self.report()
        for change in ({},{'service':'other'},{'base_url':'https://wrong.example'},
                       {'api_version':'2025-10'},{'routes_ready':False},{'hmac_status':'YES'}):
            wire=Mock(status_code=200,content=b'{}',json=lambda:{**good,**change})
            with patch('requests.get',return_value=wire) as request:
                if change and ('service' in change or 'hmac_status' in change):
                    with self.assertRaises(ValueError):receiver_readiness({'RENDER':'true'})
                elif change:
                    report=receiver_readiness({'RENDER':'true'})
                    self.assertNotEqual(receiver_callback_status(report,{'RENDER':'true'}),'VERIFIED')
                else:self.assertEqual(receiver_readiness({'RENDER':'true'}),good)
                self.assertEqual(request.call_args.kwargs,{'timeout':(3,5),'allow_redirects':False})
        for code,body in ((302,b'{}'),(503,b'{}'),(200,b'x'*4097)):
            with patch('requests.get',return_value=Mock(status_code=code,content=body)):
                with self.assertRaises(ValueError):receiver_readiness({'RENDER':'true'})

    def test_os_and_worker_use_receiver_not_their_local_secret_environment(self):
        from crm_automation_capabilities import verify
        from tests.test_crm_shopify_automation_triggers import CapabilitiesTests
        hooks=diagnostics_fixture.DiagnosticTests().hooks()
        for row in hooks:row['endpoint']['callbackUrl']=CANONICAL_BASE+'/webhooks/shopify/crm'
        with patch.dict(os.environ,{'RENDER':'true','SHOPIFY_CLIENT_SECRET':'shpat_wrong'},clear=True),patch('crm_tracking_health.subscriptions',return_value=hooks),patch('crm_shopify_webhook_config.receiver_readiness',return_value=self.report()) as remote:
            report=verify(CapabilitiesTests().shop(),Mock())
            self.assertEqual(report['triggers']['abandoned'],'AVAILABLE')
            self.assertEqual(report['checks']['Webhook HMAC'],'CONFIGURED');remote.assert_called_once()
            remote.side_effect=RuntimeError('secret provider body')
            report=verify(CapabilitiesTests().shop(),Mock())
            self.assertNotEqual(report['triggers']['abandoned'],'AVAILABLE')
            self.assertNotIn('secret provider body',json.dumps(report))
            self.assertEqual(report['checks']['ORDERS_CREATE'],'CALLBACK CONFIGURATION UNVERIFIED')

    def test_invalid_base_does_not_falsely_blame_existing_subscription(self):
        report=diagnostics_fixture.DiagnosticTests().report(env={'SHOPIFY_WEBHOOK_SECRET':'shpss_valid'})
        self.assertEqual(report['checks']['ORDERS_CREATE'],'CALLBACK CONFIGURATION UNVERIFIED')
        self.assertEqual(report['checks']['Webhook HMAC'],'CONFIGURED')

    def test_duplicate_subscription_is_distinguished_without_mutation(self):
        hooks=diagnostics_fixture.DiagnosticTests().hooks();hooks.append(dict(hooks[0]))
        report=diagnostics_fixture.DiagnosticTests().report(hooks=hooks)
        self.assertTrue(report['webhook_details'][hooks[0]['topic']]['duplicate'])
        self.assertEqual(report['checks'][hooks[0]['topic']],'VERIFIED')

    def test_abandoned_setup_only_creates_missing_topics_once(self):
        import io
        from contextlib import redirect_stdout
        from scripts.register_crm_webhooks import main,QUERY
        from crm_automation_capabilities import CONNECTION
        from tests.test_crm_shopify_automation_triggers import CapabilitiesTests
        rows=[{'id':'paid','topic':'ORDERS_PAID','apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':CANONICAL_BASE+'/webhooks/shopify/orders-paid'}},
              {'id':'created','topic':'ORDERS_CREATE','apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':CANONICAL_BASE+'/webhooks/shopify/crm'}}]
        created=[]
        def query(doc,args):
            if doc==CONNECTION:return CapabilitiesTests().shop().query(doc,{}),{}
            if doc==QUERY:return {'webhookSubscriptions':{'nodes':list(rows),'pageInfo':{'hasNextPage':False}}},{}
            created.append(args['topic'])
            rows.append({'id':str(len(rows)),'topic':args['topic'],'apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':args['webhookSubscription']['callbackUrl']}})
            return {'webhookSubscriptionCreate':{'userErrors':[]}},{}
        env={'SPORTS_CAVE_WEBHOOK_BASE_URL':CANONICAL_BASE,'SHOPIFY_API_VERSION':'2026-04'}
        with patch.dict(os.environ,env,clear=True),patch('shopify_sync.graphql_request',side_effect=query),patch('crm_tracking_health.subscriptions',side_effect=lambda shop:list(rows)),redirect_stdout(io.StringIO()):
            main(['--abandoned-only','--apply']);main(['--abandoned-only','--apply'])
        self.assertEqual(set(created),{'CHECKOUTS_CREATE','CHECKOUTS_UPDATE'});self.assertEqual(len(created),2)

    def test_registration_mismatch_duplicate_and_old_version_never_create_or_delete(self):
        import io
        from contextlib import redirect_stdout
        from scripts.register_crm_webhooks import main,QUERY
        from crm_automation_capabilities import CONNECTION
        from tests.test_crm_shopify_automation_triggers import CapabilitiesTests
        rows=diagnostics_fixture.DiagnosticTests().hooks()
        rows[0]['endpoint']['callbackUrl']='https://old.example/unrelated'
        rows.append(dict(rows[0]));rows[1]['apiVersion']['handle']='2025-10'
        def query(doc,args):
            if doc==CONNECTION:return CapabilitiesTests().shop().query(doc,{}),{}
            self.assertEqual(doc,QUERY)
            return {'webhookSubscriptions':{'nodes':rows,'pageInfo':{'hasNextPage':False}}},{}
        with patch.dict(os.environ,{'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example','SHOPIFY_API_VERSION':'2026-04'},clear=True),patch('shopify_sync.graphql_request',side_effect=query),redirect_stdout(io.StringIO()) as output:
            main(['--automation-only','--apply'])
        self.assertIn('duplicate subscriptions',output.getvalue());self.assertIn('review',output.getvalue())

    def test_paid_conversion_committed_before_allocation_and_ack_or_retry(self):
        import webhook_server as server
        payload={'id':456,'checkout_token':'valid-checkout-token'};raw=json.dumps(payload).encode();order=[]
        with patch.object(server,'verify_shopify_webhook_hmac',return_value={'ok':True}),patch('crm_store.Store'),patch('crm_webhooks.receive_shopify',side_effect=lambda *a:order.append('conversion')),patch.object(server,'_process_paid_order_durably',side_effect=lambda *a:order.append('allocation') or {'state':'duplicate'}),patch('crm_webhooks.forward_paid_order'):
            response=TestClient(server.app).post('/webhooks/shopify/orders-paid',content=raw,headers={'X-Shopify-Event-Id':'event-1'})
            self.assertEqual(response.status_code,200);self.assertEqual(order,['conversion','allocation'])
        with patch.object(server,'verify_shopify_webhook_hmac',return_value={'ok':True}),patch('crm_store.Store'),patch('crm_webhooks.receive_shopify',side_effect=RuntimeError('private')),patch.object(server,'_process_paid_order_durably') as allocate:
            response=TestClient(server.app).post('/webhooks/shopify/orders-paid',content=raw,headers={'X-Shopify-Event-Id':'event-1'})
            self.assertEqual(response.status_code,503);allocate.assert_not_called();self.assertNotIn('private',response.text)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback Postgres required')
class CheckoutLedgerTests(unittest.TestCase):
    setUp=trigger_fixture.TriggerTests.setUp
    published=trigger_fixture.TriggerTests.published
    event=trigger_fixture.TriggerTests.event

    def test_fresh_admin_checkout_must_match_enrollment_token_not_just_customer(self):
        from crm_automation_runtime import enter
        from crm_logic import now
        from datetime import timedelta
        automation=self.published('abandoned');self.clock=now()+timedelta(seconds=1)
        self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']}})
        enrollment=enter(self.engine,automation,self.customer['id'],'gid://shopify/AbandonedCheckout/123','checkout:'+self.key,self.clock,checkout_key=self.key)
        self.shop.checkout.return_value={'id':enrollment['trigger_shopify_id'],'customer':{'id':self.customer['id']},
            'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/another-token/recover'}
        self.assertEqual(self.engine.validate(self.customer['id'],enrollment)[2],'checkout_identity_changed')
        self.provider.send.assert_not_called()

    def test_create_update_retry_and_old_ids_use_one_token_ledger(self):
        from crm_webhooks import receive_shopify
        from crm_logic import now
        from datetime import timedelta
        first=self.event('checkouts/create',{'token':self.token,'id':999,'customer':{'id':self.customer['id']}})
        later=self.clock+timedelta(minutes=5)
        second=self.event('checkouts/update',{'token':self.token,'id':1234,'updated_at':later.isoformat()})
        self.assertFalse(receive_shopify(self.store,'checkouts/update',second['event_id'],{'token':self.token},later))
        row=self.store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)
        from crm_logic import date
        self.assertLess(abs((date(row['activity_at'])-later).total_seconds()),0.001)
        self.assertEqual(row['source_event_id'],second['event_id'])
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)['n'],1)
        # Old checkout_id alone must never convert an unrelated token record.
        self.event('orders/create',{'id':456,'checkout_id':999})
        self.assertEqual(self.store.q('SELECT status FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)['status'],'OPEN')
        order=self.event('orders/paid',{'id':456,'checkout_token':self.token})
        self.assertFalse(receive_shopify(self.store,'orders/paid',order['event_id'],{'id':456,'checkout_token':self.token},now()))
        self.event('checkouts/update',{'token':self.token,'updated_at':(later+timedelta(minutes=1)).isoformat()})
        self.assertEqual(self.store.q('SELECT status FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)['status'],'RECOVERED')
