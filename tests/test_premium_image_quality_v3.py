"""Read-only offline regression tests for the premium image-quality upgrade."""
import unittest
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import ads_ie_visual_systems as ie
import ads_product_catalog as catalog
import ads_page
import mockup_product_prompts as mock
import sports_cave_prompt_blocks as blocks
import sports_cave_physical_realism as physical


class PremiumImageQualityV3Tests(unittest.TestCase):
    def test_original_artwork_research_and_unframed_have_no_framed_upgrade(self):
        for raw in ('Create new artwork with {TITLE}', 'Find source photographs.\n' + blocks.SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER):
            text = blocks.append_sports_cave_image_realism_rules(raw, include_product_lock=False)
            self.assertIn(raw, text)
            self.assertNotIn(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER, text)
            self.assertNotIn(physical.MARKER, text)
        for metadata in ({'frame_finish':'Unframed'}, {'selected_variant':'Unframed / XL'},
                         {'physical_product':{'frame_label':'Unframed'}}):
            text = blocks.append_sports_cave_image_realism_rules('Keep my scene', physical_product=metadata)
            self.assertNotIn(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER, text)
            self.assertNotIn(physical.MARKER, text)
            self.assertIn('UNFRAMED PRODUCT - EXACT SOURCE LOCK', text)
        self.assertFalse(physical.is_unframed({'frame_finish':'Black', 'frame_specs':{
            'verified':True, 'source':'stale specification', 'frame_finish':'Unframed'}}))

    def test_legacy_ending_and_existing_premium_marker_remain_idempotent(self):
        ending = 'Generate the approved card now?'
        for raw in ('Saved {ROOM} {CAMERA}\n' + blocks.SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,
                    'Saved {ROOM} {CAMERA}\n' + blocks.SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3):
            raw += '\n\n' + ending
            updated = blocks.append_sports_cave_image_realism_rules(raw, required_ending=ending)
            self.assertTrue(updated.endswith(ending))
            self.assertEqual(updated.count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)
            self.assertEqual(updated.count(physical.MARKER), 1)
            self.assertEqual(blocks.append_sports_cave_image_realism_rules(updated, required_ending=ending), updated)

    def test_custom_and_resolved_mockups_never_redraw_user_selections(self):
        custom = 'Room: {ROOM}; Camera: manually selected 6 degree left; lighting: morning'
        with patch.object(mock.random, 'choice', side_effect=AssertionError('Do not randomise authored settings')):
            first = mock.build('01-man-cave-prompt.txt', custom)
            self.assertIn(custom, first)
            self.assertEqual(mock.build('01-man-cave-prompt.txt', first), first)
            edited = first.replace('morning', 'afternoon')
            result = mock.preserve_selection(edited, first)
            self.assertIn(edited, result)
            self.assertEqual(result.count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)

    def test_saved_prompt_override_is_enriched_without_write_or_variable_reset(self):
        import image_factory
        import prompt_store
        saved = 'Custom room {ROOM}, lighting {LIGHT}, camera {CAMERA}.\n' + blocks.SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER
        before = deepcopy(prompt_store._RUNTIME_PROMPT_CACHE)
        try:
            prompt_store._cache_runtime_record('lifestyle::01-man-cave', {'prompt_text':saved})
            with patch.object(prompt_store, '_upsert_prompt_to_supabase', side_effect=AssertionError('No persistence write')):
                result = image_factory.build_lifestyle_prompt_items('Collector', 'Tennis', local_only=True)
            self.assertIn(saved, result[0]['prompt'])
            self.assertEqual(result[0]['prompt'].count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)
            self.assertEqual(prompt_store.get_cached_prompt('lifestyle::01-man-cave'), saved)
        finally:
            prompt_store._RUNTIME_PROMPT_CACHE.clear()
            prompt_store._RUNTIME_PROMPT_CACHE.update(before)

    def test_ie_manual_refinement_and_edit_stability(self):
        visual = {'resolved_camera_variation':'Approved eye-level view, keep the right camera role'}
        ie.resolve_visual_system(visual, 0, {}, 'same-generation')
        self.assertEqual(visual['resolved_camera_variation'], 'Approved eye-level view, keep the right camera role')
        self.assertEqual(ie.resolved_camera_variation({}, 1, {'artwork_mood':'heritage'}, 'saved'),
                         ie.resolved_camera_variation({}, 1, {'artwork_mood':'modern'}, 'saved'))

    def test_reopened_ads_upgrade_does_not_rebuild_or_overwrite_saved_output(self):
        from tests.test_ads_refresh_plan import fixture
        result = fixture()
        result['master_prompt'] = result['master_prompt'].replace('\n\n' + blocks.SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3, '')
        result['generated_ad_output'] = 'User-edited output {ROOM}, 4 cards, custom copy'
        before = deepcopy(result)
        with patch.object(ads_page, 'build_ads_result_record', side_effect=AssertionError('No scene rebuild')):
            updated = ads_page.ensure_current_ads_result_prompt(result)
        self.assertEqual(result, before)
        self.assertEqual(updated['generated_ad_output'], before['generated_ad_output'])
        self.assertIn(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER, updated['master_prompt'])
        for key in before.keys() - {'master_prompt'}:
            self.assertEqual(updated[key], before[key], key)
        self.assertIs(ads_page.ensure_current_ads_result_prompt(updated), updated)

    def test_complete_main_rules_remain_valid_but_partial_contracts_fail(self):
        import ads_refresh_plan as plan
        from tests.test_ads_refresh_plan import fixture, executions
        old = json.loads((Path(__file__).parent / 'fixtures/premium_legacy_rules_main.json').read_text(encoding='utf-8'))
        value = fixture()
        records = executions(value)
        for record in records:
            detail = 'detail' in record['role']
            current = blocks.build_sports_cave_image_realism_rules(allow_intentional_detail_crop=detail)
            record['image_prompt'] = record['image_prompt'].replace(current, old['detail' if detail else 'normal']).replace(plan.CAROUSEL_AUTHORITY, old['authority'])
        self.assertFalse(plan.execution_issues(records, value['creative_refresh_context']['refresh_plan'], value['product_name'], 'Carousel'))
        for phrase in (old['authority'], 'no fake edition numbers', 'never invent hidden or illegible details'):
            broken = deepcopy(records)
            broken[0]['image_prompt'] = broken[0]['image_prompt'].replace(phrase, '')
            self.assertTrue(plan.execution_issues(broken, value['creative_refresh_context']['refresh_plan'], value['product_name'], 'Carousel'), phrase)

    def test_visual_acknowledgement_expires_for_pixels_references_and_metadata(self):
        from tests.fixtures.refresh_ui import ready_carousel
        result, workflow = ready_carousel()
        key = ads_page._creative_refresh_visual_review_key(result, workflow)
        state = {key:True}
        with patch.object(ads_page.st, 'session_state', state):
            self.assertFalse(ads_page._creative_refresh_visual_review_issues(result, workflow))
            changed_workflow = deepcopy(workflow)
            changed_workflow['slots']['carousel-01']['data'] = b'replaced pixels with stale source_hash'
            self.assertTrue(ads_page._creative_refresh_visual_review_issues(result, changed_workflow))
            changed_result = deepcopy(result)
            changed_result['creative_refresh_context']['source_winner']['carousel_cards'][0]['image_url'] = 'https://example.test/new-winner.png'
            self.assertTrue(ads_page._creative_refresh_visual_review_issues(changed_result, workflow))
            changed_result = {**result, 'product_metadata':{'frame_finish':'White'}}
            self.assertTrue(ads_page._creative_refresh_visual_review_issues(changed_result, workflow))

    def test_unreviewed_direct_post_renderer_cannot_bypass_gate(self):
        from tests.fixtures.refresh_ui import ready_carousel
        result, workflow = ready_carousel()
        with patch.object(ads_page.st, 'session_state', {}), patch.object(ads_page.st, 'button') as button, patch.object(ads_page.st, 'caption'):
            ads_page._render_saved_ad_post_now(result, workflow, quality_issues=[])
        button.assert_not_called()

    def test_unchanged_winner_pixels_block_post_even_with_stale_upload_hash_and_review(self):
        import hashlib
        from tests.fixtures.refresh_ui import ready_carousel
        result, workflow = ready_carousel()
        slot = workflow['slots']['carousel-01']
        result['creative_refresh_context']['refresh_plan']['references'][0]['image_sha256'] = hashlib.sha256(slot['data']).hexdigest()
        slot['source_hash'] = 'stale-upload-hash'
        state = {ads_page._creative_refresh_visual_review_key(result, workflow): True}
        with patch.object(ads_page.st, 'session_state', state), patch.object(ads_page.st, 'button') as button, patch.object(ads_page.st, 'caption') as caption:
            ads_page._render_saved_ad_post_now(result, workflow, quality_issues=[])
        button.assert_not_called()
        self.assertIn('Unchanged winner/canonical source', caption.call_args.args[0])

    def test_black_value_in_unrelated_option_does_not_verify_frame(self):
        for variant in ({'title':'Default', 'selected_options':[{'name':'Artwork colour','value':'Black'}]},
                        {'title':'Black / XL','selected_options':[{'name':'Frame','value':'White'}]}):
            with patch('shopify_sync.fetch_product_by_shopify_id', return_value={
                'handle':'collector','online_store_url':'https://www.sportscaveshop.com/products/collector',
                'variants':[{**variant,'legacy_resource_id':'123'}]}):
                with self.assertRaisesRegex(ValueError, 'No explicitly Black'):
                    catalog.verify_live_black_frame_variant('456', 'collector')

    def test_glazing_and_shadow_quality_are_material_neutral(self):
        prompt = blocks.build_sports_cave_image_realism_rules(physical_product={
            'frame_specs': {'verified': True, 'source': 'Sports Cave verified', 'glazing': 'clear acrylic'},
            'selected_size': 'M',
        })
        self.assertIn('acrylic/Perspex OR glass', prompt)
        self.assertIn('premium reflections', prompt.lower())
        self.assertIn('soft contact shadows', prompt)
        self.assertIn('source-consistent wall separation', prompt)
        self.assertEqual(prompt.count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)

    def test_legacy_custom_prompt_keeps_editable_variables_and_upgrades_once(self):
        old = 'Create a premium room with [ROOM TYPE], {CAMERA_ANGLE} and {{ARTWORK}}.\n\nSPORTS_CAVE_IMAGE_REALISM_RULES_V1'
        upgraded = blocks.append_sports_cave_image_realism_rules(old)
        for variable in ('[ROOM TYPE]', '{CAMERA_ANGLE}', '{{ARTWORK}}'):
            self.assertIn(variable, upgraded)
        self.assertEqual(upgraded.count(blocks.SPORTS_CAVE_PREMIUM_REALISM_MARKER), 1)
        self.assertEqual(blocks.append_sports_cave_image_realism_rules(upgraded), upgraded)

    def test_five_mockup_angles_keep_full_frame_readable(self):
        self.assertEqual(len(mock.ANGLES), 5)
        for angle in mock.ANGLES:
            with patch.object(mock.random, 'choice', side_effect=lambda pool: pool[-1]):
                got = mock.build('01-man-cave-prompt.txt', avoid_angles=set(mock.ANGLES) - {angle})
            self.assertIn('Selected camera angle: ' + angle, got)
            self.assertIn('Preserve the supplied artwork and frame exactly', got)

    def test_ie_five_variations_are_repeatable_without_changing_slot_identity(self):
        context = {'product_sport': 'Motorsport', 'product_era': 'historic', 'artwork_mood': 'heritage'}
        self.assertEqual(len(ie.CAMERA_VARIATIONS), 5)
        for index, role in enumerate(('RIGHT', 'FRONT', 'LEFT')):
            first = {}
            second = {}
            ie.resolve_visual_system(first, index, context, 'variation-test')
            ie.resolve_visual_system(second, index, context, 'variation-test')
            self.assertEqual(first['resolved_camera_variation'], second['resolved_camera_variation'])
            self.assertEqual(first['camera_role'], role)
            self.assertIn(first['resolved_camera_variation'], ie.camera_wall_rules(first))
            self.assertEqual(first['camera_side'], second['camera_side'])

    def test_live_black_variant_is_verified_without_any_shopify_mutation(self):
        value = {
            'handle': 'greg-murphy-lap-of-the-gods-wall-art',
            'online_store_url': 'https://www.sportscaveshop.com/products/greg-murphy-lap-of-the-gods-wall-art',
            'variants': [
                {'title': 'Oak / XL', 'id': 'gid://shopify/ProductVariant/111', 'selected_options': [{'name': 'Frame', 'value': 'Oak'}]},
                {'title': 'Black / XL', 'id': 'gid://shopify/ProductVariant/222', 'selected_options': [{'name': 'Frame', 'value': 'Black'}]},
            ],
            'images': [{'url': 'https://cdn.shopify.com/black-framed-product.webp', 'alt': 'Black framed Greg Murphy'}],
        }
        with patch('shopify_sync.fetch_product_by_shopify_id', return_value=value) as read:
            found = catalog.verify_live_black_frame_variant(
                'gid://shopify/Product/10211086926131',
                'greg-murphy-lap-of-the-gods-wall-art')
        read.assert_called_once()
        self.assertEqual(found['variant_id'], '222')
        self.assertTrue(found['variant_url'].endswith('?variant=222'))
        self.assertEqual(found['original_black_image_url'], value['images'][0]['url'])
        self.assertIn('visual confirmation still required', found['verification_source'])

    def test_black_variant_wrong_product_fails_closed(self):
        with patch('shopify_sync.fetch_product_by_shopify_id', return_value={
            'handle': 'another-product', 'online_store_url': 'https://www.sportscaveshop.com/products/another-product',
            'variants': [{'title': 'Black / XL', 'legacy_resource_id': '1'}],
        }):
            with self.assertRaisesRegex(ValueError, 'does not match'):
                catalog.verify_live_black_frame_variant('123456', 'greg-murphy-lap-of-the-gods-wall-art')

    def test_visual_signoff_resets_on_image_replacement(self):
        result = {'campaign_type': 'Carousel', 'context_key': 'read-only-test'}
        workflow = {'slots': {'carousel-01': {'source_hash': 'image-first'}}}
        first = ads_page._creative_refresh_visual_review_key(result, workflow)
        self.assertEqual(first, ads_page._creative_refresh_visual_review_key(result, workflow))
        workflow['slots']['carousel-01']['source_hash'] = 'new-image'
        self.assertNotEqual(first, ads_page._creative_refresh_visual_review_key(result, workflow))


if __name__ == '__main__':
    unittest.main()
