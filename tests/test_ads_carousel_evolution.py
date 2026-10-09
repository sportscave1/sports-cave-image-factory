"""Source-relative contracts using offline fixtures; no provider calls or model claims."""
from copy import deepcopy
import csv
import io
import unittest
from unittest.mock import patch

import ads_carousel_evolution as evolution
import ads_page as ads
import ads_refresh_plan as plan
import ads_refresh_saved as saved
import meta_review_creative as creative
from tests.fixtures.carousel_evolution import greg, review, attach_reviews, GREG_CARDS, GREG_ORIGINAL, GREG_REFRESH
from tests.test_ads_posting_handoff import completed_ad, save_locally


class CarouselEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.result, self.copy, self.records = greg()
        self.context = self.result['creative_refresh_context']
        self.refs = self.context['refresh_plan']['references']

    def issues(self):
        return evolution.quality_issues(self.copy, self.records, self.context, self.refs,
            self.result['product_name'], self.result['product_url'], ['Limited to 100'])

    def test_greg_four_cards_and_independent_source_mapping(self):
        self.assertEqual(self.issues(), [])
        self.assertEqual([r['label'] for r in self.refs], [f'WINNER_CARD_{i}' for i in range(1,5)])
        self.assertEqual(len(ads._result_image_slots(self.result)), 4)
        self.assertEqual([r['role'] for r in self.refs], [c[5] for c in GREG_CARDS])
        self.assertEqual([n['source_id'] for n in self.records[0]['shared_copy_review']['primary_texts']],
                         [f'PRIMARY_{i}' for i in range(1,6)])

    def test_active_prompt_has_priority_contract_without_new_ads_priority(self):
        prompt = self.result['master_prompt']
        self.assertIn(evolution.CONTRACT, prompt)
        self.assertLess(prompt.index(evolution.CONTRACT), prompt.index('SOURCE CARDS'))
        for text in ('same argument', '±15%', '±1 word', 'normally within one sentence',
                     'framing remains framing/presentation', 'fan ownership', 'verified edition-limit',
                     'No fixed global sentence count', 'strongest relevant distinct source angles',
                     'no invented variation-level performance', 'PRIMARY_5', 'derived_no_original',
                     'revise only that item', 'all five shared headline variation rows',
                     'all five shared description variation rows'):
            self.assertIn(text, prompt)
        self.assertNotIn('new hook, argument and expression', prompt)
        self.assertNotIn('Do not force generic room language', prompt)
        self.assertNotIn('no more than three sentences', prompt)
        self.assertNotIn('Priority order:', prompt)

    def test_greg_proposed_copy_preserves_roles_and_verified_edition(self):
        cards = self.copy['cards']
        self.assertEqual((cards[0]['headline'], cards[0]['description']), ('Lap Of The Gods', 'Collector Edition'))
        self.assertIn('Gallery', cards[1]['headline']); self.assertIn('Framed', cards[1]['description'])
        self.assertIn('Faithful', cards[2]['headline']); self.assertIn('Cave', cards[2]['description'])
        self.assertEqual(cards[3]['headline'], '100 Editions Only')
        for card in cards:
            for field in ('headline', 'description'):
                self.assertLessEqual(len(card[field]), 17)
                self.assertNotRegex(card[field], r'[.,]')

    def test_greg_primary_keeps_short_lines_and_length(self):
        self.assertEqual(evolution.measures(GREG_ORIGINAL)['words'], 27)
        self.assertEqual(evolution.measures(GREG_REFRESH)['words'], 26)
        for key in ('lines', 'paragraphs', 'fragments'):
            self.assertEqual(evolution.measures(GREG_ORIGINAL)[key], evolution.measures(GREG_REFRESH)[key])
        self.assertNotIn('2003', GREG_REFRESH)

    def test_short_medium_and_long_word_bounds(self):
        for n, target in ((5,(3,7)), (20,(17,23)), (40,(34,46)), (60,(51,69))):
            with self.subTest(n=n):
                self.assertEqual(evolution.bounds(' '.join(['word'] * n)), target)
        self.assertEqual(evolution.measures("Don't re-write — a fan’s story.")['words'], 5)

    def test_primary_gate_uses_mapped_source_not_slot_number(self):
        original = ' '.join(['remember'] * 60) + '.'
        self.context['source_winner']['shared_primary_texts'][4] = original
        self.copy['primary_texts'][0] = ' '.join(['recall'] * 60) + '.'
        catalog,_ = evolution.sources(self.context,self.refs)
        notes = self.records[0]['shared_copy_review']['primary_texts']
        notes[0] = review(catalog['primary_texts'][4],self.copy['primary_texts'][0],1)
        self.copy['primary_texts'][4] = GREG_REFRESH
        notes[4] = review(catalog['primary_texts'][0],GREG_REFRESH,5)
        self.assertFalse(any('words;' in s or 'source selection' in s for s in self.issues()))
        self.copy['primary_texts'][0] = ' '.join(['recall'] * 70) + '.'
        notes[0]['output_text'] = self.copy['primary_texts'][0]
        self.assertTrue(any('required 51–69' in s for s in self.issues()))

    def test_both_ends_of_primary_length_are_enforced(self):
        for size in (3, 60):
            self.copy['primary_texts'][0] = ' '.join(['refresh'] * size)
            self.records[0]['shared_copy_review']['primary_texts'][0]['output_text'] = self.copy['primary_texts'][0]
            self.assertTrue(any('primary_texts 1' in s and 'words;' in s for s in self.issues()))

    def test_source_line_and_sentence_rhythm_gate(self):
        self.copy['primary_texts'][0] = GREG_REFRESH.replace('\n',' ')
        self.records[0]['shared_copy_review']['primary_texts'][0]['output_text'] = self.copy['primary_texts'][0]
        self.assertTrue(any('line-break rhythm' in s for s in self.issues()))

    def test_changed_csv_or_source_invalidates_only_corresponding_review(self):
        self.copy['cards'][1]['headline'] = 'Gallery Pride'
        issues = self.issues()
        self.assertTrue(any('Card 2 headline: review is stale' in s for s in issues))
        self.assertFalse(any(s.startswith('Card 1') for s in issues))
        self.refs[2]['description'] = 'Made For Your Den'
        self.assertTrue(any('Card 3 description: review is stale' in s for s in self.issues()))

    def test_wrong_card_source_mapping_cannot_pass(self):
        self.records[1]['copy_review']['headline']['source_id'] = 'CARD_3_HEADLINE'
        self.assertTrue(any('Card 2 headline: source mapping' in s for s in self.issues()))

    def test_failed_or_unexplained_qualitative_rubric_blocks(self):
        check = self.records[1]['copy_review']['headline']['checks']['strategy']
        check.update(passed=False, reason='Replaced framing with general race history.')
        self.assertTrue(any('Card 2 headline: revise/review strategy' in s for s in self.issues()))
        check.update(passed=True, reason='')
        self.assertTrue(any('revise/review strategy' in s for s in self.issues()))
        self.records[2]['copy_review']['headline']['checks']['emotion']['passed'] = False
        self.assertTrue(any('Card 3 headline: revise/review emotion' in s for s in self.issues()))

    def test_rubric_does_not_claim_semantic_similarity_score(self):
        self.assertIn('not automated semantic certification or numeric similarity scores', self.result['master_prompt'])
        self.assertNotIn('SequenceMatcher', evolution.quality_issues.__code__.co_names)
        self.assertIn('inspect generated images before use', self.result['master_prompt'])

    def test_missing_ambiguous_copy_is_explicit_and_never_fabricated(self):
        self.refs[1]['headline'] = ''
        self.context['source_winner']['shared_primary_texts'] = [{'text':'Ambiguous variant'}]
        catalog, issues = evolution.sources(self.context,self.refs)
        self.assertEqual(catalog['primary_texts'], [])
        self.assertTrue(any('ambiguous' in s for s in issues))
        self.assertTrue(any('Card 2 source headline is missing' in s for s in self.issues()))
        self.assertIn('Stop before producing completed copy/CSV', evolution.instruction(self.context,self.refs))

    def test_more_than_five_sources_require_five_distinct_mappings(self):
        self.context['source_winner']['shared_primary_texts'] += ['Another faithful angle for your wall.', 'Holden memories for a collector.']
        notes = self.records[0]['shared_copy_review']['primary_texts']
        notes[4]['source_id'] = 'PRIMARY_1'
        self.assertTrue(any('five distinct originals' in s for s in self.issues()))

    def test_fewer_sources_allow_explicit_reuse_not_invented_baselines(self):
        self.context['source_winner']['shared_primary_texts'] = [GREG_ORIGINAL]
        self.records = attach_reviews(self.result,self.copy,self.records)
        self.assertFalse(any('source selection' in s for s in self.issues()))
        self.records[0]['shared_copy_review']['primary_texts'][3]['source_id'] = 'PRIMARY_4'
        self.assertTrue(any('primary_texts 4: source mapping' in s for s in self.issues()))

    def test_shared_options_have_individual_original_baselines_when_available(self):
        source = self.context['source_winner']
        source['shared_headlines'] = ['Recall The Mountain', 'Holden In Your Heart', 'The Bathurst Flashback', 'For Real Fans', 'Remember Your Motorsport']
        source['shared_descriptions'] = ['Remember this lap', 'Loyal to Holden', 'Hear it again', 'A fans collection', 'A racing memory']
        self.records = attach_reviews(self.result,self.copy,self.records)
        self.assertFalse(self.issues())
        note = self.records[0]['shared_copy_review']['headlines'][0]
        self.assertEqual((note['source_id'],note['baseline_kind']), ('HEADLINE_1','original'))
        self.copy['headlines'][0] = 'This explanatory paragraph is much too long for the original shared headline'
        note['output_text'] = self.copy['headlines'][0]
        self.assertTrue(any('headlines 1' in s and 'words;' in s for s in self.issues()))

    def test_absent_shared_options_explicitly_derived_without_card_char_limit(self):
        self.assertGreater(len(self.copy['headlines'][1]),17)
        self.assertFalse(self.issues())
        self.assertTrue(all(n['baseline_kind']=='derived_no_original' for n in self.records[0]['shared_copy_review']['headlines']))
        self.records[0]['shared_copy_review']['headlines'][0]['baseline_kind'] = 'original'
        self.assertTrue(any('wrong output/source/baseline' in s for s in self.issues()))

    def test_card_word_counts_characters_and_punctuation(self):
        for bad in ('This headline is too long', 'Gallery, Framed', 'Gallery Framed.', 'Art'):
            self.copy['cards'][0]['headline'] = bad
            self.records[0]['copy_review']['headline']['output_text'] = bad
            self.assertTrue(any(s.startswith('Card 1 headline:') for s in self.issues()),bad)

    def test_verified_edition_not_remaining_stock_or_different_limit(self):
        for bad in ('Only 20 Left', '100 Left', '200 Editions Only', 'Rare Editions'):
            self.copy['cards'][3]['headline'] = bad
            self.records[3]['copy_review']['headline']['output_text'] = bad
            self.assertTrue(any('claims' in s and s.startswith('Card 4 headline') or 'stock/demand' in s for s in self.issues()),bad)

    def test_unchanged_sentences_rejected_but_product_identity_permitted(self):
        self.assertFalse(self.issues()) # Lap Of The Gods is protected identity.
        self.copy['primary_texts'][0] = GREG_ORIGINAL
        self.records[0]['shared_copy_review']['primary_texts'][0]['output_text'] = GREG_ORIGINAL
        self.assertTrue(any('unchanged sentence' in s for s in self.issues()))

    def test_stock_guard_does_not_reject_fan_language_using_left(self):
        self.copy['primary_texts'][4] = 'Remember the lap that left every Bathurst fan speechless.'
        note = self.records[0]['shared_copy_review']['primary_texts'][4]
        note['output_text'] = self.copy['primary_texts'][4]
        self.assertFalse(any('stock/demand' in s for s in self.issues()))

    def test_generic_additions_and_new_emojis_rejected(self):
        for value in ('Transform your space with that mountain memory.', 'Keep that mountain memory close 🏆'):
            self.copy['primary_texts'][4] = value
            self.records[0]['shared_copy_review']['primary_texts'][4]['output_text'] = value
            self.assertTrue(any('marketing addition' in s or 'emojis' in s for s in self.issues()))

    def test_complete_shared_output_counts_no_blank_cells(self):
        for group in ('primary_texts','headlines','descriptions'):
            value = self.copy[group].pop()
            self.assertTrue(any('exactly five populated' in s for s in self.issues()))
            self.copy[group].append(value)
            self.copy[group][0], old = '', self.copy[group][0]
            self.assertTrue(any('populate the production' in s for s in self.issues()))
            self.copy[group][0] = old

    def test_visual_collective_references_scene_and_role_continuity(self):
        for record in self.records:
            prompt = record['image_prompt']
            for i in range(1,5): self.assertIn(f'WINNER_CARD_{i}',prompt)
            self.assertIn('square 1080 x 1080', prompt)
            self.assertIn('source-preserving', prompt)
            self.assertIn('Redesign architecture and layout', prompt)
        self.assertFalse(plan.execution_issues(self.records,self.context['refresh_plan'],self.result['product_name'],'Carousel'))
        self.records[1]['scene'] = 'office'
        self.assertTrue(any('scene anchor changed' in s for s in plan.execution_issues(self.records,self.context['refresh_plan'],self.result['product_name'],'Carousel')))

    def test_visual_review_and_card_order_required(self):
        self.records[2]['visual_review']['passed'] = False
        self.copy['cards'][0], self.copy['cards'][1] = self.copy['cards'][1], self.copy['cards'][0]
        self.assertTrue(any('review visual continuity' in s for s in self.issues()))
        self.assertTrue(any('preserve source/card/slot order' in s for s in self.issues()))

    def test_wrong_destination_never_inherited_from_source(self):
        self.assertTrue(all(c['destination_url'] == self.result['product_url'] for c in self.copy['cards']))
        self.copy['cards'][0]['destination_url'] = self.context['source_winner']['carousel_cards'][0]['destination_url']
        self.assertTrue(any('verified selected product destination' in s for s in self.issues()))

    def workflow(self):
        _, workflow = completed_ad('Carousel','creative_refresh')
        workflow['context_key'] = self.result['context_key']
        workflow['slots'] = dict(list(workflow['slots'].items())[:4])
        workflow['ad_notes']['refresh_executions'] = deepcopy(self.records)
        ads._store_carousel_copy_notes(workflow,self.copy,self.result)
        return workflow

    def test_csv_roundtrip_exact_headers_rows_urls_and_copy(self):
        workflow = self.workflow()
        data = ads.build_carousel_copy_csv(self.result,workflow)
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        rows = list(reader)
        self.assertEqual(reader.fieldnames,list(ads.CAROUSEL_COPY_CSV_HEADERS))
        self.assertEqual(len(rows),20)
        self.assertEqual([r['slot_id'] for r in rows if r['row_type']=='card'],[f'carousel-{i:02d}' for i in range(1,5)])
        parsed = ads.parse_carousel_copy_csv(data,self.result)
        for group in ('primary_texts','headlines','descriptions'):
            self.assertEqual(parsed[group],self.copy[group])
        self.assertNotIn('source_analysis',data.decode('utf-8-sig'))
        self.assertTrue(all(c['destination_url']==self.result['product_url'] for c in parsed['cards']))
        self.assertFalse(ads.creative_refresh_quality_issues(self.result,workflow))

    def test_gate_blocks_save_before_any_write_preserves_work(self):
        workflow = self.workflow()
        workflow['ad_notes']['carousel']['cards'][1]['headline'] = 'Mount Panorama'
        before = deepcopy(workflow)
        with patch.object(ads.dropbox_integration,'upload_batch',side_effect=AssertionError('No write')):
            with self.assertRaisesRegex(ValueError,'review is stale'):
                save_locally(self.result,workflow)
        self.assertEqual(workflow['slots'],before['slots'])
        self.assertEqual(workflow['ad_notes']['refresh_executions'],before['ad_notes']['refresh_executions'])
        for after, original in zip(workflow['ad_notes']['carousel']['cards'],before['ad_notes']['carousel']['cards']):
            for field in ('headline','description','destination_url'):
                self.assertEqual(after[field],original[field])

    def test_workspace_roundtrip_keeps_mapping_and_hash_detects_edits(self):
        workflow = self.workflow()
        old = ads._ads_saved_source_signature(self.result,workflow)
        state = {}
        saved.restore(saved.dumps(self.result,workflow),state)
        restored = state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]
        self.assertEqual(restored['ad_notes']['refresh_executions'],self.records)
        restored['ad_notes']['refresh_executions'][0]['copy_review']['headline']['selection_reason'] = 'Edited'
        self.assertNotEqual(old,ads._ads_saved_source_signature(self.result,restored))

    def test_four_card_save_retains_all_four_and_existing_posting_limit(self):
        workflow = self.workflow()
        uploaded = save_locally(self.result,workflow)
        exported = next(data for name,data in uploaded.items() if name.endswith(ads.CAROUSEL_COPY_FILENAME))
        self.assertEqual(len(ads.parse_carousel_copy_csv(exported,self.result)['cards']),4)
        self.assertEqual(len(workflow['slots']),4)
        self.assertIn('five-card',workflow.get('posting_package_error',''))
        self.assertTrue(any(name.endswith(saved.FILENAME) for name in uploaded))

    def test_meta_shared_options_survive_complete_winner_handoff(self):
        from tests.test_meta_review_creative import inline, package
        raw = inline(4)
        raw['asset_feed_spec'] = {'titles':[{'text':'Original shared headline'}],
                                  'descriptions':[{'text':'Original shared description'}]}
        source = package(raw)
        self.assertEqual(source['shared_headlines'],['Shared headline','Original shared headline'])
        self.assertEqual(source['shared_descriptions'],['Original shared description'])

    def test_active_ui_new_copy_review_blocks_save_then_recovers(self):
        import json
        from tests.test_ads_refresh_repair import app_for, button
        app = app_for()
        self.assertFalse(button(app,'Save now').disabled)
        original = deepcopy(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['ad_notes']['carousel'])
        editor = next(t for t in app.text_area if t.label=='Card execution notes (JSON)')
        records = json.loads(editor.value)
        records[1]['copy_review']['headline']['checks']['strategy']['passed'] = False
        editor.set_value(json.dumps(records)).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(button(app,'Save now').disabled)
        self.assertEqual(app.session_state[ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY]['ad_notes']['carousel'],original)
        records[1]['copy_review']['headline']['checks']['strategy']['passed'] = True
        next(t for t in app.text_area if t.label=='Card execution notes (JSON)').set_value(json.dumps(records)).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(button(app,'Save now').disabled)

    def test_old_plans_keep_compatibility_but_new_prompts_upgrade(self):
        old = deepcopy(self.context)
        old['refresh_plan'].pop('copy_contract')
        updated = plan.current_plan(old,'Carousel',self.result['product_name'],self.result['category'],'seed')
        self.assertEqual(updated['copy_contract'],evolution.CONTRACT)
        with patch.object(evolution,'quality_issues',side_effect=AssertionError('Historical package must not opt in')):
            result = {**self.result,'creative_refresh_context':old}
            ads.creative_refresh_quality_issues(result,self.workflow())

    def test_meta_normalisation_retains_available_shared_options(self):
        raw = {'id':'123','asset_feed_spec':{'bodies':[{'text':'A winning body'}],
            'titles':[{'text':'Original shared title'}], 'descriptions':[{'text':'Original shared description'}]},
            'object_story_spec':{'link_data':{'child_attachments':[
                {'name':'One','description':'First','image_hash':'hash1'},
                {'name':'Two','description':'Second','image_hash':'hash2'}]}}}
        source = creative.normalize(raw,images={'hash1':'https://example.fbcdn.net/one.png','hash2':'https://example.fbcdn.net/two.png'})
        self.assertEqual(source['shared_headlines'],['Original shared title'])
        self.assertEqual(source['shared_descriptions'],['Original shared description'])

    def test_malformed_review_data_fails_closed(self):
        for bad in (None, {}, [None]*4, [{'shared_copy_review':[]},None,None,None]):
            self.records = bad
            self.assertTrue(self.issues())


if __name__ == '__main__':
    unittest.main()
