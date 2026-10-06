"""Anonymous confirmation and capability-protected CRM actions; no public database reads."""
import hashlib
import html
import io
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, urlencode, urlunsplit, parse_qsl

from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, Response

import wall_preview_api as archive
import wall_preview_crm_store as store
import wall_preview_identity as identity

LOG = logging.getLogger(__name__)
BASE = 'https://sports-cave-image-factory.onrender.com'
CONSENT_TEXT = 'By selecting Send, you’ll also receive Sports Cave collector emails. Unsubscribe anytime.'
CONSENT_VERSION = 'wall_preview_hd_email_send_v1'


def timestamp(value):
    if not value:return None
    if len(str(value))>40:raise ValueError('Invalid preview timestamp.')
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None or result>datetime.now(timezone.utc)+timedelta(minutes=5):
        raise ValueError('Invalid preview timestamp.')
    return result


def product_url(value, variant=''):
    parts = urlsplit(str(value or ''))
    if parts.scheme != 'https' or parts.netloc not in {'sportscaveshop.com','www.sportscaveshop.com'} or not parts.path.startswith('/products/'):
        raise ValueError('A verified Sports Cave product URL is required.')
    variant = str(variant or '').rsplit('/',1)[-1]
    if variant and not variant.isdigit():
        raise ValueError('Invalid variant ID.')
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode({'variant':variant}) if variant else '', ''))


def clean_image(data, content_type, finished_composite=False):
    archive._inspect_image(data,content_type)
    with Image.open(io.BytesIO(data)) as image:
        # Canvas-exported finished JPEGs contain no private source metadata.
        # Preserve the exact Download bytes and dimensions after normal validation.
        if finished_composite and image.format == 'JPEG' and not image.getexif() and not (
            set(image.info) - {'jfif','jfif_version','jfif_unit','jfif_density'}
        ):
            return data, image.width, image.height
        # Retain orientation but remove EXIF/GPS, ICC comments and embedded thumbnails.
        image = ImageOps.exif_transpose(image).convert('RGB')
        if not finished_composite:
            image.thumbnail((2400,2400))
        output = io.BytesIO()
        image.save(output,'JPEG',quality=90,optimize=True)
        return output.getvalue(), image.width, image.height


def attribution(params):
    result = {}
    for key in ('utm_source','utm_medium','utm_campaign','utm_content','utm_term'):
        value = archive._query_text(type('Query',(),{'query_params':params})(),key,160)
        if value:
            result[key] = value
    for key in ('referrer','landing_url'):
        value = str(params.get(key) or '')
        parts = urlsplit(value)
        if parts.scheme == 'https' and parts.hostname and not parts.username:
            result[key] = urlunsplit((parts.scheme,parts.netloc,parts.path,'',''))[:1200]
    return result


def save(request,data,content_type,cors):
    try:
        params = request.query_params
        client, session = store.identifier(params.get('client_preview_id')), store.identifier(params.get('session_id'))
        unit = archive._query_text(request,'unit',2)
        if unit not in ('','cm','in'):
            raise ValueError('Choose cm or in.')
        data,width,height = clean_image(data,content_type,params.get('finished_composite') == '1')
        address = str(params.get('customer_email') or '').strip()
        ident = {'customer_email':'','customer_name':'','shopify_customer_id':'','identity_source':'anonymous','email_marketing_state':'UNKNOWN'}
        if address:
            source = 'logged_in' if params.get('identity_source') == 'logged_in' else 'guest'
            ident = identity.resolve(address,params.get('customer_name') or 'Collector',source)
            if not ident['shopify_customer_id'] and not params.get('customer_name'):
                ident['customer_name'] = ''
            if source != 'logged_in' or not ident['shopify_customer_id']:
                ident['identity_source'] = 'email_capture'
        payload = {'client_preview_id':client,'session_id':session,'preview_id':params.get('preview_id'),
                   'image_sha256':hashlib.sha256(data).hexdigest(),'width':width,'height':height,'bytes':len(data),
                   'identity':ident,'attribution':attribution(params),'measurement_unit':unit}
        if 'image_reuse_allowed' in params:
            if params['image_reuse_allowed'] not in ('0','1') or params.get('reuse_consent_source') != 'wall_preview_download_checkbox':
                raise ValueError('Explicit download image permission required.')
            payload['image_reuse_allowed'] = params['image_reuse_allowed'] == '1'
        payload['started_at']=timestamp(params.get('started_at'))
        timestamp(params.get('confirmed_at')) # server confirmation time remains authoritative
        for key,limit in (('product_id',80),('variant_id',80),('product_handle',255),('product_title',500)):
            payload[key] = archive._query_text(request,key,limit)
        payload['frame_label'] = archive._query_text(request,'frame',120)
        payload['size_label'] = archive._query_text(request,'size',160)
        payload['product_url'] = product_url(params.get('product_url'),payload['variant_id'])
        market = email_options({key:params[key] for key in ('market_country_code','market_country_name') if key in params})
        payload.update({key:market[key] for key in ('market_country_code','market_country_name')})
        payload['archive_image'] = data
        def upload(previous,preview_id):
            root = '/Sportscave Team Folder'
            # Keep the last committed path until the worker safely relocates it.
            folder = (previous or {}).get('customer_folder') or f'{root}/{archive.DROPBOX_RELATIVE_ROOT}/' + (
                identity.customer_folder_name(ident['customer_email']) if ident['customer_email'] else 'Anonymous')
            path = (previous or {}).get('dropbox_path') or f'{folder}/{client}.jpg'
            if not archive.dropbox_integration.path_is_within_root(path,f'{root}/{archive.DROPBOX_RELATIVE_ROOT}'):
                raise ValueError('Invalid archive destination.')
            # Commit the cleaned composite and job together before acknowledging.
            # Dropbox runs in the existing worker, never on the shopper request.
            return {'folder':folder,'path':path,'file_id':'','pending_archive':True}
        row,duplicate = store.confirm(payload,upload)
        LOG.info('wall_preview_confirmed preview_id=%s version=%s duplicate=%s bytes=%s',row['id'],row['version'],duplicate,len(data))
        response = {'ok':True,'preview_id':str(row['id']),'client_preview_id':client,'preview_token':session,
                    'version':row['version'],'duplicate':duplicate,
                    'archive_status':row.get('archive_status','accepted')}
        if row.get('share_token') and not row.get('share_revoked_at'):
            response['share_url'] = BASE+'/wall-preview/'+row['share_token']
        return JSONResponse(response,headers=cors)
    except PermissionError:
        return JSONResponse({'ok':False,'error':'preview_not_authorized'},status_code=403,headers=cors)
    except (ValueError,TypeError) as exc:
        return JSONResponse({'ok':False,'error':'invalid_preview','message':str(exc)[:160]},status_code=400,headers=cors)
    except Exception as exc:
        LOG.warning('wall_preview_confirm_failed error_type=%s',type(exc).__name__)
        return JSONResponse({'ok':False,'error':'storage_unavailable'},status_code=503,headers=cors)


