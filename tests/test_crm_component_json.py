"""Production-shaped PostgreSQL values at the JavaScript boundary; no external I/O."""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from crm_component_json import json_safe, render_component
from crm_campaign_library import library_rows, insert_saved_template, save_template
from crm_campaign_content import new_document
from crm_template_cache import invalidate


class ComponentJSONTests(unittest.TestCase):
    def tearDown(self):
        invalidate()

    def test_recursive_boundary_preserves_source_and_string_ids(self):
        identity = uuid4()
        source = {'sections': [{'id': identity, 'nested': {'ref': identity}}],
                  'templates': ({'id': identity, 'name': 'Trust Icons'},),
                  'warnings': {identity: ['issue']}, 'ack': identity,
                  'date': date(2026, 9, 29), 'updated': datetime(2026, 9, 29, tzinfo=timezone.utc),
                  'price': Decimal('123.4567890123456789'), 'tags': {'a', 'b'}, 'string_id': 'unchanged'}
        before = deepcopy(source)
        result = json_safe(source)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result['sections'][0]['nested']['ref'], str(identity))
        self.assertEqual(result['templates'][0]['id'], str(identity))
        self.assertEqual(result['warnings'], {str(identity): ['issue']})
        self.assertEqual(result['ack'], str(identity))
        self.assertEqual(result['date'], '2026-09-29')
        self.assertEqual(result['price'], '123.4567890123456789')
        self.assertEqual(result['string_id'], 'unchanged')
        self.assertEqual(source, before)

    def test_unsupported_values_fail_without_logging_content(self):
        component = Mock()
        with patch('streamlit.error') as error, self.assertLogs('crm_component_json') as logs:
            self.assertIsNone(render_component(component, sections=[object()]))
        error.assert_called_once()
        component.assert_not_called()
        self.assertIn('type=TypeError', logs.output[0])

    def test_marshalling_error_is_contained(self):
        from streamlit.components.v1.custom_component import MarshallComponentException
        component = Mock(side_effect=MarshallComponentException('private payload'))
        with patch('streamlit.error') as error, self.assertLogs('crm_component_json') as logs:
            self.assertIsNone(render_component(component, sections=[]))
        error.assert_called_once()
        self.assertNotIn('private payload', str(logs.output))

    def test_uuid_cached_template_insertion_and_edit_keep_identity(self):
        identity = uuid4()
        row = {'id': identity, 'name': 'Trust Icons', 'version': 1, 'kind': 'Campaign',
               'content': {'format': 'campaign_blocks_v1'}}
        body = new_document(); body.update(content_mode='HTML', custom_html='<p>Trust Icons</p>')
        store = Mock(connect=object())
        store.html_library.return_value = [row]
        store.get.return_value = {**row, 'content': {**row['content'], 'document': body}}
        store.template_document.side_effect = lambda r: deepcopy(r['content']['document'])
        for _ in range(2):
            payload = json_safe({'templates': library_rows(store)})
            json.dumps(payload)
            doc = new_document(); doc.update(content_mode='HTML', custom_html='')
            insert_saved_template(store, doc, payload['templates'][0]['id'], 1)
            self.assertEqual(doc['template_ref']['id'], str(identity))
            self.assertEqual(doc['middle_sections'][0]['html'], '<p>Trust Icons</p>')
        store.html_library.assert_called_once_with(metadata=True)
        store.get.assert_called_once_with('templates', identity)
        save_template(store, {}, 'Edited', '<p>Edited</p>', library_rows(store)[0])
        self.assertEqual(store.save_design.call_args.args[-2:], (identity, 1))
        self.assertIsInstance(library_rows(store)[0]['id'], type(identity))

    def test_actual_middle_component_receives_safe_cached_metadata(self):
        from crm_section_ui import middle_editor
        identity = uuid4()
        store = Mock(connect=object())
        store.html_library.return_value = [{'id': identity, 'name': 'Trust Icons', 'version': 1}]
        with self.assertRaisesRegex(TypeError, 'UUID'):
            json.dumps({'templates': library_rows(store)})
        doc = new_document(); doc.update(content_mode='HTML', custom_html='<p>Body</p>')
        received = []
        def component(**payload):
            callback=payload.pop('on_change',None)
            self.assertTrue(callable(callback)) # Streamlit consumes callbacks outside JSON.
            received.append(json.loads(json.dumps(payload)))
        with patch('crm_section_ui.st') as ui, patch('crm_section_ui.components.declare_component', return_value=component):
            ui.session_state = {}
            middle_editor(doc, 'fixture', None, store)
            middle_editor(doc, 'fixture', None, store)
        self.assertEqual(received[0]['templates'][0]['id'], str(identity))
        self.assertEqual(received[0], received[1])
        store.html_library.assert_called_once()
        store.get.assert_not_called()

    def test_recovery_component_handles_database_uuid(self):
        from crm_recovery_ui import recovery_bridge
        identity = uuid4()
        editor = {'id': identity, 'version': 1, 'name': 'Draft', 'document': new_document()}
        received = []
        def component(**payload):
            received.append(json.loads(json.dumps(payload)))
        with patch('crm_recovery_ui.st') as ui, patch('crm_recovery_ui.preference_key', return_value='scope'), patch('crm_recovery_ui.components.declare_component', return_value=component):
            ui.session_state = {}
            recovery_bridge(Mock(), {}, editor, 'fixture')
        self.assertEqual(received[0]['editor']['id'], str(identity))
        self.assertEqual(editor['id'], identity)

    @unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES') == '1', 'Disposable SQL required')
    def test_campaign_page_editor_and_templates_with_uuid_metadata(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        from crm_campaign_store import CampaignStore
        original = CampaignStore.html_library
        from uuid import UUID
        def rows(store, **kwargs):
            return [{**row, 'id': UUID(str(row['id']))} for row in original(store, **kwargs)]
        with patch.object(CampaignStore, 'html_library', rows):
            at = AppTest.from_string(SCRIPT)
            at.session_state['route'] = 'CRM Campaigns'
            at.run(timeout=20)
            for panel in ('Editor', 'Templates', 'Editor'):
                at.session_state[at.session_state['campaign_edit_key']+'panel'] = panel
                at.run(timeout=20)
                self.assertFalse(at.exception)
                self.assertFalse(at.error)
