"""Isolated Streamlit UI checks; no app startup, credentials or network."""
import os
import sys
import types
import unittest
from unittest.mock import patch
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
            self.assertEqual(len(page.text_area), 3)
            self.assertTrue(all(b.disabled for b in page.button if b.label in ('Save draft', 'Activate version')))
            page.text_area[0].set_value('Unsaved editor text').run()
            self.assertFalse(page.exception)
            self.assertEqual(page.text_area[0].value, 'Unsaved editor text')

    def test_unauthorised_user_cannot_open_editor(self):
        accounts = types.ModuleType('os_accounts')
        accounts.is_admin = lambda user: False
        with patch.dict(sys.modules, {'os_accounts': accounts}):
            page = AppTest.from_string("from prompts_page import render_page\nrender_page({'id':'worker'})").run()
            self.assertEqual(len(page.error), 1)
            self.assertEqual(len(page.text_area), 0)


if __name__ == '__main__':
    unittest.main()
