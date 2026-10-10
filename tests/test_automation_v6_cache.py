"""Aggregate isolation, expiry and stale-result fencing without application data."""
import unittest
from unittest.mock import patch
from concurrent.futures import Future
from types import SimpleNamespace
import crm_automation_aggregate_cache as cache


class CacheTests(unittest.TestCase):
    def setUp(self):
        cache._entries.clear()
        self.connect=lambda:None
        self.scope=cache.scope(self.connect,{'id':'admin'},'shop-a')
        self.value=[{'active':3,'all_count':3,'drafts':0,'paused':0,'archived':0}]

    def save(self):
        cache.put(self.scope,'counts',self.value,cache.token(self.scope,'counts'))

    def test_account_store_connection_isolation_and_missing_scope(self):
        self.save()
        for scope in (cache.scope(self.connect,{'id':'other'},'shop-a'),
                      cache.scope(self.connect,{'id':'admin'},'shop-b'),
                      cache.scope(lambda:None,{'id':'admin'},'shop-a'),None):
            self.assertIsNone(cache.get(scope,'counts'))
        self.assertIsNone(cache.scope(self.connect,{},'shop-a'))
        self.assertIsNone(cache.scope(self.connect,{'id':'admin'},None))

    def test_incomplete_previous_period_is_not_a_success(self):
        from crm_automation_home import payload
        with self.assertRaises(ValueError):
            payload(('delivery',None),lambda:dict(sent_emails=0,delivery_rate=None,
                open_rate=None,click_rate=None,revenue={},previous={}))

    def test_values_are_copied_and_expire(self):
        with patch.object(cache,'monotonic',return_value=10):self.save()
        self.value[0]['active']=99
        with patch.object(cache,'monotonic',return_value=190):
            result=cache.get(self.scope,'counts');self.assertEqual(result['value'][0]['active'],3)
            result['value'][0]['active']=8
            self.assertEqual(cache.get(self.scope,'counts')['value'][0]['active'],3)
        with patch.object(cache,'monotonic',return_value=3611):self.assertIsNone(cache.get(self.scope,'counts'))

    def test_invalidation_preserves_last_good_and_fences_old_completion(self):
        self.save();old=cache.token(self.scope,'counts');cache.invalidate(self.scope)
        cache.put(self.scope,'counts',[{'active':100}],old)
        self.assertTrue(cache.get(self.scope,'counts')['expired'])
        self.assertEqual(cache.get(self.scope,'counts')['value'],self.value)
        self.save();self.assertNotIn('expired',cache.get(self.scope,'counts'))

    def test_lru_is_bounded_and_evicted_completion_cannot_repopulate(self):
        old=cache.token(self.scope,'counts')
        for i in range(cache.MAX_SCOPES):cache.token(cache.scope(self.connect,{'id':str(i)},'shop'),'counts')
        self.assertEqual(len(cache._entries),cache.MAX_SCOPES)
        cache.put(self.scope,'counts',self.value,old)
        self.assertIsNone(cache.get(self.scope,'counts'))

    def test_fresh_hit_needs_no_job_or_database_and_failed_refresh_retains_value(self):
        from crm_automation_home import read
        state={'analytics_scope':self.scope};store=SimpleNamespace(connect=self.connect)
        self.save()
        with patch('crm_automation_ui.home_state',return_value=state),patch('crm_automation_ui.job') as job:
            self.assertEqual(read(store,('counts',None),lambda:self.fail('No query on hit')),self.value[0])
            job.assert_not_called()
        cache.invalidate(self.scope)
        def failed_job(state,store,key,load,**kwargs):
            future=Future()
            try:future.set_result(load())
            except Exception as exc:future.set_exception(exc)
            state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,future)
            return future
        with patch('crm_automation_ui.home_state',return_value=state),patch('crm_automation_ui.job',side_effect=failed_job),patch('crm_automation_home.st.caption'),patch('crm_automation_home.st.button',return_value=False):
            self.assertEqual(read(store,('counts',None),lambda:{}),self.value[0])
            self.assertEqual(state['activity']['counts'],'ERROR')
            self.assertEqual(cache.get(self.scope,'counts')['value'],self.value)


if __name__=='__main__':unittest.main()
