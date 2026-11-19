import ast
import copy
import unittest

from prompt_library import Prompt, catalog, digest, replace_source, slots, validate_text
from prompt_releases import GitStore, ReleaseError, SERVICE


class SourceTests(unittest.TestCase):
    def test_catalog_covers_three_workflows(self):
        items = catalog()
        self.assertEqual({p.category for p in items}, {'Design', 'Upload', 'Ads'})
        self.assertEqual(len({p.key for p in items}), len(items))
        self.assertTrue(any(p.symbol == 'SPORTS_CAVE_MASTER_DESIGN_SYSTEM_PROMPT' for p in items))

    def test_unicode_and_unrelated_code_survive(self):
        source = '# café\nPROMPT = "Before {product}"\nOTHER = 7\n'
        prompt = Prompt('ads_page.py', 'PROMPT', 'Ads', 'Before {product}')
        result = replace_source(prompt, source, digest(prompt.text), 'After {product} — collector')
        self.assertIn('OTHER = 7', result)
        self.assertEqual(ast.literal_eval(ast.parse(result).body[0].value), 'After {product} — collector')

    def test_interpolation_is_not_executable_from_editor(self):
        source = 'PROMPT = f"Hello {name!r}: {price:.2f}"\n'
        original = ast.parse(source).body[0].value
        text, bindings = slots(original)
        prompt = Prompt('ads_page.py', 'PROMPT', 'Ads', text)
        result = replace_source(prompt, source, digest(text), text + ' {danger()}')
        changed = ast.parse(result).body[0].value
        self.assertEqual([ast.dump(n) for n in changed.values if isinstance(n, ast.FormattedValue)],
                         [ast.dump(n) for n in bindings.values()])
        self.assertIn('{danger()}', slots(changed)[0])

    def test_stale_and_invalid_templates_rejected(self):
        p = Prompt('ads_page.py', 'PROMPT', 'Ads', 'Hello {product}')
        with self.assertRaises(ValueError):
            replace_source(p, 'PROMPT="Changed"', digest(p.text), 'New')
        for text in ('', 'Missing placeholder', '{product} {product}'):
            with self.assertRaises(ValueError):
                validate_text(p.text, text)
        with self.assertRaises(ValueError):
            replace_source(Prompt('../secret.py', '', 'Ads', 'a'), 'a', digest('a'), 'b')


class FakeStore(GitStore):
    def __init__(self):
        super().__init__('fake', 'fake')
        self.calls = []
        self.saved = None
        self.conflict = False
        self.deploys = []
        self.manifest = None

    def head(self, branch='main', missing=False):
        return 'a' * 40

    def read(self, path, ref, missing=False):
        if path.endswith('releases.json'):
            return self.manifest, None
        return 'PROMPT="Original"\nUNRELATED=42\n', 'source-sha'

    def write_history(self, prompt, data, expected_sha):
        self.calls.append(('history', expected_sha))
        if self.conflict:
            raise ReleaseError('Concurrent edit')
        self.saved = copy.deepcopy(data)
        return 'saved-sha'

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if path == 'services/' + SERVICE:
            return {'id': SERVICE, 'name': 'sports-cave-os', 'branch': 'main', 'autoDeploy': 'yes',
                    'autoDeployTrigger': 'commit', 'repo': 'https://github.com/sportscave1/sports-cave-image-factory'}
        if '/deploys?' in path:
            return self.deploys
        if path.startswith('git/commits/'):
            return {'tree': {'sha': 'tree-sha'}}
        if path == 'git/trees':
            return {'sha': 'new-tree'}
        if path == 'git/commits':
            return {'sha': 'b' * 40}
        if path.startswith('compare/'):
            return {'status': 'ahead'}
        return {}


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.prompt = Prompt('ads_page.py', 'PROMPT', 'Ads', 'Original')
        self.history = {'versions': [{'id': 'id', 'version': '1.1', 'text': 'Changed', 'base_hash': digest('Original')}]}

    def test_save_is_draft_only_and_preserves_versions(self):
        before = copy.deepcopy(self.history)
        self.store.save(self.prompt, 'Second', 'why', 'owner', self.history, 'cas')
        self.assertEqual(self.history, before)
        self.assertEqual(len(self.store.saved['versions']), 2)
        self.assertEqual(self.store.calls, [('history', 'cas')])

    def test_activation_only_changes_prompt_and_manifest(self):
        self.store.activate(self.prompt, 'id', self.history, 'cas')
        tree = next(c[2] for c in self.store.calls if c[:2] == ('POST', 'git/trees'))
        self.assertEqual([x['path'] for x in tree['tree']], ['ads_page.py', 'prompts/releases.json'])
        self.assertIn('UNRELATED=42', tree['tree'][0]['content'])
        self.assertEqual(self.store.calls[-1], ('PATCH', 'git/refs/heads/main', {'sha': 'b'*40, 'force': False}))
        self.assertEqual(self.store.saved['versions'][0]['commit'], 'b'*40)

    def test_concurrent_draft_edit_prevents_publication(self):
        self.store.conflict = True
        with self.assertRaises(ReleaseError):
            self.store.activate(self.prompt, 'id', self.history, 'old-sha')
        self.assertFalse(any(c[0] == 'PATCH' for c in self.store.calls))

    def test_no_repeat_publication(self):
        self.history['versions'][0]['commit'] = 'b'*40
        with self.assertRaises(ReleaseError):
            self.store.activate(self.prompt, 'id', self.history, 'cas')
        self.assertEqual(self.store.calls, [])

    def test_live_requires_deployed_manifest_identity(self):
        import json
        item = {**self.history['versions'][0], 'commit': 'b'*40}
        self.store.deploys = [{'deploy': {'status': 'live', 'commit': {'id': 'b'*40}}}]
        self.assertNotEqual(self.store.status(self.prompt, item), 'Live')
        self.store.manifest = json.dumps({self.prompt.key: {'id': 'id', 'hash': digest('Changed')}})
        self.assertEqual(self.store.status(self.prompt, item), 'Live')
        self.store.deploys = [{'deploy': {'status': 'build_in_progress', 'commit': {'id': 'b'*40}}}]
        self.assertEqual(self.store.status(self.prompt, item), 'Deploying')


class RuntimeTests(unittest.TestCase):
    def test_release_wins_over_legacy_override_without_database_read(self):
        from unittest.mock import patch
        import prompt_store
        import prompt_release_runtime as runtime
        release = {'x': {'path': 'design_studio_page.py', 'symbol': 'FIND_THE_MOMENT_PROMPT', 'version': '1.2'}}
        with patch.object(runtime, 'manifest', return_value=release), patch.object(prompt_store, '_runtime_saved_record') as cached:
            row = prompt_store.load_prompt('design-studio::find-the-moment', 'New deployed instructions')
            self.assertEqual(row['text'], 'New deployed instructions')
            self.assertEqual(row['source'], 'git_release')
            cached.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'version-controlled'):
                prompt_store.save_prompt('design-studio::find-the-moment', 'Moment', 'Old editor')
            self.assertIsNone(runtime.active_version('unrelated'))


if __name__ == '__main__':
    unittest.main()
