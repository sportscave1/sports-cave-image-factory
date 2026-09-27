"""Lazy, compact design bonus tracker embedded at the bottom of Edition Ops."""
import logging

import streamlit as st

import design_tracking_store
import os_accounts


SNAPSHOT_KEY = "edition_design_tracking_snapshot"
REVISION_KEY = "edition_design_tracking_revision"


def render():
    actor = st.session_state.get("sports_cave_current_user") or {}
    if not os_accounts.can_access_page(actor, "edition_ops"):
        return
    panel = st.expander("Designs tracking", expanded=False,
                        key="edition_design_tracking_open", on_change="rerun")
    if not panel.open:
        st.session_state.pop(SNAPSHOT_KEY, None)
        return
    with panel:
        _render_table(actor)


def _reset():
    st.session_state.pop(SNAPSHOT_KEY, None)
    st.session_state[REVISION_KEY] = st.session_state.get(REVISION_KEY, 0) + 1


def _render_table(actor):
    st.caption("Designs added since 1 September 2026. First order updates from recorded orders. "
               "Fill in Designed by; an admin enters the Bonus date when paid. Blank means unpaid.")
    if st.button("Refresh designs", key="edition_design_tracking_refresh"):
        _reset()
    notice = st.session_state.pop("edition_design_tracking_notice", None)
    if notice:
        st.success(notice)
    store = design_tracking_store.Store()
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    try:
        if not snapshot or snapshot["actor"] != str(actor["id"]):
            _reset()
            snapshot = {"actor": str(actor["id"]), "rows": store.list_rows(actor)}
            st.session_state[SNAPSHOT_KEY] = snapshot
        rows = snapshot["rows"]
        if not rows:
            st.info("New designs will appear here when added to Edition Ops.")
            return
        sold = sum(bool(row["first_order"]) for row in rows)
        paid = sum(bool(row["bonus_paid_on"]) for row in rows)
        st.caption(f"{len(rows)} designs · {sold} with orders · {paid} bonuses paid")
        admin = os_accounts.is_admin(actor)
        with st.form("edition_design_tracking_form", border=False):
            edited = st.data_editor(
                [{key: row[key] for key in ("product_title", "first_order", "designed_by", "bonus_paid_on")}
                 for row in rows],
                hide_index=True, num_rows="fixed", height=350, width="stretch",
                key=f"edition_design_tracking_editor_{st.session_state.get(REVISION_KEY,0)}",
                disabled=["product_title", "first_order"] + ([] if admin else ["bonus_paid_on"]),
                column_config={
                    "product_title": st.column_config.TextColumn("Product", width="large"),
                    "first_order": st.column_config.TextColumn("First order", width="small"),
                    "designed_by": st.column_config.TextColumn("Designed by", max_chars=120),
                    "bonus_paid_on": st.column_config.DateColumn("Bonus", format="DD/MM/YYYY",
                        help="Admin only: date the bonus was paid for the first order. Leave blank until paid."),
                },
            )
            submitted = st.form_submit_button("Save design tracking")
        if submitted:
            changes = design_tracking_store.editor_changes(rows, edited)
            count = store.save(actor, changes)
            if count:
                _reset()
                st.session_state["edition_design_tracking_notice"] = f"Saved {count} design(s)."
                st.rerun()
            else:
                st.info("No changes to save.")
    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
    except Exception as exc:
        logging.getLogger(__name__).warning("design_tracking_unavailable type=%s", type(exc).__name__)
        st.error("Design tracking is temporarily unavailable. Your changes have not been saved. Try again or refresh.")
