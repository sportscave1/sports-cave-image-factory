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
        for style in plan.select_styles('priority-test', product=TITLE):
            prompt = generation.ie_refresh_standalone_brief(ads, TITLE, style=style)
            self.assertLess(prompt.index('Output: square'), prompt.index('REFERENCE: WINNER_IE'))
            self.assertLess(prompt.index('CANONICAL_PRODUCT —'), prompt.index(generation.IE_CRITICAL_PRODUCT_REALISM))
            self.assertLess(prompt.index(generation.IE_CRITICAL_PRODUCT_REALISM), prompt.index('Candidate execution'))
            self.assertTrue(prompt.endswith(generation.IE_FINAL_PRODUCT_REALISM_GATE))
            for required in ('frame thickness, bevel profile, depth and outer proportions exactly',
                             'clearly visible room-based reflections', 'front bevel',
                             'WALL SEPARATION', 'CONTACT SHADOW', 'ambient occlusion',
                             'PRODUCT FIRST', 'Product physics comes before room decoration'):
                self.assertIn(required, prompt)
            self.assertEqual(prompt.count(plan.build_sports_cave_image_realism_rules(include_product_lock=True)), 1)
            self.assertEqual(prompt.count(ads.build_instant_experience_fixed_opaque_footer_rules()), 1)
            self.assertIn('All 3 outputs must use distinct scarcity/support pairings', prompt)
            self.assertIn('supporting line must not repeat the headline', prompt)
            for copy in generation.IE_REFRESH_FOOTER_HEADLINES + generation.IE_REFRESH_FOOTER_SUPPORT:
                self.assertIn(copy, prompt)
            self.assertIn(style['name'], prompt)
        self.assertEqual(len(fixture('Instant Experience')['creative_refresh_context']['refresh_plan']['styles']), 3)

    def test_non_ie_refresh_and_new_ads_never_use_ie_helper(self):
        before = fixture('Carousel')['master_prompt']
        new = ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Instant Experience')
        with patch.object(generation, 'ie_refresh_standalone_brief', side_effect=AssertionError('IE refresh only')):
            self.assertEqual(fixture('Carousel')['master_prompt'], before)
            self.assertEqual(ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Instant Experience'), new)
        for prompt in (before, new):
            self.assertNotIn(generation.IE_CRITICAL_PRODUCT_REALISM, prompt)
            self.assertNotIn(generation.IE_FINAL_PRODUCT_REALISM_GATE, prompt)


if __name__ == '__main__':
    unittest.main()
