"""Public marketplace routes. Only approved item fields/images leave the server."""
import base64
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from xml.sax.saxutils import escape as xml_escape

from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, Response

import marketplace as core
import marketplace_views as views
from marketplace_store import MarketplaceStore

_RATE = OrderedDict()
_RATE_LOCK = threading.Lock()
ASSET_ROOT = Path(__file__).resolve().parent / 'static' / 'marketplace'


def security(nonce=''):
    return {'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin',
            'X-Frame-Options': 'DENY', 'Cache-Control': 'no-store',
            'Content-Security-Policy': "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                "form-action 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; font-src 'self' https://www.sportscaveshop.com; "
                f"script-src 'self' 'nonce-{nonce}'; object-src 'none'"}


async def page(request):
    nonce = secrets.token_urlsafe(18)
    config = core.deployed_site()
    path = request.url.path.rstrip('/')
    try:
        if path == core.BASE_PATH + '/sell':
            document = views.sell(config, nonce)
        elif path == core.BASE_PATH + '/terms':
            document = views.terms(nonce)
        elif 'listing_id' in request.path_params:
            listing_id = core.identifier(request.path_params['listing_id'])
            row = await run_in_threadpool(MarketplaceStore().listing, listing_id, public=True)
            if row is None:
                return unavailable_page(nonce, 404)
            document = views.item(row, nonce)
        else:
            unavailable = False
            try:
                rows = await run_in_threadpool(MarketplaceStore().listings, public=True)
            except Exception:
                rows, unavailable = [], True
            document = views.home(config, rows, request.query_params, nonce, unavailable, browse=path == core.BASE_PATH + '/browse')
        headers = security(nonce)
        headers['X-Sports-Cave-Marketplace-Release'] = config['release_id']
        if path in (core.BASE_PATH, core.BASE_PATH + '/terms'):
            headers['Cache-Control'] = 'public, max-age=0, s-maxage=15, must-revalidate'
        return HTMLResponse(document, headers=headers)
    except ValueError:
        return unavailable_page(nonce, 404)
    except Exception:
        return unavailable_page(nonce, 503)


def unavailable_page(nonce, status):
    title = 'This piece is no longer listed.' if status == 404 else 'Back in a moment.'
    document = views.shell(f'<main id="main" class="narrow"><h1>{title}</h1><p>Please return to the marketplace.</p><a class="button dark" href="{core.BASE_PATH}">Browse finds</a></main>',
                            title=title + ' | Sports Cave Marketplace', description=title, nonce=nonce, noindex=True)
    return HTMLResponse(document, status_code=status, headers=security(nonce))


async def asset(request):
    name = request.path_params['asset']
    paths = {'marketplace.css': (ASSET_ROOT / 'marketplace.css', 'text/css'),
             'marketplace-home.css': (ASSET_ROOT / 'marketplace-home.css', 'text/css'),
             'collector-room-1600.webp': (ASSET_ROOT / 'collector-room-1600.webp', 'image/webp'),
             'collector-room-800.webp': (ASSET_ROOT / 'collector-room-800.webp', 'image/webp'),
             'marketplace.js': (ASSET_ROOT / 'marketplace.js', 'text/javascript'),
             'logo.webp': (ASSET_ROOT / 'logo-320.webp', 'image/webp')}
    if name not in paths:
        return Response(status_code=404)
    path, media = paths[name]
    data = path.read_bytes()
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    headers = {'Cache-Control': 'public,max-age=3600,must-revalidate', 'ETag': etag,
               'X-Content-Type-Options': 'nosniff'}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers=headers)
    headers['Content-Length'] = str(len(data))
    return Response(b'' if request.method == 'HEAD' else data, media_type=media, headers=headers)


async def photo(request):
    try:
        listing_id = core.identifier(request.path_params['listing_id'])
        data = await run_in_threadpool(MarketplaceStore().photo, listing_id, int(request.path_params['index']), public=True)
        if not data:
            return Response(status_code=404, headers={'Cache-Control': 'no-store'})
        data = base64.b64decode(data)
        # Recheck approval on every request. Withdrawal also withdraws image access.
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Length': str(len(data))}
        return Response(b'' if request.method == 'HEAD' else data, media_type='image/webp', headers=headers)
    except (ValueError, TypeError):
        return Response(status_code=404)
    except Exception:
        return Response(status_code=503)


def allow_rate(request, address=''):
    # Bounded ephemeral abuse buckets. Identity is hashed and never logged/stored.
    host = request.client.host if request.client else 'unknown'
    key = hashlib.sha256((host + '|' + address).encode()).digest()
    at = time.monotonic()
    with _RATE_LOCK:
        expired = [k for k, value in _RATE.items() if value[0] < at - 3600]
        for old in expired:
            _RATE.pop(old, None)
        start, count = _RATE.get(key, (at, 0))
        if count >= (5 if address else 90) or len(_RATE) >= 10000 and key not in _RATE:
            return False
        _RATE[key] = (start, count + 1)
        return True


