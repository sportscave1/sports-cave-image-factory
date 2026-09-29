"""Read-only campaign catalogue facts and escaped email cards. No edition writes."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from html import escape
import logging
import re
from urllib.parse import urlsplit, parse_qsl
from crm_campaign_html import email_image_url
from crm_tracking import public_https

FACTS_QUERY = '''query CrmCatalogueFacts($ids:[ID!]!,$country:CountryCode!) {
 nodes(ids:$ids) { ... on Product { id handle title status onlineStoreUrl
 featuredMedia { ... on MediaImage { image { url(transform:{maxWidth:1000,preferredContentType:JPG}) altText } } }
 contextualPricing(context:{country:$country}) { minVariantPricing { price { amount currencyCode } compareAtPrice { amount currencyCode } } }
 } } }'''
FIELDS = {'id','handle','title','status','url','image','price','compare_at','currency','market','edition'}


def product_url(value):
    if not public_https(value): return ''
    if any(k.lower() in {'token','key','api_key','access_token','signature','hmac','password'} for k,v in parse_qsl(urlsplit(value).query)): return ''
    return value


def product_id(value):
    value = str(value or '').rsplit('/', 1)[-1]
    return 'gid://shopify/Product/'+value if value.isdigit() else ''


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

    def search(self, query='', offset=0, active=True):
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
    if p['status'] != 'ACTIVE' or not p['title'].strip() or not product_url(p['url']): issues.append('Product must be active with a title and public HTTPS URL.')
    if cfg['display']['image'] and not email_image_url(product_url(p['image'])): issues.append('A public HTTPS product image is required.')
    if cfg['display']['price'] and (not amount(p['price']) or not p['currency']): issues.append('Current product price is required.')
    return issues


def price_label(p):
    if not amount(p['price']): return 'Price unavailable'
    currency = {'AUD':'A$','USD':'US$','GBP':'£'}.get(p['currency'], p['currency']+' ')
    return currency + format(Decimal(p['price']), '.2f')


def catalogue_html(section):
    cfg, products = section['settings'], section['products']; display = cfg['display']; cells = []
    e = lambda v:escape(str(v), quote=True)
    for p in products:
        if product_issues(p, cfg): continue  # Editor/preflight show the error; never customer-facing diagnostics.
        url = e(p['url']); parts = []
        if display['image']: parts.append('<a href="'+url+'"><img src="'+e(p['image'])+'" alt="'+e(p['title'])+'" width="'+('560' if cfg['columns']==1 else '260')+'" style="width:100%;max-width:560px;height:auto;border:0"></a>')
        if display['title']: parts.append('<p style="font-family:Arial;font-weight:700;font-size:18px;line-height:24px"><a style="color:#171717;text-decoration:none" href="'+url+'">'+e(p['title'])+'</a></p>')
        ed = p['edition']
        if ed:
            if display['limit']: parts.append('<p style="font-size:11px;letter-spacing:1px;color:#94753c">LIMITED TO '+str(ed['limit'])+' WORLDWIDE</p>')
            if display['next'] and ed['remaining']>0 and ed['next']<=ed['limit']: parts.append('<p>Next available <strong>#'+format(ed['next'],'03d')+' / '+str(ed['limit'])+'</strong></p>')
            if display['remaining']: parts.append('<p>Only '+str(ed['remaining'])+' remaining</p>' if ed['remaining'] else '<p>Sold out</p>')
        if display['price']:
            price = 'From '+e(price_label(p))
            if amount(p['compare_at']) and Decimal(p['compare_at'])>Decimal(p['price']):
                price += ' <s style="color:#777">'+e(price_label({**p,'price':p['compare_at']}))+'</s>'
            parts.append('<p>'+price+'</p>')
        if display['cta']: parts.append('<p><a href="'+url+'" style="display:inline-block;background:#171717;color:#fff;padding:10px 14px;font-size:12px;text-decoration:none">'+e(cfg['cta'])+'</a></p>')
        cells.append('<td class="sc-stack" width="'+str(100//cfg['columns'])+'%" valign="top" style="padding:12px;font-family:Arial;font-size:13px;line-height:20px">'+''.join(parts)+'</td>')
    rows = ['<tr>'+''.join(cells[i:i+cfg['columns']])+'</tr>' for i in range(0,len(cells),cfg['columns'])]
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#fff">'+''.join(rows)+'</table>'


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
