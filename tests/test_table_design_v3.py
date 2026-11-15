"""Cross-module presentation contracts captured before the V3 restyle.

Protect data expressions, column definitions, callbacks and widget identities at
every audited native call site; do not replace behavioural module tests.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

from scripts.sync_table_design import HOSTS, expected
from table_design import TABLE_CSS, TABLE_ROW_HEIGHT

ROOT = Path(__file__).resolve().parents[1]


def native_calls(source):
    calls = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'st'
                and node.func.attr in ('dataframe', 'data_editor', 'table')):
            node.keywords = [kw for kw in node.keywords if kw.arg != 'row_height']
            calls.append((node.lineno, ast.dump(node, include_attributes=False)))
    return [hashlib.sha256(value.encode()).hexdigest() for _, value in sorted(calls)]


def scripts_digest(source):
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', source, re.S)
    return hashlib.sha256('\n'.join(scripts).encode()).hexdigest()


class TableDesignContracts(unittest.TestCase):
    def test_every_native_data_expression_and_interaction_is_preserved(self):
        contracts = json.loads((ROOT / 'tests/fixtures/table_v3_contracts.json').read_text())
        for file, signatures in contracts['native'].items():
            with self.subTest(module=file):
                # Concurrent feature work may add tables. Every original call
                # must still appear unmodified and in its original order.
                current = iter(native_calls((ROOT / file).read_text(encoding='utf8')))
                for signature in signatures:
                    self.assertIn(signature, current)

    def test_component_event_and_render_scripts_are_unchanged(self):
        contracts = json.loads((ROOT / 'tests/fixtures/table_v3_contracts.json').read_text())
        for file, signature in contracts['scripts'].items():
            with self.subTest(component=file):
                self.assertEqual(scripts_digest((ROOT / file).read_text(encoding='utf8')), signature)

    def test_component_skins_cannot_drift_from_shared_source(self):
        for component, host in HOSTS.items():
            with self.subTest(component=component):
                source = (ROOT / 'components' / component / 'index.html').read_text(encoding='utf8')
                self.assertEqual(source, expected(source, host))

    def test_new_native_grids_use_the_shared_density_or_an_explicit_override(self):
        # Include future application modules, not just the original inventory.
        for path in ROOT.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'st'
                        and node.func.attr in ('dataframe', 'data_editor')):
                    with self.subTest(file=path.name, line=node.lineno):
                        self.assertTrue(any(kw.arg == 'row_height' for kw in node.keywords))

    def test_native_theme_is_table_only(self):
        import tomllib
        theme = tomllib.loads((ROOT / '.streamlit/config.toml').read_text())['theme']
        self.assertEqual(theme, {'dataframeBorderColor': '#eeece5',
                                 'dataframeHeaderBackgroundColor': '#f3f2ec'})
        self.assertEqual(TABLE_ROW_HEIGHT, 34)
        self.assertNotIn('@import', TABLE_CSS)
        self.assertNotIn('url(', TABLE_CSS)


if __name__ == '__main__':
    unittest.main()
