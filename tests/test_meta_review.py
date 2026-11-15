import ast
import copy
from datetime import date
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page
import meta_ads_client as client
import meta_review_analysis as a
import meta_review_handoff as handoff
import meta_review_store as store
import meta_review_sync as sync

ROOT=Path(__file__).resolve().parents[1]
CREATIVE={'id':'c1','image_url':'https://example.fbcdn.net/winner.jpg',
          'object_story_spec':{'link_data':{'message':'Exact primary\n\nDo not rewrite.','name':'Exact headline',
             'description':'Original description','link':'https://sportscave.com.au/products/winner','call_to_action':{'type':'SHOP_NOW'}}}}


def raw(purchases=6,spend=120,value=600,**extra):
    return {'ad_id':'1','date_start':'2026-09-01','date_stop':'2026-09-01','spend':str(spend),'impressions':'1000',
        'clicks':'40','inline_link_clicks':'30','reach':'700','frequency':'1.4',
        'actions':[{'action_type':'omni_purchase','value':str(purchases)},
                   {'action_type':'offsite_conversion.fb_pixel_purchase','value':str(purchases)},
                   {'action_type':'add_to_cart','value':'12'},{'action_type':'initiate_checkout','value':'8'}],
        'action_values':[{'action_type':'omni_purchase','value':str(value)}],**extra}


def ad(identifier='1',r=None):
    metrics=a.normalize_metrics(r or raw())
    return {'ad_id':identifier,'ad_name':'Ad '+identifier,'assets':a.creative_assets(CREATIVE),'metrics':metrics,
            'decision':a.analyse(metrics,[metrics,a.normalize_metrics(raw(purchases=3,value=240))])}


def history():
    return {'accounts':[{'account_id':'123','name':'Fixture','currency':'AUD'}],
        'campaigns':[{'campaign_id':'cam','campaign_name':'Historic campaign','status':'PAUSED'}],
        'adsets':[{'adset_id':'set','adset_name':'Test set','raw':{'targeting':{'geo_locations':{'countries':['AU']}}}}],
        'ads':[{'ad_id':'1','ad_name':'Real original ad','campaign_id':'cam','adset_id':'set','creative_id':'c1','raw':{'creative':CREATIVE}},
               {'ad_id':'3','ad_name':'Comparison ad','campaign_id':'cam','adset_id':'set','creative_id':'c1','raw':{'creative':CREATIVE}}],
        'creatives':[{'creative_id':'c1','raw':CREATIVE}],
        'daily':[{'ad_id':'1','date':'2026-09-01','raw':raw()}, {'ad_id':'3','date':'2026-09-01','raw':raw(purchases=3,value=240,ad_id='3')}],
        'assets':[],'mapping':[],'logs':[],'selections':[],'observations':[]}


class MetricsTests(unittest.TestCase):
    def test_purchase_aliases_not_double_counted(self): self.assertEqual(a.normalize_metrics(raw())['purchases'],6)
    def test_add_to_cart(self): self.assertEqual(a.normalize_metrics(raw())['add_to_cart'],12)
    def test_checkout(self): self.assertEqual(a.normalize_metrics(raw())['checkout'],8)
    def test_purchase_value_and_roas(self):
        m=a.normalize_metrics(raw()); self.assertEqual((m['purchase_value'],m['roas'],m['cpa']),(600,5,20))
    def test_missing_is_not_zero(self):
        m=a.normalize_metrics({}); self.assertIsNone(m['purchases']); self.assertIsNone(m['roas']); self.assertEqual(page.fmt(m['spend']),'—')
    def test_missing_action_not_inferred_zero(self): self.assertIsNone(a.normalize_metrics({'actions':[]})['purchases'])
    def test_explicit_zero_retained(self): self.assertEqual(a.normalize_metrics(raw(purchases=0))['purchases'],0)
    def test_malformed_actions(self): self.assertIsNone(a.normalize_metrics({'actions':[None,{},'bad']})['purchases'])
    def test_nonfinite_rejected(self):
        for value in ('nan','inf',-1,None): self.assertIsNone(a.number(value))
    def test_reported_roas_fallback(self):
        self.assertEqual(a.normalize_metrics({'spend':'10','purchase_roas':[{'action_type':'omni_purchase','value':'4'}]})['roas'],4)
    def test_roas_is_weighted_not_average(self):
        result=a.aggregate([a.normalize_metrics(raw(spend=100,value=200)),a.normalize_metrics(raw(spend=300,value=300))])
        self.assertEqual(result['roas'],1.25)
    def test_unknown_period_poisoned_sum(self):
        self.assertIsNone(a.aggregate([a.normalize_metrics(raw()),a.normalize_metrics({})])['purchases'])
    def test_unique_reach_not_summed(self):
        result=a.aggregate([a.normalize_metrics(raw()),a.normalize_metrics(raw())]); self.assertIsNone(result['reach']); self.assertIsNone(result['frequency'])
    def test_link_clicks_not_all_clicks(self): self.assertEqual(a.normalize_metrics(raw())['ctr'],3)
    def test_ie_missing_and_present(self):
        self.assertIsNone(a.normalize_metrics(raw())['instant_experience_clicks_to_open'])
        self.assertEqual(a.normalize_metrics(raw(instant_experience_clicks_to_open='9'))['instant_experience_clicks_to_open'],9)


