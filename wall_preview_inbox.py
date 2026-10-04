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
import wall_preview_identity


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


def _current_marketing(rows):
    """One cached, read-only batch for the visible customer matches, never consent writes."""
    identities = list({row.get('shopify_customer_id') for row in rows if row.get('shopify_customer_id')})
    if not identities:
        return {}
    try:
        customers = wall_preview_identity.crm_shopify.Shopify().customer_batch(identities[:50])
        return {customer['id']: customer for customer in customers}
    except Exception as error:
        logging.getLogger(__name__).warning('wall_preview_marketing_unavailable error_type=%s', type(error).__name__)
        return {}


def _render_card(user, row, *, key_prefix):
    if not os_accounts.is_admin(user) and not row.get("marketing_permission"):
        return

    path = str(row.get("dropbox_path") or "")
    try:
        image_url = _temporary_link(
            path,
            str(row.get("dropbox_file_id") or ""),
        ) if path else ""
    except Exception as error:
        category = next(
            (
                value
                for value in (
                    "missing_scope",
                    "expired_access_token",
                    "invalid_access_token",
                    "not_found",
                )
                if value in str(error)
            ),
            "unavailable",
        )
        logging.getLogger(__name__).warning(
            "wall_preview_image_unavailable error_type=%s category=%s",
            type(error).__name__,
            category,
        )
        image_url = ""

    title = str(
        row.get("product_title")
        or row.get("product_handle")
        or "Sports Cave edition"
    ).strip()
    customer_name = str(row.get("customer_name") or "").strip()
    customer_email = str(row.get("customer_email") or "").strip()
    customer_label = customer_name or ("Guest preview" if customer_email else "Customer preview")
    details = " · ".join(
        value
        for value in (
            str(row.get("frame_label") or "").strip(),
            str(row.get("size_label") or "").strip(),
        )
        if value
    )
    status = str(row.get("status") or "new").lower()
    status_label = STATUS_LABELS.get(status, status.title())
    received = _format_received(row.get("received_at"))
    permitted = bool(row.get("marketing_permission"))

    product_url = str(row.get("product_url") or "").strip()
    parts = urlsplit(product_url)
    valid_product_url = (
        parts.scheme == "https"
        and parts.netloc in {"sportscaveshop.com", "www.sportscaveshop.com"}
        and parts.path.startswith("/products/")
    )

    safe_image = html.escape(image_url, quote=True)
    safe_title = html.escape(title)
    safe_customer = html.escape(customer_label)
    safe_email = html.escape(customer_email)
    safe_details = html.escape(details)
    safe_received = html.escape(received)
    safe_product_url = html.escape(product_url, quote=True)

    if image_url:
        image_markup = (
            f'<a class="sc-wall-photo-link" href="{safe_image}" target="_blank" '
            'rel="noopener noreferrer" aria-label="View wall preview">'
            f'<img src="{safe_image}" alt="{safe_title} wall preview" '
            'loading="lazy" decoding="async"></a>'
        )
    else:
        image_markup = (
            '<div class="sc-wall-photo-missing">'
            '<span>Preview unavailable</span>'
            '</div>'
        )

    if valid_product_url:
        product_markup = (
            f'<a class="sc-wall-product" href="{safe_product_url}" '
            f'target="_blank" rel="noopener noreferrer">{safe_title}</a>'
        )
    else:
        product_markup = f'<div class="sc-wall-product">{safe_title}</div>'

    email_markup = ""
    if os_accounts.is_admin(user) and customer_email:
        email_markup = f'<div class="sc-wall-email">{safe_email}</div>'

    permission_class = "is-approved" if permitted else "is-private"
    permission_label = "Social approved" if permitted else "Private"
    status_class = "sc-status-" + status if status in STATUS_LABELS else "sc-status-new"

    st.markdown(
        f"""
        <article class="sc-wall-card">
          <div class="sc-wall-photo">
            {image_markup}
            <span class="sc-wall-status {status_class}">{html.escape(status_label)}</span>
          </div>
          <div class="sc-wall-card-body">
            <div class="sc-wall-customer">{safe_customer}</div>
            {email_markup}
            {product_markup}
            {'<div class="sc-wall-details">' + safe_details + '</div>' if details else ''}
            <div class="sc-wall-card-footer">
              <span>{safe_received}</span>
              <span class="sc-wall-permission {permission_class}">{permission_label}</span>
            </div>
          </div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def render(user):
    if not os_accounts.can_access_page(user, social_media.SOCIAL_MEDIA_ROUTE):
        st.caption("Wall Preview Inbox access is not approved for this account.")
        return

    st.markdown(
        """
        <style>
        .sc-wall-gallery-intro {
            margin: 0 0 1.05rem;
        }
        .sc-wall-gallery-intro h2 {
            margin: 0;
            color: #111111;
            font-size: clamp(1.55rem, 2.2vw, 2rem);
            line-height: 1.08;
            font-weight: 850;
            letter-spacing: -0.035em;
        }
        .sc-wall-gallery-intro p {
            margin: .38rem 0 0;
            color: #77716a;
            font-size: .9rem;
            line-height: 1.45;
        }
        .st-key-wall-preview-grid {
            margin-top: .85rem;
        }
        .st-key-wall-preview-grid [data-testid="stHorizontalBlock"] {
            gap: 1rem;
            align-items: flex-start;
        }
        .sc-wall-card {
            overflow: hidden;
            border: 1px solid #e4ded4;
            border-radius: 15px;
            background: #ffffff;
            box-shadow: 0 3px 14px rgba(17,17,17,.055);
            transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
        }
        .sc-wall-card:hover {
            transform: translateY(-2px);
            border-color: #d6c39a;
            box-shadow: 0 8px 24px rgba(17,17,17,.085);
        }
        .sc-wall-photo {
            position: relative;
            aspect-ratio: 4 / 3;
            overflow: hidden;
            background: #f0ece4;
            border-bottom: 1px solid #ece6dc;
        }
        .sc-wall-photo-link {
            display: flex;
            width: 100%;
            height: 100%;
            align-items: center;
            justify-content: center;
            text-decoration: none;
        }
        .sc-wall-photo img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: #f0ece4;
        }
        .sc-wall-photo-missing {
            display: flex;
            width: 100%;
            height: 100%;
            align-items: center;
            justify-content: center;
            color: #8a837a;
            font-size: .78rem;
            font-weight: 700;
        }
        .sc-wall-status {
            position: absolute;
            top: 11px;
            right: 11px;
            display: inline-flex;
            align-items: center;
            min-height: 27px;
            padding: 0 10px;
            border: 1px solid rgba(255,255,255,.52);
            border-radius: 999px;
            background: rgba(17,17,17,.80);
            color: #ffffff;
            font-size: .67rem;
            line-height: 1;
            font-weight: 800;
            letter-spacing: .025em;
            backdrop-filter: blur(8px);
        }
        .sc-status-approved {
            background: rgba(111,84,24,.88);
        }
        .sc-status-used {
            background: rgba(53,53,53,.84);
        }
        .sc-status-archived {
            background: rgba(103,98,91,.84);
        }
        .sc-wall-card-body {
            padding: .9rem .95rem .88rem;
        }
        .sc-wall-customer {
            overflow: hidden;
            color: #171717;
            font-size: .94rem;
            line-height: 1.25;
            font-weight: 800;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .sc-wall-email {
            overflow: hidden;
            margin-top: .12rem;
            color: #858078;
            font-size: .73rem;
            line-height: 1.25;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .sc-wall-product {
            display: block;
            margin-top: .72rem;
            color: #1f1d1a !important;
            font-size: .82rem;
            line-height: 1.35;
            font-weight: 720;
            text-decoration: none !important;
        }
        .sc-wall-product:hover {
            color: #8b681f !important;
        }
        .sc-wall-details {
            margin-top: .2rem;
            color: #77716a;
            font-size: .72rem;
            line-height: 1.35;
        }
        .sc-wall-card-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .6rem;
            margin-top: .78rem;
            padding-top: .68rem;
            border-top: 1px solid #eee8de;
            color: #8a847b;
            font-size: .66rem;
            line-height: 1.25;
        }
        .sc-wall-permission {
            flex: 0 0 auto;
            padding: 4px 7px;
            border-radius: 999px;
            font-weight: 800;
            white-space: nowrap;
        }
        .sc-wall-permission.is-approved {
            background: #f4ead2;
            color: #7b5a14;
        }
        .sc-wall-permission.is-private {
            background: #f0efed;
            color: #706b65;
        }
        @media(max-width: 900px) {
            .st-key-wall-preview-grid [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }
            .st-key-wall-preview-grid [data-testid="stColumn"] {
                flex: 1 1 calc(50% - .6rem);
                min-width: 0;
            }
        }
        @media(max-width: 560px) {
            .st-key-wall-preview-grid [data-testid="stColumn"] {
                flex: 1 1 100%;
            }
            .sc-wall-card-body {
                padding: .82rem .85rem;
            }
            .sc-wall-gallery-intro p {
                font-size: .84rem;
            }
        }
        </style>
        <div class="sc-wall-gallery-intro">
          <h2>Wall Preview Inbox</h2>
          <p>Customer wall previews from See It On Your Wall.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    is_admin = os_accounts.is_admin(user)
    labels = ("All", "New", "Approved", "Used", "Archived")
    selected = st.segmented_control(
        "Preview status",
        labels,
        default="All",
        key="wall-preview-inbox-status",
        label_visibility="collapsed",
    )
    status = next(
        (key for key, label in STATUS_LABELS.items() if label == selected),
        "all",
    )
    customer_search = st.text_input(
        "Search customer name or email",
        placeholder="Search customer name or email",
        key="wall-preview-customer-search",
        max_chars=254,
        label_visibility="collapsed",
    )

    try:
        rows = wall_preview_store.list_previews(
            status=status,
            limit=60,
            include_private=is_admin,
            customer_search=customer_search,
        )
    except Exception:
        st.warning("Wall previews are temporarily unavailable. Please try again shortly.")
        return

    if not rows:
        st.markdown(
            """
            <div style="padding:2.25rem 1rem;text-align:center;color:#837d74;
                        border:1px dashed #d8d1c5;border-radius:14px;background:#faf8f4;">
              No wall previews to show yet.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    with st.container(key="wall-preview-grid"):
        for start in range(0, len(rows), 3):
            columns = st.columns(3)
            for column, row in zip(columns, rows[start:start + 3]):
                with column:
                    _render_card(
                        user,
                        row,
                        key_prefix=f"wall-preview-{row['id']}",
                    )

