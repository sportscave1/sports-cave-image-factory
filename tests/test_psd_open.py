import csv
import io
import json
import unittest
import zipfile
from unittest.mock import patch, Mock
from types import SimpleNamespace
from pathlib import Path
from starlette.requests import Request
from dropbox.exceptions import ApiError
import files_upload_api as api
import dropbox_integration as dbx
import psd_directory as psd


def request(method='POST',pid='gid://shopify/Product/1',payload=None,origin='http://test',extra=''):
    from urllib.parse import quote
    async def receive():
        return {'type':'http.request','body':json.dumps(payload if payload is not None else {'action':'openPhotoshop'}).encode(),'more_body':False}
    headers=[(b'origin',origin.encode())] if origin else []
    return Request({'type':'http','method':method,'scheme':'http','server':('test',80),'path':'/api/files-psd-open',
                    'headers':headers,'query_string':('product_gid='+quote(pid,safe='')+extra).encode()},receive)


def metadata(path=psd.ROOT+'/Renamed.psd',fid='id:1'):
    return {'.tag':'file','id':fid,'name':path.rsplit('/',1)[-1],'path_display':path,'size':5,'rev':'test-revision','content_hash':'a'*64}


class PsdOpenTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, auth={'id':'test-user'}, permitted=True, record=True, meta=None,req=None):
        self.context=Mock(return_value={'access_token':'fake-test-token','root_path':'/Sportscave Team Folder'})
        self.read=Mock(return_value=meta or metadata())
        mapping={'gid://shopify/Product/1':{'verified':True,'state':'Linked','dropbox_file_id':'id:1'}} if record else {}
        manager=api.NativeTransferManager()
        with patch.object(api,'_request_user',return_value=auth),patch.object(api.os_accounts,'can_access_page',return_value=permitted),patch.object(api,'_dropbox_context',self.context),patch.object(psd,'directory',return_value=mapping),patch.object(dbx,'psd_open_metadata',self.read),patch.object(api,'NATIVE_TRANSFER_MANAGER',manager):
            response=await api.open_product_psd(req or request())
        self.manager=manager
        return response

    async def test_permission_denied_before_mapping_or_dropbox(self):
        for auth,permitted in [(None,True),({'id':'blocked'},False)]:
            self.assertEqual((await self.call(auth=auth,permitted=permitted)).status_code,403)
            self.context.assert_not_called();self.read.assert_not_called()

    async def test_get_is_human_page_and_does_not_prepare_or_download(self):
        response=await self.call(req=request('GET',origin=''))
        self.assertEqual(response.status_code,200)
        self.assertIn('Sports Cave OS Desktop',response.body.decode())
        self.assertEqual(response.headers['content-type'].split(';')[0],'text/html')
        self.context.assert_not_called();self.read.assert_not_called()
        denied=await self.call(auth=None,req=request('GET',origin=''))
        self.assertEqual(denied.status_code,403);self.assertIn('text/html',denied.headers['content-type'])

    async def test_missing_mapping_and_paths_never_reach_dropbox(self):
        self.assertEqual((await self.call(record=False)).status_code,404);self.context.assert_not_called()
        for req in [request(origin='http://evil.test'),request(origin=''),request(payload={'action':'openPhotoshop','path':'../evil.psd'}),request(extra='&path=evil.psd')]:
            self.assertIn((await self.call(req=req)).status_code,[400,403]);self.context.assert_not_called()

    async def test_renamed_plain_psd_without_preview_becomes_native_grant(self):
        response=await self.call()
        self.assertEqual(response.status_code,200)
        result=json.loads(response.body)
        self.assertEqual(result['action'],'openPhotoshop');self.assertEqual(result['name'],'Renamed.psd')
        self.read.assert_called_once_with('fake-test-token','id:1',include_preview=False)
        record=self.manager.get(result['ticket'],result['secret'])
        self.assertEqual(record.purpose,'photoshop_master');self.assertEqual(record.items[0]['dropbox_id'],'id:1')
        self.assertEqual(record.roots[0]['source_relative_path'],'02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Renamed.psd')
        self.assertNotIn('fake-test-token',response.body.decode());self.assertNotIn('location',response.headers)
        self.assertEqual(response.headers['cache-control'],'no-store')

    async def test_wrong_id_review_file_and_missing_hash_fail_closed(self):
        for meta in [metadata(psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Renamed.psd'),metadata(fid='id:wrong'),metadata('/outside/Renamed.psd')]:
            self.assertEqual((await self.call(meta=meta)).status_code,403)
        self.assertEqual((await self.call(meta={**metadata(),'content_hash':''})).status_code,409)

    async def test_safe_diagnostics_identify_stage_and_class_without_secret_messages(self):
        with patch.object(api,'_request_user',return_value={'id':'test'}),patch.object(api.os_accounts,'can_access_page',return_value=True),patch.object(psd,'directory',side_effect=RuntimeError('SECRET_CREDENTIAL_IN_EXCEPTION')),self.assertLogs(api.__name__,level='WARNING') as logs:
            response=await api.open_product_psd(request())
        self.assertEqual(response.status_code,503);self.assertIn('stage=mapping',' '.join(logs.output));self.assertIn('RuntimeError',' '.join(logs.output));self.assertNotIn('SECRET_CREDENTIAL',' '.join(logs.output)+response.body.decode())
        self.assertNotEqual(json.loads(response.body)['code'],'files_unavailable')

    async def test_representative_real_ids_renames_and_multiline_orders_read_only(self):
        folder=Path(__file__).resolve().parents[1]/'output'/'psd_snapshot'
        rows=list(csv.DictReader(io.StringIO((folder/'approved_dropbox_psds_282.csv').read_text(encoding='utf-8-sig'))))
        selected=[rows[0],rows[100],rows[-1]]
        mapping={r['shopify_product_gid']:{'verified':True,'state':'Linked','dropbox_file_id':r['dropbox_file_id']} for r in selected}
        before=json.dumps(mapping,sort_keys=True)
        for row in selected:
            with patch.object(api,'_request_user',return_value={'id':'test'}),patch.object(api.os_accounts,'can_access_page',return_value=True),patch.object(psd,'directory',return_value=mapping),patch.object(api,'_dropbox_context',return_value={'access_token':'fake','root_path':'/Sportscave Team Folder'}),patch.object(dbx,'psd_open_metadata',return_value=metadata(fid=row['dropbox_file_id'])) as read,patch.object(api,'NATIVE_TRANSFER_MANAGER',api.NativeTransferManager()),patch.object(psd,'save',side_effect=AssertionError('No mapping writes')):
                self.assertEqual((await api.open_product_psd(request(pid=row['shopify_product_gid']))).status_code,200)
                self.assertEqual(read.call_args.args[1],row['dropbox_file_id'])
        import orders_page
        with patch.object(psd,'directory',return_value=mapping):
            output=orders_page._display_rows([{'order':'#MOCK','shopify_product_id':r['shopify_product_gid']} for r in selected],normalised=True)
        self.assertEqual(len(set(r['file'] for r in output)),3)
        self.assertTrue(all(r['file'].endswith('#Open PSD') for r in output))
        self.assertEqual(json.dumps(mapping,sort_keys=True),before)


class PsdIntegrationTests(unittest.TestCase):
    def test_metadata_only_removes_actual_sharing_exception_path(self):
        client=Mock();client.files_get_metadata.return_value=metadata()
        client.sharing_get_file_metadata.side_effect=ApiError('test-request','ordinary PSD has no sharing preview SECRET',None,None)
        with patch.object(dbx,'team_space_client',return_value=client):
            with self.assertRaises(dbx.DropboxApiError) as old:
                dbx.psd_open_metadata('fake','id:1')
            self.assertIsInstance(old.exception.__cause__,ApiError)
            self.assertEqual(dbx.psd_open_metadata('fake','id:1',include_preview=False)['id'],'id:1')
        self.assertEqual(client.sharing_get_file_metadata.call_count,1)
        client.sharing_create_shared_link_with_settings.assert_not_called()

    def test_safe_sdk_exception_tag_diagnostics(self):
        from dropbox.files import GetMetadataError, LookupError
        error=ApiError('test-request',GetMetadataError.path(LookupError.not_found),None,None)
        with self.assertLogs(api.__name__,level='WARNING') as logs:
            api._psd_failure(error,'dropbox_metadata_by_id','test-reference')
        self.assertIn('ApiError',' '.join(logs.output))
        self.assertIn('provider_tags=path,not_found',' '.join(logs.output))
        self.assertNotIn('test-request',' '.join(logs.output))

    def test_native_manifest_scope_and_secret_protections(self):
        manager=api.NativeTransferManager()
        record=manager.create_psd(access_token='fake',root_path='/Sportscave Team Folder',user={'id':'test'},metadata=metadata())
        with self.assertRaises(api.FilesUploadError):manager.get(record.ticket,'wrong-secret')
        self.assertEqual(manager.get(record.ticket,record.secret).items[0]['content_hash'],'a'*64)


if __name__=='__main__':unittest.main()
