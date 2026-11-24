"""Signed, bounded storefront submissions. Anonymous visitors never earn rewards."""
import hashlib
import hmac
import json
import os
import secrets
import time
from reviews_model import normalize,product_gid

def secret():
    value=os.environ.get('REVIEWS_FORM_SECRET') or os.environ.get('CRM_UNSUBSCRIBE_SECRET','')
    if len(value)<32:raise ValueError('Review collection is unavailable.')
    return value.encode()

def signature(value):return hmac.new(secret(),('public-review-v1:'+value).encode(),hashlib.sha256).hexdigest()

def issue(product=''):
    if product and not product_gid(product):raise ValueError('Invalid product.')
    identity=product_gid(product).split('/')[-1] if product else 'store'
    value=f'{int(time.time())}.{secrets.token_hex(16)}.{identity}'
    return value+'.'+signature(value)

def verify(token):
    import re
    if not re.fullmatch(r'\d{10}\.[a-f0-9]{32}\.(?:store|\d{1,30})\.[a-f0-9]{64}',token):raise ValueError('Invalid form.')
    value,sig=token.rsplit('.',1)
    if not hmac.compare_digest(signature(value),sig):raise ValueError('Invalid form.')
    stamp,nonce,product=value.split('.')
    age=time.time()-int(stamp)
    if not 0<=age<=3600:raise ValueError('Reload the review form and try again.')
    return '' if product=='store' else product_gid(product)

def submit(store,token,payload,uploads):
    product=verify(token)
    if set(payload)-{'rating','title','body','reviewer_name','website','display_consent'} or payload.get('website') or payload.get('display_consent') is not True:raise ValueError('Confirm display permission.')
    if len(uploads)>5 or sum(u['kind']=='video' for u in uploads)>1:raise ValueError('Attach up to five files including one video.')
    item=normalize(payload,'sports_cave');mapped=store.match_product({'product_id':product}) if product else None
    if product and not mapped:raise ValueError('Product unavailable.')
    key='storefront:'+hashlib.sha256(token.encode()).hexdigest()
    existing=store.q('SELECT id FROM sc_reviews WHERE dedupe_key=%s',(key,),True)
    if existing:return str(existing['id'])
    from reviews_media import save_owned
    media=[{**save_owned(u['data'],u['kind'],defer_processing=True),'kind':u['kind']} for u in uploads]
    with store.db() as conn:
        row=conn.execute('''INSERT INTO sc_reviews(source,source_review_id,product_id,product_title,product_handle,product_image,product_url,
          reviewer_name,rating,title,body,status,verified_purchase,dedupe_key,review_type)
          VALUES('sports_cave',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',false,%s,%s)
          ON CONFLICT(dedupe_key) DO UPDATE SET dedupe_key=excluded.dedupe_key RETURNING id''',
          (key,product or None,(mapped or {}).get('title',''),(mapped or {}).get('handle',''),(mapped or {}).get('image_url',''),
           (mapped or {}).get('online_store_url',''),item['reviewer_name'],item['rating'],item['title'],item['body'],key,'PRODUCT' if product else 'STORE')).fetchone()
        for m in media:
            conn.execute('''INSERT INTO sc_review_media(review_id,kind,source_url,object_key,sha256,size_bytes,mime_type,status,consent,storage)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,true,%s::jsonb) ON CONFLICT DO NOTHING''',
              (row['id'],m['kind'],'native:'+m['sha256'],m['object_key'],m['sha256'],m['size_bytes'],m['mime_type'],'QUEUED' if m['storage'].get('processing')=='pending' else 'COPIED',json.dumps(m['storage'])))
    return str(row['id'])
