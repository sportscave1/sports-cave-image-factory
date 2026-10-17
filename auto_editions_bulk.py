"""Explicit TEST visual review. No queue claims, generation, or supplier writes."""
import asyncio
import base64
import io
import json
import logging
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from contextlib import contextmanager, nullcontext
from pathlib import Path

from PIL import Image, ImageCms
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, Response
import auto_editions as ae
import auto_editions_api as api
import auto_editions_runtime as runtime
import auto_editions_status as statuses
from auto_editions_onboarding_store import Queue

LOG=logging.getLogger(__name__)

SORTS={'Failed First':('Failed',), 'Not Connected First':('Not Connected','Connect'),
       'Queued First':('Queued','Deferred'), 'Needs Review First':('Needs Review','Review'),
       'Synced / Cloud Ready First':('Cloud Ready','Production Ready'), 'Default Order':()}


def sorted_rows(rows, values, choice, identity):
    preferred=SORTS.get(choice,())
    return sorted(rows,key=lambda r:values.get(identity(r),{}).get('status') not in preferred)


def evidence(record):
    m=record['manifest'];ae.validate_manifest(m);digest=ae.fingerprint(m)
    if record['hash']!=digest:raise ValueError('Preparation identity changed.')
    colour=m.get('colour_evidence')
    if colour:
        if colour.get('pixels_converted') is not False or not re.fullmatch('[a-f0-9]{64}',str(colour.get('icc_sha256'))):
            raise ValueError('Current source colour evidence required.')
        if colour.get('policy'):
            from auto_editions_colour_policy import resolve
            _,active=resolve(m['source'])
            if active!=colour['policy']:raise ValueError('Source colour policy changed.')
    proofs=record.get('proofs') or []
    if (not proofs or any(p.get('preparation_hash')!=digest for p in proofs)
            or not any(p.get('outside_number_exact') is True for p in proofs)
            or not {1,m['edition_total']} <= {p.get('number') for p in proofs if p.get('pixel_exact') is True}):
        raise ValueError('Current first/last number and original preservation proofs required.')
    plaque=ae.bounds(m.get('plaque_bounds'),m['dimensions']);r=m['number_region']
    if not (plaque[0]<=r[0]<r[2]<=plaque[2] and plaque[1]<=r[1]<r[3]<=plaque[3]) or m.get('source_modified') is not False:
        raise ValueError('Plaque geometry or source preservation needs attention.')
    assets=[m['master'],*m['patches'].values()]
    receipts=record.get('receipts') or {};rows=receipts.get('assets') or []
    if (receipts.get('preparation_hash')!=digest or len(rows)!=len(assets)
            or {r.get('name') for r in rows}!={a['name'] for a in assets}
            or len({r.get('file_id') for r in rows})!=len(rows)
            or any(not str(r.get('file_id','')).startswith('id:') or not r.get('revision') or type(r.get('bytes')) is not int or r['bytes']<=0 for r in rows)):
        raise ValueError('Complete immutable upload receipts required.')
    return m


def inspect_asset(root, asset, expected, fetch, digest, receipts, expected_icc=None):
    from auto_editions_cloud import DropboxAssets
    path=root/asset['name'];fetch(digest,asset,path);ae.asset_path(root,asset)
    if not 0<path.stat().st_size<=DropboxAssets.MAX_ASSET_BYTES:raise ValueError('Prepared review asset exceeds the transfer limit.')
    receipt=next(r for r in receipts['assets'] if r['name']==asset['name'])
    if path.stat().st_size!=receipt['bytes']:raise ValueError('Prepared file size changed.')
    with Image.open(path) as image:
        if image.format!='PNG' or image.mode!='RGB' or list(image.size)!=expected:
            raise ValueError('Prepared file geometry or mode changed.')
        profile=image.info.get('icc_profile',b'')
        if not profile:raise ValueError('Embedded ICC profile required.')
        from auto_editions_colour_source import profile_info
        actual=profile_info(profile)
        if expected_icc and actual['sha256']!=expected_icc:raise ValueError('Source ICC evidence differs from prepared bytes.')
    return profile


REVIEW_DECODERS=threading.BoundedSemaphore(2)


