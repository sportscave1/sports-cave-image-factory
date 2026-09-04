import json
import socket
import unittest
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import edition_ops
import supabase_backend
from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest

from tests.test_edition_ops_stability import _FakeStreamlit, _product, _snapshot


def _page():
    import streamlit as st
    import edition_ops

    page = st.selectbox("Page", ["Edition Ops", "Home"], key="test_page")
    if page == "Edition Ops":
        edition_ops.render_page()
    else:
        st.title("Home")


class EditionOpsTableEditingTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("No network in tests")))
        for name in ("_write_snapshot", "_invalidate_edition_ops_cache", "record_activity_log"):
            self.stack.enter_context(patch.object(edition_ops, name))

    def test_visible_columns_editability_links_and_review_messages(self):
        row = dict(_product(), sync_status="needs_reconciliation", sync_error="Allocation requires review")
        fake_st = _FakeStreamlit({
            edition_ops.SNAPSHOT_LOADED_KEY: True,
            edition_ops.ROWS_KEY: [row], edition_ops.ORIGINAL_ROWS_KEY: [deepcopy(row)],
            edition_ops.IMPORT_WARNINGS_KEY: ["Existing import warning"],
        })
        fake_st.data_editor = Mock(side_effect=fake_st.data_editor)
        with patch.object(edition_ops, "st", fake_st), patch.object(
            edition_ops, "_configured_supabase_backend", return_value=object()
        ):
            edition_ops.render_page()
        kwargs = fake_st.data_editor.call_args.kwargs
        self.assertEqual(kwargs["column_order"], (
            "product_title", "handle", "edition_enabled", "edition_total", "edition_next_number",
            "edition_sold_count", "edition_remaining", "admin_url", "online_store_url",
        ))
        for field in ("edition_total", "edition_next_number", "edition_enabled"):
            self.assertNotIn(field, kwargs["disabled"])
            self.assertIn(field, edition_ops.EDITABLE_FIELDS)
        for field in ("handle", "edition_sold_count", "edition_remaining", "admin_url"):
            self.assertIn(field, kwargs["disabled"])
        for field in ("edition_status", "sync_status"):
            self.assertNotIn(field, fake_st.editor_payloads[0][0])
            self.assertIn(field, fake_st.session_state[edition_ops.ROWS_KEY][0])
            self.assertIn(field, edition_ops.CSV_COLUMNS)
        self.assertIn("Existing import warning", fake_st.warnings)
        self.assertIn("Some rows need review before they are fully synced.", fake_st.errors)
        self.assertIn("edition_status", edition_ops.SHOPIFY_MIRROR_METAFIELD_KEYS)

    def test_numeric_config_allows_sold_out_sentinel(self):
        config = edition_ops._column_config()["edition_next_number"]
        self.assertEqual(config["type_config"]["type"], "number")
        self.assertEqual(config["type_config"]["step"], 1)
        row = dict(_product(), edition_next_number=101, edition_sold_count=100, edition_remaining=0)
        self.assertEqual(edition_ops._save_validation_error(row, row), "")
        self.assertTrue(edition_ops._save_validation_error(dict(row, edition_next_number=102), row))

    def test_callback_maps_filtered_row_and_protects_readonly_fields(self):
        rows = [_product(1), _product(2), _product(3)]
        state = {edition_ops.ROWS_KEY: deepcopy(rows), edition_ops.ORIGINAL_ROWS_KEY: deepcopy(rows),
                 edition_ops.EDITOR_KEY: {"edited_rows": {0: {
                     "edition_next_number": 17, "edition_sold_count": 999,
                     "edition_remaining": 0, "handle": "wrong-product", "edition_status": "wrong",
                 }}}}
        with patch.object(edition_ops, "st", SimpleNamespace(session_state=state)):
            edition_ops._capture_editor_changes([rows[1]])
            edited = state[edition_ops.ROWS_KEY]
            self.assertEqual(edition_ops._editable_changed_keys(edited, rows), ["edition_product:2"])
            self.assertEqual(edited[1]["edition_next_number"], 17)
            self.assertEqual(edited[1]["sync_status"], "Unsaved")
            for field in ("edition_sold_count", "edition_remaining", "handle", "edition_status"):
                self.assertEqual(edited[1][field], rows[1][field])
            self.assertEqual(edited[0], rows[0])
            self.assertEqual(edited[2], rows[2])
            # Reverting a cell removes its dirty state.
            state[edition_ops.EDITOR_KEY]["edited_rows"][0] = {"edition_next_number": 2}
            edition_ops._capture_editor_changes([rows[1]])
            self.assertEqual(edition_ops._changed_rows(state[edition_ops.ROWS_KEY], rows), [])

    def test_actual_streamlit_edit_save_reload_and_navigation(self):
        stored = [_product(1), _product(2)]
        backend = Mock()

        def save(batch, **kwargs):
            for item in batch:
                record = next(row for row in stored if edition_ops._stable_row_key(row) == item["row_key"])
                record["edition_next_number"] = item["next_edition_number"]
            return [{"ok": True, "key": item["row_key"], "handle": item["handle"]} for item in batch]

        backend.update_edition_products_batch.side_effect = save
        backend.sync_product_edition_metafields_for_handles.side_effect = lambda handles, **kwargs: {
            "results": [{"handle": handle, "status": "updated"} for handle in handles]
        }
        self.stack.enter_context(patch.object(edition_ops, "_configured_supabase_backend", return_value=backend))
        self.stack.enter_context(patch.object(edition_ops, "_load_snapshot", side_effect=lambda: _snapshot(deepcopy(stored))))
        self.stack.enter_context(patch.object(edition_ops.shopify_sync, "get_config", return_value={"configured": True}))
        self.stack.enter_context(patch.object(edition_ops, "_render_advanced_controls"))
        app = AppTest.from_function(_page).run()
        self.assertFalse(app.exception)
        columns = json.loads(app.get("dataframe")[0].proto.columns)
        for field in ("edition_total", "edition_next_number", "edition_enabled"):
            self.assertFalse(columns[field].get("disabled", False))
        for field in ("edition_sold_count", "edition_remaining", "handle"):
            self.assertTrue(columns[field]["disabled"])
        self.assertEqual(columns["admin_url"]["type_config"]["type"], "link")

        def edit_next(value):
            table = app.get("dataframe")[0]
            widgets = app._tree.get_widget_states()
            widgets.widgets.append(WidgetState(id=table.proto.id, string_value=json.dumps({
                "edited_rows": {"0": {"edition_next_number": value}}, "added_rows": [], "deleted_rows": [],
            })))
            app._run(widgets)
            self.assertFalse(app.exception)

        edit_next(17)
        self.assertEqual(stored[0]["edition_next_number"], 1)
        self.assertIn("1 unsaved change", " ".join(item.value for item in app.caption))
        app.selectbox(key="test_page").select("Home").run()
        app.selectbox(key="test_page").select("Edition Ops").run()
        self.assertEqual(app.session_state[edition_ops.ROWS_KEY][0]["edition_next_number"], 17)
        app.button(key="edition-ops-save-changes").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(stored[0]["edition_next_number"], 17)
        self.assertEqual(stored[1], _product(2))
        batch = backend.update_edition_products_batch.call_args.args[0]
        self.assertEqual(len(batch), 1)
        self.assertTrue(batch[0]["manual_next_number_override"])
        self.assertEqual(batch[0]["expected_next_edition_number"], 1)
        self.assertIsNone(batch[0]["active"])
        self.assertIsNone(batch[0]["edition_total"])
        self.assertEqual(app.session_state[edition_ops.ROWS_KEY][0]["edition_sold_count"], 0)
        self.assertEqual(app.session_state[edition_ops.ROWS_KEY][0]["edition_remaining"], 100)
        self.assertIn("0 unsaved changes", " ".join(item.value for item in app.caption))
        backend.sync_product_edition_metafields_for_handles.assert_called_once_with(
            ["product-1"], config={"configured": True}, ensure_schema_first=False
        )
        edit_next(18)
        app.button(key="edition-ops-save-changes").click().run()
        self.assertEqual(stored[0]["edition_next_number"], 18)
        fresh = AppTest.from_function(_page).run()
        self.assertFalse(fresh.exception)
        self.assertEqual(fresh.session_state[edition_ops.ROWS_KEY][0]["edition_next_number"], 18)


class EditionOpsPointerPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.product = {
            "id": 7, "shopify_handle": "test-product", "shopify_product_gid": "gid://shopify/Product/7",
            "active_edition_run_id": 8, "edition_total": 100, "next_edition_number": 10,
            "sold_count": 9, "remaining_count": 91, "last_assigned_edition": 9, "active": True,
        }
        self.run = {"id": 8, "edition_total": 100, "next_edition_number": 10, "status": "active"}
        self.ledger = {"allocation_count": 5, "min_assigned": 1, "max_assigned": 9}
        self.cursor = Mock()
        self.cursor.fetchone.side_effect = lambda: dict(self.ledger)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.lookup = self.stack.enter_context(patch.object(
            supabase_backend, "_get_active_edition_run_for_handle", return_value=(self.product, self.run)
        ))
        self.audit = self.stack.enter_context(patch.object(supabase_backend, "_insert_edition_adjustment_with_cursor"))
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("No network")))

    def save(self, next_number, **kwargs):
        return supabase_backend._update_edition_product_with_cursor(
            self.cursor, "test-product", next_edition_number=next_number,
            manual_next_number_override=True, expected_next_edition_number=10, **kwargs,
        )

    def test_manual_correction_updates_both_pointers_only_and_audits(self):
        before = deepcopy((self.product, self.run, self.ledger))
        result = self.save(7, reason="manual_next_number_lowered")
        writes = [call.args for call in self.cursor.execute.call_args_list if call.args[0].startswith("UPDATE")]
        self.assertEqual(writes, [
            ("UPDATE edition_runs SET next_edition_number=%s, updated_at=now() WHERE id=%s RETURNING *", (7, 8)),
            ("UPDATE edition_products SET next_edition_number=%s, updated_at=now() WHERE id=%s", (7, 7)),
        ])
        self.assertEqual((self.product, self.run, self.ledger), before)
        self.lookup.assert_called_once_with(self.cursor, "test-product", lock=True, create_missing=False)
        self.assertTrue(result["manual_next_number_lowered"])
        self.assertEqual(self.audit.call_args.kwargs["old_next"], 10)
        self.assertEqual(self.audit.call_args.kwargs["new_next"], 7)
        self.assertEqual(self.audit.call_args.kwargs["source"], "manual_app")

    def test_sold_out_next_101_is_valid_and_does_not_change_flags_or_counts(self):
        self.product.update(sold_count=100, remaining_count=0, active=False, sold_out=True)
        self.run["status"] = "sold_out"
        self.assertEqual(self.save(101)["next_edition_number"], 101)
        for call in self.cursor.execute.call_args_list:
            if call.args[0].startswith("UPDATE"):
                self.assertNotIn("status=", call.args[0])
                self.assertNotIn("count=", call.args[0])
                self.assertNotIn("active=", call.args[0])

    def test_out_of_range_values_fail_without_writes(self):
        for value in (0, -1, 102):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "one past"):
                self.save(value)
        self.assertFalse(any(call.args[0].startswith("UPDATE") for call in self.cursor.execute.call_args_list))
        self.audit.assert_not_called()

    def test_stale_original_fails_without_overwriting_new_allocation(self):
        self.run["next_edition_number"] = 11
        with self.assertRaisesRegex(ValueError, "changed since this table was loaded"):
            self.save(17)
        self.assertFalse(any(call.args[0].startswith("UPDATE") for call in self.cursor.execute.call_args_list))

    def test_ordinary_backend_call_keeps_ledger_guard(self):
        self.ledger.update(allocation_count=9)
        with self.assertRaisesRegex(ValueError, "ledger-derived"):
            supabase_backend._update_edition_product_with_cursor(self.cursor, "test-product", next_edition_number=7)

    def test_later_total_edit_keeps_the_saved_manual_pointer(self):
        self.product.update(next_edition_number=17, sold_count=0, remaining_count=100)
        self.run["next_edition_number"] = 17
        self.ledger.update(allocation_count=0, min_assigned=0, max_assigned=0)
        result = supabase_backend._update_edition_product_with_cursor(
            self.cursor, "test-product", next_edition_number=17, edition_total=90,
        )
        self.assertEqual(result["next_edition_number"], 17)
        self.assertEqual(result["edition_total"], 90)
        writes = [call.args for call in self.cursor.execute.call_args_list if "UPDATE edition_runs" in call.args[0]]
        self.assertEqual(writes[0][1][1:3], (90, 17))

    def test_total_edit_still_respects_existing_allocation_guard(self):
        with self.assertRaisesRegex(ValueError, "immutable after the first allocation"):
            self.save(17, edition_total=90)
        self.audit.assert_not_called()

    def test_batch_forwards_override_in_existing_transaction(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        self.cursor.__enter__ = Mock(return_value=self.cursor)
        self.cursor.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = self.cursor
        with patch.object(supabase_backend, "connect", return_value=connection), patch.object(
            supabase_backend, "ensure_schema", side_effect=AssertionError("No migrations on save")
        ):
            results = supabase_backend.update_edition_products_batch([{
                "handle": "test-product", "next_edition_number": 17,
                "manual_next_number_override": True, "expected_next_edition_number": 10,
            }])
        self.assertTrue(results[0]["ok"])
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
