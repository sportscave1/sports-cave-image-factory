"""Synthetic Graph fixtures; every network/storage operation is mocked."""
from copy import deepcopy
import csv
import io
import unittest
from unittest.mock import patch

import meta_review_creative as creative
import meta_review_live as live
import meta_review_analysis as analysis
import meta_review_handoff as handoff
import ads_page as ads
import ads_refresh_plan as plan
from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules

CONFIG = {'configured': True, 'ad_account_id': 'act_123', 'api_version': 'v26.0', 'access_token': 'synthetic-secret'}


def inline(n=5):
    return {'id': '1234', 'name': 'An IE name must not override cards',
            'object_story_spec': {'link_data': {'message': 'Shared collector message',
                'name': 'Shared headline', 'multi_share_optimized': True, 'multi_share_end_card': True,
                'child_attachments': [{'image_hash': f'h{i}', 'picture': f'https://fixture.fbcdn.net/card{i}.jpg',
                    'name': f'Headline {i}', 'description': f'Description {i}',
                    'link': f'https://example.com/products/card{i}', 'call_to_action': {'type': 'SHOP_NOW'}}
                    for i in range(1, n+1)]}}}


def package(raw):
    resolved = creative.normalize(raw)
    ad = {'ad_id': '55', 'ad_name': 'Carousel', 'adset_id': '66',
          'assets': analysis.creative_assets(raw), 'raw': {'creative': raw},
          'winning_creative': resolved, 'metrics': {}, 'decision': {}}
    picks = {kind: {'ad_id': '55', 'value': value} for kind, value in
             [('image', resolved['cards'][0]['image_url']), ('primary_text', 'Shared collector message'), ('headline', 'Shared headline')]}
    return handoff.build_package(ad, picks, {'campaign_id': '77', 'date_range': 'synthetic'}, 'complete_ad')


