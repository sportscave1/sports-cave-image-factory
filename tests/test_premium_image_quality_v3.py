"""Read-only offline regression tests for the premium image-quality upgrade."""
import unittest
from unittest.mock import patch

import ads_ie_visual_systems as ie
import ads_product_catalog as catalog
import ads_page
import mockup_product_prompts as mock
import sports_cave_prompt_blocks as blocks


class PremiumImageQualityV3Tests(unittest.TestCase):
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
