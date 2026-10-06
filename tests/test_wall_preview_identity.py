"""Customer matching and per-customer archive tests; Shopify/Dropbox are mocked."""
import io
import logging
import asyncio
import time
import unittest
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import Mock, patch

import wall_preview_api as api
import wall_preview_identity as identity
import wall_preview_store as store
import wall_preview_inbox as inbox
import run_migrations
from tests.test_wall_preview_feature import WallPreviewHttpTests, INBOX_PAGE
from streamlit.testing.v1 import AppTest
from PIL import Image


def page(customers, more=False, cursor=None):
    return {'nodes':customers, 'pageInfo':{'hasNextPage':more, 'endCursor':cursor}}


class IdentityTests(unittest.TestCase):
    def test_exact_match_canonicalizes_and_ignores_claimed_id(self):
        shop = Mock()
        shop.customers.return_value = page([
            {'id':'gid://shopify/Customer/1', 'email':'other@example.com'},
            {'id':'gid://shopify/Customer/42', 'email':'JANE@Example.com',
             'firstName':'Jane', 'lastName':'Collector',
             'emailMarketingConsent':{'marketingState':'UNSUBSCRIBED'}}])
        with patch.object(identity.crm_shopify, 'Shopify', return_value=shop):
            result = identity.resolve(' JANE@example.com ', 'Entered Name', 'logged_in')
        self.assertEqual(result, {'customer_email':'jane@example.com', 'customer_name':'Jane Collector',
            'shopify_customer_id':'gid://shopify/Customer/42', 'identity_source':'logged_in',
            'email_marketing_state':'UNSUBSCRIBED'})
        shop.customers.assert_called_once_with(query='email:"jane@example.com"', fresh=True, after=None)
        shop.unsubscribe_only.assert_not_called()

    def test_no_match_ambiguous_or_outage_stays_guest_unknown(self):
        shop = Mock()
        for response in (page([]), page([{'id':'1','email':'jane@example.com'}, {'id':'2','email':'jane@example.com'}])):
            shop.customers.return_value = response
            with patch.object(identity.crm_shopify, 'Shopify', return_value=shop):
                result = identity.resolve('jane@example.com', 'Jane', 'logged_in')
            self.assertEqual(result['identity_source'],'guest')
            self.assertEqual(result['shopify_customer_id'],'')
            self.assertEqual(result['email_marketing_state'],'UNKNOWN')
        shop.customers.side_effect = RuntimeError('temporary provider failure')
        with patch.object(identity.crm_shopify, 'Shopify', return_value=shop):
            result = identity.resolve('jane@example.com','Jane','guest')
        self.assertEqual(result['email_marketing_state'],'UNKNOWN')
        shop.unsubscribe_only.assert_not_called()

    def test_pagination_exact_match_and_incomplete_results_never_trusted(self):
        shop = Mock()
        shop.customers.side_effect = [page([], True, 'next'), page([{'id':'1','email':'jane@example.com'}])]
        with patch.object(identity.crm_shopify,'Shopify',return_value=shop):
            self.assertEqual(identity.resolve('jane@example.com','Jane','guest')['shopify_customer_id'],'gid://shopify/Customer/1')
        shop.customers.side_effect = None
        shop.customers.return_value = page([{'id':'1','email':'jane@example.com'}],True,'repeated')
        with patch.object(identity.crm_shopify,'Shopify',return_value=shop):
            self.assertEqual(identity.resolve('jane@example.com','Jane','logged_in')['shopify_customer_id'],'')

    def test_required_identity_validation(self):
        for address,name,source in [('', 'Jane','guest'), ('bad','Jane','guest'),
                ('jane@example.com','','guest'), ('jane@example.com','x'*201,'guest'),
                ('jane@example.com','Jane','fake'), ('a\x00@example.com','Jane','guest')]:
            with self.assertRaises(ValueError):identity.resolve(address,name,source)

    def test_folder_identity_sanitizing_and_no_date_nesting(self):
        def folder(value):
            return api._dropbox_destination('/Sportscave Team Folder','edition','a'*64,'image/jpeg',value)
        one,path = folder(' JANE@Example.com ')
        self.assertEqual(one, '/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox/jane@example.com')
        self.assertEqual(one, folder('jane@example.com')[0])
        self.assertNotEqual(one, folder('other@example.com')[0])
        self.assertEqual(path.count('/'),one.count('/')+1)
        self.assertRegex(path.rsplit('/',1)[-1], r'^edition-\d{8}T\d{12}Z-a{16}\.jpg$')
        dangerous = identity.customer_folder_name('some/\\:*?"|one@example.com')
        self.assertFalse(any(char in dangerous for char in '/\\:*?"|'))
        self.assertNotEqual(identity.customer_folder_name('a/b@example.com'),identity.customer_folder_name('a%2Fb@example.com'))

    def test_configured_admin_customer_link_only(self):
        with patch('shopify_sync.get_config',return_value={'store_domain':'real-store.myshopify.com'}):
            self.assertEqual(identity.customer_admin_url('gid://shopify/Customer/42'),'https://admin.shopify.com/store/real-store/customers/42')
            self.assertEqual(identity.customer_admin_url('not-a-customer'),'')
        with patch('shopify_sync.get_config',return_value={'store_domain':'evil.example'}):
            self.assertEqual(identity.customer_admin_url('42'),'')

    def test_identity_migration_reviewed_and_server_only(self):
        path=Path('migrations/20261004_wall_preview_customer_identity.sql')
        sql=path.read_text()
        self.assertTrue(run_migrations.reviewed_migration_sql(path,sql))
        self.assertIn(path.name,run_migrations.DEPLOYMENT_MIGRATIONS)
        self.assertIn('ENABLE ROW LEVEL SECURITY',sql)
        self.assertIn('REVOKE ALL',sql)
        self.assertNotIn('ip_address',sql)

    def test_access_logs_exclude_identity_queries_only_for_wall_preview(self):
        import sports_cave_server
        wall_filter=sports_cave_server._WallPreviewAccessLogFilter()
        def record(path):
            return logging.LogRecord('uvicorn.access',logging.INFO,'',0,
                '%s - "%s %s HTTP/%s" %d',('client','POST',path,'1.1',200),None)
        self.assertFalse(wall_filter.filter(record('/api/wall-previews?customer_email=private@example.com&customer_name=Private')))
        self.assertTrue(wall_filter.filter(record('/healthz')))

    def test_indexed_prefix_search_escapes_wildcards_and_is_parameterized(self):
        conn=Mock();cur=Mock();conn.cursor.return_value=nullcontext(cur);cur.fetchall.return_value=[]
        with patch.object(store,'_backend') as backend:
            backend.return_value.connect.return_value=nullcontext(conn)
            store.list_previews(customer_search='Jane%_')
        sql,params=cur.execute.call_args.args
        self.assertIn('customer_email LIKE %s',sql)
        self.assertIn('marketing_permission = TRUE',sql)
        self.assertEqual(params,('new',r'jane\%\_%',r'jane\%\_%',r'jane\%\_%',36))


