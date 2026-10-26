"""Fault injection only. SQL tests require the disposable loopback fixture."""
from datetime import datetime, timezone
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from support_email_provider import MailboxError
from support_email_durable import DurableRegistry, OutboxWorker
from tests import test_email_durable_delivery as durable_cases
from tests import test_email_inbox_reliability as inbox_cases
from tests import test_support_email_live as provider_cases
from copy import deepcopy
import time
import socket
from tests.test_support_email import header


class TransportFallbackTests(unittest.TestCase):
    def test_ipv6_blackhole_budget_is_shared_and_reserves_ipv4_attempt(self):
        from support_email_transport import connect_tcp
        now = [0.0]
        addresses = [(socket.AF_INET6,socket.SOCK_STREAM,6,'',('::1',993,0,0)),
                     (socket.AF_INET6,socket.SOCK_STREAM,6,'',('::2',993,0,0)),
                     (socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',993))]
        first, working = Mock(), Mock()
        def blackhole(address):
            now[0] += first.settimeout.call_args.args[0]
            raise TimeoutError('Synthetic IPv6 timeout')
        first.connect.side_effect = blackhole
        with patch('support_email_transport.time.monotonic',side_effect=lambda:now[0]), \
             patch('socket.getaddrinfo',return_value=addresses) as dns, \
             patch('socket.socket',side_effect=[first,working]) as sockets:
            self.assertIs(connect_tcp('fixture.invalid',993,8),working)
        dns.assert_called_once_with('fixture.invalid',993,0,socket.SOCK_STREAM)
        self.assertEqual(sockets.call_count,2)
        first.settimeout.assert_called_once_with(1.0)
        working.settimeout.assert_called_once_with(7.0)
        working.connect.assert_called_once_with(('127.0.0.1',993))
        first.close.assert_called_once()

    def test_ipv6_only_dns_retains_full_connection_budget(self):
        from support_email_transport import connect_tcp
        wire=Mock()
        addresses=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('::1',993,0,0))]
        with patch('support_email_transport.time.monotonic',return_value=0), \
             patch('socket.getaddrinfo',return_value=addresses), patch('socket.socket',return_value=wire):
            self.assertIs(connect_tcp('fixture.invalid',993,8),wire)
        wire.settimeout.assert_called_once_with(8)


