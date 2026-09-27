"""Spreadsheet-style design tracker with autosave and retained failed-save drafts."""
from copy import deepcopy
from datetime import datetime
import logging
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

import design_tracking_store
import os_accounts

SNAPSHOT_KEY = "edition_design_tracking_snapshot"
REVISION_KEY = "edition_design_tracking_revision"
DRAFT_KEY = "edition_design_tracking_draft"
ERROR_KEY = "edition_design_tracking_error"
RELOAD_KEY = "edition_design_tracking_reload"
ADD_KEY = "edition_design_tracking_add_request"
NOTICE_KEY = "edition_design_tracking_notice"
EDITOR_ROWS_KEY = "edition_design_tracking_editor_source"


def _bump_editor():
    st.session_state[REVISION_KEY] = st.session_state.get(REVISION_KEY, 0) + 1


def _error(exc):
    if isinstance(exc, (PermissionError, ValueError)):
        message = str(exc)
    else:
        logging.getLogger(__name__).warning("design_tracking_save_failed type=%s", type(exc).__name__)
        message = "Could not save. Your draft is still here; use Retry saving."
    st.session_state[ERROR_KEY] = message


def _try_save(actor):
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    draft = st.session_state.get(DRAFT_KEY)
    if draft is None or not snapshot:
        return True
    try:
        changes = design_tracking_store.editor_changes(snapshot["rows"], draft)
        saved = design_tracking_store.Store().save(actor, changes)
        by_id = {row["id"]: row for row in saved}
        fields_by_id = {change["id"]: change["values"] for change in changes}
        # The stable grid still displays its original unedited cells. Do not
        # replace their comparison baseline with unseen concurrent changes, or
        # a subsequent edit could silently write those stale cells back.
        snapshot["rows"] = [
            {**row, **{field: by_id[row["id"]][field] for field in fields_by_id[row["id"]]},
             "version": by_id[row["id"]]["version"]} if row["id"] in by_id else row
            for row in snapshot["rows"]
        ]
        st.session_state.pop(DRAFT_KEY, None)
        st.session_state.pop(ERROR_KEY, None)
        st.session_state[NOTICE_KEY] = "All changes saved."
        return True
    except Exception as exc:
        _error(exc)
        return False


def _capture_edits(editor_key, displayed_rows):
    actor = st.session_state.get("sports_cave_current_user") or {}
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    if not snapshot or snapshot["actor"] != str(actor.get("id")):
        return
    event = st.session_state.get(editor_key) or {}
    edited = deepcopy(displayed_rows)
    try:
        if event.get("added_rows") or event.get("deleted_rows"):
            raise ValueError("Use Add product to add a row. Existing rows cannot be deleted.")
        for index, fields in event.get("edited_rows", {}).items():
            row = edited[int(index)]
            for key, value in fields.items():
                if key in design_tracking_store.EDITABLE_FIELDS:
                    row[key] = design_tracking_store._value(key, value)
        # Store the draft before attempting any validation or network operation.
        st.session_state[DRAFT_KEY] = edited
        _try_save(actor)
    except Exception as exc:
        _error(exc)


def _refresh(actor):
    if _try_save(actor):
        st.session_state[RELOAD_KEY] = True


def render():
    actor = st.session_state.get("sports_cave_current_user") or {}
    if not os_accounts.can_access_page(actor, "edition_ops"):
        return
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    if snapshot and snapshot["actor"] != str(actor["id"]):
        # A different login must never inherit another person's unsaved cells.
        for key in (SNAPSHOT_KEY,DRAFT_KEY,ERROR_KEY,ADD_KEY,NOTICE_KEY,EDITOR_ROWS_KEY):
            st.session_state.pop(key, None)
        _bump_editor()
    panel = st.expander("Designs tracking", expanded=False,
                        key="edition_design_tracking_open", on_change="rerun")
    if not panel.open:
        st.session_state[RELOAD_KEY] = True
        return  # Retain pending edits when collapsing/navigating away.
    with panel:
        _render_table(actor)


