"""Exercise the actual Meta Review resolver/detail/handoff, with GET mocks only."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import meta_review_creative as creative
import meta_review_live as live
import meta_review_handoff as handoff
from tests.test_meta_review_creative import inline,CONFIG,package


def dynamic_feed(n=5):
    return {'id':'1234','thumbnail_url':'https://fixture.fbcdn.net/generic.jpg','asset_feed_spec':{
        'ad_formats':['CAROUSEL'],'carousels':[{'child_attachments':[
            {'image_label':{'name':f'image{i}'},'title_label':{'name':f'title{i}'}} for i in range(1,n+1)]}],
        'images':[{'hash':f'h{i}','adlabels':[{'name':f'image{i}'}]} for i in range(1,n+1)],
        'titles':[{'text':f'Headline {i}','adlabels':[{'name':f'title{i}'}]} for i in range(1,n+1)]}}


class DetailTests(unittest.TestCase):
    def test_asset_feed_ordered_labels_resolve_all_hashes_in_one_batch(self):
        raw=dynamic_feed(6)
        images={'data':[{'hash':f'h{i}','url':f'https://fixture.fbcdn.net/{i}.jpg'} for i in (5,2,4,1,6,3)]}
        with patch.object(live.meta,'_request',side_effect=[raw,images]) as read:
            value=creative.resolve(CONFIG,'1234')
        self.assertEqual(read.call_count,2)
        self.assertEqual(value['creative_format'],'DYNAMIC_CAROUSEL')
        self.assertEqual(value['carousel_structure_source'],'asset_feed_spec.carousels.child_attachments')
        self.assertEqual([c['image_url'] for c in value['cards']],[f'https://fixture.fbcdn.net/{i}.jpg' for i in range(1,7)])
        self.assertEqual([c['headline'] for c in value['cards']],[f'Headline {i}' for i in range(1,7)])

    def test_dynamic_existing_post_is_no_longer_skipped(self):
        raw={'id':'1234','effective_object_story_id':'1_2','asset_feed_spec':{'bodies':[{'text':'Shared'}]}}
        story={'id':'1_2','attachments':{'data':[{'subattachments':{'data':[
            {'type':'photo','title':f'Card {i}','media':{'image':{'src':f'https://fixture.fbcdn.net/{i}.jpg'}}} for i in range(1,6)]}}]}}
        with patch.object(live.meta,'_request',side_effect=[raw,story]) as read:value=creative.resolve(CONFIG,'1234')
        self.assertEqual(read.call_count,2)
        self.assertEqual(len(value['cards']),5)
        self.assertEqual(value['creative_format'],'DYNAMIC_CAROUSEL')

    def test_generic_thumbnail_never_fills_missing_cards_or_certifies_handoff(self):
        raw=dynamic_feed()
        value=creative.normalize(raw)
        self.assertEqual(len(value['cards']),5)
        self.assertTrue(all(c['image_unavailable'] and not c['image_url'] for c in value['cards']))
        with self.assertRaisesRegex(ValueError,'1, 2, 3, 4, 5'):
            handoff.require_complete_carousel({'carousel_cards':value['cards']})
        import ads_refresh_plan
        with self.assertRaisesRegex(ValueError,'Complete winning Carousel'):
            ads_refresh_plan.reference_map('Carousel',{'creative_format':'DYNAMIC_CAROUSEL','carousel_cards':value['cards']})

    def test_ambiguous_asset_labels_and_multiple_sequences_fail_closed(self):
        raw=dynamic_feed();raw['asset_feed_spec']['images'].append(deepcopy(raw['asset_feed_spec']['images'][0]))
        ambiguous = creative.normalize(raw)
        self.assertEqual(ambiguous['carousel_structure_source'], 'ambiguous_asset_feed_labels')
        self.assertEqual(ambiguous['creative_format'], 'DYNAMIC')
        self.assertFalse(ambiguous['cards'])
        raw['asset_feed_spec']['carousels']*=2
        self.assertEqual(creative.normalize(raw)['creative_format'],'DYNAMIC')
        self.assertFalse(creative.normalize(raw)['cards'])

    def test_repeated_legitimate_images_are_distinct_source_cards(self):
        raw=inline();raw['object_story_spec']['link_data']['child_attachments'][1]['picture']=raw['object_story_spec']['link_data']['child_attachments'][0]['picture']
        self.assertEqual(len(creative.normalize(raw)['cards']),5)
        self.assertNotEqual(creative.normalize(raw)['cards'][0]['identity'],creative.normalize(raw)['cards'][1]['identity'])

    def test_actual_dynamic_ad_detail_navigates_all_cards_without_graph_on_arrows(self):
        def app():
            import ads_meta_review_page as page
            import meta_review_analysis as analysis
            from tests.test_meta_review_creative import inline
            raw=inline();raw['asset_feed_spec']={'bodies':[{'text':'Shared'}]}
            ad={'ad_id':'55','ad_name':'Synthetic dynamic carousel','assets':analysis.creative_assets(raw),'metrics':{},'decision':{}}
            page.ad_card(ad)
        raw=inline();raw['asset_feed_spec']={'bodies':[{'text':'Shared'}]}
        with patch.object(live.meta,'get_meta_config',return_value=CONFIG),patch.object(live.meta,'_request',return_value=raw) as read:
            app_test=AppTest.from_function(app).run()
            self.assertFalse(app_test.exception)
            for i in range(1,6):
                self.assertIn('Headline '+str(i),str([x.proto for x in app_test.get('html')]))
                self.assertIn(f'https://fixture.fbcdn.net/card{i}.jpg',str([x.proto for x in app_test.get('iframe')]))
            self.assertFalse(any(b.label in ('Next card','Previous card') for b in app_test.button))
            for _ in range(3):app_test.run()
        self.assertEqual(read.call_count,2) # creative + all image hashes, cached on reruns

    def test_handoff_while_viewing_card_three_contains_every_card(self):
        import ads_meta_review_page as page
        def app():
            import ads_meta_review_page as page
            import meta_review_analysis as analysis
            from tests.test_meta_review_creative import inline
            raw=inline();raw['asset_feed_spec']={'bodies':[{'text':'Shared'}]}
            ad={'ad_id':'55','ad_name':'Synthetic carousel','assets':analysis.creative_assets(raw),'metrics':{},'decision':{},'benchmark':{}}
            page.simple_winner([ad],{'selections':[],'assets':[],'mapping':[]},{'campaign_id':'77','account_id':'123','date_range':'synthetic'})
        raw=inline();raw['asset_feed_spec']={'bodies':[{'text':'Shared'}]}
        value={**creative.normalize(raw),'raw':raw}
        with patch.object(page.meta,'get_meta_config',return_value=CONFIG),patch.object(creative,'resolve',return_value=value),patch.object(handoff,'queue_link',return_value='?page=creative-refresh') as queue:
            at=AppTest.from_function(app).run()
            next(s for s in at.selectbox if s.label=='Winner to use').set_value('55').run()
            at.session_state['meta-card-index-legacy']=2
            at.run()
            next(b for b in at.button if b.label=='APPLY TO CREATIVE REFRESH').click().run()
        self.assertFalse(at.exception)
        self.assertEqual([c['position'] for c in queue.call_args.args[0]['carousel_cards']],[1,2,3,4,5])
        self.assertEqual(handoff.resolve_campaign_type(queue.call_args.args[0])['campaign_type'],'Carousel')
