"""Phase 3: read-only connection and asynchronous Orders result safeguards."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import os_accounts
from scripts.benchmark_account_reads import Connection, Cursor


def orders_functions(st, marker, busy=lambda: False):
    names = {'_check_orders_supabase_live_refresh', '_render_orders_supabase_live_refresh'}
    nodes = [n for n in ast.parse(Path('orders_page.py').read_text(encoding='utf-8')).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(st=st, _orders_supabase_visibility_marker=marker,
              _certificate_action_in_progress=busy, _reload_orders_from_source=Mock(),
              ORDERS_SUPABASE_LIVE_MARKER_KEY='marker', ORDERS_SUPABASE_LIVE_CHECK_SECONDS=30)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'orders_page.py', 'exec'), ns)
    return ns


class Phase3ReadTests(unittest.TestCase):
    def test_account_refresh_autocommit_only_single_statement(self):
        store = os_accounts.PostgresAccountStore()
        cur = Cursor()
        with patch.object(store, 'ensure_schema'), patch.object(store, '_connect', return_value=Connection(cur)) as connect, patch('scripts.benchmark_account_reads.time.sleep'):
            store.get_user('fixture')
        connect.assert_called_once_with(autocommit=True)
        self.assertEqual(cur.calls, 1)
        self.assertIn('p.user_id=u.id', cur.sql)

    def test_connection_defaults_keep_transactions_and_timeouts(self):
        store = os_accounts.PostgresAccountStore()
        with patch.object(store, '_database_url', return_value='fixture'), patch('psycopg.connect') as connect:
            store._connect()
            self.assertFalse(connect.call_args.kwargs['autocommit'])
            self.assertEqual(connect.call_args.kwargs['connect_timeout'], 4)
            self.assertIn('statement_timeout=4000', connect.call_args.kwargs['options'])
            store._connect(autocommit=True)
            self.assertTrue(connect.call_args.kwargs['autocommit'])

    def test_failed_read_propagates_and_closes_connection(self):
        store = os_accounts.PostgresAccountStore()
        conn = Mock()
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        conn.cursor.side_effect = RuntimeError('fixture timeout')
        with patch.object(store, 'ensure_schema'), patch.object(store, '_connect', return_value=conn):
            with self.assertRaisesRegex(RuntimeError, 'fixture timeout'): store.get_user('fixture')
        conn.__exit__.assert_called_once()

    def test_parallel_registration_preserves_cadence(self):
        st = SimpleNamespace(session_state={}, rerun=Mock(), fragment=Mock(side_effect=lambda **kw: lambda f: f))
        ns = orders_functions(st, lambda: '')
        ns['_render_orders_supabase_live_refresh']()
        st.fragment.assert_called_once_with(run_every='30s', parallel=True)

    def test_changes_only_invalidate_when_still_current(self):
        for outcome in ('same', 'first', 'changed', 'empty', 'failed', 'navigate', 'account', 'certificate'):
            with self.subTest(outcome=outcome):
                state = {'current_page': 'Orders', 'sports_cave_current_user': {'id':'a'}, 'marker':'old'}
                if outcome == 'first': state.pop('marker')
                busy = [False]
                def marker():
                    if outcome == 'navigate': state['current_page'] = 'Home'
                    if outcome == 'account': state['sports_cave_current_user'] = {'id':'b'}
                    if outcome == 'certificate': busy[0] = True
                    if outcome == 'failed': raise RuntimeError('fixture unavailable')
                    return '' if outcome == 'empty' else 'old' if outcome == 'same' else 'new'
                st = SimpleNamespace(session_state=state, rerun=Mock())
                ns = orders_functions(st, marker, lambda: busy[0])
                ns['_check_orders_supabase_live_refresh']()
                self.assertEqual(ns['_reload_orders_from_source'].call_count, int(outcome == 'changed'))
                self.assertEqual(st.rerun.call_count, int(outcome == 'changed'))
                if outcome in ('navigate','account','certificate','failed','empty'):
                    self.assertEqual(state['marker'], 'old')

if __name__ == '__main__': unittest.main()
