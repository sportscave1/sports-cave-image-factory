"""Focused Post Ad presentation/state checks. No external services."""
from pathlib import Path
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import requests
from streamlit.testing.v1 import AppTest
import ads_posting_page as page
from ads_posting_progress import progress_value

FIXTURE = Path(__file__).parent / 'fixtures/post_ad_compact_preview.py'


class CompactPostingTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(FIXTURE), default_timeout=30).run()

    def test_modes_fields_and_removed_technical_panels(self):
        app = self.app()
        for mode in ('New Campaign', 'Add to Existing'):
            for kind, count in ((page.AD_TYPE, 3), (page.CAROUSEL_AD_TYPE, 5)):
                app.session_state[page.POSTING_MODE_KEY] = mode
                app.session_state[page.AD_TYPE_KEY] = kind
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(sum(x.label == 'Create Ad' for x in app.button), 1)
                self.assertEqual(len(app.text_area), count)
                self.assertEqual(len(app.get('file_uploader')), count + 1)
                self.assertTrue({'Product URL', 'Dataset'} <= {x.label for x in app.text_input})
                labels = {x.label for x in app.selectbox} | {x.label for x in app.text_input}
                self.assertTrue({'Country', 'Sport / category', 'Audience', 'Customer Lifecycle Strategy'} <= labels)
                self.assertFalse({'Recent Posting jobs', 'Advanced Meta Diagnostics'} & {x.label for x in app.expander})
                self.assertNotIn('Meta connected · ready', str([x.value for x in app.markdown]))

    def test_values_and_image_records_survive_hidden_form_and_return(self):
        app = self.app()
        app.text_area(key=page.PRIMARY_TEXT_KEYS[0]).set_value('Preserve this copy').run()
        image = {'valid': True, 'data': b'original-quality-bytes'}
        app.session_state[page.IMAGE_STATE_KEYS[0]] = image
        with patch('ads_posting_progress.render_current', return_value=True):
            app.run()
        self.assertEqual(app.session_state[page.PRIMARY_TEXT_KEYS[0]], 'Preserve this copy')
        self.assertEqual(app.session_state[page.IMAGE_STATE_KEYS[0]], image)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area(key=page.PRIMARY_TEXT_KEYS[0]).value, 'Preserve this copy')

    def test_index_resolution_matches_legacy_and_invalidates_changed_rows(self):
        rows = ({'shopify_product_id': '42', 'product_title': 'First', 'product_handle': 'first'},)
        state = {}
        records, by_id = page._product_selector_state(rows, state=state)
        value = records[0]['identity']
        self.assertEqual(page._resolve_selected_product(value, rows, records, by_id),
                         page.ads_page.resolve_ads_product_selector_value(value, rows=rows, records=records))
        changed = ({**rows[0], 'product_title': 'Changed'},)
        updated, _ = page._product_selector_state(changed, state=state)
        self.assertIn('Changed', updated[0]['label'])

    def test_progress_reserves_final_verification(self):
        ads = [{'index': n, 'meta_ad_id': str(n), 'meta_ad_configured_status': 'PAUSED'} for n in (1, 2, 3)]
        self.assertLess(progress_value({'status': 'AD_CREATED', 'ad_results': ads}), 1)
        self.assertEqual(progress_value({'status': 'COMPLETE', 'ad_results': ads}), 1)
        ads[2]['meta_ad_configured_status'] = 'ACTIVE'
        self.assertLess(progress_value({'status': 'COMPLETE', 'ad_results': ads}), 1)

    def test_status_outage_stops_automatic_checks_and_offers_read_only_recovery(self):
        app = AppTest.from_file(str(Path(__file__).parent / 'meta_posting_progress_fixture.py'), default_timeout=30)
        app.query_params['meta_posting_job'] = '11111111-1111-4111-8111-111111111111'
        with patch('meta_posting_jobs.PostingJobs.snapshot', side_effect=TimeoutError), \
             patch('meta_posting_jobs.PostingJobs.submit') as submit:
            for _ in range(5):
                app.run()
            self.assertFalse(app.exception)
            self.assertGreaterEqual(app.session_state['posting_status_failures'], 5)
            self.assertIn('Retry status', [b.label for b in app.button])
            self.assertTrue(any('Automatic status checks paused' in x.value for x in app.caption))
            submit.assert_not_called()

    def test_meta_write_timeout_and_network_loss_are_not_retried(self):
        from meta_ads_client import _post, MetaAdsAmbiguousResultError
        config = {'configured': True, 'api_version': 'v23.0', 'access_token': 'fixture'}
        for error in (requests.Timeout, requests.ConnectionError):
            with patch('meta_ads_client.requests.post', side_effect=error) as send:
                with self.assertRaises(MetaAdsAmbiguousResultError):
                    _post('act_fixture/campaigns', config=config)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(send.call_args.kwargs['timeout'], 45)

    def test_meta_rate_limit_is_reported_without_automatic_write_retry(self):
        from meta_ads_client import _post, MetaAdsApiError
        response = Mock(status_code=429, ok=False)
        response.json.return_value = {'error': {'message': 'Rate limit exceeded', 'code': 4}}
        config = {'configured': True, 'api_version': 'v23.0', 'access_token': 'fixture'}
        with patch('meta_ads_client.requests.post', return_value=response) as send:
            with self.assertRaises(MetaAdsApiError):
                _post('act_fixture/campaigns', config=config)
            self.assertEqual(send.call_count, 1)


if __name__ == '__main__':
    unittest.main()
