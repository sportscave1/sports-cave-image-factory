"""Offline prompt routing and collector-copy regressions."""
import unittest
import ads_page as ads
import ads_ie_legacy_description as legacy


class RacingCollectorCopyTests(unittest.TestCase):
    def test_racing_rule_reaches_new_ad_formats(self):
        for sport in ('Horse Racing', 'F1', 'NASCAR', 'V8 Supercars', 'Rally',
                      'IndyCar', 'MotoGP', 'Motorsport', 'Racing'):
            for campaign in ('Instant Experience', 'Carousel', 'Single Image / Video'):
                with self.subTest(sport=sport, campaign=campaign):
                    prompt = ads.build_ads_prompt('Test Driver No. 5', sport, 'Australia', campaign)
                    self.assertIn(ads.RACING_WRITTEN_COPY_INSTRUCTIONS, prompt)

    def test_racing_rule_reaches_refresh_copy(self):
        for campaign in ('Instant Experience', 'Single Image / Video', 'Carousel'):
            prompt = ads.build_ads_prompt('Test Driver No. 5', 'NASCAR', 'Australia', campaign,
                creative_refresh_context={'winning_primary_text': 'Reference copy',
                                          'winning_headline': 'Reference headline'})
            self.assertIn(ads.RACING_WRITTEN_COPY_INSTRUCTIONS, prompt)

    def test_only_third_written_headline_has_collector_direction_in_all_markets(self):
        rules = legacy.build_new_ad_style_rules('Kyle Larson Talladega', 'NASCAR', {})
        first_two, third = rules.split('AD 3 — choose_a_side', 1)
        cue = 'make the written Meta headline collector-focused'
        self.assertNotIn(cue, first_two)
        self.assertIn(cue, third)
        self.assertIn('rather than repeating or paraphrasing the opening', third)
        self.assertIn('preserve the description and all on-image headline assignments', third)
        for market in ('USA', 'Australia'):
            prompt = ads.build_ads_prompt('Kyle Larson Talladega', 'NASCAR', market, 'Instant Experience')
            self.assertEqual(prompt.count(cue), 1)

    def test_third_slot_is_product_grounded_collector_copy(self):
        rules = legacy.build_new_ad_style_rules('Kyle Larson Talladega', 'NASCAR', {})
        third = rules.split('AD 3 — choose_a_side')[1].split('Headline:')[0]
        self.assertIn('Every collection needs a centrepiece.\nOnly 100 collectors can own this one.', third)
        self.assertNotIn('What deserves', third)
        self.assertNotIn('forgettable', third)
        self.assertNotIn('You already know the answer', third)
        self.assertIn('PRODUCT / SUBJECT / MOMENT', third)
        self.assertIn('SPORTING MEANING OR SUPPORTER CONNECTION', third)
        self.assertIn('Claim this edition for your collection…\nor leave it for another collector.', third)
        self.assertEqual(rules.count('CTA: Claim Your Edition'), 3)
        self.assertIn('without inventing memories', rules)

if __name__ == '__main__':
    unittest.main()
