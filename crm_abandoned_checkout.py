"""Native checkout content. Preview state is never a live-send context."""
from copy import deepcopy
from decimal import Decimal,InvalidOperation
from html import escape
import re
from crm_tracking import public_https

BLOCK='abandoned_checkout_products'
TEMPLATE='Abandoned Checkout — Collector Reminder'


def dynamic(doc):
    from crm_checkout_styles import count
    return bool(count(doc))


def reject_unresolved(value):
    if re.search(r'\{\{|\{%|SC_ABANDONED_CHECKOUT',str(value)):
        raise ValueError('Unresolved checkout template syntax. Use the Abandoned Checkout template instead of Liquid.')


def money(value):
    try:amount=Decimal(str(value.get('amount','')))
    except (InvalidOperation,AttributeError,ValueError):raise ValueError('Checkout price unavailable.') from None
    currency=value.get('currencyCode','')
    if not amount.is_finite() or amount<0 or not re.fullmatch('[A-Z]{3}',currency):raise ValueError('Checkout price unavailable.')
    return amount,currency


def context(checkout,*,edition_reader=None):
    if not isinstance(checkout,dict) or checkout.get('completedAt'):raise ValueError('Checkout is unavailable or already recovered.')
    identity=checkout.get('id','');url=checkout.get('abandonedCheckoutUrl','')
    if not re.fullmatch(r'gid://shopify/AbandonedCheckout/\d+',identity) or not public_https(url):raise ValueError('Checkout recovery data unavailable.')
    lines=checkout.get('lineItems') or {};nodes=lines.get('nodes')
    if not isinstance(nodes,list) or not nodes or len(nodes)>500 or (lines.get('pageInfo') or {}).get('hasNextPage'):raise ValueError('Complete checkout products unavailable.')
    items=[]
    for item in nodes:
        title=item.get('title') or (item.get('product') or {}).get('title')
        quantity=item.get('quantity');variant=item.get('variantTitle') or (item.get('variant') or {}).get('title') or ''
        if not isinstance(title,str) or not title.strip() or type(quantity) is not int or quantity<1:raise ValueError('Checkout product unavailable.')
        price=item.get('discountedTotalPriceWithCodeDiscount') or item.get('discountedTotalPriceSet') or item.get('originalTotalPriceSet')
        if price:amount,currency=money(price.get('presentmentMoney') or price.get('shopMoney'))
        else:
            unit=item.get('originalUnitPriceSet') or {};amount,currency=money(unit.get('presentmentMoney') or unit.get('shopMoney'));amount*=quantity
        image=(item.get('image') or {}).get('url','')
        if image:
            from crm_campaign_html import email_image_url
            image=email_image_url(image)
            if not image:raise ValueError('Checkout image needs a public HTTPS destination.')
        product=(item.get('variant') or {}).get('product') or item.get('product') or {}
        items.append({'title':title,'variant':variant,'quantity':quantity,'image':image,'amount':str(amount),'currency':currency,
                      'product_id':product.get('id'),'edition':None})
    # Read existing ledger facts once per context, never during HTML rendering.
    # This projection has next/limit facts, but no checkout reservation authority.
    from crm_catalogue import product_id,edition_for
    ids=list(dict.fromkeys(product_id(item['product_id']) for item in items if product_id(item['product_id'])))
    if ids:
        try:
            if edition_reader is None:
                from supabase_backend import list_edition_products_read_only
                edition_reader=list_edition_products_read_only
            rows=[]
            for start in range(0,len(ids),50):
                rows.extend(edition_reader(product_ids=ids[start:start+50],handles=[],limit=100))
            for item in items:
                pid=product_id(item['product_id'])
                if not pid:continue
                item['edition']=edition_for({'id':pid,'handle':''},rows)
                exact=[row for row in rows if product_id(row.get('shopify_product_gid') or row.get('shopify_product_id'))==pid]
                if item['edition'] is None and len(exact)==1:
                    row=exact[0];limit=row.get('edition_total')
                    if not row.get('allocation_blocked') and row.get('active') is not False and type(limit) is int and limit>0:
                        item['edition']={'limit':limit}
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning('checkout_editions_unavailable type=%s',type(exc).__name__)
    customer=checkout.get('customer') or {}
    return {'checkout_id':identity,'customer_id':customer.get('id'),'created_at':checkout.get('createdAt'),
      'label':' '.join(str(customer.get(k) or '').strip() for k in ('firstName','lastName')).strip() or customer.get('email') or 'latest abandoned checkout',
      'recovery_url':url,'items':items}


