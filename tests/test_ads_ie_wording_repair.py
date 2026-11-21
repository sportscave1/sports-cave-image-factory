from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
"""Whole exported-prompt, finite wording-bank and CSV consistency regressions."""
import csv
import io
import json
import re
import unittest

import ads_page as ads
import ads_ie_copy as writing
import ads_ie_visual_systems as visuals
import ads_ie_scenes as scenes


SAMPLE_METADATA = {"edition_limit": 100, "edition_limit_source": "offline test fixture; not a live product verification",
                   "athlete_names": ["Alexander Volkanovski"]}
SAMPLE_COPY = (
    ("This isn’t just wall art. It’s who you back.\n\nAlexander Volkanovski belongs where your loyalty is visible. Not as a list of results, but as a name that means something to the fan choosing it.\n\nGive that pride a place in your home.\n\nLimited to 100 editions.\nClaim your edition.", "Back Alexander Volkanovski"),
    ("The anticipation of the next exchange.\nThe attention a fighter can command.\n\nFor the MMA fan, Volkanovski gives that feeling a familiar focus. Keep the subject close and leave room for what following the sport means to you, in a piece chosen for the connection it carries.\n\nLimited to 100 editions.\nBring it home.", "Volkanovski, In Focus"),
    ("A collection says something through the names you keep.\n\nAlexander Volkanovski gives an MMA collection a clear point of connection: a subject chosen because the sport matters to you. A considered choice for the fan building a wall around personal meaning rather than filling a space.\n\nLimited to 100 editions.\nMake it yours.", "Volkanovski For Your Collection"),
)


