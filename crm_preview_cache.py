"""Bounded session-only cache for pure preview output, never delivery decisions."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json

from crm_campaign_content import render_campaign, validate_document

KEY = '_crm_preview_cache'
LIMIT = 4
BYTE_LIMIT = 1024 * 1024
RENDER_FIELDS = ('renderer_version', 'content_mode', 'content', 'blocks', 'custom_html',
                 'html_sections', 'campaign_key', 'market')


def preview_key(doc, cfg, images_off=False):
    # Validate even on a hit; the cache cannot make an invalid document valid.
    validate_document(doc)
    content = {field: doc.get(field) for field in RENDER_FIELDS}
    return hashlib.sha256(json.dumps([content, cfg, images_off], sort_keys=True).encode()).hexdigest()


def preview(state, doc, cfg, *, images_off=False, loading=None):
    from contextlib import nullcontext
    key = preview_key(doc, cfg, images_off)
    cache = state.setdefault(KEY, OrderedDict())
    if key in cache:
        cache.move_to_end(key)
        return deepcopy(cache[key][0])
    with loading() if loading else nullcontext():
        result = render_campaign(doc, cfg, images_off=images_off)
    size = sum(len(value.encode('utf-8')) for value in result.values())
    if size <= BYTE_LIMIT:
        cache[key] = (deepcopy(result), size)
        while len(cache) > LIMIT or sum(item[1] for item in cache.values()) > BYTE_LIMIT:
            cache.popitem(last=False)
    return result
