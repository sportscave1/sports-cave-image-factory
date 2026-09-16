import unittest

import ads_page
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


class ThreeVisualSystemsTests(unittest.TestCase):
    def visuals(self, token="visual-test", metadata=None):
        return ads_page.resolve_standard_instant_experience_visuals(
            product_name="Collector Cricket Print", category="Cricket",
            product_metadata=metadata, variation_token=token,
        )

    def prompts(self, metadata=None):
        return [ads_page.build_standard_instant_experience_image_prompt(
            i, v, product_name="Collector Cricket Print", category="Cricket",
            country="Australia", product_url="https://example.com/products/collector",
        ) for i, v in enumerate(self.visuals(metadata=metadata), 1)]

    def test_three_families_preserve_persisted_identities(self):
        visuals = self.visuals()
        self.assertEqual([v["concept_id"] for v in visuals], [c["id"] for c in INSTANT_EXPERIENCE_CONCEPTS])
        self.assertEqual([v["visual_family"] for v in visuals],
                         ["premium_scarcity_smart_hybrid", "private_gallery", "the_cave"])
        self.assertEqual([v["group_heading"] for v in visuals], [
            "GROUP 1 — PREMIUM SCARCITY — SMART HYBRID", "GROUP 2 — PRIVATE GALLERY", "GROUP 3 — THE CAVE"])

    def test_distinct_layouts_and_wording(self):
        hybrid, gallery, cave = self.prompts({"edition_limit": 100})
        footer = ads_page.build_instant_experience_fixed_opaque_footer_rules()
        self.assertIn(footer, hybrid)
        for prompt in (gallery, cave):
            self.assertNotIn(footer, prompt)
            self.assertIn("LIMITED TO 100\n", prompt)
            self.assertNotIn("LIMITED TO 100 WORLDWIDE", prompt.upper())
            self.assertNotIn("LIMITED TO 100 WORLD WIDE", prompt.upper())
        self.assertIn("FOR THE ROOM THAT REMEMBERS.", gallery)
        self.assertIn("THE CAVE\nSTARTS\nHERE.", cave)
        self.assertIn("RIGHT GRAPHIC COLUMN: 32–34%", cave)
        self.assertIn("CABINET TOP MUST BE COMPLETELY EMPTY", cave)
        self.assertIn("No wall texture, perspective, room shadows or physical plaque effect", cave)

    def test_unknown_edition_is_non_numeric(self):
        for visual in self.visuals()[1:]:
            self.assertEqual(visual["supporting_line"], "LIMITED COLLECTOR RELEASE")
        for visual in self.visuals(metadata={"edition_limit": 250})[1:]:
            self.assertEqual(visual["supporting_line"], "LIMITED TO 250")

    def test_token_determinism_variation_and_factual_stability(self):
        self.assertEqual(self.visuals(), self.visuals())
        packs = [self.visuals(str(n), {"edition_limit": 100}) for n in range(32)]
        for slot in range(3):
            self.assertGreater(len({p[slot]["camera_side"] for p in packs}), 2)
            self.assertGreater(len({p[slot]["wall_colour"] for p in packs}), 1)
            self.assertTrue(all(p[slot]["edition_limit_used"] == "100" for p in packs))

    def test_all_prompts_keep_realism_and_smart_product_selection(self):
        for prompt in self.prompts():
            self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
            for phrase in ("PRODUCT SOURCE-ASSET FIDELITY", "LIGHTING, GLASS AND MOUNTING PHYSICS",
                           "ANTI-AI INTERIOR CONTROL", "1024 x 1024", "CREATIVE_VARIATION_TOKEN: visual-test",
                           "Resolve exactly ONE camera", "palette, brightness, frame colour",
                           "Never append worldwide, world wide", "Never invent a limit"):
                self.assertIn(phrase, prompt)
            self.assertNotIn("Don Mattingly", prompt)

    def test_fingerprints_capture_new_layouts(self):
        for i, visual in enumerate(self.visuals(), 1):
            fp = ads_page.standard_instant_experience_fingerprint(i, visual)
            self.assertEqual(fp["visual_family"], visual["visual_family"])
            self.assertEqual(fp["camera_family"], visual["camera_side"])
            self.assertEqual(fp["urgency_placement"], visual["overlay_position"])
            self.assertEqual(fp["campaign_line"], visual["headline_text"])

    def test_group_tables_and_setup_contract(self):
        grouped = ads_page.build_standard_instant_experience_group_output_contract(
            product_name="Collector Cricket Print", category="Cricket", country="Australia")
        self.assertEqual(grouped.count("\nIMAGE GENERATION PROMPT\n"), 3)
        self.assertEqual(grouped.count("\nCOPY VARIATIONS\n"), 3)
        for key in ("legacy_standard", "framed_greatness", "choose_a_side"):
            self.assertEqual(grouped.count(f"| {key} |"), 3)
        master = ads_page.build_ads_prompt("Collector Cricket Print", "Cricket", "Australia", "Instant Experience")
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, master)
        self.assertIn("Catalogue product headline field uses: product.name", master)


if __name__ == "__main__":
    unittest.main()
