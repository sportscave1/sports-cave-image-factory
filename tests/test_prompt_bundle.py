import ast
import json
import unittest
from unittest.mock import patch
from prompt_library import Prompt, catalog, digest
from prompt_bundle import bundle_prompt, combine, split
from tests.test_prompt_library import FakeStore


class BundleTests(unittest.TestCase):
    def test_real_catalog_round_trip_is_lossless(self):
        for category in ('Design', 'Upload', 'Ads'):
            rows = [p for p in catalog() if p.category == category]
            self.assertEqual(split(rows, combine(rows)), {p.key: p.text for p in rows})

    def test_boundaries_and_each_sections_placeholders_are_required(self):
        rows = [Prompt('ads_page.py', 'ONE', 'Ads', 'First {name}'), Prompt('ads_page.py', 'TWO', 'Ads', 'Second')]
        for text in (combine(rows).replace('<<<END', '<<<BROKEN', 1), combine(rows[::-1]),
                     combine(rows, {rows[0].key: 'First', rows[1].key: 'Second {name}'})):
            with self.assertRaises(ValueError):
                split(rows, text)

    def test_combined_release_updates_same_file_sections_atomically(self):
        rows = [Prompt('ads_page.py', 'ONE', 'Ads', 'First'), Prompt('ads_page.py', 'TWO', 'Ads', 'Second')]
        prompt = bundle_prompt(rows, 'Ads')
        store = FakeStore()
        original_read = store.read
        store.read = lambda path, ref, missing=False: ('ONE="First"\nTWO="Second"\nOTHER=42\n', None) if path == 'ads_page.py' else original_read(path, ref, missing)
        text = combine(rows, {rows[0].key: 'Changed one', rows[1].key: 'Changed two'})
        with patch('prompt_releases.catalog', return_value=rows):
            item = store.save(prompt, text, 'Both', 'owner', {'versions': []}, None)
        history = store.saved
        store.activate(prompt, item['id'], history, 'cas')
        tree = next(c[2]['tree'] for c in store.calls if c[:2] == ('POST', 'git/trees'))
        self.assertEqual(len(tree), 2)
        self.assertEqual(tree[0]['path'], 'ads_page.py')
        source = ast.parse(tree[0]['content'])
        self.assertEqual([ast.literal_eval(n.value) for n in source.body], ['Changed one', 'Changed two', 42])
        manifest = json.loads(tree[1]['content'])
        for p in rows:
            self.assertEqual(manifest[p.key]['id'], item['id'])
        self.assertEqual(sum(c[0] == 'PATCH' for c in store.calls), 1)

    def test_stale_section_prevents_any_publication(self):
        rows = [Prompt('ads_page.py', 'ONE', 'Ads', 'First')]
        prompt = bundle_prompt(rows, 'Ads')
        store = FakeStore()
        with patch('prompt_releases.catalog', return_value=rows):
            item = store.save(prompt, combine(rows, {rows[0].key: 'Changed'}), '', 'owner', {'versions': []}, None)
        with self.assertRaises(ValueError):
            store.activate(prompt, item['id'], store.saved, 'cas')
        self.assertFalse(any(c[0] in ('PATCH', 'POST') for c in store.calls))

    def test_category_not_live_if_a_changed_section_was_replaced(self):
        rows = [Prompt('ads_page.py', 'ONE', 'Ads', 'First')]
        prompt = bundle_prompt(rows, 'Ads')
        store = FakeStore()
        with patch('prompt_releases.catalog', return_value=rows):
            item = store.save(prompt, combine(rows, {rows[0].key: 'Changed'}), '', 'owner', {'versions': []}, None)
        item['commit'] = 'b' * 40
        store.deploys = [{'status': 'live', 'commit': {'id': 'b' * 40}}]
        manifest = {prompt.key: {'id': item['id'], 'hash': digest(item['text'])}, rows[0].key: {'hash': digest('Changed')}}
        store.manifest = json.dumps(manifest)
        self.assertEqual(store.status(prompt, item), 'Live')
        manifest[rows[0].key]['hash'] = digest('Later section')
        store.manifest = json.dumps(manifest)
        self.assertNotEqual(store.status(prompt, item), 'Live')
