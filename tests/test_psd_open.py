import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
from starlette.requests import Request
import files_upload_api as api
import dropbox_integration as dbx
import psd_directory as psd


def request():
    return Request({'type': 'http', 'method': 'GET', 'scheme': 'http', 'server': ('test', 80),
                    'path': '/api/files-psd-open', 'headers': [],
                    'query_string': b'product_gid=gid%3A%2F%2Fshopify%2FProduct%2F1'})


def metadata(path=psd.ROOT + '/Renamed.psd', url='https://www.dropbox.com/scl/fi/test'):
    return {'.tag': 'file', 'id': 'id:1', 'name': 'Renamed.psd', 'path_display': path, 'preview_url': url}


class PsdOpenTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, auth={'id': 'test-user'}, permitted=True, record=True, meta=None):
        self.context = Mock(return_value={'access_token': 'fake-test-token'})
        self.read = Mock(return_value=meta or metadata())
        mapping = {'gid://shopify/Product/1': {'verified': True, 'state': 'Linked', 'dropbox_file_id': 'id:1'}} if record else {}
        with patch.object(api, '_request_user', return_value=auth), patch.object(api.os_accounts, 'can_access_page', return_value=permitted), \
             patch.object(api, '_dropbox_context', self.context), patch.object(psd, 'directory', return_value=mapping), \
             patch.object(dbx, 'psd_open_metadata', self.read):
            return await api.open_product_psd(request())

    async def test_authentication_and_files_permission_fail_before_cloud_access(self):
        for auth, permitted in [(None, True), ({'id': 'blocked'}, False)]:
            response = await self.call(auth=auth, permitted=permitted)
            self.assertEqual(response.status_code, 403)
            self.context.assert_not_called()
            self.read.assert_not_called()

    async def test_existing_auth_denial(self):
        with patch.object(api, '_request_user', side_effect=api.FilesUploadError('denied', status_code=403)), patch.object(api, '_dropbox_context') as cloud:
            response = await api.open_product_psd(request())
            self.assertEqual(response.status_code, 403)
            cloud.assert_not_called()

    async def test_missing_mapping_never_reads_cloud(self):
        response = await self.call(record=False)
        self.assertEqual(response.status_code, 404)
        self.context.assert_not_called()

    async def test_rename_resolves_stable_id_and_permission_preview(self):
        response = await self.call()
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers['location'], 'https://www.dropbox.com/scl/fi/test')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.read.assert_called_once_with('fake-test-token', 'id:1')

    async def test_review_folder_wrong_id_and_unsafe_redirect(self):
        for meta in [metadata(psd.ROOT + '/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Renamed.psd'),
                     {**metadata(), 'id': 'id:another'}, metadata('/outside/Renamed.psd')]:
            self.assertEqual((await self.call(meta=meta)).status_code, 403)
        for url in ['javascript:alert(1)', 'https://www.dropbox.com.evil/preview/a',
                    'https://www.dropbox.com/s/a', 'https://www.dropbox.com/scl/fi/a?rlkey=public', '']:
            self.assertEqual((await self.call(meta=metadata(url=url))).status_code, 503)


class PsdIntegrationTests(unittest.TestCase):
    def test_immutable_id_is_not_path_normalised_and_only_metadata_is_read(self):
        client = Mock()
        client.files_get_metadata.return_value = metadata()
        with patch.object(dbx, 'team_space_client', return_value=client):
            self.assertEqual(dbx.psd_open_metadata('fake-test-token', 'id:1')['id'], 'id:1')
        client.files_get_metadata.assert_called_once_with('id:1')
        client.sharing_get_file_metadata.assert_not_called()

    def test_existing_sharing_preview_fallback_does_not_create_links(self):
        client = Mock()
        client.files_get_metadata.return_value = {k: v for k, v in metadata().items() if k != 'preview_url'}
        client.sharing_get_file_metadata.return_value = SimpleNamespace(preview_url='https://www.dropbox.com/scl/fi/test')
        with patch.object(dbx, 'team_space_client', return_value=client):
            result = dbx.psd_open_metadata('fake-test-token', 'id:1')
        self.assertTrue(result['preview_url'])
        client.sharing_get_file_metadata.assert_called_once_with('id:1')
        client.sharing_create_shared_link_with_settings.assert_not_called()


if __name__ == '__main__':
    unittest.main()
