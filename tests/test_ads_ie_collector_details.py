from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
"""Offline contracts for fresh collector details and immutable saved scenes."""
import copy
import json
import unittest
from unittest.mock import patch

import ads_ie_scenes as scenes
import ads_page as ads


class CollectorDetailsTests(unittest.TestCase):
    def record(self, seed="details", history=(), metadata=None, refresh=False):
        return ads.build_ads_result_record("Michael Jordan", "NBA", "Australia", "Instant Experience",
            variation_token=seed, product_metadata=metadata or {"edition_limit": 100},
            recent_instant_experience_fingerprints=history,
            creative_refresh_context={"winning_primary_text": "Winner text", "winning_headline": "Winner headline"} if refresh else None)

    def test_both_exports_resolve_one_compatible_detail_and_no_extra_cue(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        scenes_ie(self)

    def test_all_options_rotate_independently_of_home_and_avoid_latest(self):
        history, previous = [], []
        used = [set(), set(), set()]
        # Fixed rooms show that details are not tied permanently to a home or slot.
        for i in range(32):
            chosen = [dict(slot[0]) for slot in scenes.SCENES]
            scenes.resolve_collector_details(chosen, str(i), history)
            self.assertEqual(len({s["collector_detail_family"] for s in chosen}), 3)
            current = [s["collector_detail"] for s in chosen]
            self.assertTrue(all(a != b for a, b in zip(previous, current)))
            for slot, detail in enumerate(current):
                used[slot].add(detail)
            previous = current
            history = (chosen + history)[:scenes.HISTORY_LIMIT]
        self.assertEqual(used, [{text for text, _ in options} for options in scenes.COLLECTOR_DETAILS])

    def test_new_saved_packs_keep_exact_selections_on_reopen_copy_and_export(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        saved_ie(self)

    def test_legacy_saved_packs_are_not_restyled(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        saved_ie(self)

    def test_only_peripheral_fields_change_not_architecture_copy_or_camera(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)


if __name__ == "__main__":
    unittest.main()
