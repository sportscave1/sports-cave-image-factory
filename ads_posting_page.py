from __future__ import annotations

import html

import streamlit as st

import ads_page
from ads_image_workflow import AdsImageValidationError, prepare_meta_posting_image
from ads_product_catalog import load_live_edition_product_rows
from meta_ads_client import MetaAdsApiError, MetaPostingClient, diagnose_meta_posting_connection
from meta_posting_service import (
    AD_TYPE,
    CAMPAIGN_DAILY_BUDGET_MINOR,
    COUNTRY_META_CODES,
    EXPECTED_CATALOG_NAME,
    EXPECTED_PIXEL_NAME,
    INSTANT_EXPERIENCE_BUTTON_TEXT,
    PRODUCT_DESCRIPTION,
    SPORT_OPTIONS,
    SUCCESS_MESSAGE,
    MetaPostingService,
    PostingAmbiguousError,
    PostingBusyError,
    PostingError,
    PostingRequest,
    PostingValidationError,
    ads_manager_url,
    adset_name,
    campaign_name,
    next_instant_experience_ad_name,
    load_posting_reference_snapshot,
    posting_submission_id,
)


STATE_PREFIX = "ads_posting_v2_"
SUBMISSION_ID_KEY = f"{STATE_PREFIX}submission_id"
PRODUCT_KEY = f"{STATE_PREFIX}product"
PRODUCT_TRACK_KEY = f"{STATE_PREFIX}product_track"
COUNTRY_KEY = f"{STATE_PREFIX}country"
SPORT_KEY = f"{STATE_PREFIX}sport"
CATALOG_KEY = f"{STATE_PREFIX}catalog"
PRODUCT_SET_KEY = f"{STATE_PREFIX}product_set"
AUDIENCE_KEY = f"{STATE_PREFIX}audience"
IMAGE_KEY = f"{STATE_PREFIX}image"
PRIMARY_TEXT_KEY = f"{STATE_PREFIX}primary_text"
HEADLINE_KEY = f"{STATE_PREFIX}headline"
DESCRIPTION_KEY = f"{STATE_PREFIX}description"
RESULT_KEY = f"{STATE_PREFIX}result"
PROCESSING_KEY = f"{STATE_PREFIX}processing"
META_OVERVIEW_STATE_KEY = "ads_posting_meta_overview"
META_OVERVIEW_ERROR_KEY = "ads_posting_meta_overview_error"
META_REFERENCES_STATE_KEY = "ads_posting_meta_references"
META_REFERENCES_ERROR_KEY = "ads_posting_meta_references_error"
PRODUCT_ROWS_STATE_KEY = "ads_posting_product_rows"


@st.cache_data(ttl=300, show_spinner=False)
def _load_meta_overview():
    return diagnose_meta_posting_connection()


@st.cache_data(ttl=300, show_spinner=False)
def _load_meta_references():
    return load_posting_reference_snapshot(MetaPostingClient())


@st.cache_data(ttl=30, show_spinner=False)
def _load_recent_posts():
    return tuple(dict(row) for row in MetaPostingService().recent_posts(limit=20))


def _clear_meta_cache():
    _load_meta_overview.clear()
    _load_meta_references.clear()
    for key in (
        META_OVERVIEW_STATE_KEY,
        META_OVERVIEW_ERROR_KEY,
        META_REFERENCES_STATE_KEY,
        META_REFERENCES_ERROR_KEY,
    ):
        st.session_state.pop(key, None)


def _session_cached_load(state, value_key, error_key, loader, *, force=False):
    """Keep read-only Meta results stable across ordinary Streamlit reruns."""

    if not force and (value_key in state or error_key in state):
        return dict(state.get(value_key) or {}), str(state.get(error_key) or "")
    state.pop(value_key, None)
    state.pop(error_key, None)
    try:
        value = dict(loader() or {})
    except MetaAdsApiError as error:
        state[error_key] = str(error)
        return {}, str(error)
    state[value_key] = value
    return value, ""


def _meta_state(*, force=False):
    overview, overview_error = _session_cached_load(
        st.session_state,
        META_OVERVIEW_STATE_KEY,
        META_OVERVIEW_ERROR_KEY,
        _load_meta_overview,
        force=force,
    )
    if overview_error or not overview.get("connected"):
        return overview, {}, overview_error, ""
    references, references_error = _session_cached_load(
        st.session_state,
        META_REFERENCES_STATE_KEY,
        META_REFERENCES_ERROR_KEY,
        _load_meta_references,
        force=force,
    )
    return overview, references, overview_error, references_error


