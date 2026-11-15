"""Bounded, public-only image preparation for the insertable frame banner.

Crops verified against sports-cave-wall-artwork.js on 2026-10-08. The theme
first requests a square 2000px CDN image, then crops in a 1000-unit space.
No room compositing or additional frame is applied here.
"""
import hashlib
import io
import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from PIL import Image
from crm_cache import DisplayCache
from crm_tracking import public_https, store_host

CROPS = {'black': (30,151,930,692), 'oak': (27,148,938,696),
         'white': (31,148,934,696), 'unframed': (85,208,822,581)}
REVISION = 'frame-banner-v1'
CACHE = DisplayCache(limit=128, byte_limit=1024*1024)
MAX_BYTES = 12*1024*1024


def frame_name(value):
    value = str(value).lower()
    if 'unframed' in value or 'poster only' in value:return 'unframed'
    matches = [frame for frame in ('black','oak','white') if re.search(r'\b'+frame+r'\b',value)]
    return matches[0] if len(matches)==1 else None


def cdn_image(value):
    if not public_https(value):return ''
    p=urlsplit(value)
    if not ((p.hostname=='cdn.shopify.com' and p.path.startswith('/s/files/1/0722/2332/6515/files/'))
            or (store_host(p.hostname) and p.path.startswith('/cdn/shop/files/'))):return ''
    if not re.search(r'\.(?:png|jpe?g|webp)$',p.path,re.I):return ''
    pairs=parse_qsl(p.query)
    if any(k not in {'v','width','height','crop','format'} for k,_ in pairs):return ''
    return value


def image_identity(value):
    if not cdn_image(value):return None
    p=urlsplit(value)
    # Verified aliases for this store's CDN namespace (never other merchants).
    return (p.path.split('/files/',1)[-1] if '/cdn/shop/' in p.path else p.path.split('/files/',2)[-1],
            dict(parse_qsl(p.query)).get('v',''))


def fetch(url, limit=MAX_BYTES):
    # Callers construct store product URLs or strictly allowlisted Shopify CDN
    # URLs. Never follow redirects to arbitrary hosts or signed/private assets.
    with requests.get(url,timeout=(3,8),stream=True,allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code!=200:raise ValueError('Public asset unavailable')
        result=bytearray()
        for chunk in response.iter_content(65536):
            result.extend(chunk)
            if len(result)>limit:raise ValueError('Public asset exceeds size limit')
        return bytes(result)


class WallRoot(HTMLParser):
    def __init__(self):super().__init__();self.roots=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'data-sc-wall-root' in attrs:self.roots.append(attrs)


def wall_source(product_url, product_id, frame):
    p=urlsplit(product_url)
    if not public_https(product_url) or not store_host(p.hostname):return ''
    if not re.fullmatch(r'/(?:[a-z]{2}(?:-[a-z]{2})?/)?products/[\w-]+/?',p.path):return ''
    url=urlunsplit(('https',p.netloc,p.path,'section_id=sc-wall-preview',''))
    key=('mapping',url,str(product_id))
    roots=CACHE.get(key)
    if roots is None:
        parser=WallRoot();parser.feed(fetch(url,2*1024*1024).decode('utf-8'))
        roots=parser.roots;CACHE.put(key,roots,600)
    pid=str(product_id or '').split('/')[-1]
    for root in roots:
        if not pid or root.get('data-product-id')!=pid:continue
        selected='black' if frame=='unframed' else frame
        url=root.get('data-'+selected+'-url','')
        if frame in ('oak','white') and url==root.get('data-black-url'):return ''
        if url.startswith('//'):url='https:'+url
        # Oak/white fallbacks to black in the website must not become wrong-frame
        # email crops. An exact checkout-image match is required by prepare().
        return cdn_image(url)
    return ''


def crop_image(payload, frame):
    with Image.open(io.BytesIO(payload)) as source:
        if source.width*source.height>20_000_000:raise ValueError('Image too large')
        if source.width!=source.height:raise ValueError('Expected verified square Shopify source')
        x,y,w,h=CROPS[frame];sx=source.width/1000;sy=source.height/1000
        image=source.convert('RGB').resize((1200,round(1200*h/w)),Image.Resampling.LANCZOS,
                    box=(x*sx,y*sy,(x+w)*sx,(y+h)*sy))
        out=io.BytesIO();image.save(out,format='JPEG',quality=88,optimize=True)
        return out.getvalue()


def public_asset(payload,key):
    from services import r2_storage
    base=os.getenv('CRM_EMAIL_ASSET_PUBLIC_BASE_URL','').rstrip('/')
    if not public_https(base) or urlsplit(base).query or urlsplit(base).fragment:return ''
    bucket=r2_storage.get_bucket_name('assets')
    if not bucket or not r2_storage.safe_r2_enabled():return ''
    url=base+'/'+key
    if not r2_storage.object_exists(bucket,key):
        if not r2_storage.upload_bytes(bucket,key,payload,'image/jpeg').get('ok'):return ''
    # Never advertise successful storage before the durable public URL works.
    with requests.get(url,timeout=(3,8),stream=True,allow_redirects=False) as response:
        if response.status_code!=200 or not response.headers.get('Content-Type','').startswith('image/'):return ''
    return url


def prepare(item):
    """Return a verified raster URL or text-only fallback; never mutate context."""
    original=cdn_image(item.get('image',''))
    if not original:return ''
    frame=frame_name(item.get('variant',''))
    identity=(item.get('product_id'),item.get('variant_id'),original,frame,REVISION)
    key=('prepared',*identity)
    result=CACHE.get(key)
    if result is not None:return result
    try:
        payload=fetch(original)
        with Image.open(io.BytesIO(payload)) as img:
            if img.width*img.height>20_000_000:raise ValueError('Image too large')
            img.verify()
    except (requests.RequestException,ValueError,OSError,Image.DecompressionBombError):
        CACHE.put(key,'',30);return ''
    # Original image is the safe fallback, retaining its own aspect ratio.
    result=original
    if frame:
        try:
            source=wall_source(item.get('product_url',''),item.get('product_id'),frame)
            if image_identity(source)==image_identity(original) and source:
                query=dict(parse_qsl(urlsplit(source).query))
                if query.get('width')=='2000' and query.get('height')=='2000' and query.get('crop')=='center':
                    cropped=crop_image(fetch(source),frame)
                    digest=hashlib.sha256(json.dumps([identity,source,CROPS[frame]],sort_keys=True).encode()).hexdigest()
                    result=public_asset(cropped,'email/frame-banner/'+digest+'.jpg') or original
        except (requests.RequestException,ValueError,OSError,Image.DecompressionBombError):pass
    CACHE.put(key,result,600)
    return result
