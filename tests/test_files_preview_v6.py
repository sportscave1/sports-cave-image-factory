"""Adaptive representation, colour and bounded persistent cache contracts."""
import asyncio
import base64
import io
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageCms
from services import files_preview_cache as cache
import files_upload_api as api
from tests import test_files_preview_v3 as fixture
from tests.test_files_window import get_request


class PreviewV6Tests(unittest.TestCase):
    def setUp(self):
        fixture.PreviewV3Tests.setUp(self)

    def raster(self, noise=False):
        image=Image.effect_noise((2400,1800),24).convert('RGB') if noise else Image.new('RGB',(2400,1800),(150,40,25))
        output=io.BytesIO()
        image.save(output,'JPEG',quality=95,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        return output.getvalue()

    def test_tiers_have_real_detail_and_fit_encrypted_storage_budget(self):
        rows=[]
        for noisy in [False,True]:
            start=time.perf_counter()
            assets=cache.prepare('synthetic',fixture.META,True,self.raster(noisy),True)
            sizes={}
            for name,bounds in [('small',(256,192)),('screen1024',(1024,768)),('screen',(1600,1200)),('screen2048',(2048,1536))]:
                data=base64.b64decode(assets[name]);sizes[name]=len(data)
                with Image.open(io.BytesIO(data)) as image:
                    self.assertEqual(image.size,bounds)
                    if not noisy:
                        self.assertTrue(all(abs(a-b)<5 for a,b in zip(image.convert('RGB').getpixel((10,10)),(150,40,25))))
            self.store.write('assets/fixture',{'assets':assets,'expires':time.time()+60})
            encrypted=len(self.s3.data[self.store.prefix+'assets/fixture'][0])
            self.assertLess(encrypted,cache.MAX_OBJECT)
            rows.append({'noise':noisy,'bytes':sizes,'encrypted_bytes':encrypted,'prepare_ms':(time.perf_counter()-start)*1000})
        Path('test-results/files-v6-assets.json').write_text(json.dumps(rows,indent=2))

    def test_provider_upgrade_preserves_lower_asset_on_failure_without_original(self):
        key=cache.asset_key('worker','/Synthetic',fixture.META)
        assets=cache.prepare('synthetic',fixture.META,False,self.raster(),True)
        self.store.write(key,{'assets':assets,'max_tier':1024,'expires':time.time()+60})
        with patch.object(cache,'_download_source') as source:
            cache._slots.acquire()
            cache._job(self.store,key,'synthetic',fixture.META,True,None,True,2048)
            source.assert_not_called()
        with patch.object(cache,'current_store',return_value=self.store),patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META):
            args=dict(root='/Synthetic',user_id='worker',revision='r1',representation='screen')
            data,_=cache.request_preview('synthetic',fixture.META['path_display'],tier='1024',**args)
            self.assertEqual(data,base64.b64decode(assets['screen1024']))
            with self.assertRaises(cache.PreviewError):cache.request_preview('synthetic',fixture.META['path_display'],tier='2048',**args)

    def test_bundle_compaction_retains_sharp_pixels_and_derives_lower_tiers(self):
        assets=cache.prepare('synthetic',fixture.META,True,self.raster(),True)
        with patch.object(cache,'MAX_OBJECT',15000):
            self.store.write('assets/compact',{'assets':assets,'expires':time.time()+60})
            compact=self.store.read('assets/compact')
            self.assertEqual(set(compact['assets']),{'screen2048','small'})
            self.assertEqual(compact['assets']['screen2048'],assets['screen2048'])
            data=cache._cached_representation(compact['assets'],'screen1024')
            with Image.open(io.BytesIO(data)) as image:self.assertEqual(image.size,(1024,768))

    def test_small_provider_asset_is_not_encoded_again_for_identical_tiers(self):
        source=io.BytesIO();Image.new('RGB',(1024,768),'navy').save(source,'JPEG')
        save=Image.Image.save
        with patch.object(Image.Image,'save',autospec=True,side_effect=save) as encoder:
            assets=cache.prepare('synthetic',fixture.META,False,source.getvalue(),True)
        self.assertEqual(encoder.call_count,2)  # one screen plus the grid thumbnail
        self.assertEqual(assets['screen1024'],assets['screen2048'])

    def test_tiers_share_one_prepared_bundle_without_source_or_provider_reads(self):
        key=cache.asset_key('worker','/Synthetic',fixture.META)
        assets=cache.prepare('synthetic',fixture.META,True,self.raster(),True)
        self.store.write(key,{'assets':assets,'max_tier':2048,'expires':time.time()+60})
        with patch.object(cache,'current_store',return_value=self.store),patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META) as metadata,patch.object(cache,'_provider_preview') as provider,patch.object(cache,'_download_source') as original:
            for tier in ['1024','1600','2048','1024']:
                self.assertTrue(cache.request_preview('synthetic',fixture.META['path_display'],root='/Synthetic',user_id='worker',revision='r1',representation='screen',tier=tier)[0])
            self.assertEqual(metadata.call_count,4);provider.assert_not_called();original.assert_not_called()

    def test_ordinary_large_preview_cannot_download_original_in_background(self):
        key=cache.asset_key('worker','/Synthetic',fixture.META)
        with patch.object(cache,'current_store',return_value=self.store),patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META),patch.object(cache,'_provider_preview',side_effect=cache.PreviewError('unavailable')),patch.object(cache,'_download_source') as source,patch.object(cache._pool,'submit',side_effect=lambda fn,*args:fn(*args)):
            data,_=cache.request_preview('synthetic',fixture.META['path_display'],root='/Synthetic',user_id='worker',revision='r1',representation='screen',tier='2048')
            self.assertIsNone(data);source.assert_not_called()
            self.assertTrue(self.store.read(key)['unavailable'])

    def test_fallback_api_validates_tiers_and_uses_provider_sizes(self):
        with patch.object(api,'_request_user',return_value={'id':'worker'}),patch.object(api,'_dropbox_context',return_value={'access_token':'synthetic','root_path':'/Synthetic'}),patch.object(cache,'configured',return_value=False),patch.object(api,'_preview_bytes',return_value=b'jpeg') as preview:
            for tier,size in [('1024','w1024h768'),('1600','w2048h1536'),('2048','w2048h1536')]:
                result=asyncio.run(api.image_preview(get_request('/api/files-image-preview',{'path':'Artwork.jpg','representation':'screen','tier':tier})))
                self.assertEqual(result.status_code,200);self.assertEqual(preview.call_args.kwargs['size'],size)
            result=asyncio.run(api.image_preview(get_request('/api/files-image-preview',{'path':'Artwork.jpg','representation':'screen','tier':'9000'})))
            self.assertEqual(result.status_code,400)
