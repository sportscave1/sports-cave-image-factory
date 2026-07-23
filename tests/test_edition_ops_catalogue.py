import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import edition_ops
import shopify_sync
import supabase_backend


CONFIG = {
    "configured": True,
    "store_domain": "sports-cave.myshopify.com",
    "api_version": "2026-04",
}


def _shopify_product(index, *, title=None, handle=None, status="ACTIVE"):
    return {
        "shopify_product_id": f"gid://shopify/Product/{index}",
        "shopify_product_gid": f"gid://shopify/Product/{index}",
        "legacy_resource_id": str(index),
        "title": title or f"Product {index}",
        "handle": handle or f"product-{index}",
        "status": status,
        "thumbnail_url": "",
    }


def _edition_product(index, *, title=None, handle=None, with_id=True):
    gid = f"gid://shopify/Product/{index}" if with_id else ""
    return {
        "id": f"edition-{index}",
        "edition_product_id": f"edition-{index}",
        "shopify_product_id": gid,
        "shopify_product_gid": gid,
        "shopify_handle": handle or f"product-{index}",
        "handle": handle or f"product-{index}",
        "product_title": title or f"Product {index}",
        "edition_total": 250,
        "next_edition_number": 73,
        "last_assigned_edition": 72,
        "sold_count": 72,
        "remaining_count": 178,
        "active": True,
        "is_active": True,
        "featured_image_url": "",
    }


class _Cursor:
    rowcount = 1

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchone(self):
        return {}

    def fetchall(self):
        return []


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        return None


