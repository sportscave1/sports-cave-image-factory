"""Posting-contract and active-screen regressions; Graph/storage writes forbidden."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page
import ads_refresh_plan as plan
import meta_review_analysis as analysis
import meta_review_creative as creative
import meta_review_handoff as handoff
import meta_review_live as live
from meta_posting_service import build_carousel_creative_payload
from tests.test_meta_review_creative import CONFIG


def authored():
    return {'id': '1234', **build_carousel_creative_payload(
        name='Production contract fixture', page_id='11', instagram_user_id='22',
        cards=[{'image_hash': f'h{i}', 'headline': f'Headline {i}',
                'description': f'Description {i}'} for i in range(1, 6)],
        primary_texts=[f'Shared text {i}' for i in range(1, 6)],
        destination_url='https://example.com/products/art')}


def image_response():
    return {'data': [{'hash': f'h{i}', 'url': f'https://fixture.fbcdn.net/card{i}.jpg'}
                     for i in (4, 2, 5, 1, 3)]}


def feed_creative():
    return {'id': '1234', 'asset_feed_spec': {
        'carousels': [{'child_attachments': [
            {f'{key}_label': {'name': f'{key}{i}'} for key in ('image', 'title', 'description', 'link_url')}
            for i in range(1, 6)]}],
        'images': [{'hash': f'h{i}', 'adlabels': [{'name': f'image{i}'}]} for i in range(1, 6)],
        'titles': [{'text': f'Headline {i}', 'adlabels': [{'name': f'title{i}'}]} for i in range(1, 6)],
        'descriptions': [{'text': f'Description {i}', 'adlabels': [{'name': f'description{i}'}]} for i in range(1, 6)],
        'link_urls': [{'website_url': f'https://example.com/{i}', 'adlabels': [{'name': f'link_url{i}'}]} for i in range(1, 6)]}}


def story_response():
    return {'id': '11_22', 'attachments': {'data': [{'subattachments': {'data': [
        {'id': f'a{i}', 'type': 'photo', 'title': f'Story {i}', 'description': f'Desc {i}',
         'url': f'https://example.com/{i}', 'target': {'id': str(i)},
         'media': {'image': {'src': f'https://fixture.fbcdn.net/story{i}.jpg'}}}
        for i in range(1, 6)]}}]}}


def ad_for(raw, resolved):
    ad = {'campaign_id': '77', 'ad_id': '55', 'ad_name': 'Carousel fixture',
          'assets': analysis.creative_assets(raw), 'metrics': {},
          'decision': {'label': 'WINNER — REFRESH THIS', 'reason': 'Fixture'}, 'benchmark': {}}
    page.apply_resolved(ad, {**resolved, 'raw': raw})
    return ad


def package_for(raw, resolved):
    ad = ad_for(raw, resolved)
    picks = {k: {'ad_id': '55', 'value': ad['assets'][k][0]['value']}
             for k in ('image', 'primary_text', 'headline')}
    return handoff.build_package(ad, picks, {'campaign_id': '77'}, 'complete_ad')


class ContractTests(unittest.TestCase):
    def test_actual_posting_contract_and_shuffled_hashes(self):
        raw = authored()
        with patch.object(live.meta, '_request', side_effect=[raw, image_response()]) as graph:
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(graph.call_count, 2)
        self.assertEqual(graph.call_args.args[0], 'act_123/adimages')
        self.assertEqual(json.loads(graph.call_args.kwargs['params']['hashes']), [f'h{i}' for i in range(1, 6)])
        self.assertEqual(value['creative_format'], 'DYNAMIC_CAROUSEL')
        self.assertEqual(value['shared_primary_texts'], [f'Shared text {i}' for i in range(1, 6)])
        package = package_for(raw, value)
        for i, card in enumerate(package['carousel_cards'], 1):
            self.assertEqual(card['position'], i)
            self.assertEqual(card['source_position'], i)
            self.assertEqual(card['image_hash'], f'h{i}')
            self.assertEqual(card['image_url'], f'https://fixture.fbcdn.net/card{i}.jpg')
            self.assertEqual(card['headline'], f'Headline {i}')
            self.assertEqual(card['description'], f'Description {i}')
            self.assertEqual(card['destination_url'], 'https://example.com/products/art')
            self.assertEqual(card['cta'], 'SHOP_NOW')
            self.assertEqual(card['source_ad_id'], '55')
            self.assertEqual(card['source_creative_id'], '1234')
            self.assertNotIn('primary_text', card)
        self.assertEqual(package['source_campaign_type'], 'Carousel')
        self.assertEqual(package['shared_primary_texts'], value['shared_primary_texts'])
        self.assertEqual([r['label'] for r in plan.reference_map('Carousel', package)],
                         [f'WINNER_CARD_{i}' for i in range(1, 6)] + ['CANONICAL_PRODUCT'])

    def test_inline_precedes_both_story_and_feed(self):
        raw = authored()
        raw['effective_object_story_id'] = '11_22'
        raw['asset_feed_spec'].update(feed_creative()['asset_feed_spec'])
        with patch.object(live.meta, '_request', side_effect=[raw, image_response()]) as graph:
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(graph.call_count, 2)
        self.assertTrue(value['creative_format_source'].startswith('object_story_spec'))

    def test_story_precedes_feed_and_keeps_copy_identity(self):
        raw = feed_creative()
        raw['effective_object_story_id'] = '11_22'
        with patch.object(live.meta, '_request', side_effect=[raw, story_response()]) as graph:
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(graph.call_count, 2)
        self.assertEqual(graph.call_args.args[0], '11_22')
        self.assertEqual([c['headline'] for c in value['cards']], [f'Story {i}' for i in range(1, 6)])
        self.assertEqual(value['cards'][2]['source_attachment_id'], 'a3')
        self.assertTrue(value['diagnostic']['story_pagination_complete'])

    def test_partial_story_never_falls_back_to_feed(self):
        for edge in ('attachments', 'subattachments'):
            raw = feed_creative(); raw['object_story_id'] = '11_22'
            story = story_response()
            target = story['attachments'] if edge == 'attachments' else story['attachments']['data'][0]['subattachments']
            target['paging'] = {'next': 'https://graph.facebook.com/?access_token=SECRET'}
            with patch.object(live.meta, '_request', side_effect=[raw, story]):
                value = creative.resolve(CONFIG, '1234')
            self.assertEqual(value['cards'], [])
            self.assertTrue(value['carousel_resolution_incomplete'])
            self.assertFalse(value['diagnostic']['story_pagination_complete'])
            self.assertNotIn('SECRET', json.dumps(creative.diagnostic(value)))

    def test_feed_labels_are_deterministic(self):
        with patch.object(live.meta, '_request', side_effect=[feed_creative(), image_response()]):
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(len(value['cards']), 5)
        self.assertEqual(value['cards'][4]['destination_url'], 'https://example.com/5')
        self.assertEqual(value['cards'][4]['description'], 'Description 5')

    def test_labelled_video_identity_is_preserved_without_pool_pairing(self):
        raw = feed_creative()
        child = raw['asset_feed_spec']['carousels'][0]['child_attachments'][0]
        child.pop('image_label')
        child['video_label'] = {'name': 'clip1'}
        raw['asset_feed_spec']['videos'] = [{'video_id': '9001', 'adlabels': [{'name': 'clip1'}],
                                            'thumbnail_url': 'https://fixture.fbcdn.net/video1.jpg'}]
        value = creative.normalize(raw)
        self.assertEqual(value['cards'][0]['video_id'], '9001')
        self.assertEqual(value['cards'][0]['image_url'], 'https://fixture.fbcdn.net/video1.jpg')
        self.assertEqual(value['cards'][0]['image_hash'], '')

    def test_ambiguous_or_missing_label_fails_closed(self):
        for collection in ('images', 'titles', 'descriptions', 'link_urls'):
            for duplicate in (True, False):
                raw = feed_creative()
                if duplicate: raw['asset_feed_spec'][collection].append(deepcopy(raw['asset_feed_spec'][collection][0]))
                else: raw['asset_feed_spec'][collection].pop(0)
                value = creative.normalize(raw)
                self.assertEqual(value['cards'], [])
                self.assertTrue(value['carousel_resolution_incomplete'])

    def test_missing_card_never_filled_by_thumbnail(self):
        raw = authored(); raw['thumbnail_url'] = 'https://fixture.fbcdn.net/cover.jpg'
        images = image_response(); images['data'] = [r for r in images['data'] if r['hash'] != 'h3']
        with patch.object(live.meta, '_request', side_effect=[raw, images]):
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(len(value['cards']), 5)
        self.assertEqual(value['cards'][2]['image_url'], '')
        with self.assertRaisesRegex(ValueError, 'Missing source carousel cards: 3'):
            package_for(raw, value)

    def test_truncated_handoff_and_refresh_fail_closed(self):
        raw = authored()
        value = creative.normalize(raw, images={r['hash']: r['url'] for r in image_response()['data']})
        package = package_for(raw, value)
        package['carousel_cards'].pop()
        with self.assertRaisesRegex(ValueError, 'count changed'): handoff.require_complete_carousel(package)
        with self.assertRaisesRegex(ValueError, 'Complete source'): plan.reference_map('Carousel', package)

    def test_archive_and_hydration_keep_every_card_and_shared_text(self):
        raw = authored()
        value = creative.normalize(raw, images={r['hash']: r['url'] for r in image_response()['data']})
        package = package_for(raw, value)
        state = {}
        with patch.object(handoff.products, 'enrich', side_effect=lambda p: p), \
             patch.object(handoff, 'archive_image', side_effect=lambda url: 'archive-' + url) as archive, \
             patch.object(handoff.store, 'save_selection', return_value='saved') as save:
            handoff.queue(package, state)
        self.assertEqual(archive.call_count, 5)
        self.assertEqual(len(save.call_args.args[0]['carousel_cards']), 5)
        self.assertTrue(all(c['image_sha256'] for c in package['carousel_cards']))
        handoff.hydrate(state)
        self.assertEqual(state['ads_campaign_type'], 'Carousel')
        self.assertEqual(len(state[handoff.ACTIVE]['shared_primary_texts']), 5)
        self.assertEqual(len(state[handoff.ACTIVE]['carousel_cards']), 5)

    def test_invalid_inline_placeholders_do_not_mask_valid_story(self):
        raw = {'id': '1234', 'effective_object_story_id': '11_22',
               'object_story_spec': {'link_data': {'child_attachments': [{}, {}]}}}
        with patch.object(live.meta, '_request', side_effect=[raw, story_response()]):
            value = creative.resolve(CONFIG, '1234')
        self.assertEqual(len(value['cards']), 5)
        self.assertIn('subattachments', value['creative_format_source'])

    def test_diagnostic_counts_are_explicit_not_raw_graph(self):
        with patch.object(live.meta, '_request', side_effect=[authored(), image_response()]):
            value = creative.resolve(CONFIG, '1234')
        d = creative.diagnostic(value, campaign_id='77', ad_id='55', displayed_count=5)
        for key in ('inline_child_attachment_count', 'image_hash_count', 'resolved_image_count',
                    'source_card_count', 'normalized_card_count', 'resolved_card_count', 'displayed_card_count'):
            self.assertEqual(d[key], 5, key)
        self.assertEqual(d['handoff_card_count'], 0)
        self.assertIsNone(d['story_pagination_complete'])
        self.assertTrue(d['asset_feed_spec_present'])
        self.assertNotIn('https://', json.dumps(d))


class ActiveScreenTests(unittest.TestCase):
    def test_failed_selected_read_cannot_handoff_representative_thumbnail(self):
        def app():
            import streamlit as st
            import ads_meta_review_page as page
            import meta_review_creative as creative
            import meta_review_analysis as analysis
            from tests.test_meta_review_carousel_contract import authored, CONFIG
            raw = authored(); raw['thumbnail_url'] = 'https://fixture.fbcdn.net/cover.jpg'
            ad = {'ad_id': '55', 'assets': analysis.creative_assets(raw),
                  'winning_creative': creative.normalize(raw)}
            page.resolve_selected(ad, CONFIG)
            st.json(ad['winning_creative'])
        with patch.object(live.meta, '_request', side_effect=ValueError('Unavailable')):
            at = AppTest.from_function(app).run()
        self.assertFalse(at.exception)
        data = json.loads(at.json[0].value)
        self.assertTrue(data['carousel_resolution_incomplete'])
        self.assertEqual(data['cards'], [])

    def test_viewer_all_cards_and_apply_from_three_uses_one_resolution(self):
        def app():
            import ads_meta_review_page as page
            from tests.test_meta_review_carousel_contract import authored
            import meta_review_analysis as analysis
            raw = authored()
            ad = {'ad_id': '55', 'campaign_id': '77', 'ad_name': 'Carousel',
                  'assets': analysis.creative_assets(raw), 'metrics': {}, 'benchmark': {},
                  'decision': {'label': 'WINNER — REFRESH THIS', 'reason': 'Fixture'}}
            page.simple_winner([ad], {'selections': [], 'assets': [], 'mapping': []},
                               {'campaign_id': '77', 'account_id': '123'})
        with patch.object(page.meta, 'get_meta_config', return_value=CONFIG), \
             patch.object(live.meta, '_request', side_effect=[authored(), image_response()]) as graph, \
             patch.object(handoff, 'queue_link', return_value='?page=creative-refresh&handoff_id=fixture') as queue:
            at = AppTest.from_function(app).run()
            self.assertFalse(at.exception)
            for i in range(1, 6):
                self.assertTrue(any(t.value == f'Shared text {i}' for t in at.text))
            for _ in range(4): next(b for b in at.button if b.label == 'Next card').click().run()
            self.assertTrue(any(t.value == 'Headline: Headline 5' for t in at.text))
            for _ in range(4): next(b for b in at.button if b.label == 'Previous card').click().run()
            for _ in range(2): next(b for b in at.button if b.label == 'Next card').click().run()
            self.assertTrue(any(t.value == 'Headline: Headline 3' for t in at.text))
            next(b for b in at.button if b.label == 'APPLY TO CREATIVE REFRESH').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(graph.call_count, 2)
            package = queue.call_args.args[0]
            self.assertEqual(len(package['carousel_cards']), 5)
            self.assertEqual(package['shared_primary_texts'], [f'Shared text {i}' for i in range(1, 6)])
            self.assertEqual(package['diagnostic']['handoff_card_count'], 5)
            self.assertEqual(package['diagnostic']['displayed_card_count'], 5)
            self.assertEqual(package['diagnostic']['ad_id'], '55')
            self.assertEqual(package['diagnostic']['campaign_id'], '77')

    def test_admin_diagnostic_is_safe_and_worker_cannot_see_it(self):
        def app(role):
            import streamlit as st
            import ads_meta_review_page as page
            st.session_state['sports_cave_current_user'] = {'role': role, 'is_active': True}
            page.render_creative_diagnostic({'ad_id': '55', 'winning_creative': {
                'creative_id': '1234', 'raw': {'access_token': 'SECRET'},
                'diagnostic': {'access_token': 'SECRET'}, 'cards': []}})
        admin = AppTest.from_function(app, args=('admin',)).run()
        self.assertFalse(admin.exception)
        self.assertTrue(any(e.label == 'Advanced Meta diagnostic' for e in admin.expander))
        self.assertNotIn('SECRET', str([j.value for j in admin.json]))
        worker = AppTest.from_function(app, args=('worker',)).run()
        self.assertEqual(len(worker.json), 0)


if __name__ == '__main__':
    unittest.main()
