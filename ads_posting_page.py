from __future__ import annotations

from datetime import datetime
import html

import streamlit as st

from ads_image_workflow import AdsImageValidationError, prepare_meta_posting_image
from meta_ads_client import (
    MetaAdsApiError,
    MetaPostingClient,
    diagnose_meta_posting_connection,
)
from meta_posting_service import (
    MetaPostingService,
    PostingAmbiguousError,
    PostingBusyError,
    PostingError,
    PostingRequest,
    PostingValidationError,
    SUCCESS_MESSAGE,
    ads_manager_url,
    default_ad_name,
    posting_submission_id,
)


STATE_PREFIX = "ads_posting_"
SUBMISSION_ID_KEY = f"{STATE_PREFIX}submission_id"
CAMPAIGN_KEY = f"{STATE_PREFIX}campaign_id"
CAMPAIGN_TRACK_KEY = f"{STATE_PREFIX}campaign_track"
ADSET_KEY = f"{STATE_PREFIX}adset_id"
URL_KEY = f"{STATE_PREFIX}product_url"
IMAGE_KEY = f"{STATE_PREFIX}image"
PRIMARY_TEXT_KEY = f"{STATE_PREFIX}primary_text"
HEADLINE_KEY = f"{STATE_PREFIX}headline"
AD_NAME_KEY = f"{STATE_PREFIX}ad_name"
AUTO_AD_NAME_KEY = f"{STATE_PREFIX}auto_ad_name"
DESCRIPTION_KEY = f"{STATE_PREFIX}description"
RESULT_KEY = f"{STATE_PREFIX}result"


@st.cache_data(ttl=300, show_spinner=False)
def _load_meta_overview():
    return diagnose_meta_posting_connection()


@st.cache_data(ttl=300, show_spinner=False)
def _load_campaign_adsets(campaign_id):
    client = MetaPostingClient()
    return tuple(dict(row) for row in client.campaign_adsets(campaign_id))


@st.cache_data(ttl=30, show_spinner=False)
def _load_recent_posts():
    return tuple(dict(row) for row in MetaPostingService().recent_posts(limit=20))


def _clear_meta_cache():
    _load_meta_overview.clear()
    _load_campaign_adsets.clear()


def _render_recent_posts():
    with st.expander("Recent Posts", expanded=False):
        try:
            records = _load_recent_posts()
        except Exception:
            st.caption("Recent posting history is unavailable.")
            return
        if not records:
            st.caption("No paused ads have been posted yet.")
            return
        account_id = MetaPostingClient().ad_account_id
        rows = []
        for record in records:
            rows.append(
                {
                    "Date": str(record.get("completed_at") or record.get("created_at") or ""),
                    "Ad name": str(record.get("ad_name") or ""),
                    "Campaign": str(record.get("campaign_name") or ""),
                    "Ad set": str(record.get("adset_name") or ""),
                    "Status": str(record.get("meta_status") or record.get("status") or "").title(),
                    "Meta Ad ID": str(record.get("meta_ad_id") or ""),
                    "Open": (
                        ads_manager_url(
                            account_id=account_id,
                            campaign_id=record.get("campaign_id"),
                            adset_id=record.get("adset_id"),
                            ad_id=record.get("meta_ad_id"),
                        )
                        if record.get("meta_ad_id")
                        else ""
                    ),
                }
            )
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            column_config={"Open": st.column_config.LinkColumn("Open", display_text="Open")},
        )


def _reset_posting_state():
    for key in (
        SUBMISSION_ID_KEY,
        CAMPAIGN_KEY,
        CAMPAIGN_TRACK_KEY,
        ADSET_KEY,
        URL_KEY,
        IMAGE_KEY,
        PRIMARY_TEXT_KEY,
        HEADLINE_KEY,
        AD_NAME_KEY,
        AUTO_AD_NAME_KEY,
        DESCRIPTION_KEY,
        RESULT_KEY,
    ):
        st.session_state.pop(key, None)
    st.session_state[SUBMISSION_ID_KEY] = posting_submission_id()


def _status_label(row):
    return str(row.get("effective_status") or row.get("status") or "Unknown").replace("_", " ").title()


def _option_label(row):
    name = str(row.get("name") or row.get("id") or "Unnamed")
    return f"{name} — {_status_label(row)}"


def _connection_status(container, label, *, tone):
    colour = {"success": "green", "warning": "orange", "error": "red"}.get(tone, "gray")
    container.markdown(f":{colour}[● **{label}**]")


