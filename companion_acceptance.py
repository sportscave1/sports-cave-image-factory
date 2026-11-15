"""One explicitly configured host-only acceptance run in a private SQL schema.

Uses the production durable Sessions, package proofs and immutable Dropbox
publisher. No customer grant, product, allocation, source or approval writes.
Disabled unless a release operator configures an exact UUID run identifier.
"""
from contextlib import contextmanager
import hashlib,json,os,re,time
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import auto_editions as ae
from companion_package_store import Sessions
from companion_package_provider import PackageProvider
from companion_acceptance_fixture import validate_fixture

def configured():
    value=os.getenv('COMPANION_ACCEPTANCE_RUN','')
    return value if re.fullmatch(r'[a-f0-9]{32}',value) else None

@contextmanager
def connect():
    import supabase_backend
    with supabase_backend.connect() as connection:
        with connection.cursor() as cursor:cursor.execute('SET LOCAL search_path TO companion_acceptance_v1')
        yield connection

def provider(run):
    if run!=configured():raise ValueError('Acceptance run is disabled or changed.')
    class Isolated(PackageProvider):
        ROOT=PackageProvider.ROOT+'/Acceptance/'+run
    return Isolated()

def service():return Sessions(connect,provider(configured()))

def run_row(run):
    with connect() as connection,connection.cursor() as cursor:
        cursor.execute('SELECT * FROM runs WHERE id=%s',(run,));row=cursor.fetchone()
        if not row:raise PermissionError('Acceptance run is not owned by this host.')
        return dict(row)

def event(run,key,value):
    with connect() as connection,connection.cursor() as cursor:
        cursor.execute('UPDATE runs SET evidence=evidence || %s::jsonb WHERE id=%s',(json.dumps({key:value}),run))

def process(row,archive):
    from auto_editions_package import unpack
    from auto_editions_cloud import DropboxAssets
    from files_upload_api import _dropbox_context
    import dropbox_integration as integration
    run=row['context']['acceptance_run'];validate_fixture(row['descriptor']['manifest'],run)
    root=archive.parent/'assets';root.mkdir()
    manifest,proofs=unpack(archive,root,row['context']['source'],100,100,resumable=True)
    if ae.fingerprint(manifest)!=row['descriptor']['preparation_hash']:raise ValueError('Acceptance preparation changed.')
    # Independently check deterministic synthetic pixels, not client claims.
    from PIL import Image
    import random
    with Image.open(root/'master.png') as image:
        if image.convert('RGB').tobytes()!=random.Random(20261020).randbytes(1024*768*3):raise ValueError('Synthetic master differs.')
    for number in range(1,101):
        with Image.open(root/manifest['patches'][str(number)]['name']) as image:
            if image.size!=(32,16) or image.convert('RGB').tobytes()!=bytes((number,255-number,number*2%256))*(32*16):raise ValueError('Synthetic edition differs.')
    token=_dropbox_context()['access_token']
    class Assets(DropboxAssets):ROOT=PackageProvider.ROOT+'/Acceptance/'+run+'/Assets'
    assets=Assets(token,integration);digest=ae.fingerprint(manifest)
    state=run_row(run)['evidence']
    if not state.get('partial_publication_injected'):
        path=root/manifest['master']['name'];destination=assets.path(digest,path.name)
        integration.ensure_folder_path(token,destination.rsplit('/',1)[0],root_path='/Sportscave Team Folder')
        meta=integration.get_metadata_if_exists(token,destination) or integration.upload_local_file(token,destination,path,conflict='cancel')
        if meta.get('content_hash')!=ae.file_hash(path,dropbox=True):raise ValueError('Partial publication receipt differs.')
        event(run,'partial_publication_injected',dict(file_id=meta['id'],revision=meta['rev']))
        raise ConnectionError('Isolated acceptance: retry after durable master publication.')
    receipts=assets.publish_preparation(manifest,root)
    # Fresh independent provider listing, followed by downloads of every asset.
    checked=0;download_bytes=0
    for asset in [manifest['master']]+list(manifest['patches'].values()):
        destination=assets.path(digest,asset['name']);meta,response=integration.get_file_response(token,destination)
        try:
            h=hashlib.sha256();size=0
            for block in response.iter_content(chunk_size=1024*1024):h.update(block);size+=len(block)
            receipt=next(r for r in receipts['assets'] if r['name']==asset['name'])
            if (h.hexdigest()!=asset['sha256'] or size!=receipt['bytes'] or meta['id']!=receipt['file_id'] or meta['rev']!=receipt['revision']):raise ValueError('Independent cloud receipt verification failed.')
            checked+=1;download_bytes+=size
        finally:response.close()
    from auto_editions_package_limits import LEGACY_BYTES
    result=dict(status='Cloud Ready',scope='Isolated acceptance only',preparation_hash=digest,verified_assets=checked,
        package_bytes=archive.stat().st_size,acceptance_scope='large-v2' if archive.stat().st_size>LEGACY_BYTES else 'v1',
        proof_count=len(proofs),receipts=receipts,timings=dict(provider_verification_bytes=download_bytes,**assets.timings))
    event(run,'completed',result)
    return result

