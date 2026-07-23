import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import edition_ops
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(rows=None):
    rows = list(rows or [])
    return {
        "version": edition_ops.SNAPSHOT_VERSION,
        "rows": rows,
        "original_rows": [dict(row) for row in rows],
        "last_refreshed_from_shopify": "2026-07-13T22:40:00Z",
        "saved_at": "2026-07-13T22:40:00Z",
        "source": "supabase",
        "cached": False,
        "database_read": {
            "operation": "edition_ops.products.latest",
            "category": "ok",
            "query_count": 1,
            "duration_ms": 20,
        },
    }


def _product(index=1):
    return edition_ops._normalise_row(
        {
            "edition_product_id": str(index),
            "shopify_product_gid": f"gid://shopify/Product/{index}",
            "product_title": f"Product {index}",
            "handle": f"product-{index}",
            "edition_enabled": True,
            "edition_total": 100,
            "edition_next_number": index,
            "edition_sold_count": index - 1,
            "edition_remaining": 101 - index,
            "edition_status": "Limited Edition",
            "sync_status": "Loaded from Supabase",
        }
    )


class _Cursor:
    def __init__(self, rows=None, error=None):
        self.rows = list(rows or [])
        self.error = error
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        if self.error:
            raise self.error

    def fetchall(self):
        return list(self.rows)


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.rollback_calls = 0
        self.close_calls = 0

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1
        self.closed = True


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Column:
    def button(self, *args, **kwargs):
        return False

    def download_button(self, *args, **kwargs):
        return None

    def popover(self, *args, **kwargs):
        return _Context()


class _Slot:
    def caption(self, *args, **kwargs):
        return None

    def container(self):
        return _Context()


class _FakeStreamlit:
    def __init__(self, session_state=None):
        self.session_state = dict(session_state or {})
        self.errors = []
        self.warnings = []
        self.editor_payloads = []
        self.column_config = SimpleNamespace(
            TextColumn=lambda *args, **kwargs: None,
            NumberColumn=lambda *args, **kwargs: None,
            CheckboxColumn=lambda *args, **kwargs: None,
            LinkColumn=lambda *args, **kwargs: None,
        )

    def markdown(self, *args, **kwargs):
        return None

    def title(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def success(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, message, *args, **kwargs):
        self.warnings.append(str(message))

    def error(self, message, *args, **kwargs):
        self.errors.append(str(message))

    def empty(self):
        return _Slot()

    def expander(self, *args, **kwargs):
        return _Context()

    def form(self, *args, **kwargs):
        return _Context()

    def spinner(self, *args, **kwargs):
        return _Context()

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Column() for _ in range(count)]

    def button(self, *args, **kwargs):
        return False

    def form_submit_button(self, *args, **kwargs):
        return False

    def selectbox(self, label, options, *args, **kwargs):
        return options[0]

    def data_editor(self, rows, *args, **kwargs):
        payload = [dict(row) for row in rows]
        self.editor_payloads.append(payload)
        return payload

    def file_uploader(self, *args, **kwargs):
        return None


