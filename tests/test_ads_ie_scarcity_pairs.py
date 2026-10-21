"""Approved-bank pairing/evidence tests; no image generation or live data."""
import json
import unittest

import ads_ie_visual_systems as wording
import ads_refresh_generation as recovered
import ads_page as ads


class ScarcityPairTests(unittest.TestCase):
    def record(self, token="scarcity-pairs", metadata=None, history=()):
        return ads.build_ads_result_record("Alexander Volkanovski Collector", "MMA", "Australia", "Instant Experience",
            product_metadata=metadata if metadata is not None else {"edition_limit": 250}, variation_token=token,
            recent_instant_experience_fingerprints=history)

    def test_restored_options_have_repository_sources(self):
        self.assertEqual(wording.RESTORED_HEADLINES[1:], recovered.IE_REFRESH_FOOTER_HEADLINES)
        self.assertTrue(set(recovered.IE_REFRESH_FOOTER_SUPPORT) <= set(wording.RESTORED_SUPPORT_LINES))
        self.assertTrue(set(wording.SUPPORT_LINES[1:]) <= set(wording.RESTORED_SUPPORT_LINES))
        self.assertIn("LIMITED EDITION", wording.eligible_headlines({"edition_limit": 250}))

    def test_many_verified_packs_have_complementary_scarcity_and_distinct_lines(self):
        for limit in (25, 100, 250):
            for seed in range(24):
                rows = self.record(f"{limit}-{seed}", {"edition_limit": limit})["instant_experience_fingerprints"]
                self.assertEqual(len({r["headline_text"] for r in rows}), 3)
                self.assertEqual(len({r["supporting_line"] for r in rows}), 3)
                for row in rows:
                    head, sub = row["headline_text"], row["supporting_line"]
                    self.assertTrue(wording.coherent_pair(head, sub), (head, sub))
                    self.assertNotEqual(wording.explicit_scarcity(head), wording.explicit_scarcity(sub))
                    self.assertFalse(wording.meaningful_words(head) & wording.meaningful_words(sub))
                    self.assertEqual(ads.validate_instant_experience_on_image_copy(head, sub, row["cta_text"]), ())
                    self.assertEqual(row["cta_text"], "CLAIM YOUR EDITION")
                    if limit != 100:
                        self.assertNotIn("100", head + sub)

    def test_reject_repeated_stems_numbers_and_vague_or_duplicate_claims(self):
        bad = (("LIMITED EDITION", "Own this limited edition."),
               ("ONLY 100 EDITIONS", "Limited to just 100."),
               ("FOR YOUR COLLECTION", "A piece for every collector."),
               ("SPORTS CAVE COLLECTOR", "A rare piece for those who know its meaning."),
               ("FOR YOUR COLLECTION", "The moment lasts. The opportunity won’t."),
               ("LIMITED EDITION", "A rare piece for those who know its meaning."),
               ("BUILT FOR COLLECTORS", "Built as a limited run, not a mass release."))
        for pair in bad:
            self.assertFalse(wording.coherent_pair(*pair), pair)
        self.assertTrue(wording.coherent_pair("FOR YOUR COLLECTION", "Limited to 250 Editions"))
        self.assertTrue(wording.coherent_pair("LIMITED EDITION", "Made for serious collectors."))

    def test_inventory_and_permanence_are_not_inferred_from_edition_size(self):
        base = dict(edition_limit=250)
        for context in (base, {**base, "remaining_editions": 249, "editions_sold": 1},
                        {**base, "remaining_editions": 250, "editions_sold": 1}):
            pool = wording.eligible_headlines(context)
            self.assertFalse(any("AVAILABLE" in h or "EVER" in h or "NO SECOND RUN" in h for h in pool))
        pool = wording.eligible_headlines({**base, "remaining_editions": 250, "editions_sold": 0})
        self.assertIn("ONLY 250 AVAILABLE", pool)
        self.assertNotIn("No second run after sellout.", wording.eligible_support_lines({**base, "retires_when_sold_out": True}))

    def test_verified_status_without_a_number_and_unknown_evidence(self):
        known = self.record(metadata={"is_limited_edition": True})
        for r in known["instant_experience_fingerprints"]:
            self.assertTrue(wording.coherent_pair(r["headline_text"], r["supporting_line"]))
            self.assertNotIn("100", r["headline_text"] + r["supporting_line"])
        unknown = self.record(metadata={})
        self.assertTrue(all(not wording.explicit_scarcity(r["headline_text"] + " " + r["supporting_line"])
                            for r in unknown["instant_experience_fingerprints"]))

    def test_saved_wording_is_not_revalidated_or_rerolled(self):
        result = self.record()
        metadata = json.loads(json.dumps(result["product_metadata"]))
        # An old approved pair remains literal, even if fresh generation rejects it.
        metadata["instant_experience_footer_selections"][0].update(
            headline_text="LIMITED EDITION", supporting_line="Own this limited edition.")
        rebuilt = self.record("different", metadata, result["instant_experience_fingerprints"])
        for old, new in zip(metadata["instant_experience_footer_selections"], rebuilt["product_metadata"]["instant_experience_footer_selections"]):
            for field in ("headline_text", "supporting_line", "cta_text", "eligible_headline_alternatives"):
                self.assertEqual(old[field], new[field])
        reopened = json.loads(json.dumps(result))
        self.assertIs(ads.ensure_current_ads_result_prompt(reopened), reopened)
        self.assertEqual(ads.creation_instructions(reopened["master_prompt"]), result["master_prompt"])

    def test_fit_alternatives_and_both_prompt_paths_use_the_resolved_pair(self):
        result = self.record()
        rows = ads.resolve_standard_instant_experience_visuals(product_name=result["product_name"], category="MMA",
            country="Australia", variation_token="ignored", product_metadata=result["product_metadata"])
        for i, row in enumerate(rows, 1):
            for alternative in row["eligible_headline_alternatives"]:
                self.assertTrue(wording.coherent_pair(alternative, row["supporting_line"]))
            individual = ads.build_standard_instant_experience_image_prompt(i, row,
                product_name=result["product_name"], category="MMA", country="Australia")
            for prompt in (individual, result["master_prompt"]):
                self.assertIn("HEADLINE: " + row["headline_text"], prompt)
                self.assertIn("SUPPORTING LINE: " + row["supporting_line"], prompt)
                self.assertIn("CTA: CLAIM YOUR EDITION", prompt)
                self.assertIn("Never echo meaningful words, stems, numbers", prompt)


if __name__ == "__main__":
    unittest.main()
