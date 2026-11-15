"""Guards for audited cancellations; no I/O or configuration at import time."""


def require_certificate_allocation(cur, assignment):
    """Hold the order and allocation through generation, including force/retries."""
    order_id = str(assignment.get('shopify_order_id') or '').rsplit('/', 1)[-1]
    cur.execute("""SELECT o.cancelled_at,
      EXISTS(SELECT 1 FROM edition_order_sync_locks l
        WHERE l.canonical_order_key='id:'||%s AND lower(l.status)='cancelled') AS cancelled
      FROM shopify_orders o WHERE regexp_replace(o.shopify_order_id,'^.*/','')=%s
      FOR SHARE OF o""", (order_id, order_id))
    order = cur.fetchone()
    if not order or order.get('cancelled_at') or order.get('cancelled'):
        raise ValueError('Order is missing or cancelled; certificate generation is blocked.')
    reference = str(assignment.get('id') or '')
    if reference.startswith('manual-edition:'):
        return
    cur.execute('SELECT allocation_valid,status FROM edition_orders WHERE id::text=%s FOR SHARE', (reference,))
    unit = cur.fetchone()
    if not unit or unit.get('allocation_valid') is not True or str(unit.get('status') or '').lower() in {
        'cancelled', 'voided', 'refunded', 'superseded'
    }:
        raise ValueError('Allocation is released or invalid; certificate generation is blocked.')
