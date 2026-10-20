from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import seo_navigation as nav

FIXTURE=Path(__file__).parent/'fixtures'/'seo_phase1_preview.py'

class Phase1UITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict('os.environ',{'SEO_PHASE1_FIXTURE_DIR':self.temp.name,'SEO_PHASE1_MODE':'local'})
        self.env.start()
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('External requests forbidden in offline UI'))
        self.database=patch('psycopg.connect',side_effect=AssertionError('Production persistence forbidden in offline UI'))
        self.network_mock=self.network.start(); self.database_mock=self.database.start()
    def tearDown(self):
        self.assertEqual(self.network_mock.call_count,0)
        self.assertEqual(self.database_mock.call_count,0)
        self.network.stop(); self.database.stop()
        self.env.stop(); self.temp.cleanup()
    def app(self):return AppTest.from_file(str(FIXTURE),default_timeout=15).run()
    def select(self,app,label,value):
        next(x for x in app.selectbox if x.label==label).set_value(value).run()
        self.assertEqual(list(app.exception),[])
    def click(self,app,label):
        next(x for x in app.button if x.label==label).click().run()
        self.assertEqual(list(app.exception),[])
    def test_analytics_plan_review_history_flow(self):
        app=self.app(); self.assertEqual(list(app.exception),[])
        self.select(app,'Workspace',nav.SEO_ANALYTICS_ROUTE)
        self.select(app,'View','Queries')
        self.click(app,'Create Plan task')
        self.select(app,'Workspace',nav.SEO_PLAN_ROUTE)
        self.assertTrue(any('title' in d.value and any('Review search performance' in title for title in d.value['title']) for d in app.dataframe))
        self.click(app,'Prepare linked content draft')
        self.select(app,'Workspace',nav.SEO_REVIEW_ROUTE)
        self.click(app,'Save review decision')
        self.select(app,'Workspace',nav.SEO_HISTORY_ROUTE)
        self.assertTrue(any('Review decision' in x.label for x in app.expander))
        self.select(app,'Workspace',nav.SEO_OVERVIEW_ROUTE)
        self.click(app,'Evaluate loaded search opportunities')
        self.assertTrue(any('Scan completed' in x.value for x in app.success))
    def test_all_views_and_partial_failure_keep_working_source(self):
        app=self.app(); self.select(app,'Workspace',nav.SEO_ANALYTICS_ROUTE)
        for view in ('Queries','Pages','Channels','Engagement','Ecommerce','Events','Audience','Realtime','Overview details','Store operations','Mappings'):
            self.select(app,'View',view)
        self.select(app,'View','Pages')
        app.session_state['fixture-fail-ga4']=True
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('GA4 is unavailable' in x.value for x in app.warning))
        self.assertTrue(any('Google organic clicks'==m.label and m.value=='4.00' for m in app.metric))
    def test_existing_blog_project_editor_offline(self):
        app=self.app(); self.select(app,'Workspace',nav.SEO_REVIEW_ROUTE)
        self.select(app,'Content workflow','Blog projects')
        self.click(app,'+ New')
        self.assertFalse(app.exception)
        self.assertTrue(any(x.label=='Project' for x in app.selectbox))

if __name__=='__main__':unittest.main()
