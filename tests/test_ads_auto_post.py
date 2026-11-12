"""Offline save-before-handoff contracts. Dropbox/Meta are mocked throughout."""
from copy import deepcopy
from unittest import TestCase, mock
from types import SimpleNamespace
import ads_auto_post as auto
import ads_page as ads
import ads_posting_handoff as handoff
from tests.test_ads_posting_handoff import completed_ad


class AutomaticPostTests(TestCase):
    def run_save(self, result, workflow, *, fail=False, state=None):
        state = state if state is not None else {}
        uploads = []
        def upload(token, folder, items, **kwargs):
            uploads.append((folder, deepcopy(items)))
            return {'successes': [] if fail else [dict(relative_path=i['relative_path'], metadata={
                'id': 'test-id', 'rev':'test-rev', 'path_display':folder+'/'+i['relative_path']}) for i in items],
                'failures': [{'relative_path':items[0]['relative_path'], 'error':'offline failure'}] if fail else []}
        with (mock.patch.object(ads.st, 'session_state', state), mock.patch.object(ads.st, 'query_params', {}),
              mock.patch.object(ads.os_accounts, 'can_access_page', return_value=True),
              mock.patch.object(ads, '_ads_dropbox_connection', return_value=('fake', '/approved')),
              mock.patch.object(ads.dropbox_integration, 'ensure_folder_path'),
              mock.patch.object(ads.dropbox_integration, 'get_metadata_if_exists', return_value=None),
              mock.patch.object(ads.dropbox_integration, 'upload_batch', side_effect=upload),
              mock.patch.object(ads, '_save_ads_upload_metadata'),
              mock.patch.object(ads, 'record_activity_log'),
              mock.patch.object(ads, '_ads_clear_directory_cache')):
            if fail:
                with self.assertRaises(ValueError): auto.save_and_queue(ads,result,workflow,{'id':'test'})
                self.assertNotIn(handoff.PENDING_KEY, state)
                self.assertNotIn('current_page', state)
            else:
                auto.save_and_queue(ads,result,workflow,{'id':'test'})
                self.assertEqual(state['current_page'], ads.POSTING_ROUTE)
                self.assertIn(auto.SCROLL_KEY, state)
                self.assertEqual(handoff.content_hash(state[handoff.PENDING_KEY]['package']), handoff.content_hash(workflow[handoff.SAVED_PACKAGE_KEY]))
        return uploads, state

    def test_existing_save_handoff_for_new_and_refresh_formats(self):
        for source in (ads.ADS_WORKFLOW_MODE_NEW, ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH):
            for kind in ('Instant Experience','Carousel'):
                with self.subTest(source=source,kind=kind):
                    r,w=completed_ad(kind,source)
                    uploads,state=self.run_save(r,w)
                    self.assertTrue(uploads)
                    for folder,items in uploads:
                        self.assertTrue(folder.startswith('/approved/04_OUTPUT/ads/'))
                        self.assertNotIn('product-images',folder)
                    handoff.validate_saved_package(state[handoff.PENDING_KEY]['package'])
                    if source == ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH:
                        self.assertTrue(w['refresh_workspace_saved'])

    def test_failed_upload_does_not_navigate_and_retry_reuses_folder(self):
        r,w=completed_ad('Instant Experience')
        self.run_save(r,w,fail=True)
        folder=w['saved_folder_path']
        self.run_save(r,w)
        self.assertEqual(folder,w['saved_folder_path'])

    def test_distinct_drafts_do_not_overwrite_and_old_destination_is_ignored(self):
        r,w=completed_ad('Instant Experience')
        old=deepcopy(w)
        w['saved_folder_path']='/approved/04_OUTPUT/product-images/Old'
        self.run_save(r,w)
        self.run_save(r,old)
        self.assertNotEqual(w['saved_folder_path'],old['saved_folder_path'])
        self.assertNotIn('product-images',w['saved_folder_path'])

    def test_input_changes_change_destination(self):
        r,w=completed_ad('Instant Experience')
        self.run_save(r,w)
        first=w['saved_folder_path']
        r['country']='USA'
        if '/USA/' in first: r['country']='Australia'
        self.run_save(r,w)
        self.assertNotEqual(first,w['saved_folder_path'])

    def test_missing_destination_inputs_and_files_access_fail_closed(self):
        with self.assertRaises(ValueError): auto.destination(ads.dropbox_integration,'/approved',{})
        r,w=completed_ad()
        with mock.patch.object(ads.os_accounts,'can_access_page',return_value=False), mock.patch.object(ads,'_ads_dropbox_connection') as connect:
            with self.assertRaises(ValueError): auto.save_and_queue(ads,r,w,{})
            connect.assert_not_called()

    def test_top_reset_is_one_shot_and_targets_streamlit_scroller(self):
        st=SimpleNamespace(session_state={auto.SCROLL_KEY:'test-token'},components=SimpleNamespace(v1=SimpleNamespace(html=mock.Mock())))
        auto.scroll_to_top(st); auto.scroll_to_top(st)
        st.components.v1.html.assert_called_once()
        script=st.components.v1.html.call_args.args[0]
        self.assertIn('stMain',script)
        self.assertIn('scrollTo',script)
        self.assertNotIn(auto.SCROLL_KEY,st.session_state)

    def test_unverified_save_and_refresh_workspace_failure_never_queue(self):
        for kind in ('missing-receipt', 'refresh-persistence'):
            r,w=completed_ad('Instant Experience', ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH if kind=='refresh-persistence' else ads.ADS_WORKFLOW_MODE_NEW)
            state={}
            with (mock.patch.object(ads.st,'session_state',state),
                  mock.patch.object(ads.st,'query_params',{}),
                  mock.patch.object(ads.os_accounts,'can_access_page',return_value=True),
                  mock.patch.object(ads,'_ads_dropbox_connection',return_value=('fake','/approved')),
                  mock.patch.object(ads,'_save_ads_upload_metadata'),
                  mock.patch.object(ads,'_ads_clear_directory_cache'),
                  mock.patch.object(ads,'save_ads_images_to_dropbox',side_effect=ValueError('workspace failed') if kind=='refresh-persistence' else None,return_value={})):
                with self.assertRaises(ValueError): auto.save_and_queue(ads,r,w,{})
                self.assertNotIn(handoff.PENDING_KEY,state)
                self.assertNotIn('current_page',state)

    def test_render_has_one_full_width_action_and_keeps_validation(self):
        r,w=completed_ad('Instant Experience')
        fake=SimpleNamespace(session_state={},query_params={},button=mock.Mock(return_value=False),caption=mock.Mock())
        with mock.patch.object(ads,'st',fake), mock.patch('ads_direct_post.render_settings',return_value=({},[])), mock.patch.object(ads.os_accounts,'can_access_page',return_value=True), mock.patch.object(ads,'instant_experience_package_ready',return_value=True), mock.patch.object(auto,'save_and_queue') as save:
            auto.render(ads,r,w)
            fake.button.assert_called_once()
            self.assertEqual(fake.button.call_args.args,('Post now',))
            self.assertTrue(fake.button.call_args.kwargs['use_container_width'])
            self.assertFalse(fake.button.call_args.kwargs['disabled'])
            save.assert_not_called()
            fake.button.reset_mock()
            auto.render(ads,r,w,source_matches=False)
            self.assertTrue(fake.button.call_args.kwargs['disabled'])
            save.assert_not_called()

    def test_compact_new_ad_editor_has_only_post_action_and_no_cover_download(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string("""
import streamlit as st
from unittest.mock import patch
import ads_page as ads
from tests.test_ads_posting_handoff import completed_ad
r,w=completed_ad('Instant Experience')
with patch.object(ads, '_process_ads_image_upload'), patch.object(ads, '_render_instant_experience_copy_csv_control'), patch.object(ads, '_render_final_ad_review'):
    ads._render_instant_experience_concepts(r,w)
    ads._render_ads_final_actions(r,w)
""")
        app.run(timeout=20)
        self.assertFalse(list(app.exception))
        labels=[b.label for b in app.button]
        self.assertEqual(labels.count('Post now'),1)
        self.assertFalse(any('Save' in label or 'Open folder' in label for label in labels))
        self.assertFalse(list(app.get('download_button')))
        self.assertFalse(any('Original size' in c.value or ' MB' in c.value for c in app.caption))
        self.assertEqual(len(app.get('file_uploader')),3)
        self.assertTrue(app.text_area)
