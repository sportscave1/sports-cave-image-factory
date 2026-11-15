"""Readiness recovery is tested offline; never start a delivery worker."""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock,patch
from datetime import timedelta
from crm_logic import now
from crm_engine import Engine,WorkerStopping
from crm_resend import Config
from tests.test_crm_send_flow import LIVE


class RecoveryTests(unittest.TestCase):
    def test_shutdown_releases_only_owned_lease_without_certifying_or_sending(self):
        store=Mock();store.lease.return_value=True
        engine=Engine(store,Mock(),config=Config(LIVE));engine.stop_requested=lambda:True
        with patch.object(engine,'send_one') as send:
            with self.assertRaises(WorkerStopping):engine.tick('owner')
        store.release.assert_called_once_with('owner')
        store.set_state.assert_not_called();send.assert_not_called()
        self.assertIsNone(engine.owner)

    def test_shutdown_at_delivery_boundary_does_not_claim_or_write_health(self):
        store=Mock();engine=Engine(store,Mock(),config=Config(LIVE));engine.owner='owner';engine.stop_requested=lambda:True
        with self.assertRaises(WorkerStopping):engine.delivery_checkpoint(force=True)
        store.lease.assert_not_called();store.set_state.assert_not_called();store.claim_send.assert_not_called()

    def test_readiness_reports_missing_topic_and_actual_work_age(self):
        from tests.test_crm_publication_readiness import ReadinessTests
        fixture=ReadinessTests();fixture.setUp()
        fixture.row['config']['draft']['emails'][0]['requires_fulfilment']=True
        state=fixture.values['shopify_automation_capabilities']
        state['webhooks']['ORDERS_FULFILLED']=False
        state['checks']={'ORDERS_FULFILLED':'MISSING'}
        fixture.values['worker_health']['checked_at']=(now()-timedelta(minutes=7)).isoformat()
        from crm_automation_readiness import blockers
        with patch('crm_lifecycle_products.selected',return_value=False),patch('crm_collector_images.configurations',return_value=[]):
            reasons=blockers(fixture.store,fixture.row,LIVE)
        self.assertTrue(any('ORDERS_FULFILLED — MISSING' in r for r in reasons))
        self.assertTrue(any('limit 300s' in r for r in reasons))
        self.assertFalse(any('start the existing CRM worker' in r for r in reasons))

    def test_single_topic_registration_is_idempotent_and_identity_checked(self):
        from scripts.register_crm_webhooks import main,QUERY
        from crm_automation_capabilities import CONNECTION
        from tests.test_crm_shopify_automation_triggers import CapabilitiesTests
        rows=[];created=[];identities=[]
        def query(doc,args):
            if doc==CONNECTION:
                identities.append(True);return CapabilitiesTests().shop().query(doc,{}),{}
            if doc==QUERY:return {'webhookSubscriptions':{'nodes':list(rows),'pageInfo':{'hasNextPage':False}}},{}
            created.append(args['topic'])
            rows.append({'id':'fixture','topic':args['topic'],'apiVersion':{'handle':'2026-04'},'endpoint':{'callbackUrl':args['webhookSubscription']['callbackUrl']}})
            return {'webhookSubscriptionCreate':{'userErrors':[]}},{}
        env={'SPORTS_CAVE_WEBHOOK_BASE_URL':'https://fixture.example','SHOPIFY_API_VERSION':'2026-04'}
        with patch.dict(os.environ,env,clear=True),patch('shopify_sync.graphql_request',side_effect=query),patch('crm_tracking_health.subscriptions',side_effect=lambda shop:list(rows)),redirect_stdout(io.StringIO()):
            main(['--topic','ORDERS_FULFILLED'])
            self.assertEqual(created,[])
            main(['--topic','ORDERS_FULFILLED','--apply']);main(['--topic','ORDERS_FULFILLED','--apply'])
        self.assertEqual(created,['ORDERS_FULFILLED']);self.assertEqual(len(identities),2)
        self.assertEqual(rows[0]['endpoint']['callbackUrl'],'https://fixture.example/webhooks/shopify/crm')

    def test_fulfilled_callback_authenticates_hmac_and_store_before_processing(self):
        import base64,hashlib,hmac
        from fastapi.testclient import TestClient
        import webhook_server
        raw=b'{"id":123,"fulfillment_status":"fulfilled"}'
        secret='offline-fixture-secret'
        signature=base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()
        headers={'X-Shopify-Hmac-Sha256':signature,'X-Shopify-Shop-Domain':'fixture.myshopify.com','X-Shopify-Topic':'orders/fulfilled','X-Shopify-Event-Id':'fixture-event'}
        with patch.dict(os.environ,{'SHOPIFY_WEBHOOK_SECRET':secret,'SHOPIFY_STORE_DOMAIN':'fixture.myshopify.com'},clear=True),patch('crm_store.Store'),patch('crm_webhooks.receive_shopify') as receive:
            client=TestClient(webhook_server.app)
            self.assertEqual(client.post('/webhooks/shopify/crm',content=raw,headers={**headers,'X-Shopify-Hmac-Sha256':'invalid'}).status_code,401)
            self.assertEqual(client.post('/webhooks/shopify/crm',content=raw,headers={**headers,'X-Shopify-Shop-Domain':'other.myshopify.com'}).status_code,403)
            receive.assert_not_called()
            self.assertEqual(client.post('/webhooks/shopify/crm',content=raw,headers=headers).status_code,200)
            self.assertEqual(receive.call_args.args[1],'orders/fulfilled')
            receive.assert_called_once()

    def test_stop_during_cycle_unwinds_instead_of_marking_delivery_failure(self):
        store=Mock();store.lease.return_value=True;store.state.return_value={'checked_at':now().isoformat()}
        stopping=False
        def inbox(*args,**kwargs):
            nonlocal stopping
            stopping=True
            return []
        store.q.side_effect=inbox
        engine=Engine(store,Mock(),config=Config(LIVE));engine.publication_background=True
        engine.stop_requested=lambda:stopping
        with patch('crm_campaign_schedule.schedule_gate'),patch.object(engine,'send_one') as send:
            with self.assertRaises(WorkerStopping):engine.tick('owner')
        store.release.assert_called_once_with('owner');send.assert_not_called()
        store.set_state.assert_not_called()
        self.assertFalse(issubclass(WorkerStopping,Exception),'Cancellation must bypass delivery error/retry handlers')
