import unittest
import csv
import io

import ads_page as ads
import ads_ie_legacy_description as legacy


class LegacyDescriptionTests(unittest.TestCase):
    def record(self):
        return ads.build_ads_result_record(
            "Collector Athlete", "Cricket", "Australia", "Instant Experience",
            variation_token="legacy-style", product_metadata={"edition_limit": 100},
            creative_refresh_context={"winning_primary_text": "This isn't wall art.\nA collector's memory.", "winning_headline": "Remember The Winning Moment"},
        )

    def test_winner_refinement_keeps_three_pairs_without_forcing_historical_styles(self):
        result = self.record()
        text = result["master_prompt"]
        self.assertEqual(text, result["generated_ad_output"])
        self.assertNotIn(legacy.VERSION, text)
        self.assertIn("Create THREE refreshed creatives", text)
        self.assertIn("ONE copy pair per permanent slot, variation=1, output_mode=winner_refinement", text)
        self.assertIn("This isn't wall art.\nA collector's memory.", text)
        self.assertIn("Remember The Winning Moment", text)
        self.assertIn("retaining the winner's underlying emotional/collector appeal", text)
        for framework in ('Framed Greatness:', 'Choose a Side:', 'A two-line ownership challenge.'):
            self.assertNotIn(framework, text)
        self.assertNotIn("Description 2 —", text)
        self.assertNotIn("Description 3 —", text)
        self.assertNotIn("COPY VARIATIONS", text)
        self.assertNotIn("WHY BUY NOW", text)
        self.assertNotIn("Explain why this specific product matters", text)
        csv_text = ads.build_instant_experience_copy_csv(result, blank=True).decode("utf-8-sig")
        self.assertIn(csv_text.replace('\r\n', '\n').strip(), text.replace('\r\n', '\n'))
        self.assertEqual(len(csv_text.splitlines()), 4)
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual([row['route_key'] for row in rows], [concept['id'] for concept in ads.INSTANT_EXPERIENCE_CONCEPTS])
        self.assertTrue(all(row['output_mode'] == 'winner_refinement' and row['variation'] == '1' for row in rows))

    def test_version_refreshes_cached_prompt_preserving_completed_copy(self):
        current = self.record()
        stale = {**current, "prompt_contract_version": 'historical IE copy contract',
                 "master_prompt": "Previous generic instructions", "generated_ad_output": "Completed winning copy"}
        rebuilt = ads.ensure_current_ads_result_prompt(stale)
        self.assertIn('Create THREE refreshed creatives', rebuilt["master_prompt"])
        self.assertNotIn(legacy.VERSION, rebuilt["master_prompt"])
        self.assertEqual(rebuilt["generated_ad_output"], "Completed winning copy")
        for key in ("context_key", "product_metadata", "creative_refresh_context", "variation_token"):
            self.assertEqual(current[key], rebuilt[key])
        self.assertIs(ads.ensure_current_ads_result_prompt(rebuilt), rebuilt)

    def test_new_ads_and_other_campaigns_do_not_receive_refresh_style_override(self):
        for kind in ("Instant Experience", "Carousel", "Single Image / Video"):
            text = ads.build_ads_prompt("Collector Athlete", "Cricket", "Australia", kind)
            self.assertNotIn(legacy.VERSION, text)


if __name__ == "__main__":
    unittest.main()
