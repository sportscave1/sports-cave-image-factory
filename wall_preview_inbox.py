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
import wall_preview_crm_store


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
    customer_label = customer_name or ("Identified preview" if customer_email else "Anonymous preview" if row.get('client_preview_id') else "Legacy preview")
    details = " · ".join(
        value
        for value in (
            str(row.get("frame_label") or "").strip(),
            str(row.get("size_label") or "").strip(),
        )
        if value
    )
    status = str(row.get("status") or "new").lower()
    status_label = ('Purchased' if row.get('purchased_at') else 'Added to cart' if row.get('added_to_cart')
                    else 'Email sent' if row.get('email_sent_at') else 'Identified' if customer_email
                    else 'Anonymous' if row.get('client_preview_id') else STATUS_LABELS.get(status, status.title()))
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

    markup = f"""
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
        """
    # Blank optional identity lines must not terminate Markdown's HTML block and
    # turn the remaining indented HTML into a visible code block (anonymous/legacy).
    st.markdown('\n'.join(line.strip() for line in markup.splitlines() if line.strip()),unsafe_allow_html=True)
    if st.button('Details', icon=':material/info:',key=key_prefix+'-details',use_container_width=True):
        st.session_state['wall-preview-details'] = str(row['id'])
    if st.session_state.get('wall-preview-details') == str(row['id']):
        with st.container(border=True):
            st.caption('Preview ID · '+str(row['id']))
            if row.get('client_preview_id'):st.caption('Client ID · '+str(row['client_preview_id']))
            if os_accounts.is_admin(user):
                st.caption('Email delivery · '+('Sent' if row.get('email_sent_at') else 'Requested' if row.get('email_requested_at') else 'Not requested'))
                st.caption('Follow-up flow · '+wall_preview_crm_store.FLOW_NAME)
                if row.get('shopify_customer_id'):
                    customer_url=wall_preview_identity.customer_admin_url(row['shopify_customer_id'])
                    if customer_url:st.link_button('Open Shopify customer',customer_url)
            try:
                for item in wall_preview_crm_store.timeline(str(row['id'])):
                    st.caption(item['event_name'].removeprefix('WallPreview')+' · '+_format_received(item['occurred_at']))
            except Exception:st.caption('Timeline temporarily unavailable.')
            if row.get('share_token') and not row.get('share_revoked_at'):
                share_url='https://sports-cave-image-factory.onrender.com/wall-preview/'+row['share_token']
                st.link_button('Open share page',share_url)
                st.code(share_url,language=None)
                if os_accounts.is_admin(user) and st.button('Revoke share link',key=key_prefix+'-revoke'):
                    wall_preview_crm_store.revoke_share(str(row['id']));st.rerun()
            if row.get('marketing_permission'):
                if st.button('Approve',key=key_prefix+'-approve'):_set_status(user,row,'approved')
                if st.button('Mark used',key=key_prefix+'-used'):_set_status(user,row,'used')
            if os_accounts.is_admin(user) or row.get('marketing_permission'):
                if st.button('Archive',key=key_prefix+'-archive'):_set_status(user,row,'archived')
            if st.button('Close details',key=key_prefix+'-close'):
                st.session_state.pop('wall-preview-details',None);st.rerun()


def _open_wall_preview_folder():
    clean_path=dropbox_integration.normalize_dropbox_path(WALL_PREVIEW_DROPBOX_PATH)
    st.session_state['files_browser_path']=clean_path
    st.session_state.pop('files_preview_path',None)
    st.session_state['current_page']='Files'
    st.session_state['selected_page']='Files'
    st.session_state['current_page_source']='wall-preview-inbox'
    st.query_params['page']='files'
    st.query_params['files_path']=clean_path
    for key in ('files_preview','files_action','files_selected'):
        if key in st.query_params:del st.query_params[key]
    st.rerun()


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
            overflow-wrap: anywhere;
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
    folder_col,refresh_col=st.columns([3,1])
    with folder_col:
        if st.button('Open Wall Preview Folder',icon=':material/folder_open:',key='wall-preview-open-dropbox-folder',
                     disabled=not os_accounts.can_access_page(user,'Files')):_open_wall_preview_folder()
    with refresh_col:
        if st.button('Refresh',icon=':material/refresh:',key='wall-preview-refresh'):_TEMP_LINK_CACHE.clear()
    try:
        counts=wall_preview_store.summary(include_private=is_admin)
        st.caption(' · '.join(f'{label} {counts.get(key,0):,}' for key,label in
            (('total','Inbox'),('confirmed','Confirmed'),('email_captured','Email captured'),('added_to_cart','Added to cart'),('purchased','Purchased'))))
    except Exception:st.caption('Inbox counts temporarily unavailable.')
    intent=st.selectbox('CRM intent',('All','Confirmed','Email captured','Added to cart','Purchased'),key='wall-preview-intent')
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
            intent={'All':'all','Confirmed':'confirmed','Email captured':'email_captured','Added to cart':'added_to_cart','Purchased':'purchased'}[intent],
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
