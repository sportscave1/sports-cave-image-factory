"""Explicit release transitions on Edition Ops' existing run/allocator ledger.

No import-time I/O. Pending runs are durable jobs; the existing reconciliation
worker resumes them after a restart. A local executor only accelerates dispatch.
"""
from contextlib import contextmanager
from html import escape
import json
import threading

import supabase_backend as backend
import shopify_sync


def create(handle, *, expected_run, request_id, name, start, total, reason, actor_id):
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT start_edition_version(%s,%s,%s,%s,%s,%s,%s,%s) AS version',
                    (handle,expected_run,request_id,name,start,total,reason,actor_id))
        result=cur.fetchone()['version']
    kick(handle)
    return result


@contextmanager
def mirror_lock(handle):
    """Serialize mirrors and release transitions with the allocator's lock.

    Reuse the reconciliation worker's transaction-lease pattern. Session locks
    are unsafe behind Supabase transaction pooling. This dedicated connection
    holds only the advisory lock; business writes use short transactions.
    """
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id) AS gid FROM edition_products WHERE shopify_handle=%s",(handle,))
            product=cur.fetchone()
            if not product:raise ValueError('Edition product not found')
            gid=product['gid']
            cur.execute('SET LOCAL idle_in_transaction_session_timeout = 0')
            cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(gid,))
            try:
                cur.execute('SELECT to_jsonb(r) AS version FROM edition_products p JOIN edition_runs r ON r.id=p.active_edition_run_id WHERE p.shopify_handle=%s',(handle,))
                version=(cur.fetchone() or {}).get('version') or {}
                yield version
            finally:
                conn.rollback()


def disclosure(version):
    return (f"{version['edition_name']} — separate artwork release {version['id']}. "
            f"This release is limited to {version['edition_total']} numbered editions. "
            "Earlier designs are separate releases; their certificates remain valid.")


def ensure_disclosure(product_id, version, *, config=None, request_post=None):
    """Only append a necessary release disclosure, preserving current description.

    Product identity, variants, price, images and existing description are never
    submitted from cached Edition Ops data.
    """
    query='query EditionReleaseDescription($id: ID!) {product(id:$id){id descriptionHtml}}'
    args=dict(config=config,request_post=request_post)
    data,_=shopify_sync.graphql_request(query,{'id':product_id},**args)
    product=data.get('product')
    if not product:raise ValueError('Shopify product unavailable for release disclosure')
    marker=f'data-sports-cave-release="{version["id"]}"'
    body=product.get('descriptionHtml') or ''
    if marker in body:return
    updated=body+'\n<p '+marker+'>'+escape(disclosure(version))+'</p>'
    mutation='''mutation EditionReleaseDisclosure($product: ProductUpdateInput!) {
      productUpdate(product:$product){product{id descriptionHtml} userErrors{field message}}}'''
    data,_=shopify_sync.graphql_request(mutation,{'product':{'id':product_id,'descriptionHtml':updated}},**args)
    result=data.get('productUpdate') or {}
    if result.get('userErrors'):raise ValueError('; '.join(x['message'] for x in result['userErrors']))
    if marker not in ((result.get('product') or {}).get('descriptionHtml') or ''):
        raise ValueError('Shopify did not confirm the release disclosure')