class IdentityHttpTests(WallPreviewHttpTests):
    async def test_concurrent_same_customer_double_click_uploads_once(self):
        stream=io.BytesIO();Image.new('RGB',(10,20)).save(stream,'JPEG');blob=stream.getvalue()
        state={}
        def save(payload):
            state['row']={'id':'preview','marketing_permission':False}
            return state['row']
        def upload(*args,**kwargs):
            time.sleep(.03)
            return {'id':'file'}
        with patch.object(store,'find_preview',side_effect=lambda *args,**kwargs:state.get('row')), patch.object(api,'_dropbox_connection',return_value=('token','/Sportscave Team Folder')), patch('dropbox_integration.ensure_folder_path'), patch('dropbox_integration.upload_stream',side_effect=upload) as uploader, patch.object(store,'record_preview',side_effect=save):
            params={'customer_email':'jane@example.com','customer_name':'Jane','identity_source':'guest'}
            results=await asyncio.gather(*(self.client.post('/api/wall-previews',params=params,content=blob,headers=self.headers) for _ in range(2)))
            self.assertEqual([result.status_code for result in results],[200,200])
            self.assertEqual(sorted(result.json().get('duplicate',False) for result in results),[False,True])
            uploader.assert_called_once()

    async def test_logged_in_request_uses_server_matched_customer_not_claim(self):
        stream=io.BytesIO();Image.new('RGB',(10,20)).save(stream,'JPEG');blob=stream.getvalue()
        self.identity_shop.stop()
        shop=Mock();shop.customers.return_value=page([{'id':'gid://shopify/Customer/42','email':'jane@example.com','firstName':'Canonical Jane','emailMarketingConsent':{'marketingState':'SUBSCRIBED'}}])
        with patch.object(identity.crm_shopify,'Shopify',return_value=shop), patch.object(store,'find_preview',return_value=None), patch.object(api,'_dropbox_connection',return_value=('token','/Sportscave Team Folder')), patch('dropbox_integration.ensure_folder_path'), patch('dropbox_integration.upload_stream',return_value={'id':'file'}), patch.object(store,'record_preview',return_value={'id':'preview','marketing_permission':False}) as save:
            response=await self.client.post('/api/wall-previews',params={'customer_email':'JANE@example.com','customer_name':'Posted Jane','shopify_customer_id':'999','identity_source':'logged_in'},content=blob,headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(save.call_args.args[0]['shopify_customer_id'],'gid://shopify/Customer/42')
            self.assertEqual(save.call_args.args[0]['customer_name'],'Canonical Jane')
            self.assertEqual(save.call_args.args[0]['email_marketing_state'],'SUBSCRIBED')
            self.assertFalse(save.call_args.args[0]['marketing_permission'])
            shop.unsubscribe_only.assert_not_called()

    async def test_required_guest_identity_and_safe_public_response(self):
        stream=io.BytesIO();Image.new('RGB',(10,20)).save(stream,'JPEG');blob=stream.getvalue()
        with patch.object(api,'_dropbox_connection') as connection:
            for params in ({}, {'customer_email':'jane@example.com','identity_source':'guest'},
                           {'customer_name':'Jane','identity_source':'guest'}):
                response=await self.client.post('/api/wall-previews',params=params,content=blob,headers=self.headers)
                self.assertEqual(response.status_code,400)
            connection.assert_not_called()

    async def test_clean_bytes_archived_unchanged_identity_and_outage(self):
        stream=io.BytesIO();Image.new('RGB',(10,20),'red').save(stream,'PNG');blob=stream.getvalue()
        self.identity_shop.stop()
        shop=Mock();shop.customers.side_effect=RuntimeError('provider unavailable')
        with patch.object(identity.crm_shopify,'Shopify',return_value=shop), patch.object(store,'find_preview',return_value=None), patch.object(api,'_dropbox_connection',return_value=('token','/Sportscave Team Folder')), patch('dropbox_integration.ensure_folder_path') as ensure, patch('dropbox_integration.upload_stream',return_value={'id':'file'}) as upload, patch.object(store,'record_preview',return_value={'id':'preview','marketing_permission':False}) as save:
            response=await self.client.post('/api/wall-previews',params={'customer_email':' JANE@example.com ', 'customer_name':'Jane', 'shopify_customer_id':'999', 'identity_source':'logged_in'},content=blob,headers=dict(self.headers,**{'Content-Type':'image/png'}))
            self.assertEqual(response.status_code,200)
            self.assertEqual(upload.call_args.args[2].getvalue(),blob)
            payload=save.call_args.args[0]
            self.assertEqual(payload['customer_email'],'jane@example.com')
            self.assertEqual(payload['shopify_customer_id'],'')
            self.assertEqual(payload['email_marketing_state'],'UNKNOWN')
            self.assertEqual(payload['customer_folder'],ensure.call_args.args[1])
            self.assertTrue(payload['dropbox_path'].startswith(payload['customer_folder']+'/'))
            self.assertNotIn('customer_email',response.json())
            self.assertNotIn('shopify_customer_id',response.json())
            self.assertNotIn('email_marketing_state',response.json())
            self.assertNotIn('jane',response.text)


class IdentityUiTests(unittest.TestCase):
    def test_staff_has_no_admin_customer_action(self):
        original=inbox._temporary_link
        try:
            app=AppTest.from_string('''
import wall_preview_inbox as inbox
inbox._temporary_link=lambda *args: 'https://dl.dropboxusercontent.com/fixture.jpg'
inbox._details({'role':'worker','is_active':True},
    {'id':'a','customer_email':'jane@example.com','customer_name':'Jane',
     'shopify_customer_id':'gid://shopify/Customer/42','marketing_permission':True,
     'dropbox_path':'/a.jpg','status':'new'})
''').run()
            self.assertEqual(len(app.exception),0)
            self.assertNotIn('Open Shopify customer',[item.label for item in app.get('link_button')])
        finally:inbox._temporary_link=original

    def test_customer_display_and_admin_action(self):
        original=(store.summary,store.list_previews,inbox._temporary_link)
        try:
            with patch.object(inbox,'_current_marketing',return_value={'gid://shopify/Customer/42':{'id':'gid://shopify/Customer/42','email':'jane@example.com','emailMarketingConsent':{'marketingState':'UNSUBSCRIBED'}}}), patch.object(identity,'customer_admin_url',return_value='https://admin.shopify.com/store/test/customers/42'):
                app=AppTest.from_string(INBOX_PAGE)
                app.session_state['fixture-rows']=[{'id':'a','customer_name':'Jane Collector','customer_email':'jane@example.com', 'shopify_customer_id':'gid://shopify/Customer/42','marketing_permission':True,'status':'new','dropbox_path':'/a.jpg'}]
                app.run()
                self.assertEqual(len(app.exception),0)
                markup='\n'.join(item.value for item in app.markdown)
                self.assertIn('jane@example.com',str(app.get('component_instance')[-1].proto))
                self.assertIn('jane@example.com',str(app.get('component_instance')[-1].proto))
                self.assertEqual(len(app.get('component_instance')),1)
                self.assertIn('Search customer or product',[item.label for item in app.text_input])
        finally:
            store.summary,store.list_previews,inbox._temporary_link=original

    def test_current_marketing_one_readonly_batch_not_per_card(self):
        shop=Mock();shop.customer_batch.return_value=[{'id':'gid://shopify/Customer/1','email':'jane@example.com'}]
        with patch.object(identity.crm_shopify,'Shopify',return_value=shop):
            inbox._current_marketing([{'shopify_customer_id':'gid://shopify/Customer/1'}]*8)
        shop.customer_batch.assert_called_once_with(['gid://shopify/Customer/1'])
        shop.unsubscribe_only.assert_not_called()
