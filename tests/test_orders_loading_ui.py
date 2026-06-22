from pathlib import Path
import unittest

import edition_ops


ROOT = Path(__file__).resolve().parents[1]


class EditionOpsUiTests(unittest.TestCase):
    def test_app_routes_to_edition_ops_not_old_orders_or_limited_pages(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Edition Ops"', source)
        self.assertIn("get_edition_ops().render_page()", source)
        self.assertNotIn('"Limited Editions",', source)
        self.assertNotIn('"Orders",', source)
        self.assertNotIn("render_limited_editions_page", source)
        self.assertNotIn("render_lightweight_orders_page", source)
        self.assertNotIn("render_edition_orders_page", source)
        self.assertNotIn("render_edition_integrity_check_page", source)

    def test_edition_ops_uses_one_editor_and_no_old_data_sources(self):
        source = (ROOT / "edition_ops.py").read_text(encoding="utf-8")

        self.assertIn("st.data_editor", source)
        self.assertIn("edition_ops_products_snapshot.json", source)
        self.assertIn("edition_ops_orders_snapshot.json", source)
        self.assertIn("Refresh Products From Shopify", source)
        self.assertIn("Refresh Orders From Shopify", source)
        self.assertIn("Export CSV Backup", source)
        self.assertIn("Import CSV Updates", source)
        self.assertIn("shipping_method", source)
        self.assertIn("certificate_display", source)
        self.assertIn("default_paid_unfulfilled_filter=False", source)
        self.assertIn("_hydrate_from_snapshot_once()", source)
        self.assertIn("_hydrate_orders_snapshot_once()", source)
        self.assertIn("_write_snapshot", source)
        self.assertLess(source.index('_render_orders_table(config, product_rows_for_orders)'), source.index('st.subheader("Products")'))
        self.assertNotIn("Clear Table", source)
        self.assertNotIn("Save Changed Rows", source)
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
        source = (ROOT / "os_pages.py").read_text(encoding="utf-8")

        self.assertIn('"Edition Ops Setup"', source)
        self.assertIn("Check Metafield Definitions", source)
        self.assertIn("Create Missing Metafield Definitions", source)

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
        self.assertEqual(updated_rows[0]["remaining"], 79)

    def test_order_editions_and_certificates_are_derived_from_product_table(self):
        product = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "handle": "all-rise-wall-art",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 53,
            }
        )
        order_rows = [
            edition_ops._normalise_order_row(
                {
                    "shopify_line_item_id": "gid://shopify/LineItem/old",
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "order_name": "#SC1",
                    "created_at": "2026-06-20T10:00:00Z",
                    "quantity": 2,
                }
            ),
            edition_ops._normalise_order_row(
                {
                    "shopify_line_item_id": "gid://shopify/LineItem/new",
                    "shopify_product_gid": "gid://shopify/Product/1",
                    "order_name": "#SC2",
                    "created_at": "2026-06-21T10:00:00Z",
                    "quantity": 1,
                }
            ),
        ]

        recalculated = edition_ops._recalculate_order_editions(order_rows, [product])
        by_id = {row["shopify_line_item_id"]: row for row in recalculated}

        self.assertEqual(by_id["gid://shopify/LineItem/old"]["edition_display"], "#53-54/100")
        self.assertEqual(by_id["gid://shopify/LineItem/old"]["certificate_display"], "SC-SC1-0053 +1")
        self.assertEqual(by_id["gid://shopify/LineItem/new"]["edition_display"], "#55/100")
        self.assertEqual(by_id["gid://shopify/LineItem/new"]["edition_status"], "Ready")
        self.assertEqual(by_id["gid://shopify/LineItem/new"]["certificate_display"], "SC-SC2-0055")

    def test_existing_order_editions_remain_and_new_orders_advance_product_next(self):
        product = edition_ops._normalise_row(
            {
                "shopify_product_gid": "gid://shopify/Product/1",
                "handle": "all-rise-wall-art",
                "edition_enabled": True,
                "edition_total": 100,
                "edition_next_number": 53,
            }
        )
        existing = edition_ops._normalise_order_row(
            {
                "shopify_line_item_id": "gid://shopify/LineItem/old",
                "shopify_product_gid": "gid://shopify/Product/1",
                "order_name": "#SC1",
                "created_at": "2026-06-20T10:00:00Z",
                "quantity": 1,
                "edition_display": "#53/100",
            }
        )
        orders = [
            {
                "shopify_order_id": "gid://shopify/Order/1",
                "order_name": "#SC1",
                "created_at": "2026-06-20T10:00:00Z",
                "line_items": [
                    {
                        "shopify_line_item_id": "gid://shopify/LineItem/old",
                        "shopify_product_id": "gid://shopify/Product/1",
                        "product_handle": "all-rise-wall-art",
                        "quantity": 1,
                    }
                ],
            },
            {
                "shopify_order_id": "gid://shopify/Order/2",
                "order_name": "#SC2",
                "created_at": "2026-06-21T10:00:00Z",
                "line_items": [
                    {
                        "shopify_line_item_id": "gid://shopify/LineItem/new",
                        "shopify_product_id": "gid://shopify/Product/1",
                        "product_handle": "all-rise-wall-art",
                        "quantity": 1,
                    }
                ],
            },
        ]

        order_rows = edition_ops._order_rows_from_shopify_orders(
            orders,
            [product],
            existing_order_rows=[existing],
        )
        by_id = {row["shopify_line_item_id"]: row for row in order_rows}
        updated_products, advanced_products = edition_ops._advance_product_rows_from_orders([product], order_rows)

        self.assertEqual(by_id["gid://shopify/LineItem/old"]["edition_display"], "#53/100")
        self.assertEqual(by_id["gid://shopify/LineItem/new"]["edition_display"], "#54/100")
        self.assertEqual(updated_products[0]["edition_next_number"], 55)
        self.assertEqual(advanced_products[0]["edition_next_number"], 55)

    def test_certificate_schema_uses_uuid_safe_related_column_without_runtime_fk(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("related_edition_order_id uuid NULL", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey", source)
        self.assertNotIn("FOREIGN KEY (edition_order_id)", source)
        self.assertNotIn("FOREIGN KEY (related_edition_order_id)", source)


if __name__ == "__main__":
    unittest.main()
