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

    def test_only_support_assignments_change_against_current_release(self):
        baseline = {}
        exec(subprocess.check_output(['git', 'show', '95b8c223:ads_ie_visual_systems.py']).decode('utf-8'), baseline)
        history = []
        seen = set()
        for refresh in (False, True):
            for seed in range(8):
                kwargs = dict(product_metadata={'edition_limit': 100}, variation_token=str(seed),
                              recent_instant_experience_fingerprints=history,
                              creative_refresh_context={'winning_primary_text': 'Synthetic winner', 'winning_headline': 'Synthetic headline'} if refresh else None)
                args = ('Synthetic Collector Edition', 'Cricket', 'Australia', 'Instant Experience')
                with patch.object(words, 'resolve_set_copy', baseline['resolve_set_copy']):
                    old = ads.build_ads_result_record(*args, **copy.deepcopy(kwargs))
                new = ads.build_ads_result_record(*args, **copy.deepcopy(kwargs))
                old_meta, new_meta = old['product_metadata'], new['product_metadata']
                self.assertEqual(old_meta['instant_experience_scene_selections'], new_meta['instant_experience_scene_selections'])
                selected = new_meta['instant_experience_footer_selections']
                self.assertEqual([v['headline_text'] for v in old_meta['instant_experience_footer_selections']],
                                 [v['headline_text'] for v in selected])
                self.assertEqual(len({v['supporting_line'] for v in selected}), 3)
                for row in selected:
                    seen.add(row['supporting_line'])
                    self.assertTrue(words.coherent_pair(row['headline_text'], row['supporting_line']))
                    self.assertIn('SUPPORTING LINE: ' + row['supporting_line'], new['master_prompt'])
                reopened = ads.build_ads_result_record(*args, **{**kwargs, 'product_metadata': new_meta})
                self.assertEqual(selected, reopened['product_metadata']['instant_experience_footer_selections'])
                self.assertIn('supporting line 24–26 px, Montserrat Regular', new['master_prompt'])
                self.assertIn('18–20%', new['master_prompt'])
                self.assertIn('Always highlight all three digits of 100', new['master_prompt'])
                history = new['instant_experience_fingerprints'] + history
        self.assertEqual(seen, set(words.eligible_support_lines({})))

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
