"""Transport failures must not bypass backoff; no network or app startup."""
import socket
import imaplib
import unittest
from unittest.mock import Mock, patch

from support_email_provider import ImapProvider, MailboxError
from support_email_runtime import MailboxRuntime, operation
from tests.test_support_email import CONFIG
from tests.test_email_connection_recovery import Wire


class DialBackoffTests(unittest.TestCase):
    def test_health_diagnostic_bounds_logout_after_authentication_failure(self):
        from scripts.check_support_email_health import check
        wire = Mock()
        def initialize(connection, *args, **kwargs):
            connection.sock = wire
        output = []
        with patch.object(imaplib.IMAP4_SSL, '__init__', initialize), \
             patch.object(imaplib.IMAP4_SSL, 'capability', return_value=('OK', [b'IDLE'])), \
             patch.object(imaplib.IMAP4_SSL, 'login', side_effect=imaplib.IMAP4.error('private')), \
             patch.object(imaplib.IMAP4_SSL, 'logout', side_effect=TimeoutError('private')), \
             patch.object(imaplib.IMAP4_SSL, 'shutdown') as shutdown:
            self.assertEqual(check(CONFIG, output.append), 1)
        wire.settimeout.assert_called_once_with(1)
        shutdown.assert_called_once()
        wire.close.assert_called_once()
        self.assertNotIn('private', str(output))

    def test_failed_dial_waits_for_backoff_then_recovers(self):
        for stage, error in [('tcp', TimeoutError('private')),
                             ('dns', socket.gaierror('private'))]:
            for background in (False, True):
                with self.subTest(stage=stage, background=background):
                    error.email_stage = stage
                    clock = [100.0]
                    runtime = MailboxRuntime(clock=lambda: clock[0])
                    factory = Mock(side_effect=[error, Wire()])
                    provider = ImapProvider(CONFIG, connection_factory=factory, runtime=runtime)
                    with operation(background=background):
                        with self.assertRaises(MailboxError) as failed:
                            provider.discover_folders()
                        self.assertEqual(failed.exception.stage, stage)
                        self.assertEqual(factory.call_count, 1)
                        self.assertGreater(runtime.recovery(CONFIG.scope)['retry_after'], 0)
                        with self.assertRaises(MailboxError):
                            provider.discover_folders()
                        self.assertEqual(factory.call_count, 1)
                        clock[0] += 60
                        self.assertTrue(provider.discover_folders()['folders'])
                    self.assertEqual(factory.call_count, 2)
                    self.assertEqual(runtime.active, 0)
                    self.assertEqual(runtime.recovery(CONFIG.scope)['retry_after'], 0)

    def test_explicit_refresh_allows_one_dial_but_not_an_immediate_second(self):
        error = TimeoutError('private')
        error.email_stage = 'tcp'
        factory = Mock(side_effect=error)
        runtime = MailboxRuntime()
        provider = ImapProvider(CONFIG, connection_factory=factory, runtime=runtime)
        with provider.interactive_refresh(), self.assertRaises(MailboxError):
            provider.discover_folders()
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(runtime.active, 0)
        self.assertGreater(runtime.recovery(CONFIG.scope)['retry_after'], 0)


if __name__ == '__main__':
    unittest.main()
