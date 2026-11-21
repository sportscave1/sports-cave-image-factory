from tests.ads_prompt_contracts import current_ie, saved_ie, scenes_ie, copy_styles, refresh_contract
"""Verify executable prompt contracts and real CSVs, without calling an image model."""
import csv
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import ads_page as ads
import sports_cave_physical_realism as physical


HEADERS = "schema_version,campaign_type,output_mode,route_key,route_label,variation,description_key,description_label,primary_text,headline,cta".split(",")


class CombinedExecutionTests(unittest.TestCase):
    def record(self, token="integration", category="Cricket", metadata=None, country="Australia", recent=()):
        return ads.build_ads_result_record("Collector Cricket Print", category, country, "Instant Experience",
            product_url="https://example.com/products/collector", variation_token=token,
            product_metadata=metadata or {"edition_limit": 100}, recent_instant_experience_fingerprints=recent)

    def test_sequence_is_three_independent_calls_then_completed_csv_and_setup(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        current_ie(self)

    def test_execution_priority_is_shared_with_project_template_and_text_only_gate(self):
        template = (Path(ads.__file__).parent / "prompts" / "sports_cave_universal_creative_system.txt").read_text(encoding="utf-8").strip()
        priority = ads.build_ads_execution_priority()
        self.assertTrue(template.startswith(priority))
        prompt = self.record()["master_prompt"]
        from ads_generation_review import REVIEW_UPDATES
        for old, new in REVIEW_UPDATES:
            priority = priority.replace(old, new)
        self.assertEqual(prompt.count(priority), 1)
        self.assertNotIn("COPY-ONLY OR PROMPT-ONLY REQUESTS", prompt)
        for campaign in ("Carousel", "Instant Experience", "Single Image / Video"):
            gate = ads.build_ads_text_first_image_generation_gate(campaign)
            self.assertIn(template, gate)
            self.assertIn("Apply the remainder of this gate only to copy-only or prompt-only requests", gate)
            self.assertIn("skip this gate and its approval question entirely", gate)
            self.assertNotIn("Your first response must be text and planning only", gate)
            self.assertNotIn("even if this Ads prompt contains", gate)
            self.assertNotIn("Then wait for explicit approval before generating anything", gate)

    def test_combined_authorisation_recovers_attachments_and_never_requires_a_reply(self):
        prompt = self.record()["master_prompt"]
        for required in (
            "begin the requested generation workflow immediately",
            "explicit authorisation for every requested image and downloadable CSV",
            "output format and image count take precedence over generic carousel defaults",
            "Read the supplied references and resolve copy internally",
            "try the available attachment location",
            "Once access succeeds, automatically resume the original task",
            "An access confirmation is not task completion",
            "Do not stop at acknowledging the request, confirming attachment access",
            "additional approval between outputs",
            "Never claim an image or CSV exists unless it was created",
        ):
            self.assertIn(required, prompt)
        for obsolete in ("all five image prompts", "Only generate a mockup when", "Would you like me to generate Card 1?",
                         "CARD 4 IMAGE GENERATION PROMPT", "CARD 5 IMAGE GENERATION PROMPT", "first text-only response"):
            self.assertNotIn(obsolete, prompt)

    def test_shared_template_is_unchanged_and_expanded_for_each_call(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        current_ie(self)

    def test_automatic_wall_palettes_and_minimal_architectural_glimpses(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        scenes_ie(self)

    def test_explicit_wall_override_is_preserved_and_metadata_is_consistent(self):
        metadata = {"instant_experience_scene_selections": [{}, {"wall_colour": "explicit pink mineral paint"}, {}]}
        for token in ("first", "second"):
            rows = ads.resolve_standard_instant_experience_visuals(product_name="Collector", category="MMA",
                product_metadata=metadata, variation_token=token)
            self.assertEqual(rows[1]["wall_colour"], "explicit pink mineral paint")
            self.assertEqual(rows[1]["wall_finish"], "explicit pink mineral paint")
            self.assertIn("explicit pink mineral paint", rows[1]["scene_brief"])

    def test_exhausted_scene_library_uses_oldest_available_fingerprint(self):
        library = ads.ie_visuals.scene_library
        old = library.select("old", {})
        new = library.select("new", {}, old)
        # Constrain to six known compatible candidates to force finite exhaustion.
        pools = tuple((new[i], old[i]) for i in range(3))
        with patch.object(library, "SCENES", pools):
            selected = library.select("exhausted", {}, new + old)
        self.assertGreater(selected[0]["history_exclusions_relaxed"], 0)
        self.assertTrue(all(s["scene_signature"] not in {n["scene_signature"] for n in new} for s in selected))
        for a, b in ((0, 1), (0, 2), (1, 2)):
            self.assertTrue(library.different(selected[a], selected[b]))

    def test_market_history_and_saved_results_are_stable(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        saved_ie(self)

    def test_previous_complete_prompts_and_approved_copy_are_not_migrated(self):
        current = self.record()
        old_prompt = "\n".join([ads.ie_copy.VERSION, ads.ie_visuals.VERSION,
            *[v["group_heading"] for v in ads.resolve_standard_instant_experience_visuals()],
            *([ads.build_instant_experience_fixed_opaque_footer_rules()] * 3)])
        old = {**current, "master_prompt": old_prompt, "generated_ad_output": "Approved saved wording", "prompt_contract_version": "previous"}
        with patch("ads_page.build_ads_result_record", side_effect=AssertionError("must not regenerate")):
            self.assertIs(ads.ensure_current_ads_result_prompt(old), old)

    def test_csv_contract_and_unicode_multiline_rows_round_trip(self):
        result = self.record()
        samples = json.loads((Path(__file__).parent / "fixtures/ie_description_samples.json").read_text(encoding="utf8"))[0]["descriptions"]
        samples[0] = "This isn’t just wall art. It’s the player you back.\n\n" + samples[0]
        samples[0] += '\nA "personal, lasting" connection — yours.'
        notes = {key: [{"primary_text": text, "headline": "A Collector’s Connection", "cta": values[3]}]
                 for (key, values), text in zip(ads.ie_copy.ROUTES.items(), samples)}
        data = ads.build_instant_experience_copy_csv(result, concept_notes=notes)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", data)
        self.assertIn(b'""personal, lasting""', data)
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        self.assertEqual(reader.fieldnames, HEADERS)
        rows = list(reader)
        self.assertEqual([r["route_key"] for r in rows], list(ads.ie_copy.ROUTES))
        self.assertTrue(all(all(row.values()) for row in rows))
        for row in rows:
            self.assertEqual((row["schema_version"], row["campaign_type"], row["output_mode"], row["variation"], row["description_key"]),
                             ("2", "instant_experience", "three_visual_copy_v2", "1", "legacy_standard"))
        parsed = ads.parse_instant_experience_copy_csv(data, result)
        self.assertEqual([parsed[k][0]["primary_text"] for k in ads.ie_copy.ROUTES], samples)
        contract = ads.build_instant_experience_completed_csv_contract()
        self.assertIn(",".join(HEADERS), contract)
        for required in ("create and attach a real ad_copy.csv", "UTF-8 with BOM", "CRLF", "same final copy records",
                         "provide the completed CSV text", "without claiming an attachment", "do not assume it can fetch"):
            self.assertIn(required, contract)

    def test_individual_copy_action_remains_a_standalone_one_image_prompt(self):
        row = ads.resolve_standard_instant_experience_visuals(product_name="Collector", category="Cricket")[0]
        prompt = ads.build_standard_instant_experience_image_prompt(1, row, product_name="Collector", category="Cricket", country="Australia")
        self.assertIn("Generate this one ad image", prompt)
        self.assertIn(ads.build_instant_experience_fixed_opaque_footer_rules(), prompt)
        self.assertNotIn(ads.ADS_IE_COMBINED_EXECUTION_VERSION, prompt)
        self.assertNotIn("ad_copy.csv", prompt)


if __name__ == "__main__":
    unittest.main()
