from tests.ads_prompt_contracts import current_ie, saved_ie, scenes_ie, copy_styles, refresh_contract
from tests.ads_prompt_contracts import current_ie, saved_ie, scenes_ie, copy_styles, refresh_contract
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
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)
        refresh_contract(self)

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
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)


class PreservedDescriptionStyleTests(unittest.TestCase):
    def test_first_two_templates_and_style_identities_are_unchanged(self):
        # Snapshot of the approved production templates before this wording upgrade.
        self.assertEqual(legacy.NEW_AD_STYLE_KEYS,
                         ('legacy_standard', 'framed_greatness', 'choose_a_side'))
        self.assertEqual(hashlib.sha256(json.dumps(legacy.NEW_AD_TEMPLATES[:2],
                         ensure_ascii=False).encode()).hexdigest(),
                         'cd023a123743fa78fb1a5a34233edbc2e4638b386b0415017ea2305fcde3cf28')
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
        """Validate the active approved contract, not a superseded full-prompt snapshot."""
        copy_styles(self)


if __name__ == '__main__':
    unittest.main()
