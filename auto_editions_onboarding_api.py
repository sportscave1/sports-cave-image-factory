"""Product-level one-time preparation through existing private transfer grants."""
import json
import tempfile
import hashlib
import secrets
import re
import time
from pathlib import Path
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse,FileResponse,HTMLResponse
import auto_editions as ae
import auto_editions_api as api
import auto_editions_runtime as runtime
from auto_editions_onboarding_store import Queue


def queue():
    import supabase_backend
    return Queue(supabase_backend.connect)


def host_session_version(user):
    if user['id']=='legacy-master-admin':
        import os,hmac,sc_auth
        key=sc_auth._signing_key(extra_secret=str(os.getenv('SPORTS_CAVE_AUTH_SECRET') or '').strip())
        return hmac.new(key,b'auto-editions-preparation-host-v1',hashlib.sha256).hexdigest()
    return str(user.get('session_version'))


def host_account(row):
    import os_accounts
    import auto_editions_cloud as cloud
    user=(dict(id='legacy-master-admin',role=os_accounts.ROLE_ADMIN,is_active=True,page_permissions=[])
          if row['actor_id']=='legacy-master-admin' else os_accounts.DEFAULT_STORE.get_user(row['actor_id']))
    if not user or host_session_version(user)!=row['session_version']:
        raise PermissionError('Preparation administrator session changed.')
    cloud.require_access(user,setup=True)
    return user


async def preparation_actor(request):
    """A host can claim preparation work, but cannot map, approve or render orders."""
    token=request.headers.get('x-sports-cave-preparation-host')
    if not token:return await api.actor(request,setup=True,write=True)
    if request.headers.get('origin') or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
        raise PermissionError('Invalid preparation host request.')
    if not runtime.enabled():raise PermissionError('Cloud editions are disabled.')
    digest=hashlib.sha256(token.encode()).hexdigest()
    def resolve():
        import os_accounts
        import auto_editions_cloud as cloud
        with queue().connect() as conn,conn.cursor() as cur:
            cur.execute('''SELECT * FROM auto_edition_preparation_hosts WHERE token_hash=%s
                AND revoked_at IS NULL AND expires_at>now()''',(digest,))
            row=cur.fetchone()
            if not row:raise PermissionError('Preparation host expired or was revoked.')
            user=host_account(row)
            cur.execute("""UPDATE auto_edition_preparation_hosts SET last_seen_at=now(),
                expires_at=now()+interval '30 days' WHERE token_hash=%s""",(digest,))
            return user
    return await run_in_threadpool(resolve)


