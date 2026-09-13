import copy
from contextlib import ExitStack
from datetime import date
import importlib
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page
import meta_ads_client as meta
import meta_review_live as live
import meta_review_analysis as analysis
import meta_review_store as store
import meta_review_handoff as handoff
from tests.test_meta_review import CREATIVE, history

CONFIG = {'configured': True, 'ad_account_id': 'act_123', 'api_version': 'v26.0', 'access_token': 'fixture-token'}
SINCE, UNTIL = date(2026,9,7), date(2026,9,13)
CAMPAIGN = {'id':'900','name':'September campaign','status':'ACTIVE','effective_status':'ACTIVE','created_time':'2026-09-12'}


class LiveReadTests(unittest.TestCase):
    def test_all_and_completed_request_only_reportable_statuses(self):
        for status in ('All', 'COMPLETED', 'ACTIVE', 'PAUSED', 'ARCHIVED', 'Active and paused'):
            with self.subTest(status=status), patch.object(meta, '_request', side_effect=[
                {'account_id':'123'}, {'data':[]}]) as request:
                live.load_campaigns(CONFIG, None, UNTIL, status=status)
                params=request.call_args.kwargs['params']
                expected=(['ACTIVE','PAUSED','ARCHIVED'] if status in ('All','COMPLETED') else
                          ['ACTIVE','PAUSED'] if status=='Active and paused' else [status])
                self.assertEqual(json.loads(params['effective_status']),expected)
                self.assertNotIn('DELETED',json.dumps(params))

    def test_unsupported_status_never_reaches_meta(self):
        for status in ('DELETED','deleted','UNKNOWN'):
            with self.subTest(status=status), patch.object(meta,'_request') as request:
                with self.assertRaisesRegex(ValueError,'Unsupported live campaign status'):
                    live.load_campaigns(CONFIG,None,UNTIL,status=status)
                request.assert_not_called()

    def test_deleted_rows_excluded_across_pages_without_losing_supported_rows(self):
        rows=[{**CAMPAIGN,'id':str(i),'status':status,'effective_status':status}
              for i,status in enumerate(('ACTIVE','PAUSED','ARCHIVED','DELETED'))]
        responses=[{'account_id':'123'},
            {'data':rows[:2], 'paging':{'next':'yes','cursors':{'after':'second'}}},
            {'data':rows[2:]+[{**CAMPAIGN,'id':'5','configured_status':'DELETED'}]}]
        with patch.object(meta,'_request',side_effect=responses) as request:
            result=live.load_campaigns(CONFIG,None,UNTIL,status='All')
        self.assertEqual({r['status'] for r in result['campaigns']},{'ACTIVE','PAUSED','ARCHIVED'})
        for call in request.call_args_list:
            self.assertNotIn('DELETED',json.dumps(call.kwargs['params']))
        self.assertEqual(live.filter_campaigns(rows,status='All'),rows[:3])

    def test_api_errors_are_not_hidden_as_successful_partial_pages(self):
        for message in ('OAuthException code 190','Permissions error code 200',
                        'Cannot request deleted objects code 100 subcode 1815001'):
            with self.subTest(message=message), patch.object(meta,'_request',side_effect=[
                {'data':[CAMPAIGN],'paging':{'next':'yes','cursors':{'after':'second'}}},
                meta.MetaAdsApiError(message)]):
                # An errored page has no safe next cursor: never claim partial data is complete.
                with self.assertRaises(meta.MetaAdsApiError):
                    live.Reader(CONFIG).pages('act_123/campaigns',{})

    def test_campaign_normalization_pagination_and_date_status_params(self):
        responses = [{'account_id':'123','name':'Sports Cave','currency':'AUD'},
            {'data':[CAMPAIGN], 'paging':{'next':'https://untrusted.example/?access_token=never-follow','cursors':{'after':'cursor2'}}},
            {'data':[{**CAMPAIGN,'id':'901','status':'PAUSED','effective_status':'PAUSED'}]}]
        with patch.object(meta,'_request',side_effect=responses) as request:
            result=live.load_campaigns(CONFIG,SINCE,UNTIL)
        self.assertEqual([r['campaign_id'] for r in result['campaigns']],['901','900'])
        self.assertEqual(result['campaigns'][1]['campaign_name'],'September campaign')
        self.assertEqual(request.call_args_list[2].args[0],'act_123/campaigns')
        params=request.call_args_list[2].kwargs['params']
        self.assertEqual(params['after'],'cursor2')
        self.assertEqual(json.loads(params['effective_status']),['ACTIVE','PAUSED'])
        self.assertEqual(json.loads(params['time_range']),{'since':str(SINCE),'until':str(UNTIL)})
        self.assertIn('stop_time',params['fields'])

    def test_wrong_account_rejected(self):
        with patch.object(meta,'_request',return_value={'account_id':'other'}):
            with self.assertRaisesRegex(ValueError,'different ad account'): live.load_campaigns(CONFIG,SINCE,UNTIL)

    def test_campaign_search_and_effective_status(self):
        rows=[{'campaign_name':'Current September','effective_status':'ACTIVE'},
              {'campaign_name':'Current paused','effective_status':'PAUSED','status':'ACTIVE'},
              {'campaign_name':'Archived','effective_status':'ARCHIVED'}]
        self.assertEqual(len(live.filter_campaigns(rows,status='Active and paused')),2)
        self.assertEqual(live.filter_campaigns(rows,'SEPT','ACTIVE'),rows[:1])
        self.assertEqual(live.filter_campaigns(rows,status='PAUSED'),rows[1:2])

    def test_page_limit_is_failure_not_silent_partial_list(self):
        with patch.object(meta,'_request',return_value={'data':[CAMPAIGN],'paging':{'next':'yes','cursors':{'after':'a'}}}):
            with self.assertRaisesRegex(ValueError,'page limit'): live.Reader(CONFIG,max_pages=1).pages('123/campaigns',{})

    def test_repeated_cursor_rejected(self):
        with patch.object(meta,'_request',return_value={'data':[],'paging':{'next':'yes','cursors':{'after':'a'}}}):
            with self.assertRaisesRegex(ValueError,'pagination'): live.Reader(CONFIG).pages('123/campaigns',{})

    def test_malformed_page_rejected(self):
        with patch.object(meta,'_request',return_value={'data':[None]}):
            with self.assertRaises(ValueError): live.Reader(CONFIG).pages('123/campaigns',{})

    def test_selected_campaign_only_ads_adsets_and_range_insights(self):
        creative=copy.deepcopy(CREATIVE)
        creative['object_story_spec']['link_data']['link']='https://www.facebook.com/canvas/123'
        def response(path,params,config):
            if params.get('breakdowns')=='country': return {'data':[{'ad_id':'1','country':'US','spend':'6.49'}]}
            if path=='900/ads': return {'data':[{'id':'1','name':'IA 1','adset_id':'77','creative':creative}]}
            if path=='900/adsets': return {'data':[{'id':'77','name':'USA set','targeting':{'geo_locations':{'countries':['US']}}}]}
            if path=='900/insights': return {'data':[{'ad_id':'1','spend':'6.49','impressions':'1059','clicks':'42','inline_link_clicks':'22','reach':'900','frequency':'1.176667'}]}
            raise AssertionError(path)
        with patch.object(meta,'_request',side_effect=response) as request,patch.object(meta,'_post') as post:
            result=live.load_campaign(CONFIG,'900',SINCE,UNTIL)
        self.assertEqual(request.call_count,4); post.assert_not_called()
        params=request.call_args_list[2].kwargs['params']
        self.assertEqual(params['use_unified_attribution_setting'],'true')
        self.assertEqual(params['level'],'ad'); self.assertNotIn('time_increment',params)
        self.assertIn('website_purchase_roas',params['fields'])
        ads=page.build_ads(result,'900')
        self.assertEqual(ads[0]['ad_name'],'IA 1'); self.assertEqual(ads[0]['markets'],['US'])
        self.assertEqual(ads[0]['metrics']['reach'],900)
        self.assertEqual(ads[0]['assets']['url'][0]['value'],'https://www.facebook.com/canvas/123')
        self.assertEqual(ads[0]['assets']['cta'][0]['value'],'SHOP_NOW')

    def test_range_and_identity_validation(self):
        with self.assertRaises(ValueError): live.date_params(UNTIL,SINCE)
        self.assertEqual(live.date_params(None,UNTIL),{'date_preset':'maximum'})
        with patch.object(meta,'_request') as request:
            with self.assertRaises(ValueError): live.load_campaign(CONFIG,'../ads',SINCE,UNTIL)
        request.assert_not_called()

    def test_conflicting_range_reports_fail_instead_of_double_counting(self):
        responses=[{'data':[]},{'data':[]},{'data':[{'ad_id':'1','spend':'2'},{'ad_id':'1','spend':'3'}]}]
        with patch.object(meta,'_request',side_effect=responses):
            with self.assertRaisesRegex(ValueError,'conflicting range reports'):
                live.load_campaign(CONFIG,'900',SINCE,UNTIL)

    def test_import_never_calls_meta(self):
        with patch.object(meta,'_request') as request:
            importlib.reload(live)
        request.assert_not_called()


