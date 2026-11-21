"""Historical subheadline restoration without changing current creative contracts."""
import copy
import subprocess
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_ie_visual_systems as words


class RestoredSubheadlineTests(unittest.TestCase):
    def test_bank_and_eligibility_match_october_24_history(self):
        historical = {}
        exec(subprocess.check_output(['git', 'show', '1cd4132e:ads_ie_visual_systems.py']).decode('utf-8'), historical)
        self.assertEqual(words.APPROVED_SUPPORT_LINES, historical['APPROVED_SUPPORT_LINES'])
        self.assertEqual(words.eligible_support_lines({}), historical['eligible_support_lines']({}))

    def test_footer_split_preserves_support_assignment_and_saved_packs(self):
        import ads_ie_two_line as footer
        seen = set()
        history = []
        args = ('Synthetic Collector Edition', 'Cricket', 'Australia', 'Instant Experience')
        for seed in range(16):
            result = ads.build_ads_result_record(*args, variation_token=str(seed),
                recent_instant_experience_fingerprints=history)
            selected = result['product_metadata']['instant_experience_footer_selections']
            self.assertEqual(len({row['supporting_line'] for row in selected}), 3)
            for row in selected:
                self.assertIn(row['supporting_line'], words.eligible_support_lines({'supporting_line_market':'Australia'}))
                self.assertIn(footer.image_copy(row), result['master_prompt'])
                expected = row['supporting_line'] if row['footer_second_line_kind'] == 'CTA' else 'Claim Your Edition'
                self.assertEqual(row['meta_headline_text'], expected)
                seen.add(row['supporting_line'])
            reopened = ads.build_ads_result_record(*args, variation_token='new', product_metadata=copy.deepcopy(result['product_metadata']))
            self.assertEqual(selected, reopened['product_metadata']['instant_experience_footer_selections'])
            self.assertIs(ads.ensure_current_ads_result_prompt(result), result)
            history = result['instant_experience_fingerprints'] + history
        self.assertEqual(seen, set(words.eligible_support_lines({'supporting_line_market':'Australia'})))

    def test_history_rotates_supports_without_rerolling_headlines(self):
        first = [{'resolved_seed': 'restore-history'} for _ in range(3)]
        words.resolve_set_copy(first, {}, lambda h: True)
        history = [{'on_image_headline': r['headline_text'], 'on_image_subline': r['supporting_line']} for r in first]
        second = [{'resolved_seed': 'restore-history'} for _ in range(3)]
        words.resolve_set_copy(second, {}, lambda h: True, history)
        self.assertEqual([r['headline_text'] for r in first], [r['headline_text'] for r in second])
        self.assertNotEqual([r['supporting_line'] for r in first], [r['supporting_line'] for r in second])


if __name__ == '__main__':
    unittest.main()
