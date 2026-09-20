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
                         ["premium_scarcity"] * 3)
        self.assertEqual([v["group_heading"] for v in visuals], [
            "GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE", "GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON", "GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE"])

    def test_shared_banner_and_three_different_rooms(self):
        visuals = self.visuals(metadata={"edition_limit": 100})
        for field in ("room_profile", "wall_colour", "primary_cue", "secondary_cue", "architectural_cue", "lighting"):
            self.assertEqual(len({v[field] for v in visuals}), 3)
        for i, prompt in enumerate(self.prompts({"edition_limit":100})):
            for required in ("ONLY 100 WILL EVER EXIST", "Once they’re claimed, this edition retires forever.",
                             "CLAIM YOUR EDITION", "24–28%", "72–76%", "Never mirror artwork"):
                self.assertIn(required, prompt)
            self.assertIn(("RIGHT ANGLE", "CENTRE / STRAIGHT-ON", "LEFT ANGLE")[i], prompt)

    def test_unknown_and_other_limits_remain_truthful(self):
        self.assertTrue(all(v['headline_text']=='SPORTS CAVE COLLECTOR' for v in self.visuals()))
        self.assertTrue(all(v['headline_text']=='ONLY 250 WILL EVER EXIST' for v in self.visuals(metadata={'edition_limit':250})))

    def test_fixed_camera_roles_and_determinism(self):
        self.assertEqual(self.visuals(), self.visuals())
        for token in ('one', 'two'):
            self.assertEqual([v['camera_role'] for v in self.visuals(token)], ['RIGHT','FRONT','LEFT'])

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
        self.assertEqual(grouped.count("\nAD COPY\n"), 3)
        self.assertNotIn("COPY VARIATIONS", grouped)
        master = ads_page.build_ads_prompt("Collector Cricket Print", "Cricket", "Australia", "Instant Experience")
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, master)
        self.assertIn("Catalogue product headline field uses: product.name", master)


if __name__ == "__main__":
    unittest.main()
