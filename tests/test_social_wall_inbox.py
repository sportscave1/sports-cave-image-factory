"""Local PostgreSQL and rendered UI regressions for the dedicated inbox."""
import inspect
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from streamlit.testing.v1 import AppTest
import wall_preview_store as ledger
import wall_preview_crm_store as crm
import wall_preview_inbox as inbox
import os_accounts
from tests import test_wall_preview_crm_v2 as fixtures
payload=fixtures.payload

ADMIN={'id':str(uuid.uuid4()),'role':'admin','is_active':True}

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback PostgreSQL required')
class InboxDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.DatabaseTests.setUpClass.__func__)
    setUp=fixtures.DatabaseTests.setUp
    tearDown=fixtures.DatabaseTests.tearDown
    create=fixtures.DatabaseTests.create

    def test_delete_one_retains_events_and_other_preview_and_is_idempotent(self):
        row=self.create();pid=str(row['id'])
        other=crm.confirm(payload(),Mock(return_value=dict(self.upload.return_value,path='/other.jpg',file_id='id:other')))[0]
        before=crm.timeline(pid)
        remove=Mock()
        with patch('activity_log.record_activity_log') as audit:
            self.assertTrue(ledger.delete_preview(pid,user=ADMIN,remove_asset=remove))
            self.assertFalse(ledger.delete_preview(pid,user=ADMIN,remove_asset=remove))
            remove.assert_called_once();audit.assert_called_once()
        self.assertEqual(ledger.get_preview(pid,include_private=True),{})
        self.assertEqual(crm.timeline(pid),before)
        self.assertEqual([str(r['id']) for r in ledger.list_previews(status='all',include_private=True)],[str(other['id'])])
        with self.assertRaises(ValueError):crm.confirm(self.data,self.upload)

    def test_storage_failure_rolls_back_and_retry_succeeds(self):
        row=self.create();pid=str(row['id'])
        with self.assertRaises(RuntimeError):ledger.delete_preview(pid,user=ADMIN,remove_asset=Mock(side_effect=RuntimeError('offline')))
        self.assertTrue(ledger.get_preview(pid,include_private=True))
        with patch('activity_log.record_activity_log'):
            self.assertTrue(ledger.delete_preview(pid,user=ADMIN,remove_asset=Mock()))

    def test_shared_asset_fails_closed_and_nonadmin_cannot_delete(self):
        row=self.create();crm.confirm(payload(),self.upload)
        remove=Mock()
        with self.assertRaises(ledger.WallPreviewStoreError):ledger.delete_preview(str(row['id']),user=ADMIN,remove_asset=remove)
        with self.assertRaises(PermissionError):ledger.delete_preview(str(row['id']),user={'role':'worker','is_active':True},remove_asset=remove)
        remove.assert_not_called()

    def test_keyset_pages_and_product_date_filters(self):
        for _ in range(5):crm.confirm(payload(),self.upload)
        first=ledger.list_previews(status='all',include_private=True,limit=2)
        second=ledger.list_previews(status='all',include_private=True,limit=2,cursor=(first[-1]['received_at'],str(first[-1]['id'])))
        self.assertEqual(len(first),2);self.assertEqual(len(second),2)
        self.assertFalse({r['id'] for r in first}&{r['id'] for r in second})
        self.assertEqual(ledger.list_previews(status='all',include_private=True,product_id='missing'),[])
        self.assertEqual(ledger.list_previews(status='all',include_private=True,end_date='2000-01-01T00:00:00Z'),[])

    def test_pending_job_image_removed_without_upload(self):
        self.data['archive_image']=b'fixture'
        self.upload.return_value['file_id']=''
        row=self.create();pid=str(row['id']);remove=Mock()
        with self.Adapter() as cur:
            cur.execute("INSERT INTO wall_preview_archive_jobs(preview_id,version,image) VALUES (%s,1,decode('ff','hex'))",(pid,))
        with patch('activity_log.record_activity_log'):ledger.delete_preview(pid,user=ADMIN,remove_asset=remove)
        remove.assert_called_once()
        with self.Adapter() as cur:
            cur.execute('SELECT state,image,reason FROM wall_preview_archive_jobs WHERE preview_id=%s',(pid,))
            self.assertEqual(cur.fetchone(),{'state':'failed','image':None,'reason':'admin_deleted'})

    def test_device_source_filters_use_latest_known_dimensions(self):
        row=self.create();pid=str(row['id'])
        with self.Adapter() as cur:
            cur.execute("""INSERT INTO wall_preview_events(preview_id,client_preview_id,event_name,event_key,device_type,capture_source,occurred_at)
                VALUES (%s,%s,'WallPreviewPhotoReady','dimensions','mobile','camera',now()-interval '1 minute'),
                (%s,%s,'WallPreviewConfirmed','empty-dimensions','','',now())""",(pid,self.data['client_preview_id'],pid,self.data['client_preview_id']))
        self.assertEqual(len(ledger.list_previews(status='all',include_private=True,device_type='mobile',capture_source='camera')),1)
        self.assertEqual(ledger.list_previews(status='all',include_private=True,device_type='desktop'),[])

    def test_active_delivery_blocks_delete(self):
        row=self.create();pid=str(row['id'])
        with self.Adapter() as cur:
            cur.execute("INSERT INTO wall_preview_email_jobs(preview_id,kind,state) VALUES (%s,'requested','processing')",(pid,))
        remove=Mock()
        with self.assertRaises(ledger.WallPreviewStoreError):ledger.delete_preview(pid,user=ADMIN,remove_asset=remove)
        remove.assert_not_called()

    def test_large_inbox_returns_only_requested_page(self):
        import time,statistics
        with self.Adapter() as cur:
            cur.execute("""INSERT INTO wall_previews(image_sha256,dropbox_path,image_width,image_height,image_bytes,product_title)
                SELECT md5(i::text)||md5(i::text),'/fixture/'||i,640,480,1024,'Artwork '||i FROM generate_series(1,1000) i""")
        durations=[]
        for _ in range(5):
            start=time.perf_counter();rows=ledger.list_previews(status='all',include_private=True,limit=25)
            durations.append((time.perf_counter()-start)*1000)
            self.assertEqual(len(rows),25)
            self.assertNotIn('image',rows[0])
        print('1000-row local inbox: 25 metadata rows, median %.1fms'%statistics.median(durations))