def _product_rows_state():
    if PRODUCT_ROWS_STATE_KEY not in st.session_state:
        st.session_state[PRODUCT_ROWS_STATE_KEY] = tuple(load_live_edition_product_rows())
    return tuple(st.session_state.get(PRODUCT_ROWS_STATE_KEY) or ())


def _posting_form_ready(
    *, product_title, product_url, image, image_error, country, sport,
    catalog_id, product_set_id, primary_text, headline, dataset_id, identities_ready,
):
    return bool(
        product_title and product_url and image and not image_error and country and sport
        and catalog_id and product_set_id and str(primary_text or "").strip()
        and str(headline or "").strip() and dataset_id and identities_ready
    )


def _reset_posting_state():
    for key in tuple(st.session_state):
        if str(key).startswith(STATE_PREFIX):
            st.session_state.pop(key, None)
    st.session_state[SUBMISSION_ID_KEY] = posting_submission_id()


def _connection_status(container, label, *, tone):
    colour = {"success": "green", "warning": "orange", "error": "red"}.get(tone, "gray")
    container.markdown(f":{colour}[● **{label}**]")


def _render_connection_details(overview):
    with st.expander("Connection details", expanded=False):
        for key in ("configuration", "page_identity", "instagram_identity", "ad_account", "permissions"):
            check = dict((overview.get("checks") or {}).get(key) or {})
            if check:
                st.caption(
                    f"**{check.get('label') or key}:** {check.get('message') or check.get('status') or 'Unknown'}"
                )
        st.caption(
            f"Graph API: `{overview.get('api_version') or 'unknown'}` · "
            f"permission: `{overview.get('permission_state') or 'unknown'}`"
        )


def _infer_sport(selection):
    row = dict(selection.get("row") or {})
    candidates = [
        str(row.get("product_type") or ""),
        *[str(value or "") for value in row.get("collections") or ()],
        str(selection.get("selected_label") or ""),
    ]
    joined = " | ".join(candidates).casefold()
    aliases = {
        "nba": "NBA", "basketball": "NBA", "motorsport": "Motorsport", "formula 1": "Motorsport",
        "football": "Football", "soccer": "Football", "cricket": "Cricket", "golf": "Golf",
        "horse racing": "Horse Racing", "baseball": "Baseball", "boxing": "Combat", "ufc": "Combat",
        "combat": "Combat", "ice hockey": "Ice Hockey", "nhl": "Ice Hockey", "nfl": "NFL",
        "rugby union": "Rugby Union", "tennis": "Tennis",
    }
    for needle, sport in aliases.items():
        if needle in joined:
            return sport
    return "Other"


def _audience_options(references):
    rows = [{"key": "broad", "type": "broad", "label_type": "Broad", "id": "", "name": "Broad"}]
    rows.extend(
        {
            "key": f"saved:{row.get('id')}", "type": "saved", "id": str(row.get("id") or ""),
            "label_type": "Saved",
            "name": str(row.get("name") or row.get("id") or "Saved audience"),
        }
        for row in references.get("saved_audiences") or () if row.get("id")
    )
    rows.extend(
        {
            "key": f"custom:{row.get('id')}", "type": "custom",
            "label_type": "Lookalike" if row.get("lookalike_spec") or str(row.get("subtype") or "").upper() == "LOOKALIKE" else "Custom",
            "id": str(row.get("id") or ""),
            "name": str(row.get("name") or row.get("id") or "Custom audience"),
        }
        for row in references.get("custom_audiences") or () if row.get("id")
    )
    return tuple(rows)


def _render_object_result(result, *, title):
    st.subheader(title)
    rows = []
    for label, name_key, id_key in (
        ("Campaign", "campaign_name", "campaign_id"),
        ("Ad set", "adset_name", "adset_id"),
        ("Page photo", "", "meta_page_photo_id"),
        ("IE photo element", "", "meta_canvas_photo_element_id"),
        ("IE product element", "", "meta_canvas_product_element_id"),
        ("IE button element", "", "meta_canvas_button_element_id"),
        ("IE footer element", "", "meta_canvas_footer_element_id"),
        ("Instant Experience", "", "meta_instant_experience_id"),
        ("Creative", "", "meta_creative_id"),
        ("Ad", "ad_name", "meta_ad_id"),
    ):
        object_id = str(result.get(id_key) or "")
        rows.append({"Object": label, "Name": str(result.get(name_key) or ""), "ID": object_id, "State": "Created" if object_id else "Not created"})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    if result.get("safe_error"):
        st.caption(str(result.get("safe_error")))


