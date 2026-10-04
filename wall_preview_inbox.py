"""Streamlit Wall Preview Inbox for shopper-created room previews."""

from __future__ import annotations

import html
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

import streamlit as st

import dropbox_integration
import os_accounts
import social_media
import wall_preview_store


_TEMP_LINK_CACHE = {}


WALL_PREVIEW_DROPBOX_PATH = "/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox"


STATUS_LABELS = {
    "new": "New",
    "approved": "Approved",
    "used": "Used",
    "archived": "Archived",
    "all": "All",
}


def _dropbox_connection():
    cached = st.session_state.get("wall-preview-dropbox-token") or {}
    if cached.get("token") and float(cached.get("expires_at") or 0) > time.monotonic():
        return cached["token"]
    auth = dropbox_integration.resolve_server_auth(validate=False)
    token = auth["access_token"]
    st.session_state["wall-preview-dropbox-token"] = {
        "token": token,
        "expires_at": time.monotonic() + 20 * 60,
    }
    return token


def _temporary_link(path, file_id=""):
    now = time.monotonic()
    cached = _TEMP_LINK_CACHE.get(path) or {}
    if cached.get("url") and float(cached.get("expires_at") or 0) > now:
        return cached["url"]
    token = _dropbox_connection()
    try:
        url = dropbox_integration.get_temporary_link(token, path)
    except dropbox_integration.DropboxApiError:
        # IDs survive path/namespace changes and avoid creating shared links.
        if not file_id.startswith("id:"):
            raise
        result = dropbox_integration.team_space_client(token).files_get_temporary_link(file_id)
        url = str(result.link or "")
    _TEMP_LINK_CACHE[path] = {"url": url, "expires_at": now + 8 * 60}
    if len(_TEMP_LINK_CACHE) > 250:
        for key in list(_TEMP_LINK_CACHE)[:50]:
            if float((_TEMP_LINK_CACHE.get(key) or {}).get("expires_at") or 0) <= now:
                _TEMP_LINK_CACHE.pop(key, None)
    return url


def _format_received(value):
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(social_media.SYDNEY_TZ).strftime("%d %b %Y · %I:%M %p")
    except Exception:
        return str(value)


def _set_status(user, row, status):
    try:
        wall_preview_store.update_status(
            row.get("id"),
            status,
            actor_user_id=user.get("id"),
            include_private=os_accounts.is_admin(user),
        )
        _TEMP_LINK_CACHE.pop(str(row.get("dropbox_path") or ""), None)
        st.rerun()
    except wall_preview_store.WallPreviewStoreError as error:
        st.error(str(error))
    except Exception:
        st.error("This change could not be saved. Please retry.")


def _render_card(user, row, *, key_prefix):
    if not os_accounts.is_admin(user) and not row.get("marketing_permission"):
        return
    path = str(row.get("dropbox_path") or "")
    try:
        image_url = _temporary_link(path, str(row.get("dropbox_file_id") or "")) if path else ""
    except Exception as error:
        category = next((value for value in ('missing_scope', 'expired_access_token', 'invalid_access_token', 'not_found') if value in str(error)), 'unavailable')
        logging.getLogger(__name__).warning("wall_preview_image_unavailable error_type=%s category=%s", type(error).__name__, category)
        image_url = ""
    with st.container(border=True):
        if image_url:
            st.image(image_url, use_container_width=True)
        else:
            st.caption("Preview image is temporarily unavailable.")

        title = str(row.get("product_title") or row.get("product_handle") or "Sports Cave edition")
        st.markdown(f"**{html.escape(title)}**")
        details = " · ".join(
            value
            for value in (
                str(row.get("frame_label") or "").strip(),
                str(row.get("size_label") or "").strip(),
            )
            if value
        )
        if details:
            st.caption(details)
        st.caption(_format_received(row.get("received_at")))

        permitted = bool(row.get("marketing_permission"))
        if permitted:
            st.caption("Social permission granted")
        else:
            st.caption("PRIVATE PREVIEW · No social permission")

        status = str(row.get("status") or "new").lower()
        st.caption(f"Status · {STATUS_LABELS.get(status, status.title())}")
        actions = st.columns(2)
        if permitted and status == "new":
            if actions[0].button(
                "Approve",
                key=f"{key_prefix}-approve",
                use_container_width=True,
            ):
                _set_status(user, row, "approved")
        elif permitted and status == "approved":
            if actions[0].button(
                "Mark used",
                key=f"{key_prefix}-used",
                use_container_width=True,
            ):
                _set_status(user, row, "used")
        else:
            actions[0].caption(STATUS_LABELS.get(status, status.title()))

        if status != "archived":
            if actions[1].button(
                "Archive",
                key=f"{key_prefix}-archive",
                use_container_width=True,
            ):
                _set_status(user, row, "archived")

        if image_url:
            st.link_button("Open preview", image_url, use_container_width=True)
        product_url = str(row.get("product_url") or "").strip()
        parts = urlsplit(product_url)
        if parts.scheme == "https" and parts.netloc in {"sportscaveshop.com", "www.sportscaveshop.com"} and parts.path.startswith("/products/"):
            st.link_button("Open product", product_url, use_container_width=True)


