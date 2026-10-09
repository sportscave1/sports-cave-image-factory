"""Offline prompt contracts; these tests do not certify the dimensions of pixels."""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch

import sports_cave_physical_realism as physical
import sports_cave_prompt_blocks as blocks


def strip_physical(prompt):
    return re.sub(r'\n\n' + re.escape(physical.MARKER) + r'.*?' + re.escape(physical.END), '', prompt, flags=re.S).replace('; PHYSICAL FRAME REALISM V2','').replace('\nPHYSICAL FRAME REALISM V2','')


class PhysicalDimensionsTests(unittest.TestCase):
    def test_xl_landscape_and_portrait(self):
        for orientation, expected in [('landscape',(87,62)),('portrait',(62,87))]:
            with self.subTest(orientation=orientation):
                value = physical.resolve({'selected_size':'XL','orientation':orientation})
                self.assertEqual((value['width_cm'],value['height_cm']),expected)
                self.assertEqual(value['measurement_basis'],'display size; outer frame unconfirmed')
        for label in ('Extra Large','Extra-large'):
            self.assertEqual(physical.resolve({'selected_size':label,'orientation':'landscape'})['width_cm'],87)

    def test_all_smaller_variants_use_existing_actual_display_sizes(self):
        for size, pair in [('S',(30,21)),('M',(45,30)),('L',(62,45))]:
            value = physical.resolve({'selected_size':size,'orientation':'landscape'})
            self.assertEqual((value['width_cm'],value['height_cm']),pair)
            text = physical.build({'selected_size':size,'orientation':'landscape'})
            self.assertNotIn('87',text)

    def test_existing_selected_variant_label_and_a_size_alias(self):
        for label in ('Oak / M - 30 × 45 cm (11.8 × 17.7 in)', 'M - 30 x 45 cm', 'A3', 'Medium'):
            value = physical.resolve({'selected_variant':label,'orientation':'landscape'})
            self.assertEqual((value['width_cm'],value['height_cm']),(45,30))

    def test_verified_outer_frame_overrides_label_no_border_added(self):
        value = physical.resolve({'selected_size':'XL','orientation':'landscape',
            'frame_specs':{'verified':True,'source':'Selected product specification','outer_width_cm':86.7,'outer_height_cm':61.8}})
        self.assertEqual((value['width_cm'],value['height_cm']),(86.7,61.8))
        self.assertEqual(value['measurement_basis'],'verified outer frame')

    def test_verified_variant_dimensions_and_nominal_basis_preserved(self):
        value = physical.resolve({'selected_variant':{'verified':True,'source':'Variant specification',
            'width_cm':59.4,'height_cm':84.1,'measurement_basis':'nominal print'}})
        self.assertEqual(value['measurement_basis'],'nominal print')
        self.assertEqual((value['width_cm'],value['height_cm']),(59.4,84.1))
        self.assertNotIn('verified_depth_mm',value)

    def test_explicit_dimensions_outrank_largest_fallback(self):
        value = physical.resolve({'showcase_largest':True,'explicit_dimensions':{'width_cm':80,'height_cm':56}})
        self.assertEqual((value['width_cm'],value['height_cm']),(80,56))
        self.assertEqual(value['dimension_source'],'explicitly supplied product dimensions')

    def test_largest_reference_only_when_applicable(self):
        value = physical.resolve({'showcase_largest':True,'orientation':'landscape'})
        self.assertEqual((value['width_cm'],value['height_cm']),(87,62))
        for metadata in ({}, {'width':1920,'height':1080}, {'selected_size':'Custom'}):
            value = physical.resolve(metadata)
            self.assertNotIn('width_cm',value)
            self.assertIn('unresolved',value['measurement_basis'])

    def test_unknown_orientation_does_not_force_landscape_or_ratios(self):
        value = physical.resolve({'selected_size':'XL'})
        self.assertIn('orient to the unchanged source',value['axes'])
        self.assertNotIn('comparable_depth_width_ratios',value)

    def test_conflicting_verified_axes_require_confirmation_not_stretching(self):
        value = physical.resolve({'orientation':'portrait','frame_specs':{'verified':True,'source':'Spec',
            'outer_width_cm':87,'outer_height_cm':62}})
        self.assertIn('needs_confirmation',value)
        self.assertEqual((value['width_cm'],value['height_cm']),(87,62))
        self.assertNotIn('comparable_depth_width_ratios',value)

    def test_unverified_specs_do_not_invent_depth_glazing_or_dimensions(self):
        value = physical.resolve({'frame_specs':{'outer_width_cm':120,'outer_height_cm':90,'depth_mm':70,'glazing':'glass'}})
        for field in ('width_cm','height_cm','verified_depth_mm','glazing'):
            self.assertNotIn(field,value)

    def test_depth_glazing_finish_only_from_verified_spec(self):
        value = physical.resolve({'frame_specs':{'verified':True,'source':'Test product specification',
            'depth_mm':18,'glazing':'clear acrylic / Perspex','frame_finish':'Oak'}})
        self.assertEqual(value['verified_depth_mm'],18)
        self.assertEqual(value['glazing'],'clear acrylic / Perspex')
        self.assertEqual(value['frame_finish'],'Oak')

    def test_conflicting_specification_cannot_replace_selected_finish(self):
        value = physical.resolve({'frame_finish':'White','frame_specs':{'verified':True,
            'source':'Product specification','frame_finish':'Black'}})
        self.assertEqual(value['frame_finish'],'White')
        self.assertIn('finish_needs_confirmation',value)

    def test_malformed_nonfinite_and_pixel_values_never_become_physical_size(self):
        for bad in ('unknown', -1, 0, float('nan'), float('inf'), True):
            value = physical.resolve({'explicit_dimensions':{'width_cm':bad,'height_cm':62}})
            self.assertNotIn('width_cm',value)
        self.assertNotIn('width_cm',physical.resolve({'image':{'width':1024,'height':1024}}))

    def test_frame_sofa_sideboard_doorway_proportions(self):
        ratios = physical.resolve({'selected_size':'XL','orientation':'landscape'})['comparable_depth_width_ratios']
        self.assertAlmostEqual(ratios['180 cm sideboard'],.4833)
        self.assertAlmostEqual(ratios['200 cm sofa'],.435)
        self.assertAlmostEqual(ratios['85 cm doorway'],1.0235)
        small = physical.resolve({'selected_size':'S','orientation':'landscape'})['comparable_depth_width_ratios']
        self.assertEqual(small['200 cm sofa'],.15)

    def test_input_metadata_is_not_mutated_and_private_fields_not_serialised(self):
        metadata = {'physical_product':{'selected_size':'M','frame_specs':{'verified':True,'source':'spec',
            'glazing':'acrylic','access_token':'secret'}},'customer_email':'private@example.test'}
        original = deepcopy(metadata)
        prompt = physical.build(metadata)
        self.assertEqual(metadata,original)
        self.assertNotIn('secret',prompt); self.assertNotIn('private@example.test',prompt)
        self.assertNotIn('access_token',json.dumps(physical.physical_metadata(metadata)))


