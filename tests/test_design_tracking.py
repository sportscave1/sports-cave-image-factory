from copy import deepcopy
from datetime import date
import json
import unittest
from unittest.mock import Mock, patch

from streamlit.proto.WidgetStates_pb2 import WidgetState
from streamlit.testing.v1 import AppTest

import design_tracking_store as tracking
import design_tracking_page as page


ACTOR_ID = "00000000-0000-0000-0000-000000000001"
ACTOR = {"id": ACTOR_ID, "role": "worker", "is_active": True,
         "page_permissions": ["edition_ops"], "session_version": 1}
ROW = {"edition_product_id": 630, "product_title": "Example design", "first_order": "#SC3160",
       "first_order_id": "gid://shopify/Order/10", "designed_by": "", "bonus_paid_on": None, "version": 0}


def connection(*rows):
    conn = Mock()
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    conn.execute.side_effect = [Mock(fetchone=Mock(return_value=row)) for row in rows]
    return conn


def change(**fields):
    return {**ROW, **fields}


class TrackingWriteTests(unittest.TestCase):
    def test_staff_cannot_set_or_clear_bonus(self):
        for old, paid in [({}, date(2026,9,28)),
                          ({"bonus_paid_on": date(2026,9,28), "version": 0}, None)]:
            conn = connection({"id": 630}, old)
            with self.assertRaisesRegex(PermissionError, "Only an admin"):
                tracking.Store._save_row(conn, ACTOR_ID, False, change(bonus_paid_on=paid))
            self.assertEqual(conn.execute.call_count, 2)

    def test_staff_designer_edit_preserves_paid_receipt(self):
        old = {"version": 3, "designed_by": "VA One", "bonus_paid_on": date(2026,9,28),
               "paid_order_id": ROW["first_order_id"], "paid_order_name": ROW["first_order"],
               "bonus_paid_by": ACTOR_ID}
        conn = connection({"id": 630}, old, None)
        tracking.Store._save_row(conn, ACTOR_ID, False,
                                 change(version=3, designed_by="VA Two", bonus_paid_on=old["bonus_paid_on"]))
        params = conn.execute.call_args.args[1]
        self.assertEqual(params[1:6], ("VA Two", old["bonus_paid_on"], old["paid_order_id"],
                                      old["paid_order_name"], ACTOR_ID))

    def test_admin_payment_links_server_verified_order(self):
        conn = connection({"id": 630}, {}, {"order_id": ROW["first_order_id"], "order_name": "#SC3160"}, None)
        tracking.Store._save_row(conn, ACTOR_ID, True, change(bonus_paid_on="2026-09-28"))
        params = conn.execute.call_args.args[1]
        self.assertEqual(params[2:6], (date(2026,9,28), ROW["first_order_id"], "#SC3160", ACTOR_ID))

    def test_admin_cannot_pay_unsold_or_changed_order(self):
        for first, error in [(None, ValueError), ({"order_id": "other", "order_name": "#SC1"}, tracking.TrackingConflict)]:
            conn = connection({"id": 630}, {}, first)
            with self.assertRaises(error):
                tracking.Store._save_row(conn, ACTOR_ID, True, change(bonus_paid_on="2026-09-28"))
            self.assertEqual(conn.execute.call_count, 3)

    def test_admin_can_clear_receipt(self):
        conn = connection({"id": 630}, {"bonus_paid_on": date(2026,9,28), "version": 0,
                         "paid_order_id": "10", "paid_order_name": "#SC3160", "bonus_paid_by": ACTOR_ID}, None)
        tracking.Store._save_row(conn, ACTOR_ID, True, change())
        self.assertEqual(conn.execute.call_args.args[1][2:6], (None,None,None,None))

    def test_stale_edits_fail_without_writes(self):
        conn = connection({"id": 630}, {"version": 2})
        with self.assertRaises(tracking.TrackingConflict):
            tracking.Store._save_row(conn, ACTOR_ID, True, change(designed_by="VA"))
        self.assertEqual(conn.execute.call_count, 2)

    def test_unchanged_blank_rows_create_no_storage(self):
        conn = connection({"id": 630}, {})
        tracking.Store._save_row(conn, ACTOR_ID, True, change())
        self.assertEqual(conn.execute.call_count, 2)
        self.assertEqual(tracking.editor_changes([ROW], [ROW]), [])

    def test_forged_client_role_is_not_trusted(self):
        user = {"id": ACTOR_ID, "role": "worker", "is_active": True, "account_status": "active",
                "removed_at": None, "session_version": 1}
        conn = connection(user, {"allowed": 1})
        self.assertEqual(tracking.Store._authorize(conn, {**ACTOR,"role":"admin"}), (ACTOR_ID,False))

    def test_revoked_account_permission_and_session_are_rejected(self):
        user = {"id": ACTOR_ID, "role": "worker", "is_active": True, "account_status": "active",
                "removed_at": None, "session_version": 1}
        for record in [None, {**user,"is_active":False}, {**user,"account_status":"removed"},
                       {**user,"session_version":2}, user]:
            conn = connection(record, None)
            with self.assertRaises(PermissionError):
                tracking.Store._authorize(conn, ACTOR)

    def test_read_only_fields_and_client_ids_are_ignored(self):
        edited = {**ROW,"edition_product_id":999,"version":99,"first_order_id":"fake","designed_by":" VA "}
        result = tracking.editor_changes([ROW], [edited])[0]
        self.assertEqual(result["edition_product_id"], 630)
        self.assertEqual(result["version"], 0)
        self.assertEqual(result["first_order_id"], ROW["first_order_id"])
        self.assertEqual(result["designed_by"], "VA")

    def test_batch_failure_rolls_back_transaction(self):
        conn = connection()
        store = tracking.Store(connect=lambda:conn)
        with patch.object(store,"_authorize",return_value=(ACTOR_ID,True)), \
                patch.object(store,"_save_row",side_effect=[None,tracking.TrackingConflict("Conflict")]):
            with self.assertRaises(tracking.TrackingConflict):
                store.save(ACTOR, [change(),change(edition_product_id=631)])
        self.assertIs(conn.__exit__.call_args.args[0], tracking.TrackingConflict)