class NormalizationTests(unittest.TestCase):
    def test_malformed_creative_lists_are_safe(self):
        result=analysis.creative_assets({'asset_feed_spec':{'images':7,'bodies':False,'videos':True,'link_urls':9},
            'object_story_spec':{'link_data':{'child_attachments':12}}})
        self.assertEqual(result['image'],[])

    def test_ecommerce_alias_precedence_not_sum(self):
        for metric, canonical, aliases in (
            ('add_to_cart','add_to_cart',['offsite_conversion.fb_pixel_add_to_cart','onsite_web_add_to_cart','omni_add_to_cart']),
            ('checkout','initiate_checkout',['offsite_conversion.fb_pixel_initiate_checkout','onsite_web_initiate_checkout','omni_initiated_checkout']),
            ('purchases','purchase',['offsite_conversion.fb_pixel_purchase','onsite_web_purchase','omni_purchase'])):
            row={'actions':[{'action_type':canonical,'value':'2'}]+[{'action_type':a,'value':'8'} for a in aliases]}
            self.assertEqual(analysis.normalize_metrics(row)[metric],2)
            self.assertEqual(analysis.normalize_metrics({'actions':[{'action_type':aliases[1],'value':'2'}]})[metric],2)

    def test_missing_and_explicit_zero_roas(self):
        self.assertIsNone(analysis.normalize_metrics({'spend':'6.49','actions':[]})['roas'])
        self.assertEqual(analysis.normalize_metrics({'website_purchase_roas':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'0'}]})['roas'],0)

    def test_exact_reported_rates_survive_one_range_aggregation(self):
        m=analysis.normalize_metrics({'spend':'6.49','ctr':'3.966006','cpc':'0.154524','inline_link_click_ctr':'2.077432','cost_per_inline_link_click':'0.295'})
        m=analysis.aggregate([m])
        self.assertEqual(m['ctr'],2.077432); self.assertEqual(m['click_ctr'],3.966006)
        self.assertEqual(m['cpc'],.154524); self.assertEqual(m['cost_per_link_click'],.295)

    def test_instant_experience_and_asset_feed_fallback(self):
        raw=copy.deepcopy(CREATIVE)
        raw['object_story_spec']['link_data'].update(link='https://www.facebook.com/canvas/123',image_hash='exact-hash')
        assets=analysis.creative_assets(raw)
        self.assertEqual(assets['primary_text'][0]['value'],'Exact primary\n\nDo not rewrite.')
        self.assertEqual(assets['headline'][0]['value'],'Exact headline')
        self.assertEqual(assets['cta'][0]['value'],'SHOP_NOW')
        self.assertEqual(assets['image'][0]['value'],raw['image_url'])
        self.assertEqual(assets['image'][0]['id'],'exact-hash')
        self.assertEqual(assets['url'][0]['value'],'https://www.facebook.com/canvas/123')
        feed=analysis.creative_assets({'asset_feed_spec':{'bodies':[{'text':'Body'}],'titles':[{'text':'Title'}],
            'images':[{'url':'https://a.fbcdn.net/image','hash':'hash'}],'call_to_action_types':['SHOP_NOW'],'link_urls':[{'website_url':'https://example.com'}]}})
        self.assertEqual(feed['headline'][0]['value'],'Title'); self.assertEqual(feed['cta'][0]['value'],'SHOP_NOW')
        self.assertEqual(feed['url'][0]['value'],'https://example.com'); self.assertTrue(feed['dynamic'])

    def test_ia_live_comparison_separates_clicks_and_intent(self):
        rows=[]
        for i,spend,ctr,cpc,links,outbound in [('1','6.49','2.077432','0.295','22','17'),('2','3.53','3.333333','0.207647','17','10'),('3','6.01','3.717026','0.193871','31','22')]:
            row={'spend':spend,'inline_link_click_ctr':ctr,'cost_per_inline_link_click':cpc,'inline_link_clicks':links,
                 'outbound_clicks':[{'action_type':'outbound_click','value':outbound}]}
            if i=='1': row['actions']=[{'action_type':'add_to_cart','value':'2'},{'action_type':'initiate_checkout','value':'1'}]
            m=analysis.normalize_metrics(row)
            rows.append({'ad_id':i,'metrics':m,'decision':analysis.analyse(m)})
        leaders=analysis.signal_leaders(rows)
        self.assertEqual(leaders['commercial']['ad_id'],'1')
        self.assertEqual(leaders['click']['ad_id'],'3')
        self.assertIsNone(analysis.choose_winner(rows))
        self.assertEqual(rows[0]['decision']['label'],'NEEDS MORE SPEND')
        self.assertTrue(all(r['decision']['confidence']=='Low' for r in rows))