def run_one():
    if not configured():return False
    from auto_editions_setup_api import IMPORT_LOCK
    if not IMPORT_LOCK.acquire(blocking=False):return False
    try:return service().run_one(process)
    finally:IMPORT_LOCK.release()

def cleanup_probe(store,owner,host,context,descriptor):
    from auto_editions_setup_api import IMPORT_LOCK
    with IMPORT_LOCK:return _cleanup_probe(store,owner,host,context,descriptor)

def _cleanup_probe(store,owner,host,context,descriptor):
    # Only a second tiny isolated session is expired; active main data retained.
    payload=b'isolated-expiry-proof';d={**descriptor,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'chunks':[hashlib.sha256(payload).hexdigest()]}
    state=store.create(owner,host,'https://isolated.acceptance',{**context,'cleanup_probe':True},d)
    store.chunk(state['id'],owner,host,0,payload,d['chunks'][0]);store.finalize(state['id'],owner,host)
    with connect() as connection,connection.cursor() as cursor:
        cursor.execute("UPDATE companion_package_uploads SET expires_at=now()-interval '1 second' WHERE id=%s",(state['id'],))
    count=store.cleanup()
    if count!=1 or store.provider.metadata_if_present(store.provider.destination(state['id'])) is not None:raise ValueError('Isolated cleanup failed.')
    return dict(expired_sessions=count,active_main_preserved=True)

