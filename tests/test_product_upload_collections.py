import json
from pathlib import Path
import unittest

import app
from product_upload_collections import RULES, START, preview_collections
from tests.test_product_upload_prompts import source_context


CATALOGUE = json.loads((Path(__file__).parent / 'fixtures' /
    'product_upload_collections_2026_09_16.json').read_text(encoding='utf-8'))['collections']


class ProductCollectionTests(unittest.TestCase):
    def test_real_catalogue_multiple_matches_and_no_cross_sport(self):
        cases = [
            ({'league': 'Formula One'}, {'Formula One Wall Art', 'Motor Racing Wall Art', 'Collector Series Wall Art'}),
            ({'league': 'NBA', 'athletes': ['Michael Jordan']}, {'NBA Wall Art', 'Michael Jordan Wall Art', 'Collector Series Wall Art'}),
            ({'league': 'NFL', 'country': 'USA'}, {'NFL Wall Art', 'Collector Series Wall Art'}),
            ({'sub_sport': 'Supercars', 'country': 'Australia'}, {'Motor Racing Wall Art', 'Collector Series Wall Art'}),
        ]
        for facts, expected in cases:
            facts = dict(facts, collector_eligible=True)
            with self.subTest(facts=facts):
                plan = preview_collections(facts, CATALOGUE + CATALOGUE)
                self.assertEqual({r['title'] for r in plan['review'] if r['selected']}, expected)
                self.assertEqual(len(plan['manual_ids']), len(set(plan['manual_ids'])))
                self.assertEqual(len(plan['review']), 34)
                for mode in ('DRAFT', 'LIVE'):
                    metadata = dict(source_context(), verified_collection_facts=facts, collection_catalogue=CATALOGUE)
                    prompt = app.get_product_upload_prompt(metadata, publication_mode=mode)
                    self.assertIn(json.dumps(plan, ensure_ascii=False), prompt)
                    self.assertIn('apply EVERY selected manual ID', prompt)
                    self.assertEqual(prompt.count(START), 1)
                    self.assertEqual(app.apply_product_upload_prompt_updates(prompt, metadata, publication_mode=mode), prompt)

    def test_smart_collections_never_enter_manual_ids(self):
        plan = preview_collections({'league': 'NBA', 'collector_eligible': True}, CATALOGUE)
        automatic = [r for r in plan['review'] if r['type'] == 'Automatic']
        self.assertEqual({r['title'] for r in automatic}, {
            'All Sports Wall Art', 'Best Selling Sports Wall Art', 'New Sports Wall Art'})
        for row in automatic:
            self.assertFalse(row['selected'])
            self.assertNotIn(row['id'], plan['manual_ids'])
        modified = [dict(c, ruleSet={'rules': []}) for c in CATALOGUE]
        self.assertEqual(preview_collections({'league': 'NBA'}, modified)['manual_ids'], [])
        unknown = [{k: v for k, v in c.items() if k != 'ruleSet'} for c in CATALOGUE]
        self.assertEqual(preview_collections({'league': 'NBA'}, unknown)['manual_ids'], [])

    def test_vague_titles_curated_markets_and_wrong_subject_are_not_matches(self):
        facts = {'title': 'Greatest King Legend Champion Final Moment', 'country': 'UK'}
        self.assertEqual(preview_collections(facts, CATALOGUE)['manual_ids'], [])
        facts.update(league='F1', athletes=['Michael Jordan'], collector_eligible=True)
        selected = {r['title'] for r in preview_collections(facts, CATALOGUE)['review'] if r['selected']}
        self.assertNotIn('Michael Jordan Wall Art', selected)
        self.assertNotIn('Best Selling Wall Art UK', selected)
        self.assertNotIn('Popular', selected)

    def test_actual_public_entry_point_exports_same_policy_in_preview_and_copy(self):
        for mode in ('DRAFT', 'LIVE'):
            for preview in (False, True):
                prompt = app.get_product_upload_prompt(source_context(), publication_mode=mode, preview=preview)
                self.assertIn(RULES, prompt)
                for rule in ('paginating to the end', 'deduplicated LIST', 'Before upload show a compact table',
                             'Never truncate to index 0', 'never association football',
                             'all/any semantics', 'never send an unsupported manual'):
                    self.assertIn(rule.casefold(), prompt.casefold())
                self.assertNotIn('Add membership in both', prompt)
                self.assertNotIn('product and both collection IDs', prompt)
        existing = app.get_product_upload_prompt(source_context(), update_existing=True)
        self.assertNotIn(START, existing)


if __name__ == '__main__':
    unittest.main()
