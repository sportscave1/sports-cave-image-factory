"""Frozen, server-only publication jobs consumed by the existing CRM worker.

Publication never enrolls a customer or submits an email. Delivery remains with
the existing trigger/runtime. Expensive validation happens outside the row lock.
"""
from copy import deepcopy
import json
import logging
import re
import uuid
from time import perf_counter
from crm_logic import now,date
from crm_navigation import require
from crm_automation_definition import validate, native, status, production_document
from crm_store import StoreUnavailable
from crm_automation_publish_state import has_changes

LOG=logging.getLogger(__name__)
MAX_ATTEMPTS=3
PUBLICATION_SECONDS=1200


def run(store,owner,stop,*,interval=1.0):
    """One bounded consumer in the existing worker, using the same durable claims.

    Maintenance/Shopify calls cannot delay queue pickup. No UI-owned executor,
    new service, independent scheduler, or delivery work is introduced. The
    owner/attempt fence still protects against crashes and overlapping workers.
    """
    connection=None
    if store.connect is None:
        from supabase_backend import connect
        from crm_publication_connection import Connection
        from crm_automation_store import AutomationStore
        connection=Connection(connect);store=AutomationStore(connection)
    try:
        while not stop.is_set():
            try:
                worked=tick(store,owner)
            except Exception as exc:
                LOG.warning('automation_publication_poll_failed error_class=%s',type(exc).__name__)
                stop.wait(5)
                continue
            # Avoid a hot loop, but drain queued work without another maintenance pass.
            stop.wait(.05 if worked else interval)
    finally:
        if connection:connection.close()


def progress(store,identity):
    """Small persisted job read; never infer success from elapsed time."""
    return store.q("""SELECT state,requested_at,started_at,available_at,attempts
        FROM crm_automation_publish_jobs WHERE automation_id=%s
        AND state IN ('QUEUED','RUNNING') ORDER BY requested_at DESC LIMIT 1""",(identity,),True)


def progress_text(job):
    if not job:return 'Reconciling publication status…'
    age=max(0,int((now()-date(job['requested_at'])).total_seconds()))
    operation='Validating and storing publication' if job['state']=='RUNNING' else 'Waiting for publication worker'
    if job['state']=='QUEUED' and job.get('attempts',0):operation='Storage unavailable · waiting for bounded retry'
    if age>=30:operation+=' · taking longer than expected; current live version retained'
    return operation+' · '+str(age)+'s'


def overdue(publication):
    requested=date(publication.get('requested_at'))
    return publication.get('state')=='PUBLISHING' and requested is not None and (now()-requested).total_seconds()>=PUBLICATION_SECONDS


def expire(store,identity):
    """Fence abandoned jobs even when the worker is offline; retain the draft/live version."""
    with store.db() as conn:
        conn.execute("SET LOCAL lock_timeout='2s'")
        jobs=conn.execute("""SELECT * FROM crm_automation_publish_jobs WHERE automation_id=%s
          AND state IN ('QUEUED','RUNNING') AND requested_at<=now()-interval '20 minutes'
          FOR UPDATE SKIP LOCKED""",(identity,)).fetchall()
        for job in jobs:fail(conn,job,'Publication timed out. Check the CRM worker and retry publishing.')


def approved(flow):
    result=deepcopy(flow)
    for step in result['emails']:step['document']['copy_reviewed']=True
    return result


def preflight(row,revision):
    if not row or not native(row) or row['config'].get('deleted_at') or status(row)=='ARCHIVED':
        raise ValueError('Automation is not publishable.')
    if row['config']['revision']!=revision:raise ValueError('A newer draft exists. Save your changes before publishing.')
    from crm_automation_timing import single_delay
    flow=validate(single_delay(row['config']['draft']))
    if not any(s.get('enabled',True) for s in flow['emails']):raise ValueError('Enable at least one email before publishing.')
    for step in flow['emails']:
        if not step.get('enabled',True):continue
        subject=step['document']['content']['subject'].strip()
        if not subject:raise ValueError('Add a subject before publishing.')
        if re.match(r'\s*(re|fwd?)\s*:',subject,re.I):raise ValueError('Use a truthful subject without RE: or FWD:.')
    return flow


