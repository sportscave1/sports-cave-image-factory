"""Offline persisted attribution health recovery; no database or Shopify writes."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import Mock, patch

from crm_campaign_attribution import reconcile
from crm_engine import Engine
from crm_logic import now
from crm_resend import Config
from crm_tracking_health import observations


class AttributionHealthRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.at=now()
        self.scan={'error':'source_unavailable','watermark':'saved-watermark',
                   'next_at':(self.at+timedelta(minutes=5)).isoformat(),
                   'cursor':'saved-cursor','pending':['saved-order'],
                   'start':(self.at-timedelta(hours=1)).isoformat(),'end':self.at.isoformat(),
                   'more':True}
        self.states={'email_attribution_scan':deepcopy(self.scan)}
        self.due=[{'shopify_order_id':'due-order'}]
        self.active=self.at-timedelta(days=1)
        self.store=Mock()
        self.store.lease.return_value=True
        self.store.state.side_effect=lambda key:deepcopy(self.states.get(key,{}))
        self.store.set_state.side_effect=lambda key,value:self.states.update({key:deepcopy(value)})
        def query(sql,*args,**kwargs):
            if sql.startswith('SELECT shopify_order_id FROM crm_order_attribution'):return self.due
            if 'min(sending_started_at)' in sql:return {'first':self.active}
            if 'max(received_at)' in sql:return {'shopify':None,'resend':None}
            return []
        self.store.q.side_effect=query
        self.shop=Mock()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.fetch=self.stack.enter_context(patch('crm_attribution_shopify.order',return_value={'id':'due-order'}))
        self.updated=self.stack.enter_context(patch('crm_attribution_shopify.updated'))
        self.record=self.stack.enter_context(patch('crm_campaign_attribution.record',return_value=None))
        self.mirror=self.stack.enter_context(patch('crm_campaign_attribution.mirror'))
        self.stack.enter_context(patch('crm_campaign_schedule.schedule_gate'))
        self.stack.enter_context(patch('crm_consent_sync.reconcile_pending'))
        self.stack.enter_context(patch('crm_tracking_health.now',return_value=self.at))

    def tick(self):
        Engine(self.store,self.shop,config=Config({}),clock=lambda:self.at).tick('fixture-owner')

    def assert_recovered(self):
        self.assertEqual(self.states['email_attribution_scan'],
                         {key:value for key,value in self.scan.items() if key!='error'})
        self.assertEqual(self.states['email_reconcile_health'],{'last_run':self.at.isoformat()})
        status=observations(self.store)['Attribution reconcile']
        self.assertTrue(status.startswith('RECENT'),status)
        self.assertIn(self.at.isoformat(),status)
        for call in self.store.q.call_args_list:
            sql=call.args[0].upper()
            self.assertNotIn('DELETE',sql)
            self.assertNotIn('TRUNCATE',sql)

    def test_failure_then_due_order_recovery_during_scan_backoff(self):
        self.fetch.side_effect=ConnectionError('synthetic outage')
        with self.assertLogs('crm_engine',level='WARNING'):
            self.tick()
        self.assertEqual(self.states['email_attribution_scan']['error'],'source_unavailable')
        self.assertNotIn('email_reconcile_health',self.states)
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
        self.fetch.side_effect=None
        self.tick()
        self.assert_recovered()
        self.assertEqual(self.states['email_journey_health'],{'verified_at':self.at.isoformat()})
        self.updated.assert_not_called()
        # A fresh failure must override the previous successful health timestamp.
        self.fetch.side_effect=ConnectionError('new outage')
        with self.assertLogs('crm_engine',level='WARNING'):
            self.tick()
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')

    def test_success_without_active_campaigns_clears_only_error(self):
        self.active=None
        self.tick()
        self.assert_recovered()
        self.updated.assert_not_called()

    def test_successful_idle_pass_without_campaigns_clears_historical_error(self):
        self.active=None;self.due=[]
        self.tick()
        self.assert_recovered()
        self.fetch.assert_not_called()
        self.record.assert_not_called()

    def test_idle_backoff_with_active_campaign_does_not_hide_current_error(self):
        self.due=[]
        self.tick()
        self.assertEqual(self.states['email_attribution_scan'],self.scan)
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
        self.assertNotIn('email_reconcile_health',self.states)
        self.fetch.assert_not_called()
        self.updated.assert_not_called()

    def test_incremental_scan_failure_does_not_record_success(self):
        self.due=[]
        self.states['email_attribution_scan']={'error':'source_unavailable'}
        self.updated.side_effect=ConnectionError('scan outage')
        with self.assertLogs('crm_engine',level='WARNING'):
            self.tick()
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
        self.assertNotIn('email_reconcile_health',self.states)
        self.updated.side_effect=None
        self.updated.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
        self.at+=timedelta(minutes=6)
        self.tick()
        self.assertNotIn('error',self.states['email_attribution_scan'])
        self.assertEqual(self.states['email_reconcile_health']['last_run'],self.at.isoformat())

    def test_contained_malformed_order_failure_is_not_marked_healthy(self):
        self.due=[]
        self.states['email_attribution_scan']={**self.scan,'next_at':self.at.isoformat()}
        self.fetch.side_effect=ValueError('incomplete journey')
        with self.assertLogs('crm_campaign_attribution',level='WARNING'):
            reconcile(self.store,self.shop,lambda:self.at)
        self.assertEqual(self.states['email_attribution_scan']['error'],'source_unavailable')
        self.assertNotIn('email_reconcile_health',self.states)
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')


if __name__=='__main__':unittest.main()
