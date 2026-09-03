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
from meta_collection_diagnostics import (
    MetaCollectionDiagnosticSafetyError,
    MetaCollectionValidateOnlyProbe,
    sanitized_collection_request_shape,
)
from meta_collection_template_copy import (
    MetaCollectionTemplateCopySafetyError,
    MetaCollectionTemplateCopyService,
    MetaCollectionTemplateCopyVerificationError,
    configured_collection_template_ad_id,
    sanitized_template_copy_error,
)
from meta_posting_service import (
    AD_TYPE,
    CAMPAIGN_DAILY_BUDGET_MINOR,
    COUNTRY_META_CODES,
    EXPECTED_CATALOG_NAME,
    EXPECTED_PIXEL_NAME,
    INSTANT_EXPERIENCE_BUTTON_TEXT,
    META_OBJECT_EXISTING_TARGET,
    POSTING_MODE_EXISTING,
    POSTING_MODE_NEW,
    PRODUCT_DESCRIPTION,
    SPORT_OPTIONS,
    SUCCESS_MESSAGE,
    MetaPostingService,
    PostingAmbiguousError,
    PostingAbandonedError,
    PostingBusyError,
    PostingCreative,
    PostingError,
    PostingRequest,
    PostingValidationError,
    ads_manager_url,
    adset_name,
    build_collection_creative_payload,
    campaign_name,
    next_instant_experience_ad_names,
    load_posting_reference_snapshot,
    load_existing_posting_targets,
    posting_ad_results,
    posting_submission_id,
    validate_existing_posting_target,
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
RUN_STATE_KEY = f"{STATE_PREFIX}run_state"
POSTING_MODE_KEY = f"{STATE_PREFIX}posting_mode"
EXISTING_CAMPAIGN_KEY = f"{STATE_PREFIX}existing_campaign"
EXISTING_ADSET_KEY = f"{STATE_PREFIX}existing_adset"
COLLECTION_DIAGNOSTIC_RESULT_KEY = f"{STATE_PREFIX}collection_diagnostic_result"
COLLECTION_DIAGNOSTIC_PROCESSING_KEY = f"{STATE_PREFIX}collection_diagnostic_processing"
COLLECTION_TEMPLATE_COPY_RESULT_KEY = f"{STATE_PREFIX}collection_template_copy_result"
COLLECTION_TEMPLATE_COPY_PROCESSING_KEY = f"{STATE_PREFIX}collection_template_copy_processing"
COLLECTION_TEMPLATE_COPY_ATTEMPTED_KEY = f"{STATE_PREFIX}collection_template_copy_attempted"
META_OVERVIEW_STATE_KEY = "ads_posting_meta_overview"
META_OVERVIEW_ERROR_KEY = "ads_posting_meta_overview_error"
META_REFERENCES_STATE_KEY = "ads_posting_meta_references"
META_REFERENCES_ERROR_KEY = "ads_posting_meta_references_error"
PRODUCT_ROWS_STATE_KEY = "ads_posting_product_rows"
PRODUCT_SELECTOR_STATE_KEY = "ads_posting_product_selector"
PRODUCT_SELECTOR_RUNTIME_VERSION = "2026-09-03-session-selector-v1"
CSV_IMPORT_KEY = f"{STATE_PREFIX}csv_import"
CSV_IMPORT_STATE_KEY = f"{STATE_PREFIX}csv_import_state"
ADS_COPY_ROUTES_STATE_KEY = f"{STATE_PREFIX}ads_copy_routes"

RUN_STATE_DRAFT = "DRAFT"
RUN_STATE_ACTIVE = "ACTIVE"
RUN_STATE_FAILED = "FAILED"
RUN_STATE_COMPLETE = "COMPLETE"
RUN_STATE_ABANDONED = "ABANDONED_EXTERNALLY"
RUN_TERMINAL_STATES = {RUN_STATE_COMPLETE, RUN_STATE_ABANDONED}
RUN_STARTED_STATES = {
    RUN_STATE_ACTIVE,
    RUN_STATE_FAILED,
    "VALIDATING",
    "CAMPAIGN_CREATED",
    "ADSET_CREATED",
    "IMAGE_UPLOADED",
    "PAGE_PHOTO_CREATED",
    "INSTANT_EXPERIENCE_CREATED",
    "CREATIVE_CREATED",
    "AD_CREATED",
    "AMBIGUOUS",
}

POSTING_MODE_LABELS = {
    POSTING_MODE_NEW: "New Campaign",
    POSTING_MODE_EXISTING: "Add to Existing",
}


@st.cache_data(ttl=300, show_spinner=False)
def _load_meta_overview():
    return diagnose_meta_posting_connection()


@st.cache_data(ttl=300, show_spinner=False)
def _load_meta_references():
    return load_posting_reference_snapshot(MetaPostingClient())


@st.cache_data(ttl=60, show_spinner=False)
def _load_existing_meta_targets():
    return load_existing_posting_targets(MetaPostingClient())


@st.cache_data(ttl=30, show_spinner=False)
def _load_recent_posts():
    return tuple(dict(row) for row in MetaPostingService().recent_posts(limit=20))


def _clear_meta_cache():
    _load_meta_overview.clear()
    _load_meta_references.clear()
    _load_existing_meta_targets.clear()
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


def _existing_targets_state(*, force=False):
    """Return short-TTL, read-only Campaign/Ad Set selector data."""

    if force:
        _load_existing_meta_targets.clear()
    try:
        return dict(_load_existing_meta_targets() or {}), ""
    except MetaAdsApiError as error:
        return {}, str(error)


def _adsets_for_campaign(targets, campaign_id):
    campaign_id = str(campaign_id or "")
    return tuple(
        dict(row)
        for row in dict(targets or {}).get("adsets") or ()
        if str(row.get("campaign_id") or "") == campaign_id
    )


def _product_rows_state():
    if PRODUCT_ROWS_STATE_KEY not in st.session_state:
        st.session_state[PRODUCT_ROWS_STATE_KEY] = tuple(load_live_edition_product_rows())
    return tuple(st.session_state.get(PRODUCT_ROWS_STATE_KEY) or ())


def _product_selector_state(product_rows, *, state=None):
    """Build the large Posting selector once per session, not once per rerun."""

    state = st.session_state if state is None else state
    cached = state.get(PRODUCT_SELECTOR_STATE_KEY)
    if (
        isinstance(cached, dict)
        and cached.get("runtime_version") == PRODUCT_SELECTOR_RUNTIME_VERSION
    ):
        return tuple(cached.get("records") or ()), dict(
            cached.get("record_by_identity") or {}
        )

    records = tuple(ads_page.build_ads_product_selector_records(product_rows))
    record_by_identity = {
        str(record["identity"]): record for record in records
    }
    state[PRODUCT_SELECTOR_STATE_KEY] = {
        "runtime_version": PRODUCT_SELECTOR_RUNTIME_VERSION,
        "records": records,
        "record_by_identity": record_by_identity,
    }
    return records, record_by_identity


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
    _prepare_posting_run_for_import(state)

    if str((batch or {}).get("source_schema_kind") or "") == "ads_copy":
        updates = {
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
    posting_mode=POSTING_MODE_NEW,
    target_campaign_id="",
    target_adset_id="",
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
        posting_mode=str(posting_mode or POSTING_MODE_NEW),
        target_campaign_id=str(target_campaign_id or ""),
        target_adset_id=str(target_adset_id or ""),
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


def _collection_validation_signature(
    *, submission_id, product_title, product_set_id, product_url, primary_text, headline
):
    values = (
        submission_id,
        product_title,
        product_set_id,
        product_url,
        primary_text,
        headline,
    )
    return hashlib.sha256(
        "\x1f".join(str(value or "").strip() for value in values).encode("utf-8")
    ).hexdigest()


def _resolve_collection_validation_context(
    record, *, product_title, product_set_id
):
    """Fail closed unless one ledger row contains the complete route-1 retry state."""
    record = dict(record or {})
    if str(record.get("status") or "").upper() != "FAILED":
        raise PostingValidationError(
            "Meta Collection validation requires a failed partial Posting job."
        )
    if str(record.get("product_title") or "").strip() != str(product_title or "").strip():
        raise PostingValidationError(
            "The failed Posting job does not match the currently selected product."
        )
    if str(record.get("product_set_id") or "").strip() != str(product_set_id or "").strip():
        raise PostingValidationError(
            "The failed Posting job does not match the currently selected Product Set."
        )
    route_one = dict(posting_ad_results(record.get("ad_results"))[0])
    context = {
        "campaign_id": str(record.get("campaign_id") or "").strip(),
        "adset_id": str(record.get("adset_id") or "").strip(),
        "instant_experience_id": str(
            route_one.get("meta_instant_experience_id")
            or record.get("meta_instant_experience_id")
            or ""
        ).strip(),
        "image_hash": str(
            route_one.get("meta_image_hash") or record.get("meta_image_hash") or ""
        ).strip(),
        "ad_name": str(
            route_one.get("ad_name") or record.get("ad_name") or ""
        ).strip(),
    }
    missing = [
        label
        for key, label in (
            ("campaign_id", "Campaign"),
            ("adset_id", "Ad Set"),
            ("instant_experience_id", "Instant Experience 1"),
            ("image_hash", "route 1 Meta image hash"),
            ("ad_name", "route 1 ad name"),
        )
        if not context[key]
    ]
    if missing:
        raise PostingValidationError(
            "The failed Posting job is missing: " + ", ".join(missing) + "."
        )
    return context


def collection_validation_decision(test_a, test_b):
    test_a = dict(test_a or {})
    test_b = dict(test_b or {})
    if test_a.get("validated"):
        return (
            "Standalone creative creation validates; investigate difference between "
            "diagnostic and production request."
        )
    if test_b.get("validated"):
        return (
            "Inline Collection creation validated. Production Posting should switch "
            "from standalone AdCreative creation to inline /ads creative creation."
        )
    return (
        "Neither direct path validates. Do not retry production. Proceed to "
        "Collection template/copy investigation."
    )


def run_collection_validation_from_posting_state(
    *,
    submission_id,
    product_title,
    product_set_id,
    product_url,
    primary_text,
    headline,
    service=None,
    client=None,
    probe=None,
):
    """Run Meta's two validate-only paths from current UI and persisted retry state."""
    client = client or MetaPostingClient()
    service = service or MetaPostingService(client=client)
    record = service.failed_collection_diagnostic_job(
        submission_id=submission_id,
        product_title=product_title,
        product_set_id=product_set_id,
    )
    context = _resolve_collection_validation_context(
        record,
        product_title=product_title,
        product_set_id=product_set_id,
    )
    creative_payload = build_collection_creative_payload(
        name=f"{context['ad_name']} | Collection",
        page_id=client.page_id,
        instagram_user_id=client.instagram_user_id,
        image_hash=context["image_hash"],
        canvas_id=context["instant_experience_id"],
        product_set_id=product_set_id,
        destination_url=product_url,
        primary_text=primary_text,
        headline=headline,
    )
    probe = probe or MetaCollectionValidateOnlyProbe(client.config)
    test_a, test_b = probe.run_ab(
        ad_name=context["ad_name"],
        adset_id=context["adset_id"],
        creative_payload=creative_payload,
    )
    return {
        "persistent_meta_writes": "NONE",
        "test_a": dict(test_a or {}),
        "test_b": dict(test_b or {}),
        "decision": collection_validation_decision(test_a, test_b),
        "request_shapes": {
            "test_a": sanitized_collection_request_shape(mode="standalone"),
            "test_b": sanitized_collection_request_shape(
                mode="inline_ad", adset_id=context["adset_id"]
            ),
        },
    }


def run_collection_template_copy_from_posting_state(
    *,
    submission_id,
    product_title,
    product_set_id,
    product_url,
    primary_text,
    headline,
    service=None,
    client=None,
    template_copy_service=None,
):
    """Create and verify one paused template copy from current route-1 state."""
    client = client or MetaPostingClient()
    service = service or MetaPostingService(client=client)
    record = service.failed_collection_diagnostic_job(
        submission_id=submission_id,
        product_title=product_title,
        product_set_id=product_set_id,
    )
    context = _resolve_collection_validation_context(
        record,
        product_title=product_title,
        product_set_id=product_set_id,
    )
    creative_parameters = build_collection_creative_payload(
        name=f"{context['ad_name']} | Collection",
        page_id=client.page_id,
        instagram_user_id=client.instagram_user_id,
        image_hash=context["image_hash"],
        canvas_id=context["instant_experience_id"],
        product_set_id=product_set_id,
        destination_url=product_url,
        primary_text=primary_text,
        headline=headline,
    )
    template_copy_service = template_copy_service or MetaCollectionTemplateCopyService(
        client
    )
    return template_copy_service.create_one_paused_copy(
        source_ad_id=configured_collection_template_ad_id(),
        target_adset_id=context["adset_id"],
        creative_parameters=creative_parameters,
        expected_ad_name=context["ad_name"],
    )


def _ensure_posting_run(state=None):
    state = st.session_state if state is None else state
    run_id = str(state.get(SUBMISSION_ID_KEY) or "").strip()
    if not run_id:
        run_id = posting_submission_id()
        state[SUBMISSION_ID_KEY] = run_id
    state.setdefault(RUN_STATE_KEY, RUN_STATE_DRAFT)
    state.setdefault(POSTING_MODE_KEY, POSTING_MODE_LABELS[POSTING_MODE_NEW])
    return run_id


def _posting_mode(state=None):
    state = st.session_state if state is None else state
    value = str(
        state.get(POSTING_MODE_KEY) or POSTING_MODE_LABELS[POSTING_MODE_NEW]
    )
    return next(
        (
            mode
            for mode, label in POSTING_MODE_LABELS.items()
            if value in {mode, label}
        ),
        POSTING_MODE_NEW,
    )


def _current_run_state(state):
    result = dict(state.get(RESULT_KEY) or {})
    return str(
        result.get("status") or state.get(RUN_STATE_KEY) or RUN_STATE_DRAFT
    ).upper()


def _start_new_posting_run(*, state=None):
    """Open a blank Meta run while retaining the VA's reviewed staging inputs."""

    state = st.session_state if state is None else state
    for key in (
        RESULT_KEY,
        PROCESSING_KEY,
        COLLECTION_DIAGNOSTIC_RESULT_KEY,
        COLLECTION_DIAGNOSTIC_PROCESSING_KEY,
        COLLECTION_TEMPLATE_COPY_RESULT_KEY,
        COLLECTION_TEMPLATE_COPY_PROCESSING_KEY,
        COLLECTION_TEMPLATE_COPY_ATTEMPTED_KEY,
        EXISTING_CAMPAIGN_KEY,
        EXISTING_ADSET_KEY,
    ):
        state.pop(key, None)
    run_id = posting_submission_id()
    state[SUBMISSION_ID_KEY] = run_id
    state[RUN_STATE_KEY] = RUN_STATE_DRAFT
    state[POSTING_MODE_KEY] = POSTING_MODE_LABELS[POSTING_MODE_NEW]
    state[PROCESSING_KEY] = False
    state[COLLECTION_DIAGNOSTIC_PROCESSING_KEY] = False
    state[COLLECTION_TEMPLATE_COPY_PROCESSING_KEY] = False
    return run_id


def _prepare_posting_run_for_import(state):
    """Treat a valid CSV as staging data, never as historical run identity."""

    _ensure_posting_run(state)
    run_state = _current_run_state(state)
    if run_state in RUN_TERMINAL_STATES:
        return _start_new_posting_run(state=state)
    if run_state in RUN_STARTED_STATES:
        raise PostingImportCSVError(
            "This Posting run already has Meta history. Retry it unchanged or "
            "choose Start fresh campaign before importing a different package."
        )
    return str(state[SUBMISSION_ID_KEY])


def _reset_posting_state():
    """Compatibility wrapper for the result-screen New campaign action."""

    return _start_new_posting_run()


def _connection_status(container, label, *, tone):
    colour = {"success": "green", "warning": "orange", "error": "red"}.get(tone, "gray")
    container.markdown(f":{colour}[● **{label}**]")


def _render_connection_details(overview):
    with st.expander("Connection details", expanded=False):
        for key in (
            "configuration", "page_identity", "page_token", "page_auth",
            "instagram_identity", "ad_account", "permissions",
        ):
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
    completed_paused = (
        str(result.get("status") or "").upper() == "COMPLETE"
        and str(result.get("meta_status") or "").upper() == "PAUSED"
    )
    for label, name_key, id_key in (
        ("Campaign", "campaign_name", "campaign_id"),
        ("Ad set", "adset_name", "adset_id"),
    ):
        object_id = str(result.get(id_key) or "")
        ownership_key = "campaign_ownership" if label == "Campaign" else "adset_ownership"
        status_key = (
            "campaign_configured_status"
            if label == "Campaign"
            else "adset_configured_status"
        )
        is_existing_target = (
            str(result.get(ownership_key) or "").upper()
            == META_OBJECT_EXISTING_TARGET
        )
        rows.append(
            {
                "Object": label,
                "Name": str(result.get(name_key) or ""),
                "ID": object_id,
                "State": (
                    str(result.get(status_key) or "Existing").upper()
                    if object_id and is_existing_target
                    else "PAUSED"
                    if object_id and completed_paused
                    else "Created"
                    if object_id
                    else "Not created"
                ),
            }
        )
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
                    "State": (
                        "Reused"
                        if canvas_id and ad_result.get("meta_instant_experience_reused")
                        else "Created" if canvas_id else state
                    ),
                },
                {
                    "Object": f"Ad {index}",
                    "Name": str(ad_result.get("ad_name") or ""),
                    "ID": ad_id,
                    "State": (
                        "PAUSED"
                        if ad_id
                        and str(ad_result.get("meta_ad_configured_status") or "").upper()
                        == "PAUSED"
                        else state
                    ),
                },
            )
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)
    for ad_result in posting_ad_results(result.get("ad_results")):
        verification = dict(
            ad_result.get("instant_experience_verification") or {}
        )
        if not verification:
            continue
        label = str(
            verification.get("display_status")
            or verification.get("verification_state")
            or "UNAVAILABLE"
        )
        source = str(verification.get("verification_source") or "Unavailable")
        st.caption(
            f"Instant Experience {ad_result.get('index')} destination: "
            f"**{label}** · Verification source: {source}"
        )
    if result.get("safe_error"):
        st.caption(str(result.get("safe_error")))
    first_ad = posting_ad_results(result.get("ad_results"))[0]
    product_health = dict(first_ad.get("product_set_health") or {})
    if product_health:
        label = str(product_health.get("status") or "WARNING").upper()
        message = str(product_health.get("message") or "Product Set health unavailable.")
        if label == "READY":
            st.success(f"Product Set health: READY — {message}")
        elif label == "NOT AVAILABLE VIA META API":
            st.info(f"Product Set health: NOT AVAILABLE VIA META API — {message}")
        else:
            st.warning(f"Product Set health: WARNING — {message}")
        if label != "NOT AVAILABLE VIA META API":
            counts = (
                f"Reported: {product_health.get('reported_product_count')} · "
                f"Readable: {product_health.get('readable_product_count')} · "
                f"Eligible: {product_health.get('eligible_product_count')}"
            )
            st.caption(counts)
        reason_details = tuple(product_health.get("reason_details") or ())
        if reason_details:
            st.caption("Reasons: " + " · ".join(str(value) for value in reason_details))


