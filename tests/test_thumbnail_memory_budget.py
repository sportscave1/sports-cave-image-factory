"""Synthetic image streams only; no browser, provider or database access."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import worker_memory as memory
from crm_thumbnail_render import ThumbnailImages


def png(size=(20, 20)):
    output = BytesIO()
    with Image.new('RGB', size) as image:
        image.save(output, format='PNG')
    return output.getvalue()


class ImageBudgetTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session_patch = patch('requests.Session', return_value=self.session)
        self.session_patch.start()
        self.images = ThumbnailImages()

    def tearDown(self):
        self.images.close()
        self.session.close.assert_called_once()
        self.session_patch.stop()

    def response(self, chunks, headers=None, status=200):
        response = Mock(status_code=status, headers=headers or {'Content-Type': 'image/png'})
        response.iter_content.return_value = iter(chunks)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        self.session.get.return_value = response
        return response

    def test_small_image_preserved_and_response_closed(self):
        data = png()
        response = self.response([data])
        self.assertEqual(self.images.fetch('https://fixture.invalid/image.png'), (data, 'image/png'))
        self.session.get.assert_called_once_with('https://fixture.invalid/image.png', stream=True, allow_redirects=False, timeout=5)
        response.__exit__.assert_called_once()
        self.assertFalse(self.session.trust_env)

    def test_declared_oversize_rejected_without_reading(self):
        response = self.response([], {'Content-Type': 'image/png', 'Content-Length': str(3 * 1024 * 1024)})
        with self.assertRaises(ValueError):
            self.images.fetch('https://fixture.invalid/image.png')
        response.iter_content.assert_not_called()
        response.__exit__.assert_called_once()

    def test_missing_or_false_length_cannot_bypass_stream_limit(self):
        for length in (None, '1'):
            headers = {'Content-Type': 'image/png'}
            if length:
                headers['Content-Length'] = length
            response = self.response([b'x' * 65536] * 34, headers)
            with self.assertRaises(ValueError):
                self.images.fetch('https://fixture.invalid/image.png')
            response.__exit__.assert_called_once()

    def test_small_compressed_image_with_excessive_pixels_rejected(self):
        data = png((2048, 2048))
        self.assertLess(len(data), 100000)
        self.response([data])
        with self.assertRaisesRegex(ValueError, 'pixel budget'):
            self.images.fetch('https://fixture.invalid/image.png')

    def test_document_byte_and_request_budgets(self):
        self.images.remaining = 5
        self.response([b'123456'])
        with self.assertRaises(ValueError):
            self.images.fetch('https://fixture.invalid/image.png')
        self.images.remaining = 1000
        self.images.requests = self.images.MAX_REQUESTS
        self.session.get.reset_mock()
        with self.assertRaises(ValueError):
            self.images.fetch('https://fixture.invalid/image.png')
        self.session.get.assert_not_called()

    def test_redirect_and_nonimage_do_not_read_body(self):
        for status, content_type in ((302, 'image/png'), (200, 'text/html')):
            response = self.response([], {'Content-Type': content_type}, status)
            with self.assertRaises(ValueError):
                self.images.fetch('https://fixture.invalid/image.png')
            response.iter_content.assert_not_called()


class AdmissionTests(unittest.TestCase):
    def test_256_mib_reserved_and_unknown_limits_keep_existing_behaviour(self):
        for current, limit, allowed in ((380, 512, False), (256, 512, True),
                                        (380, 2048, True), (None, 512, True), (380, None, True)):
            group = {'current': None if current is None else current * memory.MIB,
                     'limit': None if limit is None else limit * memory.MIB}
            with patch.object(memory, 'cgroup_memory', return_value=group):
                self.assertEqual(memory.thumbnail_has_headroom(), allowed)

    def test_memory_pressure_skips_renderer_releases_lease_and_allows_retry(self):
        import crm_thumbnail_cache as cache
        key = cache.token('synthetic-memory-pressure')
        load = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', CRM_THUMBNAIL_CACHE_DIR=directory), \
                patch.object(cache, 'thumbnail_has_headroom', return_value=False), \
                patch.object(cache, 'run_renderer') as renderer, \
                patch('crm_thumbnail_store.acquire', return_value=('CLAIMED', None, 'fixture-owner')), \
                patch('crm_thumbnail_store.finish') as finish:
            cache.PENDING[key] = 0
            cache.generate(key, load, Mock())
            renderer.assert_not_called()
            load.assert_not_called()
            finish.assert_called_once()
            self.assertEqual(finish.call_args.args[1:], (key, 'fixture-owner'))
            self.assertNotIn(key, cache.PENDING)
            self.assertFalse((Path(directory) / (key + '.lock')).exists())
            self.assertEqual(cache.diagnostic(key)['category'], 'memory_pressure')
            self.assertEqual(cache.request(key, load), ('ERROR', None))
        cache.FAILURES.pop(key, None)
        cache.DIAGNOSTICS.pop(key, None)


if __name__ == '__main__':
    unittest.main()