class ReviewCache:
    """Bounded thumbnail bytes only; bounded cold decoders; durable derived JPEGs, no PSD/JPG renders."""
    def __init__(self,max_bytes=32*1024*1024):
        self.entries=OrderedDict();self.lock=threading.Lock();self.build_locks=[threading.Lock() for _ in range(64)];self.decoders=REVIEW_DECODERS;self.max_bytes=max_bytes

    def remember(self,key,data):
        with self.lock:
            self.entries.pop(key,None)
            while self.entries and sum(map(len,self.entries.values()))+len(data)>self.max_bytes:self.entries.popitem(last=False)
            if len(data)<=self.max_bytes:self.entries[key]=data

    @staticmethod
    def key(record,width=300):
        return (ae.fingerprint(dict(renderer='review-jpeg-v2',hash=record['hash'],receipts=record['receipts'],source=record['manifest']['source'])),width)

    @staticmethod
    def valid(data,width):
        if not data or len(data)>524288:return False
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format!='JPEG' or image.mode!='RGB' or image.width>width or image.height>1200:return False
                image.load()
            return True
        except (OSError,ValueError):return False

    @contextmanager
    def decoder(self,background):
        acquired=self.decoders.acquire(blocking=not background)
        try:yield acquired
        finally:
            if acquired:self.decoders.release()

    def get(self,record,fetch,width=300,store=None,cache_checked=False,*,local_root=None,metrics=None,queued_at=None,background=False):
        if width not in (300,1200):raise ValueError('Fixed review sizes required.')
        metrics={} if metrics is None else metrics;started=time.perf_counter()
        metrics.update(queue_wait_ms=round((started-queued_at)*1000,3) if queued_at else 0,asset_fetch_ms=0,decode_compose_ms=0,persistence_ms=0)
        m=evidence(record);digest=record['hash'];key=self.key(record,width)
        with self.lock:
            if key in self.entries:
                self.entries.move_to_end(key);metrics['cache']='memory';return self.entries[key]
        try:persisted=store.get(ae.fingerprint(key)) if store and not cache_checked else None
        except Exception as error:
            LOG.warning('REVIEW_PREVIEW cache_read_failed type=%s',type(error).__name__)
            persisted=None
        if self.valid(persisted,width):
            self.remember(key,persisted)
            metrics['cache']='persistent'
            return persisted
        # Serialize duplicate cold builds only, after both warm cache paths.
        waited=time.perf_counter()
        with self.build_locks[int(key[0][:8],16)%len(self.build_locks)]:
            metrics['queue_wait_ms']+=round((time.perf_counter()-waited)*1000,3)
            with self.lock:
                if key in self.entries:
                    self.entries.move_to_end(key);metrics['cache']='memory';return self.entries[key]
            from auto_editions_review_thumbnails import build_lease
            with build_lease(store,key[0]) as token:
                if token is False:return None
                if token is not None:
                    # A different process can publish between the initial read and claim.
                    persisted=store.get(ae.fingerprint(key))
                    if self.valid(persisted,width):
                        self.remember(key,persisted);metrics['cache']='persistent';return persisted
                waited=time.perf_counter()
                with self.decoder(background) as available:
                    if not available:return None
                    with (nullcontext(str(local_root)) if local_root is not None else tempfile.TemporaryDirectory(prefix='sc-review-small-')) as folder:
                        metrics['queue_wait_ms']+=round((time.perf_counter()-waited)*1000,3)
                        phase=time.perf_counter()
                        root=Path(folder);r=m['number_region'];profile=None
                        for asset,size in ((m['master'],m['dimensions']),(m['patches']['1'],[r[2]-r[0],r[3]-r[1]])):
                            p=inspect_asset(root,asset,size,(lambda *a:None) if local_root is not None else fetch,digest,record['receipts'],(m.get('colour_evidence') or {}).get('icc_sha256'))
                            if profile is not None and p!=profile:raise ValueError('Number ICC profile differs.')
                            profile=p
                        metrics['asset_fetch_ms']=round((time.perf_counter()-phase)*1000,3)
                        phase=time.perf_counter()
                        source_metrics=getattr(fetch,'review_timings',getattr(getattr(fetch,'__self__',None),'timings',{}))
                        if isinstance(source_metrics,dict):
                            metrics.update({name:source_metrics.get('review_'+name,0) for name in ('provider_transfer_ms','provider_bytes','asset_cache_hits','asset_cache_misses','cache_copy_ms')})
                        # Resize each existing verified asset before composition. Never build a full canvas/JPG.
                        scale=min(1,1200/m['dimensions'][0],1200/m['dimensions'][1])
                        size=tuple(max(1,round(n*scale)) for n in m['dimensions'])
                        with Image.open(root/m['master']['name']) as master:
                            master.thumbnail(size,Image.Resampling.LANCZOS);small=master.copy()
                        try:
                            box=[round(n*scale) for n in r]
                            with Image.open(root/m['patches']['1']['name']) as patch:
                                with patch.resize((max(1,box[2]-box[0]),max(1,box[3]-box[1])),Image.Resampling.LANCZOS) as number:
                                    small.paste(number,(box[0],box[1]))
                            # Convert only the small review to browser sRGB; retain the source profile untouched.
                            with ImageCms.profileToProfile(small,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB') as display:
                                outputs={}
                                for target in (1200,300):
                                    with display.copy() as scaled:
                                        scaled.thumbnail((target,1200),Image.Resampling.LANCZOS)
                                        output=io.BytesIO();scaled.save(output,'JPEG',quality=78);outputs[target]=output.getvalue()
                            data=outputs[width]
                        finally:small.close()
                metrics['decode_compose_ms']=round((time.perf_counter()-phase)*1000,3)
                phase=time.perf_counter()
                if store:
                    try:
                        if token is not None:
                            if not store.publish(key[0],token,{ae.fingerprint((key[0],target)):value for target,value in outputs.items()}):return None
                        else:
                            for target,value in outputs.items():store.put(ae.fingerprint((key[0],target)),value)
                    except Exception as error:LOG.warning('REVIEW_PREVIEW cache_write_failed type=%s',type(error).__name__)
                metrics.update(persistence_ms=round((time.perf_counter()-phase)*1000,3),cache='local-assets' if local_root is not None else 'built',jpeg_bytes=len(data),total_ms=round((time.perf_counter()-started)*1000,3))
                for target,value in outputs.items():self.remember((key[0],target),value)
                LOG.info('REVIEW_PREVIEW build_metrics=%s',json.dumps(metrics,sort_keys=True))
                return data


thumbnails=ReviewCache()


class PreviewBuilds:
    """Bounded disposable image work; never owns approvals or preparation jobs."""
    def __init__(self):
        self.lock=threading.Lock();self.pending={};self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='review-preview')

    def read(self,record,fetch,width,store,cache_checked=False):
        evidence(record);key=thumbnails.key(record,width)
        with thumbnails.lock:data=thumbnails.entries.get(key)
        if data:return data
        # Both display sizes come from one build. HTTP retries cannot duplicate it.
        with self.lock:
            for old,(future,created) in list(self.pending.items()):
                if future.done():
                    error=future.exception();ttl=30 if isinstance(error,(ValueError,KeyError,TypeError)) else 1
                    if error is None or time.monotonic()-getattr(future,'review_finished_at',created)>ttl:self.pending.pop(old)
            entry=self.pending.get(key[0])
            if entry:
                future,_=entry
                if future.done():
                    future.result()
                    with thumbnails.lock:return thumbnails.entries.get(key)
                return None
            if len(self.pending)>=8:return None
        # A stored hit is already small; never queue it behind a PNG transfer.
        try:data=store.get(ae.fingerprint(key)) if not cache_checked else None
        except Exception:data=None
        if thumbnails.valid(data,width):
            thumbnails.remember(key,data);return data
        with self.lock:
            if key[0] in self.pending or len(self.pending)>=8:return None
            future=self.pool.submit(thumbnails.get,record,fetch,width,store,True,queued_at=time.perf_counter())
            future.add_done_callback(lambda finished:setattr(finished,'review_finished_at',time.monotonic()))
            self.pending[key[0]]=(future,time.monotonic())
        return None