async def body(request, limit):
    origin = request.headers.get('origin', '')
    own = f'{request.url.scheme}://{request.url.netloc}'
    if origin not in (core.PUBLIC_ORIGIN, own) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise PermissionError('Use the form on the Sports Cave Marketplace website.')
    if request.headers.get('content-type', '').split(';', 1)[0].lower() != 'application/json':
        raise ValueError('Use the marketplace submission form.')
    if not allow_rate(request):
        raise OverflowError('Too many requests. Please try again later.')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise BufferError('The submission is too large. Use photos up to 2 MB each.')
        data.extend(chunk)
    payload = json.loads(data)
    if not isinstance(payload, dict) or payload.get('website'):
        raise ValueError('Please check the submission form.')
    return payload


async def submit(request):
    headers = security()
    try:
        payload = await body(request, 11500000)
        if not core.deployed_site()['intake_open']:
            return JSONResponse({'error': 'New seller submissions are currently paused.'}, status_code=503, headers=headers)
        row = core.submission(payload)
        if not allow_rate(request, row['seller_email']):
            raise OverflowError('You have sent several submissions. Please try again later.')
        photos = await run_in_threadpool(core.prepare_photos, payload.get('photos'))
        result = await run_in_threadpool(MarketplaceStore().submit, row, photos)
        return JSONResponse({'ok': True, 'reference': result['id']}, status_code=201, headers=headers)
    except Exception as exc:
        return form_error(exc, headers)


async def enquire(request):
    headers = security()
    try:
        payload = await body(request, 6000)
        listing_id = core.identifier(payload.get('listing_id'))
        name = core.clean_text(payload.get('name'), 'your name', 70)
        address = core.email(payload.get('email'))
        message = core.clean_text(payload.get('message'), 'your message', 1000)
        if payload.get('consent') is not True:
            raise ValueError('Agree to sharing your enquiry with the seller.')
        if not allow_rate(request, address):
            raise OverflowError('You have sent several enquiries. Please try again later.')
        enquiry_id = await run_in_threadpool(MarketplaceStore().enquire, listing_id, name, address, message)
        return JSONResponse({'ok': True, 'reference': enquiry_id}, status_code=201, headers=headers)
    except Exception as exc:
        return form_error(exc, headers)


def form_error(error, headers):
    if isinstance(error, PermissionError):
        status, message = 403, str(error)
    elif isinstance(error, BufferError):
        status, message = 413, str(error)
    elif isinstance(error, OverflowError):
        status, message = 429, str(error)
        headers = {**headers, 'Retry-After': '3600'}
    elif isinstance(error, (ValueError, TypeError, KeyError)):
        status, message = 400, str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'Please check your form details.'
    else:
        status, message = 503, 'Submissions are temporarily unavailable. Please try again shortly.'
    return JSONResponse({'ok': False, 'error': message}, status_code=status, headers=headers)


async def sitemap(request):
    try:
        rows = await run_in_threadpool(MarketplaceStore().listings, public=True)
        paths = [core.BASE_PATH, core.BASE_PATH + '/browse', core.BASE_PATH + '/sell', core.BASE_PATH + '/terms'] + [core.listing_url(row) for row in rows]
        urls = ''.join('<url><loc>' + xml_escape(core.PUBLIC_ORIGIN + p) + '</loc></url>' for p in paths)
        return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>', media_type='application/xml', headers={'Cache-Control': 'no-store'})
    except Exception:
        return Response(status_code=503, headers={'Cache-Control': 'no-store'})


async def robots(request):
    return Response('User-agent: *\nAllow: /marketplace\nDisallow: /marketplace/api/\nDisallow: /?\nDisallow: /app\nSitemap: ' + core.PUBLIC_ORIGIN + core.BASE_PATH + '/sitemap.xml\n',
                    media_type='text/plain', headers={'Cache-Control': 'public,max-age=3600'})


ROUTES = (
    (BASE := core.BASE_PATH, page, ('GET', 'HEAD')),
    (BASE + '/', page, ('GET', 'HEAD')),
    (BASE + '/browse', page, ('GET', 'HEAD')),
    (BASE + '/sell', page, ('GET', 'HEAD')),
    (BASE + '/terms', page, ('GET', 'HEAD')),
    (BASE + '/item/{listing_id}', page, ('GET', 'HEAD')),
    (BASE + '/assets/{asset}', asset, ('GET', 'HEAD')),
    (BASE + '/images/{listing_id}/{index:int}.webp', photo, ('GET', 'HEAD')),
    (BASE + '/api/submissions', submit, ('POST',)),
    (BASE + '/api/enquiries', enquire, ('POST',)),
    (BASE + '/sitemap.xml', sitemap, ('GET', 'HEAD')),
    ('/robots.txt', robots, ('GET', 'HEAD')),
)
