"""Trash-only permanent deletion: no real mailbox, SMTP or database access."""
from contextlib import ExitStack
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
import uuid

import support_email_provider as provider
import support_email_smtp as smtp
import support_email_store as store
from support_email_compose import default_settings
from support_email_workspace import Workspace, reference_key
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp, FOLDER_DATA
from tests.test_support_email import CONFIG, USER, header


class TrashMailbox(MailboxFixture):
    def __init__(self):
        super().__init__(0)
        first = header('1', '<trash-root@example.test>', subject='Disposable Trash conversation')
        second = header('2', '<trash-reply@example.test>', refs=('<trash-root@example.test>',))
        other = header('3', '<unrelated@example.test>', subject='Keep this Trash message')
        outside = header('4', '<sent-related@example.test>', refs=('<trash-root@example.test>',))
        for message in (first, second, other):
            message['folder'] = 'Trash'
        outside['folder'] = 'INBOX.Sent Items'
        self.messages = [first, second, other, outside]
        self.delete_error = None

    def delete_trash_messages(self, headers, **kwargs):
        self.calls.append(('delete', deepcopy(headers), kwargs))
        if self.delete_error:
            raise self.delete_error
        keys = {reference_key(h) for h in headers}
        self.messages = [m for m in self.messages if reference_key(m) not in keys]
        return {'status': 'deleted'}


class TrashWorkspaceTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(provider.imaplib, 'IMAP4_SSL', side_effect=AssertionError('No live IMAP')))
        stack.enter_context(patch.object(smtp.smtplib, 'SMTP_SSL', side_effect=AssertionError('No live SMTP')))
        stack.enter_context(patch.object(store, 'load_email_settings', return_value=(default_settings(), None)))
        self.audit = stack.enter_context(patch.object(store, 'audit'))
        self.mailbox, self.transport, self.state = TrashMailbox(), fixture_smtp(), {'folder': 'Trash'}
        self.w = Workspace(self.state, USER, CONFIG, smtp.SMTPConfiguration(password='fixture'),
                           imap=self.mailbox, smtp=self.transport, registry=smtp.SendRegistry())
        self.w.load()
        self.thread = next(t for t in self.state['threads'] if len(t['messages']) == 2)

    def event(self, action, **values):
        event = {'id': str(uuid.uuid4()), 'action': action, **values}
        self.w.handle(event)
        return event

    def request(self):
        self.event('request_delete_forever', thread_key=self.thread['thread_key'])
        return self.state['delete_confirmation']['token']

    def deletes(self):
        return [c for c in self.mailbox.calls if c[0] == 'delete']

    def test_request_and_cancel_never_mutate(self):
        token = self.request()
        self.assertEqual(self.w.model()['delete_confirmation']['count'], 2)
        self.assertNotIn('messages', self.w.model()['delete_confirmation'])
        self.event('cancel_delete_forever', token=token)
        self.event('confirm_delete_forever', token=token)
        self.assertEqual(self.deletes(), [])
        self.assertEqual(len(self.mailbox.messages), 4)

    def test_success_exact_thread_refresh_count_reading_pane_and_replay(self):
        self.w.open_thread(self.thread['thread_key'])
        # Reading history can contain Sent; deletion must never use this list.
        self.state['conversation'] = [*self.state['conversation'], deepcopy(self.mailbox.messages[-1])]
        token = self.request()
        event = self.event('confirm_delete_forever', token=token)
        self.assertFalse(self.w.handle(event))
        self.event('confirm_delete_forever', token=token)
        Workspace(self.state, USER, CONFIG, self.w.smtp_config, imap=self.mailbox, smtp=self.transport).model()
        self.assertEqual(len(self.deletes()), 1)
        self.assertEqual({m['uid'] for m in self.deletes()[0][1]}, {'1', '2'})
        self.assertEqual({m['uid'] for m in self.mailbox.messages}, {'3', '4'})
        self.assertEqual(len(self.w.model()['threads']), 1)
        self.assertEqual(self.state['snapshot']['total'], 1)
        self.assertEqual(self.state['conversation'], [])
        self.assertIsNone(self.state['selected'])
        self.assertIsNone(self.state['active_message'])
        self.assertGreaterEqual(len([c for c in self.mailbox.calls if c[0] == 'headers']), 2)
        self.assertEqual(self.state['notice'], 'Permanently deleted from Trash.')
        self.transport.submit.assert_not_called()

    def test_failure_keeps_row_and_consumes_confirmation(self):
        self.mailbox.delete_error = RuntimeError('secret-password')
        token = self.request(); self.event('confirm_delete_forever', token=token)
        self.event('confirm_delete_forever', token=token)
        self.assertEqual(len(self.deletes()), 1)
        self.assertEqual(len(self.w.model()['threads']), 2)
        self.assertEqual(len(self.mailbox.messages), 4)
        self.assertIn('Could not permanently delete', self.state['notice'])
        self.assertNotIn('secret-password', str(self.w.model()))

    def test_uncertain_partial_result_is_explicit_and_not_optimistic(self):
        self.mailbox.delete_error = provider.MailboxError('Some may have been deleted. Refresh Trash before trying again.', code='delete_uncertain')
        token = self.request(); self.event('confirm_delete_forever', token=token)
        self.assertIn('Some may have been deleted', self.state['notice'])
        self.assertEqual(len(self.state['threads']), 2)

    def test_only_trash_mail_view_and_real_row_can_request(self):
        for folder, view, key in [('INBOX', 'mail', self.thread['thread_key']), ('Trash', 'compose', self.thread['thread_key']),
                                  ('Trash', 'mail', 'forged')]:
            self.state.update(folder=folder, view=view)
            self.event('request_delete_forever', thread_key=key)
            self.assertNotIn('delete_confirmation', self.state)
        self.assertEqual(self.deletes(), [])

    def test_wrong_token_navigation_and_changed_mapping_cannot_delete(self):
        token = self.request(); self.event('confirm_delete_forever', token='forged')
        self.assertIn('delete_confirmation', self.state)
        self.event('folder', folder='INBOX')
        self.event('confirm_delete_forever', token=token)
        self.assertEqual(self.deletes(), [])
        self.event('folder', folder='Trash'); token = self.request()
        self.state['settings']['folder_mapping']['trash'] = 'Customers'
        self.event('confirm_delete_forever', token=token)
        self.assertEqual(self.deletes(), [])

    def test_confirmation_does_not_expand_to_new_thread_members(self):
        token = self.request()
        arrived = header('5', '<new@example.test>', refs=('<trash-root@example.test>',)); arrived['folder'] = 'Trash'
        self.mailbox.messages.append(arrived)
        self.w.load(force=True)
        self.event('confirm_delete_forever', token=token)
        self.assertIn('5', {m['uid'] for m in self.mailbox.messages})

    def test_empty_trash_normal_empty_model(self):
        for thread in list(self.state['threads']):
            self.thread = thread
            self.event('confirm_delete_forever', token=self.request())
        self.assertEqual(self.w.model()['threads'], [])
        self.assertEqual(self.state['snapshot']['total'], 0)
        self.assertEqual([m['folder'] for m in self.mailbox.messages], ['INBOX.Sent Items'])

    def test_repeated_request_keeps_one_confirmation_and_no_mutation(self):
        token = self.request()
        self.assertEqual(token, self.request())
        self.w.model(); self.w.model()
        self.assertEqual(self.deletes(), [])

    def test_confirmed_success_uses_existing_safe_audit(self):
        self.event('confirm_delete_forever', token=self.request())
        self.assertEqual(self.audit.call_args.args[0], 'email_permanently_deleted')
        self.assertRegex(self.audit.call_args.args[1], r'^[a-f0-9]{64}$')

    def test_refresh_failure_after_success_does_not_restore_deleted_rows(self):
        token = self.request()
        self.mailbox.fail = True
        self.event('confirm_delete_forever', token=token)
        self.assertEqual(len(self.w.model()['threads']), 1)
        self.assertIn('Permanently deleted', self.state['notice'])
        self.assertIn('refresh is temporarily unavailable', self.state['notice'])


