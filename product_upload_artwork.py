"""Server PSD adapter before the unchanged Mockups generation engine.

Decode the full-resolution saved PSD composite, never a thumbnail. Photoshop,
native host grants and Companion are not involved. Cache bytes are disposable.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from time import perf_counter
from datetime import datetime, timezone

from product_upload_intake import Intakes

_slots = threading.BoundedSemaphore(1)


def source(row):
    m = row['data']['source']
    return dict(template_id='product-upload:'+m['id'],file_id=m['id'],revision=m['rev'],content_hash=m['content_hash'])


def settings(connect):
    import image_factory as factory
    from PIL import __version__
    from auto_editions_colour_store import configuration
    root=Path(__file__).parent
    payload=dict(version='server-psd-composite-v1',pillow=__version__,edge=factory.MAX_WORKING_EDGE,
                 colour=configuration(connect),code={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                 for name in ('product_upload_artwork.py','image_factory.py','auto_editions_colour_source.py','auto_editions_colour_policy.py')})
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
        from auto_editions_colour_policy import resolve
        config=configuration(connect)
        icc,policy=resolve(source(row),policies=config['policies'],memberships=config['memberships'],default_group=config['default_group'])
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
        try:converted.save(destination,format='PNG',icc_profile=srgb.tobytes())
        finally:converted.close()
    if destination.stat().st_size>factory.MAX_UPLOAD_SIZE_BYTES:raise ValueError('Prepared artwork exceeds the existing Mockups image limit.')
    return dict(source_profile_sha256=hashlib.sha256(icc).hexdigest(),policy=policy,operation='server ICC conversion to sRGB',decoder='Pillow full-resolution PSD saved composite')


def prepare(connect, provider, key, actor):
    import image_factory as factory
    from auto_editions import file_hash
    if not key:raise ValueError('Select an exact Dropbox PSD workflow first.')
    store=Intakes(connect);row=store.read(key,actor)
    if not row or row['data'].get('workflow_version')!=3:raise ValueError('Select a Dropbox PSD first.')
    processing=settings(connect);current(provider,row)
    if not _slots.acquire(blocking=False):
        raise ValueError('The server is preparing another artwork. Retry preparation shortly.')
    started=perf_counter()
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL idle_in_transaction_session_timeout = '5min'")
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('server-product-artwork:'+json.dumps(source(row),sort_keys=True),))
            with store.locked(key,actor) as (value,_):value['data']['server_artwork']=dict(state='Preparing',source=source(row),settings=processing)
            ready=cached(row,processing);reused=bool(ready)
            if not ready:
                target=folder(row,processing)
                with tempfile.TemporaryDirectory(dir=target.parent,prefix='staging-') as temporary:
                    stage=Path(temporary);psd=stage/'selected.psd'
                    from auto_editions_source_limits import check_source
                    check_source(row['data']['source']['size'],stage)
                    provider.download(row['data']['source'],psd)
                    if psd.stat().st_size!=row['data']['source']['size'] or file_hash(psd,dropbox=True)!=row['data']['source']['content_hash']:
                        raise ValueError('Downloaded PSD bytes do not match the selected Dropbox revision.')
                    colour=decode(psd,stage/'artwork.png',row,connect)
                    factory.create_preview_file(stage/'artwork.png',stage,'preview.webp')
                    current(provider,row)
                    receipt=dict(source=source(row),settings=processing,colour=colour,
                        hashes={n:file_hash(stage/n) for n in ('artwork.png','preview.webp')})
                    target.mkdir(exist_ok=True)
                    for name in ('artwork.png','preview.webp'):os.replace(stage/name,target/name)
                    (target/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
                    ready=target,receipt
            current(provider,row)
            if settings(connect)!=processing:raise ValueError('Artwork processing settings changed. Retry preparation.')
            with store.locked(key,actor) as (value,_):
                if source(value)!=source(row):raise ValueError('Selection changed during preparation.')
                value['data']['server_artwork']=dict(state='Ready',source=source(row),settings=processing,reused=reused,
                    elapsed_ms=round((perf_counter()-started)*1000,2),completed_at=datetime.now(timezone.utc).isoformat())
                value['data'].update(state='Ready',reason='')
    except Exception as error:
        with store.locked(key,actor) as (value,_):
            value['data']['server_artwork']=dict(state='Failed',reason=str(error) if isinstance(error,(ValueError,factory.MemoryLimitExceededError)) else 'Server artwork preparation failed. Retry or review the PSD saved composite.',source=source(row))
        if isinstance(error,factory.MemoryLimitExceededError):raise ValueError(str(error)) from error
        raise
    finally:_slots.release()
    return store.read(key,actor)


def ready(row, connect, provider):
    spec=row['data'].get('server_artwork',{})
    processing=settings(connect);current(provider,row)
    value=cached(row,processing)
    if spec.get('state')!='Ready' or spec.get('source')!=source(row) or spec.get('settings')!=processing or not value:
        raise ValueError('Prepare this exact PSD revision on the server first.')
    return value[0]


def ensure_ready(row, connect, provider):
    current(provider,row)
    try:return row,ready(row,connect,provider)
    except ValueError:
        # Disposable server caches can expire or be lost on restart. Rebuild
        # from the pinned source instead of requiring a new product workflow.
        row=prepare(connect,provider,str(row['id']),row['actor_id'])
        return row,ready(row,connect,provider)
