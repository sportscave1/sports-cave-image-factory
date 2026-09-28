"""Inbox default selection only; deterministic providers, no external I/O."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from tests import test_support_email_v2 as existing


class InboxSelectionTests(unittest.TestCase):
    setUp = existing.WorkspaceTests.setUp
    event = existing.WorkspaceTests.event

    def test_first_conversation_and_body_are_ready_without_mailbox_writes(self):
        model = self.w.model()
        self.assertEqual(model['selected'], model['threads'][0]['key'])
        self.assertTrue(any(m['expanded'] and m.get('html') for m in model['messages']))
        self.assertEqual(len([c for c in self.imap.calls if c[0]=='body']), 1)
        self.assertFalse(any(c[0] in ('flag','move','append','delete') for c in self.imap.calls))

    def test_valid_selection_survives_refresh_and_rerun(self):
        selected = self.state['threads'][2]['thread_key']
        self.event('open_thread', thread_key=selected)
        self.imap.calls.clear()
        self.event('refresh'); self.w.load(); self.w.model()
        self.assertEqual(self.state['selected'], selected)
        self.assertFalse(any(c[0]=='body' for c in self.imap.calls))

    def test_missing_and_invalid_selection_fall_back(self):
        for selected in (None, 'no-longer-present'):
            self.state.update(selected=selected, conversation=[])
            self.w.load(force=True)
            self.assertEqual(self.state['selected'], self.state['threads'][0]['thread_key'])
            self.assertTrue(self.w.model()['messages'][0]['expanded'])

    def test_removed_selected_conversation_falls_back_on_refresh(self):
        removed = self.state['conversation'][0]['uid']
        self.imap.messages = [m for m in self.imap.messages if m['uid']!=removed]
        self.event('refresh')
        self.assertEqual(self.state['selected'], self.state['threads'][0]['thread_key'])
        self.assertNotEqual(self.state['conversation'][0]['uid'], removed)
        self.assertTrue(self.w.model()['messages'][0]['expanded'])

    def test_empty_inbox_keeps_empty_state(self):
        self.imap.messages=[]; self.event('refresh')
        model=self.w.model()
        self.assertIsNone(model['selected'])
        self.assertEqual(model['threads'], [])
        self.assertEqual(model['messages'], [])

    def test_other_folders_unchanged_and_return_to_inbox_selects(self):
        for folder in ('Drafts','INBOX.Sent Items','Archive','Junk','Trash','Customers'):
            message=deepcopy(self.imap.messages[0]); message['folder']=folder
            self.imap.messages.append(message)
            self.event('folder',folder=folder)
            self.assertTrue(self.w.model()['threads'])
            self.assertIsNone(self.state['selected'])
            self.assertEqual(self.w.model()['messages'], [])
        self.event('folder',folder='INBOX')
        self.assertEqual(self.state['selected'],self.state['threads'][0]['thread_key'])
        self.assertTrue(self.w.model()['messages'][0]['expanded'])

    def test_search_and_compose_are_not_auto_selected(self):
        self.event('search',query='customer0@example.test')
        self.assertTrue(self.w.model()['threads'])
        self.assertIsNone(self.state['selected'])
        self.state.update(query='',view='compose',selected=None)
        self.w.load(force=True)
        self.assertEqual(self.state['view'],'compose')
        self.assertIsNone(self.state['selected'])

    def test_body_failure_retains_list_and_safe_notice(self):
        self.state.update(selected=None,conversation=[]); self.w.bodies.clear()
        with patch.object(self.imap,'read_message',side_effect=RuntimeError('private-error')):
            self.w.load(force=True)
        model=self.w.model()
        self.assertTrue(model['threads'])
        self.assertEqual(model['selected'],model['threads'][0]['key'])
        self.assertIn('Could not open',model['notice'])
        self.assertNotIn('private-error',str(model))
