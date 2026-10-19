"""Offline regressions for automatic conversation hydration and sender layout."""
from copy import deepcopy
import unittest
import uuid
from unittest.mock import patch

from support_email_cache import DisplayLRU
from support_email_render import sanitize_received_html, reader_document
from support_email_workspace import reference_key
from support_email_provider import MailboxError
from tests import test_support_email_v2 as fixtures


class FullConversationTests(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.WorkspaceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def event(self, fixture, action, **values):
        fixture.w.handle(dict(id=str(uuid.uuid4()), action=action, **values))

    def test_all_cached_bodies_visible_without_expanded_state(self):
        f = self.fixture()
        thread = f.state['threads'][0]
        f.w._select_thread(thread)
        first = f.state['conversation'][0]
        other = deepcopy(first)
        other.update(uid='999', message_id='<synthetic-other@example.test>')
        f.state['conversation'] = [first, other]
        f.w.bodies.clear()
        f.imap.calls.clear()
        for message in f.state['conversation']:
            self.event(f, 'load_conversation_body', thread_key=thread['thread_key'], message_key=reference_key(message))
        f.state['expanded'] = set()
        self.assertTrue(all(m['expanded'] for m in f.w.model()['messages']))
        self.assertEqual(sum(c[0] == 'body' for c in f.imap.calls), 2)
        for message in f.state['conversation']:
            self.event(f, 'load_conversation_body', thread_key=thread['thread_key'], message_key=reference_key(message))
        self.assertEqual(sum(c[0] == 'body' for c in f.imap.calls), 2)

    def test_stale_thread_and_unselected_inbox_bodies_never_loaded(self):
        f = self.fixture()
        f.w.bodies.clear()
        f.imap.calls.clear()
        f.w.model()
        self.event(f, 'load_conversation_body', thread_key='stale', message_key=f.state.get('active_message'))
        self.assertFalse(any(c[0] == 'body' for c in f.imap.calls))

    def test_historical_async_completion_without_changing_action_target(self):
        f = self.fixture()
        thread = f.state['threads'][0]
        active = f.w._select_thread(thread)
        other = deepcopy(active)
        other.update(uid='999', message_id='<async-history@example.test>')
        f.state['conversation'].append(other)
        key = reference_key(other)
        with patch.object(f.imap, 'read_message', side_effect=MailboxError('Pending', code='pending')):
            self.event(f, 'load_conversation_body', thread_key=thread['thread_key'], message_key=key)
        self.assertEqual(f.state['body_pending'], key)
        f.state['body_completion'] = {'ticket': 'synthetic'}
        self.assertEqual(f.w.model()['body_completion'], {'ticket': 'synthetic'})
        self.event(f, 'load_visible_body', message_key=key)
        self.assertEqual(f.state['active_message'], reference_key(active))
        self.assertTrue(next(m for m in f.w.model()['messages'] if m['key'] == key)['expanded'])

    def test_unsafe_text_geometry_removed_and_image_privacy_retained(self):
        safe = sanitize_received_html('<div height="2" style="height:2px;line-height:0;margin-top:-50px;position:absolute">'
                                      '<p>First</p><p>Second</p></div><img src="https://example.test/pixel">')
        for unsafe in ('height=', 'height:', 'line-height:', 'margin-top:', 'position:'):
            self.assertNotIn(unsafe, safe)
        self.assertIn('data-sc-remote-src=', safe)
        self.assertNotIn(' src="https:', reader_document(safe))
        self.assertIn('display:flow-root', reader_document(safe))

    def test_long_conversation_does_not_evict_itself_or_exceed_byte_budget(self):
        cache = DisplayLRU({}, 'test', limit=2, byte_limit=100)
        cache.pinned = {'a', 'b', 'c'}
        for key in cache.pinned:
            self.assertTrue(cache.put(key, 'body'))
        self.assertEqual(len(cache.data['entries']), 3)
        self.assertFalse(cache.put('c', 'x' * 100))
        self.assertIsNotNone(cache.get('a'))
        self.assertLessEqual(cache.data['bytes'], 100)


if __name__ == '__main__':
    unittest.main()
