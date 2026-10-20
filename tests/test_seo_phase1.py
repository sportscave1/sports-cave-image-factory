"""Offline Phase 1 regressions. Never use credentials or production persistence."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest
import seo_phase1 as m
import seo_navigation as n
import analytics_navigation as a
import seo_workspace as w
import os_accounts

class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.state=w.default_state()
    def test_menu_and_legacy_routes_keep_access(self):
        self.assertEqual([n.SEO_NAV_LABELS[r] for r in n.SEO_MENU_ROUTES],['Worker','Analytics','Plan','Review','History'])
        self.assertEqual(m.destination(n.SEO_KEYWORDS_ROUTE),(n.SEO_ANALYTICS_ROUTE,'Queries'))
        for old in a.ANALYTICS_ROUTES:
            self.assertEqual(m.destination(old)[0],n.SEO_ANALYTICS_ROUTE)
        analytics={'role':'worker','page_permissions':['analytics']}
        self.assertTrue(os_accounts.can_access_page(analytics,n.SEO_ANALYTICS_ROUTE))
        self.assertFalse(os_accounts.can_access_page(analytics,n.SEO_KEYWORDS_ROUTE))
        self.assertFalse(os_accounts.can_access_page(analytics,n.SEO_PLAN_ROUTE))
        self.assertFalse(os_accounts.can_access_page({'role':'worker','page_permissions':[]},n.SEO_ANALYTICS_ROUTE))
    def test_dedup_preserves_intent_and_url_identity(self):
        def add(**kwargs):return m.create_task(self.state,title='Review',**kwargs)
        one,added=add(target='https://example.test/p?variant=1&utm_source=gsc',query='Art',intent='title')
        self.assertTrue(added)
        duplicate,added=add(target='https://example.test/p?variant=1',query='art',intent='title')
        self.assertFalse(added); self.assertEqual(one['id'],duplicate['id'])
        self.assertTrue(add(target='https://example.test/p?variant=2',query='art',intent='title')[1])
        self.assertTrue(add(target='https://example.test/p?variant=1',query='art',intent='links')[1])
    def test_persistence_mapping_draft_and_review_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            store=w.LocalSEOStore(Path(folder)/'state.json')
            task,_=m.create_task(self.state,title='Test')
            draft=w.upsert_record(self.state,'blog_records',{'article_title':'Test','article_draft':'old'})
            m.update_task(self.state,task,{'draft_id':draft['id'],'priority':'High'})
            w.upsert_record(self.state,'keyword_mappings',{'primary_keyword':'art','target_page':'/p'})
            m.review_decision(self.state,draft,'Approved')
            store.save(self.state)
            loaded=w.LocalSEOStore(store.path).load()
            self.assertEqual(loaded['plan_items'][0]['draft_id'],draft['id'])
            self.assertEqual(loaded['keyword_mappings'][0]['target_page'],'/p')
            self.assertEqual(m.valid_decision(loaded,draft),'Approved')
            edited=w.upsert_record(loaded,'blog_records',{'article_draft':'new'},record_id=draft['id'])
            self.assertEqual(m.valid_decision(loaded,edited),'Needs review')
    def test_missing_values_weighted_ctr_and_complete_window(self):
        self.assertIsNone(m.gsc_totals([])['clicks'])
        totals=m.gsc_totals([{'clicks':1,'impressions':2},{'clicks':0,'impressions':98}])
        self.assertEqual(totals['ctr'],Decimal('.01'))
        start,end=m.period(today=date(2026,10,20))
        self.assertEqual(end,date(2026,10,17)); self.assertEqual((end-start).days+1,28)
    def test_scopes_and_no_conversion_join(self):
        self.assertIn(('sessionSource','EXACT','google'),m.ga4_contract('Google organic').filters)
        self.assertNotIn(('sessionSource','EXACT','google'),m.ga4_contract('All organic').filters)
        self.assertEqual(m.ga4_contract('All channels').filters,())
        self.assertNotIn('sessionKeyEventRate',m.ga4_contract('Google organic').metrics)
    def test_scan_only_observed_signals_and_deduplicates(self):
        rows=[{'query':'art','impressions':1000,'clicks':4,'ctr':'.004','average_position':12,'page':'/p'}, {'query':'empty'}]
        self.assertEqual(m.scan(self.state,rows,{'end':'2026-10-17'}),1)
        self.assertEqual(m.scan(self.state,rows,{'end':'2026-10-17'}),0)
        self.assertEqual(len(self.state['plan_items']),1)
        self.assertEqual(self.state['plan_items'][0]['work_type'],'Other')
    def test_health_distinct_issues_and_history(self):
        rows=[{'canonical_url':'https://example.test/p','issue_summary':x,'source':'HTML','status':'Open'} for x in ('Missing title','Broken link')]
        self.assertEqual(m.import_health(self.state,rows),2)
        self.assertEqual(m.import_health(self.state,rows),0)
        self.assertEqual(len(self.state['plan_items']),2)
    def test_local_store_never_discovers_database(self):
        with patch.dict('os.environ',{'SEO_PHASE1_MODE':'local','DATABASE_URL':'unusable'}),patch.object(w,'default_store',side_effect=AssertionError('remote store')):
            self.assertIsInstance(m.store_for_workspace(),w.LocalSEOStore)
    def test_local_projects_reuse_interface_and_event_idempotency(self):
        with tempfile.TemporaryDirectory() as folder:
            store=w.LocalSEOStore(Path(folder)/'local.json'); projects=m.LocalBlogProjects(store)
            saved=projects.save_project({'title':'Existing brief','owner_id':'one','brief':{'primary_keyword':'art'}})
            projects.save_project({**saved,'title':'Edited'})
            self.assertEqual(len(projects.list_projects(owner_id='one')),1)
            self.assertEqual(projects.list_projects(owner_id='two'),[])
            args=dict(actor_id='one',actor_name='one',action_type='saved',idempotency_key='rev1')
            self.assertTrue(projects.record_event(saved['id'],**args))
            self.assertFalse(projects.record_event(saved['id'],**args))

    def test_saved_history_is_read_only_and_keeps_partial_streams(self):
        from unittest.mock import MagicMock
        backend=MagicMock()
        cur=backend.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.side_effect=[RuntimeError('missing audit'),[{'id':'sync1','source':'GSC','status':'failed','created_at':'2026-10-19','error_summary':'quota'}],[]]
        events,errors=m.read_saved_events(backend,actor_id='worker',admin=False)
        self.assertEqual(errors,['SEO audit'])
        self.assertEqual(events[0]['action'],'Data refresh')
        self.assertEqual(events[0]['status'],'failed')
        for call in cur.execute.call_args_list:
            self.assertTrue(call.args[0].startswith('SELECT'))
        self.assertEqual(backend.connect.return_value.__enter__.return_value.commit.call_count,0)
    def test_saved_work_preserves_source_identity_and_visibility(self):
        tasks=[{'id':'existing-task','title':'Existing','status':'draft','target_page':'/p'}]
        self.assertEqual(m.import_saved_work(self.state,tasks=tasks),1)
        self.assertEqual(m.import_saved_work(self.state,tasks=tasks),0)
        self.assertTrue(self.state['plan_items'][0]['admin_only'])
        self.assertEqual(self.state['plan_items'][0]['source_ref'],'growth_task:existing-task')
    def test_scan_is_bounded_and_records_real_evaluated_count(self):
        rows=[{'query':'same','impressions':1000,'ctr':'.01'}]*501
        m.scan(self.state,rows,{})
        detail=self.state['workspace_events'][-1]['detail']
        self.assertEqual(detail['rows_evaluated'],500)
        self.assertEqual(detail['rows_available'],501)

    def test_render_uses_shared_storage_and_local_override_is_explicit(self):
        with patch.dict('os.environ',{'RENDER_SERVICE_ID':'srv-fixture'},clear=True):
            self.assertFalse(m.local_mode())
            with patch.dict('os.environ',{'SEO_PHASE1_MODE':'local'}):self.assertTrue(m.local_mode())
        with patch.dict('os.environ',{},clear=True):self.assertTrue(m.local_mode())

if __name__=='__main__':unittest.main()
