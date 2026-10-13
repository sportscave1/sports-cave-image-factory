import json
import time
import unittest
from unittest.mock import patch, Mock
import files_native_launch as launch
import files_upload_api as api
from tests.test_psd_access import PsdAccessTests, USERS


class NativeV2AccessTests(PsdAccessTests):
    # Inherit the real signed-cookie regression setup and existing preservation tests.
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.manager=launch.LaunchManager()
        self.extra=patch.object(launch,'LAUNCHES',self.manager);self.extra.start()
        self.record={'action':'openWith','item':{'id':'id:1','revision':'test-revision'}}
        self.headers={'origin':'https://test.local'}
    async def asyncTearDown(self):
        self.extra.stop();await super().asyncTearDown()
    async def prepare(self):
        return await self.client.post('/api/files-native-launch',json=self.record,headers=self.headers)
    async def claim(self,code,method='POST',headers=None):
        return await self.client.request(method,'/api/files-native-launch/claim',json={'code':code},headers=headers or self.headers)

    async def test_single_use_same_files_user_and_no_secret_in_launch(self):
        for role in ['admin','va','va_attach']:
            self.cookie(role);r=await self.prepare();self.assertEqual(r.status_code,200,r.text)
            d=r.json();self.assertNotIn('secret',d);self.assertNotIn('fake',r.text);self.assertNotIn('Renamed',r.text)
            self.assertTrue(d['launch_url'].endswith('#'+d['code']))
            c=await self.claim(d['code']);self.assertEqual(c.status_code,200,c.text)
            self.assertEqual(c.json()['action'],'openWith');self.assertEqual(c.json()['transfer']['base_url'],'https://test.local')
            self.assertEqual((await self.claim(d['code'])).status_code,409)
        self.store.attach.assert_not_called()

    async def test_other_user_session_expiry_denial_origin_cancel(self):
        self.cookie('va');d=(await self.prepare()).json()
        self.cookie('admin');self.assertEqual((await self.claim(d['code'])).status_code,403)
        self.cookie('va');self.assertEqual((await self.claim(d['code'],headers={'origin':'https://evil.test'})).status_code,403)
        self.assertEqual((await self.claim(d['code'],'DELETE')).status_code,200)
        self.assertEqual((await self.claim(d['code'])).status_code,403)
        d=(await self.prepare()).json();self.manager.records[d['code']]['expires']=time.monotonic()-1
        self.assertEqual((await self.claim(d['code'])).status_code,403)
        for who in [None,'unauthorised','inactive']:
            self.cookie(who);self.assertEqual((await self.prepare()).status_code,403)
        self.cookie('va',version=1);self.assertEqual((await self.prepare()).status_code,403)
        self.cookie('va');self.assertEqual((await self.client.post('/api/files-native-launch',json=self.record,headers={'origin':'https://evil.test'})).status_code,403)
        self.assertEqual((await self.client.post('/api/files-native-launch',json=self.record)).status_code,403)

    async def test_revision_renames_scope_metadata_and_executables(self):
        self.cookie('va')
        renamed={**api.dropbox_integration.psd_open_metadata('fake','id:1',include_preview=False),'name':'New name.psd','path_display':'/Sportscave Team Folder/New name.psd'}
        with patch.object(api.dropbox_integration,'psd_open_metadata',return_value=renamed) as cloud:
            d=(await self.prepare()).json();c=(await self.claim(d['code'])).json()
            grant=api.NATIVE_TRANSFER_MANAGER.get(c['transfer']['ticket'],c['transfer']['secret'])
            self.assertEqual(grant.items[0]['dropbox_id'],'id:1');self.assertEqual(grant.roots[0]['source_relative_path'],'New name.psd')
            cloud.assert_called_once_with('fake','id:1',include_preview=False)
        for changes in [{'id':'id:other'},{'rev':'new'},{'content_hash':''},{'path_display':'/outside/Renamed.psd'},{'path_display':'/Sportscave Team Folder/back'+chr(92)+'slash/New name.psd'},{'name':'bad.exe','path_display':'/Sportscave Team Folder/bad.exe'},{'name':'bad.exe.','path_display':'/Sportscave Team Folder/bad.exe.'},{'name':'bad.psd.','path_display':'/Sportscave Team Folder/bad.psd.'},{'.tag':'folder'}]:
            with patch.object(api.dropbox_integration,'psd_open_metadata',return_value={**renamed,**changes}):
                self.assertGreaterEqual((await self.prepare()).status_code,400)
        for extra in ['path','origin','secret']:
            self.record[extra]='bad';self.assertEqual((await self.prepare()).status_code,400);self.record.pop(extra)

    async def test_large_prepare_no_download_and_pinned_stream(self):
        self.cookie('va');meta={**api.dropbox_integration.psd_open_metadata('fake','id:1',include_preview=False),'size':2**31}
        with patch.object(api.dropbox_integration,'psd_open_metadata',return_value=meta),patch.object(api.dropbox_integration,'get_psd_file_response',return_value=(meta,self.stream)) as download:
            r=await self.client.post('/api/files-native-open',json=self.record,headers=self.headers)
            self.assertEqual(r.status_code,200);download.assert_not_called();grant=r.json()
            record=api.NATIVE_TRANSFER_MANAGER.get(grant['ticket'],grant['secret'])
            self.assertEqual(record.purpose,'native_open');self.assertEqual(record.items[0]['size'],2**31)
            # Stream smoke uses a small mock response; the master is not loaded in memory.
            meta['size']=5
            response=await self.client.get('/api/files-native-transfer/content',params={'ticket':grant['ticket'],'item':record.items[0]['token']},headers={'x-sports-cave-transfer-secret':grant['secret']})
            self.assertEqual(response.status_code,200);self.assertEqual(response.content,b'mock!')
            download.assert_called_once_with('fake','id:1','test-revision')

    async def test_launch_page_no_query_credential_and_safe_headers(self):
        r=await self.client.get('/files-native-launch');self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['referrer-policy'],'no-referrer');self.assertEqual(r.headers['x-frame-options'],'DENY')
        self.assertIn('history.replaceState',r.text);self.assertIn('version 11',r.text)


