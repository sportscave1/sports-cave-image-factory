"""Greg Murphy four-card save/handoff; synthetic images, no provider writes."""
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_posting_handoff as handoff
import ads_posting_page as posting
import ads_refresh_saved as saved
from tests.fixtures.refresh_ui import ready_carousel
from tests.test_ads_posting_handoff import save_locally
from tests.test_ads_refresh_workflow import ROW

GREG_ROW={'shopify_product_id':'fixture-greg','product_title':'Greg Murphy — Lap of the Gods',
          'product_handle':'greg-murphy-lap-of-the-gods','collections':['Motorsport'],
          'online_store_url':'https://sportscave.com.au/products/greg-murphy-lap-of-the-gods'}

def greg():
    from meta_review_products import canonical
    result,workflow=ready_carousel(4)
    result.update(product_name=GREG_ROW['product_title'],category='Motorsport',
                  product_id=GREG_ROW['shopify_product_id'],product_url=GREG_ROW['online_store_url'])
    source=result['creative_refresh_context']['source_winner']
    source.update(ad_name=GREG_ROW['product_title'],product_mapping=canonical(GREG_ROW))
    for card in workflow['ad_notes']['carousel']['cards']:
        card['destination_url']=GREG_ROW['online_store_url']
    workflow['ad_notes']['refresh_executions']=[]
    return result,workflow


