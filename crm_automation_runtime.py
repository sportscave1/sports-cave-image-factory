"""Native linear flows reuse Engine validation, queue, leases and Resend."""
from copy import deepcopy
from datetime import timedelta
import json
import logging
from time import perf_counter
from crm_logic import date, now, eligibility, recipient_hash, consent
from crm_automation_definition import native, qualifies

LOG=logging.getLogger(__name__)


def enter(engine, automation, customer_id, trigger_id, event_id, occurred_at, *, checkout_key=None, source_event_id=None,event_facts=None,manual_checkout=False,recipient=None,checkout_source=None):
    """Serialize re-entry with publication/pause and freeze the complete flow."""
    started=perf_counter();store=engine.store;at=date(occurred_at)
    if not at: return None
    c=recipient if recipient is not None else engine.shop.customer(customer_id,fresh=True)
    if automation['trigger_type']=='abandoned':
        from crm_checkout_eligibility import recovery_eligibility,policy
        checkout_source=checkout_source or engine.shop.checkout(trigger_id,fresh=True)
        if not recovery_eligibility(checkout_source,c,policy(store),suppressed=store.suppressed(customer_id,recipient_hash((c or {}).get('email'))),manual=manual_checkout)[0]:return None
    elif not eligibility(c,store.suppressed(customer_id,recipient_hash((c or {}).get('email'))))[0]:return None
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
            if not checkout or checkout['status']=='RECOVERED' or checkout['customer_id'] not in ('',customer_id):return None
            if not manual_checkout and date(checkout['activity_at'])>at:return None
            if manual_checkout:
                # Recheck under the same row locks as publication and enrollment;
                # a concurrent checkout update must not bypass the inactivity timer.
                if flow['trigger']!='abandoned' or row['config'].get('archived_at') or row['config'].get('deleted_at'):return None
                # Explicit single-checkout admin entry may predate activation.
                # Automatic reconciliation below retains its future-only cutoff.
                if date(checkout['activity_at'])>at:return None
        if not qualifies(flow,c,event_facts):return None
        # Duplicate source identities remain blocked across ALL flow versions.
        if conn.execute('SELECT 1 FROM crm_automation_enrollments WHERE automation_id=%s AND trigger_key=%s',(row['id'],event_id)).fetchone():return None
        prior=conn.execute('SELECT trigger_at,status FROM crm_automation_enrollments WHERE automation_id=%s AND shopify_customer_id=%s ORDER BY trigger_at DESC LIMIT 1',(row['id'],customer_id)).fetchone()
        if prior and (flow['reentry_days']==0 or prior['status']=='ACTIVE' or at<date(prior['trigger_at'])+timedelta(days=flow['reentry_days'])):return None
        from crm_automation_timing import enrollment_steps,scheduled_at
        steps=enrollment_steps(row)
        if not steps:return None
        due_base=at
        if manual_checkout:
            steps[0]['manual_checkout']=True
            steps[0]['delay_seconds']=0
        result=conn.execute('''INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,trigger_shopify_id,trigger_key,trigger_at,steps,next_due_at,checkout_key,source_event_id)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *''',
          (row['id'],customer_id,trigger_id,event_id,due_base,json.dumps(steps),scheduled_at(due_base,steps[0]['delay_seconds']),checkout_key,source_event_id)).fetchone()
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
    if a['trigger_type']=='win_back':
        return reconcile_inactive(engine,a)
    if a['trigger_type']!='abandoned':return
    state_key='reconcile:native:'+str(a['id'])+':'+str(a['config']['published_version'])+':'+str(a['activated_at'])
    state=engine.store.state(state_key);at=engine.clock()
    if date(state.get('next_at')) and date(state['next_at'])>at:return
    cutoff=date(a['activated_at'])
    # First rollout establishes a future-only boundary; cache/repair cannot bulk enroll history.
    boundary=engine.store.state('checkout-auto-start-v2')
    if not boundary.get('started_at'):
        boundary={'started_at':at.isoformat()};engine.store.set_state('checkout-auto-start-v2',boundary)
    cutoff=max(cutoff,date(boundary['started_at']))
    from crm_automation_capabilities import require as require_trigger
    require_trigger(engine.store,'abandoned')
    # Reuse the working Admin mirror. No second catalogue/pagination scan.
    candidates=engine.store.q("""SELECT c.* FROM crm_shopify_checkouts c
      LEFT JOIN crm_runtime_state v ON v.key='checkout-evaluation:'||c.checkout_key||':'||%s::text
      WHERE c.created_at>=%s AND c.activity_at>=%s AND c.activity_at<=%s AND c.status<>'RECOVERED'
      AND c.admin_checkout_id IS NOT NULL AND c.analytics->>'shopify_abandoned'='true'
      AND NOT EXISTS(SELECT 1 FROM crm_automation_enrollments e WHERE e.automation_id=%s AND e.checkout_key=c.checkout_key)
      AND (v.value->>'at' IS NULL OR (v.value->>'at')::timestamptz<c.activity_at OR (v.value->>'at')::timestamptz<%s)
      ORDER BY c.activity_at,c.checkout_key LIMIT 20""",(str(a['id']),cutoff,cutoff,at,a['id'],at-timedelta(minutes=5)))
    for candidate in candidates:
        engine.hold_lease()
        # One fresh detail only for a bounded, not-yet-enrolled candidate.
        evaluation_key='checkout-evaluation:'+candidate['checkout_key']+':'+str(a['id'])
        try:checkout=engine.shop.checkout(candidate['admin_checkout_id'],fresh=True)
        except Exception as exc:
            engine.store.set_state(evaluation_key,{'result':'Error: checkout verification unavailable','at':at.isoformat()})
            LOG.warning('checkout_verification_held checkout_key=%s automation_id=%s error_class=%s',candidate['checkout_key'],a['id'],type(exc).__name__)
            continue
        if not isinstance(checkout,dict) or not checkout:
            engine.store.set_state(evaluation_key,{'result':'Error: checkout unavailable','at':at.isoformat()});continue
        created=date(checkout.get('createdAt'))
        c=checkout.get('customer')
        from crm_shopify_automation_events import key_from_recovery_url
        import os
        key=key_from_recovery_url(checkout.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN',''))
        if key!=candidate['checkout_key'] or checkout.get('id')!=candidate['admin_checkout_id']:
            engine.store.set_state(evaluation_key,{'result':'Error: checkout identity mismatch','at':at.isoformat()});continue
        from crm_checkout_analytics import details
        details(engine.store,checkout)
        state_row=engine.store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(key,),True) if key else None
        if not state_row or state_row['status']=='RECOVERED':continue
        if date(state_row['activity_at'])<cutoff:continue
        if engine.store.q('SELECT 1 FROM crm_automation_enrollments WHERE automation_id=%s AND checkout_key=%s',(a['id'],key),True):continue
        from crm_checkout_identity import recipient
        evaluation_key='checkout-evaluation:'+key+':'+str(a['id'])
        try:c=recipient(engine.shop,engine.store,checkout,state_row)
        except ValueError:
            engine.store.set_state(evaluation_key,{'result':'Missing email' if not state_row.get('analytics',{}).get('email') else 'Not eligible: verified identity unavailable','at':at.isoformat()});continue
        from crm_checkout_eligibility import recovery_eligibility,policy
        ok,reason=recovery_eligibility(checkout,c,policy(engine.store),suppressed=engine.store.suppressed((c or {}).get('id'),recipient_hash((c or {}).get('email'))))
        if not ok:
            from crm_checkout_identity import block_label
            engine.store.set_state(evaluation_key,{'result':block_label(reason),'reason':reason,'at':at.isoformat()})
            LOG.info('checkout_ineligible automation_id=%s reason=%s',a['id'],reason)
            continue
        threshold=0  # Admin has identified abandonment; one delay starts at verified activity.
        activity=date(state_row['activity_at'])
        if created and activity>=cutoff and activity<=at-timedelta(seconds=threshold) and not checkout.get('completedAt'):
            engine.store.q("UPDATE crm_shopify_checkouts SET admin_checkout_id=%s,status=CASE WHEN status='OPEN' THEN 'ABANDONED' ELSE status END WHERE checkout_key=%s AND status<>'RECOVERED'",(checkout['id'],key))
            from crm_automation_rule_facts import checkout_facts
            entered=enter(engine,a,c['id'],checkout['id'],'checkout:'+key,activity+timedelta(seconds=threshold),checkout_key=key,source_event_id=state_row['source_event_id'],event_facts=checkout_facts(checkout),recipient=c,checkout_source=checkout)
            engine.store.set_state(evaluation_key,{'result':'Added to flow' if entered else 'Not eligible: rules, re-entry or changed state','at':at.isoformat()})
            LOG.info('checkout_evaluated checkout_key=%s automation_id=%s enrolled=%s',key,a['id'],bool(entered))
    engine.store.set_state(state_key,{'next_at':(at+timedelta(seconds=30)).isoformat()})
    LOG.info('checkout_reconcile_complete automation_id=%s scanned=%s',a['id'],len(candidates))


