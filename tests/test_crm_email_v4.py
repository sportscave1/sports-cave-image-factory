"""State correctness and bounded publication processing. All data is fabricated."""
from copy import deepcopy
from datetime import timedelta
from threading import Event,Thread
from unittest.mock import Mock,patch
import unittest
from tests.test_crm_simple_editor import document


class EditorStateTests(unittest.TestCase):
    def test_forced_unchanged_automation_save_does_no_io(self):
        from crm_email_editor_context import flush_automation
        store=Mock();editor={'id':'test','name':'Flow','version':1,'document':document()}
        state={'automation_editor':editor,'automation_saved':deepcopy(editor),'automation_editor_context':(store,{})}
        self.assertTrue(flush_automation(state,force=True));store.save.assert_not_called()
        editor['document']['custom_html']+='\n '
        store.save.return_value=deepcopy(editor)
        self.assertTrue(flush_automation(state,force=True));store.save.assert_called_once()
        self.assertTrue(state['automation_saved']['document']['custom_html'].endswith('\n '))

    def test_unchanged_campaign_flush_does_no_io_and_revert_is_clean(self):
        from crm_campaign_recovery import flush_current
        editor={'id':'test','name':'Campaign','version':1,'document':document()}
        state={'campaign_editor':editor,'campaign_saved':deepcopy(editor),'campaign_recovery_context':(Mock(),{})}
        original=editor['document']['custom_html'];editor['document']['custom_html']+=' changed';editor['document']['custom_html']=original
        with patch('streamlit.session_state',state),patch('crm_campaign_recovery.save_checkpoint') as save:
            self.assertTrue(flush_current(force=True));save.assert_not_called()

    def test_section_mount_has_no_product_lookup_or_document_mutation(self):
        from crm_section_ui import middle_editor
        from tests.test_crm_modular_catalogue import catalogue_doc
        doc=catalogue_doc();before=deepcopy(doc)
        with patch('crm_section_ui.st.session_state',{}),patch('crm_section_ui.components.declare_component'),patch('crm_section_ui.render_component',return_value=None),patch('crm_section_ui.refresh_catalogues') as refresh:
            middle_editor(doc,'local',Mock())
        self.assertEqual(before,doc);refresh.assert_not_called()

    def test_unchanged_native_blur_does_not_revoke_review_or_save(self):
        from crm_campaign_page import commit_editor_field
        editor={'name':'Flow','document':document()};editor['document']['copy_reviewed']=True
        with patch('streamlit.session_state',{'subject':editor['document']['content']['subject']}),patch('crm_campaign_page.flush_current') as flush:
            commit_editor_field(editor,'','subject')
        flush.assert_not_called();self.assertTrue(editor['document']['copy_reviewed'])

    def test_exact_undo_restores_review_but_whitespace_remains_a_change(self):
        from crm_email_editor_context import mark_content_edit,flush_automation
        editor={'id':'test','version':1,'name':'Flow','document':document()};editor['document']['copy_reviewed']=True
        store=Mock();state={'email_editor_mode':'automation','automation_editor':editor,'automation_saved':deepcopy(editor),'automation_editor_context':(store,{})}
        body=editor['document']['custom_html']
        editor['document']['custom_html']+=' ';mark_content_edit(state,editor)
        self.assertFalse(editor['document']['copy_reviewed'])
        editor['document']['custom_html']=body;mark_content_edit(state,editor)
        self.assertTrue(editor['document']['copy_reviewed'])
        self.assertTrue(flush_automation(state,force=True));store.save.assert_not_called()

    def test_presentation_normalization_does_not_mutate_stored_source(self):
        from crm_email_editor_context import editable_document
        from crm_abandoned_checkout import apply_template
        doc=document();apply_template(doc);before=deepcopy(doc)
        view=editable_document(doc)
        self.assertEqual(doc,before)
        self.assertFalse(any(s['type']=='abandoned_checkout_products' for s in view['middle_sections']))
        self.assertEqual(editable_document(view),view)

    def test_toolbar_snapshot_is_session_local_and_checks_fresh_marker(self):
        from crm_automation_toolbar import definition
        store=Mock();store.q.return_value={'updated_at':'1'};store.flow.return_value={'name':'A'}
        state={};self.assertEqual(definition(store,state,'a'),{'name':'A'})
        definition(store,state,'a');self.assertEqual(store.flow.call_count,1)
        store.q.return_value={'updated_at':'2'};store.flow.return_value={'name':'B'}
        self.assertEqual(definition(store,state,'a'),{'name':'B'})
        definition(store,{},'a');self.assertEqual(store.flow.call_count,3)


class PublicationLaneTests(unittest.TestCase):
    def test_same_durable_executor_runs_without_maintenance_or_ui(self):
        from crm_automation_publication import run
        stop=Event();called=Event();store=Mock()
        def execute(*args):called.set();stop.set();return True
        with patch('crm_automation_publication.tick',side_effect=execute) as tick:
            thread=Thread(target=run,args=(store,'owner',stop));thread.start();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertTrue(called.is_set());tick.assert_called_once_with(store,'owner')

    def test_idle_and_failure_polling_are_bounded(self):
        from crm_automation_publication import run
        for value,seconds in ((False,1),(RuntimeError('fixture'),5)):
            stop=Mock();stop.is_set.side_effect=[False,True]
            with patch('crm_automation_publication.tick',**({'side_effect':value} if isinstance(value,Exception) else {'return_value':value})):
                run(Mock(),'owner',stop)
            stop.wait.assert_called_once_with(seconds)

    def test_long_wait_is_explained_and_never_reports_success(self):
        from crm_automation_publication import progress_text
        from crm_logic import now
        for stage in ('QUEUED','RUNNING'):
            text=progress_text({'state':stage,'requested_at':now()-timedelta(seconds=45),'attempts':1})
            self.assertIn('taking longer',text);self.assertIn('45s',text)
            self.assertNotIn('success',text.lower())


class PublicationConnectionTests(unittest.TestCase):
    def test_reuses_socket_but_commits_each_transaction_and_closes_on_failure(self):
        from crm_publication_connection import Connection
        from unittest.mock import MagicMock
        first=MagicMock();first.closed=False;second=MagicMock();second.closed=False
        factory=Mock(side_effect=[first,second]);connection=Connection(factory)
        for _ in range(3):
            with connection() as conn:conn.execute('SELECT 1')
        self.assertTrue(first.autocommit);self.assertEqual(factory.call_count,1)
        self.assertEqual(first.transaction.call_count,3);first.close.assert_not_called()
        with self.assertRaises(ValueError):
            with connection():raise ValueError('validation failed')
        first.close.assert_called_once()
        with connection():pass
        self.assertEqual(factory.call_count,2);connection.close();second.close.assert_called_once()

    def test_commit_disconnect_propagates_without_replaying(self):
        from crm_publication_connection import Connection
        from unittest.mock import MagicMock
        raw=MagicMock();raw.closed=False;raw.transaction.return_value.__exit__.side_effect=ConnectionError('lost ack')
        connect=Mock(return_value=raw);connection=Connection(connect)
        with self.assertRaises(ConnectionError):
            with connection() as conn:conn.execute('UPDATE fixture')
        self.assertEqual(raw.execute.call_count,1);self.assertEqual(connect.call_count,1);raw.close.assert_called_once()
