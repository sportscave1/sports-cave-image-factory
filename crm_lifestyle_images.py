"""Insertable image-only HTML; Shopify gallery facts resolve on render copies only."""
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import logging
import re

TOKENS = {n: f'SC_LIFESTYLE_IMAGE_{n}_URL' for n in (2, 3, 4)}
TOKEN = re.compile(r'SC_LIFESTYLE_IMAGE_[234]_URL')
IDENTITIES = {f'builtin-lifestyle-image-{n-1}': n for n in TOKENS}
NO_CONTEXT = 'Lifestyle images need an abandoned checkout product. They are omitted until a checkout context is available.'


def library_rows():
    return [{'id':identity, 'name':f'Lifestyle Image {n-1}', 'version':1, 'builtin':True}
            for identity, n in IDENTITIES.items()]


def source(position):
    if position not in TOKENS: raise ValueError('Choose lifestyle image 1, 2 or 3.')
    return (Path(__file__).parent/'templates'/'lifestyle_image.html').read_text(encoding='utf-8').replace(TOKENS[2], TOKENS[position])


def present(doc):
    sources = ([s.get('html','') for s in doc['middle_sections'] if s.get('visible')]
               if 'middle_sections' in doc else [doc.get('custom_html','')])
    return any(TOKEN.search(value) for value in sources)


def gallery(data, shop=None):
    """Match the leading checkout product, never its selected variant or another line.

    campaign_images uses product.media's default POSITION order, filters out
    non-MediaImage nodes and reuses the existing shop-scoped 60s query cache.
    Its proportional email derivative changes neither the artwork nor crop.
    Keep invalid URL positions in place so subsequent images never shift slots.
    """
    items = (data or {}).get('items') or []
    if not items or (data or {}).get('preview_only'): return []
    identity = items[0].get('product_id')
    if not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*', str(identity or '')): return []
    images, after, cursors = [], None, set()
    try:
        if shop is None:
            from crm_shopify import Shopify
            shop = Shopify()
        # Bound latency for pathological all-video galleries/cursor failures.
        for _ in range(12):
            page = shop.campaign_images(identity, after=after)
            if not isinstance(page, dict) or not isinstance(page.get('nodes'), list): break
            images.extend(page['nodes'])
            if len(images) >= 4: break
            info = page.get('pageInfo') or {}
            if not info.get('hasNextPage'): break
            after = info.get('endCursor')
            if not isinstance(after, str) or not after or after in cursors: break
            cursors.add(after)
    except Exception as error:
        # These optional images never change checkout eligibility or leak errors
        # into customer HTML. Keep any already confirmed earlier image positions.
        logging.getLogger(__name__).warning('lifestyle_gallery_unavailable type=%s', type(error).__name__)
    return images[:4]


def render_html(value, urls):
    if not TOKEN.search(value): return value
    # Replace just the img start tag. Preserve surrounding authored HTML/CSS,
    # including split tables and the protected checkout insertion marker.
    class Images(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.edits = []
            self.lines = [0]
            self.lines.extend(m.end() for m in re.finditer('\n', value))
        def handle_starttag(self, tag, attrs):
            raw = self.get_starttag_text()
            if tag != 'img' or not TOKEN.search(raw): return
            src = dict(attrs).get('src')
            url = urls.get(src, '')
            replacement = raw.replace(src, escape(url, quote=True)) if url else ''
            line, column = self.getpos()
            start = self.lines[line-1] + column
            self.edits.append((start, start+len(raw), replacement))
        def handle_startendtag(self, tag, attrs): self.handle_starttag(tag, attrs)
    parser = Images()
    parser.feed(value); parser.close()
    for start, end, replacement in reversed(parser.edits):
        value = value[:start] + replacement + value[end:]
    # Misplaced tokens (including copied text/comments) cannot reach recipients.
    return TOKEN.sub('', value)


def resolve(doc, data=None, *, shop=None):
    sources = [s.get('html','') for s in doc.get('middle_sections',[])] + [doc.get('custom_html','')]
    if not any(TOKEN.search(value) for value in sources): return doc
    images = gallery(data, shop) if present(doc) else []
    from crm_campaign_html import email_image_url
    urls = {token: email_image_url(images[n-1].get('url',''))
            if len(images) >= n and isinstance(images[n-1], dict) else '' for n, token in TOKENS.items()}
    result = deepcopy(doc)
    for section in result.get('middle_sections',[]):
        if section.get('type') in ('html','image'):
            section['html'] = render_html(section.get('html',''), urls)
    result['custom_html'] = render_html(result.get('custom_html',''), urls)
    return result