class FormatTests(unittest.TestCase):
    def test_inline_counts_and_copy_order(self):
        for n in (4, 5, 6):
            with self.subTest(n=n):
                value = creative.normalize(inline(n))
                self.assertEqual(value['creative_format'], 'CAROUSEL')
                self.assertEqual(value['creative_format_confidence'], 'deterministic')
                self.assertEqual(len(value['cards']), n)
                self.assertEqual([c['headline'] for c in value['cards']], [f'Headline {i}' for i in range(1, n+1)])
                self.assertEqual([c['description'] for c in value['cards']], [f'Description {i}' for i in range(1, n+1)])
                self.assertEqual(len({c['identity'] for c in value['cards']}), n)
                self.assertTrue(value['multi_share_optimized'])
                # The end-card flag alone never deletes a real authored card.
                self.assertEqual(value['cards'][-1]['position'], n)

    def test_existing_post_cards_and_explicit_profile_end_card(self):
        story = {'attachments': {'data': [{'type': 'album', 'subattachments': {'data': [
            {'type': 'photo', 'target': {'id': str(i)}, 'media': {'image': {'src': f'https://fixture.fbcdn.net/{i}.jpg'}},
             'title': f'Headline {i}', 'description': f'Description {i}'} for i in range(1, 5)] + [{'type': 'profile'}]}}]}}
        value = creative.normalize({'id': '1234', 'effective_object_story_id': '1_2',
                                    'object_story_spec': {'link_data': {'multi_share_end_card': True}}}, story)
        self.assertEqual(value['creative_format'], 'CAROUSEL')
        self.assertEqual(len(value['cards']), 4)
        self.assertEqual(value['cards'][2]['source_id'], '3')
        self.assertIn('subattachments', value['creative_format_source'])

    def test_canvas_is_concrete_destination_evidence(self):
        raw = {'id': '1234', 'object_story_spec': {'link_data': {'link': 'https://www.facebook.com/canvas/123'}}}
        self.assertEqual(creative.normalize(raw)['creative_format'], 'INSTANT_EXPERIENCE')

    def test_one_image_is_not_ie(self):
        self.assertEqual(creative.normalize({'id': '1', 'image_url': 'https://fixture.fbcdn.net/image.jpg'})['creative_format'], 'SINGLE_IMAGE')

    def test_thumbnail_and_names_are_unknown(self):
        self.assertEqual(creative.normalize({'name': 'Instant Experience Carousel', 'thumbnail_url': 'https://fixture.fbcdn.net/t.jpg'})['creative_format'], 'UNKNOWN')

    def test_unresolved_existing_post_is_unknown(self):
        self.assertEqual(creative.normalize({'effective_object_story_id': '1_2', 'image_url': 'https://fixture.fbcdn.net/cover.jpg'})['creative_format'], 'UNKNOWN')

    def test_video(self):
        self.assertEqual(creative.normalize({'video_id': '123'})['creative_format'], 'VIDEO')

    def test_dynamic_alternatives_are_not_carousel(self):
        raw = inline()
        raw['asset_feed_spec'] = {'ad_formats': ['CAROUSEL'], 'images': [{'hash': 'one'}, {'hash': 'two'}]}
        value = creative.normalize(raw)
        self.assertEqual(value['creative_format'], 'DYNAMIC_CAROUSEL')
        self.assertEqual(len(value['cards']),5)
        raw['object_story_spec']['link_data'].pop('child_attachments')
        self.assertEqual(creative.normalize(raw)['creative_format'],'DYNAMIC')
        self.assertEqual(creative.normalize(raw)['cards'],[])

    def test_carousel_destination_does_not_replace_cover_format(self):
        raw = inline()
        raw['object_story_spec']['link_data']['link'] = 'https://www.facebook.com/canvas/123'
        self.assertEqual(creative.normalize(raw)['creative_format'], 'CAROUSEL')

    def test_empty_child_entries_do_not_prove_carousel(self):
        self.assertEqual(creative.normalize({'object_story_spec': {'link_data': {'child_attachments': [{}, {}]}}})['creative_format'], 'UNKNOWN')

    def test_malformed_payload(self):
        for raw in (None, [], {'object_story_spec': 'broken'}, {'asset_feed_spec': 'broken'}):
            self.assertEqual(creative.normalize(raw)['creative_format'], 'UNKNOWN')

    def test_unavailable_card_preserves_position_copy(self):
        raw = inline()
        del raw['object_story_spec']['link_data']['child_attachments'][2]['picture']
        value = creative.normalize(raw)
        self.assertEqual(len(value['cards']), 5)
        self.assertTrue(value['cards'][2]['image_unavailable'])
        self.assertEqual(value['cards'][2]['headline'], 'Headline 3')
        self.assertEqual(value['cards'][3]['position'], 4)

    def test_mixed_campaign(self):
        self.assertEqual(creative.campaign_format([creative.normalize(inline()), creative.normalize({'video_id': '1'})]), 'MIXED')

    def test_url_rotation_does_not_change_card_identity(self):
        raw = inline()
        before = creative.normalize(raw)['cards'][0]['identity']
        raw['object_story_spec']['link_data']['child_attachments'][0]['picture'] += '?new=1'
        self.assertEqual(before, creative.normalize(raw)['cards'][0]['identity'])


