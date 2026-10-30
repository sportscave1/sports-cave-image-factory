"""Offline public-boundary regressions for the compact footer."""
import copy
import unittest

import ads_page as ads
from ads_footer import COMPACT_FOOTER_RULES, FOOTER_VERSION
from tests.test_ads_refresh_plan import fixture


class CompactFooterTests(unittest.TestCase):
    def test_approved_headlines_preserved_in_compact_footer(self):
        for seed in ('footer-baseline', 'footer-two', 'footer-three'):
            rows = ads.resolve_standard_instant_experience_visuals(
                product_name='Synthetic Collector Edition', category='Cricket',
                product_metadata={'edition_limit': 100}, variation_token=seed)
            self.assertEqual(len({r['headline_text'] for r in rows}), 3)
            for i, row in enumerate(rows, 1):
                self.assertIn(row['headline_text'], ads.ie_visuals.HEADLINES)
                prompt = ads.build_standard_instant_experience_image_prompt(
                    i, row, product_name='Synthetic Collector Edition', category='Cricket', country='Australia')
                self.assertIn('HEADLINE: ' + row['headline_text'], prompt)
                self.assertIn('CTA: CLAIM YOUR EDITION', prompt)
                self.assertIn('SUPPORTING LINE: ' + row['supporting_line'], prompt)

    def test_all_public_formats_and_refresh_receive_central_policy(self):
        for campaign in ('Instant Experience', 'Carousel', 'Single Image / Video'):
            for country in ('Australia', 'USA', 'UK', 'Canada', 'New Zealand'):
                prompt = ads.build_ads_prompt('Synthetic Collector Edition', 'Cricket', country, campaign, product_metadata={'edition_limit': 100})
                self.assertIn(COMPACT_FOOTER_RULES, prompt)
                self.assertIn(FOOTER_VERSION, ads.ads_prompt_contract_version_for_campaign(campaign))
            self.assertIn(COMPACT_FOOTER_RULES, fixture(campaign)['master_prompt'])

    def test_no_conflicting_footer_directions_in_active_ie_prompts(self):
        for prompt in (ads.build_ads_prompt('Synthetic Collector Edition', 'Cricket', 'Australia', 'Instant Experience', product_metadata={'edition_limit': 100}),
                       fixture('Instant Experience')['master_prompt']):
            for old in ('24–28%', '24-28%', '72–76%', 'do not shrink the panel',
                        'no supporting sentence', 'Render no supporting line',
                        'Do not render a supporting line', 'no subheadlines',
                        'Remove the supporting sentence', 'exactly two elements'):
                self.assertNotIn(old, prompt)
            self.assertIn('18–20%', prompt)

    def test_saved_pack_upgrade_keeps_exact_headline_and_scene_selections(self):
        original = ads.build_ads_result_record('Synthetic Collector Edition', 'Cricket', 'Australia',
            'Instant Experience', product_metadata={'edition_limit': 100}, variation_token='footer-baseline')
        stale = copy.deepcopy(original)
        stale['master_prompt'] = stale['master_prompt'].replace(COMPACT_FOOTER_RULES, '')
        stale['generated_ad_output'] = stale['master_prompt']
        rebuilt = ads.ensure_current_ads_result_prompt(stale)
        self.assertIn(COMPACT_FOOTER_RULES, rebuilt['master_prompt'])
        for key in ('instant_experience_footer_selections', 'instant_experience_scene_selections'):
            self.assertEqual(original['product_metadata'][key], rebuilt['product_metadata'][key])
        self.assertIs(ads.ensure_current_ads_result_prompt(rebuilt), rebuilt)


if __name__ == '__main__':
    unittest.main()