def _render_success(result):
    st.success(SUCCESS_MESSAGE)
    _render_object_result(result, title=str(result.get("ad_name") or "Created Meta hierarchy"))
    currency = str(result.get("account_currency") or "account currency")
    st.caption(
        f"Product: **{result.get('product_title') or ''}** · Country: **{result.get('country') or ''}** · "
        f"Product set: **{result.get('product_set_name') or result.get('product_set_id') or ''}** · "
        f"Destination: {result.get('destination_url') or ''}"
    )
    if str(result.get("posting_mode") or POSTING_MODE_NEW).upper() == POSTING_MODE_EXISTING:
        st.caption(
            "Existing Campaign and Ad Set retained their status, budget, audience and targeting · "
            "3 new route ads: **PAUSED** · Multi-advertiser ads: **On** · "
            "Generate backgrounds: **Off**"
        )
    else:
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


def _collection_validation_message(result):
    result = dict(result or {})
    return str(
        result.get("error_user_msg")
        or result.get("error_user_title")
        or result.get("safe_error")
        or ("Meta accepted this validate-only request." if result.get("validated") else "Validation failed.")
    )


def _render_collection_validation_test(*, title, endpoint, result):
    result = dict(result or {})
    st.markdown(f"**{title}**")
    if result.get("validated"):
        st.success("Result: PASS")
    else:
        st.error("Result: FAIL")
    st.caption(f"Endpoint: `{endpoint}`")
    st.caption(
        f"HTTP status: `{result.get('http_status') if result.get('http_status') is not None else '—'}` · "
        f"Code: `{result.get('error_code') if result.get('error_code') is not None else '—'}` · "
        f"Subcode: `{result.get('error_subcode') if result.get('error_subcode') is not None else '—'}`"
    )
    if result.get("error_user_title"):
        st.caption(f"Title: {result['error_user_title']}")
    st.write(f"Message: {_collection_validation_message(result)}")
    if result.get("fbtrace_id"):
        st.caption(f"fbtrace_id: `{result['fbtrace_id']}`")


