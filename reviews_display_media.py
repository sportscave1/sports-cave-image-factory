"""Idempotent Dropbox carousel derivatives for previously imported public media."""
from copy import deepcopy
import hashlib
import io
import json


def public_media(store,identity):
    sql="""SELECT m.kind,m.storage FROM sc_review_media m JOIN sc_reviews r ON r.id=m.review_id
        WHERE m.id=%s AND m.status='COPIED' AND m.approved=true AND r.status='PUBLISHED'"""
    if store.connect:return store.q(sql,(identity,),True)
    from supabase_backend import read_connection
    with read_connection() as conn:return conn.execute(sql,(identity,)).fetchone()


def carousel_copy(data):
    from PIL import Image
    if len(data)>1024*1024:raise ValueError('Display source is oversized.')
    with Image.open(io.BytesIO(data)) as original:
        if original.width*original.height>1280*1280:raise ValueError('Invalid display source.')
        image=original.convert('RGB');image.thumbnail((640,640),Image.Resampling.LANCZOS)
        for quality in (82,76,70):
            out=io.BytesIO();image.save(out,'WEBP',quality=quality,method=6)
            if out.tell()<=90000:break
        return {'data':out.getvalue(),'width':image.width,'height':image.height}


def ensure_carousel(store,identity,media,storage=None):
    from reviews_dropbox import ReviewDropboxStorage,asset
    storage=storage or ReviewDropboxStorage();owned=deepcopy(media['storage'])
    group='posters' if media['kind']=='video' else 'variants'
    if (owned.get(group) or {}).get('640'):return owned
    ref,_=asset(owned,'1280',media['kind'])
    if ref['size']>1024*1024:raise ValueError('Display source is oversized.')
    stream=storage.open(ref)
    try:
        data=bytearray()
        for chunk in stream.iter_chunks():
            data.extend(chunk)
            if len(data)>1024*1024:raise ValueError('Display source is oversized.')
    finally:stream.close()
    if hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('Display source changed.')
    result=carousel_copy(bytes(data))
    saved=storage.put(ref['sha256']+'-display-640-v1.webp',result.pop('data'))
    variant={**saved,**result}
    row=store.q("""UPDATE sc_review_media m SET storage=jsonb_set(m.storage,%s::text[],%s::jsonb)
        WHERE m.id=%s AND m.status='COPIED' AND m.approved=true AND m.storage->'original'=%s::jsonb
        AND EXISTS(SELECT 1 FROM sc_reviews r WHERE r.id=m.review_id AND r.status='PUBLISHED') RETURNING m.storage""",
        ([group,'640'],json.dumps(variant),identity,json.dumps(owned['original'])),True)
    if not row:raise ValueError('Media is no longer public.')
    from reviews_public_cache import CACHE
    CACHE.invalidate()
    return row['storage']
