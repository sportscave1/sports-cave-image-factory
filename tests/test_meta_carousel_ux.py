import copy
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import meta_carousel_view as view
import meta_review_creative as creative
import meta_review_live as live
import meta_review_handoff as handoff
import ads_meta_review_page as page
from tests.test_meta_review_carousel_contract import authored, image_response, CONFIG


class CarouselUXTests(unittest.TestCase):
    def test_urls_order_and_no_mutation(self):
        cards=[{'position':i,'identity':str(i),'thumbnail_url':f'https://example.test/small/{i}',
                'image_url':f'https://example.test/full/{i}','headline':str(i)} for i in range(1,5)]
        source={'cards':cards}; before=copy.deepcopy(source)
        result=view.card_views(source)
        self.assertEqual([c['number'] for c in result],[1,2,3,4])
        self.assertEqual(result[2]['preview'],'https://example.test/small/3')
        self.assertEqual(result[2]['full'],'https://example.test/full/3')
        self.assertEqual(source,before)
        html=view.strip_html(result)
        self.assertNotIn('base64',html)
        self.assertNotIn('graph.facebook',html)
        self.assertIn('loading=index<4',html)

    def test_script_injection_and_unsafe_urls(self):
        self.assertEqual(view.image_url('javascript:alert(1)'),'')
        self.assertNotIn('</script><b>',view.strip_html([{'full':'</script><b>'}]))

    def test_manual_row_skips_winner_selector_and_preserves_handoff(self):
        def app():
            import streamlit as st
            import ads_meta_review_page as p
            import meta_review_analysis as a
            from tests.test_meta_review_carousel_contract import authored
            raw=authored();raw['object_story_spec']['link_data']['child_attachments']=raw['object_story_spec']['link_data']['child_attachments'][:4]
            ad={'ad_id':'55','campaign_id':'77','ad_name':'Selected carousel','assets':a.creative_assets(raw),
                'metrics':{},'benchmark':{},'decision':{'label':'NO DATA'}}
            st.session_state['sports_cave_current_user']={'role':'worker','is_active':True}
            p.simple_winner([ad],{'selections':[],'assets':[],'mapping':[]},{'campaign_id':'77','account_id':'123'},selected=ad)
        raw=authored();raw['object_story_spec']['link_data']['child_attachments']=raw['object_story_spec']['link_data']['child_attachments'][:4]
        with patch.object(page.meta,'get_meta_config',return_value=CONFIG),patch.object(live.meta,'_request',side_effect=[raw,image_response()]) as graph,patch.object(handoff,'queue_link',return_value='?handoff_id=fixture') as queue:
            at=AppTest.from_function(app).run()
            self.assertFalse(at.exception)
            self.assertFalse(any(s.label=='Winner to use' for s in at.selectbox))
            self.assertFalse(any(e.label in ('Diagnostics','Advanced winner options') for e in at.expander))
            self.assertEqual(len(at.get('iframe')),1)
            next(b for b in at.button if b.label=='APPLY TO CREATIVE REFRESH').click().run()
            self.assertFalse(at.exception)
            cards=queue.call_args.args[0]['carousel_cards']
            self.assertEqual([c['headline'] for c in cards],[f'Headline {i}' for i in range(1,5)])
            self.assertEqual(len(cards),4);self.assertEqual(graph.call_count,2)

    def test_refresh_renders_all_cards_and_primary_text(self):
        def app():
            import streamlit as st
            import meta_review_handoff as h
            st.session_state[h.ACTIVE]={'creative_format':'DYNAMIC_CAROUSEL','carousel_cards':[
                {'position':i,'image_url':f'https://example.test/{i}.jpg','headline':f'Title {i}','description':f'Copy {i}'} for i in range(1,5)],'shared_primary_texts':['Shared variation']}
            h.render_source(st)
        with patch.object(handoff,'hydrate'):
            at=AppTest.from_function(app).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.get('iframe')),1)
        html=str([x.proto for x in at.get('html')])
        for i in range(1,5): self.assertIn(f'Title {i}',html)
        self.assertIn('Shared variation',html)
        self.assertFalse(at.button)


if __name__=='__main__': unittest.main()
