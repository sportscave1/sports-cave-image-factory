from copy import deepcopy
import unittest
from unittest.mock import patch

import ads_page as ads
import ads_posting_handoff as handoff
import ads_posting_page as posting
import ads_refresh_saved as saved
import meta_review_handoff as winner_handoff
from tests.test_ads_posting_handoff import completed_ad, save_locally
from tests.test_ads_refresh_plan import fixture
from tests.test_ads_refresh_workflow import ROW


class RefreshSaveRestoreTests(unittest.TestCase):
    def ready_ie(self):
        result = fixture('Instant Experience')
        _, workflow = completed_ad('Instant Experience', 'creative_refresh')
        workflow['context_key'] = result['context_key']
        for concept in ads.INSTANT_EXPERIENCE_CONCEPTS:
            workflow['ad_notes']['instant_experience_concepts'][concept['id']] = [
                dict(primary_text='A collector tribute for your wall.', headline='Claim this edition', cta='Claim Your Edition')]
        return result, workflow

    def test_ie_save_without_analysis_reopen_and_existing_posting(self):
        result, workflow = self.ready_ie()
        workflow['ad_notes']['refresh_execution_error'] = True
        self.assertTrue(ads.instant_experience_package_ready(result, workflow))
        uploads = save_locally(result, workflow)
        path = next(p for p in uploads if p.endswith(saved.FILENAME))
        state = {}
        saved.restore(uploads[path], state)
        reopened = state[ads._ads_image_state_key('creative_refresh')]
        package = reopened[handoff.SAVED_PACKAGE_KEY]
        self.assertEqual(package['source_provenance'], result['creative_refresh_context'])
        self.assertEqual(package['package_id'], workflow[handoff.SAVED_PACKAGE_KEY]['package_id'])
        self.assertEqual([a['concept_id'] for a in package['assets']], [c['id'] for c in ads.INSTANT_EXPERIENCE_CONCEPTS])
        self.assertEqual(package['batch']['product_url'], result['product_url'])
        handoff.queue_saved_package(package, state=state)
        self.assertTrue(posting.consume_saved_posting_package(ads.build_ads_product_selector_records([ROW]), state=state))
        for i in range(3):
            self.assertTrue(state[posting.PRIMARY_TEXT_KEYS[i]])
        reopened['ad_notes']['instant_experience_concepts'][ads.INSTANT_EXPERIENCE_CONCEPTS[0]['id']][0]['headline'] = 'Changed'
        self.assertNotEqual(package['source_signature'], ads._ads_saved_source_signature(result, reopened))

    def test_incomplete_image_and_corrupt_workspace_fail_closed(self):
        result, workflow = self.ready_ie()
        workflow['slots'].pop(next(iter(workflow['slots'])))
        self.assertFalse(ads.instant_experience_package_ready(result, workflow))
        with self.assertRaises(ValueError):
            saved.loads(b'{"version":1}')

    def test_exact_mapping_is_appended_even_when_missing_from_selector_rows(self):
        from meta_review_products import canonical
        mapping = canonical(ROW)
        state = {winner_handoff.ACTIVE: {'product_mapping': mapping}}
        rows = winner_handoff.product_selector_rows([], state)
        self.assertEqual(rows, [mapping['canonical_row']])
        winner_handoff.hydrate_product(state, mapping)
        self.assertEqual(state[ads.ADS_PRODUCT_URL_KEY], mapping['product_url'])

    def test_exact_id_resolves_without_fuzzy_selection_and_missing_stays_manual(self):
        state = {winner_handoff.ACTIVE: {'product_id': ROW['shopify_product_id']}}
        winner_handoff.product_selector_rows([ROW], state)
        self.assertTrue(state[winner_handoff.ACTIVE]['product_mapping']['canonical_row'])
        state = {winner_handoff.ACTIVE: {'product_resolution': {'candidates': [ROW]}}}
        self.assertEqual(winner_handoff.product_selector_rows([ROW], state), [ROW])
        self.assertNotIn('product_mapping', state[winner_handoff.ACTIVE])

    def test_carousel_save_restores_all_cards_and_preserves_dynamic_posting_count(self):
        result, workflow = completed_ad('Carousel', 'creative_refresh')
        from ads_refresh_plan import reference_map
        result['creative_refresh_context'] = {'source_winner': {'carousel_cards': [
            {'position': i, 'image_url': 'https://example.com/'+str(i)} for i in range(1,7)]}}
        cards = workflow['ad_notes']['carousel']['cards']
        cards.append({**deepcopy(cards[-1]), 'position': 6, 'slot_id': 'carousel-06', 'headline': 'Sixth card'})
        workflow['slots']['carousel-06'] = deepcopy(workflow['slots']['carousel-05'])
        uploads = save_locally(result, workflow)
        path = next(p for p in uploads if p.endswith(saved.FILENAME))
        restored_result, reopened = saved.loads(uploads[path])
        self.assertEqual(len(ads._result_image_slots(restored_result)), 6)
        self.assertEqual(len(reopened['slots']), 6)
        self.assertEqual([c['position'] for c in reopened['ad_notes']['carousel']['cards']], list(range(1,7)))
        package=reopened[handoff.SAVED_PACKAGE_KEY]
        self.assertEqual([a['position'] for a in package['assets']],list(range(1,7)))
        self.assertEqual([c['card_number'] for c in package['batch']['cards']],list(range(1,7)))
        self.assertNotIn('posting_package_error',reopened)

    def test_workspace_save_failure_disables_post_now_and_is_retryable(self):
        result, workflow = self.ready_ie()
        with self.assertRaisesRegex(ValueError, 'could not be persisted'):
            save_locally(result, workflow, fail=saved.FILENAME)
        self.assertFalse(workflow['refresh_workspace_saved'])
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
        save_locally(result, workflow)
        self.assertTrue(workflow['refresh_workspace_saved'])

    def test_four_five_and_six_cards_reach_posting_with_all_five_copy_variations(self):
        from tests.fixtures.refresh_ui import ready_carousel
        for count in (4, 5, 6):
            with self.subTest(count=count):
                result, workflow = ready_carousel(count)
                save_locally(result, workflow)
                package = workflow[handoff.SAVED_PACKAGE_KEY]
                state = {posting.CAROUSEL_IMAGE_STATE_KEYS[-1]: {'stale': True}}
                handoff.queue_saved_package(package, state=state)
                self.assertTrue(posting.consume_saved_posting_package(ads.build_ads_product_selector_records([ROW]), state=state))
                self.assertEqual(state[posting.CAROUSEL_COUNT_KEY], count)
                self.assertEqual([state[key] for key in posting.CAROUSEL_PRIMARY_TEXT_KEYS],
                                 workflow['ad_notes']['carousel']['primary_texts'])
                for index, card in enumerate(workflow['ad_notes']['carousel']['cards']):
                    self.assertEqual(state[posting.CAROUSEL_HEADLINE_KEYS[index]], card['headline'])
                    self.assertEqual(state[posting.CAROUSEL_DESCRIPTION_KEYS[index]], card['description'])
                    asset = state[posting.CAROUSEL_IMAGE_STATE_KEYS[index]]['saved_asset']
                    self.assertEqual(asset['position'], index + 1)
                self.assertNotIn(posting.CAROUSEL_IMAGE_STATE_KEYS[-1], state)
                self.assertEqual(state[handoff.LOADED_KEY]['source_provenance'], result['creative_refresh_context'])

    def test_incomplete_ie_draft_saves_and_reopens_without_invented_assets_or_review(self):
        result, workflow = self.ready_ie()
        missing = next(iter(workflow['slots']))
        workflow['slots'].pop(missing)
        originals = deepcopy(workflow['slots'])
        save_locally(result, workflow)
        _, restored = saved.loads(workflow['refresh_workspace_export'])
        self.assertEqual(set(restored['slots']), set(originals))
        for slot_id, original in originals.items():
            self.assertEqual({key: restored['slots'][slot_id][key] for key in original}, original)
        package = restored[handoff.SAVED_PACKAGE_KEY]
        self.assertTrue(package['draft_workspace'])
        self.assertEqual(len(package['assets']), 2)
        self.assertNotIn(missing, [a['slot_id'] for a in package['assets']])
        with patch.object(ads.st, 'session_state', {}):
            self.assertTrue(ads._creative_refresh_visual_review_issues(result, restored))

    def test_saved_route_reopens_with_files_authorization(self):
        result, workflow = self.ready_ie()
        uploads = save_locally(result, workflow)
        path = next(p for p in uploads if p.endswith(saved.FILENAME))
        with patch.object(ads, 'current_ads_user', return_value={}), \
             patch.object(ads.os_accounts, 'can_access_page', return_value=True), \
             patch.object(ads, '_ads_dropbox_connection', return_value=('fake', '/approved')), \
             patch.object(ads.dropbox_integration, 'get_file_bytes', return_value=({}, uploads[path])) as download:
            state = {}
            saved.restore_folder(ads, workflow['saved_folder_path'], state)
            self.assertTrue(state[ads._ads_image_state_key('creative_refresh')]['refresh_workspace_saved'])
            download.assert_called_once_with('fake', path)
            with self.assertRaises(ValueError):
                saved.restore_folder(ads, '/outside', {})
            self.assertEqual(download.call_count, 1)

    def test_new_ads_does_not_write_refresh_workspace(self):
        result, workflow = completed_ad('Instant Experience')
        uploads = save_locally(result, workflow)
        self.assertFalse(any(p.endswith(saved.FILENAME) for p in uploads))

    def test_post_now_ui_navigates_with_saved_record_and_no_legacy_ui(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('''
import streamlit as st
from unittest.mock import patch
import ads_page as ads
from tests.test_ads_refresh_save_restore import RefreshSaveRestoreTests
from tests.test_ads_posting_handoff import save_locally
if 'pair' not in st.session_state:
    st.session_state.pair = RefreshSaveRestoreTests().ready_ie()
result, workflow = st.session_state.pair
if st.button('Mock save'):
    save_locally(result, workflow)
with patch.object(ads, '_ads_image_workflow', return_value=workflow), patch.object(ads, '_render_ads_image_save'):
    ads.render_supported_result(result)
''').run(timeout=20)
        self.assertFalse(app.exception)
        self.assertNotIn('POST NOW', [b.label for b in app.button])
        next(b for b in app.button if b.label == 'Mock save').click().run(timeout=20)
        self.assertFalse(app.exception)
        visible = '\n'.join(str(e.value) for kind in ('caption','subheader','markdown') for e in app.get(kind))
        for obsolete in ('Build it in Meta', 'Final Ad Review', 'Execution notes', 'Refresh checks',
                         'Refresh analysis & standalone briefs', 'Attach WINNER_IE', 'st.iframe'):
            self.assertNotIn(obsolete, visible)
        self.assertNotIn('POST NOW', [b.label for b in app.button])
        next(c for c in app.checkbox if c.label.startswith('I checked every refreshed image')).check().run(timeout=20)
        next(b for b in app.button if b.label == 'POST NOW').click().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['current_page'], ads.POSTING_ROUTE)
        package = app.session_state[handoff.PENDING_KEY]['package']
        self.assertEqual(len(package['assets']), 3)

    def test_exact_mapping_prefills_editable_product_without_confirmation(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('''
import streamlit as st
import ads_page as ads
from meta_review_products import canonical
from tests.test_ads_refresh_workflow import ROW
st.session_state[ads.ADS_ACTIVE_WORKFLOW_MODE_KEY] = 'creative_refresh'
st.session_state['meta-review-refresh-source'] = {'product_mapping': canonical(ROW)}
ads.render_product_name_input(rows=[])
''').run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox), 1)
        self.assertEqual(app.selectbox[0].value, ads._edition_ops_product_selector_identity(ROW))


if __name__ == '__main__':
    unittest.main()