class EditionOpsStabilityTests(unittest.TestCase):
    def test_normal_and_empty_supabase_snapshots_load_without_error(self):
        fake_st = SimpleNamespace(session_state={})
        normal = _snapshot([_product(1)])
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_load_supabase_snapshot", return_value=normal
        ):
            loaded = edition_ops._load_snapshot()
        self.assertEqual(len(loaded["rows"]), 1)
        self.assertEqual(loaded["source"], "supabase")
        self.assertNotIn("load_error", loaded)

        with patch.object(edition_ops, "st", SimpleNamespace(session_state={})), patch.object(
            edition_ops, "_load_supabase_snapshot", return_value=_snapshot([])
        ):
            empty = edition_ops._load_snapshot()
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["source"], "supabase")

    def test_slow_supabase_response_completes_without_triggering_retry_or_crash(self):
        def slow_snapshot():
            time.sleep(0.02)
            return _snapshot([_product(2)])

        started = time.perf_counter()
        with patch.object(edition_ops, "st", SimpleNamespace(session_state={})), patch.object(
            edition_ops, "_load_supabase_snapshot", side_effect=slow_snapshot
        ) as loader:
            loaded = edition_ops._load_snapshot()
        self.assertGreaterEqual(time.perf_counter() - started, 0.02)
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(loaded["rows"][0]["handle"], "product-2")

    def test_closed_connection_is_discarded_and_retried_once_for_edition_ops(self):
        operational_error = type("OperationalError", (Exception,), {})
        stale = _Connection(_Cursor(error=operational_error("connection to database closed")))
        fresh = _Connection(
            _Cursor(
                rows=[
                    {
                        "id": 7,
                        "shopify_product_id": "gid://shopify/Product/7",
                        "shopify_handle": "product-7",
                        "product_title": "Product 7",
                        "edition_total": 100,
                        "next_edition_number": 7,
                        "active": True,
                        "sold_out": False,
                        "sold_count": 6,
                    }
                ]
            )
        )
        with patch.object(supabase_backend, "connect", side_effect=[stale, fresh]):
            rows = supabase_backend.list_edition_products_read_only(limit=50)
        self.assertEqual(rows[0]["shopify_handle"], "product-7")
        self.assertEqual(stale.close_calls, 1)
        self.assertEqual(fresh.close_calls, 1)
        self.assertGreaterEqual(stale.rollback_calls, 1)
        self.assertGreaterEqual(fresh.rollback_calls, 1)
        diagnostic = supabase_backend.get_last_database_read_diagnostic()
        self.assertTrue(diagnostic["recovered"])
        self.assertEqual(diagnostic["attempts"], 2)
        self.assertEqual(diagnostic["query_count"], 1)

    def test_temporary_failure_uses_labelled_session_cache_and_render_stays_alive(self):
        cached_row = _product(3)
        fake_st = _FakeStreamlit(
            {
                edition_ops.ROWS_KEY: [cached_row],
                edition_ops.ORIGINAL_ROWS_KEY: [cached_row],
                edition_ops.META_KEY: {
                    "source": "supabase",
                    "saved_at": "2026-07-13T22:40:00Z",
                    "last_refreshed_from_shopify": "2026-07-13T22:40:00Z",
                },
            }
        )
        error = supabase_backend.DatabaseReadError(
            "The database is temporarily unavailable. Please retry.",
            {
                "operation": "edition_ops.products.latest",
                "category": "database_unavailable",
                "exception_class": "OperationalError",
                "duration_ms": 8000,
            },
        )
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_load_supabase_snapshot", side_effect=error
        ), patch.object(edition_ops, "_configured_supabase_backend", return_value=None), patch.object(
            edition_ops, "_local_cached_snapshot", return_value=None
        ):
            edition_ops._ensure_state()
            result = edition_ops._load_snapshot()
        self.assertTrue(result["cached"])
        self.assertEqual(result["source"], "session_cache")
        self.assertEqual(result["rows"][0]["handle"], "product-3")
        self.assertIn("temporarily unavailable", result["load_error"])

    def test_repeated_reruns_only_hydrate_once(self):
        fake_st = SimpleNamespace(session_state={})
        with patch.object(edition_ops, "st", fake_st):
            edition_ops._ensure_state()
            with patch.object(edition_ops, "_load_snapshot", return_value=_snapshot([_product(4)])) as loader:
                edition_ops._hydrate_from_snapshot_once()
                edition_ops._hydrate_from_snapshot_once()
        self.assertEqual(loader.call_count, 1)
        self.assertTrue(fake_st.session_state[edition_ops.SNAPSHOT_LOADED_KEY])

    def test_render_is_bounded_and_does_not_load_diagnostics_shopify_or_writes(self):
        rows = [_product(index) for index in range(1, 121)]
        fake_st = _FakeStreamlit(
            {
                edition_ops.SNAPSHOT_LOADED_KEY: True,
                edition_ops.ROWS_KEY: rows,
                edition_ops.ORIGINAL_ROWS_KEY: [dict(row) for row in rows],
                edition_ops.META_KEY: {"source": "supabase", "cached": False},
            }
        )
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=object()
        ), patch.object(
            edition_ops,
            "_render_product_sync_diagnostics",
            side_effect=AssertionError("Collapsed diagnostics must not query on page load."),
        ), patch.object(
            edition_ops.shopify_sync,
            "get_config",
            side_effect=AssertionError("Edition Ops page load must not call Shopify."),
        ), patch.object(
            edition_ops,
            "_write_snapshot",
            side_effect=AssertionError("Edition Ops page load must not write a snapshot."),
        ):
            edition_ops.render_page()
        self.assertEqual(len(fake_st.editor_payloads), 1)
        self.assertEqual(len(fake_st.editor_payloads[0]), 120)
        self.assertEqual(
            set(fake_st.editor_payloads[0][0]),
            {"edition_product_id", "shopify_product_gid", *edition_ops.VISIBLE_COLUMNS},
        )

    def test_paginated_editor_submission_preserves_rows_outside_the_visible_page(self):
        rows = [_product(index) for index in range(1, 121)]
        originals = [dict(row) for row in rows]
        source_page = rows[50:100]
        edited_page = [edition_ops._editor_payload(row) for row in source_page]
        edited_page[0]["edition_next_number"] = 99
        fake_st = SimpleNamespace(
            session_state={
                edition_ops.ROWS_KEY: rows,
                edition_ops.ORIGINAL_ROWS_KEY: originals,
                edition_ops.EDITOR_ROWS_KEY: [dict(row) for row in rows],
            }
        )
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=None
        ):
            edition_ops._save_changed_rows(edited_page, source_rows=source_page)
        saved_rows = fake_st.session_state[edition_ops.ROWS_KEY]
        self.assertEqual(len(saved_rows), 120)
        self.assertEqual(saved_rows[50]["edition_next_number"], 99)
        self.assertEqual(saved_rows[49]["edition_next_number"], rows[49]["edition_next_number"])
        self.assertEqual(saved_rows[100]["edition_next_number"], rows[100]["edition_next_number"])

    def test_failed_initial_read_is_an_in_page_error_not_a_process_exception(self):
        fake_st = _FakeStreamlit()
        error = supabase_backend.DatabaseReadError(
            "The database read timed out. Please retry.",
            {
                "operation": "edition_ops.products.latest",
                "category": "request_timeout",
                "exception_class": "QueryCanceled",
                "duration_ms": 8000,
            },
        )
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_load_supabase_snapshot", side_effect=error
        ), patch.object(edition_ops, "_configured_supabase_backend", return_value=None), patch.object(
            edition_ops, "_local_cached_snapshot", return_value=None
        ):
            edition_ops.render_page()
        self.assertTrue(fake_st.errors)
        self.assertIn("timed out", fake_st.errors[0])
        self.assertEqual(fake_st.editor_payloads, [])

    def test_edition_ops_query_is_one_bounded_bulk_read_without_write_sql(self):
        cursor = _Cursor(rows=[])
        connection = _Connection(cursor)
        with patch.object(supabase_backend, "connect", return_value=connection):
            rows = supabase_backend.list_edition_products_read_only(limit=5000)
        self.assertEqual(rows, [])
        self.assertEqual(len(cursor.statements), 1)
        statement, params = cursor.statements[0]
        upper = statement.upper()
        self.assertIn("WITH SELECTED_PRODUCTS AS", upper)
        self.assertIn("SELECTED_ORDERS AS", upper)
        self.assertIn("HANDLE_TOTALS AS", upper)
        self.assertNotIn("SELECT EP.*", upper)
        self.assertEqual(upper.count("FROM EDITION_ORDERS"), 1)
        self.assertNotIn("INSERT INTO", upper)
        self.assertNotIn("UPDATE EDITION_", upper)
        self.assertNotIn("DELETE FROM", upper)
        self.assertEqual(params[-2:], (1000, 0))
        self.assertEqual(connection.close_calls, 1)

    def test_product_webhook_contract_remains_present_and_separate(self):
        webhook_source = (ROOT / "webhook_server.py").read_text(encoding="utf-8")
        edition_source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")
        self.assertIn('@app.post("/webhooks/shopify/products-create")', webhook_source)
        self.assertIn('@app.post("/webhooks/shopify/products-update")', webhook_source)
        self.assertIn("verify_shopify_webhook_hmac", webhook_source)
        self.assertIn("process_product_create_webhook", webhook_source)
        self.assertNotIn("process_product_create_webhook", edition_source[edition_source.index("def render_page():") :])


if __name__ == "__main__":
    unittest.main()