class RetrievalTests(unittest.TestCase):
    def test_one_creative_read_all_inline_cards_no_writes(self):
        raw = inline(6)
        for card in raw['object_story_spec']['link_data']['child_attachments']:
            card.pop('image_hash')
        with patch.object(live.meta, '_request', return_value=raw) as get:
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(len(value['cards']), 6)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs['params']['fields'], creative.CREATIVE_FIELDS)

    def test_missing_hashes_resolved_in_one_batch(self):
        raw = inline(6)
        for card in raw['object_story_spec']['link_data']['child_attachments']:
            del card['picture']
        images = {'data': [{'hash': f'h{i}', 'url': f'https://fixture.fbcdn.net/full{i}.jpg'} for i in range(1, 7)]}
        with patch.object(live.meta, '_request', side_effect=[raw, images]) as get:
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(get.call_count, 2)
        self.assertEqual(len(__import__('json').loads(get.call_args.kwargs['params']['hashes'])), 6)
        self.assertFalse(any(c['image_unavailable'] for c in value['cards']))

    def test_story_permission_failure_does_not_guess(self):
        with patch.object(live.meta, '_request', side_effect=[{'id': '1234', 'effective_object_story_id': '1_2'}, ValueError('token secret')]):
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(value['creative_format'], 'UNKNOWN')
        self.assertNotIn('secret', str(value['warnings']))

    def test_partial_story_pagination_fails_closed(self):
        story = {'attachments': {'data': [], 'paging': {'next': 'token'}}}
        with patch.object(live.meta, '_request', side_effect=[{'id': '1234', 'object_story_id': '1_2'}, story]):
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(value['creative_format'], 'UNKNOWN')

    def test_scope_cache_reuses_resolution(self):
        cache, calls = {}, []
        def load():
            calls.append(1)
            return creative.normalize(inline())
        key = (live.scope(CONFIG), 'creative', '1234')
        live.cached_read(cache, key, load)
        live.cached_read(cache, key, load)
        self.assertEqual(calls, [1])

    def test_best_hash_url_beats_preview_picture(self):
        raw = inline(4)
        value = creative.normalize(raw, images={'h1': 'https://fixture.fbcdn.net/original.jpg'})
        self.assertEqual(value['cards'][0]['image_url'], 'https://fixture.fbcdn.net/original.jpg')

    def test_existing_post_lazy_read_preserves_all_cards(self):
        story = {'message': 'Shared post message', 'attachments': {'data': [{'subattachments': {'data': [
            {'type': 'photo', 'title': f'Card {i}', 'media': {'image': {'src': f'https://fixture.fbcdn.net/{i}.jpg'}}}
            for i in range(1, 7)]}}]}}
        with patch.object(live.meta, '_request', side_effect=[{'id': '1234', 'effective_object_story_id': '1_2'}, story]) as get:
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(get.call_count, 2)
        self.assertEqual(len(value['cards']), 6)
        self.assertEqual(value['shared_primary_text'], 'Shared post message')


class SourceUITests(unittest.TestCase):
    def test_all_cards_and_copy_render_no_network(self):
        from streamlit.testing.v1 import AppTest
        def app(n):
            import streamlit as st
            from tests.test_meta_review_creative import inline
            import meta_review_creative
            meta_review_creative.render_cards(st, meta_review_creative.normalize(inline(n)))
        for n in (4, 5, 6):
            with patch.object(live.meta, '_request', side_effect=AssertionError('network')), patch.object(handoff.requests, 'get', side_effect=AssertionError('download')):
                at = AppTest.from_function(app, args=(n,)).run()
            self.assertFalse(at.exception)
            self.assertEqual(len([c for c in at.caption if c.value.startswith('CARD ')]), 1)
            self.assertEqual(len([b for b in at.button if b.label == 'Copy winning image']), 0)
            for _ in range(n-1):next(b for b in at.button if b.label=='Next card').click().run()
            self.assertTrue(any(t.value == f'Headline: Headline {n}' for t in at.text))
            self.assertTrue(any(t.value == f'Description: Description {n}' for t in at.text))

    def test_missing_card_warning_keeps_all_positions(self):
        from streamlit.testing.v1 import AppTest
        def app():
            import streamlit as st
            from tests.test_meta_review_creative import inline
            import meta_review_creative
            raw = inline()
            del raw['object_story_spec']['link_data']['child_attachments'][2]['picture']
            meta_review_creative.render_cards(st, meta_review_creative.normalize(raw))
        at = AppTest.from_function(app).run()
        self.assertFalse(at.exception)
        self.assertIn('1 of 5', at.warning[0].value)
        for _ in range(2):next(b for b in at.button if b.label=='Next card').click().run()
        self.assertTrue(any('Card 3 — image unavailable from Meta' == c.value for c in at.caption))

    def test_selected_resolution_and_rerender_reuse_cache(self):
        from streamlit.testing.v1 import AppTest
        def app():
            import streamlit as st
            import ads_meta_review_page as page
            import meta_review_analysis
            from tests.test_meta_review_creative import inline, CONFIG
            ad = {'ad_id': '55', 'assets': meta_review_analysis.creative_assets(inline())}
            page.resolve_selected(ad, CONFIG)
            st.caption(ad['winning_creative']['creative_format'])
        with patch.object(creative, 'resolve', return_value={**creative.normalize(inline()), 'raw': inline()}) as resolve:
            at = AppTest.from_function(app).run()
            at.run()
        self.assertFalse(at.exception)
        self.assertEqual(resolve.call_count, 1)

    def test_building_ad_table_does_not_resolve_creatives(self):
        import ads_meta_review_page as page
        from tests.test_meta_review import history
        with patch.object(creative, 'resolve', side_effect=AssertionError('eager read')):
            values = page.build_ads(history())
        self.assertTrue(values)

    def test_apply_reuses_complete_cached_source_and_saved_link(self):
        from streamlit.testing.v1 import AppTest
        import ads_meta_review_page as page
        def app():
            import ads_meta_review_page as page
            import meta_review_analysis
            from tests.test_meta_review_creative import inline
            raw = inline(6)
            ad = {'ad_id': '55', 'ad_name': 'Winning carousel', 'assets': meta_review_analysis.creative_assets(raw),
                  'creative_metadata': raw, 'metrics': {}, 'decision': {'label': 'WINNER — REFRESH THIS', 'reason': 'Synthetic evidence'}, 'benchmark': {}}
            page.simple_winner([ad], {'selections': [], 'assets': [], 'mapping': []},
                               {'campaign_id': '77', 'account_id': '123', 'date_range': 'synthetic'})
        value = {**creative.normalize(inline(6)), 'raw': inline(6)}
        with patch.object(page.meta, 'get_meta_config', return_value=CONFIG), patch.object(creative, 'resolve', return_value=value) as resolve, patch.object(handoff, 'queue_link', return_value='?page=creative-refresh&handoff_id=synthetic') as queue:
            at = AppTest.from_function(app).run()
            next(b for b in at.button if b.label == 'APPLY TO CREATIVE REFRESH').click().run()
            next(b for b in at.button if b.label == 'APPLY TO CREATIVE REFRESH').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(queue.call_count, 1)
        self.assertEqual(len(queue.call_args.args[0]['carousel_cards']), 6)
        self.assertFalse(any(s.label == 'Choose original image' for s in at.selectbox))


