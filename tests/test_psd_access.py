import json
import html
import os
import unittest
from unittest.mock import patch,Mock
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
import files_upload_api as api
import psd_directory as psd
import sc_auth
import os_accounts
from tests.test_psd_open import metadata

USERS={
    'admin':{'id':'admin','role':'admin','is_active':True,'session_version':3},
    'va_attach':{'id':'va_attach','role':'worker','is_active':True,'session_version':3,'page_permissions':['files','attach_missing_psd']},
    'va':{'id':'va','role':'worker','is_active':True,'session_version':3,'page_permissions':['files']},
    'unauthorised':{'id':'unauthorised','role':'worker','is_active':True,'session_version':3,'page_permissions':[]},
    'inactive':{'id':'inactive','role':'admin','is_active':False,'session_version':3},
}
PID='gid://shopify/Product/1'


class PsdAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app=Starlette(routes=[Route(path,handler,methods=list(methods)) for path,handler,methods in api.FILES_UPLOAD_ROUTES])
        self.cloud=Mock(return_value={'access_token':'fake','root_path':'/Sportscave Team Folder'})
        self.stream=Mock();self.stream.iter_content.return_value=[b'mock!'];
        self.store=Mock();self.store.get_product.return_value={'product_title':'Renamed'};self.store.read.return_value={}
        self.store.attach.return_value={'verified':True,'state':'Linked','dropbox_file_id':'id:1'}
        self.patches=[patch.dict(os.environ,{'SPORTS_CAVE_AUTH_SECRET':'local-test-secret'}),
            patch.object(os_accounts.DEFAULT_STORE,'get_user',side_effect=lambda key:USERS.get(key,{})),
            patch.object(api,'_dropbox_context',self.cloud),
            patch.object(psd,'directory',return_value={PID:{'verified':True,'state':'Linked','dropbox_file_id':'id:1'}}),
            patch.object(api.dropbox_integration,'psd_open_metadata',return_value=metadata()),
            patch.object(api,'_directory_entries',return_value=[metadata()]),
            patch.object(api.dropbox_integration,'get_psd_thumbnail_bytes',return_value=b'jpeg-preview'),
            patch.object(api.dropbox_integration,'get_psd_file_response',return_value=(metadata(),self.stream)),
            patch('psd_mapping_store.STORE',self.store)]
        for p in self.patches:p.start()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://test.local')

    async def asyncTearDown(self):
        await self.client.aclose()
        for p in reversed(self.patches):p.stop()

    def cookie(self,user,version=3,expired=False):
        self.client.cookies.clear()
        if user:
            token=sc_auth.create_user_auth_token(user,extra_secret='local-test-secret',session_version=version,now=1 if expired else None)
            self.client.cookies.set(sc_auth.AUTH_COOKIE_NAME,token)

    async def test_same_signed_account_has_device_independent_read_access(self):
        for ua in ['Windows Chrome','macOS Safari','macOS Chrome','iPhone Safari','iPad Safari','Android Chrome','Linux ChromeOS']:
            for role in ['admin','va','va_attach']:
                self.cookie(role)
                for path in ['/files-window','/api/files-psd-open?product_gid='+PID]:
                    response=await self.client.get(path,headers={'user-agent':ua})
                    self.assertEqual(response.status_code,200)
                    self.assertIn('text/html',response.headers['content-type'])
                for action in ['files','describe','openPhotoshop','preview']:
                    response=await self.client.post('/api/files-psd-open?product_gid='+PID,json={'action':action},headers={'origin':'https://test.local','user-agent':ua})
                    self.assertEqual(response.status_code,200,(role,ua,action))
                response=await self.client.get('/api/files-psd-original?product_gid='+PID,headers={'user-agent':ua})
                self.assertEqual(response.status_code,200);self.assertEqual(response.content,b'mock!')
        self.store.attach.assert_not_called()

    async def test_attachment_permission_uses_same_cookie_without_escalating_va(self):
        self.cookie('admin')
        self.assertEqual((await self.client.get('/files-psd-picker?product_gid='+PID)).status_code,200)
        self.assertEqual((await self.client.get('/api/files-psd-options?product_gid='+PID)).status_code,200)
        response=await self.client.post('/api/files-psd-attach',json={'product_gid':PID,'file_id':'id:1','confirm_mismatch':True},headers={'origin':'https://test.local'})
        self.assertEqual(response.status_code,200);self.assertEqual(self.store.attach.call_count,1)
        self.cookie('va')
        response=await self.client.get('/files-psd-picker?product_gid='+PID)
        self.assertEqual(response.status_code,403);self.assertIn('text/html',response.headers['content-type'])
        self.assertIn("don't have permission to attach PSD",html.unescape(response.text))
        self.assertNotIn('"ok":',response.text);self.assertNotIn('upload_error',response.text)
        self.assertEqual((await self.client.get('/api/files-psd-options?product_gid='+PID)).status_code,403)
        response=await self.client.post('/api/files-psd-attach',json={'product_gid':PID,'file_id':'id:1'},headers={'origin':'https://test.local'})
        self.assertEqual(response.status_code,403);self.assertEqual(response.json()['code'],'psd_attach_denied')
        self.assertEqual(self.store.attach.call_count,1)

    async def test_authorised_va_first_attach_and_admin_only_replacement(self):
        self.cookie('va_attach')
        self.assertEqual((await self.client.get('/files-psd-picker?product_gid='+PID)).status_code,200)
        options=await self.client.get('/api/files-psd-options?product_gid='+PID)
        self.assertEqual(options.status_code,200);self.assertFalse(options.json()['can_replace'])
        response=await self.client.post('/api/files-psd-attach',json={'product_gid':PID,'file_id':'id:1','confirm_mismatch':True},headers={'origin':'https://test.local'})
        self.assertEqual(response.status_code,200);self.assertEqual(self.store.attach.call_args.args[2]['id'],'va_attach')
        for ua in ['Windows Edge','macOS Safari','macOS Chrome','iPhone Safari','iPad Safari','Android Chrome','Linux ChromeOS']:
            page=await self.client.get('/files-psd-picker?product_gid='+PID,headers={'user-agent':ua})
            self.assertEqual(page.status_code,200)
            result=await self.client.post('/api/files-psd-attach',json={'product_gid':PID,'file_id':'id:1','confirm_mismatch':True},headers={'origin':'https://test.local','user-agent':ua})
            self.assertEqual(result.status_code,200,ua)
        for flags in [{'confirm_replace':True},{'expected_file_id':'id:old'}]:
            self.cloud.reset_mock()
            response=await self.client.post('/api/files-psd-attach',json={'product_gid':PID,'file_id':'id:1',**flags},headers={'origin':'https://test.local'})
            self.assertEqual(response.status_code,403);self.cloud.assert_not_called()
        self.store.read.return_value={PID:{'dropbox_file_id':'id:old'}}
        self.cloud.reset_mock()
        options=await self.client.get('/api/files-psd-options?product_gid='+PID)
        self.assertEqual(options.status_code,403);self.assertEqual(options.json()['code'],'psd_replace_denied');self.cloud.assert_not_called()

    async def test_missing_expired_revoked_inactive_or_unapproved_sessions_deny_before_cloud(self):
        for role,version,expired in [(None,3,False),('admin',3,True),('admin',2,False),('inactive',3,False),('unauthorised',3,False)]:
            self.cookie(role,version,expired);self.cloud.reset_mock()
            for path in ['/files-psd-picker?product_gid='+PID,'/api/files-psd-open?product_gid='+PID,'/files-window']:
                response=await self.client.get(path)
                self.assertEqual(response.status_code,403,(role,version,path))
                self.assertIn('text/html',response.headers['content-type'])
                self.assertNotIn('"ok":',response.text)
            response=await self.client.post('/api/files-psd-open?product_gid='+PID,json={'action':'files'},headers={'origin':'https://test.local'})
            self.assertEqual(response.status_code,403)
            self.cloud.assert_not_called();self.store.attach.assert_not_called()

    async def test_cross_origin_writes_remain_denied_and_diagnostics_do_not_log_cookie(self):
        self.cookie('admin')
        response=await self.client.post('/api/files-psd-attach',json={'product_gid':PID,'file_id':'id:1'},headers={'origin':'https://evil.local'})
        self.assertEqual(response.status_code,403);self.store.attach.assert_not_called();self.cloud.assert_not_called()
        self.cookie('va')
        with self.assertLogs(api.__name__,level='WARNING') as logs:
            await self.client.get('/files-psd-picker?product_gid='+PID)
        output=' '.join(logs.output)
        self.assertIn('attach_permission_required',output);self.assertIn('picker_page',output)
        self.assertNotIn(self.client.cookies.get(sc_auth.AUTH_COOKIE_NAME),output)
        self.assertNotIn('local-test-secret',output)

if __name__=='__main__':unittest.main()
