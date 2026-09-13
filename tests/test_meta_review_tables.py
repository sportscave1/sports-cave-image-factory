import copy
from datetime import date
import json
import unittest
from unittest.mock import patch
import meta_ads_client as meta
import meta_review_live as live
import meta_review_tables as tables
from tests.test_meta_review import ad
from tests.test_meta_review_live import CONFIG


class CompactTableTests(unittest.TestCase):
    def campaigns(self):
        return [
            {'campaign_id':'1','campaign_name':'Old start','start_time':'2026-07-01T00:00:00Z','created_time':'2026-09-01','metrics':{'roas':4.12,'purchases':2}},
            {'campaign_id':'2','campaign_name':'New start','start_time':'2026-09-12T00:00:00+10:00','metrics':{'roas':None,'purchases':None}},
            {'campaign_id':'3','campaign_name':'Created fallback','created_time':'2026-08-01','metrics':{'roas':0,'purchases':0}},
            {'campaign_id':'4','campaign_name':'No date','metrics':{'roas':2,'purchases':9}}]

    def test_newest_uses_start_then_created_missing_last(self):
        self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(self.campaigns())],['2','3','1','4'])

    def test_roas_descending_missing_below_explicit_zero(self):
        self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(self.campaigns(),'ROAS')],['1','4','3','2'])

    def test_purchases_descending_missing_below_explicit_zero(self):
        self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(self.campaigns(),'Purchases')],['4','1','3','2'])

    def test_styling_formats_currency_percent_counts_and_missing(self):
        styled=tables.styled([{'Spend':26.55,'ROAS':4.12,'Link CTR':3.23,'CPC':.13,'Purchases':2,'ATC':None}])
        html=styled.to_html()
        for text in ('$26.55','4.12','3.23%','$0.13','—'): self.assertIn(text,html)
        self.assertEqual(styled.data['Spend'][0],26.55)

    def test_selection_uses_displayed_sorted_identity(self):
        rows=tables.sort_campaigns(self.campaigns(),'Purchases')
        self.assertEqual(tables.selected_row({'selection':{'rows':[0]}},rows)['campaign_id'],'4')
        self.assertEqual(tables.selected_row({'selection':{'cells':[[1,'Campaign']]}},rows)['campaign_id'],'1')
        self.assertIsNone(tables.selected_row({'selection':{'rows':[100]}},rows))
        self.assertIsNone(tables.selected_row({'selection':{'rows':[]}},rows))

    def test_compact_creative_rows_preserve_full_original_details(self):
        item=ad(); item['assets']['primary_text'][0]['value']='Exact long original text. '*40
        before=copy.deepcopy(item)
        row=tables.creative_rows([item])[0]
        self.assertLessEqual(len(row['Primary Text']),140)
        self.assertEqual(row['Headline'],'Exact headline')
        self.assertEqual(row['Creative'],item['assets']['image'][0]['value'])
        self.assertEqual(row['Spend'],120)
        self.assertEqual(item,before)

    def test_presentation_preserves_kill_warning_and_winner_decisions(self):
        item=ad(); item['decision']['label']='KILL CANDIDATE'
        self.assertEqual(tables.result_labels([item])['1'],'Kill candidate')
        self.assertEqual(item['decision']['label'],'KILL CANDIDATE')


class CampaignOverviewTests(unittest.TestCase):
    def test_paginated_campaign_level_insights_without_ad_reads(self):
        calls=[]
        def response(path,params,config):
            calls.append((path,params))
            if path=='act_123': return {'account_id':'123','currency':'AUD'}
            if path=='act_123/campaigns': return {'data':[{'id':'1','name':'Current'},{'id':'2','name':'No metrics'}]}
            if path=='act_123/insights':
                if params.get('after'): return {'data':[]}
                return {'data':[{'campaign_id':'1','spend':'26.55','actions':[
                    {'action_type':'purchase','value':'2'},{'action_type':'omni_purchase','value':'2'},
                    {'action_type':'add_to_cart','value':'3'},{'action_type':'omni_add_to_cart','value':'3'}],
                    'purchase_roas':[{'action_type':'purchase','value':'4.12'}]}],
                    'paging':{'next':'https://untrusted.example','cursors':{'after':'next-page'}}}
            raise AssertionError('Unexpected ad read '+path)
        with patch.object(meta,'_request',side_effect=response),patch.object(meta,'_post') as write:
            result=live.load_overview(CONFIG,None,date(2026,9,13))
        write.assert_not_called()
        self.assertEqual(len(calls),4)
        params=calls[-1][1]
        self.assertEqual(params['level'],'campaign')
        self.assertEqual(params['date_preset'],'maximum')
        self.assertEqual(params['use_unified_attribution_setting'],'true')
        self.assertNotIn('ad_id',params['fields'].split(','))
        metrics={r['campaign_id']:r['metrics'] for r in result['campaigns']}
        self.assertEqual(metrics['1']['purchases'],2)
        self.assertEqual(metrics['1']['add_to_cart'],3)
        self.assertEqual(metrics['1']['roas'],4.12)
        self.assertIsNone(metrics['2']['roas'])

    def test_missing_reported_roas_is_not_synthesized_for_overview(self):
        with patch.object(live,'load_campaigns',return_value={'campaigns':[{'campaign_id':'1'}]}),patch.object(live.Reader,'pages',return_value=[{'campaign_id':'1','spend':'10','action_values':[{'action_type':'purchase','value':'50'}]}]):
            self.assertIsNone(live.load_overview(CONFIG,None,date(2026,9,13))['campaigns'][0]['metrics']['roas'])

    def test_conflicting_campaign_summaries_fail_without_double_count(self):
        with patch.object(live,'load_campaigns',return_value={'campaigns':[]}),patch.object(live.Reader,'pages',return_value=[{'campaign_id':'1','spend':'10'},{'campaign_id':'1','spend':'11'}]):
            with self.assertRaisesRegex(ValueError,'conflicting campaign'):
                live.load_overview(CONFIG,None,date(2026,9,13))


if __name__=='__main__': unittest.main()
