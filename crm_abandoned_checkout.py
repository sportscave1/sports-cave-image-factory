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


def context(checkout):
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
        items.append({'title':title,'variant':variant,'quantity':quantity,'image':image,'amount':str(amount),'currency':currency})
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


def block_html(data,*,test=False):
    """Dynamic facts and semantic markup only. Theme belongs to authored HTML."""
    rows=[]
    for index,item in enumerate(data['items']):
        image='' if not item['image'] else '<img class="sc-cart-image" src="'+escape(item['image'],quote=True)+'" alt="'+escape(item['title'],quote=True)+'" style="display:block;width:100%;height:auto">'
        label=item['currency']+' '+format(Decimal(item['amount']),',.2f') if item['amount'] is not None else 'Price unavailable in sample preview'
        rows.append('<tr'+(' class="sc-cart-extra-items"' if index else '')+'><td class="sc-cart-image-wrap"><p class="sc-cart-label">YOUR SELECTED EDITION</p>'+image+'<p class="sc-cart-title">'+escape(item['title'])+'</p>'+('<p class="sc-cart-variant">'+escape(item['variant'])+'</p>' if item['variant'] else '')+'<p class="sc-cart-meta">Quantity: '+str(item['quantity'])+'</p><p class="sc-cart-price">Line total: '+escape(label)+'</p></td></tr>')
    disabled=test or data.get('preview_only')
    cta='<span class="sc-cart-button">'+('Recovery action disabled in test email' if test else 'Complete Your Order →')+'</span>' if disabled else '<a class="sc-cart-button" href="'+escape(data['recovery_url'],quote=True)+'">Complete Your Order →</a>'
    return '<table class="sc-cart-block" role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;table-layout:fixed">'+''.join(rows)+'<tr><td class="sc-cart-button-wrap" align="center">'+cta+'</td></tr></table>'


def hydrate(doc,data,*,test=False,preview=False):
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
    return compile_document(result,strict=not preview)


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
