"""Offline deployment gate: connection ownership and optional-IDLE isolation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import imaplib
import errno
import socket
import ssl
import subprocess
import sys
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch

from support_email_runtime import MailboxRuntime, Deferred, operation
from support_email_provider import MailboxError
from support_email_idle import IdleLifecycle
from tests.test_email_poll_recovery import World
from tests.test_support_email import CONFIG
from tests.test_support_email_idle import MemorySignals, simulate_consumers
from scripts.check_support_email_health import check


class ReliabilityTests(unittest.TestCase):
    def test_each_failed_address_reported_last_error_cannot_hide_timeout(self):
        from support_email_transport import connect_tcp
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 993)),
                     (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::1', 993, 0, 0))]
        wires = [Mock(), Mock()]
        wires[0].connect.side_effect = TimeoutError('fixture-secret')
        wires[1].connect.side_effect = OSError(errno.ENETUNREACH, 'fixture-secret')
        with patch('socket.getaddrinfo', return_value=addresses), patch('socket.socket', side_effect=wires), \
             self.assertLogs('support_email_transport', 'WARNING') as logs, self.assertRaises(TimeoutError):
            connect_tcp('fixture.invalid', 993, 8)
        self.assertIn('family=ipv4 type=TimeoutError', str(logs.output))
        self.assertIn(f'family=ipv6 type=OSError errno={errno.ENETUNREACH}', str(logs.output))
        self.assertNotIn('fixture-secret', str(logs.output))
        for wire in wires: wire.close.assert_called_once()

    def test_transport_tls_validates_original_hostname_and_closes_failure(self):
        from support_email_transport import connect_tls
        wire = Mock();context = Mock()
        context.wrap_socket.side_effect = ssl.SSLError('fixture-secret')
        with patch('support_email_transport.connect_tcp', return_value=wire), self.assertRaises(ssl.SSLError):
            connect_tls('fixture.invalid', 993, 8, context)
        context.wrap_socket.assert_called_once_with(wire, server_hostname='fixture.invalid')
        wire.close.assert_called_once()

    def test_transport_failed_endpoint_falls_through_without_forcing_ip_family(self):
        from support_email_transport import connect_tcp
        wires = [Mock(), Mock()]
        wires[0].connect.side_effect = OSError(errno.ENETUNREACH, 'fixture-secret')
        addresses = [(socket.AF_INET6,socket.SOCK_STREAM,6,'',('::1',993,0,0)),
                     (socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',993))]
        with patch('socket.getaddrinfo',return_value=addresses), patch('socket.socket',side_effect=wires):
            self.assertIs(connect_tcp('fixture.invalid',993,8),wires[1])
        wires[0].close.assert_called_once();wires[1].close.assert_not_called()

    def test_concurrent_sessions_never_exceed_one_short_lived_connection(self):
        runtime = MailboxRuntime()
        barrier = threading.Barrier(4)
        peak = []
        def foreground():
            barrier.wait()
            with runtime.connection(CONFIG.scope):
                peak.append(runtime.active)
                time.sleep(.01)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: foreground(), range(4)))
        self.assertEqual(peak, [1]*4)
        self.assertEqual(runtime.active, 0)

    def test_budget_timeout_is_bounded_and_does_not_leak(self):
        runtime = MailboxRuntime()
        with runtime.connection(CONFIG.scope):
            with self.assertRaises(Deferred) as error:
                with runtime.connection(CONFIG.scope, timeout=.01):
                    self.fail('second permit admitted')
            self.assertEqual(error.exception.reason, 'connection_budget_timeout')
        self.assertEqual(runtime.active, 0)
        self.assertEqual(runtime.foreground_waiting, 0)

    def test_stale_deployment_lease_does_not_gate_foreground(self):
        store = MemorySignals(lambda: 1)
        self.assertTrue(store.claim(CONFIG.address, 'old-process'))
        self.assertFalse(store.claim(CONFIG.address, 'new-process'))
        world = World()
        self.assertTrue(world.adapter().discover_folders()['folders'])
        self.assertEqual(world.attempts, world.closed)

    def test_watcher_failure_does_not_open_foreground_circuit(self):
        world = World()
        world.runtime.watcher(CONFIG.scope, 'reconnecting')
        self.assertEqual(world.adapter().get_unread_count(), 2)
        health = world.runtime.health(CONFIG.scope)
        self.assertEqual(health['state'], 'DEGRADED')
        self.assertEqual(health['consecutive_failures'], 0)
        self.assertIsNotNone(health['last_success_at'])

    def test_health_tracks_failure_stage_without_error_text(self):
        world = World()
        with self.assertRaises(MailboxError):
            with world.runtime.connection(CONFIG.scope):
                raise MailboxError('fixture-secret', code='timeout', stage='status')
        health = world.runtime.health(CONFIG.scope)
        self.assertEqual(health['failure_stage'], 'status')
        self.assertEqual(health['state'], 'UNAVAILABLE')
        self.assertNotIn('fixture-secret', str(health))
        with operation(force=True), world.runtime.connection(CONFIG.scope):
            pass
        self.assertEqual(world.runtime.health(CONFIG.scope)['consecutive_failures'], 0)

    def test_watcher_initialization_failure_does_not_fail_asgi_startup(self):
        sent = []
        async def app(scope, receive, send):
            await send({'type': 'lifespan.startup.complete'})
        async def send(message): sent.append(message)
        lifecycle = IdleLifecycle(app, factory=Mock(side_effect=RuntimeError('fixture-secret')))
        with self.assertLogs('support_email_idle', 'WARNING') as logs:
            asyncio.run(lifecycle({'type':'lifespan'}, None, send))
        self.assertEqual(sent, [{'type':'lifespan.startup.complete'}])
        self.assertNotIn('fixture-secret', str(logs.output))

    def test_crm_imports_do_not_connect_or_start_watchers(self):
        with patch('imaplib.IMAP4_SSL', side_effect=AssertionError('IMAP forbidden')), \
             patch('smtplib.SMTP_SSL', side_effect=AssertionError('SMTP forbidden')), \
             patch('support_email_idle.MailboxWatcher.start', side_effect=AssertionError('watcher forbidden')):
            for name in ('crm_navigation','crm_page','crm_service','crm_http','crm_engine','crm_worker'):
                importlib.import_module(name)

    def test_all_six_crm_pages_and_reruns_do_not_enter_email_runtime(self):
        # Other legacy full-suite AppTests leave global form context behind.
        # A fresh interpreter validates the real pages without inheriting that state.
        result = subprocess.run([sys.executable, '-c',
            'from tests.test_email_permanent_reliability import ReliabilityTests; ReliabilityTests()._verify_crm_pages()'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)

    def _verify_crm_pages(self):
        from streamlit.testing.v1 import AppTest
        script = '''
from unittest.mock import Mock, patch
import streamlit as st
from crm_page import render_page
from crm_shopify import Shopify
from crm_cache import DisplayCache
from crm_resend import Config
from tests.crm_fixtures import ShopifyFixture
store=Mock()
store.state.return_value={}
store.list.return_value=[]
store.q.return_value=[]
store.reports.return_value=({k:0 for k in ('sends','delivered','opened','clicked','bounces','complaints','unsubscribes')},[],[])
with patch('support_email_provider.ImapProvider._connection',side_effect=AssertionError('IMAP forbidden')) as imap, patch('smtplib.SMTP_SSL',side_effect=AssertionError('SMTP forbidden')) as smtp, patch('support_email_idle.MailboxWatcher.start',side_effect=AssertionError('Watcher forbidden')) as watcher:
    render_page(st.session_state['route'], {'id':'fixture','role':'admin','is_active':True}, shop=Shopify(ShopifyFixture(),DisplayCache()), store=store, config=Config({}))
    assert imap.call_count == smtp.call_count == watcher.call_count == 0
'''
        for route in ('CRM Customers','CRM Segments','CRM Automations','CRM Campaigns','CRM Templates','CRM Reports'):
            app = AppTest.from_string(script)
            app.session_state['route'] = route
            app.run(timeout=15)
            self.assertFalse(app.exception, route)
            if route == 'CRM Campaigns':
                self.assertTrue(all('LIVE MARKETING DELIVERY: DISABLED' in item.value for item in app.warning))
            else:
                self.assertFalse(app.warning, route)
            app.run(timeout=15)
            self.assertFalse(app.exception, route)

    def test_health_check_no_credentials_required_to_report_configuration_failure(self):
        from support_email_provider import Configuration
        output = []
        self.assertEqual(check(Configuration(), output.append), 1)
        self.assertEqual(output, ['FAIL configuration category=configuration duration_ms=0'])

    def test_health_check_readonly_and_no_fetch_and_cleanup_on_auth_failure(self):
        for failed in (False, True):
            output = []
            with patch.object(imaplib.IMAP4_SSL, '__init__', return_value=None), \
                 patch.object(imaplib.IMAP4_SSL, 'capability', return_value=('OK',[b'IMAP4rev1 IDLE'])), \
                 patch.object(imaplib.IMAP4_SSL, 'login', side_effect=imaplib.IMAP4.error('fixture-secret') if failed else None, return_value=('OK',[])), \
                 patch.object(imaplib.IMAP4_SSL, 'select', return_value=('OK',[b'1'])) as select, \
                 patch.object(imaplib.IMAP4_SSL, 'status', return_value=('OK',[])), \
                 patch.object(imaplib.IMAP4_SSL, 'fetch', side_effect=AssertionError('BODY forbidden')), \
                 patch.object(imaplib.IMAP4_SSL, 'logout', return_value=('BYE',[])) as logout, \
                 patch.object(imaplib.IMAP4_SSL, 'shutdown') as shutdown:
                self.assertEqual(check(CONFIG, output.append), int(failed))
                if not failed: select.assert_called_once_with('"INBOX"', readonly=True)
                logout.assert_called_once();shutdown.assert_called_once()
            self.assertNotIn('fixture-secret', str(output))
            self.assertNotIn(CONFIG.password, str(output))

    def test_hour_simulation_watchers_fallback_notifications_and_leaks(self):
        result = simulate_consumers()
        self.assertEqual(result['logical_watchers'], 1)
        self.assertLessEqual(result['peak_total_connections'], 2)
        self.assertEqual(result['leaked_connections'], 0)
        self.assertEqual(result['body_fetches'], 0)
        self.assertEqual(result['duplicate_notifications'], 0)
        self.assertEqual(result['notifications'], 5)


if __name__ == '__main__':
    unittest.main()