async def action(request):
    if request.method=='OPTIONS' or archive._origin(request) not in archive._allowed_origins():
        return await _action(request)
    if not archive._INGEST_SLOTS.acquire(blocking=False):
        return JSONResponse({'ok':False,'error':'storage_busy'},status_code=503,headers=archive._cors_headers(archive._origin(request)))
    try:return await _action(request)
    finally:archive._INGEST_SLOTS.release()


async def _action(request):
    origin = archive._origin(request)
    cors = archive._cors_headers(origin)
    if request.method == 'OPTIONS':
        return Response(status_code=204 if origin in archive._allowed_origins() else 403,headers=cors)
    if origin not in archive._allowed_origins():
        return JSONResponse({'ok':False,'error':'origin_not_allowed'},status_code=403,headers=cors)
    if not archive._rate_allowed('action:'+archive._client_key(request)):
        return JSONResponse({'ok':False,'error':'rate_limited'},status_code=429,headers=cors)
    if request.url.path.endswith('/email') and not archive._rate_allowed('email:'+archive._client_key(request),limit=5):
        return JSONResponse({'ok':False,'error':'rate_limited'},status_code=429,headers=cors)
    # Limit stream before JSON parsing, independently of Content-Length.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4096:
            return JSONResponse({'ok':False,'error':'payload_too_large'},status_code=413,headers=cors)
    try:
        payload = json.loads(body)
        if not isinstance(payload,dict):
            raise ValueError('Object required.')
        timestamp(payload.get('occurred_at') or payload.get('requested_at'))
        preview_id = store.identifier(request.path_params['preview_id'])
        token = request.headers.get('x-wall-preview-token','')
        if request.url.path.endswith('/events'):
            if set(payload)-{'event_name','event_id','occurred_at'}:
                raise ValueError('Unsupported event fields.')
            await run_in_threadpool(store.add_event,preview_id,token,payload.get('event_name'),payload.get('event_id'))
            result = {'ok':True}
        else:
            if set(payload)-{'email','product_url','requested_at','name','image_reuse_allowed',
                             'marketing_opt_in','marketing_consent_source','reuse_consent_source',
                             'marketing_consent_text','marketing_consent_version',
                             'market_country_code','market_country_name'}:
                raise ValueError('Unsupported email fields.')
            options = email_options(payload)
            address = identity.normalize_email(payload.get('email'))
            # Never queue emails to reserved/testing domains; useful production non-delivery check.
            if address.rsplit('@',1)[-1].endswith(('.invalid','.test','.example')):
                raise ValueError('A deliverable email address is required.')
            from wall_preview_email import configured
            if not configured(address):
                return JSONResponse({'ok':False,'error':'email_delivery_not_configured'},status_code=503,headers=cors)
            state = await run_in_threadpool(store.request_email,preview_id,token,address,options)
            result = {'ok':True,'preview_id':preview_id,'email_status':state,'marketing_subscribed':False}
        return JSONResponse(result,headers=cors)
    except PermissionError:
        return JSONResponse({'ok':False,'error':'preview_not_authorized'},status_code=403,headers=cors)
    except (ValueError,TypeError,KeyError):
        return JSONResponse({'ok':False,'error':'invalid_request'},status_code=400,headers=cors)
    except Exception as exc:
        LOG.warning('wall_preview_action_failed error_type=%s',type(exc).__name__)
        return JSONResponse({'ok':False,'error':'temporarily_unavailable'},status_code=503,headers=cors)


