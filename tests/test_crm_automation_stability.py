"""Offline queue capacity, retention, cancellation and isolation regressions."""
import inspect,time,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import Future
import crm_automation_read_cache as cache

class StabilityTests(unittest.TestCase):
    def test_global_capacity_and_duplicate_pending_read(self):
        gate=threading.Event();state={};store=SimpleNamespace(connect=None)
        def slow():gate.wait(3);return []
        try:
            futures=[cache.job(state,store,('probe',i),slow) for i in range(10)]
            self.assertEqual(sum(f is not None for f in futures),6)
            self.assertIs(cache.job(state,store,('probe',0),slow),futures[0])
            cache.dispose(state)
            self.assertTrue(any(f.cancelled() for f in futures if f))
        finally:
            gate.set()
            for f in futures:
                if f and not f.cancelled():f.result(4)
        self.assertFalse(state.get('campaign_home_cache'))
    def test_large_results_are_compact_and_budgeted(self):
        values=[{'key':str(i),'display':'synthetic data '*40} for i in range(5000)]
        packed=cache.pack(values)
        self.assertIsInstance(packed,cache.PackedRows)
        self.assertLess(len(packed.data),1024*1024)
        self.assertEqual(cache.unpack(packed),values)
    def test_fifty_navigation_cycles_keep_cache_bounded(self):
        store=SimpleNamespace(connect=None);state={}
        for cycle in range(50):
            f=cache.job(state,store,('checkout-list',cycle),lambda:[{'text':'x'*1000} for _ in range(100)])
            self.assertIsNotNone(f);f.result(2)
            result,phase=cache.resolve(state,store,('checkout-list',cycle),f)
            self.assertEqual(phase,'READY')
            cache.dispose(state)
            self.assertEqual(len(state.get('campaign_home_resolved',{})),0)
    def test_error_retains_last_good_and_does_not_leak_text(self):
        store=SimpleNamespace(connect=None);state={};key=('probe',0)
        f=cache.job(state,store,key,lambda:[{'safe':1}]);f.result(2)
        cache.resolve(state,store,key,f)
        fail=Future();fail.set_exception(ValueError('private credentials'))
        state['campaign_home_cache'][(None,key)]=(None,fail)
        result,phase=cache.resolve(state,store,key,fail)
        self.assertEqual((result,phase),([{'safe':1}],'ERROR'))
    def test_fragment_failure_is_local(self):
        @cache.isolated
        def broken():raise RuntimeError('secret')
        with patch('streamlit.caption') as caption:broken()
        self.assertNotIn('secret',caption.call_args.args[0])
    def test_no_permanent_server_timer_or_fast_retry(self):
        import crm_automation_home as home,crm_automation_analytics_ui as analytics
        source=inspect.getsource(home)+inspect.getsource(analytics)
        for term in ("run_every=",'setTimeout(tick,250)','setTimeout(tick,500)',"poll',.1"):
            self.assertNotIn(term,source)
        self.assertIn('window.scAutoRequest',source)
    def test_campaign_pool_is_unchanged(self):
        import crm_campaign_home_cache as campaign
        self.assertEqual(campaign.POOL._max_workers,4)
        self.assertEqual(cache.POOL._max_workers,2)

    def test_route_boundary_preserves_shell_and_safe_error(self):
        from crm_page import automation_workspace
        with patch('crm_automation_ui.workspace',side_effect=RuntimeError('private')),patch('crm_page.st.error') as error:
            automation_workspace(None,None,None)
        self.assertIn('Other OS sections remain available',error.call_args.args[0])
        self.assertNotIn('private',error.call_args.args[0])

    def test_navigation_preserves_draft_and_disposes_ui_work(self):
        from crm_navigation import navigation_allowed
        pending=Future();state={'automation_analytics_reads':{'campaign_home_cache':{(None,('detail',)):(None,pending)}}}
        self.assertTrue(navigation_allowed(state,'CRM Automations','Home'))
        self.assertTrue(pending.cancelled());self.assertNotIn('automation_analytics_reads',state)
        state={'automation_editor':{'name':'unsaved','document':{}},'automation_saved':{'name':'saved','document':{}}}
        self.assertFalse(navigation_allowed(state,'CRM Automations','Home'))
        self.assertEqual(state['automation_editor']['name'],'unsaved')