preview_builds=PreviewBuilds()
# Listing snapshots avoid a metadata query for each image; short lived, bounded, actor scoped.
snapshots=OrderedDict();snapshot_lock=threading.Lock()
PAGE_SIZE=10
LIST_TIMEOUT_SECONDS=12
READ_DEADLINE_SECONDS=6
READ_SLOTS=threading.BoundedSemaphore(3)

# Bound candidates BEFORE loading manifests, proof/receipt arrays or status laterals.
# Ordinality is a stable cursor within the caller's fixed catalogue/search context.
PAGE_SQL='''WITH candidates AS (SELECT w.pid AS product_gid,w.position,last_review.state AS review_result,last_review.reason AS review_reason
    FROM unnest(%s::text[]) WITH ORDINALITY AS w(pid,position)
    JOIN auto_edition_onboarding q ON q.product_gid=w.pid
    LEFT JOIN LATERAL (SELECT state,reason FROM auto_edition_review_jobs j
        WHERE j.product_gid=w.pid AND j.preparation_hash=q.preparation_hash
        ORDER BY created_at DESC,id DESC LIMIT 1) last_review ON true
    WHERE q.preparation_hash IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM auto_edition_review_jobs j
          WHERE j.product_gid=w.pid AND j.state IN ('Pending','Processing'))
      AND NOT EXISTS(SELECT 1 FROM auto_edition_layouts l
          WHERE l.product_gid=w.pid AND l.preparation_hash=q.preparation_hash
            AND l.approval->>'preparation_hash'=q.preparation_hash
            AND COALESCE(l.approval->>'actor_id','')<>''
            AND l.approval->>'visual_approved'='true' AND l.approval->>'pixel_exact'='true'
            AND l.approval->>'test_only'='true')
    ), counted AS (SELECT *,count(*) OVER() AS total_remaining FROM candidates)
    SELECT * FROM counted WHERE position>%s ORDER BY position LIMIT %s'''


@contextmanager
def review_read(connect):
    if not READ_SLOTS.acquire(blocking=False):
        raise ValueError('Review reads are busy. Retry in a moment.')
    try:
        with connect() as conn:
            # Pool-side checkout waits are outside PostgreSQL statement_timeout.
            # Cancel only this exclusive lease, never a connection after return.
            finished=threading.Event();cancel_lock=threading.Lock()
            def cancel_read():
                with cancel_lock:
                    if finished.is_set():return
                    safe_cancel=getattr(conn,'cancel_safe',None)
                    if callable(safe_cancel):
                        try:safe_cancel(timeout=1)
                        except Exception:pass
            timer=threading.Timer(READ_DEADLINE_SECONDS,cancel_read);timer.daemon=True;timer.start()
            # The existing read pool uses autocommit. Keep limits/read-only state
            # transaction-local so they never leak to Orders or other pool users.
            try:
                with conn.transaction() if hasattr(conn,'transaction') else nullcontext():
                    with conn.cursor() as cur:
                        cur.execute("SET TRANSACTION READ ONLY; SET LOCAL statement_timeout='2500ms'; SET LOCAL lock_timeout='500ms'")
                    yield conn
            finally:
                with cancel_lock:finished.set();timer.cancel()
    finally:READ_SLOTS.release()


