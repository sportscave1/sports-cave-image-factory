"""Shopify-owned buyer audiences. Runtime storage is an ID-only projection.

No segment writes, consent writes, or customer-tag inference. Sends always read
the saved Shopify definitions and current membership again, never this cache.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from crm_campaign_segments import sources

BUYER_NAMES = tuple(name + ' Buyers' for name in (
    'AFL', 'Basketball', 'Baseball', 'Combat Sports', 'Cricket', 'Football', 'Golf',
    'Horse Racing', 'Ice Hockey', 'NFL', 'Olympics', 'Rugby League', 'Rugby Union',
    'Surfing', 'Tennis', 'WWE', 'Athletics', 'Motorsport', 'Formula One', 'NASCAR',
    'V8 Supercars', 'MotoGP', 'Motocross', 'Rally', 'Motorcycle Road Racing',
    'Rally Raid', 'IndyCar', 'Apparel'))
TTL = 300


def validate_ids(values):
    if (not isinstance(values, list) or len(values) > 28
            or any(not isinstance(v, str) or not re.fullmatch(r'gid://shopify/Segment/\d+', v) for v in values)
            or len(set(values)) != len(values)):
        raise ValueError('Invalid Shopify buyer segment selection.')


def definitions(shop):
    rows = {}; cursor = None; seen = set()
    for _ in range(100):
        page = shop.segments(after=cursor, fresh=True)
        for row in page['nodes']:
            if not row.get('id') or not row.get('query'): raise ValueError('Incomplete Shopify segment definitions.')
            rows[row['id']] = row
        if not page['pageInfo'].get('hasNextPage'): return rows
        cursor = page['pageInfo'].get('endCursor')
        if not cursor or cursor in seen: raise ValueError('Shopify segment pagination did not advance.')
        seen.add(cursor)
    raise ValueError('Shopify segment catalogue exceeds supported limit.')


def selected_definitions(shop, doc):
    selected = doc.get('shopify_segment_ids', [])
    validate_ids(selected)
    if selected and doc.get('shopify_segment_store') != shop.namespace:
        raise ValueError('Buyer segment store differs from this connection. Review the saved audience.')
    rows = []
    for identity in selected:
        row = shop.segment(identity, fresh=True)
        if not row or row.get('id') != identity or not row.get('query'):
            raise ValueError('Selected Shopify segment is unavailable: ' + identity + '. Review required; audience was not broadened.')
        rows.append(row)
    return rows


def member_ids(shop, store, doc):
    """Location AND union, using actual saved definitions including history clauses."""
    selected = selected_definitions(shop, doc)
    location = sources(shop, store)[doc['market']]['query']
    query = location
    if selected:
        query = '(' + location + ') AND (' + ' OR '.join('(' + r['query'] + ')' for r in selected) + ')'
    return shop.campaign_member_ids(query)


def audience(shop, store, doc):
    from crm_campaign_review_reads import selected_reads
    from crm_audience import evaluate_profiles
    from crm_logic import now
    identities = member_ids(shop, store, doc)
    profiles, conflicts, suppressed, ids, recent = selected_reads(shop, store, identities, doc.get('smart_hours', 16))
    result = evaluate_profiles(list(profiles.values()), set(), set(), suppressed | conflicts, ids, recent, recipients=True)
    result.update(profiles=profiles, complete=True, checked_at=now().isoformat())
    return result


def snapshot_key(shop):
    return 'buyer-segments-v8:' + hashlib.sha256(shop.namespace.encode()).hexdigest()[:24]


def dispatch_exclusions(engine, doc, recipients):
    """Fresh remove-only check before provider submission, including schedules.

    Any failed/partial Shopify read raises before touching provider idempotency.
    Never modify an already attempted batch to retry a different payload.
    """
    if not doc.get('shopify_segment_ids'): return set()
    from crm_campaign_review_reads import selected_profiles
    from crm_logic import eligibility, recipient_hash
    members = member_ids(engine.shop, engine.store, doc)
    profiles, conflicts = selected_profiles(engine.shop, {r['id'] for r in recipients})
    suppressed, ids = engine.store.active_suppression_hashes()
    blocked = set()
    for row in recipients:
        customer = profiles[row['id']]
        ok, _ = eligibility(customer, row['hash'] in suppressed or row['id'] in ids)
        if (row['id'] not in members or not ok or row['hash'] in conflicts
                or recipient_hash(customer.get('email')) != row['hash']): blocked.add(row['hash'])
    return blocked


def synchronize(shop, store):
    """Called only in background. Atomic snapshot; distributed lock avoids overlap.

    A failed refresh leaves the last successful projection intact and stale.
    Five-minute polling reconciles purchases, refunds and consent independently
    of webhook order or whether a webhook proves final Shopify membership.
    """
    key = snapshot_key(shop)
    with store.db() as conn:
        locked = conn.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS locked', (key,)).fetchone()
        if not locked['locked']: return store.state(key) or {}
        row = conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s', (key,)).fetchone()
        previous = row['value'] if row else {}
        if previous and time.time() - previous.get('timestamp', 0) < TTL: return previous
        catalogue = definitions(shop)
        # Remember IDs across renames; never replace a deleted saved ID by name.
        bindings = dict(previous.get('bindings', {}))
        for name in BUYER_NAMES:
            if name in bindings: continue
            matches = [r['id'] for r in catalogue.values() if r['name'] == name]
            if len(matches) > 1: raise ValueError('Ambiguous Shopify buyer segment: ' + name)
            if matches: bindings[name] = matches[0]
        rows = {}; started = time.monotonic()
        for identity in bindings.values():
            if time.monotonic() - started > 240: raise TimeoutError('Buyer segment synchronization timed out.')
            if identity not in catalogue: continue
            definition = catalogue[identity]
            rows[identity] = {**definition, 'members': sorted(shop.campaign_member_ids(definition['query']))}
        result = {'bindings': bindings, 'segments': rows, 'timestamp': time.time(),
                  'checked_at': datetime.now(timezone.utc).isoformat(),
                  'missing': [n for n in BUYER_NAMES if bindings.get(n) not in rows]}
        conn.execute('''INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()''', (key, json.dumps(result)))
        return result


def display_snapshot(shop, store, hours=16):
    # SegmentCounts supplies bounded async scheduling/backoff and account scope.
    result = synchronize(shop, store)
    return {identity: {'subscribed': len(row['members']), 'name': row['name'],
                       'checked_at': result['checked_at'], 'missing': result['missing']}
            for identity, row in result.get('segments', {}).items()}


from crm_segment_counts import SegmentCounts
CATALOGUE = SegmentCounts(loader=display_snapshot)


def run(store, shop, stop):
    import logging
    while not stop.is_set():
        try: synchronize(shop, store)
        except Exception as exc:
            logging.getLogger(__name__).warning('buyer_segment_sync_failed type=%s', type(exc).__name__)
        stop.wait(60)
