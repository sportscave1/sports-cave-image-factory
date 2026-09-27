"""Mailbox recovery uses fabricated wire connections only; no network or secrets."""
import imaplib
import ssl
import unittest
from unittest.mock import Mock, patch

import support_email_provider as provider
from tests.test_support_email import CONFIG, FakeImap
from tests import test_support_email_v2 as v2


class Wire(FakeImap):
    capabilities = (b"IMAP4rev1",)

    def __init__(self, failure=None):
        super().__init__()
        self.failure, self.closed = failure, False

    def list(self):
        self.calls.append(("list",))
        if self.failure:
            raise self.failure
        return super().list()

    def status(self, *args):
        if self.closed:
            raise AssertionError("Closed connection reused")
        return "OK", [b'"INBOX" (UNSEEN 3 MESSAGES 75 UIDNEXT 102 UIDVALIDITY 500)']

    def logout(self):
        self.closed = True
        super().logout()


class ConnectionRecoveryTests(unittest.TestCase):
    def test_existing_render_names_and_password_survive_reruns(self):
        env = {"SPORTSCAVE_EMAIL_IMAP_HOST": "ventraip.email", "SPORTSCAVE_EMAIL_IMAP_PORT": "993",
               "SPORTSCAVE_EMAIL_IMAP_SSL": "true", "SPORTSCAVE_EMAIL_ADDRESS": CONFIG.address,
               "SPORTSCAVE_EMAIL_PASSWORD": "fixture-password", "SPORTSCAVE_EMAIL_SMTP_PASSWORD": "different"}
        for _ in range(3):
            cfg = provider.load_configuration(env)
            self.assertTrue(cfg.configured)
            self.assertEqual(cfg.password, "fixture-password")
            self.assertEqual(cfg.scope, provider.load_configuration(env).scope)

    def test_stale_socket_discarded_once_then_folders_restore(self):
        stale, healthy = Wire(imaplib.IMAP4.abort("fixture-secret stale socket")), Wire()
        factory = Mock(side_effect=[stale, healthy])
        result = provider.ImapProvider(CONFIG, connection_factory=factory).discover_folders()
        self.assertEqual(result["folders"][0]["name"], "INBOX")
        self.assertEqual(factory.call_count, 2)
        self.assertTrue(stale.closed and healthy.closed)

    def test_list_rejection_retry_is_bounded_and_distinct(self):
        wires = [Wire(), Wire()]
        for wire in wires:
            wire.list = Mock(return_value=("NO", [b"fixture-secret server response"]))
        factory = Mock(side_effect=wires)
        with self.assertLogs(provider.LOGGER, level="WARNING") as logs:
            with self.assertRaises(provider.MailboxError) as error:
                provider.ImapProvider(CONFIG, connection_factory=factory).discover_folders()
        self.assertEqual(error.exception.code, "folders")
        self.assertEqual(factory.call_count, 2)
        self.assertNotIn("fixture-secret", str(error.exception) + str(logs.output))

    def test_timeout_retries_once_and_reports_timeout(self):
        factory = Mock(side_effect=TimeoutError("fixture-secret"))
        with self.assertRaises(provider.MailboxError) as error:
            provider.ImapProvider(CONFIG, connection_factory=factory).discover_folders()
        self.assertEqual(error.exception.code, "timeout")
        self.assertEqual(factory.call_count, 2)
        self.assertIn("timed out", str(error.exception))

    def test_authentication_failure_does_not_retry_or_leak(self):
        wire = Wire()
        wire.login = Mock(side_effect=imaplib.IMAP4.error("fixture-secret authentication rejected"))
        factory = Mock(return_value=wire)
        with self.assertLogs(provider.LOGGER, level="WARNING") as logs:
            with self.assertRaises(provider.MailboxError) as error:
                provider.ImapProvider(CONFIG, connection_factory=factory).discover_folders()
        self.assertEqual(error.exception.code, "authentication")
        self.assertEqual(factory.call_count, 1)
        self.assertNotIn("fixture-secret", str(error.exception) + str(logs.output))
        self.assertTrue(wire.closed)

    def test_tls_failure_is_distinct_without_retry(self):
        factory = Mock(side_effect=ssl.SSLCertVerificationError("fixture-secret"))
        with self.assertRaises(provider.MailboxError) as error:
            provider.ImapProvider(CONFIG, connection_factory=factory).discover_folders()
        self.assertEqual(error.exception.code, "tls")
        self.assertEqual(factory.call_count, 1)

    def test_connection_timeout_then_fresh_connection_recovers(self):
        wire = Wire()
        factory = Mock(side_effect=[TimeoutError("fixture-secret"), wire])
        self.assertEqual(provider.ImapProvider(CONFIG, connection_factory=factory).test_connection()["count"], 75)
        self.assertEqual(factory.call_count, 2)
        self.assertTrue(wire.closed)

    def test_header_read_retries_but_mailbox_write_never_replays(self):
        stale, healthy = Wire(), Wire()
        stale.fetch = Mock(side_effect=imaplib.IMAP4.abort("fixture-secret"))
        factory = Mock(side_effect=[stale, healthy])
        self.assertTrue(provider.ImapProvider(CONFIG, connection_factory=factory).list_headers()["messages"])
        self.assertEqual(factory.call_count, 2)
        wire = Wire()
        wire.uid = Mock(side_effect=imaplib.IMAP4.abort("fixture-secret"))
        factory = Mock(return_value=wire)
        with self.assertRaises(provider.MailboxError):
            provider.ImapProvider(CONFIG, connection_factory=factory).set_flag(
                {"folder": "INBOX", "uidvalidity": "500", "uid": "101"}, "\\Seen", True)
        self.assertEqual(factory.call_count, 1)
        wire.uid.assert_called_once()

    def test_notification_and_page_operations_never_share_sockets(self):
        wires = [Wire(), Wire(), Wire()]
        factory = Mock(side_effect=wires)
        adapter = provider.ImapProvider(CONFIG, connection_factory=factory)
        self.assertEqual(adapter.get_unread_count(), 3)
        self.assertEqual(adapter.discover_folders()["folders"][0]["name"], "INBOX")
        self.assertEqual(adapter.list_headers()["messages"][0]["uid"], "101")
        self.assertEqual(factory.call_count, 3)
        self.assertTrue(all(w.closed for w in wires))

    def test_test_connection_selects_readonly_and_lists_then_logs_out(self):
        wire = Wire()
        result = provider.ImapProvider(CONFIG, connection_factory=Mock(return_value=wire)).test_connection()
        self.assertEqual(result["count"], 75)
        self.assertIn(("select", "INBOX", True), wire.calls)
        self.assertIn(("list",), wire.calls)
        self.assertTrue(wire.closed)


class FolderFailureRecoveryTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event

    def test_failure_not_cached_as_empty_and_refresh_recovers(self):
        with patch.object(self.imap, "discover_folders", side_effect=provider.MailboxError("Folder listing failed. Retry connection.")):
            self.w.load(force=True)
        self.assertEqual(self.state["error"], "")
        self.assertIn("last successful", self.state["live_error"])
        self.assertIn("folder_cache", self.state)
        self.assertTrue(self.w.model()["threads"])
        self.w.load(force=True)
        self.assertEqual(self.state["error"], "")
        self.assertTrue(self.state["folders"] and self.state["threads"])

    def test_repeated_rerun_failure_is_throttled_separately_from_data(self):
        with patch.object(self.imap, "discover_folders", side_effect=provider.MailboxError("Folder listing failed.")) as discover:
            self.w.load(force=True)
            for _ in range(4):
                self.w.load()
            self.assertEqual(discover.call_count, 1)
            self.assertTrue(self.state["folder_cache"]["data"]["folders"])


if __name__ == "__main__":
    unittest.main()
