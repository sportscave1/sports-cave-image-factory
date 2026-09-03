import copy
import unittest
from unittest.mock import patch

import edition_ops
import supabase_backend


def _read_row(**overrides):
    row = {
        "id": 715,
        "shopify_product_id": "gid://shopify/Product/715",
        "shopify_product_gid": "gid://shopify/Product/715",
        "shopify_handle": "historical-gap-product",
        "product_title": "Historical Gap Product",
        "edition_total": 100,
        "next_edition_number": 10,
        "active_run_next_edition_number": 10,
        "run_next_edition_number": 10,
        "last_assigned_edition": 9,
        "sold_count": 9,
        "remaining_count": 91,
        "allocation_baseline_sold_count": 9,
        "historical_allocation_count": 5,
        "historical_min_assigned": 1,
        "historical_max_assigned": 9,
        "historical_invalid_number_count": 0,
        "live_duplicate_number_count": 0,
        "next_occupied_count": 0,
        "active_suffix_count": 0,
        "active_suffix_min": 0,
        "active_suffix_max": 0,
        "active_suffix_duplicate_count": 0,
        "active_suffix_invalid_number_count": 0,
        "active_suffix_above_limit_count": 0,
        "active_suffix_identity_mismatch_count": 0,
        "active": True,
        "sold_out": False,
        "run_status": "active",
        "metafields_sync_status": "Synced",
    }
    row.update(overrides)
    return row


class _Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))

    def fetchall(self):
        return copy.deepcopy(self.rows)


class _Connection:
    def __init__(self, rows=()):
        self.cursor_value = _Cursor(rows)
        self.rollback_calls = 0
        self.close_calls = 0

    def cursor(self):
        return self.cursor_value

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


