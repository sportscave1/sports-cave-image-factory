import unittest

import ads_page as ads
import ads_ie_legacy_description as legacy


class LegacyDescriptionTests(unittest.TestCase):
    def record(self):
        return ads.build_ads_result_record(
            "Collector Athlete", "Cricket", "Australia", "Instant Experience",
            variation_token="legacy-style", product_metadata={"edition_limit": 100},
            creative_refresh_context={"winning_primary_text": "This isn't wall art.\nA collector's memory.", "winning_headline": "Remember The Winning Moment"},
        )

    def test_actual_result_restores_three_historical_styles_without_extra_rows(self):
        result = self.record()
        text = result["master_prompt"]
        self.assertEqual(text, result["generated_ad_output"])
        self.assertEqual(text.count(legacy.VERSION), 1)
        for phrase in ("Legacy Standard:", "Framed Greatness:", "Choose a Side:",
                       '"This isn\'t wall art."', "Greatness doesn't fade. It gets framed.",
                       '"Secure yours."', "A two-line ownership challenge.",
                       "ARTWORK_TYPE or RELATIONSHIP_TYPE verifies rivalry/opposition",
                       "You know the name.", "Wrong question."):
            self.assertIn(phrase, text)
        self.assertIn("For EACH creative return exactly ONE Primary Text / Description and ONE Headline", text)
        self.assertIn("Return exactly THREE data rows", text)
        self.assertIn("Exactly three complete ad combinations total", text)
        self.assertIn("one Instant Experience description", text)
        self.assertNotIn("Description 2 —", text)
        self.assertNotIn("Description 3 —", text)
        self.assertNotIn("COPY VARIATIONS", text)
        self.assertNotIn("WHY BUY NOW", text)
        self.assertNotIn("Explain why this specific product matters", text)
        self.assertIn("Preserve the winning hook, tone, structure", text)
        self.assertIn("do not force a different framework", text)
        csv_text = ads.build_instant_experience_copy_csv(result, blank=True).decode("utf-8-sig")
        self.assertIn(csv_text, text)
        self.assertEqual(len(csv_text.splitlines()), 4)

    def test_version_refreshes_cached_prompt_preserving_completed_copy(self):
        current = self.record()
        stale = {**current, "prompt_contract_version": current["prompt_contract_version"].replace("; " + legacy.VERSION, ""),
                 "master_prompt": "Previous generic instructions", "generated_ad_output": "Completed winning copy"}
        rebuilt = ads.ensure_current_ads_result_prompt(stale)
        self.assertIn(legacy.VERSION, rebuilt["master_prompt"])
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
