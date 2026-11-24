"""Inbound Shop reviews through Shopify Flow's merchant-private metaobject inbox.

No public ingestion endpoint, new credentials, outbound syndication or rewards.
Flow only supplies publication events, not a deletion feed or historical export.
"""
from datetime import datetime, timedelta
import hashlib
import json
import logging
import re
import uuid

from crm_logic import now
from reviews_model import normalize

TYPE = 'sports_cave_shop_review_inbox'
KEY = 'shop_app_connection'
QUERY = '''query ShopReviewInbox($query:String!,$after:String) {
 metaobjects(type:"sports_cave_shop_review_inbox",first:10,sortKey:"updated_at",query:$query,after:$after) {
  nodes { id handle updatedAt fields { key value } }
  pageInfo { hasNextPage endCursor }
 }
}'''
PRODUCT = '''query ShopReviewProduct($id:ID!) { product(id:$id) {
 id title handle onlineStoreUrl media(first:20) { nodes { ... on MediaImage { image { url } } } }
} }'''
ORDER = '''query ShopReviewOrder($id:ID!) { order(id:$id) {
 id lineItems(first:250) { nodes { id product { id } variant { id } } }
} }'''


def gid(value, kind):
    value = str(value or '')
    if value.isdigit():value = 'gid://shopify/'+kind+'/'+value
    if not re.fullmatch(r'gid://shopify/'+kind+r'/\d+', value):raise ValueError('Invalid Shop '+kind+' reference.')
    return value


def decode(entry, shop_domain):
    if not re.fullmatch(r'[a-z0-9-]+\.myshopify\.com', shop_domain):raise ValueError('Invalid Shop store.')
    fields = {f['key']:f['value'] for f in entry['fields']}
    order = gid(fields.get('order_id'), 'Order')
    line = gid(fields.get('line_item_id'), 'LineItem')
    variant = gid(fields.get('variant_id'), 'ProductVariant')
    product = gid(fields.get('product_id'), 'Product')
    expected = 'shop-'+order.rsplit('/',1)[-1]+'-'+line.rsplit('/',1)[-1]
    if entry.get('handle') != expected:raise ValueError('Shop inbox identity mismatch.')
    # Rating-only events are intentionally not imported, matching the previous
    # provider's Shop collection policy. They remain in the private inbox.
    if not str(fields.get('body') or '').strip():return None
    submitted = fields.get('submitted_at')
    if not submitted:raise ValueError('Missing Shop review date.')
    item = normalize({'source_review_id':expected,'product_id':product,
      'reviewer_name':fields.get('display_name'),'rating':fields.get('rating'),
      'body':fields['body'],'created_at':submitted,'source_verified':True,
      'status':'PUBLISHED','review_type':'product'}, source='shop_app',source_store=shop_domain)
    item.update(order_id=order,line_item_id=line,variant_id=variant,inbox_id=entry['id'])
    return item