def sync_locked(handle, version, *, config=None, request_post=None):
    """Called only under mirror_lock; deterministic retry after uncertain results."""
    payload={}
    try:
        payload=backend.get_product_edition_metafield_payload(handle,ensure_schema_first=False)
        if str(payload.get('active_edition_run_id'))!=str(version['id']):raise ValueError('Release changed during sync')
        if version['status'] not in ('pending_sync','active','sold_out','inactive'):
            raise ValueError('Expired releases cannot control Shopify')
        if payload.get('allocation_blocked'):raise ValueError('Release allocation state requires reconciliation')
        pending=version['status']=='pending_sync'
        if pending:
            payload.update(active=True,run_status='active',is_archived=False)
            payload.update(backend.calculate_product_edition_metafield_values(payload))
        payload.update(edition_enabled=not payload['is_archived'],edition_next_number=payload['next_edition_number'],
                       edition_sold_count=payload['sold_count'],edition_remaining=payload['remaining_count'],
                       edition_label=version['edition_name']+' · Release '+str(version['id']))
        # Preserve the allocator's total-minus-sold ledger invariant, while the
        # storefront reports numbers actually available from this cursor.
        available=min(payload['remaining_count'],max(0,payload['edition_total']-payload['next_edition_number']+1))
        payload.update(remaining_count=available,edition_remaining=available)
        if not payload['is_archived'] and not payload['is_sold_out']:
            payload['edition_status']='final_editions' if available<=5 else 'selling_quickly' if available<=12 else 'limited_release'
            if available<=5:payload['edition_display_text']=f'Final Editions — Only {available} Remaining'
        if pending:ensure_disclosure(payload['shopify_product_id'],version,config=config,request_post=request_post)
        result=shopify_sync.sync_complete_product_edition_metafields(payload,config=config,request_post=request_post,
                                                                   verify=True,compare=True)
        with backend.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT set_config('sports_cave.edition_version_action','activate',true)")
            cur.execute("UPDATE edition_runs SET status=CASE WHEN status='pending_sync' THEN 'active' ELSE status END, activated_at=COALESCE(activated_at,now()),sync_error='',sync_attempts=sync_attempts+1,sync_retry_at=NULL,updated_at=now() WHERE id=%s RETURNING id",(version['id'],))
            if pending:
                cur.execute('UPDATE edition_products SET active=true,is_active=true,updated_at=now() WHERE active_edition_run_id=%s',(version['id'],))
                cur.execute("INSERT INTO edition_version_audit(run_id,action,after_state,reason) VALUES(%s,'ACTIVE',%s::jsonb,'Shopify metafields and release disclosure confirmed')",(version['id'],json.dumps({'next':payload['next_edition_number'],'sold':payload['sold_count']})))
        backend._mark_product_metafields_sync(handle,payload,'Synced','')
        backend._mark_allocation_metafield_mirror_status(handle,'synced','')
        return {'shopify_handle':handle,'payload':payload,'mirror_status':'updated',**result}
    except Exception as exc:
        # Never allocate during an uncertain transition. Re-read and set the
        # same values on retry; metafield CAS protects against late stale writes.
        with backend.connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE edition_runs SET sync_error=%s,sync_attempts=sync_attempts+1,sync_retry_at=CASE WHEN sync_attempts<7 THEN now()+least(3600,power(2,least(sync_attempts,6))*30)*interval '1 second' END WHERE id=%s",
                        (str(exc)[:1000],version['id']))
            cur.execute("INSERT INTO edition_version_audit(run_id,action,reason) VALUES(%s,'SYNC FAILED',%s)",(version['id'],str(exc)[:1000]))
        backend._mark_product_metafields_sync(handle,payload,'Failed',str(exc))
        raise


def pending(limit=10):
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT shopify_handle FROM edition_runs WHERE status='pending_sync' AND sync_retry_at<=now() ORDER BY sync_retry_at LIMIT %s",(min(50,max(1,limit)),))
        return [r['shopify_handle'] for r in cur.fetchall()]


def resume_pending():
    # Existing worker invocation; installation is explicitly separate from boot.
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regprocedure('start_edition_version(text,uuid,uuid,text,integer,integer,text,uuid)') AS ready")
        if not cur.fetchone()['ready']:return
    # Also recover ordinary row edits whose process stopped before its local
    # accelerator mirrored the committed counters.
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT shopify_handle FROM edition_products WHERE metafields_sync_status='Pending' ORDER BY updated_at LIMIT 10")
        edits=[r['shopify_handle'] for r in cur.fetchall()]
    for handle in dict.fromkeys(pending()+edits):
        try:backend.sync_product_edition_metafields(handle,ensure_schema_first=False)
        except Exception:pass  # Durable per-run error is visible to administrators.


_lock=threading.Lock()
_running=set()
_executor=None


