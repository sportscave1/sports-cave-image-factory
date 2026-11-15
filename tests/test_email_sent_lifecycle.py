"""Send acceptance, rerun recovery and real-mailbox storage; all transports are fakes."""
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser
import inspect
import unittest
import uuid
from unittest.mock import Mock, patch

from tests import test_support_email_v2 as v2
from tests.email_v2_fixtures import MAILBOX, USER, CONFIG
from support_email_workspace import Workspace
from support_email_provider import MailboxError, folder_roles, parse_folders
from support_email_compose import make_attachment
import support_email_smtp as smtp


class SentLifecycleTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    compose = v2.WorkspaceTests.compose
    open = v2.WorkspaceTests.open

    def action(self, name, **values):
        self.w.handle({'id': str(uuid.uuid4()), 'action': name, **values})

    def test_real_stages_exact_mime_navigation_reading_and_no_render_io(self):
        draft = self.compose()
        draft.update(cc='cc@example.test', bcc='private@example.test')
        draft['attachments'] = [make_attachment('note.txt', b'exact attachment')]
        op = draft['operation_id']
        with patch('support_email_workspace.build_mime', wraps=v2.compose.build_mime) as build:
            self.action('send', operation_id=op)
            self.assertEqual(self.w.model()['send_stage'], 'SENDING')
            build.assert_called_once()
            for _ in range(3): self.w.model()
            self.smtp.submit.assert_not_called()
            self.assertFalse(self.imap.appended)
            save = self.w.registry.save_sent
            def saving(*args, **kwargs):
                self.assertEqual(self.w.model()['send_stage'], 'SAVING_SENT_COPY')
                return save(*args, **kwargs)
            with patch.object(self.w.registry, 'save_sent', side_effect=saving):
                self.action('advance_send', operation_id=op)
            self.smtp.submit.assert_called_once()
            # SMTP and storage finish server-side without another browser event.
            self.assertEqual(len(self.imap.appended), 1)
            self.action('advance_send', operation_id=op)
        result = self.w.model()
        self.assertEqual(result['send_stage'], 'SENT')
        self.assertEqual(result['send_progress'], {})
        self.assertEqual(result['view'], 'mail')
        self.assertIsNone(result['draft'])
        self.assertEqual(result['folder'], 'INBOX.Sent Items')
        self.assertEqual(result['threads'][0]['subject'], 'Fixture subject')
        self.assertEqual(result['selected'], result['threads'][0]['key'])
        self.assertIn('Fixture body', result['messages'][0]['html'])
        self.assertEqual(result['messages'][0]['attachments'][0]['filename'], 'note.txt')
        self.assertTrue(result['send_result']['sent_at'])
        self.assertEqual(len(self.imap.appended), 1)
        sent_mime = self.smtp.submit.call_args.args[0]
        self.assertEqual(sent_mime['bytes'], self.imap.appended[0])
        parsed = BytesParser(policy=policy.default).parsebytes(sent_mime['bytes'])
        self.assertIn('private@example.test', sent_mime['recipients'])
        self.assertNotIn('Bcc', parsed)  # SMTP envelope preserves Bcc without disclosing it.
        for header in ('Message-ID', 'Date', 'To', 'Cc', 'From', 'Subject'):
            self.assertTrue(parsed[header])
        self.assertEqual(next(parsed.iter_attachments()).get_payload(decode=True), b'exact attachment')
        for _ in range(3):
            self.action('advance_send', operation_id=op)
            self.action('send', operation_id=op)
            self.w.model()
        self.smtp.submit.assert_called_once()
        self.assertEqual(len(self.imap.appended), 1)

    def test_validation_failure_is_editable_and_does_not_leave_five_percent(self):
        draft = self.compose(); draft['to'] = 'invalid'
        self.action('send', operation_id=draft['operation_id'])
        self.assertEqual(self.w.model()['send_stage'], 'VALIDATION_FAILED')
        self.assertFalse(self.state.get('send_result'))
        self.assertEqual(self.state['send_progress'], {})
        self.smtp.submit.assert_not_called()
        self.assertFalse(self.imap.appended)
        draft['to'] = 'valid@example.test'
        self.event('send', operation_id=draft['operation_id'])
        self.assertEqual(self.state['send_stage'], 'SENT')

    def test_transport_rejected_never_creates_sent_copy(self):
        self.smtp.submit.return_value = {'status': 'rejected', 'notice': 'Nothing was sent.'}
        draft = self.compose(); self.event('send', operation_id=draft['operation_id'])
        self.assertEqual(self.state['send_stage'], 'REJECTED')
        self.assertFalse(self.imap.appended)
        self.assertFalse(self.state.get('last_sent'))
        self.assertEqual(self.state['view'], 'compose')

    def test_post_send_view_failure_cannot_downgrade_or_retransmit(self):
        op = self.compose()['operation_id']
        with patch.object(self.w, '_show_sent', side_effect=RuntimeError('private server text')):
            self.event('send', operation_id=op)
        self.assertEqual(self.w.model()['send_stage'], 'SENT')
        self.assertEqual(self.w.model()['send_progress'], {})
        self.assertIsNone(self.state['draft'])
        self.assertIn('Email sent.', self.state['notice'])
        self.assertNotIn('private server text', self.state['notice'])
        self.event('advance_send', operation_id=op)
        self.smtp.submit.assert_called_once()

    def test_failed_copy_retry_survives_new_compose_and_never_retransmits(self):
        draft = self.compose(); op = draft['operation_id']
        with patch.object(self.imap, 'append_message', side_effect=MailboxError('Safe', code='append_rejected')):
            self.event('send', operation_id=op)
        self.assertEqual(self.state['send_stage'], 'CONFIRMING_SENT_COPY')
        self.assertEqual(self.state['send_result']['status'], 'accepted')
        self.assertTrue(self.w.model()['last_sent']['copy']['retryable'])
        self.assertIn(op, self.state['pending_sent'])
        self.event('compose')
        current_draft = self.state['draft']
        self.event('retry_sent_copy', operation_id=op)
        self.assertIs(self.state['draft'], current_draft)
        self.assertEqual(self.state['view'], 'compose')
        self.assertNotIn(op, self.state['pending_sent'])
        self.smtp.submit.assert_called_once()
        self.assertEqual(len(self.imap.appended), 1)

    def test_old_pending_copy_survives_later_successful_send(self):
        first = self.compose()['operation_id']
        with patch.object(self.imap, 'append_message', side_effect=MailboxError('Safe', code='append_not_started')):
            self.event('send', operation_id=first)
        second = self.compose()['operation_id']
        self.event('send', operation_id=second)
        self.assertEqual(self.w.model()['pending_sent'][0]['operation_id'], first)
        self.event('retry_sent_copy', operation_id=first)
        self.assertFalse(self.w.model()['pending_sent'])
        self.assertEqual(self.smtp.submit.call_count, 2)
        self.assertEqual(len(self.imap.appended), 2)

    def test_uncertain_append_can_only_verify_never_append_twice(self):
        draft = self.compose(); append = self.imap.append_message
        def interrupted(*args, **kwargs):
            append(*args, **kwargs)
            raise MailboxError('Connection lost after APPEND')
        with patch.object(self.imap, 'append_message', side_effect=interrupted) as mocked:
            self.event('send', operation_id=draft['operation_id'])
            self.assertEqual(self.state['send_stage'], 'CONFIRMING_SENT_COPY')
            self.assertFalse(self.state['sent_result'].get('retryable'))
            self.event('retry_sent_copy', operation_id=draft['operation_id'])
            self.assertEqual(self.state['sent_result']['status'], 'present')
            mocked.assert_called_once()
        self.smtp.submit.assert_called_once()

    def test_unknown_transport_never_saves_or_resubmits(self):
        self.smtp.submit.return_value = {'status': 'unknown', 'notice': 'Do not resend.'}
        op = self.compose()['operation_id']; self.event('send', operation_id=op)
        self.event('advance_send', operation_id=op)
        self.event('retry_sent_copy', operation_id=op)
        self.event('check_sent')
        self.assertFalse(self.imap.appended)
        self.smtp.submit.assert_called_once()
        self.assertEqual(self.state['send_stage'], 'UNKNOWN')

    def test_retry_event_cannot_override_confirmed_server_saving(self):
        self.state['settings']['sent_policy'] = 'server'
        op = self.compose()['operation_id']; self.event('send', operation_id=op)
        self.event('retry_sent_copy', operation_id=op)
        self.assertFalse(self.imap.appended)
        self.smtp.submit.assert_called_once()

    def test_rerun_after_smtp_acceptance_recovers_without_progress_bridge(self):
        op = self.compose()['operation_id']; self.action('send', operation_id=op)
        def submit(mime, *, mailbox, progress):
            progress(100, 'Sent')
            raise KeyboardInterrupt('Simulated script interruption after SMTP 250')
        self.smtp.submit.side_effect = submit
        with self.assertRaises(KeyboardInterrupt): self.action('advance_send', operation_id=op)
        self.w = Workspace(self.state, USER, CONFIG, v2.SMTP_CONFIG, imap=self.imap,
                           smtp=self.smtp, registry=self.w.registry)
        self.assertEqual(self.w.model()['send_stage'], 'SAVING_SENT_COPY')
        self.action('advance_send', operation_id=op)
        self.assertEqual(self.w.model()['send_stage'], 'SENT')
        self.smtp.submit.assert_called_once()
        self.assertEqual(len(self.imap.appended), 1)

    def test_rerun_after_append_acceptance_finds_exact_copy(self):
        op = self.compose()['operation_id']; self.action('send', operation_id=op)
        original = self.imap.append_message
        def append(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt()
        with patch.object(self.imap, 'append_message', side_effect=append) as mocked:
            with self.assertRaises(KeyboardInterrupt): self.action('advance_send', operation_id=op)
            self.action('advance_send', operation_id=op)
            mocked.assert_called_once()
        self.assertEqual(self.w.model()['send_stage'], 'SENT')
        self.smtp.submit.assert_called_once()

    def test_existing_server_copy_is_reused_and_external_sent_mail_is_retained(self):
        op = self.compose()['operation_id']; self.action('send', operation_id=op)
        mime = self.state['outgoing_mime']
        self.imap.append_message('INBOX.Sent Items', mime['bytes'])
        external = v2.header('600', '<external@example.test>', subject='Sent from another client', hours=-10)
        external['folder'] = 'INBOX.Sent Items'; self.imap.messages.append(external)
        with patch.object(self.imap, 'append_message', wraps=self.imap.append_message) as append:
            self.action('advance_send', operation_id=op); self.action('advance_send', operation_id=op)
            append.assert_not_called()
        self.assertEqual(len(self.w.model()['threads']), 2)
        self.assertEqual(self.state['sent_result']['status'], 'present')

    def test_concurrent_copy_claim_is_serialized_across_workspaces(self):
        op = self.compose()['operation_id']; self.action('send', operation_id=op)
        mime = self.state['outgoing_mime']
        self.w.registry.submit(op, MAILBOX, mime, self.smtp)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.w.registry.save_sent(op, MAILBOX, self.imap, mime, 'INBOX.Sent Items', 'append'), range(24)))
        self.assertEqual(len(self.imap.appended), 1)
        self.smtp.submit.assert_called_once()

    def test_page_has_no_streamlit_progress_bridge_inside_transport(self):
        import support_email_page
        self.assertNotIn('progress_callback', inspect.getsource(support_email_page))
        self.assertNotIn('percent', inspect.getsource(Workspace.model))
        for _ in range(5): self.w.model()
        self.smtp.submit.assert_not_called()
        self.assertFalse(self.imap.appended)


