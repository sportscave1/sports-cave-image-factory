"""Exact Shopify membership and existing, recipient-linked recommendation signals.

No title inference and no identity join to anonymous browser/pixel telemetry.
The handle allowlist is the existing audited Sports Cave taxonomy, not a family map.
"""
from crm_catalogue import product_id
from sports_categories import SPORT_COLLECTION_HANDLES

SPORT_HANDLES = frozenset(h for sport, handles in SPORT_COLLECTION_HANDLES.items()
                         if sport != 'Motorsport' for h in handles)
MEMBERSHIPS = '''query SmartMemberships($ids:[ID!]!) {
 nodes(ids:$ids) { ... on Product { id collections(first:20) {
 nodes { id title handle } pageInfo { hasNextPage endCursor } } } } }'''
COLLECTION_PRODUCTS = '''query SmartCollectionProducts($id:ID!,$after:String) {
 collection(id:$id) { products(first:100,after:$after,sortKey:COLLECTION_DEFAULT) {
 nodes { id } pageInfo { hasNextPage endCursor } } } }'''


def memberships(shop, ids):
    found = {}
    from crm_shopify import COLLECTIONS
    # Bound nested connection cost below Shopify's single-query cost limit.
    for start in range(0, len(ids), 25):
        nodes = shop.query(MEMBERSHIPS, {'ids':ids[start:start+25]},
                           'smart catalogue interests', 300)['nodes']
        for node in nodes:
            if not node:continue
            page = node['collections'];seen = set()
            while True:
                for c in page['nodes']:
                    if c.get('handle') in SPORT_HANDLES:found[c['id']] = c
                info = page.get('pageInfo') or {}
                if not info.get('hasNextPage'):break
                cursor = info.get('endCursor')
                if not cursor or cursor in seen:raise ValueError('Incomplete sport memberships')
                seen.add(cursor)
                page = shop.query(COLLECTIONS, {'id':node['id'], 'after':cursor},
                                  'smart catalogue interests', 300)['product']['collections']
    return list(found)


def collection_products(shop, identity):
    ids = [];cursor = None;seen = set()
    while True:
        page = (shop.query(COLLECTION_PRODUCTS, {'id':identity,'after':cursor},
                'smart collection recommendations', 300).get('collection') or {}).get('products') or {}
        ids.extend(p['id'] for p in page.get('nodes',[]) if product_id(p.get('id')) == p.get('id'))
        info = page.get('pageInfo') or {}
        if not info.get('hasNextPage'):return list(dict.fromkeys(ids))
        cursor = info.get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Incomplete sport collection')
        seen.add(cursor)


def behaviour(store, customer):
    """Reuse signed checkout events and provider-confirmed product-link clicks.

    The current pixel tables have no authenticated customer association; they
    intentionally cannot supply viewed products. A verified integration adapter
    can supply permitted views through the explicit behaviour argument to hydrate.
    """
    return behaviours(store,[customer['id']])[customer['id']]


def behaviours(store, ids):
    """Two set-based local reads per preparation batch, no global customer cache."""
    result={cid:{'customer_id':cid,'viewed':[],'checkout':[],'engaged':[]} for cid in ids}
    if not ids:return result
    rows=store.q('''SELECT related_customer_id,normalized FROM (
        SELECT related_customer_id,normalized,occurred_at,
          row_number() OVER (PARTITION BY related_customer_id ORDER BY occurred_at DESC) AS rank
        FROM crm_webhook_events WHERE provider='shopify' AND related_customer_id=ANY(%s)
          AND topic IN ('checkouts/create','checkouts/update')
          AND occurred_at>now()-interval '90 days'
        ) events WHERE rank<=30 ORDER BY occurred_at DESC''',(ids,))
    for row in rows:
        data=row.get('normalized') or {};target=result.get(row.get('related_customer_id'))
        if target is not None and not data.get('completed'):target['checkout'].extend(data.get('product_ids') or [])
    # Match provider-confirmed destinations to the product mirror. An email
    # click is engagement, never proof that a product page was viewed.
    rows=store.q('''SELECT customer_id,shopify_product_id FROM (
        SELECT s.shopify_customer_id AS customer_id,p.shopify_product_id,e.occurred_at,
          row_number() OVER (PARTITION BY s.shopify_customer_id ORDER BY e.occurred_at DESC) AS rank
        FROM crm_marketing_sends s JOIN crm_delivery_events e ON e.send_id=s.id
        JOIN shopify_products p ON split_part(e.clicked_url,'?',1)=p.online_store_url
        WHERE s.shopify_customer_id=ANY(%s) AND NOT s.test_send AND s.status='ACCEPTED'
          AND e.event_type='email.clicked' AND e.occurred_at>now()-interval '90 days'
        ) clicks WHERE rank<=30 ORDER BY occurred_at DESC''',(ids,))
    for row in rows:
        target=result.get(row.get('customer_id'))
        if target is not None:target['engaged'].append(row.get('shopify_product_id'))
    return result


def signal_ids(signals, customer_id, field):
    if not isinstance(signals,dict) or signals.get('customer_id') != customer_id:return []
    return list(dict.fromkeys(product_id(i) for i in signals.get(field,[]) if product_id(i)))


def balanced(groups, products, count):
    """Rank verified sales within each collection; stable merchandising ties.

    Alternate eligible collections, then use surplus from any that still have
    products. Shared memberships never create duplicate cards.
    """
    buckets = []
    for group in groups:
        bucket = [i for i in group if i in products]
        bucket.sort(key=lambda i:-((products[i].get('edition') or {}).get('sold') or 0))
        buckets.append(bucket)
    chosen = [];seen = set()
    while len(chosen)<count:
        added = False
        for bucket in buckets:
            while bucket and bucket[0] in seen:bucket.pop(0)
            if bucket:
                i = bucket.pop(0);seen.add(i);chosen.append(products[i]);added = True
                if len(chosen)==count:break
        if not added:break
    return chosen
