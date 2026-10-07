"""Isolated SQL coverage for arrival events and per-user image receipts."""
import os
import unittest
import uuid
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import wall_preview_notifications as notifications
import wall_preview_crm_store as crm
import wall_preview_store as ledger
from tests import test_wall_preview_crm_v2 as fixture


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL fixture required')
class NotificationTests(unittest.TestCase):
    setUpClass=classmethod(fixture.DatabaseTests.setUpClass.__func__)
    tearDown=fixture.DatabaseTests.tearDown

    def setUp(self):
        fixture.DatabaseTests.setUp(self)
        self.user={'id':str(uuid.uuid4()),'role':'admin','is_active':True}
        self.claims={'sub':self.user['id'],'role':'admin','allowed_routes':['Wall Preview Inbox']}

    def create(self):
        return crm.confirm(fixture.payload(),self.upload)[0]

    def status(self):
        return notifications.status(self.claims)

    def test_three_images_one_seen_persists_and_other_user_stays_unread(self):
        rows=[self.create() for _ in range(3)]
        self.assertEqual(self.status()['unread_count'],3)
        # Polling and opening the list are read-only.
        ledger.list_previews(status='all',include_private=True)
        self.assertEqual(self.status()['unread_count'],3)
        notifications.mark_seen(rows[0]['id'],self.user)
        self.assertEqual(self.status()['unread_count'],2)
        self.assertNotIn(str(rows[0]['id']),[x['wall_preview_id'] for x in self.status()['notifications']])
        other={**self.claims,'sub':str(uuid.uuid4())}
        self.assertEqual(notifications.status(other)['unread_count'],3)
        # Fresh objects/connections model another login/device; no session cache.
        self.assertEqual(notifications.status(dict(self.claims))['unread_count'],2)
        for row in rows:notifications.mark_seen(row['id'],dict(self.user))
        self.assertEqual(self.status(),{'unread_count':0,'notifications':[]})

    def test_retry_and_concurrent_receipts_are_idempotent(self):
        row=crm.confirm(self.data,self.upload)[0]
        crm.confirm(self.data,self.upload)
        for _ in range(3):
            with crm.transaction() as cur:notifications.record(cur,row['id'])
        self.assertEqual(self.status()['unread_count'],1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:notifications.mark_seen(row['id'],self.user),range(8)))
        self.assertEqual(self.status()['unread_count'],0)
        with self.Adapter() as cur:
            cur.execute('SELECT count(*) AS n FROM app_sync_state WHERE key=%s',
                        (notifications._prefix(self.user['id'])+str(row['id']),))
            self.assertEqual(cur.fetchone()['n'],1)

    def test_historical_capture_retries_do_not_create_arrival(self):
        with patch.object(notifications,'record'):
            row=crm.confirm(self.data,self.upload)[0]
        crm.confirm(self.data,self.upload)
        self.assertEqual(self.status()['unread_count'],0)
        self.assertTrue(ledger.get_preview(str(row['id']),include_private=True))

    def test_failed_upload_has_no_event_and_deleted_pending_capture_disappears(self):
        with self.assertRaises(RuntimeError):
            crm.confirm(self.data,lambda *_:(_ for _ in ()).throw(RuntimeError('upload failed')))
        self.assertEqual(self.status()['unread_count'],0)
        row=self.create()
        with self.Adapter() as cur:
            cur.execute("UPDATE wall_previews SET attribution=attribution || '{\"inbox_deletion\":{}}'::jsonb WHERE id=%s",(row['id'],))
        self.assertEqual(self.status()['unread_count'],0)

    def test_permissions_and_private_image_visibility(self):
        row=self.create()
        self.assertEqual(notifications.status({**self.claims,'allowed_routes':[]})['unread_count'],0)
        worker={**self.claims,'role':'worker'}
        self.assertEqual(notifications.status(worker)['unread_count'],0)
        with patch('os_accounts.can_access_page',return_value=False):
            with self.assertRaises(PermissionError):notifications.mark_seen(row['id'],self.user)
        with patch('os_accounts.can_access_page',return_value=True):
            notifications.mark_seen(row['id'],{**self.user,'role':'worker'})
        self.assertEqual(self.status()['unread_count'],1)

    def test_count_includes_more_than_notification_window_and_targets_exact_image(self):
        rows=[self.create() for _ in range(12)]
        result=self.status()
        self.assertEqual(result['unread_count'],12)
        self.assertEqual(len(result['notifications']),10)
        self.assertEqual(result['notifications'][0]['route_key'],'social_media_wall_previews')
        self.assertEqual(result['notifications'][0]['wall_preview_id'],str(rows[-1]['id']))

    def test_legacy_ingest_emits_once(self):
        data={'image_sha256':'a'*64,'dropbox_path':'/fixture/new.jpg','image_width':640,
              'image_height':480,'image_bytes':100,'marketing_permission':True}
        row=ledger.record_preview(data)
        ledger.record_preview(data)
        self.assertEqual(self.status()['unread_count'],1)
        self.assertEqual(self.status()['notifications'][0]['wall_preview_id'],str(row['id']))

    def test_notification_and_capture_commit_together(self):
        original=notifications.record
        def interrupted(cur,identity):
            original(cur,identity)
            raise RuntimeError('transaction interrupted')
        with patch.object(notifications,'record',side_effect=interrupted):
            with self.assertRaises(RuntimeError):self.create()
        self.assertEqual(self.status()['unread_count'],0)
        self.assertEqual(ledger.list_previews(status='all',include_private=True),[])


class NotificationApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_endpoint_combines_existing_items_and_wall_count(self):
        import httpx
        import top_bar_api
        from starlette.applications import Starlette
        from starlette.routing import Route
        app=Starlette(routes=[Route(top_bar_api.NOTIFICATIONS_PATH,top_bar_api.top_bar_notifications)])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://fixture') as client:
            response=await client.get(top_bar_api.NOTIFICATIONS_PATH)
            self.assertEqual(response.status_code,403)
            with patch.object(top_bar_api,'_claims',return_value={'sub':'fixture'}), \
                 patch.object(top_bar_api,'load_notification_sources',return_value=([],[])), \
                 patch.object(top_bar_api,'build_notifications',return_value=[{'title':'Existing order'}]), \
                 patch.object(notifications,'status',return_value={'unread_count':3,'notifications':[{'title':'New image'}]}):
                response=await client.get(top_bar_api.NOTIFICATIONS_PATH)
                self.assertEqual(response.json()['wall_unread_count'],3)
                self.assertEqual([item['title'] for item in response.json()['notifications']],['New image','Existing order'])
            with patch.object(top_bar_api,'_claims',return_value={'sub':'fixture'}), \
                 patch.object(top_bar_api,'load_notification_sources',return_value=([],[])), \
                 patch.object(top_bar_api,'build_notifications',return_value=[{'title':'Existing email'}]), \
                 patch.object(notifications,'status',side_effect=RuntimeError('database unavailable')):
                response=await client.get(top_bar_api.NOTIFICATIONS_PATH)
                self.assertIsNone(response.json()['wall_unread_count'])
                self.assertEqual(response.json()['notifications'],[{'title':'Existing email'}])