class WordingRepairTests(unittest.TestCase):
    def record(self, token="volkanovski-repair", history=(), metadata=None):
        return ads.build_ads_result_record("Alex Volkanovski UFC Champion", "MMA", "Australia", "Instant Experience",
            product_url="https://example.com/products/volkanovski", variation_token=token,
            product_metadata=dict(metadata or SAMPLE_METADATA), recent_instant_experience_fingerprints=history)

    def test_whole_export_has_only_fixed_ctas_and_preserves_platform_and_routes(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_all_recovered_words_reachable_with_evidence_and_history_rotation(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        rotated_ie(self)

    def test_claim_gates_and_empty_pools_do_not_invent_alternatives(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        rotated_ie(self)

    def test_exhaustion_is_deterministic_and_lru_does_not_invent_words(self):
        history = []
        for i in range(30):
            r = self.record(str(i), history)
            history = (r["instant_experience_fingerprints"] + history)[:scenes.HISTORY_LIMIT]
        first, second = self.record("exhausted", history), self.record("exhausted", history)
        self.assertEqual(first["master_prompt"], second["master_prompt"])
        pool = set(visuals.eligible_headlines({"edition_limit": 100}))
        self.assertTrue(all(r["headline_text"] in pool for r in first["instant_experience_fingerprints"]))
        old = [r["on_image_headline"] for r in history]
        oldest = max(pool, key=lambda h: old.index(h) if h in old else len(history) + 1)
        self.assertIn(oldest, {r["headline_text"] for r in first["instant_experience_fingerprints"]})

    def test_saved_footer_and_copy_are_stable_across_json_copy_and_new_history(self):
        result = json.loads(json.dumps(self.record()))
        self.assertIs(ads.ensure_current_ads_result_prompt(result), result)
        self.assertEqual(ads.creation_instructions(result["master_prompt"]), result["master_prompt"])
        original = result["product_metadata"]["instant_experience_footer_selections"]
        new_rows = ads.resolve_standard_instant_experience_visuals(product_name=result["product_name"], category="MMA",
            country="Australia", variation_token="changed", product_metadata=result["product_metadata"],
            recent_fingerprints=result["instant_experience_fingerprints"])
        self.assertEqual([{k: r[k] for k in visuals.FOOTER_FIELDS} for r in new_rows], original)

    def test_identity_is_required_once_and_other_descriptions_have_different_messages(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)

    def test_csv_reuses_sample_records_and_keeps_schema_encoding_and_fixed_cta(self):
        result = self.record()
        notes = {key: [dict(primary_text=text, headline=headline, cta="Claim Your Edition")]
                 for key, (text, headline) in zip(writing.ROUTES, SAMPLE_COPY)}
        data = ads.build_instant_experience_copy_csv(result, concept_notes=notes)
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(tuple(rows[0]), ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        self.assertEqual(len(rows), 3)
        parsed = ads.parse_instant_experience_copy_csv(data, result)
        for row, (key, (text, headline)) in zip(rows, zip(writing.ROUTES, SAMPLE_COPY)):
            self.assertEqual(row["primary_text"], text)
            self.assertEqual(row["headline"], headline)
            self.assertEqual(row["cta"], "Claim Your Edition")
            self.assertEqual(parsed[key][0]["primary_text"], text)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", data)
        notes[next(iter(writing.ROUTES))][0]["cta"] = "Secure Your Edition"
        with self.assertRaises(ads.InstantExperienceCopyCSVError):
            ads.build_instant_experience_copy_csv(result, concept_notes=notes)

    def test_legacy_saved_copy_is_not_automatically_changed(self):
        result = self.record()
        old = {**result, "master_prompt": result["master_prompt"].replace(writing.IDENTITY_CONTRACT, ""),
               "generated_ad_output": "Approved saved copy"}
        self.assertIs(ads.ensure_current_ads_result_prompt(old), old)
        self.assertEqual(old["generated_ad_output"], "Approved saved copy")
        notes = {key: [dict(primary_text=text, headline=headline, cta=cta)]
                 for key, (text, headline), cta in zip(writing.ROUTES, SAMPLE_COPY, ads.INSTANT_EXPERIENCE_LEGACY_CREATIVE_CTAS)}
        legacy_csv = ads.build_instant_experience_copy_csv(old, concept_notes=notes)
        parsed = ads.parse_instant_experience_copy_csv(legacy_csv, old)
        self.assertEqual([parsed[k][0]["cta"] for k in writing.ROUTES], list(ads.INSTANT_EXPERIENCE_LEGACY_CREATIVE_CTAS))

    def test_camera_definitions_and_each_image_call_have_only_that_cover_copy(self):
        expected = ("RIGHT: camera physically to the right of the artwork, looking left towards it",
                    "FRONT: camera centred, directly facing the artwork",
                    "LEFT: camera physically to the left of the artwork, looking right towards it")
        self.assertEqual(visuals.CAMERAS, expected)
        rows = ads.resolve_standard_instant_experience_visuals(product_name="Volkanovski", category="MMA", product_metadata=SAMPLE_METADATA)
        for i, r in enumerate(rows, 1):
            prompt = ads.build_standard_instant_experience_image_prompt(i, r, product_name="Volkanovski", category="MMA", country="Australia")
            self.assertIn(expected[i - 1], prompt)
            self.assertIn("HEADLINE: " + r["headline_text"], prompt)
            self.assertNotIn("eligible_alternatives", prompt)
            self.assertNotIn("Reserved sibling", prompt)
            for other in rows:
                if other is not r:
                    self.assertNotIn(other["headline_text"], prompt)
                    self.assertNotIn(other["supporting_line"], prompt)

    def test_neutral_wall_contrast_and_partial_saved_choices_shape_automatic_scenes(self):
        sand = next(s for s in scenes.SCENES[0] if s["wall_colour"] == "pale weathered stone")
        taupe = next(s for s in scenes.SCENES[1] if s["wall_colour"] == "smoked earthy taupe")
        self.assertFalse(scenes.different(sand, taupe))
        metadata = {**SAMPLE_METADATA, "instant_experience_scene_selections": [
            {"wall_colour": "warm ivory", "wall_finish": "smooth matte paint"}, {}, {}]}
        r = self.record(metadata=metadata)["instant_experience_fingerprints"]
        self.assertEqual(r[0]["wall_colour"], "warm ivory")
        self.assertEqual(r[0]["wall_finish"], "smooth matte paint")
        for a, b in ((0, 1), (0, 2), (1, 2)):
            self.assertTrue(scenes.different(r[a], r[b]))

    def test_description_plans_do_not_assign_the_same_rhythm_or_close(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        current_ie(self)


if __name__ == "__main__":
    unittest.main()
