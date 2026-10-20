"""Attribute-level scene and persistence checks; these do not inspect model pixels."""
import json
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_ie_scenes as library


class CuratedHomeTests(unittest.TestCase):
    def record(self, token="homes", history=(), metadata=None):
        return ads.build_ads_result_record("Alexander Volkanovski Collector", "MMA", "Australia", "Instant Experience",
            variation_token=token, product_metadata=metadata or {"edition_limit": 100},
            recent_instant_experience_fingerprints=history)

    def test_many_packs_have_distinct_settings_values_finishes_and_visible_attributes(self):
        seen = [set(), set(), set()]
        families, treatments = set(), set()
        for token in range(120):
            scenes = self.record(str(token))["instant_experience_fingerprints"]
            self.assertEqual(len({s["home_setting"] for s in scenes}), 3)
            self.assertEqual(len({s["wall_lightness"] for s in scenes}), 3)
            self.assertEqual(len({s["wall_colour_family"] for s in scenes}), 3)
            self.assertEqual(len({s["wall_finish"] for s in scenes}), 3)
            self.assertEqual(len({s["light_family"] for s in scenes}), 3)
            self.assertTrue(any(s["wall_finish"] in {"smooth matte paint", "restrained painted wall panelling", "honed limestone"} for s in scenes))
            for a, b in ((0, 1), (0, 2), (1, 2)):
                self.assertTrue(library.different(scenes[a], scenes[b]))
            for i, s in enumerate(scenes):
                seen[i].add(s["scene_signature"])
                families.add(s["wall_colour_family"])
                treatments.add(s["wall_finish"])
                for key in library.SCENE_FIELDS:
                    self.assertIn(key, s)
        self.assertTrue(all(len(s) > 40 for s in seen))
        self.assertEqual(len(families), 8)
        self.assertEqual(len(treatments), 6)  # Oak is a small architectural accent, not a whole wall.

    def test_history_rejects_actual_combinations_and_near_duplicates_across_products(self):
        history = []
        for token in range(24):
            scenes = self.record(str(token), history)["instant_experience_fingerprints"]
            for s in scenes:
                self.assertFalse(any(library._history_conflict(s, old) for old in history[:library.HISTORY_LIMIT]))
                self.assertEqual(s["history_exclusions_relaxed"], 0)
            history = scenes + history
        # A different token/adjective is not evidence of a new scene.
        current = library.SCENES[0][0]
        old = {**current, "creative_variation_token": "changed", "room_type": "renamed room"}
        self.assertTrue(library._history_conflict(current, old))
        graphite = dict(current, wall_visual_group="grey", wall_colour="graphite", wall_lightness="dark", wall_finish="fine mineral plaster")
        charcoal = dict(graphite, wall_colour="charcoal", wall_lightness="mid", wall_finish="subtle limewash")
        self.assertEqual(library.signature(graphite, near=True), library.signature(charcoal, near=True))

    def test_saved_attributes_survive_json_and_ignore_new_history_or_tokens(self):
        result = self.record()
        reopened = json.loads(json.dumps(result))
        saved = reopened["product_metadata"]["instant_experience_scene_selections"]
        self.assertEqual(len(saved), 3)
        with patch.object(library, "select", side_effect=AssertionError("saved scenes must not redraw")):
            self.assertIs(ads.ensure_current_ads_result_prompt(reopened), reopened)
            rows = ads.resolve_standard_instant_experience_visuals(product_name=result["product_name"], category="MMA",
                country="Australia", product_metadata=reopened["product_metadata"], variation_token="different",
                recent_fingerprints=result["instant_experience_fingerprints"])
        for selected, row in zip(saved, rows):
            for key in library.SCENE_FIELDS:
                if key != "assigned_camera_angle":
                    self.assertEqual(selected[key], row[key], key)
        self.assertEqual(result["master_prompt"], reopened["master_prompt"])
        self.assertEqual(ads.creation_instructions(reopened["master_prompt"]), result["master_prompt"])

    def test_reopened_history_and_session_history_are_bounded_and_combined(self):
        result = self.record()
        another = self.record("another", result["instant_experience_fingerprints"])
        with patch.object(ads.st, "session_state", {ads.ADS_IE_RECENT_FINGERPRINTS_KEY: another["instant_experience_fingerprints"]}):
            combined = ads.recent_instant_experience_scene_history(result)
            self.assertEqual(len(combined), 6)
            self.assertEqual(combined[:3], another["instant_experience_fingerprints"])
            ads.update_recent_instant_experience_fingerprints([dict(combined[0], test_index=i) for i in range(60)])
            self.assertEqual(len(ads.st.session_state[ads.ADS_IE_RECENT_FINGERPRINTS_KEY]), library.HISTORY_LIMIT)

    def test_straight_on_glazing_is_resolved_but_construction_never_changes(self):
        for construction in ("glass", "acrylic", "unglazed"):
            metadata = {"edition_limit": 100, "frame_specs": {"verified": True, "source": "fixture", "glazing": construction}}
            record = self.record(metadata=metadata)
            row = record["instant_experience_fingerprints"][1]
            if construction != "unglazed":
                self.assertIn(row["reflection_source"], row["glazing_treatment"])
            if construction == "unglazed":
                self.assertIn("Verified unglazed: no glazing", row["glazing_treatment"])
            else:
                self.assertIn("subtle but perceptible", row["glazing_treatment"])
                self.assertIn("even straight-on", row["glazing_treatment"])
                self.assertIn(construction, row["glazing_treatment"])
            self.assertIn("Never add glazing to known unglazed", record["master_prompt"])

    def test_reference_isolation_frame_corners_and_real_inspection_are_explicit(self):
        prompt = self.record()["master_prompt"]
        for text in ("Its surrounding wall, lighting and room are not scene references and must not be copied",
                     "Never use a previously generated mockup as the artwork source", "above every outer frame corner",
                     "No competing framed art, trophies, helmets", "individually AND together", "Prompt/schema checks do not establish visual distinction",
                     "at most one correction call per image", "no deterministic Ads footer renderer"):
            self.assertIn(text, prompt)
        self.assertNotIn("Add promotional typography as a deterministic post-production layer", prompt)

    def test_metadata_preferences_guide_selection_without_inventing_team_props(self):
        changed = 0
        for seed in map(str, range(16)):
            baseline = library.select(seed, {})
            guided = library.select(seed, {"product_metadata": {"artwork_colours": "navy ivory"}, "frame_finish": "white", "product_era": "historic"})
            changed += [s["scene_signature"] for s in baseline] != [s["scene_signature"] for s in guided]
            self.assertTrue(all(s["wall_colour"] in {w[0] for w in library.WALLS} for s in guided))
        self.assertGreaterEqual(changed, 4)

    def test_legacy_history_uses_saved_appearance_even_without_a_scene_id(self):
        scene = next(s for s in library.SCENES[0] if s["wall_colour"] == "mineral grey" and s["light_source"] == "courtyard window")
        legacy = {"room_type": "old room name", "wall_colour_family": "graphite plaster", "wall_material": "fine plaster",
                  "lighting_direction": "soft courtyard-window daylight"}
        self.assertTrue(library._history_conflict(scene, legacy))

    def test_fresh_pack_action_dispatches_a_new_pack_without_changing_submit_reuse(self):
        # Exercise only dispatch expressions, never start the app or use live integrations.
        source = Path(ads.__file__).read_text(encoding="utf-8")
        page = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "render_page")
        dispatch = [n for n in ast.walk(page) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id in {"fresh_ie_pack", "submitted"} for t in n.targets)]
        dispatch.sort(key=lambda n: n.lineno)
        class Buttons:
            def __init__(self, pressed): self.pressed = pressed
            def button(self, label, **kw): return label == self.pressed
        for pressed in ("Fresh pack", "Submit", "neither"):
            scope = dict(st=Buttons(pressed), is_google=False, is_creative_refresh=False,
                         campaign_type="Instant Experience", result={"master_prompt": "saved", "campaign_type": "Instant Experience"},
                         creative_refresh_context=None, deliberate_new=False)
            exec(compile(ast.Module(body=dispatch, type_ignores=[]), "ads-dispatch", "exec"), scope)
            self.assertEqual(scope["fresh_ie_pack"], pressed == "Fresh pack")
            self.assertEqual(scope["submitted"], pressed != "neither")
        reuse = next(n.test for n in ast.walk(page) if isinstance(n, ast.If)
                     and "existing_result.get('context_key')" in ast.unparse(n.test))
        for fresh in (True, False):
            value = eval(compile(ast.Expression(reuse), "ads-reuse", "eval"), dict(existing_result={"context_key": "same"}, context_key="same", fresh_ie_pack=fresh))
            self.assertEqual(value, not fresh)

    def test_fresh_pack_uses_existing_draft_isolation_without_inheriting_assets(self):
        old, new = self.record("old"), self.record("new")
        new["input_context_key"] = new["context_key"]
        new["context_key"] += "::pack::" + new["variation_token"]
        old_workflow = {"context_key": old["context_key"], "slots": {"old": {"data": b"old image"}},
                        "ad_notes": {"old": "approved copy"}}
        state = {ads._ads_image_state_key(): old_workflow}
        with patch.object(ads.st, "session_state", state), patch.object(ads, "_new_ads_image_workflow",
                side_effect=lambda r: {"context_key": r["context_key"], "slots": {}, "ad_notes": {}}):
            fresh = ads._reset_ads_image_workflow(new)
        self.assertEqual(fresh["slots"], {})
        self.assertEqual(fresh["ad_notes"], {})
        self.assertIs(state["ads-workflow-drafts"][old["context_key"]], old_workflow)
        self.assertEqual(old_workflow["ad_notes"], {"old": "approved copy"})


if __name__ == "__main__":
    unittest.main()
