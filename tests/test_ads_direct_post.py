"""Offline direct posting: source fidelity, inherited targeting and no duplicate dispatch."""
from copy import deepcopy
from unittest import TestCase, mock
from streamlit.testing.v1 import AppTest
import ads_direct_post as direct
import ads_posting_page as posting
import ads_posting_handoff as handoff
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_posting_import_csv import product_records


def refs():
    return {'page': {'id':'page'}, 'instagram': {'id':'ig'},
            'dataset_resolution': {'resolved':True, 'id':'pixel'},
            'catalog_resolution': {'resolved':True, 'id':'catalog'},
            'product_sets':[{'id':'set', 'name':'NBA Michael Jordan'}]}


def settings():
    return {'submission_id':'11111111-1111-4111-8111-111111111111',
            'posting_mode':posting.POSTING_MODE_NEW, 'catalog_id':'catalog', 'product_set_id':'set',
            'audience':{'key':'broad','type':'broad','id':''}}


def saved(kind='Instant Experience', refresh=False):
    result, workflow = completed_ad(kind, 'creative_refresh' if refresh else 'new_ads')
    result['posting_settings'] = settings()
    if refresh:
        result['creative_refresh_context'] = {'source_winner':{'ad_id':'source'}}
    save_locally(result, workflow)
    return workflow[handoff.SAVED_PACKAGE_KEY]