def _add_product(actor):
    with st.popover("Add product"):
        st.caption("Adds a row to this tracker. Designed by is filled from your account.")
        request_id = st.session_state.setdefault(ADD_KEY, str(uuid4()))
        with st.form("edition_design_add_" + request_id, border=False):
            title = st.text_input("Product name", max_chars=500)
            created = st.date_input("Date created", value=datetime.now(ZoneInfo("Australia/Sydney")).date())
            add = st.form_submit_button("Add to tracker")
        if add:
            if not _try_save(actor):
                st.error("Save the pending table edits before adding a product.")
                return
            try:
                row = design_tracking_store.Store().create(
                    actor, row_id=request_id, product_title=title, date_created=created)
                snapshot = st.session_state[SNAPSHOT_KEY]
                snapshot["rows"] = [row] + [r for r in snapshot["rows"] if r["id"] != row["id"]]
                st.session_state[ADD_KEY] = str(uuid4())
                st.session_state.pop(ERROR_KEY, None)
                st.session_state[NOTICE_KEY] = "Product added and saved."
                _bump_editor()
                st.rerun()
            except Exception as exc:
                _error(exc)


def _render_table(actor):
    st.caption("Edit or paste into cells; press Enter or Tab to save automatically. "
               "First order is manual. Only admins can edit the Bonus paid date.")
    st.button("Refresh designs", key="edition_design_tracking_refresh", on_click=_refresh, args=(actor,))
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    try:
        refresh_due = st.session_state.get(RELOAD_KEY) or (
            snapshot and time.monotonic() - snapshot.get("loaded_at", 0) >= 60
        )
        if snapshot is None or (refresh_due and DRAFT_KEY not in st.session_state):
            rows = design_tracking_store.Store().list_rows(actor)
            snapshot = {"actor": str(actor["id"]), "rows": rows, "loaded_at": time.monotonic()}
            st.session_state[SNAPSHOT_KEY] = snapshot
            st.session_state[RELOAD_KEY] = False
            _bump_editor()
    except Exception as exc:
        _error(exc)
    if not snapshot:
        st.error(st.session_state.get(ERROR_KEY) or "Design tracking is unavailable.")
        return
    _add_product(actor)
    rows = st.session_state.get(DRAFT_KEY, snapshot["rows"])
    error = st.session_state.get(ERROR_KEY)
    if error:
        st.error(error)
    if DRAFT_KEY in st.session_state:
        st.warning("Unsaved edits are retained below. Refresh will not discard them.")
        st.button("Retry saving", key="edition_design_tracking_retry", on_click=_try_save, args=(actor,))
        # Discard is explicit and only affects the session draft, never saved rows.
        if st.button("Discard unsaved edits and reload", key="edition_design_tracking_discard"):
            st.session_state.pop(DRAFT_KEY, None)
            st.session_state.pop(ERROR_KEY, None)
            st.session_state[RELOAD_KEY] = True
            _bump_editor()
            st.rerun()
    else:
        st.caption(st.session_state.get(NOTICE_KEY, "Changes save automatically."))
    sold = sum(bool(row["first_order"]) for row in rows)
    paid = sum(bool(row["bonus_paid_on"]) for row in rows)
    st.caption(f"{len(rows)} designs · {sold} with orders · {paid} bonuses paid")
    if not rows:
        st.info("Use Add product, or new Edition Ops products will appear here.")
        return
    editor_key = f"edition_design_tracking_editor_{st.session_state.get(REVISION_KEY,0)}"
    # Keep the widget's input stable during autosaves: Streamlit accumulates cell
    # deltas against this input. Recreating it on every save loses focus/scroll.
    # When navigation destroys the widget, rebuild from saved rows or the draft.
    if EDITOR_ROWS_KEY not in st.session_state or editor_key not in st.session_state:
        st.session_state[EDITOR_ROWS_KEY] = deepcopy(rows)
    editor_rows = st.session_state[EDITOR_ROWS_KEY]
    st.data_editor(
        [{key: row[key] for key in design_tracking_store.EDITABLE_FIELDS} for row in editor_rows],
        hide_index=True, num_rows="fixed", height=380, width="stretch", key=editor_key,
        on_change=_capture_edits, args=(editor_key, deepcopy(editor_rows)),
        disabled=[] if os_accounts.is_admin(actor) else ["bonus_paid_on"],
        column_config={
            "product_title": st.column_config.TextColumn("Product", width="large", max_chars=500, required=True),
            "date_created": st.column_config.DateColumn("Date created", format="DD/MM/YYYY", required=True),
            "first_order": st.column_config.TextColumn("First order", width="small", max_chars=120,
                help="Enter or clear the first order manually. It will not be overwritten by order sync."),
            "designed_by": st.column_config.TextColumn("Designed by", max_chars=120),
            "bonus_paid_on": st.column_config.DateColumn("Bonus", format="DD/MM/YYYY",
                help="Admin only: enter the date the bonus was paid. Leave blank until paid."),
        },
    )
