import copy
import unittest
from unittest.mock import patch
import meta_review_benchmarks as b
import meta_review_tables as tables
import ads_meta_review_page as page
from tests.test_meta_review import history


def metrics(spend=55, purchases=0, atc=0, checkout=0, lpv=100, roas=None):
    row={'spend':str(spend),'impressions':'2000','inline_link_clicks':'110','ctr':'6.1234567','cpc':'.2134567',
         'actions':[{'action_type':k,'value':str(v)} for k,v in (
             ('landing_page_view',lpv),('add_to_cart',atc),('initiate_checkout',checkout),('purchase',purchases))]}
    if roas is not None: row['purchase_roas']=[{'action_type':'omni_purchase','value':str(roas)}]
    return b.graph_metrics(row)


class GraphTests(unittest.TestCase):
    def test_canonical_actions_never_sum_or_fallback_to_aliases(self):
        raw={'spend':'100','actions':[{'action_type':k,'value':'2'} for k in ('purchase','add_to_cart','initiate_checkout','landing_page_view')]+
             [{'action_type':k,'value':'90'} for k in ('omni_purchase','offsite_conversion.fb_pixel_purchase','onsite_web_purchase','web_in_store_purchase','omni_add_to_cart','omni_initiated_checkout')],
             'action_values':[{'action_type':'purchase','value':'51'},{'action_type':'omni_purchase','value':'999'}]}
        m=b.graph_metrics(raw)
        for key in ('purchases','add_to_cart','checkout','landing_page_views'): self.assertEqual(m[key],2)
        self.assertEqual(m['purchase_value'],51)
        self.assertEqual(b.graph_metrics({'spend':'1','actions':[{'action_type':'omni_purchase','value':'90'}]})['purchases'],0)

    def test_full_precision_funnel_formulas(self):
        m=metrics(55,2,8,4,90)
        for key,value in dict(lpv_rate=90/110*100,atc_rate=8/90*100,checkout_rate=4/90*100,purchase_cvr=2/90*100,
                              checkout_purchase=50,cost_per_lpv=55/90,cost_per_atc=55/8,cost_per_checkout=55/4,cpa=27.5).items():
            with self.subTest(key=key): self.assertEqual(m[key],value)
        self.assertEqual(m['click_ctr'],6.1234567)
        self.assertEqual(m['cpc'],.2134567)

    def test_outbound_graph_rates_and_roas_preserved(self):
        m=b.graph_metrics({'spend':'1','outbound_clicks':[{'action_type':'outbound_click','value':'17'}],
            'outbound_clicks_ctr':[{'action_type':'outbound_click','value':'1.234567'}],
            'cost_per_outbound_click':[{'action_type':'outbound_click','value':'.987654'}],
            'purchase_roas':[{'action_type':'omni_purchase','value':'12.12345'},{'action_type':'purchase','value':'9'}]})
        self.assertEqual(m['outbound_clicks'],17); self.assertEqual(m['outbound_ctr'],1.234567)
        self.assertEqual(m['outbound_cpc'],.987654); self.assertEqual(m['roas'],12.12345)

    def test_missing_data_and_zero_events(self):
        empty=b.graph_metrics({})
        self.assertIsNone(empty['purchases']); self.assertEqual(b.evaluate(empty)['recommendation'],'NO DATA')
        m=metrics(10,lpv=0)
        for key in ('cost_per_lpv','cost_per_atc','cost_per_checkout','cpa','atc_rate'): self.assertIsNone(m[key])
        self.assertEqual(m['purchases'],0)
        self.assertEqual(b.evaluate(m,'INSTANT EXPERIENCE','AU')['recommendation'],'LEARNING')

    def test_format_uses_metadata_not_names(self):
        self.assertEqual(b.ad_format({'name':'Instant Experience Carousel'}),'UNKNOWN')
        self.assertEqual(b.ad_format({'object_story_spec':{'link_data':{'link':'https://www.facebook.com/canvas/123','child_attachments':[{},{}]}}}),'INSTANT EXPERIENCE')
        self.assertEqual(b.ad_format({'object_story_spec':{'link_data':{'child_attachments':[{},{}]}}}),'CAROUSEL')
        self.assertEqual(b.ad_format({'asset_feed_spec':{'ad_formats':['CAROUSEL']}}),'CAROUSEL')
        self.assertEqual(b.ad_format({'object_story_spec':4}),'UNKNOWN')
        self.assertEqual(b.ad_format({'link':'https://facebook.com.attacker.test/canvas/1'}),'UNKNOWN')

    def test_market_uses_only_delivery_spend(self):
        for c in ('AU','US','GB'):
            self.assertEqual(b.market([{'country':c,'spend':'10'},{'country':'ZZ','spend':'0'}]),c)
        self.assertEqual(b.market([{'country':'AU','spend':99},{'country':'US','spend':1}]),'MIXED')
        self.assertEqual(b.market([]),'UNKNOWN')


