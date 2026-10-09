"""Offline active UI regression tests; colour tiles are not image-analysis evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
import ads_page as ads
import ads_posting_handoff as posting
import ads_refresh_plan as plan
import ads_refresh_reference as reference
import ads_refresh_saved as saved
from tests.fixtures.refresh_ui import ready_carousel
from tests.test_ads_refresh_plan import fixture
from tests.test_ads_posting_handoff import save_locally
from tests.test_posting_import_csv import FakeUpload, png_image_bytes


def app_for(kind='Carousel', count=5):
    app = AppTest.from_file('tests/fixtures/refresh_ui.py')
    app.query_params.update({'format':kind,'count':str(count)})
    return app.run(timeout=30)


def button(app, label):
    return next(b for b in app.button if b.label == label)


class ActiveRefreshRepairTests(unittest.TestCase):
    def test_five_card_save_reopen_post_uses_exact_package(self):
        app = app_for()
        self.assertFalse(app.exception)
        self.assertFalse(button(app,'Save now').disabled)
        before = deepcopy(app.session_state[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY])
        button(app,'Save now').click().run(timeout=30)
        button(app,'Save 5 images here').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(button(app,'POST NOW').disabled)
        workflow = app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]
        package = workflow[posting.SAVED_PACKAGE_KEY]
        self.assertEqual(len(package['assets']),5)
        self.assertEqual(package['source_provenance']['source_winner']['ad_id'],'fixture-ad')
        data = next(v for k,v in app.session_state['fixture_saved_files'].items() if k.endswith(saved.FILENAME))
        state={}; saved.restore(data,state)
        self.assertEqual(state[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY]['product_url'],before['product_url'])
        self.assertEqual(posting.content_hash(state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY][posting.SAVED_PACKAGE_KEY]),posting.content_hash(package))
        button(app,'POST NOW').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['current_page'],ads.POSTING_ROUTE)
        self.assertEqual(posting.content_hash(app.session_state[posting.PENDING_KEY]['package']),posting.content_hash(package))

    def test_ie_active_save_then_post_preserves_three_covers(self):
        app = app_for('Instant Experience')
        self.assertFalse(app.exception)
        original=app.session_state[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY]['master_prompt']
        button(app,'Save now').click().run(timeout=30)
        button(app,'Save Instant Experience Package here').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY]['master_prompt'],original)
        button(app,'POST NOW').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state[posting.PENDING_KEY]['package']['assets']),3)

    def test_incomplete_analysis_leaves_visible_disabled_save_and_preserves_copy(self):
        app=app_for()
        editor=next(t for t in app.text_area if t.label=='Card execution notes (JSON)')
        records=json.loads(editor.value)
        editor.set_value('{invalid').run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(button(app,'Save now').disabled)
        self.assertNotIn('POST NOW',[b.label for b in app.button])
        workflow=app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]
        self.assertEqual(workflow['ad_notes']['refresh_executions'],records)
        next(t for t in app.text_area if t.label=='Card execution notes (JSON)').set_value(json.dumps(records)).run(timeout=30)
        self.assertFalse(button(app,'Save now').disabled)

    def test_four_and_six_card_editor_uses_source_roles_without_crash(self):
        for count in (4,6):
            with self.subTest(count=count):
                app=app_for(count=count)
                self.assertFalse(app.exception)
                text='\n'.join(e.value for e in app.markdown)
                for i in range(1,count+1):
                    self.assertIn(f'Card {i} — Original Winner → Refreshed Card {i}',text)
                self.assertEqual(len([x for x in app.text_input if x.label.endswith('destination URL')]),count)

    def test_settings_mismatch_disables_save_without_losing_images(self):
        app=app_for()
        originals=deepcopy(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['slots'])
        next(t for t in app.text_input if t.label=='Product page URL *').set_value('https://sportscave.com.au/products/wrong').run(timeout=30)
        self.assertTrue(button(app,'Save now').disabled)
        self.assertEqual(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['slots'],originals)
        button(app,'Submit').click().run(timeout=30)
        self.assertTrue(any('do not match' in e.value for e in app.warning))
        self.assertEqual(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['slots'],originals)

    def test_ie_rerenders_read_winner_once_without_lost_inputs(self):
        app=app_for('Instant Experience')
        original=deepcopy(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['slots'])
        for _ in range(3):app.run(timeout=30)
        self.assertEqual(app.session_state['fixture_media_reads'],1)
        self.assertEqual(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['slots'],original)

    def test_duplicate_output_blocks_save(self):
        value, workflow = ready_carousel()
        workflow['slots']['carousel-02']=deepcopy(workflow['slots']['carousel-01'])
        self.assertIn('Identical output image assigned to multiple refresh slots.',ads.creative_refresh_quality_issues(value,workflow))
        with self.assertRaises(ValueError), patch.object(ads.dropbox_integration,'upload_batch',side_effect=AssertionError('No writes')):
            ads.save_ads_images_to_dropbox('fake','/approved','/approved',value,workflow)

    def test_missing_analysis_does_not_write(self):
        value,workflow=ready_carousel()
        workflow['ad_notes'].pop('refresh_executions')
        with self.assertRaisesRegex(ValueError,'execution'), patch.object(ads.dropbox_integration,'upload_batch',side_effect=AssertionError('No writes')):
            ads.save_ads_images_to_dropbox('fake','/approved','/approved',value,workflow)

    def test_reference_authorities_and_all_required_copy_explicit(self):
        prompt=fixture()['master_prompt']
        self.assertIn('all five shared headline variation rows',prompt)
        self.assertIn('all five shared description variation rows',prompt)
        self.assertEqual(prompt.count('If an optional canonical black-frame product photograph'),5)
        self.assertEqual(len(fixture()['creative_refresh_context']['refresh_plan']['references']),5)
        self.assertIn('No additional product image is required',prompt)
        self.assertNotIn('ATTACHMENT 6',prompt)

    def test_duplicate_original_references_fail_without_fabrication(self):
        source=fixture()['creative_refresh_context']['source_winner']
        source['carousel_cards'][2]['image_url']=source['carousel_cards'][0]['image_url']
        with self.assertRaisesRegex(ValueError,'same winning image'):
            plan.reference_map('Carousel',source)

    def test_preview_and_upload_id_reuse_preserve_original_quality(self):
        value,workflow=ready_carousel()
        spec=ads._result_image_slots(value)[0]
        upload=FakeUpload(png_image_bytes(color=(12,45,67)),name='finished.png',file_id='new-upload')
        with patch.object(ads.st,'session_state',{}):
            ads._process_ads_image_upload(value,workflow,spec,upload)
            content=workflow['slots'][spec['id']]['data']
            self.assertTrue(workflow['slots'][spec['id']]['preview_data'])
            with patch.object(upload,'getvalue',side_effect=AssertionError('Unchanged upload must not be reread')):
                ads._process_ads_image_upload(value,workflow,spec,upload)
            self.assertEqual(workflow['slots'][spec['id']]['data'],content)

    def test_session_media_cache_changes_winner_and_user_and_retries_errors(self):
        loader=Mock(return_value=(b'original','image/png'));state={}
        source={'image_sha256':'first','ad_account_id':'a'}
        for _ in range(3):self.assertEqual(reference.load_winner_media(state,source,loader),(b'original','image/png'))
        self.assertEqual(loader.call_count,1)
        reference.load_winner_media(state,{**source,'image_sha256':'second'},loader)
        state['sports_cave_current_user']={'id':'new-user'}
        reference.load_winner_media(state,source,loader)
        self.assertEqual(loader.call_count,3)
        source['image_sha256']='missing';loader.return_value=(None,None)
        reference.load_winner_media(state,source,loader);reference.load_winner_media(state,source,loader)
        self.assertEqual(loader.call_count,5)

    def test_saved_url_and_widgets_are_restored_without_catalogue_overwrite(self):
        result,workflow=ready_carousel()
        result['product_url'] += '?utm_source=meta&utm_campaign=winner#edition'
        for card in workflow['ad_notes']['carousel']['cards']:
            card['destination_url']=result['product_url']
        save_locally(result,workflow)
        key=ads._carousel_card_widget_key(result['context_key'],1,'headline')
        state={key:'Unsaved stale edit','ads-carousel-copy::unrelated::headlines::1':'keep'}
        saved.restore(workflow['refresh_workspace_export'],state)
        self.assertNotIn(key,state)
        self.assertEqual(state['ads-carousel-copy::unrelated::headlines::1'],'keep')
        mapping=result['creative_refresh_context']['source_winner']['product_mapping']
        with patch.object(ads.st,'session_state',state):
            ads.prepare_ads_product_url_state(result['product_name'],selection={
                'selected_label':result['product_name'], 'selector_identity':state[ads.ADS_PRODUCT_SELECTOR_KEY],
                'product_url':mapping['product_url']})
        self.assertEqual(state[ads.ADS_PRODUCT_URL_KEY],result['product_url'])

    def test_legacy_saved_url_keeps_tracking_after_selector_identity_resolution(self):
        value,workflow=ready_carousel()
        value['creative_refresh_context'].pop('source_winner')
        value['product_url']+='?utm_campaign=legacy'
        state={};saved.restore(saved.dumps(value,workflow),state)
        with patch.object(ads.st,'session_state',state):
            ads.prepare_ads_product_url_state(value['product_name'],result=value,selection={
                'product_id':value['product_id'],'selected_label':value['product_name'],
                'selector_identity':'resolved-catalogue-identity','product_url':'https://www.sportscaveshop.com/products/legends-never-die-messi-vs-ronaldo-wall-art'})
        self.assertEqual(state[ads.ADS_PRODUCT_URL_KEY],value['product_url'])

    def test_existing_prompts_identical_outside_approved_physical_contract(self):
        from sports_cave_physical_realism import MARKER
        from tests.test_physical_frame_realism import strip_physical
        baseline=json.loads(Path('tests/fixtures/refresh_unaffected_prompts.json').read_text())
        for identity,expected in baseline.items():
            mode,category,kind=identity.split('/',2)
            context=fixture(kind)['creative_refresh_context'] if mode=='refresh' else None
            value=fixture(kind) if context else {'product_name':'Verified Collector Artwork','product_url':'https://sportscave.com.au/products/verified'}
            prompt=ads.build_ads_prompt(value['product_name'],category,'Australia',kind,product_url=value['product_url'],
                variation_token='baseline',creative_refresh_context=context)
            self.assertIn(MARKER,prompt,identity)
            self.assertEqual(hashlib.sha256(strip_physical(prompt).encode()).hexdigest(),expected,identity)


if __name__=='__main__':unittest.main()
