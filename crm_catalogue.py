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
 editionMetafields:metafields(first:30,namespace:"sports_cave") { nodes { key value } }
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
            any(type(edition[k]) is not int or edition[k] < 0 for k in ('limit','next')) or
            any(edition[k] is not None and (type(edition[k]) is not int or not 0<=edition[k]<=edition['limit']) for k in ('sold','remaining')) or
            not 1 <= edition['next'] <= edition['limit']+1 or
            not isinstance(edition['status'], str) or len(edition['status']) > 100): raise ValueError('Invalid edition snapshot.')


UNAVAILABLE_EDITIONS = frozenset(('sold_out','sold out','closed','archived','expired','allocation_blocked','unavailable','exhausted','paused'))


def edition_available(ed):
    return bool(ed and ed['status'].lower() not in UNAVAILABLE_EDITIONS and
                1<=ed['next']<=ed['limit'] and ed.get('remaining')!=0 and ed.get('sold')!=ed['limit'])


def edition_for(p, rows, metafields=None):
    exact = [r for r in rows if product_id(r.get('shopify_product_gid') or r.get('shopify_product_id')) == p['id']]
    candidates = exact or [r for r in rows if r.get('shopify_handle') == p['handle'] and
                           not product_id(r.get('shopify_product_gid') or r.get('shopify_product_id'))]
    if len(candidates) != 1: return None
    r = candidates[0]
    if r.get('allocation_blocked') or r.get('active') is False or r.get('is_archived'): return None
    values = {'limit':r.get('run_edition_total') if r.get('run_edition_total') is not None else r.get('edition_total'),
              'next':r.get('run_next_edition_number') if r.get('run_next_edition_number') is not None else r.get('next_edition_number'),
              'sold':r.get('sold_count'), 'remaining':r.get('remaining_count')}
    if any(type(values[k]) is not int or values[k]<1 for k in ('limit','next')):return None
    if values['next']>values['limit']+1:return None
    status=str(r.get('run_status') or r.get('status') or '')[:100]
    if (r.get('sold_out') or r.get('is_sold_out') or values['next']>values['limit'] or
            type(values['remaining']) is int and values['remaining']<=0 or
            type(values['sold']) is int and values['sold']>=values['limit']):status='sold_out'
    if status.lower() in UNAVAILABLE_EDITIONS:values['remaining']=0
    for key in ('sold','remaining'):
        if type(values[key]) is not int or not 0<=values[key]<=values['limit']:values[key]=None
    # Sales and numbering are independent. Do not manufacture remaining from
    # the cursor, nor publish more editions than can still be allocated.
    remaining=values['remaining'];sold=values['sold']
    if remaining is not None and remaining>0 and (remaining>values['limit']-values['next']+1 or
            sold is not None and remaining+sold!=values['limit']):values['remaining']=None
    if r.get('next_edition_number') is not None and r['next_edition_number']!=values['next']:return None
    mirrors={m['key']:m.get('value') for m in (metafields or [])}
    if mirrors.get('edition_enabled')=='false' or mirrors.get('is_sold_out')=='true' or mirrors.get('edition_status','').lower() in UNAVAILABLE_EDITIONS:
        status='sold_out';values['remaining']=0
    # Read both canonical and existing legacy mirrors. A conflict is not fixed
    # by choosing whichever value looks nicer; exclude until reconciled.
    for field,keys in {'limit':('edition_total',),'next':('edition_next_number','next_edition_number'),
                       'sold':('edition_sold_count','sold_count'),'remaining':('edition_remaining','remaining_count')}.items():
        for key in keys:
            if key not in mirrors:continue
            try:value=int(mirrors[key])
            except (ValueError,TypeError):return None
            if values[field] is not None and value!=values[field]:return None
    return {**values,'status':status}


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

    def resolve(self, ids, market='AU', *, fresh=False, allow_missing=False):
        ids = list(dict.fromkeys(ids))
        if not ids: return []
        if len(ids)>50 or any(product_id(i)!=i for i in ids): raise ValueError('Invalid catalogue selection.')
        country = {'AU':'AU','US':'US','UK':'GB','Global':'AU','CA':'CA','NZ':'NZ'}[market]
        # The edition metafield connection adds nested cost. Keep each Admin
        # query below its cost limit without reducing the selected product set.
        nodes = []
        for start in range(0,len(ids),20):
            nodes.extend(self.shop.query(FACTS_QUERY, {'ids':ids[start:start+20],'country':country}, 'catalogue products', 60, fresh)['nodes'])
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
        by_node={n['id']:n for n in nodes if n}
        for p in products:
            p['edition'] = edition_for(p, rows, (by_node[p['id']].get('editionMetafields') or {}).get('nodes',[]))
            validate_snapshot(p)
        by_id = {p['id']:p for p in products}
        if not allow_missing and set(by_id) != set(ids): raise ValueError('A selected product is no longer available. Remove it or refresh the catalogue.')
        return [by_id[i] for i in ids if i in by_id]


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
    """Catalogue pairs stay two-up in every email client and viewport."""
    return 2


