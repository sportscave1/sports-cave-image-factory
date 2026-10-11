"""Recipient-scoped artwork blocks inside the existing HTML document contract.

Only configuration is persisted. Recipient facts are supplied by the delivery
adapter and rendered into a copy; they never enter templates or editor state.
"""
from copy import deepcopy
from html import escape
import json
import re
from urllib.parse import urlsplit

from crm_campaign_html import email_image_url

SOURCES = ('Actual Purchased Product', 'Related Products', 'Featured Collection',
           'Verified New Releases', 'Verified Bestsellers', 'Static Selected Image', 'No Image')
MARKER = re.compile(r'<!--SC_COLLECTOR_IMAGE_V1:([0-9a-f]+)-->')
COLLECTION = 'https://www.sportscaveshop.com/collections/all'
ACCOUNT = 'https://account.sportscaveshop.com/pages/019ef355-648a-7996-8977-897320e5ffd7'


def validate(config):
    if not isinstance(config, dict) or set(config) != {'source','count','product_ids','collection_id','image','alt'}:
        raise ValueError('Invalid personalised image settings.')
    if config['source'] not in SOURCES or type(config['count']) is not int or not 1 <= config['count'] <= 3:
        raise ValueError('Choose an image source and one to three products.')
    ids = config['product_ids']
    if not isinstance(ids, list) or len(ids)>12 or any(not isinstance(i,str) or not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*',i) for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('Choose up to twelve distinct Shopify products.')
    if not isinstance(config['collection_id'], str) or config['collection_id'] and not re.fullmatch(r'gid://shopify/Collection/[1-9][0-9]*',config['collection_id']):
        raise ValueError('Choose a Shopify collection.')
    for field in ('image','alt'):
        if not isinstance(config[field],str) or len(config[field])>2000:raise ValueError('Invalid image text.')
    if config['image'] and not durable_image(config['image']):raise ValueError('Use a durable public email image.')
    if config['source']=='Static Selected Image' and (not config['image'] or not config['alt'].strip()):
        raise ValueError('Choose an image and provide its description.')
    return config


def settings(source='No Image', count=1, **overrides):
    return validate({**dict(source=source,count=count,product_ids=[],collection_id='',image='',alt=''),**overrides})


def marker(config):
    return '<!--SC_COLLECTOR_IMAGE_V1:'+json.dumps(validate(config),sort_keys=True,separators=(',',':')).encode().hex()+'-->'


def configurations(doc):
    if not isinstance(doc,dict):raise ValueError('Invalid email document.')
    sources = [s.get('html','') for s in doc.get('middle_sections',[]) if s.get('visible')]
    if 'middle_sections' not in doc:sources=[doc.get('custom_html','')]
    result=[]
    for source in sources:
        if 'SC_COLLECTOR_IMAGE_V1:' in MARKER.sub('',source):raise ValueError('Damaged personalised image block.')
        for match in MARKER.finditer(source):
            if len(match[1])>16000:raise ValueError('Personalised image settings are too large.')
            try:config=json.loads(bytes.fromhex(match[1]).decode())
            except (ValueError,UnicodeError):raise ValueError('Invalid personalised image block.') from None
            result.append(validate(config))
    if len(result)>12:raise ValueError('Use at most twelve personalised image blocks.')
    return result


def durable_image(value):
    if not isinstance(value,str):return ''
    from urllib.parse import parse_qsl
    if any(k.lower() in {'token','access_token','api_key','key','password','hmac','signature','expires','sig','se','x-amz-signature','x-goog-signature'} for k,_ in parse_qsl(urlsplit(value).query)):return ''
    return email_image_url(value)


def card(product, *, small=False):
    title=product.get('title','')
    if not isinstance(title,str) or not title.strip():return ''
    e=lambda x:escape(str(x),quote=True)
    image=durable_image(product.get('image',''))
    parts=[]
    if image:
        width=240 if small else 520
        parts.append(f'<img src="{e(image)}" alt="{e(title)}" width="{width}" style="display:block;width:100%;max-width:{width}px;height:auto;border:0;margin:0 auto">')
    parts.append('<p style="margin:16px 0 6px;color:#f4efe5;font-family:Georgia,serif;font-size:22px;line-height:28px">'+e(title)+'</p>')
    for key in ('variant','edition'):
        value=product.get(key)
        if value and value!='Default Title':parts.append('<p style="margin:4px 0;color:#d3b779;font-size:14px;line-height:21px">'+e(value)+'</p>')
    from crm_catalogue import canonical_product_url
    url=canonical_product_url({'url':product.get('url','')})
    if url and not product.get('owned'):
        parts.append('<p style="margin:14px 0"><a style="color:#d3b779;font-size:14px" href="'+e(url)+'">Explore artwork</a></p>')
    return '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#171717"><tr><td align="center" style="padding:20px 16px;border-bottom:1px solid #39342b;font-family:Arial,sans-serif">'+''.join(parts)+'</td></tr></table>'


def render(doc, facts=None, *, preview=False):
    """No network or writes. Unavailable optional imagery is omitted."""
    configs=configurations(doc)
    if not configs:return doc
    facts=facts or {};result=deepcopy(doc)
    emitted=set()
    def replace(match):
        config=validate(json.loads(bytes.fromhex(match[1]).decode()))
        key=marker(config)
        if config['source']=='No Image':return ''
        if config['source']=='Static Selected Image':
            return '<img src="'+escape(durable_image(config['image']),quote=True)+'" alt="'+escape(config['alt'],quote=True)+'" width="520" style="display:block;width:100%;max-width:520px;height:auto;margin:0 auto;border:0">'
        products=facts.get(key,[])
        if config['source']!='Actual Purchased Product':
            unique=[]
            for p in products:
                identity=p.get('id') or p.get('url')
                if identity and identity in emitted:continue
                unique.append(p)
                if identity:emitted.add(identity)
            products=unique
        count=min(config['count'],2 if config['source']=='Actual Purchased Product' else 3)
        body=''.join(card(p,small=config['source']=='Actual Purchased Product' and config['count']==1) for p in products[:count])
        if preview:
            label='Sample preview · fixture artwork' if body else 'Sample preview · no verified artwork selected'
            body='<p style="color:#d3b779;font:12px Arial;padding:12px 16px">'+label+'</p>'+body
        return body
    for section in result.get('middle_sections',[]):
        if 'html' in section:section['html']=MARKER.sub(replace,section['html'])
    emitted.clear()  # custom_html is a mirror, not a second displayed section.
    result['custom_html']=MARKER.sub(replace,result.get('custom_html',''))
    return result


def sample_facts(doc):
    """Public artwork examples only; never used by the delivery resolver."""
    from pathlib import Path
    rows=json.loads((Path(__file__).parent/'templates/collector_preview_artwork.json').read_text(encoding='utf-8'))['artwork']
    configs=configurations(doc);owned=any(c['source']=='Actual Purchased Product' for c in configs)
    return {marker(c):([{**row,'owned':True,'variant':'Synthetic variant · '+('Large black frame' if i==0 else 'Small black frame'),
                        'edition':'Synthetic allocation · #007/100' if i==0 else None} for i,row in enumerate(rows)] if c['source']=='Actual Purchased Product'
                       else deepcopy(rows[1:] if owned else rows))[:c['count']] for c in configs
            if c['source'] not in ('No Image','Static Selected Image')}


def purchased(order, customer_id, products, *, allocation_reader=None):
    """Exact customer/order/product join. Never use another order as fallback."""
    if not customer_id or not re.fullmatch(r'gid://shopify/Customer/[1-9][0-9]*',customer_id):raise ValueError('Verified customer identity required.')
    if not order:return []
    if (order.get('customer') or {}).get('id')!=customer_id:raise ValueError('Purchased artwork recipient mismatch.')
    if not re.fullmatch(r'gid://shopify/Order/[1-9][0-9]*',str(order.get('id',''))):raise ValueError('Verified order identity required.')
    from crm_lifecycle_policy import qualifying
    if not qualifying(order) or order.get('displayFinancialStatus')=='PARTIALLY_REFUNDED':return []
    by_id={p['id']:p for p in products};result=[]
    for line in (order.get('lineItems') or {}).get('nodes',[])[:2]:
        pid=(line.get('product') or {}).get('id');product=by_id.get(pid,{})
        if not pid or not line.get('title'):continue
        variant=line.get('variant') or {}
        exact=(variant.get('product') or {}).get('id')==pid
        image=(variant.get('image') or {}).get('url','') if exact else ''
        image=durable_image(image) or durable_image((product.get('featuredImage') or {}).get('url',''))
        edition=allocation_reader(order['id'],customer_id,pid,line.get('id')) if allocation_reader else None
        if not isinstance(edition,str) or not re.fullmatch(r'#[0-9]+/[0-9]+',edition):edition=None
        if edition:
            number,total=map(int,edition[1:].split('/'))
            if not 1<=number<=total:edition=None
        result.append(dict(title=line['title'],variant=line.get('variantTitle',''),image=image,edition=edition,owned=True))
    return result
