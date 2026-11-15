"""Native interaction checks using real render functions and disposable reads."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/appwide_ui_v1_preview.py'
class AppwidePresentationTests(unittest.TestCase):
 def app(self,route='Prodigi'):
  app=AppTest.from_file(str(FIXTURE),default_timeout=15)
  app.query_params.update(phase='after',route=route)
  app.run();self.assertFalse(app.exception)
  return app
 def test_dispatch_search_is_submitted_and_retained_across_filter_changes(self):
  app=self.app()
  app.text_input(key='prodigi-dispatch-log-search').set_value('#SC3001')
  next(b for b in app.button if b.label=='Search').click().run()
  self.assertEqual(app.session_state['prodigi_dispatch_submitted_search'],'#SC3001')
  self.assertEqual(len(app.dataframe[0].value),1)
  app.radio[0].set_value('History').run()
  self.assertEqual(app.session_state['prodigi_dispatch_submitted_search'],'#SC3001')
  self.assertEqual(len(app.dataframe[0].value),1)
 def test_lookup_preserves_empty_validation_and_exact_order_reference(self):
  app=self.app()
  app.button(key='prodigi-dispatch-find-order').click().run()
  self.assertIn('Enter a Shopify order number first.',[w.value for w in app.warning])
  app.text_input(key='prodigi-dispatch-order-search').set_value('#SC9999')
  app.button(key='prodigi-dispatch-find-order').click().run()
  self.assertEqual(app.session_state['fixture_lookup'],'#SC9999')
  self.assertIn('Order not found. Sync New Orders first, then try again.',[w.value for w in app.warning])
 def test_diagnostic_tables_keep_original_read_columns(self):
  for route,columns in [('Webhook Events',['ID','Topic','Status','Received']),('Sync Runs',['ID','Type','Status','Rows']),('App Errors',['ID','Source','Message','Resolved'])]:
   with self.subTest(route=route):
    app=self.app(route)
    self.assertEqual(list(app.dataframe[0].value.columns),columns)
 def test_persistence_refresh_and_navigation_actions_remain_available(self):
  app=self.app('Persistence Check')
  next(b for b in app.button if b.label=='Refresh Persistence Check').click().run()
  self.assertFalse(app.exception)
  self.assertEqual(len(app.dataframe[0].value),3)
  for label,route in [('Check Product Assets','Product Assets'),('Check Edition Tables','Limited Editions'),('Run Integrity Check','Edition Integrity Check')]:
   next(b for b in app.button if b.label==label).click().run()
   self.assertEqual(app.session_state['pending_page'],route)
if __name__=='__main__':unittest.main()
