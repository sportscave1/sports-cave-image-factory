from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

import supabase_backend
from scripts import repair_allocation_incident_20260825 as incident


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, function_present=True, columns=()):
        self.function_present = function_present
        self.columns = list(columns)
        self.call = 0

    def execute(self, _sql, _params=()):
        self.call += 1

    def fetchone(self):
        return {"function_name": "allocate_edition_line_units_atomic(...)"} if self.function_present else {"function_name": None}

    def fetchall(self):
        return [{"column_name": value} for value in self.columns]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, cursor):
        self.value = cursor

    def cursor(self):
        return self.value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _candidate(order_name, product_gid, title, paid_at):
    suffix = order_name.removeprefix("#SC")
    return {
        "order_name": order_name,
        "shopify_order_id": f"gid://shopify/Order/{suffix}",
        "shopify_line_item_id": suffix,
        "shopify_product_id": product_gid,
        "shopify_handle": "stable-handle",
        "product_title": title,
        "variant_title": "Black / L",
        "sku": f"SKU-{suffix}",
        "quantity": 1,
        "assignment_status": "Error",
        "last_error": "function allocate_edition_line_units_atomic does not exist",
        "paid_at": paid_at,
        "raw_json": {"source_name": "web"},
    }


class AtomicAllocationIncidentRepairTests(unittest.TestCase):
    def test_backend_starts_when_optional_manual_override_module_is_not_deployed(self):
        script = textwrap.dedent(
            """
            import builtins
            import importlib.util
            from pathlib import Path

            original_import = builtins.__import__

            def without_manual_override(name, *args, **kwargs):
                if name == "order_line_edition_override":
                    error = ModuleNotFoundError("optional manual override is absent")
                    error.name = name
                    raise error
                return original_import(name, *args, **kwargs)

            builtins.__import__ = without_manual_override
            path = Path("supabase_backend.py").resolve()
            spec = importlib.util.spec_from_file_location("backend_without_override", path)
            backend = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(backend)
            assignment = backend._effective_assignment({"edition_number": 10})
            assert assignment["edition_number"] == 10
            assert assignment["manual_edition_override"] is False
            assert backend._manual_override_fulfillment_status_is_locked("fulfilled")
            try:
                backend._manual_override_dependency_required()
            except RuntimeError as error:
                assert "not deployed" in str(error)
            else:
                raise AssertionError("override-only calls must fail closed")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_atomic_rpc_and_columns_are_reported_before_allocation(self):
        cursor = _Cursor(function_present=False, columns=("source_channel",))
        with patch.object(supabase_backend, "connect", return_value=_Connection(cursor)):
            capability = supabase_backend.atomic_edition_allocation_capability()
        self.assertFalse(capability["ready"])
        self.assertFalse(capability["function_present"])
        self.assertIn("external_order_id", capability["missing_columns"])

    def test_complete_atomic_capability_is_ready(self):
        cursor = _Cursor(
            function_present=True,
            columns=sorted(supabase_backend.ATOMIC_EDITION_LEDGER_REQUIRED_COLUMNS),
        )
        with patch.object(supabase_backend, "connect", return_value=_Connection(cursor)):
            capability = supabase_backend.atomic_edition_allocation_capability()
        self.assertTrue(capability["ready"])
        self.assertEqual(capability["missing_columns"], [])

    def test_incident_dry_run_uses_authoritative_product_sequences(self):
        candidates = [
            _candidate("#SC3060", "gid://shopify/Product/8116473790771", "Shane Warne Tribute Wall Art", "2026-08-25T07:34:29Z"),
            _candidate("#SC3061", "gid://shopify/Product/10180244439347", "Legends Never Die Kobe vs Jordan Wall Art", "2026-08-25T13:35:33Z"),
            _candidate("#SC3062", "gid://shopify/Product/10180244439347", "Legends Never Die Kobe vs Jordan Wall Art", "2026-08-25T14:05:44Z"),
            _candidate("#SC3063", "gid://shopify/Product/10155674403123", "All Rise Aaron Judge Wall Art", "2026-08-25T17:40:12Z"),
            _candidate("#SC3064", "gid://shopify/Product/10155674403123", "All Rise Aaron Judge Wall Art", "2026-08-25T18:53:34Z"),
        ]
        states = {
            "gid://shopify/Product/8116473790771": {
                "product_title": "Shane Warne Tribute Wall Art", "edition_total": 100,
                "sold_count": 9, "remaining_count": 91, "last_assigned_edition": 9,
                "next_edition_number": 10, "baseline": 0,
            },
            "gid://shopify/Product/10180244439347": {
                "product_title": "Legends Never Die Kobe vs Jordan Wall Art", "edition_total": 100,
                "sold_count": 46, "remaining_count": 54, "last_assigned_edition": 46,
                "next_edition_number": 47, "baseline": 39,
            },
            "gid://shopify/Product/10155674403123": {
                "product_title": "All Rise Aaron Judge Wall Art", "edition_total": 100,
                "sold_count": 79, "remaining_count": 21, "last_assigned_edition": 79,
                "next_edition_number": 80, "baseline": 74,
            },
        }
        with patch.object(incident, "_active_product_state", side_effect=lambda _cur, gid: states[gid]):
            plan = incident.build_plan(object(), candidates)
        self.assertEqual(
            [(row["order_name"], row["edition_numbers"]) for row in plan["orders"]],
            [
                ("#SC3060", [10]),
                ("#SC3061", [47]),
                ("#SC3062", [48]),
                ("#SC3063", [80]),
                ("#SC3064", [81]),
            ],
        )
        self.assertEqual(plan["products"]["gid://shopify/Product/8116473790771"]["after"]["next"], 11)
        self.assertEqual(plan["products"]["gid://shopify/Product/10180244439347"]["after"]["next"], 49)
        self.assertEqual(plan["products"]["gid://shopify/Product/10155674403123"]["after"]["next"], 82)

    def test_incident_scope_refuses_missing_or_unexpected_orders(self):
        candidate = _candidate(
            "#SC3060",
            "gid://shopify/Product/8116473790771",
            "Shane Warne Tribute Wall Art",
            "2026-08-25T07:34:29Z",
        )
        with self.assertRaisesRegex(RuntimeError, "Incident scope mismatch"):
            incident.build_plan(object(), [candidate])

    def test_compatible_migration_is_run_scoped_and_preserves_legacy_duplicates(self):
        sql = (ROOT / "migrations" / "20260825_atomic_edition_allocation_ledger.sql").read_text(encoding="utf-8")
        self.assertIn("identity_enforced BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("WHERE identity_enforced AND allocation_valid", sql)
        self.assertIn("edition_orders_run_edition_uidx", sql)
        self.assertIn("allocation_baseline_sold_count", sql)
        self.assertIn("WHERE eo.edition_run_id = v_run.id", sql)
        self.assertNotIn("WHERE eo.shopify_product_gid = p_shopify_product_gid\n      AND eo.allocation_valid", sql)
        self.assertIn("COALESCE(so.raw_json->>'source_name', '')", sql)

    def test_repair_script_is_dry_run_by_default_and_hash_gated_for_apply(self):
        source = (ROOT / "scripts" / "repair_allocation_incident_20260825.py").read_text(encoding="utf-8")
        self.assertIn("--snapshot-sha256", source)
        self.assertIn("edition_allocation_incident_backups", source)
        self.assertIn("Snapshot SHA confirmation did not match", source)
        self.assertIn("generate_certificate_for_edition_order", source)
        self.assertIn("sync_order_certificate_metafields", source)
        self.assertIn("certificate_r2_bucket", source)

    def test_storefront_values_use_the_active_run_opening_floor(self):
        values = supabase_backend.calculate_product_edition_metafield_values(
            {
                "edition_total": 100,
                "allocation_baseline_sold_count": 74,
                "first_assigned_edition": 75,
                "last_assigned_edition": 81,
                "valid_allocation_count": 7,
            }
        )
        self.assertFalse(values["allocation_blocked"])
        self.assertEqual(values["sold_count"], 81)
        self.assertEqual(values["remaining_count"], 19)
        self.assertEqual(values["last_assigned_edition"], 81)
        self.assertEqual(values["next_edition_number"], 82)

    def test_storefront_values_reject_a_gap_inside_the_active_run(self):
        values = supabase_backend.calculate_product_edition_metafield_values(
            {
                "edition_total": 100,
                "allocation_baseline_sold_count": 39,
                "first_assigned_edition": 40,
                "last_assigned_edition": 48,
                "valid_allocation_count": 8,
            }
        )
        self.assertTrue(values["allocation_blocked"])


if __name__ == "__main__":
    unittest.main()