class NativePrepareBenchmark(unittest.TestCase):
    def test_metadata_only_two_gb_before_after(self):
        from tests.test_psd_open import metadata
        import statistics
        meta={**metadata(),'size':2**31}
        context={'access_token':'fake','root_path':'/Sportscave Team Folder'}
        metrics={}
        with patch.object(api.dropbox_integration,'get_file_metadata',return_value=meta) as old,patch.object(api.dropbox_integration,'psd_open_metadata',return_value=meta) as new,patch.object(api.dropbox_integration,'get_psd_file_response') as download:
            for label in ['baseline','v2']:
                times=[]
                for _ in range(25):
                    start=time.perf_counter()
                    if label=='baseline':
                        api.NativeTransferManager().create(access_token='fake',root_path=context['root_path'],user={'id':'va'},selections=[{'path':'02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Renamed.psd','id':'id:1','revision':'test-revision','tag':'file'}])
                    else:launch.create_open_transfer(context,{'id':'va'},{'id':'id:1','revision':'test-revision'})
                    times.append((time.perf_counter()-start)*1000)
                times.sort();metrics[label]={'median':statistics.median(times),'p95':times[23],'metadata_calls':25,'master_downloads':0,'size':2**31}
            self.assertEqual(old.call_count,25);self.assertEqual(new.call_count,25);download.assert_not_called()
        from pathlib import Path
        root=Path(__file__).resolve().parents[1];(root/'output').mkdir(exist_ok=True);(root/'output/native_v2_prepare_bench.json').write_text(json.dumps(metrics,indent=2))
        print('2 GiB metadata-only preparation (mock Dropbox, actual grant code): '+json.dumps(metrics))
