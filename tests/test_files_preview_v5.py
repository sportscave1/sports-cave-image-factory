"""V5 offline measurements: real Pillow/crypto, synthetic storage and metadata."""
import base64
import io
import json
import subprocess
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from services import files_preview_cache as cache
from tests import test_files_preview_v3 as fixture


class PreviewV5Tests(unittest.TestCase):
    def setUp(self):
        fixture.PreviewV3Tests.setUp(self)

    def test_configuration_report_contains_no_values_or_activation_claim(self):
        from scripts.files_preview_status import status
        import os
        result=status()
        report=json.dumps(result)
        self.assertTrue(result['encryption_key_valid'])
        self.assertNotIn(os.environ['FILES_PREVIEW_ENCRYPTION_KEY'],report)
        self.assertNotIn(os.environ['FILES_PREVIEW_BUCKET'],report)
        self.assertIn('NOT PERFORMED',result['provider_validation'])
        with patch.dict('os.environ',{'FILES_PREVIEW_ENCRYPTION_KEY':'invalid-private-value'}):
            report=status();self.assertFalse(report['encryption_key_valid'])
            self.assertNotIn('invalid-private-value',json.dumps(report))

    def seed(self):
        key=cache.asset_key('worker','/Synthetic',fixture.META)
        self.store.write(key,{'assets':{'screen':base64.b64encode(b'private-preview').decode()},'expires':time.time()+60})
        return key

    def request(self, **kwargs):
        return cache.request_preview('synthetic',fixture.META['path_display'],root='/Synthetic',
            user_id=kwargs.get('user_id','worker'),revision='r1',representation='screen')

    def test_memory_hit_keeps_permission_and_revision_checks(self):
        self.seed()
        with patch.object(cache,'current_store',return_value=self.store), patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META) as metadata, patch.object(self.store,'read',wraps=self.store.read) as read:
            self.request(); data,timing=self.request()
            self.assertEqual(data,b'private-preview');self.assertIn('memory;',timing)
            self.assertEqual(read.call_count,1);self.assertEqual(metadata.call_count,2)
            for meta,status in [({**fixture.META,'rev':'r2'},409),({**fixture.META,'path_display':'/Other/Artwork.jpg'},403)]:
                metadata.return_value=meta
                with self.assertRaises(cache.PreviewError) as error:self.request()
                self.assertEqual(error.exception.status,status)
            metadata.side_effect=PermissionError('revoked')
            with self.assertRaises(PermissionError):self.request()

    def test_memory_is_bounded_expires_and_does_not_cross_store_or_user(self):
        key=self.seed()
        cache._remember(self.store,key,'screen',b'a',time.time()+1)
        self.assertLessEqual(next(iter(cache._fast.values()))[0]-time.monotonic(),1)
        with patch.object(cache,'current_store',return_value=self.store),patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META):
            with patch.object(cache,'_provider_preview',side_effect=AssertionError('must not need provider')):
                with patch.object(self.store,'read',wraps=self.store.read) as read:
                    with patch.object(cache.time,'monotonic',return_value=time.monotonic()+31):
                        self.assertEqual(self.request()[0],b'private-preview')
                    self.assertEqual(read.call_count,1)
            # Another user cannot obtain this cached asset; force the miss to stop before work.
            with patch.object(self.store,'read',side_effect=RuntimeError('storage miss')):
                with self.assertRaises(RuntimeError):self.request(user_id='other')
        other=cache.Store()
        with patch.object(cache,'current_store',return_value=other),patch.object(cache.dbx,'get_file_metadata',return_value=fixture.META),patch.object(other,'read',side_effect=RuntimeError('new configuration')):
            with self.assertRaises(RuntimeError):self.request()
        for index in range(40):cache._remember(self.store,str(index),'screen',b'x'*1_000_000)
        self.assertLessEqual(sum(len(v[1]) for v in cache._fast.values()),32*1024*1024)
        for index in range(140):cache._remember(self.store,str(index),'small',b'x')
        self.assertLessEqual(len(cache._fast),128)

    def test_thumbnail_job_encodes_only_small_asset(self):
        source=io.BytesIO();Image.new('RGB',(1024,768),'blue').save(source,'JPEG')
        with patch.object(cache,'_download_source') as original:
            result=cache.prepare('synthetic',fixture.META,False,source.getvalue(),True,thumbnail_only=True)
            self.assertEqual(set(result),{'small'});original.assert_not_called()
        with Image.open(io.BytesIO(base64.b64decode(result['small']))) as image:
            self.assertLessEqual(max(image.size),256)

    def test_interleaved_baseline_measurements(self):
        baseline = types.ModuleType('files_v4_baseline')
        exec(compile(subprocess.check_output(['git','show','09709ea3:services/files_preview_cache.py']).decode(), 'v4', 'exec'), baseline.__dict__)
        source = io.BytesIO()
        Image.effect_noise((256,256),80).convert('RGB').save(source,'JPEG',quality=85)
        samples = {name: {'thumbnail_ms': [], 'warm_read_ms': [], 'storage_gets': 0}
                   for name in ['v4','v5']}
        for index in range(30):
            for name, module in ([('v4',baseline),('v5',cache)] if index%2==0 else [('v5',cache),('v4',baseline)]):
                start=time.perf_counter()
                options = {'thumbnail_only':True} if 'thumbnail_only' in module.prepare.__code__.co_varnames else {}
                result=module.prepare('synthetic',fixture.META,False,source.getvalue(),True,**options)
                samples[name]['thumbnail_ms'].append((time.perf_counter()-start)*1000)
                self.assertTrue(result['small'])
        for name,module in [('v4',baseline),('v5',cache)]:
            module._fast.clear()
            store=module.Store()
            key=module.asset_key('worker','/Synthetic',fixture.META)
            store.write(key,{'assets':{'screen':base64.b64encode(b'x'*600_000).decode()},'expires':time.time()+60})
            with patch.object(module,'current_store',return_value=store), patch.object(module.dbx,'get_file_metadata',return_value=fixture.META) as metadata, patch.object(self.s3,'get_object',wraps=self.s3.get_object) as get:
                for _ in range(30):
                    start=time.perf_counter()
                    value,_=module.request_preview('synthetic',fixture.META['path_display'],root='/Synthetic',user_id='worker',revision='r1',representation='screen')
                    samples[name]['warm_read_ms'].append((time.perf_counter()-start)*1000)
                    self.assertEqual(len(value),600_000)
                self.assertEqual(metadata.call_count,30)
                samples[name]['storage_gets']=get.call_count
        for result in samples.values():
            for field in ['thumbnail_ms','warm_read_ms']:
                values=sorted(result[field]);result[field+'_p50']=values[15];result[field+'_p95']=values[28]
        Path('test-results').mkdir(exist_ok=True)
        Path('test-results/files-v5-pipeline.json').write_text(json.dumps({'source':'synthetic; no Dropbox/R2 latency','samples':samples},indent=2))


if __name__=='__main__':
    unittest.main()
