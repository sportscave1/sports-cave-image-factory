"""Reachable manual persistence control; synthetic provider and identity only."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page

ADMIN = {'id': 'fixture', 'role': 'admin', 'is_active': True}
CONFIG = {'configured': True, 'ad_account_id': 'act_123', 'access_token': 'synthetic', 'api_version': 'v26.0'}
RESULT = {'warnings': [], 'reporting': {'since': '2026-11-05', 'until': '2026-11-05',
    'timezone': 'Australia/Sydney', 'currency': 'AUD', 'captured_at': '2026-11-06T00:00:00Z',
    'attribution_windows': 'Per-adset settings; exact windows not returned by this query.'}}


class SavedPerformanceTests(unittest.TestCase):
    def test_permission_is_checked_before_io_and_on_each_call(self):
        with patch.object(page.sync_service, 'sync_reporting', return_value=RESULT) as sync:
            for user in ({}, {'role': 'admin', 'is_active': False}, {'role': 'worker'}):
                with self.assertRaises(PermissionError):
                    page.refresh_saved_performance(lambda: user, 1)
            sync.assert_not_called()
            page.refresh_saved_performance(lambda: ADMIN, 1)
            sync.assert_called_once_with(days=1)
            with self.assertRaises(PermissionError):
                page.refresh_saved_performance(lambda: {}, 1)
            self.assertEqual(sync.call_count, 1)

    def test_invalid_ranges_fail_before_io(self):
        with patch.object(page.sync_service, 'sync_reporting') as sync:
            for days in (0, 32, True, 1.5):
                with self.assertRaises(ValueError):
                    page.refresh_saved_performance(lambda: ADMIN, days)
            sync.assert_not_called()

    def app(self, configured=True):
        return AppTest.from_string(
            'from tests.test_meta_saved_performance import CONFIG, ADMIN\n'
            'import ads_meta_review_page as p\n'
            f'p.render_saved_performance(dict(CONFIG, configured={configured}), lambda: ADMIN)',
            default_timeout=15).run()

    def test_explicit_click_only_and_reopen_does_not_sync(self):
        with patch.object(page.sync_service, 'sync_reporting', return_value=RESULT) as sync:
            at = self.app()
            sync.assert_not_called()
            at.button[0].click().run()
            sync.assert_called_once_with(days=1)
            self.assertFalse(at.exception)
            self.assertIn('Australia/Sydney', at.success[0].value)
            at.run()
            self.assertEqual(sync.call_count, 1)

    def test_missing_connection_disabled(self):
        with patch.object(page.sync_service, 'sync_reporting') as sync:
            at = self.app(False)
            self.assertTrue(at.button[0].disabled)
            sync.assert_not_called()

    def test_failure_visible_and_manual_recovery(self):
        with patch.object(page.sync_service, 'sync_reporting', side_effect=[RuntimeError('private details'), RESULT]) as sync:
            at = self.app()
            at.button[0].click().run()
            self.assertFalse(at.exception)
            self.assertFalse(at.success)
            self.assertNotIn('private details', at.error[0].value)
            at.button[0].click().run()
            self.assertTrue(at.success)
            self.assertEqual(sync.call_count, 2)

    def test_existing_app_route_supplies_fresh_permission_callback(self):
        import ast
        from pathlib import Path
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8'))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'render_page'
                 and isinstance(node.func.value, ast.Call)
                 and isinstance(node.func.value.func, ast.Name)
                 and node.func.value.func.id == 'get_ads_meta_review_page']
        self.assertEqual(len(calls), 1)
        callback = next(k.value for k in calls[0].keywords if k.arg == 'authorize')
        self.assertIn('_refresh_session_account_if_due', ast.unparse(callback))
