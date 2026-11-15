"""V4 synthetic storage/encoding/upload integration checks; no provider network."""
import asyncio
import base64
import io
import json
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from services import files_preview_cache as cache
import files_upload_api as api
from tests import test_files_preview_v3 as fixture
from tests.test_files_window import get_request


class ThumbnailV4Tests(unittest.TestCase):
    def setUp(self):
        fixture.PreviewV3Tests.setUp(self)

    def run_job(self, allow_original, payload):
        key=cache.asset_key('worker','/Synthetic',fixture.META)
        cache._slots.acquire()
        cache._job(self.store,key,'synthetic',fixture.META,allow_original,payload,True)
        return self.store.read(key)

    def raster(self, size=(256,192)):
        result=io.BytesIO();Image.new('RGB',size,(30,100,180)).save(result,'JPEG');return result.getvalue()

    def test_grid_persists_small_only_without_original_and_upgrades_on_open(self):
        with patch.object(cache,'_download_source') as download:
            small=self.run_job(False,self.raster())
            self.assertTrue(small['thumbnail_only']); self.assertEqual(set(small['assets']),{'small'})
            screen=self.run_job(True,self.raster((1600,1200)))
            self.assertFalse(screen['thumbnail_only']);self.assertEqual(set(screen['assets']),{'screen','small','screen1024','screen2048'})
            download.assert_not_called()
        with Image.open(io.BytesIO(base64.b64decode(screen['assets']['screen']))) as image:
            self.assertEqual(image.size,(1600,1200))

    def test_fresh_session_grid_reads_persistent_asset_with_permission_metadata_check(self):
        self.run_job(False,self.raster());cache._fast.clear();cache._store_for_configuration.cache_clear()
        with patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META) as metadata, patch.object(cache,'_provider_preview') as provider:
            for _ in range(3):
                data,_=cache.request_preview('synthetic',fixture.META['path_display'],root='/Synthetic',user_id='worker',revision='r1',representation='small')
                self.assertTrue(data)
            self.assertEqual(metadata.call_count,3);provider.assert_not_called()

    def test_failed_screen_upgrade_preserves_working_grid_thumbnail(self):
        first=self.run_job(False,self.raster())
        with patch.object(cache,'prepare',side_effect=cache.PreviewError('no screen')):
            second=self.run_job(True,self.raster())
        self.assertEqual(first['assets']['small'],second['assets']['small'])
        self.assertGreater(second['screen_unavailable_until'],time.time())

    def test_webp_fallback_to_jpeg(self):
        with patch('PIL.features.check',return_value=False):
            assets=cache.prepare('synthetic',fixture.META,False,self.raster(),True)
        with Image.open(io.BytesIO(base64.b64decode(assets['small']))) as image:self.assertEqual(image.format,'JPEG')

    def test_unsupported_grid_returns_fallback_without_polling_or_source_download(self):
        key=cache.asset_key('worker','/Synthetic',fixture.META)
        with patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META),patch.object(cache,'_provider_preview',side_effect=cache.PreviewError('unsupported')),patch.object(cache._pool,'submit') as submit,patch.object(cache,'_download_source') as source:
            try:
                with self.assertRaises(cache.PreviewError) as result:
                    cache.request_preview('synthetic',fixture.META['path_display'],root='/Synthetic',user_id='worker',revision='r1',representation='small')
                self.assertEqual(result.exception.status,404)
                self.assertFalse(submit.call_args.args[5]);source.assert_not_called()
            finally:
                with cache._lock:cache._pending.discard(key)
                cache._slots.release()

    def test_webp_api_content_type_matches_representation(self):
        data=base64.b64decode(cache.prepare('synthetic',fixture.META,False,self.raster(),True)['small'])
        with patch.object(api,'_request_user',return_value={'id':'worker'}),patch.object(api,'_dropbox_context',return_value={'access_token':'synthetic','root_path':'/Synthetic'}),patch.object(cache,'request_preview',return_value=(data,'metadata;dur=1')):
            result=asyncio.run(api.file_thumbnail(get_request('/api/files-thumbnail',{'path':'/Synthetic/Artwork.jpg'})))
        self.assertEqual(result.headers['content-type'],'image/webp')
        self.assertEqual(result.headers['cache-control'],'private, no-store')

    def test_upload_only_warms_after_confirmed_save_and_duplicate_final_is_safe(self):
        manager=api.DropboxChunkUploadManager()
        record=api.ChunkUploadRecord(upload_id='fixture',upload_secret='synthetic',access_token='synthetic',destination='/Synthetic/Artwork.jpg',mode='add',relative_path='Artwork.jpg',name='Artwork.jpg',size=3,user={'id':'worker'},root_path='/Synthetic',dropbox_session_id='session')
        manager._records[record.upload_id]=record
        with patch.object(api.dropbox_integration,'finish_upload_session',return_value=fixture.META),patch.object(cache,'queue_saved_file',side_effect=RuntimeError('optional cache failed')) as warm:
            self.assertTrue(manager.append('fixture','synthetic',0,b'abc',final=True)['just_completed'])
            self.assertEqual(record.state,'completed')
            self.assertFalse(manager.append('fixture','synthetic',0,b'abc',final=True)['just_completed'])
            self.assertEqual(warm.call_count,1)
            self.assertEqual(warm.call_args.kwargs,{'root':'/Synthetic','user_id':'worker','revision':'r1'})

    def test_no_upload_warmup_when_save_fails(self):
        manager=api.DropboxChunkUploadManager()
        record=api.ChunkUploadRecord(upload_id='fixture',upload_secret='synthetic',access_token='synthetic',destination='/Synthetic/Artwork.jpg',mode='add',relative_path='Artwork.jpg',name='Artwork.jpg',size=3,user={'id':'worker'},root_path='/Synthetic',dropbox_session_id='session')
        manager._records[record.upload_id]=record
        with patch.object(api.dropbox_integration,'finish_upload_session',side_effect=RuntimeError('failed')),patch.object(cache,'queue_saved_file') as warm:
            with self.assertRaises(api.FilesUploadError):manager.append('fixture','synthetic',0,b'abc',final=True)
            warm.assert_not_called()

    def test_background_upload_warmup_is_small_and_configuration_gated(self):
        with patch.object(cache._upload_pool,'submit',side_effect=lambda fn:fn()),patch.object(cache,'request_preview') as request:
            self.assertTrue(cache.queue_saved_file('synthetic','/Synthetic/Artwork.jpg',root='/Synthetic',user_id='worker',revision='r1'))
            self.assertEqual(request.call_args.kwargs['representation'],'small')
            request.reset_mock()
            with patch.object(cache,'configured',return_value=False):
                self.assertFalse(cache.queue_saved_file('synthetic','/Synthetic/Artwork.jpg',root='/Synthetic',user_id='worker',revision='r1'))
            request.assert_not_called()

    def test_download_uses_revision_path_and_retains_returned_identity(self):
        client=Mock();response=Mock();client.files_download.return_value=(fixture.META,response)
        with patch.object(cache.dbx,'team_space_client',return_value=client),patch.object(cache.dbx,'_metadata_to_dict',side_effect=lambda value:value):
            self.assertEqual(cache._download_source('synthetic',fixture.META),(fixture.META,response))
            client.files_download.assert_called_once_with('rev:r1')

    def test_asset_size_fixture_measurements(self):
        samples=[]
        for noise in [0,12,32,64]:
            image=Image.effect_noise((1600,1200),noise).convert('RGB') if noise else Image.new('RGB',(1600,1200),(30,100,180))
            source=io.BytesIO();image.save(source,'JPEG',quality=95)
            started=time.perf_counter();assets=cache.prepare('synthetic',fixture.META,False,source.getvalue(),True)
            samples.append({'fixture':'flat' if not noise else f'noise-{noise}', 'small_bytes':len(base64.b64decode(assets['small'])),'screen_bytes':len(base64.b64decode(assets['screen'])),'prepare_ms':(time.perf_counter()-started)*1000})
        result={'environment':'synthetic Pillow flat/noise images; no provider time','samples':samples,'mean_small_bytes':sum(x['small_bytes'] for x in samples)/len(samples),'mean_screen_bytes':sum(x['screen_bytes'] for x in samples)/len(samples)}
        Path('test-results/files-v4-asset-sizes.json').write_text(json.dumps(result,indent=2),encoding='utf8')
