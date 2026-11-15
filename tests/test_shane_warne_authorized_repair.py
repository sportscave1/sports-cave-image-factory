import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import incident_repair
from scripts import repair_shane_warne_editions
from scripts import recover_sc3058


class ShaneWarneAuthorizedRepairTests(unittest.TestCase):
    def build_snapshot(self):
        orders = []
        lines = []
        allocations = []
        for target in incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE:
            orders.append(
                {
                    "shopify_order_id": target["order_gid"],
                    "order_name": target["order_name"],
                    "financial_status": "PAID",
                    "cancelled_at": None,
                    "test": False,
                }
            )
            lines.append(
                {
                    "shopify_order_id": target["order_gid"],
                    "shopify_line_item_id": target["line_gid"],
                    "shopify_product_id": incident_repair.SHANE_WARNE_PRODUCT_GID,
                    "quantity": 1,
                }
            )
            if target["edition_number"] <= 7:
                allocations.append(
                    {
                        "id": f"edition-{target['edition_number']}",
                        "source_channel": "shopify",
                        "external_order_id": target["order_gid"],
                        "external_line_item_id": target["line_gid"],
                        "shopify_order_id": target["order_gid"],
                        "shopify_order_name": target["order_name"],
                        "shopify_line_item_id": target["line_gid"],
                        "shopify_product_gid": incident_repair.SHANE_WARNE_PRODUCT_GID,
                        "edition_run_id": "active-run",
                        "edition_number": 93 + target["edition_number"],
                        "edition_total": 100,
                        "quantity": 1,
                        "financial_status": "PAID",
                        "allocation_valid": True,
                    }
                )
        michael = {
            "id": "michael-jordan-91",
            "shopify_order_id": "gid://shopify/Order/7372755468595",
            "shopify_order_name": "#SC3056",
            "shopify_line_item_id": incident_repair.MICHAEL_JORDAN_SC3056_LINE_GID,
            "shopify_product_gid": "gid://shopify/Product/8452870799667",
            "edition_number": 91,
            "edition_total": 100,
            "allocation_valid": True,
        }
        allocations.append(michael)
        return {
            "edition_products": [
                {
                    "id": "shane-product",
                    "shopify_product_gid": incident_repair.SHANE_WARNE_PRODUCT_GID,
                    "active_edition_run_id": "active-run",
                    "edition_total": 100,
                }
            ],
            "edition_runs": [
                {
                    "id": "active-run",
                    "edition_product_id": "shane-product",
                    "status": "active",
                    "edition_total": 100,
                }
            ],
            "orders": orders,
            "order_lines": lines,
            "allocations": allocations,
        }

    def test_explicit_sequence_repairs_3055_and_3056_without_touching_michael_jordan(self):
        report = incident_repair.build_shane_warne_authorised_plan(self.build_snapshot())

        self.assertEqual(report["apply_blockers"], [])
        changes = {change["order_name"]: change for change in report["changes"]}
        self.assertEqual(changes["#SC3047"]["after_edition_number"], 6)
        self.assertEqual(changes["#SC3050"]["after_edition_number"], 7)
        self.assertEqual(changes["#SC3055"]["operation"], "insert")
        self.assertEqual(changes["#SC3055"]["after_edition_number"], 8)
        self.assertEqual(changes["#SC3056"]["operation"], "insert")
        self.assertEqual(changes["#SC3056"]["after_edition_number"], 9)
        self.assertEqual(report["michael_jordan_sc3056"]["row_count"], 1)
        self.assertEqual(report["michael_jordan_sc3056"]["proposed_changes"], 0)
        self.assertEqual(report["authoritative_active_state"]["numbers"], list(range(1, 10)))
        self.assertEqual(report["authoritative_active_state"]["sold_count"], 9)
        self.assertEqual(report["authoritative_active_state"]["remaining_count"], 91)
        self.assertEqual(report["authoritative_active_state"]["next_edition_number"], 10)

    def test_paid_allocation_outside_authorized_nine_blocks_apply(self):
        snapshot = self.build_snapshot()
        snapshot["allocations"].append(
            {
                "id": "unexpected-paid-row",
                "shopify_order_id": "gid://shopify/Order/7260692316467",
                "shopify_order_name": "#SC2905",
                "shopify_line_item_id": "gid://shopify/LineItem/17287645167923",
                "shopify_product_gid": incident_repair.SHANE_WARNE_PRODUCT_GID,
                "edition_run_id": "active-run",
                "edition_number": 92,
                "allocation_valid": True,
                "certificate_status": "Certificate Ready",
            }
        )

        report = incident_repair.build_shane_warne_authorised_plan(snapshot)

        self.assertTrue(any("#SC2905" in blocker for blocker in report["apply_blockers"]))

    def test_invalid_historical_rows_are_preserved_as_audit_evidence_not_deleted(self):
        snapshot = self.build_snapshot()
        snapshot["allocations"].append(
            {
                "id": "historical-91",
                "shopify_order_id": "gid://shopify/Order/7201680720179",
                "shopify_order_name": "#SC2762",
                "shopify_line_item_id": "gid://shopify/LineItem/17183921471795",
                "shopify_product_gid": incident_repair.SHANE_WARNE_PRODUCT_GID,
                "edition_run_id": "active-run",
                "edition_number": 91,
                "allocation_valid": False,
                "invalidation_reason": "historical order replay",
            }
        )

        report = incident_repair.build_shane_warne_authorised_plan(snapshot)

        self.assertEqual(report["apply_blockers"], [])
        self.assertEqual(report["preserved_outside_active_sequence"][0]["order_name"], "#SC2762")
        self.assertFalse(any(change.get("order_name") == "#SC2762" for change in report["changes"]))

    def test_failed_or_ambiguous_target_evidence_blocks_writes(self):
        snapshot = self.build_snapshot()
        target = incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE[-1]
        snapshot["orders"] = [
            {**order, "financial_status": "REFUNDED"}
            if order["shopify_order_id"] == target["order_gid"]
            else order
            for order in snapshot["orders"]
        ]

        report = incident_repair.build_shane_warne_authorised_plan(snapshot)

        self.assertTrue(any("#SC3056 is not a verified paid unit" in blocker for blocker in report["apply_blockers"]))

    def test_repair_cli_is_dry_run_by_default_and_apply_is_hash_bound(self):
        args = repair_shane_warne_editions.build_parser().parse_args([])
        self.assertFalse(args.apply)
        self.assertFalse(args.sync_shopify)
        self.assertFalse(args.regenerate_certificates)

        report = incident_repair.build_shane_warne_authorised_plan(self.build_snapshot())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(__import__("json").dumps(report), encoding="utf-8")
            with self.assertRaises(ValueError):
                repair_shane_warne_editions.apply_report(path, "wrong-hash")

    def test_second_apply_of_already_consistent_report_performs_zero_writes(self):
        snapshot = self.build_snapshot()
        for target in incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE[-2:]:
            snapshot["allocations"].append(
                {
                    "id": f"edition-{target['edition_number']}",
                    "source_channel": "etsy" if target["order_name"] == "#SC3055" else "shopify",
                    "external_order_id": target["order_gid"],
                    "external_line_item_id": target["line_gid"],
                    "shopify_order_id": target["order_gid"],
                    "shopify_order_name": target["order_name"],
                    "shopify_line_item_id": target["line_gid"],
                    "shopify_product_gid": incident_repair.SHANE_WARNE_PRODUCT_GID,
                    "edition_run_id": "active-run",
                    "edition_number": target["edition_number"],
                    "edition_total": 100,
                    "quantity": 1,
                    "allocation_valid": True,
                }
            )
        for allocation in snapshot["allocations"]:
            target = next(
                (
                    target
                    for target in incident_repair.SHANE_WARNE_AUTHORISED_SEQUENCE
                    if target["line_gid"] == allocation.get("shopify_line_item_id")
                ),
                None,
            )
            if target:
                allocation["edition_number"] = target["edition_number"]
        report = incident_repair.build_shane_warne_authorised_plan(snapshot)
        self.assertTrue(all(change["operation"] == "no_op" for change in report["changes"]))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(__import__("json").dumps(report), encoding="utf-8")
            with patch.object(repair_shane_warne_editions, "fetch_snapshot") as fetch:
                result = repair_shane_warne_editions.apply_report(path, report["report_sha256"])
        fetch.assert_not_called()
        self.assertEqual(result, {"applied": False, "already_consistent": True, "writes": 0})