def reconcile_inactive(engine,a):
    """Bounded existing Shopify customer scan; stable customer/order identity."""
    from crm_automation_capabilities import require as require_trigger
    require_trigger(engine.store,'win_back')
    key='reconcile:inactive:'+str(a['id']);state=engine.store.state(key);at=engine.clock()
    if date(state.get('next_at')) and date(state['next_at'])>at:return
    page=engine.shop.customers(state.get('cursor'),fresh=True)
    days=a['config']['published'].get('inactive_days',180)
    for c in page['nodes']:
        last=c.get('lastOrder') or {};occurred=date(last.get('createdAt'))
        if consent(c)=='SUBSCRIBED' and occurred and last.get('id') and occurred<=at-timedelta(days=days):
            enter(engine,a,c['id'],last['id'],c['id']+':'+last['id'],at,recipient=c)
    more=page['pageInfo'].get('hasNextPage')
    engine.store.set_state(key,{'cursor':page['pageInfo'].get('endCursor') if more else None,'next_at':(at+timedelta(seconds=2 if more else 300)).isoformat()})


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
    if enrollment.get('checkout_key') and receipt['status']=='FAILED' and receipt.get('error_code') in ('provider_rejected','revalidation_unavailable'):
        store.q("UPDATE crm_automation_enrollments SET retry_after=now()+interval '5 minutes',stop_reason=%s WHERE id=%s",(receipt['error_code'],enrollment['id']));return
    if receipt['status']!='ACCEPTED':engine.stop(enrollment,receipt['error_code'] or 'send_held');return
    if enrollment.get('checkout_key'):
        store.q("UPDATE crm_shopify_checkouts SET status='RECOVERY_EMAIL_SENT',updated_at=now() WHERE checkout_key=%s AND status<>'RECOVERED'",(enrollment['checkout_key'],))
    index+=1
    at=date(receipt['updated_at']) or engine.clock()
    due=at+timedelta(seconds=steps[index]['delay_seconds']) if index<len(steps) else at
    store.q("UPDATE crm_automation_enrollments SET current_step=%s,next_due_at=%s,status=%s,retry_after=NULL,stop_reason='',last_checked_at=now(),updated_at=now() WHERE id=%s AND current_step=%s",
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
    from crm_frame_banner_template import present as has_banner
    if dynamic(doc) or (has_banner(doc) and content.get('trigger')=='abandoned'):
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