def import_entry(store, shop, entry, domain):
    item = decode(entry, domain)
    if item is None:return 'rating_only'
    digest=hashlib.sha256(json.dumps(entry,sort_keys=True).encode()).hexdigest()
    previous=store.q("""SELECT r.source_metadata->>'shop_inbox_digest' AS digest
      FROM sc_review_identities i JOIN sc_reviews r ON r.id=i.review_id
      WHERE i.source='shop_app' AND i.source_store_id=%s AND i.external_id=%s""",
      (domain,item['source_review_id']),one=True)
    if previous and previous['digest']==digest:return 'unchanged'
    product = shop.query(PRODUCT,{'id':item['product_id']},'shop-review-product',fresh=True).get('product')
    if not product:return 'deleted_product'
    order = shop.query(ORDER,{'id':item['order_id']},'shop-review-order',fresh=True).get('order')
    if not order:raise ValueError('Shop review order unavailable.')
    lines = order['lineItems']['nodes']
    line = next((r for r in lines if r['id']==item['line_item_id']),None)
    if not line or (line.get('product') or {}).get('id')!=item['product_id'] or (line.get('variant') or {}).get('id')!=item['variant_id']:
        raise ValueError('Shop review purchase references do not match.')
    metadata = {'date_known':True,'shop_app':True,'shop_inbox_id':item['inbox_id'],
      'shop_line_item_id':item['line_item_id'],'shop_variant_id':item['variant_id'],
      'shop_order_id':item['order_id'],'shop_transport':'shopify_flow','shop_inbox_digest':digest}
    with store.db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('shop-review:'+domain+':'+item['source_review_id'],))
        existing = conn.execute('SELECT review_id AS id FROM sc_review_identities WHERE source=%s AND source_store_id=%s AND external_id=%s',
          ('shop_app',domain,item['source_review_id'])).fetchone()
        if not existing:
            # Reconcile a previously migrated copy only on a unique exact match
            # of product, public name, full body, stars and original timestamp.
            candidates = conn.execute("""SELECT id FROM sc_reviews WHERE source IN ('judgeme','csv')
              AND product_id=%s AND lower(reviewer_name)=lower(%s) AND body=%s AND rating=%s
              AND created_at=%s::timestamptz LIMIT 2""",
              (item['product_id'],item['reviewer_name'],item['body'],item['rating'],item['created_at'])).fetchall()
            if len(candidates)>1:raise ValueError('Ambiguous historical Shop review.')
            existing = candidates[0] if candidates else None
        if existing:
            # Local moderation and the original provenance are never overridden.
            conn.execute("""UPDATE sc_reviews SET source_metadata=source_metadata||%s::jsonb,
              rating=CASE WHEN source='shop_app' THEN %s ELSE rating END,
              body=CASE WHEN source='shop_app' THEN %s ELSE body END,updated_at=now() WHERE id=%s""",
              (json.dumps(metadata),item['rating'],item['body'],existing['id']))
            identity=existing['id'];result='updated'
        else:
            identity=conn.execute("""INSERT INTO sc_reviews(source,source_review_id,source_store_id,
              product_id,product_title,product_handle,product_image,product_url,reviewer_name,rating,
              body,created_at,status,source_verified,source_metadata,dedupe_key,review_type)
              VALUES('shop_app',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PUBLISHED',true,%s::jsonb,%s,'PRODUCT') RETURNING id""",
              (item['source_review_id'],domain,product['id'],product['title'],product['handle'],
               next((m['image']['url'] for m in (product.get('media') or {}).get('nodes',[]) if m.get('image')), ''),product.get('onlineStoreUrl') or '',
               item['reviewer_name'],item['rating'],item['body'],item['created_at'],json.dumps(metadata),item['dedupe_key'])).fetchone()['id']
            result='imported'
        conn.execute('INSERT INTO sc_review_identities(source,source_store_id,external_id,review_id) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',
          ('shop_app',domain,item['source_review_id'],identity))
    from reviews_public_cache import CACHE
    CACHE.invalidate()
    return result


def tick(store, shop=None, clock=None):
    clock=clock or now()
    with store.db() as conn:
        row=conn.execute('SELECT value FROM sc_review_settings WHERE key=%s FOR UPDATE SKIP LOCKED',(KEY,)).fetchone()
        if not row or not row['value'].get('enabled'):return None
        state=dict(row['value'])
        due=state.get('next_check')
        if due and datetime.fromisoformat(due)>clock:return None
        # Persist a lease before network work; another worker must not race it.
        state['next_check']=(clock+timedelta(minutes=15)).isoformat()
        claim=uuid.uuid4().hex;state['lease_token']=claim
        conn.execute('UPDATE sc_review_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s',(json.dumps(state),KEY))
    try:
        if shop is None:
            from crm_shopify import Shopify
            shop=Shopify()
        domain=state['shop_domain']
        upper=state.get('scan_until') or (clock-timedelta(seconds=2)).isoformat()
        lower=datetime.fromisoformat(state.get('watermark') or '2020-01-01T00:00:00+00:00')-timedelta(minutes=2)
        query="updated_at:>='"+lower.isoformat()+"' updated_at:<='"+upper+"'"
        page=shop.query(QUERY,{'query':query,'after':state.get('cursor')},'shop-review-inbox',fresh=True)['metaobjects']
        counts={}
        for entry in page['nodes']:
            result=import_entry(store,shop,entry,domain)
            counts[result]=counts.get(result,0)+1
        more=page['pageInfo']['hasNextPage']
        state.update(cursor=page['pageInfo']['endCursor'] if more else None,
          scan_until=upper if more else None,watermark=state.get('watermark') if more else upper,
          last_success=clock.isoformat(),last_error=None,last_batch=counts,
          next_check=(clock+timedelta(seconds=2 if more else 60)).isoformat())
    except Exception as exc:
        # Leave cursor/watermark intact so a transient failure cannot lose events.
        state.update(last_error='shop_sync_unavailable',next_check=(clock+timedelta(seconds=60)).isoformat())
        logging.getLogger(__name__).warning('shop_review_sync_unavailable type=%s',type(exc).__name__)
    store.q("UPDATE sc_review_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s AND value->>'lease_token'=%s",(json.dumps(state),KEY,claim))
    return state