class Sc3058RecoveryTests(unittest.TestCase):
    def order(self, **overrides):
        order = {
            "shopify_order_id": incident_repair.SC3058_ORDER_GID,
            "order_name": incident_repair.SC3058_ORDER_NAME,
            "source_name": "ebay-au",
            "source_display": "eBay Australia",
            "source_identifier": "01-15093-49797",
            "source_app_id": "gid://shopify/App/1777077",
            "source_app_name": "Marketplace Connect",
            "tags": ["eBay", "eBay-AU"],
            "financial_status": "PAID",
            "fulfillment_status": "UNFULFILLED",
            "cancelled_at": None,
            "test": False,
            "processed_at": "2026-08-24T20:24:33Z",
            "line_items": [
                {
                    "shopify_line_item_id": incident_repair.SC3058_LINE_GID,
                    "shopify_product_id": incident_repair.MUHAMMAD_ALI_PRODUCT_GID,
                    "shopify_variant_id": incident_repair.MUHAMMAD_ALI_VARIANT_GID,
                    "variant_id": incident_repair.MUHAMMAD_ALI_VARIANT_GID,
                    "sku": incident_repair.MUHAMMAD_ALI_SKU,
                    "product_title": "eBay-modified Muhammad Ali title",
                    "quantity": 1,
                }
            ],
        }
        order.update(overrides)
        return order

    def states(self):
        return {
            "muhammad_ali": {
                "edition_total": 100,
                "valid_numbers": list(range(1, 76)),
                "valid_count": 75,
                "highest_valid": 75,
            },
            "shane_warne": {
                "edition_total": 100,
                "valid_numbers": list(range(1, 10)),
                "valid_count": 9,
                "highest_valid": 9,
            },
        }

    def mapping(self):
        return [
            {
                "mapping_status": "matched",
                "mapping_method": "shopify_product_and_variant_gid",
                "mapped_product_gid": incident_repair.MUHAMMAD_ALI_PRODUCT_GID,
            }
        ]

    def test_paid_ebay_sc3058_derives_next_muhammad_ali_edition_without_title_matching(self):
        report = incident_repair.build_sc3058_recovery_plan(
            self.order(), self.states(), mapping=self.mapping(), trace={}
        )
        self.assertEqual(report["apply_blockers"], [])
        self.assertEqual(report["source_channel"], "ebay")
        self.assertEqual(report["source_display"], "eBay Australia")
        self.assertEqual(report["expected_edition_number"], 76)
        self.assertEqual(report["product_gid"], incident_repair.MUHAMMAD_ALI_PRODUCT_GID)
        self.assertEqual(report["idempotency_identity"]["external_order_id"], incident_repair.SC3058_ORDER_GID)

    def test_sc3058_replay_keeps_existing_edition_exactly_once(self):
        report = incident_repair.build_sc3058_recovery_plan(
            self.order(),
            self.states(),
            mapping=self.mapping(),
            trace={
                "order_stored": True,
                "allocations": [
                    {
                        "operational_units": 1,
                        "first_edition_number": 76,
                        "last_edition_number": 76,
                    }
                ],
            },
        )
        self.assertEqual(report["apply_blockers"], [])
        self.assertTrue(report["already_allocated"])
        self.assertEqual(report["expected_edition_number"], 76)

    def test_sc3058_wrong_or_unmatched_variant_is_blocked_without_changing_shane(self):
        order = self.order()
        order["line_items"][0]["shopify_variant_id"] = "gid://shopify/ProductVariant/999"
        order["line_items"][0]["variant_id"] = "gid://shopify/ProductVariant/999"
        states = self.states()
        shane_before = list(states["shane_warne"]["valid_numbers"])
        report = incident_repair.build_sc3058_recovery_plan(
            order,
            states,
            mapping=[{"mapping_status": "missing", "mapped_product_gid": ""}],
            trace={},
        )
        self.assertTrue(report["apply_blockers"])
        self.assertEqual(states["shane_warne"]["valid_numbers"], shane_before)

    def test_recovery_cli_is_dry_run_and_hash_bound(self):
        args = recover_sc3058.build_parser().parse_args([])
        self.assertFalse(args.apply)
        self.assertFalse(args.generate_certificate)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(
                __import__("json").dumps(
                    {
                        "report_sha256": "approved",
                        "shopify_order_id": incident_repair.SC3058_ORDER_GID,
                        "apply_blockers": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                recover_sc3058.apply_report(path, "wrong")


if __name__ == "__main__":
    unittest.main()
