"""No providers: reproduce replayed handoff resets and bound failed archive reads."""
from copy import deepcopy
import unittest
from unittest.mock import patch,Mock
import ads_page as ads
import meta_review_handoff as handoff
from tests.test_ads_refresh_workflow import winner

class RefreshStabilityTests(unittest.TestCase):
    def test_failed_archive_reads_are_bounded_and_explicitly_retryable(self):
        import meta_carousel_view as view
        state={};st=Mock(session_state=state)
        source={'carousel_cards':[{'position':i,'image_sha256':str(i),'image_url':'https://example.test/image'} for i in range(1,5)]}
        with patch('meta_review_store.load_media',side_effect=TimeoutError('offline')) as load,patch.object(view.time,'monotonic',return_value=1):
            for _ in range(20):view.render(st,source,archived=True)
            self.assertEqual(load.call_count,4)
            st.button.call_args.kwargs['on_click']()
            view.render(st,source,archived=True)
            self.assertEqual(load.call_count,8)
        with patch('meta_review_store.load_media',side_effect=TimeoutError('offline')) as load,patch.object(view.time,'monotonic',return_value=32):
            view.render(st,source,archived=True);self.assertEqual(load.call_count,4)
        self.assertEqual(len(state['meta-carousel-preview-failures']),4)

    def test_duplicate_handoff_keeps_draft_product_and_uploads(self):
        source=winner(True)
        source['campaign_type_resolution']=handoff.resolve_campaign_type(source)
        state={handoff.PENDING:deepcopy(source)}
        handoff.hydrate(state)
        state[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY]={'sentinel':'edited prompt'}
        state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]={'sentinel':'uploaded images'}
        state[ads.ADS_PRODUCT_URL_KEY]+='?collector=1'
        before=deepcopy(state)
        state[handoff.PENDING]=deepcopy(source)
        self.assertFalse(handoff.hydrate(state))
        self.assertEqual(state,before)

    def test_new_winner_still_replaces_workflow(self):
        first=winner(True);state={handoff.PENDING:first};handoff.hydrate(state)
        state[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY]={'old':True}
        second=deepcopy(first);second['ad_id']='different';state[handoff.PENDING]=second
        self.assertTrue(handoff.hydrate(state))
        self.assertNotIn(ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY,state)