class CreativeTests(unittest.TestCase):
    def test_exact_body_headline_image(self):
        assets=a.creative_assets(CREATIVE)
        self.assertEqual(assets['primary_text'][0]['value'],'Exact primary\n\nDo not rewrite.')
        self.assertEqual(assets['headline'][0]['value'],'Exact headline')
        self.assertEqual(assets['image'][0]['value'],CREATIVE['image_url'])
    def test_dynamic_preserves_all_choices(self):
        assets=a.creative_assets({'asset_feed_spec':{'bodies':[{'text':'A'},{'text':'B'}],'titles':[{'text':'X'},{'text':'Y'}],'images':[{'hash':'h','url':'https://x.fbcdn.net/a'}]}})
        self.assertEqual([r['value'] for r in assets['primary_text']],['A','B']); self.assertTrue(assets['dynamic'])
    def test_carousel_and_video(self):
        assets=a.creative_assets({'object_story_spec':{'link_data':{'child_attachments':[{'picture':'https://x.fbcdn.net/1','name':'Card1'},{'picture':'https://x.fbcdn.net/2','name':'Card2'}]}}})
        self.assertTrue(assets['carousel']); self.assertEqual(len(assets['image']),2)
        self.assertEqual(a.creative_assets({'thumbnail_url':'https://x.fbcdn.net/thumb'})['image'][0]['value'],'https://x.fbcdn.net/thumb')
    def test_malformed_image_never_becomes_local_file_read(self):
        self.assertEqual(a.creative_assets({'image_url':'C:/private/image.png'})['image'],[])
    def test_malformed_creative(self): self.assertEqual(a.creative_assets('bad')['headline'],[])
    def test_direct_asset_source(self):
        rows=[{'ad_id':'1','breakdown':'body_asset','asset_key':'Exact primary\n\nDo not rewrite.','raw':raw()}]
        self.assertEqual(a.component_candidates([ad()],'primary_text',rows)[0]['source'],'DIRECT META ASSET RESULT')
    def test_inference_not_direct(self):
        for kind in ('image','primary_text','headline'):
            self.assertEqual(a.component_candidates([ad()],kind)[0]['source'],'INFERRED FROM WINNING ADS')


