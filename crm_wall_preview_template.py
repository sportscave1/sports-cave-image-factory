"""Insertable HTML copy and recipient-scoped, public product link resolution."""
from copy import deepcopy
from html import escape
from pathlib import Path
import re
from urllib.parse import urlsplit,urlunsplit,urlencode
from crm_tracking import public_https,store_host

IDENTITY='builtin-wall-preview-section'
NAME='See It On Your Wall — Interactive Preview'
TOKEN='SC_WALL_PREVIEW_URL'


def library_row():
    return {'id':IDENTITY,'name':NAME,'version':1,'builtin':True}


def source():
    return (Path(__file__).parent/'templates'/'wall_preview_section.html').read_text(encoding='utf-8')


def present(doc):
    return any(TOKEN in s.get('html','') for s in doc.get('middle_sections',[]) if s.get('visible')) if 'middle_sections' in doc else TOKEN in doc.get('custom_html','')


def product_link(data):
    # Match the leading checkout product. Never silently switch to another item.
    items=(data or {}).get('items') or []
    if not items:return ''
    item=items[0];url=item.get('product_url','')
    if not public_https(url):return ''
    parts=urlsplit(url)
    if not store_host(parts.hostname) or not re.fullmatch(r'/(?:[a-z]{2}(?:-[a-z]{2})?/)?products/[a-zA-Z0-9_-]+/?',parts.path):return ''
    # Rebuild from public Shopify fields; discard every original query/fragment.
    variant=re.fullmatch(r'(?:gid://shopify/ProductVariant/)?([1-9][0-9]*)',str(item.get('variant_id') or ''))
    query=[('variant',variant[1])] if variant else []
    query.append(('sc_wall_preview','1'))
    return urlunsplit(('https',parts.netloc,parts.path,urlencode(query),''))


def resolve(doc,data):
    """Render a copy only. No URL means no CTA, never a placeholder destination."""
    result=deepcopy(doc);url=product_link(data)
    def html(value):
        if TOKEN not in value:return value
        if url:return value.replace(TOKEN,escape(url,quote=True))
        value=re.sub(r'<a\b[^>]*\bhref\s*=\s*([\"\'])'+TOKEN+r'\1[^>]*>.*?</a\s*>','',value,flags=re.I|re.S)
        if TOKEN in value:raise ValueError('Wall preview link must be used as the complete CTA destination.')
        return value
    for section in result.get('middle_sections',[]):
        if section.get('type') in ('html','image'):section['html']=html(section['html'])
    result['custom_html']=html(result.get('custom_html',''))
    return result
