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
        self.assertIn("Refresh Products From Shopify", source)
        self.assertIn("Clear Table", source)
        self.assertIn("Save Changed Rows", source)
        self.assertIn("Export CSV Backup", source)
        self.assertIn("Import CSV Updates", source)
        self.assertIn("Open Shopify Orders", source)
        self.assertIn("_hydrate_from_snapshot_once()", source)
        self.assertIn("_write_snapshot", source)
        self.assertNotIn("Shopify Metafield Setup", source)
        self.assertNotIn("Check Metafield Definitions", source)
        self.assertNotIn("Create Missing Metafield Definitions", source)
        self.assertNotIn("import supabase", source.casefold())
        self.assertNotIn("supabase_backend", source.casefold())
        self.assertNotIn("import google", source.casefold())
        self.assertNotIn("certificate", source.casefold())
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

    def test_certificate_schema_uses_uuid_safe_related_column_without_runtime_fk(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("related_edition_order_id uuid NULL", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey", source)
        self.assertNotIn("FOREIGN KEY (edition_order_id)", source)
        self.assertNotIn("FOREIGN KEY (related_edition_order_id)", source)


if __name__ == "__main__":
    unittest.main()
