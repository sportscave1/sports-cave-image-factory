"""Fresh headline rotation and immutable saved-pack contracts."""
import copy
import unittest
import ads_page as ads
import ads_ie_visual_systems as words

APPROVED = (
    "Limited to 100 Editions", "Only 100 Will Ever Exist",
    "Only 100 Editions Available", "Limited to 100 Worldwide",
    "100 Edition Collector Run",
)

class FiveHeadlinesTests(unittest.TestCase):
    def record(self, token="six-headlines", recent=(), metadata=None, refresh=False):
        return ads.build_ads_result_record("Volkanovski", "MMA", "Australia", "Instant Experience",
            variation_token=token, product_metadata=metadata or {"edition_limit":100},
            recent_instant_experience_fingerprints=recent,
            creative_refresh_context={"winning_primary_text":"Winner text", "winning_headline":"Winner headline"} if refresh else None)

    def test_exact_bank_and_both_paths_use_distinct_headlines(self):
        self.assertEqual(words.HEADLINES, APPROVED)
        for refresh in (False, True):
            first = self.record(refresh=refresh)
            second = self.record("next", first["instant_experience_fingerprints"], refresh=refresh)
            sets = []
            for record in (first, second):
                heads = {r["headline_text"] for r in record["instant_experience_fingerprints"]}
                self.assertEqual(len(heads), 3)
                self.assertTrue(heads <= set(APPROVED))
                sets.append(heads)
                for h in heads:
                    self.assertIn("HEADLINE: " + h, record["master_prompt"])
            self.assertNotEqual(sets[0], sets[1])

    def test_five_options_rotate_over_many_packs_and_reopen_verbatim(self):
        history = []
        used = set()
        for i in range(12):
            record = self.record(str(i), history)
            selections = record["product_metadata"]["instant_experience_footer_selections"]
            used.update(s["headline_text"] for s in selections)
            rebuilt = self.record("different", history, record["product_metadata"])
            self.assertEqual(selections, rebuilt["product_metadata"]["instant_experience_footer_selections"])
            self.assertIs(ads.ensure_current_ads_result_prompt(record), record)
            history = record["instant_experience_fingerprints"] + history
        self.assertEqual(used, set(APPROVED))

    def test_legacy_or_duplicate_selections_upgrade_once_and_stay_fixed(self):
        for headline in ("FOR YOUR COLLECTION", "STRICTLY LIMITED TO 100 EDITIONS", APPROVED[0]):
            for refresh in (False, True):
                record = self.record(refresh=refresh)
                metadata = copy.deepcopy(record["product_metadata"])
                for saved in metadata["instant_experience_footer_selections"]:
                    saved["headline_text"] = saved["headline_fit_fallback"] = headline
                    saved["eligible_headline_alternatives"] = ["FOR YOUR COLLECTION"]
                rebuilt = self.record(metadata=metadata, refresh=refresh)
                selected = rebuilt["product_metadata"]["instant_experience_footer_selections"]
                self.assertEqual(len({s["headline_text"] for s in selected}), 3)
                self.assertTrue(all(s["headline_text"] in APPROVED for s in selected))
                self.assertNotIn("FOR YOUR COLLECTION", rebuilt["master_prompt"])
                reopened = self.record("other", metadata=rebuilt["product_metadata"], refresh=refresh)
                self.assertEqual(selected, reopened["product_metadata"]["instant_experience_footer_selections"])

    def test_exports_keep_assignments_and_mandatory_number_emphasis(self):
        for refresh in (False, True):
            result = self.record(refresh=refresh)
            rows = ads.resolve_standard_instant_experience_visuals(
                product_name="Volkanovski", category="MMA", country="Australia",
                variation_token="different", product_metadata=result["product_metadata"])
            for index, row in enumerate(rows, 1):
                prompt = ads.build_standard_instant_experience_image_prompt(
                    index, row, product_name="Volkanovski", category="MMA", country="Australia")
                expected = result["product_metadata"]["instant_experience_footer_selections"][index-1]["headline_text"]
                self.assertIn("HEADLINE: " + expected, prompt)
                self.assertIn("CTA: CLAIM YOUR EDITION", prompt)
                self.assertIn("Always highlight all three digits of 100", prompt)
                self.assertIn("18–20%", prompt)
                self.assertNotIn("SUPPORTING LINE:", prompt)
                self.assertNotIn("FOR YOUR COLLECTION", prompt)
                self.assertEqual(row["eligible_headline_alternatives"], [])

    def test_no_normalisation_or_fallback_headline(self):
        for text in ("FOR YOUR COLLECTION", APPROVED[0].upper(), "invented headline", "x"*100):
            with self.assertRaises(ValueError):
                ads.shorten_instant_experience_on_image_headline(text, fallback=APPROVED[0])
        for text in APPROVED:
            self.assertEqual(ads.shorten_instant_experience_on_image_headline(text), text)

    def test_owner_policy_overrides_missing_or_legacy_edition_metadata(self):
        for limit in (100, 25, None):
            metadata = ads.instant_experience_product_metadata_from_selection(
                {"row": {"edition_limit": limit}}, category="Baseball")
            self.assertEqual(metadata["edition_limit"], 100)
            self.record(metadata=metadata)

    def test_stale_prompt_upgrade_removes_legacy_bank_and_preserves_rooms(self):
        record = self.record()
        stale = copy.deepcopy(record)
        stale["prompt_contract_version"] = "old-six-headline-bank"
        stale["master_prompt"] = stale["master_prompt"].replace(words.VERSION, "OLD VERSION")
        stale["generated_ad_output"] = stale["master_prompt"]
        for selection in stale["product_metadata"]["instant_experience_footer_selections"]:
            selection["headline_text"] = "FOR YOUR COLLECTION"
        updated = ads.ensure_current_ads_result_prompt(stale)
        self.assertEqual(record["product_metadata"]["instant_experience_scene_selections"],
                         updated["product_metadata"]["instant_experience_scene_selections"])
        self.assertNotIn("FOR YOUR COLLECTION", updated["master_prompt"])
        self.assertEqual(ads.creation_instructions(updated["master_prompt"]), updated["master_prompt"])
        self.assertIs(ads.ensure_current_ads_result_prompt(updated), updated)

    def test_fewer_than_three_fit_options_cannot_repeat_to_fill_pack(self):
        visuals = [{"resolved_seed":"test"} for _ in range(3)]
        with self.assertRaises(ValueError):
            words.resolve_set_copy(visuals, {"edition_limit":100}, lambda h: h == APPROVED[0])

if __name__ == "__main__":
    unittest.main()
