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
        for refresh in (False, True):
            record = self.record(refresh=refresh)
            rows = record["instant_experience_fingerprints"]
            self.assertEqual(len(rows), 3)
            self.assertEqual(len({r["collector_detail_family"] for r in rows}), 3)
            for slot, row in enumerate(rows):
                self.assertIn((row["collector_detail"], row["collector_detail_family"]), scenes.COLLECTOR_DETAILS[slot])
                self.assertEqual(row["furniture_cue"], row["collector_detail"])
                self.assertIn(row["collector_detail"], row["primary_cue"])
                self.assertIn(row["primary_cue"], record["master_prompt"])
                self.assertNotRegex(row["architectural_cue"], "window seat|bench edge|reading bench|seating silhouette|furniture silhouette")
            prompt = record["master_prompt"]
            for phrase in ("No decorative plants, flowers or vases", "Never widen the shot, shrink the edition",
                           "real supporting surface", "outdoor greenery through a window",
                           "prominent alcohol branding", "replacing the previous peripheral cue"):
                self.assertIn(phrase, prompt)
            self.assertNotIn("restrained dark timber console/joinery", prompt)
            self.assertNotIn("resolved leather media lounge, pool-table corner or restrained home-bar joinery", prompt)

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
        for refresh in (False, True):
            record = self.record(refresh=refresh)
            saved = json.loads(json.dumps(record))
            self.assertIs(ads.ensure_current_ads_result_prompt(saved), saved)
            rebuilt = self.record("different", record["instant_experience_fingerprints"],
                                  saved["product_metadata"], refresh)
            for field in ("instant_experience_scene_selections", "instant_experience_footer_selections"):
                self.assertEqual(record["product_metadata"][field], rebuilt["product_metadata"][field])
            for a, b in zip(record["instant_experience_fingerprints"], rebuilt["instant_experience_fingerprints"]):
                self.assertEqual(a["primary_cue"], b["primary_cue"])
                self.assertIn(a["primary_cue"], rebuilt["master_prompt"])

    def test_legacy_saved_packs_are_not_restyled(self):
        for refresh in (False, True):
            with patch.object(scenes, "resolve_collector_details"):
                record = self.record(refresh=refresh)
            original = copy.deepcopy(record)
            self.assertIs(ads.ensure_current_ads_result_prompt(record), record)
            self.assertEqual(record, original)
            rebuilt = self.record(metadata=record["product_metadata"], refresh=refresh)
            self.assertEqual(record["master_prompt"], rebuilt["master_prompt"])
            self.assertEqual(record["product_metadata"]["instant_experience_scene_selections"],
                             rebuilt["product_metadata"]["instant_experience_scene_selections"])
            self.assertFalse(any("collector_detail" in r for r in rebuilt["instant_experience_fingerprints"]))

    def test_only_peripheral_fields_change_not_architecture_copy_or_camera(self):
        for refresh in (False, True):
            with patch.object(scenes, "resolve_collector_details"):
                before = self.record(refresh=refresh)
            after = self.record(refresh=refresh)
            allowed = {"collector_detail", "collector_detail_family", "primary_cue", "furniture_cue",
                       "residential_cue_family", "architectural_cue", "scene_signature", "room_materials"}
            for a, b in zip(before["instant_experience_fingerprints"], after["instant_experience_fingerprints"]):
                for key in set(a) | set(b):
                    if key not in allowed:
                        self.assertEqual(a.get(key), b.get(key), key)
            self.assertEqual(before["product_metadata"]["instant_experience_footer_selections"],
                             after["product_metadata"]["instant_experience_footer_selections"])


if __name__ == "__main__":
    unittest.main()
