from tests.test_crm_flow_v4 import webp
import os
import unittest
import uuid
from crm_thumbnail_store import acquire,finish,state_key
from crm_store import Store
from unittest.mock import patch
from tests.crm_db_fixture import connect

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SharedThumbnailTests(unittest.TestCase):
    def setUp(self):self.store=Store(connect);self.key='fixture-'+uuid.uuid4().hex
    def tearDown(self):self.store.q('DELETE FROM crm_runtime_state WHERE key=%s',(state_key(self.key),))
    def test_cross_service_claim_deduplication_and_restart_cache(self):
        phase,_,owner=acquire(self.store,self.key);self.assertEqual(phase,'CLAIMED')
        self.assertEqual(acquire(Store(connect),self.key)[0],'BUSY')
        data=webp()
        finish(self.store,self.key,owner,data)
        self.assertEqual(acquire(Store(connect),self.key),('READY',data,None))
    def test_stale_claim_recovers_and_previous_owner_cannot_overwrite(self):
        _,_,old=acquire(self.store,self.key)
        self.store.q("UPDATE crm_runtime_state SET updated_at=now()-interval '4 minutes' WHERE key=%s",(state_key(self.key),))
        phase,_,new=acquire(self.store,self.key);self.assertEqual(phase,'CLAIMED')
        finish(self.store,self.key,old,webp())
        self.assertEqual(acquire(self.store,self.key)[0],'BUSY')
        finish(self.store,self.key,new,webp())
        self.assertEqual(acquire(self.store,self.key)[1],webp())
    def test_failure_backoff_and_corrupt_shared_asset_recovery(self):
        _,_,owner=acquire(self.store,self.key);finish(self.store,self.key,owner)
        self.assertEqual(acquire(self.store,self.key)[0],'BUSY')
        self.store.set_state(state_key(self.key),{'state':'READY','webp':'broken'})
        self.assertEqual(acquire(self.store,self.key)[0],'CLAIMED')

    def test_corrupt_invalidation_cannot_erase_concurrent_valid_replacement(self):
        import base64
        self.store.set_state(state_key(self.key),{'state':'READY','webp':'broken'})
        query=self.store.q
        image=webp()
        def racing(sql,args=(),one=False):
            if sql.startswith("UPDATE crm_runtime_state SET value='{}'"):
                query("UPDATE crm_runtime_state SET value=%s::jsonb WHERE key=%s",
                      ('{"state":"READY","webp":"'+base64.b64encode(image).decode()+'"}',state_key(self.key)))
            return query(sql,args,one=one)
        with patch.object(self.store,'q',side_effect=racing):
            self.assertEqual(acquire(self.store,self.key)[0],'BUSY')
        self.assertEqual(acquire(self.store,self.key),('READY',image,None))
    def test_cache_does_not_touch_delivery_or_analytics_tables(self):
        tables=('crm_automations','crm_automation_enrollments','crm_marketing_sends','crm_delivery_events')
        before={t:self.store.q('SELECT count(*) n FROM '+t,one=True)['n'] for t in tables}
        _,_,owner=acquire(self.store,self.key);finish(self.store,self.key,owner,webp())
        self.assertEqual(before,{t:self.store.q('SELECT count(*) n FROM '+t,one=True)['n'] for t in tables})
