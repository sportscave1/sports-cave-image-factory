"""Sectioned campaign authoring; isolated SQL and mocked delivery only."""
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from crm_campaign_content import render_campaign, settings, preflight, validate_document
from crm_campaign_sections import section_defaults, FOOTER_TOKEN
from crm_campaign_footer import prepare_footer
from crm_html_workspace import PREVIEW_WIDTHS
from tests.test_crm_simple_editor import document, HTML
from tests.test_crm_resend_marketing import ENV
from tests.test_crm import ADMIN


def sectioned():
    doc = document()
    doc['html_sections'] = section_defaults(settings(ENV))
    return doc


class SectionTests(unittest.TestCase):
    def test_defaults_and_order_and_plain_text(self):
        doc = sectioned()
        doc['html_sections'] = {'header':'<p>Custom header</p>', 'footer':'<p>Custom footer</p>' + FOOTER_TOKEN}
        original = deepcopy(doc)
        result = render_campaign(doc, settings(ENV))
        for source in (result['html'], result['text']):
            self.assertLess(source.index('Custom header'), source.index('A collector moment'))
            self.assertLess(source.index('A collector moment'), source.index('Custom footer'))
            self.assertNotIn('Unsubscribe', source)
        self.assertEqual(doc, original)
        self.assertNotIn(FOOTER_TOKEN, result['html'])
        self.assertTrue(preflight(doc, ENV)['test_ready'])
        self.assertFalse(preflight(doc, ENV)['live_ready'])

    def test_default_header_has_no_invented_asset_and_body_stays_required(self):
        doc = sectioned()
        self.assertIn('SPORTS CAVE', doc['html_sections']['header'])
        self.assertNotIn('<img', doc['html_sections']['header'])
        self.assertIn('{{UNSUBSCRIBE_URL}}', doc['html_sections']['footer'])
        doc['custom_html'] = ''
        self.assertFalse(preflight(doc, ENV)['test_ready'])

    def test_legacy_tokens_never_inject_a_footer(self):
        cfg = settings({**ENV, 'BUSINESS_POSTAL_ADDRESS':'Configured business address'})
        for footer in ('', FOOTER_TOKEN * 2,
                       '<div hidden style="display:none;position:fixed;height:0;overflow:hidden">' + FOOTER_TOKEN,
                       '</td></tr></table><script>evil()</script><table><tr><td>Custom footer'):
            with self.subTest(footer=footer):
                doc = sectioned(); doc['html_sections']['footer'] = footer
                output = render_campaign(doc, cfg)
                self.assertNotIn('Configured business address', output['html'])
                self.assertNotIn('You’re receiving this marketing email', output['html'])
                self.assertNotIn('Unsubscribe', output['html'])
                self.assertNotIn('<script', output['html'])
                self.assertNotIn(FOOTER_TOKEN, output['html'])
                self.assertNotIn('Configured business address', output['text'])

    def test_checks_cover_header_and_footer_without_mutating_source(self):
        for section in ('header','footer'):
            for source in ('<img src="https://example.com/a.png">', '<a href="javascript:bad">Bad</a>', '<script>bad()</script>'):
                doc = sectioned(); doc['html_sections'][section] = source
                self.assertFalse(preflight(doc, ENV)['test_ready'])
                self.assertEqual(doc['html_sections'][section], source)

    def test_validation_and_combined_size_limit(self):
        for sections in (None, {'header':1,'footer':''}, {'header':'x'}, {'header':'x'*95000,'footer':''}):
            doc = sectioned(); doc['html_sections'] = sections
            with self.assertRaises(ValueError):validate_document(doc)

    def test_legacy_path_keeps_source_and_one_existing_system_header_footer(self):
        doc = document(); before = deepcopy(doc)
        output = render_campaign(doc, settings(ENV))
        self.assertEqual(doc, before)
        self.assertEqual(output['html'].count('CAMPAIGN TEST / PREVIEW'), 1)
        self.assertEqual(output['html'].count('Unsubscribe'), 1)
        self.assertNotIn('html_sections', doc)
        self.assertEqual(doc['custom_html'], HTML)

    def test_responsive_widths_remain_and_message_is_not_fixed_to_preview(self):
        self.assertEqual(PREVIEW_WIDTHS, (600,430,390,375,320))
        rendered = render_campaign(sectioned())['html']
        self.assertIn('width="100%"', rendered)
        self.assertIn('max-width:600px', rendered)
        self.assertIn('width=device-width', rendered)
        self.assertNotIn('width="390"', rendered)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires disposable SQL fixture')
