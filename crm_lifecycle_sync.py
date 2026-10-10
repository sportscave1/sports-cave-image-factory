"""Bounded cache refresh in the existing worker. No delivery or enrollment."""
from time import monotonic
from crm_lifecycle_audience import sync_page

_next_check=0

def tick(store,shop):
    global _next_check
    at=monotonic()
    if at<_next_check:return False
    _next_check=at+30
    # Additive migration can be rolled back without breaking the existing worker.
    ready=store.q("SELECT to_regclass('crm_lifecycle_customers') IS NOT NULL AS ready",one=True)
    if not ready or not ready['ready']:return False
    if not store.q("SELECT 1 FROM crm_automations WHERE config->'draft'->>'lifecycle_version'='1' LIMIT 1",one=True):return False
    store.q("DELETE FROM crm_lifecycle_customers c USING crm_suppressions s WHERE s.shopify_customer_id=c.customer_id AND s.reason='redacted'")
    worked=sync_page(store,shop)
    from crm_lifecycle_shopify import sync_order_facts
    sync_order_facts(store,shop)
    return worked
