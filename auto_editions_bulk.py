"""Explicit TEST visual review. No queue claims, generation, or supplier writes."""
import io
import json
import re
import tempfile
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageCms
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, Response
import auto_editions as ae
import auto_editions_api as api
import auto_editions_runtime as runtime
import auto_editions_status as statuses
from auto_editions_onboarding_store import Queue

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
    path=root/asset['name'];fetch(digest,asset,path);ae.asset_path(root,asset)
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


class ReviewCache:
    """Bounded thumbnail bytes only; one cold decoder at a time, no PSD/JPG renders."""
    def __init__(self,max_bytes=32*1024*1024):
        self.entries=OrderedDict();self.lock=threading.Lock();self.build_lock=threading.Lock();self.max_bytes=max_bytes

    def get(self,record,fetch,width=300):
        if width not in (300,1200):raise ValueError('Fixed review sizes required.')
        m=evidence(record);digest=record['hash'];key=(digest,width)
        with self.lock:
            if key in self.entries:
                self.entries.move_to_end(key);return self.entries[key]
        with self.build_lock:
            with self.lock:
                if key in self.entries:
                    self.entries.move_to_end(key);return self.entries[key]
            with tempfile.TemporaryDirectory(prefix='sc-review-small-') as folder:
                root=Path(folder);r=m['number_region'];profile=None
                for asset,size in ((m['master'],m['dimensions']),(m['patches']['1'],[r[2]-r[0],r[3]-r[1]])):
                    p=inspect_asset(root,asset,size,fetch,digest,record['receipts'],(m.get('colour_evidence') or {}).get('icc_sha256'))
                    if profile is not None and p!=profile:raise ValueError('Number ICC profile differs.')
                    profile=p
                # Resize each existing verified asset before composition. Never build a full canvas/JPG.
                scale=min(1,width/m['dimensions'][0],1200/m['dimensions'][1])
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
                        output=io.BytesIO();display.save(output,'JPEG',quality=78)
                    data=output.getvalue()
                finally:small.close()
            with self.lock:
                while self.entries and sum(map(len,self.entries.values()))+len(data)>self.max_bytes:self.entries.popitem(last=False)
                self.entries[key]=data
            return data


thumbnails=ReviewCache()
# Listing snapshots avoid a metadata query for each image; short lived, bounded, actor scoped.
snapshots=OrderedDict();snapshot_lock=threading.Lock()


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


def listing(connect,ids,user):
    start=time.perf_counter();data=statuses.batch(connect,ids,writable=True)
    candidates=[r for r in data['rows'] if r['status'] in ('Review','Needs Review')]
    found=records(connect,[r['product_gid'] for r in candidates]);public=[]
    with snapshot_lock:
        now=time.monotonic()
        for k in list(snapshots):
            if snapshots[k][0]<now:del snapshots[k]
        for row in candidates:
            record=found.get(row['product_gid']);eligible=False;reason=row['reason']
            if record:
                try:evidence(record);eligible=eligible_state(row)
                except (ValueError,KeyError,TypeError):reason='Preparation proofs, geometry or receipts need attention.'
                key=(str(user['id']),row['product_gid'],record['hash'])
                snapshots[key]=(now+900,record)
            public.append(dict(product_gid=row['product_gid'],hash=row['preparation_hash'],
                               title=record['product_title'] if record else row['product_gid'],eligible=eligible,reason=reason))
        while len(snapshots)>1000:snapshots.popitem(last=False)
    return dict(rows=public,metadata_queries=2,duration_ms=round((time.perf_counter()-start)*1000,2))


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
            p=inspect_asset(Path(folder),a,m['dimensions'] if a==m['master'] else [r[2]-r[0],r[3]-r[1]],assets.fetch,record['hash'],record['receipts'],(m.get('colour_evidence') or {}).get('icc_sha256'))
            if profile is not None and p!=profile:raise ValueError('ICC profiles differ.')
            profile=p
            if ae.file_hash(Path(folder)/a['name'],dropbox=True)!=fresh.get('content_hash'):raise ValueError('Cloud file integrity differs.')
            (Path(folder)/a['name']).unlink()