class ScoringTests(unittest.TestCase):
    def test_every_locked_threshold_boundary(self):
        for format,metrics_ in b.RATES.items():
            for metric,(a,g) in metrics_.items():
                with self.subTest(format=format,metric=metric):
                    self.assertEqual(b.metric_score(a-.00001,(a,g))[1],'RED')
                    self.assertEqual(b.metric_score(a,(a,g)),(4,'AMBER'))
                    self.assertEqual(b.metric_score(g,(a,g)),(7,'GREEN'))
                    self.assertEqual(b.metric_score(g*1e6,(a,g))[0],9)
        for context,metrics_ in b.COSTS.items():
            for metric,(g,a) in metrics_.items():
                with self.subTest(context=context,metric=metric):
                    self.assertEqual(b.metric_score(g,(g,a),True),(7,'GREEN'))
                    self.assertEqual(b.metric_score(a,(g,a),True),(4,'AMBER'))
                    self.assertEqual(b.metric_score(a+.001,(g,a),True)[1],'RED')
                    self.assertEqual(b.metric_score(a*1e6,(g,a),True)[0],1)

    def test_locked_specific_constants(self):
        self.assertEqual(b.COSTS['AU','INSTANT EXPERIENCE']['cpc'],(.22,.25))
        self.assertEqual(b.COSTS['AU','CAROUSEL']['cost_per_checkout'],(26.57,48.63))
        self.assertEqual(b.COSTS['US','INSTANT EXPERIENCE']['cost_per_atc'],(12.25,18.90))
        self.assertEqual(b.COSTS['US','CAROUSEL']['cost_per_lpv'],(1.79,2.85))
        self.assertEqual(b.RATES['INSTANT EXPERIENCE']['checkout_rate'],(.63,3.40))
        self.assertEqual(b.RATES['CAROUSEL']['checkout_rate'],(.5,1.90))

    def test_neutral_display_only_and_renormalization(self):
        m=metrics(55,atc=8,checkout=4)
        for country,format,keys in [('GB','INSTANT EXPERIENCE',('cpc','cpa','cost_per_lpv')),
            ('AU','INSTANT EXPERIENCE',('cost_per_atc',)),('US','CAROUSEL',('cost_per_atc','cost_per_checkout')),
            ('MIXED','CAROUSEL',('cpc','cost_per_lpv'))]:
            r=b.evaluate(m,format,country)
            for key in keys: self.assertNotIn(key,r['cells'])
        r=b.evaluate(m,'CAROUSEL','AU')
        self.assertEqual(r['cells']['cost_per_atc']['weight'],0)
        before=r['score']; m.update(ctr=1e6,outbound_ctr=1e6)
        self.assertEqual(b.evaluate(m,'CAROUSEL','AU')['score'],before)
        active=[v for v in r['cells'].values() if v['score'] is not None and v['weight']>0]
        self.assertAlmostEqual(r['score'],sum(v['score']*v['weight'] for v in active)/sum(v['weight'] for v in active))

    def test_maturity_exact_boundaries(self):
        for spend,stage in [(0,'LEARNING'),(28.239,'LEARNING'),(28.24,'EARLY REVIEW'),(41.579,'EARLY REVIEW'),(41.58,'MATURE REVIEW'),(62.65,'MATURE REVIEW'),(62.651,'DECISION POINT')]:
            self.assertEqual(b.maturity(metrics(spend)),stage)

    def test_recommendations_and_purchase_precedence(self):
        for spend,atc,checkout,expected in [(10,0,0,'LEARNING'),(20,8,4,'LEARNING'),(30,0,0,'WATCH'),
                (55,8,4,'CHECK STORE / CHECKOUT'),(55,0,0,'REFRESH CREATIVE'),(75,0,0,'STOP / REPLACE')]:
            with self.subTest(spend=spend): self.assertEqual(b.evaluate(metrics(spend,atc=atc,checkout=checkout),'INSTANT EXPERIENCE','AU')['recommendation'],expected)
        m=metrics(192,8,8,8,100,12); m['click_ctr']=.001
        self.assertEqual(b.evaluate(m,'INSTANT EXPERIENCE','AU')['recommendation'],'TOP WINNER')
        m['roas']=4
        self.assertEqual(b.evaluate(m,'INSTANT EXPERIENCE','AU')['recommendation'],'KEEP RUNNING')
        m['roas']=2
        self.assertEqual(b.evaluate(m,'INSTANT EXPERIENCE','AU')['recommendation'],'WATCH PROFITABILITY')

    def test_unknown_format_no_format_specific_score(self):
        self.assertIsNone(b.evaluate(metrics(),'UNKNOWN','AU')['score'])
        self.assertNotIn('cpc',b.evaluate(metrics(),'UNKNOWN','AU')['cells'])

    def test_individual_ads_score_independently_without_mutating_winner_data(self):
        h=history(); h['currency']='AUD'; h['country_delivery']=[{'ad_id':a['ad_id'],'country':'AU','spend':'55'} for a in h['ads']]
        for c in h['creatives']: c['raw']['object_story_spec']['link_data']['link']='https://facebook.com/canvas/123'
        before=copy.deepcopy(h)
        ads=page.build_ads(h)
        self.assertTrue(all('benchmark' in a for a in ads))
        self.assertEqual(h,before)
        for a in ads:
            self.assertIn('decision',a)  # existing manual winner framework remains intact

    def test_new_sort_options_missing_last(self):
        rows=[{'campaign_id':'1','metrics':{'spend':10},'benchmark':{'score':8}},
              {'campaign_id':'2','metrics':{'spend':20},'benchmark':{'score':2}},
              {'campaign_id':'3','metrics':{},'benchmark':{}}]
        for sort,expected in [('Lowest Score',['2','1','3']),('Highest Score',['1','2','3']),('Highest Spend',['2','1','3'])]:
            self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(rows,sort)],expected)

    def test_campaign_and_child_recommendations_do_not_mask_each_other(self):
        def raw(spend,purchase,roas):
            return {'spend':str(spend),'impressions':'1000','ctr':'6','cpc':'.2','inline_link_clicks':'100',
                'actions':[{'action_type':'landing_page_view','value':'90'}, {'action_type':'purchase','value':str(purchase)}],
                'purchase_roas':[{'action_type':'omni_purchase','value':str(roas)}]}
        h={'ads':[{'ad_id':'1','campaign_id':'900','creative_id':'c'},{'ad_id':'2','campaign_id':'900','creative_id':'c'}],
           'creatives':[{'creative_id':'c','raw':{'object_story_spec':{'link_data':{'link':'https://facebook.com/canvas/123'}}}}],
           'adsets':[], 'currency':'AUD', 'daily':[{'ad_id':'1','date':'2026-09-13','raw':raw(24,1,12)},
               {'ad_id':'2','date':'2026-09-13','raw':raw(75,0,0)}],
           'country_delivery':[{'ad_id':i,'country':'AU','spend':'1'} for i in ('1','2')]}
        ads=page.build_ads(h,'900')
        self.assertEqual([a['benchmark']['recommendation'] for a in ads],['TOP WINNER','STOP / REPLACE'])
        campaign=b.evaluate(b.graph_metrics(raw(99,1,4)),'INSTANT EXPERIENCE','AU')
        self.assertEqual(campaign['recommendation'],'KEEP RUNNING')
        self.assertNotEqual(campaign['score'],ads[1]['benchmark']['score'])

    def test_colour_and_neutral_ui_score_cells(self):
        m=metrics(75)
        item={'campaign_id':'1','metrics':m,'benchmark':b.evaluate(m,'INSTANT EXPERIENCE','AU')}
        frame=tables.styled(tables.campaign_rows([item]),[item])
        html=frame.to_html()
        self.assertIn('STOP / REPLACE',html); self.assertIn('#ae3434',html)
        self.assertIn('—',html)


if __name__=='__main__': unittest.main()