async def host(request):
    from auto_editions_onboarding_api import preparation_actor
    import auto_editions_api as api
    try:
        run=configured()
        if not run:raise ValueError('Isolated acceptance is disabled.')
        if not request.headers.get('x-sports-cave-preparation-host'):raise PermissionError('Registered host required.')
        user=await preparation_actor(request)
        import os_accounts
        if user.get('role')!=os_accounts.ROLE_ADMIN:raise PermissionError('Acceptance administrator required.')
        host_hash=hashlib.sha256(request.headers['x-sports-cave-preparation-host'].encode()).hexdigest();owner=str(user['id'])
        action=request.path_params['acceptance_action'];store=await run_in_threadpool(service)
        if action=='ping':
            from companion_package_api import capability
            from companion_package_identity import generation
            return JSONResponse(dict(ok=True,run=run,upload_protocol=capability(),generation=generation(),large_package_fixture=True),headers=api.HEADERS)
        if action=='create':
            from files_upload_api import _json_body
            descriptor=await _json_body(request);validate_fixture(descriptor['manifest'],run)
            from auto_editions_package_limits import LEGACY_BYTES
            if not (8*1024**2<descriptor['bytes']<12*1024**2 or LEGACY_BYTES<descriptor['bytes']<LEGACY_BYTES+16*1024**2):
                raise ValueError('Bounded small or oversized isolated acceptance fixture required.')
            context=dict(source=descriptor['manifest']['source'],number=100,total=100,acceptance_run=run)
            def create():
                with connect() as connection,connection.cursor() as cursor:
                    cursor.execute('INSERT INTO runs(id,owner_id,host_hash) VALUES(%s,%s,%s) ON CONFLICT(id) DO NOTHING',(run,owner,host_hash))
                r=run_row(run)
                if r['owner_id']!=owner or r['host_hash']!=host_hash:raise PermissionError('Acceptance run owner changed.')
                return store.create(owner,host_hash,str(request.base_url).rstrip('/'),context,descriptor)
            result=await run_in_threadpool(create)
        else:
            r=await run_in_threadpool(run_row,run)
            if r['owner_id']!=owner or r['host_hash']!=host_hash:raise PermissionError('Acceptance belongs to another host.')
            key=request.query_params.get('id','')
            from companion_package_api import private
            row=await run_in_threadpool(private,store,key,owner,host_hash)
            if row['context'].get('acceptance_run')!=run or row['context'].get('cleanup_probe'):raise PermissionError('Exact main acceptance session required.')
            if action=='status':result=await run_in_threadpool(store.status,key,owner,host_hash)
            elif action=='chunk':
                from companion_package_identity import CHUNK
                length=request.headers.get('content-length','');offset=request.headers.get('x-sc-chunk-offset','')
                if not length.isdecimal() or not 0<int(length)<=CHUNK or not offset.isdecimal():raise ValueError('Bounded chunk required.')
                data=bytearray()
                async for block in request.stream():
                    if len(data)+len(block)>int(length):raise ValueError('Chunk too large.')
                    data.extend(block)
                if len(data)!=int(length):raise ValueError('Incomplete chunk.')
                result=await run_in_threadpool(store.chunk,key,owner,host_hash,int(offset),data,request.headers.get('x-sc-chunk-sha256',''))
                if not r['evidence'].get('lost_chunk_ack'):
                    await run_in_threadpool(event,run,'lost_chunk_ack',dict(offset=result['offset']))
                    return JSONResponse(dict(error='Isolated acceptance lost acknowledgement'),status_code=503,headers=api.HEADERS)
            elif action=='finalize':
                result=await run_in_threadpool(store.finalize,key,owner,host_hash)
                import auto_editions_runtime
                auto_editions_runtime._wake.set()
                if not r['evidence'].get('lost_finalize_ack'):
                    await run_in_threadpool(event,run,'lost_finalize_ack',True)
                    return JSONResponse(dict(error='Isolated acceptance lost finalise acknowledgement'),status_code=503,headers=api.HEADERS)
            elif action=='evidence':
                if row['state']!='Complete' or (row.get('result') or {}).get('status')!='Cloud Ready':raise ValueError('Acceptance is not verified.')
                if not r['evidence'].get('cleanup'):
                    proof=await run_in_threadpool(cleanup_probe,store,owner,host_hash,row['context'],row['descriptor'])
                    await run_in_threadpool(event,run,'cleanup',proof)
                evidence=await run_in_threadpool(run_row,run)
                result=dict(session=store.public(row),evidence=evidence['evidence'])
            else:raise ValueError('Unsupported isolated acceptance action.')
        correlation=request.headers.get('x-sc-transfer-id','')
        headers=dict(api.HEADERS)
        if re.fullmatch('[a-f0-9]{32}',correlation):headers['X-SC-Transfer-ID']=correlation
        if action=='chunk':headers['X-SC-Received-Bytes']=str(len(data))
        return JSONResponse(result,headers=headers)
    except Exception as error:return api.failure(error)

ROUTES=(('/api/auto-editions/acceptance/{acceptance_action}',host,('POST',)),)
