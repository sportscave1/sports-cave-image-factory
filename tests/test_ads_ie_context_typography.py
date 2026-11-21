from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
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
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_cross_product_refresh_history_rotates_role_palettes_and_layouts(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        rotated_ie(self)

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
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

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
