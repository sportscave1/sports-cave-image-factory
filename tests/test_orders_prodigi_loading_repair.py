import inspect
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import os_pages
import orders_page
import supabase_backend


class PendingFuture:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True
        return True


class CapturingExecutor:
    def __init__(self):
        self.calls = []
        self.future = PendingFuture()

    def submit(self, function, *args, **kwargs):
        self.calls.append((function, args, kwargs))
        return self.future


class OrdersProdigiLoadingRepairTests(unittest.TestCase):
    def test_orders_default_async_load_requests_latest_50_without_shopify(self):
        executor = CapturingExecutor()
        fake_st = SimpleNamespace(session_state={})

        with patch.object(orders_page, "st", fake_st), patch.object(
            orders_page, "_ORDERS_LOAD_EXECUTOR", executor
        ), patch.object(
            orders_page.shopify_sync,
            "iter_order_pages",
            side_effect=AssertionError("Normal Orders load must not call Shopify."),
        ):
            orders_page._start_snapshot_load("")

        self.assertEqual(len(executor.calls), 1)
        function, args, kwargs = executor.calls[0]
        self.assertIs(function, orders_page._read_orders_snapshot)
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {"search": "", "limit": 50})

    def test_orders_search_is_submitted_and_periodic_database_poll_is_not_rendered(self):
        search_source = inspect.getsource(orders_page._render_orders_search_form)
        render_source = inspect.getsource(orders_page.render_page)

        self.assertIn('st.form("orders-search-form"', search_source)
        self.assertIn("if search_submitted", render_source)
        self.assertIn("_start_snapshot_load(search_text, force=True)", render_source)
        self.assertNotIn("_render_orders_supabase_live_refresh", render_source)
        self.assertIn("_render_orders_loading_fragment", render_source)

    def test_orders_failure_keeps_safe_display_cache_and_retry_copy(self):
        fake_st = SimpleNamespace(
            session_state={
                orders_page.ROWS_KEY: [{"order": "#SC2906"}],
                orders_page.META_KEY: {"source": "shopify_mirror_supabase_edition_ledger"},
                orders_page.LOAD_ERROR_KEY: "",
            }
        )

        with patch.object(orders_page, "st", fake_st):
            orders_page._record_snapshot_load_error(RuntimeError("pool unavailable"), "")

        self.assertEqual(fake_st.session_state[orders_page.ROWS_KEY], [{"order": "#SC2906"}])
        self.assertEqual(
            fake_st.session_state[orders_page.META_KEY]["source"],
            "shopify_mirror_supabase_edition_ledger",
        )
        self.assertIn(
            "Orders could not be loaded. Please retry.",
            inspect.getsource(orders_page._render_orders_load_failure),
        )
        self.assertIn('st.button("Retry"', inspect.getsource(orders_page._render_orders_load_failure))

    def test_prodigi_default_async_load_is_bounded(self):
        executor = CapturingExecutor()
        fake_st = SimpleNamespace(session_state={})

        with patch.object(os_pages, "st", fake_st), patch.object(
            os_pages, "_PRODIGI_LOAD_EXECUTOR", executor
        ):
            os_pages._start_prodigi_dispatch_load("Last 7 Days", "", 50)

        self.assertEqual(len(executor.calls), 1)
        function, args, kwargs = executor.calls[0]
        self.assertIs(function, os_pages.prodigi_load_dispatch_rows)
        self.assertEqual(args, ("Last 7 Days", "", 50))
        self.assertEqual(kwargs, {"raise_on_error": True})

    def test_prodigi_dispatch_query_is_one_bounded_read(self):
        statements = []

        class Cursor:
            def execute(self, sql, params=None):
                statements.append((str(sql), tuple(params or ())))

            def fetchall(self):
                return []

        def run_read(operation, callable_):
            self.assertEqual(operation, "prodigi.dispatch.latest_50")
            return callable_(Cursor()), {"duration_ms": 1}

        with patch.object(supabase_backend, "_run_read_operation", side_effect=run_read):
            rows = supabase_backend.list_prodigi_dispatch_rows(days=7, limit=50)

        self.assertEqual(rows, [])
        self.assertEqual(len(statements), 1)
        self.assertEqual(statements[0][1][-1], 50)
        self.assertIn("FROM prodigi_dispatch_rows", statements[0][0])

    def test_prodigi_failure_is_visible_and_does_not_write_error_to_failed_backend(self):
        loader_source = inspect.getsource(os_pages.prodigi_load_dispatch_rows)
        page_source = inspect.getsource(os_pages.render_prodigi_page)

        self.assertNotIn("log_app_error", loader_source)
        self.assertIn("raise_on_error", loader_source)
        self.assertIn("Prodigi orders could not be loaded. Please retry.", page_source)
        self.assertIn('st.button("Retry"', page_source)
        self.assertIn('st.form("prodigi-dispatch-log-search-form"', page_source)

    def test_database_read_deadline_cancels_pool_checkout(self):
        cancelled = threading.Event()

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                cancelled.wait(1)
                raise TimeoutError("unable to check out connection from the pool")

        class Connection:
            closed = False

            def cursor(self):
                return Cursor()

            def cancel_safe(self, timeout=1.0):
                cancelled.set()

            def rollback(self):
                return None

            def close(self):
                self.closed = True

        started = time.perf_counter()
        with patch.object(supabase_backend, "connect", return_value=Connection()), patch.object(
            supabase_backend, "_db_read_deadline_seconds", return_value=0.01
        ):
            with self.assertRaises(supabase_backend.DatabaseReadError) as raised:
                supabase_backend._run_read_operation("orders.latest_50.base", lambda cur: cur.read())

        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(raised.exception.diagnostic["category"], "request_timeout")


if __name__ == "__main__":
    unittest.main()