class TargetedImap:
    capabilities = (b'IMAP4REV1', b'UIDPLUS')

    def __init__(self):
        self.calls, self.messages, self.deleted = [], {'1', '2', '99'}, {'99'}
        self.validity, self.failure = b'500', ''
        self.folder_data = FOLDER_DATA

    def login(self, *args): return 'OK', [b'authenticated']
    def select(self, folder, readonly=False):
        self.calls.append(('select', folder, readonly)); return 'OK', [b'3']
    def response(self, name): return name, [self.validity]
    def list(self): return 'OK', self.folder_data
    def logout(self): self.calls.append(('logout',))
    def shutdown(self): pass

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == 'SEARCH':
            criteria = args[-1].decode().split()
            found = self.messages.intersection(criteria[1].split(','))
            if 'DELETED' in criteria: found &= self.deleted
            return 'OK', [' '.join(sorted(found)).encode()]
        uids = set(args[0].split(','))
        if command == 'STORE':
            if args[1] == '+FLAGS.SILENT':
                if self.failure == 'store': return 'NO', [b'rejected']
                self.deleted |= uids & self.messages
            else: self.deleted -= uids
        if command == 'EXPUNGE':
            if self.failure == 'reject': return 'NO', [b'rejected']
            if self.failure in {'partial', 'disconnect'}:
                self.messages.discard('1')
                if self.failure == 'disconnect': raise TimeoutError('private secret')
            else: self.messages -= uids & self.deleted
        return 'OK', [b'']


