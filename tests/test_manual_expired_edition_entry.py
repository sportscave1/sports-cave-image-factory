import inspect
from pathlib import Path
import unittest

import order_allocator
import orders_page
import run_migrations
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_NAME = "20260828_manual_expired_order_line_editions.sql"


def eligible_state(**overrides):
    state = {
        "schema_available": True,
        "line_found": True,
        "expected_source_channel": "shopify",
        "actual_source_channel": "Online Store",
        "shopify_order_id": "gid://shopify/Order/1",
        "shopify_line_item_id": "gid://shopify/LineItem/2",
        "expected_product_gid": "gid://shopify/Product/3",
        "line_product_gid": "gid://shopify/Product/3",
        "canonical_product_gid": "gid://shopify/Product/3",
        "canonical_edition_total": 100,
        "sold_count": 100,
        "remaining_count": 0,
        "next_edition_number": 101,
        "sold_out": True,
        "product_active": False,
        "series_status": "sold_out / limited_release",
        "assignment_status": "Edition disabled",
        "last_error": "Edition limit reached: next 101, requested 1, total 100.",
        "manual_edition_id": "",
        "valid_normal_allocation_count": 0,
        "fulfilled": False,
        "terminal_dispatch_count": 0,
        "certificate_count": 0,
        "edition_product_found": True,
        "edition_product_count": 1,
        "edition_run_found": True,
    }
    state.update(overrides)
    return state


