"""Offline body-laziness, retry and isolation contracts using the real controller."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from support_email_cache import DisplayLRU
from support_email_provider import MailboxError
from support_email_workspace import Workspace, reference_key
from tests import test_support_email_v2 as fixtures


class LazyConversationTests(unittest.TestCase):
    def setUp(self):
        self.f = f = fixtures.WorkspaceTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        thread = deepcopy(f.state['threads'][0])
        original = thread['messages'][0]
        thread['messages'] = [dict(deepcopy(original), uid=str(i + 1000),
                                   message_id=f'<lazy-{i}@example.test>', snippet=f'Preview {i}')
                              for i in range(120)]
        f.imap.messages.extend(deepcopy(thread['messages']))
        self.thread = thread
        f.state['thread_index'][thread['thread_key']] = thread
        self.key = thread['thread_key']
        f.imap.calls.clear()

    def event(self, action, **values):
        return self.f.event(action, **values)

    def open(self):
        self.event('open_thread', thread_key=self.key)

    def bodies(self):
        return [c for c in self.f.imap.calls if c[0] == 'body']

    def test_120_message_open_fetches_first_only_and_omits_collapsed_content(self):
        self.open()
        rows = self.f.w.model()['messages']
        self.assertEqual(len(rows), 120)
        self.assertEqual(self.bodies(), [('body', '1000')])
        self.assertTrue(rows[0]['expanded'])
        self.assertEqual(self.f.state['active_message'], rows[0]['key'])
        self.assertEqual([m['key'] for m in rows], [reference_key(m) for m in self.thread['messages']])
        for row in rows[1:]:
            self.assertFalse(row['expanded'])
            self.assertEqual(row['attachments'], [])
            self.assertTrue(row['preview'].startswith('Preview'))
            for field in ('html', 'reader_document', 'quote', 'approved_reader_document'):
                self.assertNotIn(field, row)
        self.assertFalse(any(c[0] in {'attachment', 'related', 'headers'} for c in self.f.imap.calls))

    def test_expand_collapse_reopen_and_thread_reopen_reuse_content(self):
        self.open()
        key = reference_key(self.thread['messages'][5])
        self.event('open_message', message_key=key)
        self.assertEqual(self.bodies(), [('body', '1000'), ('body', '1005')])
        self.event('collapse_message', message_key=key)
        row = next(r for r in self.f.w.model()['messages'] if r['key'] == key)
        self.assertNotIn('html', row)
        self.event('open_message', message_key=key)
        self.open()
        self.assertEqual(len(self.bodies()), 2)
        self.assertEqual(sum(m['expanded'] for m in self.f.w.model()['messages']), 1)

    def test_old_auto_hydration_client_cannot_download_collapsed_messages(self):
        self.open()
        self.event('load_conversation_body', thread_key=self.key,
                   message_key=reference_key(self.thread['messages'][3]))
        self.assertEqual(len(self.bodies()), 1)

    def test_failure_retry_is_message_local_and_does_not_refetch_list(self):
        self.open()
        key = reference_key(self.thread['messages'][2])
        with patch.object(self.f.imap, 'read_message', side_effect=MailboxError('Synthetic failure')):
            self.event('open_message', message_key=key)
        rows = self.f.w.model()['messages']
        self.assertTrue(rows[0]['expanded'])
        self.assertTrue(rows[2]['body_error'])
        self.assertFalse(rows[2]['body_loading'])
        self.event('open_message', message_key=key)
        row = self.f.w.model()['messages'][2]
        self.assertTrue(row['expanded'])
        self.assertFalse(row['body_error'])
        self.assertEqual(len(self.bodies()), 2)

    def test_pending_feedback_and_stale_completion_after_switch_are_ignored(self):
        with patch.object(self.f.imap, 'read_message', side_effect=MailboxError('Pending', code='pending')):
            self.open()
        old = reference_key(self.thread['messages'][0])
        row = self.f.w.model()['messages'][0]
        self.assertTrue(row['body_loading'])
        self.assertNotIn('html', row)
        self.event('open_thread', thread_key=self.f.state['threads'][1]['thread_key'])
        selected = self.f.state['selected']
        before = len(self.bodies())
        self.event('load_visible_body', message_key=old)
        self.assertEqual(self.f.state['selected'], selected)
        self.assertEqual(len(self.bodies()), before)

    def test_deferred_failure_retry_clears_completion_and_loading(self):
        with patch.object(self.f.imap, 'read_message', side_effect=MailboxError('Pending', code='pending')):
            self.open()
        key = self.f.state['active_message']
        with patch.object(self.f.imap, 'read_message', side_effect=MailboxError('Unavailable')):
            self.event('load_visible_body', message_key=key)
        row = self.f.w.model()['messages'][0]
        self.assertFalse(row['body_loading'])
        self.assertTrue(row['body_error'])
        self.assertFalse(self.f.w.model()['body_completion'])
        self.event('open_message', message_key=key)
        self.assertTrue(self.f.w.model()['messages'][0]['expanded'])

    def test_account_scope_clears_body_and_resolved_header_caches(self):
        self.open()
        self.f.w.resolved_threads.put(('old', self.key), self.thread['messages'])
        changed = dict(self.f.user if hasattr(self.f, 'user') else fixtures.USER, id='another-actor')
        w = Workspace(self.f.state, changed, fixtures.CONFIG, fixtures.SMTP_CONFIG,
                      imap=self.f.imap, smtp=self.f.smtp)
        self.assertFalse(w.bodies.data['entries'])
        self.assertFalse(w.resolved_threads.data['entries'])

    def test_reply_to_expanded_later_message_keeps_exact_source_and_reader(self):
        self.open()
        source = self.thread['messages'][5]
        key = reference_key(source)
        self.event('open_message', message_key=key)
        before = len(self.bodies())
        self.event('compose', mode='reply', message_key=key)
        self.assertEqual(self.f.state['draft']['source_message']['message_id'], source['message_id'])
        self.assertEqual(self.f.state['active_message'], key)
        self.assertIn(key, self.f.state['expanded'])
        self.assertEqual(len(self.bodies()), before)
        self.event('close_composer')
        self.assertEqual(self.f.state['active_message'], key)
        self.assertTrue(next(m for m in self.f.w.model()['messages'] if m['key'] == key)['expanded'])

    def test_collapse_all_cancels_pending_body_without_completion_loop(self):
        with patch.object(self.f.imap, 'read_message', side_effect=MailboxError('Pending', code='pending')):
            self.open()
        key = self.f.state['active_message']
        self.event('collapse_conversation')
        self.assertFalse(self.f.state.get('body_pending'))
        self.assertFalse(self.f.state.get('body_loading'))
        self.event('load_visible_body', message_key=key)
        self.assertEqual(self.bodies(), [])

    def test_changed_header_snapshot_preserves_expansion_and_action_target(self):
        messages = deepcopy(self.thread['messages'][:3])
        for i, m in enumerate(messages):
            m.update(references=() if i == 0 else (messages[0]['message_id'],),
                     flags=('\\Seen',), unread=False)
        self.f.imap.messages = messages
        self.f.state.update(selected=None, conversation=[])
        self.f.w.load(force=True, previews=False)
        self.key = self.f.state['threads'][0]['thread_key']
        self.open()
        key = reference_key(messages[-1])
        self.event('open_message', message_key=key)
        expanded = set(self.f.state['expanded'])
        before = len(self.bodies())
        messages[0]['flags'] = ('\\Seen', '\\Flagged')
        self.f.w.load(force=True, previews=False, defer_body=True)
        self.assertEqual(self.f.state['active_message'], key)
        self.assertEqual(self.f.state['expanded'], expanded)
        self.assertEqual(len(self.bodies()), before)

    def test_inbox_sync_keeps_expanded_cross_folder_reply_selected(self):
        original = deepcopy(self.thread['messages'][0])
        original.update(flags=('\\Seen',), unread=False)
        sent = deepcopy(original)
        sent.update(uid='4000', message_id='<sent-history@example.test>',
                    folder='INBOX.Sent Items', references=(original['message_id'],))
        self.f.imap.messages = [original, sent]
        self.f.state.update(selected=None, conversation=[])
        self.f.w.load(force=True, previews=False)
        self.key = self.f.state['threads'][0]['thread_key']
        self.open()
        self.event('resolve_thread', thread_key=self.key, mailbox_version=self.f.state['mailbox_version'])
        key = reference_key(sent)
        self.event('open_message', message_key=key)
        before = len(self.bodies())
        original['flags'] = ('\\Seen', '\\Flagged')
        self.f.w.load(force=True, previews=False, defer_body=True)
        self.assertEqual(self.f.state['active_message'], key)
        self.assertTrue(next(m for m in self.f.w.model()['messages'] if m['key'] == key)['expanded'])
        self.assertEqual(len(self.bodies()), before)
        # Compose can race the deferred history lookup after this Inbox refresh.
        self.event('compose', mode='forward', message_key=key)
        self.assertEqual(self.f.state['active_message'], key)
        self.assertTrue(any(m['key'] == key for m in self.f.w.model()['messages']))
        self.event('close_composer')
        self.assertTrue(next(m for m in self.f.w.model()['messages'] if m['key'] == key)['expanded'])
        self.assertEqual(len(self.bodies()), before)

    def test_cache_count_and_byte_limits_stay_strict_for_long_threads(self):
        cache = DisplayLRU({}, 'bodies', limit=2, byte_limit=100)
        for key in range(120):
            self.assertTrue(cache.put(key, 'body'))
        self.assertEqual(len(cache.data['entries']), 2)
        self.assertLessEqual(cache.data['bytes'], 100)
        self.assertFalse(cache.put('oversize', 'x' * 100))


if __name__ == '__main__':
    unittest.main()
