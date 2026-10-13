"""Audited manual paid-order requests in the existing CRM worker/state queue."""
import json,uuid
from datetime import timedelta
from crm_logic import now,date

PREFIX='lifecycle-enroll:'


def approved(value,row,customer_id,order_id):
    requested=date(value.get('requested_at'))
    return bool(row['trigger_type']=='post_purchase' and value.get('state')=='CHECKING' and value.get('confirmed') is True
        and value.get('actor') and value.get('automation_id')==str(row['id']) and value.get('customer_id')==customer_id
        and value.get('order_id')==order_id and value.get('published_version')==row['config'].get('published_version')
        and requested and now()-timedelta(hours=1)<=requested<=now()+timedelta(minutes=1))


def request(store,user,identity,orders,*,confirmed=False):
    from crm_navigation import require
    import os_accounts
    require(user,'crm_automations_manage')
    if not os_accounts.is_admin(user):raise PermissionError('Administrator confirmation required')
    if confirmed is not True:raise ValueError('Confirm the selected orders before adding to the flow')
    orders=sorted(set(orders))
    if not orders or len(orders)>100:raise ValueError('Select 1–100 orders')
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        if not row or row['trigger_type']!='post_purchase' or row['status']!='ACTIVE' or not row['config'].get('published_version'):
            raise ValueError('Publish and activate this flow before adding orders; Draft selection never sends')
        from crm_automation_readiness import require_ready
        require_ready(store,row,conn=conn,published=True)
        records=conn.execute('SELECT shopify_order_id,COALESCE(NULLIF(shopify_customer_id,\'\'),customer_id) AS customer_id FROM shopify_orders WHERE shopify_order_id=ANY(%s)',(orders,)).fetchall()
        if len(records)!=len(orders):raise ValueError('Selected orders changed; refresh the table')
        payload=[]
        for order in records:
            if not order['customer_id']:raise ValueError('Selected order has no Shopify customer; cannot verify marketing eligibility')
            key=PREFIX+str(identity)+':'+order['shopify_order_id']
            value=dict(automation_id=str(identity),order_id=order['shopify_order_id'],customer_id=order['customer_id'],
                published_version=row['config']['published_version'],actor=str(user.get('id') or 'administrator'),
                confirmed=True,requested_at=now().isoformat(),state='QUEUED',result='Awaiting fresh eligibility verification')
            payload.append({'key':key,'value':value})
        results=conn.execute('''INSERT INTO crm_runtime_state AS prior(key,value)
          SELECT key,value FROM jsonb_to_recordset(%s::jsonb) AS input(key text,value jsonb)
          ON CONFLICT(key) DO UPDATE SET
            value=CASE WHEN prior.value->>'state'='FAILED' THEN excluded.value||jsonb_build_object('previous',prior.value) ELSE prior.value END,
            updated_at=CASE WHEN prior.value->>'state'='FAILED' THEN now() ELSE prior.updated_at END RETURNING value''',(json.dumps(payload),)).fetchall()
        return [r['value'] for r in results]


def tick(store,shop,at=None):
    at=at or now();owner=str(uuid.uuid4())
    with store.db() as conn:
        job=conn.execute('''SELECT key,value FROM crm_runtime_state WHERE starts_with(key,%s)
          AND (value->>'state'='QUEUED' OR (value->>'state'='CHECKING' AND (value->>'lease_until')::timestamptz<%s))
          ORDER BY updated_at LIMIT 1 FOR UPDATE SKIP LOCKED''',(PREFIX,at)).fetchone()
        if not job:return False
        value=job['value'];value.update(state='CHECKING',owner=owner,lease_until=(at+timedelta(minutes=5)).isoformat())
        conn.execute('UPDATE crm_runtime_state SET value=%s::jsonb,updated_at=now() WHERE key=%s',(json.dumps(value),job['key']))
    try:
        from crm_automation_store import AutomationStore
        from crm_engine import Engine
        from crm_automation_readiness import require_ready
        from crm_lifecycle_runtime import enter
        repository=AutomationStore(store.connect);row=repository.flow(value['automation_id'])
        if not approved(value,row,value['customer_id'],value['order_id']):raise ValueError('Flow changed or confirmation expired; confirm again')
        if row['status']!='ACTIVE':raise ValueError('Flow is paused or unpublished')
        require_ready(repository,row,published=True)
        event=repository.q("SELECT event_id,occurred_at FROM crm_webhook_events WHERE provider='shopify' AND topic='orders/paid' AND object_id=%s AND related_customer_id=%s ORDER BY occurred_at LIMIT 1",(value['order_id'],value['customer_id']),True)
        if not event:raise ValueError('Verified payment event unavailable; no order enrolled')
        prior=repository.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s AND trigger_shopify_id=%s',(row['id'],value['order_id']),True)
        if prior:result='Already enrolled';journey=prior
        else:
            journey=enter(Engine(store,shop),row,value['customer_id'],value['order_id'],value['order_id'],event['occurred_at'],
                source_event_id=event['event_id'],approval_key=job['key'])
            if not journey:raise ValueError('Not eligible: verify consent, suppression, order state and existing purchase/re-entry policy')
            result='Enrolled; configured payment delay preserved'
        value.update(state='ENROLLED',result=result,enrollment_id=str(journey['id']),completed_at=now().isoformat())
    except Exception as exc:
        # Only local allowlisted messages leave the worker; no provider bodies.
        message=str(exc) if isinstance(exc,(ValueError,PermissionError)) and str(exc).startswith(('Flow ','Not eligible','Verified payment','Automation publication')) else 'Verification unavailable; no confirmed enrollment. Refresh and confirm a retry.'
        value.update(state='FAILED',result=message,completed_at=now().isoformat())
    with store.db() as conn:
        conn.execute("UPDATE crm_runtime_state SET value=%s::jsonb,updated_at=now() WHERE key=%s AND value->>'owner'=%s",(json.dumps(value),job['key'],owner))
    return True
