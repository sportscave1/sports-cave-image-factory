"""Durable manual enrollment and immediate first-step delivery in the CRM worker.

Uses the existing private runtime-state store and CRM worker, not another email
queue. Manual requests retain fresh eligibility checks and leased provider dispatch.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
import logging
from threading import Lock
from time import perf_counter
import uuid

from crm_logic import now, date, recipient_hash
from crm_navigation import require

LOG = logging.getLogger(__name__)
PREFIX = 'checkout-enroll:'
ACTIVE = ('QUEUED', 'CHECKING')
CONCURRENCY = 4
REQUEST_MAX_AGE = timedelta(minutes=15)
MAX_ATTEMPTS = 3


def reconciled_result(row, value, at=None):
    """Persisted membership wins over a lost acknowledgement; never enroll here."""
    from crm_checkout_identity import recovered
    if recovered(row) or row.get('status') == 'RECOVERED':
        return dict(value, state='DONE', result='Recovered',delivery='skipped')
    if row.get('enrollment_id') and not value.get('manual_dispatch'):
        return value if value.get('state') == 'DONE' else dict(value, state='DONE', result='Already in flow')
    if value.get('manual_dispatch') and value.get('delivery')!='skipped':
        receipt=next((s for s in row.get('sends',[]) if s.get('step')==0 and str(s.get('enrollment_id'))==str(row.get('enrollment_id'))),None)
        if receipt and receipt['status']=='ACCEPTED' and receipt.get('provider_id'):
            return dict(value,state='DONE',result='Sent',delivery='sent')
        if receipt and receipt['status'] in ('FAILED','BLOCKED','UNCERTAIN'):
            return dict(value,state='FAILED',delivery='failed',result=receipt.get('error_detail') or receipt.get('error') or 'Send failed')
    requested = date(value.get('requested_at'))
    if value.get('state') in ACTIVE and (not requested or (at or now())-requested >= REQUEST_MAX_AGE):
        return dict(value, state='FAILED', result='Request expired — retry to recheck', error_code='request_expired',delivery='failed')
    if value.get('state')=='FAILED' and value.get('delivery')=='queued':return dict(value,delivery='failed')
    return value


def reconcile_requests(store):
    """Bound stale manual intent without releasing historical checkouts to send.

    A healthy in-flight lease is left alone. Existing membership/recovery is
    acknowledged; old unprocessed intent expires and requires an explicit retry.
    This changes request receipts only, never enrollments or send history.
    """
    rows = store.q('''WITH candidates AS (
      SELECT r.key,r.value,c.status AS checkout_status,j.id AS enrollment_id
      FROM crm_runtime_state r
      LEFT JOIN crm_shopify_checkouts c ON c.checkout_key=r.value->>'checkout_key'
      LEFT JOIN LATERAL (SELECT id FROM crm_automation_enrollments
        WHERE automation_id::text=r.value->>'automation_id' AND checkout_key=c.checkout_key LIMIT 1) j ON true
      WHERE starts_with(r.key,%s) AND r.value->>'state' IN ('QUEUED','CHECKING')
        AND (r.value->>'state'='QUEUED' OR COALESCE((r.value->>'lease_until')::timestamptz,'-infinity')<=now())
        AND ((j.id IS NOT NULL AND COALESCE((r.value->>'manual_dispatch')::boolean,false)=false) OR c.status='RECOVERED'
          OR COALESCE((r.value->>'requested_at')::timestamptz,'-infinity')<=now()-%s::interval
          OR COALESCE((r.value->>'attempts')::int,0)>=%s)
      ORDER BY r.updated_at LIMIT 100 FOR UPDATE OF r SKIP LOCKED
    ) UPDATE crm_runtime_state r SET value=r.value || jsonb_build_object(
      'state',CASE WHEN (c.enrollment_id IS NOT NULL AND COALESCE((r.value->>'manual_dispatch')::boolean,false)=false) OR c.checkout_status='RECOVERED' THEN 'DONE' ELSE 'FAILED' END,
      'result',CASE WHEN c.checkout_status='RECOVERED' THEN 'Recovered'
        WHEN c.enrollment_id IS NOT NULL AND COALESCE((r.value->>'manual_dispatch')::boolean,false)=false THEN 'Already in flow' ELSE 'Request expired — retry to recheck' END,
      'error_code',CASE WHEN (c.enrollment_id IS NOT NULL AND COALESCE((r.value->>'manual_dispatch')::boolean,false)=false) OR c.checkout_status='RECOVERED' THEN NULL ELSE 'request_expired' END,
      'completed_at',now()),updated_at=now()
      FROM candidates c WHERE r.key=c.key RETURNING r.value->>'state' AS state''',
      (PREFIX,REQUEST_MAX_AGE,MAX_ATTEMPTS))
    if rows:LOG.info('checkout_requests_reconciled completed=%s expired=%s',
                    sum(r['state']=='DONE' for r in rows),sum(r['state']=='FAILED' for r in rows))
    return len(rows)


def request_key(identity, checkout_key):
    return PREFIX + str(identity) + ':' + checkout_key


def request(store, user, identity, selected):
    """Batched SQL plus stale-intent reconciliation; zero Shopify/provider calls."""
    require(user, 'crm_automations_manage')
    identity = str(uuid.UUID(str(identity)))
    if not selected or len(selected)>500 or any(not isinstance(k,str) or len(k)>256 for k in selected):
        raise ValueError('Select between 1 and 500 checkouts.')
    keys = sorted(set(selected))
    reconcile_requests(store)
    from crm_automation_definition import native
    from crm_checkout_analytics import disabled_reason
    started = perf_counter()
    with store.db() as conn:
        automation = conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR SHARE', (identity,)).fetchone()
        if not automation or not native(automation) or automation['trigger_type'] != 'abandoned':
            raise ValueError('Not eligible')
        rows = conn.execute('''SELECT c.*,j.id AS enrollment_id,j.status AS flow_status,j.current_step FROM crm_shopify_checkouts c
          LEFT JOIN LATERAL (SELECT id,status,current_step FROM crm_automation_enrollments WHERE automation_id=%s
            AND checkout_key=c.checkout_key LIMIT 1) j ON true
          WHERE c.checkout_key=ANY(%s::text[])''', (identity,keys)).fetchall()
        indexed = {c['checkout_key']:c for c in rows}
        suppressions = conn.execute('''SELECT recipient_hash,shopify_customer_id,reason FROM crm_suppressions
          WHERE active=true AND (recipient_hash=ANY(%s::text[]) OR shopify_customer_id=ANY(%s::text[]))''',
          ([recipient_hash((c.get('analytics') or {}).get('email')) for c in rows],
           [c['customer_id'] for c in rows if c.get('customer_id')])).fetchall()
        by_hash = {s['recipient_hash']:s for s in suppressions}
        by_customer = {s['shopify_customer_id']:s for s in suppressions if s.get('shopify_customer_id')}
        pending = []
        for key in keys:
            c = indexed.get(key)
            reason = disabled_reason(c,automation) if c else 'Not eligible'
            if c and reason=='Already in flow' and c.get('flow_status')=='ACTIVE' and c.get('current_step')==0:
                reason=disabled_reason({**c,'enrollment_id':None},automation)
            if c and not reason:
                suppression = by_hash.get(recipient_hash((c.get('analytics') or {}).get('email'))) or by_customer.get(c.get('customer_id'))
                if suppression:
                    reason = 'Unsubscribed' if suppression['reason'] in ('unsubscribe','unsubscribed') else 'Suppressed'
            pending.append({'key':request_key(identity,key),'value':{
                'automation_id':identity,'checkout_key':key,'checkout_id':c.get('admin_checkout_id') if c else None,
                'actor':str(user.get('id') or 'operator'),'requested_at':now().isoformat(),'manual_dispatch':True,
                'state':'DONE' if reason else 'QUEUED','result':reason or 'Queued','delivery':'skipped' if reason else 'queued'}})
        # Active requests cannot be resubmitted. Terminal rows may be explicitly
        # retried; previous results survive in private history. No per-row writes.
        result = conn.execute('''INSERT INTO crm_runtime_state AS existing(key,value)
          SELECT key,value FROM jsonb_to_recordset(%s::jsonb) AS input(key text,value jsonb)
          ON CONFLICT(key) DO UPDATE SET value=CASE WHEN existing.value->>'state' IN ('QUEUED','CHECKING')
            THEN existing.value ELSE excluded.value || jsonb_build_object('history',
              COALESCE(existing.value->'history','[]'::jsonb) || jsonb_build_array(existing.value-'history')) END,
            updated_at=CASE WHEN existing.value->>'state' IN ('QUEUED','CHECKING') THEN existing.updated_at ELSE now() END
          RETURNING key,value''', (json.dumps(pending),)).fetchall()
    LOG.info('checkout_enrollment_requested automation_id=%s rows=%s duration_ms=%.1f',
             identity,len(keys),(perf_counter()-started)*1000)
    return [r['value'] for r in result]


def read_requests(store, identity, keys):
    """One indexed batch; the join returns the actual persisted schedule."""
    if not keys:return []
    return store.q('''SELECT r.value-'history' AS request,c.checkout_key,c.analytics,c.status,c.order_id,c.activity_at,
        c.admin_checkout_id,j.id AS enrollment_id,j.status AS flow_status,j.stop_reason,j.current_step,j.steps,j.next_due_at,
        a.status AS automation_status,a.config->>'archived_at' AS archived_at,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('id',s.id,'enrollment_id',s.enrollment_id,'step',s.step_index,'step_id',related.steps->s.step_index->>'step_id','due_at',s.due_at,'status',s.status,'provider_id',s.provider_email_id,'error',s.error_code,'updated_at',s.updated_at,'error_detail',(SELECT value->>'message' FROM crm_runtime_state WHERE key='checkout-send-error:'||s.id::text))) FROM crm_marketing_sends s JOIN crm_automation_enrollments related ON related.id=s.enrollment_id JOIN crm_automations related_flow ON related_flow.id=related.automation_id WHERE related.checkout_key=c.checkout_key AND related_flow.trigger_type='abandoned' AND NOT s.test_send),'[]') AS sends
      FROM crm_runtime_state r JOIN crm_shopify_checkouts c ON c.checkout_key=r.value->>'checkout_key'
      JOIN crm_automations a ON a.id=(r.value->>'automation_id')::uuid
      LEFT JOIN LATERAL (SELECT * FROM crm_automation_enrollments WHERE automation_id=a.id
        AND checkout_key=c.checkout_key ORDER BY trigger_at DESC LIMIT 1) j ON true
      WHERE r.key=ANY(%s::text[])''', ([request_key(identity,k) for k in keys],))


def claim(store, limit, owner):
    """Atomic row leases recover unfinished work after a worker restart."""
    reconcile_requests(store)
    return store.q('''WITH candidates AS (
        SELECT key FROM crm_runtime_state WHERE starts_with(key,%s)
        AND COALESCE((value->>'requested_at')::timestamptz,'-infinity')>now()-%s::interval
        AND COALESCE((value->>'attempts')::int,0)<%s
        AND (value->>'state'='QUEUED' OR (value->>'state'='CHECKING' AND
          COALESCE((value->>'lease_until')::timestamptz,'-infinity')<now()))
        ORDER BY updated_at,key LIMIT %s FOR UPDATE SKIP LOCKED)
      UPDATE crm_runtime_state r SET value=r.value || jsonb_build_object(
        'state','CHECKING','result','Checking eligibility…','owner',%s::text,
        'lease_until',now()+interval '10 minutes','attempts',COALESCE((r.value->>'attempts')::int,0)+1),updated_at=now()
      FROM candidates c WHERE r.key=c.key RETURNING r.key,r.value''', (PREFIX,REQUEST_MAX_AGE,MAX_ATTEMPTS,limit,owner))


def safe_failure(exc):
    """Persist safe codes only; never raw Shopify/DB exception strings."""
    from crm_shopify import CapabilityUnavailable
    from crm_store import StoreUnavailable
    if isinstance(exc,CapabilityUnavailable):return 'FAILED','Failed — Shopify unavailable','shopify_unavailable'
    if isinstance(exc,StoreUnavailable):return 'FAILED','Failed — persistence error','persistence_error'
    if isinstance(exc,ValueError):
        message = str(exc)
        if 'identity' in message.lower():return 'FAILED','Failed — identity changed','identity_unverified'
        for label in ('Already in flow','Recovered','Missing email','Invalid email','Suppressed','Unsubscribed','Opted out','Region requires consent','Historical — not auto-enrolled','Not recoverable','Recovery policy needs configuration','Recovery permission not verified','Platform recovery eligibility unavailable','Not eligible'):
            if message.startswith(label):return 'DONE',label,'eligibility_block'
        if 'Shopify' in message:return 'FAILED','Failed — Shopify unavailable','shopify_unavailable'
        return 'DONE','Not eligible','eligibility_block'
    return 'FAILED','Failed — verification unavailable',type(exc).__name__


def process(store,shop,claimed):
    from crm_automation_analytics import _authorized_add_to_flow
    from crm_checkout_manual_dispatch import dispatch,history
    key,value = claimed['key'],claimed['value']
    started = perf_counter()
    result={'state':'DONE','result':'Not eligible','delivery':'skipped','enrolled':False}
    try:
        current = read_requests(store,value['automation_id'],[value['checkout_key']])
        if not current:raise ValueError('Not eligible')
        c = current[0]
        if c['request'].get('owner')!=value['owner'] or c['request'].get('state')!='CHECKING':return
        from crm_checkout_identity import recovered
        if recovered(c):raise ValueError('Recovered')
        previous=history(store,value['checkout_key'])
        if previous:
            result.update(state='FAILED' if previous['status'] in ('UNCERTAIN','SUBMITTING') else 'DONE',
                          result='Awaiting provider confirmation; no resend' if previous['status'] in ('UNCERTAIN','SUBMITTING') else 'Already sent',
                          delivery='skipped')
        else:
            if c.get('enrollment_id'):
                enrollment=store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(c['enrollment_id'],),True)
                if enrollment['status']!='ACTIVE' or enrollment['current_step']!=0:raise ValueError('Already in flow')
            else:
                enrollment=_authorized_add_to_flow(shop,store,value['automation_id'],value['checkout_id'],expected_key=value['checkout_key'])
                result['enrolled']=True
                store.q("UPDATE crm_runtime_state SET value=value || '{\"enrolled\":true}'::jsonb WHERE key=%s AND value->>'owner'=%s",(key,value['owner']))
            result['enrolled']=result['enrolled'] or bool(c['request'].get('enrolled'))
            result.update(dispatch(store,shop,enrollment))
    except Exception as exc:
        state,label,error=safe_failure(exc)
        from crm_resend import MarketingDisabled
        if isinstance(exc,MarketingDisabled):state,label,error='FAILED',str(exc),'delivery_disabled'
        result.update(state=state,result=label,error_code=error,delivery='failed' if state=='FAILED' else 'skipped')
    store.q('''UPDATE crm_runtime_state SET value=value || %s::jsonb,updated_at=now()
      WHERE key=%s AND value->>'owner'=%s AND value->>'state'='CHECKING' ''',
      (json.dumps({**result,'completed_at':now().isoformat()}),key,value['owner']))
    LOG.info('checkout_enrollment_result request_id=%s result=%s duration_ms=%.1f',
             key,result['state'],(perf_counter()-started)*1000)


class SharedLookups:
    """Coalesce only overlapping fresh profile reads. No stale consent cache.

    Shopify's existing global request semaphore/cost limiter remains in force.
    No cache survives a request completion or a worker restart.
    """
    def __init__(self,shop):
        self.shop=shop;self.lock=Lock();self.inflight={}

    def __getattr__(self,name):return getattr(self.shop,name)

    def _read(self,name,key,*args,**kwargs):
        token=(name,key)
        with self.lock:
            future=self.inflight.get(token);leader=future is None
            if leader:future=self.inflight[token]=Future()
        if leader:
            try:future.set_result(getattr(self.shop,name)(*args,**kwargs))
            except Exception as exc:future.set_exception(exc)
            finally:
                with self.lock:self.inflight.pop(token,None)
        return deepcopy(future.result())

    def customer(self,identity,fresh=False):
        return self._read('customer',identity,identity,fresh=True)

    def campaign_email_profiles(self,addresses):
        return self._read('campaign_email_profiles',tuple(sorted(set(addresses))),addresses)


class Processor:
    """A bounded lane in the existing CRM worker; no UI-owned enrollment work."""
    def __init__(self,store,shop):
        self.store=store;self.shop=SharedLookups(shop)
        self.pool=ThreadPoolExecutor(max_workers=CONCURRENCY,thread_name_prefix='checkout-enrollment')
        self.futures=set()

    def pump(self):
        for f in list(self.futures):
            if f.done():
                self.futures.remove(f)
                try:f.result()
                except Exception as exc:LOG.warning('checkout_enrollment_persistence_held error_class=%s',type(exc).__name__)
        capacity=CONCURRENCY-len(self.futures)
        if capacity:
            for item in claim(self.store,capacity,str(uuid.uuid4())):
                self.futures.add(self.pool.submit(process,self.store,self.shop,item))

    def run(self,stop):
        try:
            while not stop.is_set():
                try:self.pump()
                except Exception as exc:LOG.warning('checkout_enrollment_poll_failed error_class=%s',type(exc).__name__)
                stop.wait(2 if self.futures else 5)
        finally:self.pool.shutdown(wait=False,cancel_futures=True)
