"""Released source templates take precedence over their legacy saved overrides.

Unreleased prompts retain the existing persistence behavior. No network reads.
"""
from functools import lru_cache
import json
from pathlib import Path

MANIFEST = Path(__file__).parent / 'prompts' / 'releases.json'
SOURCES = {
    'design-studio::upgrade-existing-design': ('design_studio_page.py', 'UPGRADE_EXISTING_DESIGN_PROMPT'),
    'design-studio::expired-edition-next-chapter': ('design_studio_prompts/expired_edition_next_chapter_prompt.txt', ''),
    'design-studio::find-the-moment': ('design_studio_page.py', 'FIND_THE_MOMENT_PROMPT'),
    'design-studio::create-sports-cave-style-artwork': ('design_studio_page.py', 'CREATE_SPORTS_CAVE_STYLE_ARTWORK_PROMPT'),
    'design-studio::harsh-review': ('design_studio_page.py', 'HARSH_REVIEW_PROMPT'),
    'product-upload::new-shopify-product': ('product_upload_prompt_core.py', 'NEW_SHOPIFY_PRODUCT_PROMPT'),
    'product-upload::update-existing-shopify-product': ('product_upload_prompt_core.py', 'UPDATE_EXISTING_PRODUCT_PROMPT'),
}


@lru_cache(maxsize=1)
def manifest():
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def active_version(prompt_id):
    source = SOURCES.get(prompt_id)
    if not source:
        return None
    return next((row.get('version') for row in manifest().values()
                 if (row.get('path'), row.get('symbol', '')) == source), None)
