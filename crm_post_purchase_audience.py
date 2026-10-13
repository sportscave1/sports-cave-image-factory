"""Order-ledger-first presentation; order contact details never grant consent."""
from crm_logic import now,date
from crm_lifecycle_audience import SORTS

FILTERS=('All','New','Queued','Completed','Unsubscribed','Suppressed','Pending verification','Paid','Refunded','Partially refunded','Cancelled')

# Filter/page the indexed order ledger before collecting journey receipts.
ORDER_SQL="""WITH audience AS (
 SELECT o.shopify_order_id AS key,COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id) AS customer_id,
 CASE WHEN privacy.redacted THEN 'Redacted customer' ELSE COALESCE(NULLIF(c.name,''),NULLIF(o.customer_name,''),'Customer enrichment pending') END AS name,
 CASE WHEN privacy.redacted THEN '' ELSE COALESCE(NULLIF(c.email,''),NULLIF(o.customer_email,''),o.email,'') END AS email,
 CASE WHEN privacy.redacted THEN 'REDACTED' ELSE COALESCE(c.consent,'UNVERIFIED') END AS consent,
 c.verified_at,c.source,o.created_at AS audience_at,NULL::timestamptz AS last_paid_at,o.order_name,o.financial_status,o.fulfillment_status,o.cancelled_at,
 CASE WHEN c.profile->'amountSpent'->>'amount' ~ '^[0-9]+([.][0-9]+)?$' THEN (c.profile->'amountSpent'->>'amount')::numeric END AS lifetime_value,
 c.profile->'amountSpent'->>'currencyCode' AS currency,
 (privacy.suppressed OR privacy.redacted) AS suppressed,
 j.id AS enrollment_id,j.status AS flow_state,j.stop_reason,j.current_step,j.current_step+1 AS stage,j.steps,j.next_due_at
 FROM shopify_orders o LEFT JOIN crm_lifecycle_customers c ON c.customer_id=COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)
 LEFT JOIN LATERAL(SELECT COALESCE(bool_or(x.reason='redacted'),false) AS redacted,
   COALESCE(bool_or(x.active),false) AS suppressed FROM crm_suppressions x
   WHERE x.shopify_customer_id=COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id) OR x.recipient_hash=c.recipient_hash
     OR (COALESCE(NULLIF(o.customer_email,''),o.email,'')<>'' AND
       x.recipient_hash=encode(sha256(convert_to(lower(trim(COALESCE(NULLIF(o.customer_email,''),o.email,''))),'UTF8')),'hex'))) privacy ON true
 LEFT JOIN LATERAL(SELECT id,status,stop_reason,current_step,steps,next_due_at FROM crm_automation_enrollments
   WHERE automation_id=%s AND trigger_shopify_id=o.shopify_order_id ORDER BY created_at DESC LIMIT 1) j ON true
), picked AS MATERIALIZED (SELECT * FROM audience WHERE __GUARDS__ ORDER BY __SORT__,key DESC LIMIT 51 OFFSET %s)
 SELECT p.*,(SELECT count(*) FROM shopify_orders known WHERE COALESCE(NULLIF(known.shopify_customer_id,''),known.customer_id)=p.customer_id
   AND upper(known.financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND known.cancelled_at IS NULL) AS order_count,
 COALESCE(messages.sends,'[]'::jsonb) AS sends,request.value->>'state' AS enrollment_request_state,request.value->>'result' AS enrollment_request_result
 FROM picked p LEFT JOIN LATERAL(SELECT jsonb_agg(jsonb_build_object(
   'enrollment_id',s.enrollment_id,'step',s.step_index,'step_id',p.steps->s.step_index->>'step_id',
   'status',s.status,'provider_id',s.provider_email_id,'submitted_at',s.first_submitted_at,'due_at',s.due_at,'error',s.error_code,
   'opened',EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.send_id=s.id AND e.event_type='email.opened'),
   'clicked',EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.send_id=s.id AND e.event_type='email.clicked')) ORDER BY s.step_index) AS sends
   FROM crm_marketing_sends s WHERE s.enrollment_id=p.enrollment_id AND NOT s.test_send) messages ON true
 LEFT JOIN crm_runtime_state request ON request.key='lifecycle-enroll:'||%s::text||':'||p.key
 ORDER BY __SORT__,key DESC"""


