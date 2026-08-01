import unittest

import prompt_store
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,
    append_sports_cave_image_realism_rules,
    build_sports_cave_image_realism_rules,
)


class SportsCaveImageRealismRulesTests(unittest.TestCase):
    def test_product_rules_append_once(self):
        prompt = "Create a product mockup."

        once = append_sports_cave_image_realism_rules(prompt, include_product_lock=True)
        twice = append_sports_cave_image_realism_rules(once, include_product_lock=True)

        self.assertEqual(twice, once)
        self.assertEqual(once.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", once)
        self.assertIn("Treat the uploaded full-resolution product as an immutable physical asset.", once)

    def test_original_artwork_rules_exclude_immutable_product_lock(self):
        block = build_sports_cave_image_realism_rules(include_product_lock=False)

        self.assertEqual(block.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertIn("GLOBAL PHOTOGRAPHIC REALISM RULES - MANDATORY", block)
        self.assertIn("ORIGINAL ARTWORK MODE - PRODUCT LOCK EXCLUSION", block)
        self.assertNotIn("Treat the uploaded full-resolution product as an immutable physical asset.", block)

    def test_required_exact_ending_is_preserved(self):
        ending = "Would you like me to generate Card 1?"
        prompt = f"Prompt body.\n\n{ending}"

        result = append_sports_cave_image_realism_rules(
            prompt,
            include_product_lock=True,
            required_ending=ending,
        )

        self.assertTrue(result.endswith(ending))
        self.assertEqual(result.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
        self.assertLess(result.index(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), result.index(ending))

    def test_prompt_store_contract_version_bumped_for_legacy_prompt_cache(self):
        self.assertEqual(prompt_store.PROMPT_STORE_VERSION, 3)


if __name__ == "__main__":
    unittest.main()
