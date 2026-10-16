"""Worker Health adapters for the existing preparation queue; no artwork/ledger writes."""
from contextlib import contextmanager
import hashlib
import json
import re
import uuid

import worker_diagnostics as diagnostics
import worker_health as health
from auto_editions_onboarding_store import Queue

FILTERS=('All','Active','Queued','Failed','Needs Review','Completed')
PAGE_SIZE=50


def identity(value):
    if not isinstance(value,str) or not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*',value):raise ValueError('Choose an existing product ID.')
    return value


def version(row):return hashlib.sha256(json.dumps(row,sort_keys=True,default=str).encode()).hexdigest()[:20]


def collection(service,category='All'):
    if category not in FILTERS:raise ValueError('Invalid job filter.')
    from worker_health_cache import snapshot
    data=snapshot(service);jobs=data.pop('jobs')
    data['filters']={name:sum(name=='All' or j['category']==name for j in jobs) for name in FILTERS}
    selected=sorted((dict(j,version=version(j)) for j in jobs if category=='All' or j['category']==category),key=lambda j:j['id'])
    return data,selected


def page(service,category='All',cursor=''):
    if cursor:identity(cursor)
    summary,rows=collection(service,category)
    batch=[r for r in rows if r['id']>cursor][:PAGE_SIZE+1];more=len(batch)>PAGE_SIZE;batch=batch[:PAGE_SIZE]
    return dict(summary=summary,jobs=batch,total_rows=len(rows),next_cursor=batch[-1]['id'] if more else None,
                scanned_to=batch[-1]['id'] if more else 'end',page_size=PAGE_SIZE)


def changes(service,category,known,scanned_to):
    if not isinstance(known,dict) or len(known)>10000:raise ValueError('Bounded loaded job versions required.')
    for pid,value in known.items():
        identity(pid)
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{20}',value):raise ValueError('Invalid job version.')
    if scanned_to not in ('','end'):identity(scanned_to)
    summary,rows=collection(service,category);current={r['id']:r for r in rows}
    updates=[r for r in rows if r['id'] in known and known[r['id']]!=r['version']]
    # Reconcile newly matching jobs behind the stable cursor after live changes.
    arrivals=[r for r in rows if r['id'] not in known and (scanned_to=='end' or r['id']<=scanned_to)][:PAGE_SIZE]
    return dict(summary=summary,jobs=updates+arrivals,removed=[pid for pid in known if pid not in current],total_rows=len(rows))


PRODUCT_SQL="""SELECT COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id) AS pid,p.product_title,p.edition_total,
    (SELECT count(*) FROM edition_products other WHERE COALESCE(NULLIF(other.shopify_product_gid,''),other.shopify_product_id)=COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)) AS product_count,
    m.dropbox_file_id,m.file_path,q.status,q.file_id,q.preparation_hash,q.lease_until,q.attempts,q.priority,q.reason,q.source,
    to_jsonb(q)->'replacement' AS replacement,to_jsonb(q)->'reset_cancellation' AS reset_cancellation,
    EXISTS(SELECT 1 FROM auto_edition_layouts l WHERE l.product_gid=m.shopify_product_gid) AS approved,
    EXISTS(SELECT 1 FROM auto_edition_preparations prep WHERE prep.manifest->'source'->>'product_gid'=m.shopify_product_gid) AS retained,
    EXISTS(SELECT 1 FROM auto_edition_review_jobs j WHERE j.product_gid=m.shopify_product_gid AND j.state IN ('Pending','Processing')) AS reviewing
    FROM edition_products p LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)
    LEFT JOIN auto_edition_onboarding q ON q.product_gid=m.shopify_product_gid"""