class HandoffTests(unittest.TestCase):
    def test_every_card_survives_package_hydration(self):
        for n in (4, 5, 6):
            value, state = package(inline(n)), {}
            state[handoff.PENDING] = value
            handoff.hydrate(state)
            self.assertEqual(state['ads_campaign_type'], 'Carousel')
            self.assertEqual(len(state[handoff.ACTIVE]['carousel_cards']), n)
            self.assertEqual(state[handoff.ACTIVE]['carousel_cards'][-1]['description'], f'Description {n}')
            self.assertFalse(handoff.hydrate(state))

    def test_ie_type_auto_selects(self):
        self.assertEqual(handoff.resolve_campaign_type({'creative_format': 'INSTANT_EXPERIENCE'})['campaign_type'], 'Instant Experience')

    def test_unknown_dynamic_cannot_certify_carousel(self):
        for fmt in ('UNKNOWN', 'DYNAMIC', 'VIDEO'):
            self.assertFalse(handoff.resolve_campaign_type({'creative_format': fmt, 'format': 'CAROUSEL'})['confirmed'])

    def test_card_copy_order_and_context_invalidate(self):
        original = package(inline())
        for key in ('campaign_id', 'ad_id', 'creative_id', 'product_mapping', 'creative_format', 'date_range'):
            changed = deepcopy(original)
            changed[key] = 'changed'
            self.assertNotEqual(plan.identity_hash({'source_winner': original}, 'Carousel', 'Product', 'Golf'),
                                plan.identity_hash({'source_winner': changed}, 'Carousel', 'Product', 'Golf'))
        changed = deepcopy(original)
        changed['carousel_cards'].reverse()
        self.assertNotEqual(creative.fingerprint(original), creative.fingerprint(changed))
        changed = deepcopy(original)
        changed['carousel_cards'][0]['headline'] = 'Changed'
        self.assertNotEqual(creative.fingerprint(original), creative.fingerprint(changed))

    def test_archive_preserves_all_six_and_isolates_missing_image(self):
        value, state = package(inline(6)), {}
        def archive(url):
            if 'card3.' in url:
                raise ValueError('unavailable')
            return 'hash-' + url
        with patch.object(handoff.products, 'enrich', side_effect=lambda p: p), patch.object(handoff, 'archive_image', side_effect=archive) as read, patch.object(handoff.store, 'save_selection', return_value=1) as save:
            with self.assertRaisesRegex(ValueError,'card 3'):handoff.queue(value, state)
            save.assert_not_called()
        self.assertNotIn(handoff.PENDING,state)
        self.assertEqual(len(value['carousel_cards']),6)


