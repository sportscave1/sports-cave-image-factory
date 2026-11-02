"""Offline coverage for written headlines; no app startup, model calls or saved ads."""
import copy
import unittest
import ads_page as ads
import ads_creative_refresh as refresh


class WrittenMetaHeadlineTests(unittest.TestCase):
    def test_new_and_refresh_routes_share_headline_rules(self):
        winner = {'winning_primary_text': 'Supplied reference copy', 'winning_headline': 'Assigned headline'}
        for sport in ('Basketball', 'Baseball', 'MMA', 'Motorsport', 'Other'):
            for market in ('USA', 'Australia'):
                for campaign in ('Instant Experience', 'Single Image / Video'):
                    for context in (None, winner):
                        with self.subTest(sport=sport, market=market, campaign=campaign, refresh=bool(context)):
                            prompt = ads.build_ads_prompt('Test edition', sport, market, campaign,
                                product_metadata={'edition_limit': 100}, creative_refresh_context=context)
                            self.assertEqual(prompt.count(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS), 1)
                            self.assertNotIn('Create 5 headline options.', prompt)
                            self.assertNotIn('Strong short-line examples for this category:', prompt)
        for builder in (ads.build_generic_instant_experience_prompt, ads.build_baseball_instant_experience_prompt):
            self.assertIn(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS,
                builder('Test edition', 'Baseball', 'USA', 'Instant Experience'))
        self.assertIn(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS,
            refresh.build_creative_refresh_review_prompt({'product_name': 'Test edition'}, 'Reference', 'Assigned'))
        self.assertIn(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS,
            refresh.build_creative_refresh_prompt({'campaign_type': 'Single Image / Video'}, {}))

    def test_saved_headlines_and_prompt_are_not_upgraded(self):
        record = ads.build_ads_result_record('Test edition', 'Baseball', 'USA', 'Instant Experience',
            product_metadata={'edition_limit': 100}, variation_token='saved')
        record['master_prompt'] = record['master_prompt'].replace('\n\n' + ads.WRITTEN_META_HEADLINE_INSTRUCTIONS, '')
        record['generated_ad_output'] = 'Previously saved ad output: Claim Yours'
        record['standard_ads'] = [{'headline': 'Claim Yours'}]
        before = copy.deepcopy(record)
        self.assertEqual(ads.ensure_current_ads_result_prompt(record), before)
        self.assertEqual(record, before)

    def test_headline_rules_do_not_enter_image_briefs_or_carousel(self):
        prompt = ads.build_ads_prompt('Test edition', 'Baseball', 'USA', 'Instant Experience',
            product_metadata={'edition_limit': 100})
        grouped = prompt.split('GROUPED INSTANT EXPERIENCE OUTPUT — THREE SEPARATE IMAGES')[1]
        self.assertNotIn(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS, grouped)
        self.assertEqual(grouped.count('Headline:\n[one final product-specific headline]'), 3)
        self.assertIn('CLAIM YOUR EDITION', grouped)
        carousel = ads.build_ads_prompt('Test edition', 'Baseball', 'USA', 'Carousel')
        self.assertNotIn(ads.WRITTEN_META_HEADLINE_INSTRUCTIONS, carousel)


if __name__ == '__main__':
    unittest.main()