class DecisionTests(unittest.TestCase):
    def test_lone_low_roas_ad_is_not_a_winner_without_targets(self):
        metrics=a.normalize_metrics(raw(value=1))
        self.assertEqual(a.analyse(metrics,[metrics])['label'],'WATCH')
    def test_strong_winner_explained(self):
        result=ad()['decision']; self.assertEqual(result['label'],'WINNER — REFRESH THIS'); self.assertIn('reported purchases',result['reason'])
    def test_low_spend_one_purchase_not_winner(self):
        result=ad(r=raw(purchases=1,spend=5,value=5000))['decision']; self.assertEqual(result['label'],'NEEDS MORE SPEND'); self.assertEqual(result['confidence'],'Low')
    def test_no_metrics_no_winner(self):
        self.assertEqual(a.analyse({})['label'],'INSUFFICIENT DATA'); self.assertIsNone(a.choose_winner([]))
    def test_confidence_categories(self):
        for count,expected in ((1,'Low'),(5,'Medium'),(12,'High')):
            m=a.normalize_metrics(raw(purchases=count)); self.assertEqual(a.analyse(m,[m])['confidence'],expected)
    def test_kill_requires_configured_economics(self):
        m=a.normalize_metrics(raw(purchases=0,spend=400))
        self.assertEqual(a.analyse(m,rules=a.Rules(target_cpa=100))['label'],'KILL CANDIDATE')
        self.assertNotEqual(a.analyse(m)['label'],'KILL CANDIDATE')
    def test_landing_page_label(self):
        m={**a.normalize_metrics(raw()),'inline_link_clicks':80,'add_to_cart':0,'purchases':0}
        self.assertEqual(a.analyse(m)['label'],'LANDING PAGE / PRODUCT ISSUE')
    def test_fatigue_requires_history(self):
        before=a.normalize_metrics(raw()); after={**before,'ctr':1,'max_daily_frequency':4}
        self.assertEqual(a.analyse(after,[after],before)['label'],'REFRESH CREATIVE')
        self.assertNotEqual(a.analyse(after,[after])['label'],'REFRESH CREATIVE')
    def test_scale_is_read_only_economics_qualified(self):
        m=a.normalize_metrics(raw(purchases=12)); self.assertEqual(a.analyse(m,[m],rules=a.Rules(target_cpa=30,target_roas=3))['label'],'SCALE CANDIDATE')
    def test_repeat_purchase_winner_beats_tiny_roas_anomaly(self):
        real=ad('real'); tiny=ad('tiny',raw(purchases=1,spend=5,value=5000))
        self.assertEqual(a.choose_winner([tiny,real])['ad_id'],'real')


class HandoffTests(unittest.TestCase):
    def package(self,mode='complete_ad'):
        item=ad(); choices={kind:a.component_candidates([item],kind)[0] for kind in ('image','primary_text','headline')}
        return handoff.build_package(item,choices,{'account_id':'123','campaign_id':'cam','market':'AU','product_mapping':{'product_title':'Wall Art'}},mode)
    def test_complete_mode(self): self.assertEqual(self.package()['mode'],'complete_ad')
    def test_best_components_mode(self): self.assertEqual(self.package('best_components')['mode'],'best_components')
    def test_complete_mode_rejects_mixed_sources(self):
        item=ad(); choices={k:a.component_candidates([item],k)[0] for k in ('image','primary_text','headline')}; choices['headline']['ad_id']='other'
        with self.assertRaises(ValueError): handoff.build_package(item,choices,{},'complete_ad')
        self.assertEqual(handoff.build_package(item,choices,{},'best_components')['components']['headline']['ad_id'],'other')
    def test_hydration_exact_copy_and_manual_edits_survive(self):
        state={handoff.PENDING:self.package()}; self.assertTrue(handoff.hydrate(state))
        self.assertEqual(state['ads_creative_refresh_winning_primary_text'],'Exact primary\n\nDo not rewrite.')
        self.assertEqual(state['ads_country'],'Australia')
        state['ads_creative_refresh_winning_primary_text']='operator edit'; self.assertFalse(handoff.hydrate(state))
        self.assertEqual(state['ads_creative_refresh_winning_primary_text'],'operator edit')
    def test_queue_after_persistent_save_only(self):
        state={}
        with patch.object(handoff,'archive_image',return_value='sha'),patch.object(store,'save_selection',side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError): handoff.queue(self.package(),state)
        self.assertNotIn(handoff.PENDING,state)
    def test_archive_rejects_private_or_untrusted_urls(self):
        for url in ('http://127.0.0.1/image','https://evil.test/image','https://fbcdn.net.evil.test/image'):
            with self.assertRaises(ValueError),patch.object(handoff.requests,'get') as get: handoff.archive_image(url)
            get.assert_not_called()