def image_alt(p):
    from crm_campaign_html import import_html
    value=' '.join(import_html(p.get('image_alt') or '')[1].split())
    return value if value.casefold() not in ('','image','product image','wall art image') else p['title']


def collection_display_title(title):
    """Email collection copy only; keep canonical product facts untouched."""
    cleaned, count = re.subn(r'\bwall\s+art\b', '', title, flags=re.IGNORECASE)
    if not count:
        return title
    cleaned = ' '.join(cleaned.split()).strip(' -–—|:;,/·•')
    return cleaned or title


def catalogue_html(section, *, campaign_key=''):
    """Snapshot-only pairs with shared field rows, including Word email clients.

    Each pair owns its table: the tallest cell sets only that pair's field height.
    No title estimates, fixed text heights, media queries or client-side layout.
    """
    if section['settings'].get('smart'):return ''  # Recipient hydration owns these cards.
    cfg=section['settings'];display=cfg['display']
    products=[p for p in section['products'] if not product_issues(p,cfg)]
    if not products:return ''
    single=len(products)==1;e=lambda v:escape(str(v),quote=True)
    table='<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;table-layout:fixed">'
    def paragraph(text,style):return '<p style="margin:0;'+style+'">'+text+'</p>'
    def fields(p):
        canonical=canonical_product_url(p)
        destination=campaign_link(canonical,campaign_key,'product_'+p['id'].rsplit('/',1)[-1],test=True) if campaign_key else canonical
        link='href="'+e(destination)+'" target="_blank" rel="noopener noreferrer"'
        result={}
        if display['image']:
            result['image']='<a '+link+' style="display:block;text-decoration:none"><img src="'+e(p['image'])+'" alt="'+e(image_alt(p))+'" width="274" border="0" style="display:block;width:100%;max-width:100%;height:auto;border:0"></a>'
        if display['title']:
            result['title']=paragraph('<a '+link+' style="color:#faf6eb;text-decoration:none">'+e(collection_display_title(p['title']))+'</a>',
                'font-size:14px;line-height:19px;font-weight:700;word-wrap:break-word')
        ed=p['edition']
        if ed:
            if display['limit']:result['limit']=paragraph('LIMITED TO '+str(ed['limit'])+(' WORLDWIDE' if single else ''),'color:#d4b77d;font-size:11px;line-height:16px')
            next_ok=display['next'] and edition_available(ed)
            if next_ok:result['next']=paragraph('#'+format(ed['next'],'03d')+' / '+str(ed['limit']),'color:#faf6eb;font-size:16px;line-height:28px;font-weight:700')
            status=['NEXT AVAILABLE'] if next_ok and single else []
            if display['remaining'] and ed['remaining'] is not None:status.append(str(ed['remaining'])+' REMAINING' if ed['remaining'] else 'SOLD OUT')
            if status:result['remaining']=paragraph(' · '.join(status),'color:#d6d0c4;font-size:11px;line-height:16px')
        if display['price']:
            price='From '+e(price_label(p))
            if amount(p['compare_at']) and Decimal(p['compare_at'])>Decimal(p['price']):price+=' <s>'+e(price_label({**p,'price':p['compare_at']}))+'</s>'
            result['price']=paragraph(price,'color:#d6d0c4;font-size:13px;line-height:18px')
        if display['cta']:
            result['cta']=table+'<tr><td align="center" bgcolor="#151515" style="border:1px solid #d4b77d"><a '+link+' style="display:block;color:#eed9ad;padding:12px 4px;font-size:11px;line-height:18px;font-weight:700;text-decoration:none;text-transform:uppercase;word-wrap:break-word">'+e(cfg['cta'])+'</a></td></tr></table>'
        return result
    pairs=[]
    for start in range(0,len(products),2):
        pair=[fields(p) for p in products[start:start+2]]
        rows=[]
        for field in ('image','title','limit','next','remaining','price','cta'):
            if not any(field in p for p in pair):continue
            cells=[]
            for index in range(2):
                if index>=len(pair):
                    # Empty layout cell only; never a fabricated product or link.
                    cells.append('<td width="50%" bgcolor="#111111"></td>');continue
                padding='0' if field=='image' else '8px 8px 0'
                if field=='cta':padding='8px'
                cells.append('<td width="50%" valign="top" bgcolor="#151515" style="padding:'+padding+';border-left:4px solid #111111;border-right:4px solid #111111;font-family:Arial,Helvetica,sans-serif;word-wrap:break-word">'+pair[index].get(field,'')+'</td>')
            rows.append('<tr>'+''.join(cells)+'</tr>')
        # A shared bottom edge also keeps cards equal when the CTA is disabled.
        rows.append('<tr>'+''.join('<td width="50%" height="8" bgcolor="'+('#151515' if i<len(pair) else '#111111')+'" style="border-left:4px solid #111111;border-right:4px solid #111111;font-size:0;line-height:0"></td>' for i in range(2))+'</tr>')
        pairs.append('<tr><td style="padding:0 0 8px">'+table+''.join(rows)+'</table></td></tr>')
    heading=''
    if cfg.get('headline'):heading+=paragraph(e(cfg['headline']),'margin-bottom:8px;color:#eed9ad;font-size:24px;line-height:29px;font-family:Georgia,serif')
    if cfg.get('subtext'):heading+=paragraph(e(cfg['subtext']),'color:#d6d0c4;font-size:13px;line-height:19px')
    rows='<tr><td align="center" style="padding:16px 12px 8px">'+heading+'</td></tr>' if heading else ''
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#111111" style="background:#111111;border-collapse:collapse;table-layout:fixed">'+rows+'<tr><td style="padding:8px 4px 0">'+table+''.join(pairs)+'</table></td></tr></table>'


