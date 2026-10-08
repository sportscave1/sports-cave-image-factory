"""Background refreshes must not overwrite newer edits."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch, MagicMock

import edition_ops as ops
import edition_version_ui as ui
import edition_cursor_overrides as overrides


class EditionVersionUiTests(TestCase):
    def test_sync_feedback_counts_only_confirmed_readbacks_and_hides_sql(self):
        state={'edition-sync-watching':{'ok','bad','pending'}}
        fake=MagicMock();fake.session_state=state
        conn=MagicMock()
        conn.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchall.return_value=[
            dict(shopify_handle='ok',product_title='Confirmed',status='active',metafields_sync_status='Synced'),
            dict(shopify_handle='bad',product_title='Retry product',status='active',metafields_sync_status='Failed',last_metafield_error='SELECT secret_internal_function()'),
            dict(shopify_handle='pending',product_title='Pending',status='active',metafields_sync_status='Pending')]
        with patch.object(ui,'st',fake),patch.object(ui.versions.backend,'connect',return_value=conn),patch.object(ui,'refresh_handle') as refresh:
            ui.sync_status.__wrapped__()
        refresh.assert_called_once_with('ok')
        self.assertEqual(state['edition-sync-watching'],{'bad','pending'})
        self.assertIn('1 editions verified in Shopify · 1 pending · 1 require attention',str(fake.caption.call_args_list))
        self.assertNotIn('secret_internal_function',str(fake.caption.call_args_list))

    def test_missing_schema_stops_batch_and_retains_all_edits(self):
        old=[ops._normalise_row(dict(edition_product_id=str(i),edition_run_id='run-'+str(i),handle=str(i),edition_next_number=95)) for i in range(331)]
        edited=deepcopy(old);edited[0]['edition_next_number']=5;edited[10]['edition_next_number']=1
        state={ops.ROWS_KEY:edited,ops.ORIGINAL_ROWS_KEY:old,ops.EDITOR_ROWS_KEY:deepcopy(edited)}
        with patch.object(ui,'st',SimpleNamespace(session_state=state)),patch.object(overrides,'require_schema',side_effect=overrides.SchemaUnavailable('Database upgrade required')) as check,patch.object(overrides,'save') as save,patch.object(ops,'_save_changed_rows',side_effect=AssertionError('No fallback')):
            ui.save_cursor_changes()
        check.assert_called_once();save.assert_not_called()
        self.assertEqual(state[ops.ROWS_KEY],edited);self.assertEqual(state[ops.ORIGINAL_ROWS_KEY],old)
        self.assertEqual(state[ops.NOTICE_KEY],'Database upgrade required')

    def test_only_edited_rows_save_and_failed_input_is_retained(self):
        old=[ops._normalise_row(dict(edition_product_id=str(i),edition_run_id='run-'+str(i),handle=str(i),edition_next_number=95)) for i in range(331)]
        edited=deepcopy(old);edited[0]['edition_next_number']=5;edited[10]['edition_total']=90
        state={ops.ROWS_KEY:edited,ops.ORIGINAL_ROWS_KEY:old,ops.EDITOR_ROWS_KEY:deepcopy(edited)}
        with patch.object(ui,'st',SimpleNamespace(session_state=state)),patch.object(overrides,'require_schema'),patch.object(overrides,'save',side_effect=[{},RuntimeError('internal SQL details')]) as save:
            ui.save_cursor_changes()
        self.assertEqual(save.call_count,2)
        self.assertEqual(state[ops.ORIGINAL_ROWS_KEY][0]['edition_next_number'],5)
        self.assertEqual(state[ops.ORIGINAL_ROWS_KEY][10]['edition_total'],100)
        self.assertEqual(state[ops.ROWS_KEY][10]['edition_total'],90)
        self.assertNotIn('internal SQL',str(state['edition-save-errors']))

    def test_pending_refresh_preserves_unsaved_input_and_concurrency_baseline(self):
        original=ops._normalise_row({'edition_product_id':'1','handle':'art','edition_next_number':10})
        edited={**original,'edition_next_number':17}
        state={ops.ROWS_KEY:[deepcopy(edited)],ops.EDITOR_ROWS_KEY:[deepcopy(edited)],ops.ORIGINAL_ROWS_KEY:[deepcopy(original)]}
        backend=SimpleNamespace(list_edition_products_read_only=lambda **kw:[{'id':1,'shopify_handle':'art','next_edition_number':11}])
        with patch.object(ui,'st',SimpleNamespace(session_state=state)),patch.object(ops,'_configured_supabase_backend',return_value=backend):
            ui.refresh_handle('art')
        self.assertEqual(state[ops.ROWS_KEY][0]['edition_next_number'],17)
        self.assertEqual(state[ops.ORIGINAL_ROWS_KEY][0]['edition_next_number'],10)

    def test_refresh_updates_only_affected_product(self):
        original=ops._normalise_row({'edition_product_id':'1','handle':'art','edition_next_number':10})
        other=ops._normalise_row({'edition_product_id':'2','handle':'other','edition_next_number':23})
        state={key:deepcopy([original,other]) for key in (ops.ROWS_KEY,ops.EDITOR_ROWS_KEY,ops.ORIGINAL_ROWS_KEY)}
        backend=SimpleNamespace(list_edition_products_read_only=lambda **kw:[{'id':1,'shopify_handle':'art','next_edition_number':11}])
        with patch.object(ui,'st',SimpleNamespace(session_state=state)),patch.object(ops,'_configured_supabase_backend',return_value=backend):
            ui.refresh_handle('art')
        self.assertEqual(state[ops.ROWS_KEY][0]['edition_next_number'],11)
        self.assertEqual(state[ops.ROWS_KEY][1],other)