def listing(store,row,*,search='',filter_by='All',sort='Newest',start=None,end=None,page=0,at=None):
    if sort not in SORTS or filter_by not in FILTERS:raise ValueError('Invalid audience filter')
    if type(page) is not int or not 0<=page<=20000:raise ValueError('Invalid page')
    guards=[];args=[row['id']]
    if search.strip():
        guards.append('(name ILIKE %s OR email ILIKE %s OR customer_id ILIKE %s OR order_name ILIKE %s OR key ILIKE %s)')
        needle='%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')[:200]+'%'
        args.extend([needle]*5)
    if start:guards.append('audience_at>=%s');args.append(start)
    if end:guards.append('audience_at<%s');args.append(end)
    filters={'New':'enrollment_id IS NULL','Queued':"flow_state='ACTIVE'",'Completed':"flow_state='COMPLETED'",
        'Unsubscribed':"consent IN ('UNSUBSCRIBED','NOT_SUBSCRIBED')",'Suppressed':'suppressed',
        'Pending verification':"consent='UNVERIFIED'",'Paid':"upper(financial_status)='PAID' AND cancelled_at IS NULL",
        'Refunded':"upper(financial_status)='REFUNDED'",'Partially refunded':"upper(financial_status)='PARTIALLY_REFUNDED'",
        'Cancelled':'cancelled_at IS NOT NULL'}
    if filter_by in filters:guards.append(filters[filter_by])
    args.append(page*50)
    args.append(str(row['id']))
    return store.q(ORDER_SQL.replace('__GUARDS__',' AND '.join(guards) or 'true').replace('__SORT__',SORTS[sort]),tuple(args))


def selection(state,slot,keys,event):
    selected=set(state.get(slot+'-selected',[]))
    if event and event.get('sequence')!=state.get(slot+'-event'):
        state[slot+'-event']=event.get('sequence')
        selected.difference_update(keys);selected.update(k for k in event.get('selected',[]) if k in keys)
        state[slot+'-selected']=sorted(selected)
        if event.get('detail') in keys:state[slot+'-detail']=event['detail']
    return sorted(selected)


def email_cells(record,flow,at=None):
    from crm_checkout_progress import columns,progress,cell
    schema=columns(flow.get('emails',[]));at=at or now()
    row={**record,'checkout_key':record['key'],'flow_status':record.get('flow_state'),
        'automation_status':record.get('automation_status','ACTIVE'),'analytics':{'email':record.get('email'),'shopify_abandoned':True}}
    if record.get('enrollment_id'):
        values=progress(row,schema,at)
        for index,col in enumerate(schema):
            if values[index]['label']=='Suppressed' and not record['suppressed'] and record.get('stop_reason') in (
                    'order_ineligible','superseded_by_latest_order','recent_purchase'):
                values[index]=cell('Not eligible',reason=record['stop_reason'])
        return values
    reason='Pending consent verification' if record['consent']=='UNVERIFIED' else 'Marketing consent required' if record['consent']!='SUBSCRIBED' else 'Not enrolled'
    if record['suppressed']:reason='Suppressed'
    elif record.get('cancelled_at') or str(record.get('financial_status','')).upper() not in ('PAID','PARTIALLY_REFUNDED'):reason='Order not eligible for marketing'
    if record.get('enrollment_request_state')=='FAILED':reason=record.get('enrollment_request_result') or 'Not eligible'
    return [cell('Disabled' if not col['enabled'] else 'Not eligible' if reason not in ('Not enrolled','Pending consent verification') else reason,
        reason=reason) for col in schema]
