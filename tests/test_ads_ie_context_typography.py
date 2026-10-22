"""Cross-product scene attributes and complete prompt checks, never image calls."""
import json
import re
import unittest
from unittest.mock import patch

import ads_ie_scenes as scenes
import ads_page as ads


class ContextTypographyTests(unittest.TestCase):
    def record(self, product="Alexander Volkanovski Collector", sport="MMA", seed="context", history=(), metadata=None):
        return ads.build_ads_result_record(product, sport, "Australia", "Instant Experience", variation_token=seed,
            product_metadata=metadata or {"edition_limit": 100}, recent_instant_experience_fingerprints=history)

    def test_every_automatic_front_option_has_a_recognisable_home_glimpse(self):
        for scene in scenes.SCENES[1]:
            self.assertRegex(scene["architectural_cue"], r"furniture silhouette|seating silhouette|sitting-area glimpse|stair-landing glimpse|window seat|bench edge|adjoining living area")
            self.assertRegex(scene["architectural_cue"], r"far left|far right")
            self.assertNotIn("closed shallow niche", scene["architectural_cue"])

    def test_cross_product_refresh_history_rotates_role_palettes_and_layouts(self):
        history, previous = [], None
        used = [set(), set(), set()]
        products = (("Alexander Volkanovski Collector", "MMA"), ("Lionel Messi Tribute", "Football"),
                    ("Peter Brock Bathurst", "Motorsport"), ("Michael Jordan Collection", "NBA"))
        for i in range(28):
            name, sport = products[i % len(products)]
            rows = self.record(name, sport, str(i), history)["instant_experience_fingerprints"]
            for slot, row in enumerate(rows):
                self.assertEqual(row["scene_slot"], slot)
                self.assertFalse(any(scenes._history_conflict(row, old) for old in history[:scenes.HISTORY_LIMIT]))
                if previous:
                    self.assertNotEqual(row["wall_visual_group"], previous[slot]["wall_visual_group"])
                    self.assertNotEqual(row["architecture_style"], previous[slot]["architecture_style"])
                used[slot].add(row["wall_colour_family"])
            previous = rows
            history = (rows + history)[:scenes.HISTORY_LIMIT]
        self.assertTrue(all(len(families) >= 6 for families in used))

    def test_older_history_without_new_slot_field_still_influences_ranking(self):
        old = self.record()["instant_experience_fingerprints"]
        legacy = [{k: v for k, v in row.items() if k != "scene_slot"} for row in old]
        modern = self.record("Another Product", "Cricket", "next", old)
        earlier = self.record("Another Product", "Cricket", "next", legacy)
        self.assertEqual(modern["instant_experience_fingerprints"], earlier["instant_experience_fingerprints"])

    def test_session_and_captured_draft_history_reuse_all_products(self):
        first = self.record()
        second = self.record("Peter Brock", "Motorsport", "next")
        with patch.object(ads.st, "session_state", {ads.ADS_IE_RECENT_FINGERPRINTS_KEY: first["instant_experience_fingerprints"]}):
            history = ads.recent_instant_experience_scene_history(second)
        self.assertEqual(len(history), 6)
        self.assertEqual(history[:3], first["instant_experience_fingerprints"])
        self.assertEqual(history[3:], second["instant_experience_fingerprints"])

    def test_complete_exports_prioritise_roles_and_one_stable_type_contract(self):
        for name, sport in (("Volkanovski", "MMA"), ("Messi", "Football"), ("Peter Brock", "Motorsport")):
            record = self.record(name, sport, name)
            prompt = record["master_prompt"]
            self.assertLess(prompt.index(ads.IE_CREATIVE_VARIETY_AND_TYPOGRAPHY), prompt.index("\nSCENE:"))
            for phrase in ("for OTHER products too", "small residential glimpse", "premium residential man cave setting",
                           "exactly three successful image-generation calls", "not guaranteed cross-session memory"):
                self.assertIn(phrase, prompt)
            shared = ads.build_instant_experience_typography_quality_rules(shared=True)
            self.assertEqual(prompt.count(shared), 1)
            for text in ("headline 42–48 px", "supporting line 24–26 px, Montserrat Regular", "CTA 26–28 px, Montserrat Medium",
                         "Uppercase wording is casing only", "Never enlarge text to fill empty panel space"):
                self.assertIn(text, prompt)
            for obsolete in ("Relative guidance", "recent oversized reference", "Montserrat SemiBold", "Montserrat Bold",
                             "opaque promotional banner", "at most one correction call"):
                self.assertNotIn(obsolete, prompt)
            briefs = re.findall(r"\nIMAGE GENERATION PROMPT\n(.*?)\nAD COPY\n", prompt, re.S)
            self.assertEqual(len(briefs), 3)
            self.assertIn("Premium collector hallway", briefs[0])
            self.assertIn("tiny but recognisable", briefs[1])
            self.assertIn("Premium residential man cave", briefs[2])
            self.assertTrue(all("CTA: CLAIM YOUR EDITION" in brief for brief in briefs))

    def test_saved_and_explicit_choices_are_not_rerolled(self):
        original = self.record()
        saved = json.loads(json.dumps(original))
        self.assertIs(ads.ensure_current_ads_result_prompt(saved), saved)
        rebuilt = self.record(seed="changed", history=original["instant_experience_fingerprints"], metadata=saved["product_metadata"])
        self.assertEqual(rebuilt["product_metadata"]["instant_experience_scene_selections"], saved["product_metadata"]["instant_experience_scene_selections"])
        selected = scenes.select("explicit", {}, recent=original["instant_experience_fingerprints"], selections=[{"wall_colour": "warm ivory"}])
        self.assertEqual(selected[0]["wall_colour"], "warm ivory")


if __name__ == "__main__":
    unittest.main()