class EditionOpsCatalogueTests(unittest.TestCase):
    def test_catalogue_fetch_returns_every_product_and_stops_on_final_page(self):
        pages = [
            {
                "products": [_shopify_product(index) for index in range(1, 251)],
                "has_next_page": True,
                "end_cursor": "cursor-250",
                "api_version": "2026-04",
            },
            {
                "products": [_shopify_product(index) for index in range(251, 312)],
                "has_next_page": False,
                "end_cursor": "cursor-311",
                "api_version": "2026-04",
            },
        ]
        with patch.object(
            shopify_sync,
            "fetch_edition_ops_active_products_page",
            side_effect=pages,
        ) as fetch_page:
            result = shopify_sync.fetch_edition_ops_active_products(config=CONFIG)

        self.assertEqual(len(result["products"]), 311)
        self.assertEqual(result["page_count"], 2)
        self.assertTrue(result["complete"])
        self.assertEqual(fetch_page.call_args_list[0].kwargs["page_size"], 250)
        self.assertIsNone(fetch_page.call_args_list[0].kwargs["after"])
        self.assertEqual(fetch_page.call_args_list[1].kwargs["after"], "cursor-250")

    def test_partial_pagination_failure_returns_no_partial_catalogue(self):
        first_page = {
            "products": [_shopify_product(index) for index in range(1, 251)],
            "has_next_page": True,
            "end_cursor": "cursor-250",
        }
        with patch.object(
            shopify_sync,
            "fetch_edition_ops_active_products_page",
            side_effect=[first_page, shopify_sync.ShopifyAPIError("Shopify timeout")],
        ):
            with self.assertRaisesRegex(shopify_sync.ShopifyAPIError, "Shopify timeout"):
                shopify_sync.fetch_edition_ops_active_products(config=CONFIG)

    def test_streamlit_catalogue_cache_reads_all_database_pages_once(self):
        products = [
            {
                "id": str(index),
                "shopify_product_id": f"gid://shopify/Product/{index}",
                "shopify_handle": f"product-{index}",
                "product_title": f"Product {index}",
                "edition_total": 100,
                "next_edition_number": 1,
                "active": True,
            }
            for index in range(1, 1206)
        ]

        class Backend:
            def __init__(self):
                self.offsets = []

            def list_edition_products_read_only(self, *, search, limit, offset=0):
                self.offsets.append(offset)
                return products[offset : offset + limit]

            def get_last_database_read_diagnostic(self):
                return {"query_count": 1}

        backend = Backend()
        edition_ops._cached_supabase_products_snapshot.clear()
        with patch.object(edition_ops, "_configured_supabase_backend", return_value=backend):
            first = edition_ops._cached_supabase_products_snapshot(987654321)
            second = edition_ops._cached_supabase_products_snapshot(987654321)
        edition_ops._cached_supabase_products_snapshot.clear()

        self.assertEqual(len(first["rows"]), 1205)
        self.assertEqual(len(second["rows"]), 1205)
        self.assertEqual(backend.offsets, [0, 1000])
        self.assertEqual(first["database_read"]["query_count"], 2)

    def test_manual_refresh_uses_full_reconciliation_and_preserves_selection(self):
        selected_key = "edition_product:edition-2"
        fake_st = SimpleNamespace(
            session_state={edition_ops.EDITOR_PRODUCT_SELECTION_KEY: selected_key}
        )
        backend = Mock()
        backend.reconcile_all_shopify_products_to_edition_ops.return_value = {
            "products_checked": 311,
        }
        snapshot = {
            "rows": [edition_ops._normalise_row(_edition_product(2))],
            "original_rows": [edition_ops._normalise_row(_edition_product(2))],
            "last_refreshed_from_shopify": "2026-07-23T02:00:00Z",
            "saved_at": "2026-07-23T02:00:00Z",
        }
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops.shopify_sync, "get_config", return_value=CONFIG
        ), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=backend
        ), patch.object(
            edition_ops, "_load_supabase_snapshot", return_value=snapshot
        ), patch.object(edition_ops, "_write_snapshot"):
            edition_ops._load_active_products_from_shopify()

        backend.reconcile_all_shopify_products_to_edition_ops.assert_called_once_with(config=CONFIG)
        self.assertEqual(fake_st.session_state[edition_ops.EDITOR_PRODUCT_SELECTION_KEY], selected_key)

    def test_product_selector_can_open_an_item_beyond_the_old_fifty_row_limit(self):
        rows = [edition_ops._normalise_row(_edition_product(index)) for index in range(1, 121)]
        selected_key = edition_ops._stable_row_key(rows[100])

        class FakeStreamlit:
            def __init__(self):
                self.session_state = {
                    edition_ops.EDITOR_PRODUCT_SELECTION_KEY: selected_key,
                }

            def selectbox(self, _label, _options, **_kwargs):
                return self.session_state[edition_ops.EDITOR_PRODUCT_SELECTION_KEY]

        with patch.object(edition_ops, "st", FakeStreamlit()):
            visible, selected = edition_ops._editor_visible_rows(rows)

        self.assertEqual(selected, selected_key)
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["product_title"], "Product 101")

    def test_title_and_handle_rename_match_by_shopify_id_without_counter_changes(self):
        existing = _edition_product(
            91,
            title="The Mountain Chooses: Payne vs Feeney Wall Art",
            handle="the-mountain-chooses-payne-vs-feeney",
        )
        product = _shopify_product(
            91,
            title="Payne vs Feeney The Mountain Chooses Wall Art",
            handle="payne-vs-feeney-the-mountain-chooses-wall-art",
        )
        actions = supabase_backend._plan_edition_product_incremental_sync([product], [existing])

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "update")
        self.assertEqual(actions[0]["match_type"], "shopify_product_id")
        self.assertEqual(actions[0]["fields"]["product_title"], product["title"])
        self.assertEqual(actions[0]["fields"]["shopify_handle"], product["handle"])
        for protected in (
            "edition_total",
            "next_edition_number",
            "last_assigned_edition",
            "sold_count",
            "remaining_count",
        ):
            self.assertNotIn(protected, actions[0]["fields"])

    def test_rename_is_idempotent_and_does_not_create_a_duplicate(self):
        product = _shopify_product(92, title="Current Product", handle="current-product")
        existing = _edition_product(92, title="Old Product", handle="old-product")
        first = supabase_backend._plan_edition_product_incremental_sync([product], [existing])
        updated = {**existing, **first[0]["fields"]}
        second = supabase_backend._plan_edition_product_incremental_sync([product], [updated])

        self.assertEqual(first[0]["action"], "update")
        self.assertEqual(second[0]["action"], "skip")
        self.assertFalse(any(action["action"] == "insert" for action in first + second))

    def test_rename_updates_run_metadata_without_touching_run_counters(self):
        cursor = _Cursor()
        existing = _edition_product(93, title="Old Product", handle="old-product")
        updates = {
            "shopify_product_id": "gid://shopify/Product/93",
            "shopify_product_gid": "gid://shopify/Product/93",
            "product_title": "Current Product",
            "shopify_handle": "current-product",
        }
        self.assertTrue(
            supabase_backend._update_existing_edition_product_safe_fields(cursor, existing, updates)
        )

        self.assertEqual(len(cursor.statements), 2)
        run_sql = cursor.statements[1][0]
        self.assertIn("UPDATE edition_runs", run_sql)
        self.assertIn("edition_product_id", run_sql)
        self.assertNotIn("edition_total", run_sql)
        self.assertNotIn("next_edition_number", run_sql)
        self.assertNotIn("sold_count", run_sql)

    def test_unambiguous_legacy_handle_backfills_shopify_id(self):
        legacy = _edition_product(94, with_id=False, handle="legacy-product")
        product = _shopify_product(94, handle="legacy-product", title="Current Product")
        action = supabase_backend._plan_edition_product_incremental_sync([product], [legacy])[0]

        self.assertEqual(action["action"], "update")
        self.assertEqual(action["match_type"], "handle")
        self.assertEqual(action["fields"]["shopify_product_id"], product["shopify_product_id"])

    def test_unambiguous_exact_legacy_title_is_a_last_resort_migration(self):
        legacy = _edition_product(
            98,
            with_id=False,
            title="Exact Legacy Product",
            handle="old-legacy-handle",
        )
        product = _shopify_product(
            99,
            title="Exact Legacy Product",
            handle="current-shopify-handle",
        )
        action = supabase_backend._plan_edition_product_incremental_sync([product], [legacy])[0]

        self.assertEqual(action["action"], "update")
        self.assertEqual(action["match_type"], "exact_title_migration")
        self.assertEqual(action["fields"]["shopify_product_id"], product["shopify_product_id"])

    def test_ambiguous_legacy_title_is_not_merged_or_inserted(self):
        first = _edition_product(95, with_id=False, title="Legacy Product", handle="legacy-one")
        second = _edition_product(96, with_id=False, title="Legacy Product", handle="legacy-two")
        product = _shopify_product(97, title="Legacy Product", handle="current-product")
        action = supabase_backend._plan_edition_product_incremental_sync(
            [product],
            [first, second],
        )[0]

        self.assertEqual(action["action"], "error")
        self.assertIn("matches more than one", action["error"])

    def test_reconciliation_failure_never_calls_catalogue_upsert(self):
        connection = _Connection()
        with patch.object(supabase_backend, "ensure_schema"), patch.object(
            supabase_backend, "start_sync_run", return_value="run-1"
        ), patch.object(supabase_backend, "finish_sync_run"), patch.object(
            supabase_backend, "log_app_error"
        ), patch.object(supabase_backend, "connect", return_value=connection), patch.object(
            supabase_backend.shopify_sync,
            "fetch_edition_ops_active_products",
            side_effect=shopify_sync.ShopifyAPIError("page two failed"),
        ), patch.object(
            supabase_backend, "upsert_shopify_products_to_edition_products"
        ) as upsert, patch.object(supabase_backend, "set_app_setting"):
            with self.assertRaisesRegex(shopify_sync.ShopifyAPIError, "page two failed"):
                supabase_backend.reconcile_all_shopify_products_to_edition_ops(config=CONFIG)

        upsert.assert_not_called()

    def test_read_model_keeps_order_history_visible_after_a_handle_rename(self):
        cursor = _Cursor()
        connection = _Connection()
        connection.cursor_value = cursor
        with patch.object(supabase_backend, "connect", return_value=connection), patch.object(
            supabase_backend, "_run_read_operation", side_effect=lambda _operation, callback: (callback(cursor), {})
        ):
            supabase_backend.list_edition_products_read_only(limit=10)

        query = cursor.statements[0][0]
        self.assertIn("selected.active_edition_run_id = eo.edition_run_id", query)
        self.assertIn("selected.shopify_product_id", query)
        self.assertIn("current_shopify_handle", query)


if __name__ == "__main__":
    unittest.main()
