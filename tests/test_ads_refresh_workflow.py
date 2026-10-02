"""Offline acceptance checks. All saves are fake Dropbox receipts; no Meta client."""
import copy
import csv
import io
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_standard_workflow as standard
import ads_posting_handoff as posting_handoff
import ads_posting_page as posting
import meta_review_handoff as meta
import meta_review_products as products
from tests.test_ads_posting_handoff import save_locally, completed_ad
from tests.test_posting_import_csv import FakeUpload, png_image_bytes
from streamlit.testing.v1 import AppTest

TITLE = 'Legends Never Die Messi vs Ronaldo Wall Art'
ROW = {'shopify_product_id': 'fixture-messi', 'product_title': TITLE,
       'product_handle': 'legends-never-die-messi-vs-ronaldo-wall-art', 'collections': ['Football'],
       'online_store_url': 'https://sportscave.com.au/products/legends-never-die-messi-vs-ronaldo-wall-art'}


def winner(carousel=False):
    return {'ad_id': 'fixture-ad', 'adset_id': 'fixture-adset', 'campaign_id': 'fixture-campaign',
            'creative_id': 'fixture-creative', 'image_sha256': 'fixture-archive', 'market': 'AU',
            'format': 'CAROUSEL' if carousel else 'SINGLE IMAGE', 'carousel': carousel,
            'carousel_cards': [{'position':i,'image_url':f'https://example.fbcdn.net/card{i}.jpg'} for i in range(1,6)] if carousel else [],
            'mode': 'complete_ad', 'product_mapping': products.canonical(ROW),
            'components': {'primary_text': {'value': 'Two legends. One unforgettable rivalry.'},
                           'headline': {'value': 'Legends Never Die'},
                           'image': {'value': 'https://example.fbcdn.net/reference.jpg'}},
            'decision': {'reason': 'Signals inconclusive', 'confidence': 'LOW'},
            'description': 'Collector wall art', 'cta': 'SHOP_NOW', 'date_range': 'fixture-date-range'}


def result(carousel=False):
    source = winner(carousel)
    return ads.build_ads_result_record(TITLE, 'Football', 'Australia',
        'Carousel' if carousel else 'Single Image / Video', product_url=ROW['online_store_url'],
        product_id=ROW['shopify_product_id'], creative_refresh_context={
            'winning_primary_text': source['components']['primary_text']['value'],
            'winning_headline': source['components']['headline']['value'], 'source_winner': source})


def completed_single():
    value = result()
    workflow = {'context_key': value['context_key'], 'campaign_type': value['campaign_type'],
                'slots': {}, 'outcomes': {}, 'widget_nonces': {}, 'export_date': '2026-09-30', 'ad_notes': {}}
    rows = [{'schema_version': '1', 'ad_number': i, 'product_name': TITLE, 'strategy': f'Refresh {i}',
             'primary_text': ('A rivalry worth a place on your wall.', 'Remember the moments that made football yours.', 'Give your collection an enduring centrepiece.')[i-1], 'headline': ('Own the rivalry', 'Football remembered', 'A collectors centrepiece')[i-1],
             'description': ('A rivalry for your wall', 'Keep the football memory', 'A focal point for collectors')[i-1], 'cta': 'Shop Now',
             'image_prompt': TITLE + '. ' + ('Preserve exact black-frame artwork in a premium collector room with controlled composition and realistic light. ' * 3)} for i in range(1, 4)]
    import ads_refresh_plan as plan
    selected = value['creative_refresh_context']['refresh_plan']
    workflow['ad_notes']['refresh_executions'] = [dict(
        position=i, winner_reference='WINNER_AD', reference_inspected=True, canonical_inspected=True,
        observations={k:'Synthetic fixture observation: '+style['name'] for k in ('scene_category','ad_role','defining_objects','composition','product_attention','strengths','clutter','mood_contrast','copy_hook','tone','structure','emotional_appeal')}, scene=style['name'], role='collector ownership',
        keep='Rivalry appeal and product prominence', change='New architecture, wall, furniture, lighting and composition',
        improvement='Less clutter; keep artwork readable', style_id=style['id'],
        execution=dict(architecture=style['architecture'], layout=f'Fixture layout {i}', wall_palette=style['wall_hue'], wall_material=style['wall_material'], camera=f'Fixture composition {i}', furniture=style['furniture_materials'], lighting=style['lighting']),
        image_prompt=plan.standalone_brief(TITLE, 'WINNER_AD', style=style))
        for i, style in enumerate(selected['styles'], 1)]
    for row, execution in zip(rows, workflow['ad_notes']['refresh_executions']):
        row['image_prompt'] = execution['image_prompt']
    with patch.object(ads.st, 'session_state', {}):
        standard.apply_csv(ads, value, workflow, ads.build_standard_ads_csv(rows))
        for slot in ads.ads_image_workflow.campaign_image_slots(value['campaign_type']):
            upload = FakeUpload(png_image_bytes(color=(slot['position'] * 30, 70, 110)), name='creative.png', file_id=str(slot['position']))
            ads._process_ads_image_upload(value, workflow, slot, upload)
    return value, workflow


