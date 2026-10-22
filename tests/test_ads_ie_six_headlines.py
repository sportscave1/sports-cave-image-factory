"""Fresh headline rotation and immutable saved-pack contracts."""
import copy
import unittest
import ads_page as ads
import ads_ie_visual_systems as words

APPROVED = (
    "STRICTLY LIMITED TO 100 EDITIONS", "ONLY 100 EDITIONS AVAILABLE",
    "LIMITED EDITION — 100 ONLY", "ONLY 100 AVAILABLE",
    "LIMITED TO 100 EDITIONS", "100 EDITIONS ONLY",
)

class SixHeadlinesTests(unittest.TestCase):
    def record(self, token="six-headlines", recent=(), metadata=None, refresh=False):
        return ads.build_ads_result_record("Volkanovski", "MMA", "Australia", "Instant Experience",
            variation_token=token, product_metadata=metadata or {"edition_limit":100},
            recent_instant_experience_fingerprints=recent,
            creative_refresh_context={"winning_primary_text":"Winner text", "winning_headline":"Winner headline"} if refresh else None)

    def test_exact_bank_and_both_paths_use_disjoint_next_pack(self):
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
            self.assertFalse(sets[0] & sets[1])

    def test_six_options_rotate_over_many_packs_and_reopen_verbatim(self):
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

    def test_existing_saved_repeated_and_legacy_headlines_are_not_replaced(self):
        for headline in ("STRICTLY LIMITED TO 100 EDITIONS", "LIMITED TO 100 WORLDWIDE"):
            for refresh in (False, True):
                record = self.record(refresh=refresh)
                metadata = copy.deepcopy(record["product_metadata"])
                for saved in metadata["instant_experience_footer_selections"]:
                    saved["headline_text"] = saved["headline_fit_fallback"] = headline
                rebuilt = self.record(metadata=metadata, refresh=refresh)
                self.assertEqual(metadata["instant_experience_footer_selections"],
                                 rebuilt["product_metadata"]["instant_experience_footer_selections"])
                self.assertIs(ads.ensure_current_ads_result_prompt(rebuilt), rebuilt)

    def test_fewer_than_three_fit_options_cannot_repeat_to_fill_pack(self):
        visuals = [{"resolved_seed":"test"} for _ in range(3)]
        with self.assertRaises(ValueError):
            words.resolve_set_copy(visuals, {"edition_limit":100}, lambda h: h == APPROVED[0])

if __name__ == "__main__":
    unittest.main()
