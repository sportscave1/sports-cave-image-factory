"""Event-anchored adapter for the existing enrollment and outbound send ledgers.

Activation is authorized by the durable, readiness-checked publication boundary.
"""
from copy import deepcopy
from datetime import timedelta
import json
from crm_logic import date,recipient_hash,eligibility,consent
from crm_lifecycle_policy import preview,latest_paid,qualifying,order_from_ledger

def locked(row):
    # A saved lifecycle draft is never authority for delivery.
    return bool(is_lifecycle(row) and not row.get('config',{}).get('published_version'))

def is_lifecycle(row):
    config=(row or {}).get('config',{})
    return any(config.get(key,{}).get('lifecycle_version') for key in ('published_flow','draft','published'))

def verified_plan(engine,row,customer,trigger_id=None,trigger_at=None):
    """Fresh order history before each stage; no dependence on customer.lastOrder."""
    scopes=set(engine.store.state('shopify_automation_capabilities').get('scopes',[]))
    if not {'read_customers','read_orders','read_all_orders'}.issubset(scopes):
        raise ValueError('Complete verified order history requires read_customers, read_orders and read_all_orders')
    orders=[];cursor=None;seen=set()
    for _ in range(50):
        page=engine.shop.orders(customer['id'],after=cursor,fresh=True)
        orders.extend(page['nodes'])
        if not page['pageInfo'].get('hasNextPage'):break
        cursor=page['pageInfo'].get('endCursor')
        if not cursor or cursor in seen:raise ValueError('Order history pagination is incomplete')
        seen.add(cursor)
    else:raise ValueError('Order history exceeds verification bound')
    ids=[o['id'] for o in orders]
    ledger=engine.store.q('SELECT * FROM shopify_orders WHERE shopify_order_id=ANY(%s)',(ids,)) if ids else []
    events=engine.store.q("SELECT object_id,topic,occurred_at FROM crm_webhook_events WHERE provider='shopify' AND object_id=ANY(%s) AND topic IN ('orders/paid','orders/fulfilled')",(ids,)) if ids else []
    by_id={r['shopify_order_id']:r for r in ledger};by_event={}
    for event in events:by_event.setdefault(event['object_id'],[]).append(event)
    facts=[]
    from crm_lifecycle_shopify import order_facts,operational_facts
    verified=order_facts(engine.shop,ids) if ids else {}
    for o in orders:
        cached=order_from_ledger(by_id.get(o['id'],dict(shopify_order_id=o['id'])),by_event.get(o['id'],[]))
        # Fresh Shopify payment/cancellation/fulfilment state overrides the cache.
        item={**cached,**o}
        item.update(operational_facts(verified[o['id']],o.get('displayFulfillmentStatus')=='FULFILLED'))
        if o.get('displayFulfillmentStatus')!='FULFILLED':item.update(fulfilled_at=None,delivered_at=None)
        if o['id']==trigger_id and row['trigger_type']=='post_purchase':item['paid_at']=item.get('paid_at') or date(trigger_at)
        facts.append(item)
    flow=row['config'].get('published_flow') or row['config']['draft']
    result=preview(flow,customer,facts,engine.clock(),suppressed=engine.store.suppressed(customer['id'],recipient_hash(customer.get('email'))),
                   subscribed_at=trigger_at or (customer.get('emailMarketingConsent') or {}).get('consentUpdatedAt'),
                   order_id=trigger_id if flow['trigger']=='post_purchase' else None)
    result['orders']=facts
    return result

def cancel(conn,customer_id,hashed,at,kinds,reason,*,except_order=None):
    """Keep submitted/uncertain receipts immutable; cancel only unsent follow-ups."""
    rows=conn.execute('''UPDATE crm_automation_enrollments e SET status='STOPPED',stop_reason=%s,updated_at=now()
      FROM crm_automations a WHERE a.id=e.automation_id AND a.config->'draft'->>'lifecycle_version'='1'
      AND a.trigger_type=ANY(%s) AND e.status='ACTIVE' AND e.trigger_at<=%s
      AND (e.shopify_customer_id=%s OR e.steps->0->>'recipient_hash'=%s)
      AND (%s::text IS NULL OR e.trigger_shopify_id<>%s) RETURNING e.id''',
      (reason,list(kinds),at,customer_id,hashed,except_order,except_order)).fetchall()
    if rows:
        conn.execute("UPDATE crm_marketing_sends SET status='BLOCKED',error_code=%s,lease_until=NULL,updated_at=now() WHERE enrollment_id=ANY(%s::uuid[]) AND status IN ('PENDING','CLAIMED') AND first_submitted_at IS NULL",(reason,[r['id'] for r in rows]))

def paid_exit(engine,customer,at):
    hashed=recipient_hash(customer.get('email'))
    with engine.store.db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('lifecycle:'+hashed,))
        cancel(conn,customer['id'],hashed,at,('welcome','win_back'),'paid_order')

