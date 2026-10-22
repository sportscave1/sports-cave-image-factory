"""Exercise the actual native message boundary with isolated receipt folders."""
import datetime
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest
import uuid


@unittest.skipUnless(os.name == 'nt', 'Windows native receipt host')
class ReceiptHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.exe = cls.root / 'Receipt.exe'
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        source = Path(__file__).resolve().parents[1] / 'native/DownloadReceiptHost.cs'
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/reference:System.Web.dll',
                        '/reference:System.Web.Extensions.dll', '/reference:System.Core.dll',
                        '/out:' + str(cls.exe), str(source)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.events = self.root / str(uuid.uuid4())
        self.events.mkdir()
        (self.root / 'active.json').write_text(json.dumps({
            'events': str(self.events), 'session': 'isolated-test',
            'expires': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        }))
        self.value = dict(v=1, event='changed', id='42',
            url='http://127.0.0.1:18963/sample.txt?sc_download=' + str(uuid.uuid4()),
            final_url='', filename=str(self.events / 'sample.txt'), state='complete', bytes=13,
            started=datetime.datetime.now(datetime.timezone.utc).isoformat(), ended='', error='', observed=1)
        self.value['final_url'] = self.value['url']

    def send(self, value, fragmented=False):
        body = json.dumps(value).encode()
        data = struct.pack('<I', len(body)) + body
        process = subprocess.Popen([str(self.exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        if fragmented:
            for chunk in (data[:1], data[1:3], data[3:4], data[4:]):
                process.stdin.write(chunk)
                process.stdin.flush()
                time.sleep(.03)
            process.stdin.close()
            process.stdin = None
            output, _ = process.communicate(timeout=5)
        else:
            output, _ = process.communicate(data, timeout=5)
        return output

    def test_fragmented_frame_and_metadata_only_receipt(self):
        output = self.send(self.value, fragmented=True)
        self.assertEqual(json.loads(output[4:]), {'accepted': True})
        receipts = list(self.events.glob('*.json'))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text())
        self.assertEqual(receipt['session'], 'isolated-test')
        self.assertEqual(receipt['id'], '42')

    def test_extra_content_wrong_origin_nonce_and_state_rejected(self):
        for patch in ({'contents': 'private content'}, {'url': 'https://example.com/file'},
                      {'url': 'http://127.0.0.1:18963/file'}, {'state': 'unknown'}):
            with self.subTest(patch=list(patch)):
                self.assertEqual(self.send(dict(self.value, **patch)), b'')
                self.assertEqual(list(self.events.glob('*.json')), [])
