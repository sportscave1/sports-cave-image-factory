"""Shopify segment definitions, with mandatory subscription as an additional gate.

Only segment IDs are persisted. Counts and customer membership always come from
Shopify; there is no local customer mirror or local country approximation.
"""
import hashlib
from crm_logic import now

LABELS={'AU':'AUSTRALIA','US':'USA','UK':'UK','Global':'ALL SUBSCRIBERS','CA':'CANADA','NZ':'NEW ZEALAND'}
COUNTRIES={'AU':'AU','US':'US','UK':'GB','CA':'CA','NZ':'NZ'}
NAMES={'AU':'Australia','US':'USA','UK':'UK','Global':'Email subscribers','CA':'Canada','NZ':'New Zealand'}
SUBSCRIBED="email_subscription_status = 'SUBSCRIBED'"

def canonical_query(market):
    code=COUNTRIES.get(market)
    return (f"(customer_countries CONTAINS '{code}' OR customer_tags CONTAINS 'SC_COUNTRY_{code}') AND " if code else '')+SUBSCRIBED

def sources(shop,store):
    key='campaign_segment_ids:'+hashlib.sha256(shop.namespace.encode()).hexdigest()[:24]
    saved=store.state(key)
    ids=dict(saved.get('ids',{}));catalog={};cursor=None;seen=set()
    while True:
        page=shop.segments(after=cursor,fresh=True)
        catalog.update({s['id']:s for s in page['nodes']})
        if not page['pageInfo'].get('hasNextPage'):break
        cursor=page['pageInfo'].get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Segment pagination did not advance.')
        seen.add(cursor)
    result={}
    for market in LABELS:
        identity=ids.get(market)
        if identity and identity not in catalog:
            # Never silently replace a deleted, previously bound segment.
            raise ValueError('A linked Shopify segment is unavailable.')
        if not identity:
            matches=[s for s in catalog.values() if s['name'].strip().casefold()==NAMES[market].casefold()]
            if len(matches)>1:raise ValueError('Ambiguous Shopify segment name.')
            if matches:identity=ids[market]=matches[0]['id']
        source=catalog.get(identity)
        query=(f"({source['query']}) AND {SUBSCRIBED}" if source else canonical_query(market))
        result[market]={'id':identity,'query':query,'last_edit':source.get('lastEditDate') if source else None,
                        'source':'shopify_segment' if source else 'shopify_query'}
    if ids!=saved.get('ids',{}):store.set_state(key,{'ids':ids})
    return result

def count_snapshot(shop,store,hours=16):
    definitions=sources(shop,store)
    counts=shop.campaign_segment_counts(definitions)
    fetched_at=now().isoformat()
    return {m:{'subscribed':counts[m],'source':definitions[m],'fetched_at':fetched_at} for m in LABELS}