def _render_collection_validation(result):
    result = dict(result or {})
    with st.container(border=True):
        st.markdown("### META COLLECTION VALIDATION")
        st.markdown("**Persistent Meta writes:** NONE")
        if result.get("error"):
            st.error(str(result["error"]))
            return
        _render_collection_validation_test(
            title="Test A — Standalone AdCreative",
            endpoint="/adcreatives",
            result=result.get("test_a"),
        )
        _render_collection_validation_test(
            title="Test B — Inline Creative on Ad",
            endpoint="/ads",
            result=result.get("test_b"),
        )
        st.markdown("**DECISION:**")
        st.write(str(result.get("decision") or "No decision is available."))
        with st.expander("Sanitized request shapes", expanded=False):
            st.json(dict(result.get("request_shapes") or {}))


def _render_collection_template_copy(result):
    result = dict(result or {})
    with st.container(border=True):
        st.markdown("### META COLLECTION TEMPLATE COPY")
        st.markdown(
            f"**Persistent Meta writes:** {result.get('persistent_meta_writes') or 'NONE CONFIRMED'}"
        )
        if str(result.get("status") or "").upper() == "PASS":
            if result.get("reconciled_existing_copy"):
                st.success("PASS — the existing paused template copy was reconciled and verified.")
            else:
                st.success("PASS — one paused template copy was created and verified.")
        else:
            st.error(str(result.get("error") or result.get("safe_error") or "Template copy failed."))
        if result.get("copied_ad_id"):
            st.caption(
                f"Copied Ad: `{result.get('copied_ad_id')}` · "
                f"Creative: `{result.get('copied_creative_id') or 'unavailable'}` · "
                f"Target Ad Set: `{result.get('target_adset_id') or 'unavailable'}`"
            )
            st.caption(
                f"Status: `{result.get('copied_status') or '—'}` · "
                f"Configured status: `{result.get('copied_configured_status') or '—'}` · "
                f"Effective status: `{result.get('copied_effective_status') or '—'}`"
            )
        if result.get("error_code") is not None or result.get("http_status") is not None:
            st.caption(
                f"HTTP status: `{result.get('http_status') if result.get('http_status') is not None else '—'}` · "
                f"Code: `{result.get('error_code') if result.get('error_code') is not None else '—'}` · "
                f"Subcode: `{result.get('error_subcode') if result.get('error_subcode') is not None else '—'}`"
            )
        if result.get("error_user_title"):
            st.caption(f"Title: {result['error_user_title']}")
        if result.get("error_user_msg"):
            st.write(f"Message: {result['error_user_msg']}")
        if result.get("fbtrace_id"):
            st.caption(f"fbtrace_id: `{result['fbtrace_id']}`")
        checks = dict(result.get("checks") or {})
        if checks:
            st.dataframe(
                [
                    {
                        "Read-back check": name.replace("_", " ").title(),
                        "Result": "PASS" if passed else "FAIL",
                    }
                    for name, passed in checks.items()
                ],
                hide_index=True,
                use_container_width=True,
            )


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
    st.caption("Create three route-specific Collection + Instant Experience ads safely in Meta.")
    _ensure_posting_run()
    st.session_state.setdefault(PROCESSING_KEY, False)
    st.session_state.setdefault(COLLECTION_DIAGNOSTIC_PROCESSING_KEY, False)
    st.session_state.setdefault(COLLECTION_TEMPLATE_COPY_PROCESSING_KEY, False)

    st.caption("**POSTING MODE**")
    st.segmented_control(
        "Posting mode",
        tuple(POSTING_MODE_LABELS.values()),
        default=POSTING_MODE_LABELS[POSTING_MODE_NEW],
        key=POSTING_MODE_KEY,
        label_visibility="collapsed",
        disabled=_current_run_state(st.session_state) != RUN_STATE_DRAFT,
    )
    posting_mode = _posting_mode(st.session_state)

    result = dict(st.session_state.get(RESULT_KEY) or {})
    if str(result.get("status") or "") == "COMPLETE":
        _render_success(result)
        _render_recent_posts()
        return
    if str(result.get("status") or "") == "ABANDONED_EXTERNALLY":
        st.error(
            str(
                result.get("safe_error")
                or "The Meta campaign for this Posting run no longer exists. "
                "Start a New Campaign to create a fresh set of ads."
            )
        )
        _render_object_result(result, title="Posting run abandoned externally")
        if st.button("Start fresh campaign", type="primary"):
            _start_new_posting_run()
            st.rerun()
        _render_recent_posts()
        return
    if str(result.get("status") or "") in {"FAILED", "AMBIGUOUS"}:
        st.warning(
            "This Posting run has Meta history. Retry the current run to reconcile it, "
            "or start fresh to create a new campaign without reusing these IDs."
        )
        if st.button("Start fresh campaign", type="secondary"):
            _start_new_posting_run()
            st.rerun()

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
    elif not overview.get("posting_ready"):
        _connection_status(status_col, str(overview.get("summary") or "Meta unavailable"), tone="warning")
        _render_connection_details(overview)
    elif references_ready:
        _connection_status(status_col, "Meta connected · ready", tone="success")
    else:
        _connection_status(status_col, "Meta connected · setup needs attention", tone="warning")
    warnings = tuple(str(value) for value in references.get("warnings") or () if str(value).strip())
    if warnings:
        st.caption("⚠ " + " · ".join(warnings[:3]))

    target_campaign_id = ""
    target_adset_id = ""
    target_campaign = {}
    target_adset = {}
    existing_targets_error = ""
    if posting_mode == POSTING_MODE_EXISTING:
        st.markdown("#### Existing Meta destination")
        refresh_existing = st.button(
            "Refresh Meta campaigns",
            type="secondary",
            disabled=st.session_state[PROCESSING_KEY],
            key=f"{STATE_PREFIX}refresh_existing_targets",
        )
        with st.spinner("Loading existing Meta campaigns and ad sets…"):
            existing_targets, existing_targets_error = _existing_targets_state(
                force=refresh_existing
            )
        if existing_targets_error:
            st.error(f"Existing Meta campaigns could not be loaded — {existing_targets_error}")
            existing_targets = {}
        campaigns = tuple(dict(row) for row in existing_targets.get("campaigns") or ())
        campaign_by_id = {
            str(row.get("id")): row for row in campaigns if row.get("id")
        }
        if str(st.session_state.get(EXISTING_CAMPAIGN_KEY) or "") not in campaign_by_id:
            st.session_state.pop(EXISTING_CAMPAIGN_KEY, None)
        target_campaign_id = st.selectbox(
            "Existing Campaign",
            tuple(campaign_by_id),
            index=None,
            placeholder="Select an ACTIVE or PAUSED Sales campaign",
            format_func=lambda value: str(campaign_by_id[value].get("name") or value),
            key=EXISTING_CAMPAIGN_KEY,
            disabled=not campaign_by_id,
        ) if campaign_by_id else ""
        target_campaign = dict(campaign_by_id.get(str(target_campaign_id)) or {})

        adsets = _adsets_for_campaign(existing_targets, target_campaign_id)
        adset_by_id = {str(row.get("id")): row for row in adsets if row.get("id")}
        if str(st.session_state.get(EXISTING_ADSET_KEY) or "") not in adset_by_id:
            st.session_state.pop(EXISTING_ADSET_KEY, None)
        target_adset_id = st.selectbox(
            "Existing Ad Set",
            tuple(adset_by_id),
            index=None,
            placeholder="Select an Ad Set in this Campaign",
            format_func=lambda value: str(adset_by_id[value].get("name") or value),
            key=EXISTING_ADSET_KEY,
            disabled=not adset_by_id,
        ) if adset_by_id else ""
        target_adset = dict(adset_by_id.get(str(target_adset_id)) or {})
        if target_campaign and target_adset:
            st.markdown(
                f"Campaign: **{html.escape(str(target_campaign.get('name') or ''))}**  \n"
                f"Campaign status: **{html.escape(str(target_campaign.get('status') or 'UNKNOWN'))}**  \n"
                f"Ad Set: **{html.escape(str(target_adset.get('name') or ''))}**  \n"
                f"Ad Set status: **{html.escape(str(target_adset.get('status') or 'UNKNOWN'))}**  \n"
                "New ads: **Will be created PAUSED**"
            )
            st.caption(
                f"Campaign ID: {target_campaign_id} · Ad Set ID: {target_adset_id}"
            )

    product_rows = _product_rows_state()
    product_records, record_by_identity = _product_selector_state(product_rows)
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
        if _current_run_state(st.session_state) == RUN_STATE_DRAFT:
            st.session_state.pop(COLLECTION_DIAGNOSTIC_RESULT_KEY, None)
            st.session_state.pop(COLLECTION_TEMPLATE_COPY_RESULT_KEY, None)
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

    if posting_mode == POSTING_MODE_EXISTING:
        st.text_input(
            "Audience",
            value="Inherited from the selected Ad Set",
            disabled=True,
        )
        st.caption("Audience and targeting will not be changed.")
        audience = {
            "key": "inherited",
            "type": "inherited",
            "label_type": "Inherited",
            "id": "",
            "name": "Inherited from existing Ad Set",
        }
    else:
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
    generated_campaign_name = (
        str(target_campaign.get("name") or target_campaign_id)
        if posting_mode == POSTING_MODE_EXISTING
        else campaign_name(product_title, country, sport) if product_title else ""
    )
    generated_adset_name = (
        str(target_adset.get("name") or target_adset_id)
        if posting_mode == POSTING_MODE_EXISTING
        else adset_name(country, sport, audience["name"])
    )
    generated_ad_names = (
        next_instant_experience_ad_names(product_title, existing_names, count=3)
        if product_title else ("", "", "")
    )
    product_set_label = str((product_set_by_id.get(product_set_id) or {}).get("name") or "Unresolved")
    account_currency = str((references.get("account") or {}).get("currency") or "account currency")

    existing_compatibility_error = ""
    if (
        posting_mode == POSTING_MODE_EXISTING
        and target_campaign
        and target_adset
        and dataset_id
        and product_set_id
    ):
        try:
            validate_existing_posting_target(
                campaign=target_campaign,
                adset=target_adset,
                expected_campaign_id=target_campaign_id,
                expected_adset_id=target_adset_id,
                expected_account_id=MetaPostingClient().ad_account_id,
                expected_catalog_id=catalog_id,
                expected_product_set_id=product_set_id,
                expected_pixel_id=dataset_id,
            )
        except PostingValidationError as error:
            existing_compatibility_error = str(error)
            st.error(existing_compatibility_error)

    st.subheader("Review")
    with st.container(border=True):
        if posting_mode == POSTING_MODE_EXISTING:
            st.markdown(
                f"Campaign: **{html.escape(generated_campaign_name or 'Select a Campaign')}**  \n"
                f"Ad set: **{html.escape(generated_adset_name or 'Select an Ad Set')}**  \n"
                "Structure: **Existing Campaign → Existing Ad Set → 3 New Ads**"
            )
            st.markdown(
                "**Existing settings:** Campaign and Ad Set statuses, budget, audience, "
                "targeting and optimization will not be changed."
            )
            st.caption(
                f"Purchase optimization · Existing audience · {country} package copy · "
                "Facebook + Instagram identities · Multi-advertiser ads On · Generate backgrounds Off"
            )
        else:
            st.markdown(
                f"Campaign: **{html.escape(generated_campaign_name or 'Waiting for product')}**  \n"
                f"Ad set: **{html.escape(generated_adset_name)}**  \n"
                "Structure: **1 New Campaign → 1 New Ad Set → 3 New Ads**"
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

    identities_ready = bool(
        references.get("page")
        and references.get("instagram")
        and overview.get("posting_ready")
    )
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
    ) and bool(
        posting_mode == POSTING_MODE_NEW
        or (
            target_campaign_id
            and target_adset_id
            and not existing_targets_error
            and not existing_compatibility_error
        )
    )

    if posting_mode == POSTING_MODE_EXISTING:
        st.info(
            "Sports Cave OS will add 3 PAUSED ads to:\n\n"
            f"{generated_campaign_name or 'Select a Campaign'}\n\n"
            f"{generated_adset_name or 'Select an Ad Set'}\n\n"
            "Existing live ads and settings will not be changed."
        )
        st.caption("Existing campaign budget will not be changed.")
        spinner_label = "Creating three paused ads in the selected existing Ad Set…"
    else:
        st.caption(
            "Creates one paused campaign, one paused ad set and three paused "
            "Instant Experience ads in Meta for review."
        )
        spinner_label = "Creating one paused campaign, one ad set and three ads…"

    if posting_mode == POSTING_MODE_EXISTING:
        create_clicked = st.button(
            "Add 3 Paused Ads to Existing Ad Set",
            type="primary",
            use_container_width=True,
            disabled=not ready or st.session_state[PROCESSING_KEY],
            key=f"{STATE_PREFIX}create",
        )
    else:
        create_clicked = st.button(
            "Create 3 Paused Meta Ads", type="primary", use_container_width=True,
            disabled=not ready or st.session_state[PROCESSING_KEY], key=f"{STATE_PREFIX}create",
        )

    if create_clicked:
        st.session_state[PROCESSING_KEY] = True
        st.session_state[RUN_STATE_KEY] = RUN_STATE_ACTIVE
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
            posting_mode=posting_mode,
            target_campaign_id=target_campaign_id,
            target_adset_id=target_adset_id,
        )
        try:
            with st.spinner(spinner_label):
                posted = MetaPostingService().create_paused_campaign(request)
        except (
            PostingValidationError,
            PostingBusyError,
            PostingAbandonedError,
            PostingAmbiguousError,
            PostingError,
        ) as error:
            st.error(str(error))
            partial = dict(getattr(error, "result", {}) or {})
            if partial:
                st.session_state[RESULT_KEY] = partial
                st.session_state[RUN_STATE_KEY] = str(
                    partial.get("status") or RUN_STATE_FAILED
                ).upper()
                _render_object_result(partial, title="Partial result — all created ad objects remain paused")
            elif isinstance(error, PostingValidationError):
                st.session_state[RUN_STATE_KEY] = RUN_STATE_DRAFT
            else:
                st.session_state[RUN_STATE_KEY] = RUN_STATE_FAILED
        else:
            st.session_state[RESULT_KEY] = dict(posted)
            st.session_state[RUN_STATE_KEY] = RUN_STATE_COMPLETE
            _load_recent_posts.clear()
            st.rerun()
        finally:
            st.session_state[PROCESSING_KEY] = False

    diagnostics_panel = st.expander("Advanced Meta Diagnostics", expanded=False)
    diagnostics_panel.markdown("#### Collection diagnostic")
    diagnostics_panel.caption("Uses Meta validate_only. Creates no campaign, ad set, creative or ad.")
    diagnostic_signature = _collection_validation_signature(
        submission_id=st.session_state[SUBMISSION_ID_KEY],
        product_title=product_title,
        product_set_id=product_set_id,
        product_url=product_url,
        primary_text=creative_inputs[0]["primary_text"],
        headline=creative_inputs[0]["headline"],
    )
    diagnostic_ready = bool(
        product_title
        and product_url
        and product_set_id
        and str(creative_inputs[0]["primary_text"] or "").strip()
        and str(creative_inputs[0]["headline"] or "").strip()
        and overview.get("posting_ready")
    )
    if diagnostics_panel.button(
        "Run Collection Validation — No Ads Created",
        type="secondary",
        use_container_width=True,
        disabled=(
            not diagnostic_ready
            or st.session_state[PROCESSING_KEY]
            or st.session_state[COLLECTION_DIAGNOSTIC_PROCESSING_KEY]
        ),
        key=f"{STATE_PREFIX}collection_diagnostic",
    ):
        st.session_state[COLLECTION_DIAGNOSTIC_PROCESSING_KEY] = True
        try:
            with st.spinner("Running Meta validate-only Collection tests…"):
                diagnostic = run_collection_validation_from_posting_state(
                    submission_id=st.session_state[SUBMISSION_ID_KEY],
                    product_title=product_title,
                    product_set_id=product_set_id,
                    product_url=product_url,
                    primary_text=creative_inputs[0]["primary_text"],
                    headline=creative_inputs[0]["headline"],
                )
        except (PostingValidationError, MetaCollectionDiagnosticSafetyError) as error:
            diagnostic = {
                "persistent_meta_writes": "NONE",
                "error": str(error),
            }
        except Exception:
            diagnostic = {
                "persistent_meta_writes": "NONE",
                "error": (
                    "Meta Collection validation could not run safely. No Meta objects "
                    "were created and the Posting ledger was not changed."
                ),
            }
        finally:
            st.session_state[COLLECTION_DIAGNOSTIC_PROCESSING_KEY] = False
        st.session_state[COLLECTION_DIAGNOSTIC_RESULT_KEY] = {
            "signature": diagnostic_signature,
            "result": diagnostic,
        }

    saved_diagnostic = dict(
        st.session_state.get(COLLECTION_DIAGNOSTIC_RESULT_KEY) or {}
    )
    if saved_diagnostic.get("signature") == diagnostic_signature:
        with diagnostics_panel:
            _render_collection_validation(saved_diagnostic.get("result"))

    diagnostics_panel.markdown("#### Real-write Collection diagnostic")
    diagnostics_panel.warning(
        "Creates exactly one real PAUSED ad by copying the configured Collection "
        "template into the existing failed-job Ad Set. It does not create a campaign, "
        "ad set, Instant Experience, Page photo, or additional route ads."
    )
    template_copy_attempted = bool(
        st.session_state.get(COLLECTION_TEMPLATE_COPY_ATTEMPTED_KEY)
    )
    if diagnostics_panel.button(
        "Create 1 Paused Template Copy",
        type="secondary",
        use_container_width=True,
        disabled=(
            not diagnostic_ready
            or st.session_state[PROCESSING_KEY]
            or st.session_state[COLLECTION_DIAGNOSTIC_PROCESSING_KEY]
            or st.session_state[COLLECTION_TEMPLATE_COPY_PROCESSING_KEY]
            or template_copy_attempted
        ),
        key=f"{STATE_PREFIX}collection_template_copy",
    ):
        # Lock the control before the network call. A Meta failure or ambiguous
        # response must never cause an automatic or accidental second copy.
        st.session_state[COLLECTION_TEMPLATE_COPY_ATTEMPTED_KEY] = {
            "signature": diagnostic_signature,
            "source_ad_id": configured_collection_template_ad_id(),
        }
        st.session_state[COLLECTION_TEMPLATE_COPY_PROCESSING_KEY] = True
        try:
            with st.spinner("Creating and verifying one paused Meta template copy…"):
                template_copy_result = run_collection_template_copy_from_posting_state(
                    submission_id=st.session_state[SUBMISSION_ID_KEY],
                    product_title=product_title,
                    product_set_id=product_set_id,
                    product_url=product_url,
                    primary_text=creative_inputs[0]["primary_text"],
                    headline=creative_inputs[0]["headline"],
                )
        except MetaCollectionTemplateCopyVerificationError as error:
            template_copy_result = dict(error.result or {})
            template_copy_result["status"] = "FAIL"
            template_copy_result["error"] = str(error)
        except MetaAdsApiError as error:
            template_copy_result = {
                "status": "FAIL",
                "persistent_meta_writes": "NONE CONFIRMED — REVIEW REQUIRED",
                **sanitized_template_copy_error(error),
            }
        except (PostingValidationError, MetaCollectionTemplateCopySafetyError) as error:
            template_copy_result = {
                "status": "FAIL",
                "persistent_meta_writes": "NONE",
                "error": str(error),
            }
        except Exception:
            template_copy_result = {
                "status": "FAIL",
                "persistent_meta_writes": "NONE CONFIRMED — REVIEW REQUIRED",
                "error": (
                    "The template-copy diagnostic could not confirm a safe result. "
                    "Do not retry until the source ad copies are reviewed in Meta."
                ),
            }
        finally:
            st.session_state[COLLECTION_TEMPLATE_COPY_PROCESSING_KEY] = False
        st.session_state[COLLECTION_TEMPLATE_COPY_RESULT_KEY] = {
            "signature": diagnostic_signature,
            "result": template_copy_result,
        }

    saved_template_copy = dict(
        st.session_state.get(COLLECTION_TEMPLATE_COPY_RESULT_KEY) or {}
    )
    if saved_template_copy.get("signature") == diagnostic_signature:
        with diagnostics_panel:
            _render_collection_template_copy(saved_template_copy.get("result"))
    elif template_copy_attempted:
        diagnostics_panel.caption(
            "A template-copy attempt has already been made in this Posting session. "
            "Further copies are blocked."
        )

    _render_recent_posts()
