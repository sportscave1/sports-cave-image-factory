"""Orders V20: bounded reads, fresh results and unchanged operational boundaries."""
import ast
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

import orders_page as orders
from orders_read_batch import read_batch
from orders_read_executor import OrdersReadExecutor, ReadQueueFull


class PipelineTests(unittest.TestCase):
    def test_deduplicated_order_json_is_restored_independently_per_line(self):
        import supabase_backend as db
        from tests.test_orders_bounded_reader import ProductionCardinalityDatabase
        from tests.read_connection_fakes import disposable_read_connection
        database = ProductionCardinalityDatabase(order_count=560, lines_per_order=2)
        original = ProductionCardinalityDatabase.Cursor.fetchall
        def fetch(cur):
            rows = original(cur)
            if 'LEFT JOIN shopify_order_lines li' in cur.sql:
                for index, row in enumerate(rows):
                    row['order_raw_json'] = {'_orders_refund': {'status': 'Refund Pending', 'blocked': True},
                                             'customer': {'name': 'Synthetic'}} if index % 2 == 0 else None
            return rows
        with patch.object(db, 'connect', side_effect=database.connect), patch.object(db, 'read_connection', side_effect=disposable_read_connection), patch.object(ProductionCardinalityDatabase.Cursor, 'fetchall', fetch):
            rows = db.list_hybrid_order_rows(limit=50)
        self.assertEqual(len(rows), 100)
        self.assertEqual(rows[0]['order_raw_json'], rows[1]['order_raw_json'])
        rows[0]['order_raw_json']['customer']['name'] = 'Changed local copy'
        self.assertEqual(rows[1]['order_raw_json']['customer']['name'], 'Synthetic')
        self.assertTrue(rows[1]['order_raw_json']['_orders_refund']['blocked'])

    def test_all_queries_sync_before_fetch_on_one_exclusive_connection(self):
        events = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, name): events.append(name)
            def fetchall(self):
                self_test.assertEqual(events[:3], ['dispatch', 'allocations', 'sync'])
                events.append('fetch')
                return []
        class Connection:
            def cursor(self): return Cursor()
            @contextmanager
            def pipeline(self):
                yield
                events.append('sync')
        self_test = self
        result = read_batch(SimpleNamespace(connection=Connection()), {
            name: lambda cur, name=name: (cur.execute(name), True)[1]
            for name in ('dispatch', 'allocations')})
        self.assertEqual(result['executed'], {'dispatch', 'allocations'})
        self.assertEqual(events, ['dispatch', 'allocations', 'sync', 'fetch', 'fetch'])

    def test_pipeline_failure_never_merges_partial_results(self):
        connection = Mock()
        connection.pipeline.return_value.__enter__ = Mock()
        connection.pipeline.return_value.__exit__ = Mock(side_effect=RuntimeError('cancelled'))
        connection.cursor.return_value.__enter__ = Mock(return_value=Mock())
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            read_batch(SimpleNamespace(connection=connection), {'a': lambda c: True})
        connection.cursor.return_value.__enter__.return_value.fetchall.assert_not_called()


class ExecutorTests(unittest.TestCase):
    def test_cancellation_and_pressure_are_bounded_and_slots_recover(self):
        release = Event()
        started = [Event(), Event()]
        executor = OrdersReadExecutor()
        def block(index):
            started[index].set()
            release.wait(3)
        try:
            running = [executor.submit(block, index) for index in range(2)]
            self.assertTrue(all(event.wait(1) for event in started))
            skipped = Mock()
            pending = [executor.submit(skipped) for _ in range(6)]
            for future in pending: self.assertTrue(future.cancel())
            # Cancelled queue entries still occupy slots until drained.
            for _ in range(100):
                with self.assertRaises(ReadQueueFull): executor.submit(skipped).result()
            self.assertEqual(len(executor._pending), 8)
            release.set()
            for future in running: future.result(2)
            executor.shutdown()
            skipped.assert_not_called()
            self.assertEqual(len(executor._pending), 0)
            for _ in range(8): self.assertTrue(executor._slots.acquire(False))
            self.assertFalse(executor._slots.acquire(False))
        finally:
            release.set()
            executor.shutdown()

    def test_shutdown_settles_cancelled_outer_futures(self):
        release = Event()
        executor = OrdersReadExecutor()
        futures = [executor.submit(release.wait, 1) for _ in range(8)]
        executor.shutdown(wait=False, cancel_futures=True)
        release.set()
        executor.shutdown()
        self.assertTrue(all(future.done() for future in futures))
        self.assertEqual(len(executor._pending), 0)
        with self.assertRaises(RuntimeError): executor.submit(lambda: None)


