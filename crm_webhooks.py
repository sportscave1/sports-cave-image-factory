"""Minimal CRM webhook processing. Never persists raw Shopify/Resend payloads."""
import hashlib
from crm_logic import date,now,email,recipient_hash
from crm_shopify import gid

SHOPIFY_TOPICS={
 'customers/create':'CUSTOMERS_CREATE','customers/update':'CUSTOMERS_UPDATE','customers/delete':'CUSTOMERS_DELETE',
 'customers_email_marketing_consent/update':'CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE',
 'orders/create':'ORDERS_CREATE','orders/updated':'ORDERS_UPDATED','orders/cancelled':'ORDERS_CANCELLED',
 'checkouts/create':'CHECKOUTS_CREATE','checkouts/update':'CHECKOUTS_UPDATE','checkouts/delete':'CHECKOUTS_DELETE',
}
# Existing orders/paid fulfillment registration/handler is untouched. orders/updated
# re-queries fullyPaid to start CRM post-purchase, deduplicated by order ID.

def receive_shopify(store,topic,event_id,payload,occurred_at):
    if topic not in SHOPIFY_TOPICS and topic!='customers/redact':raise ValueError('Unsupported CRM topic.')
    if not event_id or len(event_id)>200:raise ValueError('Missing webhook identity.')
    kind='Customer' if topic.startswith('customers') else 'Order' if topic.startswith('orders/') else 'AbandonedCheckout'
    value=(payload.get('customer_id') if topic=='customers_email_marketing_consent/update' else payload.get('id')) or (payload.get('customer') or {}).get('id')
    customer_id=gid(value) if kind=='Customer' else gid((payload.get('customer') or {}).get('id'))
    object_id=gid(value,kind)
    if not object_id:raise ValueError('Missing Shopify object identity.')
    return store.webhook('shopify',event_id,topic,object_id,customer_id,date(occurred_at) or now())

def receive_resend(store,event_id,payload):
    event_type=payload.get('type','');data=payload.get('data') or {};provider_id=str(data.get('email_id') or '')
    allowed={'email.sent','email.delivered','email.opened','email.clicked','email.bounced','email.complained','email.suppressed','email.failed'}
    if event_type not in allowed:return False
    row=store.q('SELECT * FROM crm_marketing_sends WHERE provider_email_id=%s',(provider_id,),True)
    # Signed events can arrive before the send response is recorded. Retain only ID/type;
    # suppression is also checked directly against Resend before every subsequent send.
    address=next((email(x) for x in data.get('to',[]) if email(x)),'')
    hashed=row['recipient_hash'] if row else recipient_hash(address) if address else None
    result=store.event(event_id,provider_id,event_type,hashed,date(payload.get('created_at')) or now())
    if event_type in ('email.bounced','email.complained','email.suppressed') and hashed:
        reason={'email.bounced':'bounce','email.complained':'complaint','email.suppressed':'suppressed'}[event_type]
        store.suppress(hashed,row.get('shopify_customer_id') if row else None,reason,'resend',address or None)
    return bool(result)

def unsubscribe(store,config,token,shop=None):
    send_id=config.verify_token(token)
    if not send_id:raise ValueError('Invalid unsubscribe link.')
    row=store.receipt(send_id)
    if not row or not row.get('recipient_hash'):raise ValueError('Invalid unsubscribe link.')
    address=row.get('test_recipient')
    # Suppress immediately, even during Shopify outages. The worker resolves the
    # original delivery address from Resend only when provider synchronization needs it.
    store.suppress(row['recipient_hash'],row['shopify_customer_id'],'unsubscribe','marketing_footer',address)
    return True
