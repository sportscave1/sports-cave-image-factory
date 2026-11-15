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
ROW_ID = "00000000-0000-0000-0000-000000000630"
ACTOR = {"id": ACTOR_ID, "role": "worker", "is_active": True,
         "page_permissions": ["edition_ops"], "session_version": 1}
ROW = {"id": ROW_ID, "edition_product_id": 630, "product_title": "Example design",
       "date_created": date(2026,9,3), "first_order": "#SC3160",
       "designed_by": "", "bonus_paid_on": None, "version": 1}


def connection(*rows):
    conn = Mock()
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    conn.execute.side_effect = [Mock(fetchone=Mock(return_value=row)) for row in rows]
    return conn


def change(original=None, **values):
    old = original or ROW
    return {"id": old["id"], "values": values, "original": {k:old.get(k) for k in values}}


class TrackingWriteTests(unittest.TestCase):
    def test_staff_cannot_set_or_clear_bonus(self):
        for old, paid in [(ROW, date(2026,9,28)), ({**ROW,"bonus_paid_on":date(2026,9,28)},None)]:
            conn = connection(old)
            with self.assertRaisesRegex(PermissionError,"Only an admin"):
                tracking.Store._save_row(conn,ACTOR_ID,False,change(old,bonus_paid_on=paid))
            self.assertEqual(conn.execute.call_count,1)

    def test_staff_can_edit_product_date_designer_and_manual_order(self):
        values = {"product_title":"Renamed", "date_created":date(2026,9,5),
                  "designed_by":"VA Two", "first_order":"Manual-123"}
        conn = connection(ROW, {**ROW,**values,"version":2})
        result = tracking.Store._save_row(conn,ACTOR_ID,False,change(**values))
        self.assertEqual(result["first_order"],"Manual-123")
        sql,params = conn.execute.call_args.args
        self.assertNotIn("paid_order",sql)
        self.assertNotIn("bonus_paid_on=%s",sql)
        self.assertEqual(params[:-2],tuple(values.values()))

    def test_clearing_manual_first_order_is_persisted(self):
        conn = connection(ROW,{**ROW,"first_order":"","version":2})
        result = tracking.Store._save_row(conn,ACTOR_ID,False,change(first_order=""))
        self.assertEqual(result["first_order"],"")
        self.assertEqual(conn.execute.call_args.args[1][0],"")

    def test_staff_edits_preserve_existing_paid_receipt(self):
        old = {**ROW,"bonus_paid_on":date(2026,9,26),"paid_order_id":"gid://shopify/Order/10",
               "paid_order_name":"#SC3160","bonus_paid_by":ACTOR_ID}
        conn = connection(old,{**old,"first_order":"Corrected-10","version":2})
        tracking.Store._save_row(conn,ACTOR_ID,False,change(old,first_order="Corrected-10"))
        sql = conn.execute.call_args.args[0]
        self.assertNotIn("paid_order_name=",sql)
        self.assertNotIn("bonus_paid_by=",sql)
        self.assertNotIn("bonus_paid_on=",sql)

    def test_admin_can_pay_a_manually_entered_order(self):
        old = {**ROW,"first_order":"MANUAL-ONE"}
        conn = connection(old,{**old,"bonus_paid_on":date(2026,9,28),"version":2})
        tracking.Store._save_row(conn,ACTOR_ID,True,change(old,bonus_paid_on="2026-09-28"))
        self.assertEqual(conn.execute.call_args.args[1][:4],
                         (date(2026,9,28),"manual:MANUAL-ONE","MANUAL-ONE",ACTOR_ID))

    def test_admin_can_clear_paid_receipt(self):
        old = {**ROW,"bonus_paid_on":date(2026,9,26)}
        conn = connection(old,ROW)
        tracking.Store._save_row(conn,ACTOR_ID,True,change(old,bonus_paid_on=None))
        self.assertEqual(conn.execute.call_args.args[1][:4],(None,None,None,None))

    def test_no_order_cannot_be_marked_paid(self):
        old = {**ROW,"first_order":""}
        with self.assertRaisesRegex(ValueError,"Enter First order"):
            tracking.Store._save_row(connection(old),ACTOR_ID,True,change(old,bonus_paid_on="2026-09-28"))

    def test_conflicting_cell_is_not_overwritten(self):
        conn = connection({**ROW,"first_order":"Other edit","version":2})
        with self.assertRaises(tracking.TrackingConflict):
            tracking.Store._save_row(conn,ACTOR_ID,True,change(first_order="My edit"))
        self.assertEqual(conn.execute.call_count,1)

    def test_disjoint_concurrent_edits_merge(self):
        old = {**ROW,"designed_by":"Other person's edit","version":2}
        conn = connection(old,{**old,"first_order":"Mine","version":3})
        result = tracking.Store._save_row(conn,ACTOR_ID,False,change(first_order="Mine"))
        self.assertEqual(result["designed_by"],"Other person's edit")
        self.assertNotIn("designed_by=",conn.execute.call_args.args[0])

    def test_retry_after_success_is_idempotent(self):
        conn = connection({**ROW,"first_order":"Already saved","version":2})
        tracking.Store._save_row(conn,ACTOR_ID,False,change(first_order="Already saved"))
        self.assertEqual(conn.execute.call_count,1)

    def test_invalid_title_or_date_cannot_erase_required_data(self):
        for fields in [{"product_title":""},{"date_created":None}]:
            conn = connection(ROW)
            with self.assertRaises(ValueError):
                tracking.Store._save_row(conn,ACTOR_ID,False,change(**fields))
            self.assertEqual(conn.execute.call_count,1)

    def test_forged_client_role_is_not_trusted(self):
        user = {"id":ACTOR_ID,"role":"worker","is_active":True,"account_status":"active",
                "removed_at":None,"session_version":1}
        self.assertEqual(tracking.Store._authorize(connection(user,{"allowed":1}),
                                                   {**ACTOR,"role":"admin"}),(ACTOR_ID,False))

    def test_revoked_account_permission_and_session_are_rejected(self):
        user = {"id":ACTOR_ID,"role":"worker","is_active":True,"account_status":"active",
                "removed_at":None,"session_version":1}
        for record in [None,{**user,"is_active":False},{**user,"account_status":"removed"},
                       {**user,"session_version":2},user]:
            with self.assertRaises(PermissionError):
                tracking.Store._authorize(connection(record,None),ACTOR)

    def test_row_identity_is_not_taken_from_editor(self):
        edited = {**ROW,"id":"fake","edition_product_id":999,"first_order":"Manual"}
        result = tracking.editor_changes([ROW],[edited])[0]
        self.assertEqual(result["id"],ROW_ID)
        self.assertEqual(result["values"],{"first_order":"Manual"})
        self.assertEqual(result["original"],{"first_order":"#SC3160"})
        self.assertEqual(tracking.editor_changes([ROW],[ROW]),[])

    def test_create_uses_persisted_creator_and_idempotent_request(self):
        created = {**ROW,"edition_product_id":None,"designed_by":"Real VA"}
        conn = connection({"display_name":"Real VA","username":"va"},None,created)
        store = tracking.Store(connect=lambda:conn)
        with patch.object(store,"_authorize",return_value=(ACTOR_ID,False)):
            result = store.create({**ACTOR,"display_name":"Forged"},row_id=ROW_ID,
                                  product_title="Example design",date_created=date(2026,9,3))
        self.assertEqual(result["designed_by"],"Real VA")
        insert = conn.execute.call_args_list[1]
        self.assertIn("ON CONFLICT (id) DO NOTHING",insert.args[0])
        self.assertEqual(insert.args[1][3:],("Real VA",ACTOR_ID,ACTOR_ID))

    def test_batch_failure_rolls_back_all_cells(self):
        conn = connection()
        store = tracking.Store(connect=lambda:conn)
        with patch.object(store,"_authorize",return_value=(ACTOR_ID,True)), patch.object(
                store,"_save_row",side_effect=[ROW,tracking.TrackingConflict("Conflict")]):
            with self.assertRaises(tracking.TrackingConflict):
                store.save(ACTOR,[change(first_order="1"),{"id":ACTOR_ID,"values":{},"original":{}}])
        self.assertIs(conn.__exit__.call_args.args[0],tracking.TrackingConflict)


