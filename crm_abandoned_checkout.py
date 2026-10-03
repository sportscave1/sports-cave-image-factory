"""Native checkout content. Preview state is never a live-send context."""
from copy import deepcopy
from decimal import Decimal,InvalidOperation
from html import escape
import re
from crm_tracking import public_https

BLOCK='abandoned_checkout_products'
TEMPLATE='Abandoned Checkout — Collector Reminder'


def dynamic(doc):return any(s.get('type')==BLOCK and s.get('visible') for s in doc.get('middle_sections',[]))


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


def preview_context(state,shop,*,refresh=False,auto_refresh=True):
    from time import monotonic
    from crm_campaign_home_cache import POOL,CAPACITY
    entry=state.get('abandoned_preview')
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
        entry=state['abandoned_preview']={'future':future,'started':monotonic(),'namespace':namespace,'last_good':last_good}
    if not entry['future'].done():return last_good,'Refreshing latest abandoned checkout…' if last_good else 'Loading latest abandoned checkout…'
    try:value=entry['future'].result()
    except Exception:return last_good,'Checkout preview temporarily unavailable.'
    if value:
        if entry.get('last_good')!=value:entry['last_good']=value
        return value,''
    return last_good,'No recent abandoned checkout available for preview.'


def block_html(data,*,test=False):
    rows=[]
    for item in data['items']:
        image='' if not item['image'] else '<img src="'+escape(item['image'],quote=True)+'" alt="'+escape(item['title'],quote=True)+'" width="540" style="display:block;width:100%;max-width:540px;height:auto;border:0;margin:0">'
        label=item['currency']+' '+format(Decimal(item['amount']),',.2f') if item['amount'] is not None else 'Price unavailable in sample preview'
        rows.append('<tr><td style="padding:14px 24px;font:15px/1.5 Arial;word-wrap:break-word"><p style="font-size:11px;color:#76633c">YOUR SELECTED EDITION</p>'+image+'<p style="font-weight:700">'+escape(item['title'])+'</p>'+('<p>'+escape(item['variant'])+'</p>' if item['variant'] else '')+'<p>Quantity: '+str(item['quantity'])+' · Line total: '+escape(label)+'</p></td></tr>')
    disabled=test or data.get('preview_only')
    cta='<span style="display:inline-block;background:#c8a346;color:#171717;padding:14px 24px;font:bold 15px Arial">'+('Recovery action disabled in test email' if test else 'Complete Your Order →')+'</span>' if disabled else '<a href="'+escape(data['recovery_url'],quote=True)+'" style="display:inline-block;background:#c8a346;color:#171717;padding:14px 24px;font:bold 15px Arial;text-decoration:none">Complete Your Order →</a>'
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;table-layout:fixed">'+''.join(rows)+'<tr><td align="center" style="padding:14px 24px">'+cta+'</td></tr></table>'


def hydrate(doc,data,*,test=False):
    result=deepcopy(doc)
    for section in result.get('middle_sections',[]):
        if section['type']==BLOCK:
            if section['visible'] and not data:raise ValueError('No recent abandoned checkout available for preview.')
            section.update(type='image',html=block_html(data,test=test) if section['visible'] else '')
        elif section['type'] in ('html','image'):reject_unresolved(section['html'])
    reject_unresolved(result.get('custom_html',''))
    return result


def publication_document(doc,trigger):
    """Validate authored content offline; recipient HTML is checked again at dispatch."""
    if dynamic(doc) and trigger!='abandoned':raise ValueError('Abandoned Checkout template requires Checkout abandoned trigger.')
    reject_unresolved(doc.get('custom_html',''))
    result=deepcopy(doc);result['middle_sections']=[s for s in result.get('middle_sections',[]) if s['type']!=BLOCK]
    for s in result['middle_sections']:
        if s['type'] in ('html','image'):reject_unresolved(s['html'])
    return result if 'middle_sections' in doc else doc


def apply_template(doc):
    from crm_middle_sections import commit_middle
    import uuid
    sections=[{'id':uuid.uuid4().hex,'type':'html','html_number':1,'visible':True,'html':'<table role="presentation" width="100%"><tr><td style="padding:24px;font:16px/1.6 Arial"><h2>YOUR COLLECTION AWAITS</h2><p>Still thinking it over?</p><p>You were close to adding this piece to your collection.<br>Pick up exactly where you left off below.</p></td></tr></table>'},
      {'id':uuid.uuid4().hex,'type':BLOCK,'visible':True},
      {'id':uuid.uuid4().hex,'type':'html','html_number':2,'visible':True,'html':'<table role="presentation" width="100%"><tr><td style="padding:16px 24px;font:14px/1.6 Arial">Questions about sizing or framing?<br>Just reply to this email.</td></tr></table>'}]
    doc['content_mode']='HTML';commit_middle(doc,sections);doc['copy_reviewed']=False
    doc['content']['subject']='Your collection awaits';doc['content']['preheader']='Pick up exactly where you left off.'


