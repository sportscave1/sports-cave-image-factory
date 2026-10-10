"""Deterministic eligibility and event-anchored deadlines for lifecycle drafts."""
from datetime import timedelta
from crm_logic import date, consent

def qualifying(order):
    return bool(order and order.get('fullyPaid') is True and not order.get('cancelledAt')
                and order.get('displayFinancialStatus') not in ('REFUNDED', 'VOIDED', 'PENDING', 'PARTIALLY_PAID', 'AUTHORIZED')
                and not order.get('fraudulent') and not order.get('disputed') and not order.get('unresolved_return'))

def latest_paid(orders):
    valid = [o for o in orders if qualifying(o) and date(o.get('paid_at') or o.get('createdAt'))]
    return max(valid, key=lambda o:(date(o.get('paid_at') or o['createdAt']), o['id']), default=None)

def preview(flow, customer, orders, at, *, suppressed=False, subscribed_at=None, order_id=None):
    """No enqueue or external I/O. Missing authority always produces a hold."""
    at = date(at)
    last = latest_paid(orders)
    reason = 'suppressed' if suppressed else ''
    if consent(customer) != 'SUBSCRIBED': reason = 'marketing_consent_required'
    kind = flow['trigger']
    anchor = date(subscribed_at)
    order = None
    if kind == 'welcome':
        if last: reason = 'purchased'
        if not anchor: reason = reason or 'subscription_timestamp_unverified'
    elif kind == 'post_purchase':
        order = next((o for o in orders if o['id'] == order_id), None) if order_id else last
        if not qualifying(order): reason = reason or 'order_ineligible'
        if last and order and last['id'] != order['id']: reason = reason or 'superseded_by_latest_order'
        anchor = date((order or {}).get('paid_at'))
        if not anchor: reason = reason or 'payment_timestamp_unverified'
    else:
        if not last: reason = reason or 'no_qualifying_purchase'
        anchor = date((last or {}).get('paid_at') or (last or {}).get('createdAt'))
        if anchor and at < anchor + timedelta(days=flow.get('inactive_days',90)):
            reason = reason or 'not_yet_inactive'
    stages = []
    for step in flow['emails']:
        blocked = reason
        base = anchor
        offset = step['delay_seconds']
        evidence = step['anchor']
        if kind == 'post_purchase' and step['anchor'] == 'delivery':
            base = date((order or {}).get('delivered_at'))
            if not base:
                base = date((order or {}).get('fulfilled_at'))
                fallback = flow.get('fulfilment_fallback_days')
                if base and fallback is not None:
                    offset = fallback * 86400; evidence = 'verified_fulfilment_fallback'
                else: base = None
            if not base: blocked = blocked or 'awaiting_delivery_or_verified_fulfilment'
        if kind == 'post_purchase' and (step['anchor'] == 'delivery' or step.get('requires_fulfilment')):
            if not (order or {}).get('fulfilled_at') and not (order or {}).get('delivered_at'):
                blocked = blocked or 'unfulfilled'
        due = base + timedelta(seconds=offset) if base else None
        stages.append(dict(step_id=step['step_id'], name=step.get('name'), due_at=due,
                           state='DISABLED' if not step.get('enabled', True) else 'HELD' if blocked else 'DRAFT',
                           reason=blocked, anchor=evidence))
    return dict(eligible=not reason, reason=reason, stages=stages,
                cycle=(last or {}).get('id') if kind == 'win_back' else (order or {}).get('id') or customer.get('id'))

def order_from_ledger(row, events=()):
    """Use original Shopify facts. Never interpret fulfilled as delivered."""
    raw = row.get('raw_json') or row.get('raw') or {}
    state = str(row.get('financial_status') or raw.get('displayFinancialStatus') or raw.get('financial_status') or '').upper()
    fulfilled = str(row.get('fulfillment_status') or raw.get('displayFulfillmentStatus') or raw.get('fulfillment_status') or '').upper()
    paid = [date(e['occurred_at']) for e in events if e['topic'] == 'orders/paid' and date(e.get('occurred_at'))]
    fulfilments = raw.get('fulfillments') or []
    if isinstance(fulfilments, dict): fulfilments = fulfilments.get('nodes', [])
    shipments = [f for f in fulfilments if str(f.get('status','')).upper() == 'SUCCESS']
    delivered = [date(f.get('deliveredAt')) for f in shipments]
    if fulfilled != 'FULFILLED' or not delivered or not all(delivered): delivered = []
    completed = [date(f.get('createdAt') or f.get('created_at')) for f in fulfilments
                 if str(f.get('status','')).upper() == 'SUCCESS'] if fulfilled == 'FULFILLED' else []
    completed += [date(e['occurred_at']) for e in events if e['topic'] == 'orders/fulfilled' and fulfilled == 'FULFILLED']
    result=dict(id=row['shopify_order_id'], name=row.get('order_name') or row.get('order_number'),
        createdAt=row.get('created_at'), paid_at=min(paid) if paid else None,
        fullyPaid=state in ('PAID', 'PARTIALLY_REFUNDED'), displayFinancialStatus=state,
        displayFulfillmentStatus=fulfilled, cancelledAt=row.get('cancelled_at'),
        fulfilled_at=max(filter(None,completed),default=None), delivered_at=max(filter(None,delivered),default=None),
        fraudulent=raw.get('fraudulent') is True, disputed=bool(raw.get('disputes') or raw.get('disputed')),
        products=(raw.get('lineItems') or {}).get('nodes',[]) if isinstance(raw.get('lineItems'),dict) else raw.get('line_items',[]))
    if raw.get('lifecycleFacts'):
        from crm_lifecycle_shopify import operational_facts
        result.update(operational_facts(raw['lifecycleFacts'],fulfilled=='FULFILLED'))
    return result
