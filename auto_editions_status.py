"""Small authoritative Edition Ops status snapshots; no Dropbox/Shopify I/O."""
from datetime import datetime,timezone
import re
import time
import json
import hashlib
import hmac
import os
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse,JSONResponse
import auto_editions_api as api
import auto_editions_runtime as runtime
from auto_editions_onboarding_store import Queue

LABELS=('Not Connected','Connect','Queued','Deferred','Preparing','Review','Needs Review','Cloud Ready','Production Ready','Needs Repair','Failed','Unavailable')
ICONS=dict(zip(LABELS,('○','↗','◷','–','↻','◇','◇','✅','✅','⚒','!','?')))


def labels():
    from auto_editions_quality import enabled as quality_enabled
    hidden=('Review','Cloud Ready') if quality_enabled() else ('Needs Review','Production Ready')
    return tuple(label for label in LABELS if label not in hidden)


CHECKPOINTS={'queued':'Queued','mapping_confirmed':'Mapping saved','claimed':'Companion claimed',
    'Preparing':'Preparing','Blocked':'Preparation paused','Cloud Ready':'Cloud Ready',
    'Needs PSD Repair':'PSD repair required','visual_quality_approved':'Visual review approved',
    'preparation_metrics':'Preparation uploaded','priority':'Priority updated','retry':'Retry queued','prepare_now':'Prepare Now queued'}

SQL="""SELECT w.pid AS product_gid,m.dropbox_file_id,q.file_id,q.status,q.priority,
 q.preparation_hash,q.source,q.reason,q.attempts,q.lease_until,q.updated_at,
 p.edition_total AS product_total,prep.manifest->'source' AS prepared_source,
 prep.manifest->'edition_total' AS prepared_total,prep.hash AS stored_hash,
 proof.pixel_exact,proof.outside_exact,proof.bound,
 approval.approved,approval.hash_count,a.event AS checkpoint,a.created_at AS checkpoint_at,
 {observed} AS observed_source {quality_select}
 FROM unnest(%s::text[]) w(pid)
 LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=w.pid
 LEFT JOIN auto_edition_onboarding q ON q.product_gid=w.pid
 LEFT JOIN edition_products p ON p.shopify_product_gid=w.pid OR
   (NULLIF(p.shopify_product_gid,'') IS NULL AND p.shopify_product_id IN(w.pid,regexp_replace(w.pid,'^gid://shopify/Product/','')))
 LEFT JOIN auto_edition_preparations prep ON prep.hash=q.preparation_hash
 LEFT JOIN LATERAL (SELECT
   bool_or((value->>'pixel_exact')='true') AS pixel_exact,
   bool_or((value->>'outside_number_exact')='true') AS outside_exact,
   bool_and(COALESCE(value->>'preparation_hash'=prep.hash,false)) AS bound
   FROM jsonb_array_elements(CASE WHEN jsonb_typeof(prep.proofs)='array' THEN prep.proofs ELSE '[]'::jsonb END)) proof ON true
 LEFT JOIN LATERAL (SELECT count(DISTINCT l.preparation_hash) AS hash_count,
   bool_or(l.preparation_hash=q.preparation_hash
     AND l.approval->>'preparation_hash'=q.preparation_hash
     AND COALESCE(l.approval->>'actor_id','')<>''
     AND l.approval->>'visual_approved'='true' AND l.approval->>'pixel_exact'='true'
     AND l.approval->>'test_only'='true') AS approved
   FROM auto_edition_layouts l WHERE l.product_gid=w.pid) approval ON true
 LEFT JOIN LATERAL (SELECT event,created_at FROM auto_edition_onboarding_audit
   WHERE product_gid=w.pid ORDER BY created_at DESC,id DESC LIMIT 1) a ON true
 {inventory}
 {quality_join}
"""


def identity(value):
    if not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*',str(value or '')):
        raise ValueError('An exact product identity is required.')
    return value


def reason(value):
    text=' '.join(str(value or '').split())[:240]
    # Checkpoint failure text is never a channel for paths or credentials.
    if re.search(r'[A-Za-z][A-Za-z0-9+.-]*://|[A-Za-z]:[\\/]|(?:^|[\s:=(])/|token|password|secret|credential|Bearer\s|shpat_|sk_live|ghp_|\b[A-Za-z0-9_+-]{40,}\b',text,re.I):
        return 'Preparation needs attention. Technical details are retained in the server log.'
    return text


def unavailable(pid):
    return dict(product_gid=pid,status='Unavailable',icon='?',reason='Authoritative status unavailable. Retry refresh.',
                checkpoint='',checkpoint_at=None,preparation_hash=None,actions=[])