def kick(handle):
    global _executor
    from concurrent.futures import ThreadPoolExecutor
    with _lock:
        if handle in _running:return
        if _executor is None:_executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='edition-sync')
        _running.add(handle)
    def run():
        try:backend.sync_product_edition_metafields(handle,ensure_schema_first=False)
        except Exception:pass
        finally:
            with _lock:_running.discard(handle)
    _executor.submit(run)


def archive(search='',offset=0,limit=25):
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id,shopify_handle,product_title,edition_name,last_allocated_number,sold_count,
          archived_at,retired_reason,status FROM edition_runs WHERE status='expired'
          AND (%s='' OR concat_ws(' ',product_title,edition_name,shopify_handle) ILIKE %s)
          ORDER BY archived_at DESC,id LIMIT %s OFFSET %s""",(search,'%'+search+'%',min(50,limit),max(0,offset)))
        return cur.fetchall()


def details(run_id):
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM edition_runs WHERE id=%s',(run_id,));run=cur.fetchone()
        cur.execute("SELECT edition_number,edition_total,shopify_order_name,certificate_status,status FROM edition_orders WHERE edition_run_id=%s ORDER BY edition_number LIMIT 100",(run_id,))
        allocations=cur.fetchall()
        cur.execute('SELECT action,reason,occurred_at FROM edition_version_audit WHERE run_id=%s ORDER BY id DESC LIMIT 25',(run_id,))
        return {'version':run,'allocations':allocations,'audit':cur.fetchall()}


def reconcile(handle,expected_run,actor_id,reason):
    """Repair only derived boundary/baseline; never invent sales or release numbers."""
    if len(reason.strip())<5:raise ValueError('A reconciliation reason is required')
    with mirror_lock(handle):
        with backend.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM os_users WHERE id=%s AND role='admin' AND is_active AND COALESCE(account_status,'active')<>'removed'",(actor_id,))
            if not cur.fetchone():raise PermissionError('Active administrator required')
            product,run=backend._get_active_edition_run_for_handle(cur,handle,lock=True,create_missing=False)
            if not run or str(run['id'])!=str(expected_run) or run['status'] in ('expired','pending_sync'):
                raise ValueError('Release changed or is pending sync; reload before reconciliation')
            cur.execute("""SELECT count(*) AS records,count(DISTINCT edition_number) AS numbers,
              max(edition_number) AS highest,count(*) FILTER(WHERE identity_enforced AND allocation_valid
                AND COALESCE(status,'') NOT IN ('voided','refunded','cancelled','superseded')) AS atomic_count
              FROM edition_orders WHERE edition_run_id=%s OR (edition_run_id IS NULL AND shopify_product_gid=%s)""",
              (run['id'],product.get('shopify_product_gid') or product['shopify_product_id']))
            ledger=cur.fetchone();sold=int(product['sold_count']);total=int(product['edition_total'])
            if ledger['records']!=ledger['numbers'] or sold<ledger['atomic_count'] or not 0<=sold<=total:
                raise ValueError('Conflicting allocations or sales need an audited historical repair; no counters changed')
            next_number=max(int(product['next_edition_number']),int(product.get('last_assigned_edition') or 0)+1,int(ledger['highest'] or 0)+1,int(run.get('starting_number') or 1))
            if next_number>total+1:raise ValueError('Issued boundary exceeds this release; review allocations')
            cur.execute('UPDATE edition_runs SET next_edition_number=%s,allocation_baseline_sold_count=%s,updated_at=now() WHERE id=%s',(next_number,sold-ledger['atomic_count'],run['id']))
            cur.execute("UPDATE edition_products SET next_edition_number=%s,remaining_count=%s,metafields_sync_status='Pending',updated_at=now() WHERE id=%s",(next_number,total-sold,product['id']))
            cur.execute("INSERT INTO edition_version_audit(run_id,actor_id,action,before_state,after_state,reason) VALUES(%s,%s,'RECONCILED',%s::jsonb,%s::jsonb,%s)",
                        (run['id'],actor_id,json.dumps(dict(product),default=str),json.dumps({'next':next_number,'sold':sold}),reason))
    kick(handle)
    return next_number
