import inspect
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import edition_ops
import shopify_sync
import supabase_backend
from tests.test_edition_ops_stability import _FakeStreamlit, _product


CONFIG = {
    "store_domain": "sports-cave.myshopify.com",
    "access_token": "test-token",
    "api_version": "2026-07",
    "configured": True,
}


def _shopify_product(number, *, handle=None, title=None, created_at=None):
    return {
        "shopify_product_id": f"gid://shopify/Product/{number}",
        "legacy_resource_id": str(number),
        "handle": handle or f"product-{number}",
        "title": title or f"Product {number}",
        "status": "ACTIVE",
        "created_at": created_at or f"2026-07-14T00:{int(number) % 60:02d}:00Z",
        "remote_updated_at": created_at or f"2026-07-14T00:{int(number) % 60:02d}:00Z",
    }


def _existing_product(number, *, handle=None, **counters):
    return {
        "shopify_product_id": f"gid://shopify/Product/{number}",
        "shopify_product_gid": f"gid://shopify/Product/{number}",
        "shopify_handle": handle or f"product-{number}",
        **counters,
    }


class EditionOpsNewProductPullTests(unittest.TestCase):
    def _run_pull(
        self,
        products,
        *,
        existing_rows=None,
        state=None,
        has_next_page=False,
        insert_result=None,
        mirror_result=None,
    ):
        insert_result = insert_result or {
            "inserted_handles": [],
            "new_products_inserted": 0,
            "concurrent_skips": 0,
        }
        mirror_result = mirror_result or {
            "attempted": len(insert_result.get("inserted_handles") or []),
            "synced": len(insert_result.get("inserted_handles") or []),
            "failed": 0,
            "errors": [],
        }
        with patch.object(
            supabase_backend,
            "_start_new_product_discovery",
            return_value=(list(existing_rows or []), dict(state or {})),
        ), patch.object(
            supabase_backend.shopify_sync,
            "fetch_newest_products_for_edition_ops",
            return_value={
                "products": list(products),
                "has_next_page": has_next_page,
                "query": "(status:active OR status:draft)",
            },
        ) as fetch, patch.object(
            supabase_backend,
            "_insert_new_product_candidates",
            return_value=insert_result,
        ) as insert, patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            return_value=mirror_result,
        ) as mirror, patch.object(
            supabase_backend,
            "_finish_new_product_discovery_state",
        ) as finish:
            result = supabase_backend.sync_new_shopify_products_to_edition_ops(config=CONFIG)
        return result, fetch, insert, mirror, finish

    def test_no_new_products_skips_existing_without_writes(self):
        product = _shopify_product(1)
        result, fetch, insert, mirror, _ = self._run_pull(
            [product],
            existing_rows=[_existing_product(1)],
        )
        self.assertEqual(result["new_products_inserted"], 0)
        self.assertEqual(result["existing_products_skipped"], 1)
        fetch.assert_called_once()
        insert.assert_called_once_with([])
        mirror.assert_not_called()

    def test_one_new_product_is_inserted_and_mirrored_once(self):
        result, _, insert, mirror, _ = self._run_pull(
            [_shopify_product(2)],
            insert_result={
                "inserted_handles": ["product-2"],
                "new_products_inserted": 1,
                "concurrent_skips": 0,
            },
        )
        self.assertEqual(result["new_products_inserted"], 1)
        self.assertEqual(result["shopify_metafields_pushed"], 1)
        self.assertEqual(insert.call_args.args[0][0]["shopify_product_id"], "gid://shopify/Product/2")
        mirror.assert_called_once_with(["product-2"], config=CONFIG, ensure_schema_first=False)

    def test_several_new_products_and_same_title_use_distinct_ids(self):
        products = [
            _shopify_product(3, title="Same Title"),
            _shopify_product(4, title="Same Title"),
            _shopify_product(5),
        ]
        classified = supabase_backend._classify_new_shopify_products(products, [])
        self.assertEqual(len(classified["missing_products"]), 3)
        self.assertEqual(
            {item["shopify_product_id"] for item in classified["missing_products"]},
            {"gid://shopify/Product/3", "gid://shopify/Product/4", "gid://shopify/Product/5"},
        )

    def test_first_fifty_products_already_exist_and_only_one_page_is_requested(self):
        products = [_shopify_product(index) for index in range(1, 51)]
        existing = [_existing_product(index) for index in range(1, 51)]
        result, fetch, insert, mirror, _ = self._run_pull(
            products,
            existing_rows=existing,
            has_next_page=True,
        )
        self.assertEqual(result["products_fetched"], 50)
        self.assertEqual(result["existing_products_skipped"], 50)
        self.assertEqual(result["maximum_products_fetched"], 50)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs["page_size"], 50)
        insert.assert_called_once_with([])
        mirror.assert_not_called()

    def test_button_pressed_twice_only_inserts_on_first_press(self):
        product = _shopify_product(6)
        contexts = [([], {}), ([_existing_product(6)], {})]
        inserts = [
            {"inserted_handles": ["product-6"], "new_products_inserted": 1, "concurrent_skips": 0},
            {"inserted_handles": [], "new_products_inserted": 0, "concurrent_skips": 0},
        ]
        with patch.object(
            supabase_backend,
            "_start_new_product_discovery",
            side_effect=contexts,
        ), patch.object(
            supabase_backend.shopify_sync,
            "fetch_newest_products_for_edition_ops",
            return_value={"products": [product], "has_next_page": False, "query": "newest"},
        ), patch.object(
            supabase_backend,
            "_insert_new_product_candidates",
            side_effect=inserts,
        ) as insert, patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            return_value={"attempted": 1, "synced": 1, "failed": 0, "errors": []},
        ) as mirror, patch.object(
            supabase_backend,
            "_finish_new_product_discovery_state",
        ):
            first = supabase_backend.sync_new_shopify_products_to_edition_ops(config=CONFIG)
            second = supabase_backend.sync_new_shopify_products_to_edition_ops(config=CONFIG)
        self.assertEqual(first["new_products_inserted"], 1)
        self.assertEqual(second["new_products_inserted"], 0)
        self.assertEqual(second["existing_products_skipped"], 1)
        self.assertEqual(insert.call_count, 2)
        mirror.assert_called_once()

    def test_webhook_race_is_counted_as_skip_and_never_mirrored(self):
        class RaceCursor:
            def __init__(self):
                self.results = [None, None]
                self.statements = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, statement, params=None):
                self.statements.append(statement)

            def fetchone(self):
                return self.results.pop(0)

        class RaceConnection:
            def __init__(self, cursor):
                self._cursor = cursor
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self._cursor

            def commit(self):
                self.commits += 1

        race_cursor = RaceCursor()
        race_connection = RaceConnection(race_cursor)
        with patch.object(supabase_backend, "connect", return_value=race_connection):
            race_result = supabase_backend._insert_new_product_candidates([_shopify_product(7)])
        self.assertEqual(race_result["new_products_inserted"], 0)
        self.assertEqual(race_result["concurrent_skips"], 1)
        self.assertEqual(race_connection.commits, 1)
        self.assertTrue(all("ON CONFLICT DO NOTHING" in statement for statement in race_cursor.statements))

        result, _, _, mirror, _ = self._run_pull(
            [_shopify_product(7)],
            insert_result={
                "inserted_handles": [],
                "new_products_inserted": 0,
                "concurrent_skips": 1,
            },
        )
        self.assertEqual(result["new_products_inserted"], 0)
        self.assertEqual(result["existing_products_skipped"], 1)
        mirror.assert_not_called()

    def test_changed_handle_with_same_product_id_is_existing_and_untouched(self):
        product = _shopify_product(8, handle="new-handle")
        existing = _existing_product(
            8,
            handle="old-handle",
            edition_total=250,
            next_edition_number=73,
            sold_count=72,
            remaining_count=178,
            active=False,
        )
        classified = supabase_backend._classify_new_shopify_products([product], [existing])
        self.assertEqual(classified["missing_products"], [])
        self.assertEqual(classified["existing_products_skipped"], 1)

    def test_old_row_without_id_may_use_handle_fallback_only(self):
        old_row = {"shopify_product_id": "", "shopify_product_gid": "", "shopify_handle": "legacy-handle"}
        product = _shopify_product(9, handle="legacy-handle")
        classified = supabase_backend._classify_new_shopify_products([product], [old_row])
        self.assertEqual(classified["missing_products"], [])
        self.assertEqual(classified["existing_products_skipped"], 1)

    def test_metafield_failure_keeps_insert_and_marks_only_new_product_pending(self):
        product = _shopify_product(10)
        with patch.object(
            supabase_backend,
            "_start_new_product_discovery",
            return_value=([], {}),
        ), patch.object(
            supabase_backend.shopify_sync,
            "fetch_newest_products_for_edition_ops",
            return_value={"products": [product], "has_next_page": False, "query": "newest"},
        ), patch.object(
            supabase_backend,
            "_insert_new_product_candidates",
            return_value={
                "inserted_handles": ["product-10"],
                "new_products_inserted": 1,
                "concurrent_skips": 0,
            },
        ), patch.object(
            supabase_backend,
            "sync_product_edition_metafields_for_handles",
            side_effect=RuntimeError("Shopify unavailable"),
        ), patch.object(
            supabase_backend,
            "_mark_product_metafields_sync",
        ) as mark, patch.object(
            supabase_backend,
            "_finish_new_product_discovery_state",
        ) as finish:
            result = supabase_backend.sync_new_shopify_products_to_edition_ops(config=CONFIG)
        self.assertEqual(result["new_products_inserted"], 1)
        self.assertEqual(result["shopify_metafields_failed_pending"], 1)
        mark.assert_called_once()
        self.assertEqual(mark.call_args.args[0], "product-10")
        self.assertEqual(mark.call_args.args[1]["next_edition_number"], 1)
        self.assertEqual(finish.call_args.kwargs["status"], "complete_with_warnings")

    def test_existing_edition_counters_and_state_never_enter_write_path(self):
        existing = _existing_product(
            11,
            edition_total=500,
            next_edition_number=222,
            sold_count=221,
            remaining_count=279,
            active=False,
        )
        result, _, insert, mirror, _ = self._run_pull(
            [_shopify_product(11, handle="renamed-product", title="Renamed Product")],
            existing_rows=[existing],
        )
        self.assertEqual(result["existing_products_skipped"], 1)
        insert.assert_called_once_with([])
        mirror.assert_not_called()
        insertion_source = inspect.getsource(supabase_backend._insert_edition_product_if_missing)
        self.assertIn("100, 1, 0, 0, 100", insertion_source)
        self.assertNotIn("SET edition_total", insertion_source)
        self.assertNotIn("SET next_edition_number", insertion_source)
        self.assertNotIn("SET sold_count", insertion_source)

    def test_watermark_advances_only_after_successful_complete_discovery(self):
        product = _shopify_product(12, created_at="2026-07-14T01:00:00Z")
        result, _, _, _, finish = self._run_pull([product], has_next_page=False)
        self.assertTrue(result["watermark_advanced"])
        self.assertEqual(result["latest_shopify_product_id"], "gid://shopify/Product/12")
        self.assertIsNotNone(finish.call_args.kwargs.get("successful_at"))

        with patch.object(
            supabase_backend,
            "_start_new_product_discovery",
            return_value=([], {"latest_shopify_product_created_at": "2026-07-13T00:00:00Z"}),
        ), patch.object(
            supabase_backend.shopify_sync,
            "fetch_newest_products_for_edition_ops",
            side_effect=RuntimeError("Shopify timeout"),
        ), patch.object(
            supabase_backend,
            "_finish_new_product_discovery_state",
        ) as failed_finish:
            with self.assertRaisesRegex(RuntimeError, "Shopify timeout"):
                supabase_backend.sync_new_shopify_products_to_edition_ops(config=CONFIG)
        self.assertEqual(failed_finish.call_args.kwargs["status"], "failed")
        self.assertNotIn("successful_at", failed_finish.call_args.kwargs)

    def test_shopify_discovery_query_is_newest_first_lightweight_and_capped_at_fifty(self):
        captured = {}

        def fake_graphql(query, variables=None, **kwargs):
            captured["query"] = query
            captured["variables"] = variables
            return ({"products": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "cursor"}}}, "2026-07")

        with patch.object(shopify_sync, "graphql_request", side_effect=fake_graphql):
            result = shopify_sync.fetch_newest_products_for_edition_ops(
                created_after="2026-07-14T00:00:00Z",
                page_size=5000,
                config=CONFIG,
            )
        self.assertEqual(captured["variables"]["first"], 50)
        self.assertIn("created_at:>='2026-07-14T00:00:00Z'", captured["variables"]["query"])
        self.assertIn("sortKey: CREATED_AT", captured["query"])
        self.assertIn("reverse: true", captured["query"])
        self.assertNotIn("variants(", captured["query"])
        self.assertNotIn("metafields(", captured["query"])
        self.assertTrue(result["has_next_page"])

    def test_normal_page_load_makes_no_shopify_call_and_editor_has_complete_catalogue(self):
        rows = [_product(index) for index in range(1, 121)]
        fake_st = _FakeStreamlit(
            {
                edition_ops.SNAPSHOT_LOADED_KEY: True,
                edition_ops.ROWS_KEY: rows,
                edition_ops.ORIGINAL_ROWS_KEY: [dict(row) for row in rows],
                edition_ops.META_KEY: {"source": "supabase", "cached": False},
            }
        )
        backend = SimpleNamespace(sync_new_shopify_products_to_edition_ops=Mock())
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops,
            "_configured_supabase_backend",
            return_value=backend,
        ), patch.object(
            edition_ops.shopify_sync,
            "get_config",
            side_effect=AssertionError("Normal Edition Ops load must not call Shopify."),
        ):
            edition_ops.render_page()
        backend.sync_new_shopify_products_to_edition_ops.assert_not_called()
        self.assertEqual(len(fake_st.editor_payloads[0]), 120)

    def test_manual_refresh_uses_complete_reconciliation_and_recovery_action_stays_gated(self):
        ui_source = inspect.getsource(edition_ops._render_advanced_controls)
        normal_pull_source = inspect.getsource(supabase_backend.sync_new_shopify_products_to_edition_ops)
        reconciliation_source = inspect.getsource(supabase_backend.reconcile_all_shopify_products_to_edition_ops)
        self.assertIn('"Refresh Shopify Catalogue"', ui_source)
        self.assertIn("backend.reconcile_all_shopify_products_to_edition_ops", ui_source)
        self.assertIn('"Full Product Reconciliation"', ui_source)
        self.assertIn("reconciliation_confirmed = st.checkbox", ui_source)
        self.assertIn("disabled=not backend or not reconciliation_confirmed", ui_source)
        self.assertNotIn("iter_catalog_pages", normal_pull_source)
        self.assertIn("fetch_edition_ops_active_products", reconciliation_source)

    def test_zero_and_one_new_product_paths_complete_quickly_with_mocked_io(self):
        zero_started = time.perf_counter()
        zero, *_ = self._run_pull([], existing_rows=[])
        zero_elapsed = time.perf_counter() - zero_started
        one_started = time.perf_counter()
        one, *_ = self._run_pull(
            [_shopify_product(13)],
            insert_result={
                "inserted_handles": ["product-13"],
                "new_products_inserted": 1,
                "concurrent_skips": 0,
            },
        )
        one_elapsed = time.perf_counter() - one_started
        self.assertEqual(zero["new_products_inserted"], 0)
        self.assertEqual(one["new_products_inserted"], 1)
        self.assertLess(zero_elapsed, 0.25)
        self.assertLess(one_elapsed, 0.25)


if __name__ == "__main__":
    unittest.main()
