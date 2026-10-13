import json
import unittest
from unittest.mock import patch,Mock
from starlette.requests import Request
import files_upload_api as api
import psd_directory as psd
import psd_mapping_store

ADMIN={'id':'picker-test','role':'admin','is_active':True}
PID='gid://shopify/Product/1'
META={'.tag':'file','id':'id:test','name':'Art.psd','path_display':psd.ROOT+'/Art.psd'}


def request(method='GET',payload=None,origin='http://test'):
    sent=False
    async def receive():
        nonlocal sent
        if sent:return {'type':'http.request','body':b'','more_body':False}
        sent=True;return {'type':'http.request','body':json.dumps(payload or {}).encode(),'more_body':False}
    headers=[(b'origin',origin.encode())] if origin else []
    return Request({'type':'http','method':method,'scheme':'http','server':('test',80),'path':'/','headers':headers,
                    'query_string':b'product_gid=gid%3A%2F%2Fshopify%2FProduct%2F1'},receive)


class PsdPickerApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_permissions_and_bad_origin_deny_before_cloud(self):
        with patch.object(api,'_request_user',return_value={**ADMIN,'role':'worker'}),patch.object(api,'_dropbox_context') as cloud:
            self.assertEqual((await api.psd_picker_page(request())).status_code,403)
            self.assertEqual((await api.psd_picker_options(request())).status_code,403)
            self.assertEqual((await api.attach_product_psd(request('POST',{'product_gid':PID,'file_id':'id:test'}))).status_code,403)
            cloud.assert_not_called()
        for origin in ('http://evil.test',''):
            with patch.object(api,'_psd_attach_user') as auth:
                self.assertEqual((await api.attach_product_psd(request('POST',origin=origin))).status_code,403)
                auth.assert_not_called()

    async def test_picker_filters_review_folder_and_returns_identity(self):
        store=Mock();store.get_product.return_value={'product_title':'Art','shopify_handle':'art'};store.read.return_value={}
        entries=[META,{**META,'id':'id:review','path_display':psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Art.psd'},
                 {**META,'id':'id:jpg','name':'Art.jpg','path_display':psd.ROOT+'/Art.jpg'}]
        with patch.object(api,'_psd_attach_user',return_value=ADMIN),patch.object(api,'_dropbox_context',return_value={'access_token':'fake','root_path':psd.ROOT}),patch.object(api,'_directory_entries',return_value=entries) as listing,patch.object(psd_mapping_store,'STORE',store):
            result=await api.psd_picker_options(request())
        body=json.loads(result.body);self.assertEqual(body['product_title'],'Art');self.assertEqual(len(body['files']),1);self.assertFalse(body['files'][0]['mismatch']);listing.assert_called_once()

    async def test_confirmed_save_uses_current_server_metadata_and_audited_store(self):
        store=Mock();store.attach.return_value={'verified':True,'state':'Linked','dropbox_file_id':'id:test'}
        payload={'product_gid':PID,'file_id':'id:test','expected_file_id':'','confirm_mismatch':True,'confirm_replace':False}
        with patch.object(api,'_psd_attach_user',return_value=ADMIN),patch.object(api,'_dropbox_context',return_value={'access_token':'fake'}),patch.object(api.dropbox_integration,'psd_open_metadata',return_value=META) as metadata,patch.object(psd_mapping_store,'STORE',store):
            response=await api.attach_product_psd(request('POST',payload))
        self.assertEqual(response.status_code,200);metadata.assert_called_once_with('fake','id:test',include_preview=False)
        self.assertTrue(store.attach.call_args.kwargs['confirm_mismatch']);self.assertTrue(json.loads(response.body)['open_url'])

    async def test_invalid_file_current_location_or_duplicate_are_rejected(self):
        payload={'product_gid':PID,'file_id':'id:test'}
        for meta in [{**META,'id':'id:wrong'},{**META,'path_display':psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Art.psd'}]:
            with patch.object(api,'_psd_attach_user',return_value=ADMIN),patch.object(api,'_dropbox_context',return_value={'access_token':'fake'}),patch.object(api.dropbox_integration,'psd_open_metadata',return_value=meta),patch.object(psd_mapping_store.STORE,'attach') as save:
                self.assertEqual((await api.attach_product_psd(request('POST',payload))).status_code,403);save.assert_not_called()
        with patch.object(api,'_psd_attach_user',return_value=ADMIN),patch.object(api,'_dropbox_context',return_value={'access_token':'fake'}),patch.object(api.dropbox_integration,'psd_open_metadata',return_value=META),patch.object(psd_mapping_store.STORE,'attach',side_effect=psd_mapping_store.MappingConflict('already assigned')):
            self.assertEqual((await api.attach_product_psd(request('POST',payload))).status_code,409)
