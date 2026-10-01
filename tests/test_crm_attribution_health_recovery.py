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
            if sql.startswith('SELECT attempts FROM crm_order_attribution'):return {'attempts':3}
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

    def test_contained_malformed_scan_order_does_not_poison_global_health(self):
        self.due=[]
        self.states['email_attribution_scan']={**self.scan,'next_at':self.at.isoformat()}
        self.fetch.side_effect=ValueError('incomplete journey')
        with self.assertLogs('crm_campaign_attribution',level='WARNING'):
            reconcile(self.store,self.shop,lambda:self.at)
        self.assertNotIn('error',self.states['email_attribution_scan'])
        self.assertIn('email_reconcile_health',self.states)
        self.assertTrue(observations(self.store)['Attribution reconcile'].startswith('RECENT'))

    def test_bad_due_order_retries_and_second_order_succeeds_with_safe_stage_logs(self):
        bad='gid://shopify/Order/100';good='gid://shopify/Order/200'
        self.due=[{'shopify_order_id':bad},{'shopify_order_id':good}]
        private='customer@example.test Name Address https://example.test?token=secret raw-payload'
        for stage in ('fetch_order','record_evidence','mirror'):
            with self.subTest(stage=stage):
                self.states={'email_attribution_scan':deepcopy(self.scan)}
                self.store.q.reset_mock()
                self.fetch.reset_mock(side_effect=True)
                self.record.reset_mock(side_effect=True)
                self.mirror.reset_mock(side_effect=True)
                self.fetch.side_effect=[ValueError(private),{'id':good}] if stage=='fetch_order' else [{'id':bad},{'id':good}]
                self.record.side_effect=[KeyError(private),None] if stage=='record_evidence' else None
                self.mirror.side_effect=[TypeError(private),None] if stage=='mirror' else None
                with self.assertLogs('crm_campaign_attribution',level='WARNING') as logs:
                    self.tick()
                self.assertEqual([call.args[1] for call in self.fetch.call_args_list],[bad,good])
                self.record.assert_any_call(self.store,{'id':good})
                self.mirror.assert_any_call(self.store,{'id':good},None)
                retries=[call for call in self.store.q.call_args_list if 'attempts=attempts+1' in call.args[0]]
                self.assertEqual(len(retries),1)
                self.assertEqual(retries[0].args[1],(bad,))
                self.assertIn("interval '15 minutes'",retries[0].args[0])
                output='\n'.join(logs.output)
                self.assertIn('order_id='+bad,output)
                self.assertIn('stage='+stage,output)
                self.assertIn('retry_attempt=4',output)
                for forbidden in ('customer@example.test','Name','Address','token=secret','raw-payload'):
                    self.assertNotIn(forbidden,output)
                self.assert_recovered()

    def test_capability_unavailable_aborts_due_loop_and_keeps_error(self):
        from crm_shopify import CapabilityUnavailable
        self.due=[{'shopify_order_id':'100'},{'shopify_order_id':'200'}]
        self.fetch.side_effect=CapabilityUnavailable('order API')
        with self.assertLogs(level='WARNING'):
            self.tick()
        self.fetch.assert_called_once_with(self.shop,'100')
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
        self.assertNotIn('email_reconcile_health',self.states)
        self.updated.assert_not_called()

    def test_database_failure_in_record_is_systemic(self):
        from crm_store import StoreUnavailable
        from psycopg import OperationalError
        self.due=[{'shopify_order_id':'100'},{'shopify_order_id':'200'}]
        for error in (StoreUnavailable('database secret'),OperationalError('private DSN')):
            with self.subTest(error=type(error).__name__):
                self.fetch.reset_mock()
                self.record.side_effect=error
                with self.assertLogs(level='WARNING') as logs:
                    self.tick()
                self.fetch.assert_called_once()
                self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
                self.assertNotIn('email_reconcile_health',self.states)
                self.assertNotIn('private DSN','\n'.join(logs.output))
                self.assertNotIn('database secret','\n'.join(logs.output))

    def test_failure_updating_order_retry_is_systemic(self):
        from crm_store import StoreUnavailable
        original=self.store.q.side_effect
        def query(sql,*args,**kwargs):
            if 'attempts=attempts+1' in sql:raise StoreUnavailable('retry storage unavailable')
            return original(sql,*args,**kwargs)
        self.store.q.side_effect=query
        self.fetch.side_effect=ValueError('bad order')
        with self.assertLogs(level='WARNING'):
            self.tick()
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
        self.assertNotIn('email_reconcile_health',self.states)

    def test_unknown_errors_fail_closed_and_decimal_shape_errors_are_isolated(self):
        from decimal import InvalidOperation
        for error,isolated in ((InvalidOperation('bad decimal'),True),
                               (AttributeError('bad nested field'),True),
                               (RuntimeError('unknown service error'),False)):
            with self.subTest(error=type(error).__name__):
                self.states={'email_attribution_scan':deepcopy(self.scan)}
                self.fetch.side_effect=error
                with self.assertLogs(level='WARNING'):
                    self.tick()
                status=observations(self.store)['Attribution reconcile']
                if isolated:self.assertTrue(status.startswith('RECENT'),status)
                else:self.assertEqual(status,'ERROR')

    def test_database_setup_failure_is_never_classified_as_bad_evidence(self):
        original=self.store.q.side_effect
        def query(sql,*args,**kwargs):
            if sql.startswith('SELECT attempts FROM'):raise ValueError('database setup failure')
            return original(sql,*args,**kwargs)
        self.store.q.side_effect=query
        with self.assertLogs(level='WARNING'):
            self.tick()
        self.fetch.assert_not_called()
        self.assertEqual(observations(self.store)['Attribution reconcile'],'ERROR')
        self.assertNotIn('email_reconcile_health',self.states)

    def test_invalid_identity_cannot_put_pii_or_tokens_in_logs(self):
        self.due=[{'shopify_order_id':'customer@example.test?token=secret'}]
        self.fetch.side_effect=ValueError('private payload')
        with self.assertLogs('crm_campaign_attribution',level='WARNING') as logs:
            self.tick()
        output='\n'.join(logs.output)
        self.assertIn('order_id=invalid_order_id',output)
        self.assertNotIn('customer@example.test',output)
        self.assertNotIn('token=secret',output)
        self.assertNotIn('private payload',output)


if __name__=='__main__':unittest.main()
