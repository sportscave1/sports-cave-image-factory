"""Background refreshes must not overwrite newer edits."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import edition_ops as ops
import edition_version_ui as ui


class EditionVersionUiTests(TestCase):
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
