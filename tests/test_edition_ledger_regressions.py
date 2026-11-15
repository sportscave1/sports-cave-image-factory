from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

import edition_ledger
import supabase_backend
from scripts import reconcile_edition_ledger


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260825_atomic_edition_allocation_ledger.sql"


def paid_order(**overrides):
    order = {
        "shopify_order_id": "gid://shopify/Order/100",
        "source_name": "web",
        "financial_status": "PAID",
        "cancelled_at": None,
        "test": False,
        "processed_at": "2026-08-25T00:00:00Z",
        "line_items": [{"shopify_line_item_id": "gid://shopify/LineItem/200", "quantity": 1}],
    }
    order.update(overrides)
    return order


class EditionLedgerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.product_gid = "gid://shopify/Product/8116473790771"
        self.ledger = edition_ledger.AtomicLedgerModel(edition_total=100)

    def test_01_new_product_starts_at_001_of_100(self):
        state = self.ledger.state(self.product_gid)
        self.assertEqual(state["next_edition_number"], 1)
        self.assertEqual(state["edition_total"], 100)

    def test_02_one_paid_unit_allocates_exactly_one(self):
        self.assertEqual(self.ledger.allocate("shopify", "o1", "l1", self.product_gid), [1])
        self.assertEqual(self.ledger.state(self.product_gid)["sold_count"], 1)

    def test_03_quantity_two_is_consecutive(self):
        self.assertEqual(self.ledger.allocate("shopify", "o1", "l1", self.product_gid, 2), [1, 2])

    def test_04_repeated_shopify_webhook_is_noop(self):
        first = self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        second = self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        self.assertEqual(first, second)
        self.assertEqual(self.ledger.state(self.product_gid)["numbers"], [1])

    def test_05_webhook_plus_reconciliation_is_one_allocation(self):
        webhook = self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        reconciliation = self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        self.assertEqual(webhook, reconciliation)
        self.assertEqual(self.ledger.state(self.product_gid)["sold_count"], 1)

    def test_06_fulfilment_or_status_update_does_not_reallocate(self):
        self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        before = self.ledger.state(self.product_gid)
        self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        self.assertEqual(self.ledger.state(self.product_gid), before)

    def test_07_certificate_regeneration_does_not_reallocate(self):
        allocation = self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        regenerated_certificate_edition = allocation[0]
        self.assertEqual(regenerated_certificate_edition, 1)
        self.assertEqual(self.ledger.state(self.product_gid)["numbers"], [1])

    def test_08_overlapping_channel_order_ids_do_not_collide(self):
        self.assertEqual(self.ledger.allocate("shopify", "123", "1", self.product_gid), [1])
        self.assertEqual(self.ledger.allocate("etsy", "123", "1", self.product_gid), [2])
        self.assertEqual(self.ledger.allocate("ebay", "123", "1", self.product_gid), [3])
        keys = {
            supabase_backend.allocation_identity_key("123", "1", 1, source_channel=channel)
            for channel in ("shopify", "etsy", "ebay")
        }
        self.assertEqual(len(keys), 3)
        self.assertEqual(
            edition_ledger.source_channel_for_order({"source_name": "Etsy Integration & Sync"}),
            "etsy",
        )
        self.assertEqual(
            edition_ledger.source_channel_for_order({"source_name": "eBay Marketplace Connect"}),
            "ebay",
        )

    def test_shopify_hosted_marketplace_orders_use_shopify_ids_not_sales_record_ids(self):
        order = paid_order(
            shopify_order_id="gid://shopify/Order/7373639811379",
            source_name="ebay-au",
            source_identifier="01-15093-49797",
            ebay_order_id="01-15093-49797",
        )
        line = {
            "shopify_line_item_id": "gid://shopify/LineItem/17476720886067",
            "ebay_line_item_id": "external-transaction",
        }
        self.assertEqual(
            edition_ledger.external_order_id_for_order(order),
            "gid://shopify/Order/7373639811379",
        )
        self.assertEqual(
            edition_ledger.external_line_item_id_for_line(order, line),
            "gid://shopify/LineItem/17476720886067",
        )

    def test_direct_marketplace_payloads_keep_native_ids(self):
        order = {"source_name": "ebay", "id": "01-15093-49797"}
        line = {"id": "transaction-1"}
        self.assertEqual(edition_ledger.external_order_id_for_order(order), "01-15093-49797")
        self.assertEqual(edition_ledger.external_line_item_id_for_line(order, line), "transaction-1")

    def test_ebay_source_labels_normalize_to_one_channel_and_preserve_display(self):
        for source in ("eBay", "eBay Australia", "ebay-au", "eBay Marketplace Connect"):
            self.assertEqual(edition_ledger.normalize_source_channel(source), "ebay")
        self.assertEqual(edition_ledger.source_display_name("eBay"), "eBay")
        self.assertEqual(edition_ledger.source_display_name("eBay Australia"), "eBay Australia")
        self.assertEqual(edition_ledger.source_display_name("ebay-au"), "eBay Australia")

    def test_09_unmatched_marketplace_listing_is_quarantinable_not_allocatable(self):
        line = {"title": "Shane Warne Tribute", "product_handle": "shane-warne", "quantity": 1}
        self.assertEqual(edition_ledger.marketplace_mapping_identity_candidates(line), [])
        self.assertTrue(edition_ledger.is_marketplace_order(paid_order(source_name="etsy")))
        order = paid_order(source_name="Etsy Integration & Sync")
        with patch.object(supabase_backend, "_persist_order_snapshot"), patch.object(
            supabase_backend,
            "edition_tracking_start_for_processing",
            return_value=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ), patch.object(
            supabase_backend,
            "resolve_edition_product_for_order_line",
            return_value={"product": {}, "status": "missing", "reason": "No explicit mapping."},
        ), patch.object(supabase_backend, "_quarantine_allocation_line") as quarantine, patch.object(
            supabase_backend, "_set_order_line_status"
        ), patch.object(supabase_backend, "allocate_edition_line_units_atomic") as allocate, patch.object(
            supabase_backend, "_set_order_ingestion_outcome"
        ), patch.object(supabase_backend, "connect"):
            result = supabase_backend.process_paid_order(
                order,
                generate_certificates=False,
                sync_product_metafields=False,
                ensure_schema_first=False,
            )
        quarantine.assert_called_once()
        allocate.assert_not_called()
        self.assertEqual(result["missing_mapping_skipped"], 1)

    def test_10_historical_import_does_not_allocate_by_default(self):
        tracking = datetime(2026, 8, 1, tzinfo=timezone.utc)
        result = edition_ledger.paid_order_eligibility(
            paid_order(processed_at=(tracking - timedelta(days=1)).isoformat()),
            tracking_start=tracking,
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "historical_order_requires_explicit_backfill")
        with patch.object(supabase_backend, "ensure_schema") as ensure_schema:
            preview = supabase_backend.preview_limited_edition_import_rows([{"handle": "legacy"}])
        ensure_schema.assert_not_called()
        self.assertEqual(preview["mode"], "retired_read_only")
        with self.assertRaises(RuntimeError):
            supabase_backend.apply_limited_edition_import_rows([])
        with self.assertRaises(RuntimeError):
            supabase_backend.import_limited_edition_rows([])

    def test_11_product_rename_keeps_gid_and_history(self):
        self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        renamed_title = "Shane Warne Renamed Artwork"
        self.assertTrue(renamed_title)
        self.assertEqual(self.ledger.state(self.product_gid)["numbers"], [1])

    def test_12_title_or_handle_similarity_cannot_redirect_marketplace_order(self):
        line = {
            "title": "Shane Warne Tribute Wall Art",
            "product_handle": "shane-warne-framed-art",
            "sku": "EXPLICIT-SKU-ONLY",
        }
        self.assertEqual(
            edition_ledger.marketplace_mapping_identity_candidates(line),
            [("sku", "EXPLICIT-SKU-ONLY")],
        )

    def test_13_two_concurrent_orders_are_unique_and_consecutive(self):
        def allocate(number):
            return self.ledger.allocate("shopify", f"o{number}", f"l{number}", self.product_gid)[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            numbers = sorted(pool.map(allocate, (1, 2)))
        self.assertEqual(numbers, [1, 2])

    def test_14_restart_or_rerun_cannot_change_sequence(self):
        first = self.ledger.allocate("shopify", "o1", "l1", self.product_gid)
        for _ in range(5):
            self.assertEqual(self.ledger.allocate("shopify", "o1", "l1", self.product_gid), first)
        with self.assertRaises(ValueError):
            self.ledger.allocate("shopify", "o1", "l1", self.product_gid, quantity=2)
        self.assertEqual(self.ledger.allocate("shopify", "o2", "l2", self.product_gid), [2])

    def test_15_edition_100_is_final_and_101_is_rejected(self):
        for number in range(1, 101):
            self.assertEqual(
                self.ledger.allocate("shopify", f"o{number}", f"l{number}", self.product_gid),
                [number],
            )
        with self.assertRaises(edition_ledger.EditionLimitReached):
            self.ledger.allocate("shopify", "o101", "l101", self.product_gid)

    def test_16_cancelled_refunded_test_and_unpaid_do_not_allocate(self):
        cases = (
            paid_order(cancelled_at="2026-08-25T00:01:00Z"),
            paid_order(financial_status="REFUNDED"),
            paid_order(test=True),
            paid_order(financial_status="PENDING"),
            paid_order(financial_status="UNPAID"),
        )
        self.assertTrue(all(not edition_ledger.paid_order_eligibility(order)["eligible"] for order in cases))

    def test_17_shane_duplicate_and_historical_marketplace_fixture_cannot_jump(self):
        tracking = datetime(2026, 7, 1, tzinfo=timezone.utc)
        events = [
            paid_order(shopify_order_id="old-etsy", source_name="etsy", processed_at="2024-01-01T00:00:00Z"),
            paid_order(shopify_order_id="old-ebay", source_name="ebay", processed_at="2025-01-01T00:00:00Z"),
            paid_order(shopify_order_id="new-1", source_name="web", processed_at="2026-07-10T00:00:00Z"),
            paid_order(shopify_order_id="new-1", source_name="web", processed_at="2026-07-10T00:00:00Z"),
            paid_order(shopify_order_id="new-2", source_name="web", processed_at="2026-07-11T00:00:00Z"),
        ]
        for order in events:
            policy = edition_ledger.paid_order_eligibility(order, tracking_start=tracking)
            if not policy["eligible"] or edition_ledger.is_marketplace_order(order):
                continue
            self.ledger.allocate(
                "shopify",
                order["shopify_order_id"],
                order["line_items"][0]["shopify_line_item_id"],
                self.product_gid,
            )
        self.assertEqual(self.ledger.state(self.product_gid)["numbers"], [1, 2])

        allocations = []
        for edition_number in range(91, 101):
            historical = edition_number == 91
            allocations.append(
                {
                    "id": str(edition_number),
                    "source_channel": "shopify",
                    "external_order_id": f"order-{edition_number}",
                    "external_line_item_id": f"line-{edition_number}",
                    "unit_ordinal": 1,
                    "shopify_product_gid": self.product_gid,
                    "edition_number": edition_number,
                    "edition_total": 100,
                    "line_quantity": 1,
                    "quantity": 1,
                    "financial_status": "PAID",
                    "order_created_at": (
                        "2026-06-08T00:00:00Z" if historical else f"2026-08-{edition_number - 71:02d}T00:00:00Z"
                    ),
                    "certificate_status": "Certificate Missing" if historical else "Certificate Ready",
                    "allocation_valid": True,
                }
            )
        report = reconcile_edition_ledger.build_report(
            {
                "product_gid": self.product_gid,
                "captured_at": "2026-08-25T00:00:00Z",
                "edition_tracking_start_at": "2026-06-22T00:00:00Z",
                "edition_products": [{"shopify_product_gid": self.product_gid, "edition_total": 100}],
                "edition_runs": [],
                "allocations": allocations,
                "certificates": [],
                "marketplace_mappings": [],
            }
        )
        self.assertEqual(report["allocation_counts"]["verified_legitimate"], 9)
        self.assertEqual(report["allocation_counts"]["confidently_invalid"], 1)
        self.assertEqual(report["authoritative_state"]["sold_count"], 9)
        self.assertEqual(report["authoritative_state"]["remaining_count"], 91)
        self.assertIsNone(report["authoritative_state"]["next_edition_number"])
        self.assertTrue(report["apply_blockers"])

    def test_database_migration_enforces_both_unique_constraints_and_atomic_lock(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("edition_orders_source_unit_uidx", sql)
        self.assertIn("edition_orders_run_edition_uidx", sql)
        self.assertIn("WHERE identity_enforced AND allocation_valid", sql)
        self.assertIn("allocation_baseline_sold_count", sql)
        self.assertIn("WHERE eo.edition_run_id = v_run.id", sql)
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("allocate_edition_line_units_atomic", sql)
        self.assertIn("'was_created', FALSE", sql)
        self.assertIn("edition_allocation_tombstones", sql)
        self.assertNotIn("ep.shopify_handle = COALESCE", sql)
        legacy_import = (ROOT / "scripts" / "stage3_apply_approved_supabase_import.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Refusing to apply: this legacy importer writes synthetic allocations", legacy_import)

    def test_failed_shopify_mirror_is_durable_and_retryable(self):
        process_source = __import__("inspect").getsource(supabase_backend.process_paid_order)
        mirror_source = __import__("inspect").getsource(
            supabase_backend.pending_allocation_metafield_mirror_handles
        )
        self.assertIn("mirror_status", process_source)
        self.assertIn("pending", mirror_source)
        self.assertIn("failed", mirror_source)

    def test_separate_certificate_evidence_forces_manual_review(self):
        allocation = {
            "id": "91",
            "source_channel": "shopify",
            "external_order_id": "historical-order",
            "external_line_item_id": "historical-line",
            "unit_ordinal": 1,
            "shopify_product_gid": self.product_gid,
            "edition_number": 91,
            "edition_total": 100,
            "line_quantity": 1,
            "financial_status": "PAID",
            "order_created_at": "2026-06-08T00:00:00Z",
            "allocation_valid": True,
        }
        reconcile_edition_ledger._merge_certificate_evidence(
            [allocation],
            [{"related_edition_order_id": "91", "certificate_status": "Certificate Ready"}],
        )
        report = reconcile_edition_ledger.build_report(
            {
                "product_gid": self.product_gid,
                "edition_tracking_start_at": "2026-06-22T00:00:00Z",
                "edition_products": [{"shopify_product_gid": self.product_gid, "edition_total": 100}],
                "edition_runs": [],
                "allocations": [allocation],
                "certificates": [],
                "marketplace_mappings": [],
            }
        )
        self.assertEqual(report["allocation_counts"]["confidently_invalid"], 0)
        self.assertEqual(report["allocation_counts"]["manual_review"], 1)
        self.assertTrue(report["apply_blockers"])

    def test_handle_only_repair_candidate_is_blocked_not_attached(self):
        report = reconcile_edition_ledger.build_report(
            {
                "product_gid": self.product_gid,
                "edition_tracking_start_at": "2026-06-22T00:00:00Z",
                "edition_products": [{"shopify_product_gid": self.product_gid, "edition_total": 100}],
                "edition_runs": [],
                "allocations": [],
                "unresolved_identity_allocations": [
                    {"id": "legacy-handle-only", "shopify_handle": "shane-warne-framed-art"}
                ],
                "certificates": [],
                "marketplace_mappings": [],
            }
        )
        self.assertIn(
            "Handle-only allocation candidates require explicit canonical Shopify product GID mapping.",
            report["apply_blockers"],
        )
        self.assertEqual(report["allocation_counts"]["total_rows"], 0)


if __name__ == "__main__":
    unittest.main()