def eligibility(row,repair_confirmed=False):
    if not row:return 'Product identity is missing.'
    if row['product_count']!=1:return 'Product identity is ambiguous. Resolve the duplicate product records first.'
    if not row['dropbox_file_id'] or not str(row.get('file_path') or '').lower().endswith('.psd'):return 'A unique existing PSD mapping is required. Use the existing mapping controls; this action never remaps.'
    if not isinstance(row['edition_total'],int) or not 1<=row['edition_total']<=1000:return 'The existing edition limit is not eligible for preparation.'
    if (row.get('reset_cancellation') or {}).get('stage') in ('Cancelling','Confirmed'):return 'Reset cancellation is pending. Wait for the companion safe-stop acknowledgement.'
    pending=row.get('replacement') or {}
    if pending.get('manual_required'):return 'Reset requires manual PSD mapping through Add before preparation can restart.'
    if pending.get('stage') in ('Discovering','Queued','Preparing'):return 'An explicit reset/reprocess is already in progress.'
    if row['status']=='Preparing':return 'An owned worker lease or recovery operation is still present. Wait for its recovery; do not force a retry.'
    if row['reviewing']:return 'An approval operation is pending or processing. Wait for its authoritative result.'
    if row['approved'] or row.get('preparation_hash') or row['retained']:return 'Prepared or approved artwork is protected. Use existing Review / Repair or the explicit reset/reprocess workflow.'
    if row.get('file_id') and row['file_id']!=row['dropbox_file_id']:return 'The mapped PSD differs from the queue source. Resolve the mapping explicitly first.'
    import auto_editions_v17
    if row['status']=='Awaiting preparation' and not auto_editions_v17.enabled() and (row['priority'] or 0)<=1:return 'This design is deferred by the existing queue policy. Use its authorised Prepare Now workflow.'
    if row['status'] not in (None,'Awaiting preparation','Blocked','Needs PSD Repair'):return 'This checkpoint cannot be queued through Retry.'
    detail=diagnostics.operator_details(row.get('reason'))
    if (row['status']=='Needs PSD Repair' or detail['manual_repair']) and not repair_confirmed:return 'Correct the recorded PSD/source/validation issue, then confirm that correction before retrying.'
    return ''


def search(connect,query):
    if not isinstance(query,str) or not 1<=len(query.strip())<=100:raise ValueError('Search by product title or ID (1â€“100 characters).')
    with connect() as conn,conn.cursor() as cur:
        cur.execute(PRODUCT_SQL+" WHERE position(lower(%s) in lower(COALESCE(p.product_title,'')||' '||COALESCE(p.shopify_product_gid,p.shopify_product_id)))>0 ORDER BY pid LIMIT 21",(query.strip(),))
        found=cur.fetchall()
    result=[];seen=set()
    for r in found[:20]:
        if r['pid'] in seen:continue
        seen.add(r['pid']);reason=eligibility(r)
        queued=r['status']=='Awaiting preparation'
        if queued and not reason:reason='Already queued. No duplicate job is needed.'
        label={'Awaiting preparation':'Queued','Needs PSD Repair':'Needs Repair','Blocked':'Failed'}.get(r['status'],r['status'] or 'Not queued')
        result.append(dict(product_gid=r['pid'],title=r['product_title'],status=label,eligible=not reason,
            reason=reason,eligible_after_repair=not queued and not eligibility(r,True),repair_required=r['status']=='Needs PSD Repair' or diagnostics.operator_details(r.get('reason'))['manual_repair']))
    return dict(rows=result,more=len(found)>20)


