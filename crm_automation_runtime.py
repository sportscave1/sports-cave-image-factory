"""Native linear flows reuse Engine validation, queue, leases and Resend."""
from copy import deepcopy
from datetime import timedelta
import json
import logging
from time import perf_counter
from crm_logic import date, now, eligibility, recipient_hash, consent
from crm_automation_definition import native, qualifies

LOG=logging.getLogger(__name__)


def enter(engine, automation, customer_id, trigger_id, event_id, occurred_at, *, checkout_key=None, source_event_id=None,event_facts=None):
    """Serialize re-entry with publication/pause and freeze the complete flow."""
    started=perf_counter();store=engine.store;at=date(occurred_at)
    if not at: return None
    c=engine.shop.customer(customer_id,fresh=True)
    if not eligibility(c,store.suppressed(customer_id,recipient_hash((c or {}).get('email'))))[0]:return None
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(automation['id'],)).fetchone()
        if not row or not native(row) or row['status']!='ACTIVE' or not row['activated_at'] or at<date(row['activated_at']):return None
        flow=row['config']['published']
        from crm_automation_capabilities import require as require_trigger
        try:require_trigger(store,flow['trigger'])
        except ValueError:
            LOG.info('automation_trigger_held automation_id=%s trigger_type=%s reason=capability_unverified',row['id'],flow['trigger'])
            return None
        if checkout_key:
            checkout=conn.execute("SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s FOR UPDATE",(checkout_key,)).fetchone()
            if not checkout or checkout['status']=='RECOVERED' or checkout['customer_id']!=customer_id:return None
        if not qualifies(flow,c,event_facts):return None
        # Duplicate source identities remain blocked across ALL flow versions.
        if conn.execute('SELECT 1 FROM crm_automation_enrollments WHERE automation_id=%s AND trigger_key=%s',(row['id'],event_id)).fetchone():return None
        prior=conn.execute('SELECT trigger_at,status FROM crm_automation_enrollments WHERE automation_id=%s AND shopify_customer_id=%s ORDER BY trigger_at DESC LIMIT 1',(row['id'],customer_id)).fetchone()
        if prior and (flow['reentry_days']==0 or prior['status']=='ACTIVE' or at<date(prior['trigger_at'])+timedelta(days=flow['reentry_days'])):return None
        steps=deepcopy(row['steps'])
        if not steps:return None
        result=conn.execute('''INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,trigger_shopify_id,trigger_key,trigger_at,steps,next_due_at,checkout_key,source_event_id)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *''',
          (row['id'],customer_id,trigger_id,event_id,at,json.dumps(steps),at+timedelta(seconds=steps[0]['delay_seconds']),checkout_key,source_event_id)).fetchone()
    if result:LOG.info('automation_entry automation_id=%s automation_version=%s trigger_type=%s trigger_event_id=%s journey_id=%s journey_status=ACTIVE due_at=%s duration_ms=%.1f',row['id'],steps[0]['automation_version'],flow['trigger'],event_id,result['id'],result['next_due_at'],(perf_counter()-started)*1000)
    return result


def process_event(engine,event,automations):
    topic=event['topic'];at=date(event['occurred_at'])
    if not at:return
    normalized=event.get('normalized') or {}
    key=normalized.get('checkout_key')
    if key and topic.startswith('orders/'):
        from crm_shopify_automation_events import recover
        recover(engine.store,key)
    candidates=[a for a in automations if native(a) and a['status']=='ACTIVE' and date(a['activated_at']) and at>=date(a['activated_at'])]
    if not candidates:return
    if topic=='customers_email_marketing_consent/update':
        identity=event['related_customer_id']
        c=engine.shop.customer(identity,fresh=True)
        changed=date((c.get('emailMarketingConsent') or {}).get('consentUpdatedAt')) if c else None
        if consent(c)!='SUBSCRIBED' or not changed or abs((changed-at).total_seconds())>300:return
        # New consent events must explicitly report subscribed and match Shopify's
        # current consent version. Legacy inbox rows cannot enroll native flows.
        if normalized.get('consent_state')!='SUBSCRIBED' or normalized.get('consent_unchanged'):return
        event_changed=date(normalized.get('consent_updated_at'))
        if event_changed and event_changed!=changed:return
        for a in candidates:
            if a['trigger_type']=='welcome':enter(engine,a,identity,identity,identity+':'+changed.isoformat(),changed,source_event_id=event.get('event_id'))
    elif topic in ('orders/paid','orders/fulfilled'):
        order=engine.shop.order(event['object_id'],fresh=True)
        if not order or order.get('cancelledAt') or not order.get('customer'):return
        if topic=='orders/paid' and not order.get('fullyPaid'):return
        created=date(order.get('createdAt'))
        from crm_automation_rule_facts import order_facts
        relevant=[r for a in candidates if a['trigger_type'] in ('post_purchase','fulfilled') for r in a['config']['published']['rules']]
        context=order_facts(engine.shop,order,relevant)
        for a in candidates:
            kind='post_purchase' if topic=='orders/paid' else 'fulfilled'
            if kind=='fulfilled' and order.get('displayFulfillmentStatus')!='FULFILLED':continue
            if a['trigger_type']==kind and created and at>=date(a['activated_at']):
                enter(engine,a,order['customer']['id'],order['id'],order['id'] if kind=='post_purchase' else kind+':'+order['id'],at,source_event_id=event.get('event_id'),event_facts=context)


