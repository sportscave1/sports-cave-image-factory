"""Durable internal sequence tests. Never enter the customer delivery ledger.

Uncertain submissions are held for audit, never blindly retried beyond a
provider idempotency window. Only acceptance advances the next timing anchor.
"""
from copy import deepcopy
from datetime import timedelta
import json
import uuid
from crm_logic import now,email
from crm_test_recipient import authorize_internal


def actor(user):
    value=str(user.get('id') or user.get('username') or '')
    if not value:raise PermissionError('An authenticated administrator is required.')
    return value


def approved(recipient):
    import os,re
    addresses={email(os.getenv('SPORTS_CAVE_ADMIN_EMAIL',''))}
    addresses.update(email(v.strip()) for v in re.split(r'[,;\n]',os.getenv('CRM_INTERNAL_TEST_RECIPIENTS','')))
    return email(recipient) in addresses-{''}


def prepare(flow,cfg):
    from crm_automation_definition import validate
    from crm_automation_timing import single_delay
    from crm_thumbnail_render import preview_document
    from crm_campaign_content import render_campaign
    from crm_email_size import validate_rendered_email
    validate(flow)
    effective=single_delay(flow)
    enabled=[(i,s) for i,s in enumerate(effective['emails']) if s.get('enabled',True)]
    if not enabled:raise ValueError('Enable at least one email before testing.')
    if len(enabled)>32:raise ValueError('Sequence tests support at most 32 enabled emails.')
    messages=[]
    for i,stage in enabled:
        # Shared renderer uses selected artwork and existing offer information.
        # Sample checkout has no recovery URL and requires no Shopify lookup.
        doc=preview_document(deepcopy(stage['document']))
        if not doc['content'].get('subject'):raise ValueError('Every enabled email needs a subject.')
        message=render_campaign(doc,cfg,production=False)
        message['subject']='[FLOW TEST] '+doc['content']['subject']
        message['unsubscribe_url']=cfg.get('test_unsubscribe_url','')
        if not message['unsubscribe_url'].startswith('https://'):
            raise ValueError('Configure the isolated test unsubscribe endpoint before testing.')
        marker='<p style="font:12px Segoe UI">TEST sequence · sample context · no customer checkout</p>'
        message['html']=message['html'].replace('</body>',marker+'</body>')
        message['text']='TEST sequence · sample context · no customer checkout\n'+message['text']
        validate_rendered_email(message)
        messages.append((i,stage['delay_seconds'],message))
    return messages