class RefreshWorkflowTests(unittest.TestCase):
    def test_messi_hydration(self):
        source = winner()
        state = {meta.PENDING: source}
        self.assertTrue(meta.hydrate(state))
        self.assertEqual(state[ads.ADS_PRODUCT_NAME_KEY], TITLE)
        self.assertEqual(state[ads.ADS_PRODUCT_URL_KEY], ROW['online_store_url'])
        self.assertEqual(state['ads_category'], 'Football')
        self.assertEqual(state['ads_country'], 'Australia')
        self.assertEqual(state['ads_campaign_type'], 'Single Image / Video')
        self.assertEqual({k: v for k, v in state[meta.ACTIVE].items() if k != "campaign_type_resolution"}, source)
        self.assertTrue(state[meta.ACTIVE]["campaign_type_resolution"]["confirmed"])
        self.assertEqual(state[ads.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY], source['components']['primary_text']['value'])

    def test_three_slots_and_same_five_carousel_slots(self):
        self.assertEqual(len(ads.ads_image_workflow.campaign_image_slots(result()['campaign_type'])), 3)
        self.assertEqual(ads.ads_image_workflow.campaign_image_slots(result(True)['campaign_type']),
                         ads.ads_image_workflow.campaign_image_slots('Carousel'))
        self.assertEqual(len(ads.ads_image_workflow.campaign_image_slots('Carousel')), 5)

    def test_prompt_two_references_copy_evidence_and_count(self):
        prompt = result()['master_prompt']
        for text in (TITLE, 'Two legends. One unforgettable rivalry.', 'Legends Never Die',
                     'ATTACHMENT 1', 'ATTACHMENT 2', 'ATTACHMENT 3', 'BLACK-FRAME', 'THREE refreshed',
                     'Signals inconclusive', 'Do not describe inconclusive', 'Collector wall art', 'SHOP_NOW'):
            self.assertIn(text, prompt)
        self.assertIn('5-CARD', result(True)['master_prompt'])

    def test_same_parser_schema_valid_import_and_invalid_atomicity(self):
        value, workflow = completed_single()
        data = standard.csv_bytes(ads, value, workflow)
        self.assertEqual(tuple(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))).fieldnames), ads.STANDARD_ADS_CSV_HEADERS)
        self.assertEqual(tuple(workflow['standard_ads']), ads.parse_standard_ads_csv(data, product_name=TITLE))
        original = copy.deepcopy(workflow)
        with patch.object(ads.st, 'session_state', {}):
            with self.assertRaises(ads.StandardAdsCSVError) as shared:
                standard.apply_csv(ads, value, workflow, b'invalid\nrow')
            with self.assertRaises(ads.StandardAdsCSVError) as direct:
                ads.parse_standard_ads_csv(b'invalid\nrow', product_name=TITLE)
        self.assertEqual(str(shared.exception), str(direct.exception))
        self.assertEqual(workflow, original)

    def test_images_replace_remove_shared_helpers(self):
        value, workflow = completed_single()
        slot = ads.ads_image_workflow.campaign_image_slots(value['campaign_type'])[0]
        before = workflow['slots'][slot['id']]['source_hash']
        state = {ads._ads_image_state_key(): workflow}
        with patch.object(ads.st, 'session_state', state):
            ads._process_ads_image_upload(value, workflow, slot, FakeUpload(png_image_bytes(color=(1, 2, 3)), name='replacement.png', file_id='replace'))
            self.assertNotEqual(before, workflow['slots'][slot['id']]['source_hash'])
            ads._remove_ads_image_slot(value, slot['id'])
            self.assertNotIn(slot['id'], workflow['slots'])
            self.assertFalse(ads.ads_images_ready(value, workflow))

    def test_single_save_and_existing_handoff_preserve_provenance(self):
        value, workflow = completed_single()
        uploaded = save_locally(value, workflow)
        self.assertNotIn('posting_package_error', workflow, workflow.get('posting_package_error'))
        package = workflow[posting_handoff.SAVED_PACKAGE_KEY]
        self.assertEqual(package['ad_type'], 'Single Image / Video')
        self.assertTrue(package['creative_refresh'])
        self.assertEqual(package['source_provenance']['source_winner']['ad_id'], 'fixture-ad')
        notes = next(v for k, v in uploaded.items() if k.endswith('.txt'))
        self.assertIn(b'fixture-ad', notes)
        state = {}
        posting_handoff.queue_saved_package(package, state=state)
        self.assertTrue(posting.consume_saved_posting_package(ads.build_ads_product_selector_records([ROW]), state=state))
        self.assertEqual(state[posting.AD_TYPE_KEY], 'Single Image / Video')
        self.assertEqual(state[posting.PRIMARY_TEXT_KEYS[0]], workflow['standard_ads'][0]['primary_text'])
        self.assertEqual(state[posting_handoff.LOADED_KEY]['source_provenance'], value['creative_refresh_context'])
        self.assertFalse(posting.consume_saved_posting_package([], state=state))

    def test_partial_save_and_unsaved_edits_block_post_now(self):
        value, workflow = completed_single()
        save_locally(value, workflow, fail='.jpg')
        self.assertNotIn(posting_handoff.SAVED_PACKAGE_KEY, workflow)
        save_locally(value, workflow)
        package = workflow[posting_handoff.SAVED_PACKAGE_KEY]
        workflow['standard_ads'][0]['headline'] = 'Edited after saving'
        self.assertNotEqual(package['source_signature'], ads._ads_saved_source_signature(value, workflow))

    def test_carousel_save_uses_existing_package(self):
        value, workflow = completed_ad('Carousel', 'creative_refresh')
        value['creative_refresh_context'] = {'source_winner': winner(True)}
        uploaded = save_locally(value, workflow)
        package = workflow[posting_handoff.SAVED_PACKAGE_KEY]
        self.assertEqual(len(package['assets']), 5)
        self.assertEqual(package['source_provenance']['source_winner']['ad_id'], 'fixture-ad')
        self.assertTrue(any(b'fixture-ad' in data for path, data in uploaded.items() if path.endswith('.txt')))

    def test_carousel_csv_import_parity_and_posting_handoff(self):
        original, source_workflow = completed_ad('Carousel', 'creative_refresh')
        value = {**original, 'creative_refresh_context': {'source_winner': winner(True)}}
        workflow = {**source_workflow, 'ad_notes': {}}
        with patch.object(ads.st, 'session_state', {}):
            data = ads.build_carousel_copy_csv(value, source_workflow)
            ads.apply_carousel_copy_csv(value, workflow, data)
            self.assertEqual(ads._carousel_copy_notes_from_workflow(value, workflow),
                             ads._carousel_copy_notes_from_workflow(value, source_workflow))
        save_locally(value, workflow)
        state = {}
        posting_handoff.queue_saved_package(workflow[posting_handoff.SAVED_PACKAGE_KEY], state=state)
        from tests.test_posting_import_csv import product_records
        posting.consume_saved_posting_package(product_records(), state=state)
        self.assertEqual(state[posting.AD_TYPE_KEY], 'Carousel')
        self.assertEqual(state[posting_handoff.LOADED_KEY]['source_provenance']['source_winner']['ad_id'], 'fixture-ad')

    def test_catalog_image_reference_uses_selected_row_without_guessing(self):
        from ads_product_catalog import product_reference_image_url
        self.assertEqual(product_reference_image_url(ROW), '')
        url = 'https://cdn.shopify.com/s/files/product.webp'
        self.assertEqual(product_reference_image_url({**ROW, 'image_url': url}), url)
        self.assertEqual(product_reference_image_url({**ROW, 'image_url': 'javascript:alert(1)'}), '')

    def test_missing_source_fields_and_distinct_winner_contexts(self):
        value = result()
        context = {'winning_primary_text': 'A selected reference', 'winning_headline': 'A collector memory'}
        prompt = ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Carousel', product_url=ROW['online_store_url'], creative_refresh_context=context)
        self.assertIn('Winning CTA: Not supplied', prompt)
        second = copy.deepcopy(value['creative_refresh_context'])
        second['source_winner']['ad_id'] = 'different-real-fixture'
        key = ads.ads_result_context_key(value['product_id'], TITLE, 'Football', 'Australia', 'Single Image / Video', creative_refresh_context=second)
        self.assertNotEqual(value['context_key'], key)

    def test_campaign_moment_visual_opt_in(self):
        moment = {'enabled': True, 'type': 'Other', 'name': 'Collector Week', 'market': 'Australia', 'strength': 'Subtle', 'promotion': '', 'include_in_image_prompts': False}
        for include in (False, True):
            moment['include_in_image_prompts'] = include
            prompt = ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Single Image / Video', product_url=ROW['online_store_url'], creative_refresh_context=result()['creative_refresh_context'], campaign_moment=moment)
            visual = prompt.split('VISUAL CAMPAIGN MOMENT RULE', 1)[1].split('EXACT CSV TEMPLATE')[0]
            self.assertEqual('Collector Week' in visual, include)

    def test_drafts_survive_context_switch(self):
        first, second = result(), result(True)
        with patch.object(ads.st, 'session_state', {}), patch.object(ads, 'current_ads_user', return_value={}):
            workflow = ads._ads_image_workflow(first)
            workflow['standard_ads'] = [{'headline': 'Keep my edit'}]
            ads._ads_image_workflow(second)
            self.assertIs(ads._ads_image_workflow(first), workflow)

    def test_shared_ui_has_three_slots_and_post_now_only_after_save(self):
        code = '''
from unittest.mock import patch
import ads_page as ads
import ads_standard_workflow as standard
from tests.test_ads_refresh_workflow import completed_single
from tests.test_ads_posting_handoff import save_locally
import streamlit as st
if 'pair' not in st.session_state:
    st.session_state.pair = completed_single()
result, workflow = st.session_state.pair
if st.button('Simulate successful save'):
    save_locally(result, workflow)
with patch.object(ads, '_render_ads_image_save'):
    standard.render(ads, result, workflow)
'''
        app = AppTest.from_string(code).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('file_uploader')), 4)
        self.assertNotIn('POST NOW', [b.label for b in app.button])
        next(b for b in app.button if b.label == 'Simulate successful save').click().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertIn('POST NOW', [b.label for b in app.button])


if __name__ == '__main__':
    unittest.main()
