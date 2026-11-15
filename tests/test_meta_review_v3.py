"""Offline reliability contracts. Never contacts Meta or writes advertising data."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
import unittest
from unittest.mock import Mock, patch
import requests
import meta_ads_client as meta
import meta_review_live as live
import meta_review_retry as retry
from tests.test_meta_review_live import CONFIG

class RetryTests(unittest.TestCase):
    def run_read(self, responses):
        sleeps=[]
        with patch.object(meta,'_request',side_effect=responses) as request:
            result=retry.get('act_123/insights',{},CONFIG,100,clock=lambda:0,
                             sleep=sleeps.append,jitter=lambda a,b:0)
        return result,request.call_count,sleeps

    def test_transient_matrix_recovers(self):
        for status,code,subcode in [(400,2,1504044),(500,None,None),(502,None,None),
                                    (503,None,None),(504,None,None),(429,None,None),(400,4,None),(400,613,None)]:
            with self.subTest(status=status,code=code):
                result,count,sleeps=self.run_read([meta.MetaAdsApiError('temporary',status_code=status,error_code=code,error_subcode=subcode),{'data':[]}])
                self.assertEqual((result,count,sleeps),({'data':[]},2,[1]))

    def test_success_does_not_retry(self):
        self.assertEqual(self.run_read([{'data':[]}]),({'data':[]},1,[]))

    def test_permanent_errors_never_retry(self):
        for code in (10,100,102,190,200,294):
            error=meta.MetaAdsApiError('permanent',status_code=400,error_code=code,is_transient=True)
            with patch.object(meta,'_request',side_effect=error) as request:
                with self.assertRaises(meta.MetaAdsApiError):
                    retry.get('x',{},CONFIG,time.monotonic()+10)
                self.assertEqual(request.call_count,1)
        self.assertFalse(retry.transient(meta.MetaAdsApiError('permanent',error_code=2,is_transient=False)))

    def test_transport_timeout_and_interruption(self):
        for cause in (requests.Timeout(),requests.ConnectionError()):
            error=meta.MetaAdsApiError('transport'); error.__cause__=cause
            self.assertEqual(self.run_read([error,{'data':[]}])[1],2)

    def test_exhaustion_and_retry_after_budget(self):
        for wait,expected in [(None,3),('90',1)]:
            error=meta.MetaAdsApiError('limited',status_code=429,retry_after=wait)
            with patch.object(meta,'_request',side_effect=error) as request:
                with self.assertRaises(meta.MetaAdsApiError):
                    retry.get('x',{},CONFIG,35,clock=lambda:0,sleep=lambda _:None,jitter=lambda a,b:0)
                self.assertEqual(request.call_count,expected)
        self.assertEqual(self.run_read([meta.MetaAdsApiError('limited',status_code=429,retry_after='5'),{}])[2],[5])

    def test_metadata_and_timeout_propagation_get_only(self):
        response=Mock(ok=False,status_code=400,headers={'Retry-After':'3'})
        response.json.return_value={'error':{'code':2,'error_subcode':1504044,'is_transient':True}}
        with patch.object(meta.requests,'get',return_value=response) as get:
            with self.assertRaises(meta.MetaAdsApiError) as caught:
                meta._request('x',config=CONFIG)
        self.assertTrue(caught.exception.is_transient)
        self.assertEqual(caught.exception.retry_after,'3')
        self.assertEqual(get.call_args.kwargs['timeout'],30)
        with patch.object(meta,'_request',side_effect=lambda *a,**k:meta.READ_TIMEOUT.get().total):
            self.assertEqual(retry.get('x',{},CONFIG,2,clock=lambda:0),2)
        self.assertEqual(meta.READ_TIMEOUT.get(),30)

class CacheTests(unittest.TestCase):
    def test_retry_after_survives_manual_refresh(self):
        cache={}; key=('rate-limited-scope','overview')
        def fail():raise meta.MetaAdsApiError('limited',status_code=429,retry_after='90')
        entry=live.cached_read(cache,key,fail,clock=lambda:0)
        self.assertEqual(entry['expires'],90)
        live.invalidate(cache,key[0])
        loader=Mock(return_value={})
        live.cached_read(cache,key,loader,clock=lambda:20)
        loader.assert_not_called()

    def test_failed_refresh_retains_exact_scope_and_timestamp(self):
        cache={}; key=(live.scope(CONFIG),'overview','2026-01-01','2026-01-31')
        old=live.cached_read(cache,key,lambda:{'campaigns':[{'campaign_id':'1'}]},clock=lambda:0)
        live.invalidate(cache,key[0])
        def fail(): raise meta.MetaAdsApiError('temporary',error_code=2)
        stale=live.cached_read(cache,key,fail,clock=lambda:1)
        self.assertEqual(stale['data'],old['data']); self.assertEqual(stale['refreshed_at'],old['refreshed_at'])
        self.assertTrue(stale['stale']); self.assertEqual(stale['expires'],11)
        for other in [(live.scope({**CONFIG,'ad_account_id':'act_456'}),*key[1:]),(*key[:2],'2026-02-01',key[3])]:
            self.assertIsNone(live.cached_read(cache,other,fail)['data'])
        recovered=live.cached_read(cache,key,lambda:{'campaigns':[]},clock=lambda:12)
        self.assertFalse(recovered['stale']); self.assertFalse(recovered['error'])
        self.assertEqual(recovered['data'],{'campaigns':[]})

    def test_concurrent_reports_coalesce_and_copies_are_isolated(self):
        started=Event(); finish=Event(); calls=[]
        def loader():
            calls.append(1); started.set(); finish.wait(2); return {'campaigns':[{'id':'1'}]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            first=pool.submit(live.cached_read,{},('unique-test','overview'),loader)
            self.assertTrue(started.wait(1))
            others=[pool.submit(live.cached_read,{},('unique-test','overview'),loader) for _ in range(3)]
            time.sleep(.05); finish.set()
            results=[f.result() for f in [first,*others]]
        self.assertEqual(len(calls),1)
        results[0]['data']['campaigns'].clear()
        self.assertEqual(len(results[1]['data']['campaigns']),1)

    def test_partial_pagination_never_replaces_complete_cache(self):
        cache={}; key=('pagination-test',)
        live.cached_read(cache,key,lambda:[{'id':'complete'}],clock=lambda:0)
        with patch.object(meta,'_request',side_effect=[{'data':[{'id':'partial'}],'paging':{'next':'yes','cursors':{'after':'next'}}},meta.MetaAdsApiError('invalid',error_code=100)]):
            entry=live.cached_read(cache,key,lambda:live.Reader(CONFIG).pages('x',{}),clock=lambda:121)
        self.assertTrue(entry['stale']);self.assertEqual(entry['data'],[{'id':'complete'}])

if __name__=='__main__': unittest.main()
