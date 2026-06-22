from pathlib import Path
import json
import unittest
from unittest.mock import patch

import edition_ops
import orders_page
import shopify_sync


ROOT = Path(__file__).resolve().parents[1]


class EditionOpsUiTests(unittest.TestCase):
    def test_app_routes_to_edition_ops_not_old_orders_or_limited_pages(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Edition Ops"', source)
        self.assertIn('"Orders"', source)
        self.assertIn("get_edition_ops().render_page()", source)
        self.assertIn("get_orders_page().render_page()", source)
        self.assertNotIn('"Certificates"', source)
        self.assertNotIn("get_certificates_page", source)
        self.assertNotIn("certificates_page", source)
        self.assertNotIn('"Limited Editions",', source)
        self.assertNotIn("render_limited_editions_page", source)
        self.assertNotIn("render_edition_orders_page", source)
        self.assertNotIn("render_edition_integrity_check_page", source)
        self.assertIn('current_page in {"Dashboard", "Products", "Edition Ops", "Orders", "Developer", "Settings"}', source)
        self.assertIn("DEVELOPER_PAGE_PASSWORD", source)
        self.assertIn("developer_unlocked", source)

    def test_edition_ops_uses_one_editor_and_no_old_data_sources(self):
        source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")

        self.assertIn("st.data_editor", source)
        self.assertIn("edition_ops_products_snapshot.json", source)
        self.assertIn("Refresh Products", source)
        self.assertIn("Save Changed Rows", source)
        self.assertIn("Export CSV Backup", source)
        self.assertIn("Import CSV and Replace Table", source)
        self.assertIn("edition_sold_count", source)
        self.assertIn("edition_remaining", source)
        self.assertIn("edition_status", source)
        self.assertIn("_rows_to_save", source)
        self.assertIn("_hydrate_from_snapshot_once()", source)
        self.assertIn("_write_snapshot", source)
        self.assertNotIn("edition_ops_orders_snapshot.json", source)
        self.assertNotIn("Refresh Orders", source)
        self.assertNotIn("Refresh Products From Shopify", source)
        self.assertNotIn("shipping_method", source)
        self.assertNotIn("certificate_display", source)
        self.assertNotIn("default_paid_unfulfilled_filter=False", source)
        self.assertNotIn("_hydrate_orders_snapshot_once", source)
        self.assertNotIn("_render_orders_table", source)
        self.assertNotIn("Clear Table", source)
        self.assertNotIn("Refresh Unfulfilled Orders", source)
        self.assertNotIn("Open Shopify Orders", source)
        self.assertNotIn("Shopify is the permanent record", source)
        self.assertNotIn("Shopify Metafield Setup", source)
        self.assertNotIn("Check Metafield Definitions", source)
        self.assertNotIn("Create Missing Metafield Definitions", source)
        self.assertNotIn("import supabase", source.casefold())
        self.assertNotIn("supabase_backend", source.casefold())
        self.assertNotIn("import google", source.casefold())
        self.assertNotIn("fetch_orders", source)

    def test_developer_keeps_edition_ops_metafield_setup(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Shopify Limited Edition Setup"', source)
        self.assertIn("Check Product Metafield Definitions", source)
        self.assertIn("Create Missing Product Metafield Definitions", source)
        self.assertIn('"Order Metafield Setup"', source)
        self.assertIn("Check Order Metafield Definition", source)
        self.assertIn("Create Missing Order Metafield Definition", source)

    def test_orders_page_is_snapshot_based_and_lightweight(self):
        source = (ROOT / "orders_page.py").read_text(encoding="utf-8")

        self.assertEqual(
            orders_page.VISIBLE_COLUMNS,
            ("order", "date", "customer", "shipping", "product", "variant", "edition", "certificate"),
        )
        self.assertIn("orders_allocation_snapshot.json", source)
        self.assertIn("Refresh Orders", source)
        self.assertIn("_render_orders_table", source)
        self.assertIn("Generate", source)
        self.assertIn("Upload to Shopify", source)
        self.assertNotIn("Save Changed Order Editions", source)
        self.assertNotIn("Allocate Selected From Product Counter", source)
        self.assertNotIn("Overwrite Selected Order Allocation", source)
        self.assertNotIn("Override Selected Order Allocation", source)
        self.assertNotIn("Manual Allocation", source)
        self.assertNotIn("st.data_editor", source)
        self.assertIn("sync_order_allocation_metafield", source)
        self.assertNotIn('"qty"', source)
        self.assertNotIn('"allocation_status"', source)
        self.assertNotIn('"sync_status"', source)
        self.assertNotIn('"admin_url"', source)
        self.assertNotIn("supabase_backend", source)

    def test_orders_page_formats_single_edition_numbers(self):
        self.assertEqual(orders_page._format_edition("50"), "#050")
        self.assertEqual(orders_page._format_edition("#50"), "#050")
        self.assertEqual(orders_page._format_edition("050"), "#050")
        self.assertEqual(orders_page._format_edition("#050/100"), "#050")
        self.assertEqual(orders_page._format_edition(""), "")

    def test_orders_page_splits_quantity_rows_into_one_artwork_per_edition(self):
        line_item_id = "gid://shopify/LineItem/1"
        order = {
            "order_name": "#SC1234",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "customer_name": "John",
            "shipping_method": "Express Shipping",
            "metafields": [
                {
                    "namespace": "sports_cave",
                    "key": "edition_allocations",
                    "value": json.dumps({"line_items": {line_item_id: {"edition_numbers": [50, 51]}}}),
                }
            ],
        }
        line_item = {
            "shopify_line_item_id": line_item_id,
            "shopify_product_id": "gid://shopify/Product/1",
            "product_title": "Shane Warne Tribute Wall Art",
            "variant_title": "Black / XL",
            "quantity": 2,
        }

        rows = orders_page._rows_from_order_line(order, line_item, {"edition_next_number": 91})

        self.assertEqual([row["edition"] for row in rows], ["#050", "#051"])
        self.assertTrue(all("qty" not in {column.lower() for column in orders_page.VISIBLE_COLUMNS} for _ in rows))

    def test_orders_page_uses_product_next_number_when_no_saved_allocation(self):
        order = {
            "order_name": "#SC1235",
            "processed_at": "2026-06-22T10:00:00Z",
            "created_at": "2026-06-22T09:55:00Z",
            "customer_name": "John",
            "shipping_method": "Standard Shipping",
            "metafields": [],
        }
        line_item = {
            "shopify_line_item_id": "gid://shopify/LineItem/2",
            "shopify_product_id": "gid://shopify/Product/1",
            "product_title": "Shane Warne Tribute Wall Art",
            "variant_title": "Black / XL",
            "quantity": 2,
        }

        rows = orders_page._rows_from_order_line(order, line_item, {"edition_next_number": 91})

        self.assertEqual([row["edition"] for row in rows], ["#091", "#092"])

    def test_orders_page_certificate_record_uses_exact_visible_row_edition(self):
        row = orders_page._normalise_row(
            {
                "order": "#SC1234",
                "date": "2026-06-22",
                "customer": "Greg Collector",
                "customer_email": "greg@example.com",
                "product": "Greg Murphy Lap of the Gods Wall Art",
                "variant": "Black / XL",
                "edition_number": 16,
                "edition_total": 100,
                "shopify_order_id": "gid://shopify/Order/1234",
                "shopify_line_item_id": "gid://shopify/LineItem/555",
                "shopify_product_id": "gid://shopify/Product/777",
                "variant_id": "gid://shopify/ProductVariant/888",
                "product_handle": "greg-murphy-lap-of-the-gods-wall-art",
                "edition_offset": 0,
            }
        )

        record = orders_page.certificate_engine.certificate_record_from_order_row(row)

        self.assertEqual(record["edition_number"], 16)
        self.assertEqual(record["edition_display"], "#016")
        self.assertEqual(record["line_item_unit_index"], 1)
        self.assertIn("SC-SC1234-GREG-MURPHY-LAP-OF-THE-GODS-WALL-ART-EDITION-016", record["certificate_id"])

    def test_generate_lock_saves_visible_edition_before_certificate_generation(self):
        row = orders_page._normalise_row(
            {
                "order": "#SC1234",
                "product": "Greg Murphy Lap of the Gods Wall Art",
                "variant": "Black / XL",
                "edition_number": 16,
                "edition_total": 100,
                "edition_offset": 1,
                "line_quantity": 2,
                "shopify_order_id": "gid://shopify/Order/1234",
                "shopify_line_item_id": "gid://shopify/LineItem/555",
                "shopify_product_id": "gid://shopify/Product/777",
                "variant_id": "gid://shopify/ProductVariant/888",
                "product_handle": "greg-murphy-lap-of-the-gods-wall-art",
            }
        )
        synced = []

        with patch.object(
            orders_page.order_allocator,
            "read_order_allocation_state",
            return_value={"payload": {"line_items": {}}, "compare_digest": "digest-1"},
        ), patch.object(
            orders_page.shopify_sync,
            "sync_order_allocation_metafield",
            side_effect=lambda order_id, payload, compare_digest=None, config=None: synced.append(payload),
        ):
            allocation = orders_page._lock_allocation_for_row(row, {"configured": True})

        self.assertEqual(allocation["edition_numbers"], [None, 16])
        self.assertEqual(allocation["edition_number"], 16)
        self.assertEqual(synced[0]["line_items"]["gid://shopify/LineItem/555"]["edition_numbers"], [None, 16])

    def test_limited_edition_inputs_use_only_calculated_mvp_metafields(self):
        inputs = shopify_sync.limited_edition_metafield_inputs(
            "gid://shopify/Product/1",
            {
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 65,
                "edition_label": "Numbered Edition",
            },
        )
        keys = {item["key"]: item["value"] for item in inputs}

        self.assertEqual(
            set(keys),
            {
                "edition_enabled",
                "edition_total",
                "edition_next_number",
                "edition_sold_count",
                "edition_remaining",
                "edition_status",
                "edition_label",
            },
        )
        self.assertEqual(keys["edition_sold_count"], "64")
        self.assertEqual(keys["edition_remaining"], "36")
        self.assertEqual(keys["edition_status"], "Limited Edition")

    def test_edition_ops_export_uses_required_csv_columns(self):
        row = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "legacy_resource_id": "1",
                "product_title": "All Rise Wall Art",
                "handle": "all-rise-wall-art",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 53,
                "admin_url": "https://admin.shopify.com/store/sports-cave/products/1",
                "online_store_url": "https://sportscaveshop.com/products/all-rise-wall-art",
            }
        )

        exported = edition_ops._export_csv([row]).decode("utf-8-sig").splitlines()

        self.assertEqual(exported[0].split(","), list(edition_ops.CSV_COLUMNS))
        self.assertIn("48", exported[1])
        self.assertIn("Limited Edition", exported[1])

    def test_edition_ops_changed_rows_only_consider_editable_fields(self):
        original = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "edition_total": 100,
                "edition_next_number": 1,
                "sync_status": "Loaded",
            }
        )
        changed = dict(original)
        changed["sync_status"] = "Unsaved"
        changed["edition_next_number"] = 2
        unchanged_status_only = dict(original)
        unchanged_status_only["sync_status"] = "Unsaved"

        self.assertEqual(edition_ops._changed_rows([changed], [original]), [changed])
        self.assertEqual(edition_ops._changed_rows([unchanged_status_only], [original]), [])

    def test_csv_import_accepts_visible_headers_and_excel_numbers(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "handle": "all-rise-wall-art",
                    "edition_enabled": False,
                    "edition_total": 100,
                    "edition_next_number": 1,
                }
            )
        ]
        csv_text = "Handle,Enabled,Edition total,Next edition number\nall-rise-wall-art,TRUE,150.0,72.0\n"

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertTrue(updated_rows[0]["edition_enabled"])
        self.assertEqual(updated_rows[0]["edition_total"], 150)
        self.assertEqual(updated_rows[0]["edition_next_number"], 72)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 71)
        self.assertEqual(updated_rows[0]["edition_remaining"], 79)
        self.assertEqual(updated_rows[0]["edition_status"], "Limited Edition")
        self.assertEqual(updated_rows[0]["sync_status"], "Needs Sync")

    def test_csv_import_overwrites_current_next_number_even_when_lower(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "handle": "jalen-brunson-knicks-wall-art",
                    "edition_enabled": True,
                    "edition_total": 100,
                    "edition_next_number": 49,
                }
            )
        ]
        csv_text = (
            "shopify_product_gid,handle,edition_enabled,edition_total,edition_next_number\n"
            "gid://shopify/Product/1,jalen-brunson-knicks-wall-art,true,100,25\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(updated_rows[0]["edition_next_number"], 25)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 24)
        self.assertEqual(updated_rows[0]["edition_remaining"], 76)

    def test_csv_import_replaces_with_authoritative_derived_fields(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/99",
                    "product_title": "Greg Murphy Lap of the Gods Wall Art",
                    "handle": "greg-murphy-lap-of-the-gods-wall-art",
                    "edition_enabled": True,
                    "edition_total": 100,
                    "edition_next_number": 32,
                    "edition_sold_count": 31,
                    "edition_remaining": 69,
                }
            )
        ]
        csv_text = (
            "product_title,handle,edition_enabled,edition_total,edition_next_number,"
            "edition_sold_count,edition_remaining,edition_status\n"
            "Greg Murphy Lap of the Gods Wall Art,greg-murphy-lap-of-the-gods-wall-art,"
            "true,100,16,15,85,Limited Edition\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(updated_rows[0]["edition_next_number"], 16)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 15)
        self.assertEqual(updated_rows[0]["edition_remaining"], 85)
        self.assertEqual(updated_rows[0]["edition_status"], "Limited Edition")
        self.assertEqual(updated_rows[0]["sync_status"], "Needs Sync")

    def test_csv_import_supports_old_remaining_and_widget_status_headers(self):
        rows = [
            edition_ops._normalise_row(
                {
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "product_title": "Legacy Wall Art",
                    "handle": "legacy-wall-art",
                }
            )
        ]
        csv_text = (
            "Product title,Handle,Enabled,Edition total,Next edition number,remaining,widget_status\n"
            "Legacy Wall Art,legacy-wall-art,true,100,96,5,Final Editions\n"
        )

        updated_rows, changed_rows, changed_count, warnings = edition_ops._apply_csv_updates_to_rows(rows, csv_text)

        self.assertEqual(warnings, [])
        self.assertEqual(changed_count, 1)
        self.assertEqual(len(changed_rows), 1)
        self.assertEqual(updated_rows[0]["edition_next_number"], 96)
        self.assertEqual(updated_rows[0]["edition_sold_count"], 95)
        self.assertEqual(updated_rows[0]["edition_remaining"], 5)
        self.assertEqual(updated_rows[0]["edition_status"], "Final Editions")

    def test_rows_to_save_includes_needs_sync_even_without_edit_diff(self):
        original = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "edition_total": 100,
                "edition_next_number": 16,
                "sync_status": "Synced",
            }
        )
        imported = dict(original)
        imported["sync_status"] = "Needs Sync"

        self.assertEqual(edition_ops._rows_to_save([imported], [original]), [imported])

    def test_editor_changes_recalculate_derived_fields_without_order_data(self):
        source = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "edition_total": 100,
                "edition_next_number": 16,
                "edition_sold_count": 15,
                "edition_remaining": 85,
            }
        )

        merged = edition_ops._merge_visible_rows(
            [{"edition_total": 100, "edition_next_number": 20}],
            [source],
        )

        self.assertEqual(merged[0]["edition_sold_count"], 19)
        self.assertEqual(merged[0]["edition_remaining"], 81)

    def test_certificate_schema_uses_uuid_safe_related_column_without_runtime_fk(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("related_edition_order_id uuid NULL", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey", source)
        self.assertNotIn("FOREIGN KEY (edition_order_id)", source)
        self.assertNotIn("FOREIGN KEY (related_edition_order_id)", source)


if __name__ == "__main__":
    unittest.main()
