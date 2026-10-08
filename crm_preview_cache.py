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
                 'html_sections', 'middle_sections', 'campaign_key', 'market')


def presentation_document(doc):
    """Internal organisation is persisted, but cannot change preview pixels."""
    result=dict(doc)
    if 'middle_sections' in doc:
        result['middle_sections']=[{k:v for k,v in s.items() if k!='name'} for s in doc['middle_sections']]
    return result


def preview_key(doc, cfg, images_off=False):
    # Validate even on a hit; the cache cannot make an invalid document valid.
    validate_document(doc)
    content = {field: value for field,value in presentation_document(doc).items() if field in RENDER_FIELDS}
    # HTML and catalogue snapshot markup carries its own prices/content; segment
    # selection alone cannot change those bytes. Legacy blocks remain market-aware.
    if doc.get('content_mode')=='HTML':content.pop('market',None)
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
