from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
import uuid
from urllib.parse import quote, unquote, urlparse
from zoneinfo import ZoneInfo

from ads_image_workflow import AdsImageValidationError, prepare_meta_posting_image
from ads_meta_contract import META_AD_URL_PARAMETERS, META_DEFAULT_CTA
from meta_collection_template_copy import (
    MetaCollectionTemplateCopySafetyError,
    MetaCollectionTemplateCopyService,
    MetaCollectionTemplateCopyVerificationError,
    REQUIRED_COLLECTION_FEATURES,
    configured_collection_template_ad_id,
)
from meta_carousel_diagnostics import (
    MANUAL_CAROUSEL_ADSET_ID,
    MetaCarouselDiagnosticSafetyError,
    MetaCarouselValidateOnlyProbe,
    reference_carousel_image_hashes,
    validate_manual_carousel_reference_contract,
)
from meta_ads_client import (
    MetaAdsAmbiguousResultError,
    MetaAdsApiError,
    MetaPostingClient,
    is_optional_canvas_read_capability_error,
    sanitize_meta_error,
)


SUCCESS_MESSAGE = "3 Meta ads created successfully — PAUSED"
POSTING_PERMISSION = "ads_management"
EXPECTED_CATALOG_NAME = "Shopify Product Catalog"
EXPECTED_PIXEL_NAME = "Shprts Cave Pixel 2025"
CATALOG_ID_ENV_KEYS = ("META_CATALOG_ID",)
DATASET_ID_ENV_KEYS = ("META_PIXEL_ID", "META_DATASET_ID")
CAMPAIGN_OBJECTIVE = "OUTCOME_SALES"
CAMPAIGN_DAILY_BUDGET_MINOR = 2500
PRODUCT_DESCRIPTION = "Limited Edition"
INSTANT_EXPERIENCE_BUTTON_TEXT = "Claim Your Edition"
DYNAMIC_COLLECTION_RETAILER_ITEM_IDS = ("0", "0", "0", "0")
AD_TYPE = "Instant Experience"
CAROUSEL_AD_TYPE = "Carousel"
AD_TYPES = (AD_TYPE, CAROUSEL_AD_TYPE)
CAROUSEL_CARD_COUNT = 5
CAROUSEL_PRIMARY_TEXT_COUNT = 5
COUNTRY_META_CODES = {"AUS": "AU", "USA": "US", "UK": "GB", "CAN": "CA", "NZ": "NZ"}
SPORT_OPTIONS = (
    "NBA", "Motorsport", "Football", "Cricket", "Golf", "Horse Racing", "Baseball",
    "Combat", "Ice Hockey", "NFL", "Rugby Union", "Tennis", "Other",
)
POSTING_STATUSES = (
    "VALIDATING", "CAMPAIGN_CREATED", "ADSET_CREATED", "IMAGE_UPLOADED",
    "PAGE_PHOTO_CREATED", "INSTANT_EXPERIENCE_CREATED", "CREATIVE_CREATED",
    "AD_CREATED", "COMPLETE", "FAILED", "AMBIGUOUS", "ABANDONED_EXTERNALLY",
)

POSTING_MODE_NEW = "NEW"
POSTING_MODE_EXISTING = "EXISTING"
POSTING_MODES = (POSTING_MODE_NEW, POSTING_MODE_EXISTING)
CUSTOMER_LIFECYCLE_ALL_AUDIENCES = "ALL_AUDIENCES"
CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS = "ACQUIRE_NEW_CUSTOMERS"
CUSTOMER_LIFECYCLE_UNKNOWN = "UNKNOWN"
CUSTOMER_LIFECYCLE_STRATEGIES = (
    CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
    CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS,
)
CUSTOMER_LIFECYCLE_LABELS = {
    CUSTOMER_LIFECYCLE_ALL_AUDIENCES: "Get conversions from all audiences",
    CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS: "Acquire new customers",
    CUSTOMER_LIFECYCLE_UNKNOWN: "Unknown",
}
META_OBJECT_CREATED_BY_RUN = "CREATED_BY_RUN"
META_OBJECT_EXISTING_TARGET = "EXISTING_TARGET"
SELECTABLE_EXISTING_STATUSES = {"ACTIVE", "PAUSED"}
COMPATIBLE_EXISTING_CAMPAIGN_OBJECTIVES = {
    CAMPAIGN_OBJECTIVE,
    "PRODUCT_CATALOG_SALES",
}

EXTERNALLY_ABANDONED_MESSAGE = (
    "The Meta campaign for this Posting run no longer exists or is not accessible. "
    "Start a New Campaign to create a fresh set of ads."
)

EXISTING_TARGET_MISSING_MESSAGE = (
    "The selected Meta Campaign or Ad Set no longer exists or is not accessible. "
    "Choose another existing Ad Set or start a New Campaign."
)


def _configured_id(keys, *, environ=None):
    environ = os.environ if environ is None else environ
    for key in keys:
        value = str(environ.get(key, "") or "").strip()
        if value:
            return value
    return ""


def configured_catalog_id(*, environ=None):
    return _configured_id(CATALOG_ID_ENV_KEYS, environ=environ)


def configured_dataset_id(*, environ=None):
    return _configured_id(DATASET_ID_ENV_KEYS, environ=environ)


def _rows_by_id(rows):
    return {
        str(row.get("id") or "").strip(): dict(row)
        for row in rows or ()
        if str(row.get("id") or "").strip()
    }


def _resolution(*, entity, row=None, source="", error=""):
    row = dict(row or {})
    return {
        "resolved": bool(row.get("id")),
        "entity": entity,
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "source": str(source or ""),
        "error": str(error or ""),
    }


def resolve_catalog_reference(references, *, expected_id="", environ=None):
    references = dict(references or {})
    rows = _rows_by_id(references.get("catalogs") or ())
    configured_id = configured_catalog_id(environ=environ)
    required_id = str(configured_id or expected_id or "").strip()
    if required_id:
        if required_id in rows:
            return _resolution(
                entity="catalog",
                row=rows[required_id],
                source="configured_id" if configured_id else "selected_id",
            )
        fallback_ids = {
            str(value or "").strip()
            for value in references.get("catalog_fallback_ids") or ()
            if str(value or "").strip()
        }
        if required_id == configured_id or required_id in fallback_ids:
            return _resolution(
                entity="catalog",
                row={"id": required_id, "name": EXPECTED_CATALOG_NAME},
                source="configured_id" if required_id == configured_id else "existing_sales_campaign",
            )
        return _resolution(
            entity="catalog",
            error="The selected catalog could not be verified against configured or existing Sports Cave assets.",
        )

    exact = [
        row for row in rows.values()
        if str(row.get("name") or "").strip().casefold() == EXPECTED_CATALOG_NAME.casefold()
    ]
    if len(exact) == 1:
        return _resolution(entity="catalog", row=exact[0], source="exact_name")
    if len(exact) > 1:
        selected_id, conflicting = _catalog_id_from_current_campaign_evidence(
            references.get("catalog_campaign_evidence") or (),
            candidate_ids={str(row.get("id") or "") for row in exact},
        )
        if selected_id and selected_id in rows:
            return _resolution(
                entity="catalog",
                row=rows[selected_id],
                source="exact_name_current_sales_campaign",
            )
        if conflicting:
            return _resolution(
                entity="catalog",
                error=(
                    f"Multiple currently used Meta catalogs are named {EXPECTED_CATALOG_NAME}; "
                    "configure META_CATALOG_ID."
                ),
            )
        return _resolution(
            entity="catalog",
            error=f"Multiple Meta catalogs are named {EXPECTED_CATALOG_NAME}; configure META_CATALOG_ID.",
        )
    if len(rows) == 1:
        return _resolution(entity="catalog", row=next(iter(rows.values())), source="only_accessible_catalog")
    fallback_ids = sorted(
        {
            str(value or "").strip()
            for value in references.get("catalog_fallback_ids") or ()
            if str(value or "").strip()
        }
    )
    if len(fallback_ids) == 1:
        fallback_id = fallback_ids[0]
        return _resolution(
            entity="catalog",
            row=rows.get(fallback_id) or {"id": fallback_id, "name": EXPECTED_CATALOG_NAME},
            source="existing_sales_campaign",
        )
    if len(fallback_ids) > 1:
        return _resolution(
            entity="catalog",
            error="Existing Sports Cave Sales campaigns reference multiple catalog IDs; configure META_CATALOG_ID.",
        )
    return _resolution(
        entity="catalog",
        error="The Shopify Product Catalog could not be resolved from configured, accessible, or existing Sales assets.",
    )


def resolve_dataset_reference(references, *, environ=None):
    references = dict(references or {})
    rows = _rows_by_id(references.get("pixels") or ())
    configured_id = configured_dataset_id(environ=environ)
    if configured_id:
        return _resolution(
            entity="dataset",
            row=rows.get(configured_id) or {"id": configured_id, "name": EXPECTED_PIXEL_NAME},
            source="configured_id",
        )
    exact = [
        row for row in rows.values()
        if str(row.get("name") or "").strip().casefold() == EXPECTED_PIXEL_NAME.casefold()
    ]
    if len(exact) == 1:
        return _resolution(entity="dataset", row=exact[0], source="exact_name")
    if len(exact) > 1:
        return _resolution(
            entity="dataset",
            error=f"Multiple Meta datasets are named {EXPECTED_PIXEL_NAME}; configure META_PIXEL_ID or META_DATASET_ID.",
        )
    fallback_ids = sorted(
        {
            str(value or "").strip()
            for value in references.get("dataset_fallback_ids") or ()
            if str(value or "").strip()
        }
    )
    if len(fallback_ids) == 1:
        fallback_id = fallback_ids[0]
        return _resolution(
            entity="dataset",
            row=rows.get(fallback_id) or {"id": fallback_id, "name": EXPECTED_PIXEL_NAME},
            source="existing_purchase_adsets",
        )
    if len(fallback_ids) > 1:
        return _resolution(
            entity="dataset",
            error="Existing Sports Cave Purchase ad sets reference multiple Dataset/Pixel IDs; configure the intended ID.",
        )
    return _resolution(
        entity="dataset",
        error=f"The existing Dataset {EXPECTED_PIXEL_NAME} could not be resolved.",
    )


def catalog_ids_from_sales_campaigns(rows):
    ids = set()
    for row in rows or ():
        objective = str(row.get("objective") or "").strip().upper()
        promoted = dict(row.get("promoted_object") or {})
        catalog_id = str(promoted.get("product_catalog_id") or "").strip()
        if catalog_id and objective in {"OUTCOME_SALES", "PRODUCT_CATALOG_SALES", "CONVERSIONS"}:
            ids.add(catalog_id)
    return tuple(sorted(ids))


def _catalog_id_from_current_campaign_evidence(rows, *, candidate_ids):
    """Resolve duplicate named catalogs only from decisive current campaign evidence."""

    candidates = {str(value or "").strip() for value in candidate_ids if str(value or "").strip()}
    evidence = []
    for row in rows or ():
        objective = str(row.get("objective") or "").strip().upper()
        promoted = dict(row.get("promoted_object") or {})
        catalog_id = str(promoted.get("product_catalog_id") or "").strip()
        if catalog_id not in candidates or objective not in {
            "OUTCOME_SALES", "PRODUCT_CATALOG_SALES", "CONVERSIONS",
        }:
            continue
        evidence.append(
            {
                "catalog_id": catalog_id,
                "status": str(row.get("status") or "").strip().upper(),
                "effective_status": str(row.get("effective_status") or "").strip().upper(),
                "created_time": str(row.get("created_time") or ""),
                "updated_time": str(row.get("updated_time") or ""),
            }
        )
    active_ids = {
        row["catalog_id"]
        for row in evidence
        if "ACTIVE" in {row["status"], row["effective_status"]}
    }
    if len(active_ids) == 1:
        return next(iter(active_ids)), False
    if len(active_ids) > 1:
        return "", True

    newest_by_catalog = {}
    for row in evidence:
        timestamp = row["created_time"] or row["updated_time"]
        if timestamp > newest_by_catalog.get(row["catalog_id"], ""):
            newest_by_catalog[row["catalog_id"]] = timestamp
    if not newest_by_catalog:
        return "", False
    newest = max(newest_by_catalog.values())
    newest_ids = {
        catalog_id for catalog_id, timestamp in newest_by_catalog.items()
        if timestamp == newest and timestamp
    }
    if len(newest_ids) == 1:
        return next(iter(newest_ids)), False
    return "", len(newest_ids) > 1


def dataset_ids_from_purchase_adsets(rows):
    ids = set()
    for row in rows or ():
        promoted = dict(row.get("promoted_object") or {})
        event_type = str(promoted.get("custom_event_type") or "").strip().upper()
        campaign = dict(row.get("campaign") or {})
        objective = str(
            campaign.get("objective")
            or row.get("campaign_objective")
            or row.get("objective")
            or ""
        ).strip().upper()
        dataset_id = str(promoted.get("pixel_id") or promoted.get("dataset_id") or "").strip()
        if (
            dataset_id
            and event_type == "PURCHASE"
            and objective in {"OUTCOME_SALES", "PRODUCT_CATALOG_SALES", "CONVERSIONS"}
        ):
            ids.add(dataset_id)
    return tuple(sorted(ids))


def load_posting_reference_snapshot(
    client,
    *,
    include_existing_ad_names=True,
    expected_catalog_id="",
    environ=None,
):
    """Load reusable read-only Meta references once for a page/session refresh."""

    references = dict(client.reference_data() or {})
    warnings = list(references.get("warnings") or ())
    catalog_resolution = resolve_catalog_reference(
        references,
        expected_id=expected_catalog_id,
        environ=environ,
    )
    if not catalog_resolution.get("resolved"):
        loader = getattr(client, "reference_campaigns", None)
        try:
            campaigns = tuple(loader() or ()) if callable(loader) else ()
        except MetaAdsApiError:
            campaigns = ()
            warnings.append("Existing Sales campaigns were unavailable for catalog fallback discovery.")
        references["catalog_fallback_ids"] = catalog_ids_from_sales_campaigns(campaigns)
        references["catalog_campaign_evidence"] = campaigns
        catalog_resolution = resolve_catalog_reference(
            references,
            expected_id=expected_catalog_id,
            environ=environ,
        )

    dataset_resolution = resolve_dataset_reference(references, environ=environ)
    if not dataset_resolution.get("resolved"):
        loader = getattr(client, "reference_adsets", None)
        try:
            adsets = tuple(loader() or ()) if callable(loader) else ()
        except MetaAdsApiError:
            adsets = ()
            warnings.append("Existing Purchase ad sets were unavailable for Dataset fallback discovery.")
        references["dataset_fallback_ids"] = dataset_ids_from_purchase_adsets(adsets)
        dataset_resolution = resolve_dataset_reference(references, environ=environ)

    product_sets = ()
    catalog_id = str(catalog_resolution.get("id") or "")
    if catalog_id:
        try:
            product_sets = tuple(dict(row) for row in client.product_sets(catalog_id))
        except MetaAdsApiError:
            warnings.append("Product Sets are temporarily unavailable for the resolved catalog.")
    existing_ad_names = ()
    if include_existing_ad_names:
        try:
            existing_ad_names = tuple(client.existing_ad_names())
        except MetaAdsApiError:
            warnings.append("Existing ad names are unavailable; the definitive IA sequence will be checked at creation.")
    references.update(
        {
            "catalog_resolution": catalog_resolution,
            "dataset_resolution": dataset_resolution,
            "product_sets": product_sets,
            "existing_ad_names": existing_ad_names,
            "warnings": tuple(dict.fromkeys(str(value) for value in warnings if str(value).strip())),
        }
    )
    return references


def load_carousel_reference_snapshot(client, *, environ=None):
    """Load Carousel dependencies without catalogue or Product Set reads."""

    loader = getattr(client, "carousel_reference_data", None)
    references = dict(
        (loader() if callable(loader) else client.reference_data()) or {}
    )
    warnings = list(references.get("warnings") or ())
    dataset_resolution = resolve_dataset_reference(references, environ=environ)
    if not dataset_resolution.get("resolved"):
        fallback_loader = getattr(client, "reference_adsets", None)
        try:
            adsets = (
                tuple(fallback_loader() or ()) if callable(fallback_loader) else ()
            )
        except MetaAdsApiError:
            adsets = ()
            warnings.append(
                "Existing Purchase ad sets were unavailable for Dataset fallback discovery."
            )
        references["dataset_fallback_ids"] = dataset_ids_from_purchase_adsets(adsets)
        dataset_resolution = resolve_dataset_reference(references, environ=environ)
    references.update(
        {
            "catalog_resolution": {"resolved": False, "id": "", "name": ""},
            "dataset_resolution": dataset_resolution,
            "product_sets": (),
            "existing_ad_names": (),
            "warnings": tuple(
                dict.fromkeys(str(value) for value in warnings if str(value).strip())
            ),
        }
    )
    return references


def load_existing_posting_targets(client):
    """Load selectable Campaigns and Ad Sets from the configured account only.

    The account-level edges avoid one Ad Set request per Campaign. This helper
    is read-only and is cached by the Posting page only while Existing mode is
    visible.
    """

    campaigns = tuple(dict(row) for row in client.reference_campaigns() or ())
    adsets = tuple(dict(row) for row in client.reference_adsets() or ())
    return {
        "campaigns": tuple(
            row
            for row in campaigns
            if str(row.get("status") or "").strip().upper()
            in SELECTABLE_EXISTING_STATUSES
        ),
        "adsets": tuple(
            row
            for row in adsets
            if str(row.get("status") or "").strip().upper()
            in SELECTABLE_EXISTING_STATUSES
        ),
    }


