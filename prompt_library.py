"""Read and edit prompt source without importing application modules.

Only prompt text changes: Python interpolation expressions are immutable slots.
"""
import ast
from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
TEXT_FILES = {
    'design_review_instructions.md': 'Design',
    'docs/NEW_DESIGN_PROMPT.txt': 'Design',
    'design_studio_prompts/SPORTS-CAVE-HIGH-QUALITY-IMAGE-SEARCH-PROMPT-V2.txt': 'Design',
    'design_studio_prompts/expired_edition_next_chapter_prompt.txt': 'Design',
    'prompts/sports_cave_universal_creative_system.txt': 'Ads',
    'prompts/google_demand_gen_v1.txt': 'Ads',
}
MODULES = {
    'Design': ('design_studio_page.py', 'design_review_prompt.py', 'design_new_composition.py',
               'design_photographic_composition.py', 'design_collector_assets.py',
               'design_collector_background.py', 'design_collector_titles.py', 'design_motorsport.py',
               'design_subject_authenticity.py', 'design_signature_free.py'),
    'Upload': ('product_upload_prompt_core.py', 'product_upload_compact.py', 'product_upload_modes.py'),
    'Ads': ('ads_page.py', 'ads_copy_optimisation.py', 'ads_carousel_winner.py',
            'ads_final_delivery.py', 'ads_footer.py', 'ads_generation_review.py',
            'ads_ie_legacy_description.py'),
}


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def slots(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, {}
    if isinstance(node, ast.JoinedStr):
        parts, bindings = [], {}
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(value.value)
            else:
                key = f'⟪slot:{len(bindings)}⟫'
                bindings[key] = value
                parts.append(key)
        return ''.join(parts), bindings
    return '', {}


def assignments(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            yield node.targets[0].id, node.value


@dataclass(frozen=True)
class Prompt:
    path: str
    symbol: str
    category: str
    text: str

    @property
    def key(self):
        return digest(self.path + ':' + self.symbol)[:24]

    @property
    def title(self):
        name = self.symbol or Path(self.path).stem
        return name.replace('SPORTS_CAVE_', '').replace('_', ' ').replace('-', ' ').strip().title()


def catalog(root=ROOT):
    result = []
    for path, category in TEXT_FILES.items():
        file = root / path
        if file.is_file():
            result.append(Prompt(path, '', category, file.read_text(encoding='utf-8')))
    for category, paths in MODULES.items():
        for path in paths:
            if not (root / path).is_file():
                continue
            for name, node in assignments((root / path).read_text(encoding='utf-8')):
                text, _ = slots(node)
                if len(text) >= 180 and not any(term in name for term in ('SQL', 'CSS', 'HTML', 'JAVASCRIPT')):
                    result.append(Prompt(path, name, category, text))
    return sorted(result, key=lambda p: (p.category, p.title, p.path))


def validate_text(before, after):
    if not isinstance(after, str) or not after.strip() or len(after.encode('utf-8')) > 200_000:
        raise ValueError('A prompt must contain text and be smaller than 200 KB.')
    pattern = r'⟪slot:\d+⟫|\{[A-Za-z_][\w.\[\]]*(?:![rsa])?(?::[^{}]+)?\}'
    if Counter(re.findall(pattern, before)) != Counter(re.findall(pattern, after)):
        raise ValueError('Keep every template placeholder unchanged, including its number of occurrences.')


def replace_source(prompt, source, expected, text):
    """Require exact prompt content; unrelated edits in the same file survive."""
    if prompt.path not in TEXT_FILES and prompt.path not in sum(MODULES.values(), ()):
        raise ValueError('Unknown prompt source.')
    if not prompt.symbol:
        current = source
        node = None
    else:
        node = next((n for name, n in assignments(source) if name == prompt.symbol), None)
        if node is None:
            raise ValueError('Prompt source was removed. Reload the library.')
        current, bindings = slots(node)
    if digest(current) != expected:
        raise ValueError('This prompt changed in Git. Reload and compare before publishing.')
    validate_text(current, text)
    if node is None:
        return text
    if isinstance(node, ast.JoinedStr):
        values = [bindings[p] if p in bindings else ast.Constant(value=p)
                  for p in re.split(r'(⟪slot:\d+⟫)', text) if p]
        expression = ast.unparse(ast.JoinedStr(values=values))
    else:
        expression = repr(text)
    # AST columns are UTF-8 byte offsets, not Unicode character offsets.
    lines = source.encode('utf-8').splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1])) + node.col_offset
    end = sum(map(len, lines[:node.end_lineno - 1])) + node.end_col_offset
    data = source.encode('utf-8')
    updated = (data[:start] + expression.encode('utf-8') + data[end:]).decode('utf-8')
    ast.parse(updated)
    return updated
