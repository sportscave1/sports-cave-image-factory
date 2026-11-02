"""Offline coverage for written headlines; no app startup, model calls or saved ads."""
import copy
import hashlib
import json
import ads_ie_copy as writing
import ads_ie_legacy_description as legacy
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


class PreservedDescriptionStyleTests(unittest.TestCase):
    def test_three_production_templates_are_unchanged(self):
        # Snapshot of the approved production templates before this wording upgrade.
        self.assertEqual(legacy.NEW_AD_STYLE_KEYS,
                         ('legacy_standard', 'framed_greatness', 'choose_a_side'))
        self.assertEqual(hashlib.sha256(json.dumps(legacy.NEW_AD_TEMPLATES,
                         ensure_ascii=False).encode()).hexdigest(),
                         '8aaba4ac5d45b8771487907c413e27503e77f6251bbcd485af4190ef85a3bbeb')
        for product, sport in [('Jordan × Kobe', 'NBA'), ('Shohei Ohtani 50/50', 'Baseball'),
                               ('Alex Volkanovski', 'MMA'), ('Allan Moffat — 500 Miles Alone', 'Motorsport')]:
            for market in ('USA', 'Australia'):
                plan = writing.cues(product, sport, market, 'wording-upgrade', {})
                self.assertEqual([row['description_style'] for row in plan], list(legacy.NEW_AD_STYLE_KEYS))
                self.assertEqual([row['sentence_rhythm'] for row in plan],
                                 ['historical short lines and intentional blank lines'] * 3)
                self.assertEqual([row['scarcity_close'] for row in plan],
                                 ['Secure yours.', 'Secure yours.', 'two-line collector ownership challenge'])

    def test_wording_rules_respect_selected_styles_and_fixed_fields(self):
        rules = legacy.build_new_ad_style_rules('Jordan × Kobe', 'NBA', {})
        self.assertIn(legacy.DESCRIPTION_WORDING_INSTRUCTIONS, rules)
        self.assertIn('Limited to 100 worldwide.', rules)
        self.assertIn('Only 100 exist.', rules)
        self.assertEqual(rules.count('CTA: Claim Your Edition'), 3)
        self.assertIn('never restructure the description to fit the headline', rules)
        self.assertIn(legacy.DESCRIPTION_WORDING_INSTRUCTIONS, legacy.build_description_style_rules())
        prompt = ads.build_ads_prompt('Jordan × Kobe', 'NBA', 'USA', 'Instant Experience',
            creative_refresh_context={'winning_primary_text': 'Assigned style and wording',
                                      'winning_headline': 'Assigned headline'})
        self.assertIn(legacy.DESCRIPTION_WORDING_INSTRUCTIONS, prompt)
        self.assertIn('Assigned style and wording', prompt)
        self.assertNotIn('AD 1 — legacy_standard', prompt)  # No reassignment of a winner's selected style.


if __name__ == '__main__':
    unittest.main()
