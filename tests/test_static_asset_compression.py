import gzip
import unittest
from static_asset_compression import StaticAssetCompression


class StaticCompressionTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, path='/static/js/index.hash.js', *, encoding='gzip', method='GET',
                      extra=(), status=200, response_headers=(), chunks=None, root=''):
        body = b'const publicBundle = "Sports Cave";\n' * 500
        messages = []
        async def app(scope, receive, send):
            await send({'type': 'http.response.start', 'status': status, 'headers': list(dict([
                (b'content-type', b'text/javascript'), (b'etag', b'"asset"'),
                (b'cache-control', b'public, max-age=31536000'), *response_headers]).items())})
            parts = chunks if chunks is not None else [body]
            for i, part in enumerate(parts):
                await send({'type': 'http.response.body', 'body': part, 'more_body': i < len(parts)-1})
        async def send(message): messages.append(message)
        await StaticAssetCompression(app)({'type': 'http', 'path': path, 'root_path': root,
            'method': method, 'headers': [(b'accept-encoding', encoding.encode()), *extra]}, None, send)
        headers = dict(messages[0]['headers'])
        return headers, b''.join(m.get('body', b'') for m in messages), body

    async def test_gzip_exact_content_and_cache_contract(self):
        for path in ['/static/js/index.hash.js', '/static/css/index.hash.css', '/os/static/js/index.hash.js']:
            with self.subTest(path=path):
                headers, compressed, original = await self.request(path, root='/os')
                self.assertEqual(gzip.decompress(compressed), original)
                self.assertLess(len(compressed), len(original))
                self.assertEqual(headers[b'vary'], b'Accept-Encoding')
                self.assertEqual(headers[b'etag'], b'W/"asset"')
                self.assertEqual(headers[b'cache-control'], b'public, max-age=31536000')

    async def test_streamed_bundles_preserve_all_chunks(self):
        chunks = [b'var x="abcd";' * 2000, b'var y="efgh";' * 2000]
        headers, data, _ = await self.request(chunks=chunks)
        self.assertEqual(gzip.decompress(data), b''.join(chunks))
        self.assertEqual(headers[b'content-encoding'], b'gzip')

    async def test_identity_and_explicit_refusal(self):
        for encoding in ['identity', 'br, gzip;q=0', 'gzip; q=0.0']:
            headers, data, original = await self.request(encoding=encoding)
            self.assertNotIn(b'content-encoding', headers)
            self.assertEqual(data, original)
            self.assertEqual(headers[b'vary'], b'Accept-Encoding')

    async def test_private_routes_media_ranges_and_head_bypass(self):
        for args in [dict(path='/'), dict(path='/api/private.js'), dict(path='/media/image.png'),
                     dict(method='HEAD'), dict(method='POST'), dict(extra=[(b'range', b'bytes=0-100')])]:
            with self.subTest(args=args):
                headers, data, original = await self.request(**args)
                self.assertNotIn(b'content-encoding', headers)
                self.assertNotIn(b'vary', headers)
                self.assertEqual(data, original)

    async def test_preencoded_and_event_streams_are_not_recompressed(self):
        for header in [(b'content-encoding', b'br'), (b'content-type', b'text/event-stream')]:
            headers, data, original = await self.request(response_headers=[header])
            self.assertEqual(data, original)

    async def test_small_and_304_response(self):
        for body, status in [(b'small', 200), (b'', 304)]:
            headers, data, _ = await self.request(chunks=[body], status=status)
            self.assertEqual(data, body)
            self.assertNotIn(b'content-encoding', headers)
            self.assertEqual(headers[b'vary'], b'Accept-Encoding')

    async def test_websocket_passthrough(self):
        calls = []
        async def app(scope, receive, send): calls.append(scope['type'])
        await StaticAssetCompression(app)({'type': 'websocket', 'path': '/_stcore/stream'}, None, None)
        self.assertEqual(calls, ['websocket'])


if __name__ == '__main__': unittest.main()
