"""Read-only recipient adapter for flows without a lifecycle audience source.

Show recorded enrollments only. Never infer historical eligibility or enrollment
from orders, including fulfilled orders.
"""
SORTS={'Newest':'j.created_at DESC','Oldest':'j.created_at ASC','Sequence stage':'j.current_step DESC'}
FILTERS=('All','Active','Completed','Stopped')


def listing(store,row,*,search='',filter_by='All',sort='Newest',start=None,end=None,page=0):
    if sort not in SORTS or filter_by not in FILTERS:raise ValueError('Invalid recipient filter')
    if type(page) is not int or not 0<=page<=20000:raise ValueError('Invalid page')
    guards=['j.automation_id=%s'];args=[row['id']]
    if filter_by!='All':guards.append('j.status=%s');args.append(filter_by.upper())
    if search.strip():
        guards.append("(COALESCE(c.name,'') ILIKE %s OR COALESCE(c.email,'') ILIKE %s OR j.shopify_customer_id ILIKE %s OR j.trigger_shopify_id ILIKE %s)")
        needle='%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')[:200]+'%'
        args.extend([needle]*4)
    if start:guards.append('j.created_at>=%s');args.append(start)
    if end:guards.append('j.created_at<%s');args.append(end)
    args.append(page*50)
    return store.q('''WITH picked AS MATERIALIZED (
      SELECT j.id::text AS key,j.id AS enrollment_id,j.shopify_customer_id AS customer_id,
        COALESCE(c.name,j.shopify_customer_id) AS name,COALESCE(c.email,'') AS email,
        COALESCE(c.consent,'UNVERIFIED') AS consent,c.verified_at,j.created_at AS audience_at,
        j.trigger_shopify_id AS reference,j.status AS flow_state,j.current_step,j.current_step+1 AS stage,
        j.next_due_at,j.steps,j.stop_reason,
        EXISTS(SELECT 1 FROM crm_suppressions x WHERE x.shopify_customer_id=j.shopify_customer_id OR x.recipient_hash=c.recipient_hash) AS suppressed
      FROM crm_automation_enrollments j LEFT JOIN crm_lifecycle_customers c ON c.customer_id=j.shopify_customer_id
      WHERE '''+' AND '.join(guards)+' ORDER BY '+SORTS[sort]+''',j.id LIMIT 51 OFFSET %s)
      SELECT p.*,COALESCE(receipts.sends,'[]'::jsonb) AS sends FROM picked p
      LEFT JOIN LATERAL(SELECT jsonb_agg(jsonb_build_object('enrollment_id',s.enrollment_id,'step',s.step_index,
        'status',s.status,'provider_id',s.provider_email_id,'submitted_at',s.first_submitted_at,
        'due_at',s.due_at,'error',s.error_code) ORDER BY s.step_index) AS sends
        FROM crm_marketing_sends s WHERE s.enrollment_id=p.enrollment_id AND NOT s.test_send) receipts ON true
      ORDER BY '''+SORTS[sort].replace('j.created_at','p.audience_at').replace('j.current_step','p.current_step')+',p.key',tuple(args))
