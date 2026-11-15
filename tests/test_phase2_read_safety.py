"""No production services: execute actual auth, display-read and lazy-tab paths."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
import uuid

import analytics_page
import os_accounts
from crm_cache import DisplayCache
from crm_automation_store import AutomationStore
from crm_campaign_store import CampaignStore
from crm_automation_definition import FORMAT, new_flow
from scripts.benchmark_phase2 import auth_functions
from tests.test_analytics_fragment_reads import Tab


class AuthenticationReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.source = Path('app.py').read_text(encoding='utf-8')

    def setup_refresh(self):
        user = dict(id='fixture', role='worker', is_active=True, account_status='active',
                    session_version=1, page_permissions=['email'])
        store = Mock()
        store.get_user.return_value = deepcopy(user)
        ns, cleared = auth_functions(self.source, user, store)
        return user, store, ns, cleared

    def test_current_account_only_and_same_30_second_interval(self):
        user, store, ns, cleared = self.setup_refresh()
        with patch.object(os_accounts, 'DEFAULT_STORE', store), patch('time.monotonic', return_value=100):
            ns['st'].session_state['sports_cave_auth_checked_at'] = 71
            ns['_refresh_session_account_if_due'](user, max_age_seconds=30)
            store.get_user.assert_not_called()
            ns['st'].session_state['sports_cave_auth_checked_at'] = 70
            ns['_refresh_session_account_if_due'](user, max_age_seconds=30)
            store.get_user.assert_called_once_with('fixture')
            store.first_admin.assert_not_called()
            cleared.assert_not_called()

    def test_failure_revocation_and_account_switch_fail_closed(self):
        for replacement in [None, {}, {'is_active': False}, {'account_status': 'removed'},
                            {'session_version': 2}, {'id': 'another-account'}]:
            with self.subTest(replacement=replacement):
                user, store, ns, cleared = self.setup_refresh()
                if replacement is None: store.get_user.side_effect = RuntimeError('offline')
                elif replacement == {}: store.get_user.return_value = {}
                else: store.get_user.return_value.update(replacement)
                with patch.object(os_accounts, 'DEFAULT_STORE', store):
                    self.assertEqual(ns['_refresh_session_account_if_due'](user), {})
                cleared.assert_called_once()
                ns['clear_auth_cookie'].assert_called_once()

    def test_permission_change_replaces_session_with_authoritative_record(self):
        user, store, ns, cleared = self.setup_refresh()
        store.get_user.return_value['page_permissions'] = ['orders']
        with patch.object(os_accounts, 'DEFAULT_STORE', store): result = ns['_refresh_session_account_if_due'](user)
        self.assertEqual(result['page_permissions'], ['orders'])
        self.assertEqual(ns['st'].session_state['sports_cave_current_user'], result)
        cleared.assert_not_called()


class FlowReadScopeTests(unittest.TestCase):
    def setUp(self):
        self.store = AutomationStore()
        self.identity = str(uuid.uuid4())
        self.row = dict(id=self.identity, status='ACTIVE', name='Fixture', config={
            'format': FORMAT, 'draft': new_flow(), 'revision': 1, 'published_version': 1})

    def test_one_render_reuses_definition_but_returns_independent_copies(self):
        with patch.object(self.store, 'get', side_effect=lambda *_: deepcopy(self.row)) as read:
            with self.store.display_read_scope():
                first = self.store.flow(self.identity)
                first['config']['draft']['name'] = 'Unsaved edit'
                for _ in range(3): self.assertNotEqual(self.store.flow(self.identity), first)
                self.assertEqual(read.call_count, 1)
            self.store.flow(self.identity)  # next fragment/request must read again
            self.assertEqual(read.call_count, 2)

    def test_database_operation_invalidates_before_mutation(self):
        @contextmanager
        def db(_): yield Mock()
        with patch.object(self.store, 'get', side_effect=lambda *_: deepcopy(self.row)) as read, patch.object(CampaignStore, 'db', db):
            with self.store.display_read_scope():
                self.store.flow(self.identity)
                with self.store.db(): self.row['config']['revision'] = 2
                self.assertEqual(self.store.flow(self.identity)['config']['revision'], 2)
                self.assertEqual(read.call_count, 2)

    def test_exception_cleanup_and_background_thread_isolation(self):
        with patch.object(self.store, 'get', side_effect=lambda *_: deepcopy(self.row)) as read:
            with self.assertRaises(ValueError):
                with self.store.display_read_scope():
                    self.store.flow(self.identity)
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(self.store.flow, self.identity).result()
                    self.assertEqual(read.call_count, 2)
                    raise ValueError('render failed')
            self.store.flow(self.identity)
            self.assertEqual(read.call_count, 3)

    def test_other_store_cannot_reuse_definition_and_seed_stays_immutable(self):
        other = AutomationStore()
        with patch.object(other, 'get', return_value=self.row) as read, patch.object(self.store, 'get') as initial:
            with self.store.display_read_scope():
                self.store.flow(self.identity, row=self.row)
                self.store.flow(self.identity)
                other.flow(self.identity)
            initial.assert_not_called()
            read.assert_called_once()
            self.assertEqual(self.row['config']['revision'], 1)
            self.assertEqual(self.row['config']['published_version'], 1)


class VisitedAnalyticsTests(unittest.TestCase):
    def test_unvisited_and_expired_tabs_do_not_fetch_and_filters_isolate(self):
        clock = Mock(return_value=0)
        cache = DisplayCache(clock=clock)
        backend = Mock()
        backend.report_for_period.return_value = {'rows': [{'metrics': {'sessions': 12}}]}
        store = analytics_page._ReportDisplayStore(backend, cache)
        period = {'start_date': '2026-10-01', 'end_date': '2026-10-07'}
        ui = Mock()
        render = analytics_page._overview_breakdowns.__wrapped__
        with patch.object(analytics_page, 'st', ui), patch.object(analytics_page, '_table') as table:
            for selected, rendered in [(0, 1), (1, 2), (0, 2)]:
                ui.tabs.return_value = [Tab(i == selected) for i in range(4)]
                table.reset_mock()
                render(store, 'property', period)
                self.assertEqual(table.call_count, rendered)
            self.assertEqual(backend.report_for_period.call_count, 2)
            clock.return_value = 31
            table.reset_mock()
            render(store, 'property', period)
            self.assertEqual(table.call_count, 1)
            self.assertEqual(backend.report_for_period.call_count, 3)
            self.assertIsNone(store.peek_report('different-property', 'pages_screens', **{'start':period['start_date'], 'end':period['end_date']}))
            self.assertIsNone(store.peek_report('property', 'pages_screens', '2026-10-02', period['end_date']))


if __name__ == '__main__': unittest.main()
