"""Recorded media, approval privacy and accurate payment information; offline only."""
import base64
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import marketplace as core
import marketplace_api as api
import marketplace_media as media
from marketplace_store import MarketplaceStore
from crm_store import StoreUnavailable
from tests.test_marketplace import FakeDatabase, sample, photograph, memory_store


class VideoEncodingTests(unittest.TestCase):
    @staticmethod
    def clip(seconds=1):
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory(prefix='sc-video-test-') as folder:
            path = Path(folder) / 'synthetic.mp4'
            result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                '-f', 'lavfi', '-i', 'color=c=gold:s=200x300:r=2', '-t', str(seconds),
                '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p',
                '-metadata', 'title=synthetic-private-title', '-y', str(path)],
                capture_output=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise AssertionError('Synthetic video fixture could not be created.')
            return base64.b64encode(path.read_bytes()).decode('ascii')

    def test_real_transcode_is_bounded_faststart_and_removes_metadata(self):
        result = media.prepare_video(self.clip())
        self.assertGreater(result['seconds'], 0)
        self.assertLessEqual(result['seconds'], 60.05)
        self.assertLess(len(result['bytes']), media.MAX_OUTPUT)
        self.assertEqual(result['bytes'][4:8], b'ftyp')
        self.assertLess(result['bytes'].index(b'moov'), result['bytes'].index(b'mdat'))
        self.assertNotIn(b'synthetic-private-title', result['bytes'])

    def test_long_corrupt_and_remote_playlist_inputs_are_rejected(self):
        invalid = [self.clip(61), 'not base64!', base64.b64encode(b'#EXTM3U\nhttps://example.invalid/movie.mp4').decode(),
                   base64.b64encode(b'\0\0\0\x18ftyp' + b'not a video' * 30).decode(), 'A' * 20_000_004]
        for value in invalid:
            with self.subTest(kind=value[:25]), self.assertRaises(ValueError):
                media.prepare_video(value)
        self.assertIsNone(media.prepare_video(None))

    def test_encoder_concurrency_is_bounded(self):
        with media.encoder_slot():
            with self.assertRaisesRegex(ValueError, 'Another video'):
                with media.encoder_slot():
                    self.fail('A second encoder must not start.')


class VideoStorageTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.store = MarketplaceStore(self.database.connect, media_storage=self.database.media)

    def submit(self):
        key = self.store.submit(core.submission(sample()), [photograph(), photograph()],
            {'bytes': b'0123456789', 'seconds': 1})['id']
        self.metadata = self.store.video(key, public=False)
        return key

    def test_video_metadata_stays_private_and_approval_gates_bytes(self):
        key = self.submit()
        self.assertIsNone(self.store.video(key))
        self.assertEqual(self.store.video(key, public=False), self.metadata)
        self.store.moderate(key, 'published', 1, 'test-admin')
        row = self.store.listing(key, public=True)
        self.assertTrue(row['has_video'])
        self.assertNotIn('video', row)
        self.assertNotIn(self.metadata['id'], json.dumps(row))
        self.assertEqual(self.store.video(key), self.metadata)
        self.store.moderate(key, 'withdrawn', 2, 'test-admin')
        self.assertIsNone(self.store.video(key))

    def test_database_failure_preserves_the_complete_source_submission(self):
        self.database.fail_listing = True
        with self.assertRaises(StoreUnavailable):
            self.submit()
        self.assertEqual(self.database.values, {})
        self.assertTrue(any(path.endswith('/listing.json') for path in self.database.media.backend.paths))

    def test_failed_upload_does_not_create_a_listing(self):
        self.database.media.backend.fail_upload = 'video.mp4'
        with self.assertRaises(OSError):
            self.submit()
        self.assertEqual(self.database.values, {})

    def test_object_keys_are_server_owned_and_never_public_urls(self):
        client = Mock()
        storage = media.LegacyVideoStorage(client=client, bucket='synthetic-private')
        key = str(uuid4())
        result = storage.save(key, {'bytes': b'video', 'seconds': 1})
        call = client.put_object.call_args.kwargs
        self.assertTrue(call['Key'].startswith('marketplace/media/' + key + '/'))
        self.assertNotIn('ACL', call)
        self.assertEqual(call['CacheControl'], 'no-store')
        with self.assertRaises(ValueError):
            storage.open('../../outside', result)


class Body(io.BytesIO):
    def iter_chunks(self, chunk_size):
        while chunk := self.read(chunk_size):
            yield chunk