class InboxUiTests(unittest.TestCase):
    def test_routes_share_existing_permission_and_overview_does_not_import_inbox(self):
        self.assertTrue(os_accounts.can_access_page(ADMIN,'Wall Preview Inbox'))
        self.assertFalse(os_accounts.can_access_page({'role':'worker','is_active':True,'page_permissions':[]},'Wall Preview Inbox'))
        import social_media_page
        source=inspect.getsource(social_media_page.render_page)
        self.assertNotIn('wall_preview_analytics_ui',source)
        self.assertNotIn('wall_preview_inbox.render',source)

    def test_rendered_overview_makes_zero_wall_preview_reads(self):
        from tests.test_social_media_page import READY_PAGE
        script=READY_PAGE.replace('"social-media-workspace-view", "Create"','"social-media-workspace-view", "Overview"')
        with patch('wall_preview_analytics.report',side_effect=AssertionError('Overview analytics query')) as report,patch.object(ledger,'list_previews',side_effect=AssertionError('Overview inbox query')) as previews:
            app=AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.segmented_control[0].value,'Overview')
            report.assert_not_called();previews.assert_not_called()

    def test_batch_thumbnails_never_download_originals(self):
        inbox._thumbnails.clear()
        success=Mock();success.is_success.return_value=True;success.get_success.return_value.thumbnail='fixture'
        client=Mock();client.files_get_thumbnail_batch.return_value.entries=[success]*24
        with patch.object(inbox,'_dropbox_connection',return_value='fixture'),patch.object(inbox.dropbox_integration,'team_space_client',return_value=client),patch.object(inbox.dropbox_integration,'get_file_bytes') as original:
            result=inbox._thumbnails(tuple((str(i),'/fixture/'+str(i),'1') for i in range(24)))
            self.assertEqual(len(result),24);client.files_get_thumbnail_batch.assert_called_once();original.assert_not_called()

    def test_reset_preserves_unrelated_state(self):
        with patch.object(inbox.st,'session_state',{'wp-analytics-device':'mobile','wall-preview-cursors':['x'],'other':'keep'}) as state:
            inbox._reset();self.assertEqual(state['other'],'keep');self.assertEqual(state['wp-analytics-device'],'All');self.assertEqual(state['wall-preview-cursors'],[None])

    def test_actual_sidebar_contains_three_social_children(self):
        app=AppTest.from_file('tests/sidebar_preview_app.py').run()
        app.session_state['route']='Wall Preview Inbox'
        app.session_state['sidebar-open-group']='social_media'
        app.run()
        self.assertFalse(app.exception)
        labels=[b.label for b in app.button]
        self.assertIn('Overview',labels);self.assertIn('Wall Preview Inbox',labels);self.assertIn('AI Reels',labels)
