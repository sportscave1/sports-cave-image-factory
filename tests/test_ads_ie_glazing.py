"""Glazing-only IE prompt contracts; no pixel inspection or image calls."""
import unittest
import ads_page as ads
import ads_ie_visual_systems as visuals
import sports_cave_physical_realism as physical


class GlazingTests(unittest.TestCase):
    def metadata(self, glazing="premium glass"):
        return {"edition_limit": 100, "physical_product": {"selected_variant": {
            "verified": True, "source": "verified product variant", "frame_finish": "Black",
            "glazing": glazing}}}

    def test_verified_variant_glazing_survives_without_visible_photo_reflections(self):
        self.assertEqual(physical.resolve(self.metadata()["physical_product"])["glazing"], "premium glass")
        metadata = self.metadata()
        metadata["physical_product"]["selected_variant"]["verified"] = False
        self.assertEqual(physical.resolve(metadata["physical_product"])["glazing"], "premium glass")

    def test_both_paths_have_requirement_reminder_and_visual_rejection(self):
        for refresh in (False, True):
            result = ads.build_ads_result_record("Michael Jordan", "NBA", "Australia", "Instant Experience",
                product_metadata=self.metadata(), variation_token="glazing",
                creative_refresh_context={"winning_primary_text": "Winner", "winning_headline": "Winner"} if refresh else None)
            prompt = result["master_prompt"]
            self.assertIn(visuals.GLAZING_REQUIREMENT, prompt)
            self.assertIn("GLAZING CHECK: Every framed edition must show believable surface reflections clearly visible at thumbnail size.", prompt)
            self.assertIn("missing or imperceptible surface reflections", prompt)
            for old in ("only if present in the original", "subtle but perceptible reflection", "broad faint",
                        "Keep reflections subtle", "perceptible source-consistent glazing when present"):
                self.assertNotIn(old, prompt)
            for row in result["instant_experience_fingerprints"]:
                self.assertIn("premium glass", row["glazing_treatment"])
                self.assertIn(row["reflection_source"], row["glazing_treatment"])
                self.assertIn(row["reflection_placement"], row["glazing_treatment"])
            self.assertIn("even when reflections are absent", prompt)

    def test_unglazed_and_unframed_exclusions(self):
        for kind in ("unglazed", "unframed"):
            metadata = self.metadata("none" if kind == "unglazed" else "premium glass")
            if kind == "unframed":
                metadata["physical_product"]["frame_label"] = "Unframed"
            rows = ads.resolve_standard_instant_experience_visuals(product_name="Product", category="NBA",
                country="Australia", product_metadata=metadata, variation_token="glazing")
            expected = "no added glazing" if kind == "unframed" else "premium glass"
            self.assertTrue(all(expected in row["glazing_treatment"] for row in rows))

    def test_non_ie_default_physical_prose_is_unchanged(self):
        self.assertIn("256 × 256", physical.build(compact=True))
        self.assertIn("On every framed edition require premium glass with clearly visible natural window or room-light reflections", physical.build(compact=True))


if __name__ == "__main__":
    unittest.main()
