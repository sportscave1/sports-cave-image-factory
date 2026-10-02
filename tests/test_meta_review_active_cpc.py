import copy
from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import meta_review_tables as tables
import meta_review_live as live
import meta_ads_client as meta
import ads_meta_review_page as page
from tests.test_meta_review import history
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
                self.assertIn('cost_per_inline_link_click',params['fields'].split(','))
                self.assertEqual(params['level'],'campaign')
                self.assertEqual(params['use_unified_attribution_setting'],'true')
                return {'data':[{'campaign_id':'1','spend':'100','clicks':'2','cpc':'99','cost_per_inline_link_click':value}]}
            with self.subTest(value=value),patch.object(meta,'_request',side_effect=response),patch.object(meta,'_post') as write:
                rows=live.load_overview(CONFIG,date(2026,9,1),date(2026,9,14))['campaigns']
                rendered=tables.va_styled(tables.va_campaign_rows(rows),rows)
                column = list(rendered.data).index('CPC')
                self.assertEqual(rendered._display_funcs[(0,column)](rendered.data.iloc[0,column]),expected)
                self.assertEqual(rows[0]['metrics']['cost_per_link_click'],None if value is None else float(value))
                write.assert_not_called()

    def test_campaign_modal_reuses_campaign_metrics_and_shared_format_without_requests(self):
        since,until=date(2026,9,1),date(2026,9,14)
        for value,expected in [(1.2345,'$1.23'),(0.87,'$0.87'),(None,'—')]:
            campaign={'campaign_id':'cam','campaign_name':'Current','metrics':{
                'spend':100,'purchases':4,'roas':2,'cpa':25,'cost_per_link_click':value}}
            before=copy.deepcopy(campaign['metrics'])
            data=copy.deepcopy(history())
            captured=[]
            original=tables.va_styled
            def capture(rows,evidence):
                styled=original(rows,evidence); captured.append(styled); return styled
            with self.subTest(value=value),patch.object(live,'load_campaign',return_value=data) as load, \
                    patch.object(page,'_load_preferences',return_value={'selections':[],'mapping':[]}), \
                    patch.object(page.recency,'load',return_value={'available':False,'latest':{}}), \
                    patch.object(page,'winner_board'),patch.object(tables,'va_styled',side_effect=capture), \
                    patch.object(meta,'_request',side_effect=AssertionError('Unexpected Graph request')) as network, \
                    patch.object(meta,'_post',side_effect=AssertionError('Unexpected Meta write')) as write:
                app=AppTest.from_string(
                    'import ads_meta_review_page as p\nfrom tests.test_meta_review_live import CONFIG\n'
                    'from datetime import date\n'
                    f'p.render_campaign_details(CONFIG,{campaign!r},date(2026,9,1),date(2026,9,14))').run()
                self.assertFalse(app.exception)
                summary=app.dataframe[0].value
                self.assertEqual(list(summary),['Spend','Sales','ROAS','CPA','CPC','Last Sale','Action'])
                self.assertEqual(summary.iloc[0][['Spend','Sales','ROAS','CPA']].tolist(),[100,4,2,25])
                styled=captured[0]; column=list(styled.data).index('CPC')
                self.assertEqual(styled._display_funcs[(0,column)](styled.data.iloc[0,column]),expected)
                expected_ads=tables.va_ad_rows(page.build_ads(data,'cam'))
                self.assertEqual(list(app.dataframe[1].value),list(expected_ads[0]))
                for label in ('Sales','ROAS','CPA','CTR','ATC','Checkout'):
                    self.assertEqual(app.dataframe[1].value[label].tolist(),[row[label] for row in expected_ads])
                load.assert_called_once_with(CONFIG,'cam',since,until)
                app.run()
                self.assertFalse(app.exception)
                load.assert_called_once()
                network.assert_not_called(); write.assert_not_called()
                self.assertEqual(campaign['metrics'],before)

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
