import os
import inspect
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import order_allocator
import run_migrations
import shopify_sync
import shopify_order_reconciliation_worker
import supabase_backend
from scripts import reconcile_shopify_order as reconcile_script


def paid_marketplace_order(**overrides):
    order = {
        "shopify_order_id": "gid://shopify/Order/3020",
        "legacy_resource_id": "3020",
        "order_name": "#SC3020",
        "order_number": "SC3020",
        "created_at": "2026-08-17T13:22:00+10:00",
        "processed_at": "2026-08-17T13:22:10+10:00",
        "remote_updated_at": "2026-08-17T13:22:10+10:00",
        "financial_status": "PAID",
        "fulfillment_status": "UNFULFILLED",
        "source_name": "etsy",
        "source_display": "Etsy",
        "shipping_method": "Australia Post",
        "shipping_title": "Australia Post",
        "customer_name": "Marketplace customer",
        "line_items": [
            {
                "shopify_line_item_id": "gid://shopify/LineItem/30201",
                "shopify_product_id": "gid://shopify/Product/200",
                "shopify_variant_id": "gid://shopify/ProductVariant/201",
                "variant_id": "gid://shopify/ProductVariant/201",
                "product_title": "Limited Wall Art",
                "variant_title": "Black / XL",
                "sku": "LIMITED-BLACK-XL",
                "quantity": 1,
            }
        ],
    }
    order.update(overrides)
    return order


class MappingCursor:
    def __init__(self, *, variant_rows=None, sku_rows=None):
        self.variant_rows = list(variant_rows or [])
        self.sku_rows = list(sku_rows or [])
        self.rows = []
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append((str(sql), params))
        if "sv.shopify_variant_id = ANY" in str(sql):
            self.rows = self.variant_rows
        elif "LOWER(BTRIM(COALESCE(sv.sku" in str(sql):
            self.rows = self.sku_rows
        else:
            self.rows = []

    def fetchall(self):
        return list(self.rows)