def request(store,user,identity,revision):
    require(user,'crm_automations_manage')
    with store.db() as conn:
        conn.execute("SET LOCAL lock_timeout='2s'")
        row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        flow=preflight(row,revision)
        active=conn.execute("SELECT * FROM crm_automation_publish_jobs WHERE automation_id=%s AND state IN ('QUEUED','RUNNING')",(identity,)).fetchone()
        if active:
            if active['revision']!=revision:raise ValueError('A saved revision is already publishing. Wait before publishing the next revision.')
            return active
        previous=conn.execute("SELECT * FROM crm_automation_publish_jobs WHERE automation_id=%s AND revision=%s AND state='SUCCEEDED' ORDER BY requested_at DESC LIMIT 1",(identity,revision)).fetchone()
        if not has_changes(store,row,flow,conn):
            return {**(previous or {'id':None,'automation_id':row['id'],'revision':revision,'publication_version':row['config']['published_version'],'state':'SUCCEEDED'}),'unchanged':True}
        if previous:return previous
        config=deepcopy(row['config']);job_id=str(uuid.uuid4());version=config['published_version']+1
        snapshot={'flow':approved(flow),'name':row['name'],'base_status':row['status'],
                  'base_version':config['published_version']}
        job=conn.execute("""INSERT INTO crm_automation_publish_jobs(id,automation_id,revision,publication_version,snapshot,requested_by)
          VALUES(%s,%s,%s,%s,%s::jsonb,%s) RETURNING *""",
          (job_id,identity,revision,version,json.dumps(snapshot),str(user.get('id') or 'operator'))).fetchone()
        config['publication']={'job_id':job_id,'revision':revision,'version':version,'state':'PUBLISHING','requested_at':now().isoformat()}
        conn.execute('UPDATE crm_automations SET config=%s::jsonb,updated_at=now() WHERE id=%s',(json.dumps(config),identity))
        return job


def prepare(store,identity,flow,version,name,env=None):
    from crm_checkout_migration import migrate_flow
    from crm_campaign_sections import with_email_defaults
    from crm_campaign_send import production_checks,validate_tracking
    from crm_email_size import validate_rendered_email
    from crm_abandoned_checkout import publication_document
    from crm_automation_capabilities import require as require_trigger
    flow=validate(migrate_flow(flow));cfg=store.render_settings(env)
    require_trigger(store,flow['trigger']);bundles=[];steps=[]
    for index,step in enumerate(flow['emails']):
        if not step.get('enabled',True):continue
        doc=with_email_defaults(production_document(step['document']),cfg)
        validation_doc=publication_document(doc,flow['trigger'])
        template_id=str(uuid.uuid5(uuid.UUID(str(identity)),step['step_id']))
        email_size=validate_rendered_email(validate_tracking(validation_doc,cfg,template_id))
        failures=[k for k,v in production_checks(validation_doc,cfg,env,reviewed_audience=True,email_size=email_size).items() if not v]
        if failures:raise ValueError('Email '+str(index+1)+' blocked: '+'; '.join(failures))
        content={'format':'automation_delivery_v1','document':doc,'render_settings':cfg,
                 'automation_id':str(identity),'automation_version':version,'step_id':step['step_id'],
                 'trigger':flow['trigger'],'rules':flow['rules']}
        if flow.get('review_request'):
            from reviews_submission import MARKER
            if MARKER not in json.dumps(doc):raise ValueError('Add the review request link before publishing.')
            content['review_request']=deepcopy(flow['review_request'])
        bundles.append((template_id,name+' · Email '+str(index+1),content))
        steps.append({'type':'send','step_id':step['step_id'],'delay_seconds':step['delay_seconds'],
                      'template_id':template_id,'template_version':version,'automation_version':version,
                      'trigger':flow['trigger'],'rules':flow['rules'],'name':step.get('name') or 'Email '+str(index+1),
                      'inactive_days':flow.get('inactive_days',180),'exit_on_purchase':flow.get('exit_on_purchase',flow['trigger'] in ('abandoned','win_back'))})
    return flow,bundles,steps


