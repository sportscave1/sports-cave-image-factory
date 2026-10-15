"""Orders-only refund projection. Never writes Shopify or edition records."""
from datetime import datetime, timezone
import json


REFUND_QUERY = '''query OrderRefunds($ids: [ID!]!) {
  nodes(ids: $ids) { ... on Order {
    id updatedAt displayFinancialStatus displayFulfillmentStatus
    transactions(first: 250) { kind status }
    transactionsCount { count }
    lineItems(first: 250) {
      nodes { unfulfilledQuantity }
      pageInfo { hasNextPage }
    }
  } }
}'''


def projection(node):
    transactions = node.get('transactions') or []
    refunds = [t for t in transactions if t.get('kind') == 'REFUND']
    pending = any(t.get('status') in {'PENDING', 'AWAITING_RESPONSE', 'UNKNOWN'} for t in refunds)
    lines = node.get('lineItems') or {}
    complete_evidence = (
        isinstance(lines.get('nodes'), list)
        and not (lines.get('pageInfo') or {}).get('hasNextPage', True)
        and (node.get('transactionsCount') or {}).get('count') == len(transactions)
    )
    remaining = sum(int(line['unfulfilledQuantity']) for line in lines.get('nodes') or [])
    financial = str(node.get('displayFinancialStatus') or '').upper()
    closed = complete_evidence and financial == 'REFUNDED' and not pending and remaining == 0
    status = 'Refund Pending' if pending else 'Refunded' if closed else (
        'Partially Refunded' if financial == 'PARTIALLY_REFUNDED' else '')
    return {'status': status, 'closed': closed, 'blocked': pending or closed,
            'remote_updated_at': node.get('updatedAt') or ''}


def state(row):
    if row is None:
        return {}
    for source in (row, row.get('order_raw_json'), row.get('raw_json'), row.get('raw_payload')):
        if isinstance(source, dict) and isinstance(source.get('_orders_refund'), dict):
            return source['_orders_refund']
    return {}


def blocked(row):
    return bool(state(row).get('blocked'))


def reconcile(order_ids=None, *, backend=None, shopify=None, limit=50):
    """Refresh latest Shopify truth; rotate all stored orders to recover missed events.

    The existing reconciliation worker calls this alongside paid-order processing.
    A webhook calls the same function for its immutable ID. Duplicate and stale
    events therefore cannot cause payment/fulfilment/edition side effects.
    """
    if backend is None:
        import supabase_backend as backend
    if shopify is None:
        import shopify_sync as shopify
    if order_ids is None:
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute('''SELECT shopify_order_id FROM shopify_orders
                    WHERE raw_json->'_orders_refund'->>'status'='Refund Pending'
                    ORDER BY COALESCE(raw_json->>'_orders_refund_checked_at', '') LIMIT 25''')
                pending_ids = [r['shopify_order_id'] for r in cur.fetchall()]
                cur.execute('''SELECT shopify_order_id FROM shopify_orders
                    WHERE shopify_order_id ~ '^(gid://shopify/Order/)?[0-9]+$'
                    ORDER BY COALESCE(raw_json->>'_orders_refund_checked_at', ''), created_at DESC
                    LIMIT %s''', (limit,))
                order_ids = pending_ids + [r['shopify_order_id'] for r in cur.fetchall()]
    ids = list(dict.fromkeys(shopify.shopify_gid('Order', i) for i in order_ids if i))
    changed = 0
    for offset in range(0, len(ids), 2):
        batch_ids = ids[offset:offset+2]
        data, _ = shopify.graphql_request(REFUND_QUERY, variables={'ids': batch_ids})
        for order_id, node in zip(batch_ids, data.get('nodes') or []):
            if not node:
                # Inaccessible/deleted orders must not starve the rotating sweep.
                with backend.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute('''UPDATE shopify_orders SET raw_json=COALESCE(raw_json, '{}'::jsonb)
                            || jsonb_build_object('_orders_refund_checked_at', %s::text)
                            WHERE shopify_order_id=%s''',
                            (datetime.now(timezone.utc).isoformat(), order_id))
                    conn.commit()
                continue
            refund = projection(node)
            checked = datetime.now(timezone.utc).isoformat()
            patch = json.dumps({'_orders_refund': refund, '_orders_refund_checked_at': checked,
                                '_orders_workflow_status': 'closed' if refund['closed'] else
                                'on_hold' if refund['blocked'] else 'open'})
            with backend.connect() as conn:
                with conn.cursor() as cur:
                    # Preserve every historical line, allocation, certificate and
                    # Shopify fulfilment status. Only the Orders projection changes.
                    cur.execute("SELECT raw_json->'_orders_refund' AS refund FROM shopify_orders WHERE shopify_order_id=%s FOR UPDATE", (node['id'],))
                    previous = cur.fetchone()
                    cur.execute('''UPDATE shopify_orders SET
                        financial_status=%s,
                        raw_json=COALESCE(raw_json, '{}'::jsonb) || %s::jsonb,
                        raw=COALESCE(raw, '{}'::jsonb) || %s::jsonb,
                        updated_at=CASE WHEN raw_json->'_orders_refund' IS DISTINCT FROM %s::jsonb
                            THEN now() ELSE updated_at END
                        WHERE shopify_order_id=%s
                          AND COALESCE(raw_json->'_orders_refund'->>'remote_updated_at', '') <= %s
                        RETURNING shopify_order_id''',
                        (node['displayFinancialStatus'], patch, patch, json.dumps(refund), node['id'], node['updatedAt']))
                    changed += len(cur.fetchall())
                    if previous and previous.get('refund') != refund:
                        cur.execute('''INSERT INTO app_settings(key, value, updated_at)
                            VALUES ('orders_refund_visibility', %s::jsonb, now())
                            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()''',
                            (json.dumps({'changed_at': checked}),))
                conn.commit()
    return {'orders_checked': len(ids), 'orders_updated': changed}


def assert_processing_allowed(cur, order_id):
    if not order_id:
        return
    cur.execute("SELECT raw_json FROM shopify_orders WHERE shopify_order_id=%s", (order_id,))
    row = cur.fetchone()
    if row and blocked(row):
        raise ValueError('Shopify refund is pending or completed; order processing is closed or on hold.')
