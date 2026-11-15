"""Opt-in execution tests against the dedicated loopback SEO database only."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import unittest
import seo_phase1 as m
import seo_phase1_store as shared
import seo_workspace as w
from scripts.seo_phase1_devdata import DSN, connect, prepare, DevelopmentGoogleClient

@unittest.skipUnless(os.environ.get('SEO_PHASE1_TEST_POSTGRES')=='1','Opt in to isolated SEO PostgreSQL execution tests')
class SharedIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ,{'DATABASE_URL':DSN,'SEO_PHASE1_MODE':'shared'})
        cls.environment.start()
        prepare(Path(__file__).resolve().parents[1])
        cls.backend=SimpleNamespace(connect=connect)
    @classmethod
    def tearDownClass(cls):cls.environment.stop()
    def setUp(self):
        with connect() as conn:
            conn.execute("UPDATE seo_growth_tasks SET status='approved',title='Existing task',reason='Original',updated_at=now() WHERE id='dev-legacy-task'")
            conn.execute("UPDATE seo_growth_recommendations SET status='awaiting_approval',recommended_action='Original proposal',updated_at=now() WHERE id='dev-legacy-proposal'")
            state=w.default_state()
            w.upsert_record(state,'blog_records',{'id':'dev-existing-draft','article_title':'Existing','article_draft':'Preserve content','status':'Draft'})
            w.upsert_record(state,'keyword_mappings',{'id':'dev-mapping','primary_keyword':'sports art','target_page':'/products/art?variant=1'})
            conn.execute("UPDATE seo_workspace_state SET payload=%s::jsonb WHERE workspace_key='sports-cave'",(__import__('json').dumps(state),))
        self.admin={'id':'seo-admin','role':'admin','is_active':True}
    def store(self,user=None):return shared.SharedSEOStore(self.backend,user=user or self.admin)
    def find(self,state,kind):return next(r for r in state['plan_items'] if r.get('source_ref')==kind)
    def test_bidirectional_legacy_task_all_plan_statuses(self):
        import seo_growth_intelligence as growth
        for target,legacy in shared.PLAN_TO_TASK.items():
            store=self.store();state=store.load();row=self.find(state,'growth_task:dev-legacy-task')
            m.update_task(state,row,{'status':target},self.admin);store.save(state,actor_id='seo-admin')
            with connect() as conn:self.assertEqual(conn.execute("SELECT status FROM seo_growth_tasks WHERE id='dev-legacy-task'").fetchone()['status'],legacy)
            self.assertEqual(self.find(self.store().load(),'growth_task:dev-legacy-task')['status'],target)
        from google_seo_phase4 import PostgresSEOPhase4Store
        legacy_store=growth.PostgresSEOGrowthStore(PostgresSEOPhase4Store(self.backend))
        legacy_store.update_task_status('dev-legacy-task',status='assigned',actor='seo-admin')
        self.assertEqual(self.find(self.store().load(),'growth_task:dev-legacy-task')['status'],'In progress')
    def test_bidirectional_recommendations_and_no_implicit_approval(self):
        for target,legacy in shared.PLAN_TO_RECOMMENDATION.items():
            store=self.store();state=store.load();row=self.find(state,'recommendation:dev-legacy-proposal')
            m.update_task(state,row,{'status':target},self.admin);store.save(state)
            with connect() as conn:
                actual=conn.execute("SELECT status,approved_at FROM seo_growth_recommendations WHERE id='dev-legacy-proposal'").fetchone()
            self.assertEqual(actual['status'],legacy)
            self.assertIsNone(actual['approved_at'])
        with connect() as conn:conn.execute("UPDATE seo_growth_recommendations SET status='approved',updated_at=now() WHERE id='dev-legacy-proposal'")
        self.assertEqual(self.find(self.store().load(),'recommendation:dev-legacy-proposal')['status'],'Open')
    def test_editing_approved_proposal_invalidates_legacy_approval(self):
        with connect() as conn:conn.execute("UPDATE seo_growth_recommendations SET status='approved',approved_by='reviewer',approved_at=now(),updated_at=now() WHERE id='dev-legacy-proposal'")
        store=self.store();state=store.load();row=self.find(state,'recommendation:dev-legacy-proposal')
        m.update_task(state,row,{'title':'Edited proposal'})
        store.save(state)
        with connect() as conn:saved=conn.execute("SELECT status,approved_at FROM seo_growth_recommendations WHERE id='dev-legacy-proposal'").fetchone()
        self.assertEqual(saved['status'],'awaiting_approval');self.assertIsNone(saved['approved_at'])
        self.assertEqual(self.find(self.store().load(),'recommendation:dev-legacy-proposal')['status'],'Ready for review')

    def test_atomic_conflict_does_not_commit_plan_or_legacy_change(self):
        store=self.store();state=store.load();row=self.find(state,'growth_task:dev-legacy-task')
        with connect() as conn:conn.execute("UPDATE seo_growth_tasks SET status='cancelled',updated_at=now() WHERE id='dev-legacy-task'")
        m.update_task(state,row,{'status':'Done'},self.admin)
        with self.assertRaises(w.SEOStoreError):store.save(state)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM seo_growth_tasks WHERE id='dev-legacy-task'").fetchone()['status'],'cancelled')
            self.assertEqual(len(conn.execute("SELECT payload FROM seo_workspace_state WHERE workspace_key='sports-cave'").fetchone()['payload']['workspace_events']),0)
    def test_worker_cannot_mutate_admin_legacy_workflow(self):
        store=self.store({'id':'worker','role':'worker','page_permissions':['seo']});state=store.load()
        m.update_task(state,self.find(state,'growth_task:dev-legacy-task'),{'status':'Done'})
        with self.assertRaises(w.SEOStoreError):store.save(state)
    def test_disjoint_edits_merge_and_same_record_conflict_is_detected(self):
        first=self.store();second=self.store();a=first.load();b=second.load()
        m.create_task(a,title='A',target='/a');first.save(a)
        m.create_task(b,title='B',target='/b');second.save(b)
        current=self.store().load();self.assertTrue({'A','B'} <= {r['title'] for r in current['plan_items']})
        first=self.store();second=self.store();a=first.load();b=second.load()
        one=next(r for r in a['plan_items'] if r['title']=='A');two=next(r for r in b['plan_items'] if r['title']=='A')
        m.update_task(a,one,{'priority':'High'});first.save(a)
        m.update_task(b,two,{'priority':'Low'})
        with self.assertRaises(w.SEOStoreError):second.save(b)
    def test_duplicate_open_task_race_is_rejected(self):
        first=self.store();second=self.store();a=first.load();b=second.load()
        m.create_task(a,title='Same',target='/same');m.create_task(b,title='Same',target='/same')
        first.save(a)
        with self.assertRaises(w.SEOStoreError):second.save(b)
    def test_draft_mapping_review_and_history_survive_postgres_reload(self):
        store=self.store();state=store.load();draft=state['blog_records'][0]
        m.review_decision(state,draft,'Approved',self.admin);store.save(state)
        loaded=self.store().load();self.assertEqual(loaded['blog_records'][0]['article_draft'],'Preserve content')
        self.assertEqual(loaded['keyword_mappings'][0]['target_page'],'/products/art?variant=1')
        self.assertEqual(m.valid_decision(loaded,loaded['blog_records'][0]),'Approved')
        events,errors=m.read_saved_events(self.backend,actor_id='seo-admin',admin=True)
        self.assertEqual(errors,[])
    def test_real_google_contracts_scopes_filters_and_cache(self):
        from google_direct_reporting import GoogleReports,MemoryReports
        from google_seo import PostgresGoogleSEOStore
        reports=GoogleReports(connection_store=PostgresGoogleSEOStore(self.backend),cache=MemoryReports(),client_factory=lambda _:DevelopmentGoogleClient())
        start,end=m.period();filters=m.filters_for_ga4('Australia','Mobile')
        vals=[]
        for scope in ('Google organic','All organic','All channels'):
            report=reports.ga4('properties/57995487',m.ga4_contract(scope),start,end,filters=filters)
            vals.append(float(report['rows'][0]['metrics']['sessions']))
        self.assertEqual(vals,[560,1680,3360])
        totals=reports.gsc(start,end,(),{'market':'Australia','device':'Mobile'})
        queries=reports.gsc(start,end,('query','page'),{'market':'Australia','device':'Mobile'})
        self.assertEqual(totals[0]['clicks'],224)
        self.assertEqual(sum(r['clicks'] for r in queries),168)
        with connect() as conn:before=conn.execute('SELECT count(*) AS n FROM seo_phase1_dev_google_calls').fetchone()['n']
        reports.gsc(start,end,('query','page'),{'market':'Australia','device':'Mobile'})
        with connect() as conn:after=conn.execute('SELECT count(*) AS n FROM seo_phase1_dev_google_calls').fetchone()['n']
        self.assertEqual(before,after)

if __name__=='__main__':unittest.main()
