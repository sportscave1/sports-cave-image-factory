import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop_recorder.download_bridge import configure
from desktop_recorder.download_preflight import HOST, inspect_manifest


class DownloadSetupTests(unittest.TestCase):
    def test_session_rotation_preserves_previous_and_refuses_other_owner(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            bridge = base / 'bridge'
            bridge.mkdir()
            (bridge / 'DownloadReceiptHost.exe').write_bytes(b'isolated fixture, never executed')
            first = configure(base / 'candidate-a', bridge)
            before = (bridge / 'active.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'another unexpired'):
                configure(base / 'candidate-b', bridge)
            self.assertEqual((bridge / 'active.json').read_bytes(), before)
            second = configure(base / 'candidate-a', bridge)
            self.assertNotEqual(first['SC_RECORDER_DOWNLOAD_SESSION'], second['SC_RECORDER_DOWNLOAD_SESSION'])
            self.assertEqual(list(bridge.glob('active-before-*.json'))[0].read_bytes(), before)
            self.assertTrue(Path(first['SC_RECORDER_DOWNLOAD_EVENTS']).is_dir())

    def test_invalid_existing_session_is_preserved(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'DownloadReceiptHost.exe').write_bytes(b'fixture')
            (root / 'active.json').write_text('{incomplete')
            with self.assertRaisesRegex(ValueError, 'preserve and inspect'):
                configure(root / 'candidate', root)
            self.assertEqual((root / 'active.json').read_text(), '{incomplete')

    def test_manifest_diagnostics_distinguish_missing_path_and_wrong_extension(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'host.json'
            extension = 'a' * 32
            value = dict(name=HOST, type='stdio', path='receipt.exe',
                         allowed_origins=['chrome-extension://' + extension + '/'])
            path.write_text(json.dumps(value))
            self.assertIn('does not exist', inspect_manifest(path, extension)['reason'])
            (root / 'receipt.exe').write_bytes(b'not executed')
            self.assertTrue(inspect_manifest(path, extension)['ready'])
            self.assertFalse(inspect_manifest(path, 'b' * 32)['ready'])
            value['allowed_origins'] = None
            path.write_text(json.dumps(value))
            self.assertIn('array', inspect_manifest(path, extension)['reason'])
            value['name'] = 'wrong.host'
            path.write_text(json.dumps(value))
            self.assertFalse(inspect_manifest(path, extension)['ready'])
