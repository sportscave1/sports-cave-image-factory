import copy
from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import meta_review_tables as tables
import meta_review_live as live
import meta_ads_client as meta
from tests.test_meta_review_live import CONFIG


def campaigns():
    return [{'campaign_id':identity,'campaign_name':identity,'effective_status':status,
             'start_time':stamp,'metrics':{'spend':spend}}
            for identity,status,stamp,spend in [
                ('paused-new','PAUSED','2026-09-14',50),('active-old','ACTIVE','2026-09-01',1),
                ('archived','ARCHIVED','2026-09-14',90),('active-new','ACTIVE','2026-09-13',2),
                ('paused-old','PAUSED','2026-09-02',30)]]


class ActiveCpcTests(unittest.TestCase):
    def test_status_first_newest_and_manual_sort(self):
        rows=campaigns(); before=copy.deepcopy(rows)
        self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(rows)],
                         ['active-new','active-old','paused-new','paused-old','archived'])
        self.assertEqual(tables.sort_campaigns(rows,'Spend')[0]['campaign_id'],'archived')
        self.assertEqual(rows,before)
        rows[0]['status']='ACTIVE'  # effective status remains authoritative.
        rows.append({'campaign_id':'unknown','status':'OTHER','start_time':'2026-09-15'})
        self.assertEqual(tables.sort_campaigns(rows)[-1]['campaign_id'],'unknown')
        self.assertEqual(tables.sort_campaigns(rows)[0]['campaign_id'],'active-new')

    def test_graph_cpc_to_rendered_cell_without_recalculation(self):
        for value,expected in [('1.2345','$1.23'),(None,'—'),('0','$0.00')]:
            def response(path,params,config):
                if path=='act_123': return {'account_id':'123','currency':'AUD'}
                if path=='act_123/campaigns': return {'data':[{'id':'1','name':'Current','status':'ACTIVE'}]}
                if params.get('breakdowns'): return {'data':[]}
                self.assertEqual(path,'act_123/insights')
                self.assertIn('cpc',params['fields'].split(','))
                self.assertEqual(params['level'],'campaign')
                self.assertEqual(params['use_unified_attribution_setting'],'true')
                return {'data':[{'campaign_id':'1','spend':'100','clicks':'2','cpc':value}]}
            with self.subTest(value=value),patch.object(meta,'_request',side_effect=response),patch.object(meta,'_post') as write:
                rows=live.load_overview(CONFIG,date(2026,9,1),date(2026,9,14))['campaigns']
                rendered=tables.va_styled(tables.va_campaign_rows(rows),rows)
                self.assertEqual(rendered._display_funcs[(0,7)](rendered.data.iloc[0,7]),expected)
                self.assertEqual(rows[0]['metrics']['cpc'],None if value is None else float(value))
                write.assert_not_called()

    def test_active_cell_style_and_label_only(self):
        rows=campaigns()
        style=tables.va_styled(tables.va_campaign_rows(rows),rows)
        style._compute()
        status_index=list(style.data).index('Status')
        self.assertIn(('color','#287044'),style.ctx[(1,status_index)])
        self.assertIn(('color','#777777'),style.ctx[(0,status_index)])
        self.assertIn(('color','#777777'),style.ctx[(2,status_index)])
        self.assertIn('● ACTIVE',style.to_html())
        self.assertEqual(style.data.iloc[1]['Status'],'ACTIVE')

    def test_page_refresh_reorders_cached_source_and_keeps_manual_sort(self):
        with patch.object(meta,'get_meta_config',return_value=CONFIG),patch.object(live,'load_overview',side_effect=lambda *a: {'account':{'name':'Sports Cave','currency':'AUD'},'campaigns':campaigns()}) as load,patch('meta_review_recency.load',return_value={'available':False}):
            app=AppTest.from_string('import ads_meta_review_page as p\np.render_page()').run()
            self.assertFalse(app.exception)
            expected=['active-new','active-old','paused-new','paused-old','archived']
            self.assertEqual(app.dataframe[0].value['Campaign'].tolist(),expected)
            app.button[0].click().run()
            self.assertEqual(load.call_count,2)
            self.assertEqual(app.dataframe[0].value['Campaign'].tolist(),expected)
            app.selectbox[0].select('Spend').run()
            self.assertEqual(app.dataframe[0].value.iloc[0]['Campaign'],'archived')
            app.button[0].click().run()
            self.assertEqual(app.selectbox[0].value,'Spend')
            self.assertEqual(app.dataframe[0].value.iloc[0]['Campaign'],'archived')
            self.assertFalse(app.exception)


if __name__=='__main__': unittest.main()