def commit(store,conn,row,flow,bundles,steps,version,publication=None):
    config=deepcopy(row['config']);identity=row['id']
    # Two statements for 1..N emails, with the same transaction and immutable
    # version constraint. No per-email network round trips or partial commits.
    payload=json.dumps([{'id':i,'name':n,'content':c} for i,n,c in bundles])
    conn.execute("""INSERT INTO crm_templates(id,template_key,name,kind,version,content)
      SELECT b.id,'automation-email:'||b.id::text,b.name,'Automation',%s,b.content
      FROM jsonb_to_recordset(%s::jsonb) AS b(id uuid,name text,content jsonb)
      ON CONFLICT(id) DO UPDATE SET version=excluded.version,
      content=excluded.content,updated_at=now()""",(version,payload))
    conn.execute("""INSERT INTO crm_template_versions(template_id,version,content)
      SELECT b.id,%s,b.content FROM jsonb_to_recordset(%s::jsonb)
      AS b(id uuid,name text,content jsonb)""",(version,payload))
    config.update(published_version=version,published={k:deepcopy(flow[k]) for k in ('trigger','rules','reentry_days')},published_at=now().isoformat())
    config['published']['timing_version']=flow.get('timing_version',1)
    config['published'].update(inactive_days=flow.get('inactive_days',180),exit_on_purchase=flow.get('exit_on_purchase',flow['trigger'] in ('abandoned','win_back')))
    config['published_flow']=deepcopy(flow)
    documents={content['step_id']:content['document'] for _,_,content in bundles}
    for step in config['published_flow']['emails']:
        if step['step_id'] in documents:step['document']=deepcopy(documents[step['step_id']])
    if flow.get('timing_version')!=2:config['published']['abandonment_seconds']=flow.get('abandonment_seconds',3600)
    target='PAUSED' if row['status']=='PAUSED' else 'ACTIVE'
    if publication:config['publication']={**publication,'state':'LIVE','completed_at':now().isoformat()}
    # Preserve the current editable draft, including edits made after acceptance.
    return conn.execute("UPDATE crm_automations SET config=%s::jsonb,steps=%s::jsonb,trigger_type=%s,status=%s,activated_at=COALESCE(activated_at,now()),updated_at=now() WHERE id=%s RETURNING *",
                        (json.dumps(config),json.dumps(steps),flow['trigger'],target,identity)).fetchone()


def publish_direct(store,user,identity,revision,env=None):
    require(user,'crm_automations_manage');row=store.flow(identity)
    flow=approved(preflight(row,revision));version=row['config']['published_version']+1
    if not has_changes(store,row,flow):return row
    prepared=prepare(store,identity,flow,version,row['name'],env)
    with store.db() as conn:
        fresh=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        preflight(fresh,revision)
        if not has_changes(store,fresh,flow,conn):return fresh
        if fresh['config'].get('publication',{}).get('state')=='PUBLISHING':raise ValueError('A publication is already in progress.')
        if fresh['config']['published_version']!=version-1:raise ValueError('A newer publication exists.')
        result=commit(store,conn,fresh,*prepared,version)
    from crm_thumbnail_cache import prewarm
    prewarm(prepared[1],version,store)
    return result


def safe_reason(exc):
    # Persist only allowlisted operator messages; never raw provider/DB errors.
    text=str(exc).lower()
    if 'discount_not_selected:' in text:return 'Select a Shopify discount for every email using discount variables, or remove those variables, then publish again.'
    if 'discount_variable_in_url:' in text:return 'Use discount variables in offer text, not links. The recovery button applies the selected code.'
    if 'discount_' in text:return 'Review the selected Shopify discount and its offer text before publishing. The previous live version remains active.'
    if 'subject' in text:return 'Add a truthful subject before publishing.'
    if 'shopify' in text and 'trigger' in text:return 'Shopify trigger is currently unavailable. Retry after readiness is restored.'
    if 'tracking' in text:return 'Email tracking validation failed. Review the email before publishing.'
    if '95' in text or 'size' in text:return 'Email exceeds the size limit. Reduce its content before publishing.'
    if any(k in text for k in ('html','checkout','styled','selector','css','unresolved')):return 'Email HTML or checkout styling needs attention before this flow can go live.'
    if 'unsubscribe' in text or 'footer' in text:return 'Add the required unsubscribe footer before publishing.'
    if 'newer' in text or 'changed' in text:return 'Automation changed during publication. Review the saved draft and retry.'
    if isinstance(exc,StoreUnavailable):return 'Publication storage is temporarily unavailable. Retry publishing.'
    return 'Publication validation failed. Review the email content and delivery settings before retrying.'