def app_body():
    import design_tracking_page
    design_tracking_page.render()


class TrackingUiTests(unittest.TestCase):
    def test_closed_panel_does_not_read_database(self):
        with patch.object(page.design_tracking_store,"Store") as store:
            app = AppTest.from_function(app_body)
            app.session_state["sports_cave_current_user"] = ACTOR
            app.run()
            self.assertFalse(app.exception)
            store.assert_not_called()
            self.assertEqual(app.expander[0].label, "Designs tracking")

    def test_actual_editor_staff_and_admin_columns_and_save_reload(self):
        for admin in (False,True):
            stored = deepcopy(ROW)
            def save(actor, changes):
                for item in changes:
                    stored.update(item)
                    stored["version"] += 1
                return len(changes)
            backend = Mock()
            backend.list_rows.side_effect = lambda actor:[deepcopy(stored)]
            backend.save.side_effect = save
            with patch.object(page.design_tracking_store,"Store",return_value=backend):
                app = AppTest.from_function(app_body)
                app.session_state["sports_cave_current_user"] = {**ACTOR,"role":"admin" if admin else "worker"}
                app.session_state["edition_design_tracking_open"] = True
                app.run()
                self.assertFalse(app.exception)
                table = app.get("dataframe")[0]
                columns = json.loads(table.proto.columns)
                self.assertTrue(columns["product_title"]["disabled"])
                self.assertTrue(columns["first_order"]["disabled"])
                self.assertEqual(columns["bonus_paid_on"].get("disabled",False), not admin)
                self.assertEqual(columns["bonus_paid_on"]["type_config"]["type"], "date")
                edits = {"designed_by":"VA Designer"}
                if admin:
                    edits["bonus_paid_on"] = "2026-09-28"
                app.button[-1].click()
                widgets = app._tree.get_widget_states()
                widgets.widgets.append(WidgetState(id=table.proto.id,string_value=json.dumps({
                    "edited_rows":{"0":edits},"added_rows":[],"deleted_rows":[]})))
                app._run(widgets)
                self.assertFalse(app.exception)
                self.assertEqual(stored["designed_by"], "VA Designer")
                self.assertEqual(stored["bonus_paid_on"], date(2026,9,28) if admin else None)
                self.assertTrue(app.success)
                self.assertEqual(backend.save.call_count,1)
                self.assertGreaterEqual(backend.list_rows.call_count,2)


if __name__ == "__main__":
    unittest.main()