class CacheTests(unittest.TestCase):
    def test_ttl_isolation_refresh_and_copy(self):
        cache={}; key=(live.scope(CONFIG),'campaigns')
        with patch.object(meta,'_request',return_value={'data':[]}) as request:
            load=lambda: meta._request('123/campaigns')
            first=live.cached_read(cache,key,load,clock=lambda:10)
            first['data']['bad']='not saved'
            self.assertNotIn('bad',live.cached_read(cache,key,load,clock=lambda:11)['data'])
            self.assertEqual(request.call_count,1)
            live.cached_read(cache,key,load,clock=lambda:131); self.assertEqual(request.call_count,2)
            live.invalidate(cache,key[0]); live.cached_read(cache,key,load,clock=lambda:132)
            self.assertEqual(request.call_count,3)
        self.assertNotEqual(live.scope(CONFIG),live.scope({**CONFIG,'access_token':'rotated'}))

    def test_failed_refresh_labels_only_same_key_stale_and_throttles_retry(self):
        cache={}; key=(live.scope(CONFIG),'campaigns',SINCE,UNTIL)
        live.cached_read(cache,key,lambda:['live'],clock=lambda:1)
        live.invalidate(cache,key[0])
        def fail(): raise RuntimeError('private connection secret')
        result=live.cached_read(cache,key,fail,clock=lambda:2)
        self.assertTrue(result['stale']); self.assertEqual(result['data'],['live'])
        self.assertNotIn('secret',result['error'])
        self.assertIsNone(live.cached_read(cache,(*key,'different-date'),fail,clock=lambda:2)['data'])
        self.assertEqual(live.cached_read(cache,key,lambda: self.fail('retry storm'),clock=lambda:3),result)

    def test_refresh_scope_does_not_clear_other_account(self):
        cache={('one','campaigns'):{'expires':10},('two','campaigns'):{'expires':10}}
        live.invalidate(cache,'one')
        self.assertEqual(cache[('two','campaigns')]['expires'],10)


class LivePageTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(meta,'get_meta_config',return_value=CONFIG))
        self.old=self.stack.enter_context(patch.object(store,'load_history',side_effect=AssertionError('Historical reporting must not load')))
        self.network=self.stack.enter_context(patch.object(meta,'_request',side_effect=AssertionError('Unexpected network')))
        data=history()
        for ad in data['ads']: ad['campaign_id']='900'
        self.campaign={'campaign_id':'900','campaign_name':'September live campaign','effective_status':'ACTIVE','metrics':analysis.normalize_metrics({})}
        self.overview=self.stack.enter_context(patch.object(live,'load_overview',return_value={'account':{'name':'Sports Cave'},'campaigns':[self.campaign]}))
        self.ads=self.stack.enter_context(patch.object(live,'load_campaign',return_value=data))
        self.preferences=self.stack.enter_context(patch.object(page,'_load_preferences',return_value={'selections':[],'mapping':[]}))
        self.recency=self.stack.enter_context(patch.object(page.recency,'load',return_value={'available':False,'latest':{}}))
        self.at=AppTest.from_string('import ads_meta_review_page as p\np.render_page()',default_timeout=10).run()

    def refresh(self):
        next(b for b in self.at.button if b.label=='Refresh From Meta').click().run()

    def details(self):
        self.at=AppTest.from_string("import ads_meta_review_page as p\nfrom tests.test_meta_review_live import CONFIG\np.render_campaign_details(CONFIG,{'campaign_id':'900','campaign_name':'September live campaign'},None,__import__('datetime').date(2026,9,13))",default_timeout=10).run()

    def test_initial_overview_has_only_sort_and_refresh_and_no_ads(self):
        self.assertEqual(self.overview.call_count,1); self.ads.assert_not_called(); self.preferences.assert_not_called()
        self.assertEqual([s.label for s in self.at.selectbox],['Sort By'])
        self.at.run(); self.assertEqual(self.overview.call_count,1)
        self.refresh(); self.assertEqual(self.overview.call_count,2)
        self.old.assert_not_called(); self.network.assert_not_called(); self.assertFalse(self.at.exception)

    def test_expanded_sort_choices_do_not_reload_graph_or_expand_table(self):
        import meta_review_tables as tables
        selector=self.at.selectbox[0]
        self.assertEqual(selector.options,tables.SORT_OPTIONS)
        self.assertEqual(selector.value,'Newest')
        calls=self.recency.call_count
        for option in tables.SORT_OPTIONS:
            self.at.selectbox[0].select(option).run()
            self.assertFalse(self.at.exception)
        self.assertEqual(list(self.at.dataframe[0].value.columns),['Campaign','Status','Spend','Sales','ROAS','CPA','CTR','CPC','ATC','Checkout','Last Sale','Action'])
        self.assertEqual(self.overview.call_count,1)
        self.assertEqual(self.recency.call_count,calls)
        self.ads.assert_not_called(); self.network.assert_not_called()

    def test_campaign_row_opens_popup_for_correct_identity(self):
        since,until=self.at.date_input[0].value
        key=f'meta-review-campaign-table-Newest-{since}-{until}-1'
        self.at.session_state[key]={'selection':{'rows':[0],'columns':[]}}
        with patch.object(page,'campaign_popup') as popup:
            self.at.run()
        self.assertFalse(self.at.exception)
        self.assertEqual(popup.call_args.args[1]['campaign_id'],'900')
        self.ads.assert_not_called()

    def test_selected_campaign_loads_lazily_and_reruns_use_cache(self):
        self.ads.assert_not_called(); self.details(); self.assertEqual(self.ads.call_count,1)
        self.at.run(); self.assertEqual(self.ads.call_count,1)
        self.assertFalse(self.at.exception)

    def test_storage_outage_does_not_block_live_view(self):
        self.preferences.side_effect=RuntimeError('storage down')
        self.details()
        self.assertFalse(self.at.exception); self.assertFalse(self.at.error)
        self.assertTrue(any('Live Meta review remains available' in w.value for w in self.at.warning))
        self.assertTrue(self.at.dataframe)

    def test_preferences_cannot_replace_graph_performance_or_scores(self):
        self.preferences.return_value={'selections':[],'mapping':[],
            'daily':[{'ad_id':'evil','raw':{'spend':'999999'}}], 'ads':[], 'country_delivery':[]}
        self.details()
        self.assertFalse(self.at.exception)
        frames=[d.value for d in self.at.dataframe if 'Ad' in d.value.columns]
        self.assertTrue(frames)
        self.assertEqual(len(frames[0]),len(self.ads.return_value['ads']))
        self.assertNotIn(999999,frames[0]['Sales'].tolist())

    def test_failure_without_cache_never_shows_historical_campaigns(self):
        self.at.session_state['meta-review-live-cache']={}
        self.overview.side_effect=meta.MetaAdsApiError('Permission denied'); self.at.run()
        self.assertTrue(any('LIVE META UNAVAILABLE' in e.value for e in self.at.error))
        self.assertFalse(self.at.dataframe); self.old.assert_not_called()

    def test_failed_refresh_labels_prior_live_campaigns_stale(self):
        self.overview.side_effect=meta.MetaAdsApiError('Unavailable'); self.refresh()
        self.assertTrue(any('STALE CACHED META' in c.value for c in self.at.markdown))
        self.assertTrue(self.at.dataframe); self.old.assert_not_called()

    def test_full_details_expand_on_creative_row(self):
        self.details()
        self.at.session_state['meta-review-creative-table-900']={'selection':{'rows':[0],'columns':[]}}
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertTrue(any('View details' in e.label for e in self.at.expander))
        self.assertTrue(any('Exact primary' in t.value for t in self.at.text))
        self.assertTrue(any(t.value=='SHOP_NOW' for t in self.at.text))

    def test_live_winner_handoff_uses_existing_queue(self):
        self.details()
        with patch.object(handoff,'queue') as queue:
            next(b for b in self.at.button if b.label=='Refresh Winning Ad').click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(queue.call_args.args[0]['mode'],'complete_ad')
        self.assertEqual(self.at.session_state['current_page'],'Creative Refresh')


if __name__=='__main__': unittest.main()
