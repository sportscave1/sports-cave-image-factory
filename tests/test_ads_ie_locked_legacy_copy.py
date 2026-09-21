import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unittest

import ads_page as ads
import ads_ie_copy as copy
import ads_ie_legacy_description as legacy
from tests.test_ads_page import instant_experience_csv_notes


class LockedLegacyCopyTests(unittest.TestCase):
    def test_actual_public_prompt_assigns_one_framework_to_each_ad_for_all_sports(self):
        for product, sport, word in (("Michael Jordan", "NBA", "basketball"),
                                     ("Jerry Rice", "NFL", "football"),
                                     ("Shane Warne", "Cricket", "cricket"),
                                     ("Six Laps Ahead Peter Brock", "Motorsport", "motorsport"),
                                     ("Winx", "Horse Racing", "racing")):
            with self.subTest(sport=sport):
                result = ads.build_ads_result_record(product, sport, "Australia", "Instant Experience",
                                                     product_metadata={"edition_limit": 100})
                prompt = result["master_prompt"]
                self.assertIn("Made for collectors.", prompt)
                self.assertNotIn(f"Made for {word} collectors.", prompt)
                for key in legacy.NEW_AD_STYLE_KEYS:
                    self.assertIn(key, prompt)
                for line in ("This isn't wall art.", "Greatness doesn't fade.\nIt gets framed.",
                             "Something that actually means something.", "You already know the answer.",
                             "Limited to 100 worldwide.", "Only 100 exist.",
                             "Claim this edition for your collection…\nor leave it for another collector."):
                    self.assertIn(line, prompt)
                grouped = prompt.split("GROUPED INSTANT EXPERIENCE OUTPUT — COPY ONE ROUTE AT A TIME", 1)[1]
                blocks = re.findall(r"\nAD COPY\n(.*?)(?=\nGROUP |\nFINAL INSTANT EXPERIENCE IMAGE CHECK)", grouped, re.S)
                self.assertEqual(len(blocks), 3)
                for block, style, cta in zip(blocks, legacy.NEW_AD_STYLE_KEYS,
                                              ("Claim Your Edition", "Secure Your Edition", "Own This Edition")):
                    self.assertIn(style, block)
                    for label in ("Description:", "Headline:", "CTA:"):
                        self.assertEqual(block.count(label), 1)
                    self.assertIn("CTA:\n" + cta, block)
                self.assertNotIn("Vary opening-hook family", prompt)
                self.assertNotIn("Choose-a-Side / rivalry_challenge is permitted ONLY", prompt)
                if sport != "Motorsport":
                    for forbidden in ("Peter Brock", "Six Laps Ahead", "Bathurst", "racing print"):
                        if product != "Winx":
                            self.assertNotIn(forbidden, copy.instructions(product, sport, "Australia", "test", {}))

    def test_copy_only_scarcity_baseline_and_explicit_verified_override(self):
        text = legacy.build_new_ad_style_rules("Collector Subject", "NBA", {})
        self.assertEqual(text.count("Limited to 100 worldwide."), 3)  # two templates plus baseline rule
        self.assertIn("Only 100 exist.", text)
        verified = legacy.build_new_ad_style_rules("Collector Subject", "NBA", {"EDITION_LIMIT": 250})
        self.assertIn("Limited to 250 worldwide.", verified)
        self.assertIn("Only 250 exist.", verified)
        self.assertEqual(legacy.new_ad_sport_language("NBA", {"ARTWORK_TYPE": "Team"}),
                         ("basketball", "club", "team"))

    def test_current_image_prompts_and_unchanged_creative_refresh(self):
        baseline = json.loads((Path(__file__).parent / "fixtures/ie_locked_copy_scope_baseline.json").read_text())
        for case in baseline["images"]:
            actual = ads.build_standard_instant_experience_visual_prompts(**case["kwargs"])
            self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), case["sha256"])
        case = baseline["refresh"]
        actual = ads.build_ads_prompt(**case["kwargs"])
        self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), case["sha256"])

    def test_csv_identity_contract_is_unchanged_and_copy_round_trips(self):
        result = ads.build_ads_result_record("Michael Jordan", "NBA", "USA", "Instant Experience")
        data = ads.build_instant_experience_copy_csv(result, concept_notes=instant_experience_csv_notes())
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(tuple(rows[0]), ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        self.assertEqual([r["route_key"] for r in rows], list(copy.ROUTES))
        self.assertTrue(all(r["variation"] == "1" and r["description_key"] == "legacy_standard" for r in rows))
        parsed = ads.parse_instant_experience_copy_csv(data, result)
        self.assertEqual([parsed[r["route_key"]][0]["primary_text"] for r in rows], [r["primary_text"] for r in rows])


if __name__ == "__main__":
    unittest.main()
