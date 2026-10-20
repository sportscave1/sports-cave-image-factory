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
        prompt = self.record()["master_prompt"]
        steps = ("1. Resolve all three scenes and final copy", "2. Generate Image 1 (RIGHT angle)",
                 "3. Immediately generate Image 2 (STRAIGHT ON)", "4. Immediately generate Image 3 (LEFT angle)",
                 "5. Create and attach the completed downloadable ad_copy.csv", "6. Provide the existing shared Instant Experience setup")
        positions = [prompt.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(prompt.count("\nIMAGE GENERATION PROMPT\n"), 3)
        self.assertEqual(prompt.count("\nAD COPY\n"), 3)
        for expected in ("ORIGINAL product reference", "without asking for \"next\"", "no collage or triptych",
                         "at most one correction call per image", "preserve completed outputs", "Never claim pixel fidelity"):
            self.assertIn(expected, prompt)
        for obsolete in ("Do not generate images", "do not generate images", "first text-only response",
                         "FINAL RESPONSE TERMINATION", "no automatic image generation", "Do not generate the image automatically",
                         "LOCKED SPORTS CAVE LEGACY COPY FRAMEWORKS", "COPY ONE ROUTE AT A TIME"):
            self.assertNotIn(obsolete, prompt)
        self.assertLess(len(prompt), 42000)  # Resolved construction/reflection and richer home specifications.

    def test_execution_priority_is_shared_with_project_template_and_text_only_gate(self):
        template = (Path(ads.__file__).parent / "prompts" / "sports_cave_universal_creative_system.txt").read_text(encoding="utf-8").strip()
        priority = ads.build_ads_execution_priority()
        self.assertTrue(template.startswith(priority))
        prompt = self.record()["master_prompt"]
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
        prompt = self.record()["master_prompt"]
        shared = ads.build_instant_experience_shared_template()
        self.assertEqual(prompt.count(shared), 1)
        for rules in (ads.build_instant_experience_fixed_opaque_footer_rules(),
                      ads.build_instant_experience_on_image_copy_fit_rules()):
            self.assertEqual(prompt.count(rules), 1)
            self.assertIn(rules, shared)
        groups = re.findall(r"^GROUP [123] — [^\n]+\n\nIMAGE GENERATION PROMPT\n(.*?)\nAD COPY\n", prompt, re.M | re.S)
        self.assertEqual(len(groups), 3)
        for i, group in enumerate(groups):
            expanded = shared + "\n" + group
            self.assertEqual(expanded.count("PRODUCT LOCK — ABSOLUTE"), 1)
            self.assertEqual(len(physical.BLOCK.findall(expanded)), 1)
            self.assertIn(("RIGHT ANGLE", "CENTRE / STRAIGHT-ON", "LEFT ANGLE")[i], group)
            self.assertIn("CTA: CLAIM YOUR EDITION", group)
            self.assertIn("1024 x 1024", expanded)
            self.assertIn("24–28%", expanded)

    def test_automatic_wall_palettes_and_minimal_architectural_glimpses(self):
        forbidden = re.compile(r"\b(red|pink|rose|salmon|peach|orange|terracotta|ochre)\b", re.I)
        for category in ("MMA", "UFC", "Boxing", "Combat sports", "Cricket", "Football"):
            seen = [set(), set(), set()]
            for token in map(str, range(24)):
                rows = ads.resolve_standard_instant_experience_visuals(product_name="Collector Print", category=category,
                    country="Australia", variation_token=token)
                self.assertEqual([v["camera_role"] for v in rows], ["RIGHT", "FRONT", "LEFT"])
                self.assertEqual(len({v["wall_colour"] for v in rows}), 3)
                for i, v in enumerate(rows):
                    self.assertIsNone(forbidden.search(v["wall_colour"]))
                    seen[i].add(v["room_type"])
                self.assertRegex(rows[1]["primary_cue"], r"doorway|corridor return|window recess|room glimpse")
                self.assertNotRegex(rows[1]["primary_cue"], r"lamp|console|chair")
                if category in {"MMA", "UFC", "Boxing", "Combat sports"}:
                    for i, v in enumerate(rows):
                        self.assertIn(v["wall_colour"], ads.ie_visuals.COMBAT_PALETTES[i])
                self.assertTrue(rows[2]["primary_cue"].startswith("one "))
                self.assertIn("edge", rows[2]["primary_cue"])
            self.assertTrue(all(len(options) >= 4 for options in seen))

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
        first = self.record("first")
        next_pack = self.record("second", recent=first["instant_experience_fingerprints"])
        self.assertNotEqual(first["master_prompt"], next_pack["master_prompt"])
        for old, new in zip(first["instant_experience_fingerprints"], next_pack["instant_experience_fingerprints"]):
            self.assertNotEqual(old["scene_signature"], new["scene_signature"])
        self.assertEqual(self.record("second", recent=first["instant_experience_fingerprints"])["master_prompt"], next_pack["master_prompt"])
        self.assertIs(ads.ensure_current_ads_result_prompt(next_pack), next_pack)
        self.assertEqual(ads.creation_instructions(next_pack["master_prompt"]), next_pack["master_prompt"])
        self.assertIn(ads.META_AD_URL_PARAMETERS, ads.creation_instructions(next_pack["master_prompt"]))
        rows = ads.resolve_standard_instant_experience_visuals(product_name="Collector Cricket Print", category="Cricket",
            country="Australia", variation_token="second", product_metadata={"edition_limit": 100},
            recent_fingerprints=first["instant_experience_fingerprints"])
        for row, fp in zip(rows, next_pack["instant_experience_fingerprints"]):
            self.assertEqual(row["room_type"], fp["room_type"])
            self.assertIn(row["scene_brief"], next_pack["master_prompt"])

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