def refresh_catalogues(doc, catalogue, *, fresh=True):
    """Returns a document copy; counters are always read from Edition Ops."""
    result = deepcopy(doc)
    sections = result.get('middle_sections', [])
    ids = list(dict.fromkeys(p['id'] for s in sections if s['type']=='catalogue' and s['visible'] and not s['settings'].get('smart') for p in s['products']))
    if not ids: return result
    facts = {p['id']:p for p in catalogue.resolve(ids, result['market'], fresh=fresh)}
    for s in sections:
        if s['type']=='catalogue' and s['visible'] and not s['settings'].get('smart'): s['products'] = [deepcopy(facts[p['id']]) for p in s['products']]
    return result


def verify_catalogues(doc, catalogue):
    """Verify current facts before a new test operation; never rewrite the draft."""
    try:
        current = refresh_catalogues(doc, catalogue, fresh=True)
    except Exception:
        raise ValueError('Catalogue live facts could not be verified. Refresh catalogue and retry before testing.') from None
    changed = []
    for old, new in zip(doc.get('middle_sections', []), current.get('middle_sections', [])):
        if old['type'] != 'catalogue' or not old['visible'] or old['settings'].get('smart'): continue
        for before, after in zip(old['products'], new['products']):
            if before != after:
                changed.append(dict(section_id=old['id'],section_type='catalogue',display_label='Catalogue',editable=True,
                    issue_type='stale_catalogue',count=1,message=before['title'][:120]+': live Shopify/edition facts changed — refresh catalogue before testing.'))
    if changed:
        from crm_campaign_issues import CampaignValidationError
        raise CampaignValidationError({'test':{'Catalogue product facts valid':False},'section_issues':changed})
    return current
