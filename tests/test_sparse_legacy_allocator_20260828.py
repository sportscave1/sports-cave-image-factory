from pathlib import Path
import inspect
import unittest

import run_migrations
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260828_fix_sparse_legacy_allocator.sql"
REPAIR_SCRIPT = ROOT / "scripts" / "repair_sc3082.py"


class SparseLegacyAllocator20260828Tests(unittest.TestCase):
    def test_migration_changes_only_the_atomic_function(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        prefix = sql.split(
            "CREATE OR REPLACE FUNCTION allocate_edition_line_units_atomic", 1
        )[0]
        self.assertNotIn("CREATE TABLE", sql)
        self.assertNotIn("one_off_edition", sql)
        self.assertNotIn("UPDATE edition_products", prefix)
        self.assertNotIn("UPDATE edition_runs", prefix)
        self.assertNotIn("7379807207731", sql)
        self.assertNotIn("8141604290867", sql)
        self.assertNotIn("lionel-messi", sql)

    def test_sparse_legacy_rows_are_excluded_and_atomic_suffix_stays_strict(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertGreaterEqual(sql.count("AND eo.identity_enforced"), 2)
        self.assertIn(
            "v_expected_baseline := COALESCE(v_product.sold_count, 0) - v_ledger_count",
            sql,
        )
        self.assertIn("v_ledger_min <> v_expected_baseline + 1", sql)
        self.assertIn("v_ledger_max - v_ledger_min + 1 <> v_ledger_count", sql)
        self.assertIn("Atomic edition suffix is not contiguous", sql)
        self.assertIn("p_source_channel NOT IN ('shopify', 'etsy', 'ebay')", sql)
        self.assertIn("Edition limit reached", sql)
        self.assertIn("'was_created', FALSE", sql)

    def test_normal_uniqueness_and_immutability_are_not_weakened(self):
        original = (
            ROOT / "migrations" / "20260825_atomic_edition_allocation_ledger.sql"
        ).read_text(encoding="utf-8")
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("edition_orders_run_edition_uidx", original)
        self.assertNotIn("DROP INDEX", sql)
        self.assertNotIn("DROP CONSTRAINT", sql)
        self.assertNotIn("allocation_valid = FALSE", sql)
        self.assertNotIn("DELETE FROM edition_orders", sql)

    def test_only_reviewed_migration_bytes_bypass_generic_scanner(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertFalse(run_migrations.safe_migration_sql(sql))
        self.assertTrue(run_migrations.reviewed_migration_sql(MIGRATION, sql))
        self.assertTrue(run_migrations.migration_sql_is_allowed(MIGRATION, sql))
        self.assertFalse(
            run_migrations.reviewed_migration_sql(MIGRATION, sql + "\n-- changed")
        )

    def test_sparse_messi_example_calculates_next_52(self):
        values = supabase_backend.calculate_product_edition_metafield_values(
            {
                "edition_total": 100,
                "allocation_baseline_sold_count": 47,
                "first_assigned_edition": 48,
                "last_assigned_edition": 51,
                "valid_allocation_count": 4,
            }
        )
        self.assertFalse(values["allocation_blocked"])
        self.assertEqual(51, values["sold_count"])
        self.assertEqual(49, values["remaining_count"])
        self.assertEqual(52, values["next_edition_number"])

    def test_metafield_readers_use_only_identity_enforced_suffix_rows(self):
        payload_source = inspect.getsource(
            supabase_backend.get_product_edition_metafield_payload
        )
        pending_source = inspect.getsource(
            supabase_backend.pending_allocation_metafield_mirror_handles
        )
        self.assertGreaterEqual(payload_source.count("identity_enforced"), 4)
        self.assertIn("identity_enforced", pending_source)

    def test_repair_script_is_dry_run_default_hash_gated_and_atomic(self):
        source = REPAIR_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--snapshot-sha256", source)
        self.assertIn("--verify-existing", source)
        self.assertIn("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE", source)
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertIn("allocate_edition_line_units_atomic", source)
        self.assertIn("Messi retry was not idempotent", source)
        self.assertIn("cur.rowcount != 1", source)
        self.assertIn("financial_status", source)
        self.assertIn("valid_line_allocation_count", source)
        self.assertIn("line_ledger_row_count", source)
        self.assertNotIn("one_off_edition", source)
        self.assertNotIn("edition_number = 52", source)


if __name__ == "__main__":
    unittest.main()