class RefreshDraftTests(unittest.TestCase):
    def test_failed_workspace_write_preserves_inputs_and_blocks_handoff_until_saved(self):
        result,workflow=greg();workflow['slots']={}
        copy=deepcopy(workflow['ad_notes'])
        with self.assertRaisesRegex(ValueError,'could not be persisted'):
            save_locally(result,workflow,fail=saved.FILENAME)
        self.assertFalse(workflow['refresh_workspace_saved'])
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY,workflow)
        self.assertEqual(workflow['ad_notes'],copy)
        save_locally(result,workflow)
        self.assertTrue(workflow['refresh_workspace_saved'])

    def test_empty_standard_refresh_draft_can_save_and_enter_existing_review(self):
        from tests.test_ads_posting_handoff import completed_ad,product_records
        result,workflow=completed_ad('Single Image / Video','creative_refresh')
        workflow['slots']={};workflow['standard_ads']=[]
        save_locally(result,workflow)
        state={};handoff.queue_saved_package(workflow[handoff.SAVED_PACKAGE_KEY],state=state)
        posting.consume_saved_posting_package(product_records(),state=state)
        self.assertEqual(state[posting.AD_TYPE_KEY],'Single Image / Video')
        self.assertEqual(state[handoff.LOADED_KEY]['source_copy'],[])
        self.assertEqual(state[handoff.LOADED_KEY]['assets'],[])

    def test_four_card_mock_creation_and_retry_preserve_paused_and_no_duplicates(self):
        from tests.test_meta_carousel_posting import carousel_request,FakeCarouselClient,FakePostingStore,AcceptingCarouselValidator,carousel_ad_result
        from meta_posting_service import MetaPostingService,PostingError
        client=FakeCarouselClient(fail_first_ad=True)
        service=MetaPostingService(client=client,store=FakePostingStore(),carousel_validator=AcceptingCarouselValidator())
        request=carousel_request();request=replace(request,carousel_cards=request.carousel_cards[:4],carousel_card_count=4)
        with self.assertRaises(PostingError):service.create_paused_campaign(request)
        result=service.create_paused_campaign(request)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(carousel_ad_result(result['ad_results'])['meta_ad_configured_status'],'PAUSED')
        self.assertEqual(client.calls.count('campaign'),1)
        self.assertEqual(client.calls.count('adset'),1)
        self.assertEqual(client.calls.count('ad_image'),4)
        self.assertEqual(client.calls.count('carousel_creative'),1)
        self.assertEqual(len(client.carousel_ads),1)

    def test_incomplete_ie_draft_preserves_missing_middle_cover(self):
        from tests.test_ads_refresh_save_restore import RefreshSaveRestoreTests
        result,workflow=RefreshSaveRestoreTests().ready_ie()
        save_locally(result,workflow)
        old_id=workflow[handoff.SAVED_PACKAGE_KEY]['package_id']
        specs=ads._result_image_slots(result);workflow['slots'].pop(specs[1]['id'])
        workflow['ad_notes']['instant_experience_concepts'][ads.INSTANT_EXPERIENCE_CONCEPTS[1]['id']][0]['headline']=''
        save_locally(result,workflow)
        self.assertNotEqual(workflow[handoff.SAVED_PACKAGE_KEY]['package_id'],old_id)
        state={};handoff.queue_saved_package(workflow[handoff.SAVED_PACKAGE_KEY],state=state)
        posting.consume_saved_posting_package(ads.build_ads_product_selector_records([ROW]),state=state)
        self.assertNotIn(posting.IMAGE_STATE_KEYS[1],state)
        self.assertIn(posting.IMAGE_STATE_KEYS[2],state)
        self.assertEqual(state[posting.HEADLINE_KEYS[1]],'')

    def test_four_cards_optional_notes_full_and_partial_round_trip(self):
        for notes in (None,[],[{'unperformed':True}]):
            for missing in (False,True):
                with self.subTest(notes=notes,missing=missing):
                    result,workflow=greg()
                    if notes is None:workflow['ad_notes'].pop('refresh_executions',None)
                    else:workflow['ad_notes']['refresh_executions']=deepcopy(notes)
                    if missing:
                        workflow['slots'].pop('carousel-02')
                        workflow['ad_notes']['carousel']['cards'][1]['headline']=''
                    original=deepcopy(workflow['ad_notes'])
                    uploads=save_locally(result,workflow)
                    data=next(data for path,data in uploads.items() if path.endswith(saved.FILENAME))
                    restored,reopened=saved.loads(data)
                    self.assertEqual(reopened['ad_notes'].get('refresh_executions'),original.get('refresh_executions'))
                    for before,after in zip(original['carousel']['cards'],reopened['ad_notes']['carousel']['cards']):
                        self.assertEqual({k:v for k,v in before.items() if k!='image_filename'}, {k:v for k,v in after.items() if k!='image_filename'})
                    package=reopened[handoff.SAVED_PACKAGE_KEY]
                    self.assertEqual(len(package['batch']['cards']),4)
                    self.assertEqual(len(package['assets']),3 if missing else 4)
                    state={};handoff.queue_saved_package(package,state=state)
                    self.assertTrue(posting.consume_saved_posting_package(ads.build_ads_product_selector_records([GREG_ROW]),state=state))
                    self.assertEqual(state[posting.SAVED_PRODUCT_URL_KEY]['url'],GREG_ROW['online_store_url'])
                    self.assertEqual(state[posting.CAROUSEL_COUNT_KEY],4)
                    self.assertEqual(state[posting.CAROUSEL_HEADLINE_KEYS[0]],original['carousel']['cards'][0]['headline'])
                    self.assertEqual(posting.CAROUSEL_IMAGE_STATE_KEYS[1] in state,not missing)
                    self.assertIn(posting.CAROUSEL_IMAGE_STATE_KEYS[2],state)
                    self.assertFalse(posting.consume_saved_posting_package([],state=state))
                    back={};saved.restore(data,back)
                    self.assertEqual(back[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY]['product_name'],result['product_name'])

    def test_empty_draft_saves_without_claiming_uploaded_images(self):
        result,workflow=greg();workflow['slots']={}
        uploads=save_locally(result,workflow)
        self.assertTrue(workflow['refresh_workspace_saved'])
        self.assertEqual(workflow[handoff.SAVED_PACKAGE_KEY]['assets'],[])
        self.assertTrue(any(p.endswith(saved.FILENAME) for p in uploads))

    def test_four_card_actual_validation_still_requires_real_images(self):
        from tests.test_meta_carousel_posting import carousel_request
        from meta_posting_service import validate_carousel_posting_request,PostingValidationError
        request=carousel_request();request=replace(request,carousel_cards=request.carousel_cards[:4],carousel_card_count=4)
        self.assertEqual(len(validate_carousel_posting_request(request)['carousel_cards']),4)
        broken=replace(request,carousel_cards=(replace(request.carousel_cards[0],image_bytes=b''),*request.carousel_cards[1:]))
        with self.assertRaisesRegex(PostingValidationError,'Upload Carousel Image 1'):
            validate_carousel_posting_request(broken)

    def test_optional_reviews_are_absent_from_active_ui_and_draft_save_available(self):
        from tests.test_ads_refresh_repair import app_for,button
        app=app_for(count=4)
        workflow=app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]
        workflow['ad_notes']['refresh_executions']=[]
        workflow['slots']={};app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertNotIn('Card execution notes (JSON)',[x.label for x in app.text_area])
        self.assertFalse(button(app,'Save now').disabled)
        button(app,'Save now').click().run(timeout=30)
        button(app,'Save setup notes here').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertNotEqual(app.session_state.filtered_state.get('current_page'),ads.POSTING_ROUTE)
        button(app,'POST NOW').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['current_page'],ads.POSTING_ROUTE)
