"""IE Creative Refresh prompt priority only; no generation or provider calls."""
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_refresh_generation as generation
import ads_refresh_plan as plan
from tests.test_ads_refresh_plan import fixture
from tests.test_ads_refresh_workflow import TITLE


class IERefreshRealismPriorityTests(unittest.TestCase):
    def test_three_contracts_include_product_first_and_final_gate(self):
        master = fixture('Instant Experience')['master_prompt']
        contracts = master.split('STANDALONE EXECUTION CONTRACTS')[1].split('EXECUTION NOTES')[0]
        self.assertEqual(contracts.count(generation.IE_CRITICAL_PRODUCT_REALISM), 3)
        self.assertEqual(contracts.count(generation.IE_FINAL_PRODUCT_REALISM_GATE), 3)
        for prompt in contracts.split(generation.IE_CRITICAL_PRODUCT_REALISM)[1:]:
            self.assertIn("HEADLINE: ", prompt)
            self.assertIn("SUPPORTING LINE:", prompt)
            self.assertIn("CTA: CLAIM YOUR EDITION", prompt)
            self.assertIn("shared approved five-headline bank", prompt)
            self.assertIn(generation.IE_FINAL_PRODUCT_REALISM_GATE, prompt)
        self.assertIn("Premium residential man cave", contracts)
        self.assertIn("Premium collector hallway", contracts)
        self.assertEqual(len(fixture('Instant Experience')['creative_refresh_context']['refresh_plan']['styles']), 3)

    def test_non_ie_refresh_and_new_ads_never_use_ie_helper(self):
        before = fixture('Carousel')['master_prompt']
        new = ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Instant Experience', product_metadata={'edition_limit': 100})
        with patch.object(generation, 'ie_refresh_standalone_brief', side_effect=AssertionError('IE refresh only')):
            self.assertEqual(fixture('Carousel')['master_prompt'], before)
            self.assertEqual(ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Instant Experience', product_metadata={'edition_limit': 100}), new)
        for prompt in (before, new):
            self.assertNotIn(generation.IE_CRITICAL_PRODUCT_REALISM, prompt)
            self.assertNotIn(generation.IE_FINAL_PRODUCT_REALISM_GATE, prompt)


if __name__ == '__main__':
    unittest.main()
