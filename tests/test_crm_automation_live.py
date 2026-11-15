"""Production SQL and rendered payloads on disposable loopback PostgreSQL only."""
from copy import deepcopy
from datetime import timedelta
import os
import unittest
from unittest.mock import patch
from crm_automation_definition import email_step
from crm_automation_runtime import advance
from crm_automation_live import reconcile
from crm_engine import Engine
from crm_logic import date, now
from crm_automation_store import AutomationStore
from tests.crm_db_fixture import connect
from tests import test_crm_native_automations as fixtures
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE
from tests.test_crm_simple_editor import document


class PublicationErrors(unittest.TestCase):
    def test_discount_error_is_actionable_without_exposing_payload(self):
        from crm_automation_publication import safe_reason
        from crm_recovery_discount import DiscountHold
        message=safe_reason(DiscountHold('discount_not_selected: private fixture content'))
        self.assertIn('Select a Shopify discount', message)
        self.assertNotIn('private fixture content', message)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES') == '1', 'Disposable PostgreSQL required')
class LiveStages(unittest.TestCase):
    setUp = fixtures.NativeAutomationTests.setUp
    published = fixtures.NativeAutomationTests.published
    enroll = fixtures.NativeAutomationTests.enroll
    due = fixtures.NativeAutomationTests.due

    def journey(self, j):
        return self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s', (j['id'],), True)

    def receipts(self, j):
        return self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s ORDER BY step_index', (j['id'],))

    def publish_change(self, a, change, publish=True):
        a = self.store.flow(a['id']); flow = deepcopy(a['config']['draft']); change(flow)
        a = self.store.save_flow(ADMIN, a['id'], a['name'], flow, a['config']['revision'])
        return self.store.publish(ADMIN, a['id'], a['config']['revision'], env=LIVE) if publish else a

    def send_due(self, j):
        advance(self.engine, self.due(j))
        with patch('crm_workspace_store.WorkspaceRecords.frequency_blocked', return_value=False):
            self.engine.send_one()
        return self.receipts(j)[-1]

    def test_existing_scheduled_customer_uses_latest_payload_and_draft_stays_private(self):
        a = self.published(); j = self.enroll(a)
        advance(self.engine, self.due(j)); before = self.receipts(j)[0]
        a = self.publish_change(a, lambda f: f['emails'][0]['document']['content'].update(subject='LIVE VERSION TWO'))
        self.publish_change(a, lambda f: f['emails'][0]['document']['content'].update(subject='PRIVATE DRAFT THREE'), False)
        self.engine.send_one()
        sent = self.receipts(j)[0]; payload = self.provider.send.call_args.args[1]
        self.assertEqual(sent['template_version'], 2)
        self.assertEqual(sent['due_at'], before['due_at'])
        self.assertEqual(sent['idempotency_key'], before['idempotency_key'])
        self.assertEqual(payload['subject'], 'LIVE VERSION TWO')
        self.assertNotIn('PRIVATE DRAFT THREE', str(payload))
        from crm_automation_runtime import render
        expected = render(self.store.template(sent['template_id'], 2), sent, 'https://example.test/unsubscribe/fixture')
        self.assertEqual(payload['html'], expected['html'])

    def test_new_stages_three_four_five_after_exhaustion_no_reenrollment_or_replay(self):
        a = self.published(delays=(0, 0)); j = self.enroll(a)
        self.send_due(j); self.send_due(j)
        reconcile(self.store, j, self.clock)
        self.assertEqual(self.journey(j)['stop_reason'], 'awaiting_published_stage')
        for number in (3, 4, 5, 6):
            a = self.publish_change(a, lambda f: f['emails'].append(email_step(document(), 3600)))
            planned = reconcile(self.store, j, self.clock)
            self.assertEqual(planned['status'], 'ACTIVE')
            self.assertEqual(planned['current_step'], number - 1)
            previous = self.receipts(j)[-1]
            self.assertEqual(date(planned['next_due_at']), date(previous['updated_at']) + timedelta(hours=1))
            advance(self.engine, planned)
            self.assertEqual(len(self.receipts(j)), number - 1)
            self.send_due(j); reconcile(self.store, j, self.clock)
        receipts = self.receipts(j)
        self.assertEqual(len(receipts), 6)
        self.assertEqual(len({r['idempotency_key'] for r in receipts}), 6)
        self.assertEqual(self.provider.send.call_count, 6)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s', (a['id'],), True)['n'], 1)

    def test_restart_reads_live_content_and_durable_progress(self):
        a = self.published(delays=(0, 0)); j = self.enroll(a); self.send_due(j)
        a = self.publish_change(a, lambda f: f['emails'][1]['document']['content'].update(subject='AFTER RESTART'))
        self.engine = Engine(AutomationStore(connect), self.shop, self.provider, self.engine.config, clock=lambda: self.clock)
        self.send_due(j)
        self.assertEqual(self.provider.send.call_args.args[1]['subject'], 'AFTER RESTART')
        self.assertEqual([r['template_version'] for r in self.receipts(j)], [1, 2])

    def test_publish_during_render_rejects_old_reservation_then_renders_new(self):
        a = self.published(); j = self.enroll(a); advance(self.engine, self.due(j))
        original = self.store.begin_send
        def race(row, *args):
            self.publish_change(a, lambda f: f['emails'][0]['document']['content'].update(subject='CONCURRENT LIVE'))
            return original(row, *args)
        with patch.object(self.store, 'begin_send', side_effect=race):
            self.engine.send_one()
        self.provider.send.assert_not_called()
        self.assertEqual(self.receipts(j)[0]['status'], 'PENDING')
        self.engine.send_one()
        self.assertEqual(self.provider.send.call_args.args[1]['subject'], 'CONCURRENT LIVE')
        self.assertEqual(self.receipts(j)[0]['template_version'], 2)

    def test_publication_after_reservation_does_not_change_committed_payload(self):
        a = self.published(); j = self.enroll(a); advance(self.engine, self.due(j))
        original = self.store.begin_send
        def race(row, *args):
            result = original(row, *args)
            self.publish_change(a, lambda f: f['emails'][0]['document']['content'].update(subject='NEXT DELIVERY'))
            return result
        with patch.object(self.store, 'begin_send', side_effect=race):self.engine.send_one()
        self.assertEqual(self.receipts(j)[0]['template_version'], 1)
        self.assertNotEqual(self.provider.send.call_args.args[1]['subject'], 'NEXT DELIVERY')

    def test_disable_after_queue_prevents_transport(self):
        a = self.published(delays=(0, 3600)); j = self.enroll(a); advance(self.engine, self.due(j))
        self.publish_change(a, lambda f: f['emails'][0].update(enabled=False))
        self.engine.send_one(); self.provider.send.assert_not_called()
        reconcile(self.store, j, self.clock)
        self.assertEqual(self.journey(j)['current_step'], 1)

    def test_insert_predecessor_during_render_holds_existing_queue(self):
        a = self.published(); j = self.enroll(a); advance(self.engine, self.due(j))
        original = self.store.begin_send
        def race(row, *args):
            self.publish_change(a, lambda f: f['emails'].insert(0, email_step(document(), 0)))
            return original(row, *args)
        with patch.object(self.store, 'begin_send', side_effect=race):self.engine.send_one()
        self.provider.send.assert_not_called()
        plan = reconcile(self.store, j, self.clock)
        self.assertEqual(plan['current_step'], 1)  # New stable ledger slot, first live stage.
        self.send_due(j)
        self.assertEqual(self.receipts(j)[1]['status'], 'ACCEPTED')

    def test_completed_historical_journey_never_reopened(self):
        a = self.published(); j = self.enroll(a)
        self.store.q("UPDATE crm_automation_enrollments SET status='COMPLETED',current_step=1 WHERE id=%s", (j['id'],))
        self.publish_change(a, lambda f: f['emails'].append(email_step(document(), 0)))
        self.assertIsNone(reconcile(self.store, j, self.clock))
        self.assertEqual(self.journey(j)['status'], 'COMPLETED')
        self.assertEqual(self.receipts(j), [])

    def test_mixed_historical_progress_never_replays_missing_earlier_delivery(self):
        a = self.published(delays=(0, 0)); j = self.enroll(a)
        self.store.q('UPDATE crm_automation_enrollments SET current_step=1 WHERE id=%s', (j['id'],))
        self.send_due(j)
        self.publish_change(a, lambda f: f['emails'].append(email_step(document(), 0)))
        self.send_due(j)
        self.assertEqual([r['step_index'] for r in self.receipts(j)], [1, 2])
        self.assertTrue(self.journey(j)['steps'][0]['historical_pass'])

    def test_failed_publication_keeps_last_live_and_missing_live_fails_closed(self):
        a = self.published(); j = self.enroll(a); advance(self.engine, self.due(j))
        with patch('crm_automation_publication.prepare', side_effect=ValueError('Invalid publication')):
            with self.assertRaises(ValueError):
                self.publish_change(a, lambda f: f['emails'][0]['document']['content'].update(subject='INVALID'))
        self.assertEqual(self.store.flow(a['id'])['config']['published_version'], 1)
        with patch.object(self.store, 'template', side_effect=ValueError('Missing active version')):
            self.engine.send_one()
        self.provider.send.assert_not_called()
        self.assertEqual(self.receipts(j)[0]['status'], 'PENDING')

    def test_no_stage_limit_and_unpublished_draft_does_not_join(self):
        a = self.published(); j = self.enroll(a)
        a = self.publish_change(a, lambda f: f['emails'].extend(email_step(document(), n) for n in range(60)), False)
        self.assertEqual(len(reconcile(self.store, j, self.clock)['steps']), 1)
        self.store.publish(ADMIN, a['id'], a['config']['revision'], env=LIVE)
        self.assertEqual(len(reconcile(self.store, j, self.clock)['steps']), 61)

    def test_disabled_stage_skipped_but_receipt_indexes_never_move(self):
        a = self.published(delays=(0, 0, 0)); j = self.enroll(a); self.send_due(j)
        self.publish_change(a, lambda f: f['emails'][1].update(enabled=False))
        self.send_due(j)
        self.assertEqual([r['step_index'] for r in self.receipts(j)], [0, 2])
        self.assertEqual(len(self.journey(j)['steps']), 3)

    def test_reentry_policy_supersedes_exhausted_journey_without_two_active_memberships(self):
        a = self.published()
        a = self.publish_change(a, lambda f: f.update(reentry_days=7))
        j = self.enroll(a); self.send_due(j); reconcile(self.store, j, self.clock)
        from crm_automation_runtime import enter
        later = date(j['trigger_at']) + timedelta(days=8)
        entered = enter(self.engine, a, self.customer['id'], self.customer['id'], 'new-event', later)
        self.assertIsNotNone(entered)
        self.assertEqual(self.journey(j)['status'], 'COMPLETED')
        self.assertEqual(self.store.q("SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s AND status='ACTIVE'", (a['id'],), True)['n'], 1)

    def test_reentry_cannot_bypass_newly_published_unsent_stage(self):
        a = self.published()
        a = self.publish_change(a, lambda f: f.update(reentry_days=7))
        j = self.enroll(a); self.send_due(j); reconcile(self.store, j, self.clock)
        a = self.publish_change(a, lambda f: f['emails'].append(email_step(document(), 0)))
        from crm_automation_runtime import enter
        self.assertIsNone(enter(self.engine, a, self.customer['id'], self.customer['id'], 'new-event', date(j['trigger_at']) + timedelta(days=8)))
        self.assertEqual(self.journey(j)['status'], 'ACTIVE')

    def test_read_only_diagnostic_has_publication_and_receipt_but_no_customer_data(self):
        from scripts.diagnose_automation_live import audit
        a = self.published(); j = self.enroll(a); self.send_due(j)
        result = audit(self.store, a['id'])
        self.assertEqual(result['summary']['active'], 1)
        self.assertEqual(result['recent_history'][0]['selected_publication_version'], 1)
        self.assertNotIn(self.customer['email'], str(result))
        self.assertNotIn(self.customer['id'], str(result))

    def test_disabled_during_reservation_does_not_send_queued_stage(self):
        a = self.published(delays=(0, 3600)); j = self.enroll(a); advance(self.engine, self.due(j))
        original = self.store.begin_send
        def disable(row, *args):
            self.publish_change(a, lambda f: f['emails'][0].update(enabled=False))
            return original(row, *args)
        with patch.object(self.store, 'begin_send', side_effect=disable):self.engine.send_one()
        self.provider.send.assert_not_called()
        self.assertEqual(self.receipts(j)[0]['status'], 'PENDING')

    def test_publish_transaction_failure_rolls_back_templates_and_pointer(self):
        a = self.published(); j = self.enroll(a); advance(self.engine, self.due(j))
        from crm_automation_publication import commit
        def rollback(*args, **kwargs):
            commit(*args, **kwargs)
            raise ValueError('Simulated transaction abort')
        with patch('crm_automation_publication.commit', side_effect=rollback):
            with self.assertRaises(ValueError):
                self.publish_change(a, lambda f: f['emails'][0]['document']['content'].update(subject='ABORTED'))
        self.assertEqual(self.store.flow(a['id'])['config']['published_version'], 1)
        self.engine.send_one()
        self.assertEqual(self.receipts(j)[0]['template_version'], 1)
        self.assertNotEqual(self.provider.send.call_args.args[1]['subject'], 'ABORTED')

    def test_uncertain_delivery_stops_progress_without_starving_due_queue(self):
        a = self.published(delays=(0, 0)); j = self.enroll(a)
        advance(self.engine, self.due(j))
        self.provider.send.side_effect = TimeoutError('Unknown transport outcome')
        self.engine.send_one()
        self.assertEqual(self.receipts(j)[0]['status'], 'UNCERTAIN')
        self.assertIsNone(reconcile(self.store, j, self.clock))
        self.assertEqual(self.journey(j)['status'], 'STOPPED')
        self.assertEqual(len(self.receipts(j)), 1)


if __name__ == '__main__':unittest.main()