def validate_existing_posting_target(
    *,
    campaign,
    adset,
    expected_campaign_id,
    expected_adset_id,
    expected_account_id,
    expected_catalog_id,
    expected_product_set_id,
    expected_pixel_id,
    allow_product_set_mismatch=False,
):
    """Fail closed unless an existing hierarchy matches the Posting contract."""

    campaign = dict(campaign or {})
    adset = dict(adset or {})
    campaign_id = str(expected_campaign_id or "").strip()
    adset_id = str(expected_adset_id or "").strip()
    if str(campaign.get("id") or "").strip() != campaign_id:
        raise PostingValidationError(EXISTING_TARGET_MISSING_MESSAGE)
    if str(adset.get("id") or "").strip() != adset_id:
        raise PostingValidationError(EXISTING_TARGET_MISSING_MESSAGE)
    if str(adset.get("campaign_id") or "").strip() != campaign_id:
        raise PostingValidationError(
            "The selected Ad Set does not belong to the selected Campaign. "
            "Choose a matching Ad Set."
        )

    account_id = normalize_account_id(expected_account_id)
    for entity, row in (("Campaign", campaign), ("Ad Set", adset)):
        row_account_id = normalize_account_id(row.get("account_id"))
        if not row_account_id or row_account_id != account_id:
            raise PostingValidationError(
                f"The selected Meta {entity} does not belong to the configured Sports Cave ad account."
            )
        status = str(
            row.get("configured_status") or row.get("status") or ""
        ).strip().upper()
        if status not in SELECTABLE_EXISTING_STATUSES:
            raise PostingValidationError(
                f"The selected Meta {entity} must be ACTIVE or PAUSED."
            )

    objective = str(campaign.get("objective") or "").strip().upper()
    if objective not in COMPATIBLE_EXISTING_CAMPAIGN_OBJECTIVES:
        raise PostingValidationError(
            "The selected Campaign is not a compatible Sales campaign. "
            "Choose a Sales Campaign or create a New Campaign."
        )
    campaign_promoted = dict(campaign.get("promoted_object") or {})
    campaign_catalog_id = str(
        campaign_promoted.get("product_catalog_id") or ""
    ).strip()
    if campaign_catalog_id and campaign_catalog_id != str(expected_catalog_id or ""):
        raise PostingValidationError(
            "The selected Campaign uses a different catalog. Choose a compatible "
            "Campaign or create a New Campaign."
        )

    optimization_goal = str(adset.get("optimization_goal") or "").strip().upper()
    if optimization_goal != "OFFSITE_CONVERSIONS":
        raise PostingValidationError(
            "The selected Ad Set is not configured for website Purchase conversions."
        )
    if str(adset.get("billing_event") or "").strip().upper() != "IMPRESSIONS":
        raise PostingValidationError(
            "The selected Ad Set uses an incompatible billing configuration."
        )
    destination_type = str(adset.get("destination_type") or "").strip().upper()
    if destination_type and destination_type != "WEBSITE":
        raise PostingValidationError(
            "The selected Ad Set does not use a compatible Website destination."
        )

    promoted = dict(adset.get("promoted_object") or {})
    event_type = str(promoted.get("custom_event_type") or "").strip().upper()
    if event_type != "PURCHASE":
        raise PostingValidationError(
            "The selected Ad Set is not configured for the Purchase conversion event."
        )
    pixel_id = str(promoted.get("pixel_id") or promoted.get("dataset_id") or "").strip()
    if not pixel_id or pixel_id != str(expected_pixel_id or "").strip():
        raise PostingValidationError(
            "The selected Ad Set uses a different Pixel/Dataset. Choose a compatible "
            "Ad Set or create a New Campaign."
        )
    product_set_id = normalize_meta_id(promoted.get("product_set_id"))
    product_set_compatible = bool(
        product_set_id
        and product_set_id == normalize_meta_id(expected_product_set_id)
    )
    if not product_set_compatible and not allow_product_set_mismatch:
        raise PostingValidationError(
            "This Ad Set uses a different Product Set. A compatible Ad Set is required "
            "for this Instant Experience."
        )

    return {
        "campaign": campaign,
        "adset": adset,
        "campaign_status": str(
            campaign.get("configured_status") or campaign.get("status") or ""
        ).upper(),
        "adset_status": str(
            adset.get("configured_status") or adset.get("status") or ""
        ).upper(),
        "product_set_compatible": product_set_compatible,
    }


def validate_existing_carousel_target(
    *,
    campaign,
    adset,
    expected_campaign_id,
    expected_adset_id,
    expected_account_id,
    expected_pixel_id,
):
    """Validate hierarchy/Purchase compatibility without changing the target.

    Product-Set Ad Sets are not guessed compatible here. Their final Carousel
    compatibility is decided by Meta's inline-Ad ``validate_only`` response
    before any persistent Meta write.
    """

    campaign = dict(campaign or {})
    adset = dict(adset or {})
    campaign_id = str(expected_campaign_id or "").strip()
    adset_id = str(expected_adset_id or "").strip()
    if str(campaign.get("id") or "").strip() != campaign_id:
        raise PostingValidationError(EXISTING_TARGET_MISSING_MESSAGE)
    if str(adset.get("id") or "").strip() != adset_id:
        raise PostingValidationError(EXISTING_TARGET_MISSING_MESSAGE)
    if str(adset.get("campaign_id") or "").strip() != campaign_id:
        raise PostingValidationError(
            "The selected Ad Set does not belong to the selected Campaign. "
            "Choose a matching Ad Set."
        )
    account_id = normalize_account_id(expected_account_id)
    for entity, row in (("Campaign", campaign), ("Ad Set", adset)):
        if normalize_account_id(row.get("account_id")) != account_id:
            raise PostingValidationError(
                f"The selected Meta {entity} does not belong to the configured Sports Cave ad account."
            )
        status = str(
            row.get("configured_status") or row.get("status") or ""
        ).strip().upper()
        if status not in SELECTABLE_EXISTING_STATUSES:
            raise PostingValidationError(
                f"The selected Meta {entity} must be ACTIVE or PAUSED."
            )
    if str(campaign.get("objective") or "").strip().upper() not in {
        CAMPAIGN_OBJECTIVE,
        "PRODUCT_CATALOG_SALES",
    }:
        raise PostingValidationError(
            "The selected Campaign is not a compatible Sales campaign. Choose a "
            "Sales Campaign or create a New Carousel Campaign."
        )
    if str(adset.get("optimization_goal") or "").strip().upper() != "OFFSITE_CONVERSIONS":
        raise PostingValidationError(
            "The selected Ad Set is not configured for website Purchase conversions."
        )
    if str(adset.get("billing_event") or "").strip().upper() != "IMPRESSIONS":
        raise PostingValidationError(
            "The selected Ad Set uses an incompatible billing configuration."
        )
    destination_type = str(adset.get("destination_type") or "").strip().upper()
    if destination_type and destination_type != "WEBSITE":
        raise PostingValidationError(
            "The selected Ad Set does not use a compatible Website destination."
        )
    promoted = dict(adset.get("promoted_object") or {})
    if str(promoted.get("custom_event_type") or "").strip().upper() != "PURCHASE":
        raise PostingValidationError(
            "The selected Ad Set is not configured for the Purchase conversion event."
        )
    pixel_id = str(promoted.get("pixel_id") or promoted.get("dataset_id") or "").strip()
    if not pixel_id or pixel_id != str(expected_pixel_id or "").strip():
        raise PostingValidationError(
            "The selected Ad Set uses a different Pixel/Dataset. Choose a compatible "
            "Ad Set or create a New Carousel Campaign."
        )
    return {
        "campaign": campaign,
        "adset": adset,
        "campaign_status": str(
            campaign.get("configured_status") or campaign.get("status") or ""
        ).upper(),
        "adset_status": str(
            adset.get("configured_status") or adset.get("status") or ""
        ).upper(),
        "has_product_set": bool(str(promoted.get("product_set_id") or "").strip()),
    }


