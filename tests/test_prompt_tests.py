import json
import os
import unittest
from unittest.mock import Mock, patch
from contextlib import nullcontext
from streamlit.testing.v1 import AppTest
from prompt_test_inputs import database_choices, design_choices, prepare
from prompt_test_runner import run


class RunnerTests(unittest.TestCase):
    def test_draft_and_selected_item_sent_without_tools_or_storage(self):
        response = Mock(ok=True)
        response.json.return_value = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Trial listing'}]}]}
        post = Mock(return_value=response)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic'}):
            result = run('UNSAVED DRAFT', 'Upload', {'title': 'Selected artwork'}, b'jpeg', post=post)
        payload = post.call_args.kwargs['json']
        self.assertFalse(payload['store'])
        self.assertNotIn('tools', payload)
        self.assertIn('UNSAVED DRAFT', payload['input'][0]['content'][0]['text'])
        self.assertIn('Selected artwork', payload['input'][0]['content'][0]['text'])
        self.assertEqual(payload['input'][0]['content'][1]['type'], 'input_image')
        self.assertEqual(result['text'], 'Trial listing')
        self.assertFalse(result['incomplete'])
        self.assertEqual(post.call_count, 1)

    def test_quota_error_is_actionable_without_leaking_provider_body(self):
        response = Mock(ok=False, status_code=429)
        response.json.return_value = {'error': {'code': 'insufficient_quota', 'message': 'private detail'}}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic'}), self.assertRaisesRegex(ValueError, 'no available API quota') as raised:
            run('draft', 'Ads', {'title': 'Product'}, post=Mock(return_value=response))
        self.assertNotIn('private detail', str(raised.exception))

    def test_unavailable_default_model_uses_one_accessible_fallback(self):
        rejected = Mock(ok=False, status_code=403)
        rejected.json.return_value = {'error': {'code': 'model_not_found'}}
        success = Mock(ok=True)
        success.json.return_value = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Trial'}]}]}
        models = Mock(ok=True)
        models.json.return_value = {'data': [{'id': 'gpt-4.1-mini'}]}
        post = Mock(side_effect=[rejected, success])
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic', 'OPENAI_PROMPT_TEST_MODEL': ''}):
            result = run('draft', 'Ads', {'title': 'Product'}, post=post, get=Mock(return_value=models))
        self.assertEqual(result['model'], 'gpt-4.1-mini')
        self.assertEqual(post.call_count, 2)

    def test_timeout_never_retries(self):
        import requests
        post = Mock(side_effect=requests.Timeout())
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic'}), self.assertRaisesRegex(ValueError, 'No automatic retry'):
            run('draft', 'Ads', {'title': 'Product'}, post=post)
        self.assertEqual(post.call_count, 1)

    def test_provider_error_does_not_expose_response_body(self):
        post = Mock(return_value=Mock(ok=False, text='secret-provider-detail'))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic'}), self.assertRaisesRegex(ValueError, 'model service'):
            run('draft', 'Ads', {'title': 'Product'}, post=post)


class InputTests(unittest.TestCase):
    def connection(self, cur):
        conn = Mock()
        conn.cursor.return_value = nullcontext(cur)
        return lambda: nullcontext(conn)

    def test_new_design_uses_home_design_suggestions(self):
        cur = Mock()
        cur.fetchone.return_value = {'value': {'date': '2026-11-19', 'design_recommendations': [{'title': 'Home suggestion', 'recommendation': 'Specific story'}]}}
        rows = database_choices('New design', self.connection(cur))
        self.assertEqual(rows[0]['title'], 'Home suggestion')
        self.assertEqual(rows[0]['context']['recommendation'], 'Specific story')
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in cur.execute.call_args_list))

    def test_refresh_uses_shortlist_not_any_catalog_product(self):
        cur = Mock()
        cur.fetchall.side_effect = [[{'key': 'home_design_refresh', 'value': {'candidates': [{'product_id': '123', 'title': 'Refresh me'}]}}],
                                  [{'shopify_product_id': 'gid://shopify/Product/123', 'title': 'Refresh me'}, {'shopify_product_id': '456', 'title': 'Unrelated'}]]
        rows = database_choices('Refresh', self.connection(cur))
        self.assertEqual([r['title'] for r in rows], ['Refresh me'])
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in cur.execute.call_args_list))

    def test_upload_dropdown_lists_review_designs_across_pages(self):
        from product_upload_dropbox import REVIEW
        provider = Mock()
        def entry(name, identity):
            return {'.tag': 'file', 'id': identity, 'rev': 'revision', 'name': name, 'path_display': REVIEW + '/' + name}
        provider.api.list_folder_page.side_effect = [
            {'entries': [entry('One.psd', 'id:one'), entry('One - TRIAL.psd', 'id:trial')], 'has_more': True, 'cursor': 'page-two'},
            {'entries': [entry('Two.psd', 'id:two')], 'has_more': False}]
        rows = design_choices(provider)
        self.assertEqual([r['title'] for r in rows], ['One', 'Two'])
        self.assertEqual(provider.api.list_folder_page.call_count, 2)

    def test_design_revision_change_rejected_before_thumbnail(self):
        provider = Mock()
        provider.metadata_if_present.return_value = {'id': 'id:one', 'rev': 'new'}
        with self.assertRaisesRegex(ValueError, 'design changed'):
            prepare({'source': 'Design Studio', 'context': {'id': 'id:one', 'rev': 'old'}}, provider)
        provider.api.get_psd_thumbnail_bytes.assert_not_called()


class PanelTests(unittest.TestCase):
    def test_lazy_selection_unsaved_draft_and_stale_result(self):
        source = "import streamlit as st\nfrom prompt_library import Prompt\nfrom prompt_test_panel import render\ntext=st.text_area('Editor', 'unsaved instructions')\nrender(st, Prompt('ads_page.py','TEST','Ads','deployed'), text, {'id':'owner'})"
        item = {'id': '1', 'title': 'Test Product', 'source': 'Product catalogue', 'context': {}}
        def generated(text, workflow, selected, image):
            return dict(text='Generated trial', item=selected, model='test-model', created_at='2026-11-19T00:00:00', incomplete=False, draft=text)
        with patch('prompt_test_panel.load_choices', return_value=[item]) as load, patch('prompt_test_panel.configuration', return_value=('synthetic','test-model')), patch('prompt_test_panel.prepare', return_value=(item,None)), patch('prompt_test_panel.run', side_effect=generated) as generate:
            page = AppTest.from_string(source).run()
            load.assert_not_called()
            page.toggle[0].set_value(True).run()
            next(b for b in page.button if b.label == 'Load / refresh test inputs').click().run()
            next(b for b in page.button if b.label == 'Test prompt').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(generate.call_args.args[0], 'unsaved instructions')
            self.assertTrue(any(m.value == 'Generated trial' for m in page.markdown))
            page.text_area[0].set_value('changed draft').run()
            self.assertTrue(any('Previous test result' in w.value for w in page.warning))
            self.assertEqual(generate.call_count, 1)
