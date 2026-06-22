from pathlib import Path
import unittest


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
        self.assertIn("Load Active Shopify Products", source)
        self.assertIn("Refresh From Shopify", source)
        self.assertIn("Clear Loaded Table", source)
        self.assertIn("Save Changed Rows to Shopify", source)
        self.assertIn("Sync Selected Rows", source)
        self.assertIn("Open Shopify Orders", source)
        self.assertNotIn("import supabase", source.casefold())
        self.assertNotIn("supabase_backend", source.casefold())
        self.assertNotIn("import google", source.casefold())
        self.assertNotIn("csv", source.casefold())
        self.assertNotIn("certificate", source.casefold())
        self.assertNotIn("fetch_orders", source)

    def test_certificate_schema_uses_uuid_safe_related_column_without_runtime_fk(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("related_edition_order_id uuid NULL", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey", source)
        self.assertNotIn("FOREIGN KEY (edition_order_id)", source)
        self.assertNotIn("FOREIGN KEY (related_edition_order_id)", source)


if __name__ == "__main__":
    unittest.main()