async def heartbeat(request):
    try:
        import files_upload_api as files
        if not request.headers.get('x-sports-cave-preparation-host'):raise PermissionError('Preparation host required.')
        user=await preparation_actor(request)
        body=await files._json_body(request)
        transfer_settings=await run_in_threadpool(host_health,request,body.pop('health',None))
        transfer_ticket=body.pop('transfer_ticket',None)
        if body:
            if set(body)!={'product_gid','lease_token','stage'}:raise ValueError('Exact preparation lease required.')
            await run_in_threadpool(queue().heartbeat,body['product_gid'],body['lease_token'],str(user['id']),body['stage'])
        if transfer_ticket:
            await run_in_threadpool(renew_transfer,request,body,transfer_ticket)
        return JSONResponse(dict(ok=True,transfer_settings=transfer_settings),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


def renew_transfer(request, body, ticket):
    # Renew only an unexpired grant bound to this authenticated host and exact
    # already-renewed product lease. Ticket/secret never enter telemetry.
    import files_upload_api as files
    digest=hashlib.sha256(request.headers['x-sports-cave-preparation-host'].encode()).hexdigest()
    manager=files.NATIVE_TRANSFER_MANAGER
    with manager._lock:
        record=manager._records.get(str(ticket))
        if not record or record.expires_at<=time.monotonic():return False
        setup=getattr(record,'v6_setup',{})
        ctx=setup.get('context',{})
        if setup.get('host_token_hash')!=digest or any(ctx.get(k)!=body.get(k) for k in ('product_gid','lease_token')):
            raise PermissionError('Transfer grant belongs to another host or lease.')
        record.expires_at=time.monotonic()+45*60
    return True


async def colour_configuration(request):
    try:
        if not request.headers.get('x-sports-cave-preparation-host'):raise PermissionError('Preparation host required.')
        await preparation_actor(request)
        import files_upload_api as files
        if await files._json_body(request)!={}:raise ValueError('Read-only policy configuration request required.')
        from auto_editions_colour_store import configuration
        value=await run_in_threadpool(configuration,queue().connect)
        return JSONResponse(value,headers=api.HEADERS)
    except Exception as error:return api.failure(error)


def host_health(request,value):
    if value is None:return
    token=request.headers.get('x-sports-cave-preparation-host')
    if not token:raise PermissionError('Scoped preparation host required for telemetry.')
    from worker_health import record_heartbeat
    instance=hashlib.sha256(token.encode()).hexdigest()[:24]
    record_heartbeat(queue().connect,'Companion',instance,value)
    if value.get('transfer_control',{}).get('capability') in (1,2,3):
        from companion_transfer_control import requested
        return requested(queue().connect,instance)
async def cancellation(request):
    try:
        import files_upload_api as files
        from auto_editions_cancellation import Cancellation
        user=await preparation_actor(request)
        body=await files._json_body(request)
        if set(body)!={'product_gid','lease_token','stopped'} or type(body['stopped']) is not bool:
            raise ValueError('Exact preparation lease and safe-stop acknowledgement required.')
        cancelled=await run_in_threadpool(Cancellation(queue().connect).poll,
            body['product_gid'],body['lease_token'],str(user['id']),body['stopped'])
        return JSONResponse(dict(cancelled=cancelled),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def register_host(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        if await files._json_body(request)!={'confirm_preparation_host':True}:
            raise ValueError('Confirm this computer for background master preparation.')
        token=secrets.token_urlsafe(32)
        with queue().connect() as conn,conn.cursor() as cur:
            cur.execute('''INSERT INTO auto_edition_preparation_hosts(token_hash,actor_id,session_version)
                VALUES(%s,%s,%s)''',(hashlib.sha256(token.encode()).hexdigest(),str(user['id']),host_session_version(user)))
            queue().audit(cur,'preparation-host',str(user['id']),'host_registered')
        return JSONResponse(dict(base_url=str(request.base_url).rstrip('/'),token=token),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def revoke_hosts(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        if await files._json_body(request)!={}:raise ValueError('Revoke your registered preparation hosts.')
        with queue().connect() as conn,conn.cursor() as cur:
            cur.execute('UPDATE auto_edition_preparation_hosts SET revoked_at=now() WHERE actor_id=%s AND revoked_at IS NULL',(str(user['id']),))
            queue().audit(cur,'preparation-host',str(user['id']),'hosts_revoked')
        return JSONResponse(dict(ok=True),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


def candidate(pid,digest):
    registry,_=runtime.stores();record=registry.read(digest)
    if not record or record['manifest']['source']['product_gid']!=pid:
        raise ValueError('Preparation does not belong to this product.')
    with queue().connect() as conn,conn.cursor() as cur:
        cur.execute('''SELECT m.dropbox_file_id,p.edition_total FROM product_psd_mappings m
            JOIN edition_products p ON COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=m.shopify_product_gid
            WHERE m.shopify_product_gid=%s''',(pid,))
        rows=cur.fetchall()
    if len(rows)!=1:raise ValueError('Product identity is unavailable or ambiguous.')
    assets=runtime.storage();row=rows[0]
    meta=assets.integration.psd_open_metadata(assets.token,row['dropbox_file_id'],include_preview=False)
    if (record['manifest']['source']!=ae.source_identity(pid,meta)
            or record['manifest']['edition_total']!=row['edition_total']):
        raise ValueError('Source revision or edition limit changed; prepare again.')
    return record,assets


async def page(request):
    try:
        await api.actor(request,setup=True)
        if __import__('auto_editions_technical').enabled() and request.query_params.get('product_gid'):
            from starlette.responses import RedirectResponse
            from urllib.parse import quote
            return RedirectResponse('/auto-editions/status?product_gid='+quote(request.query_params['product_gid'],safe=''),headers=api.HEADERS)
        html=(Path(__file__).parent/'components/auto_editions/onboarding.html').read_text(encoding='utf-8')
        if __import__('auto_editions_technical').enabled():
            html=html.replace('</head>','<style>#approve,#quality p{display:none!important}</style></head>',1).replace('New or altered artwork needs review; supplier validation is required for production.','Mapped artwork runs required technical checks automatically; supplier certification remains separate.').replace('Review prepared artwork','Preview prepared artwork')
        return HTMLResponse(html,headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def preview(request):
    folder=None
    try:
        await api.actor(request,setup=True)
        record,assets=await run_in_threadpool(candidate,request.query_params.get('product_gid',''),request.query_params.get('hash',''))
        folder=tempfile.TemporaryDirectory(prefix='sc-preparation-review-');root=Path(folder.name)
        def render():
            manifest=record['manifest'];digest=ae.fingerprint(manifest)
            for asset in (manifest['master'],manifest['patches']['1']):assets.fetch(digest,asset,root/asset['name'])
            ae.render_jpg(manifest,root,1,root/'review.jpg')
        await run_in_threadpool(render)
        return FileResponse(root/'review.jpg',media_type='image/jpeg',headers=api.HEADERS,background=BackgroundTask(folder.cleanup))
    except Exception as error:
        if folder:folder.cleanup()
        return api.failure(error)


async def approve(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        if __import__('auto_editions_technical').enabled():raise ValueError('Artwork approval is no longer required. Technical processing continues automatically.')
        body=await files._json_body(request)
        if set(body)!={'product_gid','hash','confirm_visual_quality'} or body['confirm_visual_quality'] is not True:
            raise ValueError('Review composition, plaque, number, faces, borders and enlargement quality first.')
        record,_=await run_in_threadpool(candidate,body['product_gid'],body['hash'])
        registry,_=runtime.stores()
        # The wildcard is explicitly TEST-only and does not certify any supplier SKU.
        # Existing exact variant approvals retain precedence, including V9's scope.
        with queue().connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT status,preparation_hash FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE',(body['product_gid'],))
            current=cur.fetchone()
            if not current or current['preparation_hash']!=body['hash'] or current['status'] not in ('Blocked','Cloud Ready'):
                raise ValueError('Preparation changed. Refresh the review before approval.')
            cur.execute("SELECT preparation_hash FROM auto_edition_layouts WHERE product_gid=%s AND variant_id='*'",(body['product_gid'],))
            old=cur.fetchone()
            await run_in_threadpool(registry.approve,body['hash'],dict(shopify_product_gid=body['product_gid'],shopify_variant_id='*'),
                                    str(user['id']),old['preparation_hash'] if old else '')
            cur.execute("""UPDATE auto_edition_onboarding SET status='Cloud Ready',reason='',updated_at=now()
                WHERE product_gid=%s AND preparation_hash=%s""",(body['product_gid'],body['hash']))
            queue().audit(cur,body['product_gid'],str(user['id']),'visual_quality_approved',{'hash':body['hash'],'test_only':True})
        return JSONResponse(dict(status='Cloud Ready',print_ready=False),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def fail(request):
    try:
        import files_upload_api as files
        from auto_editions_setup_api import grant_context
        setup=await run_in_threadpool(grant_context,request)
        ctx=setup['context']
        if not ctx.get('automatic'):raise ValueError('A product preparation grant is required.')
        body=await files._json_body(request)
        if set(body) not in ({'reason','repair'},{'reason','repair','diagnostic'}) or not isinstance(body['reason'],str) or len(body['reason'])>500:
            raise ValueError('A bounded preparation failure reason is required.')
        await run_in_threadpool(queue().checkpoint,ctx['product_gid'],ctx['lease_token'],setup['actor_id'],
            'Needs PSD Repair' if body['repair'] is True else 'Blocked',body['reason'],diagnostic=body.get('diagnostic'))
        return JSONResponse(dict(ok=True),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


def product_context(pid, token):
    store=queue()
    with store.connect() as conn,conn.cursor() as cur:
        cur.execute("""SELECT q.*,m.dropbox_file_id,p.edition_total AS current_total,p.product_title
            FROM auto_edition_onboarding q
            LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
            JOIN edition_products p ON COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=q.product_gid
            WHERE q.product_gid=%s AND (q.status='Preparing' OR to_jsonb(q)->'replacement'->>'stage'='Preparing') AND q.lease_token=%s
              AND q.lease_until>now()""",(pid,token))
        rows=cur.fetchall()
    if len(rows)!=1:raise ValueError('Preparation lease or product identity is unavailable.')
    row=rows[0]
    pending=row.get('replacement') or {}
    reset_id=None
    if pending.get('stage')=='Preparing':
        from auto_editions_reset import snapshot
        if row['dropbox_file_id']!=(pending['mapping_before'] or {}).get('dropbox_file_id') or snapshot(row)!=pending['previous']:
            raise ValueError('The working design changed during reset.')
        row['file_id']=pending['file_id'];row['source']=pending['source'];reset_id=pending['id']
    elif row['file_id']!=row['dropbox_file_id']:raise ValueError('PSD mapping changed during preparation.')
    total=row['current_total']
    if type(total) is not int or not 1<=total<=1000:raise ValueError('Configure the product edition limit first.')
    assets=runtime.storage()
    meta=assets.integration.psd_open_metadata(assets.token,row['file_id'],include_preview=False)
    from auto_editions_v17 import enabled as continuous
    if continuous():
        import psd_directory as psd
        if not psd.approved_file(meta):
            from product_upload_mapping import approved_upload_source
            if reset_id or not approved_upload_source(store.connect,pid,meta):
                raise ValueError('Mapped source is not an approved original PSD.')
    if reset_id:
        import psd_directory as psd
        if pending.get('expected_source'):
            from auto_editions_reset import repair_candidate
            with store.connect() as conn,conn.cursor() as cur:
                chosen,_,why=repair_candidate(cur,pid,pending)
            if not chosen or not psd.approved_file(meta) or ae.source_identity(pid,meta)!=pending['expected_source']:
                raise ValueError(why or 'Pinned repair source changed before preparation.')
        elif not psd.approved_file(meta) or psd.filename_key(meta['name'][:-4]) not in psd.title_filename_keys(row['product_title']):
            raise ValueError('Reset original PSD no longer matches the product.')
    source=ae.source_identity(pid,meta)
    if row['source'] and row['source']!=source:raise ValueError('Source revision changed. Retry preparation.')
    return dict(automatic=True,product_gid=pid,lease_token=str(token),source=source,
                **({'reset_id':reset_id} if reset_id else {}),
                metadata={k:meta[k] for k in ('id','rev','content_hash','size','name')},
                number=1,total=total,product_title=row['product_title'])


async def summary(request):
    try:
        await api.actor(request,setup=True)
        rows=await run_in_threadpool(queue().rows)
        # Transfer secrets and active lease capabilities never enter the UI listing.
        public=[{**{k:r[k] for k in ('product_gid','product_title','status','reason','preparation_hash','attempts')},
                 'priority':r['priority'],
                 'status':'Deferred' if r['status']=='Awaiting preparation' and r['priority']==0 else r['status']} for r in rows]
        for item,row in zip(public,rows):
            if (row.get('reset_cancellation') or {}).get('stage') in ('Cancelling','Confirmed'):
                item.update(status='Cancelling'+chr(8230),reason='Waiting for Companion to confirm a safe stop; Reset resumes automatically.')
        from auto_editions_status import reason as public_reason
        for item in public:item['reason']=public_reason(item.get('reason'))
        from auto_editions_discovery import enabled,waiting_rows
        if enabled():
            public.extend(await run_in_threadpool(waiting_rows,queue().connect))
        with queue().connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT count(*) AS total,array_agg(shopify_product_gid ORDER BY shopify_product_gid) AS ids,
                (SELECT count(DISTINCT COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id)) FROM edition_products) AS catalogue_total,
                (SELECT jsonb_build_object('at',a.created_at,'product_gid',a.product_gid,
                    'title',(SELECT product_title FROM edition_products p WHERE p.shopify_product_gid=a.product_gid LIMIT 1))
                 FROM auto_edition_onboarding_audit a WHERE a.event='preparation_metrics' ORDER BY a.id DESC LIMIT 1) AS last_success
                FROM product_psd_mappings""")
            inventory=cur.fetchone();mapped=inventory['total']
            cur.execute("""SELECT count(*) AS connected,max(last_seen_at) AS last_seen FROM auto_edition_preparation_hosts
                WHERE revoked_at IS NULL AND expires_at>now()""")
            host=cur.fetchone()
        import auto_editions_v17 as v17
        public=v17.unique_products(public)
        extra={}
        if v17.enabled():
            from auto_editions_status import batch
            from datetime import datetime,timezone
            data=await run_in_threadpool(batch,queue().connect,inventory['ids'] or [])
            authoritative={r['product_gid']:r for r in data['rows']}
            for row in public:
                value=authoritative.get(row['product_gid'])
                if value:row.update(display_status=value['status'],uploaded=value.get('uploaded',False))
            present={r['product_gid'] for r in public}
            for pid,value in authoritative.items():
                if pid not in present:public.append(dict(product_gid=pid,product_title=pid,status='Awaiting preparation',
                    display_status=value['status'],reason=value['reason'],preparation_hash=value['preparation_hash'],attempts=0,priority=1,uploaded=value.get('uploaded',False)))
            mapped_rows=[r for r in public if r['product_gid'] in authoritative]
            current=next((dict(product_gid=r['product_gid'],title=r['product_title'],stage=r.get('display_status'))
                for r in mapped_rows if r.get('display_status') in ('Preparing','Uploading','Recovering')),None)
            seen=host['last_seen']
            connected=bool(seen and (datetime.now(timezone.utc)-seen).total_seconds()<=150)
            extra=dict(counts=v17.dashboard(mapped_rows,mapped),current=current,last_success=inventory['last_success'],
                       processing='Companion Connected' if connected else 'Companion heartbeat stale or disconnected')
        return JSONResponse(dict(rows=public,mapped=mapped,catalogue_total=inventory['catalogue_total'],continuous_enabled=v17.enabled(),**extra,
            host=dict(connected=host['connected'],last_seen=str(host['last_seen']) if host['last_seen'] else None)),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def resume(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        if await files._json_body(request)!={}:raise ValueError('Resume uses existing verified mappings only.')
        count=await run_in_threadpool(queue().seed,str(user['id']))
        from auto_editions_priority import refresh
        await run_in_threadpool(refresh,queue(),str(user['id']))
        return JSONResponse(dict(mapped=count),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def claim(request):
    row=None
    try:
        import files_upload_api as files
        user=await preparation_actor(request)
        body=await files._json_body(request)
        transfer_settings=await run_in_threadpool(host_health,request,body.pop('health',None))
        if body!={}:raise ValueError('Preparation reads authoritative product identities.')
        from auto_editions_priority import refresh
        store=queue()
        import os
        if os.getenv('AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED','').lower()=='true' and not __import__('auto_editions_recovery').enabled():
            from auto_editions_colour_recovery import recover
            # A bad/missing optional policy must never prevent other eligible jobs.
            def colour_recover():
                from auto_editions_colour_store import configuration
                config=configuration(store.connect);auth=files._dropbox_context()
                return recover(store,str(user['id']),dry_run=False,limit=3,**config,
                    read_metadata=lambda fid:files.dropbox_integration.psd_open_metadata(auth['access_token'],fid,include_preview=False))
            try:await run_in_threadpool(colour_recover)
            except Exception as error:
                import logging
                logging.getLogger(__name__).warning('colour_recovery_unavailable error_type=%s',type(error).__name__)
        from auto_editions_discovery import enabled
        if not enabled():
            await run_in_threadpool(refresh,store,str(user['id']),limit=100 if __import__('auto_editions_v17').enabled() else None)
        row=await run_in_threadpool(store.claim,str(user['id']))
        if not row:
            from product_upload_services import enabled as uploads_enabled
            return JSONResponse(dict(grant=None,product_mockup_renders=uploads_enabled(),transfer_settings=transfer_settings),headers=api.HEADERS)
        ctx=await run_in_threadpool(product_context,row['product_gid'],str(row['lease_token']))
        await run_in_threadpool(store.checkpoint,row['product_gid'],str(row['lease_token']),str(user['id']),
                                'Preparing',source=ctx['source'],total=ctx['total'])
        auth=await run_in_threadpool(files._dropbox_context)
        meta=await run_in_threadpool(files.dropbox_integration.psd_open_metadata,auth['access_token'],row['file_id'],include_preview=False)
        if ae.source_identity(row['product_gid'],meta)!=ctx['source']:raise ValueError('Source changed; retry.')
        from product_upload_mapping import approved_upload_source
        record=files.NATIVE_TRANSFER_MANAGER.create_psd(access_token=auth['access_token'],root_path=auth['root_path'],user=user,metadata=meta,
            product_upload=not __import__('psd_directory').approved_file(meta) and approved_upload_source(store.connect,row['product_gid'],meta))
        record.expires_at=time.monotonic()+45*60
        record.v6_setup=dict(context=ctx,actor_id=str(user['id']),session_version=user.get('session_version'),importing=False)
        host=request.headers.get('x-sports-cave-preparation-host')
        if host:record.v6_setup['host_token_hash']=hashlib.sha256(host.encode()).hexdigest()
        return JSONResponse(dict(upload_protocol=__import__('companion_package_api').capability(),package_transport=1,transfer_settings=transfer_settings,context=ctx,product_gid=row['product_gid'],grant=dict(base_url=str(request.base_url).rstrip('/'),
            ticket=record.ticket,secret=record.secret)),headers=api.HEADERS)
    except Exception as error:
        if row:
            try:
                if isinstance(error,(ValueError,PermissionError)):
                    await run_in_threadpool(queue().checkpoint,row['product_gid'],str(row['lease_token']),str(user['id']),'Blocked',str(error))
                else:await run_in_threadpool(queue().defer_owned,row['product_gid'],str(row['lease_token']),str(user['id']))
            except Exception:pass
        return api.failure(error)


async def retry(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        body=await files._json_body(request)
        if set(body)!={'product_gid'}:raise ValueError('Select one failed product.')
        from worker_health_queue import submit
        import uuid
        await run_in_threadpool(submit,queue().connect,body['product_gid'],str(user['id']),str(uuid.uuid4()))
        return JSONResponse(dict(ok=True),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def prepare_now(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        body=await files._json_body(request)
        if set(body)!={'product_gid'}:raise ValueError('Select one mapped product.')
        await run_in_threadpool(queue().prepare_now,body['product_gid'],str(user['id']))
        return JSONResponse(dict(ok=True),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def reconnect(request):
    """Reissue only the same owned preparation lease after a web-service restart."""
    try:
        import files_upload_api as files
        if not request.headers.get('x-sports-cave-preparation-host'):raise PermissionError('Preparation host required.')
        user=await preparation_actor(request);body=await files._json_body(request)
        await run_in_threadpool(host_health,request,body.pop('health',None))
        if set(body)!={'product_gid','lease_token'}:raise ValueError('Exact active preparation lease required.')
        store=queue()
        with store.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM auto_edition_onboarding_audit WHERE product_gid=%s AND actor_id=%s
                AND event='claimed' AND detail->>'lease'=%s""",(body['product_gid'],str(user['id']),body['lease_token']))
            if not cur.fetchone():raise PermissionError('Preparation lease belongs to another operator.')
        completed=await run_in_threadpool(store.completed_receipt,body['product_gid'],body['lease_token'],str(user['id']))
        if completed:
            auth=await run_in_threadpool(files._dropbox_context)
            meta=await run_in_threadpool(files.dropbox_integration.psd_open_metadata,
                auth['access_token'],completed['source']['file_id'],include_preview=False)
            if ae.source_identity(body['product_gid'],meta)!=completed['source']:
                raise ValueError('Source changed; completed receipt cannot acknowledge this package.')
            return JSONResponse(dict(completed=completed),headers=api.HEADERS)
        ctx=await run_in_threadpool(product_context,body['product_gid'],body['lease_token'])
        auth=await run_in_threadpool(files._dropbox_context)
        meta=await run_in_threadpool(files.dropbox_integration.psd_open_metadata,auth['access_token'],ctx['source']['file_id'],include_preview=False)
        if ae.source_identity(body['product_gid'],meta)!=ctx['source']:raise ValueError('Source changed; retained package cannot be reused.')
        from product_upload_mapping import approved_upload_source
        record=files.NATIVE_TRANSFER_MANAGER.create_psd(access_token=auth['access_token'],root_path=auth['root_path'],user=user,metadata=meta,
            product_upload=not __import__('psd_directory').approved_file(meta) and approved_upload_source(store.connect,body['product_gid'],meta))
        record.expires_at=time.monotonic()+45*60
        record.v6_setup=dict(context=ctx,actor_id=str(user['id']),session_version=user.get('session_version'),importing=False,
            host_token_hash=hashlib.sha256(request.headers['x-sports-cave-preparation-host'].encode()).hexdigest())
        return JSONResponse(dict(upload_protocol=__import__('companion_package_api').capability(),package_transport=1,grant=dict(base_url=str(request.base_url).rstrip('/'),ticket=record.ticket,secret=record.secret)),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def discrepancies(request):
    try:
        await api.actor(request,setup=True)
        from auto_editions_discovery import prepared_report
        import files_upload_api as files
        digest=request.query_params.get('preparation_hash','')
        offset=int(request.query_params.get('offset','0'))
        if not 0<=offset<=1000:raise ValueError('Invalid asset offset.')
        def inspect():
            auth=files._dropbox_context()
            return prepared_report(queue().connect,
                lambda fid:files.dropbox_integration.psd_open_metadata(auth['access_token'],fid,include_preview=False),
                digest,offset)
        result=await run_in_threadpool(inspect)
        return JSONResponse(result,headers=api.HEADERS)
    except Exception as error:return api.failure(error)


ROUTES=(('/api/auto-editions/onboarding/colour-configuration',colour_configuration,('POST',)),
        ('/api/auto-editions/onboarding/cancellation',cancellation,('POST',)),('/api/auto-editions/onboarding/heartbeat',heartbeat,('POST',)),
        ('/api/auto-editions/onboarding',summary,('GET',)),
        ('/api/auto-editions/onboarding/discrepancies',discrepancies,('GET',)),
        ('/api/auto-editions/onboarding/prepare-now',prepare_now,('POST',)),
        ('/api/auto-editions/onboarding/reconnect',reconnect,('POST',)),
        ('/api/auto-editions/onboarding/host',register_host,('POST',)),
        ('/api/auto-editions/onboarding/host/revoke',revoke_hosts,('POST',)),
        ('/auto-editions/onboarding',page,('GET',)),
        ('/api/auto-editions/onboarding/preview',preview,('GET',)),
        ('/api/auto-editions/onboarding/approve',approve,('POST',)),
        ('/api/auto-editions/onboarding/fail',fail,('POST',)),
        ('/api/auto-editions/onboarding/resume',resume,('POST',)),
        ('/api/auto-editions/onboarding/claim',claim,('POST',)),
        ('/api/auto-editions/onboarding/retry',retry,('POST',)))
