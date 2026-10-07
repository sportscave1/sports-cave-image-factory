"""Active Carousel Refresh contracts; synthetic evidence, no network or mutations."""
import copy
import csv
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_refresh_generation as generation
import ads_refresh_plan as plan
import meta_review_handoff as handoff
import meta_review_products as products
from tests.test_ads_refresh_workflow import ROW, TITLE, winner
from tests.test_ads_refresh_plan import fixture, executions


class CarouselRefreshGenerationTests(unittest.TestCase):
    def test_new_handoff_replaces_product_url_copy_and_workflow(self):
        source = winner(True)
        state = {handoff.PENDING: source, ads.ADS_PRODUCT_NAME_KEY: 'Old product',
                 ads.ADS_PRODUCT_URL_KEY: 'https://sportscave.com.au/products/old',
                 ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY: True,
                 ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY: {'old': True},
                 ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY: {'old': True}}
        handoff.hydrate(state)
        self.assertEqual(state[ads.ADS_PRODUCT_NAME_KEY], TITLE)
        self.assertEqual(state[ads.ADS_PRODUCT_URL_KEY], ROW['online_store_url'])
        self.assertEqual(state[ads.ADS_PRODUCT_SELECTOR_KEY], ads._edition_ops_product_selector_identity(ROW))
        self.assertEqual((state['ads_category'], state['ads_country'], state['ads_campaign_type']), ('Football', 'Australia', 'Carousel'))
        self.assertEqual(state[handoff.ACTIVE]['carousel_cards'], source['carousel_cards'])
        self.assertNotIn(ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY, state)
        self.assertNotIn(ads.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY, state)
        self.assertFalse(state[ads.ADS_PRODUCT_URL_MANUALLY_EDITED_KEY])

    def test_rerender_does_not_reset_manual_url(self):
        state = {handoff.PENDING: winner(True)}
        handoff.hydrate(state)
        state[ads.ADS_PRODUCT_URL_KEY] += '?manual=1'
        self.assertFalse(handoff.hydrate(state))
        self.assertTrue(state[ads.ADS_PRODUCT_URL_KEY].endswith('?manual=1'))

    def test_category_field_without_sport_hydrates(self):
        source = winner(True)
        source['product_mapping'].pop('sport')
        source['market'] = 'GB'
        state = {handoff.PENDING: source}
        handoff.hydrate(state)
        self.assertEqual((state['ads_category'], state['ads_country']), ('Football', 'UK'))

    def test_wrong_product_and_wrong_url_block_actual_prompt(self):
        context = dict(winning_primary_text='Source', winning_headline='Headline', source_winner=winner(True))
        for name, url in [('Wrong product', ROW['online_store_url']), (TITLE, 'https://sportscave.com.au/products/wrong')]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'do not match'):
                ads.build_ads_result_record(name, 'Football', 'Australia', 'Carousel', product_url=url, creative_refresh_context=context)

    def test_market_host_and_tracking_query_do_not_create_false_mismatch(self):
        url = 'https://www.sportscaveshop.com/products/' + ROW['product_handle'] + '?utm_source=meta'
        self.assertFalse(generation.carousel_identity_issue(TITLE, url, winner(True)))

    def test_unverified_handoff_requires_product_confirmation(self):
        source = winner(True); source['product_mapping'] = {}
        self.assertIn('Confirm', generation.carousel_identity_issue(TITLE, ROW['online_store_url'], source))

    def test_common_cards_precede_historic_posting(self):
        source = winner(True); source.pop('product_mapping')
        for card in source['carousel_cards']:
            card['destination_url'] = ROW['online_store_url'] + '?utm_source=meta'
        other = dict(ROW, product_title='Other', product_handle='other', shopify_product_id='other')
        outcome = products.resolve(source, [ROW, other], postings=[{'ad_id':source['ad_id'], 'product_handle':'other'}])
        self.assertEqual(outcome['product']['product_handle'], ROW['product_handle'])
        self.assertEqual(outcome['method'], 'common carousel product destination')

    def test_confirmed_mapping_precedes_cards(self):
        source = winner(True)
        for card in source['carousel_cards']: card['destination_url'] = 'https://sportscave.com.au/products/other'
        self.assertEqual(products.resolve(source, [ROW])['product']['product_title'], TITLE)

    def test_ambiguous_card_destinations_do_not_guess_from_name(self):
        source = winner(True); source.pop('product_mapping'); source['campaign_name'] = TITLE
        source['carousel_cards'][0]['destination_url'] = ROW['online_store_url']
        self.assertIsNone(products.resolve(source, [ROW])['product'])

    def test_verified_handle_fallback(self):
        source = winner(True); source.pop('product_mapping'); source['product_handle'] = ROW['product_handle']
        self.assertEqual(products.resolve(source, [ROW])['product']['product_title'], TITLE)

    def test_exact_order_only_five_references_and_standalone_prompts(self):
        value = fixture(); prompt = value['master_prompt']
        self.assertEqual([r['label'] for r in value['creative_refresh_context']['refresh_plan']['references']], [f'WINNER_CARD_{i}' for i in range(1,6)])
        for i in range(1,6): self.assertIn(f'Image {i} = Card {i} = WINNER_CARD_{i}', prompt)
        self.assertNotIn('CANONICAL_PRODUCT', prompt)
        self.assertNotIn('ATTACHMENT 6', prompt)
        self.assertEqual(prompt.count('PRODUCT: '+TITLE), 5)
        self.assertIn('EXACTLY 5 COMPLETE STANDALONE IMAGE PROMPTS', prompt)

    def test_matching_card_copy_and_separate_primary_pool(self):
        source = winner(True)
        source['shared_primary_texts'] = [f'Source primary {i}' for i in range(1,6)]
        for i, card in enumerate(source['carousel_cards'],1):
            card.update(headline=f'Unique headline {i}', description=f'Unique description {i}')
        context = dict(winning_primary_text='Source primary 1', winning_headline='Shared headline', source_winner=source)
        value = ads.build_ads_result_record(TITLE,'Football','Australia','Carousel',product_url=ROW['online_store_url'],creative_refresh_context=context)
        refs = value['creative_refresh_context']['refresh_plan']['references']
        for i, ref in enumerate(refs,1):
            self.assertEqual((ref['headline'],ref['description']), (f'Unique headline {i}',f'Unique description {i}'))
            self.assertIn(f'Source primary {i}', value['master_prompt'])

    def test_same_family_new_execution_and_realism(self):
        prompt = fixture()['master_prompt']
        for family in ('bedroom', 'man cave', 'office', 'lounge'):
            self.assertIn(f'{family} -> new {family}', prompt)
        for phrase in ('detail-role -> new detail execution','INDIVIDUAL WINNER ANALYSIS','collectively supply the immutable product authority',
                       'glass','bevel','contact shadow','ambient occlusion','wall separation','every word','mitred joins'):
            self.assertIn(phrase,prompt)

    def test_exact_csv_schema_and_five_shared_variations(self):
        value=fixture(); text=value['master_prompt'].split('EXACT CSV TEMPLATE\n',1)[1]
        reader=csv.DictReader(io.StringIO(text)); rows=list(reader)
        self.assertEqual(reader.fieldnames,list(ads.CAROUSEL_COPY_CSV_HEADERS))
        self.assertEqual([int(r['position']) for r in rows if r['row_type']=='card'],list(range(1,6)))
        self.assertEqual(sum(r['row_type']=='primary_text' for r in rows),5)
        parsed=ads.parse_carousel_copy_csv(text.encode('utf-8-sig'), value)
        self.assertEqual(len(parsed['cards']),5)
        self.assertEqual(len(ads._result_image_slots(value)),5)

    def test_missing_or_noncontiguous_source_fails_closed(self):
        for field in ('image_url','position'):
            source=winner(True); source['carousel_cards'][2].pop(field)
            with self.assertRaisesRegex(ValueError, 'Complete winning Carousel required. Reload the winner from Meta Review.'):
                plan.reference_map('Carousel',source)

    def test_old_session_plan_is_replaced(self):
        state={}; ctx={'source_winner':winner(True)}
        old=plan.session_plan(state,'same',ctx,'Carousel',TITLE,'Football',lambda:'seed')
        old['references'].append({'label':'CANONICAL_PRODUCT'})
        current=plan.session_plan(state,'same',ctx,'Carousel',TITLE,'Football',lambda:'unused')
        self.assertEqual(len(current['references']),5)

    def test_uninspected_or_generic_execution_is_not_ready(self):
        value=fixture(); records=executions(value); selected=value['creative_refresh_context']['refresh_plan']
        self.assertFalse(plan.execution_issues(records,selected,TITLE,'Carousel'))
        records[0]['collective_product_inspected']=False
        self.assertTrue(plan.execution_issues(records,selected,TITLE,'Carousel'))
        records=executions(value); records[0]['execution']={k:'TBD' for k in records[0]['execution']}
        self.assertTrue(plan.execution_issues(records,selected,TITLE,'Carousel'))

    def test_recolour_only_fails(self):
        value=fixture(); records=executions(value)
        records[0]['observations']['execution']=copy.deepcopy(records[0]['execution'])
        records[0]['execution']['wall_palette']='A new colour only'
        self.assertTrue(any('recolour' in s for s in plan.execution_issues(records,value['creative_refresh_context']['refresh_plan'],TITLE,'Carousel')))

    def test_source_copy_and_reordered_words_fail(self):
        context={'source_winner':{'carousel_cards':[{'headline':'Make room for a champion'}], 'shared_primary_texts':['Your wall tells the story of your sporting life']}}
        self.assertTrue(plan.copy_issues([{'headline':'A champion make room for'}],winner=context))
        self.assertTrue(plan.copy_issues([{'primary_text':'Your wall tells the story of your sporting life!'}],winner=context))

    def test_verified_fixed_facts_can_repeat(self):
        rows=[{'headline': 'Limited to 100'}, {'headline': 'Limited to 100'}]
        self.assertFalse(plan.copy_issues(rows,fixed_facts=['Limited to 100']))
        self.assertTrue(plan.copy_issues(rows))

    def test_product_guard_in_active_form_blocks_stale_url(self):
        # The same pure guard is used before Submit and by the actual prompt builder.
        source=Path(ads.__file__).read_text(encoding='utf-8')
        self.assertIn('creative_refresh_message = ads_refresh_generation.carousel_identity_issue(',source)
        self.assertIn('elif creative_refresh_message:',source)

    def test_current_prompt_migrates_old_six_reference_plan(self):
        value=fixture()
        value['prompt_contract_version']='old'
        value['creative_refresh_context']['refresh_plan']['references'].append({'label':'CANONICAL_PRODUCT'})
        updated=ads.ensure_current_ads_result_prompt(value)
        self.assertNotIn('CANONICAL_PRODUCT',updated['master_prompt'])
        self.assertEqual(len(updated['creative_refresh_context']['refresh_plan']['references']),5)

    def test_legacy_manual_prompt_still_requests_complete_references(self):
        context={'winning_primary_text':'Old copy','winning_headline':'Old headline'}
        prompt=ads.build_ads_prompt(TITLE,'Football','Australia','Carousel',creative_refresh_context=context)
        self.assertIn('legacy manual winner',prompt)
        self.assertEqual(prompt.count('PRODUCT: '+TITLE),5)

    def test_noncarousel_authority_unchanged_and_no_network(self):
        with patch('requests.get',side_effect=AssertionError('network')), patch('requests.post',side_effect=AssertionError('mutation')):
            for kind in ('Instant Experience','Single Image / Video'):
                value=fixture(kind)
                self.assertIn('CANONICAL_PRODUCT',value['master_prompt'])
                self.assertNotIn(plan.CAROUSEL_CONTRACT,value['master_prompt'])
            fixture()

    def test_active_form_hides_product_reference_and_switch_restores_it(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('''
from unittest.mock import patch
import streamlit as st
import ads_page as ads
import meta_review_handoff as handoff
from tests.test_ads_refresh_workflow import winner, ROW
if 'seeded' not in st.session_state:
    st.session_state[handoff.PENDING]=winner(True)
    st.session_state['seeded']=True
def source(st):
    handoff.hydrate(st.session_state)
    return True
with patch.object(handoff,'render_source',side_effect=source), patch.object(ads,'load_edition_ops_product_rows',return_value=[ROW]):
    ads.render_page('creative_refresh')
''').run(timeout=30)
        self.assertFalse(app.exception)
        self.assertNotIn('Find product image',[b.label for b in app.get('link_button')])
        url_input=next(t for t in app.text_input if t.label=='Product page URL *')
        self.assertEqual(products.product_url_handle(url_input.value),ROW['product_handle'])
        url_input.set_value('https://sportscave.com.au/products/wrong-product').run(timeout=30)
        next(b for b in app.button if b.label=='Submit').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('do not match' in w.value for w in app.warning))
        self.assertNotIn(ads.ADS_CREATIVE_REFRESH_RESULT_STATE_KEY, app.session_state)
        next(s for s in app.selectbox if s.label=='Campaign type').set_value('Instant Experience').run(timeout=30)
        self.assertFalse(app.exception)
        self.assertIn('Find product image',[b.label for b in app.get('link_button')])


if __name__=='__main__':
    unittest.main()