class SyncTests(unittest.TestCase):
    def test_write_batch_bounds_and_deduplicates(self):
        cur=MagicMock(); batch=store.WriteBatch(cur)
        for index in range(201):
            store._upsert(batch,'meta_campaigns',{'campaign_id':str(index),'campaign_name':'Test'},('campaign_id',))
        store._upsert(batch,'meta_campaigns',{'campaign_id':'0','campaign_name':'Newest'},('campaign_id',))
        batch.flush()
        self.assertEqual(cur.execute.call_count,3)
        self.assertEqual(cur.execute.call_args_list[0].args[1][:2],['0','Newest'])
    def test_write_deadline_fails_before_any_write(self):
        cur=MagicMock(); batch=store.WriteBatch(cur,seconds=-1)
        store._upsert(batch,'meta_campaigns',{'campaign_id':'1','campaign_name':'Test'},('campaign_id',))
        with self.assertRaises(ValueError): batch.flush()
        cur.execute.assert_not_called()
    config={'configured':True,'ad_account_id':'act_123','api_version':'v26.0','access_token':'secret'}
    def reader(self,fail=False):
        reader=MagicMock(); reader.get.return_value={'account_id':'123'}
        def pages(path,params):
            if path.endswith('/campaigns'): return [{'id':'cam','name':'Campaign'}]
            if path.endswith('/adsets'): return [{'id':'set','campaign_id':'cam'}]
            if path.endswith('/ads'): return [{'id':'1','campaign_id':'cam','adset_id':'set','creative':CREATIVE}]
            if fail: raise client.MetaAdsApiError('Token expired',error_code=190)
            if params.get('breakdowns'): raise client.MetaAdsApiError('Unsupported breakdown',error_code=100)
            return [raw()]
        reader.pages.side_effect=pages; return reader
    def test_failed_sync_keeps_previous_history(self):
        with patch.object(client,'get_meta_config',return_value=self.config),patch.object(store,'log_start',return_value=1),patch.object(store,'save_sync') as save,patch.object(store,'log_failure') as failure:
            with self.assertRaises(RuntimeError): sync.sync(date(2026,9,1),date(2026,9,2),reader=self.reader(True))
            save.assert_not_called(); failure.assert_called_once()
    def test_unsupported_assets_fall_back(self):
        with patch.object(client,'get_meta_config',return_value=self.config),patch.object(store,'log_start',return_value=1),patch.object(store,'save_sync',return_value={'daily':1}) as save:
            result=sync.sync(date(2026,9,1),date(2026,9,2),reader=self.reader())
        self.assertEqual(len(result['warnings']),6); self.assertEqual(save.call_args.args[0]['assets'],[])
    def test_pagination_uses_cursors_not_next_url(self):
        reader=sync.Reader(self.config)
        with patch.object(client,'_request',side_effect=[{'data':[1],'paging':{'next':'https://evil.test/?access_token=secret','cursors':{'after':'a'}}},{'data':[2]}]) as request:
            self.assertEqual(reader.pages('act_123/ads',{}),[1,2]); self.assertEqual(request.call_args.kwargs['params']['after'],'a')
    def test_page_limit_is_failure_not_truncation(self):
        reader=sync.Reader(self.config,max_pages=1)
        with patch.object(client,'_request',return_value={'data':[1],'paging':{'next':'url','cursors':{'after':'a'}}}):
            with self.assertRaises(ValueError): reader.pages('ads',{})
    def test_timeout_is_finite(self):
        reader=sync.Reader(self.config,seconds=-1)
        with patch.object(client,'_request') as request,self.assertRaises(TimeoutError): reader.get('ads',{})
        request.assert_not_called()
    def test_auth_error_not_swallowed_as_optional(self): self.assertFalse(sync.optional_error(client.MetaAdsApiError('expired',error_code=190)))
    def test_safe_errors_no_credentials(self):
        self.assertNotIn('password',sync.safe_error(RuntimeError('password=1234')))
    def test_no_write_transport_in_review(self):
        for module in (page,sync,handoff):
            source=inspect.getsource(module); self.assertNotIn('._post(',source); self.assertNotIn('MetaPostingService',source)
    def test_store_failure_rolls_back(self):
        connection=MagicMock(); conn=connection.__enter__.return_value; conn.cursor.return_value.__enter__.return_value.execute.side_effect=RuntimeError('db failure')
        with patch.object(store.backend,'connect',return_value=connection):
            with self.assertRaises(RuntimeError): store.save_sync({'account_id':'123','account':{}},1)
        conn.commit.assert_not_called()