class TrashProviderTests(unittest.TestCase):
    def setUp(self):
        self.server = TargetedImap()
        self.factory = Mock(return_value=self.server)
        self.p = provider.ImapProvider(CONFIG, connection_factory=self.factory)
        self.headers = [dict(header(str(i)), folder='Trash') for i in (1, 2)]

    def delete(self):
        return self.p.delete_trash_messages(self.headers, trash_folder='Trash')

    def test_uid_set_only_and_unrelated_predeleted_message_retained(self):
        self.assertEqual(self.delete()['status'], 'deleted')
        self.assertEqual(self.server.messages, {'99'})
        self.assertEqual(self.server.deleted.intersection(self.server.messages), {'99'})
        self.assertEqual([c for c in self.server.calls if c[0] == 'EXPUNGE'], [('EXPUNGE', '1,2')])
        self.assertIn(('select', '"Trash"', False), self.server.calls)
        self.assertFalse(any(c[0].lower() == 'close' for c in self.server.calls))

    def test_server_without_targeted_expunge_does_not_mark_or_delete(self):
        self.server.capabilities = (b'IMAP4REV1',)
        with self.assertRaisesRegex(provider.MailboxError, 'safe targeted deletion'): self.delete()
        self.assertFalse(any(c[0] in {'STORE', 'EXPUNGE'} for c in self.server.calls))

    def test_uidvalidity_change_prevents_any_mutation(self):
        self.server.validity = b'501'
        with self.assertRaises(provider.MailboxError): self.delete()
        self.assertFalse(any(c[0] in {'STORE', 'EXPUNGE'} for c in self.server.calls))

    def test_mixed_folder_validity_and_uid_injection_rejected(self):
        for field, value in [('folder', 'INBOX'), ('uidvalidity', '501'), ('uid', '1:*'), ('uid', '1,99')]:
            with self.subTest(field=field, value=value):
                original = self.headers[1][field]; self.headers[1][field] = value
                with self.assertRaises(provider.MailboxError): self.delete()
                self.headers[1][field] = original
        self.factory.assert_not_called()

    def test_mapping_cannot_delete_real_sent_or_inbox(self):
        for folder in ['INBOX', 'INBOX.Sent Items']:
            headers = [dict(self.headers[0], folder=folder)]
            with self.assertRaises(provider.MailboxError):
                self.p.delete_trash_messages(headers, trash_folder=folder, folder_mapping={'trash': folder})
        self.assertFalse(any(c[0] in {'STORE', 'EXPUNGE'} for c in self.server.calls))

    def test_special_use_custom_wire_name_and_explicit_mapping_supported(self):
        for data, mapping in [([b'(\\Trash) "/" "INBOX.Deleted Items"'], {}),
                              ([b'() "/" "INBOX.Deleted Items"'], {'trash': 'INBOX.Deleted Items'})]:
            server = TargetedImap(); server.folder_data = data
            p = provider.ImapProvider(CONFIG, connection_factory=Mock(return_value=server))
            self.assertEqual(p.delete_trash_messages([dict(self.headers[0], folder='INBOX.Deleted Items')],
                trash_folder='INBOX.Deleted Items', folder_mapping=mapping)['status'], 'deleted')

    def test_rejection_partial_or_disconnect_never_retries_and_rolls_back_own_flags(self):
        for failure in ['store', 'reject', 'partial', 'disconnect']:
            with self.subTest(failure=failure):
                self.server = TargetedImap(); self.factory.return_value = self.server; self.server.failure = failure
                with self.assertRaisesRegex(provider.MailboxError, 'Could not permanently delete' if failure == 'store' else 'Some may have been deleted'): self.delete()
                self.assertLessEqual(len([c for c in self.server.calls if c[0] == 'EXPUNGE']), 1)
                self.assertIn('99', self.server.messages)
                self.assertEqual(self.server.deleted.intersection(self.server.messages), {'99'})

    def test_reconfirmed_already_absent_uid_does_not_issue_commands(self):
        self.delete(); self.server.calls.clear()
        self.assertEqual(self.delete()['status'], 'deleted')
        self.assertFalse(any(c[0] in {'STORE', 'EXPUNGE'} for c in self.server.calls))

    def test_audit_whitelist_retains_safe_fixed_description(self):
        with patch('activity_log.record_activity_log') as record:
            store.audit('email_permanently_deleted', 'a'*64, actor='Fixture')
        record.assert_called_once_with('email_permanently_deleted', 'Email', 'Email permanently deleted from Trash',
            entity_type='customer_support_thread', entity_id='a'*64, actor='Fixture')


if __name__ == '__main__':
    unittest.main()
