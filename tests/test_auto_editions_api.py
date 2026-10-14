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
