from __future__ import annotations

import hashlib
import html

import streamlit as st

import ads_page
from ads_image_workflow import (
    AdsImageValidationError,
    build_meta_posting_image_record,
    source_image_signature,
)
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
    PostingCreative,
    PostingError,
    PostingRequest,
    PostingValidationError,
    ads_manager_url,
    adset_name,
    campaign_name,
    next_instant_experience_ad_names,
    load_posting_reference_snapshot,
    posting_ad_results,
    posting_submission_id,
)
from posting_import_csv import (
    ADS_CSV_IMPORT_RUNTIME_VERSION,
    POSTING_IMPORT_FILENAME,
    PostingImportCSVError,
    parse_posting_import_csv,
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
IMAGE_KEYS = tuple(f"{STATE_PREFIX}image_{index}" for index in range(1, 4))
IMAGE_STATE_KEYS = tuple(f"{STATE_PREFIX}image_state_{index}" for index in range(1, 4))
POSTING_IMAGE_RUNTIME_VERSION = "2026-09-01-durable-source-v2"
PRIMARY_TEXT_KEYS = tuple(f"{STATE_PREFIX}primary_text_{index}" for index in range(1, 4))
HEADLINE_KEYS = tuple(f"{STATE_PREFIX}headline_{index}" for index in range(1, 4))
DESCRIPTION_KEYS = tuple(f"{STATE_PREFIX}description_{index}" for index in range(1, 4))
IMAGE_KEY = IMAGE_KEYS[0]
PRIMARY_TEXT_KEY = PRIMARY_TEXT_KEYS[0]
HEADLINE_KEY = HEADLINE_KEYS[0]
DESCRIPTION_KEY = DESCRIPTION_KEYS[0]
RESULT_KEY = f"{STATE_PREFIX}result"
PROCESSING_KEY = f"{STATE_PREFIX}processing"
META_OVERVIEW_STATE_KEY = "ads_posting_meta_overview"
META_OVERVIEW_ERROR_KEY = "ads_posting_meta_overview_error"
META_REFERENCES_STATE_KEY = "ads_posting_meta_references"
META_REFERENCES_ERROR_KEY = "ads_posting_meta_references_error"
PRODUCT_ROWS_STATE_KEY = "ads_posting_product_rows"
CSV_IMPORT_KEY = f"{STATE_PREFIX}csv_import"
CSV_IMPORT_STATE_KEY = f"{STATE_PREFIX}csv_import_state"
ADS_COPY_ROUTES_STATE_KEY = f"{STATE_PREFIX}ads_copy_routes"


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


def _uploaded_file_identity(uploaded_file):
    if uploaded_file is None:
        return ""
    file_id = str(getattr(uploaded_file, "file_id", "") or "").strip()
    if file_id:
        return file_id
    return "|".join(
        (
            str(getattr(uploaded_file, "name", "") or ""),
            str(getattr(uploaded_file, "size", "") or ""),
            str(getattr(uploaded_file, "type", "") or ""),
        )
    )


def capture_posting_image_upload(uploaded_file, previous=None):
    """Read and inspect a selected image once, then reuse its stable local state."""

    if uploaded_file is None:
        return dict(previous or {})
    previous = dict(previous or {})
    upload_identity = _uploaded_file_identity(uploaded_file)
    source_file_id = str(getattr(uploaded_file, "file_id", "") or "").strip()
    if (
        previous.get("runtime_version") == POSTING_IMAGE_RUNTIME_VERSION
        and source_file_id
        and upload_identity == str(previous.get("upload_identity") or "")
        and (
            (previous.get("valid") and previous.get("data"))
            or previous.get("error")
        )
    ):
        return previous

    image_name = str(getattr(uploaded_file, "name", "") or "image")
    image_type = str(getattr(uploaded_file, "type", "") or "")
    source_bytes = bytes(uploaded_file.getvalue() or b"")
    source_hash = source_image_signature(source_bytes) if not source_file_id else ""
    if (
        previous.get("runtime_version") == POSTING_IMAGE_RUNTIME_VERSION
        and not source_file_id
        and source_hash == str(previous.get("source_hash") or "")
        and (
            (previous.get("valid") and previous.get("data"))
            or previous.get("error")
        )
    ):
        return previous
    try:
        captured = build_meta_posting_image_record(
            source_bytes,
            original_name=image_name,
            declared_content_type=image_type,
            upload_identity=upload_identity or source_hash,
            preview_max_edge=320,
            preview_quality=72,
        )
    except AdsImageValidationError as error:
        return {
            "upload_identity": upload_identity,
            "source_hash": source_hash,
            "name": image_name,
            "type": image_type,
            "runtime_version": POSTING_IMAGE_RUNTIME_VERSION,
            "valid": False,
            "error": str(error),
        }
    return {
        **captured,
        "runtime_version": POSTING_IMAGE_RUNTIME_VERSION,
    }


def _sync_posting_image_upload(index, uploaded_file, *, state=None):
    state = st.session_state if state is None else state
    state_key = IMAGE_STATE_KEYS[int(index) - 1]
    captured = capture_posting_image_upload(uploaded_file, state.get(state_key))
    if captured:
        state[state_key] = captured
    return dict(captured)


def _posting_image_size_label(size):
    size = int(size or 0)
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _posting_record_handle(record):
    row = dict((record or {}).get("row") or {})
    return str(
        row.get("product_handle")
        or row.get("shopify_handle")
        or row.get("handle")
        or ""
    ).strip().casefold()


def _posting_record_title(record):
    row = dict((record or {}).get("row") or {})
    return str(
        row.get("product_title")
        or row.get("edition_name")
        or row.get("product_name")
        or row.get("title")
        or (record or {}).get("label")
        or ""
    ).strip()


def match_posting_import_product(batch, product_records):
    records = tuple(dict(record or {}) for record in product_records or ())
    handle = str((batch or {}).get("product_handle") or "").strip().casefold()
    csv_url = str((batch or {}).get("product_url") or "").strip().rstrip("/")
    title = str((batch or {}).get("product_name") or "").strip().casefold()

    handle_matches = [record for record in records if handle and _posting_record_handle(record) == handle]
    if len(handle_matches) == 1:
        return handle_matches[0]
    if len(handle_matches) > 1:
        raise PostingImportCSVError("More than one Posting product matches this product_handle.")

    url_matches = []
    if csv_url:
        for record in records:
            canonical_url = str(
                ads_page.canonical_shopify_product_url_from_row(record.get("row") or {}) or ""
            ).strip().rstrip("/")
            if canonical_url and canonical_url.casefold() == csv_url.casefold():
                url_matches.append(record)
    if len(url_matches) == 1:
        return url_matches[0]
    if len(url_matches) > 1:
        raise PostingImportCSVError("More than one Posting product matches this product URL.")

    title_matches = [
        record for record in records
        if title and _posting_record_title(record).casefold() == title
    ]
    if len(title_matches) == 1:
        return title_matches[0]
    if len(title_matches) > 1:
        raise PostingImportCSVError(
            "The product title is duplicated. Update the CSV with the exact product_handle."
        )
    raise PostingImportCSVError(
        "The Posting CSV product could not be matched to the current Edition Ops product list."
    )


def apply_posting_import_to_state(batch, product_records, *, state=None):
    state = st.session_state if state is None else state
    ads = tuple(dict(row or {}) for row in (batch or {}).get("ads") or ())
    if len(ads) != 3:
        raise PostingImportCSVError("Posting CSV must contain exactly three ads.")

    if str((batch or {}).get("source_schema_kind") or "") == "ads_copy":
        updates = {
            SUBMISSION_ID_KEY: posting_submission_id(),
            ADS_COPY_ROUTES_STATE_KEY: ads,
        }
        for index, ad in enumerate(ads):
            updates[PRIMARY_TEXT_KEYS[index]] = str(ad.get("primary_text") or "")
            updates[HEADLINE_KEYS[index]] = str(ad.get("headline") or "")
        state.update(updates)
        state.pop(RESULT_KEY, None)

        selected_identity = str(state.get(PRODUCT_KEY) or "")
        selected_product = next(
            (
                dict(record or {})
                for record in product_records or ()
                if str((record or {}).get("identity") or "") == selected_identity
            ),
            {},
        )
        selected_url = str(
            ads_page.canonical_shopify_product_url_from_row(
                selected_product.get("row") or {}
            )
            or ""
        )
        return {
            "product": (
                _posting_record_title(selected_product)
                or str(selected_product.get("label") or "")
                or "Not selected yet"
            ),
            "product_identity": selected_identity,
            "product_url": selected_url,
            "country": str(state.get(COUNTRY_KEY) or ""),
            "sport": str(state.get(SPORT_KEY) or ""),
            "campaign_type": "Instant Experience",
            "ads_loaded": 3,
            "variations_loaded": sum(
                len(tuple(ad.get("variations") or ())) for ad in ads
            ),
        }

    matched = match_posting_import_product(batch, product_records)

    updates = {
        PRODUCT_KEY: str(matched.get("identity") or ""),
        PRODUCT_TRACK_KEY: str(matched.get("identity") or ""),
        COUNTRY_KEY: str(batch.get("country") or ""),
        SPORT_KEY: str(batch.get("sport_category") or ""),
        SUBMISSION_ID_KEY: posting_submission_id(),
    }
    for index, ad in enumerate(ads):
        updates[PRIMARY_TEXT_KEYS[index]] = str(ad.get("primary_text") or "")
        updates[HEADLINE_KEYS[index]] = str(ad.get("headline") or "")
        updates[DESCRIPTION_KEYS[index]] = str(ad.get("description") or "")
    state.update(updates)
    state.pop(RESULT_KEY, None)
    canonical_url = str(
        ads_page.canonical_shopify_product_url_from_row(matched.get("row") or {}) or ""
    )
    return {
        "product": _posting_record_title(matched) or str(matched.get("label") or ""),
        "product_identity": str(matched.get("identity") or ""),
        "product_url": canonical_url,
        "country": str(batch.get("country") or ""),
        "sport": str(batch.get("sport_category") or ""),
        "campaign_type": str(batch.get("campaign_type") or ""),
        "ads_loaded": 3,
    }


def process_posting_csv_upload(uploaded_file, product_records, *, state=None):
    state = st.session_state if state is None else state
    if uploaded_file is None:
        return dict(state.get(CSV_IMPORT_STATE_KEY) or {})
    previous = dict(state.get(CSV_IMPORT_STATE_KEY) or {})
    source_file_id = str(getattr(uploaded_file, "file_id", "") or "").strip()
    same_runtime = previous.get("runtime_version") == ADS_CSV_IMPORT_RUNTIME_VERSION
    if (
        same_runtime
        and source_file_id
        and source_file_id == str(previous.get("source_file_id") or "")
    ):
        return previous

    source_bytes = bytes(uploaded_file.getvalue() or b"")
    upload_identity = hashlib.sha256(source_bytes).hexdigest()
    if (
        same_runtime
        and not source_file_id
        and upload_identity == str(previous.get("upload_identity") or "")
    ):
        return previous
    try:
        batch = parse_posting_import_csv(
            source_bytes,
            filename=str(getattr(uploaded_file, "name", "") or POSTING_IMPORT_FILENAME),
            allowed_countries=tuple(COUNTRY_META_CODES),
            allowed_sports=SPORT_OPTIONS,
            allowed_campaign_types=(AD_TYPE,),
        )
        summary = apply_posting_import_to_state(batch, product_records, state=state)
        status = {
            "ok": True,
            "upload_identity": upload_identity,
            "source_file_id": source_file_id,
            "runtime_version": ADS_CSV_IMPORT_RUNTIME_VERSION,
            "message": (
                "Ads CSV imported — copy applied."
                if batch.get("source_schema_kind") == "ads_copy"
                else "CSV imported — ad copy applied."
            ),
            "summary": summary,
        }
    except PostingImportCSVError as error:
        status = {
            "ok": False,
            "upload_identity": upload_identity,
            "source_file_id": source_file_id,
            "runtime_version": ADS_CSV_IMPORT_RUNTIME_VERSION,
            "message": str(error),
            "summary": {},
        }
    state[CSV_IMPORT_STATE_KEY] = status
    return status


def _posting_form_ready(
    *, product_title, product_url, creatives, country, sport,
    catalog_id, product_set_id, dataset_id, identities_ready,
):
    return bool(
        product_title and product_url and country and sport and catalog_id and product_set_id
        and dataset_id and identities_ready and len(tuple(creatives or ())) == 3
        and all(
            creative.get("image") and not creative.get("image_error")
            and str(creative.get("primary_text") or "").strip()
            and str(creative.get("headline") or "").strip()
            for creative in creatives or ()
        )
    )


def _build_posting_request(
    *,
    submission_id,
    product_id,
    product_title,
    product_handle,
    product_url,
    country,
    sport,
    catalog_id,
    product_set_id,
    audience,
    creatives,
):
    """Map reviewed local creative state into the existing Meta request contract."""

    return PostingRequest(
        submission_id=submission_id,
        product_id=product_id,
        product_title=product_title,
        product_handle=product_handle,
        destination_url=product_url,
        country=country,
        sport=sport,
        catalog_id=catalog_id,
        product_set_id=product_set_id,
        audience_type=str((audience or {}).get("type") or "broad"),
        audience_id=str((audience or {}).get("id") or ""),
        creatives=tuple(
            PostingCreative(
                image_bytes=bytes((creative.get("image") or {}).get("data") or b""),
                image_name=str((creative.get("image") or {}).get("name") or "image"),
                primary_text=str(creative.get("primary_text") or ""),
                headline=str(creative.get("headline") or ""),
                description=str(creative.get("description") or ""),
            )
            for creative in creatives or ()
        ),
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
    ):
        object_id = str(result.get(id_key) or "")
        rows.append({"Object": label, "Name": str(result.get(name_key) or ""), "ID": object_id, "State": "Created" if object_id else "Not created"})
    for ad_result in posting_ad_results(result.get("ad_results")):
        index = int(ad_result.get("index") or 0)
        canvas_id = str(ad_result.get("meta_instant_experience_id") or "")
        ad_id = str(ad_result.get("meta_ad_id") or "")
        state = str(ad_result.get("status") or "PENDING").replace("_", " ").title()
        rows.extend(
            (
                {
                    "Object": f"Instant Experience {index}",
                    "Name": str(ad_result.get("instant_experience_name") or ""),
                    "ID": canvas_id,
                    "State": "Created" if canvas_id else state,
                },
                {
                    "Object": f"Ad {index}",
                    "Name": str(ad_result.get("ad_name") or ""),
                    "ID": ad_id,
                    "State": "Created" if ad_id else state,
                },
            )
        )
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
    first_ad = posting_ad_results(result.get("ad_results"))[0]
    link = ads_manager_url(
        account_id=MetaPostingClient().ad_account_id,
        campaign_id=result.get("campaign_id"), adset_id=result.get("adset_id"),
        ad_id=first_ad.get("meta_ad_id") or result.get("meta_ad_id"),
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
                    "Ads": ", ".join(
                        str(item.get("ad_name") or "")
                        for item in posting_ad_results(row.get("ad_results"))
                        if str(item.get("ad_name") or "")
                    ) or str(row.get("ad_name") or ""),
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
    st.caption("Build one Meta Sales campaign, one ad set and three Instant Experience ads — all paused.")
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
        _connection_status(status_col, "Meta connected · ready", tone="success")
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
    posting_csv = st.file_uploader(
        "Import Ads CSV",
        type=("csv",),
        accept_multiple_files=False,
        key=CSV_IMPORT_KEY,
        max_upload_size=2,
        help="Upload the Instant Experience CSV saved or exported by New Ads.",
    )
    import_status = process_posting_csv_upload(
        posting_csv,
        product_records,
    )
    if import_status.get("ok"):
        summary = dict(import_status.get("summary") or {})
        st.success(str(import_status.get("message") or "CSV imported — ad copy applied."))
        st.caption(
            f"Product: {summary.get('product') or ''} · "
            f"Country: {summary.get('country') or ''} · "
            f"Sport: {summary.get('sport') or ''} · "
            f"Ads loaded: {summary.get('ads_loaded') or 0}"
        )
    elif import_status.get("message"):
        st.error(str(import_status.get("message")))
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

    dataset_id = str(dataset_resolution.get("id") or "") if dataset_resolution.get("resolved") else ""
    dataset_label = str(dataset_resolution.get("name") or EXPECTED_PIXEL_NAME) if dataset_id else "Unresolved"
    st.text_input("Dataset", value=dataset_label, disabled=True)
    if not dataset_id:
        dataset_error = str(dataset_resolution.get("error") or "Meta references have not been refreshed yet.")
        if references or references_error:
            st.error(dataset_error)
        else:
            st.info(dataset_error)

    st.subheader("Creatives")
    creative_inputs = []
    for index in range(1, 4):
        with st.container(border=True):
            st.markdown(f"**Ad {index}**")
            uploaded = st.file_uploader(
                f"Image {index}", type=("jpg", "jpeg", "png", "webp"),
                accept_multiple_files=False, key=IMAGE_KEYS[index - 1],
            )
            image = _sync_posting_image_upload(index, uploaded)
            image_error = str(image.get("error") or "")
            if image.get("valid"):
                st.caption(
                    f":green[✓ **Image {index} ready**] · "
                    f"{_posting_image_size_label(image.get('source_size'))} "
                    f"{image.get('source_format') or ''} · "
                    f"{image.get('source_width')} × {image.get('source_height')} · "
                    "Instant Experience cover · Generate backgrounds off"
                )
            elif image_error:
                st.error(image_error)
            primary_text = st.text_area(
                f"Primary Text {index}", key=PRIMARY_TEXT_KEYS[index - 1], height=100
            )
            copy_cols = st.columns(2)
            headline = copy_cols[0].text_input(
                f"Headline {index}", key=HEADLINE_KEYS[index - 1]
            )
            description = copy_cols[1].text_input(
                f"Description {index} (optional)", key=DESCRIPTION_KEYS[index - 1]
            )
            creative_inputs.append(
                {
                    "image": image,
                    "image_error": image_error,
                    "primary_text": primary_text,
                    "headline": headline,
                    "description": description,
                }
            )

    existing_names = tuple(references.get("existing_ad_names") or ())
    generated_campaign_name = campaign_name(product_title, country, sport) if product_title else ""
    generated_adset_name = adset_name(country, sport, audience["name"])
    generated_ad_names = (
        next_instant_experience_ad_names(product_title, existing_names, count=3)
        if product_title else ("", "", "")
    )
    product_set_label = str((product_set_by_id.get(product_set_id) or {}).get("name") or "Unresolved")
    account_currency = str((references.get("account") or {}).get("currency") or "account currency")

    st.subheader("Review")
    with st.container(border=True):
        st.markdown(
            f"Campaign: **{html.escape(generated_campaign_name or 'Waiting for product')}**  \n"
            f"Ad set: **{html.escape(generated_adset_name)}**  \n"
            "Structure: **1 Campaign → 1 Ad Set → 3 Ads**"
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
    for index, (creative, ad_name) in enumerate(
        zip(creative_inputs, generated_ad_names), start=1
    ):
        with st.container(border=True):
            preview, summary = st.columns([1, 2])
            with preview:
                if creative["image"].get("preview_data"):
                    st.image(
                        creative["image"]["preview_data"],
                        caption=f"Image {index} / Storefront cover {index}",
                        use_container_width=True,
                    )
                elif creative["image"].get("valid"):
                    st.caption(f"Image {index} is ready. Preview unavailable.")
                else:
                    st.caption(f"Upload Image {index} to preview it.")
            with summary:
                st.markdown(f"**Ad {index} — {html.escape(ad_name or 'Waiting for product')}**")
                st.markdown(str(creative["primary_text"] or f"Primary Text {index}"))
                st.markdown(f"**{creative['headline'] or f'Headline {index}'}**")
                if str(creative["description"] or "").strip():
                    st.caption(f"Description: {creative['description']}")
                st.caption(f"Instant Experience: {ad_name or f'Ad {index}'} | Storefront")

    identities_ready = bool(references.get("page") and references.get("instagram"))
    ready = _posting_form_ready(
        product_title=product_title,
        product_url=product_url,
        creatives=creative_inputs,
        country=country,
        sport=sport,
        catalog_id=catalog_id,
        product_set_id=product_set_id,
        dataset_id=dataset_id,
        identities_ready=identities_ready,
    )

    st.caption(
        "Creates one paused campaign, one paused ad set and three paused "
        "Instant Experience ads in Meta for review."
    )

    if st.button(
        "Create 3 Paused Meta Ads", type="primary", use_container_width=True,
        disabled=not ready or st.session_state[PROCESSING_KEY], key=f"{STATE_PREFIX}create",
    ):
        st.session_state[PROCESSING_KEY] = True
        request = _build_posting_request(
            submission_id=st.session_state[SUBMISSION_ID_KEY],
            product_id=product_id,
            product_title=product_title,
            product_handle=product_handle,
            product_url=product_url,
            country=country,
            sport=sport,
            catalog_id=catalog_id,
            product_set_id=product_set_id,
            audience=audience,
            creatives=creative_inputs,
        )
        try:
            with st.spinner("Creating one paused campaign, one ad set and three ads…"):
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