def approve_one(connect,item,actor):
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
        cur.execute('SELECT edition_total FROM edition_products WHERE shopify_product_gid=%s FOR SHARE',(pid,));products=cur.fetchall()
        cur.execute('SELECT dropbox_file_id FROM product_psd_mappings WHERE shopify_product_gid=%s FOR SHARE',(pid,));mapping=cur.fetchone()
        cur.execute('SELECT * FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(pid,));q=cur.fetchone()
        m=record['manifest']
        if (len(products)!=1 or products[0]['edition_total']!=m['edition_total'] or not mapping or mapping['dropbox_file_id']!=m['source']['file_id']
                or not q or q['preparation_hash']!=digest or q['source']!=m['source'] or q['status'] not in ('Blocked','Cloud Ready')
                or (q.get('replacement') or {}).get('stage') in ('Discovering','Queued','Preparing','Failed')):return 'Skipped'
        cur.execute('SELECT * FROM auto_edition_preparations WHERE hash=%s FOR SHARE',(digest,));current=cur.fetchone()
        if not current or any(current[k]!=record[k] for k in ('manifest','proofs','receipts')):return 'Skipped'
        from auto_editions_quality import enabled
        if enabled():
            cur.execute('SELECT assessment FROM auto_edition_quality_checks WHERE preparation_hash=%s FOR SHARE',(digest,));check=cur.fetchone()
            if check and check['assessment'].get('status') in ('Failed','Needs Repair'):return 'Needs Attention'
        # Source can change while PNG checks run; fence again immediately before the atomic write.
        meta=assets.integration.psd_open_metadata(assets.token,m['source']['file_id'],include_preview=False)
        import psd_directory
        if not psd_directory.approved_file(meta) or ae.source_identity(pid,meta)!=m['source']:return 'Skipped'
        cur.execute('LOCK TABLE auto_edition_layouts IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('SELECT * FROM auto_edition_layouts WHERE product_gid=%s',(pid,));layouts=cur.fetchall()
        if any(l['preparation_hash']!=digest for l in layouts):return 'Needs Attention'
        # Reuse the current production projection inside our locked transaction.
        # This also fences newer visual assessments without opening another connection.
        @contextmanager
        def borrowed():yield conn
        fresh=statuses.batch(borrowed,[pid],writable=True)['rows'][0]
        if fresh['preparation_hash']!=digest:return 'Skipped'
        if not eligible_state(fresh):return 'Skipped' if fresh['status']=='Cloud Ready' else 'Needs Attention'
        evidence(record)  # Colour policy may have been revoked during file validation.
        old=next((l for l in layouts if l['variant_id']=='*'),None)
        if old:
            # Never broaden an existing restricted TEST approval on retry.
            return 'Skipped' if ae.status(m,old['approval'])=='TEST READY' else 'Needs Attention'
        if any(l['approval'].get('allocation_ids') is not None for l in layouts):return 'Needs Attention'
        approval=dict(actor_id=actor,preparation_hash=digest,visual_approved=True,pixel_exact=True,test_only=True)
        if ae.status(m,approval)!='TEST READY':return 'Needs Attention'
        cur.execute('''INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval)
            VALUES(%s,'*',%s,%s::jsonb)''',(pid,digest,json.dumps(approval)))
        cur.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready',reason='',updated_at=now() WHERE product_gid=%s",(pid,))
        cur.execute("INSERT INTO auto_edition_setup_audit(actor_id,preparation_hash,event,detail) VALUES(%s,%s,'approved_test_layout',%s::jsonb)",(actor,digest,json.dumps(dict(variant_id='*',bulk=True))))
        Queue.audit(cur,pid,actor,'visual_quality_approved',dict(hash=digest,test_only=True,bulk=True))
    return 'Approved'


async def page(request):
    try:
        await actor(request)
        return HTMLResponse((Path(__file__).parent/'components/auto_editions/bulk.html').read_text(encoding='utf-8'),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def list_api(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        user=await actor(request)
        body=await files._json_body(request);ids=body.get('product_gids')
        if set(body)!={'product_gids'} or not isinstance(ids,list) or len(ids)>1000:raise ValueError('Bounded product batch required.')
        return JSONResponse(await run_in_threadpool(listing,db.connect,list(dict.fromkeys(statuses.identity(p) for p in ids)),user),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def image_api(request):
    try:
        user=await actor(request);q=request.query_params
        key=(str(user['id']),q.get('product_gid'),q.get('hash'))
        with snapshot_lock:entry=snapshots.get(key)
        if not entry or entry[0]<time.monotonic():raise ValueError('Refresh the gallery to renew preview access.')
        width=1200 if q.get('large')=='1' else 300
        assets=None
        def fetch(*args):
            nonlocal assets
            if assets is None:assets=runtime.storage()
            return assets.fetch(*args)
        data=await run_in_threadpool(thumbnails.get,entry[1],fetch,width)
        return Response(data,media_type='image/jpeg',headers={**api.HEADERS,'Cache-Control':'private, max-age=900','Vary':'Cookie','ETag':'"'+ae.hashlib.sha256(data).hexdigest()+'"'})
    except Exception as error:return api.failure(error)


async def approve_api(request):
    try:
        import files_upload_api as files
        import supabase_backend as db
        user=await actor(request,write=True);body=await files._json_body(request)
        if set(body)!={'items','confirm_visual_quality'} or body['confirm_visual_quality'] is not True or not isinstance(body['items'],list) or not 1<=len(body['items'])<=1000:
            raise ValueError('Confirm the selected TEST compositions once before approval.')
        for item in body['items']:
            if not isinstance(item,dict) or set(item)!={'product_gid','hash'}:raise ValueError('Exact review identities required.')
            statuses.identity(item['product_gid'])
            if not re.fullmatch('[a-f0-9]{64}',str(item['hash'])):raise ValueError('Exact preparation hashes required.')
        start=time.perf_counter();counts={'Approved':0,'Skipped':0,'Needs Attention':0};results=[];seen=set()
        for item in body['items']:
            pid=item['product_gid']
            if pid in seen:continue
            seen.add(pid)
            try:result=await run_in_threadpool(approve_one,db.connect,item,str(user['id']))
            except Exception:
                __import__('logging').getLogger(__name__).exception('Bulk review validation failed product=%s',pid)
                result='Needs Attention'
            counts[result]+=1;results.append(dict(product_gid=pid,result=result))
        return JSONResponse(dict(counts=counts,results=results,duration_ms=round((time.perf_counter()-start)*1000,2),print_ready=False),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


ROUTES=(('/auto-editions/bulk',page,('GET',)),('/api/auto-editions/bulk/list',list_api,('POST',)),
        ('/api/auto-editions/bulk/image',image_api,('GET',)),('/api/auto-editions/bulk/approve',approve_api,('POST',)))
