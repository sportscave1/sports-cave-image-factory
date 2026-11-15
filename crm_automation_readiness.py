"""Lifecycle publication gates; cached preview data never authorizes delivery."""
from datetime import timedelta
from crm_logic import date,now


def required_topics(kind,flow):
    from crm_automation_capabilities import TOPICS
    topics=list(TOPICS.get(kind,()))
    if flow.get('lifecycle_version') and 'ORDERS_PAID' not in topics:topics.append('ORDERS_PAID')
    if kind=='post_purchase' and any(s.get('enabled',True) and
            (s.get('anchor')=='delivery' or s.get('requires_fulfilment')) for s in flow.get('emails',[])):
        topics.append('ORDERS_FULFILLED')
    return tuple(dict.fromkeys(topics))


def worker_configuration(config):
    from email.utils import parseaddr
    from crm_resend_marketing import single_email
    return {'marketing_enabled':config.enabled,'provider_configured':bool(config.api_key.strip()),
        'sender_configured':bool(single_email(parseaddr(config.sender)[1]) and single_email(config.reply_to)
            and not any(ord(c)<32 for c in config.sender))}


def recent_health(health,at=None):
    checked=date(health.get('checked_at'));at=at or now()
    return bool(checked and checked<=at+timedelta(minutes=1) and at-checked<=timedelta(minutes=5)
        and health.get('status')=='ok')


def blockers(store,row,env=None,*,conn=None,published=False):
    from crm_automation_capabilities import blocking_reasons
    from crm_resend import Config
    kind=row['trigger_type']
    flow=(row['config'].get('published_flow') or row['config']['draft']) if published else row['config']['draft']
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
    for topic in required_topics(kind,flow):
        if not state.get('webhooks',{}).get(topic):
            detail=state.get('webhook_details',{}).get(topic,{}).get('status') or state.get('checks',{}).get(topic,'UNVERIFIED')
            reasons.append('Verify Shopify webhook: '+topic+' — '+detail)
    at=now()
    for key,label in (('worker_health','CRM delivery worker'),('automation_publication_health','CRM publication worker')):
        # A full cycle includes slow analytics/maintenance. Only completed,
        # lease-protected delivery work can supply the more recent evidence.
        health=(read('automation_delivery_health') or read(key)) if key=='worker_health' else read(key)
        if not recent_health(health,at):
            checked=date(health.get('checked_at'))
            if not checked:detail='no completed-work checkpoint recorded'
            elif checked>at+timedelta(minutes=1):detail='checkpoint timestamp is in the future'
            elif health.get('status')!='ok':detail='last checkpoint did not report successful work'
            else:detail='last completed work '+str(max(0,int((at-checked).total_seconds())))+'s ago (limit 300s)'
            reasons.append(label+' unavailable or stale: '+detail+'. Check the existing worker deployment and lease; a process heartbeat alone cannot clear this check.')
        elif key=='worker_health' and not all(health.get(k) for k in ('marketing_enabled','provider_configured','sender_configured')):
            reasons.append('CRM delivery worker marketing/provider/sender configuration is incomplete')
    config=Config(env)
    if not config.enabled:reasons.append('Enable the existing marketing delivery configuration before activation')
    configuration=worker_configuration(config)
    if not configuration['provider_configured'] or not configuration['sender_configured']:
        reasons.append('Configure valid Resend marketing API, sender and Reply-To')
    # New delivery exclusively obtains Shopify marketingUnsubscribeUrl from a
    # fresh recipient read and blocks missing/unsafe links in Engine.send_one.
    # Legacy signed URLs and their endpoint remain supported independently.
    return reasons


def require_ready(store,row,env=None,*,conn=None,published=False):
    reasons=blockers(store,row,env,conn=conn,published=published)
    if reasons:raise ValueError('Automation publication not ready: '+'; '.join(reasons))
