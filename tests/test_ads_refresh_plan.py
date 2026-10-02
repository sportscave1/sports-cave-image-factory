"""Synthetic references only; no claimed pixel analysis or production performance."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_refresh_plan as plan
import ads_posting_handoff as handoff
import ads_posting_page as posting
import meta_review_handoff as meta
from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules
from tests.test_ads_refresh_workflow import TITLE, ROW, completed_single, winner
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_posting_import_csv import product_records

SCENES = ('bar', 'billiards', 'office', 'lounge', 'gallery')
ROLES = ('recognition', 'fan ownership', 'collector identity', 'display desire', 'edition detail')


def fixture(campaign='Carousel', seed='synthetic-v3'):
    source = winner(campaign == 'Carousel')
    source['carousel_cards'] = [dict(position=i, image_url=f'https://example.fbcdn.net/card{i}.png',
                                   scene=scene, role=role) for i, (scene, role) in enumerate(zip(SCENES, ROLES), 1)]
    context = dict(winning_primary_text='Two legends. One unforgettable rivalry.',
                   winning_headline='Legends Never Die', source_winner=source)
    return ads.build_ads_result_record(TITLE, 'Football', 'Australia', campaign,
        product_id=ROW['shopify_product_id'], product_url=ROW['online_store_url'],
        variation_token=seed, creative_refresh_context=context)


def executions(value):
    selected = value['creative_refresh_context']['refresh_plan']
    carousel = value['campaign_type'] == 'Carousel'
    result = []
    for i in range(1, 6 if carousel else 4):
        reference = selected['references'][i-1 if carousel else 0]
        style = {} if carousel else selected['styles'][i-1]
        scene = reference.get('scene') if carousel else style['name']
        role = reference.get('role') if carousel else 'collector identity'
        prompt = plan.standalone_brief(TITLE, reference['label'], scene=scene, role=role, style=style, detail=carousel and 'detail' in role,
                                      dimensions='1080 x 1080' if carousel else '1024 x 1024')
        result.append(dict(position=i, winner_reference=reference['label'], reference_inspected=True, canonical_inspected=True,
                           observations={k:'Synthetic fixture observation: '+str(scene) for k in ('scene_category','ad_role','defining_objects','composition','product_attention','strengths','clutter','mood_contrast','copy_hook','tone','structure','emotional_appeal')}, scene=scene, role=role,
                           keep=f'Preserve {scene} concept and {role}',
                           change='New architecture/layout, wall materials, camera, furniture and lighting',
                           improvement='Reduce clutter; preserve product prominence',
                           style_id=style.get('id'), image_prompt=prompt,
                           execution=dict(architecture=f'New {scene} architecture {i}', layout=f'New spatial layout {i}',
                                          wall_palette=f'Synthetic palette {i}', wall_material=f'Synthetic material {i}',
                                          camera=f'New composition {i}', furniture=f'New furnishings {i}',
                                          lighting='One coherent side light and restrained glazing', product_placement='Source preserving prominent detail' if carousel and 'detail' in role else 'Dominant mounted artwork')))
    return result


class RefreshPlanTests(unittest.TestCase):
    def test_active_carousel_maps_five_refs_and_canonical_sixth(self):
        value = fixture()
        refs = value['creative_refresh_context']['refresh_plan']['references']
        self.assertEqual([r['label'] for r in refs], [f'WINNER_CARD_{i}' for i in range(1, 6)] + ['CANONICAL_PRODUCT'])
        self.assertEqual([r['scene'] for r in refs[:5]], list(SCENES))
        prompt = value['master_prompt']
        self.assertIn('ATTACHMENT 6 — CANONICAL_PRODUCT', prompt)
        self.assertNotIn('ATTACHMENT 2 — CANONICAL', prompt)
        self.assertIn('ONE refreshed FIVE-CARD', prompt)

    def test_missing_refs_never_assume_card_one_for_all(self):
        refs = plan.reference_map('Carousel', {'image_sha256': 'only-one'})
        self.assertTrue(all(not r['image_sha256'] for r in refs[:5]))
        prompt = ads.build_ads_prompt(TITLE, 'Football', 'Australia', 'Carousel',
                                     creative_refresh_context={'winning_primary_text': 'Copy', 'winning_headline': 'Title'})
        self.assertIn('list every missing labelled image', prompt)
        self.assertIn('One winning image cannot stand in for five', prompt)
        self.assertIn('OS has not analysed winner pixels', prompt)

    def test_partial_reference_keeps_its_original_position(self):
        refs=plan.reference_map('Carousel',{'carousel_cards':[{'position':3,'image_sha256':'actual-card-three'}]})
        self.assertEqual(refs[2]['image_sha256'],'actual-card-three')
        self.assertFalse(refs[0]['image_sha256'])
        self.assertFalse(refs[1]['image_sha256'])

    def test_canonical_authority_exact_in_every_standalone(self):
        value = fixture()
        for row in executions(value):
            self.assertIn(plan.AUTHORITY, row['image_prompt'])
            self.assertIn('PRINTED', value['master_prompt'])
            self.assertIn('not a creative reference', row['image_prompt'])
            self.assertIn('Never reconstruct artwork from a winner', value['master_prompt'])

    def test_full_shared_block_in_all_active_carousel_and_ie_briefs(self):
        block = build_sports_cave_image_realism_rules(include_product_lock=True)
        for campaign, count in [('Carousel', 5), ('Instant Experience', 3)]:
            prompt = fixture(campaign)['master_prompt']
            self.assertEqual(prompt.count(block), count-1 if campaign == 'Carousel' else count)
            if campaign == 'Carousel':
                self.assertIn(build_sports_cave_image_realism_rules(include_product_lock=True, allow_intentional_detail_crop=True), prompt)
            if campaign == 'Instant Experience':
                self.assertEqual(prompt.count(ads.build_instant_experience_fixed_opaque_footer_rules()), 3)
            for row in executions(fixture(campaign)):
                applicable = build_sports_cave_image_realism_rules(include_product_lock=True, allow_intentional_detail_crop=campaign == 'Carousel' and 'detail' in row['role'])
                self.assertIn(applicable, row['image_prompt'])
                for required in ('mitred joins', 'ambient occlusion', 'transparent glass', 'physically', 'every word'):
                    self.assertIn(required, row['image_prompt'])

    def test_scenes_roles_order_preserved_and_new_execution_declared(self):
        value = fixture()
        rows = executions(value)
        self.assertFalse(plan.execution_issues(rows, value['creative_refresh_context']['refresh_plan'], TITLE, 'Carousel'))
        self.assertEqual([r['scene'] for r in rows], list(SCENES))
        self.assertEqual([r['role'] for r in rows], list(ROLES))
        rows[1]['scene'] = 'office'
        self.assertTrue(any('scene anchor changed' in s for s in plan.execution_issues(rows, value['creative_refresh_context']['refresh_plan'], TITLE, 'Carousel')))

    def test_card_one_cannot_stand_in_for_other_cards(self):
        value = fixture(); rows = executions(value)
        rows[4]['winner_reference'] = 'WINNER_CARD_1'
        self.assertTrue(any('wrong winner' in s for s in plan.execution_issues(rows, value['creative_refresh_context']['refresh_plan'], TITLE, 'Carousel')))

    def test_marker_only_and_incomplete_authority_rejected(self):
        value = fixture(); rows = executions(value)
        rows[0]['image_prompt'] = TITLE + plan.AUTHORITY + 'WINNER_CARD_1 SPORTS_CAVE_IMAGE_REALISM_RULES_V1'
        self.assertTrue(any('full shared rules' in s for s in plan.execution_issues(rows, value['creative_refresh_context']['refresh_plan'], TITLE, 'Carousel')))

    def test_supported_detail_role_does_not_require_a_room(self):
        value=fixture(); rows=executions(value)
        rows[-1]['execution']={'camera':'Photographic close detail', 'lighting':'Coherent side lighting',
                               'product_placement':'Exact source edition plaque detail'}
        self.assertFalse(plan.execution_issues(rows,value['creative_refresh_context']['refresh_plan'],TITLE,'Carousel'))
        self.assertIn('INTENTIONAL DETAIL CARD ONLY',rows[-1]['image_prompt'])
        self.assertIn('never redraw',rows[-1]['image_prompt'])

    def test_changed_product_replaces_stale_plan(self):
        value=fixture('Instant Experience'); context=value['creative_refresh_context']
        changed=ads.build_ads_result_record('Different verified product','Cricket','Australia','Instant Experience',
                                           variation_token='different',creative_refresh_context=context)
        self.assertNotEqual(changed['creative_refresh_context']['refresh_plan']['run_id'],context['refresh_plan']['run_id'])
        self.assertEqual(changed['creative_refresh_context']['refresh_plan']['product'],'Different verified product')

    def test_recolour_only_rejected(self):
        value = fixture('Instant Experience'); rows = executions(value)
        rows[1]['execution'] = {**rows[0]['execution'], 'wall_palette': 'another colour'}
        self.assertTrue(any('near-identical planned' in s for s in plan.execution_issues(rows, value['creative_refresh_context']['refresh_plan'], TITLE, 'Instant Experience')))

    def test_declared_winner_room_copy_flagged_without_claiming_pixel_analysis(self):
        value=fixture('Instant Experience'); rows=executions(value)
        rows[0]['observations']['execution']=copy.deepcopy(rows[0]['execution'])
        rows[0]['execution']['wall_palette']='Only paint changed'
        self.assertTrue(any('barely changes the winner' in s for s in plan.execution_issues(rows,value['creative_refresh_context']['refresh_plan'],TITLE,'Instant Experience')))

    def test_thirty_structured_styles_and_product_filter(self):
        self.assertEqual(len(plan.STYLES), 30)
        for style in plan.STYLES:
            self.assertTrue(all(style[k] for k in ('family','architecture','wall_hue','wall_value','wall_material','furniture_materials','lighting','context','exclusions')))
        for i in range(50):
            self.assertNotIn('18', [s['id'] for s in plan.select_styles(i, category='Football')])
        self.assertEqual(len(plan.select_styles('motor', category='Motorsport', eligible_ids=['18','01','02'])), 3)

    def test_ie_three_distinct_styles_and_no_literal_room_lock(self):
        value = fixture('Instant Experience'); selected = value['creative_refresh_context']['refresh_plan']['styles']
        self.assertEqual(len({s['id'] for s in selected}), 3)
        self.assertEqual(len({(s['family'],s['wall_hue']) for s in selected}), 3)
        self.assertIn('not three camera angles in one room', value['master_prompt'])
        self.assertNotIn('Keep the winning room style and composition', value['master_prompt'])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(value['master_prompt'].split('EXACT CSV TEMPLATE\n')[1])))), 3)

    def test_same_family_palette_rejected(self):
        twins = [dict(s, family='same', wall_hue='same') for s in plan.STYLES[:4]]
        with patch.object(plan, 'STYLES', twins), self.assertRaises(ValueError):
            plan.select_styles('seed')

    def test_repeat_style_id_rejected_by_quality_gate(self):
        value = fixture('Instant Experience'); rows = executions(value)
        rows[1]['style_id'] = rows[0]['style_id']
        self.assertTrue(any('repeated style' in s for s in plan.execution_issues(rows, value['creative_refresh_context']['refresh_plan'], TITLE, 'Instant Experience')))

    def test_seed_and_recopy_stable_new_run_avoids_recent(self):
        state = {}; seeds = iter(['one','two'])
        first = plan.session_plan(state, 'identity', {}, 'Instant Experience', TITLE, 'Football', lambda: next(seeds))
        second = plan.session_plan(state, 'identity', {}, 'Instant Experience', TITLE, 'Football', lambda: next(seeds))
        self.assertIs(first, second)
        third = plan.session_plan(state, 'identity', {}, 'Instant Experience', TITLE, 'Football', lambda: next(seeds), new=True)
        self.assertNotEqual(first['run_id'], third['run_id'])
        self.assertFalse({s['id'] for s in first['styles']} & {s['id'] for s in third['styles']})

    def test_restricted_pool_uses_least_recent_first(self):
        selected = plan.select_styles('fixed', eligible_ids=['01','02','03','04'],
                                      history=[{'style_ids':['01']}, {'style_ids':['02']}, {'style_ids':['03']}, {'style_ids':['04']}])
        self.assertEqual([s['id'] for s in selected], ['01','02','03'])

    def test_history_bounded(self):
        state = {}
        for i in range(40):
            plan.session_plan(state, str(i), {}, 'Instant Experience', TITLE, 'Football', lambda: str(i))
        self.assertLessEqual(len(state['ads-refresh-plans']), 30)
        self.assertEqual(len(state['ads-refresh-style-history'][TITLE+'::Instant Experience']), 30)

    def test_trivial_copy_rejected(self):
        for rows in ([{'primary_text':'Own this iconic moment today', 'headline':'Own the moment'},
                      {'primary_text':'Today own this iconic moment', 'headline':'Own a moment'}],
                     [{'description':'Collector art for your wall'}, {'description':'Collector art for your wall'}]):
            self.assertTrue(plan.copy_issues(rows))

    def test_fixed_facts_product_and_cta_may_repeat(self):
        rows = [dict(primary_text=text+' '+TITLE+' Limited to 100', headline=TITLE, cta='Claim Your Edition')
                for text in ('Remember why you became a fan.', 'Make a place for the rivalry.', 'A collection built around your passion.')]
        self.assertFalse(plan.copy_issues(rows, TITLE, fixed_facts=['Limited to 100']))

    def test_source_and_duplicate_bytes_flagged_without_visual_similarity(self):
        digest = hashlib.sha256(b'original').hexdigest()
        self.assertTrue(plan.asset_issues([{'data':b'original'}], [digest]))
        self.assertTrue(plan.asset_issues([{'data':b'new'}, {'data':b'new'}]))
        self.assertFalse(plan.asset_issues([{'data':b'one'}, {'data':b'two'}]))

    def test_no_network_or_storage_for_prompt_generation(self):
        with patch('requests.get', side_effect=AssertionError('network')), patch('requests.post', side_effect=AssertionError('network')):
            self.assertIn(plan.VERSION, fixture()['master_prompt'])
            self.assertIn(plan.VERSION, fixture('Instant Experience')['master_prompt'])

    def test_plan_changes_invalidate_context_but_recopy_preserves_manual_output(self):
        value = fixture('Instant Experience')
        other = fixture('Instant Experience', seed='next')
        self.assertNotEqual(value['context_key'], other['context_key'])
        value['generated_ad_output'] = 'Manual edited copy retained'
        value['prompt_contract_version'] = 'previous version'
        updated = ads.ensure_current_ads_result_prompt(value)
        self.assertEqual(updated['generated_ad_output'], value['generated_ad_output'])
        self.assertEqual(updated['creative_refresh_context']['refresh_plan'], value['creative_refresh_context']['refresh_plan'])

    def test_reference_copy_format_and_product_changes_invalidate(self):
        value = fixture()
        context = copy.deepcopy(value['creative_refresh_context'])
        for field in ('winning_primary_text','winning_headline','source_winner','refresh_plan'):
            changed = copy.deepcopy(context)
            changed[field] = {'different':True} if isinstance(changed[field],dict) else 'changed'
            key = ads.ads_result_context_key(value['product_id'], TITLE, 'Football','Australia','Carousel', creative_refresh_context=changed)
            self.assertNotEqual(key, value['context_key'])

    def test_failed_quality_checks_prevent_any_dropbox_work(self):
        value, workflow = completed_single()
        workflow['ad_notes']['refresh_executions'] = []
        with patch.object(ads.dropbox_integration, 'ensure_folder_path') as remote:
            with self.assertRaisesRegex(ValueError, 'Creative Refresh checks'):
                ads.save_ads_images_to_dropbox('fake','/approved','/approved',value,workflow)
            remote.assert_not_called()

    def test_final_notes_and_plan_survive_save_and_package_hash(self):
        value, workflow = completed_single()
        save_locally(value,workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        handoff.validate_saved_package(package)
        self.assertEqual(package['refresh_executions'],workflow['ad_notes']['refresh_executions'])
        self.assertEqual(package['source_provenance']['refresh_plan'],value['creative_refresh_context']['refresh_plan'])
        self.assertNotIn('refresh_executions', ads.STANDARD_ADS_CSV_HEADERS)
        before = ads._ads_saved_source_signature(value,workflow)
        workflow['ad_notes']['refresh_executions'][0]['change'] = 'Edited after save'
        self.assertNotEqual(before, ads._ads_saved_source_signature(value,workflow))

    def test_real_carousel_save_import_postnow_order_with_fake_storage(self):
        value = fixture(); _, workflow = completed_ad('Carousel','creative_refresh')
        workflow['context_key'] = value['context_key']
        workflow['ad_notes']['refresh_executions'] = executions(value)
        carousel = ads._carousel_copy_notes_from_workflow(value,workflow)
        carousel['primary_texts'] = ['Your rivalry deserves a place.', 'Remember the match that mattered.', 'Make room for a defining memory.', 'Bring the passion into your home.', 'Build a collection around football.']
        carousel['headlines'] = ['Own the rivalry','Remember football','For your collection','A place for passion','Frame a memory']
        carousel['descriptions'] = ['Two football legends','Your sporting story','A collector focus','Built for your wall','The rivalry lives on']
        for card in carousel['cards']:
            card['destination_url'] = value['product_url']
        ads._store_carousel_copy_notes(workflow,carousel)
        with patch.object(ads.st,'session_state',{}):
            data = ads.build_carousel_copy_csv(value,workflow)
            ads.apply_carousel_copy_csv(value,workflow,data)
        save_locally(value,workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        self.assertEqual(len(package['assets']),5)
        self.assertEqual([a['position'] for a in package['assets']],list(range(1,6)))
        self.assertEqual(package['refresh_executions'],executions(value))
        state = {}; handoff.queue_saved_package(package,state=state)
        self.assertTrue(posting.consume_saved_posting_package(ads.build_ads_product_selector_records([ROW]),state=state))
        self.assertEqual(state[handoff.LOADED_KEY]['source_provenance'],value['creative_refresh_context'])

    def test_real_ie_three_pairs_csv_package_and_postnow(self):
        value = fixture('Instant Experience'); _, workflow = completed_ad('Instant Experience','creative_refresh')
        workflow['context_key'] = value['context_key']
        workflow['ad_notes']['refresh_executions'] = executions(value)
        texts = ['A rivalry worth remembering on your wall.', 'Bring your football memories into the room.', 'Build your collection around the moments you love.']
        headlines = ['Own the rivalry','Remember your football','A place for passion']
        for i, concept in enumerate(ads.INSTANT_EXPERIENCE_CONCEPTS):
            workflow['ad_notes']['instant_experience_concepts'][concept['id']] = [dict(primary_text=texts[i],headline=headlines[i],cta='Claim Your Edition')]
        with patch.object(ads.st,'session_state',{}):
            data = ads.build_instant_experience_copy_csv(value,workflow)
            ads.apply_instant_experience_copy_csv(value,workflow,data)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))),3)
        save_locally(value,workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        self.assertEqual(len(package['assets']),3)
        self.assertEqual([len(ad['variations']) for ad in package['batch']['ads']],[1,1,1])
        state={}; handoff.queue_saved_package(package,state=state)
        self.assertTrue(posting.consume_saved_posting_package(ads.build_ads_product_selector_records([ROW]),state=state))
        for i, text in enumerate(texts):
            self.assertEqual(state[posting.PRIMARY_TEXT_KEYS[i]],text)
        self.assertEqual(package['refresh_executions'],workflow['ad_notes']['refresh_executions'])

    def test_csv_standalone_brief_cannot_bypass_full_rules(self):
        value, workflow = completed_single()
        workflow['standard_ads'][0]['image_prompt'] = TITLE + '. Short incomplete brief.'
        self.assertTrue(any('Standard CSV image prompts' in s for s in ads.creative_refresh_quality_issues(value,workflow)))

    def test_declared_analysis_does_not_claim_pixel_fidelity(self):
        value = fixture('Instant Experience')
        self.assertIn('Pending external ChatGPT',value['creative_refresh_context']['refresh_plan']['visual_analysis'])
        self.assertIn('Prompt instructions alone cannot guarantee pixel-perfect fidelity',value['master_prompt'])

    def test_session_style_switch_preserves_other_manual_work(self):
        state={'unrelated-manual-editor':'Keep this'}
        old=plan.session_plan(state,'old',{},'Instant Experience',TITLE,'Football',lambda:'old')
        new=plan.session_plan(state,'new',{},'Instant Experience',TITLE,'Football',lambda:'new')
        self.assertNotEqual(old['run_id'],new['run_id'])
        self.assertEqual(state['unrelated-manual-editor'],'Keep this')
        self.assertIs(plan.session_plan(state,'old',{},'Instant Experience',TITLE,'Football',lambda:'unused'),old)

    def test_new_ads_unchanged_by_refresh_planner(self):
        kwargs = dict(product_url=ROW['online_store_url'], variation_token='new-ads-fixed')
        for campaign in ('Carousel','Instant Experience','Single Image / Video'):
            before = ads.build_ads_prompt(TITLE,'Football','Australia',campaign,**kwargs)
            fixture(campaign)
            after = ads.build_ads_prompt(TITLE,'Football','Australia',campaign,**kwargs)
            self.assertEqual(before,after)
            self.assertNotIn(plan.VERSION,after)

    def test_handoff_preserves_raw_carousel_order_without_deduplication(self):
        from tests.test_meta_review import ad
        import meta_review_analysis as analysis
        selected = ad()
        selected['raw'] = {'creative':{'object_story_spec':{'link_data':{'child_attachments':[
            {'picture':f'https://example.fbcdn.net/{i}.jpg','name':f'Card {i}'} for i in range(1,6)]}}}}
        choices = {k:analysis.component_candidates([selected],k)[0] for k in ('image','primary_text','headline')}
        package = meta.build_package(selected,choices,{},'complete_ad')
        self.assertEqual([c['headline'] for c in package['carousel_cards']],[f'Card {i}' for i in range(1,6)])


if __name__ == '__main__':
    unittest.main()
