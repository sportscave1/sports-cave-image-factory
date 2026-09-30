"""Small structured email design system; all copy is escaped, no arbitrary HTML."""
from copy import deepcopy
from html import escape
import re
import uuid
from crm_tracking import asset_url, public_https, campaign_link

KINDS=('heading','text','image','button','product','product_grid','divider','spacer')
FIELDS={
 'heading':{'text'}, 'text':{'text'}, 'image':{'url','alt','decorative'},
 'button':{'label','url'}, 'product':{'products'}, 'product_grid':{'products'},
 'divider':set(), 'spacer':{'height'},
}
PRODUCT_FIELDS={'id','title','url','image','alt','variant_id','variant_title','market','price','currency','facts_checked_at'}
PURPOSES=('Collector Launch','New Editions','Collection Spotlight','Final Editions','Offer / Announcement','Collector Newsletter')
STARTERS=('Collector Launch','New Editions','Collector Note')


def block(kind,**data):
    defaults={'heading':{'text':''},'text':{'text':''},'image':{'url':'','alt':'','decorative':False},
              'button':{'label':'Explore the collection','url':''},'product':{'products':[]},
              'product_grid':{'products':[]},'divider':{},'spacer':{'height':16}}
    return {'id':'b_'+uuid.uuid4().hex[:16],'type':kind,**defaults[kind],**data}


def starter(name):
    if name not in STARTERS: raise ValueError('Unknown starter.')
    title={'Collector Launch':'A moment worth collecting','New Editions':'New collector editions','Collector Note':'A note for collectors'}[name]
    items=[block('heading',text=title),block('text',text='Some sporting moments stay with us. Discover a piece that belongs in your collection.')]
    if name!='Collector Note': items.append(block('product' if name=='Collector Launch' else 'product_grid'))
    items.append(block('button'))
    return items


def validate_blocks(blocks):
    if not isinstance(blocks,list) or len(blocks)>30: raise ValueError('Use at most 30 email blocks.')
    ids=set()
    for b in blocks:
        if not isinstance(b,dict) or b.get('type') not in KINDS or set(b)!=FIELDS[b['type']]|{'id','type'}: raise ValueError('Invalid structured email block.')
        if not isinstance(b['id'],str) or not re.fullmatch(r'b_[a-zA-Z0-9_-]{1,60}',b['id']) or b['id'] in ids: raise ValueError('Block identifiers must be unique.')
        ids.add(b['id'])
        for key in FIELDS[b['type']]-{'products','height','decorative'}:
            if not isinstance(b[key],str) or len(b[key])>12000: raise ValueError('Invalid block text.')
        if b['type']=='image' and type(b['decorative']) is not bool: raise ValueError('Invalid image decoration flag.')
        if b['type']=='spacer' and (type(b['height']) is not int or not 8<=b['height']<=64): raise ValueError('Spacer must be 8–64 pixels.')
        if 'products' in b:
            if not isinstance(b['products'],list) or len(b['products'])>(4 if b['type']=='product_grid' else 1): raise ValueError('Too many products in this block.')
            for p in b['products']:
                if not isinstance(p,dict) or set(p)-PRODUCT_FIELDS or not all(isinstance(v,str) and len(v)<=2000 for v in p.values()): raise ValueError('Invalid canonical product snapshot.')
                if not re.fullmatch(r'gid://shopify/Product/\d+',p.get('id','')): raise ValueError('Select a canonical Shopify product.')
    return blocks


def duplicate_block(b):
    result=deepcopy(b); result['id']=block(b['type'])['id']; return result


def block_checks(blocks,market):
    checks={'All design placeholders replaced':True,'Images use durable public JPEG/PNG URLs':True,
            'Image alt text complete':True,'CTA label and HTTPS URL valid':True,'Market-specific product prices verified':True}
    for b in blocks:
        kind=b['type']
        if kind in ('text','heading'): checks['All design placeholders replaced'] &= bool(b['text'].strip())
        if kind=='image':
            checks['Images use durable public JPEG/PNG URLs'] &= asset_url(b['url'])
            checks['Image alt text complete'] &= b['decorative'] or bool(b['alt'].strip())
        if kind=='button': checks['CTA label and HTTPS URL valid'] &= bool(b['label'].strip()) and public_https(b['url'])
        if 'products' in b:
            checks['All design placeholders replaced'] &= len(b['products'])>=(2 if kind=='product_grid' else 1)
            for p in b['products']:
                checks['All design placeholders replaced'] &= bool(p.get('title') and public_https(p.get('url')))
                checks['Images use durable public JPEG/PNG URLs'] &= asset_url(p.get('image',''))
                checks['Image alt text complete'] &= bool(p.get('alt','').strip())
                checks['Market-specific product prices verified'] &= not p.get('price') or (p.get('market')==market and p.get('currency')=={'AU':'AUD','US':'USD','UK':'GBP','CA':'CAD','NZ':'NZD'}.get(market))
    return checks