def app_body():
    import design_tracking_page
    design_tracking_page.render()


class MemoryStore:
    def __init__(self):
        self.rows = [deepcopy(ROW)]
        self.fail = False
        self.list_calls = 0
        self.saved = 0
    def list_rows(self,actor):
        self.list_calls += 1
        return deepcopy(self.rows)
    def save(self,actor,changes):
        if self.fail:
            raise RuntimeError("offline")
        updated = []
        for c in changes:
            old = next(r for r in self.rows if r["id"]==c["id"])
            for field,value in c["values"].items():
                if field=="bonus_paid_on" and actor["role"]!="admin":
                    raise PermissionError("Only an admin can change Bonus")
                old[field]=value
            old["version"] += 1
            updated.append(deepcopy(old))
            self.saved += 1
        return updated
    def create(self,actor,**kwargs):
        row = {**ROW,"id":kwargs["row_id"],"edition_product_id":None,
               "product_title":kwargs["product_title"],"date_created":kwargs["date_created"],
               "first_order":"","designed_by":"VA Creator","bonus_paid_on":None}
        self.rows.insert(0,row)
        return deepcopy(row)


def edit(app,fields):
    table = app.get("dataframe")[0]
    editor_key = next(key for key in app.session_state.filtered_state
                      if key.startswith("edition_design_tracking_editor_") and key.rsplit("_",1)[-1].isdigit())
    pending = deepcopy(app.session_state[editor_key].get("edited_rows") or {})
    pending.setdefault(0,{}).update(fields)
    widgets = app._tree.get_widget_states()
    widgets.widgets.append(WidgetState(id=table.proto.id,string_value=json.dumps({
        "edited_rows":pending,"added_rows":[],"deleted_rows":[]})))
    app._run(widgets)


