import io
import unittest
import json
import asyncio
import os
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.routing import Route
from streamlit.testing.v1 import AppTest

from PIL import Image

import wall_preview_api
import wall_preview_store
import wall_preview_inbox
import run_migrations


class WallPreviewFeatureTests(unittest.TestCase):
    def _jpeg(self, size=(640, 480)):
        stream = io.BytesIO()
        Image.new("RGB", size, "white").save(stream, format="JPEG", quality=90)
        return stream.getvalue()

    def test_storefront_origins_are_allowed_by_default(self):
        allowed = wall_preview_api._allowed_origins()
        self.assertIn("https://www.sportscaveshop.com", allowed)
        self.assertIn("https://sportscaveshop.com", allowed)

    def test_image_validation_accepts_email_safe_jpeg(self):
        width, height = wall_preview_api._inspect_image(
            self._jpeg(),
            "image/jpeg",
        )
        self.assertEqual((width, height), (640, 480))

    def test_image_validation_rejects_non_image_payload(self):
        with self.assertRaises(ValueError):
            wall_preview_api._inspect_image(b"not-an-image", "image/jpeg")

    def test_dropbox_path_is_scoped_to_wall_previews(self):
        folder, destination = wall_preview_api._dropbox_destination(
            "/Sportscave Team Folder",
            "Cristiano Ronaldo — The Mentality",
            "a" * 64,
            "image/jpeg",
            "Customer@Example.com",
        )
        self.assertIn("/03_ASSETS/11 Wall Preview Inbox/", folder)
        self.assertTrue(destination.startswith(folder + "/"))
        self.assertTrue(destination.endswith(".jpg"))
        self.assertNotIn("—", destination)

    def test_approval_states_are_bounded(self):
        self.assertEqual(
            wall_preview_store.VALID_STATUSES,
            ("new", "approved", "used", "archived"),
        )

    def test_png_dimension_limits_and_no_global_pillow_changes(self):
        stream = io.BytesIO(); Image.new('RGB', (10, 20)).save(stream, 'PNG')
        previous = Image.MAX_IMAGE_PIXELS
        self.assertEqual(wall_preview_api._inspect_image(stream.getvalue(), 'image/png'), (10, 20))
        with self.assertRaises(ValueError):
            wall_preview_api._inspect_image(self._jpeg((10001, 1)), 'image/jpeg')
        self.assertEqual(Image.MAX_IMAGE_PIXELS, previous)

    def test_migration_sha_is_reviewed_and_in_startup_manifest(self):
        path = Path('migrations/20261004_wall_preview_inbox.sql')
        self.assertTrue(run_migrations.reviewed_migration_sql(path, path.read_text(encoding='utf-8')))
        self.assertIn(path.name, run_migrations.DEPLOYMENT_MIGRATIONS)

    def test_sydney_timestamp_from_database_or_string(self):
        value = datetime(2026, 10, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(wall_preview_inbox._format_received(value), '04 Oct 2026 · 11:00 AM')
        self.assertEqual(wall_preview_inbox._format_received(value.isoformat()), '04 Oct 2026 · 11:00 AM')

    def test_permission_enforced_for_approval_used_and_staff_archive(self):
        conn = Mock(); cur = Mock(); conn.cursor.return_value = nullcontext(cur)
        cur.fetchone.return_value = {'marketing_permission': False}
        with patch.object(wall_preview_store, '_backend') as backend:
            backend.return_value.connect.return_value = nullcontext(conn)
            for status in ('approved', 'used', 'archived'):
                with self.assertRaises(wall_preview_store.WallPreviewStoreError):
                    wall_preview_store.update_status('preview-id', status)
                conn.rollback.assert_called()
            cur.fetchone.return_value = {'marketing_permission': True, 'id': 'preview-id'}
            for status in ('approved', 'used', 'archived'):
                self.assertEqual(wall_preview_store.update_status('preview-id', status)['id'], 'preview-id')

    def test_newest_first_private_filter_and_counts(self):
        conn = Mock(); cur = Mock(); conn.cursor.return_value = nullcontext(cur)
        cur.fetchall.return_value = []; cur.fetchone.return_value = {'new': 2, 'approved': 1, 'used': 0, 'private': 0}
        with patch.object(wall_preview_store, '_backend') as backend:
            backend.return_value.connect.return_value = nullcontext(conn)
            wall_preview_store.list_previews(status='all')
            sql = cur.execute.call_args.args[0]
            self.assertIn('marketing_permission = TRUE', sql)
            self.assertIn('ORDER BY received_at DESC', sql)
            self.assertEqual(wall_preview_store.summary()['new'], 2)
            self.assertIn('AND marketing_permission=TRUE', cur.execute.call_args.args[0])


class WallPreviewHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.identity_shop = patch('wall_preview_identity.crm_shopify.Shopify')
        self.identity_shop.start().return_value.customers.return_value = {'nodes':[], 'pageInfo':{'hasNextPage':False}}
        wall_preview_api._RATE_BUCKETS.clear()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=Starlette(routes=[
            Route(wall_preview_api.WALL_PREVIEW_PATH, wall_preview_api.wall_preview_ingest, methods=['POST','OPTIONS'])
        ])), base_url='https://fixture')
        self.headers = {'Origin':'https://sportscaveshop.com', 'Content-Type':'image/jpeg'}

    async def asyncTearDown(self):
        self.identity_shop.stop()
        await self.client.aclose()

    async def test_valid_upload_and_duplicate_avoid_second_dropbox_upload(self):
        blob = WallPreviewFeatureTests()._jpeg()
        row = {'id':'preview', 'marketing_permission':False}
        with patch('wall_preview_store.find_preview', side_effect=[None,row]), patch('wall_preview_api._dropbox_connection', return_value=('token','/Sportscave Team Folder')), patch('dropbox_integration.ensure_folder_path'), patch('dropbox_integration.upload_stream', return_value={'id':'file'}) as upload, patch('wall_preview_store.record_preview',return_value=row) as save:
            response = await self.client.post('/api/wall-previews?customer_email=guest@example.com&customer_name=Guest&identity_source=guest&frame=Black&size=Large&unit=cm&marketing_permission=false', content=blob,headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(save.call_args.args[0]['image_bytes'],len(blob))
            self.assertFalse(save.call_args.args[0]['marketing_permission'])
            duplicate = await self.client.post('/api/wall-previews?customer_email=guest@example.com&customer_name=Guest&identity_source=guest&marketing_permission=true',content=blob,headers=self.headers)
            self.assertTrue(duplicate.json()['duplicate']);self.assertFalse(duplicate.json()['marketing_permission'])
            upload.assert_called_once(); save.assert_called_once()

    async def test_invalid_oversize_stream_and_cors(self):
        response = await self.client.options('/api/wall-previews',headers=self.headers)
        self.assertEqual(response.status_code,204);self.assertEqual(response.headers['access-control-allow-origin'],self.headers['Origin'])
        response = await self.client.options('/api/wall-previews',headers={'Origin':'https://evil.example'})
        self.assertEqual(response.status_code,403);self.assertNotIn('access-control-allow-origin',response.headers)
        response = await self.client.post('/api/wall-previews',content=b'bad',headers=self.headers)
        self.assertEqual(response.status_code,400)
        async def chunks():
            yield b'x'*7;yield b'x'*7
        with patch.object(wall_preview_api,'MAX_IMAGE_BYTES',10):
            response = await self.client.post('/api/wall-previews',content=chunks(),headers=self.headers)
            self.assertEqual(response.status_code,413)

    async def test_rate_limit_and_storage_failure_are_safe(self):
        with patch.object(wall_preview_api,'RATE_LIMIT',1):
            await self.client.post('/api/wall-previews',content=b'bad',headers=self.headers)
            response = await self.client.post('/api/wall-previews',content=b'bad',headers=self.headers)
            self.assertEqual(response.status_code,429)
        wall_preview_api._RATE_BUCKETS.clear()
        with patch('wall_preview_store.find_preview',side_effect=RuntimeError('private secret')):
            response = await self.client.post('/api/wall-previews?customer_email=guest@example.com&customer_name=Guest&identity_source=guest',content=WallPreviewFeatureTests()._jpeg(),headers=self.headers)
            self.assertEqual(response.status_code,503);self.assertNotIn('private',response.text)

    async def test_storage_io_leaves_event_loop_responsive(self):
        started = threading.Event(); release = threading.Event()
        def slow(*args):
            started.set(); release.wait(2)
            return wall_preview_api.JSONResponse({'ok':True})
        with patch('wall_preview_api._save_preview',side_effect=slow):
            task = asyncio.create_task(self.client.post('/api/wall-previews',content=b'image',headers=self.headers))
            for _ in range(100):
                if started.is_set():break
                await asyncio.sleep(.01)
            self.assertTrue(started.is_set());self.assertFalse(task.done())
            release.set();self.assertEqual((await task).status_code,200)


INBOX_PAGE = '''
import streamlit as st
import wall_preview_inbox as inbox
user={'id':'admin','role':'admin','is_active':True,'page_permissions':[]}
inbox.wall_preview_store.summary=lambda **kwargs: {'new':1,'approved':0,'used':0,'private':1}
inbox.wall_preview_store.list_previews=lambda **kwargs: st.session_state.get('fixture-rows', [])
inbox._temporary_link=lambda path, file_id='': 'https://dl.dropboxusercontent.com/fixture.jpg'
inbox._page.clear()
inbox.render(user)
'''


class WallPreviewUiTests(unittest.TestCase):
    def setUp(self):
        self.originals = (wall_preview_store.summary, wall_preview_store.list_previews, wall_preview_inbox._temporary_link)

    def tearDown(self):
        wall_preview_store.summary, wall_preview_store.list_previews, wall_preview_inbox._temporary_link = self.originals

    def test_empty_gallery_is_clean_and_has_no_toolbar_or_metrics(self):
        app = AppTest.from_string(INBOX_PAGE).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 0)
        self.assertIn('Refresh', [button.label for button in app.button])
        self.assertIn('Open Wall Preview Folder', [button.label for button in app.button])
        self.assertEqual(next(x for x in app.selectbox if x.label=='Status').value, 'All')
        self.assertTrue(any('No customer wall previews match' in item.value for item in app.info))

    def test_gallery_cards_are_image_first_and_action_free(self):
        app = AppTest.from_string(INBOX_PAGE)
        app.session_state['fixture-rows'] = [
            {
                'id':'a',
                'customer_name':'Jane Collector',
                'customer_email':'jane@example.com',
                'product_title':'Collector edition',
                'marketing_permission':False,
                'dropbox_path':'/a.jpg',
                'status':'new',
            },
            {
                'id':'b',
                'customer_name':'Sam Fan',
                'customer_email':'sam@example.com',
                'product_title':'Another edition',
                'marketing_permission':True,
                'dropbox_path':'/b.jpg',
                'status':'approved',
                'product_url':'https://sportscaveshop.com/products/edition',
            },
        ]
        app.run()
        self.assertEqual(len(app.exception), 0)
        labels = [button.label for button in app.button]
        self.assertNotIn('Approve', labels)
        self.assertNotIn('Mark used', labels)
        self.assertNotIn('Archive', labels)
        self.assertEqual(len(app.get('link_button')), 0)
        args=json.loads(app.get('component_instance')[-1].proto.json_args)
        self.assertEqual([r['title'] for r in args['items']],['Collector edition','Another edition'])
        self.assertEqual(args['items'][0]['identity'],'jane@example.com')
        self.assertTrue(args['canDelete'])

    def test_staff_cannot_request_private_image_even_from_injected_row(self):
        with patch.object(wall_preview_inbox,'_temporary_link') as link:
            wall_preview_inbox._details({'role':'worker','is_active':True}, {'marketing_permission':False})
            link.assert_not_called()

    def test_dropbox_path_failure_uses_stable_file_id_without_public_sharing(self):
        wall_preview_inbox._TEMP_LINK_CACHE.clear()
        client=Mock();client.files_get_temporary_link.return_value.link='https://dl.dropboxusercontent.com/temporary.jpg'
        with patch.object(wall_preview_inbox,'_dropbox_connection',return_value='token'), patch('dropbox_integration.get_temporary_link',side_effect=wall_preview_inbox.dropbox_integration.DropboxApiError('not_found')), patch('dropbox_integration.team_space_client',return_value=client):
            self.assertIn('temporary.jpg',wall_preview_inbox._temporary_link('/original.jpg','id:stable'))
            client.files_get_temporary_link.assert_called_once_with('id:stable')

    def test_overview_has_no_wall_preview_calls(self):
        import inspect, social_media_page
        source=inspect.getsource(social_media_page.render_page)
        self.assertNotIn('wall_preview_inbox.render',source)
        self.assertNotIn('wall_preview_analytics_ui',source)
        self.assertIn('"Overview", "Create", "Plan", "Playbook", "Tracking"',source)


