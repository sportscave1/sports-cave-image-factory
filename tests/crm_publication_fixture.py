"""Fabricated readiness evidence for disposable localhost PostgreSQL only."""
from crm_logic import now
from crm_automation_capabilities import TOPICS

def ready(store):
    store.set_state('shopify_automation_capabilities',{
        'checked_at':now().isoformat(),
        'scopes':['read_customers','read_orders','read_all_orders','read_products'],
        'triggers':{k:'AVAILABLE' for k in ('welcome','post_purchase','win_back','abandoned','fulfilled')},
        'webhooks':{t:True for ts in TOPICS.values() for t in ts}})
    store.set_state('automation_delivery_health',{})
    for key in ('worker_health','automation_publication_health'):
        store.set_state(key,{'checked_at':now().isoformat(),'status':'ok','marketing_enabled':True,'provider_configured':True,'sender_configured':True})
