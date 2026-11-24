"""Order-bound opaque links: trusted server issuance, atomic one-time submission."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import hmac
import json
import os
import re
from crm_logic import now,date
from crm_tracking import public_https
from reviews_model import normalize,product_gid

MARKER='SC_REVIEW_REQUEST_CONTEXT'.ljust(64,'_')

def verified_context(shop,order_id,customer_id,product):
    if not re.fullmatch(r'gid://shopify/Order/\d+',str(order_id)) or not re.fullmatch(r'gid://shopify/Customer/\d+',str(customer_id)) or not product_gid(product):raise ValueError('Invalid review context.')
    order=shop.order(order_id,fresh=True)
    if not order or order.get('cancelledAt') or (order.get('customer') or {}).get('id')!=customer_id:raise ValueError('Order/customer relationship could not be verified.')
    connection=order.get('lineItems') or {};seen=set()
    for _ in range(20):
        for line in connection.get('nodes',[]):
            if (line.get('product') or {}).get('id')==product_gid(product):return True
        page=connection.get('pageInfo') or {}
        if not page.get('hasNextPage'):break
        cursor=page.get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Order products are incomplete.')
        seen.add(cursor);connection=shop.line_page(order_id,cursor,fresh=True)
    raise ValueError('This product could not be verified on the order.')

def issue(store,shop,order_id,customer_id,product,env=None):
    env=os.environ if env is None else env
    from reviews_routing import public_base
    base=public_base(env);secret=env.get('CRM_UNSUBSCRIBE_SECRET','')
    if not public_https(base) or len(secret)<32:raise ValueError('Secure review links require the existing CRM public URL and signing secret.')
    product=product_gid(product);verified_context(shop,order_id,customer_id,product)
    if not store.match_product({'product_id':product}):raise ValueError('Review product is not indexed.')
    value=hmac.new(secret.encode(),('review-request-v1:'+order_id+':'+customer_id+':'+product).encode(),hashlib.sha256).hexdigest()
    key=hashlib.sha256(value.encode()).hexdigest()
    store.q('''INSERT INTO sc_review_tokens(token_hash,order_id,customer_id,product_id,expires_at)
      VALUES(%s,%s,%s,%s,%s) ON CONFLICT(order_id,customer_id,product_id) DO NOTHING''',
      (key,order_id,customer_id,product,now()+timedelta(days=30)))
    return base+'/reviews/request/'+value

def token_row(store,token):
    if not re.fullmatch('[a-f0-9]{64}',str(token)):raise ValueError('Review link is invalid.')
    row=store.q('SELECT * FROM sc_review_tokens WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),),True)
    if not row or date(row['expires_at'])<now():raise ValueError('Review link is invalid or expired.')
    return row

def submit(store,token,payload,uploads=None):
    if not isinstance(payload,dict) or set(payload)-{'rating','title','body','reviewer_name','website','display_consent'}:raise ValueError('Invalid review submission.')
    if payload.get('website') or payload.get('display_consent') is not True:raise ValueError('Confirm permission to display your review.')
    row=token_row(store,token)
    if row['review_id']:return str(row['review_id'])
    uploads=uploads or []
    if len(uploads)>5 or sum(u['kind']=='video' for u in uploads)>1:raise ValueError('Attach up to five files, including one video.')
    item=normalize(payload,'sports_cave');product=store.match_product({'product_id':row['product_id']})
    if not product:raise ValueError('Review product is unavailable.')
    policy=store.settings();state='PUBLISHED' if policy['moderation']=='publish_all' else 'PENDING'
    from reviews_media import save_owned
    media=[{**save_owned(u['data'],u['kind'],defer_processing=True),'kind':u['kind']} for u in uploads]
    with store.db() as conn:
        locked=conn.execute('SELECT * FROM sc_review_tokens WHERE token_hash=%s FOR UPDATE',(row['token_hash'],)).fetchone()
        if not locked or date(locked['expires_at'])<now():raise ValueError('Review link is invalid or expired.')
        if locked['review_id']:return str(locked['review_id'])
        result=conn.execute('''INSERT INTO sc_reviews(source,source_review_id,product_id,product_title,product_handle,product_image,product_url,
          customer_id,order_id,reviewer_name,rating,title,body,status,verified_purchase,dedupe_key)
          VALUES('sports_cave',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s) RETURNING id''',
          (row['token_hash'],row['product_id'],product['title'],product['handle'],product.get('image_url') or '',product.get('online_store_url') or '',
           row['customer_id'],row['order_id'],item['reviewer_name'],item['rating'],item['title'],item['body'],state,'native:'+row['token_hash'])).fetchone()
        conn.execute('UPDATE sc_review_tokens SET review_id=%s WHERE token_hash=%s',(result['id'],row['token_hash']))
        for m in media:
            conn.execute("""INSERT INTO sc_review_media(review_id,kind,source_url,object_key,sha256,size_bytes,mime_type,status,consent,storage)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,true,%s::jsonb) ON CONFLICT DO NOTHING""",
              (result['id'],m['kind'],'native:'+m['sha256'],m['object_key'],m['sha256'],m['size_bytes'],m['mime_type'],'QUEUED' if m['storage'].get('processing')=='pending' else 'COPIED',json.dumps(m.get('storage',{}))))
        return str(result['id'])

def prepare_email(content,row,enrollment,shop,store):
    request=content.get('review_request')
    if not request:return content
    if content.get('trigger') not in ('fulfilled','post_purchase') or not enrollment:raise ValueError('Review request requires an order journey.')
    product=request.get('product_id')
    if 'product_index' in request:
        from reviews_journey import order_products
        order=shop.order(enrollment['trigger_shopify_id'],fresh=True)
        if not order or order.get('displayFulfillmentStatus')!='FULFILLED':raise ValueError('Order fulfilment is unverified.')
        choices=order_products(shop,order)
        if request['product_index']>=len(choices):raise ValueError('Review product is unavailable.')
        product=choices[request['product_index']]
    url=issue(store,shop,enrollment['trigger_shopify_id'],enrollment['shopify_customer_id'],product)
    from urllib.parse import urlsplit
    if urlsplit(url).netloc!=urlsplit(request['base_url']).netloc:raise ValueError('Review request URL configuration changed. Republish the flow.')
    result=deepcopy(content)
    original=request['base_url'].rstrip('/')+'/reviews/request/'+MARKER
    # One opt-in immutable template marker, never arbitrary text substitution.
    encoded=json.dumps(result['document'])
    if original not in encoded:raise ValueError('Add the review request link before publishing.')
    from html import escape
    mapped=store.match_product({'product_id':product}) or {}
    encoded=encoded.replace(original,url).replace('SC_REVIEW_PRODUCT_TITLE',json.dumps(escape(mapped.get('title','your Sports Cave edition')))[1:-1])
    result['document']=json.loads(encoded)
    return result

def create_automation(user,base,product,days):
    from crm_automation_store import AutomationStore
    from crm_middle_sections import commit_middle
    from html import escape
    from reviews_routing import public_base
    env=os.environ;url=public_base(env)
    if not public_https(url):raise ValueError('Configure the existing CRM public URL first.')
    if not 1<=int(days)<=90:raise ValueError('Choose 1–90 days after fulfilment.')
    product=product_gid(product)
    if not ReviewsStoreMatch(base,product):raise ValueError('Choose an indexed Shopify product.')
    store=AutomationStore(base.connect);row=store.create(user,'fulfilled','Review request')
    flow=deepcopy(row['config']['draft']);flow['rules']=[{'field':'product_purchased','condition':'is','value':product}]
    flow['review_request']={'product_id':product,'base_url':url}
    step=flow['emails'][0];step['delay_seconds']=int(days)*86400
    step['document']['content']['subject']='How does your Sports Cave edition look?'
    step['document']['content']['preheader']='Share your collector experience.'
    commit_middle(step['document'],[{'type':'html','id':str(__import__('uuid').uuid4()),'html_number':1,'visible':True,
      'html':'<p>We would love to hear about your Sports Cave edition.</p><p><a href="'+escape(url+'/reviews/request/'+MARKER,quote=True)+'">Share your review</a></p>'}])
    return store.save_flow(user,row['id'],row['name'],flow,row['config']['revision'])

def ReviewsStoreMatch(base,product):
    from reviews_store import ReviewsStore
    return ReviewsStore(base.connect).match_product({'product_id':product})
