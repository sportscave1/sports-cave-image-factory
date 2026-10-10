"""Durable acceptance; only the existing worker may publish verified send work."""
import json
import logging
import os
import uuid
from crm_navigation import require
from crm_resend import Config

LOG=logging.getLogger(__name__)
MAX_ATTEMPTS=3
LEASE_SECONDS=300
FAILURE_MESSAGES={
    'catalogue_changed':'Product information changed. Refresh and review a duplicate campaign.',
    'settings_changed':'Sender or rendering settings changed. Review a duplicate with the current settings.',
    'schedule_missed':'The schedule passed during verification. Review a duplicate with a future schedule.',
    'verification_unavailable':'Verification is temporarily unavailable.',
    'preparation_attempts_exhausted':'Background verification could not complete after its bounded attempts.',
    'verification_rejected':'Final verification rejected this campaign. Correct and review a duplicate.'}


def failure_message(code):
    return FAILURE_MESSAGES.get(code,'Final verification requires attention.')


def receipt(row):
    return {'id':str(row['campaign_id']),'operation_id':str(row['operation_id']),
            'status':row.get('delivery_status') or ('FAILED' if row['status']=='FAILED' else 'PREPARING'),
            'recipients':row['reviewed_count'],'accepted_at':row['accepted_at'],
            'error_code':row['error_code'],'already_started':True}


def lookup(store,user,identity):
    require(user,'crm_campaigns_manage')
    row=store.q('''SELECT p.*,c.status AS delivery_status FROM crm_campaign_preparation p
      LEFT JOIN crm_campaigns c ON c.id=p.campaign_id WHERE p.campaign_id=%s''',(str(uuid.UUID(str(identity))),),True)
    return receipt(row) if row else None


def accept(store,user,editor,operation_id,*,snapshot_id,confirmed=False,env=None):
    require(user,'crm_campaigns_manage')
    if confirmed is not True:raise ValueError('Explicit send confirmation is required.')
    identity=str(uuid.UUID(str(editor['id'])));operation=str(uuid.UUID(str(operation_id)))
    with store.db() as conn:
        draft=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        prior=conn.execute('''SELECT p.*,c.status AS delivery_status FROM crm_campaign_preparation p
          LEFT JOIN crm_campaigns c ON c.id=p.campaign_id WHERE p.campaign_id=%s''',(identity,)).fetchone()
        if prior:
            if str(prior['snapshot_id'])!=str(snapshot_id) or prior['campaign_version']!=editor['version']:
                raise ValueError('This campaign already has an accepted operation. Open its status; do not send again.')
            return receipt(prior)
        existing=conn.execute('SELECT status FROM crm_campaigns WHERE id=%s',(identity,)).fetchone()
        if existing:return {'id':identity,'status':existing['status'],'already_started':True}
        Config(os.environ if env is None else env).require_send()
        if not draft or draft['archived_at'] or draft['version']!=editor['version'] or draft['document']!=editor['document']:
            raise ValueError('Campaign changed. Save and review again.')
        reviewed=conn.execute('''SELECT campaign_version,counts,document->'send_timing' AS timing,
          jsonb_array_length(recipients) AS recipients,created_at>clock_timestamp()-interval '5 minutes' AS fresh
          FROM crm_campaign_snapshots WHERE id=%s AND campaign_id=%s''',(snapshot_id,identity)).fetchone()
        if not reviewed or reviewed['campaign_version']!=draft['version'] or not reviewed['fresh'] or not reviewed['recipients'] or not reviewed['counts'].get('complete'):
            raise ValueError('Review expired or changed. Review the current campaign again.')
        # Capture permission evidence, not credentials or the whole account profile.
        import os_accounts
        actor={'id':str(user.get('id','')),'role':user.get('role'),'active':True,
               'page_permissions':sorted(os_accounts.permission_keys(user))}
        row=conn.execute('''INSERT INTO crm_campaign_preparation(campaign_id,operation_id,snapshot_id,
          campaign_version,actor,reviewed_count,timing) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb) RETURNING *''',
          (identity,operation,snapshot_id,draft['version'],json.dumps(actor),reviewed['recipients'],json.dumps(reviewed['timing'] or {'mode':'now'}))).fetchone()
        store._history(conn,draft,'campaign_send_accepted',actor['id'],draft)
    return {**receipt(row),'already_started':False}


def claim(store):
    token=str(uuid.uuid4())
    with store.db() as conn:
        # A final crashed attempt is terminal; a lost post-commit ack is READY
        # because publication and its preparation receipt share one transaction.
        conn.execute('''UPDATE crm_campaign_preparation SET status='FAILED',error_code='preparation_attempts_exhausted',
          lease_token=NULL,lease_until=NULL,updated_at=now() WHERE status='PREPARING' AND attempts>=%s
          AND (lease_until IS NULL OR lease_until<clock_timestamp())''',(MAX_ATTEMPTS,))
        return conn.execute('''UPDATE crm_campaign_preparation p SET lease_token=%s,
          lease_until=clock_timestamp()+interval '5 minutes',attempts=attempts+1,updated_at=now(),error_code=''
          WHERE campaign_id=(SELECT campaign_id FROM crm_campaign_preparation WHERE status='PREPARING'
            AND attempts<%s AND retry_at<=clock_timestamp() AND (lease_until IS NULL OR lease_until<clock_timestamp())
            ORDER BY accepted_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING p.*''',(token,MAX_ATTEMPTS)).fetchone()


def fence(conn,identity,token):
    row=conn.execute('SELECT * FROM crm_campaign_preparation WHERE campaign_id=%s FOR UPDATE',(identity,)).fetchone()
    if row and (not token or row['status']!='PREPARING' or str(row['lease_token'])!=str(token)
                or not conn.execute('SELECT %s::timestamptz>clock_timestamp() AS valid',(row['lease_until'],)).fetchone()['valid']):
        raise ValueError('Preparation lease changed. No recipient work was released.')
    return row


def tick(store,shop,*,env=None):
    # Never claim/release a campaign when transport is unavailable.
    try:Config(os.environ if env is None else env).require_send()
    except Exception:return False
    job=claim(store)
    if not job:return False
    try:
        from crm_campaign_send import queue_campaign
        editor=store.draft(job['campaign_id'])
        queue_campaign(shop,store,job['actor'],editor,str(job['operation_id']),env=env,
                       snapshot_id=str(job['snapshot_id']),preparation_token=str(job['lease_token']))
    except Exception as exc:
        # Validation failures need a new reviewed duplicate, never automatic release.
        permanent=isinstance(exc,(ValueError,PermissionError))
        code='verification_rejected' if permanent else 'verification_unavailable'
        if permanent:
            for prefix,label in [('Catalogue facts changed','catalogue_changed'),('Sender or rendering settings changed','settings_changed'),('Schedule missed','schedule_missed')]:
                if str(exc).startswith(prefix):code=label;break
        store.q('''UPDATE crm_campaign_preparation SET status=CASE WHEN %s OR attempts>=%s THEN 'FAILED' ELSE 'PREPARING' END,
          error_code=%s,retry_at=clock_timestamp()+interval '30 seconds',lease_token=NULL,lease_until=NULL,updated_at=now()
          WHERE campaign_id=%s AND status='PREPARING' AND lease_token=%s''',
          (permanent,MAX_ATTEMPTS,code,job['campaign_id'],job['lease_token']))
        LOG.warning('campaign_preparation_failed error_class=%s',type(exc).__name__)
    return True
