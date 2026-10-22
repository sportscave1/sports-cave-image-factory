"""Description-only restoration: historical source, immutable visuals/refresh and CSV."""
import csv
import hashlib
import io
import json
import unittest
import ads_page as ads
import ads_ie_copy as writing
import ads_ie_legacy_description as legacy

BASELINE = {'images': 'c34a8d3fc7dd881a84127e8d124daff8750abeb72d4142e20131e1f45c174384', 'refresh': 'e892bc97008136d00ba6b33b2236a9a0df068e91481298e7054627d6d090f9df'}

class RestoredDescriptionStylesTests(unittest.TestCase):
    def args(self):
        return dict(product_name="Michael Jordan", category="NBA", country="Australia",
                    campaign_type="Instant Experience", product_metadata={"edition_limit": 100},
                    variation_token="restore-styles")

    def test_fixed_historical_frameworks_and_current_cta(self):
        result = ads.build_ads_result_record(**self.args())
        prompt = result["master_prompt"]
        for i, style in enumerate(legacy.NEW_AD_STYLE_KEYS, 1):
            self.assertIn(f"AD {i} — {style}", prompt)
        for text in ("This isn't wall art.", "Greatness doesn't fade.\nIt gets framed.",
                     "What deserves the centre of your basketball wall?",
                     "You already know the answer.",
                     "Claim this edition for your collection…\nor leave it for another collector."):
            self.assertIn(text, prompt)
        for old in ("MOMENT / EMOTION:", "COLLECTOR SIGNIFICANCE:", "No rigid templates"):
            self.assertNotIn(old, prompt)
        self.assertEqual([v[3] for v in writing.ROUTES.values()], ["Claim Your Edition"] * 3)
        self.assertIn("reuse the same final records verbatim", prompt)

    def test_existing_image_and_refresh_prompts_are_byte_identical(self):
        args = self.args()
        record = ads.build_ads_result_record(**args)
        visuals = ads.resolve_standard_instant_experience_visuals(
            product_name="Michael Jordan", category="NBA", country="Australia",
            product_metadata=record["product_metadata"], variation_token="restore-styles")
        images = [ads.build_standard_instant_experience_image_prompt(i, v,
            product_name="Michael Jordan", category="NBA", country="Australia")
            for i, v in enumerate(visuals, 1)]
        refresh = ads.build_ads_result_record(**args,
            creative_refresh_context={"winning_primary_text": "Winner text", "winning_headline": "Winner headline"})["master_prompt"]
        for key, value in dict(images=images, refresh=refresh).items():
            self.assertEqual(hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest(), BASELINE[key])

    def test_csv_keeps_exact_descriptions_and_allows_fixed_hooks_in_history(self):
        result = ads.build_ads_result_record(**self.args())
        descriptions = [
            "Michael Jordan.\nBasketball identity.\nA name you back.\nMade for collectors.\n\nThis isn't wall art.\nIt's a statement of basketball identity.\n\nLimited to 100 editions.\nMade for fans who know why it matters.\n\nSecure yours.",
            "Greatness doesn't fade.\nIt gets framed.\n\nMichael Jordan.\nGive your basketball loyalty a place.\n\nMade for collectors who want their basketball identity on display.\n\nLimited to 100 editions.\nBuilt for serious collectors.\nMade for fans who know why it matters.\n\nSecure yours.",
            "What deserves the centre of your basketball wall?\n\nSomething that actually means something.\n\nMichael Jordan\nor another forgettable basketball print?\n\nYou already know the answer.\n\nOnly 100 exist.\n\nClaim this edition for your collection…\nor leave it for another collector."
        ]
        notes = {key: [dict(primary_text=text, headline="Michael Jordan Collector Edition", cta="Claim Your Edition")]
                 for key, text in zip(writing.ROUTES, descriptions)}
        result["recent_instant_experience_fingerprints"] = [
            dict(copy_product_key=writing.product_key("Michael Jordan"), primary_text=text) for text in descriptions]
        data = ads.build_instant_experience_copy_csv(result, concept_notes=notes)
        parsed = ads.parse_instant_experience_copy_csv(data, result)
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual([r["primary_text"] for r in rows], descriptions)
        self.assertEqual([parsed[k][0]["primary_text"] for k in writing.ROUTES], descriptions)
        self.assertEqual(tuple(rows[0]), ads.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        self.assertEqual([r["cta"] for r in rows], ["Claim Your Edition"] * 3)

    def test_adaptation_and_scarcity_remain_grounded(self):
        rules = legacy.build_new_ad_style_rules("Team Name", "NBA",
            {"ARTWORK_TYPE": "Team", "EDITION_LIMIT": 100, "SCARCITY_VERIFIED": True})
        self.assertIn("club identity", rules)
        self.assertIn("Limited to 100 editions.", rules)
        self.assertNotIn("Limited to 100 worldwide.", rules)
        self.assertIn("never invent achievements", rules)
        self.assertIn("verified rivalry/opposition", rules)

if __name__ == "__main__":
    unittest.main()