def complete(shop,checkout):
    result=deepcopy(checkout)
    if not isinstance(result,dict):raise ValueError('Checkout unavailable.')
    connection=result.get('lineItems') or {};nodes=connection.get('nodes',[]);seen=set();cursors=set()
    for _ in range(5):
        page=connection.get('pageInfo') or {}
        if not page.get('hasNextPage'):break
        cursor=page.get('endCursor')
        if not cursor or cursor in cursors:raise ValueError('Checkout products changed. Retry verification.')
        cursors.add(cursor)
        connection=shop.checkout_lines(result['id'],cursor,fresh=True)
        if not isinstance(connection,dict) or not connection.get('nodes'):raise ValueError('Complete checkout products unavailable.')
        nodes.extend(connection['nodes'])
    if (connection.get('pageInfo') or {}).get('hasNextPage') or len(nodes)>500:raise ValueError('Checkout exceeds supported product bound.')
    for item in nodes:
        if item.get('id') and item['id'] in seen:raise ValueError('Checkout products changed. Retry verification.')
        if item.get('id'):seen.add(item['id'])
    result['lineItems']={'nodes':nodes,'pageInfo':{'hasNextPage':False}}
    return result


def latest(shop):
    """Small descending pages; invalid candidates never become sample data."""
    after=None;seen=set()
    for _ in range(4):
        page=shop.abandoned_preview(after=after,fresh=True)
        for checkout in page['nodes']:
            try:return context(complete(shop,checkout))
            except ValueError:continue
        info=page.get('pageInfo') or {}
        if not info.get('hasNextPage'):return None
        after=info.get('endCursor')
        if not after or after in seen:raise ValueError('Checkout preview pagination unavailable.')
        seen.add(after)
    return None


def preview_context(state,shop,*,refresh=False,auto_refresh=True,slot='abandoned_preview'):
    from time import monotonic
    from crm_campaign_home_cache import POOL,CAPACITY
    entry=state.get(slot)
    namespace=getattr(shop,'namespace',None)
    namespace=namespace if isinstance(namespace,str) else 'configured-shop'
    if entry and entry.get('namespace')!=namespace:entry=None
    last_good=(entry or {}).get('last_good')
    if entry and entry['future'].done():
        try:last_good=entry['future'].result() or last_good
        except Exception:pass
    if not entry or (entry['future'].done() and (refresh or (auto_refresh and monotonic()-entry['started']>=45))):
        if not CAPACITY.acquire(blocking=False):return last_good,'Refreshing latest abandoned checkout…'
        def load():
            try:return latest(shop)
            finally:CAPACITY.release()
        try:future=POOL.submit(load)
        except RuntimeError:CAPACITY.release();return last_good,'Checkout preview temporarily unavailable.'
        entry=state[slot]={'future':future,'started':monotonic(),'namespace':namespace,'last_good':last_good}
    if not entry['future'].done():return last_good,'Refreshing latest abandoned checkout…' if last_good else 'Loading latest abandoned checkout…'
    try:value=entry['future'].result()
    except Exception:return last_good,'Checkout preview temporarily unavailable.'
    if value:
        if entry.get('last_good')!=value:entry['last_good']=value
        return value,''
    return last_good,'No recent abandoned checkout available for preview.'


def variant_details(value):
    """Separate only recognisable dimensions; preserve unknown product options."""
    value=str(value or '').strip()
    match=re.search(r'\s+[-–—]\s+(\d+(?:\.\d+)?\s*[×x]\s*\d+(?:\.\d+)?\s*cm(?:\s*\([^\n<>]+\))?)$',value,re.I)
    dimensions=match[1] if match else ''
    variant=value[:match.start()].strip() if match else value
    parts=[part.strip() for part in variant.split('/')]
    if parts and parts[0] in {'Black','Oak','White','Unframed','Black Frame','Oak Frame','White Frame'}:
        parts[0]={'Black':'Black Frame','Oak':'Oak Frame','White':'White Frame'}.get(parts[0],parts[0])
        variant=' · '.join(parts)
    return variant,dimensions


def edition_label(edition):
    if not isinstance(edition,dict):return ''
    limit=edition.get('limit');number=edition.get('next')
    if type(limit) is not int or limit<1:return ''
    if type(number) is int and 1<=number<=limit and edition.get('remaining',0)>0:
        return 'YOUR EDITION NUMBER WILL BE #'+str(number).zfill(3 if limit==100 else len(str(limit)))+'/'+str(limit)
    return 'LIMITED TO '+str(limit)+' WORLDWIDE'


