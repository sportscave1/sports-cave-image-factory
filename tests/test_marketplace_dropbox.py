"""Dropbox source, private approval and revision-pinned delivery. Synthetic only."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import marketplace as core
import marketplace_api as api
import marketplace_dropbox as source
from marketplace_store import PREFIX, put
from tests.test_marketplace import memory_store, sample, photograph
from tests.marketplace_storage_fakes import MemorySource


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.store = memory_store()
        self.storage = self.store.media_storage

    def submit(self, video=True):
        return self.store.submit(core.submission(sample()), core.prepare_photos([photograph(), photograph()]),
            {'bytes': b'0123456789', 'seconds': 1} if video else None)['id']

    def test_one_item_folder_contains_all_files_and_customer_details(self):
        key = self.submit()
        backend = self.storage.backend
        self.assertEqual(len(backend.folders), 1)
        folder = backend.folders[0]
        self.assertTrue(folder.startswith(source.ROOT + '/broncos-collector-jersey--'))
        self.assertTrue(folder.endswith(key))
        self.assertNotIn('seller@example.invalid', folder)
        self.assertEqual({path[len(folder) + 1:] for path in backend.paths},
            {'photo-1.webp', 'photo-2.webp', 'video.mp4', 'listing.json'})
        row = self.store.listing(key)
        manifest = self.storage.manifest(row['media_source'])
        self.assertEqual(manifest['listing']['seller_email'], 'seller@example.invalid')
        self.assertEqual(manifest['listing']['price_cents'], 20000)
        self.assertEqual(manifest['listing']['shipping_cents'], 1500)
        self.assertEqual(manifest['listing']['provenance'], sample()['provenance'])
        self.assertEqual(manifest['listing']['team'], sample()['team'])
        self.assertIn('consented_at', manifest['listing'])
        self.assertEqual(self.store.review_listing(key), row)
        with self.store.db() as conn:
            keys = list(conn.database.values)
        self.assertEqual(keys, [PREFIX + 'listing:' + key])

    def test_photo_only_submission_creates_no_unused_video_or_subfolders(self):
        key = self.submit(video=False)
        self.assertEqual(len(self.storage.backend.folders), 1)
        self.assertEqual(len(self.storage.backend.paths), 3)
        self.assertFalse(self.store.listing(key)['has_video'])
        self.assertIsNone(self.store.video(key, public=False))

    def test_changed_index_cannot_be_approved_against_unchanged_source(self):
        key = self.submit()
        with self.store.db() as conn:
            row = deepcopy(conn.database.values[PREFIX + 'listing:' + key])
            row['price_cents'] = 1
            put(conn, 'listing:' + key, row)
        with self.assertRaisesRegex(ValueError, 'details do not match'):
            self.store.moderate(key, 'published', 1, 'test-admin')
        self.assertEqual(self.store.listing(key)['status'], 'pending')

    def test_missing_source_blocks_approval_and_does_not_substitute_database_images(self):
        key = self.submit()
        row = self.store.listing(key)
        self.storage.backend.objects.pop(row['media_source']['manifest']['id'])
        with self.assertRaises(KeyError):
            self.store.moderate(key, 'published', 1, 'test-admin')
        self.assertIsNone(self.store.listing(key, public=True))

    def test_legacy_database_photos_remain_available_after_rollout(self):
        key = self.submit(video=False)
        with self.store.db() as conn:
            row = deepcopy(conn.database.values[PREFIX + 'listing:' + key])
            row.pop('media_source')
            put(conn, 'listing:' + key, row)
            put(conn, 'image:' + key + ':0', {'webp': photograph()})
        self.store.moderate(key, 'published', 1, 'test-admin')
        self.assertEqual(self.store.photo(key, 0), photograph())

    def test_downloads_pin_revisions_and_keep_credentials_off_urls(self):
        key = self.submit()
        reference = self.store.video(key, public=False)
        stream = self.storage.open(reference, 2, 5)
        self.assertEqual(stream.read(12), b'2345')
        self.assertTrue(self.storage.backend.last_response.closed)
        request = self.storage.backend.calls[-1]
        self.assertEqual(json.loads(request['headers']['Dropbox-API-Arg']),
                         {'path': 'rev:' + reference['rev']})
        self.assertEqual(request['headers']['Range'], 'bytes=2-5')
        self.assertFalse(request['allow_redirects'])
        self.assertTrue(request['stream'])

    def test_wrong_revision_or_range_is_rejected_before_any_bytes_are_served(self):
        key = self.submit()
        reference = self.store.video(key, public=False)
        original = self.storage.backend.get
        for kind in ('revision', 'range', 'full'):
            def wrong(*args, **kwargs):
                response = original(*args, **kwargs)
                if kind == 'revision':
                    metadata = json.loads(response.headers['Dropbox-API-Result'])
                    metadata['rev'] = 'deadbeef'
                    response.headers['Dropbox-API-Result'] = json.dumps(metadata)
                elif kind == 'range':
                    response.headers['Content-Range'] = 'bytes 0-9/10'
                else:
                    response.status_code = 200
                return response
            with self.subTest(kind=kind), patch.object(self.storage.backend, 'get', side_effect=wrong):
                with self.assertRaises(RuntimeError):
                    self.storage.open(reference, 2, 5)
                self.assertTrue(self.storage.backend.last_response.closed)


class ConnectionTests(unittest.TestCase):
    def test_existing_server_connection_is_reused_and_bound_to_the_created_folder(self):
        config = {'app_key': 'synthetic-key', 'refresh_token': 'synthetic-refresh'}
        metadata = {'.tag': 'folder', 'id': source.ROOT_ID, 'path_display': source.ROOT}
        context = {'root_namespace_id': '123', 'client': Mock()}
        with patch.dict(source._AUTH, {}, clear=True), patch.object(source.dbx, 'dropbox_config', return_value=config), \
             patch.object(source.dbx, 'resolve_server_auth', return_value={'access_token': 'synthetic-access'}) as auth, \
             patch.object(source.dbx, '_team_space_context', return_value=context), \
             patch.object(source.dbx, 'get_file_metadata', return_value=metadata) as folder:
            first = source.connection()
            self.assertIs(source.connection(), first)
            auth.assert_called_once_with(config, validate=False)
            folder.assert_called_once_with('synthetic-access', source.ROOT_ID)

    def test_a_different_or_outside_folder_is_not_accepted(self):
        for metadata in ({'.tag': 'folder', 'id': 'id:other', 'path_display': source.ROOT},
                         {'.tag': 'folder', 'id': source.ROOT_ID, 'path_display': '/Unrelated/Marketplace'}):
            with self.subTest(metadata=metadata), patch.dict(source._AUTH, {}, clear=True), \
                 patch.object(source.dbx, 'dropbox_config', return_value={}), \
                 patch.object(source.dbx, 'resolve_server_auth', return_value={'access_token': 'synthetic'}), \
                 patch.object(source.dbx, '_team_space_context', return_value={'root_namespace_id': '123', 'client': Mock()}), \
                 patch.object(source.dbx, 'get_file_metadata', return_value=metadata):
                with self.assertRaises(RuntimeError):
                    source.connection()


class WebsiteSourceTests(unittest.TestCase):
    def test_real_website_flow_keeps_source_details_private_and_reads_media_from_dropbox(self):
        store = memory_store()
        storage = store.media_storage
        api._RATE.clear()
        client = TestClient(Starlette(routes=[Route(path, endpoint, methods=list(methods)) for path, endpoint, methods in api.ROUTES]), base_url=core.PUBLIC_ORIGIN)
        with patch.object(api, 'MarketplaceStore', return_value=store), patch.object(api.media, 'configured', return_value=True), \
             patch.object(api.media, 'prepare_video', return_value={'bytes': b'0123456789', 'seconds': 1}), \
             patch.object(source, 'MarketplaceDropboxStorage', return_value=storage):
            response = client.post('/marketplace/api/submissions', headers={'Origin': core.PUBLIC_ORIGIN},
                json={**sample(), 'photos': [photograph(), photograph()], 'video': 'synthetic'})
            self.assertEqual(response.status_code, 201)
            self.assertNotIn('dropbox', response.text.lower())
            key = response.json()['reference']
            photo = f'/marketplace/images/{key}/0.webp'
            video = f'/marketplace/videos/{key}/item.mp4'
            self.assertEqual(client.get(photo).status_code, 404)
            self.assertEqual(client.get(video).status_code, 404)
            store.moderate(key, 'published', 1, 'test-admin')
            self.assertEqual(client.get(photo).headers['content-type'], 'image/webp')
            response = client.get(video, headers={'Range': 'bytes=2-5'})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, b'2345')
            for path in ('/marketplace', '/marketplace/sell', '/marketplace/item/' + key):
                text = client.get(path).text
                self.assertNotIn('dropbox', text.lower())
                self.assertNotIn('seller@example.invalid', text)
                self.assertNotIn('synthetic-access', text)
                self.assertNotIn('id:synthetic-', text)
            source_count = len(storage.backend.paths)
            store.moderate(key, 'withdrawn', 2, 'test-admin')
            self.assertEqual(client.get(photo).status_code, 404)
            self.assertEqual(client.get(video).status_code, 404)
            self.assertEqual(len(storage.backend.paths), source_count)


if __name__ == '__main__':
    unittest.main()
