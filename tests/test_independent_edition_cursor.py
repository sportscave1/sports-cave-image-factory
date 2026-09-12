import copy
import unittest
from unittest.mock import MagicMock, patch

import edition_ops
import supabase_backend as backend
from scripts.repair_sc3148 import validate_before, validate_allocations
from scripts import repair_sc3148 as repair


class IndependentEditionCursorTests(unittest.TestCase):
    def row(self, **changes):
        return dict(edition_total=100, next_edition_number=52, sold_count=2,
                    remaining_count=98, last_assigned_edition=51,
                    active_run_max_assigned=51, valid_allocation_count=2,
                    first_assigned_edition=50, active=True, run_status="active", **changes)

    def test_manual_override_then_two_units_is_not_blocked(self):
        row = self.row(active_suffix_count=2, active_suffix_min=50, active_suffix_max=51)
        before = copy.deepcopy(row)
        self.assertFalse(backend.edition_allocation_integrity_from_read_row(row)["allocation_blocked"])
        self.assertEqual(row, before)

    def test_mirror_uses_independent_authoritative_values(self):
        result = backend.calculate_product_edition_metafield_values(self.row())
        self.assertEqual((result["next_edition_number"], result["sold_count"], result["remaining_count"]), (52, 2, 98))
        self.assertFalse(result["allocation_blocked"])

    def test_normalization_and_edition_ops_keep_sales(self):
        row = backend._normalize_edition_product_row(self.row())
        self.assertEqual(row["remaining_count"], 98)
        visible = edition_ops._row_from_supabase_product(row)
        self.assertEqual(visible["edition_next_number"], 52)
        self.assertEqual(visible["edition_sold_count"], 2)
        self.assertEqual(visible["edition_remaining"], 98)

    def test_override_without_sales_keeps_next50(self):
        row = self.row()
        row.update(next_edition_number=50, sold_count=0, remaining_count=100,
                   last_assigned_edition=0, active_run_max_assigned=0, valid_allocation_count=0)
        result = backend.calculate_product_edition_metafield_values(row)
        self.assertEqual(result["next_edition_number"], 50)
        self.assertEqual(result["sold_count"], 0)
        self.assertFalse(result["allocation_blocked"])

    def test_disabled_historical_product_stays_archived(self):
        row = self.row()
        row["active"] = False
        normalized = backend._normalize_edition_product_row(row)
        result = backend.calculate_product_edition_metafield_values(normalized)
        self.assertTrue(result["is_archived"])
        self.assertEqual(result["edition_status"], "archived")

    def test_sales_mismatch_and_missing_pointer_fail_closed(self):
        for changes in ({"sold_count": 0}, {"remaining_count": 100}, {"next_edition_number": None}, {"next_edition_number": 51}, {"stored_product_next": 99}):
            row = self.row()
            row.update(changes)
            self.assertTrue(backend.calculate_product_edition_metafield_values(row)["allocation_blocked"])

    def test_scoped_repair_refuses_unverified_records(self):
        with self.assertRaises((ValueError, KeyError)):
            validate_before({}, {}, {}, [], [], [], [], [])
        with self.assertRaises(ValueError):
            validate_allocations([])

    def test_repair_approval_gate_prevents_connections(self):
        with patch.object(backend, "connect") as connect:
            with self.assertRaises(ValueError):
                repair.run("unapproved")
            connect.assert_not_called()

    def test_repair_transaction_failure_rolls_back_and_never_mirrors(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(backend, "connect", return_value=conn), patch.object(repair, "apply", side_effect=ValueError("conflict")), patch.object(backend, "sync_product_edition_metafields") as mirror:
            with self.assertRaises(ValueError):
                repair.run(repair.APPROVAL)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        mirror.assert_not_called()

    def test_mirror_failure_does_not_undo_committed_units(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(backend, "connect", return_value=conn), patch.object(repair, "apply", return_value={"action": "repaired"}), patch.object(backend, "sync_product_edition_metafields", side_effect=RuntimeError("mirror unavailable")):
            with self.assertRaises(RuntimeError):
                repair.run(repair.APPROVAL)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_scoped_repair_accepts_only_audited_state_and_rejects_drift(self):
        product = dict(id=657, shopify_product_gid=repair.PRODUCT_ID, shopify_handle=repair.HANDLE,
                       active_edition_run_id=repair.RUN_ID, next_edition_number=50, sold_count=0,
                       remaining_count=100, edition_total=100, active=True, sold_out=False)
        run = dict(id=repair.RUN_ID, status="active", next_edition_number=50, edition_total=100,
                   allocation_baseline_sold_count=0)
        order = dict(order_name="#SC3148", financial_status="PAID", cancelled_at=None)
        line = dict(shopify_line_item_id=repair.LINE_ID, shopify_product_id=repair.PRODUCT_ID,
                    quantity=2, sku="FSWOA2B", shopify_variant_id=repair.VARIANT_ID)
        adjustment = dict(old_next_edition_number=1, new_next_edition_number=50, source="manual_app")
        args = [product, run, order, [line], [], [], [], [adjustment]]
        validate_before(*args)
        for field, value in {"next_edition_number": 51, "sold_count": 49, "active": False}.items():
            changed = copy.deepcopy(args)
            changed[0][field] = value
            with self.assertRaises(ValueError):
                validate_before(*changed)

        for index in (4, 5, 6):
            changed = copy.deepcopy(args)
            changed[index] = [{"id": "conflict"}]
            with self.assertRaises(ValueError):
                validate_before(*changed)

    def test_finalization_marks_only_sc3148_complete_after_verified_readback(self):
        import order_allocator
        import orders_page
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            "ingestion_status": "complete", "ingestion_reason": ""}
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            {"column_name": key} for key in ("source_name", "ingestion_status", "ingestion_method", "ingestion_result",
                "ingestion_reason", "ingestion_duration_ms", "last_ingested_at", "updated_at")]
        units = [{"edition_number": 50}, {"edition_number": 51}]
        with patch.object(backend, "connect", return_value=conn), \
             patch.object(repair, "apply", return_value={"action": "already_repaired"}), \
             patch.object(backend, "sync_product_edition_metafields", return_value={"source_values": {}, "metafields_after": []}), \
             patch.object(backend, "list_hybrid_order_rows", return_value=[]), \
             patch.object(order_allocator, "_snapshot_rows_from_supabase_order_rows", return_value=units), \
             patch.object(orders_page, "_normalise_row", side_effect=lambda row: row), \
             patch.object(backend, "list_edition_products_read_only", return_value=[]), \
             patch.object(backend, "_set_order_ingestion_outcome") as outcome:
            result = repair.run(repair.APPROVAL)
        self.assertEqual(result["ingestion_status"], "complete")
        self.assertEqual(outcome.call_args.args[0]["shopify_order_id"], repair.ORDER_ID)
        self.assertEqual(outcome.call_args.kwargs["ingestion_status"], "complete")
        conn.commit.assert_called_once()

    def test_finalization_legacy_schema_never_writes_optional_columns(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [{"column_name": "shopify_order_id"}]
        with patch.object(backend, "connect", return_value=conn), patch.object(backend, "_set_order_ingestion_outcome") as outcome:
            self.assertEqual(repair.finalize_ingestion(), "not_applicable_legacy_schema")
        outcome.assert_not_called()
        conn.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