def reconcile(engine,a):
    if a['trigger_type']!='abandoned':return
    key='reconcile:native:'+str(a['id'])+':'+str(a['config']['published_version'])+':'+str(a['activated_at'])
    state=engine.store.state(key);at=engine.clock()
    if date(state.get('next_at')) and date(state['next_at'])>at:return
    cutoff=date(a['activated_at']);cursor=state.get('cursor')
    from crm_automation_capabilities import require as require_trigger
    require_trigger(engine.store,'abandoned')
    # The signed future-only token ledger is the entry boundary. Admin checkout
    # objects only resolve/recheck those exact identities; never backfill others.
    page=engine.shop.checkouts(cursor,query='created_at:>='+cutoff.isoformat(),fresh=True)
    more=page['pageInfo'].get('hasNextPage');end=page['pageInfo'].get('endCursor')
    if more and (not end or end==cursor):raise ValueError('Abandoned checkout pagination did not advance.')
    for checkout in page['nodes']:
        created=date(checkout.get('createdAt'))
        c=checkout.get('customer')
        from crm_shopify_automation_events import key_from_recovery_url
        import os
        key=key_from_recovery_url(checkout.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN',''))
        state_row=engine.store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(key,),True) if key else None
        if not state_row or state_row['status']=='RECOVERED' or not c or state_row['customer_id']!=c['id']:continue
        threshold=a['config']['published'].get('abandonment_seconds',3600)
        activity=date(state_row['activity_at'])
        if created and cutoff<=created and cutoff<=date(state_row['created_at']) and activity<=at-timedelta(seconds=threshold) and not checkout.get('completedAt'):
            engine.store.q("UPDATE crm_shopify_checkouts SET admin_checkout_id=%s,status=CASE WHEN status='OPEN' THEN 'ABANDONED' ELSE status END WHERE checkout_key=%s AND status<>'RECOVERED'",(checkout['id'],key))
            from crm_automation_rule_facts import checkout_facts
            enter(engine,a,c['id'],checkout['id'],'checkout:'+key,activity+timedelta(seconds=threshold),checkout_key=key,source_event_id=state_row['source_event_id'],event_facts=checkout_facts(checkout))
    engine.store.set_state(key,{'cursor':end if more else None,'next_at':(at+timedelta(seconds=2 if more else 300)).isoformat()})


def advance(engine,enrollment):
    store=engine.store;steps=enrollment['steps'];index=enrollment['current_step']
    if date(enrollment.get('next_due_at')) and date(enrollment['next_due_at'])>engine.clock():return
    if index>=len(steps):
        store.q("UPDATE crm_automation_enrollments SET status='COMPLETED',updated_at=now() WHERE id=%s",(enrollment['id'],));return
    step=steps[index]
    c,_,reason=engine.validate(enrollment['shopify_customer_id'],enrollment)
    if reason=='automation_paused':return
    if reason:engine.stop(enrollment,reason);return
    key='automation:'+str(enrollment['id'])+':'+str(index)
    receipt=store.q('SELECT * FROM crm_marketing_sends WHERE idempotency_key=%s',(key,),True)
    if not receipt:
        store.enqueue(key,c['id'],recipient_hash(c['email']),{'id':step['template_id'],'version':step['template_version']},enrollment_id=enrollment['id'],step_index=index)
        return
    if receipt['status'] in ('PENDING','CLAIMED','SUBMITTING'):return
    if receipt['status']!='ACCEPTED':engine.stop(enrollment,receipt['error_code'] or 'send_held');return
    if enrollment.get('checkout_key'):
        store.q("UPDATE crm_shopify_checkouts SET status='RECOVERY_EMAIL_SENT',updated_at=now() WHERE checkout_key=%s AND status<>'RECOVERED'",(enrollment['checkout_key'],))
    index+=1
    at=date(receipt['updated_at']) or engine.clock()
    due=at+timedelta(seconds=steps[index]['delay_seconds']) if index<len(steps) else at
    store.q("UPDATE crm_automation_enrollments SET current_step=%s,next_due_at=%s,status=%s,last_checked_at=now(),updated_at=now() WHERE id=%s AND current_step=%s",
            (index,due,'ACTIVE' if index<len(steps) else 'COMPLETED',enrollment['id'],index-1))
    LOG.info('automation_progress automation_id=%s automation_version=%s journey_id=%s step_id=%s journey_status=%s',enrollment['automation_id'],step['automation_version'],enrollment['id'],step['step_id'],'ACTIVE' if index<len(steps) else 'COMPLETED')
    LOG.info('automation_submission automation_id=%s journey_id=%s step_id=%s provider_message_id=%s sent_at=%s',enrollment['automation_id'],enrollment['id'],step['step_id'],receipt.get('provider_email_id'),receipt.get('first_submitted_at'))


def render(content,row,unsubscribe,context=None):
    from crm_campaign_content import render_campaign
    from crm_campaign_send import production_checks
    from crm_email_size import validate_rendered_email
    from crm_tracking import send_identity
    from crm_automation_definition import production_document
    doc=production_document(content['document']);doc['campaign_key']='auto_'+str(row['id']).replace('-','')
    from crm_abandoned_checkout import dynamic,hydrate,context as checkout_context,reject_unresolved
    if dynamic(doc):
        source=(context or {}).get('_checkout')
        if content.get('trigger')!='abandoned' or not source or source.get('id')!=(context or {}).get('_checkout_id') or (source.get('customer') or {}).get('id')!=row['shopify_customer_id']:
            raise ValueError('Checkout recipient context mismatch.')
        doc=hydrate(doc,checkout_context(source))
    if not all(production_checks(doc,content['render_settings'],reviewed_audience=True).values()):raise ValueError('Automation production readiness failed.')
    message=render_campaign(doc,content['render_settings'],unsubscribe_url=unsubscribe,production=True,
                            campaign_id=str(row['id']),send_id=send_identity(row['id']))
    reject_unresolved(message['html']);reject_unresolved(message['text'])
    validate_rendered_email(message);message['unsubscribe_url']=unsubscribe
    return message
