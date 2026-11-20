"""Long-cycle recovery regressions. Fake clocks/providers, no network or database."""
from datetime import timedelta
from unittest import TestCase
from unittest.mock import Mock, patch

from crm_engine import Engine
from crm_logic import now


class DeliveryFreshnessTests(TestCase):
    def setUp(self):
        self.at = now()
        clock_patch = patch('crm_automation_capabilities.now', side_effect=lambda: self.at)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.state = {'checked_at': self.at.isoformat(),
                      'triggers': {'abandoned': 'AVAILABLE'}}
        self.store = Mock()
        self.store.state.side_effect = lambda key: self.state if key == 'shopify_automation_capabilities' else {}
        self.store.lease.return_value = True
        self.store.q.return_value = []
        self.engine = Engine(self.store, Mock(), config=Mock(enabled=True), clock=lambda: self.at)
        self.engine.owner = 'fixture-worker'
        self.engine.advance_due = Mock()
        self.engine.send_one = Mock(return_value=False)

    def test_verification_is_renewed_within_one_long_worker_cycle(self):
        from crm_automation_capabilities import require
        renewed = []
        def verify(*args, **kwargs):
            self.assertFalse(kwargs['include_pixel'])
            self.state['checked_at'] = self.at.isoformat()
            renewed.append(self.at)
        with patch('crm_automation_capabilities.verify', side_effect=verify), \
             patch('crm_campaign_schedule.schedule_gate'), \
             patch('crm_campaign_schedule.activate_due'), \
             patch('crm_campaign_dispatch.dispatch'):
            # No new Engine.tick: source maintenance is still in the same cycle.
            for minute in range(21):
                if minute:
                    self.at += timedelta(minutes=1)
                self.engine.delivery_checkpoint(force=True)
                require(self.store, 'abandoned')
        self.assertEqual(len(renewed), 4)
        self.assertEqual(self.engine.advance_due.call_count, 21)

    def test_failed_refresh_does_not_extend_or_bypass_expired_evidence(self):
        from crm_automation_capabilities import require
        self.at += timedelta(minutes=11)
        before = dict(self.state)
        with patch('crm_automation_capabilities.verify', side_effect=RuntimeError('private fixture')):
            self.engine.refresh_automation_capabilities()
        self.assertEqual(self.state, before)
        with self.assertRaisesRegex(ValueError, 'Diagnostic expired'):
            require(self.store, 'abandoned')

    def test_due_checkout_refreshes_expired_trigger_before_validation(self):
        self.at += timedelta(minutes=11)
        customer = {'id': 'gid://shopify/Customer/1', 'email': 'collector@example.test',
                    'validEmailAddress': True,
                    'emailMarketingConsent': {'marketingState': 'SUBSCRIBED'}}
        checkout = {'id': 'gid://shopify/AbandonedCheckout/1',
                    'createdAt': (self.at-timedelta(hours=2)).isoformat(),
                    'customer': customer,
                    'abandonedCheckoutUrl': 'https://fixture.myshopify.com/1/checkouts/token12345/recover',
                    'lineItems': {'nodes': [{'title': 'Fixture edition', 'quantity': 1}]}}
        enrollment = {'automation_id': 'fixture-flow', 'shopify_customer_id': customer['id'],
                      'trigger_shopify_id': checkout['id'], 'trigger_at': checkout['createdAt'],
                      'current_step': 0,
                      'steps': [{'automation_version': 1, 'trigger': 'abandoned', 'rules': []}]}
        self.store.suppressed.return_value = False
        self.store.get.return_value = {'status': 'ACTIVE', 'trigger_type': 'abandoned', 'config': {}}
        self.engine.shop.customer.return_value = customer
        self.engine.shop.checkout.return_value = checkout
        self.engine.shop.orders.return_value = {'nodes': []}
        def verify(*args, **kwargs):
            self.state['checked_at'] = self.at.isoformat()
        with patch('crm_automation_capabilities.verify', side_effect=verify) as refreshed:
            selected, context, reason = self.engine.validate(customer['id'], enrollment)
        refreshed.assert_called_once()
        self.assertEqual(reason, '')
        self.assertEqual(selected, customer)
        self.assertEqual(context['_checkout_id'], checkout['id'])

    def test_fresh_failed_capability_check_still_blocks(self):
        from crm_automation_capabilities import require
        self.at += timedelta(minutes=11)
        def verify(*args, **kwargs):
            self.state.update(checked_at=self.at.isoformat(),
                              triggers={'abandoned': 'UNAVAILABLE'},
                              reasons={'abandoned': ['read_orders: MISSING']})
        with patch('crm_automation_capabilities.verify', side_effect=verify):
            self.engine.refresh_automation_capabilities()
        with self.assertRaisesRegex(ValueError, 'read_orders: MISSING'):
            require(self.store, 'abandoned')

    def test_slow_due_checks_yield_before_draining_entire_backlog(self):
        engine = Engine(self.store, Mock(), config=Mock(enabled=True))
        engine.hold_lease = Mock()
        engine.advance = Mock()
        self.store.q.return_value = [{'id': str(i)} for i in range(20)]
        with patch('crm_engine.monotonic', side_effect=[0, 0, 30, 60]), \
             patch('crm_checkout_purchase_exit.stop_if_purchased', return_value=False):
            engine.advance_due()
        self.assertEqual(engine.advance.call_count, 2)
        self.assertFalse(any(call.args[0].startswith('UPDATE') for call in self.store.q.call_args_list))

    def test_abandoned_diagnostic_uses_real_completed_delivery_work(self):
        import crm_automation_diagnostic_ui as ui
        health = {'checked_at': now().isoformat(), 'status': 'ok'}
        report = {'delivery_health': health,
                  'worker': {'checked_at': (now()-timedelta(minutes=20)).isoformat()},
                  'latest_event': None, 'next_due': None, 'retry_after': None,
                  'enrolled': 0, 'accepted': 0, 'steps': [], 'draft_steps': []}
        with patch('crm_email_diagnostics.automation_status', return_value=report), \
             patch.object(ui, 'st') as st:
            ui.operational_status(Mock(), {'trigger_type': 'abandoned', 'config': {'published_version': 1}})
        captions = str(st.caption.call_args_list)
        self.assertIn('CRM delivery work recent', captions)
        self.assertIn('Last full cycle completed', captions)
        self.assertNotIn('Heartbeat stale', captions)

    def test_stale_delivery_is_not_hidden_by_a_recent_schedule_lease(self):
        import crm_automation_diagnostic_ui as ui
        old = (now()-timedelta(minutes=20)).isoformat()
        report = {'delivery_health': {'checked_at': old, 'status': 'ok'},
                  'worker': {'checked_at': old},
                  'schedule_health': {'checked_at': now().isoformat()},
                  'latest_event': None, 'next_due': None, 'retry_after': None,
                  'enrolled': 0, 'accepted': 0, 'steps': [], 'draft_steps': []}
        with patch('crm_email_diagnostics.automation_status', return_value=report), \
             patch.object(ui, 'st') as st:
            ui.operational_status(Mock(), {'trigger_type': 'abandoned', 'config': {'published_version': 1}})
        self.assertIn('Heartbeat stale', str(st.caption.call_args_list))
