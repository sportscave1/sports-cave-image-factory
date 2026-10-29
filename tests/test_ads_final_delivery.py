import unittest
from unittest.mock import patch

import ads_page as ads
from ads_final_delivery import RULES, VERSION, apply_final_delivery
from tests.test_ads_refresh_plan import fixture


class FinalDeliveryTests(unittest.TestCase):
    def test_only_final_delivery_is_added_to_new_and_refresh_packages(self):
        for campaign in ('Instant Experience', 'Single Image / Video', 'Carousel'):
            for refresh in (False, True):
                def build():
                    if refresh:
                        return fixture(campaign)['master_prompt']
                    return ads.build_ads_prompt('Synthetic Collector Edition', 'Cricket',
                        'Australia', campaign, variation_token='delivery-links',
                        product_metadata={'edition_limit': 100})
                with patch.object(ads, 'apply_final_delivery', lambda p: p):
                    original = build()
                updated = build()
                self.assertEqual(updated, RULES + '\n\n' + original)
                self.assertEqual(updated.count(RULES), 1)
                self.assertEqual(apply_final_delivery(updated), updated)
                for number in range(1, 4):
                    self.assertIn(f'Download Ad {number} — [existing scene name]', updated)
                self.assertIn('actual completed generated image file', updated)
                self.assertIn('Do not regenerate', updated)

    def test_contract_version_updates_without_changing_saved_assignments(self):
        result = ads.build_ads_result_record('Synthetic Collector Edition', 'Cricket',
            'Australia', 'Instant Experience', variation_token='delivery-links')
        self.assertIn(VERSION, result['prompt_contract_version'])
        self.assertIs(ads.ensure_current_ads_result_prompt(result), result)


if __name__ == '__main__':
    unittest.main()
