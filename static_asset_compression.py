"""Compress public frontend bundles using Starlette's standard ASGI middleware.

Streamlit's ASGI server deliberately skips its static directory when applying
gzip. On a limited connection these bundles dominate cold browser loading.
Keep the change restricted to public JS/CSS: never compress customer responses,
streams, uploads, websocket traffic or range requests here. No extra cache.
"""
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware


class StaticAssetCompression:
    def __init__(self, app):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1024, compresslevel=4)

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

        # Starlette negotiates gzip, but its substring check doesn't recognise
        # an explicit q=0 refusal. Respect it without changing request headers.
        allowed = True
        for item in headers.get('accept-encoding', '').lower().split(','):
            encoding, *params = item.strip().split(';')
            if encoding == 'gzip':
                try:
                    allowed = all(float(p.split('=', 1)[1]) > 0 for p in params if p.strip().startswith('q='))
                except ValueError:
                    allowed = False

        async def send_asset(message):
            if message['type'] == 'http.response.start':
                response = MutableHeaders(scope=message)
                # Include Vary on conditional/identity responses as well. Keep
                # the original validator usable for both encoded representations.
                if 'accept-encoding' not in response.get('vary', '').lower():
                    response.add_vary_header('Accept-Encoding')
                if response.get('content-encoding') == 'gzip' and response.get('etag', '').startswith('"'):
                    response['etag'] = 'W/' + response['etag']
            await send(message)

        await (self.compressed if allowed else self.app)(scope, receive, send_asset)