def verify_new_carousel_adset_readback(
    adset,
    *,
    expected_adset_id,
    expected_campaign_id,
    expected_pixel_id,
):
    """Fail closed if Meta did not persist the verified non-catalogue Ad Set."""

    adset = dict(adset or {})
    promoted = dict(adset.get("promoted_object") or {})
    configured_status = str(
        adset.get("configured_status") or adset.get("status") or ""
    ).strip().upper()
    checks = {
        "adset_id": str(adset.get("id") or "") == str(expected_adset_id),
        "campaign_id": str(adset.get("campaign_id") or "")
        == str(expected_campaign_id),
        "configured_status_paused": configured_status == "PAUSED",
        "optimization_goal": str(adset.get("optimization_goal") or "").upper()
        == "OFFSITE_CONVERSIONS",
        "billing_event": str(adset.get("billing_event") or "").upper()
        == "IMPRESSIONS",
        "destination_type": str(adset.get("destination_type") or "").upper()
        == "WEBSITE",
        "pixel_id": str(
            promoted.get("pixel_id") or promoted.get("dataset_id") or ""
        )
        == str(expected_pixel_id),
        "purchase_event": str(promoted.get("custom_event_type") or "").upper()
        == "PURCHASE",
        "no_product_set": not str(promoted.get("product_set_id") or "").strip(),
        "smart_pse_disabled": promoted.get("smart_pse_enabled") is False,
        "dynamic_creative_disabled": adset.get("is_dynamic_creative") is False,
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return {"verified": not failed, "checks": checks, "failed_checks": failed}


class PostingError(RuntimeError):
    def __init__(self, message, *, result=None):
        super().__init__(message)
        self.result = dict(result or {})


class PostingValidationError(PostingError):
    pass


class PostingBusyError(PostingError):
    pass


class PostingAmbiguousError(PostingError):
    pass


class PostingAbandonedError(PostingError):
    """The durable run points at a Meta hierarchy that can no longer be resumed."""


def is_meta_object_missing_or_inaccessible(error):
    """Identify an unavailable persisted object without swallowing auth failures.

    This is deliberately used only while reading the campaign already recorded
    against the current Posting run. Token error 190 remains a normal hard error.
    """

    if not isinstance(error, MetaAdsApiError):
        return False
    if str(getattr(error, "error_code", "") or "") == "190":
        return False
    detail = " ".join(
        (
            str(error),
            str(getattr(error, "error_user_title", "") or ""),
            str(getattr(error, "error_user_msg", "") or ""),
        )
    ).casefold()
    return any(
        marker in detail
        for marker in (
            "unsupported get request",
            "does not exist",
            "object with id",
            "cannot be loaded",
            "could not be loaded",
            "not accessible",
            "not have permission to access",
            "missing permissions",
        )
    )


@dataclass(frozen=True)
class PostingCreative:
    image_bytes: bytes
    image_name: str
    primary_text: str
    headline: str
    description: str = ""


@dataclass(frozen=True)
class CarouselCard:
    image_bytes: bytes
    image_name: str
    headline: str
    description: str


@dataclass(frozen=True)
class PostingRequest:
    submission_id: str
    product_id: str
    product_title: str
    product_handle: str
    destination_url: str
    country: str
    sport: str
    catalog_id: str
    product_set_id: str
    creatives: tuple[PostingCreative, ...]
    audience_type: str = "broad"
    audience_id: str = ""
    customer_lifecycle_strategy: str = CUSTOMER_LIFECYCLE_ALL_AUDIENCES
    posting_mode: str = POSTING_MODE_NEW
    target_campaign_id: str = ""
    target_adset_id: str = ""
    create_new_adset_under_existing_campaign: bool = False
    ad_type: str = AD_TYPE
    carousel_cards: tuple[CarouselCard, ...] = ()
    carousel_primary_texts: tuple[str, ...] = ()


def normalize_account_id(value):
    return re.sub(r"^act_", "", str(value or "").strip(), flags=re.IGNORECASE)


def normalize_meta_id(value):
    """Canonicalize a Graph ID without treating a numeric representation as different."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def validate_destination_url(value):
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        raise PostingValidationError("The selected product does not have a valid https:// product URL.")
    return clean


def default_ad_name(destination_url, *, now=None):
    """Legacy helper retained for stable callers outside the V2 workflow."""
    clean_url = str(destination_url or "").strip()
    parts = [unquote(part).strip() for part in urlparse(clean_url).path.split("/") if part.strip()]
    handle = parts[-1] if parts else "product"
    handle = re.sub(r"[^a-zA-Z0-9-]+", "-", handle).strip("-").casefold() or "product"
    timestamp = now or datetime.now(ZoneInfo("Australia/Sydney"))
    return f"SC | {handle} | {timestamp.date().isoformat()}"


def product_short_name(title, *, max_length=58):
    value = re.sub(r"\s+", " ", str(title or "").strip())
    suffixes = (
        "sports wall art", "framed wall art", "framed art", "limited edition", "wall art",
        "art print", "poster print", "poster", "print",
    )
    changed = True
    while value and changed:
        changed = False
        for suffix in suffixes:
            trimmed = re.sub(
                rf"(?:\s*[-|–—:]\s*|\s+){re.escape(suffix)}\s*$",
                "", value, flags=re.IGNORECASE,
            ).strip(" -|–—:")
            if trimmed != value:
                value = trimmed
                changed = True
                break
    value = value or "Product"
    if len(value) <= max_length:
        return value
    shortened = value[: max_length + 1].rsplit(" ", 1)[0].rstrip(" -|–—:")
    return shortened or value[:max_length].rstrip()


def campaign_name(product_title, country, sport, *, now=None):
    if now is None:
        local_now = datetime.now(ZoneInfo("Australia/Sydney"))
    elif now.tzinfo is not None:
        local_now = now.astimezone(ZoneInfo("Australia/Sydney"))
    else:
        local_now = now.replace(tzinfo=ZoneInfo("Australia/Sydney"))
    return f"{local_now:%d%m%y} {country} {sport} {product_short_name(product_title)}"


def adset_name(country, sport, audience_name="Broad"):
    label = re.sub(r"\s+", " ", str(audience_name or "Broad").strip()) or "Broad"
    return f"{country} {sport} {label}"


def next_instant_experience_ad_name(product_title, existing_names=()):
    return next_instant_experience_ad_names(product_title, existing_names, count=1)[0]


def next_instant_experience_ad_names(product_title, existing_names=(), *, count=3):
    short = product_short_name(product_title)
    pattern = re.compile(rf"^{re.escape(short)}\s+IA\s+(\d+)$", re.IGNORECASE)
    sequence = [
        int(match.group(1)) for name in existing_names
        if (match := pattern.match(str(name or "").strip()))
    ]
    first = (max(sequence) if sequence else 0) + 1
    return tuple(f"{short} IA {number}" for number in range(first, first + int(count)))


def next_carousel_ad_name(product_title, existing_names=()):
    short = product_short_name(product_title)
    pattern = re.compile(rf"^{re.escape(short)}\s+Carousel\s+(\d+)$", re.IGNORECASE)
    sequence = [
        int(match.group(1)) for name in existing_names
        if (match := pattern.match(str(name or "").strip()))
    ]
    return f"{short} Carousel {(max(sequence) if sequence else 0) + 1}"


def posting_submission_id():
    return str(uuid.uuid4())


def ads_manager_url(*, account_id, campaign_id, adset_id, ad_id):
    account = normalize_account_id(account_id)
    return (
        "https://www.facebook.com/adsmanager/manage/ads"
        f"?act={account}&selected_campaign_ids={campaign_id}"
        f"&selected_adset_ids={adset_id}&selected_ad_ids={ad_id}"
    )


def _request_fingerprint(clean):
    payload = {
        key: clean[key]
        for key in (
            "product_id", "product_title", "destination_url", "country", "sport",
            "catalog_id", "product_set_id", "audience_type", "audience_id",
            "posting_mode", "target_campaign_id", "target_adset_id",
        )
    }
    # Preserve fingerprints for legacy/default All Audiences runs while making
    # any future non-default lifecycle selection part of mutation protection.
    lifecycle = str(clean.get("customer_lifecycle_strategy") or "").upper()
    if lifecycle not in ("", CUSTOMER_LIFECYCLE_ALL_AUDIENCES):
        payload["customer_lifecycle_strategy"] = lifecycle
    if clean.get("create_new_adset_under_existing_campaign"):
        payload["create_new_adset_under_existing_campaign"] = True
    ad_type = str(clean.get("ad_type") or AD_TYPE)
    # Preserve every existing Instant Experience fingerprint exactly. Ad type
    # becomes explicit only for the new, independent Carousel content contract.
    if ad_type == CAROUSEL_AD_TYPE:
        payload["ad_type"] = CAROUSEL_AD_TYPE
        payload["carousel_cards"] = [
            {
                "image_checksum": card["image_checksum"],
                "headline": card["headline"],
                "description": card["description"],
            }
            for card in clean["carousel_cards"]
        ]
        payload["carousel_primary_texts"] = list(clean["carousel_primary_texts"])
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    payload["creatives"] = [
        {
            "image_checksum": creative["image_checksum"],
            "primary_text": creative["primary_text"],
            "headline": creative["headline"],
            "description": creative["description"],
        }
        for creative in clean["creatives"]
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def posting_ad_results(value, *, ad_names=()):
    """Return three stable per-ad ledger entries, tolerating legacy/JSON rows."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            value = []
    existing = {}
    for row in value or ():
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index") or 0)
        except (TypeError, ValueError):
            continue
        if index in {1, 2, 3}:
            existing[index] = dict(row)
    names = tuple(str(name or "") for name in ad_names)
    results = []
    for index in range(1, 4):
        row = existing.get(index, {})
        row.setdefault("index", index)
        row.setdefault("ad_name", names[index - 1] if len(names) >= index else "")
        row.setdefault("instant_experience_name", f"{row['ad_name']} | Storefront" if row["ad_name"] else "")
        row.setdefault("status", "PENDING")
        row.setdefault("safe_error", "")
        for field in (
            "meta_image_hash", "meta_page_photo_id", "meta_canvas_photo_element_id",
            "meta_canvas_product_element_id", "meta_canvas_button_element_id",
            "meta_canvas_footer_element_id", "meta_instant_experience_id",
            "meta_creative_id", "meta_ad_id",
        ):
            row.setdefault(field, "")
        row.setdefault("meta_instant_experience_reused", False)
        row.setdefault("meta_ad_reused", False)
        row.setdefault("meta_ad_configured_status", "")
        row.setdefault("instant_experience_verification", {})
        row.setdefault("instant_experience_creation_provenance", {})
        row.setdefault("product_set_health", {})
        results.append(row)
    return results


def carousel_ad_result(value=None, *, ad_name=""):
    """Normalize the single-Ad Carousel ledger without invoking IA defaults."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            value = ()
    if isinstance(value, (list, tuple)):
        row = dict(value[0] or {}) if value else {}
    else:
        row = dict(value or {})
    row.setdefault("index", 1)
    row.setdefault("ad_type", CAROUSEL_AD_TYPE)
    row.setdefault("ad_name", str(ad_name or ""))
    row.setdefault("status", "PENDING")
    row.setdefault("safe_error", "")
    row.setdefault("carousel_image_hashes", [])
    row.setdefault("meta_creative_id", "")
    row.setdefault("meta_ad_id", "")
    row.setdefault("creative_ownership", META_OBJECT_CREATED_BY_RUN)
    row.setdefault("ad_ownership", META_OBJECT_CREATED_BY_RUN)
    row.setdefault("meta_ad_reused", False)
    row.setdefault("meta_ad_configured_status", "")
    row.setdefault("carousel_verification", {})
    return row


def _validate_posting_mode_fields(request):
    posting_mode = str(
        getattr(request, "posting_mode", POSTING_MODE_NEW) or POSTING_MODE_NEW
    ).strip().upper()
    if posting_mode not in POSTING_MODES:
        raise PostingValidationError("Select a valid Posting mode.")
    target_campaign_id = str(
        getattr(request, "target_campaign_id", "") or ""
    ).strip()
    target_adset_id = str(getattr(request, "target_adset_id", "") or "").strip()
    if posting_mode == POSTING_MODE_EXISTING:
        if not target_campaign_id:
            raise PostingValidationError("Select an existing Meta Campaign.")
        if not target_adset_id:
            raise PostingValidationError("Select an existing Meta Ad Set.")
        return posting_mode, target_campaign_id, target_adset_id, "inherited", "", ""
    if target_campaign_id or target_adset_id:
        raise PostingValidationError(
            "New Campaign mode cannot use Campaign or Ad Set IDs from another run."
        )
    audience_type = str(request.audience_type or "broad").strip().casefold()
    audience_id = str(request.audience_id or "").strip()
    lifecycle = str(
        getattr(
            request,
            "customer_lifecycle_strategy",
            CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
        )
        or CUSTOMER_LIFECYCLE_ALL_AUDIENCES
    ).strip().upper()
    if lifecycle not in CUSTOMER_LIFECYCLE_STRATEGIES:
        raise PostingValidationError("Select a valid Customer Lifecycle Strategy.")
    if lifecycle == CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS:
        raise PostingValidationError(
            "Acquire new customers is not available yet because Meta's complete "
            "existing-customer audience contract has not been verified. Choose "
            "Get conversions from all audiences."
        )
    if audience_type not in {"broad", "saved", "custom"}:
        raise PostingValidationError("Select a valid Meta audience.")
    if audience_type != "broad" and not audience_id:
        raise PostingValidationError("Select a saved or custom audience.")
    return (
        posting_mode,
        target_campaign_id,
        target_adset_id,
        audience_type,
        audience_id,
        lifecycle,
    )


def validate_carousel_posting_request(request):
    """Validate the isolated five-card, one-Ad website Carousel contract."""

    try:
        uuid.UUID(str(request.submission_id or ""))
    except (ValueError, TypeError, AttributeError) as error:
        raise PostingValidationError("Start a new Posting submission and try again.") from error
    product_title = str(request.product_title or "").strip()
    if not product_title:
        raise PostingValidationError("Select a product from Edition Ops.")
    destination_url = validate_destination_url(request.destination_url)
    raw_cards = tuple(getattr(request, "carousel_cards", ()) or ())
    if len(raw_cards) != CAROUSEL_CARD_COUNT:
        raise PostingValidationError("Provide exactly five complete Carousel cards.")
    cards = []
    for index, card in enumerate(raw_cards, start=1):
        if not bytes(card.image_bytes or b""):
            raise PostingValidationError(f"Upload Carousel Image {index}.")
        try:
            image = prepare_meta_posting_image(
                card.image_bytes, original_name=card.image_name
            )
        except AdsImageValidationError as error:
            raise PostingValidationError(f"Carousel Image {index}: {error}") from error
        headline = str(card.headline or "")
        description = str(card.description or "")
        if not headline.strip():
            raise PostingValidationError(f"Enter Card Headline {index}.")
        if not description.strip():
            raise PostingValidationError(f"Enter Card Description {index}.")
        cards.append(
            {
                "image": image,
                "image_checksum": str(image["source_hash"]),
                "headline": headline,
                "description": description,
            }
        )
    primary_texts = tuple(
        str(value or "")
        for value in (getattr(request, "carousel_primary_texts", ()) or ())
    )
    if len(primary_texts) != CAROUSEL_PRIMARY_TEXT_COUNT:
        raise PostingValidationError("Provide exactly five Primary Text variations.")
    for index, value in enumerate(primary_texts, start=1):
        if not value.strip():
            raise PostingValidationError(f"Enter Primary Text {index}.")
    if len(set(primary_texts)) != CAROUSEL_PRIMARY_TEXT_COUNT:
        raise PostingValidationError("Carousel Primary Text variations must remain distinct.")
    country = str(request.country or "").strip().upper()
    if country not in COUNTRY_META_CODES:
        raise PostingValidationError("Select a supported country.")
    sport = str(request.sport or "").strip()
    if sport not in SPORT_OPTIONS:
        raise PostingValidationError("Select a sport/category.")
    (
        posting_mode,
        target_campaign_id,
        target_adset_id,
        audience_type,
        audience_id,
        lifecycle,
    ) = _validate_posting_mode_fields(request)
    return {
        "ad_type": CAROUSEL_AD_TYPE,
        "product_id": str(request.product_id or "").strip(),
        "product_title": product_title,
        "product_handle": str(request.product_handle or "").strip(),
        "destination_url": destination_url,
        "creatives": (),
        "carousel_cards": tuple(cards),
        "carousel_primary_texts": primary_texts,
        "country": country,
        "sport": sport,
        "catalog_id": "",
        "product_set_id": "",
        "audience_type": audience_type,
        "audience_id": audience_id,
        "customer_lifecycle_strategy": lifecycle,
        "posting_mode": posting_mode,
        "target_campaign_id": target_campaign_id,
        "target_adset_id": target_adset_id,
    }


def validate_posting_request(request):
    if str(getattr(request, "ad_type", AD_TYPE) or AD_TYPE) == CAROUSEL_AD_TYPE:
        return validate_carousel_posting_request(request)
    try:
        uuid.UUID(str(request.submission_id or ""))
    except (ValueError, TypeError, AttributeError) as error:
        raise PostingValidationError("Start a new Posting submission and try again.") from error
    product_title = str(request.product_title or "").strip()
    if not product_title:
        raise PostingValidationError("Select a product from Edition Ops.")
    destination_url = validate_destination_url(request.destination_url)
    raw_creatives = tuple(request.creatives or ())
    if len(raw_creatives) != 3:
        raise PostingValidationError("Provide exactly three complete ads.")
    creatives = []
    for index, creative in enumerate(raw_creatives, start=1):
        if not bytes(creative.image_bytes or b""):
            raise PostingValidationError(f"Upload Image {index}.")
        try:
            image = prepare_meta_posting_image(
                creative.image_bytes, original_name=creative.image_name
            )
        except AdsImageValidationError as error:
            raise PostingValidationError(f"Image {index}: {error}") from error
        primary_text = str(creative.primary_text or "")
        headline = str(creative.headline or "")
        if not primary_text.strip():
            raise PostingValidationError(f"Enter Primary Text {index}.")
        if not headline.strip():
            raise PostingValidationError(f"Enter Headline {index}.")
        creatives.append(
            {
                "image": image,
                "image_checksum": str(image["source_hash"]),
                "primary_text": primary_text,
                "headline": headline,
                "description": str(creative.description or ""),
            }
        )
    country = str(request.country or "").strip().upper()
    if country not in COUNTRY_META_CODES:
        raise PostingValidationError("Select a supported country.")
    sport = str(request.sport or "").strip()
    if sport not in SPORT_OPTIONS:
        raise PostingValidationError("Select a sport/category.")
    catalog_id = str(request.catalog_id or "").strip()
    product_set_id = str(request.product_set_id or "").strip()
    if not catalog_id:
        raise PostingValidationError("Select the Shopify product catalog.")
    if not product_set_id:
        raise PostingValidationError("Select a Meta product set.")
    posting_mode = str(
        getattr(request, "posting_mode", POSTING_MODE_NEW) or POSTING_MODE_NEW
    ).strip().upper()
    if posting_mode not in POSTING_MODES:
        raise PostingValidationError("Select a valid Posting mode.")
    target_campaign_id = str(
        getattr(request, "target_campaign_id", "") or ""
    ).strip()
    target_adset_id = str(getattr(request, "target_adset_id", "") or "").strip()
    create_new_adset_under_existing_campaign = bool(
        getattr(request, "create_new_adset_under_existing_campaign", False)
    )
    if posting_mode == POSTING_MODE_EXISTING:
        if not target_campaign_id:
            raise PostingValidationError("Select an existing Meta Campaign.")
        if not target_adset_id:
            raise PostingValidationError("Select an existing Meta Ad Set.")
        audience_type = "inherited"
        audience_id = ""
        customer_lifecycle_strategy = ""
    else:
        if create_new_adset_under_existing_campaign:
            raise PostingValidationError(
                "A compatible Ad Set can only be created under an existing Campaign."
            )
        if target_campaign_id or target_adset_id:
            raise PostingValidationError(
                "New Campaign mode cannot use Campaign or Ad Set IDs from another run."
            )
        audience_type = str(request.audience_type or "broad").strip().casefold()
        audience_id = str(request.audience_id or "").strip()
        customer_lifecycle_strategy = str(
            getattr(
                request,
                "customer_lifecycle_strategy",
                CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
            )
            or CUSTOMER_LIFECYCLE_ALL_AUDIENCES
        ).strip().upper()
        if customer_lifecycle_strategy not in CUSTOMER_LIFECYCLE_STRATEGIES:
            raise PostingValidationError("Select a valid Customer Lifecycle Strategy.")
        if customer_lifecycle_strategy == CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS:
            raise PostingValidationError(
                "Acquire new customers is not available yet because Meta's complete "
                "existing-customer audience contract has not been verified. Choose "
                "Get conversions from all audiences."
            )
    if audience_type not in {"broad", "saved", "custom", "inherited"}:
        raise PostingValidationError("Select a valid Meta audience.")
    if audience_type != "broad" and not audience_id:
        if audience_type != "inherited":
            raise PostingValidationError("Select a saved or custom audience.")
    return {
        "ad_type": AD_TYPE,
        "product_id": str(request.product_id or "").strip(),
        "product_title": product_title,
        "product_handle": str(request.product_handle or "").strip(),
        "destination_url": destination_url,
        "creatives": tuple(creatives),
        "country": country,
        "sport": sport,
        "catalog_id": catalog_id,
        "product_set_id": product_set_id,
        "audience_type": audience_type,
        "audience_id": audience_id,
        "customer_lifecycle_strategy": customer_lifecycle_strategy,
        "posting_mode": posting_mode,
        "target_campaign_id": target_campaign_id,
        "target_adset_id": target_adset_id,
        "create_new_adset_under_existing_campaign": (
            create_new_adset_under_existing_campaign
        ),
    }


def build_campaign_payload(*, name, catalog_id):
    return {
        "name": str(name), "objective": CAMPAIGN_OBJECTIVE, "buying_type": "AUCTION",
        "status": "PAUSED", "special_ad_categories": [],
        "daily_budget": str(CAMPAIGN_DAILY_BUDGET_MINOR),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "promoted_object": {"product_catalog_id": str(catalog_id)},
    }


def build_carousel_campaign_payload(*, name):
    """Build the manual-reference Sales campaign without a catalogue binding."""

    return {
        "name": str(name),
        "objective": CAMPAIGN_OBJECTIVE,
        "buying_type": "AUCTION",
        "status": "PAUSED",
        "special_ad_categories": [],
        "daily_budget": str(CAMPAIGN_DAILY_BUDGET_MINOR),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }


_PLACEMENT_KEYS = {
    "publisher_platforms", "facebook_positions", "instagram_positions", "messenger_positions",
    "audience_network_positions", "device_platforms", "excluded_publisher_categories",
    "excluded_publisher_list_ids",
}


def build_targeting(*, country, audience_type="broad", audience=None):
    audience = dict(audience or {})
    if audience_type == "saved":
        targeting = deepcopy(audience.get("targeting") or {})
        for key in _PLACEMENT_KEYS:
            targeting.pop(key, None)
    else:
        targeting = {"age_min": 24, "age_max": 65}
        if audience_type == "custom":
            targeting["custom_audiences"] = [{"id": str(audience.get("id") or "")}]
    targeting["geo_locations"] = {"countries": [COUNTRY_META_CODES[str(country).upper()]]}
    targeting["targeting_automation"] = {"advantage_audience": 1}
    return targeting


def targeting_for_compatible_adset(source_adset, *, country):
    """Reuse the selected audience while retaining Advantage+ placements."""
    targeting = deepcopy(dict(source_adset or {}).get("targeting") or {})
    for key in _PLACEMENT_KEYS:
        targeting.pop(key, None)
    targeting["geo_locations"] = {
        "countries": [COUNTRY_META_CODES[str(country).upper()]]
    }
    targeting["targeting_automation"] = {"advantage_audience": 1}
    return targeting


def compatible_adset_name(source_adset, product_set):
    """Name a Product Set-specific sibling of the selected Ad Set."""
    source_name = str(dict(source_adset or {}).get("name") or "Instant Experience")
    product_set_label = str(
        dict(product_set or {}).get("name")
        or dict(product_set or {}).get("id")
        or "Compatible Product Set"
    )
    return f"{source_name} | {product_set_label}"


def build_adset_payload(
    *,
    name,
    campaign_id,
    product_set_id,
    pixel_id,
    targeting,
    customer_lifecycle_strategy=CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
    start_time=None,
):
    begins = start_time or datetime.now(timezone.utc)
    lifecycle = str(
        customer_lifecycle_strategy or CUSTOMER_LIFECYCLE_ALL_AUDIENCES
    ).strip().upper()
    if lifecycle != CUSTOMER_LIFECYCLE_ALL_AUDIENCES:
        raise PostingValidationError(
            "Acquire new customers cannot be sent until Meta's complete "
            "existing-customer audience contract is configured."
        )
    # Meta v26 exposes acquisition configuration through ad_set_goal and
    # existing_customer_budget_percentage, but its generated models expose no
    # documented ALL_AUDIENCES enum/value. The non-acquisition contract is
    # therefore deliberately explicit in Sports Cave state and deliberately
    # omitted from the Graph payload. Audience targeting and PURCHASE
    # optimisation remain unchanged.
    return {
        "name": str(name), "campaign_id": str(campaign_id), "status": "PAUSED",
        "billing_event": "IMPRESSIONS", "optimization_goal": "OFFSITE_CONVERSIONS",
        "destination_type": "WEBSITE",
        "promoted_object": {
            "pixel_id": str(pixel_id), "custom_event_type": "PURCHASE",
            "product_set_id": str(product_set_id),
        },
        "targeting": dict(targeting or {}),
        "start_time": begins.astimezone(timezone.utc).isoformat(timespec="seconds"),
    }


def build_carousel_adset_payload(
    *,
    name,
    campaign_id,
    pixel_id,
    targeting,
    customer_lifecycle_strategy=CUSTOMER_LIFECYCLE_ALL_AUDIENCES,
    start_time=None,
):
    """Build the standard website/Purchase Ad Set from the manual reference."""

    begins = start_time or datetime.now(timezone.utc)
    lifecycle = str(
        customer_lifecycle_strategy or CUSTOMER_LIFECYCLE_ALL_AUDIENCES
    ).strip().upper()
    if lifecycle != CUSTOMER_LIFECYCLE_ALL_AUDIENCES:
        raise PostingValidationError(
            "Acquire new customers cannot be sent until Meta's complete "
            "existing-customer audience contract is configured."
        )
    return {
        "name": str(name),
        "campaign_id": str(campaign_id),
        "status": "PAUSED",
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "OFFSITE_CONVERSIONS",
        "destination_type": "WEBSITE",
        "promoted_object": {
            "pixel_id": str(pixel_id),
            "custom_event_type": "PURCHASE",
            "smart_pse_enabled": False,
        },
        "is_dynamic_creative": False,
        "targeting": dict(targeting or {}),
        "start_time": begins.astimezone(timezone.utc).isoformat(timespec="seconds"),
    }


def classify_adset_customer_lifecycle(adset, *, acquisition_fields_requested=False):
    """Classify Graph lifecycle state without inventing undocumented goal values.

    Missing fields are only meaningful when the caller confirms that its Graph
    request explicitly requested both acquisition fields. This prevents a
    partial Ad Set dict from being misclassified as All Audiences.
    """

    adset = dict(adset or {})
    goal = adset.get("ad_set_goal")
    existing_customer_budget = adset.get("existing_customer_budget_percentage")
    if goal not in (None, "", {}) or existing_customer_budget not in (None, ""):
        return CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS
    fields_present = {
        "ad_set_goal",
        "existing_customer_budget_percentage",
    }.issubset(adset)
    # A valid Graph node plus an explicit request for both acquisition fields
    # makes their absence meaningful. An empty/partial mapping remains UNKNOWN.
    if fields_present or (acquisition_fields_requested and adset.get("id")):
        return CUSTOMER_LIFECYCLE_ALL_AUDIENCES
    return CUSTOMER_LIFECYCLE_UNKNOWN


def customer_lifecycle_verification(adset, *, acquisition_fields_requested=False):
    strategy = classify_adset_customer_lifecycle(
        adset,
        acquisition_fields_requested=acquisition_fields_requested,
    )
    if strategy == CUSTOMER_LIFECYCLE_ACQUIRE_NEW_CUSTOMERS:
        source = "Meta Graph returned acquisition-only Ad Set configuration"
    elif strategy == CUSTOMER_LIFECYCLE_ALL_AUDIENCES:
        source = "Meta Graph read-back returned no acquisition-only configuration"
    else:
        source = "Meta Graph lifecycle fields were not available in this read"
    return {
        "strategy": strategy,
        "label": CUSTOMER_LIFECYCLE_LABELS[strategy],
        "verification_source": source,
    }


def adset_uses_all_audiences(adset, *, acquisition_fields_requested=False):
    """Compatibility predicate backed by the explicit three-state classifier."""

    return classify_adset_customer_lifecycle(
        adset,
        acquisition_fields_requested=acquisition_fields_requested,
    ) == CUSTOMER_LIFECYCLE_ALL_AUDIENCES


def build_collection_creative_features_spec():
    """Build supported v26 Collection enhancements and artwork protections."""
    return {
        "creative_features_spec": {
            name: {"enroll_status": enrollment}
            for name, enrollment in REQUIRED_COLLECTION_FEATURES.items()
        }
    }


def build_storefront_element_specs(*, page_photo_id, product_set_id, destination_url, button_element_id=""):
    """Build the Storefront-equivalent Instant Experience component contract."""
    return {
        "canvas_photo": {"photo_id": str(page_photo_id), "style": "FIT_TO_WIDTH"},
        "canvas_product_set": {
            "product_set_id": str(product_set_id),
            "item_headline": "{{product.name}}",
            "item_description": PRODUCT_DESCRIPTION,
        },
        "canvas_button": {
            "rich_text": {"plain_text": INSTANT_EXPERIENCE_BUTTON_TEXT},
            "open_url_action": {"url": str(destination_url)},
        },
        "canvas_footer": {"child_elements": [str(button_element_id)] if button_element_id else []},
    }


def _walk_graph_values(value):
    """Yield every mapping in a nested Graph response."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_graph_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_graph_values(child)


def _decoded_element_payload(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return ()
    try:
        decoded = json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    return decoded if isinstance(decoded, (dict, list, tuple)) else ()


def _instant_experience_button_candidates(value, *, source):
    candidates = []
    for node in _walk_graph_values(value):
        action = node.get("open_url_action")
        rich_text = node.get("rich_text")
        action = dict(action) if isinstance(action, dict) else {}
        rich_text = dict(rich_text) if isinstance(rich_text, dict) else {}
        label = str(rich_text.get("plain_text") or node.get("label") or "")
        url = str(action.get("url") or "")
        if label or (rich_text and action):
            candidates.append({"label": label, "url": url, "source": source})
    return tuple(candidates)


def build_instant_experience_creation_provenance(
    *,
    submission_id,
    request_fingerprint,
    canvas_id,
    button_element_id,
    footer_element_id,
    destination_url,
):
    """Record the immutable inputs used to create one route's fixed IA button."""

    return {
        "contract": "sports_cave_storefront_fixed_button_v1",
        "submission_id": str(submission_id or ""),
        "request_fingerprint": str(request_fingerprint or ""),
        "instant_experience_id": str(canvas_id or ""),
        "button_element_id": str(button_element_id or ""),
        "footer_element_id": str(footer_element_id or ""),
        "button_label": INSTANT_EXPERIENCE_BUTTON_TEXT,
        "destination_url": str(destination_url or ""),
    }


def _creation_provenance_matches(
    provenance,
    *,
    expected_url,
    expected_canvas_id,
    expected_request_fingerprint,
    expected_submission_id,
):
    provenance = dict(provenance or {})
    return bool(
        str(provenance.get("contract") or "")
        == "sports_cave_storefront_fixed_button_v1"
        and str(provenance.get("submission_id") or "")
        == str(expected_submission_id or "")
        and str(provenance.get("request_fingerprint") or "")
        == str(expected_request_fingerprint or "")
        and str(provenance.get("instant_experience_id") or "")
        == str(expected_canvas_id or "")
        and str(provenance.get("button_element_id") or "")
        and str(provenance.get("footer_element_id") or "")
        and str(provenance.get("button_label") or "")
        == INSTANT_EXPERIENCE_BUTTON_TEXT
        and str(provenance.get("destination_url") or "") == expected_url
    )


def verify_instant_experience_destination(
    canvas,
    *,
    expected_url,
    child_elements=(),
    provenance=None,
    expected_canvas_id="",
    expected_request_fingerprint="",
    expected_submission_id="",
):
    """Classify Meta's IA destination evidence without treating omission as mismatch."""
    expected_url = validate_destination_url(expected_url)
    parsed = urlparse(expected_url)
    hostname = str(parsed.hostname or "").casefold()
    if (
        hostname == "fb.com"
        or hostname.endswith(".fb.com")
        or hostname == "facebook.com"
        or hostname.endswith(".facebook.com")
    ):
        raise PostingValidationError(
            "The Instant Experience button destination cannot be a Facebook URL."
        )
    sports_cave_hosts = ("sportscaveshop.com", "sportscave.com.au")
    if not any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in sports_cave_hosts
    ) or not str(parsed.path or "").startswith("/products/"):
        raise PostingValidationError(
            "The Instant Experience button destination must be a Sports Cave product URL."
        )

    canvas = dict(canvas or {})
    candidates = []
    for value in (
        canvas.get("body_elements") or (),
        canvas.get("fb_body_elements") or (),
        _decoded_element_payload(canvas.get("element_payload")),
    ):
        candidates.extend(
            _instant_experience_button_candidates(
                value, source="Meta element payload"
            )
        )
    candidates.extend(
        _instant_experience_button_candidates(
            tuple(child_elements or ()), source="Meta child element"
        )
    )

    exact = next(
        (
            row
            for row in candidates
            if row["label"] == INSTANT_EXPERIENCE_BUTTON_TEXT
            and row["url"] == expected_url
        ),
        None,
    )
    if exact:
        return {
            "verified": True,
            "verification_state": "VERIFIED",
            "display_status": "VERIFIED",
            "verification_source": exact["source"],
            "label": INSTANT_EXPERIENCE_BUTTON_TEXT,
            "url": expected_url,
            "reason": "Fixed button label and destination verified from Meta Graph.",
        }

    conflicts = tuple(
        row
        for row in candidates
        if (row["label"] and row["label"] != INSTANT_EXPERIENCE_BUTTON_TEXT)
        or (row["url"] and row["url"] != expected_url)
    )
    if conflicts:
        return {
            "verified": False,
            "verification_state": "MISMATCH",
            "display_status": "MISMATCH",
            "verification_source": conflicts[0]["source"],
            "label": "",
            "url": "",
            "reason": (
                "Meta returned a fixed button label or destination that does not "
                "match the current Posting product."
            ),
        }

    if _creation_provenance_matches(
        provenance,
        expected_url=expected_url,
        expected_canvas_id=expected_canvas_id,
        expected_request_fingerprint=expected_request_fingerprint,
        expected_submission_id=expected_submission_id,
    ):
        return {
            "verified": True,
            "verification_state": "VERIFIED",
            "display_status": "VERIFIED VIA CREATION RECORD",
            "verification_source": "Persisted creation provenance",
            "label": INSTANT_EXPERIENCE_BUTTON_TEXT,
            "url": expected_url,
            "reason": (
                "Meta omitted expanded child data; the exact persisted route creation "
                "record verifies the fixed button and destination."
            ),
        }

    return {
        "verified": False,
        "verification_state": "UNAVAILABLE",
        "display_status": "UNAVAILABLE",
        "verification_source": "",
        "label": "",
        "url": "",
        "reason": (
            "Meta did not expose enough expanded Canvas element data to compare the "
            "fixed button, and no exact persisted creation provenance was available."
        ),
    }


def assess_product_set_health(payload):
    """Summarise read-only catalogue eligibility without modifying products."""
    payload = dict(payload or {})
    product_set = dict(payload.get("product_set") or {})
    products = tuple(dict(row) for row in payload.get("products") or ())
    eligible = []
    reasons = {}
    reason_details = []
    available_values = {"in stock", "available for order", "preorder"}
    for product in products:
        availability = str(product.get("availability") or "").strip().casefold()
        status = str(product.get("status") or "").strip().upper()
        visibility = str(product.get("visibility") or "").strip().casefold()
        review_status = str(product.get("review_status") or "").strip().casefold()
        errors = product.get("errors") or product.get("invalidation_errors") or ()
        failures = []
        if not availability:
            failures.append("availability=unknown")
        elif availability not in available_values:
            failures.append(f"availability={availability}")
        if status and status != "PUBLISHED":
            failures.append(f"status={status}")
        if visibility and visibility != "published":
            failures.append(f"visibility={visibility}")
        if review_status and review_status != "approved":
            failures.append(f"review_status={review_status}")
        if errors:
            failures.append("catalogue_errors")
            error_rows = errors if isinstance(errors, (list, tuple)) else (errors,)
            for error in error_rows:
                if isinstance(error, dict):
                    detail = " — ".join(
                        str(error.get(field) or "").strip()
                        for field in ("code", "title", "message")
                        if str(error.get(field) or "").strip()
                    )
                else:
                    detail = str(error or "").strip()
                if detail:
                    reason_details.append(sanitize_meta_error(detail)[:300])
        if failures:
            for reason in failures:
                reasons[reason] = reasons.get(reason, 0) + 1
            product_label = str(
                product.get("retailer_id")
                or product.get("name")
                or product.get("id")
                or "Product"
            ).strip()
            reason_details.append(
                sanitize_meta_error(f"{product_label}: {', '.join(failures)}")[:300]
            )
        else:
            eligible.append(product)
    readable_count = len(products)
    reported_count = product_set.get("product_count")
    try:
        reported_count = int(reported_count)
    except (TypeError, ValueError):
        reported_count = readable_count
    ready = bool(eligible)
    message = (
        f"Meta reports {len(eligible)} eligible product(s) in this Product Set."
        if ready
        else (
            "Collection ad created successfully, but Meta reports no eligible catalogue "
            "products in the selected Product Set. Review Commerce Manager/catalogue feed "
            "before activation."
        )
    )
    return {
        "status": "READY" if ready else "WARNING",
        "product_set_id": str(product_set.get("id") or ""),
        "product_set_name": str(product_set.get("name") or ""),
        "reported_product_count": reported_count,
        "readable_product_count": readable_count,
        "eligible_product_count": len(eligible),
        "reason_counts": reasons,
        "reason_details": tuple(dict.fromkeys(reason_details))[:20],
        "message": message,
        "read_only": True,
    }


def is_optional_product_set_health_capability_error(error):
    """Classify code 3 only for the optional Product Set health read."""
    return isinstance(error, MetaAdsApiError) and str(error.error_code or "") == "3"


def build_collection_creative_payload(
    *, name, page_id, instagram_user_id, image_hash, canvas_id, product_set_id,
    destination_url, primary_text, headline, description="", url_tags=META_AD_URL_PARAMETERS,
):
    instant_experience_url = (
        "https://fb.com/canvas_doc/"
        f"{quote(str(canvas_id), safe='')}"
    )
    link_data = {
        "link": instant_experience_url,
        "message": str(primary_text), "name": str(headline),
        "image_hash": str(image_hash),
        "call_to_action": {"type": META_DEFAULT_CTA},
        "retailer_item_ids": list(DYNAMIC_COLLECTION_RETAILER_ITEM_IDS),
    }
    return {
        "name": str(name),
        "object_story_spec": {
            "page_id": str(page_id), "instagram_user_id": str(instagram_user_id),
            "link_data": link_data,
        },
        "product_set_id": str(product_set_id),
        "image_hash": str(image_hash),
        "contextual_multi_ads": {"enroll_status": "OPT_IN"},
        "degrees_of_freedom_spec": build_collection_creative_features_spec(),
        "url_tags": str(url_tags or ""),
    }


def build_carousel_creative_payload(
    *,
    name,
    page_id,
    instagram_user_id,
    cards,
    primary_texts,
    destination_url,
    url_tags=META_AD_URL_PARAMETERS,
):
    """Build one non-catalogue, five-card Meta v26 Carousel creative."""

    clean_cards = tuple(dict(card or {}) for card in cards or ())
    clean_primary_texts = tuple(str(value or "") for value in primary_texts or ())
    if len(clean_cards) != CAROUSEL_CARD_COUNT:
        raise PostingValidationError("Carousel creative requires exactly five cards.")
    if len(clean_primary_texts) != CAROUSEL_PRIMARY_TEXT_COUNT:
        raise PostingValidationError(
            "Carousel creative requires exactly five Primary Text variations."
        )
    child_attachments = []
    for index, card in enumerate(clean_cards, start=1):
        image_hash = str(card.get("image_hash") or "").strip()
        headline = str(card.get("headline") or "")
        description = str(card.get("description") or "")
        if not image_hash or not headline.strip() or not description.strip():
            raise PostingValidationError(f"Carousel Card {index} is incomplete.")
        child_attachments.append(
            {
                "link": str(destination_url),
                "image_hash": image_hash,
                "name": headline,
                "description": description,
                "call_to_action": {"type": META_DEFAULT_CTA},
            }
        )
    return {
        "name": str(name),
        "object_story_spec": {
            "page_id": str(page_id),
            "instagram_user_id": str(instagram_user_id),
            "link_data": {
                "link": str(destination_url),
                "call_to_action": {"type": META_DEFAULT_CTA},
                "child_attachments": child_attachments,
                "multi_share_end_card": True,
                "multi_share_optimized": True,
            },
        },
        "asset_feed_spec": {
            "bodies": [{"text": value} for value in clean_primary_texts],
            "optimization_type": "DEGREES_OF_FREEDOM",
        },
        "contextual_multi_ads": {"enroll_status": "OPT_IN"},
        "degrees_of_freedom_spec": {
            "creative_features_spec": {
                "advantage_plus_creative": {"enroll_status": "OPT_IN"},
                "carousel_to_video": {"enroll_status": "OPT_IN"},
                "description_automation": {"enroll_status": "OPT_IN"},
                "enhance_cta": {"enroll_status": "OPT_IN"},
                "image_touchups": {"enroll_status": "OPT_IN"},
                "inline_comment": {"enroll_status": "OPT_IN"},
                "media_order": {"enroll_status": "OPT_IN"},
                "profile_card": {"enroll_status": "OPT_IN"},
            }
        },
        "url_tags": str(url_tags or ""),
    }


def verify_carousel_creative_readback(
    creative,
    *,
    page_id,
    instagram_user_id,
    cards,
    primary_texts,
    destination_url,
):
    """Verify exact ordered cards and exposed text variations after creation."""

    creative = dict(creative or {})
    story = dict(creative.get("object_story_spec") or {})
    link_data = dict(story.get("link_data") or {})
    actual_cards = tuple(
        dict(row or {}) for row in link_data.get("child_attachments") or ()
    )
    expected_cards = tuple(dict(row or {}) for row in cards or ())
    checks = {
        "page_id": str(story.get("page_id") or "") == str(page_id),
        "instagram_user_id": str(story.get("instagram_user_id") or "")
        == str(instagram_user_id),
        "five_cards": len(actual_cards) == len(expected_cards) == CAROUSEL_CARD_COUNT,
        "multi_share_end_card": link_data.get("multi_share_end_card") is True,
        "multi_share_optimized": link_data.get("multi_share_optimized") is True,
    }
    for index, (actual, expected) in enumerate(
        zip(actual_cards, expected_cards), start=1
    ):
        checks[f"card_{index}_image_hash"] = str(actual.get("image_hash") or "") == str(
            expected.get("image_hash") or ""
        )
        checks[f"card_{index}_link"] = str(actual.get("link") or "") == str(
            destination_url
        )
        checks[f"card_{index}_headline"] = str(actual.get("name") or "") == str(
            expected.get("headline") or ""
        )
        checks[f"card_{index}_description"] = str(
            actual.get("description") or ""
        ) == str(expected.get("description") or "")
        checks[f"card_{index}_cta"] = str(
            (actual.get("call_to_action") or {}).get("type") or ""
        ).upper() == META_DEFAULT_CTA
    feed_exposed = "asset_feed_spec" in creative
    if feed_exposed:
        feed = dict(creative.get("asset_feed_spec") or {})
        actual_texts = tuple(
            str(dict(row or {}).get("text") or "") for row in feed.get("bodies") or ()
        )
        checks["primary_text_variations"] = actual_texts == tuple(primary_texts or ())
        checks["optimization_type"] = str(
            feed.get("optimization_type") or ""
        ).upper() == "DEGREES_OF_FREEDOM"
    failed = tuple(name for name, passed in checks.items() if not passed)
    return {
        "verified": not failed,
        "checks": checks,
        "failed_checks": failed,
        "card_count": len(actual_cards),
        "primary_text_variations_exposed": feed_exposed,
    }


class SupabasePostingStore:
    """Persistent lease ledger keyed by one intentional Posting run UUID.

    ``submission_id`` is the campaign-run identity. ``request_fingerprint`` is
    content evidence only and must never select another historical run.
    """

    def _backend(self):
        import supabase_backend
        return supabase_backend

    def claim(self, request_data, *, lease_token):
        backend = self._backend()
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                target_submission_id = str(request_data["submission_id"])
                columns = (
                    "submission_id", "request_fingerprint", "status", "ad_type", "product_id",
                    "product_title", "product_handle", "country", "sport", "catalog_id",
                    "catalog_name", "product_set_id", "product_set_name", "audience_type",
                    "audience_id", "audience_name", "requested_lifecycle_strategy",
                    "verified_lifecycle_strategy", "lifecycle_verification_source",
                    "pixel_id", "pixel_name", "account_currency", "campaign_name",
                    "adset_name", "ad_name", "destination_url", "image_checksum",
                    "posting_mode", "campaign_ownership", "adset_ownership",
                    "campaign_id", "adset_id", "campaign_configured_status",
                    "adset_configured_status",
                    "ad_results",
                )
                placeholders = ["%s::uuid", *(["%s"] * (len(columns) - 1))]
                values = tuple(
                    "VALIDATING"
                    if column == "status"
                    else json.dumps(request_data.get(column) or [])
                    if column == "ad_results"
                    else CUSTOMER_LIFECYCLE_UNKNOWN
                    if column == "verified_lifecycle_strategy"
                    and not request_data.get(column)
                    else ""
                    if column == "lifecycle_verification_source"
                    and request_data.get(column) is None
                    else request_data.get(column)
                    for column in columns
                )
                placeholders[-1] = "%s::jsonb"
                cur.execute(
                    f"INSERT INTO meta_posting_submissions({', '.join(columns)}) "
                    f"VALUES ({', '.join(placeholders)}) ON CONFLICT (submission_id) DO NOTHING",
                    values,
                )
                cur.execute(
                    "SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid",
                    (target_submission_id,),
                )
                existing = dict(cur.fetchone() or {})
                if str(existing.get("request_fingerprint") or "") != request_data["request_fingerprint"]:
                    raise PostingValidationError(
                        "This Posting run changed after Meta creation began. Retry it unchanged "
                        "or choose Start fresh campaign to create a new run."
                    )
                if str(existing.get("status") or "") in {
                    "COMPLETE", "AMBIGUOUS", "ABANDONED_EXTERNALLY",
                }:
                    conn.commit()
                    return {"claimed": False, "record": existing}
                cur.execute(
                    """
                    UPDATE meta_posting_submissions
                    SET lease_token=%s::uuid, lease_expires_at=now() + interval '2 minutes',
                        updated_at=now(), safe_error=NULL
                    WHERE submission_id=%s::uuid
                      AND (lease_expires_at IS NULL OR lease_expires_at < now())
                    RETURNING *
                    """,
                    (lease_token, target_submission_id),
                )
                claimed = dict(cur.fetchone() or {})
                if not claimed:
                    cur.execute(
                        "SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid",
                        (target_submission_id,),
                    )
                    existing = dict(cur.fetchone() or {})
                conn.commit()
                return {"claimed": bool(claimed), "record": claimed or existing}

    def update_stage(self, submission_id, status, **fields):
        if status not in POSTING_STATUSES:
            raise ValueError("Unknown Posting status.")
        allowed = {
            "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_name",
            "campaign_ownership", "adset_ownership", "campaign_configured_status",
            "adset_configured_status",
            "requested_lifecycle_strategy", "verified_lifecycle_strategy",
            "lifecycle_verification_source",
            "meta_image_hash", "meta_page_photo_id", "meta_canvas_photo_element_id",
            "meta_canvas_product_element_id", "meta_canvas_button_element_id",
            "meta_canvas_footer_element_id", "meta_instant_experience_id",
            "meta_creative_id", "meta_ad_id", "meta_status", "safe_error",
            "ad_results",
        }
        values = {key: fields[key] for key in fields if key in allowed}
        assignments = ["status=%s", "updated_at=now()"]
        params = [status]
        for key, value in values.items():
            if key == "ad_results":
                assignments.append("ad_results=%s::jsonb")
                params.append(json.dumps(value or []))
            else:
                assignments.append(f"{key}=%s")
                params.append(value)
        if status in {"COMPLETE", "FAILED", "AMBIGUOUS", "ABANDONED_EXTERNALLY"}:
            assignments.extend(["lease_token=NULL", "lease_expires_at=NULL"])
        if status == "COMPLETE":
            assignments.append("completed_at=now()")
        params.append(str(submission_id))
        backend = self._backend()
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE meta_posting_submissions SET {', '.join(assignments)} "
                    "WHERE submission_id=%s::uuid RETURNING *",
                    tuple(params),
                )
                row = dict(cur.fetchone() or {})
            conn.commit()
        return row

    def recent(self, limit=20):
        backend = self._backend()
        if not backend.is_configured():
            return []
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT submission_id, created_at, completed_at, status, product_title,
                           country, sport, campaign_id, campaign_name, adset_id, adset_name,
                           ad_name, meta_instant_experience_id, meta_ad_id, meta_creative_id,
                           meta_status, safe_error, ad_results, posting_mode,
                           ad_type,
                           campaign_ownership, adset_ownership,
                           campaign_configured_status, adset_configured_status,
                           requested_lifecycle_strategy, verified_lifecycle_strategy,
                           lifecycle_verification_source
                    FROM meta_posting_submissions ORDER BY created_at DESC LIMIT %s
                    """,
                    (max(1, min(int(limit or 20), 100)),),
                )
                return [dict(row) for row in cur.fetchall()]

    def failed_collection_diagnostic_job(
        self, *, submission_id="", product_title="", product_set_id=""
    ):
        """Resolve one failed Posting job without changing the durable ledger."""
        clean_product_title = str(product_title or "").strip()
        clean_product_set_id = str(product_set_id or "").strip()
        if not clean_product_title or not clean_product_set_id:
            raise PostingValidationError(
                "Select the Posting product and Product Set before running validation."
            )
        backend = self._backend()
        if not backend.is_configured():
            raise PostingValidationError(
                "The failed Posting job ledger is unavailable in this environment."
            )
        # Deliberately do not call ensure_ads_schema() here.  This diagnostic
        # lookup is SELECT-only and must never migrate or mutate the ledger.
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT submission_id, created_at, updated_at, status,
                           product_title, product_set_id, destination_url,
                           campaign_id, campaign_name, adset_id, adset_name,
                           ad_name, meta_image_hash, meta_instant_experience_id,
                           ad_results
                    FROM meta_posting_submissions
                    WHERE status='FAILED'
                      AND product_title=%s
                      AND product_set_id=%s
                      AND created_at >= now() - interval '7 days'
                    ORDER BY updated_at DESC
                    LIMIT 3
                    """,
                    (clean_product_title, clean_product_set_id),
                )
                candidates = [dict(row) for row in cur.fetchall()]
        clean_submission_id = str(submission_id or "").strip()
        exact = [
            row for row in candidates
            if clean_submission_id
            and str(row.get("submission_id") or "") == clean_submission_id
        ]
        if len(exact) == 1:
            return exact[0]
        if len(candidates) != 1:
            raise PostingValidationError(
                "Meta Collection validation requires exactly one failed Posting job "
                "for the selected product and Product Set. Review Posting history first."
            )
        return candidates[0]


