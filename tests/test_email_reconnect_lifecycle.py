"""Fresh wire recovery and bounded UI recovery. No production I/O."""
from copy import deepcopy
import imaplib
import uuid
import unittest
from unittest.mock import Mock, patch

import support_email_provider as provider
from support_email_runtime import MailboxRuntime
from support_email_workspace import Workspace
from tests.test_email_connection_recovery import Wire
from tests.test_support_email import CONFIG, header
from tests import test_support_email_v2 as v2


class ReadRecoveryTests(unittest.TestCase):
    def test_body_disconnect_reselects_same_folder_and_validity_once(self):
        for failure in (TimeoutError('private'), EOFError('private'), ConnectionResetError('private'),
                        BrokenPipeError('private'), imaplib.IMAP4.abort('BYE private')):
            with self.subTest(failure=type(failure).__name__):
                bad, good = Wire(), Wire()
                bad.uid = Mock(side_effect=failure)
                factory = Mock(side_effect=[bad, good])
                p = provider.ImapProvider(CONFIG, connection_factory=factory, runtime=MailboxRuntime())
                with self.assertLogs(provider.LOGGER, 'INFO') as logs:
                    body = p.read_message({**header(), 'folder': 'INBOX.Sent Items'})
                self.assertIn('Hello', body['text'])
                self.assertEqual(factory.call_count, 2)
                for wire in (bad, good):
                    self.assertTrue(wire.closed)
                    self.assertIn(('select', '"INBOX.Sent Items"', True), wire.calls)
                self.assertIn('reconnect_succeeded', str(logs.output))
                self.assertNotIn('private', str(logs.output))

    def test_explicit_bye_response_retries_like_abort(self):
        bad, good = Wire(), Wire()
        bad.fetch = Mock(return_value=('BYE', [b'private']))
        factory = Mock(side_effect=[bad, good])
        self.assertTrue(provider.ImapProvider(CONFIG, connection_factory=factory).list_headers()['messages'])
        self.assertEqual(factory.call_count, 2)

    def test_body_retry_bounded_and_never_returns_closed_socket(self):
        wires = [Wire(), Wire()]
        for wire in wires: wire.uid = Mock(side_effect=EOFError())
        factory = Mock(side_effect=wires)
        with self.assertRaises(provider.MailboxError):
            provider.ImapProvider(CONFIG, connection_factory=factory).read_message(header())
        self.assertEqual(factory.call_count, 2)
        self.assertTrue(all(w.closed for w in wires))

    def test_auth_failure_survives_admission_backoff_without_relogin(self):
        wire = Wire();wire.login = Mock(return_value=('NO', [b'private']))
        factory = Mock(return_value=wire)
        p = provider.ImapProvider(CONFIG, connection_factory=factory, runtime=MailboxRuntime())
        for _ in range(2):
            with self.assertRaises(provider.MailboxError) as raised: p.discover_folders()
            self.assertEqual(raised.exception.code, 'authentication')
        self.assertEqual(factory.call_count, 1)

    def test_reconnect_never_replays_write(self):
        for action in ('move_message', 'set_flag', 'append_message'):
            with self.subTest(action=action):
                wire = Wire();wire.capabilities = (b'MOVE',)
                wire.uid = Mock(side_effect=EOFError())
                wire.append = Mock(side_effect=EOFError())
                factory = Mock(return_value=wire)
                p = provider.ImapProvider(CONFIG, connection_factory=factory)
                args = {'move_message': (header(), 'Trash'), 'set_flag': (header(), '\\Flagged', True),
                        'append_message': ('Sent', b'fixture')}[action]
                with self.assertRaises(provider.MailboxError):getattr(p, action)(*args)
                self.assertEqual(factory.call_count, 1)
                self.assertEqual(wire.uid.call_count + wire.append.call_count, 1)


class WorkspaceRecoveryTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event

    def due(self):
        self.state['load_retry_at'] = 0
        self.event('reconnect')

    def test_cold_load_recovers_without_browser_refresh(self):
        self.state.clear()
        self.w = Workspace(self.state, v2.USER, v2.CONFIG, v2.SMTP_CONFIG, imap=self.imap, smtp=self.smtp)
        with patch.object(self.imap, 'discover_folders', side_effect=provider.MailboxError('Timeout', code='timeout')):
            self.w.load()
        self.assertEqual(self.w.model()['recovery']['state'], 'waiting')
        self.assertFalse(self.w.model()['threads'])
        self.due()
        model = self.w.model()
        self.assertEqual(model['recovery']['state'], '')
        self.assertFalse(model['error'] or model['live_error'])
        self.assertEqual(model['selected'], model['threads'][0]['key'])
        self.assertTrue(any(m['expanded'] for m in model['messages']))

    def test_refresh_outage_keeps_view_selection_and_recovers_once(self):
        self.event('open_thread', thread_key=self.state['threads'][2]['thread_key'])
        before = deepcopy(self.w.model())
        self.imap.fail = True;self.event('refresh')
        failed = self.w.model()
        for key in ('threads', 'selected', 'messages', 'folders'):self.assertEqual(failed[key], before[key])
        self.assertEqual(failed['recovery']['state'], 'waiting')
        self.imap.fail = False;self.state['load_retry_at'] = 0
        event = self.event('reconnect')
        count = len(self.imap.calls)
        self.assertFalse(self.w.handle(event))
        self.assertEqual(len(self.imap.calls), count)
        self.assertEqual(self.w.model()['selected'], before['selected'])
        self.assertFalse(self.w.model()['live_error'])
        self.smtp.submit.assert_not_called()

    def test_transient_outage_keeps_retrying_with_backoff_and_recovers(self):
        self.imap.fail = True;self.event('refresh')
        for _ in range(4):self.due()
        self.assertEqual(self.w.model()['recovery']['state'], 'waiting')
        count = len(self.imap.calls)
        for _ in range(5):self.event('live_check');self.w.load()
        self.assertEqual(len(self.imap.calls), count)
        self.imap.fail = False;self.due()
        self.assertFalse(self.w.model()['recovery']['state'])
        self.assertTrue(self.w.model()['threads'])

    def test_removed_selection_and_empty_inbox_after_recovery(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                self.imap.fail = True;self.event('refresh')
                selected = self.state['active_message']
                from support_email_workspace import reference_key
                self.imap.messages = [] if empty else [m for m in self.imap.messages if reference_key(m) != selected]
                self.imap.fail = False;self.due()
                model = self.w.model()
                self.assertFalse(model['error'] or model['recovery']['state'])
                if empty:self.assertFalse(model['threads'] or model['selected'])
                else:self.assertEqual(model['selected'], model['threads'][0]['key'])

    def test_folder_switch_failure_restores_requested_folder_without_old_rows(self):
        self.imap.messages[0]['folder'] = 'Archive'
        self.imap.fail = True;self.event('folder', folder='Archive')
        self.assertEqual(self.w.model()['threads'], [])
        self.imap.fail = False;self.due()
        self.assertEqual(self.w.model()['folder'], 'Archive')
        self.assertEqual(len(self.w.model()['threads']), 1)
        self.assertFalse(self.w.model()['error'])

    def test_authentication_stops_immediately_with_actual_error(self):
        with patch.object(self.imap, 'discover_folders', side_effect=provider.MailboxError(
                provider.FAILURES['authentication'], code='authentication')) as discover:
            self.event('refresh')
            for _ in range(3):self.due()
            self.assertEqual(discover.call_count, 1)
        self.assertEqual(self.w.model()['recovery']['state'], 'stopped')
        self.assertIn('authentication', self.w.model()['recovery']['message'])

    def test_selected_body_failure_reloads_missing_body_and_clears_notice(self):
        key = self.state['threads'][3]['thread_key']
        with patch.object(self.imap, 'read_message', side_effect=provider.MailboxError('Timed out', code='timeout', retryable=True)):
            self.event('open_thread', thread_key=key)
        self.assertEqual(self.w.model()['recovery']['state'], 'waiting')
        self.due()
        model = self.w.model()
        self.assertEqual(model['selected'], key)
        self.assertTrue(any(m['expanded'] for m in model['messages']))
        self.assertFalse(model['notice'] or model['error'] or model['live_error'])

    def test_backoff_events_do_not_repeat_reads_or_extend_deadline(self):
        self.imap.fail = True;self.event('refresh')
        deadline = self.state['load_retry_at'];count = len(self.imap.calls)
        for _ in range(10):self.event('reconnect')
        self.assertEqual(len(self.imap.calls), count)
        self.assertEqual(self.state['load_retry_at'], deadline)

    def test_cold_page_rerun_leaves_retry_budget_to_controller(self):
        import support_email_page as page
        for phase in ('waiting', 'stopped'):
            state={'support_email_scope':('fixture','fixture'), 'support_email_workspace':
                   {'loaded':False, 'navigation_epoch':0, 'recovery_state':phase}}
            workspace=Mock()
            with patch.object(page.st,'session_state',state),patch.object(page.st,'query_params',{}), \
                 patch.object(page,'Workspace',return_value=workspace), \
                 patch.object(page,'load_configuration',return_value=Mock(scope='fixture')), \
                 patch.object(page,'load_smtp_configuration'), \
                 patch.object(page,'get_component',return_value=Mock(return_value=None)):
                page._render_workspace.__wrapped__({'id':'fixture'})
            workspace.load.assert_not_called()

    def test_folder_change_during_backoff_never_labels_inbox_rows_as_archive(self):
        self.imap.fail=True;self.event('refresh')
        self.event('folder',folder='Archive')
        model=self.w.model()
        self.assertEqual(model['folder'],'Archive')
        self.assertFalse(model['threads'] or model['messages'])
        self.imap.fail=False;self.due()
        self.assertFalse(self.w.model()['error'])

    def test_manual_retry_restores_body_during_automatic_recovery_backoff(self):
        key=self.state['threads'][3]['thread_key']
        with patch.object(self.imap,'read_message',side_effect=provider.MailboxError('Timed out',code='timeout',retryable=True)):
            self.event('open_thread',thread_key=key)
            self.due();self.due()
        self.assertEqual(self.w.model()['recovery']['state'],'waiting')
        self.event('retry_connection')
        model=self.w.model()
        self.assertFalse(model['recovery']['state'] or model['notice'])
        self.assertEqual(model['selected'],key)
        self.assertTrue(any(m['expanded'] for m in model['messages']))

    def test_recovered_network_does_not_retry_a_malformed_body_forever(self):
        key=self.state['threads'][3]['thread_key']
        with patch.object(self.imap,'read_message',side_effect=provider.MailboxError('Timed out',code='timeout',retryable=True)):
            self.event('open_thread',thread_key=key)
        with patch.object(self.imap,'read_message',side_effect=provider.MailboxError('Malformed MIME')):
            self.due()
        model=self.w.model()
        self.assertFalse(model['recovery']['state'] or model['live_error'])
        self.assertIn('Could not open',model['notice'])


if __name__ == '__main__':unittest.main()
