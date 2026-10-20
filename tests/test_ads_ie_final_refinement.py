"""Final scene/typography contracts; no generated-image inspection is implied."""
import copy
import json
import re
import unittest

import ads_ie_scenes as scenes
import ads_page as ads


class FinalRefinementTests(unittest.TestCase):
    def record(self, token="final-refinement", metadata=None):
        return ads.build_ads_result_record("Alexander Volkanovski Collector", "MMA", "Australia",
            "Instant Experience", variation_token=token, product_metadata=metadata or {"edition_limit": 100})

    def test_structural_and_residential_contrast_across_fresh_packs(self):
        for seed in range(80):
            pack = scenes.select(str(seed), {})
            for key in ("spatial_family", "architecture_style", "wall_colour_family", "wall_finish", "residential_cue_family", "depth_position"):
                self.assertEqual(len({s[key] for s in pack}), 3, (seed, key))
            for a, b in ((0, 1), (0, 2), (1, 2)):
                self.assertTrue(scenes.different(pack[a], pack[b]))
                restyled = dict(pack[b], spatial_family=pack[a]["spatial_family"])
                self.assertFalse(scenes.different(pack[a], restyled))

    def test_partial_saved_override_and_older_history_are_respected(self):
        pack = scenes.select("saved", {}, selections=[{"wall_colour": "warm ivory"}])
        self.assertEqual(pack[0]["wall_colour"], "warm ivory")
        old = copy.deepcopy(pack[0])
        old.pop("spatial_family")
        old.pop("residential_cue_family")
        old["scene_signature"] = "old signature"
        old["scene_near_signature"] = "old near signature"
        self.assertTrue(scenes._history_conflict(pack[0], old))

    def test_each_call_has_one_resolved_scene_without_sibling_leakage(self):
        result = self.record()
        prompts = re.findall(r"\nIMAGE GENERATION PROMPT\n(.*?)\nAD COPY\n", result["master_prompt"], re.S)
        self.assertEqual(len(prompts), 3)
        rows = result["instant_experience_fingerprints"]
        for i, prompt in enumerate(prompts):
            self.assertEqual(len(re.findall(r"^SCENE:", prompt, re.M)), 1)
            self.assertIn(rows[i]["architecture_style"], prompt)
            for j, row in enumerate(rows):
                if i != j:
                    self.assertNotIn(row["architecture_style"], prompt)
                    self.assertNotIn("Headline: " + row["headline_text"], prompt)
            for phrase in ("CTA: CLAIM YOUR EDITION",):
                self.assertIn(phrase, prompt)
            self.assertNotIn("Montserrat SemiBold", prompt)
        # Combined calls inherit one shared template; individual copy actions
        # include the same contract directly, with only their own resolved copy.
        for phrase in ("STABLE 1024 PX COLLECTOR TYPOGRAPHY TARGETS", "Montserrat Medium", "Thickness is approximately 1 px"):
            self.assertIn(phrase, result["master_prompt"])
            for i, row in enumerate(ads.resolve_standard_instant_experience_visuals(
                    product_name=result["product_name"], category="MMA", country="Australia",
                    product_metadata=result["product_metadata"], variation_token=result["variation_token"])):
                standalone = ads.build_instant_experience_canonical_prompt_v4(i + 1, row,
                    product_name=result["product_name"], category="MMA", country="Australia")
                self.assertEqual(standalone.count(phrase), 1)

    def test_visual_review_replacement_and_reference_contract(self):
        prompt = self.record()["master_prompt"]
        for phrase in ("Do these look like three different properties, or the same wall-and-opening composition restyled?",
                       "Replacement for Image 1", "Replacement for Image 2", "Replacement for Image 3",
                       "at most one correction call per image", "exactly three selected final covers",
                       "never reduce a previous generation again", "Do not compound percentage reductions"):
            self.assertIn(phrase, prompt)
        self.assertIn("no deterministic Ads footer renderer", prompt)

    def test_saved_draft_does_not_reroll_scenes_or_typography(self):
        saved = json.loads(json.dumps(self.record()))
        prompt = saved["master_prompt"]
        self.assertIs(ads.ensure_current_ads_result_prompt(saved), saved)
        self.assertEqual(ads.creation_instructions(prompt), prompt)
        self.assertEqual(saved["master_prompt"], prompt)


if __name__ == "__main__":
    unittest.main()