class DirectPostTests(TestCase):
    def test_same_saved_creatives_and_defaults_for_both_formats_without_navigation(self):
        for kind in ('Instant Experience','Carousel'):
            package=saved(kind)
            state={'current_page':'Ads', 'selected_page':'Ads'}
            with mock.patch.object(direct,'references',return_value=refs()), mock.patch.object(direct.st,'query_params',{}):
                request=direct.stage_request(package,settings(),state=state,product_records=product_records())
            self.assertEqual(state['current_page'],'Ads')
            self.assertEqual(request.submission_id, settings()['submission_id'])
            self.assertEqual(request.destination_url,package['batch']['product_url'])
            self.assertEqual(request.customer_lifecycle_strategy,posting.CUSTOMER_LIFECYCLE_ALL_AUDIENCES)
            self.assertEqual(request.audience_type,'broad')
            items=request.creatives if kind=='Instant Experience' else request.carousel_cards
            self.assertEqual([item.image_bytes for item in items],[asset['data'] for asset in package['assets']])
            self.assertEqual(state[handoff.LOADED_KEY]['package_hash'],package['package_hash'])
            self.assertEqual(state[posting.PRODUCT_SET_KEY],'set')
            self.assertEqual(state[posting.AUDIENCE_KEY],'broad')

    def test_refresh_reads_original_ad_and_inherits_exact_existing_adset(self):
        client=mock.Mock()
        client.ad.return_value={'adset_id':'original-adset','creative':{'id':'creative'}}
        client.configured_adset.return_value={'campaign_id':'original-campaign','promoted_object':{}}
        client.creative.return_value={'product_set_id':'set'}
        with mock.patch.object(posting,'MetaPostingClient',return_value=client):
            inherited=direct.refresh_destination.__wrapped__('source','Instant Experience')
        self.assertEqual(inherited['target_adset_id'],'original-adset')
        self.assertEqual(inherited['audience']['type'],'inherited')
        package=saved(refresh=True)
        with mock.patch.object(direct,'references',return_value=refs()), mock.patch.object(direct.st,'query_params',{}), mock.patch.object(direct.refresh_destination,'__wrapped__',return_value=inherited):
            request=direct.stage_request(package,settings(),state={},product_records=product_records())
        self.assertEqual(request.posting_mode,posting.POSTING_MODE_EXISTING)
        self.assertEqual(request.target_adset_id,'original-adset')
        self.assertEqual(request.target_campaign_id,'original-campaign')
        self.assertEqual(request.audience_type,'inherited')
        self.assertFalse(request.create_new_adset_under_existing_campaign)

    def test_missing_target_or_running_job_preserves_current_draft(self):
        package=saved()
        for state, selected in [({'posting_tracked_job':'other'},settings()), ({}, {**settings(),'product_set_id':'missing'})]:
            state[posting.PRIMARY_TEXT_KEYS[0]]='Keep original'
            original=deepcopy(state)
            with mock.patch.object(direct,'references',return_value=refs()), mock.patch.object(direct.st,'query_params',{}):
                with self.assertRaises(ValueError):
                    direct.stage_request(package,selected,state=state,product_records=product_records())
            self.assertEqual(state,original)

    def test_dispatch_binds_identity_before_ambiguous_error_and_never_replays(self):
        workflow={}
        request=mock.Mock(submission_id='same-job')
        state={}
        with mock.patch.object(direct,'stage_request',return_value=request), mock.patch.object(direct.st,'session_state',state), mock.patch.object(direct,'track') as track, mock.patch.object(direct.JOBS,'snapshot',side_effect=TimeoutError('unknown')), mock.patch.object(direct.JOBS,'submit',side_effect=TimeoutError('unknown')) as submit:
            with self.assertRaises(TimeoutError): direct.submit_saved({},settings(),workflow)
            with self.assertRaises(ValueError): direct.submit_saved({},settings(),workflow)
            self.assertEqual(workflow['direct_post_submission_id'],'same-job')
            submit.assert_called_once_with(request)
            track.assert_called_once_with('same-job')

    def test_selectors_render_with_smart_options_and_restore_saved_choice(self):
        app=AppTest.from_string("""
import streamlit as st
from unittest.mock import patch
import ads_direct_post as direct
from tests.test_ads_direct_post import refs
result={'campaign_type':'Instant Experience','product_name':'Michael Jordan','category':'NBA','context_key':'draft'}
workflow=st.session_state.setdefault('workflow',{})
with patch.object(direct,'references',return_value=refs()):
    settings, issues=direct.render_settings(result,workflow)
st.session_state['settings']=settings
st.session_state['issues']=issues
""").run()
        self.assertFalse(app.exception)
        self.assertEqual([x.label for x in app.selectbox],['Product set','Audience'])
        app.selectbox[0].select('set').run()
        self.assertFalse(app.session_state['issues'])
        self.assertEqual(app.session_state['settings']['product_set_id'],'set')
        self.assertEqual(app.session_state['settings']['audience']['key'],'broad')
        identity=app.session_state['settings']['submission_id']
        app.run()
        self.assertEqual(app.session_state['settings']['submission_id'],identity)

    def test_manual_posting_hides_fixed_fields_but_retains_defaults(self):
        from pathlib import Path
        app=AppTest.from_file(str(Path(__file__).parent/'fixtures/post_ad_compact_preview.py')).run(timeout=30)
        self.assertFalse(app.exception)
        labels=[x.label for x in app.text_input]+[x.label for x in app.selectbox]
        for hidden in ('Catalog','Dataset','Customer Lifecycle Strategy'):
            self.assertNotIn(hidden,labels)
        self.assertEqual(app.session_state[posting.CUSTOMER_LIFECYCLE_KEY],posting.CUSTOMER_LIFECYCLE_ALL_AUDIENCES)

    def test_post_now_saves_then_dispatches_on_same_page_and_duplicate_click_is_disabled(self):
        app=AppTest.from_string("""
import streamlit as st
from unittest.mock import patch
import ads_page as ads
import ads_auto_post as auto
import ads_direct_post as direct
from tests.test_ads_direct_post import refs
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_posting_import_csv import product_records
st.session_state.setdefault('current_page','Ads')
r,w=st.session_state.setdefault('fixture_ad',completed_ad('Instant Experience'))
def save(*args, **kwargs):
    assert kwargs['navigate'] is False
    save_locally(r,w)
    st.session_state['saved_first']=True
    return w[ads.posting_handoff.SAVED_PACKAGE_KEY]
def submit(request):
    assert st.session_state['saved_first']
    st.session_state['submitted']=request
    st.session_state['dispatch_count']=st.session_state.get('dispatch_count',0)+1
with patch.object(direct,'references',return_value=refs()), patch.object(direct.posting,'_product_rows_state',return_value=()), patch.object(direct.posting,'_product_selector_state',return_value=(product_records(),{})), patch.object(direct.JOBS,'submit',side_effect=submit), patch.object(auto,'save_and_queue',side_effect=save), patch.object(ads.os_accounts,'can_access_page',return_value=True), patch.object(ads,'instant_experience_package_ready',return_value=True):
    auto.render(ads,r,w)
""").run(timeout=30)
        for toggle in app.toggle:
            if 'product_set' in toggle.key:
                toggle.set_value(True).run()
                break
        app.selectbox[0].select('set').run()
        action=next(button for button in app.button if button.label=='Post now')
        self.assertFalse(action.disabled, [item.value for item in app.caption])
        action.click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['current_page'],'Ads')
        self.assertEqual(app.session_state['dispatch_count'],1)
        self.assertEqual(app.session_state['submitted'].product_set_id,'set')
        self.assertTrue(next(button for button in app.button if button.label=='Post now').disabled)
        app.run()
        self.assertEqual(app.session_state['dispatch_count'],1)

    def test_refresh_has_no_targeting_selectors(self):
        app=AppTest.from_string("""
from unittest.mock import patch
import ads_direct_post as direct
from tests.test_ads_direct_post import refs
result={'campaign_type':'Instant Experience','workflow_mode':'creative_refresh','context_key':'refresh',
        'creative_refresh_context':{'source_winner':{'ad_id':'source'}}}
settings={'posting_mode':direct.posting.POSTING_MODE_EXISTING,'product_set_id':'set',
          'target_campaign_id':'campaign','target_adset_id':'adset','audience':{'type':'inherited'}}
with patch.object(direct,'references',return_value=refs()), patch.object(direct,'refresh_destination',return_value=settings):
    direct.render_settings(result,{})
""").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.selectbox)

    def test_manual_recovery_reuses_saved_submission_identity_and_targeting(self):
        package=saved()
        state={}
        handoff.queue_saved_package(package,state=state)
        posting.consume_saved_posting_package(product_records(),state=state)
        self.assertEqual(state[posting.SUBMISSION_ID_KEY],settings()['submission_id'])
        self.assertEqual(state[posting.PRODUCT_SET_KEY],'set')
        self.assertEqual(state[posting.AUDIENCE_KEY],'broad')
