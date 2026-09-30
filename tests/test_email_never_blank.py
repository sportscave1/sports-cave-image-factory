"""Production outage regressions with fabricated mail only."""
from copy import deepcopy
import threading
import unittest
from unittest.mock import Mock, patch
from support_email_db_guard import DatabaseCooldown, SNAPSHOT_DB
from support_email_provider import MailboxError
from support_email_reads import ReadService, AsyncInbox
from support_email_runtime import MailboxRuntime, Deferred, operation
from tests.test_email_inbox_reliability import InboxReliability, Provider
from tests.email_v2_fixtures import CONFIG


class NeverBlank(InboxReliability):
    def test_cold_persisted_outage_rows_selection_and_recovery(self):
        self.ready()
        saved = deepcopy(self.reads.value)
        replacement = ReadService(self.mail, self.store)
        self.addCleanup(replacement.close)
        replacement.start = Mock()
        self.store.read_index.return_value = saved
        replacement.restore()
        self.mail.fail = True
        replacement.sync()
        self.w.imap = AsyncInbox(CONFIG, replacement)
        self.w.load(defer_body=True)
        before = self.w.model()
        self.assertEqual(len(before['threads']), 50)
        self.assertEqual(before['sync_health']['state'], 'RECONNECTING')
        self.mail.fail = False
        replacement.sync()
        self.w.live_check()
        self.assertEqual(self.w.model()['selected'], before['selected'])
        self.assertEqual(self.w.model()['sync_health']['state'], 'CONNECTED')

    def test_missing_table_read_is_bounded_and_live_still_works(self):
        class UndefinedTable(Exception):pass
        self.store.read_index.side_effect = UndefinedTable('private text')
        for _ in range(30):self.reads.restore()
        self.assertEqual(self.store.read_index.call_count, 1)
        self.ready()
        self.assertEqual(len(self.reads.index()['messages']), 50)

    def test_write_failure_bounded_without_losing_memory(self):
        self.store.save_index.side_effect = RuntimeError('private text')
        for _ in range(6):self.reads.sync()
        self.assertEqual(self.store.save_index.call_count, 1)
        self.assertEqual(len(self.reads.value['snapshot']['messages']), 50)

    def test_cold_empty_outage_never_fakes_rows(self):
        self.mail.fail = True
        self.reads.start = Mock()
        self.reads.restore();self.reads.sync();self.w.load(defer_body=True)
        self.assertEqual(self.w.model()['threads'], [])
        self.assertEqual(self.reads.health['state'], 'RECONNECTING')

    def test_delayed_restore_cannot_replace_live_data(self):
        self.ready()
        live = deepcopy(self.reads.value)
        self.store.read_index.return_value = {'snapshot': {'messages': []}, 'synced_at': 1}
        self.reads.restore()
        self.assertEqual(self.reads.value, live)

    def test_refresh_fences_inflight_index_and_coalesces(self):
        gate, entered = threading.Event(), threading.Event()
        original = self.mail.list_headers
        def slow(*a, **kw):
            entered.set();gate.wait(3);return original(*a, **kw)
        self.mail.list_headers = slow
        worker = threading.Thread(target=self.reads.sync)
        worker.start();self.assertTrue(entered.wait(2))
        self.reads.sync()  # Must not start another copy.
        self.reads.refresh();gate.set();worker.join(3)
        self.assertEqual(self.reads.value, {})
        self.assertEqual(len([c for c in self.mail.calls if c[0] == 'headers']), 1)
        self.reads.sync()
        self.assertEqual(len(self.reads.value['snapshot']['messages']), 50)

    def test_heartbeat_uses_index_not_remote_delta(self):
        self.ready();self.w.load(defer_body=True)
        self.mail.calls.clear()
        for _ in range(15):self.w.live_check()
        self.assertFalse(any(c[0] in ('headers', 'live') for c in self.mail.calls))


class Coordination(unittest.TestCase):
    def test_exhausted_deadline_does_not_invent_ipv6_failure(self):
        import socket
        from support_email_transport import connect_tcp
        now = [0]
        wire = Mock()
        def timeout(*_):
            now[0] = 8
            raise TimeoutError('private')
        wire.connect.side_effect = timeout
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 993)),
                     (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::1', 993, 0, 0))]
        with patch('support_email_transport.time.monotonic', side_effect=lambda:now[0]), \
                patch('socket.getaddrinfo', return_value=addresses), patch('socket.socket', return_value=wire) as factory, \
                self.assertLogs('support_email_transport', 'INFO') as logs, self.assertRaises(TimeoutError):
            connect_tcp('fixture.invalid', 993, 8)
        self.assertEqual(factory.call_count, 1)
        self.assertIn('family=ipv6 reason=deadline', str(logs.output))
        self.assertNotIn('family=ipv6 type=TimeoutError', str(logs.output))

    def test_idle_and_notification_cannot_start_during_read_backoff(self):
        runtime = MailboxRuntime()
        with self.assertRaises(MailboxError):
            with runtime.connection(CONFIG.scope):
                raise MailboxError('fixture', code='timeout', stage='tcp')
        for _ in range(20):
            with self.assertRaises(Deferred):
                with runtime.connection(CONFIG.scope, background=True):self.fail('socket admitted')

    def test_manual_refresh_cannot_bypass_budget_repeatedly(self):
        runtime = MailboxRuntime()
        with operation(force=True):
            with self.assertRaises(MailboxError):
                with runtime.connection(CONFIG.scope):raise MailboxError('fixture', code='timeout')
            with self.assertRaises(Deferred):
                with runtime.connection(CONFIG.scope):self.fail('second forced socket')

    def test_schema_missing_has_longer_cooldown_and_safe_log(self):
        class UndefinedTable(Exception):pass
        clock = [0]
        guard = DatabaseCooldown(lambda: clock[0])
        with self.assertLogs('support_email_db_guard', 'WARNING') as logs:
            guard.failed(UndefinedTable('DO NOT LOG'), 'snapshot')
            guard.failed(UndefinedTable('DO NOT LOG'), 'snapshot')
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn('DO NOT LOG', str(logs.output))
        self.assertFalse(guard.ready());clock[0] = 300;self.assertTrue(guard.ready())

    def test_email_manifest_is_complete_and_sha_reviewed(self):
        import run_migrations as runner
        for name in runner.EMAIL_MIGRATIONS:
            self.assertIn(name, runner.DEPLOYMENT_MIGRATIONS)
            path = runner.MIGRATIONS_DIR / name
            self.assertTrue(runner.reviewed_migration_sql(path, path.read_text(encoding='utf-8')))
