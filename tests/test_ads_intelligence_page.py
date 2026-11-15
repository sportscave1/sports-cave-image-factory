import unittest

import ads_intelligence_page
from sports_cave_prompt_blocks import SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER


def summary():
    return {
        "spend": 100.0,
        "purchases": 2.0,
        "revenue": 300.0,
        "roas": 3.0,
        "cpa": 50.0,
        "ctr": 1.5,
        "cpc": 0.75,
        "cpm": 12.0,
        "frequency": 1.2,
    }


class AdsIntelligencePromptTests(unittest.TestCase):
    def test_image_capable_templates_get_shared_rules_but_text_only_templates_do_not(self):
        image_templates = (
            "Country Creative Report",
            "New Ad Copy Generator",
            "New Image/Mockup Brief Generator",
            "New Creative Based on Product Winners",
            "Country/Product Creative Plan",
        )
        text_only_templates = (
            "Daily Ads Review",
            "Creative Pattern Finder",
            "Demographic Opportunity Report",
            "Platform Placement Report",
            "Product Tagging Review",
            "Loser Diagnosis",
            "Product Scaling Plan",
        )

        for template in image_templates:
            with self.subTest(template=template):
                prompt = ads_intelligence_page._prompt_for(
                    template,
                    "Last 7 days",
                    summary(),
                    [],
                )
                self.assertEqual(prompt.count(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER), 1)
                self.assertIn("SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY", prompt)

        for template in text_only_templates:
            with self.subTest(template=template):
                prompt = ads_intelligence_page._prompt_for(
                    template,
                    "Last 7 days",
                    summary(),
                    [],
                )
                self.assertNotIn(SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER, prompt)


if __name__ == "__main__":
    unittest.main()
