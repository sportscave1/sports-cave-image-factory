import unittest

import marketing_factory_page as marketing_factory


class MarketingFactoryPageTests(unittest.TestCase):
    def _inputs(self, **overrides):
        base = {
            "product_name": "Kobe Bryant Wall Art",
            "product_handle": "kobe-bryant-wall-art",
            "shopify_product_id": "gid://shopify/Product/100",
            "product_url": "https://example.com/products/kobe-bryant-wall-art",
            "sport": "Basketball",
            "fan_base": "Lakers fans",
            "country": "Australia",
            "ad_format": "Manual Carousel Upload",
            "funnel_stage": "Cold Prospecting",
            "edition_stage": "Late Stage",
            "edition_truth": "Late Stage. Use broad stage language; product page handles exact numbers.",
            "next_edition_number": 82,
            "edition_total": 100,
            "edition_remaining": 19,
            "story_context": "A legacy moment for real fans.",
            "mockup_notes": "Use a black frame room mockup.",
            "meta_signal": "No Meta signal found for this product yet.",
            "primary_angle": "Nostalgia",
            "secondary_angles": ["Collector Value"],
            "include_exact": False,
            "include_controls": {},
        }
        base.update(overrides)
        return base

    def test_edition_stage_mapping_uses_required_ladder(self):
        self.assertEqual(marketing_factory._edition_stage_from_number(1), "Low Number Rush")
        self.assertEqual(marketing_factory._edition_stage_from_number(50), "Halfway Mark")
        self.assertEqual(marketing_factory._edition_stage_from_number(97), "Closing Fast")
        self.assertEqual(marketing_factory._edition_stage_from_number(100), "Final Call")
        self.assertEqual(marketing_factory._edition_stage_from_number(42, sold_out=True), "Archived")

    def test_prompt_pack_contains_required_sections_and_country_rules(self):
        pack = marketing_factory._build_pack(self._inputs(country="UK"))
        prompt = pack["full_prompt"]

        self.assertIn("You are my Sports Cave Meta Ads strategist and copywriter.", prompt)
        self.assertIn("Country target: UK", prompt)
        self.assertIn("proper football culture", prompt)
        self.assertIn("OUTPUT EXACTLY:", prompt)
        self.assertIn("Manual carousel card copy", prompt)
        self.assertIn("Instant Experience version", prompt)

    def test_manual_carousel_outputs_mobile_sized_banks(self):
        pack = marketing_factory._build_pack(self._inputs())
        headlines = [line for line in pack["headlines"].splitlines() if line.strip()]
        descriptions = [line for line in pack["descriptions"].splitlines() if line.strip()]
        cards = [line for line in pack["carousel_labels"].splitlines() if line.strip()]

        self.assertEqual(len(headlines), 8)
        self.assertEqual(len(descriptions), 8)
        self.assertEqual(len(cards), 5)
        self.assertTrue(all(len(line.replace("- ", "").split()) <= 4 for line in headlines))


if __name__ == "__main__":
    unittest.main()
