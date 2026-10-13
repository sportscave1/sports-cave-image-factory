"""Stop reminders from signed paid-order evidence; never claim recovery/revenue."""
from crm_logic import date

REASON='NEWER_PAID_ORDER'
LABEL='Purchased — reminders stopped'

# The inbox contains HMAC-verified events, not arbitrary customer/order caches.
# Compare the payment event time, never its receipt/processing time. Cancelled
# or refunded order evidence cannot authorize a new exit. A stopped journey is
# never reopened automatically if an order is subsequently cancelled.
PROOF_SQL="""SELECT p.object_id AS order_id,p.occurred_at AS paid_at,p.event_id
 FROM crm_webhook_events p WHERE p.provider='shopify' AND p.topic='orders/paid'
 AND p.related_customer_id=%s AND p.normalized->>'shop'=%s
 AND p.normalized->>'payload_version'='2026-04' AND p.occurred_at>%s
 AND p.occurred_at<=now() AND COALESCE(p.normalized->>'order_cancelled','false')<>'true'
 AND COALESCE(p.normalized->>'financial_status','PAID')='PAID'
 AND NOT EXISTS(SELECT 1 FROM crm_webhook_events x WHERE x.provider='shopify'
   AND x.object_id=p.object_id AND x.normalized->>'shop'=p.normalized->>'shop'
   AND (x.topic='orders/cancelled' OR x.normalized->>'order_cancelled'='true'
     OR x.normalized->>'financial_status' IN ('REFUNDED','VOIDED')))
 ORDER BY p.occurred_at DESC,p.event_id LIMIT 1"""


def proof(conn,checkout,customer_id=None):
    created=date(checkout.get('created_at'));customer=customer_id or checkout.get('customer_id')
    if not created or not customer or not checkout.get('shop'):return None
    if checkout.get('customer_id') not in ('',None,customer):return None
    return conn.execute(PROOF_SQL,(customer,checkout['shop'],created)).fetchone()


def stop_locked(conn,journey,checkout):
    if journey['status']!='ACTIVE' or not checkout or checkout.get('order_id') or checkout['status']=='RECOVERED':return False
    evidence=proof(conn,checkout,journey['shopify_customer_id'])
    if not evidence:return False
    conn.execute("UPDATE crm_automation_enrollments SET status='STOPPED',stop_reason=%s,retry_after=NULL,last_checked_at=now(),updated_at=now() WHERE id=%s AND status='ACTIVE'",(REASON,journey['id']))
    conn.execute("UPDATE crm_marketing_sends SET status='BLOCKED',error_code=%s,lease_until=NULL,updated_at=now() WHERE enrollment_id=%s AND status IN ('PENDING','CLAIMED') AND first_submitted_at IS NULL AND provider_email_id IS NULL",(REASON,journey['id']))
    # Keep checkout/order_id/completion facts untouched: this checkout did not
    # convert. SUBMITTING, UNCERTAIN and ACCEPTED receipts remain immutable.
    return True


def stop_if_purchased(store,enrollment):
    if not enrollment.get('checkout_key'):return False
    with store.db() as conn:
        journey=conn.execute('SELECT * FROM crm_automation_enrollments WHERE id=%s FOR UPDATE',(enrollment['id'],)).fetchone()
        if not journey:return False
        if journey['status']=='STOPPED' and journey.get('stop_reason')==REASON:return True
        checkout=conn.execute('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(journey['checkout_key'],)).fetchone()
        return stop_locked(conn,journey,checkout)


def stop_customer(store,customer_id):
    if not customer_id:return
    rows=store.q("SELECT e.* FROM crm_automation_enrollments e JOIN crm_automations a ON a.id=e.automation_id WHERE e.shopify_customer_id=%s AND e.status='ACTIVE' AND e.checkout_key IS NOT NULL AND COALESCE(e.steps->0->>'trigger',a.trigger_type)='abandoned'",(customer_id,))
    for row in rows:stop_if_purchased(store,row)


def purchased(row):
    return row.get('stop_reason')==REASON or bool(row.get('newer_paid_order_verified'))
