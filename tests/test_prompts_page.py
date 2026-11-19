"""Isolated Streamlit UI checks; no app startup, credentials or network."""
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest


class PageTests(unittest.TestCase):
    def test_three_categories_and_safe_disconnected_editor(self):
        accounts = types.ModuleType('os_accounts')
        accounts.is_admin = lambda user: True
        accounts.account_is_active = lambda user: True
        source = "from prompts_page import render_page\nrender_page({'id':'test-owner'})"
        with patch.dict(sys.modules, {'os_accounts': accounts}), patch.dict(os.environ, {'PROMPTS_GITHUB_TOKEN': '', 'RENDER_API_KEY': ''}):
            page = AppTest.from_string(source, default_timeout=30).run()
            self.assertFalse(page.exception)
            self.assertEqual([t.label for t in page.tabs][:1], ['Design'])
            self.assertTrue({'Design', 'Upload', 'Ads'}.issubset({t.label for t in page.tabs}))
            self.assertEqual(len(page.text_area), 1)
            self.assertTrue(all(b.disabled for b in page.button if b.label in ('Save draft', 'Activate version')))
            page.text_area[0].set_value('Unsaved editor text').run()
            self.assertFalse(page.exception)
            self.assertEqual(page.text_area[0].value, 'Unsaved editor text')
            self.assertNotIn('Release connection', [e.label for e in page.expander])
            self.assertFalse(any('token' in t.label.lower() or 'api key' in t.label.lower() for t in page.text_input))
            page.session_state['prompt-category'] = 'Upload'
            page.run()
            self.assertFalse(page.exception)
            self.assertEqual(len(page.text_area), 1)
            page.session_state['prompt-category'] = 'Design'
            page.run()
            self.assertEqual(page.text_area[0].value, 'Unsaved editor text')

    def test_header_actions_save_and_activate_selected_version(self):
        accounts = types.ModuleType('os_accounts')
        accounts.is_admin = lambda user: True
        accounts.account_is_active = lambda user: True
        store = Mock(token='synthetic', render_token='synthetic')
        version = {'id': 'draft-test', 'version': '1.1', 'text': 'Saved instructions',
                   'created_at': '2026-11-19T00:00:00', 'author': 'test-owner'}
        history = {'versions': [version]}
        store.history.return_value = (history, 'history-sha')
        with patch.dict(sys.modules, {'os_accounts': accounts}), patch('prompts_page.GitStore', return_value=store):
            page = AppTest.from_string("from prompts_page import render_page\nrender_page({'id':'test-owner'})", default_timeout=30).run()
            page.text_area[0].set_value('Edited instructions').run()
            next(b for b in page.button if b.label == 'Save draft').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(store.save.call_args.args[1], 'Edited instructions')
            self.assertEqual(store.save.call_args.args[3], 'test-owner')
            page.radio[0].set_value('draft-test').run()
            self.assertEqual(page.text_area[0].value, 'Saved instructions')
            next(b for b in page.button if b.label == 'Compare versions').click().run()
            self.assertTrue(any(s.label == 'Compare against' for s in page.selectbox))
            next(b for b in page.button if b.label == 'Activate version').click().run()
            store.activate.assert_not_called()
            next(b for b in page.button if b.label == 'Publish this saved version').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(store.activate.call_args.args[1:], ('draft-test', history, 'history-sha'))

    def test_unauthorised_user_cannot_open_editor(self):
        accounts = types.ModuleType('os_accounts')
        accounts.is_admin = lambda user: False
        with patch.dict(sys.modules, {'os_accounts': accounts}):
            page = AppTest.from_string("from prompts_page import render_page\nrender_page({'id':'worker'})").run()
            self.assertEqual(len(page.error), 1)
            self.assertEqual(len(page.text_area), 0)


if __name__ == '__main__':
    unittest.main()