class TrackingUiTests(unittest.TestCase):
    def make_app(self,admin=False):
        app = AppTest.from_function(app_body)
        app.session_state["sports_cave_current_user"]={**ACTOR,"role":"admin" if admin else "worker"}
        app.session_state["edition_design_tracking_open"]=True
        return app.run()

    def test_closed_panel_does_not_read_database(self):
        with patch.object(page.design_tracking_store,"Store") as store:
            app=AppTest.from_function(app_body)
            app.session_state["sports_cave_current_user"]=ACTOR
            app.run()
            self.assertFalse(app.exception)
            store.assert_not_called()
            self.assertEqual(app.expander[0].label,"Designs tracking")

    def test_excel_cells_autosave_and_survive_new_session(self):
        for admin in (False,True):
            backend=MemoryStore()
            with patch.object(page.design_tracking_store,"Store",return_value=backend):
                app=self.make_app(admin)
                columns=json.loads(app.get("dataframe")[0].proto.columns)
                for field in ("product_title","date_created","first_order","designed_by"):
                    self.assertFalse(columns[field].get("disabled",False))
                self.assertEqual(columns["bonus_paid_on"].get("disabled",False),not admin)
                fields={"product_title":"Updated design","date_created":"2026-09-20",
                        "first_order":"MY-ORDER","designed_by":"VA Designer"}
                if admin:
                    fields["bonus_paid_on"]="2026-09-28"
                widget_id = app.get("dataframe")[0].proto.id
                edit(app,fields)
                self.assertFalse(app.exception)
                self.assertEqual(app.get("dataframe")[0].proto.id,widget_id)
                self.assertEqual(backend.rows[0]["first_order"],"MY-ORDER")
                self.assertEqual(backend.rows[0]["date_created"],date(2026,9,20))
                self.assertEqual(backend.rows[0]["bonus_paid_on"],date(2026,9,28) if admin else None)
                self.assertEqual(backend.saved,1)
                edit(app,{"designed_by":"Second edit"})
                self.assertEqual(backend.rows[0]["first_order"],"MY-ORDER")
                self.assertEqual(backend.rows[0]["designed_by"],"Second edit")
                fresh=self.make_app(admin)
                self.assertEqual(fresh.session_state[page.SNAPSHOT_KEY]["rows"][0]["first_order"],"MY-ORDER")
                edit(fresh,{"first_order":""})
                fresh.button(key="edition_design_tracking_refresh").click().run()
                self.assertEqual(fresh.session_state[page.SNAPSHOT_KEY]["rows"][0]["first_order"],"")

    def test_failed_autosave_keeps_draft_through_refresh_and_collapse(self):
        backend=MemoryStore()
        with patch.object(page.design_tracking_store,"Store",return_value=backend):
            app=self.make_app()
            backend.fail=True
            edit(app,{"first_order":"KEEP THIS","date_created":"2026-09-24"})
            self.assertEqual(app.session_state[page.DRAFT_KEY][0]["first_order"],"KEEP THIS")
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state[page.DRAFT_KEY][0]["date_created"],date(2026,9,24))
            self.assertEqual(backend.rows[0]["first_order"],"#SC3160")
            app.button(key="edition_design_tracking_refresh").click().run()
            self.assertEqual(app.session_state[page.DRAFT_KEY][0]["first_order"],"KEEP THIS")
            app.session_state["edition_design_tracking_open"]=False
            app.run()
            app.session_state["edition_design_tracking_open"]=True
            app.run()
            self.assertEqual(app.session_state[page.DRAFT_KEY][0]["first_order"],"KEEP THIS")
            backend.fail=False
            app.button(key="edition_design_tracking_retry").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(backend.rows[0]["first_order"],"KEEP THIS")
            self.assertNotIn(page.DRAFT_KEY,app.session_state.filtered_state)

    def test_later_cell_edit_does_not_erase_unseen_concurrent_change(self):
        backend=MemoryStore()
        with patch.object(page.design_tracking_store,"Store",return_value=backend):
            app=self.make_app()
            backend.rows[0]["designed_by"]="Another user's name"
            edit(app,{"first_order":"MY ORDER"})
            edit(app,{"product_title":"My label"})
            self.assertFalse(app.exception)
            self.assertEqual(backend.rows[0]["designed_by"],"Another user's name")
            self.assertEqual(backend.rows[0]["first_order"],"MY ORDER")
            app.button(key="edition_design_tracking_refresh").click().run()
            self.assertEqual(app.session_state[page.SNAPSHOT_KEY]["rows"][0]["designed_by"],"Another user's name")

    def test_add_product_is_saved_with_creator_and_date(self):
        backend=MemoryStore()
        with patch.object(page.design_tracking_store,"Store",return_value=backend):
            app=self.make_app()
            app.text_input[0].input("New manual design")
            app.date_input[0].set_value(date(2026,9,28))
            next(b for b in app.button if b.label=="Add to tracker").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(backend.rows[0]["product_title"],"New manual design")
            self.assertEqual(backend.rows[0]["designed_by"],"VA Creator")
            self.assertEqual(backend.rows[0]["date_created"],date(2026,9,28))
            self.assertEqual(len(app.session_state[page.SNAPSHOT_KEY]["rows"]),2)


if __name__=="__main__":
    unittest.main()
