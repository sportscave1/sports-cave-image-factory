from tests.ads_prompt_contracts import current_ie, saved_ie, rotated_ie, scenes_ie
"""Exported failure instructions only; no provider requests or safety bypasses."""
import re
import unittest

import ads_page as ads


class FailureReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = ads.build_ads_result_record(
            "Alexander Volkanovski Collector", "MMA", "Australia", "Instant Experience",
            product_metadata={"edition_limit": 100}, variation_token="failure-reporting")
        cls.prompt = cls.result["master_prompt"]

    def test_provider_block_is_not_a_technical_retry_or_a_bypass(self):
        for requirement in (
            "AND the provider identifies a retryable technical failure",
            "distinguish an explicit provider safety block from a technical failure using the actual returned error",
            "Never bypass provider safeguards or repeatedly reword a blocked request",
            "Do not retry a safety-blocked or unexplained failure",
            "Continue other unattempted ads with their unchanged briefs where tools remain available",
        ):
            self.assertIn(requirement, self.prompt)
        self.assertIn("never retry a safety-blocked or unexplained failure", ads.SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2)

    def test_unknown_error_cannot_be_presented_as_a_known_cause(self):
        for requirement in (
            "If no cause is supplied, say the cause is unknown; do not infer one",
            "quote its actual error when available",
            "If no error was supplied, say so",
        ):
            self.assertIn(requirement, self.prompt)

    def test_partial_delivery_preserves_assets_copy_and_honest_status(self):
        for requirement in (
            "identify each missing ad and route",
            "report the actual completed image count",
            "never label a two-image result as three completed covers",
            "all three final copy records, matching CSV rows and setup",
            "Complete the requested CSV and setup from the resolved copy even when an image is missing",
            "Never claim an image or CSV exists unless it was created",
            "Recover or redisplay an existing asset if display fails",
            "Never restart the set",
        ):
            self.assertIn(requirement, self.prompt)

    def test_three_original_requests_and_saved_export_remain_intact(self):
        """Current approved two-line/immutable-pack contract replaces retired layout assertions."""
        saved_ie(self)


if __name__ == "__main__":
    unittest.main()
