from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OrdersLoadingUiTests(unittest.TestCase):
    def test_orders_and_limited_pages_do_not_show_lazy_load_copy(self):
        source = (ROOT / "os_pages.py").read_text(encoding="utf-8")

        blocked_phrases = (
            "Load / Refresh",
            "Load orders",
            "Load edition products",
            "Fetch Latest Orders",
            "Fetch Latest Shopify Products",
            "lazy loaded",
            "Fast mode",
            "Technical detail",
        )
        for phrase in blocked_phrases:
            self.assertNotIn(phrase, source)

    def test_certificate_schema_uses_uuid_safe_related_column_without_runtime_fk(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("related_edition_order_id uuid NULL", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_edition_order_id_fkey", source)
        self.assertIn("DROP CONSTRAINT IF EXISTS certificates_related_edition_order_id_fkey", source)
        self.assertNotIn("FOREIGN KEY (edition_order_id)", source)
        self.assertNotIn("FOREIGN KEY (related_edition_order_id)", source)

    def test_orders_read_without_full_schema_gate(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("def ensure_order_read_schema", source)
        self.assertIn("def list_orders", source)
        self.assertIn("def get_order_summary", source)
        self.assertIn("ensure_order_read_schema()", source)

    def test_orders_ui_uses_cached_shopify_style_copy(self):
        source = (ROOT / "os_pages.py").read_text(encoding="utf-8")

        self.assertIn("Fetch New Orders", source)
        self.assertIn("Deep Refresh 60 Days", source)
        self.assertIn("Load 50 More", source)
        self.assertIn("Paid + Unfulfilled", source)
        self.assertIn("components.html(html_table", source)
        self.assertIn("sc-shopify-table", source)
        self.assertIn("render_supabase_orders_page()", source)


if __name__ == "__main__":
    unittest.main()