class PhysicalContractTests(unittest.TestCase):
    def test_construction_mounting_glazing_and_integrity_are_explicit(self):
        text = physical.build()
        for phrase in ('slim front moulding','side profile','clean mitred joins','invent exact frame-depth',
                       'No thick museum surround','invented matboard','minimal source-consistent wall separation',
                       'soft contact shadows','ambient occlusion','natural residential height',
                       'acrylic/Perspex','glass only when verified','without inventing composition',
                       'No thick protruding slab','signatures and existing edition numbers',
                       'source-preserving compositing','rigid product geometry','rendered pixels when available'):
            self.assertIn(phrase,text)

    def test_close_up_hero_works_without_oversizing_or_changing_creative_direction(self):
        text = physical.build()
        for phrase in ('a close-up may fill the canvas at true size','No universal percentage',
                       'never raw pixel widths','preserve the existing scene','camera-angle variation',
                       'lighting concept','output dimensions, aspect ratio, copy and sequence'):
            self.assertIn(phrase,text)

    def test_shared_rules_append_once_and_preserve_exact_ending(self):
        ending = 'Would you like me to generate Card 1?'
        raw = 'Existing room, left camera and image dimensions.\n\n'+ending
        prompt = blocks.append_sports_cave_image_realism_rules(raw,required_ending=ending)
        again = blocks.append_sports_cave_image_realism_rules(prompt,required_ending=ending)
        self.assertEqual(prompt,again)
        self.assertEqual(prompt.count(physical.MARKER),1)
        self.assertTrue(prompt.endswith(ending))

    def test_cached_legacy_prompt_gets_only_missing_block(self):
        legacy = blocks.build_sports_cave_image_realism_rules(include_physical_realism=False)
        updated = blocks.append_sports_cave_image_realism_rules(legacy)
        self.assertEqual(strip_physical(updated),legacy)
        self.assertEqual(updated.count(blocks.SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER),1)
        self.assertEqual(updated.count(physical.MARKER),1)

    def test_original_artwork_and_reference_search_not_converted_into_frame_scenes(self):
        prompt = blocks.build_sports_cave_image_realism_rules(include_product_lock=False)
        self.assertNotIn(physical.MARKER,prompt)
        self.assertEqual(physical.apply_context(prompt,{'selected_size':'XL'}),prompt)

    def test_old_product_and_photorealism_locks_remain_verbatim(self):
        prompt = blocks.build_sports_cave_image_realism_rules()
        self.assertIn(blocks.SPORTS_CAVE_PRODUCT_MOCKUP_LOCK_BLOCK,prompt)
        self.assertIn(blocks.SPORTS_CAVE_GLOBAL_PHOTOGRAPHIC_REALISM_BLOCK,prompt)
        self.assertEqual(strip_physical(prompt),blocks.build_sports_cave_image_realism_rules(include_physical_realism=False))

    def test_recontextualising_changed_size_replaces_instead_of_duplicating(self):
        original = blocks.build_sports_cave_image_realism_rules(physical_product={'selected_size':'XL','orientation':'landscape'})
        current = blocks.append_sports_cave_image_realism_rules(original,physical_product={'selected_size':'S','orientation':'portrait'})
        self.assertEqual(current.count(physical.MARKER),1)
        self.assertNotIn('87',current)
        self.assertIn('"width_cm": 21',current)
        self.assertEqual(strip_physical(current),strip_physical(original))

    def test_detail_crop_exception_stays_intact(self):
        prompt = blocks.build_sports_cave_image_realism_rules(allow_intentional_detail_crop=True)
        self.assertIn('INTENTIONAL DETAIL CARD ONLY',prompt)
        self.assertIn('retain only an already-authorised detail-photo crop',prompt)

    def test_existing_standalone_physical_block_is_not_duplicated_by_shared_wrapper(self):
        original = physical.build({'selected_size':'XL'})
        prompt = blocks.append_sports_cave_image_realism_rules(original,
            physical_product={'selected_size':'S','orientation':'portrait'})
        self.assertEqual(prompt.count(physical.MARKER),1)
        self.assertIn('"width_cm": 21',prompt)
        self.assertIn(blocks.SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,prompt)