class DynamicRefreshTests(unittest.TestCase):
    def result(self, n):
        return ads.build_ads_result_record('Verified Product Wall Art', 'Golf', 'New Zealand', 'Carousel',
            product_url='https://example.com/products/art', variation_token='test',
            creative_refresh_context={'winning_primary_text': 'Shared collector message', 'winning_headline': 'Shared headline',
                                      'source_winner': package(inline(n))})

    def test_attachment_and_output_counts_and_shared_rules(self):
        for n in (4, 5, 6):
            value = self.result(n)
            prompt = value['master_prompt']
            self.assertIn(f'ONE refreshed {n}-CARD', prompt)
            self.assertIn(f'ATTACHMENT {n+1} — CANONICAL_PRODUCT', prompt)
            self.assertNotIn(f'WINNER_CARD_{n+1}', prompt)
            self.assertEqual(prompt.count('PRODUCT: Verified Product Wall Art'), n)
            self.assertGreaterEqual(prompt.count(build_sports_cave_image_realism_rules(include_product_lock=True)), n)
            self.assertIn(f'Description {n}', prompt)
            self.assertEqual(ads._ads_image_required_count(value), n)

    def test_csv_roundtrip_uses_all_source_cards(self):
        for n in (4, 5, 6):
            value = self.result(n)
            csv_bytes = ads.build_carousel_copy_csv(value, template=True)
            parsed = ads.parse_carousel_copy_csv(csv_bytes, value)
            self.assertEqual(len(parsed['cards']), n)
            self.assertEqual(parsed['cards'][-1]['slot_id'], f'carousel-{n:02d}')
            self.assertEqual(len(parsed['primary_texts']), 5)
            workflow = {'slots': {s['id']: {} for s in ads._result_image_slots(value)}}
            ads._store_carousel_copy_notes(workflow, parsed, value)
            self.assertEqual(len(ads._carousel_copy_notes_from_workflow(value, workflow)['cards']), n)

    def test_import_before_images_keeps_six_cards(self):
        value = self.result(6)
        parsed = ads.parse_carousel_copy_csv(ads.build_carousel_copy_csv(value, template=True), value)
        workflow = {'slots': {}}
        ads._store_carousel_copy_notes(workflow, parsed, value)
        self.assertEqual(len(workflow['ad_notes']['carousel']['cards']), 6)

    def test_new_ads_remains_five(self):
        value = {'campaign_type': 'Carousel'}
        self.assertEqual(len(ads._result_image_slots(value)), 5)
        self.assertEqual(len(ads.parse_carousel_copy_csv(ads.build_carousel_copy_csv(value, template=True), value)['cards']), 5)

    def test_ie_keeps_one_reference_three_outputs(self):
        value = ads.build_ads_result_record('Verified Product Wall Art', 'Golf', 'New Zealand', 'Instant Experience',
            creative_refresh_context={'winning_primary_text': 'A collector moment', 'winning_headline': 'Own the moment',
                                      'source_winner': {'creative_format': 'INSTANT_EXPERIENCE'}})
        self.assertEqual(len(ads._result_image_slots(value)), 3)
        self.assertIn('Create THREE refreshed creatives', value['master_prompt'])
        self.assertIn('WINNER_IE', value['master_prompt'])
        self.assertNotIn('WINNER_CARD_1', value['master_prompt'])

    def test_unsupported_source_cannot_submit(self):
        for fmt in ('DYNAMIC', 'VIDEO'):
            self.assertIn('no supported', ads.validate_creative_refresh_context({
                'winning_primary_text': 'Primary', 'winning_headline': 'Headline', 'source_winner': {'creative_format': fmt}}))


if __name__ == '__main__':
    unittest.main()
