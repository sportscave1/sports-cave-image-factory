"""Supplemental country reads must never replace or block primary metrics."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import meta_ads_client as meta
import meta_review_live as live
import meta_review_benchmarks as benchmarks
import ads_meta_review_page as page
from tests.test_meta_review_live import CONFIG, SINCE, UNTIL


class CountryReadTests(unittest.TestCase):
    def response(self, path, params, config):
        if path=='act_123': return {'account_id':'123','currency':'AUD'}
        if path.endswith('/campaigns'): return {'data':[{'id':'900','name':'Campaign'}]}
        if path.endswith('/ads'):
            return {'data':[{'id':'1','creative':{'id':'c','object_story_spec':{'link_data':{'link':'https://facebook.com/canvas/1'}}}}]}
        if path.endswith('/adsets'): return {'data':[]}
        self.assertTrue(path.endswith('/insights'))
        self.assertNotIn('country',params['fields'].split(','))
        self.assertEqual(params['use_unified_attribution_setting'],'true')
        identity='campaign_id' if params['level']=='campaign' else 'ad_id'
        value='900' if params['level']=='campaign' else '1'
        if params.get('breakdowns'):
            self.assertEqual(params['breakdowns'],'country')
            self.assertEqual(params['fields'],identity+',spend')
            return {'data':[{identity:value,'country':'US','spend':'20'},
                            {identity:value,'country':'CA','spend':'5'},
                            {identity:'unrelated','country':'AU','spend':'100'}]}
        return {'data':[{identity:value,'spend':'25','impressions':'100',
                        'actions':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'1'}]}]}

    def test_campaign_and_ad_requests_join_only_context_without_double_count(self):
        with patch.object(meta,'_request',side_effect=self.response),patch.object(meta,'_post') as write:
            overview=live.load_overview(CONFIG,SINCE,UNTIL)
            history=live.load_campaign(CONFIG,'900',SINCE,UNTIL)
        campaign=overview['campaigns'][0]
        self.assertEqual(campaign['benchmark']['country'],'MIXED')
        self.assertEqual(campaign['metrics']['spend'],25)
        self.assertEqual(campaign['metrics']['purchases'],1)
        ads=page.build_ads(history,'900')
        self.assertEqual(ads[0]['benchmark']['country'],'MIXED')
        self.assertEqual(ads[0]['benchmark_metrics']['spend'],25)
        self.assertEqual(ads[0]['benchmark_metrics']['purchases'],1)
        write.assert_not_called()

    def test_single_country_and_empty_resolution(self):
        for rows,expected in [([{'country':'AU','spend':'25'}],'AU'),
                              ([{'country':'US','spend':'25'},{'country':'GB','spend':0}],'US'),([], 'UNKNOWN')]:
            self.assertEqual(benchmarks.market(rows),expected)

    def test_unsupported_country_keeps_both_primary_loaders_available(self):
        def response(path,params,config):
            if params.get('breakdowns'):
                raise meta.MetaAdsApiError('Requested country breakdown combination is not supported',error_code=100,status_code=400)
            return self.response(path,params,config)
        with patch.object(meta,'_request',side_effect=response),self.assertLogs(live.LOGGER,level='WARNING'):
            overview=live.load_overview(CONFIG,SINCE,UNTIL)
            history=live.load_campaign(CONFIG,'900',SINCE,UNTIL)
        self.assertEqual(overview['campaigns'][0]['metrics']['spend'],25)
        self.assertEqual(overview['campaigns'][0]['benchmark']['country'],'UNKNOWN')
        self.assertEqual(history['country_delivery'],[])
        ads=page.build_ads(history,'900')
        self.assertEqual(ads[0]['benchmark']['country'],'UNKNOWN')
        self.assertNotIn('cpc',ads[0]['benchmark']['cells'])

    def test_primary_failure_and_supplemental_auth_permission_errors_surface(self):
        for code,message in [(190,'Invalid access token'),(200,'Permissions error'),
                              (100,'Invalid country permission'),(100,'Other invalid parameter'),(2,'Service unavailable')]:
            with self.subTest(code=code,message=message),patch.object(meta,'_request',side_effect=meta.MetaAdsApiError(message,error_code=code)):
                with self.assertRaises(meta.MetaAdsApiError): live.load_countries(CONFIG,'900','ad',SINCE,UNTIL)
        def response(path,params,config):
            if path.endswith('/insights') and not params.get('breakdowns'):
                raise meta.MetaAdsApiError('Invalid country breakdown combination',error_code=100)
            return self.response(path,params,config)
        with patch.object(meta,'_request',side_effect=response):
            for loader in (lambda:live.load_overview(CONFIG,SINCE,UNTIL),lambda:live.load_campaign(CONFIG,'900',SINCE,UNTIL)):
                with self.assertRaises(meta.MetaAdsApiError): loader()

    def test_partial_country_pages_discarded_on_compatibility_error(self):
        with patch.object(meta,'_request',side_effect=[
            {'data':[{'ad_id':'1','country':'AU','spend':'20'}],
             'paging':{'next':'yes','cursors':{'after':'next-page'}}},
            meta.MetaAdsApiError('Unsupported country breakdown combination',error_code=100)]),self.assertLogs(live.LOGGER,level='WARNING'):
            self.assertEqual(live.load_countries(CONFIG,'900','ad',SINCE,UNTIL),[])

    def test_page_remains_live_when_only_country_is_unsupported(self):
        def response(path,params,config):
            if params.get('breakdowns'):
                raise meta.MetaAdsApiError('country is not valid for this breakdown combination',error_code=100)
            return self.response(path,params,config)
        with patch.object(meta,'get_meta_config',return_value=CONFIG),patch.object(meta,'_request',side_effect=response),self.assertLogs(live.LOGGER,level='WARNING'):
            app=AppTest.from_string('import ads_meta_review_page as p\np.render_page()',default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertNotIn('Market',app.dataframe[0].value.columns)
        self.assertEqual(app.dataframe[0].value.iloc[0]['Spend'],25)

    def test_country_pages_preserve_date_attribution_and_fields(self):
        seen=[]
        def response(path,params,config):
            seen.append(dict(params))
            if params.get('after'): return {'data':[{'campaign_id':'900','country':'US','spend':'5'}]}
            return {'data':[{'campaign_id':'900','country':'AU','spend':'20'}],
                    'paging':{'next':'unused','cursors':{'after':'page2'}}}
        with patch.object(meta,'_request',side_effect=response):
            rows=live.load_countries(CONFIG,'act_123','campaign',SINCE,UNTIL)
        self.assertEqual(benchmarks.market(rows),'MIXED')
        self.assertEqual(len(seen),2)
        for params in seen:
            self.assertEqual(params['fields'],'campaign_id,spend')
            self.assertEqual(params['breakdowns'],'country')
            self.assertEqual(params['time_range'],live.date_params(SINCE,UNTIL)['time_range'])
            self.assertEqual(params['use_unified_attribution_setting'],'true')


if __name__=='__main__': unittest.main()