def inbox_path():
    return '/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox'


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES') == '1', 'Disposable loopback database required')
class WallPreviewDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.crm_db_fixture import connect
        with connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS public.os_users(id uuid PRIMARY KEY)')
            for name in run_migrations.WALL_PREVIEW_MIGRATIONS:
                sql=Path('migrations', name).read_text().replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;', '')
                for statement in sql.split(';'):
                    if statement.strip():conn.execute(statement)
                if name == '20261004_wall_preview_inbox.sql':
                    conn.execute("INSERT INTO public.wall_previews(image_sha256,dropbox_path,image_width,image_height,image_bytes) VALUES (%s,%s,640,480,1024) ON CONFLICT DO NOTHING", ('c'*64, inbox_path()+'/legacy.jpg'))
            legacy=conn.execute("SELECT customer_email,identity_source,email_marketing_state FROM public.wall_previews WHERE image_sha256=%s",('c'*64,)).fetchone()
            assert legacy == {'customer_email':'','identity_source':'','email_marketing_state':'UNKNOWN'}

    def test_real_sql_deduplication_status_consent_and_schema(self):
        from tests.crm_db_fixture import Connection
        with Connection() as conn:
            conn.execute('TRUNCATE public.wall_previews CASCADE')
        class Adapter(Connection):
            def cursor(self):return nullcontext(self)
            def execute(self,sql,args=()):
                self.result=super().execute(sql,args);return self.result
            def fetchone(self):return self.result.fetchone()
            def fetchall(self):return self.result.fetchall()
            def commit(self):pass # enclosing fixture context owns transaction
            def rollback(self):pass
        payload={'image_sha256':'a'*64,'dropbox_path':inbox_path()+'/test.jpg', 'product_title':'Actual edition', 'image_width':640,'image_height':480,'image_bytes':1024,'marketing_permission':False}
        with patch.object(wall_preview_store,'_backend') as backend:
            backend.return_value.connect.side_effect=Adapter
            first=wall_preview_store.record_preview(payload)
            duplicate=wall_preview_store.record_preview(dict(payload,marketing_permission=True,product_title='Forged title'))
            self.assertEqual(first['id'],duplicate['id']);self.assertTrue(duplicate['duplicate'])
            self.assertFalse(duplicate['marketing_permission']);self.assertEqual(duplicate['product_title'],'Actual edition')
            for status in ('approved','used'):
                with self.assertRaises(wall_preview_store.WallPreviewStoreError):wall_preview_store.update_status(first['id'],status,include_private=True)
            self.assertEqual(wall_preview_store.list_previews(status='all'),[])
            self.assertEqual(wall_preview_store.summary(include_private=True)['private'],1)
            permitted=wall_preview_store.record_preview(dict(payload,image_sha256='b'*64,marketing_permission=True))
            for status in ('approved','used','archived'):
                self.assertEqual(wall_preview_store.update_status(permitted['id'],status)['status'],status)
            with Adapter() as cur:self.assertEqual(wall_preview_store.schema_issues(cur),[])
            # The same image from two emails remains separate from its legacy
            # owner, with independent consent and identity, and indexed search.
            jane=wall_preview_store.record_preview(dict(payload,customer_email='jane@example.com',customer_name='Jane Collector',identity_source='guest'))
            other=wall_preview_store.record_preview(dict(payload,customer_email='other@example.com',customer_name='Other Collector',identity_source='guest',marketing_permission=True))
            self.assertNotEqual(jane['id'],other['id'])
            self.assertNotEqual(jane['id'],first['id'])
            self.assertEqual(wall_preview_store.find_preview('a'*64,customer_email='jane@example.com')['id'],jane['id'])
            self.assertEqual([row['id'] for row in wall_preview_store.list_previews(status='all',customer_search='Jane',include_private=True)],[jane['id']])
            self.assertEqual(wall_preview_store.list_previews(status='all',customer_search='Jane'),[])
            # Safe to replay the new additive migration; data is retained.
            with Adapter() as cur:
                for statement in Path('migrations/20261004_wall_preview_customer_identity.sql').read_text().split(';'):
                    if statement.strip():cur.execute(statement)
                self.assertEqual(wall_preview_store.schema_issues(cur),[])
                cur.execute("SELECT has_table_privilege('anon','public.wall_previews','SELECT') AS anon,has_table_privilege('authenticated','public.wall_previews','SELECT') AS authenticated")
                self.assertEqual(cur.fetchone(),{'anon':False,'authenticated':False})


if __name__ == "__main__":
    unittest.main()
