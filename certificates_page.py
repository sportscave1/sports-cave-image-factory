from datetime import datetime

import streamlit as st

import certificate_engine
import certificate_service
import shopify_sync


ROWS_KEY = "certificates_rows"
META_KEY = "certificates_meta"
SNAPSHOT_LOADED_KEY = "certificates_snapshot_loaded"
NOTICE_KEY = "certificates_notice"

VISIBLE_COLUMNS = (
    "order",
    "date",
    "customer",
    "product",
    "variant",
    "edition",
    "certificate",
)


def _format_time(value):
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y %I:%M %p")
    except ValueError:
        return str(value)


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(META_KEY, {"last_refreshed": "", "saved_at": ""})
    st.session_state.setdefault(NOTICE_KEY, "")


def _load_snapshot_once():
    if st.session_state.get(SNAPSHOT_LOADED_KEY):
        return
    payload = certificate_engine.load_certificates_snapshot()
    st.session_state[ROWS_KEY] = payload.get("rows") or []
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }
    st.session_state[SNAPSHOT_LOADED_KEY] = True


def _display_rows(rows):
    return [{column: row.get(column, "") for column in VISIBLE_COLUMNS} for row in rows or []]


def _column_config():
    return {
        "order": st.column_config.TextColumn("Order"),
        "date": st.column_config.TextColumn("Date"),
        "customer": st.column_config.TextColumn("Customer"),
        "product": st.column_config.TextColumn("Product"),
        "variant": st.column_config.TextColumn("Variant"),
        "edition": st.column_config.TextColumn("Edition"),
        "certificate": st.column_config.TextColumn("Certificate"),
    }


def _refresh_certificates():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before refreshing certificates."
        return
    payload = certificate_engine.refresh_certificates_snapshot(config=config)
    st.session_state[ROWS_KEY] = payload.get("rows") or []
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }
    st.session_state[NOTICE_KEY] = f"Refreshed {len(st.session_state[ROWS_KEY])} certificate rows."


def _generate_missing():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before generating certificates."
        return
    result = certificate_engine.generate_missing_certificates_for_recent_orders(config=config)
    payload = certificate_engine.load_certificates_snapshot()
    st.session_state[ROWS_KEY] = payload.get("rows") or []
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }
    errors = result.get("errors") or []
    if errors:
        st.session_state[NOTICE_KEY] = (
            f"Generated {result.get('generated', 0)} certificate(s). "
            f"{len(errors)} item(s) need review."
        )
    else:
        st.session_state[NOTICE_KEY] = f"Generated {result.get('generated', 0)} missing certificate(s)."


def _regenerate_selected(certificate_id):
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before regenerating certificates."
        return
    result = certificate_engine.regenerate_certificate_by_id(certificate_id, config=config)
    payload = certificate_engine.load_certificates_snapshot()
    st.session_state[ROWS_KEY] = payload.get("rows") or []
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }
    if result.get("found"):
        st.session_state[NOTICE_KEY] = f"Regenerated {result.get('generated', 0)} certificate(s)."
    else:
        st.session_state[NOTICE_KEY] = "; ".join(result.get("errors") or ["Certificate was not found."])


def render_page():
    _ensure_state()
    _load_snapshot_once()
    rows = st.session_state.get(ROWS_KEY) or []
    meta = st.session_state.get(META_KEY) or {}
    template_status = certificate_service.certificate_template_status()

    st.title("Certificates")
    st.caption("Generate certificate PDFs only from saved order edition allocations.")
    st.caption(f"Last refreshed: {_format_time(meta.get('last_refreshed'))}")

    template_cols = st.columns(2)
    template_cols[0].metric("Print template", "Found" if template_status["print_template_found"] else "Missing")
    template_cols[1].metric("Preview template", "Found" if template_status["preview_template_found"] else "Missing")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""

    action_cols = st.columns(3)
    if action_cols[0].button("Refresh Certificates", type="primary", use_container_width=True):
        with st.spinner("Refreshing certificate status..."):
            _refresh_certificates()
        st.rerun()
    if action_cols[1].button("Generate Missing Certificates", use_container_width=True):
        with st.spinner("Generating missing certificate PDFs..."):
            _generate_missing()
        st.rerun()

    selectable = [row for row in rows if row.get("certificate_id")]
    selected_label = ""
    selected_id = ""
    if selectable:
        labels = [
            f"{row.get('order')} | {row.get('edition')} | {row.get('product')} | {row.get('certificate_id')}"
            for row in selectable
        ]
        selected_label = action_cols[2].selectbox(
            "Regenerate selected",
            [""] + labels,
            label_visibility="collapsed",
        )
        if selected_label:
            selected_id = selected_label.rsplit("|", 1)[-1].strip()
    if action_cols[2].button("Regenerate Selected Certificate", use_container_width=True, disabled=not bool(selected_id)):
        with st.spinner("Regenerating selected certificate..."):
            _regenerate_selected(selected_id)
        st.rerun()

    if not rows:
        st.info("No certificate snapshot yet. Use Refresh Certificates when you are ready.")
        return

    st.caption(f"{len(rows)} certificate rows shown.")
    st.dataframe(
        _display_rows(rows),
        hide_index=True,
        use_container_width=True,
        column_order=VISIBLE_COLUMNS,
        column_config=_column_config(),
    )

    ready_rows = [row for row in rows if row.get("pdf_url")]
    if ready_rows:
        st.subheader("Open Certificate PDF")
        link_labels = [
            f"{row.get('order')} | {row.get('edition')} | {row.get('product')} | {row.get('certificate_id')}"
            for row in ready_rows
        ]
        selected_link = st.selectbox("Certificate PDF", link_labels, label_visibility="collapsed")
        selected_row = ready_rows[link_labels.index(selected_link)]
        st.markdown(f"[Open Certificate PDF]({selected_row.get('pdf_url')})")
