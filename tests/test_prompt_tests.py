import unittest
from unittest.mock import Mock, patch
from contextlib import nullcontext
from streamlit.testing.v1 import AppTest
from prompt_test_inputs import database_choices, design_choices, edition_choices
from prompt_test_runner import build_prompt


class CopyTests(unittest.TestCase):
    def test_full_draft_applies_product_without_network(self):
        draft = 'FIRST {PRODUCT_NAME} / {{product_url}}\nLAST {COUNTRY} âŸªslot:0âŸ«'
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No network')):
            result = build_prompt(draft, 'Ads', {'title': 'Edition {COUNTRY}', 'context': {'handle': 'edition', 'details': 'Verified detail'}})
        self.assertIn('FIRST Edition {COUNTRY} / https://www.sportscaveshop.com/products/edition', result)
        self.assertIn('LAST {COUNTRY} âŸªslot:0âŸ«', result)
        self.assertIn('Verified detail', result)

    def test_custom_url_needs_no_catalogue_or_ai(self):
        url = 'https://www.sportscaveshop.com/products/allan-moffat-500-miles-alone-wall-art'
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No network')):
            result = build_prompt('FULL DRAFT {PRODUCT_URL}', 'Ads', {'title': url, 'context': {'details': ''}})
        self.assertIn('Product URL: ' + url, result)
        self.assertIn('FULL DRAFT ' + url, result)
        self.assertNotIn('Product name: https', result)

    def test_all_workflows_preserve_complete_text(self):
        for workflow in ('New design', 'Refresh', 'Edit design', 'Upload', 'Ads'):
            draft = '<<<SECTION 1>>>\nComplete prompt\n<<<END 1>>>\n' + 'x' * 50000
            result = build_prompt(draft, workflow, {'title': 'Selected design', 'context': {'path_display': '/Review/Design.psd'}})
            self.assertTrue(result.endswith(draft))
            self.assertIn('/Review/Design.psd', result)


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


class PanelTests(unittest.TestCase):
    def test_lazy_inputs_and_immediate_copyable_draft_updates(self):
        source = "import streamlit as st\nfrom prompt_library import Prompt\nfrom prompt_test_panel import render\ntext=st.text_area('Editor', 'unsaved instructions {PRODUCT_NAME}')\nrender(st, Prompt('ads_page.py','TEST','Ads','deployed'), text, {'id':'owner'})"
        item = {'id': '1', 'title': 'Test Product', 'source': 'Product catalogue', 'context': {}}
        with patch('prompt_test_panel.load_choices', return_value=[item]) as load, patch('requests.sessions.Session.request', side_effect=AssertionError('No AI or network')):
            page = AppTest.from_string(source).run()
            load.assert_not_called()
            page.toggle[0].set_value(True).run()
            self.assertEqual(load.call_count, 1)
            self.assertFalse(page.exception)
            self.assertIn('unsaved instructions Test Product', page.code[0].value)
            self.assertFalse(any(b.label == 'Test prompt' for b in page.button))
            page.text_area[0].set_value('changed full draft').run()
            self.assertTrue(page.code[0].value.endswith('changed full draft'))
            self.assertFalse(page.exception)

    def test_custom_url_is_immediately_copyable_without_loading(self):
        source = "import streamlit as st\nfrom prompt_library import Prompt\nfrom prompt_test_panel import render\nrender(st, Prompt('ads_page.py','TEST','Ads','deployed'), 'Full draft {PRODUCT_URL}', {})"
        with patch('prompt_test_panel.load_choices', return_value=[]) as load, patch('requests.sessions.Session.request', side_effect=AssertionError('No network')):
            page = AppTest.from_string(source).run()
            page.toggle[0].set_value(True).run()
            page.checkbox[0].set_value(True).run()
            page.text_input[0].set_value('https://www.sportscaveshop.com/products/example').run()
            self.assertFalse(page.exception)
            self.assertIn('Full draft https://www.sportscaveshop.com/products/example', page.code[0].value)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(len(page.text_area), 0)


class EditionPickerTests(unittest.TestCase):
    def test_read_only_names_and_urls_from_edition_ops(self):
        cur = Mock()
        cur.fetchall.return_value = [{'handle': 'z', 'title': 'Zed'}, {'handle': 'allan-moffat', 'title': 'Allan Moffat'}]
        rows = edition_choices(InputTests().connection(cur))
        self.assertEqual(rows[0]['title'], 'Allan Moffat')
        self.assertEqual(rows[0]['source'], 'Edition Ops')
        self.assertEqual(rows[0]['context'], {'product_url': 'https://www.sportscaveshop.com/products/allan-moffat'})
        sql = cur.execute.call_args.args[0]
        self.assertIn('FROM edition_products', sql)
        self.assertTrue(sql.startswith('SELECT'))
        self.assertIn('DISTINCT ON', sql)

    def test_dropdown_changes_applied_url_without_details_field_or_reloading(self):
        source = "import streamlit as st\nfrom prompt_library import Prompt\nfrom prompt_test_panel import render\nrender(st, Prompt('ads_page.py','TEST','Ads','deployed'), 'Full draft {PRODUCT_URL}', {})"
        rows = [dict(id=str(i), title=title, source='Edition Ops', context={'product_url': 'https://www.sportscaveshop.com/products/' + str(i)}) for i,title in enumerate(['Allan Moffat', 'Shane Warne'])]
        with patch('prompt_test_panel.load_choices', return_value=rows) as load:
            page = AppTest.from_string(source).run()
            load.assert_not_called()
            page.toggle[0].set_value(True).run()
            picker = next(s for s in page.selectbox if s.label == 'Edition Ops product')
            picker.set_value('1').run()
            self.assertFalse(page.exception)
            self.assertEqual(len(page.text_area), 0)
            self.assertEqual(page.text_input[0].value, rows[1]['context']['product_url'])
            self.assertTrue(page.code[0].value.endswith('Full draft ' + rows[1]['context']['product_url']))
            self.assertEqual(load.call_count, 1)
            next(s for s in page.selectbox if s.label == 'Edition Ops product').set_value('0').run()
            self.assertEqual(page.text_input[0].value, rows[0]['context']['product_url'])
            self.assertEqual(load.call_count, 1)
