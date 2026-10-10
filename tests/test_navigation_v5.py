"""Real Email return and Reporting read-scope contracts; no external I/O."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch

import reporting_store as reports
import support_email_page as email
from tests import test_support_email_v2 as existing


class ReadinessTests(unittest.TestCase):
    def test_async_email_updates_server_readiness_only_for_current_loaded_epoch(self):
        from types import SimpleNamespace
        session = {'current_page': 'Email', 'navigation_transition': {
            'to': 'Email', 'epoch': 4, 'status': 'loading', 'started_at': 90},
            'navigation_last_ready_page': 'Orders'}
        state = {'loaded': True, 'body_pending': 'message'}
        with patch.object(email, 'st', SimpleNamespace(session_state=session)), patch.object(email.time, 'monotonic', return_value=100):
            email._complete_loaded_navigation(state, 4)
            self.assertEqual(session['navigation_transition']['status'], 'loading')
            state.pop('body_pending')
            email._complete_loaded_navigation(state, 3)
            self.assertEqual(session['navigation_last_ready_page'], 'Orders')
            session['current_page'] = 'Orders'
            email._complete_loaded_navigation(state, 4)
            self.assertEqual(session['navigation_last_ready_page'], 'Orders')
            session['current_page'] = 'Email'
            email._complete_loaded_navigation(state, 4)
            self.assertEqual(session['navigation_transition']['status'], 'ready')
            self.assertEqual(session['navigation_transition']['duration_ms'], 10000)
            self.assertEqual(session['navigation_last_ready_page'], 'Email')

    def test_shell_waits_for_essential_orders_and_email_data(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_navigation_page_status')
        st = Mock(session_state={})
        ns = {'st': st}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), ns)
        status = ns['_navigation_page_status']
        self.assertEqual(status('Orders'), 'loading')
        st.session_state.update(orders_allocation_snapshot_loaded=True, orders_load_future=object())
        self.assertEqual(status('Orders'), 'loading')
        st.session_state['orders_load_future'] = None
        self.assertEqual(status('Orders'), 'ready')
        st.session_state['orders_load_error'] = 'unavailable'
        self.assertEqual(status('Orders'), 'error')
        self.assertEqual(status('Email'), 'loading')
        state = st.session_state['support_email_workspace'] = {'loaded': True, 'body_pending': 'message'}
        self.assertEqual(status('Email'), 'loading')
        state.pop('body_pending')
        self.assertEqual(status('Email'), 'ready')
        state['initial_load_pending'] = True
        self.assertEqual(status('Email'), 'loading')
        state['error'] = 'unavailable'
        self.assertEqual(status('Email'), 'error')
        self.assertEqual(status('Edition Ops'), 'ready')


class SidebarCallbackTests(unittest.TestCase):
    def functions(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('_sidebar_route_clicked', '_sidebar_route_button')]
        st = Mock()
        st.sidebar.container.return_value.button.return_value = True
        accounts = Mock()
        accounts.can_access_page.return_value = True
        ns = dict(st=st, os_accounts=accounts, current_os_user=lambda: {'id': 'fixture'},
            set_current_page=Mock(), SIDEBAR_NAV_LABELS={}, SIDEBAR_ICON_BY_ROUTE={})
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), ns)
        return ns

    def test_full_sidebar_button_registers_callback_without_second_rerun(self):
        ns = self.functions()
        ns['_sidebar_route_button']('Orders', 'Dashboard', ['Orders'])
        call = ns['st'].sidebar.container.return_value.button.call_args.kwargs
        self.assertIs(call['on_click'], ns['_sidebar_route_clicked'])
        self.assertEqual(call['args'], ('Orders',))
        ns['st'].rerun.assert_not_called()
        ns['set_current_page'].assert_not_called()
        call['on_click'](*call['args'])
        ns['set_current_page'].assert_called_once_with('Orders', source='sidebar')

    def test_fragment_route_still_requests_full_app_rerun(self):
        ns = self.functions()
        root = Mock()
        root.container.return_value.button.return_value = True
        ns['_sidebar_route_button']('Mockups', 'Dashboard', ['Mockups'], root=root)
        ns['set_current_page'].assert_called_once_with('Mockups', source='sidebar')
        ns['st'].rerun.assert_called_once()
        self.assertIsNone(root.container.return_value.button.call_args.kwargs['on_click'])

    def test_revoked_permission_cannot_change_route_from_old_widget(self):
        ns = self.functions()
        ns['os_accounts'].can_access_page.return_value = False
        ns['_sidebar_route_clicked']('Orders')
        ns['set_current_page'].assert_not_called()


class EmailReturnTests(unittest.TestCase):
    setUp = existing.WorkspaceTests.setUp

    def render_return(self):
        state = {'support_email_scope': (self.w.config.scope, str(self.w.user['id'])),
                 'support_email_workspace': self.state, 'navigation_epoch': 10}
        component = Mock(return_value=None)
        with patch.object(email.st, 'session_state', state), \
             patch.object(email.st, 'query_params', {}), \
             patch.object(email, 'load_configuration', return_value=self.w.config), \
             patch.object(email, 'load_smtp_configuration'), \
             patch.object(email, 'Workspace', return_value=self.w), \
             patch.object(email, 'get_component', return_value=component):
            email._render_workspace.__wrapped__(self.w.user)
        return component.call_args.kwargs['model']

    def test_warm_return_reuses_headers_and_preserves_composer(self):
        from support_email_compose import new_draft
        draft = new_draft(self.w.config.address)
        draft['html'] = '<p>Unsaved text</p>'
        self.state.update(view='compose', draft=draft, context={'label': 'Existing context'})
        threads = self.state['threads']
        self.imap.calls.clear()
        self.render_return()
        self.assertEqual(self.imap.calls, [])
        self.assertIs(self.state['threads'], threads)
        self.assertIs(self.state['draft'], draft)
        self.assertEqual(self.state['context']['label'], 'Existing context')

    def test_expired_headers_are_read_on_return(self):
        for entry in self.state['cache'].values():
            entry['expires'] = 0
        self.imap.calls.clear()
        self.render_return()
        self.assertEqual(sum(call[0] == 'headers' for call in self.imap.calls), 1)

    def test_explicit_refresh_still_forces_provider_reads(self):
        self.imap.calls.clear()
        import uuid
        self.w.handle({'id': str(uuid.uuid4()), 'action': 'refresh'})
        self.assertIn('headers', [call[0] for call in self.imap.calls])
        self.assertIn('folders', [call[0] for call in self.imap.calls])

    def test_return_respects_failed_connection_backoff(self):
        import time
        self.state.update(recovery_state='waiting', load_retry_at=time.monotonic() + 60)
        self.imap.calls.clear()
        self.render_return()
        self.assertEqual(self.imap.calls, [])
        self.assertEqual(self.state['recovery_state'], 'waiting')


class ReportingReadScopeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.backend = Mock()
        self.stack.enter_context(patch.object(reports, '_backend', return_value=self.backend))
        self.probe = self.stack.enter_context(patch.object(reports, 'schema_status',
            return_value={'configured': True, 'ready': True}))

    def test_scope_reuses_success_for_reads_only_and_resets_after(self):
        status = self.probe()
        with reports.page_read_schema(status):
            for _ in range(4):
                reports.require_schema(read_only=True)
            self.assertEqual(self.probe.call_count, 1)
            reports.require_schema()  # Mutations still check independently.
            self.assertEqual(self.probe.call_count, 2)
        reports.require_schema(read_only=True)
        self.assertEqual(self.probe.call_count, 3)

    def test_backend_change_cannot_reuse_probe(self):
        with reports.page_read_schema({'ready': True}):
            with patch.object(reports, '_backend', return_value=Mock()):
                reports.require_schema(read_only=True)
        self.probe.assert_called_once()

    def test_scope_does_not_leak_to_another_thread(self):
        with reports.page_read_schema({'ready': True}):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(reports.require_schema, read_only=True).result()
        self.probe.assert_called_once()

    def test_failed_probe_never_authorises_a_read(self):
        with reports.page_read_schema({'ready': False}):
            with self.assertRaises(reports.ReportingStoreError):
                reports.require_schema(read_only=True)
        reports.require_schema(read_only=True)
        self.probe.assert_called_once()

    def test_scope_restored_after_exception(self):
        with self.assertRaises(ValueError):
            with reports.page_read_schema({'ready': True}):
                raise ValueError('fixture')
        reports.require_schema(read_only=True)
        self.probe.assert_called_once()


if __name__ == '__main__':
    unittest.main()
