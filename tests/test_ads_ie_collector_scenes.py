"""Offline scene, saved-pack and physical-evidence contracts; no image generation."""
import json
from pathlib import Path
import unittest

import ads_page as ads
import sports_cave_physical_realism as physical
from sports_cave_prompt_blocks import append_sports_cave_image_realism_rules


class CollectorSceneTests(unittest.TestCase):
    def visuals(self, token="scene-example", **kwargs):
        kwargs.setdefault("country", "Australia")
        return ads.resolve_standard_instant_experience_visuals(
            product_name="Collector Print", category="Cricket", variation_token=token, **kwargs)

    def prompt(self, visual, index):
        return ads.build_standard_instant_experience_image_prompt(
            index, visual, product_name="Collector Print", category="Cricket", country="Australia")

    def test_copy_and_cameras_match_twenty_pre_edit_inputs(self):
        # Recorded before editing the approved base, including prior headline-fit upgrade.
        rows = json.loads((Path(__file__).parent / "fixtures/ie_collector_scenes_copy_baseline.json").read_text(encoding="utf8"))
        for row in rows:
            with self.subTest(inputs=row["kw"]):
                actual = ads.resolve_standard_instant_experience_visuals(**row["kw"])
                self.assertEqual([{k: v.get(k) for k in row["copy"][i]}
                                  for i, v in enumerate(actual)], row["copy"])

    def test_eighty_fresh_packs_keep_roles_and_vary_every_scene_dimension(self):
        seen = [{k: set() for k in ("room_type", "wall_colour", "architectural_cue", "primary_cue", "lighting")} for _ in range(3)]
        for token in map(str, range(80)):
            rows = self.visuals(token)
            self.assertEqual(rows, self.visuals(token))
            self.assertEqual([v["room_profile_key"] for v in rows],
                             ["hallway_gallery", "minimal_art_wall", "collector_interior"])
            for key in seen[0]:
                self.assertEqual(len({v[key] for v in rows}), 3)
                for i, v in enumerate(rows):
                    seen[i][key].add(v[key])
            self.assertIn("visible passage depth", rows[0]["scene_brief"])
            self.assertIn("exactly one understated architectural glimpse", rows[1]["scene_brief"])
            self.assertIn("Neither a hallway nor a nearly empty wall", rows[2]["scene_brief"])
        self.assertTrue(all(len(values) >= 5 for slot in seen for values in slot.values()))

    def test_recent_history_is_used_consistently_by_all_prompt_entry_points(self):
        first = self.visuals()
        recent = [ads.standard_instant_experience_fingerprint(i, v) for i, v in enumerate(first, 1)]
        fresh = self.visuals("next-pack", recent_fingerprints=recent)
        self.assertTrue(all(a["room_type"] != b["room_type"] for a, b in zip(first, fresh)))
        kwargs = dict(product_name="Collector Print", category="Cricket", variation_token="next-pack", recent_fingerprints=recent, country="Australia")
        fps = ads.build_standard_instant_experience_fingerprints(**kwargs)
        self.assertEqual([f["room_type"] for f in fps], [v["room_type"] for v in fresh])
        for builder in (ads.build_standard_instant_experience_visual_prompts,
                        ads.build_standard_instant_experience_group_output_contract):
            prompt = builder(**kwargs)
            for v in fresh:
                self.assertIn(v["scene_brief"], prompt)

    def test_explicit_scene_selections_and_reopened_prompt_remain_stable(self):
        selected = {"wall_colour": "saved pale blue", "wall_finish": "saved fine lime plaster",
                    "primary_cue": "one saved chair edge", "lighting": "saved diffused morning light"}
        metadata = {"instant_experience_scene_selections": [{}, selected, {}]}
        for token in ("one", "two"):
            visual = self.visuals(token, product_metadata=metadata)[1]
            for key, value in selected.items():
                self.assertEqual(visual[key], value)
        result = ads.build_ads_result_record("Collector Print", "Cricket", "Australia", "Instant Experience",
            variation_token="saved", product_metadata=metadata)
        self.assertIs(ads.ensure_current_ads_result_prompt(result), result)
        edited = {**result, "master_prompt": result["master_prompt"].replace("saved pale blue", "edited pale green")}
        self.assertIs(ads.ensure_current_ads_result_prompt(edited), edited)

    def test_category_scene_suggestions_do_not_conflict_with_resolved_pack(self):
        for category in ("Cricket", "Motorsport", "Baseball", "NBA", "Football", "Other"):
            prompt = ads.build_ads_prompt("Collector Print", category, "Australia", "Instant Experience",
                                          variation_token="audit")
            self.assertNotIn("Instant Experience setting:", prompt)
            self.assertNotIn("office as a workspace", prompt)
            self.assertNotIn("bar/lounge as a private entertaining space", prompt)
            for marker in (ads.SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2.splitlines()[0],
                           ads.SPORTS_CAVE_IE_SET_DIFFERENTIATION_RULES_V2,
                           ads.SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2.splitlines()[0]):
                expected = 1 if marker == ads.SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2.splitlines()[0] else 3
                self.assertEqual(prompt.count(marker), expected)

    def test_one_compact_realism_block_survives_metadata_and_shared_enrichment(self):
        metadata = {"frame_specs": {"verified": True, "source": "fixture", "outer_width_cm": 62,
                    "outer_height_cm": 45, "depth_mm": 18, "glazing": "unglazed", "frame_finish": "white"}}
        for i, v in enumerate(self.visuals(product_metadata=metadata), 1):
            prompt = self.prompt(v, i)
            enriched = append_sports_cave_image_realism_rules(prompt, physical_product=metadata)
            self.assertEqual(enriched, prompt)
            self.assertEqual(len(physical.BLOCK.findall(prompt)), 1)
            self.assertEqual(prompt.count("PRODUCT LOCK — ABSOLUTE"), 1)
            self.assertIn('"glazing": "unglazed"', prompt)
            self.assertIn('"frame_finish": "white"', prompt)
            self.assertIn('"width_cm": 62.0', prompt)
            self.assertIn("Never add glazing to known unglazed", prompt)
            self.assertNotIn("slim-to-medium black timber", prompt)
            for obsolete in ("office as a workspace", "bar/lounge as a private entertaining space",
                             "private drinks cabinet or bar shelf", "MANDATORY SEAMLESS WALL SYSTEM"):
                self.assertNotIn(obsolete, prompt)


if __name__ == "__main__":
    unittest.main()