def legacy_blocks(c):
    """In-memory conversion only; old saved content remains byte-for-byte intact."""
    blocks=[]
    if c['hero_url']:blocks.append(block('image',url=c['hero_url'],alt=c['hero_alt']))
    for k in ('eyebrow','headline','intro','body','product_block'):
        if c[k]:blocks.append(block('heading' if k=='headline' else 'text',text=c[k]))
    if c['cta_url'] or c['cta_label']:blocks.append(block('button',url=c['cta_url'],label=c['cta_label']))
    for k in ('secondary','ps'):
        if c[k]:blocks.append(block('text',text=c[k]))
    for i,b in enumerate(blocks):b['id']='b_legacy_'+str(i)
    return blocks


def render_blocks(blocks,*,campaign_key='',market='AU',images_off=False,accent='#b49450',font='Arial',button_style='Solid black'):
    validate_blocks(blocks); e=lambda v:escape(str(v),quote=True)
    link=lambda url,key:campaign_link(url,campaign_key,key,test=True) if campaign_key else url
    fonts={'Arial':'Arial,Helvetica,sans-serif','Georgia':'Georgia,Times,serif'}
    face=fonts.get(font,fonts['Arial'])
    paragraphs=lambda v:''.join('<p style="margin:0 0 16px;font:16px/1.6 '+face+'">'+e(p).replace('\n','<br>')+'</p>' for p in v.split('\n\n') if p)
    def image(url,alt,width=552):
        if images_off or not asset_url(url): return '<p style="font:16px Arial;color:#555">'+e(alt or 'Image placeholder — choose an image')+'</p>'
        return '<img src="'+e(url)+'" alt="'+e(alt)+'" width="'+str(width)+'" style="display:block;width:100%;max-width:'+str(width)+'px;height:auto;border:0">'
    def product(p,key,width):
        price=p.get('currency','')+' '+p.get('price','') if p.get('price') and p.get('market')==market else ''
        url=link(p.get('url',''),key)
        title='<h2 style="font:700 20px/1.3 '+face+';margin:16px 0 10px">'+e(p.get('title',''))+'</h2>'
        content=image(p.get('image',''),p.get('alt',''),width)+title+paragraphs(price)
        if public_https(url): content+='<a href="'+e(url)+'" style="display:inline-block;padding:12px 0;color:#171717;font:700 16px Arial">Explore artwork →</a>'
        return content, '\n'.join([p.get('title',''),price,url])
    rows=[];plain=[]
    for b in blocks:
        kind=b['type']; out=''
        if kind=='heading':out='<h1 style="font:700 28px/1.2 '+face+';margin:0">'+e(b['text'])+'</h1>';plain.append(b['text'])
        elif kind=='text':out=paragraphs(b['text']);plain.append(b['text'])
        elif kind=='image':out=image(b['url'],b['alt']);plain.append(b['alt'])
        elif kind=='button':
            url=link(b['url'],b['id']);plain.append(b['label']+': '+url)
            bg,fg=('#fff','#171717') if button_style=='Outlined black' else ('#171717','#fff')
            if public_https(url):out='<table role="presentation" cellspacing="0" cellpadding="0"><tr><td bgcolor="'+bg+'" style="border:1px solid #171717;border-bottom:3px solid '+accent+'"><a href="'+e(url)+'" style="display:inline-block;padding:16px 24px;font:700 16px '+face+';color:'+fg+';text-decoration:none">'+e(b['label'])+'</a></td></tr></table>'
            else:out=paragraphs('Choose the destination for your primary CTA.')
        elif kind in ('product','product_grid'):
            if not b['products']:out=paragraphs('Product placeholder — select a Shopify artwork before testing.')
            elif kind=='product':out,t=product(b['products'][0],b['id'],552);plain.append(t)
            else:
                for start in range(0,len(b['products']),2):
                    out+='<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
                    for i,p in enumerate(b['products'][start:start+2]):
                        cell,t=product(p,b['id']+'_'+str(start+i),264);plain.append(t)
                        out+='<td class="sc-stack" width="50%" valign="top" style="padding:0 6px 16px">'+cell+'</td>'
                    out+='</tr></table>'
        elif kind=='divider':out='<table role="presentation" width="100%"><tr><td style="border-top:1px solid #ded8ca;height:1px;font-size:1px">&nbsp;</td></tr></table>'
        else:out='<div style="height:'+str(b['height'])+'px;line-height:1px">&nbsp;</div>'
        rows.append('<tr><td style="padding:12px 24px;color:#171717">'+out+'</td></tr>')
    return ''.join(rows),'\n\n'.join(plain)