async def actor(request,write=False):
    user=await api.actor(request,setup=True,write=write)
    import os_accounts
    if not os_accounts.can_access_page(user,'Edition Ops'):raise PermissionError('Edition Ops access required.')
    return user


def records(connect,ids):
    with connect() as conn,conn.cursor() as cur:
        cur.execute('''SELECT q.product_gid,p.product_title,prep.* FROM auto_edition_onboarding q
            JOIN auto_edition_preparations prep ON prep.hash=q.preparation_hash
            JOIN edition_products p ON p.shopify_product_gid=q.product_gid
            WHERE q.product_gid=ANY(%s)''',(ids,))
        rows=cur.fetchall()
    groups={pid:[] for pid in ids}
    for r in rows:groups[r['product_gid']].append(dict(r))
    return {pid:rs[0] for pid,rs in groups.items() if len(rs)==1}


def eligible_state(row):
    return row['status'] in ('Review','Needs Review') and row.get('approval_status') not in ('Failed','Needs Repair')


def admission(conn,selected):
    """Batch current metadata/evidence checks only; slow file checks remain leased.

    Runs inside the short submission transaction, with no provider requests.
    Final approval retains its full current-source, integrity and atomic fences.
    """
    @contextmanager
    def borrowed():yield conn
    current={r['product_gid']:r for r in statuses.batch(borrowed,list(selected),writable=True)['rows']}
    found=records(borrowed,list(selected));rejected={}
    with conn.cursor() as cur:
        cur.execute("SELECT product_gid,preparation_hash FROM auto_edition_review_jobs WHERE product_gid=ANY(%s) AND state IN ('Pending','Processing')",(list(selected),))
        active={r['product_gid']:r['preparation_hash'] for r in cur.fetchall()}
    for pid,digest in selected.items():
        row=current.get(pid);record=found.get(pid)
        if pid in active and active[pid]!=digest:
            rejected[pid]='A different preparation is already processing. Wait for its recorded result before retrying.'
        elif not row or row.get('preparation_hash')!=digest or not record or record['hash']!=digest:
            rejected[pid]='Preparation changed or is missing. Review the current design before retrying.'
        elif row['status'] not in ('Cloud Ready','Production Ready'):
            try:
                if not eligible_state(row):raise ValueError('Design is not eligible. Use Review / Repair.')
                evidence(record)
            except (ValueError,KeyError,TypeError) as error:
                rejected[pid]=str(error) if isinstance(error,ValueError) else 'Required review evidence is incomplete. Use Review / Repair.'
    return rejected


def listing(connect,ids,user,cursor=0):
    start=time.perf_counter();public=[]
    with review_read(connect) as conn:
        @contextmanager
        def borrowed():yield conn
        with conn.cursor() as cur:
            cur.execute(PAGE_SQL,(ids,cursor,PAGE_SIZE+1));page=cur.fetchall()
        has_more=len(page)>PAGE_SIZE;page=page[:PAGE_SIZE]
        next_cursor=int(page[-1]['position']) if has_more else None
        data=statuses.batch(borrowed,[r['product_gid'] for r in page],writable=True)
        failures={r['product_gid']:r for r in page if r.get('review_result') in ('Failed','Needs Attention')}
        candidates=[r for r in data['rows'] if r['status'] in ('Review','Needs Review') or (r['product_gid'] in failures and r['status'] not in ('Cloud Ready','Production Ready'))]
        found=records(borrowed,[r['product_gid'] for r in candidates]) if candidates else {}
    now=time.monotonic();entries={}
    for row in candidates:
        record=found.get(row['product_gid']);eligible=False;reason=row['reason']
        if record:
            try:evidence(record);eligible=eligible_state(row)
            except (ValueError,KeyError,TypeError):reason='Preparation proofs, geometry or receipts need attention.'
            key=(str(user['id']),row['product_gid'],record['hash'])
            entries[key]=(now+900,record)
        failure=failures.get(row['product_gid'])
        if failure:reason='Previous approval: '+failure['review_result']+'. '+failure['review_reason']
        public.append(dict(product_gid=row['product_gid'],hash=row['preparation_hash'],
                           title=record['product_title'] if record else row['product_gid'],eligible=eligible,reason=reason))
    # Do not hold the image lookup lock during manifest/policy validation.
    with snapshot_lock:
        for key in list(snapshots):
            if snapshots[key][0]<now:del snapshots[key]
        snapshots.update(entries)
        while len(snapshots)>1000:snapshots.popitem(last=False)
    return dict(rows=public,next_cursor=next_cursor,scanned=len(page),page_size=PAGE_SIZE,
                total_remaining=int(page[0]['total_remaining']) if page else 0,
                metadata_queries=1+(1 if page else 0)+(1 if candidates else 0),
                duration_ms=round((time.perf_counter()-start)*1000,2))


_verified_files=OrderedDict()
_verified_lock=threading.Lock()

