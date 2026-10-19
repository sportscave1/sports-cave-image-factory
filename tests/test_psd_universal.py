import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from tests import test_psd_open as original
request, metadata = original.request, original.metadata
import files_upload_api as api
import dropbox_integration as dbx
import psd_directory as psd


class UniversalTests(unittest.IsolatedAsyncioTestCase):
    call = original.PsdOpenTests.call
    async def test_files_resolves_verified_stable_id_and_never_creates_transfer(self):
        response = await self.call(req=request(payload={'action':'files'}))
        self.assertEqual(response.status_code,200)
        value = json.loads(response.body)
        self.assertEqual(value['file_id'],'id:1')
        self.assertEqual(value['folder_path'],psd.ROOT)
        self.assertEqual(len(self.manager._records),0)
        self.read.assert_called_once_with('fake-test-token','id:1',include_preview=False)
        self.assertEqual((await self.call(record=False,req=request(payload={'action':'files'}))).status_code,404)
        self.assertEqual((await self.call(permitted=False,req=request(payload={'action':'files'}))).status_code,403)
        self.assertEqual((await self.call(meta=metadata(fid='id:other'),req=request(payload={'action':'files'}))).status_code,403)

    async def test_describe_current_renamed_id_without_public_grants(self):
        response = await self.call(req=request(payload={'action':'describe'}))
        value = json.loads(response.body)
        self.assertEqual(value['name'],'Renamed.psd')
        self.assertEqual(value['dropbox_url'],'https://www.dropbox.com/home/Sportscave%20Team%20Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED?preview=Renamed.psd')
        self.assertTrue(value['mac_url'].startswith('sports-cave-files://open?kind=master&path='))
        self.assertNotIn('ticket',value);self.assertNotIn('secret',value)
        self.assertEqual(len(self.manager._records),0)
        self.read.assert_called_once_with('fake-test-token','id:1',include_preview=False)

    async def test_preview_is_small_optional_and_permission_protected(self):
        with patch.object(dbx,'get_psd_thumbnail_bytes',return_value=b'fake-tiny-jpeg') as thumb:
            response=await self.call(req=request(payload={'action':'preview'}))
            self.assertEqual(response.body,b'fake-tiny-jpeg')
            self.assertEqual(response.headers['content-type'],'image/jpeg')
            thumb.assert_called_once_with('fake-test-token','id:1')
            await self.call(permitted=False,req=request(payload={'action':'preview'}))
            self.assertEqual(thumb.call_count,1)
        with patch.object(dbx,'get_psd_thumbnail_bytes',side_effect=RuntimeError('SECRET')):
            response=await self.call(req=request(payload={'action':'preview'}))
            self.assertEqual(response.status_code,422)
            self.assertIn('Open in Dropbox',json.loads(response.body)['message'])
            self.assertNotIn('SECRET',response.body.decode())

    async def download(self, expected=None, actual=None, permitted=True, linked=True):
        expected=expected or metadata()
        self.upstream=Mock()
        self.upstream.iter_content.return_value=iter([b'a'*api.FILES_STREAM_CHUNK_BYTES,b'end'])
        # This stream exposes chunks only; no .content access is needed.
        mapping={'gid://shopify/Product/1':{'verified':True,'state':'Linked','dropbox_file_id':'id:1'}} if linked else {}
        with patch.object(api,'_request_user',return_value={'id':'fake'}),patch.object(api.os_accounts,'can_access_page',return_value=permitted),patch.object(psd,'directory',return_value=mapping),patch.object(api,'_dropbox_context',return_value={'access_token':'fake','root_path':'/Sportscave Team Folder'}),patch.object(dbx,'psd_open_metadata',return_value=expected),patch.object(dbx,'get_psd_file_response',return_value=(actual or expected,self.upstream)) as stream:
            response=await api.download_product_psd(request('GET',origin=''))
            self.stream=stream
        return response

    async def test_over_one_gb_download_has_bounded_chunks_no_grant_and_closes(self):
        response=await self.download(expected={**metadata(),'size':2**31})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['content-length'],str(2**31))
        self.assertIn('attachment;',response.headers['content-disposition'])
        self.stream.assert_called_once_with('fake','id:1','test-revision')
        chunks=[chunk async for chunk in response.body_iterator]
        self.assertEqual(max(map(len,chunks)),api.FILES_STREAM_CHUNK_BYTES)
        self.upstream.close.assert_called_once()
        self.assertNotIn('location',response.headers)

    async def test_download_denials_and_changed_revision_are_human_errors(self):
        for permitted,linked,expected,actual,status in [(False,True,None,None,403),(True,False,None,None,404),(True,True,metadata(psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/x.psd'),None,403),(True,True,None,{**metadata(),'rev':'changed'},409)]:
            response=await self.download(expected=expected,actual=actual,permitted=permitted,linked=linked)
            self.assertEqual(response.status_code,status)
            self.assertIn('text/html',response.headers['content-type'])
            if status !=409:self.stream.assert_not_called()
            else:self.upstream.close.assert_called_once()

    async def test_sdk_missing_and_permission_errors_are_actionable(self):
        from dropbox.exceptions import ApiError, AuthError
        from dropbox.auth import AuthError as AuthProblem
        from dropbox.files import GetMetadataError, LookupError
        for tag,expected in [('not_found',404),('invalid_access_token',403)]:
            error=ApiError('test-only',GetMetadataError.path(LookupError.not_found),None,None) if tag=='not_found' else AuthError('test-only',AuthProblem.invalid_access_token)
            mapping={'gid://shopify/Product/1':{'verified':True,'state':'Linked','dropbox_file_id':'id:1'}}
            with patch.object(api,'_request_user',return_value={'id':'fake'}),patch.object(api.os_accounts,'can_access_page',return_value=True),patch.object(psd,'directory',return_value=mapping),patch.object(api,'_dropbox_context',return_value={'access_token':'fake','root_path':'/Sportscave Team Folder'}),patch.object(dbx,'psd_open_metadata',side_effect=error):
                response=await api.open_product_psd(request(payload={'action':'describe'}))
                self.assertEqual(response.status_code,expected)
                self.assertIn('Dropbox',json.loads(response.body)['message'])


class DropboxStreamTests(unittest.TestCase):
    def test_sdk_immutable_id_revision_stream_and_thumbnail_never_create_links(self):
        client=Mock();client.clone.return_value=client;stream=Mock();client.files_download.return_value=({**metadata(),'rev':'123456789'},stream)
        thumbnail=Mock();thumbnail.iter_content.return_value=iter([b'tiny']);client.files_get_thumbnail.return_value=(metadata(),thumbnail)
        with patch.object(dbx,'team_space_client',return_value=client):
            self.assertIs(dbx.get_psd_file_response('fake','id:1','123456789')[1],stream)
            client.files_download.assert_called_once_with('rev:123456789')
            self.assertEqual(dbx.get_psd_thumbnail_bytes('fake','id:1'),b'tiny')
        thumbnail.close.assert_called_once()
        client.sharing_get_file_metadata.assert_not_called()
        client.sharing_create_shared_link_with_settings.assert_not_called()
        with self.assertRaises(ValueError):dbx.get_psd_file_response('fake','/arbitrary.psd','rev')

    def test_thumbnail_is_bounded_and_closed_even_if_provider_exceeds_limit(self):
        client=Mock();response=Mock()
        response.iter_content.return_value=iter([b'x'*(64*1024)]*33)
        client.files_get_thumbnail.return_value=(metadata(),response)
        with patch.object(dbx,'team_space_client',return_value=client):
            with self.assertRaises(dbx.DropboxApiError):dbx.get_psd_thumbnail_bytes('fake','id:1')
        response.close.assert_called_once()


class MacMasterTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('mac_helper',Path(__file__).resolve().parents[1]/'desktop_helper_macos'/'SportsCaveFilesHelper.py')
        self.mac=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mac)

    def test_verified_master_request_and_review_traversal_rejections(self):
        from urllib.parse import quote
        prefix='02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/'
        for path,valid in [(prefix+'Renamed.psd',True),(prefix+'../evil.psd',False),(prefix+'99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/x.psd',False)]:
            uri='sports-cave-files://open?kind=master&path='+quote(path,safe='')+'&hash='+'a'*64+'&size=5'
            with patch.object(self.mac,'fail',side_effect=ValueError('blocked')):
                if valid:self.assertEqual(self.mac.read_request(uri),(path,'master'))
                else:
                    with self.assertRaises(ValueError):self.mac.read_request(uri)

    def test_hash_hydration_read_and_default_app_or_missing_app(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'art.psd';data=b'8BPS'+b'x'*(4*1024*1024);target.write_bytes(data)
            digest=hashlib.sha256(b''.join(hashlib.sha256(data[i:i+4*1024*1024]).digest() for i in range(0,len(data),4*1024*1024))).hexdigest()
            self.mac.verify_master(target,digest,len(data))
            with patch.object(self.mac,'fail',side_effect=ValueError('stale')):
                with self.assertRaises(ValueError):self.mac.verify_master(target,'a'*64,len(data))
            with patch.object(self.mac.subprocess,'run') as run:
                self.mac.open_target(target,prefer_adobe=False)
                run.assert_called_once_with(['/usr/bin/open',str(target)],check=True)
            with patch.object(self.mac.subprocess,'run',side_effect=self.mac.subprocess.CalledProcessError(1,['open'])):
                with self.assertRaises(self.mac.subprocess.CalledProcessError):self.mac.open_target(target,prefer_adobe=False)
            self.assertEqual(target.read_bytes(),data)
        with self.assertRaises(FileNotFoundError):self.mac.verify_master(target,digest,len(data))

if __name__=='__main__':unittest.main()
