"""Reviews V1: plain text, conservative identity, no provider verification claims."""
import hashlib
import re
from html import unescape
from html.parser import HTMLParser
from datetime import datetime, timezone
from crm_logic import date, now

SOURCES=('csv','judgeme','sports_cave')
STATUSES=('PENDING','PUBLISHED','ARCHIVED','SPAM')
FIELDS=('source_review_id','product_id','product_handle','product_url','product_sku','product_title','reviewer_name','email','rating','title','body','created_at','source_verified','merchant_reply','status')
ALIASES={'source_review_id':('review_id','id'),'product_id':('shopify_product_id','product_external_id'),
 'product_handle':('handle',),'product_url':('product_link','url'),'product_sku':('sku',),'product_title':('product_name',),
 'reviewer_name':('name','customer','reviewer'),'email':('reviewer_email','customer_email'),
 'rating':('stars','review_rating'),'title':('review_title',),'body':('review_body','review','content'),
 'created_at':('date','review_date','created_at'),'source_verified':('verified','verified_buyer'),
 'merchant_reply':('reply','reply_body'),'status':('published','review_status')}

class Plain(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        elif tag in ('br','p','div'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
    def handle_data(self,value):
        if not self.skip:self.parts.append(value)

def plain(value,limit):
    parser=Plain();parser.feed(str(value or ''));value=' '.join(unescape(''.join(parser.parts)).split())
    if len(value)>limit:raise ValueError('Text exceeds '+str(limit)+' characters.')
    return value

def product_gid(value):
    value=str(value or '').strip()
    if value.isdigit():return 'gid://shopify/Product/'+value
    return value if re.fullmatch(r'gid://shopify/Product/\d+',value) else None

def auto_mapping(headers):
    names={re.sub(r'[\s-]+','_',h.strip().lower()):h for h in headers}
    return {field:next((names[a] for a in (field,*ALIASES.get(field,())) if a in names),'') for field in FIELDS}

def normalize(raw,source='csv',mapping=None,source_store=''):
    if source not in SOURCES:raise ValueError('Unsupported review source.')
    mapping=mapping or {k:k for k in FIELDS}
    get=lambda k:raw.get(mapping.get(k,k),'')
    try:
        rating=float(get('rating'))
        if not rating.is_integer() or not 1<=rating<=5:raise ValueError()
    except (ValueError,TypeError,OverflowError):raise ValueError('Rating must be 1–5.') from None
    body=plain(get('body'),5000);title=plain(get('title'),200)
    if not body and not title:raise ValueError('Review text is required.')
    supplied=str(get('created_at') or '').strip();at=None
    if supplied:
        try:
            parsed=datetime.fromisoformat(supplied.replace('Z','+00:00'))
            at=parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:at=None
        if not at:
            for fmt in ('%d/%m/%Y','%Y-%m-%d','%m/%d/%Y'):
                try:at=datetime.strptime(supplied,fmt).replace(tzinfo=timezone.utc);break
                except ValueError:pass
        if not at or at>now():raise ValueError('Review date is invalid or in the future.')
    identity=str(get('email') or '').strip().lower()
    hashed=hashlib.sha256(identity.encode()).hexdigest() if identity else None
    name=plain(get('reviewer_name'),120) or 'Collector'
    status=str(get('status') or '').strip().lower()
    status='ARCHIVED' if status=='archived' else 'PUBLISHED' if status in ('published','true','1','yes') else 'PENDING'
    source_id=plain(get('source_review_id'),200)
    hints={k:plain(get(k),500) for k in ('product_id','product_handle','product_url','product_sku','product_title')}
    product=product_gid(hints['product_id'])
    basis=['id',source,source_store,source_id] if source_id else ['fallback',source,source_store,product or hints, int(rating),title,body,at.isoformat() if at else '',hashed or name.casefold()]
    import json
    key=hashlib.sha256(json.dumps(basis,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'source':source,'source_review_id':source_id or None,'source_store_id':source_store[:200],
      'product_id':product,'product_hints':hints,'reviewer_name':name,'reviewer_email_hash':hashed,
      'rating':int(rating),'title':title,'body':body,'created_at':at.isoformat() if at else None,
      'status':status,'source_verified':str(get('source_verified')).lower() in ('true','1','yes','verified'),
      'verified_purchase':False,'merchant_reply':plain(get('merchant_reply'),3000),'dedupe_key':key}

DEFAULT_DISPLAY={'enabled':False,'verified':True,'date':True,'thumbnail':True,'reply':True,'per_page':8,'sort':'newest','accent':'#b99232','density':'compact','moderation':'manual'}

def display_settings(value):
    result={**DEFAULT_DISPLAY,**{k:v for k,v in value.items() if k in DEFAULT_DISPLAY}}
    if any(type(result[k]) is not bool for k in ('enabled','verified','date','thumbnail','reply')):raise ValueError('Invalid display setting.')
    if type(result['per_page']) is not int or not 4<=result['per_page']<=20:raise ValueError('Use 4–20 reviews per page.')
    if result['sort'] not in ('newest','highest','lowest') or result['density'] not in ('compact','comfortable') or result['moderation'] not in ('manual','publish_all'):raise ValueError('Invalid display policy.')
    if not re.fullmatch('#[0-9a-fA-F]{6}',result['accent']):raise ValueError('Choose a valid accent colour.')
    return result
