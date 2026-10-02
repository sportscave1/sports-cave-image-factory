"""Offline stability, isolation and bounded read scheduling regressions."""
from concurrent.futures import Future
from unittest.mock import Mock, patch
import threading
import unittest
from crm_campaign_home_cache import job, resolve, MAX_ENTRIES
from crm_campaign_home_data import invalidate, reporting_window, delivery_summary, attribution_summary
from crm_store import StoreUnavailable


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock(connect=None);self.state={}

    def response(self,key,value=None,error=None):
        f=Future()
        self.state.setdefault('campaign_home_cache',{})[(None,key)]=(0,f)
        if error:f.set_exception(error)
        else:f.set_result(value)
        return f

    def test_ready_stays_visible_during_refresh_and_error(self):
        key=('delivery',);good={'sent_emails':4,'click_rate':25}
        self.assertEqual(resolve(self.state,self.store,key,self.response(key,good),fields=good),(good,'READY'))
        pending=Future();self.state['campaign_home_cache'][(None,key)]=(None,pending)
        self.assertEqual(resolve(self.state,self.store,key,pending,fields=good),(good,'REFRESHING'))
        pending.set_exception(StoreUnavailable('private customer diagnostic'))
        with self.assertLogs('crm_campaign_home_cache',level='WARNING') as logs:
            self.assertEqual(resolve(self.state,self.store,key,pending,fields=good),(good,'ERROR'))
        self.assertNotIn('private',str(logs.output))

    def test_empty_or_partial_secondary_summary_never_overwrites_good_values(self):
        key=('attribution',);good={'revenue':{'NZD':'125'},'orders':1}
        resolve(self.state,self.store,key,self.response(key,good),fields=good)
        for value in ({},None,{'orders':0},{'orders':None,'revenue':{}}):
            self.assertEqual(resolve(self.state,self.store,key,self.response(key,value),fields=good),(good,'ERROR'))
        zero={'orders':0,'revenue':{}}
        self.assertEqual(resolve(self.state,self.store,key,self.response(key,zero),fields=good),(zero,'READY'))

    def test_late_response_cannot_replace_current_response(self):
        key=('counts',);old=self.response(key,{'active':1});new=self.response(key,{'active':2})
        resolve(self.state,self.store,key,new,fields=('active',))
        self.assertEqual(resolve(self.state,self.store,key,old,fields=('active',)),({'active':2},'REFRESHING'))
        invalidate(self.state)
        self.assertEqual(resolve(self.state,self.store,key,old,fields=('active',)),({'active':2},'REFRESHING'))

    def test_unrelated_groups_fail_independently(self):
        for key,value in ((('delivery',),{'sent_emails':4,'click_rate':25}), (('attribution',),{'orders':1,'revenue':{'NZD':'125'}})):
            resolve(self.state,self.store,key,self.response(key,value),fields=value)
        resolve(self.state,self.store,('counts',),self.response(('counts',),error=StoreUnavailable('unavailable')),fields=('active',))
        self.assertEqual(self.state['campaign_home_resolved'][(None,('delivery',))]['sent_emails'],4)
        self.assertEqual(self.state['campaign_home_resolved'][(None,('attribution',))]['orders'],1)

    def test_only_clicked_tabs_fetch_and_revisit_reuses_completed_read(self):
        calls=[]
        def read(tab):calls.append(tab);return []
        allkey=('table',('All campaigns','','All','All','Newest first'),0,None)
        sentkey=('table',('Sent','','All','All','Newest first'),0,None)
        first=job(self.state,self.store,allkey,lambda:read('All campaigns'));first.result(2)
        self.assertEqual(calls,['All campaigns'])
        second=job(self.state,self.store,sentkey,lambda:read('Sent'));second.result(2)
        self.assertIs(job(self.state,self.store,sentkey,lambda:read('Sent')),second)
        self.assertEqual(calls,['All campaigns','Sent'])

    def test_query_changes_do_not_invalidate_kpi_cache(self):
        summary=job(self.state,self.store,('counts',),lambda:{'active':2});summary.result(2)
        job(self.state,self.store,('table','query A'),lambda:[]).result(2)
        job(self.state,self.store,('table','query B'),lambda:[]).result(2)
        self.assertIs(job(self.state,self.store,('counts',),lambda:None),summary)

    def test_empty_table_is_valid_and_failed_refresh_keeps_rows(self):
        key=('table','All');good=[{'id':'known'}]
        resolve(self.state,self.store,key,self.response(key,good))
        self.assertEqual(resolve(self.state,self.store,key,self.response(key,error=StoreUnavailable('offline'))),(good,'ERROR'))
        self.assertEqual(resolve(self.state,self.store,key,self.response(key,[])),([],'READY'))

    def test_bounded_cache_never_clears_pending_jobs(self):
        pending=Future();self.state['campaign_home_cache']={(None,('pending',)):(None,pending)}
        for i in range(MAX_ENTRIES-1):self.response(('table',i),[])
        job(self.state,self.store,('new',),lambda:[]).result(2)
        self.assertIn((None,('pending',)),self.state['campaign_home_cache'])
        self.assertLessEqual(len(self.state['campaign_home_cache']),MAX_ENTRIES)

    def test_many_table_queries_cannot_evict_resolved_summary(self):
        good={'active':2};key=('counts',)
        resolve(self.state,self.store,key,self.response(key,good),fields=good)
        for i in range(MAX_ENTRIES+5):
            tablekey=('table',i)
            f=job(self.state,self.store,tablekey,lambda:[]);f.result(2)
            resolve(self.state,self.store,tablekey,f)
        self.assertIn((None,key),self.state['campaign_home_cache'])
        self.assertEqual(self.state['campaign_home_resolved'][(None,key)],good)
        self.assertLessEqual(len(self.state['campaign_home_resolved']),MAX_ENTRIES)

    def test_independent_reads_run_concurrently_without_waterfall(self):
        arrived=threading.Barrier(4)
        futures=[job(self.state,self.store,(name,),lambda:arrived.wait(2)) for name in ('counts','delivery','attribution','table')]
        self.assertEqual(sorted(f.result(3) for f in futures),[0,1,2,3])

    def test_completed_ttl_does_not_expire_slow_inflight_request(self):
        gate=threading.Event()
        with patch('crm_campaign_home_cache.monotonic',return_value=0):
            future=job(self.state,self.store,('slow',),lambda:gate.wait(2))
        try:
            with patch('crm_campaign_home_cache.monotonic',return_value=100):
                self.assertIs(job(self.state,self.store,('slow',),lambda:None),future)
        finally:gate.set()
        future.result(3)
        with patch('crm_campaign_home_cache.monotonic',return_value=100):
            self.assertIs(job(self.state,self.store,('slow',),lambda:None),future)
        with patch('crm_campaign_home_cache.monotonic',return_value=110):
            self.assertIs(job(self.state,self.store,('slow',),lambda:None),future)

    def test_shared_exact_utc_window_and_source_predicates(self):
        window=reporting_window()
        self.assertEqual((window[1]-window[0]).total_seconds(),30*86400)
        delivery_summary(self.store,window);attribution_summary(self.store,window)
        self.assertEqual(self.store.q.call_args_list[0].args[1],(*window,*window,*window,*window))
        self.assertEqual(self.store.q.call_args_list[1].args[1],window)
        sql=' '.join(c.args[0] for c in self.store.q.call_args_list)
        for required in ('s.status=\'ACCEPTED\'','NOT s.test_send','delivered AND clicked','a.eligible','order_created_at<%s','sent_at<%s'):
            self.assertIn(required,sql)


if __name__=='__main__':unittest.main()