def claim(store,owner):
    with store.db() as conn:
        job=conn.execute("""SELECT * FROM crm_automation_publish_jobs WHERE
          (state='QUEUED' AND available_at<=now()) OR (state='RUNNING' AND lease_until<now())
          ORDER BY requested_at FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
        if not job:return None
        if (now()-date(job['requested_at'])).total_seconds()>=PUBLICATION_SECONDS:
            fail(conn,job,'Publication timed out. Check the CRM worker and retry publishing.');return None
        if job['attempts']>=MAX_ATTEMPTS:
            fail(conn,job,'Publication was interrupted repeatedly. Retry publishing.');return None
        return conn.execute("""UPDATE crm_automation_publish_jobs SET state='RUNNING',owner=%s,
          attempts=attempts+1,lease_until=now()+interval '5 minutes',started_at=COALESCE(started_at,now()) WHERE id=%s RETURNING *""",(owner,job['id'])).fetchone()


def fail(conn,job,reason):
    conn.execute("UPDATE crm_automation_publish_jobs SET state='FAILED',error=%s,completed_at=now(),lease_until=NULL WHERE id=%s",(reason,job['id']))
    row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(job['automation_id'],)).fetchone()
    if row and row['config'].get('publication',{}).get('job_id')==str(job['id']):
        config=deepcopy(row['config']);config['publication'].update(state='FAILED',error=reason,completed_at=now().isoformat())
        conn.execute('UPDATE crm_automations SET config=%s::jsonb,updated_at=now() WHERE id=%s',(json.dumps(config),row['id']))


def tick(store,owner,env=None):
    started=perf_counter()
    job=claim(store,owner)
    if not job:return False
    try:
        preparing=perf_counter()
        frozen=job['snapshot'];prepared=prepare(store,job['automation_id'],frozen['flow'],job['publication_version'],frozen['name'],env)
        prepared_at=perf_counter()
        with store.db() as conn:
            locked=conn.execute('SELECT * FROM crm_automation_publish_jobs WHERE id=%s FOR UPDATE',(job['id'],)).fetchone()
            if locked['state']!='RUNNING' or locked['owner']!=owner or locked['attempts']!=job['attempts']:return True
            if (now()-date(locked['requested_at'])).total_seconds()>=PUBLICATION_SECONDS:
                fail(conn,locked,'Publication timed out. Check the CRM worker and retry publishing.');return True
            row=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(job['automation_id'],)).fetchone()
            if not row or status(row)=='ARCHIVED' or row['config'].get('deleted_at') or row['status']!=frozen['base_status']:
                raise ValueError('Automation changed during publication.')
            if row['config']['published_version']!=frozen['base_version'] or row['config'].get('publication',{}).get('job_id')!=str(job['id']):
                raise ValueError('A newer publication exists.')
            commit(store,conn,row,*prepared,job['publication_version'],row['config']['publication'])
            conn.execute("UPDATE crm_automation_publish_jobs SET state='SUCCEEDED',completed_at=now(),lease_until=NULL,error=NULL WHERE id=%s",(job['id'],))
        from crm_thumbnail_cache import prewarm
        prewarm(prepared[1],job['publication_version'],store)
        LOG.info('automation_publication job_id=%s revision=%s state=SUCCEEDED claim_ms=%.1f validate_ms=%.1f commit_ms=%.1f',
                 job['id'],job['revision'],(preparing-started)*1000,(prepared_at-preparing)*1000,(perf_counter()-prepared_at)*1000)
    except Exception as exc:
        with store.db() as conn:
            locked=conn.execute('SELECT * FROM crm_automation_publish_jobs WHERE id=%s FOR UPDATE',(job['id'],)).fetchone()
            if locked['state']!='RUNNING' or locked['owner']!=owner or locked['attempts']!=job['attempts']:return True
            retry=isinstance(exc,StoreUnavailable) and job['attempts']<MAX_ATTEMPTS
            if retry:
                conn.execute("UPDATE crm_automation_publish_jobs SET state='QUEUED',available_at=now()+interval '30 seconds',lease_until=NULL WHERE id=%s",(job['id'],))
            else:fail(conn,job,safe_reason(exc))
        LOG.warning('automation_publication job_id=%s revision=%s state=%s error_class=%s',job['id'],job['revision'],'QUEUED' if retry else 'FAILED',type(exc).__name__)
    return True
