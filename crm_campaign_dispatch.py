"""Native frozen campaign dispatch. Existing worker lease owns all DB mutations.

Batch manifests live in existing server-only runtime storage. Receipts/progress
remain in crm_marketing_sends; delivery remains webhook-owned. No Shopify I/O.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html import escape
import hashlib
import json
import logging
import time
from types import SimpleNamespace
from crm_logic import date,recipient_hash
from crm_resend_batch import BATCH_SIZE,BatchError,BatchTransport
from crm_resend_marketing import single_email

LOG=logging.getLogger(__name__)
MAX_ATTEMPTS=5
RETRY_WINDOW=timedelta(hours=23)  # Provider keys expire after 24 hours.
MAX_BATCHES=12


def payload(common,recipient,config):
    from crm_email_size import REPRESENTATIVE_UNSUBSCRIBE,LIMIT_BYTES
    address=recipient.get('address','');url=recipient.get('unsubscribe_url','')
    from crm_tracking import public_https
    if not single_email(address) or not public_https(url) or len(url)>len(REPRESENTATIVE_UNSUBSCRIBE):raise ValueError('Invalid frozen recipient.')
    message={**common,'html':common['html'].replace(escape(REPRESENTATIVE_UNSUBSCRIBE,quote=True),escape(url,quote=True)),
             'text':common['text'].replace(REPRESENTATIVE_UNSUBSCRIBE,url)}
    if len(message['html'].encode('utf-8'))>LIMIT_BYTES:raise ValueError('Email size limit.')
    return {'from':config.sender,'reply_to':config.reply_to,'to':[address],
            'subject':str(message['subject']).strip(),'html':message['html'],'text':message['text'],
            'headers':{'List-Unsubscribe':'<'+url+'>'}}


def persist(conn,key,value):
    conn.execute('''INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()''',(key,json.dumps({k:v for k,v in value.items() if not k.startswith('_')})))


def stop_state(conn,campaign,rows,hours,at):
    """One bounded stop-state read. Pending signed consent changes fail closed."""
    return conn.execute('''SELECT s.id,
      CASE WHEN EXISTS(SELECT 1 FROM crm_suppressions p WHERE p.active AND
        (p.recipient_hash=s.recipient_hash OR p.shopify_customer_id=s.shopify_customer_id)) THEN 'local_suppression'
      WHEN EXISTS(SELECT 1 FROM crm_webhook_events e WHERE e.related_customer_id=s.shopify_customer_id
        AND e.topic IN ('customers_email_marketing_consent/update','customers/delete','customers/redact')
        AND e.received_at>=%s) THEN 'consent_changed_after_snapshot'
      WHEN EXISTS(SELECT 1 FROM crm_marketing_sends r WHERE r.recipient_hash=s.recipient_hash
        AND r.campaign_id IS DISTINCT FROM s.campaign_id AND NOT r.test_send
        AND r.status IN ('ACCEPTED','SUBMITTING','UNCERTAIN') AND r.first_submitted_at>=%s) THEN 'smart_sending'
      ELSE '' END AS reason FROM crm_marketing_sends s WHERE s.id=ANY(%s)''',
      (campaign['locked_at'],at-timedelta(hours=hours),[r['id'] for r in rows])).fetchall()


def prepare(engine,campaign,content,provider_blocked):
    store=engine.store;at=engine.clock();dispatch=content['dispatch'];common=dispatch['message']
    sender=SimpleNamespace(sender=dispatch['sender'],reply_to=dispatch['reply_to'])
    prefix='campaign-batch:'+str(campaign['campaign_send_id'])+':'
    plans=[]
    with store.db() as conn:
        current=conn.execute('SELECT status FROM crm_campaigns WHERE id=%s FOR UPDATE',(campaign['id'],)).fetchone()
        if current['status']!='SENDING':return []
        existing=conn.execute('SELECT key,value FROM crm_runtime_state WHERE key LIKE %s ORDER BY (value->>\'batch_index\')::integer',(prefix+'%',)).fetchall()
        for entry in existing:
            state=entry['value']
            if state['status'] not in ('SUBMITTING','RETRY'):continue
            if (state['attempt_count'] and at-date(state['request_started_at'])>=RETRY_WINDOW) or state['attempt_count']>=MAX_ATTEMPTS:
                state['status']='HELD';state['error']='retry_window_exhausted';persist(conn,entry['key'],state)
                conn.execute("UPDATE crm_marketing_sends SET status='UNCERTAIN',error_code='batch_retry_exhausted',updated_at=now() WHERE id=ANY(%s)",(state['recipient_ids'],));continue
            if date(state.get('retry_at')) and date(state['retry_at'])>at:continue
            rows=conn.execute('SELECT * FROM crm_marketing_sends WHERE id=ANY(%s)',(state['recipient_ids'],)).fetchall()
            if len(rows)!=len(state['recipient_ids']) or any(r['status']!='SUBMITTING' for r in rows):
                raise ValueError('Frozen batch receipts changed.')
            reasons=stop_state(conn,campaign,rows,content['document']['smart_hours'],at)
            if any(r['reason'] for r in reasons) or any(r['recipient_hash'] in provider_blocked for r in rows):
                state['status']='HELD';state['error']='stop_state_changed';persist(conn,entry['key'],state)
                conn.execute("UPDATE crm_marketing_sends SET status='UNCERTAIN',error_code='batch_stop_state_changed',updated_at=now() WHERE id=ANY(%s)",(state['recipient_ids'],));continue
            state['_payloads']=[payload(common,r,sender) for r in state['recipients']]
            digest=hashlib.sha256(json.dumps(state['_payloads'],sort_keys=True).encode()).hexdigest()
            if digest!=state['request_hash']:raise ValueError('Frozen batch payload changed.')
            plans.append((entry['key'],state))
        # Stable order, maximum 1,200 due recipients per tick; scheduled future
        # recipients never get pulled into a currently due batch.
        plans=plans[:MAX_BATCHES]
        rows=conn.execute('''SELECT * FROM crm_marketing_sends WHERE campaign_id=%s
          AND status='PENDING' AND NOT test_send AND due_at<=now() ORDER BY due_at,recipient_hash
          FOR UPDATE SKIP LOCKED LIMIT %s''',(campaign['id'],(MAX_BATCHES-len(plans))*BATCH_SIZE)).fetchall()
        reasons={str(r['id']):r['reason'] for r in stop_state(conn,campaign,rows,content['document']['smart_hours'],at)} if rows else {}
        jobs=[];blocked=[]
        for row in rows:
            payload_started=time.monotonic()
            reason=reasons[str(row['id'])]
            recipient=dispatch['recipients'].get(row['recipient_hash'])
            if row['recipient_hash'] in provider_blocked:reason='provider_suppression'
            try:
                if not recipient or recipient_hash(recipient['address'])!=row['recipient_hash']:raise ValueError()
                mail=payload(common,recipient,sender)
            except (ValueError,KeyError,TypeError):reason=reason or 'invalid_frozen_payload'
            if reason:blocked.append({'id':str(row['id']),'code':reason})
            else:jobs.append((row,mail,(time.monotonic()-payload_started)*1000))
        if blocked:
            conn.execute('''UPDATE crm_marketing_sends s SET status='BLOCKED',error_code=j.code,updated_at=now()
                FROM jsonb_to_recordset(%s::jsonb) AS j(id uuid,code text) WHERE s.id=j.id''',(json.dumps(blocked),))
        offset=max((e['value']['batch_index'] for e in existing),default=-1)+1
        for index,start in enumerate(range(0,len(jobs),BATCH_SIZE),offset):
            group_started=time.monotonic()
            group=jobs[start:start+BATCH_SIZE];key=prefix+str(index)
            state={'campaign_id':str(campaign['id']),'campaign_send_id':str(campaign['campaign_send_id']),
                'batch_index':index,'recipient_ids':[str(r['id']) for r,_,_ in group],
                '_payloads':[m for _,m,_ in group],
                'recipients':[dispatch['recipients'][r['recipient_hash']] for r,_,_ in group],
                'idempotency_key':f'sports-cave/{campaign["campaign_send_id"]}/batch/{index}',
                'status':'SUBMITTING','attempt_count':0,'request_started_at':at.isoformat()}
            state['request_hash']=hashlib.sha256(json.dumps(state['_payloads'],sort_keys=True).encode()).hexdigest()
            state['_prepare_ms']=sum(ms for _,_,ms in group)+(time.monotonic()-group_started)*1000
            persist(conn,key,state)
            conn.execute("UPDATE crm_marketing_sends SET status='SUBMITTING',request_hash=%s,lease_until=now()+interval '5 minutes',updated_at=now() WHERE id=ANY(%s)",(state['request_hash'],state['recipient_ids']))
            plans.append((key,state))
    return plans


def attempt(engine,transport,key,state,content):
    claim_started=time.monotonic()
    engine.hold_lease();engine.config.require_send(False)
    # Commit attempts/timestamps before external I/O. Frozen payload and key
    # never change, including when receipt persistence fails after acceptance.
    with engine.store.db() as conn:
        campaign=conn.execute('SELECT * FROM crm_campaigns WHERE id=%s FOR UPDATE',(state['campaign_id'],)).fetchone()
        if campaign['status']!='SENDING':return None
        rows=conn.execute('SELECT * FROM crm_marketing_sends WHERE id=ANY(%s)',(state['recipient_ids'],)).fetchall()
        reasons={str(r['id']):r['reason'] for r in stop_state(conn,campaign,rows,content['document']['smart_hours'],engine.clock())}
        blocked=[i for i in state['recipient_ids'] if reasons.get(i)]
        if blocked:
            if state['attempt_count']:
                state['status']='HELD';state['error']='stop_state_changed';persist(conn,key,state)
                conn.execute("UPDATE crm_marketing_sends SET status='UNCERTAIN',error_code='batch_stop_state_changed',lease_until=NULL,updated_at=now() WHERE id=ANY(%s)",(state['recipient_ids'],))
                return None
            conn.execute("UPDATE crm_marketing_sends SET status='BLOCKED',error_code='dispatch_stop_state',lease_until=NULL,updated_at=now() WHERE id=ANY(%s)",(blocked,))
            indexes=[n for n,i in enumerate(state['recipient_ids']) if i not in blocked]
            for field in ('recipient_ids','recipients','_payloads'):state[field]=[state[field][n] for n in indexes]
            state['request_hash']=hashlib.sha256(json.dumps(state['_payloads'],sort_keys=True).encode()).hexdigest()
            if not indexes:
                state['status']='BLOCKED';persist(conn,key,state);return None
        if not state['attempt_count']:state['request_started_at']=engine.clock().isoformat()
        state['attempt_count']+=1;state['status']='SUBMITTING'
        state['last_request_started_at']=engine.clock().isoformat()
        persist(conn,key,state)
        conn.execute("UPDATE crm_marketing_sends SET attempts=attempts+1,first_submitted_at=COALESCE(first_submitted_at,now()),lease_until=now()+interval '5 minutes',updated_at=now() WHERE id=ANY(%s)",(state['recipient_ids'],))
    state['_claim_ms']=(time.monotonic()-claim_started)*1000
    def send():
        started=time.monotonic()
        try:return transport.send(state['_payloads'],state['idempotency_key']),None,(time.monotonic()-started)*1000
        except BatchError as exc:return None,exc,(time.monotonic()-started)*1000
    return send


def finish(engine,key,state,result,error,request_ms):
    at=engine.clock();started=time.monotonic();provider_ids=[]
    if error:
        known=error.category=='provider_rejected'
        state['status']='FAILED' if known else 'RETRY';state['error']=error.category
        state['retry_at']=(at+timedelta(seconds=max(error.retry_after,30*2**(state['attempt_count']-1)))).isoformat()
        with engine.store.db() as conn:
            persist(conn,key,state)
            conn.execute("UPDATE crm_marketing_sends SET status=%s,error_code=%s,lease_until=NULL,updated_at=now() WHERE id=ANY(%s)",('FAILED' if known else 'SUBMITTING',error.category,state['recipient_ids']))
    else:
        provider_ids=result['ids']
        receipts=[{'id':i,'provider':p} for i,p in zip(state['recipient_ids'],provider_ids)]
        state={k:v for k,v in state.items() if k not in ('_payloads','recipients')}
        state.update(status='ACCEPTED',accepted_at=at.isoformat(),provider_ids=provider_ids,error='')
        # Batch receipt + all per-recipient receipts commit atomically.
        with engine.store.db() as conn:
            persist(conn,key,state)
            conn.execute('''UPDATE crm_marketing_sends s SET status='ACCEPTED',provider_email_id=j.provider,
                error_code='',lease_until=NULL,updated_at=now() FROM jsonb_to_recordset(%s::jsonb) AS j(id uuid,provider text)
                WHERE s.id=j.id AND s.status='SUBMITTING' ''',(json.dumps(receipts),))
    db_ms=(time.monotonic()-started)*1000+state.get('_claim_ms',0)
    prep_ms=state.get('_prepare_ms',0)
    LOG.info('campaign_dispatch campaign_id=%s campaign_send_id=%s batch_index=%s batch_number=%s batch_size=%s attempt=%s payload_prepare_ms=%.1f resend_request_ms=%.1f status_code=%s retry_after=%s rate_limit_remaining=%s accepted_count=%s failed_count=%s db_write_ms=%.1f batch_total_ms=%.1f',
        state['campaign_id'],state['campaign_send_id'],state['batch_index'],state['batch_index']+1,len(state['recipient_ids']),state['attempt_count'],prep_ms,request_ms,
        error.status if error else result['status'],error.retry_after if error else result['retry_after'],
        None if error else result['remaining'],len(provider_ids),len(state['recipient_ids']) if error and state['status']=='FAILED' else 0,db_ms,prep_ms+request_ms+db_ms)
    if provider_ids:
        try:
            from crm_workspace_store import WorkspaceRecords
            WorkspaceRecords(engine.store.connect).reconcile_events_many(provider_ids)
        except Exception:LOG.warning('campaign_dispatch event_reconciliation_deferred')


def dispatch(engine):
    if not engine.config.enabled:return False
    engine.config.require_send(False);engine.hold_lease();started=time.monotonic()
    campaign=engine.store.q('''SELECT c.* FROM crm_campaigns c JOIN crm_template_versions v
      ON v.template_id=c.template_id AND v.version=c.template_version WHERE c.status='SENDING'
      AND v.content->'dispatch'->>'version'='1'
      AND c.audience_snapshot_id IS NOT NULL AND EXISTS(SELECT 1 FROM crm_marketing_sends s
        WHERE s.campaign_id=c.id AND s.status IN ('PENDING','SUBMITTING') AND s.due_at<=now())
      ORDER BY c.created_at LIMIT 1''',one=True)
    if not campaign:return False
    content=engine.store.template(campaign['template_id'],campaign['template_version'])
    if not content.get('dispatch'):
        LOG.warning('campaign_dispatch campaign_id=%s frozen_delivery_missing',campaign['id'])
        return False  # Legacy queued snapshots require explicit safe preparation.
    provider=engine.delivery()
    if not hasattr(provider,'batch_transport'):provider.batch_transport=BatchTransport(provider)
    transport=provider.batch_transport
    previous_calls=getattr(transport,'api_calls',None)
    provider_blocked=transport.suppressed_hashes()
    engine.hold_lease()
    prepared=time.monotonic();plans=prepare(engine,campaign,content,provider_blocked)
    LOG.info('campaign_dispatch campaign_id=%s batch_prepare_ms=%.1f payload_prepare_ms=%.1f batch_count=%s shopify_calls_during_dispatch=0 individual_email_calls=0',campaign['id'],(time.monotonic()-prepared)*1000,sum(s.get('_prepare_ms',0) for _,s in plans),len(plans))
    calls=0;accepted=0
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='crm-batch') as executor:
        index=0
        while index<len(plans):
            engine.hold_lease()
            current=engine.store.q('SELECT status FROM crm_campaigns WHERE id=%s',(campaign['id'],),True)
            if current['status']!='SENDING':break
            width=min(2,transport.concurrency)
            wave=plans[index:index+width];pending=[]
            for key,state in wave:
                send=attempt(engine,transport,key,state,content)
                if send is not None:pending.append((key,state,executor.submit(send)));calls+=1
            for key,state,future in pending:
                result,error,duration=future.result();finish(engine,key,state,result,error,duration)
                if result:accepted+=len(result['ids'])
            # Read back committed truth once per bounded wave. Diagnostics cannot
            # change dispatch or mask an existing provider/persistence failure.
            try:
                from crm_campaign_progress import read_progress
                progress=read_progress(engine.store,[campaign['id']])[str(campaign['id'])]
                LOG.info('campaign_progress campaign_id=%s send_id=%s job_status=%s total=%s processed=%s submitted=%s skipped=%s failed=%s held=%s worker_started_at=%s last_progress_at=%s completed_at=%s provider_batches=%s',
                    campaign['id'],campaign['campaign_send_id'],progress['status'],progress['total'],progress['processed'],progress['submitted'],progress['skipped'],progress['failed'],progress['held'],progress.get('worker_started_at'),progress.get('last_progress_at'),progress.get('sent_at'),index+len(wave))
            except Exception as exc:
                LOG.warning('campaign_progress read_failure=%s',type(exc).__name__)
            index+=width
            if any(state.get('status')=='RETRY' for _,state in wave):break
    elapsed=time.monotonic()-started
    total_calls=transport.api_calls-previous_calls if previous_calls is not None else calls
    LOG.info('campaign_dispatch campaign_send_id=%s recipient_total=%s total_batches=%s total_resend_calls=%s batch_email_calls=%s individual_email_calls=0 shopify_calls_during_dispatch=0 accepted_count=%s total_dispatch_ms=%.1f emails_per_second=%.2f',campaign['campaign_send_id'],campaign['final_recipient_count'],len(plans),total_calls,calls,accepted,elapsed*1000,accepted/max(elapsed,.001))
    return bool(plans)