class ManualExpiredEditionEligibilityTests(unittest.TestCase):
    def test_confirmed_sold_out_line_is_eligible(self):
        result = supabase_backend._manual_edition_eligibility_from_state(eligible_state())

        self.assertTrue(result["eligible"])
        self.assertEqual(100, result["canonical_edition_total"])
        self.assertEqual("shopify", result["source_channel"])

    def test_live_available_design_is_not_eligible(self):
        result = supabase_backend._manual_edition_eligibility_from_state(
            eligible_state(
                sold_count=52,
                remaining_count=48,
                next_edition_number=53,
                sold_out=False,
                product_active=True,
                series_status="active / limited_release",
                assignment_status="Error",
                last_error="Allocation error",
            )
        )

        self.assertFalse(result["eligible"])
        self.assertIn("still available", result["reason"])

    def test_mapping_identity_and_database_failures_are_not_eligible(self):
        for error in (
            "Needs product mapping",
            "Canonical product identity mismatch",
            "Atomic suffix is not contiguous",
            "Database corruption detected",
        ):
            with self.subTest(error=error):
                result = supabase_backend._manual_edition_eligibility_from_state(
                    eligible_state(last_error=error)
                )
                self.assertFalse(result["eligible"])
                self.assertIn("normal repair", result["reason"])

    def test_normal_allocation_manual_value_certificate_and_fulfilment_fail_closed(self):
        cases = (
            ({"valid_normal_allocation_count": 1}, "normal edition allocation"),
            ({"manual_edition_id": "saved"}, "already been saved"),
            ({"certificate_count": 1}, "certificate already exists"),
            ({"fulfilled": True}, "already fulfilled"),
            ({"terminal_dispatch_count": 1}, "already fulfilled"),
            (
                {"assignment_status": "Assigned", "last_error": ""},
                "completed assignment state",
            ),
        )
        for updates, reason in cases:
            with self.subTest(updates=updates):
                result = supabase_backend._manual_edition_eligibility_from_state(
                    eligible_state(**updates)
                )
                self.assertFalse(result["eligible"])
                self.assertIn(reason, result["reason"])

    def test_immutable_source_line_and_product_identities_must_all_match(self):
        cases = (
            {"line_found": False},
            {"actual_source_channel": "Etsy"},
            {"line_product_gid": "gid://shopify/Product/99"},
            {"canonical_product_gid": "gid://shopify/Product/99"},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                result = supabase_backend._manual_edition_eligibility_from_state(
                    eligible_state(**updates)
                )
                self.assertFalse(result["eligible"])

    def test_missing_or_duplicate_canonical_design_fails_closed(self):
        for count in (0, 2):
            with self.subTest(count=count):
                result = supabase_backend._manual_edition_eligibility_from_state(
                    eligible_state(edition_product_count=count)
                )
                self.assertFalse(result["eligible"])
                self.assertIn("missing or ambiguous", result["reason"])


class ManualExpiredEditionArchitectureTests(unittest.TestCase):
    def test_migration_is_separate_immutable_audit_storage(self):
        sql = (ROOT / "migrations" / MIGRATION_NAME).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS manual_order_line_editions", sql)
        self.assertIn("UNIQUE (source_channel, external_order_id, external_line_item_id)", sql)
        self.assertIn("BEFORE UPDATE OR DELETE", sql)
        self.assertIn("role='admin'", sql)
        self.assertIn("REVOKE ALL ON TABLE manual_order_line_editions FROM PUBLIC", sql)
        self.assertIn("A valid normal allocation already exists", sql)
        self.assertIn("The canonical edition design is still available", sql)
        self.assertNotIn("allocate_edition_line_units_atomic", sql)
        self.assertNotIn("ALTER TABLE edition_orders", sql)
        self.assertNotIn("UPDATE edition_products", sql)
        self.assertNotIn("UPDATE edition_runs", sql)

    def test_reviewed_migration_hash_is_required_and_current(self):
        path = ROOT / "migrations" / MIGRATION_NAME
        sql = path.read_text(encoding="utf-8")

        self.assertEqual(
            run_migrations.REVIEWED_MIGRATION_SHA256[MIGRATION_NAME],
            __import__("hashlib").sha256(sql.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(run_migrations.migration_sql_is_allowed(path, sql))

    def test_allocator_never_reads_or_writes_manual_table(self):
        allocator_source = inspect.getsource(supabase_backend.allocate_edition_line_units_atomic)
        migration_source = (ROOT / "migrations" / "20260828_fix_sparse_legacy_allocator.sql").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("manual_order_line_editions", allocator_source)
        self.assertNotIn("manual_order_line_editions", migration_source)

    def test_orders_reader_and_certificate_use_manual_only_as_fallback(self):
        reader_source = inspect.getsource(supabase_backend.list_hybrid_order_rows)
        certificate_source = inspect.getsource(
            supabase_backend._manual_order_line_edition_assignment
        )

        self.assertIn("manual_order_line_editions", reader_source)
        self.assertIn("NOT EXISTS", reader_source)
        self.assertIn("valid_normal_line_ids", reader_source)
        self.assertIn("manual_order_line_editions", certificate_source)
        self.assertIn("NOT EXISTS", certificate_source)
        self.assertIn("allocation_valid", certificate_source)

    def test_manual_certificate_identity_includes_the_product_handle(self):
        source = inspect.getsource(supabase_backend._generate_certificate_for_assignment)

        self.assertIn("MANUAL_ORDER_LINE_EDITION_REFERENCE_PREFIX", source)
        self.assertIn('assignment.get("shopify_handle")', source)

    def test_snapshot_preserves_manual_certificate_identity(self):
        raw = {
            "shopify_order_id": "gid://shopify/Order/1",
            "order_name": "#SC1",
            "shopify_line_item_id": "gid://shopify/LineItem/2",
            "shopify_product_id": "gid://shopify/Product/3",
            "product_title": "Expired Wall Art",
            "quantity": 1,
            "assignments": [
                {
                    "edition_order_id": "manual-edition:00000000-0000-0000-0000-000000000001",
                    "edition_number": 100,
                    "edition_total": 100,
                    "allocation_index": 1,
                    "assignment_status": "Assigned",
                    "assignment_source": "manual_expired_edition_display_certificate",
                    "manual_override": True,
                }
            ],
        }

        rows = order_allocator._snapshot_rows_from_supabase_order_rows([raw])

        self.assertEqual(1, len(rows))
        self.assertEqual(100, rows[0]["edition_number"])
        self.assertEqual(
            "manual-edition:00000000-0000-0000-0000-000000000001",
            rows[0]["edition_order_id"],
        )
        self.assertTrue(rows[0]["manual_edition_override"])

    def test_ui_control_is_admin_gated_and_calls_server_eligibility(self):
        source = inspect.getsource(orders_page._render_manual_edition_entry)

        self.assertIn("_developer_mode()", source)
        self.assertIn("_manual_edition_eligibility", source)
        self.assertIn("save_manual_order_line_edition", source)
        self.assertIn("sports_cave_current_user", source)

    def test_incident_script_is_exactly_four_rows_and_never_targets_messi(self):
        source = (
            ROOT / "scripts" / "repair_expired_order_lines_20260828.py"
        ).read_text(encoding="utf-8")

        for line_id in (
            "17486226522419",
            "17483709186355",
            "17483709153587",
            "17481166717235",
        ):
            self.assertIn(line_id, source)
        self.assertNotIn("17487375302963", source)
        self.assertNotIn("7379807207731", source)
        self.assertIn("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE", source)
        self.assertIn("Dry-run snapshot changed", source)
        self.assertIn("Expected four inserts", source)
        self.assertIn("non_target_allocations", source)
        self.assertIn("post_commit_workflow", source)
        self.assertIn("Certificate input did not resolve 100/100", source)
        self.assertIn("INSERT INTO manual_order_line_editions", source)
        self.assertNotIn("INSERT INTO edition_orders", source)
        self.assertNotIn("UPDATE edition_products", source)
        self.assertNotIn("UPDATE edition_runs", source)


if __name__ == "__main__":
    unittest.main()