def validate_files(record,assets):
    m=evidence(record);r=m['number_region'];profile=None
    with tempfile.TemporaryDirectory(prefix='sc-bulk-validate-') as folder:
        for a in [m['master'],*m['patches'].values()]:
            fresh=assets.integration.psd_open_metadata(assets.token,next(v['file_id'] for v in record['receipts']['assets'] if v['name']==a['name']),include_preview=False)
            receipt=next(v for v in record['receipts']['assets'] if v['name']==a['name'])
            from auto_editions_cloud import DropboxAssets
            if (fresh.get('rev')!=receipt['revision'] or fresh.get('id')!=receipt['file_id']
                    or fresh.get('size')!=receipt['bytes']
                    or str(fresh.get('path_display','')).lower()!=DropboxAssets.path(record['hash'],a['name']).lower()):raise ValueError('Cloud receipt changed.')
            cache_key=ae.fingerprint(dict(preparation=record['hash'],asset=a,receipt=receipt,current=fresh,
                geometry=m['dimensions'] if a==m['master'] else r,icc=(m.get('colour_evidence') or {}).get('icc_sha256')))
            with _verified_lock:cached=_verified_files.get(cache_key)
            if cached:
                if profile is not None and cached!=profile:raise ValueError('ICC profiles differ.')
                profile=cached
                continue
            p=inspect_asset(Path(folder),a,m['dimensions'] if a==m['master'] else [r[2]-r[0],r[3]-r[1]],assets.fetch,record['hash'],record['receipts'],(m.get('colour_evidence') or {}).get('icc_sha256'))
            p=ae.hashlib.sha256(p).hexdigest()  # Retain a bounded fingerprint, not potentially large ICC bytes.
            if profile is not None and p!=profile:raise ValueError('ICC profiles differ.')
            profile=p
            if ae.file_hash(Path(folder)/a['name'],dropbox=True)!=fresh.get('content_hash'):raise ValueError('Cloud file integrity differs.')
            with _verified_lock:
                _verified_files[cache_key]=p;_verified_files.move_to_end(cache_key)
                while len(_verified_files)>2048:_verified_files.popitem(last=False)
            (Path(folder)/a['name']).unlink()


