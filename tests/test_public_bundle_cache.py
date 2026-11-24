import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import brotli
import httpx
from starlette.staticfiles import StaticFiles

from public_bundle_cache import PublicBundleCache
from static_asset_compression import StaticAssetCompression, encoding_quality


class PublicBundleTests(unittest.IsolatedAsyncioTestCase):
    def test_installed_framework_entrypoint_is_found(self):
        installed = PublicBundleCache()
        candidates = list((installed.root / "js").glob("index.*.js"))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(installed.source("/static/js/" + candidates[0].name), candidates[0])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "static"
        (self.root / "js").mkdir(parents=True)
        self.path = "/static/js/index.abcdef12.js"
        self.source = self.base / self.path.lstrip("/")
        self.raw = b'const safePublicBundle = "Sports Cave";' * 5000
        self.source.write_bytes(self.raw)
        self.cache = PublicBundleCache(self.root)
        self.cache.warm()
        self.app = StaticAssetCompression(StaticFiles(directory=self.base), cache=self.cache)
        self.cache.finished.wait(5)

    async def request(self, *, encoding="br, gzip", extra=None, method="GET", app=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app or self.app),
                                     base_url="http://fixture") as client:
            return await client.request(method, self.path, headers={
                "accept-encoding": encoding, **(extra or {})})

    async def test_real_static_headers_decoding_and_negotiation(self):
        # StaticFiles defaults to no cache directive; add the immutable public
        # policy used by Streamlit without replacing its conditional handler.
        static = StaticFiles(directory=self.base)
        async def public(scope, receive, send):
            async def wrap(message):
                if message["type"] == "http.response.start":
                    message["headers"].append((b"cache-control", b"public, max-age=31536000, immutable"))
                await send(message)
            await static(scope, receive, wrap)
        app = StaticAssetCompression(public, cache=self.cache)
        for encoding, expected in [("br, gzip", "br"), ("br;q=0, gzip", "gzip"),
                                   ("br;q=.2, gzip;q=.8", "gzip"), ("identity", None),
                                   ("br;q=0, gzip;q=0", None),
                                   ("br;q=.5, gzip;q=.5, identity;q=1", None)]:
            response = await self.request(encoding=encoding, app=app)
            self.assertEqual(response.content, self.raw)
            self.assertEqual(response.headers.get("content-encoding"), expected)
            self.assertIn("accept-encoding", response.headers["vary"].lower())
            if expected == "br":
                self.assertEqual(int(response.headers["content-length"]), len(self.cache.get(self.path).data))
                self.assertTrue(response.headers["etag"].startswith('W/"'))
                self.assertIn("immutable", response.headers["cache-control"])
        first = await self.request(app=app)
        conditional = await self.request(app=app, extra={"if-none-match": first.headers["etag"]})
        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(conditional.content, b"")
        self.assertNotIn("content-encoding", conditional.headers)
        ranged = await self.request(app=app, extra={"range": "bytes=0-99"})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, self.raw[:100])
        self.assertNotIn("content-encoding", ranged.headers)
        head = await self.request(app=app, method="HEAD")
        self.assertEqual(head.content, b"")
        self.assertNotIn("content-encoding", head.headers)

    async def test_no_policy_or_private_never_uses_public_payload(self):
        response = await self.request()
        self.assertNotEqual(response.headers.get("content-encoding"), "br")
        for policy in (b"private", b"public, no-store", b"public"):
            async def private(scope, receive, send):
                entry = self.cache.get(self.path)
                await send(dict(type="http.response.start", status=200, headers=[
                    (b"content-length", str(len(self.raw)).encode()), (b"etag", entry.etag.encode()),
                    (b"cache-control", policy), (b"set-cookie", b"private=1"),
                    (b"content-type", b"text/javascript")]))
                await send(dict(type="http.response.body", body=self.raw))
            response = await self.request(app=StaticAssetCompression(private, cache=self.cache))
            self.assertNotEqual(response.headers.get("content-encoding"), "br")

    async def test_stream_pathsend_root_and_validator_mismatch(self):
        entry = self.cache.get(self.path)
        for pathsend in (True, False):
            sent = []
            async def app(scope, receive, send):
                self.assertIn((b"accept-encoding", b"identity"), scope["headers"])
                await send(dict(type="http.response.start", status=200, headers=[
                    (b"content-length", str(len(self.raw)).encode()), (b"etag", entry.etag.encode()),
                    (b"cache-control", b"public, immutable"), (b"content-type", b"text/javascript")]))
                if pathsend:
                    await send(dict(type="http.response.pathsend", path=str(self.source)))
                else:
                    for chunk in (self.raw[:100], self.raw[100:]):
                        await send(dict(type="http.response.body", body=chunk, more_body=True))
                    await send(dict(type="http.response.body", body=b"", more_body=False))
            async def send(message): sent.append(message)
            await StaticAssetCompression(app, cache=self.cache)(dict(type="http", method="GET",
                path="/os"+self.path, root_path="/os", headers=[(b"accept-encoding", b"br")]), None, send)
            bodies = [m for m in sent if m["type"] == "http.response.body"]
            self.assertEqual(len(bodies), 1)
            self.assertFalse(bodies[0]["more_body"])
            self.assertEqual(brotli.decompress(bodies[0]["body"]), self.raw)
        # Same URL/size with a different validator cannot get the cached bytes.
        async def changed(scope, receive, send):
            await send(dict(type="http.response.start", status=200, headers=[
                (b"content-length", str(len(self.raw)).encode()), (b"etag", b'"other"'),
                (b"cache-control", b"public"), (b"content-type", b"text/javascript")]))
            await send(dict(type="http.response.body", body=b"x" * len(self.raw)))
        result = await self.request(app=StaticAssetCompression(changed, cache=self.cache))
        self.assertEqual(result.content, b"x" * len(self.raw))
        self.assertNotIn("content-encoding", result.headers)

    async def test_bounded_files_and_changed_source(self):
        entry = self.cache.get(self.path)
        self.assertEqual(brotli.decompress(entry.data), self.raw)
        self.source.write_bytes(b"changed")
        self.assertIsNone(self.cache.get(self.path))
        for path in ("/api/orders.js", "/static/js/../../private.abcdef.js",
                     "/static/js/plain.js", "/static/js/index.abcdef12.js/extra"):
            self.assertIsNone(self.cache.source(path))
        empty = PublicBundleCache(self.root, max_bytes=1)
        empty.warm()
        self.assertEqual(empty.bytes, 0)
        self.assertFalse(empty.entries)

    async def test_warm_is_single_background_worker_and_does_not_block_loop(self):
        cache = PublicBundleCache(self.root)
        started, release = threading.Event(), threading.Event()
        original = brotli.compress
        def slow(*args, **kwargs):
            started.set()
            release.wait(5)
            return original(*args, **kwargs)
        with patch("public_bundle_cache.brotli.compress", side_effect=slow):
            cache.start()
            await asyncio.to_thread(started.wait, 2)
            cache.start()
            self.assertFalse(cache.finished.is_set())
            await asyncio.wait_for(asyncio.sleep(.01), timeout=.5)
            release.set()
            self.assertTrue(await asyncio.to_thread(cache.finished.wait, 5))
        self.assertEqual(len(cache.entries), 1)

    def test_invalid_quality_refused(self):
        for accept in ("br;q=0", "br;q=oops", "br;q=2", "br;q=-1"):
            self.assertEqual(encoding_quality(accept, "br"), 0)