class SentFolderTests(unittest.TestCase):
    def test_connection_failure_before_append_can_be_retried(self):
        adapter, wire = v2.FolderTests().adapter()
        adapter.connection_factory = Mock(side_effect=TimeoutError())
        with self.assertRaises(MailboxError) as exc: adapter.append_message('Sent', b'MIME')
        self.assertEqual(exc.exception.code, 'append_not_started')
        self.assertFalse(any(c[0] == 'append' for c in wire.calls))

    def test_append_invalidates_shared_mailbox_snapshots(self):
        from support_email_runtime import MailboxRuntime
        adapter, wire = v2.FolderTests().adapter()
        adapter.runtime = MailboxRuntime()
        scope = adapter.configuration.scope
        before = adapter.runtime.generation(scope)
        adapter.runtime.put(scope, ('status', 'Sent'), {'messages': 0}, before)
        adapter.append_message('Sent', b'MIME')
        self.assertGreater(adapter.runtime.generation(scope), before)
        self.assertIsNone(adapter.runtime.get(scope, ('status', 'Sent')))

    def test_unambiguous_observed_fallback_names_only(self):
        for name in ('Sent', 'Sent Items', 'Sent Messages', 'INBOX.Sent'):
            self.assertEqual(folder_roles(parse_folders([f'() "/" "{name}"'.encode()]))['sent'], name)
        self.assertNotIn('sent', folder_roles(parse_folders([b'() "/" "Sent"', b'() "/" "Sent Items"'])))
        self.assertNotIn('sent', folder_roles(parse_folders([b'() "/" "Old Sent Backup"'])))
        folders = parse_folders([b'(\\Sent) "/" "Actual Sent"', b'() "/" "Sent"'])
        self.assertEqual(folder_roles(folders)['sent'], 'Actual Sent')

    def test_append_is_seen_exact_bytes_and_rejected_is_safe_to_retry(self):
        adapter, wire = v2.FolderTests().adapter()
        raw = b'From: fixture@example.test\r\nMessage-ID: <fixture@example.test>\r\n\r\nFixture'
        adapter.append_message('INBOX.Sent Items', raw)
        call = next(c for c in wire.calls if c[0] == 'append')
        self.assertEqual(call[1], '"INBOX.Sent Items"')
        self.assertEqual(call[2], '(\\Seen)')
        self.assertEqual(call[-1], raw)
        wire.append = Mock(return_value=('NO', [b'private server text']))
        with self.assertRaises(MailboxError) as exc: adapter.append_message('INBOX.Sent Items', raw)
        self.assertEqual(exc.exception.code, 'append_rejected')
        self.assertNotIn('private', str(exc.exception))


if __name__ == '__main__': unittest.main()