class SectionPersistenceTests(unittest.TestCase):
    def setUp(self):
        from crm_campaign_store import CampaignStore
        from tests.crm_db_fixture import connect
        self.store = CampaignStore(connect)

    def test_exact_sources_survive_save_reload_history_duplicate_and_template(self):
        doc = sectioned()
        doc['custom_html'] = '\r\n' + HTML + '\n  '
        doc['html_sections'] = {'header':' <h1>My header</h1>\r\n', 'footer':'<p>Closing note</p>\n' + FOOTER_TOKEN}
        row = self.store.save(ADMIN, 'Sections persistence', doc, env=ENV)
        self.assertEqual(self.store.draft(row['id'])['document'], doc)
        changed = deepcopy(doc); changed['html_sections']['header'] += '<p>Edited header</p>'
        row = self.store.save(ADMIN, row['name'], changed, row['id'], row['version'], env=ENV)
        self.assertEqual(self.store.draft(row['id'])['document'], changed)
        self.assertIn('content_changed', [h['action'] for h in self.store.history(row['id'])])
        duplicate = self.store.duplicate(ADMIN, row['id'])
        self.assertEqual(duplicate['document']['html_sections'], changed['html_sections'])
        saved = self.store.save_design(ADMIN, 'Sections template', changed)
        self.assertEqual(self.store.template_document(saved)['html_sections'], changed['html_sections'])

    def test_preview_equals_mocked_internal_test_and_repeat_is_not_resent(self):
        doc = sectioned(); row = self.store.save(ADMIN, 'Section render parity', doc, env=ENV)
        sending = self.store.setting('sending')
        self.store.save_setting(ADMIN, 'sending', {'internal_recipients':['manual@example.test'], 'smart_hours':16}, sending['version'])
        wire = Mock(); wire.post.return_value = Mock(status_code=200, json=lambda:{'id':str(uuid.uuid4())})
        operation = str(uuid.uuid4())
        expected = render_campaign(row['document'], self.store.render_settings(ENV))
        with patch('requests.sessions.Session.request', side_effect=AssertionError('External network forbidden')), patch('crm_resend_marketing._audit', return_value=True):
            for _ in range(2):
                self.store.test_campaign(ADMIN, row['id'], row['version'], recipient='manual@example.test', confirmed=True, operation_id=operation, env=ENV, session=wire)
        wire.post.assert_called_once()
        payload = wire.post.call_args.kwargs['json']
        self.assertEqual(payload['html'], expected['html'])
        self.assertEqual(payload['text'], expected['text'])
        self.assertEqual(payload['to'], ['manual@example.test'])

    def test_ui_defaults_rerun_and_edits_persist_without_hidden_conversions(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at = AppTest.from_string(SCRIPT); at.session_state['route']='CRM Campaigns'; at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual([t.label for t in at.tabs], ['Campaign Settings','HTML','Templates'])
        # Streamlit AppTest classifies expanders with an explicit icon as status.
        sections = {e.label:e.proto.expanded for e in [*at.expander, *at.status] if e.label in ('Header','Footer')}
        self.assertEqual(sections, {'Header':False, 'Footer':False})
        from crm_middle_sections import middle_sections, apply_event
        doc = at.session_state['campaign_editor']['document']
        self.assertEqual(middle_sections(doc)[0]['html'], '')
        apply_event(doc, {'type':'html','base':['html-1'],'id':'html-1','html':HTML})
        for label, value in [('Header HTML','<p>Saved header</p>\n'), ('Footer HTML','<p>Saved footer</p>')]:
            next(t for t in at.text_area if t.label==label).set_value(value)
        next(b for b in at.button if b.label=='Save draft').click().run(timeout=20)
        self.assertFalse(at.exception)
        saved = self.store.draft(at.session_state['campaign_editor']['id'])['document']
        self.assertEqual(saved['custom_html'], HTML)
        self.assertEqual(saved['html_sections'], {'header':'<p>Saved header</p>\n', 'footer':prepare_footer('<p>Saved footer</p>')})
        at.run(); self.assertEqual(at.session_state['campaign_editor']['document'], saved)
        old = self.store.save(ADMIN, 'Legacy full HTML', document(), env=ENV)
        fresh = AppTest.from_string(SCRIPT); fresh.session_state['route']='CRM Campaigns'
        fresh.session_state['campaign_editor']=deepcopy(old); fresh.session_state['campaign_saved']=deepcopy(old)
        fresh.run(timeout=20); fresh.run()
        self.assertFalse(fresh.exception)
        self.assertEqual(fresh.session_state['campaign_editor']['document']['custom_html'], old['document']['custom_html'])
        self.assertNotIn('html_sections', fresh.session_state['campaign_editor']['document'])
