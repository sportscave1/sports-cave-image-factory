"""Server PSD adapter before the unchanged Mockups generation engine.

Decode the full-resolution saved PSD composite, never a thumbnail. Photoshop,
native host grants and Companion are not involved. Cache bytes are disposable.
"""
import hashlib
import io
import json
import os
import re
from pathlib import Path
import tempfile
import threading
import logging
import traceback
import uuid
from contextlib import contextmanager,ExitStack
from time import perf_counter
from datetime import datetime, timezone, timedelta

from product_upload_intake import Intakes

_slots = threading.BoundedSemaphore(1)
_active = set()
_active_lock = threading.Lock()
_log = logging.getLogger(__name__)
_cache_lock=threading.RLock()
_cache_users={}


@contextmanager
def lease(path):
    """Protect a prepared derivative while its mockups are being rendered."""
    path=Path(path)
    with _cache_lock:
        if not path.is_dir():raise ValueError('Prepared artwork expired. Retry preparation.')
        _cache_users[path]=_cache_users.get(path,0)+1
    try:yield path
    finally:
        with _cache_lock:
            _cache_users[path]-=1
            if not _cache_users[path]:del _cache_users[path]


def prune_cache(keep):
    """Bound only this application's disposable derivatives, never originals."""
    import shutil,time
    root=Path(keep).parent
    with _cache_lock:
        entries=[]
        for path in root.iterdir():
            if path.is_symlink() or not path.is_dir() or not re.fullmatch('[0-9a-f]{64}',path.name):continue
            if path.resolve().parent!=root.resolve():continue
            size=sum(p.stat().st_size for p in path.iterdir() if p.is_file() and not p.is_symlink())
            entries.append((path.stat().st_mtime,path,size))
        total=sum(x[2] for x in entries);count=len(entries)
        for modified,path,size in sorted(entries):
            if path==keep or path in _cache_users:continue
            if count<=8 and total<=256*1024*1024 and time.time()-modified<86400:continue
            shutil.rmtree(path);total-=size;count-=1


@contextmanager
def prepared(row,connect,provider):
    with ExitStack() as stack:
        with _cache_lock:
            current_row,path=ensure_ready(row,connect,provider)
            stack.enter_context(lease(path))
        yield current_row,path


class PreparationError(ValueError):
    """Safe, persisted client diagnosis; raw provider errors never enter the UI."""
    def __init__(self, message, *, status_code=503):
        super().__init__(message)
        self.status_code = status_code


class PreparationBusyError(PreparationError):
    """Another live lease owns this source; wait without marking it failed."""


def diagnosis(error, stage, reference):
    import image_factory
    from dropbox_integration import DropboxOriginalDownloadError
    if isinstance(error, DropboxOriginalDownloadError):return str(error)
    # These stages contain our own validation messages, not provider responses.
    if isinstance(error, image_factory.MemoryLimitExceededError):return str(error)
    if isinstance(error, ValueError) and stage in ('validate source', 'verify download', 'decode original PSD', 'verify preparation'):
        return str(error)
    if isinstance(error, MemoryError):
        message = 'The server ran out of memory while preparing artwork. Retry when other image work finishes.'
    elif stage == 'connect to Dropbox':
        message = 'The Dropbox connection could not be opened for preparation. Check Files access, then retry artwork preparation.'
    elif stage == 'retrieve original PSD':
        kind = type(error).__name__
        if kind in ('AuthError', 'PermissionError'):
            message = 'Dropbox could not authorise the original PSD download. Check Files access, then retry preparation.'
        elif 'Timeout' in kind or 'Connection' in kind:
            message = 'The original PSD download was interrupted. Retry artwork preparation; the selected revision is retained.'
        else:
            message = 'Dropbox could not retrieve the selected original PSD. Check Files access and retry artwork preparation.'
    elif stage in ('write prepared artwork', 'create preview') and isinstance(error, OSError):
        message = 'The server could not write the prepared artwork or preview. Retry; if it repeats, check server temporary storage.'
    else:
        message = 'Artwork preparation stopped during '+stage+'. Retry artwork preparation; if it repeats, share this reference with support.'
    return message+' Reference: '+reference+'.'


