"""Connection pressure/outage tests. Every wire is fabricated; no network I/O."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import errno
import imaplib
import json
import ssl
import threading
import time
import unittest
from unittest.mock import Mock, patch

from support_email_runtime import MailboxRuntime, Deferred, operation
from support_email_provider import ImapProvider, MailboxError, _failure, _ManagedSSL, _SSL_CLASS
from tests.test_support_email import CONFIG, header
from tests.test_support_email_live import LiveWire
from tests import test_support_email_v2 as v2


class World:
    def __init__(self):
        self.now = 1000
        self.runtime = MailboxRuntime(lambda: self.now)
        self.attempts = self.active = self.peak = self.closed = 0
        self.wires = []
        self.fail = False

    def connect(self, *args, **kwargs):
        self.attempts += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        wire = LiveWire()
        self.wires.append(wire)
        wire.closed = False
        def shutdown():
            if not wire.closed:
                self.closed += 1
                self.active -= 1
                wire.closed = True
        wire.shutdown = shutdown
        if self.fail:
            wire.status = Mock(side_effect=TimeoutError("fixture-secret"))
        return wire

    def adapter(self, background=False):
        return ImapProvider(CONFIG, connection_factory=self.connect, runtime=self.runtime, background=background)


SNAPSHOT = {"messages": [header(str(i)) for i in (1, 2, 3)], "uidvalidity": "500", "live_uid": 3}
CURSOR = {"uidvalidity": "500", "last_uid": 3}


def simulate(outage=False):
    world = World()
    checks = 0
    started = time.perf_counter()
    # Nathan/Maria, two tabs each, 30-second heartbeats plus five reruns each tick.
    # Providers are recreated just as they are on Streamlit reruns.
    for elapsed in range(0, 600, 30):
        world.now = 1000 + elapsed
        world.fail = outage and 180 <= elapsed < 300
        for _session in range(4):
            for _rerun in range(5):
                checks += 1
                try:
                    world.adapter(True).notification_snapshot(CURSOR)
                    world.adapter().live_changes("INBOX", deepcopy(SNAPSHOT))
                except MailboxError:
                    pass
    commands = [c for wire in world.wires for c in wire.calls]
    return {"seconds_simulated": 600, "sessions": 4, "heartbeats_and_reruns": checks,
            "attempts": world.attempts, "peak": world.peak, "closed": world.closed,
            "leaked": world.active, "status_commands": sum(c[0] == "status" for c in commands),
            "body_fetches": sum("BODY" in str(c) for c in commands),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}


class PollRecoveryTests(unittest.TestCase):
    def test_ten_minutes_four_tabs_reruns_are_coalesced_and_closed(self):
        result = simulate()
        self.assertEqual(result["attempts"], 20)  # One STATUS + one flags operation/minute.
        self.assertEqual(result["status_commands"], 10)
        self.assertEqual(result["closed"], result["attempts"])
        self.assertEqual(result["leaked"], 0)
        self.assertEqual(result["peak"], 1)
        self.assertEqual(result["body_fetches"], 0)

    def test_two_minute_outage_is_bounded_then_recovers(self):
        result = simulate(True)
        self.assertLessEqual(result["attempts"], 20)
        self.assertEqual(result["leaked"], 0)
        self.assertEqual(result["attempts"], result["closed"])
        self.assertEqual(result["body_fetches"], 0)

    def test_sidebar_notifications_and_live_share_status(self):
        world = World()
        world.adapter().live_changes("INBOX", SNAPSHOT)
        self.assertEqual(world.adapter(True).notification_snapshot(CURSOR)["unseen"], 2)
        self.assertEqual(world.adapter().get_unread_count(), 2)
        self.assertEqual(world.attempts, 1)
        self.assertEqual(sum(c[0] == "status" for w in world.wires for c in w.calls), 1)

    def test_backoff_progression_and_success_reset(self):
        world = World();world.fail = True
        for delay in (15, 30, 60, 120):
            with self.assertRaises(MailboxError):
                world.adapter(True).get_unread_count()
            count = world.attempts
            for _ in range(20):
                with self.assertRaises(MailboxError):
                    world.adapter(True).get_unread_count()
            self.assertEqual(world.attempts, count)
            retry_at = world.runtime.states[CONFIG.scope]["retry_at"]
            self.assertGreaterEqual(retry_at, world.now + delay)
            self.assertLessEqual(retry_at, world.now + delay * 1.1)
            world.now = retry_at
        world.fail = False
        world.adapter(True).get_unread_count()
        self.assertEqual(world.runtime.states[CONFIG.scope]["failures"], 0)
        self.assertEqual(world.active, 0)

    def test_manual_refresh_bypasses_backoff_and_invalidates_old_poll(self):
        world = World();world.fail = True
        with self.assertRaises(MailboxError):world.adapter(True).get_unread_count()
        world.fail = False
        adapter = world.adapter()
        with adapter.interactive_refresh():
            self.assertEqual(adapter.get_unread_count(), 2)
        self.assertEqual(world.runtime.states[CONFIG.scope]["retry_at"], 0)
        def changed_during_poll():
            world.runtime.invalidate(CONFIG.scope)
            return {"flags": {"1": []}}
        with self.assertRaises(Deferred):
            world.runtime.check(CONFIG.scope, "old-result", changed_during_poll)
        self.assertIsNone(world.runtime.get(CONFIG.scope, "old-result"))

    def test_foreground_retries_once_despite_circuit_and_closes_each_socket(self):
        world = World()
        original = world.connect
        def connect(*args, **kwargs):
            wire = original(*args, **kwargs)
            if world.attempts == 1:
                wire.list = Mock(side_effect=imaplib.IMAP4.abort("fixture-secret"))
            return wire
        adapter = ImapProvider(CONFIG, connection_factory=connect, runtime=world.runtime)
        self.assertTrue(adapter.discover_folders()["folders"])
        self.assertEqual(world.attempts, 2)
        self.assertEqual(world.closed, 2)

    def test_cleanup_on_timeout_cancel_and_logout_failure(self):
        for error in (TimeoutError("fixture-secret"), KeyboardInterrupt()):
            world = World()
            adapter = world.adapter()
            with self.assertRaises((MailboxError, KeyboardInterrupt)):
                with adapter._connection() as (wire, _, __):
                    wire.logout = Mock(side_effect=TimeoutError("fixture-secret"))
                    raise error
            self.assertEqual(world.active, 0)
            self.assertEqual(world.closed, 1)
            self.assertEqual(world.runtime.active, 0)

    def test_partial_constructor_resources_close(self):
        resources = [Mock(), Mock()]
        def fail(instance, *args, **kwargs):
            instance._file, instance.sock = resources
            raise TimeoutError("fixture-secret")
        with patch.object(_SSL_CLASS, "__init__", fail), self.assertRaises(TimeoutError):
            _ManagedSSL()
        for resource in resources:resource.close.assert_called_once()

    def test_background_admission_queues_foreground_with_one_short_lived_slot(self):
        runtime = MailboxRuntime()
        entered, release = threading.Event(), threading.Event()
        def background():
            with runtime.connection(CONFIG.scope, background=True):
                entered.set();release.wait(3)
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(background)
            self.assertTrue(entered.wait(2))
            try:
                with self.assertRaises(Deferred):
                    with runtime.connection(CONFIG.scope, background=True):pass
                timer = threading.Timer(.05, release.set)
                timer.start()
                with runtime.connection(CONFIG.scope):
                    self.assertEqual(runtime.active, 1)
                timer.join()
            finally:release.set()
            future.result(3)
        self.assertEqual(runtime.active, 0)

    def test_failure_invalidates_prior_shared_success(self):
        world = World()
        adapter = world.adapter()
        adapter.live_changes("INBOX", SNAPSHOT)
        self.assertTrue(world.runtime.cache)
        with self.assertRaises(MailboxError):
            with adapter._connection():
                raise TimeoutError("fixture-secret")
        self.assertFalse(world.runtime.cache)
        before = world.attempts
        with self.assertRaises(MailboxError):adapter.live_changes("INBOX", SNAPSHOT)
        self.assertEqual(world.attempts, before)

    def test_shared_snapshots_cannot_mutate_another_sessions_result(self):
        world = World()
        nathan = world.adapter().live_changes("INBOX", SNAPSHOT)
        nathan["flags"].clear()
        maria = world.adapter().live_changes("INBOX", SNAPSHOT)
        self.assertEqual(len(maria["flags"]), 3)
        self.assertEqual(world.attempts, 1)

    def test_distinct_view_background_attempt_budget(self):
        world = World()
        for _ in range(6):
            with world.runtime.connection(CONFIG.scope, background=True):pass
        with self.assertRaises(Deferred):
            with world.runtime.connection(CONFIG.scope, background=True):pass
        with world.runtime.connection(CONFIG.scope):pass  # User actions have priority.
        world.now += 60
        with world.runtime.connection(CONFIG.scope, background=True):pass

    def test_safe_error_classification(self):
        cases = [(OSError(errno.ENETUNREACH, "fixture-secret"), "network"),
                 (ConnectionRefusedError(), "refused"), (ConnectionResetError(), "reset"),
                 (ssl.SSLEOFError("fixture-secret"), "reset"),
                 (imaplib.IMAP4.abort("BYE fixture-secret"), "bye"),
                 (imaplib.IMAP4.error("Too many connections fixture-secret"), "limit")]
        for error, expected in cases:
            self.assertEqual(_failure(error, "connect").code, expected)
            self.assertNotIn("fixture-secret", str(_failure(error, "connect")))
        world = World()
        adapter = ImapProvider(CONFIG, connection_factory=Mock(side_effect=cases[0][0]), runtime=world.runtime)
        with self.assertLogs("support_email_provider", "WARNING") as logs, self.assertRaises(MailboxError):
            adapter.get_unread_count()
        self.assertIn("errno=", str(logs.output));self.assertNotIn("fixture-secret", str(logs.output))


class CachedWorkspaceTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    open = v2.WorkspaceTests.open
    compose = v2.WorkspaceTests.compose

    def test_deferred_background_capacity_does_not_claim_outage(self):
        self.state['live_checked_at'] = 0
        with patch.object(self.imap, 'live_changes', side_effect=MailboxError('Mailbox is busy.', code='busy')):
            self.event('live_check')
        self.assertEqual(self.state['live_error'], '')

    def test_poll_failure_keeps_open_message_folders_rows_and_draft(self):
        self.open();self.compose('reply')
        before = deepcopy(self.w.model())
        self.imap.fail = True;self.state['live_checked_at'] = 0
        self.event('live_check')
        after = self.w.model()
        for key in ('folders', 'threads', 'messages', 'selected', 'draft', 'inbox_status'):
            self.assertEqual(before[key], after[key], key)
        self.assertFalse(after['error']);self.assertIn('last successful', after['live_error'])
        self.assertEqual(after['refreshed'], before['refreshed'])
        self.imap.fail = False;self.event('refresh')
        self.assertEqual(self.w.model()['live_error'], '')
        self.assertEqual(self.w.model()['draft'], before['draft'])

    def test_failed_new_folder_does_not_mislabel_old_inbox_data(self):
        self.imap.fail = True
        self.event('folder', folder='Archive')
        self.assertTrue(self.w.model()['error'])
        self.assertEqual(self.w.model()['threads'], [])

    def test_cold_failure_reruns_cannot_reconnect_until_backoff(self):
        self.state.clear()
        self.w = v2.Workspace(self.state, v2.USER, v2.CONFIG, v2.SMTP_CONFIG, imap=self.imap, smtp=self.smtp)
        self.imap.fail = True
        with patch.object(self.imap, 'discover_folders', wraps=self.imap.discover_folders) as discover:
            for _ in range(20):self.w.load()
            self.assertEqual(discover.call_count, 1)
        self.assertTrue(self.w.model()['error'])
        self.assertFalse(self.w.model()['threads'])


if __name__ == '__main__':
    print(json.dumps({"healthy": simulate(), "two_minute_outage": simulate(True)}, indent=2))
