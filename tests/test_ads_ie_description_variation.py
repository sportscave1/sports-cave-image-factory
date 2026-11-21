from tests.ads_prompt_contracts import current_ie, saved_ie, scenes_ie, copy_styles, refresh_contract
"""Offline planning and actual CSV-text checks; no text/image model or live data."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ads_ie_copy as writing
import ads_page as ads
from tests.test_ads_ie_copy_v2 import CopyV2Tests


FACT = {
    "verified": True,
    "text": "Messi won the Golden Ball at the 2022 FIFA World Cup.",
    "source_url": "https://inside.fifa.com/en/tournaments/mens/worldcup/qatar2022/news/triumphant-argentina-conclude-unprecedented-fifa-world-cup",
    "verified_on": "2026-10-21", "scope": "event",
    "context": "Qatar 2022 tournament award, not a current career record",
}


class DescriptionVariationTests(unittest.TestCase):
    def context(self, product="Lionel Messi World Cup 2022", metadata=None):
        return ads.resolve_instant_experience_description_context(product, "Football",
            product_metadata=metadata or {}, country="Australia")

    def record(self, token="description-check", **kwargs):
        return ads.build_ads_result_record("Lionel Messi World Cup 2022", "Football", "Australia",
            "Instant Experience", variation_token=token, **kwargs)

    def test_twenty_four_fresh_plans_are_distinct_and_deterministic(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)

    def test_approved_facts_keep_provenance_and_fallback_rejects_incomplete_evidence(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)

    def test_instruction_is_one_concise_contract_without_locked_templates(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)

    def test_near_duplicate_check_ignores_shared_scarcity_and_closing_anchors(self):
        a = "The name stays with you.\nA career that gives this artwork its meaning and rewards a collector's lifelong loyalty.\n\nLimited to 100 worldwide.\nSecure yours."
        b = "The moment still matters.\nRecall the tension before the result and why this particular scene belongs in your collection.\n\nLimited to 100 worldwide.\nSecure yours."
        self.assertFalse(writing.similar(a, b))
        self.assertTrue(writing.similar(a, a.replace("lifelong", "enduring")))
        self.assertTrue(writing.quality_errors([a, a.replace("career", "legacy"), b]))
        history = [{"product_name": "Matching", "primary_text": a, "first_sentence_normalized": writing.opening(a)}]
        self.assertTrue(writing.quality_errors([a], "Matching", history))
        self.assertFalse(writing.quality_errors([a], "Another Product", history))
        self.assertFalse(writing.recent_copy("Matching", [{"primary_text": a}]))

    def test_csv_duplicate_rejection_is_transactional_and_saved_import_is_idempotent(self):
        result, workflow = self.record(), {"ad_notes": {}}
        notes = CopyV2Tests().notes()
        keys = list(writing.ROUTES)
        notes[keys[1]][0]["primary_text"] = notes[keys[0]][0]["primary_text"]
        before = copy.deepcopy(workflow)
        with self.assertRaisesRegex(ads.InstantExperienceCopyCSVError, "repeats an opening"):
            ads.apply_instant_experience_copy_csv(result, workflow, ads.build_instant_experience_copy_csv(result, concept_notes=notes))
        self.assertEqual(workflow, before)
        data = ads.build_instant_experience_copy_csv(result, concept_notes=CopyV2Tests().notes())
        ads.apply_instant_experience_copy_csv(result, workflow, data)
        first = copy.deepcopy(workflow["ad_notes"])
        ads.apply_instant_experience_copy_csv(result, workflow, data)
        self.assertEqual(first, workflow["ad_notes"])
        rows = ads.st.session_state[ads.ADS_IE_RECENT_FINGERPRINTS_KEY]
        self.assertTrue(any(r.get("primary_text") and r.get("copy_product_key") for r in rows))

    def test_legacy_drafts_and_completed_copy_are_not_rebuilt(self):
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        saved_ie(self)

    def test_twenty_seven_individual_prompts_keep_footer_copy_fit_and_camera_contracts(self):
        baseline = json.loads((Path(__file__).parent / "fixtures/ie_description_image_baseline.json").read_text(encoding="utf8"))
        for row in baseline:
            kw = row["kw"]
            visuals = ads.resolve_standard_instant_experience_visuals(**kw)
            prompts = [ads.build_standard_instant_experience_image_prompt(i, v, product_name=kw["product_name"],
                category=kw["category"], country="Australia") for i, v in enumerate(visuals, 1)]
            for i, prompt in enumerate(prompts):
                self.assertIn(ads.build_instant_experience_fixed_opaque_footer_rules(), prompt)
                self.assertIn(ads.build_instant_experience_on_image_copy_fit_rules(), prompt)
                self.assertIn(visuals[i]["camera_side"], prompt)
                self.assertIn("HEADLINE: " + visuals[i]["headline_text"], prompt)
                self.assertNotIn("SUPPORTING LINE:", prompt)
                self.assertNotIn("\nCTA: CLAIM YOUR EDITION", prompt)
                self.assertIn("FOOTER SECOND LINE (", prompt)
                self.assertEqual(prompt.count("PRODUCT LOCK — ABSOLUTE"), 1)

    def test_six_authored_sample_packs_pass_within_pack_and_recent_text_checks(self):
        # Authored examples exercise lexical checks, not a claim about model output.
        samples = json.loads((Path(__file__).parent / "fixtures/ie_description_samples.json").read_text(encoding="utf8"))
        history = []
        for sample in samples:
            descriptions, product = sample["descriptions"], sample["product_name"]
            self.assertEqual(writing.quality_errors(descriptions, product, history), ())
            for text in descriptions:
                self.assertTrue(40 <= len(text.split()) <= 75, (len(text.split()), text))
            history.extend({"product_name": product, "primary_text": text,
                            "first_sentence_normalized": writing.opening(text)} for text in descriptions)


if __name__ == "__main__":
    unittest.main()