def _render_success(result):
    st.success(SUCCESS_MESSAGE)
    _render_object_result(result, title=str(result.get("ad_name") or "Created Meta hierarchy"))
    currency = str(result.get("account_currency") or "account currency")
    st.caption(
        f"Product: **{result.get('product_title') or ''}** · Country: **{result.get('country') or ''}** · "
        f"Product set: **{result.get('product_set_name') or result.get('product_set_id') or ''}** · "
        f"Destination: {result.get('destination_url') or ''}"
    )
    st.caption(
        f"Campaign budget: **$25.00 {currency}/day** · Objective: **Sales** · Optimization: **Purchase** · "
        "Placements: **Advantage+** · Audience: **Advantage+** · Multi-advertiser ads: **On** · "
        "Generate backgrounds: **Off**"
    )
    link = ads_manager_url(
        account_id=MetaPostingClient().ad_account_id,
        campaign_id=result.get("campaign_id"), adset_id=result.get("adset_id"),
        ad_id=result.get("meta_ad_id"),
    )
    actions = st.columns([1, 1, 4])
    actions[0].link_button("Open in Ads Manager", link, use_container_width=True)
    if actions[1].button("New campaign", use_container_width=True):
        _reset_posting_state()
        st.rerun()


def _render_recent_posts():
    with st.expander("Recent Posting jobs", expanded=False):
        try:
            records = _load_recent_posts()
        except Exception:
            st.caption("Posting history is unavailable.")
            return
        if not records:
            st.caption("No Posting jobs are recorded yet.")
            return
        st.dataframe(
            [
                {
                    "Date": str(row.get("completed_at") or row.get("created_at") or ""),
                    "Product": str(row.get("product_title") or ""),
                    "Ad": str(row.get("ad_name") or ""),
                    "Status": str(row.get("status") or "").replace("_", " ").title(),
                    "Campaign ID": str(row.get("campaign_id") or ""),
                    "Ad set ID": str(row.get("adset_id") or ""),
                    "Ad ID": str(row.get("meta_ad_id") or ""),
                }
                for row in records
            ],
            hide_index=True, use_container_width=True,
        )