def approve_one(connect,item,actor,*,job=None):
    from auto_editions_onboarding_api import candidate
    pid=statuses.identity(item['product_gid']);digest=item['hash']
    if not re.fullmatch('[a-f0-9]{64}',str(digest)):raise ValueError('Exact preparation hash required.')
    state=statuses.batch(connect,[pid],writable=True)['rows'][0]
    if state['preparation_hash']!=digest:return 'Skipped'
    if state['status']=='Cloud Ready':return 'Skipped'
    if not eligible_state(state):return 'Needs Attention'
    record,assets=candidate(pid,digest);validate_files(record,assets)
    # Lock the same product -> mapping -> checkpoint order as the reset/quality paths.
    with connect() as conn,conn.cursor() as cur:
        from auto_editions_bulk_jobs import ReviewJobs
        if job:
            ReviewJobs.fence(cur,job)
            if job['product_gid']!=pid or job['preparation_hash']!=digest or job['actor_id']!=actor:raise ValueError('Approval job identity changed.')
            import os_accounts
            cur.execute('SELECT id,role,is_active,account_status,removed_at FROM os_users WHERE id=%s FOR SHARE',(actor,))
            owner=cur.fetchone()
            if not os_accounts.is_admin(owner) or not os_accounts.can_access_page(owner,'Edition Ops'):raise PermissionError('Approval owner access changed.')
        def finish(result):
            if job:ReviewJobs.terminal(cur,job,result,'Current evidence or source requires Review / Repair.' if result=='Needs Attention' else 'Preparation changed or existing approval retained.' if result=='Skipped' else '')
            return result
        cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s FOR SHARE',(pid,));products=cur.fetchall()
        cur.execute('SELECT dropbox_file_id FROM product_psd_mappings WHERE shopify_product_gid=%s FOR SHARE',(pid,));mapping=cur.fetchone()
        cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,));q=cur.fetchone()
        m=record['manifest']
        if (len(products)!=1 or products[0]['edition_total']!=m['edition_total'] or not mapping or mapping['dropbox_file_id']!=m['source']['file_id']
                or not q or q['preparation_hash']!=digest or q['source']!=m['source'] or q['status'] not in ('Blocked','Cloud Ready')
                or (q.get('replacement') or {}).get('stage') in ('Discovering','Queued','Preparing','Failed')):return finish('Skipped')
        cur.execute('SELECT * FROM auto_edition_preparations WHERE hash=%s FOR SHARE',(digest,));current=cur.fetchone()
        if not current or any(current[k]!=record[k] for k in ('manifest','proofs','receipts')):return finish('Skipped')
        from auto_editions_quality import enabled
        if enabled():
            cur.execute('SELECT assessment FROM auto_edition_quality_checks WHERE preparation_hash=%s FOR SHARE',(digest,));check=cur.fetchone()
            if check and check['assessment'].get('status') in ('Failed','Needs Repair'):return finish('Needs Attention')
        # Source can change while PNG checks run; fence again immediately before the atomic write.
        meta=assets.integration.psd_open_metadata(assets.token,m['source']['file_id'],include_preview=False)
        import psd_directory
        if not psd_directory.approved_file(meta) or ae.source_identity(pid,meta)!=m['source']:return finish('Skipped')
        cur.execute('LOCK TABLE auto_edition_layouts IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('SELECT * FROM auto_edition_layouts WHERE product_gid=%s',(pid,));layouts=cur.fetchall()
        if any(l['preparation_hash']!=digest for l in layouts):return finish('Needs Attention')
        # Reuse the current production projection inside our locked transaction.
        # This also fences newer visual assessments without opening another connection.
        @contextmanager
        def borrowed():yield conn
        fresh=statuses.batch(borrowed,[pid],writable=True)['rows'][0]
        if fresh['preparation_hash']!=digest:return finish('Skipped')
        if not eligible_state(fresh):return finish('Skipped' if fresh['status']=='Cloud Ready' else 'Needs Attention')
        evidence(record)  # Colour policy may have been revoked during file validation.
        old=next((l for l in layouts if l['variant_id']=='*'),None)
        if old:
            # Never broaden an existing restricted TEST approval on retry.
            return finish('Skipped' if ae.status(m,old['approval'])=='TEST READY' else 'Needs Attention')
        if any(l['approval'].get('allocation_ids') is not None for l in layouts):return finish('Needs Attention')
        approval=dict(actor_id=actor,preparation_hash=digest,visual_approved=True,pixel_exact=True,test_only=True)
        if ae.status(m,approval)!='TEST READY':return finish('Needs Attention')
        cur.execute('''INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval)
            VALUES(%s,'*',%s,%s::jsonb)''',(pid,digest,json.dumps(approval)))
        cur.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready',reason='',updated_at=now() WHERE product_gid=%s",(pid,))
        cur.execute("INSERT INTO auto_edition_setup_audit(actor_id,preparation_hash,event,detail) VALUES(%s,%s,'approved_test_layout',%s::jsonb)",(actor,digest,json.dumps(dict(variant_id='*',bulk=True))))
        Queue.audit(cur,pid,actor,'visual_quality_approved',dict(hash=digest,test_only=True,bulk=True))
        return finish('Approved')


async def page(request):
    try:
        await actor(request)
        return HTMLResponse((Path(__file__).parent/'components/auto_editions/bulk.html').read_text(encoding='utf-8'),headers=api.HEADERS)
    except Exception as error:
        # This endpoint is an iframe document, not a JSON API. Keep diagnostic
        # details server-side, including UnicodeDecodeError (a ValueError).
        LOG.exception('BULK_REVIEW_PAGE failed to load review interface')
        return HTMLResponse('''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Bulk Review</title>
<style>body{font:14px system-ui;margin:16px;color:#28323d}h2{font-size:17px}button{padding:7px 12px;margin-right:6px;cursor:pointer}</style>
</head><body><h2>Bulk Review</h2><p role="alert">Bulk Review could not load. Retry shortly.</p>
<button id="retry-page" type="button">Retry</button><button id="close-page" type="button">Close</button>
<script>document.getElementById('retry-page').onclick=()=>location.reload();
document.getElementById('close-page').onclick=()=>parent.postMessage({type:'sports-cave-bulk-dismiss'},location.origin);</script>
</body></html>''',status_code=403 if isinstance(error,PermissionError) else 503,headers=api.HEADERS)


async def list_api(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        async def read():
            user=await actor(request)
            body=await files._json_body(request);ids=body.get('product_gids');cursor=body.get('cursor',0)
            if (set(body)-{'product_gids','cursor'} or not isinstance(ids,list) or len(ids)>1000
                    or type(cursor) is not int or not 0<=cursor<=len(ids)):
                raise ValueError('Bounded product batch and review cursor required.')
            ids=list(dict.fromkeys(statuses.identity(p) for p in ids))
            return await asyncio.to_thread(listing,db.read_connection,ids,user,cursor)
        result=await asyncio.wait_for(read(),timeout=LIST_TIMEOUT_SECONDS)
        return JSONResponse(result,headers={**api.HEADERS,'Server-Timing':f'metadata;dur={result["duration_ms"]}'})
    except TimeoutError:
        return JSONResponse(dict(error='Review metadata took too long. Retry.'),status_code=503,headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def image_api(request):
    try:
        user=await actor(request);q=request.query_params
        import supabase_backend as db
        entries,failures=await run_in_threadpool(preview_entries,user,[dict(product_gid=q.get('product_gid'),hash=q.get('hash'))],db.read_connection)
        if failures:raise ValueError(failures[0]['error'])
        record=entries[0][2]
        width=1200 if q.get('large')=='1' else 300
        fetch=prepared_fetch()
        from auto_editions_review_thumbnails import ReviewBuildStore as PreviewStore
        from auto_editions_bulk_runtime import connection
        data=await run_in_threadpool(preview_builds.read,record,fetch,width,PreviewStore(connection))
        if data is None:return JSONResponse(dict(state='Loading',error='Preparing verified preview.'),status_code=202,headers={**api.HEADERS,'Retry-After':'2'})
        return Response(data,media_type='image/jpeg',headers={**api.HEADERS,'Cache-Control':'private, max-age=900','Vary':'Cookie','ETag':'"'+ae.hashlib.sha256(data).hexdigest()+'"'})
    except Exception as error:return preview_failure(error)


def preview_failure(error):
    from files_upload_api import FilesUploadError
    LOG.warning('REVIEW_PREVIEW request_failed type=%s',type(error).__name__)
    if isinstance(error,FilesUploadError):
        return JSONResponse(dict(error=str(error)),status_code=error.status_code,headers=api.HEADERS)
    return api.failure(error)


def current_previews(connect, entries):
    """One small identity read per HTTP batch; no manifests, signing or provider I/O.

    Actor snapshots amortize expensive metadata, but cannot authorize an image
    after another process resets/unmaps the product or changes its preparation.
    """
    if not entries:return set()
    with review_read(connect) as conn,conn.cursor() as cur:
        cur.execute("""SELECT q.product_gid,q.preparation_hash,m.dropbox_file_id,
            to_jsonb(q)->'replacement' AS replacement,to_jsonb(q)->'reset_cancellation' AS cancellation
            FROM auto_edition_onboarding q LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
            WHERE q.product_gid=ANY(%s)""",(list(dict.fromkeys(pid for pid,_,_ in entries)),))
        current={r['product_gid']:r for r in cur.fetchall()}
    valid=set()
    for pid,digest,record in entries:
        row=current.get(pid) or {};reset=row.get('replacement') or {};cancel=row.get('cancellation') or {}
        if (row.get('preparation_hash')==digest and row.get('dropbox_file_id')==record['manifest']['source']['file_id']
            and not reset.get('manual_required') and reset.get('stage') not in ('Discovering','Queued','Preparing')
            and cancel.get('stage') not in ('Cancelling','Confirmed')):valid.add((pid,digest))
    return valid


def prepared_fetch():
    assets=None
    def fetch(*args):
        nonlocal assets
        if assets is None:assets=runtime.storage()
        result=assets.fetch(*args);fetch.review_timings=assets.timings;return result
    return fetch


def preview_entries(user,items,connect):
    """Renew expired actor-scoped metadata in one bounded read, never old assets.

    An unchanged immutable identity can reuse its persisted thumbnail after
    cache expiry/restart. Changed preparations require a fresh visual review.
    """
    pairs=[];entries=[];failures=[];renew=[]
    for item in items:
        if not isinstance(item,dict) or set(item)!={'product_gid','hash'}:raise ValueError('Exact preview identities required.')
        pid=statuses.identity(item['product_gid']);digest=item['hash']
        if not re.fullmatch('[a-f0-9]{64}',str(digest)):raise ValueError('Exact preparation hash required.')
        pairs.append((pid,digest))
    with snapshot_lock:
        for pid,digest in pairs:
            value=snapshots.get((str(user['id']),pid,digest))
            if not value or value[0]<time.monotonic():renew.append(pid)
    if renew:listing(connect,list(dict.fromkeys(renew)),user)
    with snapshot_lock:
        for pid,digest in pairs:
            value=snapshots.get((str(user['id']),pid,digest))
            if not value or value[0]<time.monotonic():
                failures.append(dict(product_gid=pid,hash=digest,jpeg=None,state='Unavailable',error='Preparation changed or is no longer available for review. Refresh the review list.'))
            else:entries.append((pid,digest,value[1]))
    valid=current_previews(connect,entries)
    for pid,digest,record in list(entries):
        if (pid,digest) not in valid:
            entries.remove((pid,digest,record))
            with snapshot_lock:snapshots.pop((str(user['id']),pid,digest),None)
            failures.append(dict(product_gid=pid,hash=digest,jpeg=None,state='Unavailable',error='Preparation changed or design was reset. Refresh the review list.'))
    return entries,failures


def cached_previews(entries,store,raw=False,prefetch=False):
    """One bounded cache read; the binary client can enqueue disposable misses without waiting."""
    response=[];missing={}
    for pid,digest,record in entries:
        try:
            evidence(record);key=thumbnails.key(record);identity=ae.fingerprint(key)
            with thumbnails.lock:data=thumbnails.entries.get(key)
            row=dict(product_gid=pid,hash=digest,jpeg=None);response.append(row)
            if data:row['jpeg']=data if raw else base64.b64encode(data).decode('ascii')
            else:
                with preview_builds.lock:pending=preview_builds.pending.get(key[0])
                if pending and not pending[0].done():row['state']='Loading'
                else:missing[identity]=(key,row)
        except (ValueError,KeyError,TypeError):
            response.append(dict(product_gid=pid,hash=digest,jpeg=None))
    if missing:
        try:stored=store.get_many(list(missing))
        except Exception as error:
            LOG.warning('REVIEW_PREVIEW cache_batch_failed type=%s',type(error).__name__)
            stored={}
        for identity,data in stored.items():
            key,row=missing[identity]
            if not thumbnails.valid(data,key[1]):continue
            thumbnails.remember(key,data)
            row['jpeg']=data if raw else base64.b64encode(data).decode('ascii')
        with preview_builds.lock:
            for key,row in missing.values():
                pending=preview_builds.pending.get(key[0])
                if not row['jpeg'] and pending and not pending[0].done():row['state']='Loading'
    if raw and not prefetch:
        records={(pid,digest):record for pid,digest,record in entries}
        for row in response:
            if row['jpeg']:continue
            fetch=prepared_fetch()
            try:
                data=preview_builds.read(records[(row['product_gid'],row['hash'])],fetch,300,store,True)
                if data:row['jpeg']=data
                else:row['state']='Loading'
            except (ValueError,KeyError,TypeError) as error:row.update(state='Unavailable',error=str(error))
            except Exception:row.update(state='Unavailable',error='Preview temporarily unavailable. Retry Preview.')
    return response


async def previews_api(request):
    try:
        import files_upload_api as files
        from auto_editions_review_thumbnails import ReviewBuildStore as PreviewStore
        from auto_editions_bulk_runtime import connection
        started=time.perf_counter();user=await actor(request);body=await files._json_body(request)
        if set(body)-{'items','binary','prefetch'} or not isinstance(body.get('items'),list) or not 1<=len(body['items'])<=8:
            raise ValueError('At most eight cached preview identities required.')
        import supabase_backend as db
        entries,failures=await run_in_threadpool(preview_entries,user,body['items'],db.read_connection)
        binary=body.get('binary') is True
        rows=await run_in_threadpool(cached_previews,entries,PreviewStore(connection),binary,body.get('prefetch') is True)
        rows.extend(failures)
        elapsed=round((time.perf_counter()-started)*1000,2)
        if binary:
            boundary='sc-review-preview';parts=[];meta=[]
            for index,row in enumerate(rows):
                data=row['jpeg'];meta.append(dict(product_gid=row['product_gid'],hash=row['hash'],part=str(index) if data else None,state=row.get('state'),error=row.get('error')))
                if data:parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{index}"; filename="preview.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+data+b'\r\n')
            parts.insert(0,f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()+json.dumps(dict(rows=meta,duration_ms=elapsed)).encode()+b'\r\n')
            parts.append(f'--{boundary}--\r\n'.encode())
            return Response(b''.join(parts),media_type=f'multipart/form-data; boundary={boundary}',headers={**api.HEADERS,'Server-Timing':f'cached-previews;dur={elapsed}'})
        return JSONResponse(dict(rows=rows,hits=sum(bool(r['jpeg']) for r in rows),duration_ms=elapsed),headers={**api.HEADERS,'Server-Timing':f'cached-previews;dur={elapsed}'})
    except Exception as error:return preview_failure(error)


async def approve_api(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        user=await actor(request,write=True);body=await files._json_body(request)
        if set(body)!={'items','confirm_visual_quality','request_id'} or body['confirm_visual_quality'] is not True or not isinstance(body['items'],list) or not 1<=len(body['items'])<=1000:
            raise ValueError('Confirm the selected TEST compositions once before approval.')
        for item in body['items']:
            if not isinstance(item,dict) or set(item)!={'product_gid','hash'}:raise ValueError('Exact review identities required.')
            statuses.identity(item['product_gid'])
            if not re.fullmatch('[a-f0-9]{64}',str(item['hash'])):raise ValueError('Exact preparation hashes required.')
        from auto_editions_bulk_jobs import ReviewJobs
        from auto_editions_bulk_runtime import connection,wake
        jobs=ReviewJobs(connection)
        key=await run_in_threadpool(jobs.submit,str(user['id']),body['request_id'],body['items'],admission)
        result=await run_in_threadpool(jobs.progress,str(user['id']),batch_id=key)
        wake.set()
        return JSONResponse({**result,'batch_id':key,'accepted':True,'print_ready':False},status_code=202,headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def progress_api(request):
    try:
        import files_upload_api as files
        from auto_editions_bulk_jobs import ReviewJobs
        from auto_editions_bulk_runtime import connection
        user=await actor(request);body=await files._json_body(request)
        if set(body) not in ({'batch_id'},{'product_gids'},{'product_gids','watch'}):raise ValueError('Batch identity or bounded catalogue required.')
        result=await run_in_threadpool(ReviewJobs(connection).progress,str(user['id']),active_review_only='product_gids' in body,**body)
        committed=[r['product_gid'] for r in result['rows'] if r['state']=='Approved']
        if committed:
            # Historical job success must never mask a newer source/quality change.
            current=await run_in_threadpool(statuses.batch,connection,committed,writable=True)
            by_id={r['product_gid']:r for r in current['rows']}
            for row in result['rows']:
                if row['product_gid'] in by_id:
                    value=by_id[row['product_gid']]
                    row.update(current_status=value['status'],current_hash=value['preparation_hash'],current_reason=value['reason'])
        return JSONResponse(result,headers=api.HEADERS)
    except Exception as error:return api.failure(error)


ROUTES=(('/auto-editions/bulk',page,('GET',)),('/api/auto-editions/bulk/list',list_api,('POST',)),
        ('/api/auto-editions/bulk/image',image_api,('GET',)),('/api/auto-editions/bulk/previews',previews_api,('POST',)),('/api/auto-editions/bulk/approve',approve_api,('POST',)),('/api/auto-editions/bulk/progress',progress_api,('POST',)))
