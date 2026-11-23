"""Dropbox-first originals, bounded downloads and lightweight WebP display copies."""
import hashlib
import io
import json
import os
import re
from urllib.parse import urlsplit

import requests
from crm_tracking import public_https

IMPORT_HOSTS={'judgeme.imgix.net','images.judge.me','cdn.judge.me','s3.amazonaws.com','cdn.shopify.com'}

def media_references(value,kind):
    if not value:return []
    if isinstance(value,str):
        value=value.strip()
        if value.startswith('['):
            try:value=json.loads(value)
            except ValueError:raise ValueError('Invalid media URL list.') from None
        else:value=re.split(r'\s*[,;|\n]\s*',value)
    if not isinstance(value,list) or len(value)>10:raise ValueError('Use at most 10 media files per type.')
    result=[];seen=set()
    for entry in value:
        url=(entry.get('url') or entry.get('original') or (entry.get('urls') or {}).get('original') or '') if isinstance(entry,dict) else entry
        if not isinstance(url,str) or not public_https(url):raise ValueError('Media requires a public HTTPS URL.')
        if url not in seen:result.append({'kind':kind,'source_url':url});seen.add(url)
    return result

def validate_file(data,kind):
    limit=50*1024*1024 if kind=='video' else 10*1024*1024
    if not data or len(data)>limit:raise ValueError('Media exceeds the file size limit.')
    if kind=='image':
        from PIL import Image
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.format not in ('JPEG','PNG','WEBP') or im.width*im.height>25000000:raise ValueError()
                im.load();im=im.convert('RGB');out=io.BytesIO();im.save(out,'JPEG',quality=92)
                return out.getvalue(),'image/jpeg','.jpg'
        except Exception:raise ValueError('Use a valid JPEG, PNG or WebP image (up to 25 megapixels).') from None
    if kind!='video':raise ValueError('Invalid media type.')
    if len(data)>12 and data[4:8]==b'ftyp':return bytes(data),'video/mp4','.mp4'
    if data.startswith(b'\x1aE\xdf\xa3'):return bytes(data),'video/webm','.webm'
    raise ValueError('Use an MP4 or WebM video.')

def download(url,kind,session=None,*,preserve_original=False):
    parts=urlsplit(url)
    allowed=IMPORT_HOSTS|{h.strip().lower() for h in os.getenv('REVIEW_MEDIA_IMPORT_HOSTS','').split(',') if h.strip()}
    if not public_https(url) or parts.hostname not in allowed:raise ValueError('Media host is not approved for import.')
    if parts.hostname=='s3.amazonaws.com' and not parts.path.startswith('/me.judge.review-images/'):raise ValueError('Unsupported Judge.me media path.')
    client=session or requests.Session();limit=50*1024*1024 if kind=='video' else 10*1024*1024
    try:
        with client.get(url,stream=True,timeout=(3,20),allow_redirects=False) as response:
            if response.status_code!=200:raise ValueError()
            if int(response.headers.get('Content-Length','0'))>limit:raise ValueError()
            data=bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>limit:raise ValueError()
        validated=validate_file(data,kind)
        if preserve_original and kind=='image':
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                mime,ext={'JPEG':('image/jpeg','.jpg'),'PNG':('image/png','.png'),'WEBP':('image/webp','.webp')}[im.format]
            return bytes(data),mime,ext
        return validated
    except Exception:raise ValueError('Media could not be downloaded and validated.') from None

def webp_variants(data,prefix=''):
    from PIL import Image,ImageOps
    result={}
    with Image.open(io.BytesIO(data)) as original:
        image=ImageOps.exif_transpose(original).convert('RGBA' if 'A' in original.getbands() else 'RGB')
        for size in (320,1280):
            frame=image.copy();frame.thumbnail((size,size),Image.Resampling.LANCZOS)
            for quality in (82,76,70):
                out=io.BytesIO();frame.save(out,'WEBP',quality=quality,method=6)
                if len(out.getvalue())<=(40000 if size==320 else 250000):break
            result[str(size)]={'data':out.getvalue(),'width':frame.width,'height':frame.height,'suffix':prefix+str(size)+'.webp'}
    return result

def video_poster(data,extension):
    import subprocess,tempfile
    from pathlib import Path
    import imageio_ffmpeg
    with tempfile.TemporaryDirectory(prefix='review-video-') as folder:
        path=Path(folder)/('upload'+extension);path.write_bytes(data)
        try:
            result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(path),'-frames:v','1','-vf','scale=1280:1280:force_original_aspect_ratio=decrease','-f','image2pipe','-vcodec','png','pipe:1'],capture_output=True,timeout=30,check=True)
            return result.stdout
        except Exception:raise ValueError('Video preview could not be generated. Use a playable MP4 or WebM.') from None

def prepare_assets(data,kind):
    # Validate without replacing the original upload bytes.
    _,mime,extension=validate_file(data,kind)
    if kind=='image':
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:mime,extension={'JPEG':('image/jpeg','.jpg'),'PNG':('image/png','.png'),'WEBP':('image/webp','.webp')}[im.format]
    return mime,extension

def save_owned(data,kind,storage=None):
    from reviews_dropbox import ReviewDropboxStorage
    mime,extension=prepare_assets(data,kind);body=bytes(data);digest=hashlib.sha256(body).hexdigest()
    storage=storage or ReviewDropboxStorage()
    # Original MUST be durably received by Dropbox before any display processing.
    original=storage.put(digest+'-original'+extension,body)
    source={'provider':'dropbox','original':original}
    preview=video_poster(body,extension) if kind=='video' else body
    variants=webp_variants(preview,'poster-' if kind=='video' else '')
    group='posters' if kind=='video' else 'variants';source[group]={}
    for size,value in variants.items():
        source[group][size]={**storage.put(digest+'-'+value['suffix'],value['data']),'width':value['width'],'height':value['height']}
    if kind=='video':source['video_format']=extension.lstrip('.')
    return {'object_key':original['id'],'sha256':digest,'size_bytes':len(body),'mime_type':mime,'storage':source}

def tick_media(store):
    """One resumable transfer; no source file is removed or published automatically."""
    with store.db() as conn:
        row=conn.execute("""SELECT * FROM sc_review_media WHERE status IN ('QUEUED','FAILED') AND attempts<3
          AND (lease_until IS NULL OR lease_until<now()) ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
        if not row:return None
        claim=conn.execute("UPDATE sc_review_media SET attempts=attempts+1,lease_until=now()+interval '5 minutes' WHERE id=%s RETURNING attempts",(row['id'],)).fetchone()['attempts']
    try:
        body,_,_=download(row['source_url'],row['kind'],preserve_original=True);owned=save_owned(body,row['kind'])
        store.q("""UPDATE sc_review_media SET object_key=%s,sha256=%s,size_bytes=%s,mime_type=%s,storage=%s::jsonb,
          status='COPIED',lease_until=NULL,error_code=NULL WHERE id=%s AND attempts=%s""",
          (owned['object_key'],owned['sha256'],owned['size_bytes'],owned['mime_type'],json.dumps(owned['storage']),row['id'],claim))
    except Exception:
        store.q("UPDATE sc_review_media SET status='FAILED',lease_until=NULL,error_code='transfer_failed' WHERE id=%s AND attempts=%s",(row['id'],claim))
    return row['id']