def email_options(payload):
    """Explicit Send disclosure and image permission remain independent."""
    options = {}
    for key in ('image_reuse_allowed','marketing_opt_in'):
        if key in payload and type(payload[key]) is not bool:
            raise ValueError('Consent must be a boolean.')
        options[key] = payload.get(key)
    name = payload.get('name')
    if name is None:name=''
    if not isinstance(name,str) or len(name)>200 or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('Invalid contact name.')
    options['name'] = ' '.join(name.split())
    code = payload.get('market_country_code')
    country = payload.get('market_country_name')
    if code is not None and (not isinstance(code,str) or not re.fullmatch(r'[A-Za-z]{2}',code.strip())):
        raise ValueError('Invalid market country code.')
    if country is not None and (not isinstance(country,str) or not country.strip() or len(country)>100
            or any(ord(c)<32 or ord(c)==127 for c in country)):
        raise ValueError('Invalid market country name.')
    options['market_country_code'] = code.strip().upper() if code is not None else None
    options['market_country_name'] = ' '.join(country.split()) if country is not None else None
    for key in ('marketing_consent_source','reuse_consent_source'):
        value = payload.get(key)
        allowed={'wall_preview_hd_email','wall_preview_hd_email_send'} if key=='marketing_consent_source' else {'wall_preview_hd_email'}
        if value is not None and (not isinstance(value,str) or value not in allowed):
            raise ValueError('Invalid consent source.')
        options[key] = value or 'wall_preview_hd_email'
    text=payload.get('marketing_consent_text')
    version=payload.get('marketing_consent_version')
    if text is not None and (not isinstance(text,str) or text!=CONSENT_TEXT):raise ValueError('Invalid consent disclosure.')
    if version is not None and version!=CONSENT_VERSION:raise ValueError('Invalid consent version.')
    if options['marketing_consent_source']=='wall_preview_hd_email_send':
        if options['marketing_opt_in'] is True and text!=CONSENT_TEXT:raise ValueError('Send consent requires its disclosure.')
        options['marketing_consent_version']=version or (CONSENT_VERSION if text else None)
    else:options['marketing_consent_version']=version
    options['marketing_consent_text']=text
    if payload.get('product_url'):
        product_url(payload['product_url']) # never replace the canonical preview product
    return options


async def share(request):
    if not archive._INGEST_SLOTS.acquire(blocking=False):
        return Response(status_code=503,headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})
    try:return await _share(request)
    finally:archive._INGEST_SLOTS.release()


async def _share(request):
    headers = {'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow, noarchive',
               'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
               'Content-Security-Policy':"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'"}
    if not archive._rate_allowed('share:'+archive._client_key(request)):
        return Response(status_code=429,headers=headers)
    row = await run_in_threadpool(store.public_preview,request.path_params['token'])
    if not row:
        return Response(status_code=404,headers=headers)
    if request.url.path.endswith('/image'):
        try:
            data = await run_in_threadpool(archive_bytes,row)
            return Response(data,media_type='image/jpeg',headers=headers)
        except Exception:
            return Response(status_code=404,headers=headers)
    title = html.escape(row['product_title'] or 'Your Sports Cave wall preview')
    context = html.escape(' · '.join(filter(None,(row.get('frame_label'),row.get('size_label')))))
    url = html.escape(product_url(row['product_url'],row.get('variant_id')),quote=True)
    page = f'''<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex,nofollow"><title>{title}</title></head>
    <body style="margin:0;background:#111;color:#f7f3eb;font:16px Arial;text-align:center">
    <main style="max-width:900px;margin:auto;padding:20px"><h1>{title}</h1><p>{context}</p>
    <img src="{html.escape(request.url.path,quote=True)}/image" alt="{title}" style="width:100%;height:auto">
    <p>@sportscaveshop · See It On Your Wall</p><a href="{url}" style="display:inline-block;padding:16px;background:#cfa84b;color:#111">SECURE YOUR EDITION</a></main></body></html>'''
    return HTMLResponse(page,headers=headers)


def archive_bytes(row):
    # A Dropbox outage never loses the already-confirmed composite. Capability
    # checks happen before this internal read; no public database access.
    pending=store.pending_archive_image(row['id'])
    if pending is not None:return pending
    token,_ = archive._dropbox_connection()
    client = archive.dropbox_integration.team_space_client(token)
    _, response = client.files_download(row.get('dropbox_file_id') or row['dropbox_path'])
    data = response.content
    if len(data)>archive.MAX_IMAGE_BYTES:
        raise ValueError('Image too large.')
    return data


ROUTES = (
 ('/api/wall-previews/{preview_id}/events',action,('POST','OPTIONS')),
 ('/api/wall-previews/{preview_id}/email',action,('POST','OPTIONS')),
 ('/wall-preview/{token}/image',share,('GET',)),
 ('/wall-preview/{token}',share,('GET',)),
)
