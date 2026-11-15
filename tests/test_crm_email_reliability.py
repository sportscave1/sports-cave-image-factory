"""Existing SQL queues/claims, disposable PostgreSQL, mocked providers only."""
from datetime import timedelta
import json
import os
import unittest
from unittest.mock import Mock,patch
from crm_logic import now,date
from crm_engine import Engine
from crm_campaign_progress import summarize,read_progress
from crm_campaign_schedule import schedule_gate
from crm_email_diagnostics import automation_status,campaign_status,worker_label
from tests import test_crm_batch_dispatch as batch
from tests import test_crm_campaign_v2 as campaigns
from tests import test_crm_checkout_queue_repair as checkout


class Labels(unittest.TestCase):
    def test_all_blocked_or_empty_is_not_sent(self):
        for counts in ({'BLOCKED':4},{'FAILED':4},{}):
            row=summarize({'status':'SENT','counts':counts})
            self.assertIn('needs attention',row['title']);self.assertTrue(row['attention'])
    def test_stale_worker_is_not_healthy(self):
        self.assertIn('stale',worker_label({'checked_at':(now()-timedelta(minutes=6)).isoformat()}))
        self.assertIn('No completed',worker_label({}))
    def test_campaign_home_does_not_call_zero_acceptance_sent(self):
        from crm_campaign_home import row_html
        from tests.test_crm_campaign_home import record
        row={**record(),'status':'SENT','submitted':0}
        self.assertIn('Needs attention',row_html(row))
        self.assertNotIn('>Sent<',row_html(row))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DeliveryCheckpoints(unittest.TestCase):
    def setUp(self):
        batch.DispatchTests.setUp(self)
        # Isolate delivery from journeys/campaigns left by other fixture suites.
        self.store.q("UPDATE crm_automations SET status='PAUSED' WHERE status='ACTIVE'")
        self.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE status IN ('SCHEDULED','SENDING','BUILDING')")
    tearDown=batch.DispatchTests.tearDown
    queue=batch.DispatchTests.queue
    sends=batch.DispatchTests.sends
    queued=campaigns.PersistenceAndSchedulingTests.queued

    def test_due_campaign_is_accepted_before_checkout_maintenance_and_not_replayed(self):
        identity=self.queue(2)
        def maintenance(*args,**kwargs):
            self.assertTrue(all(s['status']=='ACCEPTED' for s in self.sends(identity)))
            kwargs['checkpoint']()
        with patch('crm_automation_capabilities.verify'),patch('crm_automation_publication.tick'),\
             patch('crm_checkout_analytics.sync_cache',side_effect=maintenance),\
             patch('crm_campaign_attribution.reconcile'),patch('crm_consent_sync.reconcile_pending'):
            self.engine.tick('fixture-priority')
            self.engine.tick('fixture-priority')
        self.assertEqual(len(self.transport.calls),1)
        report=campaign_status(self.store,identity)
        self.assertEqual((report['accepted'],report['delivered']),(2,0))
        send=self.sends(identity)[0]
        for suffix in ('first','duplicate'):
            self.store.q("INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,'email.delivered',now(),%s)",
                         (str(send['id'])+suffix,send['provider_email_id'],send['id']))
        self.assertEqual(campaign_status(self.store,identity)['delivered'],1)
        self.assertEqual(self.store.q('SELECT status FROM crm_campaigns WHERE id=%s',(identity,),True)['status'],'SENT')

    def test_failed_source_cannot_stop_campaign_completion(self):
        identity=self.queue(1)
        with patch('crm_automation_capabilities.verify'),patch('crm_automation_publication.tick'),\
             patch('crm_checkout_analytics.sync_cache',side_effect=TimeoutError),\
             patch.object(type(self.store),'active_automations',return_value=[{'id':'fixture-flow','status':'ACTIVE'}]),\
             patch.object(self.engine,'reconcile',side_effect=TimeoutError),\
             patch('crm_campaign_attribution.reconcile'),patch('crm_consent_sync.reconcile_pending'):
            self.engine.tick('fixture-source-failure')
        self.assertEqual(self.sends(identity)[0]['status'],'ACCEPTED')
        self.assertEqual(len(self.transport.calls),1)

    def test_long_healthy_cycle_keeps_schedule_but_real_outage_stays_blocked(self):
        saved,_=self.queued();identity=saved['id'];self.ids.append(identity)
        job=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY due_at LIMIT 1',(identity,),True)
        at=date(job['due_at'])-timedelta(minutes=1)
        self.engine.clock=lambda:at
        self.engine.owner='fixture-checkpoints'
        self.assertTrue(self.store.lease(self.engine.owner))
        try:
            for _ in range(9):
                self.engine.hold_lease();at+=timedelta(minutes=1)
            self.assertEqual(self.store.receipt(job['id'])['status'],'PENDING')
            at+=timedelta(minutes=6);self.engine.hold_lease()
            self.assertEqual(self.store.receipt(job['id'])['error_code'],'schedule_missed')
            at+=timedelta(minutes=1);self.engine.hold_lease()
            self.assertEqual(self.store.receipt(job['id'])['status'],'BLOCKED')
            progress=read_progress(self.store,[identity])[str(identity)]
            self.assertIn('schedule_missed',progress['failures']['BLOCKED'])
            report=campaign_status(self.store,identity)
            self.assertEqual(len(report['zones']),2)
            self.assertEqual(report['timing']['time'],'07:00')
        finally:self.store.release(self.engine.owner);self.engine.owner=None

    def test_lost_worker_lease_cannot_dispatch(self):
        identity=self.queue(1);self.engine.owner='stale-worker'
        self.assertTrue(self.store.lease('actual-worker'))
        try:
            with self.assertRaisesRegex(RuntimeError,'lease changed'):self.engine.delivery_checkpoint(force=True)
            self.assertFalse(self.transport.calls)
            self.assertEqual(self.sends(identity)[0]['status'],'PENDING')
        finally:self.store.release('actual-worker');self.engine.owner=None


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class CheckoutCheckpoints(unittest.TestCase):
    setUp=checkout.QueueRepair.setUp
    published=checkout.QueueRepair.published
    candidates=checkout.QueueRepair.candidates
    automatic=checkout.QueueRepair.automatic
    def test_cache_yields_only_outside_transactions_and_records_completion(self):
        from crm_checkout_analytics import sync_cache
        a,keys,checkouts,profiles=self.candidates(3)
        self.shop.query.return_value={'abandonedCheckouts':{'nodes':list(checkouts.values()),'pageInfo':{'hasNextPage':False}}}
        self.store.set_state('checkout-cache-v2',{})
        started=now()-timedelta(minutes=2);completed=now();calls=[]
        def checkpoint():
            # A new real transaction must be safe at each callback.
            calls.append(self.store.q('SELECT count(*) AS n FROM crm_shopify_checkouts',one=True)['n'])
        with patch('crm_checkout_analytics.now',return_value=completed):
            sync_cache(self.shop,self.store,started,checkpoint=checkpoint)
        state=self.store.state('checkout-cache-v2')
        self.assertEqual(len(calls),3)
        self.assertEqual(date(state['last_synced_at']),completed)
        self.assertEqual(date(state['next_at']),started+timedelta(minutes=5))
        self.provider.send.assert_not_called()
    def test_diagnostics_published_steps_and_deadline_not_draft_or_queue_success(self):
        from crm_automation_runtime import reconcile
        a,key,_,_=self.automatic()
        reconcile(self.engine,a)
        report=automation_status(self.store,a)
        self.assertEqual(report['enrolled'],1);self.assertEqual(report['accepted'],0)
        self.assertIsNotNone(report['next_due'])
        self.assertEqual(report['steps'][0]['delay_seconds'],a['steps'][0]['delay_seconds'])
        self.assertIn('Added to flow',report['evaluations'])
        self.provider.send.assert_not_called()