def _render_connection_details(overview):
    with st.expander("Connection details", expanded=False):
        for key in (
            "configuration",
            "identity",
            "token_identity",
            "ad_account",
            "campaigns",
            "permissions",
        ):
            check = dict((overview.get("checks") or {}).get(key) or {})
            if not check:
                continue
            status = str(check.get("status") or "unknown")
            if status == "ok":
                detail = str(check.get("message") or "OK")
            elif status == "unverified":
                diagnostic = str(check.get("diagnostic") or "")
                detail = "permission introspection unavailable"
                if diagnostic:
                    detail = f"{detail} — {diagnostic}"
            else:
                detail = str(check.get("message") or "Failed")
            endpoint = str(check.get("endpoint") or "")
            endpoint_note = f" — GET `{endpoint}`" if endpoint and status != "ok" else ""
            st.caption(f"**{check.get('label') or key}:** {detail}{endpoint_note}")
        source = str(overview.get("api_version_source") or "default")
        source_label = "Render override" if source == "META_API_VERSION" else "application default"
        st.caption(
            f"**API version:** {overview.get('api_version') or 'unknown'} ({source_label})"
        )


def _render_success(result):
    st.success(SUCCESS_MESSAGE)
    left, right = st.columns(2)
    with left:
        st.markdown(
            f"**{html.escape(str(result.get('ad_name') or 'Ad'))}**  \n"
            f"Campaign: {html.escape(str(result.get('campaign_name') or ''))}  \n"
            f"Ad set: {html.escape(str(result.get('adset_name') or ''))}"
        )
    with right:
        st.markdown(
            f"Meta Ad ID: `{html.escape(str(result.get('meta_ad_id') or ''))}`  \n"
            f"Meta Creative ID: `{html.escape(str(result.get('meta_creative_id') or ''))}`  \n"
            "Status: **Paused**"
        )
    link = ads_manager_url(
        account_id=MetaPostingClient().ad_account_id,
        campaign_id=result.get("campaign_id"),
        adset_id=result.get("adset_id"),
        ad_id=result.get("meta_ad_id"),
    )
    actions = st.columns([1, 1, 4])
    actions[0].link_button("Open in Ads Manager", link, use_container_width=True)
    if actions[1].button("Reset", key=f"{STATE_PREFIX}reset_success", use_container_width=True):
        _reset_posting_state()
        st.rerun()


