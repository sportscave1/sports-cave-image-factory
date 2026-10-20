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
        for product, metadata in (
            ("Lionel Messi World Cup 2022", {"athlete_names": ["Lionel Messi"], "featured_moment": "2022 World Cup", "verified_facts": [FACT]}),
            ("Senna vs Prost Rivalry", {"athlete_names": ["Ayrton Senna", "Alain Prost"], "relationship_type": "Rivals"}),
            ("Peter Brock Six Laps Ahead", {"athlete_names": ["Peter Brock"], "product_era": "historic"}),
        ):
            context, history, seen = self.context(product, metadata), [], set()
            for token in map(str, range(8)):
                plans = writing.cues(product, "Football", "Australia", token, context, history)
                self.assertEqual(plans, writing.cues(product, "Football", "Australia", token, context, history))
                self.assertEqual([p["description_role"] for p in plans], list(writing.ROLES))
                self.assertEqual(len({p["opening_hook_family"] for p in plans}), 3)
                signatures = tuple(p["description_signature"] for p in plans)
                self.assertNotIn(signatures, seen)
                seen.add(signatures)
                history = (plans + history)[:12]

    def test_approved_facts_keep_provenance_and_fallback_rejects_incomplete_evidence(self):
        context = self.context(metadata={"verified_facts": [FACT]})
        plan = writing.cues("Messi", "Football", "Australia", "fact", context)[2]
        self.assertEqual(plan["verified_fact"]["source_url"], FACT["source_url"])
        self.assertEqual(plan["verified_fact"]["verified_on"], "2026-10-21")
        for field in ("verified", "source_url", "verified_on", "scope", "context"):
            bad = {**FACT, field: None}
            self.assertEqual(writing.verified_facts({"verified_facts": [bad]}), [])
        self.assertEqual(writing.verified_facts({"verified_facts": None}), [])
        self.assertEqual(writing.verified_facts({"verified_facts": [{**FACT, "source_url": "javascript:alert(1)"}]}), [])
        self.assertEqual(writing.verified_facts({"verified_facts": [{**FACT, "changing_record": True}]}), [])
        changing = writing.verified_facts({"verified_facts": [{**FACT, "changing_record": True, "as_of": "2022-12-18"}]})
        self.assertEqual(changing[0]["as_of"], "2022-12-18")
        fallback = writing.cues("Historic Title", "Cricket", "UK", "none", {})[2]
        self.assertIsNone(fallback["verified_fact"])
        self.assertIn("no invented record", fallback["supporting_detail"])

    def test_instruction_is_one_concise_contract_without_locked_templates(self):
        text = writing.instructions("Messi", "Football", "Australia", "one", self.context())
        self.assertLess(len(text), 8500)
        for stale in ("LOCKED SPORTS CAVE LEGACY COPY FRAMEWORKS", "always opens", "frameworks and defining hooks unchanged", "Greatness doesn't fade."):
            self.assertNotIn(stale, text)
        for required in ("40–75 words", "at most once per pack", "at most 4 writing passes", "career totals", "at most six words", "omit quantity", "no browsing on page load"):
            self.assertIn(required, text)
        with_limit = self.context(metadata={"edition_limit": 250})
        text = writing.instructions("Messi", "Football", "UK", "one", with_limit)
        self.assertIn("Limited to 250 worldwide.", text)
        baseball = ads.build_ads_prompt("Historic Player", "Baseball", "USA", "Instant Experience")
        self.assertIn("omit quantity and geographic scarcity", baseball)
        self.assertNotIn("LOCKED SPORTS CAVE LEGACY COPY FRAMEWORKS", baseball)

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
        result = self.record()
        legacy = {**result, "master_prompt": result["master_prompt"].replace(writing.VERSION, writing.LEGACY_VERSION).replace(ads.ADS_IE_COMBINED_EXECUTION_VERSION, "").replace(ads.build_instant_experience_fixed_opaque_footer_rules(), ads.build_instant_experience_fixed_opaque_footer_rules() * 3),
                  "prompt_contract_version": "older saved version", "generated_ad_output": "Approved completed copy"}
        with patch("ads_page.build_ads_result_record", side_effect=AssertionError("must not regenerate")):
            self.assertIs(ads.ensure_current_ads_result_prompt(legacy), legacy)
            self.assertIs(ads.ensure_current_ads_result_prompt(result), result)
        plans = result["instant_experience_fingerprints"]
        self.assertEqual([p["description_role"] for p in plans], list(writing.ROLES))

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
                self.assertIn("SUPPORTING LINE: " + visuals[i]["supporting_line"], prompt)
                self.assertIn("CTA: CLAIM YOUR EDITION", prompt)
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