def project(row, *, writable=False, now=None):
    """Conservative states: no inferred connection, approval or print readiness."""
    now=now or datetime.now(timezone.utc)
    pid=row['product_gid'];status=row.get('status');digest=row.get('preparation_hash')
    state='Not Connected';why='';actions=[]
    mapped=row.get('dropbox_file_id')
    source=row.get('prepared_source') if isinstance(row.get('prepared_source'),dict) else {}
    valid=(row.get('stored_hash')==digest and bool(digest) and row.get('source')==row.get('prepared_source')
        and source.get('file_id')==mapped
        and source.get('product_gid')==pid
        and type(row.get('product_total')) is int and 1<=row['product_total']<=1000
        and row.get('prepared_total')==row.get('product_total')
        and bool(re.fullmatch(r'[a-f0-9]{64}',str(digest or '')))
        and bool(re.fullmatch(r'[a-f0-9]+',str(source.get('revision') or '')))
        and bool(re.fullmatch(r'[a-f0-9]{64}',str(source.get('content_hash') or '')))
        and row.get('pixel_exact') is True and row.get('outside_exact') is True and row.get('bound') is True)
    observed=row.get('observed_source')
    if observed and observed!=row.get('prepared_source'):valid=False
    if mapped:
        if not row.get('file_id'):
            state='Connect';why='Verified PSD has no onboarding checkpoint.';actions=['connect']
        elif row['file_id']!=mapped:
            state='Failed';why='Onboarding refers to a different mapping. Administrator review required.'
        elif status=='Awaiting preparation':
            state='Deferred' if row.get('priority',0)==0 else 'Queued';actions=['prepare-now']
        elif status=='Preparing':
            lease=row.get('lease_until')
            if isinstance(lease,str):lease=datetime.fromisoformat(lease.replace('Z','+00:00'))
            if not lease or lease<=now:
                state='Failed';why='Companion lease expired. Durable worker recovery is pending.'
            else:state='Preparing'
        elif status=='Needs PSD Repair':state='Needs Repair';why=reason(row.get('reason'));actions=['retry'] if not digest else []
        elif digest:
            if not valid:state='Failed';why='Preparation differs from current source, edition limit or validation proofs. Review required.'
            elif status=='Cloud Ready' and row.get('approved') is True and row.get('hash_count')==1:state='Cloud Ready'
            elif status=='Blocked' and not row.get('approved'):state='Review';why='Prepared artwork requires visual approval.';actions=['review']
            else:state='Failed';why='Preparation approval or checkpoint is inconsistent. Administrator review required.'
        elif status=='Blocked':
            state='Failed';why=reason(row.get('reason')) or 'Preparation is blocked.';actions=['retry']
        else:state='Failed';why='Onboarding checkpoint requires administrator review.'
    from auto_editions_quality import enabled as quality_enabled,current_certificate,standards,standard_for
    if quality_enabled() and digest and valid and state in ('Review','Cloud Ready'):
        check=row.get('quality_assessment')
        if check and row.get('quality_fresh') and current_certificate(check,row.get('quality_manifest') or {},standards()):
            state='Production Ready';why='Validated supplier assets for the approved variant scope.';actions=[]
        elif check and row.get('quality_fresh') and check.get('status') in ('Failed','Needs Repair'):
            state=check['status'];why=reason(check.get('reason'));actions=['recheck']
        elif not row.get('quality_fresh') and standard_for(row.get('quality_manifest') or {},standards()):
            state='Preparing';why='Automatic production validation is pending.';actions=[]
        elif state in ('Review','Cloud Ready'):
            state='Needs Review';why=reason((check or {}).get('reason')) or 'Artwork or supplier evidence requires review.'
            actions=['review']+(['recheck'] if check else [])
    return dict(product_gid=pid,status=state,icon=ICONS[state],reason=why,
                mapping_file_id=mapped,
                checkpoint=CHECKPOINTS.get(row.get('checkpoint'),'Checkpoint recorded' if row.get('checkpoint') else ''),
                checkpoint_at=str(row.get('checkpoint_at') or row.get('updated_at') or '') or None,
                preparation_hash=digest,actions=actions if writable else [])


def batch(connect, ids, *, writable=False):
    ids=list(dict.fromkeys(identity(pid) for pid in ids))
    if len(ids)>1000:raise ValueError('Status batch exceeds the Edition Ops limit.')
    if not ids:return {'rows':[],'query_count':0,'duration_ms':0}
    from auto_editions_discovery import enabled
    from auto_editions_quality import enabled as quality_enabled
    observed="jsonb_build_object('product_gid',w.pid,'file_id',i.file_id,'revision',i.metadata->>'rev','content_hash',i.metadata->>'content_hash')"
    sql=SQL.format(observed=f"CASE WHEN i.file_id IS NOT NULL THEN {observed} WHEN c.complete THEN jsonb_build_object('missing',true) END" if enabled() else 'NULL::jsonb',
                   inventory='LEFT JOIN auto_edition_source_inventory i ON i.file_id=m.dropbox_file_id LEFT JOIN auto_edition_discovery_cursor c ON c.id=1' if enabled() else '',
                   quality_select=', qc.assessment AS quality_assessment,qc.next_check_at>now() AS quality_fresh,prep.manifest AS quality_manifest' if quality_enabled() else '',
                   quality_join='LEFT JOIN auto_edition_quality_checks qc ON qc.preparation_hash=q.preparation_hash AND qc.product_gid=w.pid' if quality_enabled() else '')
    start=time.perf_counter()
    with connect() as conn,conn.cursor() as cur:
        cur.execute(sql,(ids,));raw=cur.fetchall()
    groups={pid:[] for pid in ids}
    for row in raw:groups[row['product_gid']].append(dict(row))
    result=[]
    for pid,rows in groups.items():
        if len(rows)!=1:result.append(unavailable(pid))
        else:result.append(project(rows[0],writable=writable))
    return {'rows':result,'query_count':1,'duration_ms':round((time.perf_counter()-start)*1000,2)}


