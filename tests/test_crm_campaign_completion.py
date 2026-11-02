"""Confirmed completion cannot wait for unrelated worker maintenance."""
import os
import unittest
from unittest.mock import Mock,patch
from crm_engine import Engine


class CompletionOrderTests(unittest.TestCase):
    def test_delivery_checkpoint_finalizes_before_returning_to_maintenance(self):
        engine=Engine(Mock(),Mock());engine.owner='fixture';engine.hold_lease=Mock()
        engine.config.enabled=False;engine.send_one=Mock(return_value=False)
        order=[]
        engine.complete_campaigns=lambda:order.append('complete')
        with patch('crm_campaign_dispatch.dispatch',side_effect=lambda e:order.append('dispatch')):
            engine.delivery_checkpoint(force=True)
        order.append('maintenance')
        self.assertEqual(order,['dispatch','complete','maintenance'])


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class CompletionSQLTests(unittest.TestCase):
    def test_confirmed_receipts_complete_but_pending_and_uncertain_remain_active(self):
        from tests.test_crm_batch_dispatch import DispatchTests
        fixture=DispatchTests();fixture.setUp()
        try:
            from crm_campaign_dispatch import dispatch
            from crm_logic import now
            from datetime import timedelta
            completed=fixture.queue(1)
            dispatch(fixture.engine)
            uncertain=fixture.queue(1)
            # Unknown state originates from an interrupted provider response.
            import crm_campaign_dispatch as module
            with patch.object(module,'finish',side_effect=RuntimeError('Lost receipt')):
                with self.assertRaises(RuntimeError):dispatch(fixture.engine)
            campaign=fixture.store.q('SELECT campaign_send_id FROM crm_campaigns WHERE id=%s',(uncertain,),True)
            state=fixture.states(uncertain)[0]['value']
            state['request_started_at']=(now()-timedelta(hours=24)).isoformat()
            fixture.store.set_state('campaign-batch:'+str(campaign['campaign_send_id'])+':0',state)
            dispatch(fixture.engine)
            self.assertEqual(fixture.sends(uncertain)[0]['status'],'UNCERTAIN')
            pending=fixture.queue(1)
            fixture.engine.complete_campaigns()
            self.assertEqual(fixture.store.q('SELECT status FROM crm_campaigns WHERE id=%s',(completed,),True)['status'],'SENT')
            for identity in (pending,uncertain):
                self.assertEqual(fixture.store.q('SELECT status FROM crm_campaigns WHERE id=%s',(identity,),True)['status'],'SENDING')
        finally:
            fixture.tearDown();fixture.doCleanups()