def submit(connect,pid,actor,request_id,repair_confirmed=False):
    identity(pid)
    try:request_id=str(uuid.UUID(request_id))
    except (ValueError,TypeError,AttributeError):raise ValueError('A stable queue request UUID is required.')
    if not actor or type(repair_confirmed) is not bool:raise ValueError('Identified administrator and repair confirmation required.')
    with connect() as conn,conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='800ms'; SET LOCAL statement_timeout='4000ms'")
        # Match reset's global lock order; never hold these locks over provider I/O.
        cur.execute('LOCK TABLE edition_products,product_psd_mappings,auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
        cur.execute("SELECT actor_id,product_gid FROM auto_edition_onboarding_audit WHERE event='worker_health_queue_request' AND detail->>'request_id'=%s ORDER BY id DESC LIMIT 1",(request_id,))
        prior=cur.fetchone()
        if prior:
            if prior['actor_id']!=actor or prior['product_gid']!=pid:raise ValueError('Queue request identity is already used for another selection.')
            cur.execute('SELECT status,reason FROM auto_edition_onboarding WHERE product_gid=%s',(pid,));row=cur.fetchone()
            return dict(accepted=True,duplicate=True,product_gid=pid,status='Pending' if row and row['status']=='Awaiting preparation' else row['status'] if row else 'Stage unavailable')
        cur.execute(PRODUCT_SQL+" WHERE COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=%s",(pid,));found=cur.fetchall()
        if len(found)>1:raise ValueError('Product identity is ambiguous. Resolve the duplicate records before queueing.')
        row=found[0] if len(found)==1 else None
        reason=eligibility(row,repair_confirmed)
        if reason:raise ValueError(reason)
        now=health.datetime.now(health.timezone.utc);lease=health.stamp(row.get('lease_until'));owned=bool(lease and lease>now)
        if health.telemetry_enabled():
            cur.execute("SELECT payload,seen_at FROM auto_edition_worker_heartbeats WHERE component='Companion' ORDER BY seen_at DESC LIMIT 1")
            observed=cur.fetchone() or {};beat=observed.get('payload') or {}
            if beat.get('processor_lock') or (beat.get('product_gid')==pid and (beat.get('checkpoint_pending') or beat.get('state')=='Recovering')):
                raise ValueError('Companion recovery or uncertain processor ownership must finish first. The retained checkpoint has not been discarded.')
            fresh=observed.get('seen_at') and health.seconds(observed['seen_at'],now)<=150
            if owned and (not fresh or beat.get('product_gid')==pid):raise ValueError('This ended attempt still has an owned lease. Wait for a fresh idle companion checkpoint or expiry before retrying.')
        elif owned:raise ValueError('The previous owned lease has not expired and companion recovery cannot be verified. Wait for its checkpoint or lease expiry.')
        @contextmanager
        def borrowed():yield conn
        if row['status'] in ('Blocked','Needs PSD Repair'):
            if not __import__('auto_editions_v17').enabled() and (row['priority'] or 0)<=1:raise ValueError('This retry would remain deferred. Use the authorised Prepare Now workflow instead.')
            Queue(borrowed).retry(pid,actor)
            cur.execute('UPDATE auto_edition_onboarding SET priority=%s WHERE product_gid=%s',(row['priority'],pid))
        elif row['status'] is None:
            Queue(borrowed).enqueue_cursor(cur,pid,row['dropbox_file_id'],actor,newly_linked=False)
        Queue.audit(cur,pid,actor,'worker_health_queue_request',dict(request_id=request_id,previous_status=row['status'],previous_attempts=row['attempts'],
            previous_error=diagnostics.technical_text(row.get('reason')),previous_source=row.get('source'),priority=row['priority'],repair_confirmed=repair_confirmed))
        cur.execute('SELECT status,priority FROM auto_edition_onboarding WHERE product_gid=%s',(pid,));current=cur.fetchone()
        if not current or current['status']!='Awaiting preparation':raise ValueError('Existing preparation was retained for review; no new processing was accepted.')
        return dict(accepted=True,duplicate=row['status']=='Awaiting preparation',product_gid=pid,status='Pending',request_id=request_id)


def details(connect,pid):
    identity(pid)
    with connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT status,reason,attempts,updated_at FROM auto_edition_onboarding WHERE product_gid=%s',(pid,));row=cur.fetchone()
        if not row:raise ValueError('Queue job is no longer available.')
        cur.execute("SELECT id,event,created_at,detail FROM auto_edition_onboarding_audit WHERE product_gid=%s ORDER BY id DESC LIMIT 50",(pid,));events=cur.fetchall()
    allowed={'reason','error','error_type','message','stage','code','previous_error','previous_attempts','repair_confirmed'}
    return dict(product_gid=pid,technical_error=diagnostics.technical_text(row['reason']),attempts=row['attempts'],attempt_timestamp=health.sydney(row['updated_at']),
        events=[dict(id=r['id'],event=r['event'],at=health.sydney(r['created_at']),detail={k:diagnostics.technical_text(v) for k,v in (r['detail'] or {}).items() if k in allowed}) for r in events])
