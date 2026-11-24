"""Compress public frontend bundles using Starlette's standard ASGI middleware.

Streamlit's ASGI server deliberately skips its static directory when applying
gzip. On a limited connection these bundles dominate cold browser loading.
Keep the change restricted to public JS/CSS: never compress customer responses,
streams, uploads, websocket traffic or range requests here. Only installed
public hashed bundles are precompressed; response bodies are never cached.
"""
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware
from public_bundle_cache import default_cache


def encoding_quality(value, encoding):
    qualities = {}
    for item in value.lower().split(','):
        name, *params = item.strip().split(';')
        try:
            quality = next((float(p.strip()[2:]) for p in params if p.strip().startswith('q=')), 1.0)
            qualities[name] = quality if 0 <= quality <= 1 else 0.0
        except ValueError:
            qualities[name] = 0.0
    return qualities.get(encoding, qualities.get('*', 0.0))


class StaticAssetCompression:
    def __init__(self, app, *, cache=None):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=4)
        self.cache = cache if cache is not None else default_cache()
        self.cache.start()

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        root = scope.get('root_path', '').rstrip('/')
        if root and path.startswith(root + '/'):
            path = path[len(root):]
        bundle = ((path.startswith('/static/js/') and path.endswith('.js')) or
                  (path.startswith('/static/css/') and path.endswith('.css')))
        if scope.get('type') != 'http' or scope.get('method') != 'GET' or not bundle:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        if 'range' in headers:
            return await self.app(scope, receive, send)

        accept = headers.get('accept-encoding', '')
        gzip_quality = encoding_quality(accept, 'gzip')
        br_quality = encoding_quality(accept, 'br')
        explicit_identity = any(item.strip().split(';')[0].lower() == 'identity' for item in accept.split(','))
        identity_quality = encoding_quality(accept, 'identity') if explicit_identity else 0
        entry = self.cache.get(path) if br_quality > 0 and br_quality >= max(gzip_quality, identity_quality) else None
        replace = False
        sent = False

        async def send_asset(message):
            nonlocal replace, sent
            if message['type'] == 'http.response.start':
                response = MutableHeaders(scope=message)
                policy = response.get('cache-control', '').lower()
                replace = bool(entry and message['status'] == 200
                    and 'public' in policy and 'private' not in policy and 'no-store' not in policy
                    and 'set-cookie' not in response and 'content-encoding' not in response
                    and response.get('etag') == entry.etag
                    and response.get('content-length') == str(entry.signature[1])
                    and response.get('content-type', '').split(';')[0] in
                        {'text/javascript', 'application/javascript', 'text/css'})
                if replace:
                    response['content-encoding'] = 'br'
                    response['content-length'] = str(len(entry.data))
                # Include Vary on conditional/identity responses as well. Keep
                # the original validator usable for both encoded representations.
                if 'accept-encoding' not in response.get('vary', '').lower():
                    response.add_vary_header('Accept-Encoding')
                if response.get('content-encoding') in {'gzip', 'br'} and response.get('etag', '').startswith('"'):
                    response['etag'] = 'W/' + response['etag']
            elif replace and message['type'] in {'http.response.body', 'http.response.pathsend'}:
                if not sent:
                    await send({'type': 'http.response.body', 'body': entry.data, 'more_body': False})
                    sent = True
                return
            await send(message)

        if entry:
            # Preserve downstream conditionals/security headers but avoid double
            # compression by the framework's own middleware.
            scope = dict(scope, headers=[(k, v) for k, v in scope['headers']
                if k.lower() != b'accept-encoding'] + [(b'accept-encoding', b'identity')])
            await self.app(scope, receive, send_asset)
        else:
            await (self.compressed if gzip_quality > 0 and gzip_quality >= identity_quality else self.app)(scope, receive, send_asset)
