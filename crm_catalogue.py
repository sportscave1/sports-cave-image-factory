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
    if not isinstance(p, dict) or not FIELDS <= set(p) or set(p)-FIELDS-{'image_alt'} or product_id(p.get('id')) != p.get('id'): raise ValueError('Invalid catalogue product snapshot.')
    if 'image_alt' in p and (not isinstance(p['image_alt'],str) or len(p['image_alt'])>500):raise ValueError('Invalid image ALT.')
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
        country = {'AU':'AU','US':'US','UK':'GB','Global':'AU','CA':'CA','NZ':'NZ'}[market]
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
                currency=price.get('currencyCode') or '',market=market,edition=None,image_alt=str(image.get('altText') or '')[:500]))
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


def desktop_columns(products):
    count=len(products);longest=max((len(p['title']) for p in products),default=0)
    if count<=2:return 2
    if count==3 or count in (5,6):return 3
    if count==4:return 4 if longest<=65 else 2
    return 4 if longest<=65 else 3


def image_alt(p):
    value=' '.join((p.get('image_alt') or '').split())
    return value if value.casefold() not in ('','image','product image','wall art image') else p['title']


def catalogue_html(section, *, campaign_key=''):
    """Local snapshot-only hero or hybrid grid; two-up Word/no-media fallback."""
    cfg=section['settings'];display=cfg['display']
    products=[p for p in section['products'] if not product_issues(p,cfg)]
    if not products:return ''
    single=len(products)==1;e=lambda v:escape(str(v),quote=True)
    def paragraph(text,style):return '<p style="margin:0 0 8px;'+style+'">'+text+'</p>'
    def card(p):
        canonical=canonical_product_url(p)
        destination=campaign_link(canonical,campaign_key,'product_'+p['id'].rsplit('/',1)[-1],test=True) if campaign_key else canonical
        link='href="'+e(destination)+'" target="_blank" rel="noopener noreferrer"'
        parts=[]
        if display['image']:
            parts.append('<tr><td align="center" bgcolor="#f5f1e7" style="padding:'+('12px' if single else '6px')+'"><a '+link+' style="display:block;text-decoration:none"><img src="'+e(p['image'])+'" alt="'+e(image_alt(p))+'" width="'+('552' if single else '260')+'" border="0" style="display:block;width:100%;max-width:100%;height:auto;border:0"></a></td></tr>')
        info=[]
        if display['title']:
            info.append(paragraph('<a '+link+' style="color:#faf6eb;text-decoration:none">'+e(p['title'])+'</a>',
                'font-size:'+('21' if single and len(p['title'])<80 else '18' if single else '14')+'px;line-height:'+('27' if single else '19')+'px;font-weight:700;word-wrap:break-word'))
        ed=p['edition']
        if ed:
            if display['limit']:info.append(paragraph('LIMITED TO '+str(ed['limit'])+(' WORLDWIDE' if single else ''),'color:#d4b77d;font-size:11px;line-height:16px'))
            next_ok=display['next'] and ed['remaining']>0 and 1<=ed['next']<=ed['limit']
            if next_ok:info.append(paragraph('#'+format(ed['next'],'03d')+' / '+str(ed['limit']),'color:#faf6eb;font-size:'+('24' if single else '16')+'px;line-height:28px;font-weight:700'))
            status=['NEXT AVAILABLE'] if next_ok and single else []
            if display['remaining']:status.append(str(ed['remaining'])+' REMAINING' if ed['remaining'] else 'SOLD OUT')
            if status:info.append(paragraph(' · '.join(status),'color:#d6d0c4;font-size:11px;line-height:16px'))
        if display['price']:
            price='From '+e(price_label(p))
            if amount(p['compare_at']) and Decimal(p['compare_at'])>Decimal(p['price']):price+=' <s>'+e(price_label({**p,'price':p['compare_at']}))+'</s>'
            info.append(paragraph(price,'color:#d6d0c4;font-size:13px;line-height:18px'))
        if display['cta']:info.append('<a '+link+' style="display:inline-block;background:'+('#d4b77d;color:#111111' if single else '#151515;color:#eed9ad')+';border:1px solid #d4b77d;padding:'+('12px 18px' if single else '10px 6px')+';font-size:'+('13' if single else '11')+'px;line-height:18px;font-weight:700;text-decoration:none;text-transform:uppercase;word-wrap:break-word">'+e(cfg['cta'])+'</a>')
        parts.append('<tr><td align="'+('center' if single else 'left')+'" bgcolor="#151515" style="padding:'+('20px 16px' if single else '12px 8px')+';font-family:Arial,Helvetica,sans-serif">'+''.join(info)+'</td></tr>')
        return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:fixed">'+''.join(parts)+'</table>'
    heading=''
    if cfg.get('headline'):heading+=paragraph(e(cfg['headline']),'color:#eed9ad;font-size:24px;line-height:29px;font-family:Georgia,serif')
    if cfg.get('subtext'):heading+=paragraph(e(cfg['subtext']),'color:#d6d0c4;font-size:13px;line-height:19px')
    rows='<tr><td align="center" style="padding:16px 12px 8px">'+heading+'</td></tr>' if heading else ''
    if single:content=card(products[0])
    else:
        columns=desktop_columns(products);tiles=[]
        for i,p in enumerate(products):
            if i%2==0:tiles.append('<!--[if mso]><table role="presentation" width="100%"><tr><![endif]-->')
            tiles.append('<!--[if mso]><td width="50%" valign="top"><![endif]-->')
            tiles.append('<table class="sc-cat-item sc-cat-'+str(columns)+'" role="presentation" width="50%" cellspacing="0" cellpadding="0" style="display:inline-block;width:50%;vertical-align:top;border-collapse:collapse;table-layout:fixed"><tr><td style="padding:4px">'+card(p)+'</td></tr></table>')
            tiles.append('<!--[if mso]></td><![endif]-->')
            if i%2==1 or i==len(products)-1:tiles.append('<!--[if mso]></tr></table><![endif]-->')
        content=''.join(tiles)
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#111111" style="background:#111111;border-collapse:collapse;table-layout:fixed">'+rows+'<tr><td align="left" style="padding:8px;font-size:0">'+content+'</td></tr></table>'


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


def verify_catalogues(doc, catalogue):
    """Verify current facts before a new test operation; never rewrite the draft."""
    try:
        current = refresh_catalogues(doc, catalogue, fresh=True)
    except Exception:
        raise ValueError('Catalogue live facts could not be verified. Refresh catalogue and retry before testing.') from None
    changed = []
    for old, new in zip(doc.get('middle_sections', []), current.get('middle_sections', [])):
        if old['type'] != 'catalogue' or not old['visible']: continue
        for before, after in zip(old['products'], new['products']):
            if before != after:
                changed.append(dict(section_id=old['id'],section_type='catalogue',display_label='Catalogue',editable=True,
                    issue_type='stale_catalogue',count=1,message=before['title'][:120]+': live Shopify/edition facts changed — refresh catalogue before testing.'))
    if changed:
        from crm_campaign_issues import CampaignValidationError
        raise CampaignValidationError({'test':{'Catalogue product facts valid':False},'section_issues':changed})
    return current