def enter(engine,row,customer_id,trigger_id,event_id,at,source_event_id=None,*,approval_key=None):
    if locked(row) or row['status']!='ACTIVE':return None
    at=date(at)
    if not at or not date(row.get('activated_at')):return None
    if approval_key:
        from crm_lifecycle_enrollment_requests import approved
        if not approved(engine.store.state(approval_key),row,customer_id,trigger_id):return None
    elif at<date(row['activated_at']):return None
    customer=engine.shop.customer(customer_id,fresh=True)
    if customer and customer.get('id')==customer_id:
        from crm_lifecycle_audience import cache_customer
        cache_customer(engine.store,customer,engine.clock())
    if not eligibility(customer,engine.store.suppressed(customer_id,recipient_hash((customer or {}).get('email'))))[0]:return None
    plan=verified_plan(engine,row,customer,trigger_id,at)
    if not plan['eligible']:return None
    if not rules_allow(engine,row,customer,plan):return None
    hashed=recipient_hash(customer['email']);kind=row['trigger_type']
    cycle=customer_id if kind=='welcome' else plan['cycle']
    with engine.store.db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('lifecycle:'+hashed,))
        fresh=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
        if not fresh or locked(fresh) or fresh['status']!='ACTIVE' or fresh['config']['published_version']!=row['config']['published_version']:return None
        if approval_key:
            approval=conn.execute('SELECT value FROM crm_runtime_state WHERE key=%s FOR UPDATE',(approval_key,)).fetchone()
            if not approval or not approved(approval['value'],fresh,customer_id,trigger_id):return None
        prior=conn.execute('''SELECT e.* FROM crm_automation_enrollments e JOIN crm_automations a ON a.id=e.automation_id
          WHERE a.trigger_type=%s AND (e.shopify_customer_id=%s OR e.steps->0->>'recipient_hash'=%s)
          ORDER BY e.trigger_at DESC LIMIT 1''',(kind,customer_id,hashed)).fetchone()
        if prior:
            if kind=='welcome' or prior['trigger_shopify_id']==cycle:return None
            policy=row['config'].get('published_flow') or row['config']['draft']
            if kind=='win_back' and (policy['reentry_days']==0 or at<date(prior['trigger_at'])+timedelta(days=max(90,policy['reentry_days']))):return None
            if date(prior['trigger_at'])>=at:return None
        if kind=='post_purchase':cancel(conn,customer_id,hashed,at,('post_purchase',),'superseded_by_latest_order',except_order=cycle)
        steps=deepcopy(fresh['steps'])
        if not steps:return None
        steps[0]['recipient_hash']=hashed
        due=next(s['due_at'] for s in plan['stages'] if s['step_id']==steps[0]['step_id'])
        return conn.execute('''INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,
          trigger_shopify_id,trigger_key,trigger_at,steps,next_due_at,source_event_id)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT DO NOTHING RETURNING *''',
          (row['id'],customer_id,cycle,'lifecycle:'+kind+':'+str(cycle),at,json.dumps(steps),due,source_event_id)).fetchone()

def validate_send(engine,row,enrollment,customer):
    if locked(row):return {},'automation_paused'
    if enrollment['current_step']>=len(enrollment['steps']):return {},'automation_sequence_complete'
    plan=verified_plan(engine,row,customer,enrollment['trigger_shopify_id'],enrollment['trigger_at'])
    if not plan['eligible']:return {},plan['reason']
    if not rules_allow(engine,row,customer,plan):return {},'automation_rules_changed'
    if row['trigger_type']=='win_back' and plan['cycle']!=enrollment['trigger_shopify_id']:return {},'recent_purchase'
    slot=enrollment['steps'][enrollment['current_step']]
    stage=next((s for s in plan['stages'] if s['step_id']==slot['step_id']),None)
    if not stage or stage['state']=='DISABLED':return {},'automation_paused'
    if stage['state']=='HELD' or not stage['due_at'] or stage['due_at']>engine.clock():
        engine.store.q('UPDATE crm_automation_enrollments SET next_due_at=%s,stop_reason=%s WHERE id=%s',
            (stage['due_at'] if stage['due_at'] and stage['due_at']>engine.clock() else engine.clock()+timedelta(hours=1),stage['reason'],enrollment['id']))
        return {},'automation_paused'
    source=next((o for o in plan['orders'] if o['id']==enrollment['trigger_shopify_id']),{})
    last=latest_paid(plan['orders']) or {}
    return dict(_order=source,order_name=source.get('name','your order'),_lifecycle_orders=plan['orders'],
                _lifecycle_last_purchase=last.get('paid_at') or last.get('createdAt')),''

