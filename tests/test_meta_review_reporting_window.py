import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page
import meta_ads_client as meta
import meta_review_live as live
import meta_review_tables as tables
import meta_review_benchmarks as benchmarks
from tests.test_meta_review_live import CONFIG


class ReportingWindowTests(unittest.TestCase):
    def test_screenshot_window_graph_values_and_website_definitions(self):
        calls=[]
        def response(path,params,config):
            calls.append((path,params))
            if path=='act_123': return {'account_id':'123','currency':'AUD','timezone_name':'Australia/Sydney'}
            if path.endswith('/campaigns'):
                return {'data':[{'id':str(i),'name':name,'status':'ACTIVE'} for i,name in enumerate(['Mentality','Greg Murphy','Immortals','Standard'])]}
            if params.get('breakdowns'): return {'data':[]}
            self.assertEqual(json.loads(params['time_range']),{'since':'2026-09-13','until':'2026-09-14'})
            self.assertNotIn('date_preset',params)
            self.assertEqual(params['use_unified_attribution_setting'],'true')
            return {'data':[{'campaign_id':str(i),'spend':spend,'impressions':'1000','inline_link_clicks':'43',
                'ctr':'7.53','cpc':'.34','inline_link_click_ctr':'4.34','cost_per_inline_link_click':'.59',
                'actions':[{'action_type':'offsite_conversion.fb_pixel_'+action,'value':value} for action,value in [('purchase','2'),('add_to_cart','5'),('initiate_checkout','3')]]+
                          [{'action_type':'purchase','value':'99'},{'action_type':'omni_purchase','value':'99'}],
                'cost_per_action_type':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'13.365'}],
                'purchase_roas':[{'action_type':'omni_purchase','value':'12.34'}]}
                for i,spend in enumerate(['26.73','30.79','49.97','46.37'])]}
        with patch.object(meta,'_request',side_effect=response),patch.object(meta,'_post') as write,patch.object(page.store,'load_history',side_effect=AssertionError('No historical totals')) as history:
            result=live.load_overview(CONFIG,date(2026,9,13),date(2026,9,14))
        rows={r['Campaign']:r for r in tables.va_campaign_rows(result['campaigns'])}
        self.assertEqual([rows[name]['Spend'] for name in ['Mentality','Greg Murphy','Immortals','Standard']],[26.73,30.79,49.97,46.37])
        for key,value in {'CTR':4.34,'CPC':.59,'Sales':2,'ATC':5,'Checkout':3,'ROAS':12.34,'CPA':13.365}.items():
            self.assertEqual(rows['Mentality'][key],value)
        self.assertEqual(result['campaigns'][0]['metrics']['impressions'],1000)
        self.assertEqual(result['campaigns'][0]['metrics']['inline_link_clicks'],43)
        write.assert_not_called(); history.assert_not_called()

    def test_website_no_cross_platform_fallback_and_exact_cpa(self):
        metrics=benchmarks.graph_metrics({'spend':'20','actions':[{'action_type':'purchase','value':'99'}]},website=True)
        self.assertEqual(metrics['purchases'],0)
        self.assertIsNone(metrics['cpa'])
        self.assertIsNone(metrics['ctr']); self.assertIsNone(metrics['cost_per_link_click'])

    def test_default_custom_refresh_period_and_separate_refresh_timestamp(self):
        data={'account':{'name':'Sports Cave','currency':'AUD'},'campaigns':[{'campaign_id':'1','campaign_name':'Fixture','metrics':{}}]}
        with patch.object(meta,'get_meta_config',return_value=CONFIG),patch.object(live,'load_overview',return_value=data) as read,patch.object(page.recency,'load',return_value={'available':False}):
            app=AppTest.from_string('import ads_meta_review_page as p\np.render_page()').run()
            today=datetime.now(ZoneInfo('Australia/Sydney')).date()
            self.assertEqual(read.call_args.args[1:],(today-timedelta(days=1),today))
            period=(date(2026,9,13),date(2026,9,14))
            app.date_input[0].set_value(period).run()
            app.button[0].click().run()
            self.assertEqual(read.call_args.args[1:],period)
            self.assertTrue(any('13 Sep 2026 – 14 Sep 2026 · AUD' in m.value for m in app.markdown))
            self.assertTrue(any('Last refreshed' in c.value for c in app.caption))
            self.assertFalse(app.exception)


if __name__=='__main__': unittest.main()
