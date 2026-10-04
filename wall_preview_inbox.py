"""Streamlit Wall Preview Inbox for shopper-created room previews."""

from __future__ import annotations

import html
import time

import streamlit as st

import dropbox_integration
import os_accounts
import social_media
import wall_preview_store


_TEMP_LINK_CACHE = {}


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


def _temporary_link(path):
    now = time.monotonic()
    cached = _TEMP_LINK_CACHE.get(path) or {}
    if cached.get("url") and float(cached.get("expires_at") or 0) > now:
        return cached["url"]
    token = _dropbox_connection()
    url = dropbox_integration.get_temporary_link(token, path)
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
        return value.astimezone(social_media.SYDNEY_TZ).strftime("%d %b %Y · %I:%M %p")
    except Exception:
        return str(value)


def _set_status(user, row, status):
    try:
        wall_preview_store.update_status(
            row.get("id"),
            status,
            actor_user_id=user.get("id"),
        )
        _TEMP_LINK_CACHE.pop(str(row.get("dropbox_path") or ""), None)
        st.rerun()
    except Exception as error:
        st.error(str(error))


def _render_card(user, row, *, key_prefix):
    path = str(row.get("dropbox_path") or "")
    try:
        image_url = _temporary_link(path) if path else ""
    except Exception:
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
            st.success("Approved by shopper for social use.", icon=":material/check_circle:")
        else:
            st.caption("Private preview · social permission not granted.")

        status = str(row.get("status") or "new").lower()
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

        product_url = str(row.get("product_url") or "").strip()
        if product_url.startswith("https://"):
            st.link_button("Open product", product_url, use_container_width=True)


def render(user):
    st.subheader("Wall Preview Inbox")
    st.caption(
        "Shopper-saved See It On Your Wall previews arrive here automatically. "
        "Only previews with explicit permission can be approved for social use."
    )

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

    if not rows:
        st.info("No wall previews match this view yet.")
        return

    permitted_count = sum(bool(row.get("marketing_permission")) for row in rows)
    metrics = st.columns(3)
    metrics[0].metric("Previews", len(rows))
    metrics[1].metric("Social permission", permitted_count)
    metrics[2].metric("Private", len(rows) - permitted_count)

    columns = st.columns(3)
    for index, row in enumerate(rows):
        with columns[index % 3]:
            _render_card(
                user,
                row,
                key_prefix=f"wall-preview-{row.get('id') or index}",
            )