@unittest.skipUnless(os.getenv('EMAIL_TEST_POSTGRES') == '1', 'Disposable loopback PostgreSQL required')
class DurableRecoveryTests(unittest.TestCase):
    setUp = durable_cases.DurableDelivery.setUp
    prepare = durable_cases.DurableDelivery.prepare
    submit = durable_cases.DurableDelivery.submit
    expire = durable_cases.DurableDelivery.expire

    def test_exhausted_unknown_is_rechecked_slowly_without_retransmission(self):
        self.provider.submit.return_value = {'status': 'unknown', 'error_category': 'NETWORK'}
        self.submit()
        for _ in range(6):
            self.expire()
            self.store.due(self.mailbox)
        self.expire()
        row = self.store.due(self.mailbox)
        self.assertIsNotNone(row)
        self.assertEqual(row['status'], 'unknown')
        due = datetime.fromisoformat(str(row['due_at']).replace('Z', '+00:00'))
        self.assertGreater((due-datetime.now(timezone.utc)).total_seconds(), 800)
        self.assertIsNone(self.store.due(self.mailbox))
        OutboxWorker(Mock(address=self.mailbox), Mock(), self.registry).tick(self.imap, self.provider)
        self.provider.submit.assert_called_once()

    def test_acceptance_survives_database_failure_and_flushes_without_resend(self):
        self.prepare()
        def accepted(mime, *, mailbox, progress):
            progress(100, 'Sent')
            return {'status': 'accepted'}
        self.provider.submit.side_effect = accepted
        with patch.object(self.store, 'finish', side_effect=RuntimeError('Synthetic DB interruption')):
            result = self.submit()
            self.assertEqual(result['status'], 'accepted')
            self.assertTrue(result['persistence_pending'])
            self.assertEqual(self.registry.get(self.op, self.mailbox)['status'], 'accepted')
        self.registry.flush_acceptances()
        self.assertEqual(self.store.get(self.mailbox, self.op)['status'], 'accepted')
        self.assertEqual(self.submit()['status'], 'accepted')
        self.provider.submit.assert_called_once()

    def test_progress_acceptance_is_persisted_once_without_false_recovery_warning(self):
        self.prepare()
        def accepted(mime, *, mailbox, progress):
            progress(100, 'Sent')
            return {'status': 'accepted'}
        self.provider.submit.side_effect = accepted
        original = self.store.finish
        def finish_once(*args):
            if finish.call_count > 1:
                raise RuntimeError('Synthetic interruption after receipt was stored')
            return original(*args)
        with patch.object(self.store, 'finish', side_effect=finish_once) as finish:
            result = self.submit()
        self.assertEqual(finish.call_count, 1)
        self.assertEqual(result['status'], 'accepted')
        self.assertFalse(result['persistence_pending'])
        self.assertFalse(self.registry.acceptance_pending)
        self.assertIsNotNone(self.store.get(self.mailbox, self.op)['accepted_at'])

    def test_new_worker_after_interrupted_acceptance_does_not_submit_again(self):
        self.prepare()
        def interrupted(mime, *, mailbox, progress):
            progress(100, 'Sent')
            raise TimeoutError('Synthetic interruption after 250')
        self.provider.submit.side_effect = interrupted
        with patch.object(self.store, 'finish', side_effect=RuntimeError('Synthetic DB interruption')):
            with self.assertRaises(TimeoutError):
                self.submit()
        self.expire()
        other = DurableRegistry(self.store)
        OutboxWorker(Mock(address=self.mailbox), Mock(), other).tick(self.imap, self.provider)
        self.provider.submit.assert_called_once()

    def test_sent_evidence_does_not_invent_an_smtp_acceptance_timestamp(self):
        self.provider.submit.return_value = {'status': 'unknown'}
        self.submit()
        self.imap.find_message_id.return_value = ['42']
        result = self.registry.reconcile(self.op, self.mailbox, self.imap, 'Sent')
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['confirmation_source'], 'provider_sent')
        self.assertEqual(result['sent_at'], '')
        self.assertIsNone(self.store.get(self.mailbox, self.op)['accepted_at'])
        self.assertEqual(self.store.get(self.mailbox, self.op)['copy_status'], 'present')

    def test_old_unknown_reconciliation_cannot_starve_queued_submission(self):
        self.provider.submit.return_value = {'status': 'unknown'}
        self.submit()
        self.expire()
        other = str(uuid.uuid4())
        self.store.prepare(self.mailbox, other, dict(self.mime, message_id=f'<{other}@example.test>'))
        self.assertEqual(str(self.store.due(self.mailbox)['operation_id']), other)