class EditionOpsAllocationIntegrityTests(unittest.TestCase):
    def test_sparse_historical_truth_is_informational_and_immutable(self):
        snapshot = {
            "allocations": [1, 2, 5, 8, 9],
            "product": _read_row(),
        }
        before = copy.deepcopy(snapshot)

        first = supabase_backend.edition_allocation_integrity_from_read_row(
            snapshot["product"]
        )
        second = supabase_backend.edition_allocation_integrity_from_read_row(
            snapshot["product"]
        )

        self.assertEqual(snapshot, before)
        self.assertEqual(snapshot["allocations"], [1, 2, 5, 8, 9])
        self.assertEqual(first, second)
        self.assertTrue(first["historical_allocation_gap"])
        self.assertFalse(first["allocation_blocked"])
        self.assertEqual(first["allocation_integrity_issue"], "")

    def test_historical_gap_does_not_block_free_authoritative_next_number(self):
        result = supabase_backend.edition_allocation_integrity_from_read_row(
            _read_row(next_occupied_count=0)
        )

        self.assertFalse(result["allocation_blocked"])
        visible = edition_ops._row_from_supabase_product(
            {**_read_row(), **result}
        )
        self.assertTrue(visible["edition_enabled"])
        self.assertEqual(visible["edition_next_number"], 10)
        self.assertEqual(visible["edition_sold_count"], 9)
        self.assertEqual(visible["edition_remaining"], 91)
        self.assertEqual(visible["sync_error"], "")

    def test_current_atomic_suffix_uses_stored_sold_boundary_not_legacy_gaps(self):
        healthy = _read_row(
            next_edition_number=13,
            active_run_next_edition_number=13,
            run_next_edition_number=13,
            last_assigned_edition=12,
            sold_count=12,
            remaining_count=88,
            allocation_baseline_sold_count=9,
            historical_allocation_count=8,
            historical_max_assigned=12,
            active_suffix_count=3,
            active_suffix_min=10,
            active_suffix_max=12,
        )
        result = supabase_backend.edition_allocation_integrity_from_read_row(healthy)

        self.assertFalse(result["allocation_blocked"])
        self.assertTrue(result["historical_allocation_gap"])

    def test_real_current_integrity_problems_remain_blocking_and_specific(self):
        cases = {
            "occupied": (
                {"next_occupied_count": 1},
                "already occupied",
            ),
            "duplicate": (
                {"active_suffix_duplicate_count": 1},
                "duplicate edition number",
            ),
            "incompatible_live_duplicate": (
                {"live_duplicate_number_count": 1},
                "two live allocations use the same edition number",
            ),
            "backwards": (
                {
                    "next_edition_number": 9,
                    "active_run_next_edition_number": 9,
                    "run_next_edition_number": 9,
                },
                "behind the authoritative allocation boundary",
            ),
            "suffix_gap": (
                {
                    "next_edition_number": 13,
                    "active_run_next_edition_number": 13,
                    "run_next_edition_number": 13,
                    "last_assigned_edition": 12,
                    "sold_count": 12,
                    "remaining_count": 88,
                    "active_suffix_count": 2,
                    "active_suffix_min": 10,
                    "active_suffix_max": 12,
                },
                "current atomic allocation suffix is not contiguous",
            ),
            "invalid_number": (
                {"historical_invalid_number_count": 1},
                "zero or less",
            ),
            "above_limit": (
                {"active_suffix_above_limit_count": 1},
                "above the product limit",
            ),
            "identity_mismatch": (
                {"active_suffix_identity_mismatch_count": 1},
                "product identity mismatch",
            ),
            "run_pointer_disagreement": (
                {"active_run_next_edition_number": 11, "run_next_edition_number": 11},
                "active run and product disagree",
            ),
        }
        for label, (overrides, expected) in cases.items():
            with self.subTest(label=label):
                result = supabase_backend.edition_allocation_integrity_from_read_row(
                    _read_row(**overrides)
                )
                self.assertTrue(result["allocation_blocked"])
                self.assertIn(expected, result["allocation_integrity_issue"].lower())

    def test_bulk_read_preserves_stored_counters_and_performs_one_select_only(self):
        source = _read_row(
            last_assigned_edition=9,
            sold_count=9,
            remaining_count=93,
        )
        connection = _Connection([source])

        with patch.object(supabase_backend, "connect", return_value=connection):
            rows = supabase_backend.list_edition_products_read_only(limit=10)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["next_edition_number"], 10)
        self.assertEqual(row["last_assigned_edition"], 9)
        self.assertEqual(row["sold_count"], 9)
        self.assertEqual(row["remaining_count"], 93)
        self.assertEqual(row["remaining_editions"], 93)
        self.assertEqual(len(connection.cursor_value.statements), 1)
        sql = connection.cursor_value.statements[0][0]
        upper = sql.upper()
        self.assertNotIn("INSERT INTO", upper)
        self.assertNotIn("UPDATE EDITION_", upper)
        self.assertNotIn("DELETE FROM", upper)
        self.assertNotIn("HT.MIN_ASSIGNED <> 1", upper)
        self.assertIn("ALLOCATION_BASELINE_SOLD_COUNT", upper)
        self.assertIn("IDENTITY_ENFORCED", upper)
        self.assertIn("ACTIVE_SUFFIX_TOTALS", upper)
        self.assertIn("EP.SOLD_COUNT", upper)
        self.assertIn("EP.REMAINING_COUNT", upper)
        self.assertEqual(connection.rollback_calls, 1)
        self.assertEqual(connection.close_calls, 1)
        supabase_backend._discard_cached_read_connection()

    def test_actionable_integrity_issue_replaces_generic_history_warning(self):
        integrity = supabase_backend.edition_allocation_integrity_from_read_row(
            _read_row(next_occupied_count=1)
        )
        visible = edition_ops._row_from_supabase_product(
            {**_read_row(), **integrity}
        )

        self.assertFalse(visible["edition_enabled"])
        self.assertEqual(visible["sync_status"], "needs_reconciliation")
        self.assertIn("#010 is already occupied", visible["sync_error"])
        self.assertNotIn("Non-contiguous allocation history", visible["sync_error"])


if __name__ == "__main__":
    unittest.main()
