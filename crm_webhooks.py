"""Minimal CRM webhook processing. Never persists raw Shopify/Resend payloads."""
import hashlib
import re
import uuid
from crm_logic import date,now,email,recipient_hash
from crm_shopify import gid

SHOPIFY_TOPICS={
 'customers/create':'CUSTOMERS_CREATE','customers/update':'CUSTOMERS_UPDATE','customers/delete':'CUSTOMERS_DELETE',
 'customers_email_marketing_consent/update':'CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE',
 'segments/create':'SEGMENTS_CREATE','segments/update':'SEGMENTS_UPDATE','segments/delete':'SEGMENTS_DELETE',
 'orders/create':'ORDERS_CREATE','orders/updated':'ORDERS_UPDATED','orders/paid':'ORDERS_PAID','orders/cancelled':'ORDERS_CANCELLED',
 'checkouts/create':'CHECKOUTS_CREATE','checkouts/update':'CHECKOUTS_UPDATE','checkouts/delete':'CHECKOUTS_DELETE',
}
# The existing paid fulfillment endpoint forwards its signed event to this ledger.

def receive_shopify(store,topic,event_id,payload,occurred_at):
    if topic not in SHOPIFY_TOPICS and topic!='customers/redact':raise ValueError('Unsupported CRM topic.')
    if not event_id or len(event_id)>200:raise ValueError('Missing webhook identity.')
    kind='Segment' if topic.startswith('segments/') else 'Customer' if topic.startswith('customers') else 'Order' if topic.startswith('orders/') else 'AbandonedCheckout'
    value=(payload.get('customer_id') if topic=='customers_email_marketing_consent/update' else payload.get('id')) or (payload.get('customer') or {}).get('id')
    customer_id=gid(value) if kind=='Customer' else gid((payload.get('customer') or {}).get('id'))
    object_id=gid(value,kind)
    if not object_id:raise ValueError('Missing Shopify object identity.')
    return store.webhook('shopify',event_id,topic,object_id,customer_id,date(occurred_at) or now())

def receive_resend(store,event_id,payload):
    from crm_workspace_store import WorkspaceRecords
    if not isinstance(event_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}',event_id) or not isinstance(payload,dict):raise ValueError('Invalid event envelope.')
    event_type=payload.get('type','');data=payload.get('data')
    allowed={'email.sent','email.delivered','email.delivery_delayed','email.opened','email.clicked','email.bounced','email.complained','email.failed','email.suppressed','email.scheduled'}
    if event_type not in allowed:return False
    if not isinstance(data,dict):raise ValueError('Invalid event data.')
    try:provider_id=str(uuid.UUID(data.get('email_id','')))
    except (ValueError,TypeError,AttributeError):raise ValueError('Invalid provider ID.') from None
    occurred=date(payload.get('created_at'))
    if not occurred:raise ValueError('Invalid event timestamp.')
    bounce=data.get('bounce') or {}
    if not isinstance(bounce,dict):raise ValueError('Invalid bounce metadata.')
    hard=event_type=='email.bounced' and bounce.get('type')=='Permanent'
    records=WorkspaceRecords(store.connect)
    from crm_tracking import event_link
    click=data.get('click') or {}
    clicked_url=event_link(click.get('link')) if isinstance(click,dict) and event_type=='email.clicked' else None
    result=records.q('INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,hard_bounce,clicked_url) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id',(event_id,provider_id,event_type,occurred,hard,clicked_url),True)
    # Store minimal unmatched events for race recovery. They cannot count as CRM
    # delivery or suppress anyone until a locally stored provider receipt matches.
    records.reconcile_events(provider_id)
    return bool(result)


def forward_paid_order(payload,event_id,occurred_at):
    """Reuse the existing paid endpoint; fulfillment success is independent of CRM."""
    try:
        from crm_store import Store
        receive_shopify(Store(),'orders/paid',event_id,payload,occurred_at)
    except Exception:
        import logging
        logging.getLogger(__name__).warning('crm_paid_event_delayed; bounded reconciliation will retry')

def unsubscribe(store,config,token,shop=None):
    send_id=config.verify_token(token)
    if not send_id:raise ValueError('Invalid unsubscribe link.')
    row=store.receipt(send_id)
    if not row or not row.get('recipient_hash') or row.get('test_send'):raise ValueError('Invalid unsubscribe link.')
    # Suppress immediately, even during Shopify outages. The worker resolves the
    # original delivery address from Resend only when provider synchronization needs it.
    store.record_unsubscribe(dict(row,id=send_id))
    from crm_consent_sync import reconcile_opt_out
    # Client configuration can fail too. It must never precede the local commit.
    reconcile_opt_out(store,row['recipient_hash'],shop,approved=True)
    return True
