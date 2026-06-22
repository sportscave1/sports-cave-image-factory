from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StorefrontWidgetSnippetTests(unittest.TestCase):
    def test_remaining_pill_reads_edition_remaining_not_inventory(self):
        source = (ROOT / "shopify" / "snippets" / "sports-cave-remaining-pill.liquid").read_text(
            encoding="utf-8"
        )

        self.assertIn("product.metafields.sports_cave.edition_enabled.value", source)
        self.assertIn("product.metafields.sports_cave.edition_remaining.value", source)
        self.assertIn("product.metafields.sports_cave.edition_total.value", source)
        self.assertIn("Final 1 of ", source)
        self.assertIn("Final ", source)
        self.assertIn(" remaining", source)
        self.assertNotIn("inventory", source.lower())
        self.assertNotIn("selected_or_first_available_variant", source)
        self.assertNotIn("stock", source.lower())
        self.assertNotIn("edition_status_override", source)

    def test_numbered_bar_reads_next_edition_number(self):
        source = (
            ROOT / "shopify" / "snippets" / "sports-cave-numbered-edition-bar.liquid"
        ).read_text(encoding="utf-8")

        self.assertIn("product.metafields.sports_cave.edition_enabled.value", source)
        self.assertIn("product.metafields.sports_cave.edition_next_number.value", source)
        self.assertIn("product.metafields.sports_cave.edition_total.value", source)
        self.assertIn("#{{ edition_number_padded }} Numbered Edition of {{ edition_total }}", source)
        self.assertNotIn("inventory", source.lower())
        self.assertNotIn("selected_or_first_available_variant", source)
        self.assertNotIn("stock", source.lower())
        self.assertNotIn("edition_status_override", source)

    def test_developer_page_exposes_copyable_fallback_widgets(self):
        source = (ROOT / "os_pages.py").read_text(encoding="utf-8")

        self.assertIn("Sports Cave Remaining Pill", source)
        self.assertIn("Sports Cave Numbered Edition Bar", source)
        self.assertIn("load_edition_widget_liquid_snippets", source)
        self.assertIn("render_copy_text_button", source)


if __name__ == "__main__":
    unittest.main()