class MetaPostingService:
    def __init__(
        self,
        *,
        client=None,
        store=None,
        url_tags=META_AD_URL_PARAMETERS,
        template_copy_service=None,
        progress_callback=None,
        clock=None,
        carousel_validator=None,
    ):
        self.client = client or MetaPostingClient()
        self.store = store or SupabasePostingStore()
        self.url_tags = str(url_tags or "")
        self._progress_callback = progress_callback
        self._clock = clock or time.perf_counter
        self._performance_started = None
        self._performance_last = None
        self._performance_trace = []
        self._carousel_validator = carousel_validator
        self.template_copy_service = (
            template_copy_service or MetaCollectionTemplateCopyService(self.client)
        )

    def _start_performance_trace(self):
        now = float(self._clock())
        self._performance_started = now
        self._performance_last = now
        self._performance_trace = []

    def _checkpoint(self, stage):
        now = float(self._clock())
        previous = self._performance_last
        started = self._performance_started
        if previous is None or started is None:
            self._start_performance_trace()
            now = float(self._clock())
            previous = self._performance_last
            started = self._performance_started
        self._performance_trace.append(
            {
                "stage": str(stage or ""),
                "duration_ms": round(max(0.0, now - float(previous)) * 1000, 3),
                "elapsed_ms": round(max(0.0, now - float(started)) * 1000, 3),
            }
        )
        self._performance_last = now

    def _progress(self, message):
        callback = self._progress_callback
        if not callable(callback):
            return
        try:
            callback(str(message or ""))
        except Exception:
            # Progress is presentation-only and must never change Posting safety.
            return

    @staticmethod
    def _one(rows, *, entity, expected_id="", expected_name=""):
        candidates = [dict(row) for row in rows]
        if expected_id:
            candidates = [row for row in candidates if str(row.get("id") or "") == expected_id]
        if expected_name:
            candidates = [
                row for row in candidates
                if str(row.get("name") or "").strip().casefold() == expected_name.casefold()
            ]
        if len(candidates) != 1:
            raise PostingValidationError(
                f"Meta must expose exactly one valid {entity}; found {len(candidates)}."
            )
        return candidates[0]

    def _validate_references(self, clean):
        try:
            permissions = set(self.client.permissions())
        except MetaAdsApiError:
            permissions = None
        if permissions is not None and POSTING_PERMISSION not in permissions:
            raise PostingValidationError("Meta posting permission is unavailable.")
        if not str(self.client.page_id or "").strip():
            raise PostingValidationError("Sports Cave Facebook Page identity is not configured.")
        if not str(getattr(self.client, "page_access_token", "") or "").strip():
            raise PostingValidationError("META_PAGE_ACCESS_TOKEN is not configured.")
        if not str(self.client.instagram_actor_id or "").strip():
            raise PostingValidationError("Sports Cave Instagram identity is not configured.")
        try:
            page_auth = dict(self.client.validate_page_auth() or {})
        except MetaAdsApiError as error:
            raise PostingValidationError(sanitize_meta_error(error)) from error
        if (
            not page_auth.get("ready")
            or str(page_auth.get("page_id") or "") != str(self.client.page_id)
        ):
            raise PostingValidationError(
                "The configured Facebook Page token could not be validated for this Page."
            )
        references = load_posting_reference_snapshot(
            self.client,
            include_existing_ad_names=False,
            expected_catalog_id=clean["catalog_id"],
        )
        page = dict(references.get("page") or {})
        instagram = dict(references.get("instagram") or {})
        if str(page.get("id") or "") != str(self.client.page_id):
            raise PostingValidationError("The configured Sports Cave Facebook Page could not be validated.")
        if str(instagram.get("id") or "") != str(self.client.instagram_actor_id):
            raise PostingValidationError("The configured Sports Cave Instagram identity could not be validated.")
        catalog_resolution = dict(references.get("catalog_resolution") or {})
        if (
            not catalog_resolution.get("resolved")
            or str(catalog_resolution.get("id") or "") != clean["catalog_id"]
        ):
            raise PostingValidationError(
                str(catalog_resolution.get("error") or "The selected Shopify catalog could not be validated.")
            )
        catalog = {
            "id": clean["catalog_id"],
            "name": str(catalog_resolution.get("name") or EXPECTED_CATALOG_NAME),
        }
        product_set = self._one(
            references.get("product_sets") or (), entity="product set",
            expected_id=clean["product_set_id"],
        )
        product_catalog = dict(product_set.get("product_catalog") or {})
        if product_catalog.get("id") and str(product_catalog.get("id")) != clean["catalog_id"]:
            raise PostingValidationError(
                "The selected product set no longer belongs to the Shopify catalog."
            )
        dataset_resolution = dict(references.get("dataset_resolution") or {})
        if not dataset_resolution.get("resolved"):
            raise PostingValidationError(
                str(dataset_resolution.get("error") or f"The Dataset {EXPECTED_PIXEL_NAME} could not be validated.")
            )
        pixel = {
            "id": str(dataset_resolution.get("id") or ""),
            "name": str(dataset_resolution.get("name") or EXPECTED_PIXEL_NAME),
        }
        audience = {"id": "", "name": "Broad", "targeting": {}}
        if clean["audience_type"] == "saved":
            audience = self._one(
                references.get("saved_audiences") or (), entity="saved audience",
                expected_id=clean["audience_id"],
            )
        elif clean["audience_type"] == "custom":
            audience = self._one(
                references.get("custom_audiences") or (), entity="custom audience",
                expected_id=clean["audience_id"],
            )
        return references, catalog, product_set, pixel, audience

    def _validate_carousel_references(self, clean):
        try:
            permissions = set(self.client.permissions())
        except MetaAdsApiError:
            permissions = None
        if permissions is not None and POSTING_PERMISSION not in permissions:
            raise PostingValidationError("Meta posting permission is unavailable.")
        if not str(self.client.page_id or "").strip():
            raise PostingValidationError(
                "Sports Cave Facebook Page identity is not configured."
            )
        if not str(self.client.instagram_actor_id or "").strip():
            raise PostingValidationError(
                "Sports Cave Instagram identity is not configured."
            )
        references = load_carousel_reference_snapshot(self.client)
        page = dict(references.get("page") or {})
        instagram = dict(references.get("instagram") or {})
        if str(page.get("id") or "") != str(self.client.page_id):
            raise PostingValidationError(
                "The configured Sports Cave Facebook Page could not be validated."
            )
        if str(instagram.get("id") or "") != str(self.client.instagram_actor_id):
            raise PostingValidationError(
                "The configured Sports Cave Instagram identity could not be validated."
            )
        dataset_resolution = dict(references.get("dataset_resolution") or {})
        if not dataset_resolution.get("resolved"):
            raise PostingValidationError(
                str(
                    dataset_resolution.get("error")
                    or f"The Dataset {EXPECTED_PIXEL_NAME} could not be validated."
                )
            )
        pixel = {
            "id": str(dataset_resolution.get("id") or ""),
            "name": str(dataset_resolution.get("name") or EXPECTED_PIXEL_NAME),
        }
        audience = {"id": "", "name": "Broad", "targeting": {}}
        if clean["audience_type"] == "saved":
            audience = self._one(
                references.get("saved_audiences") or (),
                entity="saved audience",
                expected_id=clean["audience_id"],
            )
        elif clean["audience_type"] == "custom":
            audience = self._one(
                references.get("custom_audiences") or (),
                entity="custom audience",
                expected_id=clean["audience_id"],
            )
        return references, pixel, audience

    def _validate_carousel_contract(self, *, clean, ad_name, adset_id):
        """Require current Graph reference evidence plus two validate-only passes."""

        reference = dict(self.client.carousel_reference_contract() or {})
        reference_evidence = validate_manual_carousel_reference_contract(
            reference,
            expected_page_id=self.client.page_id,
            expected_instagram_user_id=self.client.instagram_user_id,
        )
        reference_hashes = reference_carousel_image_hashes(reference)
        validation_cards = tuple(
            {
                "image_hash": image_hash,
                "headline": card["headline"],
                "description": card["description"],
            }
            for card, image_hash in zip(clean["carousel_cards"], reference_hashes)
        )
        creative_payload = build_carousel_creative_payload(
            name=f"{ad_name} | Carousel validate-only",
            page_id=self.client.page_id,
            instagram_user_id=self.client.instagram_user_id,
            cards=validation_cards,
            primary_texts=clean["carousel_primary_texts"],
            destination_url=clean["destination_url"],
            url_tags=self.url_tags,
        )
        probe = self._carousel_validator
        if probe is None:
            probe = MetaCarouselValidateOnlyProbe(self.client.config)
        result = dict(
            probe.run(
                ad_name=f"{ad_name} validate-only",
                adset_id=str(adset_id),
                creative_payload=creative_payload,
            )
            or {}
        )
        result["reference"] = reference_evidence
        if not result.get("validated"):
            inline = dict(result.get("inline_ad") or {})
            standalone = dict(result.get("standalone_creative") or {})
            failure = inline if not inline.get("validated") else standalone
            code = failure.get("error_code")
            subcode = failure.get("error_subcode")
            meta_suffix = ""
            if code not in (None, ""):
                meta_suffix += f" Meta code {code}"
            if subcode not in (None, ""):
                meta_suffix += f", subcode {subcode}"
            if clean["posting_mode"] == POSTING_MODE_EXISTING:
                raise PostingValidationError(
                    "This Ad Set is not compatible with a standard Carousel. "
                    "Choose another Ad Set or create a New Carousel Campaign."
                    + (meta_suffix + "." if meta_suffix else "")
                )
            raise PostingValidationError(
                "Meta v26 did not validate the Sports Cave Carousel creative and "
                "PAUSED Ad contract. No persistent Meta objects were created."
                + (meta_suffix + "." if meta_suffix else "")
            )
        return result

    def _ambiguous(self, submission_id, message, *, record=None):
        safe_error = sanitize_meta_error(message)
        result = self.store.update_stage(submission_id, "AMBIGUOUS", safe_error=safe_error)
        raise PostingAmbiguousError(safe_error, result=result or record)

    @staticmethod
    def _configured_status(row):
        return str(row.get("configured_status") or row.get("status") or "").upper()

    def _create_or_reconcile(self, create, reconcile=None, *, submission_id, entity):
        try:
            return str(create() or "")
        except MetaAdsAmbiguousResultError as error:
            matches = ()
            if reconcile is not None:
                try:
                    matches = tuple(reconcile() or ())
                except MetaAdsApiError:
                    matches = ()
            if len(matches) == 1 and matches[0].get("id"):
                return str(matches[0]["id"])
            self._ambiguous(
                submission_id,
                f"Meta did not confirm the {entity}, and a unique matching object could not be reconciled. {error}",
            )

    @staticmethod
    def _one_match(row):
        return (row,) if row else ()

    def _existing_target_for_run(
        self,
        *,
        clean,
        pixel,
        submission_id,
        ad_results,
        record,
        allow_product_set_mismatch=False,
    ):
        """Read and validate an external target before any route Meta writes."""

        campaign_id = str(record.get("campaign_id") or clean["target_campaign_id"])
        adset_id = str(record.get("adset_id") or clean["target_adset_id"])
        try:
            campaign = dict(self.client.configured_campaign(campaign_id) or {})
            adset = dict(self.client.configured_adset(adset_id) or {})
        except MetaAdsApiError as error:
            if not is_meta_object_missing_or_inaccessible(error):
                raise
            abandoned = self.store.update_stage(
                submission_id,
                "ABANDONED_EXTERNALLY",
                safe_error=EXISTING_TARGET_MISSING_MESSAGE,
                ad_results=ad_results,
            )
            raise PostingAbandonedError(
                EXISTING_TARGET_MISSING_MESSAGE,
                result=abandoned or record,
            ) from error
        try:
            return validate_existing_posting_target(
                campaign=campaign,
                adset=adset,
                expected_campaign_id=campaign_id,
                expected_adset_id=adset_id,
                expected_account_id=self.client.ad_account_id,
                expected_catalog_id=clean["catalog_id"],
                expected_product_set_id=clean["product_set_id"],
                expected_pixel_id=pixel["id"],
                allow_product_set_mismatch=allow_product_set_mismatch,
            )
        except PostingValidationError as error:
            failed = self.store.update_stage(
                submission_id,
                "FAILED",
                safe_error=str(error),
                ad_results=ad_results,
            )
            raise PostingValidationError(str(error), result=failed or record) from error

    def create_paused_carousel_campaign(self, request):
        """Create exactly one PAUSED, non-catalogue, five-card Carousel Ad."""

        self._start_performance_trace()
        self._progress("Preparing Meta carousel…")
        clean = validate_carousel_posting_request(request)
        self._checkpoint("request_validation")
        try:
            references, pixel, audience = self._validate_carousel_references(clean)
            existing_ad_names = tuple(self.client.existing_ad_names())
        except MetaAdsApiError as error:
            raise PostingError(sanitize_meta_error(error)) from error
        self._checkpoint("meta_reference_validation")
        posting_mode = clean["posting_mode"]
        is_existing_mode = posting_mode == POSTING_MODE_EXISTING
        campaign_label = (
            clean["target_campaign_id"]
            if is_existing_mode
            else campaign_name(clean["product_title"], clean["country"], clean["sport"])
        )
        audience_label = (
            "Inherited from existing Ad Set"
            if is_existing_mode
            else str(audience.get("name") or "Broad")
        )
        adset_label = (
            clean["target_adset_id"]
            if is_existing_mode
            else adset_name(clean["country"], clean["sport"], audience_label)
        )
        proposed_ad_name = next_carousel_ad_name(
            clean["product_title"], existing_ad_names
        )
        initial_ad_result = carousel_ad_result(ad_name=proposed_ad_name)
        fingerprint = _request_fingerprint(clean)
        submission_id = str(request.submission_id)
        claim = self.store.claim(
            {
                "submission_id": submission_id,
                "request_fingerprint": fingerprint,
                "ad_type": CAROUSEL_AD_TYPE,
                "product_id": clean["product_id"],
                "product_title": clean["product_title"],
                "product_handle": clean["product_handle"],
                "country": clean["country"],
                "sport": clean["sport"],
                "catalog_id": "",
                "catalog_name": "",
                "product_set_id": "",
                "product_set_name": "",
                "audience_type": clean["audience_type"],
                "audience_id": str(audience.get("id") or ""),
                "audience_name": audience_label,
                "requested_lifecycle_strategy": (
                    clean["customer_lifecycle_strategy"] if not is_existing_mode else None
                ),
                "verified_lifecycle_strategy": CUSTOMER_LIFECYCLE_UNKNOWN,
                "lifecycle_verification_source": "",
                "pixel_id": str(pixel.get("id") or ""),
                "pixel_name": str(pixel.get("name") or ""),
                "account_currency": str(
                    (references.get("account") or {}).get("currency") or ""
                ),
                "campaign_name": campaign_label,
                "adset_name": adset_label,
                "ad_name": proposed_ad_name,
                "ad_results": [initial_ad_result],
                "destination_url": clean["destination_url"],
                "posting_mode": posting_mode,
                "campaign_ownership": (
                    META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                "adset_ownership": (
                    META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                "campaign_id": clean["target_campaign_id"] if is_existing_mode else None,
                "adset_id": clean["target_adset_id"] if is_existing_mode else None,
                "campaign_configured_status": "",
                "adset_configured_status": "",
                "image_checksum": ",".join(
                    card["image_checksum"] for card in clean["carousel_cards"]
                ),
            },
            lease_token=str(uuid.uuid4()),
        )
        self._checkpoint("ledger_claim")
        record = dict(claim.get("record") or {})
        submission_id = str(record.get("submission_id") or submission_id)
        if str(record.get("ad_type") or AD_TYPE) != CAROUSEL_AD_TYPE:
            raise PostingValidationError(
                "This Posting run belongs to a different Ad Type. Start a new run."
            )
        if str(record.get("posting_mode") or POSTING_MODE_NEW).upper() != posting_mode:
            raise PostingValidationError(
                "This Posting run belongs to a different Posting mode. Start a new run."
            )
        if is_existing_mode and (
            str(record.get("campaign_id") or "") != clean["target_campaign_id"]
            or str(record.get("adset_id") or "") != clean["target_adset_id"]
        ):
            raise PostingValidationError(
                "This Carousel run does not own the selected existing Meta target. "
                "Start a new run and select it again."
            )
        if not claim.get("claimed"):
            status = str(record.get("status") or "")
            if status == "COMPLETE":
                record["performance_trace"] = tuple(self._performance_trace)
                return record
            if status == "AMBIGUOUS":
                raise PostingAmbiguousError(
                    str(record.get("safe_error") or "Meta did not confirm the earlier result."),
                    result=record,
                )
            if status == "ABANDONED_EXTERNALLY":
                raise PostingAbandonedError(
                    str(record.get("safe_error") or EXTERNALLY_ABANDONED_MESSAGE),
                    result=record,
                )
            raise PostingBusyError(
                "This Carousel is already being created. Wait for the current request to finish.",
                result=record,
            )

        campaign_label = str(record.get("campaign_name") or campaign_label)
        adset_label = str(record.get("adset_name") or adset_label)
        ad_result = carousel_ad_result(
            record.get("ad_results"),
            ad_name=str(record.get("ad_name") or proposed_ad_name),
        )
        try:
            campaign_id = str(record.get("campaign_id") or "")
            adset_id = str(record.get("adset_id") or "")
            configured_campaign = None
            configured_adset = None
            target = None
            if is_existing_mode:
                try:
                    configured_campaign = dict(
                        self.client.configured_campaign(clean["target_campaign_id"]) or {}
                    )
                    carousel_adset_reader = getattr(
                        self.client,
                        "configured_carousel_adset",
                        self.client.configured_adset,
                    )
                    configured_adset = dict(
                        carousel_adset_reader(clean["target_adset_id"]) or {}
                    )
                except MetaAdsApiError as error:
                    if not is_meta_object_missing_or_inaccessible(error):
                        raise
                    abandoned = self.store.update_stage(
                        submission_id,
                        "ABANDONED_EXTERNALLY",
                        safe_error=EXISTING_TARGET_MISSING_MESSAGE,
                        ad_results=[ad_result],
                    )
                    raise PostingAbandonedError(
                        EXISTING_TARGET_MISSING_MESSAGE,
                        result=abandoned or record,
                    ) from error
                target = validate_existing_carousel_target(
                    campaign=configured_campaign,
                    adset=configured_adset,
                    expected_campaign_id=clean["target_campaign_id"],
                    expected_adset_id=clean["target_adset_id"],
                    expected_account_id=self.client.ad_account_id,
                    expected_pixel_id=pixel["id"],
                )
                campaign_id = clean["target_campaign_id"]
                adset_id = clean["target_adset_id"]
                campaign_label = str(configured_campaign.get("name") or campaign_id)
                adset_label = str(configured_adset.get("name") or adset_id)

            validation_target_adset_id = (
                adset_id if is_existing_mode else MANUAL_CAROUSEL_ADSET_ID
            )
            self._progress("Validating Meta carousel contract…")
            carousel_validation = self._validate_carousel_contract(
                clean=clean,
                ad_name=ad_result["ad_name"],
                adset_id=validation_target_adset_id,
            )
            ad_result["validate_only"] = carousel_validation
            record = self.store.update_stage(
                submission_id,
                "VALIDATING",
                ad_results=[ad_result],
            )
            self._checkpoint("carousel_validate_only")

            if not is_existing_mode:
                self._progress("Creating campaign…")
                if campaign_id:
                    try:
                        configured_campaign = dict(
                            self.client.configured_campaign(campaign_id) or {}
                        )
                    except MetaAdsApiError as error:
                        if not is_meta_object_missing_or_inaccessible(error):
                            raise
                        abandoned = self.store.update_stage(
                            submission_id,
                            "ABANDONED_EXTERNALLY",
                            safe_error=EXTERNALLY_ABANDONED_MESSAGE,
                            ad_results=[ad_result],
                        )
                        raise PostingAbandonedError(
                            EXTERNALLY_ABANDONED_MESSAGE,
                            result=abandoned or record,
                        ) from error
                else:
                    campaign_id = self._create_or_reconcile(
                        lambda: self.client.create_campaign(
                            build_carousel_campaign_payload(name=campaign_label)
                        ),
                        submission_id=submission_id,
                        entity="campaign",
                    )
                    record = self.store.update_stage(
                        submission_id,
                        "CAMPAIGN_CREATED",
                        campaign_id=campaign_id,
                        campaign_name=campaign_label,
                    )
            self._checkpoint("campaign_resolution")

            if not is_existing_mode:
                self._progress("Creating Ad Set…")
                if not adset_id:
                    targeting = build_targeting(
                        country=clean["country"],
                        audience_type=clean["audience_type"],
                        audience=audience,
                    )
                    adset_id = self._create_or_reconcile(
                        lambda: self.client.create_adset(
                            build_carousel_adset_payload(
                                name=adset_label,
                                campaign_id=campaign_id,
                                pixel_id=pixel["id"],
                                targeting=targeting,
                                customer_lifecycle_strategy=clean[
                                    "customer_lifecycle_strategy"
                                ],
                            )
                        ),
                        lambda: self.client.find_adsets_by_name(
                            campaign_id, adset_label
                        ),
                        submission_id=submission_id,
                        entity="ad set",
                    )
                    record = self.store.update_stage(
                        submission_id,
                        "ADSET_CREATED",
                        adset_id=adset_id,
                        adset_name=adset_label,
                    )
                carousel_adset_reader = getattr(
                    self.client,
                    "configured_carousel_adset",
                    self.client.configured_adset,
                )
                configured_adset = dict(carousel_adset_reader(adset_id) or {})
                adset_verification = verify_new_carousel_adset_readback(
                    configured_adset,
                    expected_adset_id=adset_id,
                    expected_campaign_id=campaign_id,
                    expected_pixel_id=pixel["id"],
                )
                ad_result["carousel_adset_verification"] = adset_verification
                if not adset_verification["verified"]:
                    self._ambiguous(
                        submission_id,
                        "Meta did not confirm the new paused, non-catalogue Carousel "
                        "Ad Set. Failed checks: "
                        + ", ".join(adset_verification["failed_checks"])
                        + ". No Carousel Ad was created.",
                        record=record,
                    )
                lifecycle_verification = customer_lifecycle_verification(
                    configured_adset,
                    acquisition_fields_requested=True,
                )
                record = self.store.update_stage(
                    submission_id,
                    "ADSET_CREATED",
                    requested_lifecycle_strategy=clean[
                        "customer_lifecycle_strategy"
                    ],
                    verified_lifecycle_strategy=lifecycle_verification["strategy"],
                    lifecycle_verification_source=lifecycle_verification[
                        "verification_source"
                    ],
                    ad_results=[ad_result],
                )
                if (
                    lifecycle_verification["strategy"]
                    != clean["customer_lifecycle_strategy"]
                ):
                    self._ambiguous(
                        submission_id,
                        "Meta did not confirm 'Get conversions from all audiences' "
                        "for the new paused Carousel Ad Set. No Carousel Ad was created.",
                        record=record,
                    )
            else:
                lifecycle_verification = customer_lifecycle_verification(
                    configured_adset,
                    acquisition_fields_requested=True,
                )
                record = self.store.update_stage(
                    submission_id,
                    "ADSET_CREATED",
                    campaign_id=campaign_id,
                    campaign_name=campaign_label,
                    adset_id=adset_id,
                    adset_name=adset_label,
                    campaign_ownership=META_OBJECT_EXISTING_TARGET,
                    adset_ownership=META_OBJECT_EXISTING_TARGET,
                    campaign_configured_status=target["campaign_status"],
                    adset_configured_status=target["adset_status"],
                    verified_lifecycle_strategy=lifecycle_verification["strategy"],
                    lifecycle_verification_source=lifecycle_verification[
                        "verification_source"
                    ],
                    ad_results=[ad_result],
                )
            self._checkpoint("adset_resolution")

            self._progress("Uploading 5 carousel images…")
            image_hashes = list(ad_result.get("carousel_image_hashes") or ())
            if len(image_hashes) > CAROUSEL_CARD_COUNT:
                raise PostingValidationError(
                    "The persisted Carousel image state is invalid. Start a new run."
                )
            for card in clean["carousel_cards"][len(image_hashes) :]:
                image = card["image"]
                image_hashes.append(
                    self.client.upload_image(
                        image["data"],
                        filename=image["upload_name"],
                        content_type=image["content_type"],
                    )
                )
                ad_result["carousel_image_hashes"] = list(image_hashes)
                ad_result["status"] = "IMAGE_UPLOADED"
                record = self.store.update_stage(
                    submission_id,
                    "IMAGE_UPLOADED",
                    meta_image_hash=image_hashes[0],
                    ad_results=[ad_result],
                )
            actual_cards = tuple(
                {
                    "image_hash": image_hash,
                    "headline": card["headline"],
                    "description": card["description"],
                }
                for card, image_hash in zip(clean["carousel_cards"], image_hashes)
            )
            creative_name = (
                f"{ad_result['ad_name']} | Carousel | {submission_id[:8]}"
            )
            creative_payload = build_carousel_creative_payload(
                name=creative_name,
                page_id=self.client.page_id,
                instagram_user_id=self.client.instagram_user_id,
                cards=actual_cards,
                primary_texts=clean["carousel_primary_texts"],
                destination_url=clean["destination_url"],
                url_tags=self.url_tags,
            )
            creative_id = str(ad_result.get("meta_creative_id") or "")
            if not creative_id:
                creative_id = self._create_or_reconcile(
                    lambda: self.client.create_carousel_creative(creative_payload),
                    lambda: self._one_match(
                        self.client.find_creative_by_name(creative_name)
                    ),
                    submission_id=submission_id,
                    entity="Carousel creative",
                )
                ad_result["meta_creative_id"] = creative_id
                ad_result["status"] = "CREATIVE_CREATED"
                record = self.store.update_stage(
                    submission_id,
                    "CREATIVE_CREATED",
                    meta_creative_id=creative_id,
                    ad_results=[ad_result],
                )

            self._progress("Creating 1 paused carousel ad…")
            ad_id = str(ad_result.get("meta_ad_id") or "")
            if not ad_id:
                existing_ad = self.client.find_ad_by_creative(adset_id, creative_id)
                ad_id = str((existing_ad or {}).get("id") or "")
            if not ad_id:
                ad_id = self._create_or_reconcile(
                    lambda: self.client.create_paused_ad(
                        ad_name=ad_result["ad_name"],
                        adset_id=adset_id,
                        creative_id=creative_id,
                    ),
                    lambda: self._one_match(
                        self.client.find_ad_by_creative(adset_id, creative_id)
                    ),
                    submission_id=submission_id,
                    entity="Carousel Ad",
                )
            ad_result["meta_ad_id"] = ad_id
            ad_result["meta_ad_reused"] = bool(record.get("meta_ad_id"))

            self._progress("Verifying paused Meta carousel…")
            creative_readback = dict(self.client.carousel_creative(creative_id) or {})
            verification = verify_carousel_creative_readback(
                creative_readback,
                page_id=self.client.page_id,
                instagram_user_id=self.client.instagram_user_id,
                cards=actual_cards,
                primary_texts=clean["carousel_primary_texts"],
                destination_url=clean["destination_url"],
            )
            ad_readback = dict(self.client.ad(ad_id) or {})
            ad_checks = {
                "ad_id": str(ad_readback.get("id") or "") == ad_id,
                "target_adset": str(ad_readback.get("adset_id") or "") == adset_id,
                "creative_id": str(
                    (ad_readback.get("creative") or {}).get("id") or ""
                )
                == creative_id,
                "status_paused": str(ad_readback.get("status") or "").upper()
                == "PAUSED",
                "configured_status_paused": str(
                    ad_readback.get("configured_status") or ""
                ).upper()
                == "PAUSED",
            }
            failed = list(verification["failed_checks"])
            failed.extend(name for name, passed in ad_checks.items() if not passed)
            ad_result["carousel_verification"] = {
                **verification,
                "ad_checks": ad_checks,
                "failed_checks": tuple(failed),
                "verified": not failed,
            }
            ad_result["meta_ad_configured_status"] = str(
                ad_readback.get("configured_status") or ""
            ).upper()
            if failed:
                raise MetaAdsApiError(
                    "Meta Carousel read-back verification failed. Failed checks: "
                    + ", ".join(failed)
                    + "."
                )
            ad_result["status"] = "CREATED"
            ad_result["safe_error"] = ""
            record = self.store.update_stage(
                submission_id,
                "AD_CREATED",
                ad_name=ad_result["ad_name"],
                meta_creative_id=creative_id,
                meta_ad_id=ad_id,
                ad_results=[ad_result],
            )
            self._checkpoint("carousel_ad")

            if not is_existing_mode:
                configured_campaign = dict(
                    configured_campaign
                    or self.client.configured_campaign(campaign_id)
                    or {}
                )
            campaign_status = self._configured_status(configured_campaign or {})
            adset_status = self._configured_status(configured_adset or {})
            if not is_existing_mode and (
                campaign_status != "PAUSED" or adset_status != "PAUSED"
            ):
                self._ambiguous(
                    submission_id,
                    "Meta did not confirm PAUSED status for the new Carousel Campaign "
                    "and Ad Set. Review in Ads Manager.",
                    record=record,
                )
            result = self.store.update_stage(
                submission_id,
                "COMPLETE",
                campaign_id=campaign_id,
                campaign_name=campaign_label,
                adset_id=adset_id,
                adset_name=adset_label,
                campaign_ownership=(
                    META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                adset_ownership=(
                    META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                campaign_configured_status=campaign_status,
                adset_configured_status=adset_status,
                ad_name=ad_result["ad_name"],
                meta_image_hash=image_hashes[0],
                meta_creative_id=creative_id,
                meta_ad_id=ad_id,
                meta_status="PAUSED",
                ad_results=[ad_result],
                safe_error="",
            )
            self._checkpoint("final_persistence")
            result["performance_trace"] = tuple(self._performance_trace)
            self._progress("Done — 1 Meta carousel ad is PAUSED")
            return result
        except (
            PostingAbandonedError,
            PostingAmbiguousError,
            PostingBusyError,
        ):
            raise
        except (PostingValidationError, MetaCarouselDiagnosticSafetyError) as error:
            safe_error = sanitize_meta_error(error)
            result = self.store.update_stage(
                submission_id,
                "FAILED",
                safe_error=safe_error,
                ad_results=[ad_result],
            )
            raise PostingValidationError(safe_error, result=result) from error
        except MetaAdsAmbiguousResultError as error:
            self._ambiguous(submission_id, error, record=record)
        except MetaAdsApiError as error:
            safe_error = sanitize_meta_error(error)
            ad_result["status"] = "FAILED"
            ad_result["safe_error"] = safe_error
            result = self.store.update_stage(
                submission_id,
                "FAILED",
                safe_error=safe_error,
                ad_results=[ad_result],
            )
            raise PostingError(safe_error, result=result) from error
        except Exception as error:
            safe_error = (
                "The Meta Carousel request failed. Any objects already created remain "
                "paused and are listed below."
            )
            ad_result["status"] = "FAILED"
            ad_result["safe_error"] = safe_error
            result = self.store.update_stage(
                submission_id,
                "FAILED",
                safe_error=safe_error,
                ad_results=[ad_result],
            )
            raise PostingError(safe_error, result=result) from error

    def create_paused_campaign(self, request):
        if str(getattr(request, "ad_type", AD_TYPE) or AD_TYPE) == CAROUSEL_AD_TYPE:
            return self.create_paused_carousel_campaign(request)
        self._start_performance_trace()
        self._progress("Preparing Meta campaign…")
        clean = validate_posting_request(request)
        self._checkpoint("request_validation")
        try:
            references, catalog, product_set, pixel, audience = self._validate_references(clean)
            existing_ad_names = tuple(self.client.existing_ad_names())
        except MetaAdsApiError as error:
            raise PostingError(sanitize_meta_error(error)) from error
        self._checkpoint("meta_reference_validation")
        posting_mode = clean["posting_mode"]
        is_existing_mode = posting_mode == POSTING_MODE_EXISTING
        create_compatible_adset = bool(
            clean.get("create_new_adset_under_existing_campaign")
        )
        campaign_label = (
            clean["target_campaign_id"]
            if is_existing_mode
            else campaign_name(clean["product_title"], clean["country"], clean["sport"])
        )
        audience_label = (
            "Inherited from existing Ad Set"
            if is_existing_mode
            else str(audience.get("name") or "Broad")
        )
        adset_label = (
            clean["target_adset_id"]
            if is_existing_mode
            else adset_name(clean["country"], clean["sport"], audience_label)
        )
        proposed_ad_names = next_instant_experience_ad_names(
            clean["product_title"], existing_ad_names, count=3
        )
        initial_ad_results = posting_ad_results((), ad_names=proposed_ad_names)
        fingerprint = _request_fingerprint(clean)
        submission_id = str(request.submission_id)
        claim = self.store.claim(
            {
                "submission_id": submission_id, "request_fingerprint": fingerprint,
                "ad_type": AD_TYPE,
                "product_id": clean["product_id"], "product_title": clean["product_title"],
                "product_handle": clean["product_handle"], "country": clean["country"],
                "sport": clean["sport"], "catalog_id": clean["catalog_id"],
                "catalog_name": str(catalog.get("name") or ""),
                "product_set_id": clean["product_set_id"],
                "product_set_name": str(product_set.get("name") or ""),
                "audience_type": clean["audience_type"],
                "audience_id": str(audience.get("id") or ""), "audience_name": audience_label,
                "requested_lifecycle_strategy": (
                    clean["customer_lifecycle_strategy"] if not is_existing_mode else None
                ),
                "verified_lifecycle_strategy": CUSTOMER_LIFECYCLE_UNKNOWN,
                "lifecycle_verification_source": "",
                "pixel_id": str(pixel.get("id") or ""), "pixel_name": str(pixel.get("name") or ""),
                "account_currency": str((references.get("account") or {}).get("currency") or ""),
                "campaign_name": campaign_label, "adset_name": adset_label,
                "ad_name": proposed_ad_names[0], "ad_results": initial_ad_results,
                "destination_url": clean["destination_url"],
                "posting_mode": posting_mode,
                "campaign_ownership": (
                    META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                "adset_ownership": (
                    META_OBJECT_CREATED_BY_RUN
                    if create_compatible_adset
                    else META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                "campaign_id": clean["target_campaign_id"] if is_existing_mode else None,
                "adset_id": (
                    None
                    if create_compatible_adset
                    else clean["target_adset_id"] if is_existing_mode else None
                ),
                "campaign_configured_status": "",
                "adset_configured_status": "",
                "image_checksum": ",".join(
                    creative["image_checksum"] for creative in clean["creatives"]
                ),
            },
            lease_token=str(uuid.uuid4()),
        )
        self._checkpoint("ledger_claim")
        record = dict(claim.get("record") or {})
        submission_id = str(record.get("submission_id") or submission_id)
        if str(record.get("ad_type") or AD_TYPE) != AD_TYPE:
            raise PostingValidationError(
                "This Posting run belongs to a different Ad Type. Start a new run."
            )
        record_mode = str(record.get("posting_mode") or POSTING_MODE_NEW).upper()
        if record_mode != posting_mode:
            raise PostingValidationError(
                "This Posting run belongs to a different Posting mode. Start a new run."
            )
        existing_target_record_valid = (
            str(record.get("campaign_id") or "") == clean["target_campaign_id"]
            and str(record.get("campaign_ownership") or "").upper()
            == META_OBJECT_EXISTING_TARGET
            and (
                (
                    create_compatible_adset
                    and str(record.get("adset_ownership") or "").upper()
                    == META_OBJECT_CREATED_BY_RUN
                )
                or (
                    not create_compatible_adset
                    and str(record.get("adset_id") or "") == clean["target_adset_id"]
                    and str(record.get("adset_ownership") or "").upper()
                    == META_OBJECT_EXISTING_TARGET
                )
            )
        )
        if is_existing_mode and not existing_target_record_valid:
            raise PostingValidationError(
                "This Posting run does not own the selected existing Meta target. "
                "Start a new run and select the Campaign and Ad Set again."
            )
        if not is_existing_mode and (
            str(record.get("campaign_ownership") or META_OBJECT_CREATED_BY_RUN).upper()
            != META_OBJECT_CREATED_BY_RUN
            or str(record.get("adset_ownership") or META_OBJECT_CREATED_BY_RUN).upper()
            != META_OBJECT_CREATED_BY_RUN
        ):
            raise PostingValidationError(
                "This Posting run references an external Meta target. Start a New Campaign run."
            )
        if not claim.get("claimed"):
            status = str(record.get("status") or "")
            if status == "COMPLETE":
                record["performance_trace"] = tuple(self._performance_trace)
                return record
            if status == "AMBIGUOUS":
                raise PostingAmbiguousError(
                    str(record.get("safe_error") or "Meta did not confirm the earlier result."),
                    result=record,
                )
            if status == "ABANDONED_EXTERNALLY":
                raise PostingAbandonedError(
                    str(record.get("safe_error") or EXTERNALLY_ABANDONED_MESSAGE),
                    result=record,
                )
            raise PostingBusyError(
                "This campaign is already being created. Wait for the current request to finish.",
                result=record,
            )

        # A retry must keep the names assigned to the original persistent job,
        # even if the account now contains a later IA sequence number.
        campaign_label = str(record.get("campaign_name") or campaign_label)
        adset_label = str(record.get("adset_name") or adset_label)
        ad_results = posting_ad_results(
            record.get("ad_results"), ad_names=proposed_ad_names
        )
        active_ad_index = None

        try:
            campaign_id = str(record.get("campaign_id") or "")
            configured_campaign = None
            configured_adset = None
            self._progress(
                "Checking existing Meta campaign…"
                if is_existing_mode or campaign_id
                else "Creating campaign…"
            )
            if is_existing_mode:
                target = self._existing_target_for_run(
                    clean=clean,
                    pixel=pixel,
                    submission_id=submission_id,
                    ad_results=ad_results,
                    record=record,
                    allow_product_set_mismatch=create_compatible_adset,
                )
                configured_campaign = target["campaign"]
                source_adset = target["adset"]
                campaign_id = clean["target_campaign_id"]
                campaign_label = str(configured_campaign.get("name") or campaign_id)
                if create_compatible_adset:
                    if target["product_set_compatible"]:
                        raise PostingValidationError(
                            "The selected Ad Set is already compatible. Use it directly."
                        )
                    adset_id = str(record.get("adset_id") or "")
                    adset_label = compatible_adset_name(source_adset, product_set)
                    lifecycle_verification = customer_lifecycle_verification(
                        source_adset,
                        acquisition_fields_requested=True,
                    )
                else:
                    configured_adset = source_adset
                    adset_id = clean["target_adset_id"]
                    adset_label = str(configured_adset.get("name") or adset_id)
                    lifecycle_verification = customer_lifecycle_verification(
                        configured_adset,
                        acquisition_fields_requested=True,
                    )
                record = self.store.update_stage(
                    submission_id,
                    "VALIDATING",
                    campaign_id=campaign_id,
                    campaign_name=campaign_label,
                    adset_id=adset_id or None,
                    adset_name=adset_label,
                    campaign_ownership=META_OBJECT_EXISTING_TARGET,
                    adset_ownership=(
                        META_OBJECT_CREATED_BY_RUN
                        if create_compatible_adset
                        else META_OBJECT_EXISTING_TARGET
                    ),
                    campaign_configured_status=target["campaign_status"],
                    adset_configured_status=(
                        "" if create_compatible_adset else target["adset_status"]
                    ),
                    verified_lifecycle_strategy=lifecycle_verification["strategy"],
                    lifecycle_verification_source=lifecycle_verification[
                        "verification_source"
                    ],
                    ad_results=ad_results,
                )
            elif campaign_id:
                try:
                    configured_campaign = self.client.configured_campaign(campaign_id)
                except MetaAdsApiError as error:
                    if not is_meta_object_missing_or_inaccessible(error):
                        raise
                    abandoned = self.store.update_stage(
                        submission_id,
                        "ABANDONED_EXTERNALLY",
                        safe_error=EXTERNALLY_ABANDONED_MESSAGE,
                        ad_results=ad_results,
                    )
                    raise PostingAbandonedError(
                        EXTERNALLY_ABANDONED_MESSAGE,
                        result=abandoned or record,
                    ) from error
                if str((configured_campaign or {}).get("id") or "") != campaign_id:
                    abandoned = self.store.update_stage(
                        submission_id,
                        "ABANDONED_EXTERNALLY",
                        safe_error=EXTERNALLY_ABANDONED_MESSAGE,
                        ad_results=ad_results,
                    )
                    raise PostingAbandonedError(
                        EXTERNALLY_ABANDONED_MESSAGE,
                        result=abandoned or record,
                    )
            if not campaign_id:
                campaign_id = self._create_or_reconcile(
                    lambda: self.client.create_campaign(
                        build_campaign_payload(name=campaign_label, catalog_id=clean["catalog_id"])
                    ),
                    submission_id=submission_id, entity="campaign",
                )
                record = self.store.update_stage(
                    submission_id, "CAMPAIGN_CREATED", campaign_id=campaign_id,
                    campaign_name=campaign_label,
                )
            self._checkpoint("campaign_resolution")

            adset_id = str(record.get("adset_id") or "")
            self._progress(
                "Checking existing Meta Ad Set…"
                if is_existing_mode or adset_id
                else "Creating Ad Set…"
            )
            new_adset_lifecycle = (
                lifecycle_verification["strategy"]
                if create_compatible_adset
                and lifecycle_verification["strategy"]
                != CUSTOMER_LIFECYCLE_UNKNOWN
                else CUSTOMER_LIFECYCLE_ALL_AUDIENCES
                if create_compatible_adset
                else clean["customer_lifecycle_strategy"]
            )
            if (not is_existing_mode or create_compatible_adset) and not adset_id:
                targeting = (
                    targeting_for_compatible_adset(
                        source_adset, country=clean["country"]
                    )
                    if create_compatible_adset
                    else build_targeting(
                        country=clean["country"],
                        audience_type=clean["audience_type"],
                        audience=audience,
                    )
                )
                adset_id = self._create_or_reconcile(
                    lambda: self.client.create_adset(
                        build_adset_payload(
                            name=adset_label, campaign_id=campaign_id,
                            product_set_id=clean["product_set_id"], pixel_id=pixel["id"],
                            targeting=targeting,
                            customer_lifecycle_strategy=new_adset_lifecycle,
                        )
                    ),
                    lambda: self.client.find_adsets_by_name(campaign_id, adset_label),
                    submission_id=submission_id, entity="ad set",
                )
                record = self.store.update_stage(
                    submission_id,
                    "ADSET_CREATED",
                    adset_id=adset_id,
                    adset_name=adset_label,
                    campaign_ownership=(
                        META_OBJECT_EXISTING_TARGET
                        if create_compatible_adset
                        else META_OBJECT_CREATED_BY_RUN
                    ),
                    adset_ownership=META_OBJECT_CREATED_BY_RUN,
                )
            if not is_existing_mode or create_compatible_adset:
                if configured_adset is None:
                    configured_adset = self.client.configured_adset(adset_id)
                if create_compatible_adset:
                    validate_existing_posting_target(
                        campaign=configured_campaign,
                        adset=configured_adset,
                        expected_campaign_id=campaign_id,
                        expected_adset_id=adset_id,
                        expected_account_id=self.client.ad_account_id,
                        expected_catalog_id=clean["catalog_id"],
                        expected_product_set_id=clean["product_set_id"],
                        expected_pixel_id=pixel["id"],
                    )
                lifecycle_verification = customer_lifecycle_verification(
                    configured_adset,
                    acquisition_fields_requested=True,
                )
                record = self.store.update_stage(
                    submission_id,
                    "ADSET_CREATED",
                    requested_lifecycle_strategy=new_adset_lifecycle,
                    verified_lifecycle_strategy=lifecycle_verification["strategy"],
                    lifecycle_verification_source=lifecycle_verification[
                        "verification_source"
                    ],
                    ad_results=ad_results,
                )
                if (
                    lifecycle_verification["strategy"]
                    != new_adset_lifecycle
                ):
                    self._ambiguous(
                        submission_id,
                        (
                            "Meta did not confirm 'Get conversions from all audiences' "
                            "for the new paused Ad Set. No Instant Experiences or Ads were created."
                        ),
                        record=record,
                    )

            self._checkpoint("adset_resolution")

            source_ad_id = configured_collection_template_ad_id()
            source_snapshot_loader = getattr(
                self.template_copy_service,
                "read_source_snapshot",
                None,
            )
            source_snapshot = (
                source_snapshot_loader(source_ad_id)
                if callable(source_snapshot_loader)
                else None
            )

            for index, (creative, ad_result) in enumerate(
                zip(clean["creatives"], ad_results), start=1
            ):
                self._progress(f"Creating Ad {index} of 3…")
                active_ad_index = index - 1
                ad_label = str(ad_result.get("ad_name") or proposed_ad_names[index - 1])
                persisted_route_ids = {
                    key: str(ad_result.get(key) or "")
                    for key in (
                        "meta_canvas_button_element_id",
                        "meta_canvas_footer_element_id",
                        "meta_instant_experience_id",
                    )
                }

                def persist(stage, **legacy_fields):
                    nonlocal record
                    record = self.store.update_stage(
                        submission_id, stage, ad_results=ad_results, **legacy_fields
                    )

                image = creative["image"]
                image_hash = str(ad_result.get("meta_image_hash") or "")
                if not image_hash:
                    try:
                        image_hash = self.client.upload_image(
                            image["data"], filename=image["upload_name"],
                            content_type=image["content_type"],
                        )
                    except MetaAdsAmbiguousResultError as error:
                        self._ambiguous(submission_id, error, record=record)
                    ad_result["meta_image_hash"] = image_hash
                    ad_result["status"] = "IMAGE_UPLOADED"
                    persist(
                        "IMAGE_UPLOADED",
                        **({"meta_image_hash": image_hash} if index == 1 else {}),
                    )

                page_photo_id = str(ad_result.get("meta_page_photo_id") or "")
                if not page_photo_id:
                    try:
                        page_photo_id = self.client.upload_page_photo(
                            image["data"], filename=image["upload_name"],
                            content_type=image["content_type"],
                        )
                    except MetaAdsAmbiguousResultError as error:
                        self._ambiguous(submission_id, error, record=record)
                    ad_result["meta_page_photo_id"] = page_photo_id
                    ad_result["status"] = "PAGE_PHOTO_CREATED"
                    persist(
                        "PAGE_PHOTO_CREATED",
                        **({"meta_page_photo_id": page_photo_id} if index == 1 else {}),
                    )

                storefront_specs = build_storefront_element_specs(
                    page_photo_id=page_photo_id,
                    product_set_id=clean["product_set_id"],
                    destination_url=clean["destination_url"],
                    button_element_id=str(ad_result.get("meta_canvas_button_element_id") or ""),
                )
                for result_field, element_type in (
                    ("meta_canvas_photo_element_id", "canvas_photo"),
                    ("meta_canvas_product_element_id", "canvas_product_set"),
                    ("meta_canvas_button_element_id", "canvas_button"),
                ):
                    if not str(ad_result.get(result_field) or ""):
                        ad_result[result_field] = self.client.create_canvas_element(
                            element_type, storefront_specs[element_type]
                        )
                        ad_result["status"] = "PAGE_PHOTO_CREATED"
                        persist(
                            "PAGE_PHOTO_CREATED",
                            **({result_field: ad_result[result_field]} if index == 1 else {}),
                        )
                if not str(ad_result.get("meta_canvas_footer_element_id") or ""):
                    storefront_specs = build_storefront_element_specs(
                        page_photo_id=page_photo_id,
                        product_set_id=clean["product_set_id"],
                        destination_url=clean["destination_url"],
                        button_element_id=ad_result["meta_canvas_button_element_id"],
                    )
                    ad_result["meta_canvas_footer_element_id"] = self.client.create_canvas_element(
                        "canvas_footer", storefront_specs["canvas_footer"]
                    )
                    persist(
                        "PAGE_PHOTO_CREATED",
                        **(
                            {"meta_canvas_footer_element_id": ad_result["meta_canvas_footer_element_id"]}
                            if index == 1 else {}
                        ),
                    )

                canvas_label = f"{ad_label} | Storefront"
                ad_result["instant_experience_name"] = canvas_label
                canvas_id = str(ad_result.get("meta_instant_experience_id") or "")
                canvas_was_reused = bool(canvas_id)
                if not canvas_id:
                    canvas_id = self._create_or_reconcile(
                        lambda: self.client.create_canvas(
                            name=canvas_label,
                            body_element_ids=(
                                ad_result["meta_canvas_photo_element_id"],
                                ad_result["meta_canvas_product_element_id"],
                                ad_result["meta_canvas_footer_element_id"],
                            ),
                        ),
                        submission_id=submission_id, entity=f"Instant Experience {index}",
                    )
                    ad_result["meta_instant_experience_id"] = canvas_id
                    ad_result["instant_experience_creation_provenance"] = (
                        build_instant_experience_creation_provenance(
                            submission_id=submission_id,
                            request_fingerprint=fingerprint,
                            canvas_id=canvas_id,
                            button_element_id=ad_result["meta_canvas_button_element_id"],
                            footer_element_id=ad_result["meta_canvas_footer_element_id"],
                            destination_url=clean["destination_url"],
                        )
                    )
                    ad_result["status"] = "INSTANT_EXPERIENCE_CREATED"
                    persist(
                        "INSTANT_EXPERIENCE_CREATED",
                        **({"meta_instant_experience_id": canvas_id} if index == 1 else {}),
                    )
                ad_result["meta_instant_experience_reused"] = canvas_was_reused

                provenance = dict(
                    ad_result.get("instant_experience_creation_provenance") or {}
                )
                legacy_provenance_eligible = bool(
                    canvas_was_reused
                    and persisted_route_ids["meta_canvas_button_element_id"]
                    and persisted_route_ids["meta_canvas_footer_element_id"]
                    and persisted_route_ids["meta_instant_experience_id"] == canvas_id
                    and str(record.get("request_fingerprint") or "") == fingerprint
                    and str(record.get("destination_url") or "")
                    == clean["destination_url"]
                )
                if not provenance and legacy_provenance_eligible:
                    provenance = build_instant_experience_creation_provenance(
                        submission_id=submission_id,
                        request_fingerprint=str(record.get("request_fingerprint") or ""),
                        canvas_id=canvas_id,
                        button_element_id=persisted_route_ids[
                            "meta_canvas_button_element_id"
                        ],
                        footer_element_id=persisted_route_ids[
                            "meta_canvas_footer_element_id"
                        ],
                        destination_url=str(record.get("destination_url") or ""),
                    )

                instant_experience = self.client.instant_experience(canvas_id)
                preliminary_verification = verify_instant_experience_destination(
                    instant_experience,
                    expected_url=clean["destination_url"],
                    provenance=provenance,
                    expected_canvas_id=canvas_id,
                    expected_request_fingerprint=fingerprint,
                    expected_submission_id=submission_id,
                )
                if preliminary_verification["verification_state"] == "UNAVAILABLE":
                    optional_details = {}
                    try:
                        optional_details = (
                            self.client.instant_experience_optional_details(canvas_id)
                        )
                    except AttributeError:
                        optional_details = {}
                    except MetaAdsApiError as error:
                        if not is_optional_canvas_read_capability_error(error):
                            raise
                    if optional_details:
                        instant_experience = {
                            **dict(instant_experience or {}),
                            **dict(optional_details),
                        }
                        preliminary_verification = verify_instant_experience_destination(
                            instant_experience,
                            expected_url=clean["destination_url"],
                            expected_canvas_id=canvas_id,
                            expected_request_fingerprint=fingerprint,
                            expected_submission_id=submission_id,
                        )
                child_elements = ()
                if preliminary_verification["verification_state"] == "UNAVAILABLE":
                    verification_element_ids = (
                        (
                            persisted_route_ids["meta_canvas_button_element_id"],
                            persisted_route_ids["meta_canvas_footer_element_id"],
                        )
                        if canvas_was_reused
                        else (
                            ad_result["meta_canvas_button_element_id"],
                            ad_result["meta_canvas_footer_element_id"],
                        )
                    )
                    try:
                        child_elements = self.client.instant_experience_elements(
                            verification_element_ids
                        )
                    except AttributeError:
                        child_elements = ()
                    except MetaAdsApiError as error:
                        if not is_optional_canvas_read_capability_error(error):
                            raise
                destination_verification = verify_instant_experience_destination(
                    instant_experience,
                    expected_url=clean["destination_url"],
                    child_elements=child_elements,
                    provenance=provenance,
                    expected_canvas_id=canvas_id,
                    expected_request_fingerprint=fingerprint,
                    expected_submission_id=submission_id,
                )
                ad_result["instant_experience_verification"] = destination_verification
                if not destination_verification["verified"]:
                    raise MetaAdsApiError(
                        f"Instant Experience {index} fixed button verification "
                        f"{destination_verification['verification_state'].casefold()}. "
                        f"{destination_verification['reason']} No copied Ad was created."
                    )
                if provenance and not ad_result.get(
                    "instant_experience_creation_provenance"
                ):
                    ad_result["instant_experience_creation_provenance"] = provenance

                creative_label = f"{ad_label} | Collection"
                creative_payload = build_collection_creative_payload(
                    name=creative_label,
                    page_id=self.client.page_id,
                    instagram_user_id=self.client.instagram_user_id,
                    image_hash=image_hash,
                    canvas_id=canvas_id,
                    product_set_id=clean["product_set_id"],
                    destination_url=clean["destination_url"],
                    primary_text=creative["primary_text"],
                    headline=creative["headline"],
                    description=creative["description"],
                    url_tags=self.url_tags,
                )
                copy_arguments = {
                    "source_ad_id": source_ad_id,
                    "target_adset_id": adset_id,
                    "expected_ad_name": ad_label,
                    "creative_parameters": creative_payload,
                    "persisted_ad_id": str(ad_result.get("meta_ad_id") or ""),
                }
                if source_snapshot is not None:
                    copy_arguments["source_snapshot"] = source_snapshot
                copy_result = (
                    self.template_copy_service.create_or_reconcile_paused_route_copy(
                        **copy_arguments
                    )
                )
                ad_result["meta_creative_id"] = str(
                    copy_result.get("copied_creative_id") or ""
                )
                ad_result["meta_ad_id"] = str(copy_result.get("copied_ad_id") or "")
                ad_result["meta_ad_reused"] = bool(
                    copy_result.get("reconciled_existing_copy")
                )
                ad_result["meta_ad_configured_status"] = str(
                    copy_result.get("copied_configured_status") or ""
                )
                ad_result["status"] = "CREATED"
                ad_result["safe_error"] = ""
                persist(
                    "AD_CREATED",
                    **(
                        {
                            "ad_name": ad_label,
                            "meta_creative_id": ad_result["meta_creative_id"],
                            "meta_ad_id": ad_result["meta_ad_id"],
                        }
                        if index == 1
                        else {}
                    ),
                )
                self._checkpoint(f"route_{index}")

            self._progress("Verifying paused Meta ads…")
            campaign_status = self._configured_status(
                configured_campaign or self.client.configured_campaign(campaign_id)
            )
            adset_status = self._configured_status(
                configured_adset or self.client.configured_adset(adset_id)
            )
            statuses = {
                f"ad {row['index']}": str(
                    row.get("meta_ad_configured_status") or ""
                ).upper()
                for row in ad_results
            }
            if not is_existing_mode or create_compatible_adset:
                statuses = {
                    "ad set": adset_status,
                    **statuses,
                }
                if not is_existing_mode:
                    statuses = {"campaign": campaign_status, **statuses}
            not_paused = [entity for entity, status in statuses.items() if status != "PAUSED"]
            if not_paused:
                self._ambiguous(
                    submission_id,
                    f"Meta did not confirm PAUSED status for: {', '.join(not_paused)}. Review in Ads Manager.",
                    record=record,
                )
            self._checkpoint("paused_status_verification")
            # Compatibility and ownership were verified before creation. This
            # broader catalogue-health read is optional, unsupported for the
            # configured app, and is intentionally outside the critical path.
            product_set_health = {
                "status": "NOT RUN",
                "product_set_id": clean["product_set_id"],
                "product_set_name": str(product_set.get("name") or ""),
                "message": "Optional post-creation Product Set health diagnostic was not run.",
                "read_only": True,
            }
            ad_results[0]["product_set_health"] = product_set_health
            first = ad_results[0]
            result = self.store.update_stage(
                submission_id, "COMPLETE", campaign_id=campaign_id, adset_id=adset_id,
                campaign_name=campaign_label, adset_name=adset_label,
                campaign_ownership=(
                    META_OBJECT_EXISTING_TARGET
                    if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                adset_ownership=(
                    META_OBJECT_CREATED_BY_RUN
                    if create_compatible_adset
                    else META_OBJECT_EXISTING_TARGET if is_existing_mode
                    else META_OBJECT_CREATED_BY_RUN
                ),
                campaign_configured_status=campaign_status,
                adset_configured_status=adset_status,
                ad_name=first["ad_name"], meta_image_hash=first["meta_image_hash"],
                meta_page_photo_id=first["meta_page_photo_id"],
                meta_instant_experience_id=first["meta_instant_experience_id"],
                meta_creative_id=first["meta_creative_id"],
                meta_ad_id=first["meta_ad_id"], meta_status="PAUSED",
                ad_results=ad_results, safe_error="",
            )
            self._checkpoint("final_persistence")
            result["performance_trace"] = tuple(self._performance_trace)
            self._progress("Done — 3 Meta ads are PAUSED")
            return result
        except (
            PostingAbandonedError,
            PostingAmbiguousError,
            PostingBusyError,
            PostingValidationError,
        ):
            raise
        except (
            MetaCollectionTemplateCopySafetyError,
            MetaCollectionTemplateCopyVerificationError,
        ) as error:
            safe_error = sanitize_meta_error(error)
            if active_ad_index is not None:
                active_result = ad_results[active_ad_index]
                verification_result = (
                    dict(error.result or {})
                    if isinstance(error, MetaCollectionTemplateCopyVerificationError)
                    else {}
                )
                copied_ad_id = str(verification_result.get("copied_ad_id") or "")
                copied_status = str(
                    verification_result.get("copied_status") or ""
                )
                copied_configured_status = str(
                    verification_result.get("copied_configured_status") or ""
                )
                if copied_ad_id:
                    active_result["meta_ad_id"] = copied_ad_id
                    active_result["meta_creative_id"] = str(
                        verification_result.get("copied_creative_id") or ""
                    )
                    active_result["meta_ad_configured_status"] = copied_configured_status
                    active_result["meta_ad_reused"] = bool(
                        verification_result.get("reconciled_existing_copy")
                    )
                active_result["status"] = (
                    "VERIFICATION_PENDING"
                    if (
                        copied_ad_id
                        and copied_status.upper() == "PAUSED"
                        and copied_configured_status.upper() == "PAUSED"
                    )
                    else "FAILED"
                )
                active_result["safe_error"] = safe_error
            result = self.store.update_stage(
                submission_id, "FAILED", safe_error=safe_error, ad_results=ad_results
            )
            raise PostingError(safe_error, result=result) from error
        except MetaAdsAmbiguousResultError as error:
            self._ambiguous(submission_id, error, record=record)
        except MetaAdsApiError as error:
            safe_error = sanitize_meta_error(error)
            if active_ad_index is not None:
                ad_results[active_ad_index]["status"] = "FAILED"
                ad_results[active_ad_index]["safe_error"] = safe_error
            result = self.store.update_stage(
                submission_id, "FAILED", safe_error=safe_error, ad_results=ad_results
            )
            raise PostingError(safe_error, result=result) from error
        except Exception as error:
            safe_error = (
                "The Meta request failed. Any objects already created remain paused and are listed below."
            )
            if active_ad_index is not None:
                ad_results[active_ad_index]["status"] = "FAILED"
                ad_results[active_ad_index]["safe_error"] = safe_error
            result = self.store.update_stage(
                submission_id, "FAILED", safe_error=safe_error, ad_results=ad_results
            )
            raise PostingError(safe_error, result=result) from error

    def create_paused_ad(self, request):
        """Compatibility alias for callers upgraded from Posting V1."""
        return self.create_paused_campaign(request)

    def recent_posts(self, limit=20):
        return self.store.recent(limit=limit)

    def failed_collection_diagnostic_job(
        self, *, submission_id="", product_title="", product_set_id=""
    ):
        """Read the positively matched partial job used by validate-only probes."""
        return self.store.failed_collection_diagnostic_job(
            submission_id=submission_id,
            product_title=product_title,
            product_set_id=product_set_id,
        )