class PageTests(unittest.TestCase):
    def test_insights_survive_unavailable_objects(self):
        data=history(); data['ads']=[]; data['campaigns']=[]
        data['daily'][0].update(campaign_id='cam',campaign_name='Old campaign',ad_name='Deleted ad')
        restored=page.include_unavailable_objects(data)
        self.assertEqual(restored['campaigns'][0]['campaign_name'],'Old campaign')
        self.assertEqual(page.build_ads(restored,'cam')[0]['metrics']['purchases'],6)

    def test_manual_winner_override_persists_and_no_meta_mutation(self):
        def app():
            import ads_meta_review_page
            from tests.test_meta_review import history
            data=history()
            data['ads'].append({**data['ads'][0],'ad_id':'2','ad_name':'Chosen by Nathan'})
            ads_meta_review_page.winner_board(ads_meta_review_page.build_ads(data),data,{'account_id':'123'})
        data=history(); data['ads'].append({**data['ads'][0],'ad_id':'2','ad_name':'Chosen by Nathan'})
        with patch.object(client,'get_meta_config',return_value=SyncTests.config),patch.object(store,'save_selection',return_value=10) as save,patch.object(client,'_post') as post:
            at=AppTest.from_function(app,default_timeout=10).run()
            next(s for s in at.selectbox if s.label=='Overall winning ad').set_value('2').run()
            next(b for b in at.button if b.label=='Save winner selection').click().run()
            self.assertFalse(at.exception)
        self.assertEqual(save.call_args.args[0]['overall'],'2'); post.assert_not_called()

    def test_click_handoff_navigates_after_saved_reference(self):
        def app():
            import ads_meta_review_page
            from tests.test_meta_review import history
            data=history()
            data['ads'].append({**data['ads'][0],'ad_id':'2','ad_name':'Chosen by Nathan'})
            ads_meta_review_page.winner_board(ads_meta_review_page.build_ads(data),data,{'account_id':'123'})
        with patch.object(client,'get_meta_config',return_value=SyncTests.config),patch.object(handoff,'queue') as queue:
            at=AppTest.from_function(app,default_timeout=10).run()
            next(b for b in at.button if b.label=='Refresh Winning Ad').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['current_page'],'Creative Refresh')
        self.assertEqual(queue.call_args.args[0]['mode'],'complete_ad')

    def test_historical_ads_render_without_meta(self):
        with patch.object(client,'_request',side_effect=AssertionError('network')):
            rows=page.build_ads(history(),'cam'); self.assertEqual(rows[0]['assets']['headline'][0]['value'],'Exact headline')
    def test_country_filter_is_targeting(self):
        self.assertEqual(len(page.build_ads(history(),'cam','AU')),2); self.assertEqual(page.build_ads(history(),'cam','US'),[])
    def test_open_ui_loads_overview_without_ads_or_storage(self):
        def app():
            import ads_meta_review_page
            ads_meta_review_page.render_page()
        with patch.object(page.live,'load_overview',return_value={'account':{},'campaigns':[]}),patch.object(client,'get_meta_config',return_value=SyncTests.config),patch.object(store,'load_history',side_effect=AssertionError('DB read')),patch.object(client,'_request',side_effect=AssertionError('Meta call')) as request:
            at=AppTest.from_function(app,default_timeout=10).run()
        self.assertFalse(at.exception)
        request.assert_not_called()
        self.assertTrue(any(b.label=='Refresh From Meta' for b in at.button))
        self.assertFalse(any(b.label=='Refresh Winning Ad' for b in at.button))


if __name__=='__main__': unittest.main()
