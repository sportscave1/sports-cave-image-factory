"""Exercise the Ads Submit -> result record -> clipboard boundary, not just visuals."""
import json
import re
import unittest
from unittest.mock import patch

import ads_page
from tests.test_ads_page import (
    run_ads_page, set_product_name, select_option, set_product_url, button_by_label,
)


LEGACY = """ADS INSTANT EXPERIENCE STANDARD V8 PREMIUM ROOM V4 DIFFERENT HOMES
OBJECTIVE
1. PREMIUM SCARCITY — RIGHT ANGLE
2. PREMIUM SCARCITY — STRAIGHT ON
3. PREMIUM SCARCITY — LEFT ANGLE
The three-image package must produce:
1. Slight right-angle product photograph.
2. Straight-on product photograph.
3. Slight left-angle product photograph.
SPORTS CAVE INSTANT EXPERIENCE PREMIUM ROOM SYSTEM V4
"""


class InstantExperiencePromptIntegrationTests(unittest.TestCase):
    def record(self, **kwargs):
        return ads_page.build_ads_result_record(
            "Collector Cricket Print", "Cricket", "Australia", "Instant Experience",
            product_url="https://example.com/products/collector", variation_token="integration",
            product_metadata={"edition_limit": 100}, **kwargs,
        )

    def assert_three_formats(self, text, limit=100):
        for old in ("PRIVATE GALLERY", "SMART HYBRID", "GROUP 3 — THE CAVE", "FOR THE ROOM THAT REMEMBERS.", "full-height right graphic column"):
            self.assertNotIn(old, text)
        grouped = text.split("GROUPED INSTANT EXPERIENCE OUTPUT — COPY ONE ROUTE AT A TIME", 1)[1]
        groups = re.findall(r"^GROUP ([123]) — ([^\n]+)\n\nIMAGE GENERATION PROMPT\n(.*?)\nAD COPY\n", grouped, re.M | re.S)
        self.assertEqual([label for _, label, _ in groups], [
            "PREMIUM SCARCITY — RIGHT ANGLE", "PREMIUM SCARCITY — STRAIGHT ON", "PREMIUM SCARCITY — LEFT ANGLE"])
        footer = ads_page.build_instant_experience_fixed_opaque_footer_rules()
        self.assertEqual(text.count(footer), 3)
        for i, (_, _, prompt) in enumerate(groups):
            self.assertIn(footer, prompt)
            self.assertIn(f"ONLY {limit} WILL EVER EXIST", prompt)
            self.assertIn("Once they’re claimed, this edition retires forever.", prompt)
            self.assertIn("CLAIM YOUR EDITION", prompt)
            self.assertIn(("RIGHT ANGLE", "CENTRE / STRAIGHT-ON", "LEFT ANGLE")[i], prompt)
            self.assertIn(f"Room {i+1}", prompt)
            self.assertIn("PRODUCT LOCK — ABSOLUTE", prompt)
            self.assertNotRegex(prompt, r"(?i)LIMITED TO \d+ (?:WORLDWIDE|WORLD WIDE)")
        self.assertEqual(grouped.count("\nAD COPY\n"), 3)
        self.assertNotIn("COPY VARIATIONS", grouped)
        self.assertIn(ads_page.META_AD_URL_PARAMETERS, text)

    def test_public_ads_result_entry_point_emits_three_formats(self):
        result = self.record()
        self.assert_three_formats(result["master_prompt"])
        self.assertEqual(result["master_prompt"], result["generated_ad_output"])
        self.assertEqual([f["visual_family"] for f in result["instant_experience_fingerprints"]],
                         ["premium_scarcity"] * 3)

    def test_baseball_and_generic_public_builders_use_same_contract(self):
        for category in ("Baseball", "Motorsport", "Other"):
            with self.subTest(category=category):
                text = ads_page.build_ads_prompt("Collector Print", category, "UK", "Instant Experience",
                                                product_metadata={"edition_limit": 250}, variation_token="integration")
                self.assert_three_formats(text, 250)

    def test_clipboard_serializes_the_complete_public_result(self):
        text = self.record()["master_prompt"]
        with patch("ads_page.components.html") as render_html:
            ads_page.render_prompt_copy_button(text, "ie-integration-clipboard")
        html = render_html.call_args.args[0]
        encoded = re.search(r"const promptText = (.*);", html).group(1)
        self.assertEqual(json.loads(encoded), text)
        self.assert_three_formats(json.loads(encoded))

    def test_cached_legacy_prompt_rebuilds_even_when_version_claims_current(self):
        current = self.record()
        for version in ("ADS INSTANT EXPERIENCE STANDARD V8 PREMIUM ROOM V4 DIFFERENT HOMES", current["prompt_contract_version"]):
            stale = {**current, "prompt_contract_version": version, "master_prompt": LEGACY,
                     "generated_ad_output": LEGACY}
            rebuilt = ads_page.ensure_current_ads_result_prompt(stale)
            self.assert_three_formats(rebuilt["master_prompt"])
            self.assertEqual(rebuilt["generated_ad_output"], rebuilt["master_prompt"])
            for field in ("context_key", "variation_token", "product_url", "product_metadata", "campaign_moment"):
                self.assertEqual(rebuilt[field], current[field])
            self.assertIs(ads_page.ensure_current_ads_result_prompt(rebuilt), rebuilt)

    def test_cached_refresh_preserves_completed_copy_and_does_not_rewrite_history(self):
        current = self.record(recent_instant_experience_fingerprints=[{"route": "Premium Scarcity — Right Angle"}])
        stale = {**current, "master_prompt": LEGACY, "generated_ad_output": "Completed customer copy"}
        rebuilt = ads_page.ensure_current_ads_result_prompt(stale)
        self.assertEqual(rebuilt["generated_ad_output"], "Completed customer copy")
        self.assertEqual(rebuilt["recent_instant_experience_fingerprints"], current["recent_instant_experience_fingerprints"])
        self.assertIs(ads_page.ensure_current_ads_result_prompt(rebuilt), rebuilt)

    def test_partial_current_prompt_with_late_legacy_override_is_refreshed(self):
        current = self.record()
        stale = {**current, "master_prompt": current["master_prompt"] + "\nOverride: Private Gallery with FOR THE ROOM THAT REMEMBERS. and full-height right graphic column."}
        self.assert_three_formats(ads_page.ensure_current_ads_result_prompt(stale)["master_prompt"])

    def test_submit_and_cached_rerun_deliver_correct_master_to_copy_button(self):
        app = run_ads_page()
        set_product_name(app, "Collector Cricket Print Limited to 100 editions")
        select_option(app, "Category", "Cricket")
        select_option(app, "Country", "Australia")
        select_option(app, "Campaign type", "Instant Experience")
        set_product_url(app, "https://example.com/products/collector")
        with patch("ads_page.render_prompt_copy_button") as copy_button:
            button_by_label(app, "Submit").click().run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        copied = [call.args[0] for call in copy_button.call_args_list if len(call.args) >= 2 and str(call.args[1]).startswith("ads-prompt::")]
        self.assertEqual(len(copied), 1)
        self.assert_three_formats(copied[0])
        result = dict(app.session_state[ads_page.ADS_RESULT_STATE_KEY])
        self.assertEqual(copied[0], result["master_prompt"])
        app.session_state[ads_page.ADS_RESULT_STATE_KEY] = {**result, "master_prompt": LEGACY, "generated_ad_output": LEGACY}
        with patch("ads_page.render_prompt_copy_button") as copy_button:
            app.run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        copied = [call.args[0] for call in copy_button.call_args_list if len(call.args) >= 2 and str(call.args[1]).startswith("ads-prompt::")]
        self.assertEqual(len(copied), 1)
        self.assert_three_formats(copied[0])


if __name__ == "__main__":
    unittest.main()