async def actor(request, *, write=False):
    import files_upload_api as files
    import os_accounts
    user=await run_in_threadpool(files._request_user,request)
    if not os_accounts.can_access_page(user,'Edition Ops'):
        raise PermissionError('Edition Ops access is required.')
    if write:return await api.actor(request,setup=True,write=True)
    return user


def can_write(user):
    import os_accounts
    return runtime.enabled() and os_accounts.is_admin(user) and all(os_accounts.can_access_page(user,p) for p in ('Files','Orders','Edition Ops'))


def signature(data):
    import sc_auth
    key=sc_auth._signing_key(extra_secret=os.getenv('SPORTS_CAVE_AUTH_SECRET','').strip())
    payload=b'sports-cave-edition-status-v1\0'+json.dumps(data,sort_keys=True,separators=(',',':')).encode()
    return hmac.new(key,payload,hashlib.sha256).hexdigest()


def signed(data,user):
    snapshot={'actor_id':str(user.get('id','')),'issued_at':int(time.time())}
    return {**data,'snapshot':snapshot,'signature':signature({**snapshot,'rows':data['rows']})}


def verify_snapshot(value,user,ids):
    try:
        snapshot={**value['snapshot'],'rows':value['rows']}
        if (snapshot['actor_id']!=str(user.get('id','')) or not 0<=time.time()-snapshot['issued_at']<=90
                or not hmac.compare_digest(value['signature'],signature(snapshot))
                or {r['product_gid'] for r in snapshot['rows']}!=set(ids)):
            return None
        return {r['product_gid']:r for r in snapshot['rows']}
    except (KeyError,TypeError,ValueError):return None


async def statuses(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        user=await actor(request)
        body=await files._json_body(request)
        if set(body)!={'product_gids'} or not isinstance(body['product_gids'],list):raise ValueError('A bounded product batch is required.')
        data=await run_in_threadpool(batch,db.connect,body['product_gids'],writable=can_write(user))
        return JSONResponse(signed(data,user),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


def connect_existing(connect,pid,actor_id):
    """Only a missing checkpoint is recoverable here. Never replace/reset one."""
    identity(pid);queue=Queue(connect)
    if not actor_id:raise PermissionError('An identified administrator is required.')
    with connect() as conn,conn.cursor() as cur:
        cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
        from psd_mapping_store import PostgresMappings
        PostgresMappings.product(cur,pid)
        cur.execute('SELECT dropbox_file_id FROM product_psd_mappings WHERE shopify_product_gid=%s',(pid,))
        mapping=cur.fetchone()
        if not mapping:raise ValueError('Save a verified PSD using the existing Add action first.')
        cur.execute('SELECT file_id FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,))
        current=cur.fetchone()
        if current:
            if current['file_id']!=mapping['dropbox_file_id']:raise ValueError('Existing checkpoint requires administrator review.')
            return
        queue.enqueue_cursor(cur,pid,mapping['dropbox_file_id'],actor_id)


async def connect_action(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        user=await actor(request,write=True)
        body=await files._json_body(request)
        if set(body)!={'product_gid'}:raise ValueError('Connect recovers one existing verified mapping.')
        await run_in_threadpool(connect_existing,db.connect,body['product_gid'],str(user['id']))
        return JSONResponse({'ok':True},headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def recheck_action(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        from auto_editions_quality_store import Quality
        user=await actor(request,write=True)
        body=await files._json_body(request)
        if set(body)!={'product_gid'}:raise ValueError('Recheck validates one existing preparation only.')
        await run_in_threadpool(Quality(db.connect).recheck,identity(body['product_gid']),str(user['id']))
        return JSONResponse({'ok':True},headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def detail_page(request):
    try:
        await actor(request)
        identity(request.query_params.get('product_gid'))
        return HTMLResponse((Path(__file__).parent/'components/auto_editions/status.html').read_text(encoding='utf-8'),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


ROUTES=(('/api/auto-editions/status',statuses,('POST',)),
        ('/api/auto-editions/status/connect',connect_action,('POST',)),
        ('/api/auto-editions/status/recheck',recheck_action,('POST',)),
        ('/auto-editions/status',detail_page,('GET',)))
