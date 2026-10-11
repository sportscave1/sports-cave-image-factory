import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from unittest.mock import patch
import ads_posting_page as posting
import ads_posting_progress as progress


def completed_row():
    return {'submission_id': '11111111-1111-4111-8111-111111111111',
            'status': 'COMPLETE', 'campaign_name': 'Verified fixture campaign',
            'ad_results': [{'index': n, 'meta_ad_id': str(n),
                            'meta_ad_configured_status': 'PAUSED'} for n in (1, 2, 3)]}


class ProgressViewTests(unittest.TestCase):
    def test_cleanup_is_scoped_to_verified_owner_and_preserves_other_data(self):
        row = completed_row()
        for status, same_owner in [('COMPLETE', True), ('COMPLETE', False), ('FAILED', True), ('AMBIGUOUS', True)]:
            state = {progress.RECEIPT_KEY: {**row, 'status': status},
                     posting.SUBMISSION_ID_KEY: row['submission_id'] if same_owner else 'new-draft',
                     posting.CSV_IMPORT_STATE_KEY: {'csv': b'original'},
                     posting.IMAGE_STATE_KEYS[0]: {'data': b'image'},
                     posting.posting_handoff.LOADED_KEY: {'source': 'fixture'},
                     'other_workflow': {'saved_package': 'permanent'}}
            with patch.object(progress.st, 'session_state', state), patch.object(progress.st, 'query_params', {}):
                progress.cleanup_completed()
            cleared = status == 'COMPLETE' and same_owner
            self.assertEqual(posting.CSV_IMPORT_STATE_KEY not in state, cleared)
            self.assertEqual(posting.IMAGE_STATE_KEYS[0] not in state, cleared)
            self.assertEqual(posting.posting_handoff.LOADED_KEY not in state, cleared)
            self.assertIn('other_workflow', state)

    def test_incomplete_complete_record_is_not_success(self):
        row = completed_row()
        row['ad_results'][1]['meta_ad_configured_status'] = ''
        self.assertFalse(progress.verified_success(row))

    def test_late_status_response_cannot_restore_completed_run(self):
        row = completed_row()
        identity = row['submission_id']
        def late_response(_):
            progress.st.session_state.pop(progress.JOB_KEY, None)
            progress.st.session_state[posting.SUBMISSION_ID_KEY] = 'new-draft'
            return row
        app = AppTest.from_string('import ads_posting_progress as p; p.render_current()')
        app.session_state[progress.JOB_KEY] = identity
        with patch.object(progress.JOBS, 'snapshot', side_effect=late_response):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[posting.SUBMISSION_ID_KEY], 'new-draft')
        self.assertNotIn(progress.RECEIPT_KEY, app.session_state)

    def test_refresh_restores_failed_job_identity_before_form_defaults(self):
        fixture = Path(__file__).parent / 'fixtures/post_ad_compact_preview.py'
        app = AppTest.from_file(str(fixture), default_timeout=30)
        row = {**completed_row(), 'status': 'FAILED', 'needs_original_inputs': True}
        app.query_params[progress.QUERY_KEY] = row['submission_id']
        with patch.object(progress.JOBS, 'snapshot', return_value=row):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[posting.SUBMISSION_ID_KEY], row['submission_id'])
        app.button(key='posting_result_setup').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[posting.SUBMISSION_ID_KEY], row['submission_id'])

    def test_actual_form_stays_visible_and_success_resets_inputs(self):
        fixture = Path(__file__).parent / 'fixtures/post_ad_compact_preview.py'
        app = AppTest.from_file(str(fixture), default_timeout=30).run()
        app.text_area(key=posting.PRIMARY_TEXT_KEYS[0]).set_value('Unfinished copy').run()
        labels = [x.label for x in app.selectbox]
        row = completed_row()
        identity = app.session_state[posting.SUBMISSION_ID_KEY]
        row['submission_id'] = identity
        app.session_state[progress.JOB_KEY] = identity
        with patch.object(progress.JOBS, 'snapshot', return_value={**row, 'status': 'AD_CREATED', 'running_here': True}):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(labels, [x.label for x in app.selectbox])
        self.assertEqual(app.text_area(key=posting.PRIMARY_TEXT_KEYS[0]).value, 'Unfinished copy')
        self.assertTrue(app.button(key=posting.STATE_PREFIX + 'create').disabled)
        with patch.object(progress.JOBS, 'snapshot', return_value=row):
            app.run()
        self.assertFalse(app.exception)
        self.assertNotEqual(app.session_state[posting.SUBMISSION_ID_KEY], identity)
        self.assertNotEqual(app.text_area(key=posting.PRIMARY_TEXT_KEYS[0]).value, 'Unfinished copy')
        self.assertNotIn(progress.QUERY_KEY, app.query_params)
        for button in app.button:
            if button.label == 'New Campaign':
                button.click().run()
                break
        self.assertFalse(app.exception)
        self.assertNotIn('Close', [b.label for b in app.button])

    def test_submission_immediate_progress_and_url_restoration(self):
        path = Path(__file__).with_name('meta_posting_progress_fixture.py')
        app = AppTest.from_file(str(path), default_timeout=20).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn('Creating Meta Ads…', [item.value for item in app.subheader])
        identity = app.query_params['meta_posting_job']
        restored = AppTest.from_file(str(path), default_timeout=20)
        restored.query_params['meta_posting_job'] = identity
        restored.run()
        self.assertFalse(restored.exception)
        self.assertIn('Creating Meta Ads…', [item.value for item in restored.subheader])
        app.button[1].click().run()  # Release the test-only service gate.


if __name__ == '__main__': unittest.main()