class FreshResultsTests(unittest.TestCase):
    def setUp(self):
        self.state = {'current_page': 'Orders', 'sports_cave_current_user': {'id': 'a', 'session_version': 1}}
        self.st = SimpleNamespace(session_state=self.state)

    def payload(self): return {'rows': [], 'source': 'fixture'}

    def test_old_result_cannot_replace_new_search_navigation_or_account(self):
        for change in ('search', 'page', 'account', 'version'):
            with self.subTest(change=change):
                self.setUp()
                class RacingFuture(Future):
                    def result(inner, *args, **kwargs):
                        if change == 'search': self.state[orders.LOAD_FUTURE_KEY] = Future()
                        if change == 'page': self.state['current_page'] = 'Dashboard'
                        if change == 'account': self.state['sports_cave_current_user']['id'] = 'b'
                        if change == 'version': self.state['sports_cave_current_user']['session_version'] = 2
                        return self.payload()
                future = RacingFuture()
                future.set_result(None)
                self.state[orders.LOAD_FUTURE_KEY] = future
                with patch.object(orders, 'st', self.st), patch.object(orders, '_apply_snapshot_payload') as apply:
                    self.assertEqual(orders._consume_snapshot_load(), 'superseded')
                apply.assert_not_called()

    def test_pending_loader_reuses_identical_request_and_cancels_old_query(self):
        executor = Mock()
        executor.submit.side_effect = lambda *a, **k: Future()
        with patch.object(orders, 'st', self.st), patch.object(orders, '_ORDERS_LOAD_EXECUTOR', executor):
            first = orders._start_snapshot_load('alpha')
            self.assertIs(orders._start_snapshot_load('alpha'), first)
            second = orders._start_snapshot_load('beta')
            self.assertTrue(first.cancelled())
            self.assertIs(self.state[orders.LOAD_FUTURE_KEY], second)
            self.assertEqual(executor.submit.call_count, 2)

    def test_refresh_during_search_cannot_overwrite_new_generation(self):
        self.state[orders.LOAD_GENERATION_KEY] = 1
        def read(**kwargs):
            self.state[orders.LOAD_GENERATION_KEY] = 2
            return self.payload()
        with patch.object(orders, 'st', self.st), patch.object(orders, '_read_orders_snapshot', side_effect=read), patch.object(orders, '_apply_snapshot_payload') as apply:
            self.assertFalse(orders._reload_orders_from_source())
        apply.assert_not_called()

    def test_marker_checks_keep_30_second_cadence_and_pause_for_pending_read(self):
        self.state[orders.LIVE_CHECKED_AT_KEY] = time.monotonic()
        with patch.object(orders, 'st', self.st), patch.object(orders, '_certificate_action_in_progress', return_value=False), patch.object(orders, '_orders_supabase_visibility_marker') as marker:
            orders._check_orders_supabase_live_refresh()
            marker.assert_not_called()
            self.state[orders.LIVE_CHECKED_AT_KEY] = 0
            self.state[orders.LOAD_FUTURE_KEY] = Future()
            orders._check_orders_supabase_live_refresh()
            marker.assert_not_called()

    def test_fast_success_slow_request_and_error_keep_established_presentation(self):
        from contextlib import ExitStack
        for outcome in ('ready', 'slow', 'error'):
            with self.subTest(outcome=outcome), ExitStack() as stack:
                self.setUp()
                future = Future()
                if outcome == 'ready': future.set_result(self.payload())
                if outcome == 'error': future.set_exception(RuntimeError('read failed'))
                self.state.update({orders.LOAD_FUTURE_KEY: future,
                                   orders.LOAD_STARTED_KEY: time.monotonic()})
                stack.enter_context(patch.object(orders, 'st', SimpleNamespace(session_state=self.state, title=Mock())))
                for name in ('_ensure_state', '_render_orders_styles', '_perf_log', '_render_orders_supabase_live_refresh'):
                    stack.enter_context(patch.object(orders, name))
                stack.enter_context(patch.object(orders, '_render_orders_search_form', return_value=('', False)))
                stack.enter_context(patch.object(orders, '_async_orders_load_supported', return_value=True))
                stack.enter_context(patch.object(orders, 'ORDERS_INLINE_READ_WAIT_SECONDS', 0))
                def apply(payload): self.state[orders.ROWS_KEY] = payload['rows']
                stack.enter_context(patch.object(orders, '_apply_snapshot_payload', side_effect=apply))
                error = stack.enter_context(patch.object(orders, '_record_snapshot_load_error'))
                loading = stack.enter_context(patch.object(orders, '_render_orders_loading_fragment'))
                data = stack.enter_context(patch.object(orders, '_render_orders_data_area'))
                orders.render_page()
                self.assertEqual(loading.call_count, int(outcome == 'slow'))
                self.assertEqual(data.call_count, int(outcome != 'slow'))
                self.assertEqual(error.call_count, int(outcome == 'error'))


class WorkspaceBoundaryTests(unittest.TestCase):
    def workspace(self, authenticated=True, allowed=True, page='Orders'):
        node = next(node for node in ast.parse(Path('app.py').read_text(encoding='utf-8')).body
                    if isinstance(node, ast.FunctionDef) and node.name == '_render_orders_workspace')
        node.decorator_list = []
        ns = {'st': SimpleNamespace(session_state={'current_page': page}, rerun=Mock()),
              'is_app_authenticated': Mock(return_value=authenticated),
              'ensure_current_page_access': Mock(return_value=allowed),
              'get_orders_page': Mock(return_value=SimpleNamespace(render_page=Mock())),
              '_navigation_page_status': Mock(return_value='ready'),
              '_finish_navigation_transition': Mock(), 'top_bar': Mock(),
              'get_components_module': Mock(), 'NAVIGATION_EPOCH_STATE_KEY': 'epoch',
              'logging': Mock(), '_render_navigation_failure': Mock(),
              'os_accounts': SimpleNamespace(is_admin=lambda user: False), 'current_os_user': lambda: {}}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), ns)
        ns['_render_orders_workspace']()
        return ns

    def test_fragment_always_rechecks_existing_auth_and_permission_policy(self):
        for authenticated, allowed in ((True, True), (False, True), (True, False)):
            ns = self.workspace(authenticated, allowed)
            ns['is_app_authenticated'].assert_called_once_with()
            self.assertEqual(ns['get_orders_page'].call_count, int(authenticated and allowed))
            self.assertEqual(ns['ensure_current_page_access'].call_count, int(authenticated))
            self.assertEqual(ns['st'].rerun.call_count, int(not authenticated))

    def test_late_fragment_event_cannot_render_orders_after_navigation(self):
        ns = self.workspace(page='Dashboard')
        ns['get_orders_page'].assert_not_called()
        ns['_finish_navigation_transition'].assert_not_called()


if __name__ == '__main__': unittest.main()
