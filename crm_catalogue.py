"""Read-only campaign catalogue facts and escaped email cards. No edition writes."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from html import escape
import logging
import re
from urllib.parse import urlsplit, parse_qsl
from crm_campaign_html import email_image_url
from crm_tracking import public_https, campaign_link

FACTS_QUERY = '''query CrmCatalogueFacts($ids:[ID!]!,$country:CountryCode!) {
 nodes(ids:$ids) { ... on Product { id handle title status onlineStoreUrl
 featuredMedia { ... on MediaImage { image { url(transform:{maxWidth:1000,preferredContentType:JPG}) altText } } }
 contextualPricing(context:{country:$country}) { minVariantPricing { price { amount currencyCode } compareAtPrice { amount currencyCode } } }
 } } }'''
PICKER_COLLECTIONS = """query CrmPickerCollections($after:String) {
 collections(first:100,after:$after) { nodes { id title } pageInfo { hasNextPage endCursor } }
}"""
PICKER_PRODUCTS = """query CrmPickerProducts($query:String,$after:String) {
 products(first:12,after:$after,query:$query,sortKey:TITLE) { nodes { id handle title status
 featuredImage { url(transform:{maxWidth:80,maxHeight:80}) } }
 pageInfo { hasNextPage endCursor } }
}"""


def picker_thumbnail(value):
    from urllib.parse import urlencode, urlunsplit
    value = email_image_url(value)
    if not value: return ''
    parts = urlsplit(value)
    if parts.hostname == 'cdn.shopify.com':
        params = dict(parse_qsl(parts.query)); params.update(width='80',height='80')
        return urlunsplit(parts._replace(query=urlencode(params)))
    return value


FIELDS = {'id','handle','title','status','url','image','price','compare_at','currency','market','edition'}


def product_url(value):
    if not public_https(value): return ''
    if any(k.lower() in {'token','key','api_key','access_token','signature','hmac','password'} for k,v in parse_qsl(urlsplit(value).query)): return ''
    return value


def product_id(value):
    value = str(value or '').rsplit('/', 1)[-1]
    return 'gid://shopify/Product/'+value if value.isdigit() else ''


def canonical_product_url(p):
    """Use the stored public storefront destination; never substitute an image/admin URL."""
    url = product_url(p.get('url', ''))
    if not url:
        return ''
    parts = urlsplit(url)
    if parts.hostname in {'cdn.shopify.com', 'admin.shopify.com'}:
        return ''
    if not re.fullmatch(r'/(?:[a-z]{2}(?:-[a-z]{2})?/)?products/[a-zA-Z0-9_-]+/?', parts.path):
        return ''
    if any(k.lower() in {'preview_theme_id', 'preview_key', 'expires', 'sig', 'x-amz-signature', 'x-goog-signature'} for k, _ in parse_qsl(parts.query)):
        return ''
    return url


def amount(value):
    try:
        n = Decimal(str(value))
        return format(n, 'f') if n.is_finite() and 0 <= n < 100000000 else ''
    except (InvalidOperation, ValueError): return ''


def validate_snapshot(p):
    if not isinstance(p, dict) or set(p) != FIELDS or product_id(p.get('id')) != p.get('id'): raise ValueError('Invalid catalogue product snapshot.')
    if any(not isinstance(p[k], str) or len(p[k]) > 2000 for k in FIELDS-{'edition'}): raise ValueError('Invalid catalogue product facts.')
    if p['price'] and not amount(p['price']) or p['compare_at'] and not amount(p['compare_at']): raise ValueError('Invalid catalogue price.')
    if p['currency'] and not re.fullmatch('[A-Z]{3}', p['currency']): raise ValueError('Invalid currency.')
    edition = p['edition']
    if edition is not None and (not isinstance(edition, dict) or set(edition) != {'limit','next','sold','remaining','status'} or
            any(type(edition[k]) is not int or edition[k] < 0 for k in ('limit','next','sold','remaining')) or
            not 1 <= edition['next'] <= edition['limit']+1 or not 0 <= edition['remaining'] <= edition['limit'] or
            not isinstance(edition['status'], str) or len(edition['status']) > 100): raise ValueError('Invalid edition snapshot.')


def edition_for(p, rows):
    exact = [r for r in rows if product_id(r.get('shopify_product_gid') or r.get('shopify_product_id')) == p['id']]
    candidates = exact or [r for r in rows if r.get('shopify_handle') == p['handle'] and
                           not product_id(r.get('shopify_product_gid') or r.get('shopify_product_id'))]
    if len(candidates) != 1: return None
    r = candidates[0]
    if r.get('allocation_blocked') or r.get('active') is False: return None
    values = {'limit':r.get('edition_total'), 'next':r.get('run_next_edition_number') or r.get('next_edition_number'),
              'sold':r.get('sold_count'), 'remaining':r.get('remaining_count')}
    if any(type(v) is not int or v < 0 for v in values.values()): return None
    if not 1 <= values['next'] <= values['limit']+1 or values['remaining'] > values['limit']: return None
    return {**values, 'status':str(r.get('run_status') or r.get('status') or '')[:100]}


class Catalogue:
    def __init__(self, shop, *, connect=None, edition_reader=None):
        self.shop, self.connect, self.edition_reader = shop, connect, edition_reader

    def _index_search(self, query='', offset=0, active=True):
        """12 compact index rows; no all-product mirror or Shopify request."""
        from supabase_backend import connect
        with (self.connect or connect)() as conn:
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                cur.execute("SET LOCAL statement_timeout='4000ms'")
                cur.execute("""SELECT shopify_product_id,handle,title,status,image_url FROM shopify_products
                    WHERE (position(lower(%s) in lower(COALESCE(title,'') || ' ' || COALESCE(handle,'')))>0)
                    AND (%s=false OR upper(status)='ACTIVE')
                    ORDER BY title,shopify_product_id LIMIT 13 OFFSET %s""", (str(query)[:150],bool(active),max(0,int(offset))))
                rows = list(cur.fetchall())
        return {'rows':[{'id':product_id(r['shopify_product_id']), 'title':str(r['title'] or '')[:300],
                        'handle':r['handle'], 'status':r['status'], 'image':email_image_url(r['image_url'] or '')}
                       for r in rows[:12]], 'more':len(rows)>12}

    def _picker_key(self, *parts):
        return ('catalogue-picker', self.shop.namespace, self.connect, *parts)

    def collections(self):
        from crm_picker_cache import load
        def fetch():
            rows, cursor, seen = [], None, set()
            for _ in range(50):
                result = self.shop.query(PICKER_COLLECTIONS, {'after':cursor}, 'catalogue collections', 0)['collections']
                rows.extend(result['nodes'])
                if not result['pageInfo']['hasNextPage']:
                    return sorted(rows, key=lambda r:(r['title'].casefold(), r['id']))
                cursor = result['pageInfo']['endCursor']
                if not cursor or cursor in seen: break
                seen.add(cursor)
            raise ValueError('Collection list could not be completed. Please retry.')
        rows, stale = load(self._picker_key('collections'), fetch)
        return {'rows':rows, 'stale':stale}

    def search(self, query='', offset=0, active=True, collection=''):
        from crm_picker_cache import load
        query, offset = str(query).strip()[:150], max(0,int(offset))
        if collection and not re.fullmatch(r'gid://shopify/Collection/[0-9]+', collection):
            raise ValueError('Invalid collection.')
        def fetch():
            if not collection: return self._index_search(query, offset, active)
            filters = ['collection_id:'+collection.rsplit('/',1)[-1]]
            if active: filters.append('status:active')
            if query:
                # Quoted search values cannot inject status/collection operators.
                import json
                term = json.dumps(query, ensure_ascii=False)
                filters.append('(title:'+term+' OR handle:'+term+')')
            expression = ' AND '.join(filters)
            cursor, page = None, None
            for index in range(offset//12+1):
                page = self.shop.query(PICKER_PRODUCTS, {'query':expression,'after':cursor}, 'collection products', 600)['products']
                if index < offset//12:
                    if not page['pageInfo']['hasNextPage']: return {'rows':[], 'more':False}
                    cursor = page['pageInfo']['endCursor']
                    if not cursor: raise ValueError('Invalid product pagination.')
            return {'rows':[{'id':n['id'],'title':n['title'],'handle':n['handle'],'status':n['status'],
                             'image':(n.get('featuredImage') or {}).get('url','')} for n in page['nodes']],
                    'more':page['pageInfo']['hasNextPage']}
        result, stale = load(self._picker_key('search',query,offset,bool(active),collection), fetch)
        result['stale'] = stale
        for row in result['rows']: row['image'] = picker_thumbnail(row['image'])
        return result

    def resolve(self, ids, market='AU', *, fresh=False):
        ids = list(dict.fromkeys(ids))
        if not ids: return []
        if len(ids)>50 or any(product_id(i)!=i for i in ids): raise ValueError('Invalid catalogue selection.')
        country = {'AU':'AU','US':'US','UK':'GB','Global':'AU'}[market]
        nodes = self.shop.query(FACTS_QUERY, {'ids':ids,'country':country}, 'catalogue products', 60, fresh)['nodes']
        products = []
        for n in nodes:
            if not n or n.get('id') not in ids: continue
            image = (n.get('featuredMedia') or {}).get('image') or {}
            pricing = (n.get('contextualPricing') or {}).get('minVariantPricing') or {}
            price, compare = pricing.get('price') or {}, pricing.get('compareAtPrice') or {}
            products.append(dict(id=n['id'],handle=str(n.get('handle') or ''),title=str(n.get('title') or '')[:300],
                status=str(n.get('status') or ''),url=product_url(n.get('onlineStoreUrl') or ''),image=email_image_url(product_url(image.get('url') or '')),
                price=amount(price.get('amount')),compare_at=amount(compare.get('amount')) if compare.get('currencyCode')==price.get('currencyCode') else '',
                currency=price.get('currencyCode') or '',market=market,edition=None))
        try:
            from supabase_backend import list_edition_products_read_only
            rows = (self.edition_reader or list_edition_products_read_only)(product_ids=ids,handles=[p['handle'] for p in products],limit=100)
        except Exception as exc:
            logging.getLogger(__name__).warning('crm_catalogue_editions_unavailable type=%s',type(exc).__name__)
            rows = []
        for p in products: p['edition'] = edition_for(p, rows); validate_snapshot(p)
        by_id = {p['id']:p for p in products}
        if set(by_id) != set(ids): raise ValueError('A selected product is no longer available. Remove it or refresh the catalogue.')
        return [by_id[i] for i in ids]


def product_issues(p, cfg):
    issues = []
    if p['status'] != 'ACTIVE' or not p['title'].strip() or not canonical_product_url(p): issues.append('Product must be active with a title and public HTTPS product URL.')
    if cfg['display']['image'] and not email_image_url(product_url(p['image'])): issues.append('A public HTTPS product image is required.')
    if cfg['display']['price'] and (not amount(p['price']) or not p['currency']): issues.append('Current product price is required.')
    return issues


def price_label(p):
    if not amount(p['price']): return 'Price unavailable'
    currency = {'AUD':'A$','USD':'US$','GBP':'£'}.get(p['currency'], p['currency']+' ')
    return currency + format(Decimal(p['price']), '.2f')


def catalogue_html(section, *, campaign_key=''):
    """Compact collector cards; one validated destination for every product link.

    Tracking remains in the shared campaign_link helper. One product-level reference
    keeps image/title/CTA and plaintext identical rather than tracking each anchor
    separately. The stored product URL/facts are never modified by presentation.
    """
    cfg, products = section['settings'], section['products']
    display, cells = cfg['display'], []
    e = lambda v: escape(str(v), quote=True)
    single = cfg['columns'] == 1
    image_height, image_width = (300, 560) if single else (200, 260)
    title_size, title_line = (20, 25) if single else (18, 23)
    for p in products:
        if product_issues(p, cfg):
            continue  # Validation belongs in the editor, never in customer output.
        canonical_url = canonical_product_url(p)
        destination = campaign_link(canonical_url, campaign_key, 'product_' + p['id'].rsplit('/', 1)[-1], test=True) if campaign_key else canonical_url
        link = 'href="' + e(destination) + '" target="_blank" rel="noopener noreferrer"'
        parts = []
        if display['image']:
            # A consistent image well contains the whole artwork without cropping
            # or stretching. Clients without max-height support retain natural ratio.
            parts.append('<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
                '<td align="center" valign="middle" height="' + str(image_height) + '" bgcolor="#f5f3ee" style="height:' + str(image_height) + 'px">'
                '<a ' + link + ' style="display:block;text-decoration:none">'
                '<img src="' + e(p['image']) + '" alt="' + e(p['title']) + '" width="' + str(image_width) + '" border="0" '
                'style="display:block;width:auto;max-width:100%;height:auto;max-height:' + str(image_height) + 'px;margin:0 auto;border:0">'
                '</a></td></tr></table>')
        if display['title']:
            parts.append('<p style="margin:8px 0 4px;font-family:Arial,Helvetica,sans-serif;font-weight:700;font-size:' + str(title_size) + 'px;line-height:' + str(title_line) + 'px">'
                '<a ' + link + ' style="color:#1c1c1a;text-decoration:none">' + e(p['title']) + '</a></p>')
        ed = p['edition']
        if ed:
            if display['limit']:
                parts.append('<p style="margin:0 0 5px;font-size:10px;line-height:14px;letter-spacing:1px;color:#94753c">LIMITED TO ' + str(ed['limit']) + ' WORLDWIDE</p>')
            next_available = display['next'] and ed['remaining'] > 0 and ed['next'] <= ed['limit']
            if next_available:
                parts.append('<p style="margin:0;font-size:16px;line-height:20px;font-weight:700;color:#242422">#' + format(ed['next'], '03d') + ' / ' + str(ed['limit']) + '</p>')
            status = ['NEXT AVAILABLE'] if next_available else []
            if display['remaining']:
                status.append(str(ed['remaining']) + ' REMAINING' if ed['remaining'] else 'SOLD OUT')
            if status:
                parts.append('<p style="margin:0;font-size:10px;line-height:16px;letter-spacing:.4px;color:#6b6a65">' + ' · '.join(status) + '</p>')
        if display['price']:
            price = 'From ' + e(price_label(p))
            if amount(p['compare_at']) and Decimal(p['compare_at']) > Decimal(p['price']):
                price += ' <s style="color:#85837c;font-size:11px;font-weight:400">' + e(price_label({**p, 'price':p['compare_at']})) + '</s>'
            parts.append('<p style="margin:7px 0 9px;font-size:13px;line-height:18px;font-weight:600;color:#353530">' + price + '</p>')
        if display['cta']:
            parts.append('<p style="margin:0"><a ' + link + ' style="display:inline-block;background:#171717;color:#faf8f1;border:1px solid #94753c;padding:9px 13px;font-size:11px;line-height:18px;font-weight:700;letter-spacing:.7px;text-transform:uppercase;text-decoration:none">' + e(cfg['cta']) + '</a></p>')
        cells.append('<td class="sc-stack" width="' + str(100 // cfg['columns']) + '%" valign="top" style="padding:8px 10px 16px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px">' + ''.join(parts) + '</td>')
    rows = ['<tr>' + ''.join(cells[i:i + cfg['columns']]) + '</tr>' for i in range(0, len(cells), cfg['columns'])]
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#fff">' + ''.join(rows) + '</table>'


def refresh_catalogues(doc, catalogue, *, fresh=True):
    """Returns a document copy; counters are always read from Edition Ops."""
    result = deepcopy(doc)
    sections = result.get('middle_sections', [])
    ids = list(dict.fromkeys(p['id'] for s in sections if s['type']=='catalogue' and s['visible'] for p in s['products']))
    if not ids: return result
    facts = {p['id']:p for p in catalogue.resolve(ids, result['market'], fresh=fresh)}
    for s in sections:
        if s['type']=='catalogue' and s['visible']: s['products'] = [deepcopy(facts[p['id']]) for p in s['products']]
    return result