def render_page():
    st.title("Post Ad")
    st.caption("Build a complete new Meta Sales campaign, ad set, Instant Experience, and collection ad — all paused.")
    st.session_state.setdefault(SUBMISSION_ID_KEY, posting_submission_id())
    st.session_state.setdefault(PROCESSING_KEY, False)

    result = dict(st.session_state.get(RESULT_KEY) or {})
    if str(result.get("status") or "") == "COMPLETE":
        _render_success(result)
        _render_recent_posts()
        return

    status_col, refresh_col = st.columns([5, 1])
    refresh_meta = refresh_col.button(
        "Refresh Meta",
        use_container_width=True,
        disabled=st.session_state[PROCESSING_KEY],
    )
    if refresh_meta:
        _clear_meta_cache()
        with st.spinner("Refreshing Meta references…"):
            overview, references, overview_error, references_error = _meta_state(force=True)
        st.toast(
            "Meta setup needs attention"
            if overview_error or references_error
            else "Meta references refreshed"
        )
    else:
        overview, references, overview_error, references_error = _meta_state()

    catalog_resolution = dict(references.get("catalog_resolution") or {})
    dataset_resolution = dict(references.get("dataset_resolution") or {})
    references_ready = bool(
        catalog_resolution.get("resolved")
        and dataset_resolution.get("resolved")
        and references.get("product_sets")
        and references.get("page")
        and references.get("instagram")
    )
    if overview_error:
        _connection_status(status_col, f"Meta unavailable — {overview_error}", tone="warning")
    elif not overview.get("connected") or overview.get("permission_state") == "missing":
        _connection_status(status_col, str(overview.get("summary") or "Meta unavailable"), tone="warning")
        _render_connection_details(overview)
    elif references_ready:
        _connection_status(status_col, "Meta connected · references ready", tone="success")
    else:
        _connection_status(status_col, "Meta connected · setup needs attention", tone="warning")
    warnings = tuple(str(value) for value in references.get("warnings") or () if str(value).strip())
    if warnings:
        st.caption("⚠ " + " · ".join(warnings[:3]))

    product_rows = _product_rows_state()
    product_records = ads_page.build_ads_product_selector_records(product_rows)
    record_by_identity = {str(row["identity"]): row for row in product_records}
    if not record_by_identity:
        st.error("No Edition Ops products with Shopify data are available. Posting is blocked.")
        return
    selector_value = st.selectbox(
        "Product",
        options=tuple(record_by_identity), index=None, placeholder="Search Edition Ops products",
        filter_mode="fuzzy",
        format_func=lambda value: record_by_identity[value]["label"], key=PRODUCT_KEY,
    )
    selection = ads_page.resolve_ads_product_selector_value(
        selector_value, rows=product_rows, records=product_records
    )
    selected_row = dict(selection.get("row") or {})
    selected_identity = str(selection.get("selector_identity") or "")
    if selected_identity and selected_identity != str(st.session_state.get(PRODUCT_TRACK_KEY) or ""):
        st.session_state[PRODUCT_TRACK_KEY] = selected_identity
        st.session_state[SPORT_KEY] = _infer_sport(selection)
        st.session_state[SUBMISSION_ID_KEY] = posting_submission_id()
        st.session_state.pop(RESULT_KEY, None)
    product_title = str(selection.get("selected_label") or selected_row.get("product_title") or "")
    product_url = str(ads_page.canonical_shopify_product_url_from_row(selected_row) or "")
    product_id = str(selection.get("product_id") or selected_row.get("shopify_product_id") or "")
    product_handle = str(
        selected_row.get("product_handle")
        or selected_row.get("shopify_handle")
        or selected_row.get("handle")
        or ""
    )
    st.text_input("Product URL", value=product_url, disabled=True)
    if product_title and not product_url:
        st.error("This product has no usable Shopify product URL or valid handle. Posting is blocked.")

    targeting_cols = st.columns(2)
    country = targeting_cols[0].selectbox("Country", tuple(COUNTRY_META_CODES), key=COUNTRY_KEY)
    sport = targeting_cols[1].selectbox("Sport / category", SPORT_OPTIONS, key=SPORT_KEY)

    catalog_id = str(catalog_resolution.get("id") or "") if catalog_resolution.get("resolved") else ""
    catalog_label = str(catalog_resolution.get("name") or EXPECTED_CATALOG_NAME)
    st.text_input("Catalog", value=catalog_label if catalog_id else "Not resolved", disabled=True)
    if not catalog_id:
        message = str(catalog_resolution.get("error") or "Meta references have not been refreshed yet.")
        if references or references_error:
            st.error(message)
        else:
            st.info(message)
    product_sets = tuple(dict(row) for row in references.get("product_sets") or ()) if catalog_id else ()
    product_set_by_id = {str(row.get("id")): row for row in product_sets if row.get("id")}
    if str(st.session_state.get(PRODUCT_SET_KEY) or "") not in product_set_by_id:
        st.session_state.pop(PRODUCT_SET_KEY, None)
    product_set_id = st.selectbox(
        "Product set", tuple(product_set_by_id), index=None, placeholder="Select a Meta product set",
        format_func=lambda value: str(product_set_by_id[value].get("name") or value),
        key=PRODUCT_SET_KEY, disabled=not product_set_by_id,
    ) if product_set_by_id else ""
    if catalog_id and not product_set_by_id:
        st.error("Product Sets could not be loaded for the resolved Shopify catalog.")

    audiences = _audience_options(references)
    audience_by_key = {row["key"]: row for row in audiences}
    audience_key = st.selectbox(
        "Audience", tuple(audience_by_key),
        format_func=lambda value: (
            "Broad — Sports Cave Default" if value == "broad"
            else f"{audience_by_key[value]['label_type']} — {audience_by_key[value]['name']}"
        ),
        key=AUDIENCE_KEY,
    )
    audience = audience_by_key[audience_key]
    st.text_input("Ad type", value=AD_TYPE, disabled=True)

    st.subheader("Creative")
    uploaded = st.file_uploader(
        "Finished artwork", type=("jpg", "jpeg", "png", "webp"),
        accept_multiple_files=False, key=IMAGE_KEY,
    )
    image = None
    image_error = ""
    if uploaded is not None:
        try:
            image = prepare_meta_posting_image(uploaded.getvalue(), original_name=uploaded.name)
            st.caption(f":green[✓ **Artwork ready** — {image['source_width']} × {image['source_height']}] · Generate backgrounds will be off")
        except AdsImageValidationError as error:
            image_error = str(error)
            st.error(image_error)
    primary_text = st.text_area("Primary text", key=PRIMARY_TEXT_KEY, height=120)
    copy_cols = st.columns(2)
    headline = copy_cols[0].text_input("Headline", key=HEADLINE_KEY)
    description = copy_cols[1].text_input("Description (optional)", key=DESCRIPTION_KEY)

    existing_names = tuple(references.get("existing_ad_names") or ())
    generated_campaign_name = campaign_name(product_title, country, sport) if product_title else ""
    generated_adset_name = adset_name(country, sport, audience["name"])
    generated_ad_name = next_instant_experience_ad_name(product_title, existing_names) if product_title else ""

    dataset_id = str(dataset_resolution.get("id") or "") if dataset_resolution.get("resolved") else ""
    dataset_label = str(dataset_resolution.get("name") or EXPECTED_PIXEL_NAME) if dataset_id else "Unresolved"
    st.text_input("Dataset", value=dataset_label, disabled=True)
    if not dataset_id:
        dataset_error = str(dataset_resolution.get("error") or "Meta references have not been refreshed yet.")
        if references or references_error:
            st.error(dataset_error)
        else:
            st.info(dataset_error)
    product_set_label = str((product_set_by_id.get(product_set_id) or {}).get("name") or "Unresolved")
    account_currency = str((references.get("account") or {}).get("currency") or "account currency")

    st.subheader("Review")
    with st.container(border=True):
        preview, summary = st.columns([1, 2])
        with preview:
            if image:
                st.image(image["data"], caption="Exact uploaded artwork", use_container_width=True)
            else:
                st.caption("Upload the finished artwork to preview it.")
        with summary:
            st.markdown(str(primary_text or "Primary text"))
            st.markdown(f"**{headline or 'Headline'}**")
            st.caption(product_url or "Product URL unavailable")
            st.caption(
                f"Campaign: **{html.escape(generated_campaign_name or 'Waiting for product')}**  \n"
                f"Ad set: **{html.escape(generated_adset_name)}**  \n"
                f"Ad: **{html.escape(generated_ad_name or 'Waiting for product')}**"
            )
        st.markdown(
            f"**Sales setup:** ${CAMPAIGN_DAILY_BUDGET_MINOR / 100:.2f} {account_currency}/day campaign budget · "
            f"Purchase optimization · Advantage+ placements · Advantage+ audience · {country} only · "
            "Facebook + Instagram identities · Multi-advertiser ads On · Generate backgrounds Off"
        )
        st.caption(
            f"Catalog: {catalog_label if catalog_id else 'Unresolved'} · Product set: {product_set_label} · "
            f"Dataset: {dataset_label} · "
            "Format: Collection · CTA: Shop Now"
        )
        st.caption(
            f"Instant Experience: Storefront · Catalog headline token · {PRODUCT_DESCRIPTION} · "
            f"{INSTANT_EXPERIENCE_BUTTON_TEXT} → {product_url or 'product URL unresolved'} · final status PAUSED"
        )

    identities_ready = bool(references.get("page") and references.get("instagram"))
    ready = _posting_form_ready(
        product_title=product_title,
        product_url=product_url,
        image=image,
        image_error=image_error,
        country=country,
        sport=sport,
        catalog_id=catalog_id,
        product_set_id=product_set_id,
        primary_text=primary_text,
        headline=headline,
        dataset_id=dataset_id,
        identities_ready=identities_ready,
    )

    st.caption("Creates the campaign, ad set and ad paused in Meta for review.")

    if st.button(
        "Create Paused Meta Campaign", type="primary", use_container_width=True,
        disabled=not ready or st.session_state[PROCESSING_KEY], key=f"{STATE_PREFIX}create",
    ):
        st.session_state[PROCESSING_KEY] = True
        request = PostingRequest(
            submission_id=st.session_state[SUBMISSION_ID_KEY], product_id=product_id,
            product_title=product_title, product_handle=product_handle,
            destination_url=product_url, image_bytes=uploaded.getvalue(), image_name=uploaded.name,
            country=country, sport=sport, catalog_id=catalog_id, product_set_id=product_set_id,
            audience_type=audience["type"], audience_id=audience["id"],
            primary_text=primary_text, headline=headline, description=description,
        )
        try:
            with st.spinner("Creating the paused Meta hierarchy…"):
                posted = MetaPostingService().create_paused_campaign(request)
        except (PostingValidationError, PostingBusyError, PostingAmbiguousError, PostingError) as error:
            st.error(str(error))
            partial = dict(getattr(error, "result", {}) or {})
            if partial:
                _render_object_result(partial, title="Partial result — all created ad objects remain paused")
        else:
            st.session_state[RESULT_KEY] = dict(posted)
            _load_recent_posts.clear()
            st.rerun()
        finally:
            st.session_state[PROCESSING_KEY] = False

    _render_recent_posts()
