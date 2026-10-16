import json
import unittest
from unittest.mock import Mock,patch
from starlette.requests import Request
import auto_editions_api as api
import auto_editions_setup_api as setup
import files_upload_api as files

ADMIN=dict(id='admin',role='admin',is_active=True,page_permissions=[])
VA=dict(id='va',role='worker',is_active=True,page_permissions=['Files','Orders'])


def request(method='GET',body=None,origin='https://os.test',query='allocation_id=42'):
    async def receive():return dict(type='http.request',body=json.dumps(body or {}).encode(),more_body=False)
    return Request(dict(type='http',method=method,scheme='https',server=('os.test',443),path='/',
                        headers=[(b'origin',origin.encode())] if origin else [],query_string=query.encode()),receive)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_feature_does_not_touch_cloud(self):
        with patch.object(api.runtime,'enabled',return_value=False),patch.object(api.runtime,'job_for') as cloud:
            self.assertEqual((await api.start(request('POST'))).status_code,409)
            cloud.assert_not_called()

    async def test_va_can_open_cloud_download_but_not_admin_setup(self):
        with patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=VA),patch.object(files.os_accounts,'can_access_page',return_value=True):
            response=await api.page(request())
            self.assertEqual(response.status_code,200)
            self.assertNotIn(b'127.0.0.1',response.body)
            self.assertEqual((await setup.page(request())).status_code,403)

    async def test_forged_origin_or_client_number_rejected_before_cloud(self):
        with patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=ADMIN),patch.object(api.runtime,'job_for') as cloud:
            for origin in ('','https://evil.test'):
                self.assertEqual((await api.start(request('POST',origin=origin))).status_code,403)
            self.assertEqual((await api.start(request('POST',body={'edition_number':9}))).status_code,409)
            cloud.assert_not_called()

    async def test_revoked_account_cannot_download_cached_file(self):
        with patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value={**VA,'is_active':False}),patch.object(api.runtime,'job_for') as cloud:
            self.assertEqual((await api.download(request(query='allocation_id=42&job_id=abc'))).status_code,403)
            cloud.assert_not_called()

    async def test_job_id_cannot_select_another_allocations_output(self):
        with patch.object(api.runtime,'enabled',return_value=True),patch.object(files,'_request_user',return_value=ADMIN),patch.object(api.runtime,'job_for',return_value=({'id':'current'},None)),patch.object(api.runtime,'stores') as stores:
            self.assertEqual((await api.download(request(query='allocation_id=42&job_id=other'))).status_code,409)
            stores.assert_not_called()


    async def test_retained_history_cannot_cross_allocation_identity(self):
        row=dict(payload=dict(identity=dict(allocation_id=99)),result=dict(retained=True))
        registry=Mock();registry.unit.return_value=(dict(id=42,allocation_valid=True,identity_enforced=True),None)
        jobs=Mock();jobs.read_bound.return_value=(row,dict(id=42,allocation_valid=True,identity_enforced=True))
        with patch.object(api,'actor',return_value=VA),patch.object(api.runtime,'stores',return_value=(registry,jobs)):
            response=await api.download(request(query='allocation_id=42&job_id='+'a'*64))
            self.assertEqual(response.status_code,403)
            jobs.retain.assert_not_called()

    async def test_saved_view_resolves_location_without_generation(self):
        job=dict(id='a'*64)
        assets=Mock();assets.verify_output.return_value=dict(id='id:jpg',rev='123',path_display='/Sportscave Team Folder/03_ASSETS/Auto Editions/Generated JPGs/SC3287/TEST/file.jpg')
        with patch.object(api,'actor',return_value=VA),patch.object(api.runtime,'start_worker') as worker:
            response=await api.view(request(query='allocation_id=42&job_id='+'a'*64))
            self.assertEqual(response.status_code,307)
            self.assertIn('/?page=orders&workspace=files&edition_allocation=42',response.headers['location'])
            worker.assert_not_called()

    async def test_missing_archive_never_returns_an_open_location(self):
        assets=Mock();assets.verify_output.side_effect=ValueError('Saved JPG is unavailable')
        with patch.object(api,'stored_current',return_value=({},assets,dict(status='Ready',result={'output':{}}))):
            response=await api.location(request(query='allocation_id=42&job_id='+'a'*64))
            self.assertEqual(response.status_code,409)
            self.assertNotIn('location',response.headers)

    async def test_download_streams_only_pinned_checked_bytes(self):
        import hashlib
        data=b'full resolution bytes';output=dict(file_id='id:exact',revision='abc',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        stream=Mock();stream.iter_content.return_value=[data]
        assets=Mock();assets.output_response.return_value=(dict(id='id:exact',rev='abc',size=len(data)),stream)
        row=dict(status='Ready',result=dict(output=output,filename='SC3287-005-TEST.jpg'))
        jobs=Mock()
        with patch.object(api,'stored_current',return_value=(VA,{'id':'a'*64},assets,row)),patch.object(api,'actor',return_value=VA),patch.object(api.runtime,'stores',return_value=(None,jobs)):
            response=await api.download(request(query='allocation_id=42&job_id='+'a'*64))
            self.assertEqual(response.status_code,200)
            self.assertEqual(__import__('pathlib').Path(response.path).read_bytes(),data)
            assets.output_response.assert_called_once_with(output)
            stream.close.assert_called_once()
            await response.background()

    async def test_native_handoff_receipt_preserves_bytes_filename_and_access_checks(self):
        import hashlib
        from pathlib import Path
        from auto_editions_asset_cache import output_assets
        data=b'exact verified JPG fixture'
        output=dict(file_id='id:receipt',revision='rev',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        stream=Mock();stream.iter_content.return_value=[data]
        assets=Mock();assets.output_response.return_value=(dict(id='id:receipt',rev='rev',size=len(data)),stream)
        row=dict(status='Ready',result=dict(output=output,filename='SC3287-005-TEST.jpg',retained=True))
        token='b'*32
        with patch.object(api,'stored_current',return_value=(VA,{'id':'a'*64},assets,row)) as checked,patch.object(api.runtime,'stores',return_value=(None,Mock())),patch.object(output_assets,'copy',return_value=False),patch.object(output_assets,'remember'):
            response=await api.download(request(query='allocation_id=42&job_id='+'a'*64+'&download_token='+token))
            self.assertEqual(Path(response.path).read_bytes(),data)
            self.assertEqual(response.headers['content-disposition'],'attachment; filename="SC3287-005-TEST.jpg"')
            self.assertEqual(response.chunk_size,1024*1024)
            self.assertEqual(checked.call_count,2)
            assets.verify_output.assert_called_once_with(output)
            self.assertIn('sc-jpg-'+token+'=started',response.headers['set-cookie'])
            self.assertIn('SameSite=strict',response.headers['set-cookie'])
            self.assertIn('Secure',response.headers['set-cookie'])
            self.assertNotIn('HttpOnly',response.headers['set-cookie'])
            await response.background()

    async def test_failed_access_acknowledges_error_without_cloud_or_success(self):
        with patch.object(api,'stored_current',side_effect=PermissionError('Access revoked')),patch.object(api.runtime,'stores') as stores:
            response=await api.download(request(query='allocation_id=42&job_id='+'a'*64+'&download_token='+'c'*32))
            self.assertEqual(response.status_code,403)
            self.assertIn('=error;',response.headers['set-cookie'])
            self.assertNotIn('started',response.headers['set-cookie'])
            stores.assert_not_called()

    def test_receipts_are_opt_in_and_reject_untrusted_cookie_names(self):
        from starlette.responses import Response
        for token in ('','short','A'*32,'a'*32+'; injected=1','a'*33):
            response=api.download_feedback(request(query='allocation_id=42&download_token='+token),Response(),'started')
            self.assertNotIn('set-cookie',response.headers)