class PhysicalWorkflowTests(unittest.TestCase):
    def test_existing_product_page_result_forwards_physical_evidence(self):
        # Extract the pure handoff without starting app.py or its service clients.
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n,ast.FunctionDef)
            and n.name=='build_current_mockup_prompt_items_for_result')
        factory = Mock()
        scope = {'get_image_factory':lambda:factory,'PROMPT_LABELS':{'existing':'labels'}}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'app.py','exec'),scope)
        metadata = {'selected_size':'S','orientation':'portrait'}
        scope[function.name]({'product_name':'Collector','sport_category':'Tennis',
            'product_metadata':metadata,'black_framed_webp_path':'original.webp'})
        call = factory.build_lifestyle_prompt_items.call_args
        self.assertEqual(call.args,('Collector','Tennis'))
        self.assertEqual(call.kwargs['product_metadata'],metadata)
        self.assertTrue(call.kwargs['artwork_reference_available'])
        self.assertTrue(call.kwargs['local_only'])

    def test_25_ads_prompt_combinations_keep_structure_with_new_visual_quality(self):
        import ads_page as ads
        from tests.test_ads_refresh_plan import fixture
        baseline = json.loads(Path('tests/fixtures/refresh_unaffected_prompts.json').read_text())
        # Image prompts intentionally changed; the old SHA fixtures are evidence of the
        # pre-upgrade text, not a production contract after explicit user approval.
        self.assertEqual(len(baseline), 25)
        for identity in baseline:
            mode,category,kind = identity.split('/',2)
            context = fixture(kind)['creative_refresh_context'] if mode=='refresh' else None
            value = fixture(kind) if context else {'product_name':'Verified Collector Artwork','product_url':'https://sportscave.com.au/products/verified'}
            prompt = ads.build_ads_prompt(value['product_name'],category,'Australia',kind,product_url=value['product_url'],
                variation_token='baseline',creative_refresh_context=context)
            with self.subTest(identity=identity):
                self.assertIn(physical.MARKER,prompt)
                self.assertIn('GLOBAL PHOTOGRAPHIC REALISM RULES - MANDATORY',prompt)
                self.assertIn('SPORTS_CAVE_PREMIUM_VISUAL_REALISM_V3',prompt)
                self.assertIn(value['product_name'],prompt)
                if context and kind == 'Carousel':
                    self.assertIn('COLLECTIVE WINNER CAROUSEL V1',prompt)
                    self.assertIn('CANONICAL_PRODUCT',prompt)
                if context and kind == 'Instant Experience':
                    self.assertIn('WINNER_IE',prompt)

    def test_new_ads_and_refresh_each_receive_selected_smaller_dimensions(self):
        import ads_page as ads
        from tests.test_ads_refresh_plan import fixture
        for mode in ('new','refresh'):
            for kind in ('Carousel','Instant Experience','Single Image / Video'):
                value = fixture(kind)
                context = value['creative_refresh_context'] if mode=='refresh' else None
                prompt = ads.build_ads_prompt(value['product_name'],value['category'],'Australia',kind,
                    product_url=value['product_url'],creative_refresh_context=context,
                    product_metadata={'physical_product':{'selected_size':'M','orientation':'landscape'}})
                for block in physical.BLOCK.findall(prompt):
                    self.assertIn('"width_cm": 45',block)
                    self.assertIn('"height_cm": 30',block)
                    self.assertNotIn('87',block)

    def test_ie_winner_refinement_direct_builder_applies_verified_specs(self):
        import ads_page as ads
        from tests.test_ads_refresh_plan import fixture
        value = fixture('Instant Experience')
        prompt = ads.build_instant_experience_winner_refinement_prompt(value['product_name'],'Football','Australia',
            value['product_url'],value['creative_refresh_context'],product_metadata={'selected_size':'XL','orientation':'portrait'})
        self.assertEqual(prompt.count(physical.MARKER),3)
        self.assertEqual(prompt.count('"width_cm": 62'),3)

    def test_four_card_winner_keeps_order_scene_roles_and_copy_contract(self):
        from tests.fixtures.carousel_evolution import greg
        import ads_refresh_plan as plan
        result,copy,records = greg()
        self.assertEqual(result['master_prompt'].count(physical.MARKER),4)
        self.assertIn('SPORTS_CAVE_CAROUSEL_WINNER_COPY_EVOLUTION_V2',result['master_prompt'])
        self.assertEqual(len(copy['cards']),4)
        for record in records:
            self.assertEqual(record['image_prompt'].count(physical.MARKER),1)
        # Old saved standalone briefs must not be invalidated by a new global rule.
        for record in records:
            record['image_prompt'] = strip_physical(record['image_prompt'])
        self.assertFalse(plan.execution_issues(records,result['creative_refresh_context']['refresh_plan'],result['product_name'],'Carousel'))

    def test_product_page_shopify_mockups_room_angle_and_reference_unchanged(self):
        import image_factory as factory
        import mockup_product_prompts as scenes
        with patch.object(scenes.random,'choice',side_effect=lambda options:options[0]), patch.object(factory,'get_lifestyle_prompt_text',side_effect=lambda f,t,**k:t):
            actual = factory.build_lifestyle_prompt_items('Artwork','Motorsport',local_only=True,
                product_metadata={'selected_size':'XL','orientation':'landscape'})
            with patch.object(physical,'build',return_value=''):
                previous = factory.build_lifestyle_prompt_items('Artwork','Motorsport',local_only=True)
        self.assertEqual(len(actual),3)
        for current,old in zip(actual,previous):
            self.assertEqual(strip_physical(current['prompt']),old['prompt'])
            self.assertIn('1024 x 1024',current['prompt'])
            self.assertIn('"width_cm": 87',current['prompt'])
            self.assertEqual(current['filename'],old['filename'])

    def test_active_social_prompts_keep_creative_content_dimensions_and_copy(self):
        import social_media_creator as creator
        from tests.test_social_media_creator import base_payload
        actual = creator.build_content_package(base_payload())
        with patch.object(physical,'build',return_value=''):
            previous = creator.build_content_package(base_payload())
        for current,old in zip(actual['visual_prompts'],previous['visual_prompts']):
            self.assertEqual(current['prompt'].count(physical.MARKER),1)
            self.assertEqual(strip_physical(current['prompt']),old['prompt'])
            self.assertIn('1080 x 1350',current['prompt'])

    def test_marketing_mockup_prompts_keep_nonimage_output(self):
        import marketing_factory_page as marketing
        from tests.test_marketing_factory_page import MarketingFactoryPageTests
        inputs = MarketingFactoryPageTests()._inputs()
        actual = marketing._build_pack(inputs)
        with patch.object(physical,'build',return_value=''):
            previous = marketing._build_pack(inputs)
        for key,value in actual.items():
            self.assertEqual(strip_physical(value) if isinstance(value,str) else value,previous[key],key)
        self.assertEqual(actual['mockup_brief'].count(physical.MARKER),1)

    def test_social_and_marketing_use_available_selected_variant_evidence(self):
        import social_media_creator as creator
        from tests.test_social_media_creator import base_payload
        import marketing_factory_page as marketing
        from tests.test_marketing_factory_page import MarketingFactoryPageTests
        context = {'selected_size':'S','orientation':'portrait','frame_finish':'White'}
        social = creator.build_content_package(base_payload(physical_product=context))
        pack = marketing._build_pack(MarketingFactoryPageTests()._inputs(physical_product=context))
        for text in [p['prompt'] for p in social['visual_prompts']] + [pack['mockup_brief']]:
            for block in physical.BLOCK.findall(text):
                self.assertIn('"width_cm": 21',block)
                self.assertIn('"frame_finish": "White"',block)

    def test_active_reels_stills_and_video_keep_camera_and_artwork_freeze(self):
        import social_media_reels_studio_page as reels
        scene = reels.get_scene_by_slug('wall-only')
        for builder in (reels.build_image_prompt,reels.build_video_prompt):
            actual = builder(scene,'collector','Collector artwork','Motorsport','',prompt_records={})
            with patch.object(physical,'build',return_value=''):
                previous = builder(scene,'collector','Collector artwork','Motorsport','',prompt_records={})
            self.assertEqual(actual.count(physical.MARKER),1)
            self.assertEqual(strip_physical(actual).strip(),previous.strip())

    def test_google_display_prompts_use_metadata_without_changing_strategy(self):
        import ads_google_demand_gen as google
        context = {'selected_size':'XL','orientation':'landscape'}
        args = ('Collector Artwork','Motorsport','Australia','https://example.test/products/collector')
        actual = google.build_google_prompt(*args,product_metadata=context)
        with patch.object(physical,'build',return_value=''):
            previous = google.build_google_prompt(*args,product_metadata=context)
        self.assertEqual(strip_physical(actual),previous)
        self.assertEqual(actual.count(physical.MARKER),1)
        self.assertIn('"width_cm": 87',actual)

    def test_website_blog_lifestyle_banners_preserve_canvas_and_creative_direction(self):
        import seo_blog_workflow as seo
        from tests.test_seo_blog_workflow import completed_brief
        actual = seo.build_prompt_2({'project_id':'offline','brief':completed_brief()})
        with patch.object(physical,'build',return_value=''):
            previous = seo.build_prompt_2({'project_id':'offline','brief':completed_brief()})
        self.assertEqual(strip_physical(actual),previous)
        self.assertEqual(actual.count(physical.MARKER),1)
        for canvas in ('1600x900','1600x1067','1600x1200'):
            self.assertIn(canvas,actual)

    def test_email_promotional_rooms_receive_contract_without_html_changes(self):
        import crm_email_visual_prompt as email
        email.visual_contract.cache_clear()
        prompt = email.visual_contract()
        self.assertEqual(prompt.count(physical.MARKER),1)
        original = Path('prompts/sports_cave_email_visual_v1.txt').read_text(encoding='utf-8').strip()
        self.assertEqual(strip_physical(prompt),original)
        self.assertIn('1200x900',prompt)

    def test_design_studio_original_artwork_not_reactivated_as_mockup_generator(self):
        import design_studio_page as studio
        prompt = studio.build_design_studio_image_generation_prompt('Create a new sporting artwork')
        self.assertNotIn(physical.MARKER,prompt)
        self.assertIn('ORIGINAL ARTWORK MODE',prompt)
        self.assertIn('Retired Website Mockups V2',Path('website_mockups.py').read_text())

    def test_product_metadata_projection_adds_no_fields_when_none_available(self):
        import ads_page as ads
        plain = ads.instant_experience_product_metadata_from_selection({'row':{'edition_limit':100}})
        self.assertNotIn('physical_product',plain)
        actual = ads.instant_experience_product_metadata_from_selection({'row':{'edition_limit':100,'size_label':'S - 21 × 30 cm'}})
        self.assertEqual(actual['physical_product'],{'size_label':'S - 21 × 30 cm'})


if __name__ == '__main__':
    unittest.main()