def render_page():
    st.title("Post Ad")
    st.caption("Upload the finished ad and create it paused in Meta for review.")

    st.session_state.setdefault(SUBMISSION_ID_KEY, posting_submission_id())
    result = dict(st.session_state.get(RESULT_KEY) or {})
    if result and str(result.get("status") or "") == "COMPLETE":
        _render_success(result)
        return

    status_col, refresh_col = st.columns([5, 1])
    try:
        overview = _load_meta_overview()
    except MetaAdsApiError as error:
        _connection_status(status_col, f"Meta unavailable — {error}", tone="error")
        if refresh_col.button("Refresh Meta", use_container_width=True):
            _clear_meta_cache()
            st.rerun()
        return

    configuration_ready = (
        ((overview.get("checks") or {}).get("configuration") or {}).get("status") == "ok"
    )
    if not overview.get("connected"):
        summary = str(overview.get("summary") or "Meta unavailable")
        tone = "warning" if summary == "Meta identity configuration required." else "error"
        _connection_status(status_col, summary, tone=tone)
        if refresh_col.button(
            "Refresh Meta",
            disabled=not configuration_ready,
            use_container_width=True,
        ):
            _clear_meta_cache()
            st.rerun()
        _render_connection_details(overview)
        return
    if overview.get("permission_state") == "missing":
        _connection_status(status_col, "Meta posting permission required", tone="warning")
        if refresh_col.button("Refresh Meta", use_container_width=True):
            _clear_meta_cache()
            st.rerun()
        _render_connection_details(overview)
        return
    _connection_status(status_col, "Meta connected", tone="success")
    if refresh_col.button("Refresh Meta", use_container_width=True):
        _clear_meta_cache()
        st.rerun()
    if overview.get("permission_state") == "unverified":
        _render_connection_details(overview)

    campaigns = tuple(overview.get("campaigns") or ())
    campaign_by_id = {str(row.get("id") or ""): row for row in campaigns if row.get("id")}
    if str(st.session_state.get(CAMPAIGN_KEY) or "") not in {"", *campaign_by_id}:
        st.session_state.pop(CAMPAIGN_KEY, None)
        st.session_state.pop(ADSET_KEY, None)

    st.subheader("Meta destination")
    destination_cols = st.columns(2)
    with destination_cols[0]:
        campaign_id = st.selectbox(
            "Campaign",
            options=("", *campaign_by_id),
            key=CAMPAIGN_KEY,
            format_func=lambda value: "Select campaign" if not value else _option_label(campaign_by_id[value]),
        )
    previous_campaign = str(st.session_state.get(CAMPAIGN_TRACK_KEY) or "")
    if campaign_id != previous_campaign:
        st.session_state[CAMPAIGN_TRACK_KEY] = campaign_id
        st.session_state.pop(ADSET_KEY, None)

    adsets = ()
    adset_error = ""
    if campaign_id:
        try:
            adsets = _load_campaign_adsets(campaign_id)
        except MetaAdsApiError:
            adset_error = "The selected campaign's ad sets could not be loaded."
    adset_by_id = {
        str(row.get("id") or ""): row
        for row in adsets
        if row.get("id") and str(row.get("campaign_id") or campaign_id) == campaign_id
    }
    if str(st.session_state.get(ADSET_KEY) or "") not in {"", *adset_by_id}:
        st.session_state.pop(ADSET_KEY, None)
    with destination_cols[1]:
        adset_id = st.selectbox(
            "Ad Set",
            options=("", *adset_by_id),
            key=ADSET_KEY,
            disabled=not campaign_id or bool(adset_error),
            format_func=lambda value: "Select ad set" if not value else _option_label(adset_by_id[value]),
        )
    if adset_error:
        st.error(adset_error)

    st.subheader("Finished ad")
    product_url = st.text_input("Product URL", placeholder="https://www.sportscaveshop.com/products/...", key=URL_KEY)
    uploaded = st.file_uploader(
        "Ad Image",
        type=("jpg", "jpeg", "png", "webp"),
        accept_multiple_files=False,
        key=IMAGE_KEY,
    )
    image = None
    image_error = ""
    if uploaded is not None:
        try:
            image = prepare_meta_posting_image(uploaded.getvalue(), original_name=uploaded.name)
            converted_note = " (WebP safely converted to PNG)" if image.get("converted") else ""
            st.caption(
                f":green[✓ **Ad image ready** — {image['source_width']} × "
                f"{image['source_height']}{converted_note}]"
            )
        except AdsImageValidationError as error:
            image_error = str(error)
            st.error(image_error)

    primary_text = st.text_area("Primary Text", key=PRIMARY_TEXT_KEY, height=130)
    copy_cols = st.columns(2)
    with copy_cols[0]:
        headline = st.text_input("Headline", key=HEADLINE_KEY)
    expected_auto_name = default_ad_name(product_url)
    previous_auto_name = str(st.session_state.get(AUTO_AD_NAME_KEY) or "")
    current_ad_name = str(st.session_state.get(AD_NAME_KEY) or "")
    if not current_ad_name or current_ad_name == previous_auto_name:
        st.session_state[AD_NAME_KEY] = expected_auto_name
    st.session_state[AUTO_AD_NAME_KEY] = expected_auto_name
    with copy_cols[1]:
        ad_name = st.text_input("Ad Name", key=AD_NAME_KEY)
    with st.expander("Optional", expanded=False):
        description = st.text_input("Description", key=DESCRIPTION_KEY)

    st.subheader("Preview")
    with st.container(border=True):
        preview_cols = st.columns([1, 2])
        with preview_cols[0]:
            if image:
                st.image(image["data"], width=230)
            else:
                st.caption("Ad image")
        with preview_cols[1]:
            st.markdown(str(primary_text or "Primary text"))
            st.markdown(f"**{headline or 'Headline'}**")
            st.caption(product_url.strip() or "Product URL")
            st.caption(
                f"Campaign: {_option_label(campaign_by_id[campaign_id]) if campaign_id else 'Not selected'}  \n"
                f"Ad set: {_option_label(adset_by_id[adset_id]) if adset_id else 'Not selected'}  \n"
                f"Ad name: {ad_name or 'Not set'}  \nStatus: Paused"
            )

    obvious_ready = bool(
        campaign_id
        and adset_id
        and product_url.strip()
        and image
        and not image_error
        and primary_text.strip()
        and headline.strip()
        and ad_name.strip()
    )
    if st.button(
        "Create Paused Ad",
        key=f"{STATE_PREFIX}create",
        type="primary",
        use_container_width=True,
        disabled=not obvious_ready,
    ):
        request = PostingRequest(
            submission_id=st.session_state[SUBMISSION_ID_KEY],
            campaign_id=campaign_id,
            adset_id=adset_id,
            destination_url=product_url,
            image_bytes=uploaded.getvalue() if uploaded is not None else b"",
            image_name=uploaded.name if uploaded is not None else "",
            primary_text=primary_text,
            headline=headline,
            ad_name=ad_name,
            description=description,
        )
        try:
            with st.spinner("Creating paused ad in Meta…"):
                posted = MetaPostingService().create_paused_ad(request)
        except (PostingValidationError, PostingBusyError, PostingAmbiguousError, PostingError) as error:
            st.error(str(error))
        else:
            st.session_state[RESULT_KEY] = dict(posted)
            _load_recent_posts.clear()
            st.rerun()

    _render_recent_posts()
