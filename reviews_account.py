"""Authenticated My Collection submissions into the canonical OS review store."""
import hashlib,json
from reviews_model import normalize,product_gid
from reviews_submission import verified_context

def purchase_key(order,customer,product):
 return 'native-purchase:'+hashlib.sha256((order+':'+customer+':'+product).encode()).hexdigest()

def submit(store,shop,customer,reference,payload,uploads):
 import collector_vault
 if not store.settings()['enabled']:raise ValueError('Reviews are unavailable.')
 row=collector_vault._resolve_review_reference(reference,customer)
 order=collector_vault._canonical_gid('Order',row['shopify_order_id']);product=product_gid(row['shopify_product_id'])
 verified_context(shop,order,customer,product)
 item=normalize(payload,'sports_cave');mapped=store.match_product({'product_id':product})
 if not mapped:raise ValueError('Product is unavailable.')
 if len(uploads)>5 or sum(x['kind']=='video' for x in uploads)>1:raise ValueError('Choose up to five files and one video.')
 key=purchase_key(order,customer,product)
 existing=store.q("SELECT id FROM sc_reviews WHERE source='sports_cave' AND order_id=%s AND customer_id=%s AND product_id=%s LIMIT 1",(order,customer,product),True)
 if existing:return {'status':'submitted','review_id':str(existing['id'])}
 from reviews_media import save_owned
 media=[{**save_owned(x['data'],x['kind'],defer_processing=True),'kind':x['kind']} for x in uploads]
 with store.db() as conn:
  conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(key,))
  existing=conn.execute("SELECT id FROM sc_reviews WHERE source='sports_cave' AND order_id=%s AND customer_id=%s AND product_id=%s LIMIT 1",(order,customer,product)).fetchone()
  if existing:return {'status':'submitted','review_id':str(existing['id'])}
  saved=conn.execute("""INSERT INTO sc_reviews(source,source_review_id,product_id,product_title,product_handle,product_image,product_url,
   customer_id,order_id,reviewer_name,rating,title,body,status,verified_purchase,dedupe_key,review_type)
   VALUES('sports_cave',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',true,%s,'PRODUCT') RETURNING id""",
   (key,product,mapped['title'],mapped['handle'],mapped.get('image_url') or '',mapped.get('online_store_url') or '',customer,order,item['reviewer_name'],item['rating'],item['title'],item['body'],key)).fetchone()
  for m in media:
   conn.execute("""INSERT INTO sc_review_media(review_id,kind,source_url,object_key,sha256,size_bytes,mime_type,status,consent,storage)
    VALUES(%s,%s,%s,%s,%s,%s,%s,'QUEUED',true,%s::jsonb) ON CONFLICT DO NOTHING""",
    (saved['id'],m['kind'],'native:'+m['sha256'],m['object_key'],m['sha256'],m['size_bytes'],m['mime_type'],json.dumps(m['storage'])))
  conn.execute('UPDATE sc_review_tokens SET review_id=%s WHERE order_id=%s AND customer_id=%s AND product_id=%s AND review_id IS NULL',(saved['id'],order,customer,product))
 return {'status':'submitted','review_id':str(saved['id'])}
