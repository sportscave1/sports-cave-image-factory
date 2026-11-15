"""Only on-image headline slots change when repairing duplicate assignments."""
import itertools
import unittest
from copy import deepcopy
import ads_ie_visual_systems as visual
import ads_ie_usa as usa


class HeadlineSelectionTests(unittest.TestCase):
    def test_every_approved_combination_preserves_first_occurrences(self):
        for assigned in itertools.product(visual.HEADLINES, repeat=3):
            result = visual.select_distinct_headlines({}, 'fixed', assigned)
            self.assertEqual(len(set(result)), 3)
            self.assertTrue(set(result) <= set(visual.HEADLINES))
            for index, headline in enumerate(assigned):
                if headline not in assigned[:index]:
                    self.assertEqual(result[index], headline)
            self.assertEqual(visual.select_distinct_headlines({}, 'different', result), result)

    def test_usa_duplicate_repair_keeps_supports_and_other_visual_fields(self):
        supports = usa.SUPPORT_LINES[:3]
        selections = [dict(headline_text=usa.HEADLINE, supporting_line=s) for s in supports]
        rows = [dict(resolved_seed='same', scene='unchanged', camera=i) for i in range(3)]
        usa.resolve_footer(rows, {}, lambda h: True, lambda h, s: True, selections)
        self.assertEqual(rows[0]['headline_text'], usa.HEADLINE)
        self.assertEqual(len({r['headline_text'] for r in rows}), 3)
        self.assertEqual([r['supporting_line'] for r in rows], list(supports))
        self.assertEqual([r['camera'] for r in rows], [0, 1, 2])
        original = deepcopy(rows)
        usa.resolve_footer(rows, {}, lambda h: True, lambda h, s: True, original)
        self.assertEqual(rows, original)

    def test_standard_duplicate_repair_keeps_supports(self):
        rows = [dict(resolved_seed='same') for _ in range(3)]
        context = {'supporting_line_market': 'Australia'}
        visual.resolve_set_copy(rows, context, lambda h: True)
        selections = deepcopy(rows)
        selections[1]['headline_text'] = selections[0]['headline_text']
        supports = [r['supporting_line'] for r in selections]
        visual.resolve_set_copy(rows, context, lambda h: True, selections=selections)
        self.assertEqual([r['supporting_line'] for r in rows], supports)
        self.assertEqual(rows[0]['headline_text'], selections[0]['headline_text'])
        self.assertEqual(rows[2]['headline_text'], selections[2]['headline_text'])
        self.assertEqual(len({r['headline_text'] for r in rows}), 3)