class SyncRecoveryTests(unittest.TestCase):
    setUp = inbox_cases.InboxReliability.setUp

    def test_transport_stage_and_retry_are_actionable_and_cache_remains_available(self):
        self.reads.sync()
        before = self.reads.value['snapshot']
        self.mail.live_changes = Mock(side_effect=MailboxError('Timeout', code='timeout', stage='tcp', retryable=True))
        self.reads.sync()
        health = self.reads.health_snapshot()
        self.assertEqual(health['failure_stage'], 'tcp')
        self.assertGreater(health['retry_after'], 0)
        self.assertIn('before authentication', health['diagnosis'])
        self.assertEqual(self.reads.value['snapshot'], before)
        self.assertFalse(health['authentication_valid'])

    def test_dead_index_thread_can_restart_without_discarding_cache(self):
        self.reads.thread = Mock()
        self.reads.thread.is_alive.return_value = False
        self.reads.value['snapshot'] = {'messages': []}
        with patch('support_email_reads.threading.Thread') as thread:
            self.reads.start()
        thread.return_value.start.assert_called_once()
        self.assertIn('snapshot', self.reads.value)

    def test_authentication_failure_requires_owner_then_recovers_without_losing_cache(self):
        self.reads.sync()
        before = deepcopy(self.reads.value['snapshot'])
        original = self.mail.live_changes
        self.mail.live_changes = Mock(side_effect=MailboxError('Credentials rejected', code='authentication', stage='authentication'))
        self.reads.sync()
        self.assertEqual(self.reads.value['snapshot'], before)
        self.assertIn('owner', self.reads.health_snapshot()['diagnosis'])
        self.assertGreaterEqual(self.reads.health_snapshot()['retry_after'], 899)
        self.mail.live_changes = original
        self.reads.refresh()
        self.reads.sync()
        self.assertEqual(self.reads.health_snapshot()['state'], 'CONNECTED')

    def test_rate_limit_respects_provider_retry_and_preserves_last_success(self):
        self.reads.sync()
        success = self.reads.health['last_success_at']
        self.mail.live_changes = Mock(side_effect=MailboxError('Rate limit', code='limit', retry_after=120))
        self.reads.sync()
        self.assertGreaterEqual(self.reads.health_snapshot()['retry_after'], 119)
        self.assertEqual(self.reads.health['last_success_at'], success)

    def test_missed_idle_event_is_caught_by_periodic_worker_and_duplicates_deduplicate(self):
        waits = []
        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 1:
                m = header('999', '<catchup@example.test>')
                self.mail.messages.extend([m, deepcopy(m)])
            else:
                self.reads.stop.set()
        self.reads.wake.wait = wait
        self.reads.run()
        rows = self.reads.value['snapshot']['messages']
        self.assertEqual(sum(m['uid'] == '999' for m in rows), 1)
        self.assertEqual(waits[0], 60)
        self.assertEqual(len([c for c in self.mail.calls if c[0] == 'headers']), 1)
        self.assertFalse(any(c[0] in {'body', 'attachment'} for c in self.mail.calls))

    def test_worker_restart_uses_persisted_snapshot_but_does_not_hide_recent_failure(self):
        from support_email_snapshot import SnapshotStore
        self.reads.sync()
        cached = deepcopy(self.reads.value)
        cached.update(synced_at=time.time()-10, observed_at=time.time()+1)
        self.reads.health.update(state='RECONNECTING',category='timeout',failure_stage='tcp',last_failure_at=time.time())
        store = SnapshotStore()
        store.read_index = Mock(return_value=cached)
        self.reads.store = store
        self.reads.restore()
        self.assertEqual(self.reads.health_snapshot()['state'], 'RECONNECTING')
        self.assertEqual(self.reads.value['snapshot'], cached['snapshot'])

        # A newer confirmed sync from another worker clears the old diagnosis.
        cached = deepcopy(cached)
        cached['synced_at'] = time.time()+1
        cached['observed_at'] = time.time()+2
        store.read_index.return_value = cached
        self.reads.restore()
        self.assertEqual(self.reads.health_snapshot()['state'], 'CONNECTED')
        self.assertEqual(self.reads.health_snapshot()['diagnosis'], '')

    def test_dead_idle_and_outbox_workers_restart_once_and_shutdown_is_respected(self):
        from support_email_idle import MailboxWatcher
        from tests.email_v2_fixtures import CONFIG
        for worker, module in [(MailboxWatcher(CONFIG,store=Mock()),'support_email_idle'),
                               (OutboxWorker(CONFIG,Mock(configured=True),Mock()),'support_email_durable')]:
            worker.thread = Mock()
            worker.thread.is_alive.return_value = False
            with patch(module+'.threading.Thread') as thread:
                worker.start()
                thread.return_value.start.assert_called_once()
                worker.stop.set()
                worker.start()
                thread.return_value.start.assert_called_once()


class CursorRecoveryTests(unittest.TestCase):
    setUp = provider_cases.LiveProviderTests.setUp

    def test_partial_header_batch_cannot_advance_incremental_cursor(self):
        original = self.wire.uid
        def partial(command, *args):
            if command == 'FETCH' and 'HEADER.FIELDS' in str(args):
                return 'OK', []
            return original(command, *args)
        self.wire.uid = partial
        with self.assertRaises(MailboxError) as failed:
            self.adapter.live_changes('INBOX', {'messages': [], 'uidvalidity': '500', 'live_uid': 2})
        self.assertEqual(failed.exception.stage, 'fetch_headers')
