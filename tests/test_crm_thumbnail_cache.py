from tests.test_crm_flow_v4 import webp
from pathlib import Path
from copy import deepcopy
from threading import Event
from unittest import TestCase
from unittest.mock import Mock,patch
import tempfile
import os
import time
import crm_thumbnail_cache as cache
from crm_thumbnail_render import image_url

class ThumbnailTests(TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,CRM_THUMBNAIL_CACHE_DIR=self.directory.name);self.env.start()
        self.row={'id':'flow','steps':[{'step_id':'one','template_id':'template','template_version':7}], 'config':{'revision':1}}
        self.step={'step_id':'one','document':{'subject':'draft'}}
    def tearDown(self):
        deadline=time.monotonic()+5
        while cache.PENDING and time.monotonic()<deadline:time.sleep(.01)
        self.env.stop();self.directory.cleanup()
    def test_live_version_is_immutable_despite_draft_edit(self):
        key,label,live=cache.selection(self.row,self.step)
        self.assertEqual(label,'LIVE v7')
        self.step['document']['subject']='unsaved draft'
        self.assertEqual(cache.selection(self.row,self.step)[0],key)
        self.row['steps'][0]['template_version']=8
        self.assertNotEqual(cache.selection(self.row,self.step)[0],key)
    def test_new_steps_four_five_and_six_are_drafts(self):
        for n in (4,5,6):
            step={'step_id':str(n),'document':{'subject':str(n)}}
            key,label,live=cache.selection(self.row,step)
            self.assertEqual(label,'DRAFT');self.assertIsNone(live)
            step['document']['subject']='changed'
            self.assertNotEqual(cache.selection(self.row,step)[0],key)
    def test_live_source_uses_exact_template_and_no_render_settings_read(self):
        store=Mock();store.template.return_value={'automation_id':'flow','step_id':'one','automation_version':7,'document':{'live':True},'render_settings':{'frozen':True}}
        _,_,live=cache.selection(self.row,self.step)
        self.assertEqual(cache.source_loader(store,self.row,self.step,live)(),({'live':True},{'frozen':True}))
        store.template.assert_called_once_with('template',7);store.render_settings.assert_not_called()
        store.send.assert_not_called();store.q.assert_not_called()
    def test_wrong_publication_rejected(self):
        store=Mock();store.template.return_value={'automation_id':'other'}
        with self.assertRaises(ValueError):cache.source_loader(store,self.row,self.step,self.row['steps'][0])()
    def test_cache_reused_without_database_or_generation(self):
        key=cache.token('cached');data=webp()
        (cache.cache_dir()/(key+'.webp')).write_bytes(data)
        load=Mock(side_effect=AssertionError('No DB'))
        self.assertEqual(cache.request(key,load),('READY',data));load.assert_not_called()
        # Clearing process state leaves private disk assets available after restart.
        cache.FAILURES.clear()
        self.assertEqual(cache.cached(key),data)
    def test_corrupt_asset_recovers(self):
        key=cache.token('corrupt');(cache.cache_dir()/(key+'.webp')).write_bytes(b'broken')
        self.assertIsNone(cache.cached(key));self.assertFalse((cache.cache_dir()/(key+'.webp')).exists())
    def test_nonblocking_deduplicated_generation_and_failure_isolation(self):
        entered=Event();release=Event();load=Mock()
        def slow(*args,**kwargs):entered.set();release.wait(3);raise RuntimeError('fixture failure')
        key=cache.token('failed')
        with patch('crm_thumbnail_cache.subprocess.run',side_effect=slow):
            load.return_value=({}, {})
            started=time.monotonic()
            self.assertEqual(cache.request(key,load)[0],'LOADING')
            self.assertLess(time.monotonic()-started,.1)
            self.assertTrue(entered.wait(2))
            for _ in range(8):self.assertEqual(cache.request(key,load)[0],'LOADING')
            self.assertEqual(load.call_count,1)
            release.set()
            while key in cache.PENDING:time.sleep(.01)
        self.assertEqual(cache.request(key,load)[0],'ERROR')
    def test_network_only_accepts_bounded_public_images(self):
        for value in ('http://127.0.0.1/a.png','https://tracker.test/pixel.png','https://cdn.shopify.com/events.png','https://cdn.shopify.com/s/files/a.svg'):
            self.assertIsNone(image_url(value))
        self.assertIsNone(image_url('https://cdn.shopify.com/s/files/a.png?token=private&width=4000'))
        self.assertEqual(image_url('https://cdn.shopify.com/s/files/a.png?width=4000'),'https://cdn.shopify.com/s/files/a.png?width=320')
    def test_prewarm_failures_do_not_escape(self):
        with patch('crm_thumbnail_cache.request',side_effect=RuntimeError('fixture')):
            cache.prewarm([('id','name',{'automation_id':'flow','document':{},'render_settings':{}})],8)


    def test_unwritable_cache_is_a_nonfatal_visible_error(self):
        with patch('crm_thumbnail_cache.cached',side_effect=PermissionError('fixture')):
            self.assertEqual(cache.request(cache.token('no-disk'),Mock()),('ERROR',None))
    def test_controller_survives_sanitizer_and_has_bounded_retry(self):
        import re
        from crm_flow_thumbnail import SCRIPT
        body=SCRIPT.removeprefix('<script>').removesuffix('</script>')
        self.assertIsNone(re.search(r'<[/\w!]',body))
        self.assertIn('90000',body)
        self.assertIn('img.complete&&!img.naturalWidth',body)
        self.assertIn('e.isTrusted',body)
        self.assertIn("['pointerdown','keydown','focusin']",body)