class ShopifyMarketplaceReconciliationTests(unittest.TestCase):
    def test_targeted_reconciliation_cli_is_dry_run_and_accepts_narrow_ids(self):
        args = reconcile_script.build_parser().parse_args(
            ["--order-id", "gid://shopify/Order/3020", "--order-id", "3021"]
        )

        self.assertEqual(["gid://shopify/Order/3020", "3021"], args.order_id)
        self.assertFalse(args.apply)
        self.assertFalse(args.notify)

    def test_core_order_upsert_uses_pre_marketplace_columns_and_preserves_channel_in_raw_json(self):
        class Cursor:
            def execute(self, sql, params=()):
                self.sql = str(sql)
                self.params = tuple(params or ())

        cursor = Cursor()
        order = paid_marketplace_order()

        supabase_backend._upsert_order(cursor, order)

        column_clause = cursor.sql.split("VALUES", 1)[0]
        self.assertNotIn("source_name", column_clause)
        self.assertNotIn("ingestion_status", column_clause)
        self.assertIn('"source_name": "etsy"', str(cursor.params))

    def test_optional_ingestion_diagnostics_do_not_break_old_schema(self):
        class UndefinedColumn(Exception):
            sqlstate = "42703"
            diag = SimpleNamespace(column_name="source_name")

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, _sql, _params=()):
                raise UndefinedColumn("column source_name does not exist")

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return Cursor()

            def commit(self):
                return None

        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend, "connect", return_value=Connection()
        ):
            supabase_backend._set_order_ingestion_outcome(
                paid_marketplace_order(),
                ingestion_method="webhook",
                ingestion_status="complete",
                import_result="inserted",
            )

        self.assertFalse(supabase_backend._ORDER_MARKETPLACE_READ_CAPABILITY)

    def test_optional_ingestion_diagnostic_failure_does_not_fail_committed_order(self):
        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend, "connect", side_effect=RuntimeError("diagnostic database timeout")
        ):
            supabase_backend._set_order_ingestion_outcome(
                paid_marketplace_order(),
                ingestion_method="webhook",
                ingestion_status="complete",
                import_result="inserted",
            )

    def test_core_webhook_receipt_sql_does_not_require_marketplace_columns(self):
        source = inspect.getsource(supabase_backend._claim_webhook_event)
        core_insert = source.split("ON CONFLICT", 1)[0]

        self.assertNotIn("source_name", core_insert)
        self.assertNotIn("import_result", core_insert)
        self.assertNotIn("rejection_reason", core_insert)

    def test_recent_reconciliation_state_reader_is_pre_marketplace_compatible(self):
        source = inspect.getsource(supabase_backend.list_existing_shopify_order_states)

        self.assertIn("to_jsonb(o)->>'ingestion_status'", source)
        self.assertNotIn("SELECT shopify_order_id, remote_updated_at, created_at, synced_at,\n                           ingestion_status", source)
        self.assertIn("'complete'", source)

    def test_webhook_core_status_commits_when_optional_marketplace_event_columns_are_missing(self):
        class UndefinedColumn(Exception):
            sqlstate = "42703"
            diag = SimpleNamespace(column_name="import_result")

        class Cursor:
            def __init__(self, fail_optional=False):
                self.fail_optional = fail_optional

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, _params=()):
                if self.fail_optional and "import_result=" in str(sql):
                    raise UndefinedColumn("column import_result does not exist")

        class Connection:
            def __init__(self, cursor):
                self._cursor = cursor
                self.committed = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return self._cursor

            def commit(self):
                self.committed = True

        core = Connection(Cursor())
        optional = Connection(Cursor(fail_optional=True))
        with patch.object(supabase_backend, "connect", side_effect=[core, optional]):
            supabase_backend._update_webhook_event_status(
                "webhook-3020",
                "processed",
                shopify_order_id="gid://shopify/Order/3020",
                source_name="Etsy",
                import_result="inserted",
            )

        self.assertTrue(core.committed)
        self.assertFalse(optional.committed)
        self.assertFalse(supabase_backend._ORDER_MARKETPLACE_READ_CAPABILITY)

    def test_webhook_core_status_survives_optional_diagnostic_timeout(self):
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, _sql, _params=()):
                return None

        class Connection:
            def __init__(self):
                self.committed = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return Cursor()

            def commit(self):
                self.committed = True

        core = Connection()
        with patch.object(
            supabase_backend,
            "connect",
            side_effect=[core, RuntimeError("optional diagnostics timed out")],
        ):
            supabase_backend._update_webhook_event_status(
                "webhook-3020",
                "processed",
                shopify_order_id="gid://shopify/Order/3020",
                source_name="Etsy",
                import_result="inserted",
            )

        self.assertTrue(core.committed)

    def test_inflight_webhook_is_retryable_not_acknowledged_as_completed_duplicate(self):
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, _params=()):
                self.sql = str(sql)

            def fetchone(self):
                if "SELECT status" in self.sql:
                    return {"status": "processing", "received_at": datetime.now(timezone.utc)}
                return None

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return Cursor()

            def rollback(self):
                return None

            def commit(self):
                return None

        with patch.object(supabase_backend, "connect", return_value=Connection()):
            with self.assertRaisesRegex(RuntimeError, "already in progress"):
                supabase_backend._claim_webhook_event(
                    "webhook-3020",
                    "orders/paid",
                    paid_marketplace_order(),
                )

    def test_marketplace_migration_is_additive_parseable_and_discovered(self):
        from pglast import parse_sql

        path = Path("migrations/20260818_shopify_marketplace_order_reconciliation.sql")
        sql = path.read_text(encoding="utf-8")

        self.assertGreater(len(parse_sql(sql)), 0)
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertIn(path.name, {candidate.name for candidate in run_migrations.migration_files()})
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())
        self.assertEqual(12, sql.upper().count("ADD COLUMN IF NOT EXISTS"))
        self.assertIn("CREATE INDEX IF NOT EXISTS IDX_SHOPIFY_VARIANTS_SKU_NORMALIZED", sql.upper())
        self.assertNotIn("ALTER TABLE IF EXISTS", sql.upper())

    def test_marketplace_schema_contract_is_optional_and_covers_migration(self):
        migration = Path("migrations/20260818_shopify_marketplace_order_reconciliation.sql").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            ("20260818_shopify_marketplace_order_reconciliation.sql",),
            run_migrations.MARKETPLACE_SCHEMA_MIGRATIONS,
        )
        for table_name, column_name in run_migrations.MARKETPLACE_SCHEMA_COLUMNS:
            self.assertIn(table_name, migration)
            self.assertIn(column_name, migration)
        self.assertIn(
            ("shopify_variants", "idx_shopify_variants_sku_normalized"),
            run_migrations.MARKETPLACE_SCHEMA_INDEXES,
        )

    def test_read_only_deployment_gate_reports_complete_migrated_schema(self):
        class Cursor:
            def __init__(self):
                self.rows = []
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append(str(sql))
                if "to_regclass" in sql:
                    self.rows = [{"table_name": "schema_migrations"}]
                elif "FROM schema_migrations" in sql:
                    self.rows = [{"filename": run_migrations.SHOPIFY_MARKETPLACE_MIGRATION}]
                elif "information_schema.columns" in sql:
                    self.rows = [
                        {
                            "table_name": table,
                            "column_name": column,
                            "data_type": expected[0],
                            "is_nullable": expected[1],
                            "column_default": expected[2] or None,
                        }
                        for (table, column), expected in run_migrations.MARKETPLACE_SCHEMA_COLUMNS.items()
                    ]
                elif "FROM pg_indexes" in sql:
                    self.rows = [
                        {"tablename": table, "indexname": index}
                        for table, index in run_migrations.MARKETPLACE_SCHEMA_INDEXES
                    ]

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        cursor = Cursor()
        self.assertEqual([], run_migrations.marketplace_schema_issues(cursor))
        for statement in cursor.statements:
            upper = statement.upper()
            for token in ("ALTER ", "CREATE ", "INSERT ", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE "):
                self.assertNotIn(token, upper)

    def test_read_only_deployment_gate_names_missing_migration_column_and_index(self):
        class Cursor:
            def __init__(self):
                self.rows = []

            def execute(self, sql, params=()):
                if "to_regclass" in sql:
                    self.rows = [{"table_name": None}]
                else:
                    self.rows = []

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        self.assertEqual([], run_migrations.required_schema_issues(Cursor()))
        issues = run_migrations.marketplace_schema_issues(Cursor())

        self.assertIn(
            "missing migration record: 20260818_shopify_marketplace_order_reconciliation.sql",
            issues,
        )
        self.assertIn("missing column: shopify_orders.source_name", issues)
        self.assertIn("missing column: shopify_order_lines.mapping_method", issues)
        self.assertIn("missing index: idx_shopify_variants_sku_normalized on shopify_variants", issues)

    def test_render_services_do_not_gate_core_shopify_on_optional_marketplace_schema(self):
        render = Path("render.yaml").read_text(encoding="utf-8")

        self.assertIn(
            "preDeployCommand: python run_migrations.py --only "
            "20260828_fix_sparse_legacy_allocator.sql",
            render,
        )
        self.assertNotIn(
            "preDeployCommand: python run_migrations.py --only "
            "20260818_shopify_marketplace_order_reconciliation.sql",
            render,
        )
        self.assertNotIn("startCommand: python sports_cave_server.py", render)
        self.assertIn("startCommand: python webhook_server.py", render)
        self.assertNotIn("--verify-required-schema", render)
        self.assertNotIn("--verify-marketplace-schema", render)
        self.assertNotIn("startCommand: python run_migrations.py --only", render)

    def test_order_queries_request_channel_and_test_flags_without_filtering_channel(self):
        for query in (
            shopify_sync.ORDERS_QUERY,
            shopify_sync.ORDERS_SAFE_QUERY,
            shopify_sync.ORDERS_LIGHT_QUERY,
            shopify_sync.ORDERS_BY_IDS_QUERY,
        ):
            self.assertIn("sourceName", query)
            self.assertIn("test", query)
            self.assertNotIn("sourceName:", query)

    def test_etsy_rest_order_is_normalized_and_eligible_with_attribution(self):
        payload = {
            "id": 3020,
            "name": "#SC3020",
            "financial_status": "paid",
            "fulfillment_status": None,
            "source_name": "etsy",
            "shipping_lines": [{"title": "Australia Post"}],
            "line_items": [
                {
                    "id": 30201,
                    "product_id": 200,
                    "variant_id": 201,
                    "sku": "LIMITED-BLACK-XL",
                    "title": "Limited Wall Art",
                    "variant_title": "Black / XL",
                    "quantity": 1,
                }
            ],
        }

        order = supabase_backend.normalize_rest_order(payload)

        self.assertEqual(order["shopify_order_id"], "gid://shopify/Order/3020")
        self.assertEqual(order["source_name"], "etsy")
        self.assertEqual(order["source_display"], "Etsy")
        self.assertEqual(order["shipping_method"], "Australia Post")
        self.assertEqual(order["line_items"][0]["shopify_variant_id"], "gid://shopify/ProductVariant/201")
        self.assertTrue(supabase_backend.shopify_order_eligibility(order)["eligible"])

    def test_channel_never_changes_business_eligibility(self):
        for source in ("web", "etsy", "pos", "shopify_draft_order", "future_marketplace"):
            order = paid_marketplace_order(source_name=source, source_display=source)
            self.assertTrue(supabase_backend.shopify_order_eligibility(order)["eligible"], source)

        for changes, reason in (
            ({"test": True}, "test_order"),
            ({"cancelled_at": "2026-08-17T14:00:00Z"}, "cancelled_order"),
            ({"financial_status": "PENDING"}, "financial_status_pending"),
        ):
            decision = supabase_backend.shopify_order_eligibility(paid_marketplace_order(**changes))
            self.assertFalse(decision["eligible"])
            self.assertEqual(decision["reason"], reason)

    def test_variant_id_is_the_first_mapping_identity(self):
        product = {
            "id": 7,
            "shopify_product_id": "gid://shopify/Product/200",
            "shopify_handle": "limited-wall-art",
            "product_title": "Limited Wall Art",
            "active": True,
        }
        cursor = MappingCursor(variant_rows=[product], sku_rows=[product])

        result = supabase_backend._resolve_edition_product_for_order_line_with_cursor(
            cursor,
            paid_marketplace_order()["line_items"][0],
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["match_method"], "shopify_variant_id")
        self.assertEqual(len(cursor.statements), 1)

    def test_exact_sku_maps_when_marketplace_variant_id_is_missing(self):
        product = {
            "id": 7,
            "shopify_product_id": "gid://shopify/Product/200",
            "shopify_handle": "limited-wall-art",
            "product_title": "Limited Wall Art",
            "active": True,
        }
        cursor = MappingCursor(sku_rows=[product])
        line = dict(paid_marketplace_order()["line_items"][0])
        line["shopify_variant_id"] = ""
        line["variant_id"] = ""

        result = supabase_backend._resolve_edition_product_for_order_line_with_cursor(cursor, line)

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["match_method"], "sku")
        self.assertEqual(len(cursor.statements), 1)

    def test_ebay_shopify_product_and_variant_ids_win_over_modified_title(self):
        product = {
            "id": 58,
            "shopify_product_id": "gid://shopify/Product/8887274373427",
            "shopify_handle": "muhammad-ali-motivational-art",
            "product_title": "Muhammad Ali Motivational Wall Art",
            "active": True,
        }
        cursor = MappingCursor(variant_rows=[product])
        order = paid_marketplace_order(source_name="ebay-au", source_display="eBay Australia")
        line = {
            "shopify_line_item_id": "gid://shopify/LineItem/17476720886067",
            "shopify_product_id": "gid://shopify/Product/8887274373427",
            "shopify_variant_id": "gid://shopify/ProductVariant/48821710029107",
            "variant_id": "gid://shopify/ProductVariant/48821710029107",
            "product_title": "Marketplace-modified title that must not be matched",
            "product_handle": "wrong-title-derived-handle",
            "sku": "MALIAMOTIVATIONALA4B",
            "quantity": 1,
        }

        result = supabase_backend._resolve_marketplace_product_with_cursor(cursor, order, line)

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["match_method"], "shopify_product_and_variant_gid")
        self.assertEqual(result["product"]["shopify_product_id"], "gid://shopify/Product/8887274373427")
        self.assertEqual(len(cursor.statements), 1)

    def test_unmatched_ebay_title_never_enters_title_or_handle_fallback(self):
        cursor = MappingCursor()
        order = paid_marketplace_order(source_name="eBay Australia", source_display="eBay Australia")
        line = {
            "shopify_line_item_id": "gid://shopify/LineItem/999",
            "product_title": "Shane Warne Tribute Wall Art nearly identical title",
            "product_handle": "shane-warne-framed-art",
            "quantity": 1,
        }

        result = supabase_backend._resolve_marketplace_product_with_cursor(cursor, order, line)

        self.assertEqual(result["status"], "missing")
        self.assertIn("Title and handle fallback matching is disabled", result["reason"])
        sql = "\n".join(statement for statement, _ in cursor.statements)
        self.assertNotIn("ep.shopify_handle", sql)
        self.assertNotIn("normalized_product_title", sql)

    def test_ebay_product_id_with_unknown_variant_requires_exact_sku_or_review(self):
        product = {
            "id": 58,
            "shopify_product_id": "gid://shopify/Product/8887274373427",
            "shopify_handle": "muhammad-ali-motivational-art",
            "product_title": "Muhammad Ali Motivational Wall Art",
            "active": True,
        }
        cursor = MappingCursor(variant_rows=[], sku_rows=[product])
        order = paid_marketplace_order(source_name="ebay-au", source_display="eBay Australia")
        line = {
            "shopify_product_id": "gid://shopify/Product/8887274373427",
            "shopify_variant_id": "gid://shopify/ProductVariant/unknown",
            "variant_id": "gid://shopify/ProductVariant/unknown",
            "sku": "MALIAMOTIVATIONALA4B",
            "product_title": "Unsafe title fallback",
        }

        result = supabase_backend._resolve_marketplace_product_with_cursor(cursor, order, line)

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["product"]["match_method"], "exact_shopify_sku")
        self.assertEqual(len(cursor.statements), 2)

    def test_unmapped_marketplace_item_is_persisted_as_needs_mapping_without_edition(self):
        order = paid_marketplace_order()
        with patch.object(supabase_backend, "_persist_order_snapshot") as persist, patch.object(
            supabase_backend,
            "edition_tracking_start_for_processing",
            return_value=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={"product": {}, "status": "missing", "reason": "No safe match.", "candidates": []},
        ), patch.object(supabase_backend, "_set_order_line_status") as set_status, patch.object(
            supabase_backend, "allocate_edition_line_units_atomic"
        ) as allocate, patch.object(supabase_backend, "connect"), patch.object(
            supabase_backend, "_quarantine_allocation_line"
        ) as quarantine, patch.object(
            supabase_backend, "_set_order_ingestion_outcome"
        ) as outcome:
            result = supabase_backend.process_paid_order(
                order,
                generate_certificates=False,
                sync_product_metafields=False,
                ensure_schema_first=False,
            )

        persist.assert_called_once_with(order)
        allocate.assert_not_called()
        quarantine.assert_called_once()
        self.assertEqual(set_status.call_args.args[2], "Needs product mapping")
        self.assertEqual(set_status.call_args.kwargs["mapping_method"], "unmapped")
        self.assertEqual(result["ingestion_status"], "needs_mapping")
        self.assertEqual(result["missing_mapping_skipped"], 1)
        self.assertEqual(outcome.call_args.kwargs["import_result"], "needs_mapping")

    def test_fulfilment_snapshot_keeps_channel_and_actionable_unmapped_units(self):
        rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [
                {
                    "shopify_order_id": "gid://shopify/Order/3020",
                    "order_name": "#SC3020",
                    "source_name": "Etsy",
                    "customer_name": "Marketplace customer",
                    "shopify_line_item_id": "gid://shopify/LineItem/30201",
                    "product_title": "Limited Wall Art",
                    "variant_title": "Black / XL",
                    "quantity": 2,
                    "assignment_status": "Needs product mapping",
                    "order_raw_json": {
                        "shipping_method": "Australia Post",
                        "shipping_address_summary": "NSW 2000, Australia",
                    },
                    "assignments": [],
                }
            ]
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["channel"] for row in rows}, {"Etsy"})
        self.assertEqual({row["edition"] for row in rows}, {"Needs product mapping"})
        self.assertFalse(any(row["has_saved_allocation"] for row in rows))

    def test_pre_marketplace_order_without_channel_defaults_to_shopify_display_only(self):
        rows = order_allocator._snapshot_rows_from_supabase_order_rows(
            [
                {
                    "shopify_order_id": "gid://shopify/Order/3019",
                    "order_name": "#SC3019",
                    "shopify_line_item_id": "gid://shopify/LineItem/30191",
                    "quantity": 1,
                    "order_raw_json": {},
                    "assignments": [],
                }
            ]
        )

        self.assertEqual("Shopify", rows[0]["channel"])

    def test_targeted_display_name_resolution_uses_exact_match_and_immutable_id(self):
        config = {"store_domain": "sports-cave.myshopify.com"}
        expected = paid_marketplace_order()
        with patch.object(
            shopify_sync,
            "fetch_orders_page",
            return_value={"orders": [expected], "has_next_page": True, "end_cursor": "ignored"},
        ) as fetch_page:
            result = shopify_sync.fetch_order_by_name("SC3020", config=config)

        self.assertEqual(result["shopify_order_id"], "gid://shopify/Order/3020")
        self.assertEqual(fetch_page.call_args.kwargs["page_size"], 10)
        self.assertFalse(fetch_page.call_args.kwargs["default_paid_unfulfilled_filter"])

    def test_targeted_reconciliation_is_dry_run_by_default_and_reports_existing_trace(self):
        order = paid_marketplace_order()
        trace = {"order_stored": False, "webhook_received": False, "stored_line_count": 0}
        with patch.object(shopify_sync, "fetch_order_by_name", return_value=order), patch.object(
            supabase_backend, "get_shopify_order_ingestion_trace", return_value=trace
        ), patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set()), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={
                "product": {"handle": "limited-wall-art", "match_method": "shopify_variant_id"},
                "status": "matched",
                "reason": "matched",
            },
        ), patch.object(supabase_backend, "process_single_paid_shopify_order_for_editions") as process:
            result = supabase_backend.reconcile_single_shopify_order(
                order_name="SC3020",
                apply=False,
                config={"store_domain": "sports-cave.myshopify.com"},
                ensure_schema_first=False,
            )

        process.assert_not_called()
        self.assertEqual(result["shopify_order_id"], "gid://shopify/Order/3020")
        self.assertEqual(result["source_name"], "Etsy")
        self.assertTrue(result["eligible"])
        self.assertFalse(result["applied"])
        self.assertTrue(result["backfill_safe_to_repeat"])
        self.assertEqual(result["trace_before"], trace)

    def test_targeted_apply_uses_immutable_identity_and_idempotent_notification_event(self):
        order = paid_marketplace_order()
        before = {"order_stored": False, "webhook_received": False}
        after = {"order_stored": True, "stored_line_count": 1, "allocated_operational_units": 1}
        with patch.object(shopify_sync, "fetch_orders_by_ids", return_value=[order]) as fetch, patch.object(
            supabase_backend, "get_shopify_order_ingestion_trace", side_effect=[before, after]
        ), patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set()), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={
                "product": {"handle": "limited-wall-art", "match_method": "shopify_variant_id"},
                "status": "matched",
                "reason": "matched",
            },
        ), patch.object(
            supabase_backend,
            "process_single_paid_shopify_order_for_editions",
            return_value={
                "processed": True,
                "new_order_inserted": True,
                "import_result": "inserted_or_updated",
                "ingestion_status": "complete",
                "imported_lines": 1,
                "editions_assigned": 1,
                "assigned_editions": ["edition-1"],
                "errors": [],
            },
        ) as process, patch.object(
            supabase_backend, "record_new_order_notification_events", return_value=1
        ) as notify:
            result = supabase_backend.reconcile_single_shopify_order(
                shopify_order_id="gid://shopify/Order/3020",
                apply=True,
                notify=True,
                config={"store_domain": "sports-cave.myshopify.com"},
                ensure_schema_first=False,
            )

        fetch.assert_called_once_with(["gid://shopify/Order/3020"], config={"store_domain": "sports-cave.myshopify.com"})
        self.assertEqual(process.call_args.args[0]["shopify_order_id"], "gid://shopify/Order/3020")
        notify.assert_called_once_with([order], source="targeted_reconciliation")
        self.assertTrue(result["applied"])
        self.assertEqual(result["new_order_notification_events_created"], 1)
        self.assertEqual(result["trace_after"], after)

    def test_targeted_apply_does_not_notify_historical_repair_by_default(self):
        order = paid_marketplace_order()
        with patch.object(shopify_sync, "fetch_orders_by_ids", return_value=[order]), patch.object(
            supabase_backend,
            "get_shopify_order_ingestion_trace",
            side_effect=[{"order_stored": False}, {"order_stored": True}],
        ), patch.object(supabase_backend, "list_existing_shopify_order_ids", return_value=set()), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={"product": {}, "status": "missing", "reason": "No safe match."},
        ), patch.object(
            supabase_backend,
            "process_single_paid_shopify_order_for_editions",
            return_value={"processed": True, "new_order_inserted": True, "errors": []},
        ), patch.object(supabase_backend, "record_new_order_notification_events") as notify:
            result = supabase_backend.reconcile_single_shopify_order(
                shopify_order_id=order["shopify_order_id"],
                apply=True,
                config={"store_domain": "sports-cave.myshopify.com"},
                ensure_schema_first=False,
            )

        notify.assert_not_called()
        self.assertTrue(result["applied"])
        self.assertFalse(result["notifications_requested"])

    def test_safe_webhook_receipt_does_not_store_customer_pii(self):
        payload = {
            "id": 3020,
            "name": "#SC3020",
            "source_name": "etsy",
            "email": "private@example.com",
            "shipping_address": {"address1": "private"},
            "line_items": [{"id": 1}],
        }
        safe = supabase_backend._safe_webhook_order_payload(payload)

        self.assertEqual(safe["source_name"], "etsy")
        self.assertEqual(safe["line_item_count"], 1)
        self.assertNotIn("email", safe)
        self.assertNotIn("shipping_address", safe)

    def test_background_reconciliation_is_disabled_locally_and_uses_bounded_window_when_run(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SHOPIFY_ORDER_RECONCILIATION_ENABLED", None)
            os.environ.pop("RENDER", None)
            os.environ.pop("RENDER_SERVICE_NAME", None)
            self.assertFalse(shopify_order_reconciliation_worker.enabled())

        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend,
            "sync_latest_paid_orders_to_supabase",
            return_value={"shopify_orders_fetched": 2, "new_orders_inserted": 1},
        ) as sync, patch.object(
            supabase_backend,
            "shopify_order_reconciliation_lease",
            return_value=nullcontext(True),
        ):
            shopify_order_reconciliation_worker.run_once()

        sync.assert_called_once_with(
            limit=50,
            lookback_days=14,
            ensure_schema_first=False,
            allow_unrelated_allocation_duplicates=True,
        )

    def test_targeted_reconciliation_cli_never_runs_schema_maintenance(self):
        source = Path("scripts/reconcile_shopify_order.py").read_text(encoding="utf-8")

        self.assertIn("ensure_schema_first=False", source)

    def test_background_reconciliation_isolates_unrelated_historical_duplicates(self):
        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend,
            "sync_latest_paid_orders_to_supabase",
            return_value={"shopify_orders_fetched": 1, "new_orders_inserted": 1},
        ) as sync, patch.object(
            supabase_backend,
            "shopify_order_reconciliation_lease",
            return_value=nullcontext(True),
        ):
            shopify_order_reconciliation_worker.run_once()

        sync.assert_called_once_with(
            limit=50,
            lookback_days=14,
            ensure_schema_first=False,
            allow_unrelated_allocation_duplicates=True,
        )

    def test_overlapping_background_reconciliation_does_not_fetch_or_advance(self):
        with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
            supabase_backend,
            "shopify_order_reconciliation_lease",
            return_value=nullcontext(False),
        ), patch.object(
            supabase_backend,
            "sync_latest_paid_orders_to_supabase",
        ) as sync:
            result = shopify_order_reconciliation_worker.run_once()

        sync.assert_not_called()
        self.assertEqual(result["status"], "already_running")
        self.assertTrue(result["sync_blocked"])

    def test_reconciliation_lease_is_database_backed_and_crash_safe(self):
        source = inspect.getsource(supabase_backend.shopify_order_reconciliation_lease)

        self.assertIn("pg_try_advisory_xact_lock", source)
        self.assertIn("idle_in_transaction_session_timeout = 0", source)
        self.assertIn("lease_connection.rollback()", source)
        self.assertIn("with connect() as lease_connection", source)


if __name__ == "__main__":
    unittest.main()