def start(store,user,identity,recipient,operation,revision,*,clock=now):
    authorize_internal(user,recipient)
    if not approved(recipient):raise PermissionError('This mailbox must be configured in CRM_INTERNAL_TEST_RECIPIENTS or SPORTS_CAVE_ADMIN_EMAIL for background testing.')
    from crm_navigation import require
    require(user,'crm_automations_manage')
    from crm_resend import Config
    Config().require_send(True)
    owner=actor(user);operation=str(uuid.UUID(str(operation)));at=clock()
    # Per-admin advisory lock serializes rate limits and idempotency across flows.
    with store.db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('flow-test:'+owner,))
        existing=conn.execute('SELECT * FROM crm_flow_tests WHERE actor=%s AND operation=%s',(owner,operation)).fetchone()
        if existing:
            if str(existing['automation_id'])!=str(identity) or existing['recipient']!=email(recipient):
                raise ValueError('This test operation already belongs to another saved sequence or mailbox.')
            return existing
        row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR SHARE',(identity,)).fetchone()
        if not row or row['config']['revision']!=revision:
            raise ValueError('The saved flow changed. Reopen Test and try again.')
        if row['config'].get('archived_at'):raise ValueError('Archived flows cannot be tested.')
        count=conn.execute('SELECT count(*) AS n FROM crm_flow_tests WHERE actor=%s AND created_at>%s',
                           (owner,at-timedelta(hours=24))).fetchone()['n']
        if count>=5:raise ValueError('Test limit reached: five sequences per administrator per day.')
        running=conn.execute("SELECT count(*) AS n FROM crm_flow_tests t WHERE actor=%s AND cancelled_at IS NULL AND EXISTS(SELECT 1 FROM crm_flow_test_stages s WHERE s.test_id=t.id AND s.status IN ('WAITING','SCHEDULED','SUBMITTED'))",(owner,)).fetchone()['n']
        if running>=2:raise ValueError('Cancel or finish a pending test before starting another.')
        snapshot=deepcopy(row['config']['draft']);cfg=deepcopy(store.render_settings())
        messages=prepare(snapshot,cfg)
        source='TEST — LIVE' if snapshot==row['config'].get('published_flow') else 'TEST — Draft'
        tid=str(uuid.uuid4())
        result=conn.execute('INSERT INTO crm_flow_tests(id,automation_id,actor,recipient,operation,snapshot,source,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
            (tid,identity,owner,email(recipient),operation,json.dumps({'flow':snapshot,'settings':cfg,'revision':revision}),source,at)).fetchone()
        from crm_automation_timing import scheduled_at
        for n,(position,delay,message) in enumerate(messages):
            conn.execute('INSERT INTO crm_flow_test_stages(id,test_id,position,delay_seconds,message,status,due_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (str(uuid.uuid4()),tid,position,delay,json.dumps(message),'SCHEDULED' if n==0 else 'WAITING',scheduled_at(at,delay) if n==0 else None))
        return result


def latest(store,user,identity):
    import os_accounts
    if not os_accounts.is_admin(user):raise PermissionError('Administrator required.')
    row=store.q('SELECT * FROM crm_flow_tests WHERE actor=%s AND automation_id=%s ORDER BY created_at DESC LIMIT 1',(actor(user),identity),True)
    if row:row['stages']=store.q('SELECT position,status,due_at,provider_id,error FROM crm_flow_test_stages WHERE test_id=%s ORDER BY position LIMIT 32',(row['id'],))
    return row


def cancel(store,user,identity,*,clock=now):
    import os_accounts
    if not os_accounts.is_admin(user):raise PermissionError('Administrator required.')
    with store.db() as conn:
        row=conn.execute('SELECT * FROM crm_flow_tests WHERE id=%s AND actor=%s FOR UPDATE',(identity,actor(user))).fetchone()
        if not row:raise PermissionError('Test does not belong to this session administrator.')
        conn.execute('UPDATE crm_flow_tests SET cancelled_at=%s WHERE id=%s',(clock(),identity))
        conn.execute("UPDATE crm_flow_test_stages SET status='CANCELLED' WHERE test_id=%s AND status IN ('WAITING','SCHEDULED')",(identity,))


def tick(store,*,clock=now,transport=None):
    """At most one due delivery per worker cycle. No browser scheduling authority."""
    from crm_resend import Config,Resend
    cfg=Config()
    if not cfg.tests_enabled:return False
    at=clock()
    # Lock parent first, same order as cancellation. SKIP LOCKED bounds contention.
    with store.db() as conn:
        test=conn.execute("SELECT t.* FROM crm_flow_tests t WHERE t.cancelled_at IS NULL AND EXISTS(SELECT 1 FROM crm_flow_test_stages s WHERE s.test_id=t.id AND s.status='SCHEDULED' AND s.due_at<=%s) ORDER BY t.created_at FOR UPDATE SKIP LOCKED LIMIT 1",(at,)).fetchone()
        if not test:return False
        stage=conn.execute("SELECT * FROM crm_flow_test_stages WHERE test_id=%s AND status='SCHEDULED' AND due_at<=%s ORDER BY position FOR UPDATE LIMIT 1",(test['id'],at)).fetchone()
        cfg.require_send(True)
        # Revalidate deployment-managed recipient eligibility before each send.
        if not approved(test['recipient']):
            conn.execute("UPDATE crm_flow_test_stages SET status='FAILED',error='recipient_authorization_revoked' WHERE id=%s",(stage['id'],))
            conn.execute("UPDATE crm_flow_test_stages SET status='CANCELLED' WHERE test_id=%s AND status='WAITING'",(test['id'],))
            return True
        conn.execute("UPDATE crm_flow_test_stages SET status='SUBMITTED',submitted_at=%s WHERE id=%s",(at,stage['id']))
    # Persist submission before provider contact. A crash leaves an auditable
    # SUBMITTED hold; never resubmit an uncertain stage after a restart.
    try:
        provider=(transport or Resend(cfg)).send(test['recipient'],stage['message'],'flow-test:'+str(stage['id']),True)
        if not provider:raise ValueError('Provider acceptance is uncertain.')
    except Exception as exc:
        from email_service import EmailDeliveryError
        rejected=isinstance(exc,EmailDeliveryError) and exc.status_code in (400,401,403,404,422)
        store.q("UPDATE crm_flow_test_stages SET status=%s,error=%s WHERE id=%s",('FAILED' if rejected else 'SUBMITTED','provider_rejected' if rejected else 'provider_acceptance_uncertain',stage['id']))
        return True
    with store.db() as conn:
        parent=conn.execute('SELECT * FROM crm_flow_tests WHERE id=%s FOR UPDATE',(test['id'],)).fetchone()
        accepted=clock()
        conn.execute("UPDATE crm_flow_test_stages SET status='ACCEPTED',accepted_at=%s,provider_id=%s,error=NULL WHERE id=%s",(accepted,str(provider),stage['id']))
        if not parent['cancelled_at']:
            following=conn.execute("SELECT * FROM crm_flow_test_stages WHERE test_id=%s AND status='WAITING' ORDER BY position LIMIT 1",(test['id'],)).fetchone()
            if following:
                from crm_automation_timing import scheduled_at
                conn.execute("UPDATE crm_flow_test_stages SET status='SCHEDULED',due_at=%s WHERE id=%s",(scheduled_at(accepted,following['delay_seconds']),following['id']))
    return True