def rules_allow(engine,row,customer,plan):
    from crm_automation_capabilities import require
    from crm_automation_definition import qualifies
    from crm_automation_rule_facts import order_facts
    require(engine.store,row['trigger_type'])
    flow=row['config'].get('published_flow') or row['config']['draft']
    order=next((o for o in plan['orders'] if o['id']==plan['cycle']),{})
    facts=order_facts(engine.shop,order,flow['rules']) if row['trigger_type']=='post_purchase' else {}
    return qualifies(flow,customer,facts)

def advance(engine,enrollment):
    row=engine.store.get('automations',enrollment['automation_id'])
    if not row or locked(row) or row['status']!='ACTIVE' or enrollment['status']!='ACTIVE':return
    # Preserve slot identity; publication changes cannot replay accepted steps.
    receipts=engine.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s AND NOT test_send',(enrollment['id'],))
    if any(r['status'] in ('SUBMITTING','UNCERTAIN') for r in receipts):return
    accepted={r['step_index'] for r in receipts if r['status']=='ACCEPTED'}
    steps=deepcopy(enrollment['steps']);slots={s['step_id']:i for i,s in enumerate(steps)}
    for step in row['steps']:
        if step['step_id'] not in slots:slots[step['step_id']]=len(steps);steps.append(step)
    pending=next((s for s in row['steps'] if slots[s['step_id']] not in accepted),None)
    if not pending:
        engine.store.q("UPDATE crm_automation_enrollments SET status='COMPLETED',stop_reason='sequence_complete',updated_at=now() WHERE id=%s",(enrollment['id'],));return
    index=slots[pending['step_id']]
    engine.store.q('UPDATE crm_automation_enrollments SET steps=%s::jsonb,current_step=%s WHERE id=%s',(json.dumps(steps),index,enrollment['id']))
    enrollment={**enrollment,'steps':steps,'current_step':index}
    customer,_,reason=engine.validate(enrollment['shopify_customer_id'],enrollment)
    if reason=='automation_paused':return
    if reason:engine.stop(enrollment,reason);return
    receipt=next((r for r in receipts if r['step_index']==index),None)
    if receipt:
        if receipt['status'] in ('BLOCKED','FAILED'):engine.stop(enrollment,receipt['error_code'] or 'send_held')
        return
    engine.store.q('UPDATE crm_automation_enrollments SET next_due_at=%s,stop_reason=%s WHERE id=%s',(engine.clock(),'',enrollment['id']))
    engine.store.enqueue('automation:'+str(enrollment['id'])+':'+str(index),customer['id'],recipient_hash(customer['email']),
        {'id':pending['template_id'],'version':pending['template_version']},enrollment_id=enrollment['id'],step_index=index)

def reserve(conn,automation,journey,row,hashed):
    if locked(automation):return False
    if not conn.execute('SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS acquired',('lifecycle:'+hashed,)).fetchone()['acquired']:return False
    recent=conn.execute('''SELECT 1 FROM crm_marketing_sends s JOIN crm_automation_enrollments e ON e.id=s.enrollment_id
      JOIN crm_automations a ON a.id=e.automation_id WHERE s.recipient_hash=%s AND NOT s.test_send AND s.id<>%s
      AND a.trigger_type IN ('welcome','post_purchase','win_back')
      AND s.status IN ('ACCEPTED','SUBMITTING','UNCERTAIN') AND s.first_submitted_at>now()-interval '24 hours' LIMIT 1''',(hashed,row['id'])).fetchone()
    if recent:
        conn.execute("UPDATE crm_marketing_sends SET status='PENDING',due_at=now()+interval '1 hour',lease_until=NULL,error_code='lifecycle_frequency_cap' WHERE id=%s AND lease_token=%s",(row['id'],row['lease_token']))
        return False
    return True

def reconcile(engine,row):
    if locked(row) or row['status']!='ACTIVE' or row['trigger_type']!='win_back':return
    from crm_lifecycle_audience import listing
    key='lifecycle-inactivity:'+str(row['id']);state=engine.store.state(key);at=engine.clock()
    if date(state.get('next_at')) and date(state['next_at'])>at:return
    page=int(state.get('page',0))
    # A live draft edit must not change candidate eligibility before publication.
    published=deepcopy(row)
    published['config']['draft']=deepcopy(row['config']['published_flow'])
    records=listing(engine.store,published,sort='Longest inactivity',page=page,at=at)
    for record in records[:50]:
        # Only thresholds reached after activation; no automatic historical replay.
        due=date(record['last_paid_at'])+timedelta(days=row['config']['published_flow'].get('inactive_days',90))
        if due<date(row['activated_at']):continue
        engine.hold_lease();engine.delivery_checkpoint()
        enter(engine,row,record['customer_id'],None,record['customer_id'],due)
    engine.store.set_state(key,{'page':page+1 if len(records)>50 else 0,'next_at':(at+timedelta(minutes=5)).isoformat()})