def log_failure(error, stage, reference, row):
    # Stack frames and error class provide the failing operation without logging
    # response bodies, credentials, signed URLs, locals or arbitrary error text.
    status=None;request_id=None;cause=error
    # The shared adapter retains the SDK exception as its cause. Record only
    # bounded identifiers/status, never provider bodies or arbitrary messages.
    for _ in range(6):
        candidate=getattr(cause,'status_code',None)
        if type(candidate) is int and 100<=candidate<=599:status=candidate
        candidate=getattr(cause,'request_id',None)
        if isinstance(candidate,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',candidate):request_id=candidate
        cause=getattr(cause,'__cause__',None)
        if cause is None:break
    _log.error('product_artwork_failed reference=%s workflow=%s file_id=%s revision=%s stage=%s error_type=%s provider_status=%s provider_request_id=%s stack=\n%s',
               reference, row['id'], source(row)['file_id'], source(row)['revision'], stage,
               type(error).__module__+'.'+type(error).__name__, status, request_id,
               ''.join(traceback.format_list(traceback.extract_tb(error.__traceback__))))


def source(row):
    m = row['data']['source']
    return dict(template_id='product-upload:'+m['id'],file_id=m['id'],revision=m['rev'],content_hash=m['content_hash'])


def settings(connect):
    import image_factory as factory
    from PIL import __version__
    from auto_editions_colour_store import configuration
    root=Path(__file__).parent
    payload=dict(version='server-psd-composite-v2-fast-lossless-png',pillow=__version__,edge=factory.MAX_WORKING_EDGE,
                 colour=configuration(connect),code={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                 for name in ('product_upload_artwork.py','product_upload_colour.py','image_factory.py','auto_editions_colour_source.py','auto_editions_colour_policy.py')})
    return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()


def folder(row, processing):
    import image_factory
    key=hashlib.sha256(json.dumps([source(row),processing],sort_keys=True).encode()).hexdigest()
    root=image_factory.app_temp_root()/'product-upload-artwork';root.mkdir(exist_ok=True)
    return root/key


def current(provider, row):
    expected=row['data']['source'];actual=provider.metadata_if_present(expected['id'])
    if not actual or any(actual.get(k)!=expected.get(k) for k in ('id','rev','content_hash')):
        raise ValueError('Selected PSD revision changed. Choose its current revision again.')


def cached(row, processing):
    from auto_editions import file_hash
    target=folder(row,processing)
    try:
        if target.is_symlink():return None
        receipt=json.loads((target/'receipt.json').read_text(encoding='utf-8'))
        if receipt['source']!=source(row) or receipt['settings']!=processing:return None
        for name in ('artwork.png','preview.webp'):
            path=target/name
            if path.is_symlink() or not path.is_file() or file_hash(path)!=receipt['hashes'][name]:return None
        os.utime(target,None)
        return target,receipt
    except (OSError,ValueError,KeyError):return None


def decode(psd, destination, row, connect):
    import image_factory as factory
    from PIL import Image, ImageCms
    from auto_editions_colour_source import inspect_psd
    inspection=inspect_psd(psd)
    if inspection['mode']!=3 or inspection['depth']!=8:
        raise ValueError('Choose an RGB, 8-bit PSD supported by the artwork pipeline.')
    # The shared image engine permits truncated image inputs globally. PSD
    # originals must instead contain the entire saved composite plane stream.
    with Path(psd).open('rb') as stream:
        header=stream.read(26);channels=int.from_bytes(header[12:14],'big')
        for _ in range(3):
            raw=stream.read(4)
            if len(raw)!=4:raise ValueError('PSD section framing is truncated.')
            stream.seek(int.from_bytes(raw,'big'),1)
        compression=stream.read(2)
        if compression==b'\0\0':
            required=inspection['width']*inspection['height']*channels
        elif compression==b'\0\1':
            length=inspection['height']*channels*2
            counts=stream.read(length)
            if len(counts)!=length:raise ValueError('PSD composite row table is truncated.')
            required=sum(int.from_bytes(counts[i:i+2],'big') for i in range(0,length,2))
        else:raise ValueError('This PSD saved composite encoding is unsupported by the server decoder. Save a compatible RGB8 PSD.')
        if stream.tell()+required>Path(psd).stat().st_size:raise ValueError('PSD full-resolution saved composite is truncated; a thumbnail cannot replace it.')
    icc=inspection['icc'];policy=None
    if not icc:
        from auto_editions_colour_store import configuration
        from product_upload_colour import resolve_web
        config=configuration(connect)
        icc,policy=resolve_web(source(row),config)
    srgb=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
    factory.validate_image_dimensions(inspection['width'],inspection['height'])
    factory.validate_processing_memory(inspection['width'],inspection['height'])
    with Image.open(psd) as image:
        if image.format!='PSD' or image.size!=(inspection['width'],inspection['height']):
            raise ValueError('PSD composite dimensions do not match its document.')
        # Pillow's PSD decoder reads the document-sized merged image data.
        # It does not use resource thumbnails or attempt layer recomposition.
        image.load()
        image.thumbnail((factory.MAX_WORKING_EDGE,factory.MAX_WORKING_EDGE),Image.Resampling.LANCZOS,reducing_gap=3.0)
        converted=ImageCms.profileToProfile(image,ImageCms.ImageCmsProfile(io.BytesIO(icc)),srgb,outputMode='RGBA' if image.mode=='RGBA' else 'RGB')
        # This private working PNG is consumed locally by the same WEBP-only
        # factory. Lower DEFLATE effort is lossless; final image encoding and
        # uploaded bytes stay unchanged. The existing 8-entry cache bound stays.
        try:converted.save(destination,format='PNG',icc_profile=srgb.tobytes(),compress_level=1)
        finally:converted.close()
    if destination.stat().st_size>factory.MAX_UPLOAD_SIZE_BYTES:raise ValueError('Prepared artwork exceeds the existing Mockups image limit.')
    return dict(source_profile_sha256=hashlib.sha256(icc).hexdigest(),policy=policy,operation='server ICC conversion to sRGB',decoder='Pillow full-resolution PSD saved composite')


def prepare(connect, provider, key, actor, *, provider_factory=None, progress=None):
    import image_factory as factory
    from auto_editions import file_hash
    if not key:raise ValueError('Select an exact Dropbox PSD workflow first.')
    store=Intakes(connect);row=store.read(key,actor)
    if not row or row['data'].get('workflow_version')!=3:raise ValueError('Select a Dropbox PSD first.')
    with _active_lock:
        if not _slots.acquire(blocking=False):
            if key in _active:return store.read(key, actor)
            raise PreparationError('The server is preparing another artwork. Retry preparation when it finishes.', status_code=409)
        _active.add(key)
    started=perf_counter();stage='load processing settings';attempt=uuid.uuid4().hex
    previous_spec=row['data'].get('server_artwork',{})
    processing=None
    stages=[]
    def report(label,completed=None,total=None):
        if not stages or stages[-1]['stage']!=label:stages.append(dict(stage=label,elapsed_ms=round((perf_counter()-started)*1000,2)))
        if progress:progress(label,completed,total)
    _log.info('product_artwork_start workflow=%s file_id=%s revision=%s attempt=%s',key,source(row)['file_id'],source(row)['revision'],attempt[:12])

    try:
        report('Checking prepared artwork');processing=settings(connect)
        if provider is None:
            stage='connect to Dropbox'
            from product_upload_services import Dropbox
            provider=(provider_factory or Dropbox)()
        stage='validate source';current(provider,row)
        stage='acquire preparation lock'
        cache_key=json.dumps([source(row),processing],sort_keys=True)
        with connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('server-product-artwork:'+json.dumps(source(row),sort_keys=True),))
            cur.execute("""SELECT id FROM product_upload_intakes
                WHERE data->'server_artwork'->>'cache_key'=%s
                AND data->'server_artwork'->>'state'='Preparing'
                AND (data->'server_artwork'->>'lease_until')::timestamptz > now() LIMIT 1""",(cache_key,))
            if cur.fetchone():raise PreparationBusyError('Waiting for the existing source preparation. Retry shortly; no duplicate download was started.',status_code=409)
            with store.locked(key,actor) as (value,_):
                if source(value)!=source(row):raise ValueError('Selection changed before preparation.')
                value['data']['server_artwork']=dict(state='Preparing',source=source(row),settings=processing,attempt=attempt,
                    cache_key=cache_key,lease_until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
                value['data'].update(state='Preparing',reason='')
        # No database transaction spans network, hashing, decoding or rendering.
        pulse_stop=threading.Event()
        def heartbeat():
            while not pulse_stop.wait(45):
                try:
                    with store.locked(key,actor) as (value,_):
                        spec=value['data'].get('server_artwork',{})
                        if spec.get('attempt')!=attempt or spec.get('state')!='Preparing':return
                        spec['lease_until']=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
                except Exception:
                    _log.warning('product_artwork_lease_refresh_failed workflow=%s attempt=%s',key,attempt[:12])
                    return
        pulse=threading.Thread(target=heartbeat,name='product-artwork-lease',daemon=True);pulse.start()
        stage='read prepared cache'
        ready=cached(row,processing);reused=bool(ready)
        if not ready:
            target=folder(row,processing)
            prune_cache(target)
            with tempfile.TemporaryDirectory(dir=target.parent,prefix='staging-') as temporary:
                staging=Path(temporary);psd=staging/'selected.psd'
                from auto_editions_source_limits import check_source
                stage='validate source'
                check_source(row['data']['source']['size'],staging)
                stage='retrieve original PSD'
                report('Downloading PSD',0,row['data']['source']['size'])
                if progress:
                    provider.download(row['data']['source'],psd,progress=lambda done,total:report('Downloading PSD',done,total))
                else:provider.download(row['data']['source'],psd)
                stage='verify download'
                report('Checking file')
                if psd.stat().st_size!=row['data']['source']['size'] or file_hash(psd,dropbox=True)!=row['data']['source']['content_hash']:
                    raise ValueError('Downloaded PSD bytes do not match the selected Dropbox revision.')
                _log.info('product_artwork_download_verified workflow=%s attempt=%s bytes=%s',key,attempt[:12],psd.stat().st_size)
                stage='decode original PSD'
                report('Preparing artwork')
                colour=decode(psd,staging/'artwork.png',row,connect)
                stage='create preview'
                factory.create_preview_file(staging/'artwork.png',staging,'preview.webp')
                stage='verify preparation'
                receipt=dict(source=source(row),settings=processing,colour=colour,
                    hashes={n:file_hash(staging/n) for n in ('artwork.png','preview.webp')})
                stage='write prepared artwork'
                with _cache_lock:
                    target.mkdir(exist_ok=True)
                    for name in ('artwork.png','preview.webp'):os.replace(staging/name,target/name)
                    (target/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
                    prune_cache(target)
                ready=target,receipt
        stage='verify preparation'
        current(provider,row)
        if settings(connect)!=processing:raise ValueError('Artwork processing settings changed. Retry preparation.')
        with store.locked(key,actor) as (value,_):
            if source(value)!=source(row) or value['data']['server_artwork'].get('attempt')!=attempt:raise ValueError('Selection changed during preparation.')
            value['data']['server_artwork']=dict(state='Ready',source=source(row),settings=processing,reused=reused,attempt=attempt,
                elapsed_ms=round((perf_counter()-started)*1000,2),stages=stages,completed_at=datetime.now(timezone.utc).isoformat())
            value['data'].update(state='Ready',reason='')
    except PreparationBusyError:
        raise
    except Exception as error:
        reference=attempt[:12];log_failure(error,stage,reference,row)
        message=diagnosis(error,stage,reference)
        safe=PreparationError(message, status_code=409 if isinstance(error,ValueError) else 503)
        try:
            with store.locked(key,actor) as (value,_):
                spec=value['data'].get('server_artwork',{})
                if source(value)==source(row) and (spec.get('attempt')==attempt or (spec==previous_spec and spec.get('state')!='Preparing')):
                    value['data']['server_artwork']=dict(state='Failed',reason=message,source=source(row),attempt=attempt,reference=reference,stage=stage)
                    value['data'].update(state='Error',reason=message)
            from product_upload_dropbox import status
            from product_upload_intake import public
            safe.upload=public(status(store.read(key,actor),connect))
        except Exception as checkpoint_error:
            log_failure(checkpoint_error,'save failure checkpoint',reference,row)
        raise safe from error
    finally:
        if 'pulse_stop' in locals():pulse_stop.set();pulse.join(timeout=1)
        with _active_lock:
            _active.discard(key)
            _slots.release()
    _log.info('product_artwork_ready workflow=%s attempt=%s reused=%s elapsed_ms=%.2f',key,attempt[:12],reused,(perf_counter()-started)*1000)
    report('Ready',1,1)
    return store.read(key,actor)


def ready(row, connect, provider, *, validated=False):
    spec=row['data'].get('server_artwork',{})
    processing=settings(connect)
    if not validated:current(provider,row)
    value=cached(row,processing)
    if spec.get('state')!='Ready' or spec.get('source')!=source(row) or spec.get('settings')!=processing or not value:
        raise ValueError('Prepare this exact PSD revision on the server first.')
    return value[0]


def ensure_ready(row, connect, provider):
    current(provider,row)
    try:return row,ready(row,connect,provider,validated=True)
    except ValueError:
        # Disposable server caches can expire or be lost on restart. Rebuild
        # from the pinned source instead of requiring a new product workflow.
        row=prepare(connect,provider,str(row['id']),row['actor_id'])
        return row,ready(row,connect,provider,validated=True)
