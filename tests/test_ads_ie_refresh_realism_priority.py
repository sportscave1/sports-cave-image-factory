"""IE Creative Refresh prompt priority only; no generation or provider calls."""
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_refresh_generation as generation
import ads_refresh_plan as plan
from tests.test_ads_refresh_plan import fixture
from tests.test_ads_refresh_workflow import TITLE


class IERefreshRealismPriorityTests(unittest.TestCase):
    def test_source_authority_precedes_legacy_ie_room_and_footer_rules(self):
        master = fixture('Instant Experience')['master_prompt']
        self.assertIn(plan.preserve.AUTHORITY,master)
        self.assertNotIn('shared approved five-headline bank',master)
        self.assertNotIn('Premium residential man cave',master)
        self.assertNotIn('Premium collector hallway',master)
        self.assertEqual(fixture('Instant Experience')['creative_refresh_context']['refresh_plan']['styles'],[])
        self.assertIn('original image bytes',master)

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