class MediaPageTests(unittest.TestCase):
    def setUp(self):
        self.store = memory_store()
        self.store_patch = patch.object(api, 'MarketplaceStore', return_value=self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        api._RATE.clear()
        self.client = TestClient(Starlette(routes=[Route(path, endpoint, methods=list(methods)) for path, endpoint, methods in api.ROUTES]), base_url=core.PUBLIC_ORIGIN)
        self.headers = {'Origin': core.PUBLIC_ORIGIN}
        self.storage = Mock()

    def listing(self):
        key = self.store.submit(core.submission(sample()), [photograph(), photograph()],
            {'bytes': b'0123456789', 'seconds': 1})['id']
        self.metadata = self.store.video(key, public=False)
        return key

    def test_public_video_ranges_head_and_withdrawal(self):
        key = self.listing()
        url = f'/marketplace/videos/{key}/item.mp4'
        with patch.object(media, 'VideoStorage', return_value=self.storage):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.storage.open.assert_not_called()
            self.store.moderate(key, 'published', 1, 'test-admin')
            def open_stream(listing_id, metadata, first, last):
                stream = Body(b'0123456789'[first:last + 1])
                self.stream = stream
                return stream
            self.storage.open.side_effect = open_stream
            for requested, expected, status in ((None, b'0123456789', 200), ('bytes=2-5', b'2345', 206), ('bytes=-3', b'789', 206), ('bytes=7-', b'789', 206)):
                response = self.client.get(url, headers={'Range': requested} if requested else {})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.content, expected)
                self.assertEqual(int(response.headers['content-length']), len(expected))
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertTrue(self.stream.closed)
            response = self.client.head(url, headers={'Range': 'bytes=2-5'})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.headers['content-range'], 'bytes 2-5/10')
            self.assertEqual(response.content, b'')
            for bad in ('bytes=10-', 'bytes=5-2', 'bytes=0-1,3-4', 'bytes=-0', 'words=0-2'):
                self.assertEqual(self.client.get(url, headers={'Range': bad}).status_code, 416)
            self.store.moderate(key, 'withdrawn', 2, 'test-admin')
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_upload_success_is_private_and_storage_failure_is_not_success(self):
        payload = {**sample(), 'photos': [photograph(), photograph()], 'video': 'synthetic-upload'}
        with patch.object(media, 'configured', return_value=True), patch.object(media, 'prepare_video', return_value={'bytes': b'0123456789', 'seconds': 1}), patch.object(media, 'VideoStorage', return_value=self.storage):
            response = self.client.post('/marketplace/api/submissions', json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 201)
            key = response.json()['reference']
            self.assertIsNone(self.store.listing(key, public=True))
            self.assertTrue(self.store.listing(key)['has_video'])
            self.store.media_storage.backend.fail_upload = 'video.mp4'
            response = self.client.post('/marketplace/api/submissions', json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json()['ok'])

    def test_upload_concurrency_returns_retry_without_reading_more_files(self):
        with patch.object(api, '_UPLOADS') as uploads:
            uploads.acquire.return_value = False
            response = self.client.post('/marketplace/api/submissions', json=sample(), headers=self.headers)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['retry-after'], '30')
            uploads.release.assert_not_called()

    def test_unconfigured_video_is_explicit_but_photos_still_work(self):
        with patch.object(media, 'configured', return_value=False):
            response = self.client.get('/marketplace/sell')
            self.assertRegex(response.text, r'name="video"[^>]*disabled')
            payload = {**sample(), 'photos': [photograph(), photograph()], 'video': 'synthetic'}
            response = self.client.post('/marketplace/api/submissions', json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertIn('Remove the video', response.json()['error'])
            payload['video'] = ''
            self.assertEqual(self.client.post('/marketplace/api/submissions', json=payload, headers=self.headers).status_code, 201)

    def test_item_gallery_has_video_schema_without_fake_live_or_checkout(self):
        key = self.listing()
        self.store.moderate(key, 'published', 1, 'test-admin')
        response = self.client.get('/marketplace/item/' + key)
        self.assertIn('data-gallery', response.text)
        self.assertIn('playsinline preload="none"', response.text)
        self.assertNotIn('autoplay', response.text)
        self.assertIn('media-src \'self\'', response.headers['content-security-policy'])
        self.assertNotIn(self.metadata['id'], response.text)
        self.assertNotIn('seller@example.invalid', response.text)
        self.assertNotIn('Buy now', response.text)
        self.assertNotIn('Live stream', response.text)
        schema = json.loads(re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', response.text).group(1))
        product = schema['@graph'][0]
        self.assertEqual(product['subjectOf']['@type'], 'VideoObject')
        self.assertEqual(product['subjectOf']['duration'], 'PT1S')
        self.assertIn('Ask about this item', response.text)

    def test_admin_video_review_uses_session_data_not_a_shared_media_url(self):
        from streamlit.testing.v1 import AppTest
        import marketplace_page
        self.listing()
        self.storage.preview.return_value = b'synthetic-private-video'
        with patch.object(marketplace_page, 'MarketplaceStore', return_value=self.store), patch.object(media, 'VideoStorage', return_value=self.storage):
            page = AppTest.from_string("import streamlit as st\nfrom marketplace_page import render_listings, MarketplaceStore\nstore=MarketplaceStore()\nrender_listings(st, store, store.listings(), {'id':'test-admin'})").run()
            self.assertFalse(page.exception)
            next(b for b in page.button if b.label == 'Load video for review').click().run()
            self.assertFalse(page.exception)
            self.assertTrue(page.get('video')[0].proto.url.startswith('data:video/mp4;base64,'))
            self.assertNotIn('/media/', page.get('video')[0].proto.url)
            images = [image for element in page.get('imgs') for image in element.proto.imgs]
            self.assertEqual(len(images), 2)
            self.assertTrue(all(image.url.startswith('data:image/webp;base64,') for image in images))

    def test_payment_pages_footer_canonicals_and_sitemap_are_complete(self):
        for path, heading in (('/paypal', 'A familiar way to pay.'), ('/buyer-protection', 'Confidence starts with the details.')):
            response = self.client.get('/marketplace' + path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(heading, response.text)
            self.assertIn('Marketplace checkout is coming next.', response.text)
            self.assertIn('https://www.paypal.com/au/legalhub/paypal/buyer-protection', response.text)
            self.assertIn('href="' + core.PUBLIC_ORIGIN + '/marketplace' + path + '"', response.text)
            self.assertNotIn('guaranteed protection', response.text.lower())
        protection = self.client.get('/marketplace/buyer-protection').text
        for fact in ('Friends &amp; Family', 'Resale purchases are excluded', 'A$20,000', '180 days', '30 days', '20 days'):
            self.assertIn(fact, protection)
        for path in ('/paypal', '/buyer-protection'):
            self.assertIn('/marketplace' + path, self.client.get('/marketplace/sitemap.xml').text)
            self.assertIn('href="/marketplace' + path + '"', self.client.get('/marketplace').text)


if __name__ == '__main__':
    unittest.main()