def block_html(data,*,test=False):
    """Dynamic facts and semantic markup only. Theme belongs to authored HTML."""
    rows=[]
    for index,item in enumerate(data['items']):
        image='' if not item['image'] else '<img class="sc-cart-image" src="'+escape(item['image'],quote=True)+'" alt="'+escape(item['title'],quote=True)+'" style="display:block;width:100%;height:auto">'
        from crm_catalogue import price_label
        price=price_label({'currency':item['currency'],'price':item['amount']}) if item['amount'] is not None else 'Price unavailable in sample preview'
        variant,dimensions=variant_details(item['variant']);label=edition_label(item.get('edition'))
        rows.append('<tr'+(' class="sc-cart-extra-items"' if index else '')+'><td class="sc-cart-image-wrap">'+
          ('<p class="sc-cart-label">'+escape(label)+'</p>' if label else '')+image+
          '<p class="sc-cart-title">'+escape(item['title'])+'</p>'+
          ('<p class="sc-cart-variant">'+escape(variant)+'</p>' if variant else '')+
          ('<p class="sc-cart-dimensions">'+escape(dimensions)+'</p>' if dimensions else '')+
          '<p class="sc-cart-meta"><span class="sc-cart-qty">Qty '+str(item['quantity'])+'</span>'+
          '<span class="sc-cart-divider"> | </span><span class="sc-cart-price">'+escape(price)+'</span></p>'+
          '<hr class="sc-cart-rule"></td></tr>')
    disabled=test or data.get('preview_only')
    cta='<span class="sc-cart-button">'+('Recovery action disabled in test email' if test else 'Complete Your Order →')+'</span>' if disabled else '<a class="sc-cart-button" href="'+escape(data['recovery_url'],quote=True)+'">Complete Your Order →</a>'
    return '<table class="sc-cart-block" role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;table-layout:fixed">'+''.join(rows)+'<tr><td class="sc-cart-button-wrap" align="center">'+cta+'</td></tr></table>'


def hydrate(doc,data,*,test=False,preview=False,preview_warnings=None):
    from crm_checkout_styles import MARKER,compile_document
    result=deepcopy(doc)
    for section in result.get('middle_sections',[]):
        if section['type']==BLOCK:
            if section['visible'] and not data:raise ValueError('No recent abandoned checkout available for preview.')
            section.update(type='image',html=block_html(data,test=test) if section['visible'] else '')
        elif section['type'] in ('html','image'):
            if MARKER in section['html']:
                if not data:raise ValueError('Checkout context could not be resolved.')
                section['html']=section['html'].replace(MARKER,block_html(data,test=test))
            reject_unresolved(section['html'])
    if 'middle_sections' in result:
        result['custom_html']=next((s['html'] for s in result['middle_sections'] if s.get('html_number')==1),'')
    elif MARKER in result.get('custom_html',''):
        if not data:raise ValueError('Checkout context could not be resolved.')
        result['custom_html']=result['custom_html'].replace(MARKER,block_html(data,test=test))
    reject_unresolved(result.get('custom_html',''))
    if not preview:return compile_document(result,strict=True)
    try:return compile_document(result,strict=False)
    except Exception as exc:
        # Editor-only recovery. Delivery/publication keep strict compilation.
        import logging
        logging.getLogger(__name__).error('checkout_preview_css_failed type=%s',type(exc).__name__)
        from crm_checkout_styles import compile_html,rules,default_html
        theme=rules(default_html())
        if 'middle_sections' in result:
            for section in result['middle_sections']:
                if section.get('type') in ('html','image'):section['html']=compile_html(section['html'],theme)
            result['custom_html']=next((s['html'] for s in result['middle_sections'] if s.get('html_number')==1),'')
        else:result['custom_html']=compile_html(result.get('custom_html',''),theme)
        if preview_warnings is not None:preview_warnings.append('Template styles unavailable · preview uses safe defaults.')
        return result


def publication_document(doc,trigger):
    """Validate authored HTML offline; enrollment data is resolved at dispatch."""
    from crm_checkout_styles import MARKER,count,compile_document
    total=count(doc)
    if total and trigger!='abandoned':raise ValueError('Abandoned Checkout template requires Checkout abandoned trigger.')
    if total>1:raise ValueError('Use exactly one abandoned checkout products block.')
    result=deepcopy(doc);result['middle_sections']=[s for s in result.get('middle_sections',[]) if s['type']!=BLOCK]
    for s in result['middle_sections']:
        if s['type'] in ('html','image'):
            s['html']=s['html'].replace(MARKER,'');reject_unresolved(s['html'])
    result['custom_html']=result.get('custom_html','').replace(MARKER,'');reject_unresolved(result['custom_html'])
    if 'middle_sections' not in doc:result.pop('middle_sections',None)
    return compile_document(result) if total else result


def apply_template(doc,html=None):
    from crm_middle_sections import commit_middle
    from crm_checkout_styles import MARKER,default_html
    import uuid
    html=default_html() if html is None else html
    if html.count(MARKER)!=1:raise ValueError('Keep exactly one protected checkout insertion point.')
    before,after=html.split(MARKER)
    sections=[{'id':uuid.uuid4().hex,'type':'html','html_number':1,'visible':True,'html':before},
      {'id':uuid.uuid4().hex,'type':BLOCK,'visible':True},
      {'id':uuid.uuid4().hex,'type':'html','html_number':2,'visible':True,'html':after}]
    doc['content_mode']='HTML';commit_middle(doc,sections);doc['copy_reviewed']=False
    doc['content']['subject']='Your collection awaits';doc['content']['preheader']='Pick up exactly where you left off.'