def _open_wall_preview_folder():
    clean_path = dropbox_integration.normalize_dropbox_path(WALL_PREVIEW_DROPBOX_PATH)
    st.session_state["files_browser_path"] = clean_path
    st.session_state.pop("files_preview_path", None)
    st.session_state["current_page"] = "Files"
    st.session_state["selected_page"] = "Files"
    st.session_state["current_page_source"] = "wall-preview-inbox"
    try:
        st.query_params["page"] = "files"
        st.query_params["files_path"] = clean_path
        for key in ("files_preview", "files_action", "files_selected"):
            if key in st.query_params:
                del st.query_params[key]
    except Exception:
        pass
    st.rerun()


def render(user):
    if not os_accounts.can_access_page(user, social_media.SOCIAL_MEDIA_ROUTE):
        st.caption("Wall Preview Inbox access is not approved for this account.")
        return
    st.markdown("""<style>
        .st-key-wall-preview-grid [data-testid="stImage"] img {width:100%;height:auto;object-fit:contain}
        @media(max-width:900px){.st-key-wall-preview-grid [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
        .st-key-wall-preview-grid [data-testid="stColumn"]{flex:1 1 45%;min-width:0}}
        @media(max-width:560px){.st-key-wall-preview-grid [data-testid="stColumn"]{flex:1 1 100%}}
        </style>""", unsafe_allow_html=True)
    st.subheader("Wall Preview Inbox")
    st.caption(
        "Shopper-saved See It On Your Wall previews arrive here automatically. "
        "Only previews with explicit permission can be approved for social use."
    )
    folder_col, refresh_col = st.columns([3, 1])
    with folder_col:
        if st.button(
            "Open Wall Preview Folder",
            icon=":material/folder_open:",
            key="wall-preview-open-dropbox-folder",
            use_container_width=True,
            disabled=not os_accounts.can_access_page(user, "Files"),
        ):
            _open_wall_preview_folder()
    with refresh_col:
        if st.button("Refresh", icon=":material/refresh:", key="wall-preview-refresh", use_container_width=True):
            _TEMP_LINK_CACHE.clear()
    st.caption(f"Dropbox · {WALL_PREVIEW_DROPBOX_PATH}")

    is_admin = os_accounts.is_admin(user)
    labels = ("New", "Approved", "Used", "Archived", "All")
    selected = st.segmented_control(
        "Preview status",
        labels,
        default="New",
        key="wall-preview-inbox-status",
        label_visibility="collapsed",
    )
    status = next(
        (key for key, label in STATUS_LABELS.items() if label == selected),
        "new",
    )
    try:
        counts = wall_preview_store.summary(include_private=is_admin)
        rows = wall_preview_store.list_previews(
            status=status,
            limit=48,
            include_private=is_admin,
        )
    except Exception:
        st.warning(
            "Wall Preview Inbox is not ready yet. The database migration or Dropbox "
            "connection may still need to be deployed."
        )
        return

    metrics = st.columns(4)
    for column, (key, label) in zip(metrics, (("new", "New Previews"), ("approved", "Approved For Social"), ("used", "Used"), ("private", "Private"))):
        column.metric(label, counts.get(key, 0))

    if not rows:
        st.info("No wall previews match this view yet. Save a preview from a product page, then Refresh.")
        return

    with st.container(key="wall-preview-grid"):
        for start in range(0, len(rows), 3):
            columns = st.columns(3)
            for column, row in zip(columns, rows[start:start + 3]):
                with column:
                    _render_card(user, row, key_prefix=f"wall-preview-{row['id']}")
