"""Each intentional capture crosses the real API/SQL/worker path with mock Dropbox."""
import json
import os
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import wall_preview_crm_api as api
import wall_preview_crm_store as store
import wall_preview_archive as worker
from wall_preview_identity import capture_folder
from tests import test_wall_preview_archive_recovery as recovery
from tests import test_wall_preview_crm_v2 as fixture


class FolderTests(unittest.TestCase):
    def test_identity_product_and_session_separation(self):
        root = '/Sportscave Team Folder'
        row = {'session_id': str(uuid.uuid4()), 'product_id': '123', 'product_handle': 'kobe-vs-jordan',
               'customer_email': 'nathan-baker@live.com.au'}
        first = capture_folder(row, root, '03_ASSETS/11 Wall Preview Inbox')
        self.assertIn('/nathan-baker@live.com.au/kobe-vs-jordan-', first)
        self.assertNotEqual(first, capture_folder(dict(row, product_id='456'),root,'03_ASSETS/11 Wall Preview Inbox'))
        anon = dict(row, customer_email='')
        self.assertIn('/Anonymous/'+row['session_id']+'/', capture_folder(anon,root,'inbox'))
        self.assertNotEqual(capture_folder(anon,root,'inbox'),capture_folder(dict(anon,session_id=str(uuid.uuid4())),root,'inbox'))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES') == '1', 'Disposable loopback PostgreSQL required')
class CaptureTests(unittest.TestCase):
    setUpClass = classmethod(fixture.DatabaseTests.setUpClass.__func__)
    setUp = recovery.RecoveryTests.setUp
    tearDown = fixture.DatabaseTests.tearDown
    put = recovery.RecoveryTests.put
    move = recovery.RecoveryTests.move
    read = recovery.RecoveryTests.read
    fail = recovery.RecoveryTests.fail

    def capture(self, product='123', color='red', email='collector@example.test', event_id=None, permission=None):
        params = {'client_preview_id':event_id or str(uuid.uuid4()), 'session_id':self.data['session_id'],
                  'capture_mode':'save_event','finished_composite':'1','product_id':product,
                  'product_handle':'product-'+product,'product_title':'Product '+product,
                  'product_url':'https://sportscaveshop.com/products/product-'+product,
                  'customer_email':email,'customer_name':'', 'unit':'cm'}
        if permission is not None:
            params.update(image_reuse_allowed='1' if permission else '0', reuse_consent_source='wall_preview_download_checkbox')
        identity = dict(self.data['identity'],customer_email=email,customer_name='',identity_source='email_capture')
        with patch.object(api.identity,'resolve',return_value=identity):
            response = api.save(SimpleNamespace(query_params=params),fixture.jpeg(color),'image/jpeg',{})
        self.assertEqual(response.status_code,200,response.body)
        return json.loads(response.body)

    def drain(self):
        while worker.tick():
            pass

    def test_identified_same_product_every_image_retained_latest_is_newest(self):
        rows = [self.capture(color=color) for color in ('red','green','blue')]
        self.drain()
        self.assertEqual(len(self.files),3)
        self.assertEqual(len({r['preview_id'] for r in rows}),3)
        self.assertEqual(self.files[self.read(rows[-1]['preview_id'])['dropbox_path']]['image'],fixture.jpeg('blue'))
        with self.Adapter() as cur:
            cur.execute('SELECT id FROM wall_previews ORDER BY received_at DESC LIMIT 1')
            self.assertEqual(str(cur.fetchone()['id']),rows[-1]['preview_id'])
            cur.execute("SELECT count(*) n FROM wall_preview_events WHERE event_name='WallPreviewStarted'")
            self.assertEqual(cur.fetchone()['n'],0)  # Saving again does not invent another open.

    def test_multiple_products_and_return_to_first(self):
        rows=[self.capture(product=p) for p in ('1','2','3','4','1')]
        self.drain();self.assertEqual(len(self.files),5)
        self.assertEqual(len({self.read(r['preview_id'])['customer_folder'] for r in rows}),4)

    def test_anonymous_four_saves_all_retained_no_invented_identity(self):
        rows=[self.capture(product=p,email='') for p in ('1','2','3','1')]
        self.drain();self.assertEqual(len(self.files),4)
        for r in rows:
            row=self.read(r['preview_id'])
            self.assertFalse(row['customer_email']);self.assertIn('/Anonymous/'+self.data['session_id']+'/',row['dropbox_path'])

    def test_rapid_identical_saves_and_exact_request_retry(self):
        rows=[self.capture() for _ in range(12)]
        retry=self.capture(event_id=rows[0]['client_preview_id'])
        self.assertTrue(retry['duplicate']);self.assertEqual(retry['preview_id'],rows[0]['preview_id'])
        self.drain();self.assertEqual(len(self.files),12)
        self.capture(event_id=rows[0]['client_preview_id']);self.assertFalse(worker.tick())

    def test_failed_save_does_not_block_new_capture_or_recovery(self):
        first=self.capture()
        with patch.object(worker,'_upload',side_effect=RuntimeError('mock Dropbox outage')):
            self.assertTrue(worker.tick(first['preview_id']))
        self.assertFalse(self.read(first['preview_id'])['dropbox_file_id'])
        second=self.capture();self.drain();self.assertEqual(len(self.files),1)
        self.fail(first['preview_id'])
        again=self.capture(event_id=first['client_preview_id'])
        self.assertEqual(again['preview_id'],first['preview_id'])
        self.drain();self.assertEqual(len(self.files),2)
        self.assertTrue(self.read(second['preview_id'])['dropbox_file_id'])

    def test_reused_event_cannot_replace_product_or_image(self):
        first=self.capture()
        with self.assertRaises(AssertionError):
            self.capture(product='other',event_id=first['client_preview_id'])
        self.drain();self.assertEqual(len(self.files),1)

    def test_permission_separate_from_identification(self):
        for consent in (None,False,True):
            row=self.capture(permission=consent)
            self.assertEqual(self.read(row['preview_id'])['marketing_permission'],consent is True)
        self.drain();self.assertEqual(len(self.files),3)
        with self.Adapter() as cur:
            cur.execute('SELECT count(*) n FROM wall_preview_email_jobs');self.assertEqual(cur.fetchone()['n'],0)
