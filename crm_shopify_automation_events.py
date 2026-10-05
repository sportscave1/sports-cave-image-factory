"""Minimal signed event facts. Tokens are hashed, never logged or stored raw."""
import hashlib
import json
import logging
import re
from urllib.parse import urlsplit
from crm_logic import date, now
from crm_shopify import gid

LOG = logging.getLogger(__name__)
VERSION = '2026-04'


def checkout_key(token, shop):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,256}', token) or not shop:
        return None
    return hashlib.sha256((shop.lower() + ':' + token).encode()).hexdigest()


def key_from_recovery_url(url, shop):
    """Match only Shopify's explicit checkout path; never infer a numeric GID."""
    parts = urlsplit(url or '')
    if parts.scheme != 'https': return None
    path = parts.path.split('/')
    try:
        index = path.index('checkouts') + 1
        if path[index] in ('cn','ac'): index += 1
        return checkout_key(path[index], shop)
    except (ValueError, IndexError): return None


def facts(topic, payload, shop, at):
    if not isinstance(payload, dict): raise ValueError('Invalid Shopify envelope.')
    result = {'payload_version': VERSION, 'shop': shop}
    token = payload.get('token') if topic.startswith('checkouts/') else payload.get('checkout_token')
    key = checkout_key(token, shop)
    if topic.startswith('checkouts/') and not key: raise ValueError('Missing checkout token.')
    if key: result['checkout_key'] = key
    if topic == 'customers_email_marketing_consent/update':
        consent = payload.get('email_marketing_consent') or {}
        state = consent.get('state') or consent.get('marketing_state') or payload.get('email_marketing_consent_state')
        changed = date(consent.get('consent_updated_at') or payload.get('consent_updated_at'))
        if isinstance(state, str): result['consent_state'] = state.upper()
        if changed: result['consent_updated_at'] = changed.isoformat()
    if topic.startswith(('checkouts/', 'orders/')):
        created = date(payload.get('created_at'))
        updated = date(payload.get('updated_at')) or at
        if created: result['created_at'] = created.isoformat()
        result['updated_at'] = updated.isoformat()
        result['completed'] = bool(payload.get('completed_at')) or topic.startswith('orders/')
        # Only IDs and country; no addresses, names, email or raw line items.
        products = sorted({gid(p.get('product_id'), 'Product') for p in (payload.get('line_items') or []) if isinstance(p, dict)} - {''})
        result['product_ids'] = products[:100]
        country = (payload.get('shipping_address') or payload.get('billing_address') or {}).get('country_code')
        if isinstance(country, str) and re.fullmatch('[A-Z]{2}', country): result['checkout_country'] = country
    return result


def persist(store, event_id, topic, object_id, customer_id, at, normalized,*,display=None):
    """Commit inbox and completion guard together; no Shopify/Resend work here."""
    key = normalized.get('checkout_key')
    with store.db() as conn:
        inserted = conn.execute('''INSERT INTO crm_webhook_events(provider,event_id,topic,object_id,related_customer_id,occurred_at,normalized)
          VALUES('shopify',%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING event_id''',
          (event_id, topic, object_id, customer_id or '', at, json.dumps(normalized))).fetchone()
        if not inserted: return False
        if topic=='customers_email_marketing_consent/update':
            changed=date(normalized.get('consent_updated_at'));state=normalized.get('consent_state')
            if changed and state:
                prior=conn.execute('SELECT * FROM crm_shopify_consent_versions WHERE customer_id=%s FOR UPDATE',(customer_id,)).fetchone()
                normalized['consent_unchanged']=bool(prior and (prior['state']==state or date(prior['changed_at'])>=changed))
                conn.execute('''INSERT INTO crm_shopify_consent_versions(customer_id,state,changed_at) VALUES(%s,%s,%s)
                  ON CONFLICT(customer_id) DO UPDATE SET state=excluded.state,changed_at=excluded.changed_at
                  WHERE crm_shopify_consent_versions.changed_at<excluded.changed_at''',(customer_id,state,changed))
                conn.execute("UPDATE crm_webhook_events SET normalized=%s::jsonb WHERE provider='shopify' AND event_id=%s",(json.dumps(normalized),event_id))
        if key:
            completed = normalized.get('completed', False)
            conn.execute('''INSERT INTO crm_shopify_checkouts(checkout_key,shop,customer_id,source_event_id,created_at,activity_at,status,order_id)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(checkout_key) DO UPDATE SET
              customer_id=COALESCE(NULLIF(excluded.customer_id,''),crm_shopify_checkouts.customer_id),
              source_event_id=CASE WHEN excluded.activity_at>=crm_shopify_checkouts.activity_at THEN excluded.source_event_id ELSE crm_shopify_checkouts.source_event_id END,
              activity_at=GREATEST(excluded.activity_at,crm_shopify_checkouts.activity_at),
              status=CASE WHEN excluded.status='RECOVERED' THEN 'RECOVERED' ELSE crm_shopify_checkouts.status END,
              order_id=COALESCE(excluded.order_id,crm_shopify_checkouts.order_id),updated_at=now()''',
              (key, normalized['shop'], customer_id or '', event_id, date(normalized.get('created_at')) or at,
               date(normalized['updated_at']), 'RECOVERED' if completed else 'OPEN', object_id if topic.startswith('orders/') else None))
            if display:
                from crm_logic import recipient_hash
                safe={k:v for k,v in display.items() if k in ('name','email','country','region') and v}
                conn.execute("""UPDATE crm_shopify_checkouts SET analytics=analytics||%s::jsonb
                  WHERE checkout_key=%s AND activity_at<=%s AND NOT EXISTS(SELECT 1 FROM crm_suppressions
                  WHERE reason='redacted' AND (shopify_customer_id=%s OR recipient_hash=%s))""",
                  (json.dumps(safe),key,date(normalized['updated_at']),customer_id,recipient_hash(safe.get('email'))))
    store.invalidate()
    LOG.info('shopify_automation_ingest shopify_topic=%s shopify_event_id=%s checkout_key=%s order_id=%s', topic, event_id, key or '-', object_id if topic.startswith('orders/') else '-')
    return True


def recover(store, key):
    """Worker cancels pending steps. SUBMITTING/ACCEPTED receipts stay immutable."""
    with store.db() as conn:
        rows = conn.execute("SELECT id FROM crm_automation_enrollments WHERE checkout_key=%s AND status='ACTIVE' FOR UPDATE", (key,)).fetchall()
        for row in rows:
            conn.execute("UPDATE crm_automation_enrollments SET status='RECOVERED',stop_reason='CHECKOUT_RECOVERED',updated_at=now() WHERE id=%s", (row['id'],))
            conn.execute("UPDATE crm_marketing_sends SET status='BLOCKED',error_code='CHECKOUT_RECOVERED',updated_at=now() WHERE enrollment_id=%s AND status IN ('PENDING','CLAIMED')", (row['id'],))
    LOG.info('shopify_automation_recovery checkout_key=%s journey_cancelled=%s recovered=true', key, len(rows))
