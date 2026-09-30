"""Run with CRM_TEST_POSTGRES=1 and tests/crm_postgres_server.mjs on loopback."""
import os
import json
import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch
from tests.test_crm import config,ADMIN
from tests.crm_fixtures import ShopifyFixture,ResendFixture
from tests.crm_db_fixture import connect
from crm_store import Store,StoreUnavailable
from crm_shopify import Shopify,gid
from crm_engine import Engine
from crm_logic import now,recipient_hash,consent,rule
from crm_webhooks import receive_shopify,receive_resend,unsubscribe
from email_service import EmailDeliveryError

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Start isolated PostgreSQL fixture explicitly.')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(connect)
        self.store.q('TRUNCATE crm_marketing_events,crm_suppressions,crm_webhook_events,crm_runtime_state,crm_marketing_sends,crm_campaigns,crm_automation_enrollments,crm_automations,crm_template_versions,crm_templates,crm_segment_definitions CASCADE')
        self.store.seed();self.wire=ShopifyFixture(5);self.shop=Shopify(self.wire);self.provider=ResendFixture()
        self.engine=Engine(self.store,self.shop,self.provider,config())
        self.template=next(t for t in self.store.list('templates') if t['template_key']=='product_launch')
    def queue(self,test=False):
        return self.store.enqueue('test-'+str(uuid.uuid4()),gid(1) if not test else None,recipient_hash('collector1@example.test'),self.template,test_recipient='tester@example.test' if test else None)
    def automation(self,kind):
        row=next(a for a in self.store.list('automations') if a['trigger_type']==kind)
        self.store.save_automation(row['id'],row['steps'],row['config'],'ACTIVE')
        self.store.q("UPDATE crm_automations SET activated_at=now()-interval '10 days' WHERE id=%s",(row['id'],))
        return self.store.get('automations',row['id'])
    def test_seed_drafts_and_rls(self):
        self.store.seed();self.assertEqual(len(self.store.list('templates')),9);self.assertEqual(len(self.store.list('segments')),17)
        self.assertTrue(all(a['status']=='DRAFT' for a in self.store.list('automations')))
        rows=self.store.q("SELECT relname,relrowsecurity FROM pg_class WHERE relname LIKE 'crm_%' AND relkind='r'")
        self.assertEqual(len(rows),20);self.assertTrue(all(r['relrowsecurity'] for r in rows))
    def test_template_version_immutable(self):
        original=self.store.template(self.template['id'],1);content=dict(original);content['headline']='Edited'
        updated=self.store.save_template(self.template['id'],'Edited',content)
        self.assertEqual(updated['version'],2);self.assertEqual(self.store.template(self.template['id'],1),original)
    def test_send_fresh_consent_no_customer_body_storage(self):
        row=self.queue();self.engine.send_one()
        receipt=self.store.receipt(row['id']);self.assertEqual(receipt['status'],'ACCEPTED');self.assertEqual(len(self.provider.sent),1)
        self.assertNotIn('collector1@example.test',json.dumps(receipt,default=str));self.assertNotIn('<html',json.dumps(receipt,default=str))
        self.assertFalse(self.engine.send_one());self.assertEqual(len(self.provider.sent),1)
    def test_stale_positive_consent_denied_at_execution(self):
        self.shop.customer(1);row=self.queue();self.wire.customers[0]['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        self.engine.send_one();self.assertEqual(self.store.receipt(row['id'])['status'],'BLOCKED');self.assertEqual(self.provider.sent,[])
    def test_provider_suppression_blocks(self):
        row=self.queue();self.provider.blocked=True;self.engine.send_one();self.assertEqual(self.store.receipt(row['id'])['status'],'BLOCKED')
        self.assertTrue(self.store.suppressed(gid(1),recipient_hash('collector1@example.test')))
    def test_missing_consent_blocks(self):
        row=self.queue();self.wire.customers[0]['emailMarketingConsent']=None;self.engine.send_one()
        self.assertEqual(self.store.receipt(row['id'])['status'],'BLOCKED')
    def test_api_failure_defers_without_send(self):
        row=self.queue();self.wire.fail=TimeoutError('secret');self.engine.send_one()
        receipt=self.store.receipt(row['id']);self.assertEqual(receipt['status'],'PENDING');self.assertNotIn('secret',json.dumps(receipt,default=str))
    def test_uncertain_never_retried(self):
        row=self.queue();self.provider.error=TimeoutError('private');self.engine.send_one()
        self.assertEqual(self.store.receipt(row['id'])['status'],'UNCERTAIN');self.engine.send_one();self.assertEqual(len(self.provider.sent),1)
    def test_known_rejection_failed(self):
        row=self.queue();self.provider.error=EmailDeliveryError('Rejected',status_code=422);self.engine.send_one()
        self.assertEqual(self.store.receipt(row['id'])['status'],'FAILED')
    def test_crash_before_submission_reclaim_after_lease(self):
        row=self.queue();first=self.store.claim_send();self.assertIsNone(self.store.claim_send())
        self.store.q("UPDATE crm_marketing_sends SET lease_until=now()-interval '1 second' WHERE id=%s",(row['id'],))
        second=self.store.claim_send();self.assertNotEqual(first['lease_token'],second['lease_token'])
        self.assertIsNone(self.store.begin_send(first,'hash',first['recipient_hash']))
        self.assertIsNotNone(self.store.begin_send(second,'hash',second['recipient_hash']))
    def test_crash_after_submission_holds(self):
        row=self.queue();claim=self.store.claim_send();self.store.begin_send(claim,'hash',claim['recipient_hash'])
        self.store.q("UPDATE crm_marketing_sends SET lease_until=now()-interval '1 second' WHERE id=%s",(row['id'],))
        self.assertIsNone(self.store.claim_send());self.assertEqual(self.store.receipt(row['id'])['status'],'UNCERTAIN')
    def test_campaign_recipient_minimal_and_email_dedupe(self):
        definition=self.store.save_segment('All',rule('consent','SUBSCRIBED'),'fixture')
        campaign=self.store.save_campaign('Fixture',self.template,definition_id=definition['id'])
        self.store.q("UPDATE crm_campaigns SET status='BUILDING' WHERE id=%s",(campaign['id'],))
        self.wire.customers[3]['email']=self.wire.customers[0]['email']
        self.engine.campaign_page(campaign)
        sends=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(campaign['id'],))
        self.assertEqual(len(sends),2);self.assertNotIn('Collector',json.dumps(sends,default=str));self.assertNotIn('@example.test',json.dumps(sends,default=str))
        self.engine.campaign_page(campaign);self.assertEqual(len(self.store.q('SELECT * FROM crm_marketing_sends')),2)
    def test_native_campaign_resolves_live(self):
        campaign=self.store.save_campaign('Native',self.template,segment_id=gid(1,'Segment'))
        self.store.q("UPDATE crm_campaigns SET status='BUILDING' WHERE id=%s",(campaign['id'],));self.engine.campaign_page(campaign)
        self.assertEqual(self.store.get('campaigns',campaign['id'])['status'],'SENDING')
        self.assertEqual(len(self.store.q('SELECT * FROM crm_marketing_sends')),3)
    def test_lease_two_workers_fenced(self):
        self.assertTrue(self.store.lease('one'));self.assertFalse(self.store.lease('two'));self.store.release('two');self.assertFalse(self.store.lease('two'))
        self.store.release('one');self.assertTrue(self.store.lease('two'))
    def test_checkout_recovered_and_new_paid_order_stop(self):
        a=self.automation('abandoned');e=self.store.enroll(a,gid(1),gid(1,'AbandonedCheckout'),'one',now()-timedelta(hours=2))
        self.wire.checkouts[0]['completedAt']=now().isoformat();self.assertEqual(self.engine.validate(gid(1),e)[2],'recovered')
        self.wire.checkouts[0]['completedAt']=None;self.wire.orders[gid(1)][0]['createdAt']=now().isoformat();self.assertEqual(self.engine.validate(gid(1),e)[2],'recovered')
    def test_abandoned_reconciliation_delays_and_dedupe(self):
        a=self.automation('abandoned');self.engine.reconcile(a);self.store.set_state('reconcile:abandoned',{});self.engine.reconcile(a)
        rows=self.store.q('SELECT * FROM crm_automation_enrollments');self.assertEqual(len(rows),1)
        e=rows[0];self.engine.advance(e);updated=self.store.q('SELECT * FROM crm_automation_enrollments',one=True);self.assertEqual(updated['current_step'],1)
    def test_welcome_only_consent_event(self):
        a=self.automation('welcome');timestamp=now();self.wire.customers[0]['emailMarketingConsent']['consentUpdatedAt']=timestamp.isoformat()
        event={'topic':'customers/create','related_customer_id':gid(1),'object_id':gid(1),'occurred_at':timestamp}
        self.engine.process_event(event);self.assertEqual(self.store.q('SELECT * FROM crm_automation_enrollments'),[])
        event['topic']='customers_email_marketing_consent/update';self.engine.process_event(event);self.engine.process_event(event)
        self.assertEqual(len(self.store.q('SELECT * FROM crm_automation_enrollments')),1)
    def test_pre_activation_event_does_not_enroll(self):
        a=self.automation('welcome');timestamp=now()-timedelta(days=20);self.wire.customers[0]['emailMarketingConsent']['consentUpdatedAt']=timestamp.isoformat()
        self.engine.process_event({'topic':'customers_email_marketing_consent/update','related_customer_id':gid(1),'object_id':gid(1),'occurred_at':timestamp})
        self.assertEqual(self.store.q('SELECT * FROM crm_automation_enrollments'),[])
    def test_winback_rechecks_recent_purchase(self):
        a=self.automation('win_back');e=self.store.enroll(a,gid(1),gid(1,'Order'),'one',now())
        self.assertEqual(self.engine.validate(gid(1),e)[2],'recent_purchase')
        self.wire.customers[0]['lastOrder']['createdAt']=(now()-timedelta(days=200)).isoformat();self.assertEqual(self.engine.validate(gid(1),e)[2],'')
    def test_post_purchase_queries_order_id(self):
        a=self.automation('post_purchase');o=self.wire.orders[gid(1)][0]
        self.engine.process_event({'topic':'orders/updated','related_customer_id':gid(1),'object_id':o['id'],'occurred_at':now()})
        e=self.store.q('SELECT * FROM crm_automation_enrollments',one=True);self.assertEqual(e['trigger_shopify_id'],o['id'])
        o['cancelledAt']=now().isoformat();self.assertEqual(self.engine.validate(gid(1),e)[2],'order_ineligible')
    def test_webhook_dedupe_invalidation_no_raw_payload(self):
        payload={'id':1,'email':'private@example.test','note':'private body'}
        self.assertTrue(receive_shopify(self.store,'customers/update','evt1',payload,now()))
        old=self.store.state('cache_version');self.assertFalse(receive_shopify(self.store,'customers/update','evt1',payload,now()))
        self.assertNotEqual(old,self.store.state('cache_version'))
        self.assertNotIn('private',json.dumps(self.store.q('SELECT * FROM crm_webhook_events'),default=str))
    def test_resend_events_deduped_and_reports(self):
        row=self.queue();self.engine.send_one();receipt=self.store.receipt(row['id'])
        provider_id=str(uuid.uuid4())
        self.store.q('UPDATE crm_marketing_sends SET provider_email_id=%s WHERE id=%s',(provider_id,row['id']))
        for event in ('sent','delivered','opened','clicked','bounced','complained','delivery_delayed'):
            payload={'type':'email.'+event,'created_at':now().isoformat(),'data':{'email_id':provider_id,'to':['collector1@example.test'],'html':'never stored','bounce':{'type':'Permanent'}}}
            receive_resend(self.store,event,payload);receive_resend(self.store,event,payload)
        self.assertEqual(len(self.store.q('SELECT * FROM crm_marketing_events')),7)
        summary,_,_=self.store.reports();self.assertEqual(summary['delivered'],1);self.assertEqual(summary['bounces'],1)
    def test_unsubscribe_local_immediate_provider_sync(self):
        row=self.queue();self.engine.send_one();token=config().unsubscribe_url(row['id']).split('token=')[1]
        unsubscribe(self.store,config(),token,self.shop)
        self.assertTrue(self.store.suppressed(gid(1),recipient_hash('collector1@example.test')))
        self.engine.tick('fixture');self.assertTrue(self.store.q('SELECT provider_synced FROM crm_suppressions',one=True)['provider_synced'])
    def test_full_tick_drafts_no_delivery(self):
        result=self.engine.tick('fixture');self.assertTrue(result['leader']);self.assertEqual(self.provider.sent,[])
    def test_pause_during_validation_fences_submission_and_resume_keeps_receipt(self):
        campaign=self.store.save_campaign('Pause test',self.template,segment_id=gid(1,'Segment'))
        self.store.q("UPDATE crm_campaigns SET status='SENDING' WHERE id=%s",(campaign['id'],))
        self.store.enqueue('pause-receipt',gid(1),recipient_hash('collector1@example.test'),self.template,campaign_id=campaign['id'])
        claim=self.store.claim_send();self.store.pause_campaign(campaign['id'])
        self.assertIsNone(self.store.begin_send(claim,'hash',claim['recipient_hash']))
        self.store.resume_campaign(campaign['id'])
        self.assertEqual(self.store.get('campaigns',campaign['id'])['status'],'SENDING')
        self.assertEqual(len(self.store.q('SELECT * FROM crm_marketing_sends')),1)
    def test_test_only_gate_does_not_claim_customer_queue(self):
        self.queue();self.assertIsNone(self.store.claim_send(allow_customer=False,allow_test=True))
    def test_pending_payment_order_also_stops_abandonment(self):
        a=self.automation('abandoned');e=self.store.enroll(a,gid(1),gid(1,'AbandonedCheckout'),'pending',now())
        self.wire.orders[gid(1)][0].update(createdAt=now().isoformat(),fullyPaid=False)
        self.assertEqual(self.engine.validate(gid(1),e)[2],'recovered')
    def test_editions_read_only_query(self):
        self.assertEqual(self.store.editions(gid(1),'collector1@example.test'),[])

if __name__=='__main__':unittest.main()
