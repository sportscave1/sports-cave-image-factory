"""Lifecycle publication gates; cached preview data never authorizes delivery."""
from datetime import timedelta
from crm_logic import date,now


def blockers(store,row,env=None,*,conn=None):
    from crm_automation_capabilities import blocking_reasons
    from crm_resend import Config
    kind=row['trigger_type'];flow=row['config'].get('published_flow') or row['config']['draft']
    def read(key):
        if conn is None:return store.state(key) or {}
        record=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s',(key,)).fetchone()
        return record['value'] if record else {}
    state=read('shopify_automation_capabilities')
    reasons=list(blocking_reasons(state,kind))
    scopes={'read_customers'}
    if kind!='welcome' or flow.get('lifecycle_version'):scopes.add('read_orders')
    if flow.get('lifecycle_version') or kind=='win_back':scopes.add('read_all_orders')
    from crm_lifecycle_products import selected
    from crm_collector_images import configurations
    try:
        products=any(selected(step['document']) or any(c['source'] not in ('No Image','Static Selected Image') for c in configurations(step['document'])) for step in flow.get('emails',[]) if step.get('enabled',True))
    except ValueError as exc:
        products=True;reasons.append(str(exc))
    if kind in ('post_purchase','fulfilled') or products:
        scopes.add('read_products')
    for scope in sorted(scopes-set(state.get('scopes',[]))):
        reasons.append('Shopify permission missing: '+scope)
    # Expanded journeys depend on these events for payment exits and delivery clocks.
    if flow.get('lifecycle_version'):
        topics=['ORDERS_PAID']
        if kind=='post_purchase':topics.append('ORDERS_FULFILLED')
        for topic in topics:
            if not state.get('webhooks',{}).get(topic):reasons.append('Verify Shopify webhook: '+topic)
    at=now()
    for key,label in (('worker_health','CRM delivery worker'),('automation_publication_health','CRM publication worker')):
        health=read(key);checked=date(health.get('checked_at'))
        if not checked or checked>at+timedelta(minutes=1) or at-checked>timedelta(minutes=5) or health.get('status')!='ok':
            reasons.append(label+' unavailable or stale; start the existing CRM worker and rerun Diagnostics')
        elif key=='worker_health' and not all(health.get(k) for k in ('marketing_enabled','provider_configured','sender_configured')):
            reasons.append('CRM delivery worker marketing/provider/sender configuration is incomplete')
    config=Config(env)
    if not config.enabled:reasons.append('Enable the existing marketing delivery configuration before activation')
    if not config.api_key or not config.sender or not config.reply_to:reasons.append('Configure Resend marketing API, sender and Reply-To')
    try:config.unsubscribe_url('00000000-0000-4000-8000-000000000001')
    except ValueError:reasons.append('Configure the public HTTPS unsubscribe endpoint and signing secret')
    except RuntimeError:reasons.append('Configure the public HTTPS unsubscribe endpoint and signing secret')
    return reasons


def require_ready(store,row,env=None,*,conn=None):
    reasons=blockers(store,row,env,conn=conn)
    if reasons:raise ValueError('Automation publication not ready: '+'; '.join(reasons))
