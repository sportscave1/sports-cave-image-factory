from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import uuid
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from ads_image_workflow import AdsImageValidationError, prepare_meta_posting_image
from ads_meta_contract import META_AD_URL_PARAMETERS, META_DEFAULT_CTA
from meta_ads_client import (
    MetaAdsAmbiguousResultError,
    MetaAdsApiError,
    MetaPostingClient,
    sanitize_meta_error,
)


SUCCESS_MESSAGE = "Meta ad created successfully — PAUSED"
POSTING_PERMISSION = "ads_management"
EXPECTED_CATALOG_NAME = "Shopify Product Catalog"
EXPECTED_PIXEL_NAME = "Shprts Cave Pixel 2025"
CATALOG_ID_ENV_KEYS = ("META_CATALOG_ID",)
DATASET_ID_ENV_KEYS = ("META_PIXEL_ID", "META_DATASET_ID")
CAMPAIGN_OBJECTIVE = "OUTCOME_SALES"
CAMPAIGN_DAILY_BUDGET_MINOR = 2500
PRODUCT_DESCRIPTION = "Limited Edition"
INSTANT_EXPERIENCE_BUTTON_TEXT = "Claim Your Edition"
AD_TYPE = "Instant Experience"
COUNTRY_META_CODES = {"AUS": "AU", "USA": "US", "UK": "GB", "CAN": "CA", "NZ": "NZ"}
SPORT_OPTIONS = (
    "NBA", "Motorsport", "Football", "Cricket", "Golf", "Horse Racing", "Baseball",
    "Combat", "Ice Hockey", "NFL", "Rugby Union", "Tennis", "Other",
)
POSTING_STATUSES = (
    "VALIDATING", "CAMPAIGN_CREATED", "ADSET_CREATED", "IMAGE_UPLOADED",
    "PAGE_PHOTO_CREATED", "INSTANT_EXPERIENCE_CREATED", "CREATIVE_CREATED",
    "AD_CREATED", "COMPLETE", "FAILED", "AMBIGUOUS",
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
    required_id = str(expected_id or configured_id or "").strip()
    if required_id:
        if required_id in rows:
            return _resolution(entity="catalog", row=rows[required_id], source="configured_or_selected_id")
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


@dataclass(frozen=True)
class PostingRequest:
    submission_id: str
    product_id: str
    product_title: str
    product_handle: str
    destination_url: str
    image_bytes: bytes
    image_name: str
    country: str
    sport: str
    catalog_id: str
    product_set_id: str
    primary_text: str
    headline: str
    audience_type: str = "broad"
    audience_id: str = ""
    description: str = ""


def normalize_account_id(value):
    return re.sub(r"^act_", "", str(value or "").strip(), flags=re.IGNORECASE)


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
    short = product_short_name(product_title)
    pattern = re.compile(rf"^{re.escape(short)}\s+IA\s+(\d+)$", re.IGNORECASE)
    sequence = [
        int(match.group(1)) for name in existing_names
        if (match := pattern.match(str(name or "").strip()))
    ]
    return f"{short} IA {(max(sequence) if sequence else 0) + 1}"


def posting_submission_id():
    return str(uuid.uuid4())


def ads_manager_url(*, account_id, campaign_id, adset_id, ad_id):
    account = normalize_account_id(account_id)
    return (
        "https://www.facebook.com/adsmanager/manage/ads"
        f"?act={account}&selected_campaign_ids={campaign_id}"
        f"&selected_adset_ids={adset_id}&selected_ad_ids={ad_id}"
    )


def _request_fingerprint(request, *, image_checksum):
    payload = {
        "product_id": str(request.product_id or "").strip(),
        "product_title": str(request.product_title or "").strip(),
        "destination_url": str(request.destination_url or "").strip(),
        "image_checksum": image_checksum,
        "country": str(request.country or "").strip(),
        "sport": str(request.sport or "").strip(),
        "catalog_id": str(request.catalog_id or "").strip(),
        "product_set_id": str(request.product_set_id or "").strip(),
        "audience_type": str(request.audience_type or "broad").strip().casefold(),
        "audience_id": str(request.audience_id or "").strip(),
        "primary_text": str(request.primary_text or ""),
        "headline": str(request.headline or ""),
        "description": str(request.description or ""),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_posting_request(request):
    try:
        uuid.UUID(str(request.submission_id or ""))
    except (ValueError, TypeError, AttributeError) as error:
        raise PostingValidationError("Start a new Posting submission and try again.") from error
    product_title = str(request.product_title or "").strip()
    if not product_title:
        raise PostingValidationError("Select a product from Edition Ops.")
    destination_url = validate_destination_url(request.destination_url)
    if not bytes(request.image_bytes or b""):
        raise PostingValidationError("Upload the finished ad image.")
    try:
        image = prepare_meta_posting_image(request.image_bytes, original_name=request.image_name)
    except AdsImageValidationError as error:
        raise PostingValidationError(str(error)) from error
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
    primary_text = str(request.primary_text or "")
    headline = str(request.headline or "")
    if not primary_text.strip():
        raise PostingValidationError("Enter the final primary text.")
    if not headline.strip():
        raise PostingValidationError("Enter the final headline.")
    audience_type = str(request.audience_type or "broad").strip().casefold()
    if audience_type not in {"broad", "saved", "custom"}:
        raise PostingValidationError("Select a valid Meta audience.")
    audience_id = str(request.audience_id or "").strip()
    if audience_type != "broad" and not audience_id:
        raise PostingValidationError("Select a saved or custom audience.")
    return {
        "product_id": str(request.product_id or "").strip(),
        "product_title": product_title,
        "product_handle": str(request.product_handle or "").strip(),
        "destination_url": destination_url,
        "image": image,
        "image_checksum": str(image["source_hash"]),
        "country": country,
        "sport": sport,
        "catalog_id": catalog_id,
        "product_set_id": product_set_id,
        "audience_type": audience_type,
        "audience_id": audience_id,
        "primary_text": primary_text,
        "headline": headline,
        "description": str(request.description or ""),
    }


def build_campaign_payload(*, name, catalog_id):
    return {
        "name": str(name), "objective": CAMPAIGN_OBJECTIVE, "buying_type": "AUCTION",
        "status": "PAUSED", "special_ad_categories": [],
        "daily_budget": str(CAMPAIGN_DAILY_BUDGET_MINOR),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "promoted_object": {"product_catalog_id": str(catalog_id)},
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


def build_adset_payload(*, name, campaign_id, product_set_id, pixel_id, targeting, start_time=None):
    begins = start_time or datetime.now(timezone.utc)
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


def build_creative_features_spec():
    opted_in = (
        "standard_enhancements_catalog", "adapt_to_placement", "description_automation",
        "enhance_cta", "hide_price", "inline_comment", "product_extensions",
        "text_optimizations",
    )
    features = {name: {"enroll_status": "OPT_IN"} for name in opted_in}
    features["image_background_gen"] = {"enroll_status": "OPT_OUT"}
    return {"creative_features_spec": features}


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


def build_collection_creative_payload(
    *, name, page_id, instagram_user_id, image_hash, canvas_id, product_set_id,
    destination_url, primary_text, headline, description="", url_tags=META_AD_URL_PARAMETERS,
):
    link_data = {
        "image_hash": str(image_hash), "link": str(destination_url), "canvas_id": str(canvas_id),
        "message": str(primary_text), "name": str(headline),
        "call_to_action": {"type": META_DEFAULT_CTA, "value": {"link": str(destination_url)}},
    }
    if str(description or "").strip():
        link_data["description"] = str(description)
    return {
        "name": str(name),
        "object_story_spec": {
            "page_id": str(page_id), "instagram_user_id": str(instagram_user_id),
            "link_data": link_data,
        },
        "product_set_id": str(product_set_id),
        "contextual_multi_ads": {"enroll_status": "OPT_IN"},
        "degrees_of_freedom_spec": build_creative_features_spec(),
        "url_tags": str(url_tags or ""),
    }


class SupabasePostingStore:
    """Persistent lease ledger for safe retries and partial Meta object recovery."""

    def _backend(self):
        import supabase_backend
        return supabase_backend

    def claim(self, request_data, *, lease_token):
        backend = self._backend()
        backend.ensure_ads_schema()
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM meta_posting_submissions
                    WHERE request_fingerprint=%s AND status='COMPLETE'
                      AND created_at >= now() - interval '15 minutes'
                    ORDER BY completed_at DESC NULLS LAST LIMIT 1
                    """,
                    (request_data["request_fingerprint"],),
                )
                completed = dict(cur.fetchone() or {})
                if completed:
                    conn.commit()
                    return {"claimed": False, "record": completed}
                columns = (
                    "submission_id", "request_fingerprint", "status", "product_id",
                    "product_title", "product_handle", "country", "sport", "catalog_id",
                    "catalog_name", "product_set_id", "product_set_name", "audience_type",
                    "audience_id", "audience_name", "pixel_id", "pixel_name", "account_currency", "campaign_name",
                    "adset_name", "ad_name", "destination_url", "image_checksum",
                )
                placeholders = ["%s::uuid", *(["%s"] * (len(columns) - 1))]
                values = tuple(
                    "VALIDATING" if column == "status" else request_data.get(column)
                    for column in columns
                )
                cur.execute(
                    f"INSERT INTO meta_posting_submissions({', '.join(columns)}) "
                    f"VALUES ({', '.join(placeholders)}) ON CONFLICT (submission_id) DO NOTHING",
                    values,
                )
                cur.execute(
                    "SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid",
                    (request_data["submission_id"],),
                )
                existing = dict(cur.fetchone() or {})
                if str(existing.get("request_fingerprint") or "") != request_data["request_fingerprint"]:
                    raise PostingValidationError(
                        "This submission changed after posting began. Reset and create a new submission."
                    )
                if str(existing.get("status") or "") in {"COMPLETE", "AMBIGUOUS"}:
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
                    (lease_token, request_data["submission_id"]),
                )
                claimed = dict(cur.fetchone() or {})
                if not claimed:
                    cur.execute(
                        "SELECT * FROM meta_posting_submissions WHERE submission_id=%s::uuid",
                        (request_data["submission_id"],),
                    )
                    existing = dict(cur.fetchone() or {})
                conn.commit()
                return {"claimed": bool(claimed), "record": claimed or existing}

    def update_stage(self, submission_id, status, **fields):
        if status not in POSTING_STATUSES:
            raise ValueError("Unknown Posting status.")
        allowed = {
            "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_name",
            "meta_image_hash", "meta_page_photo_id", "meta_canvas_photo_element_id",
            "meta_canvas_product_element_id", "meta_canvas_button_element_id",
            "meta_canvas_footer_element_id", "meta_instant_experience_id",
            "meta_creative_id", "meta_ad_id", "meta_status", "safe_error",
        }
        values = {key: fields[key] for key in fields if key in allowed}
        assignments = ["status=%s", "updated_at=now()"]
        params = [status]
        for key, value in values.items():
            assignments.append(f"{key}=%s")
            params.append(value)
        if status in {"COMPLETE", "FAILED", "AMBIGUOUS"}:
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
                           meta_status, safe_error
                    FROM meta_posting_submissions ORDER BY created_at DESC LIMIT %s
                    """,
                    (max(1, min(int(limit or 20), 100)),),
                )
                return [dict(row) for row in cur.fetchall()]


class MetaPostingService:
    def __init__(self, *, client=None, store=None, url_tags=META_AD_URL_PARAMETERS):
        self.client = client or MetaPostingClient()
        self.store = store or SupabasePostingStore()
        self.url_tags = str(url_tags or "")

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
        if not str(self.client.instagram_actor_id or "").strip():
            raise PostingValidationError("Sports Cave Instagram identity is not configured.")
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

    def _ambiguous(self, submission_id, message, *, record=None):
        safe_error = sanitize_meta_error(message)
        result = self.store.update_stage(submission_id, "AMBIGUOUS", safe_error=safe_error)
        raise PostingAmbiguousError(safe_error, result=result or record)

    @staticmethod
    def _configured_status(row):
        return str(row.get("configured_status") or row.get("status") or "").upper()

    def _create_or_reconcile(self, create, reconcile, *, submission_id, entity):
        try:
            return str(create() or "")
        except MetaAdsAmbiguousResultError as error:
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

    def create_paused_campaign(self, request):
        clean = validate_posting_request(request)
        try:
            references, catalog, product_set, pixel, audience = self._validate_references(clean)
            existing_ad_names = tuple(self.client.existing_ad_names())
        except MetaAdsApiError as error:
            raise PostingError(sanitize_meta_error(error)) from error
        campaign_label = campaign_name(clean["product_title"], clean["country"], clean["sport"])
        audience_label = str(audience.get("name") or "Broad")
        adset_label = adset_name(clean["country"], clean["sport"], audience_label)
        ad_label = next_instant_experience_ad_name(clean["product_title"], existing_ad_names)
        fingerprint = _request_fingerprint(request, image_checksum=clean["image_checksum"])
        submission_id = str(request.submission_id)
        claim = self.store.claim(
            {
                "submission_id": submission_id, "request_fingerprint": fingerprint,
                "product_id": clean["product_id"], "product_title": clean["product_title"],
                "product_handle": clean["product_handle"], "country": clean["country"],
                "sport": clean["sport"], "catalog_id": clean["catalog_id"],
                "catalog_name": str(catalog.get("name") or ""),
                "product_set_id": clean["product_set_id"],
                "product_set_name": str(product_set.get("name") or ""),
                "audience_type": clean["audience_type"],
                "audience_id": str(audience.get("id") or ""), "audience_name": audience_label,
                "pixel_id": str(pixel.get("id") or ""), "pixel_name": str(pixel.get("name") or ""),
                "account_currency": str((references.get("account") or {}).get("currency") or ""),
                "campaign_name": campaign_label, "adset_name": adset_label, "ad_name": ad_label,
                "destination_url": clean["destination_url"], "image_checksum": clean["image_checksum"],
            },
            lease_token=str(uuid.uuid4()),
        )
        record = dict(claim.get("record") or {})
        if not claim.get("claimed"):
            status = str(record.get("status") or "")
            if status == "COMPLETE":
                return record
            if status == "AMBIGUOUS":
                raise PostingAmbiguousError(
                    str(record.get("safe_error") or "Meta did not confirm the earlier result."),
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
        ad_label = str(record.get("ad_name") or ad_label)

        try:
            campaign_id = str(record.get("campaign_id") or "")
            if not campaign_id:
                campaign_id = self._create_or_reconcile(
                    lambda: self.client.create_campaign(
                        build_campaign_payload(name=campaign_label, catalog_id=clean["catalog_id"])
                    ),
                    lambda: self.client.find_campaigns_by_name(campaign_label),
                    submission_id=submission_id, entity="campaign",
                )
                record = self.store.update_stage(
                    submission_id, "CAMPAIGN_CREATED", campaign_id=campaign_id,
                    campaign_name=campaign_label,
                )

            targeting = build_targeting(
                country=clean["country"], audience_type=clean["audience_type"], audience=audience
            )
            adset_id = str(record.get("adset_id") or "")
            if not adset_id:
                adset_id = self._create_or_reconcile(
                    lambda: self.client.create_adset(
                        build_adset_payload(
                            name=adset_label, campaign_id=campaign_id,
                            product_set_id=clean["product_set_id"], pixel_id=pixel["id"],
                            targeting=targeting,
                        )
                    ),
                    lambda: self.client.find_adsets_by_name(campaign_id, adset_label),
                    submission_id=submission_id, entity="ad set",
                )
                record = self.store.update_stage(
                    submission_id, "ADSET_CREATED", adset_id=adset_id, adset_name=adset_label
                )

            image_hash = str(record.get("meta_image_hash") or "")
            if not image_hash:
                try:
                    image_hash = self.client.upload_image(
                        clean["image"]["data"], filename=clean["image"]["upload_name"],
                        content_type=clean["image"]["content_type"],
                    )
                except MetaAdsAmbiguousResultError as error:
                    self._ambiguous(submission_id, error, record=record)
                record = self.store.update_stage(
                    submission_id, "IMAGE_UPLOADED", meta_image_hash=image_hash
                )

            page_photo_id = str(record.get("meta_page_photo_id") or "")
            if not page_photo_id:
                try:
                    page_photo_id = self.client.upload_page_photo(
                        clean["image"]["data"], filename=clean["image"]["upload_name"],
                        content_type=clean["image"]["content_type"],
                    )
                except MetaAdsAmbiguousResultError as error:
                    self._ambiguous(submission_id, error, record=record)
                record = self.store.update_stage(
                    submission_id, "PAGE_PHOTO_CREATED", meta_page_photo_id=page_photo_id
                )

            photo_element_id = str(record.get("meta_canvas_photo_element_id") or "")
            if not photo_element_id:
                storefront_specs = build_storefront_element_specs(
                    page_photo_id=page_photo_id, product_set_id=clean["product_set_id"],
                    destination_url=clean["destination_url"],
                )
                photo_element_id = self.client.create_canvas_element(
                    "canvas_photo", storefront_specs["canvas_photo"]
                )
                record = self.store.update_stage(
                    submission_id, "PAGE_PHOTO_CREATED",
                    meta_canvas_photo_element_id=photo_element_id,
                )
            product_element_id = str(record.get("meta_canvas_product_element_id") or "")
            if not product_element_id:
                storefront_specs = build_storefront_element_specs(
                    page_photo_id=page_photo_id, product_set_id=clean["product_set_id"],
                    destination_url=clean["destination_url"],
                )
                product_element_id = self.client.create_canvas_element(
                    "canvas_product_set", storefront_specs["canvas_product_set"]
                )
                record = self.store.update_stage(
                    submission_id, "PAGE_PHOTO_CREATED",
                    meta_canvas_product_element_id=product_element_id,
                )
            button_element_id = str(record.get("meta_canvas_button_element_id") or "")
            if not button_element_id:
                storefront_specs = build_storefront_element_specs(
                    page_photo_id=page_photo_id, product_set_id=clean["product_set_id"],
                    destination_url=clean["destination_url"],
                )
                button_element_id = self.client.create_canvas_element(
                    "canvas_button", storefront_specs["canvas_button"]
                )
                record = self.store.update_stage(
                    submission_id, "PAGE_PHOTO_CREATED",
                    meta_canvas_button_element_id=button_element_id,
                )
            footer_element_id = str(record.get("meta_canvas_footer_element_id") or "")
            if not footer_element_id:
                storefront_specs = build_storefront_element_specs(
                    page_photo_id=page_photo_id, product_set_id=clean["product_set_id"],
                    destination_url=clean["destination_url"], button_element_id=button_element_id,
                )
                footer_element_id = self.client.create_canvas_element(
                    "canvas_footer", storefront_specs["canvas_footer"]
                )
                record = self.store.update_stage(
                    submission_id, "PAGE_PHOTO_CREATED",
                    meta_canvas_footer_element_id=footer_element_id,
                )

            canvas_label = f"{ad_label} | Storefront"
            canvas_id = str(record.get("meta_instant_experience_id") or "")
            if not canvas_id:
                canvas_id = self._create_or_reconcile(
                    lambda: self.client.create_canvas(
                        name=canvas_label,
                        body_element_ids=(photo_element_id, product_element_id, footer_element_id),
                    ),
                    lambda: self.client.find_canvases_by_name(canvas_label),
                    submission_id=submission_id, entity="Instant Experience",
                )
                record = self.store.update_stage(
                    submission_id, "INSTANT_EXPERIENCE_CREATED",
                    meta_instant_experience_id=canvas_id,
                )

            creative_label = f"{ad_label} | Collection"
            creative_id = str(record.get("meta_creative_id") or "")
            if not creative_id:
                creative_id = self._create_or_reconcile(
                    lambda: self.client.create_collection_creative(
                        build_collection_creative_payload(
                            name=creative_label, page_id=self.client.page_id,
                            instagram_user_id=self.client.instagram_user_id,
                            image_hash=image_hash, canvas_id=canvas_id,
                            product_set_id=clean["product_set_id"],
                            destination_url=clean["destination_url"],
                            primary_text=clean["primary_text"], headline=clean["headline"],
                            description=clean["description"], url_tags=self.url_tags,
                        )
                    ),
                    lambda: self._one_match(self.client.find_creative_by_name(creative_label)),
                    submission_id=submission_id, entity="collection creative",
                )
                record = self.store.update_stage(
                    submission_id, "CREATIVE_CREATED", meta_creative_id=creative_id
                )

            ad_id = str(record.get("meta_ad_id") or "")
            if not ad_id:
                ad_id = self._create_or_reconcile(
                    lambda: self.client.create_paused_ad(
                        ad_name=ad_label, adset_id=adset_id, creative_id=creative_id
                    ),
                    lambda: self._one_match(
                        self.client.find_ad_by_creative(adset_id, creative_id)
                    ),
                    submission_id=submission_id, entity="ad",
                )
                record = self.store.update_stage(
                    submission_id, "AD_CREATED", meta_ad_id=ad_id
                )

            statuses = {
                "campaign": self._configured_status(self.client.configured_campaign(campaign_id)),
                "ad set": self._configured_status(self.client.configured_adset(adset_id)),
                "ad": self._configured_status(self.client.ad(ad_id)),
            }
            not_paused = [entity for entity, status in statuses.items() if status != "PAUSED"]
            if not_paused:
                self._ambiguous(
                    submission_id,
                    f"Meta did not confirm PAUSED status for: {', '.join(not_paused)}. Review in Ads Manager.",
                    record=record,
                )
            return self.store.update_stage(
                submission_id, "COMPLETE", campaign_id=campaign_id, adset_id=adset_id,
                ad_name=ad_label, meta_image_hash=image_hash,
                meta_page_photo_id=page_photo_id, meta_instant_experience_id=canvas_id,
                meta_creative_id=creative_id, meta_ad_id=ad_id, meta_status="PAUSED",
                safe_error="",
            )
        except (PostingAmbiguousError, PostingBusyError, PostingValidationError):
            raise
        except MetaAdsAmbiguousResultError as error:
            self._ambiguous(submission_id, error, record=record)
        except MetaAdsApiError as error:
            safe_error = sanitize_meta_error(error)
            result = self.store.update_stage(submission_id, "FAILED", safe_error=safe_error)
            raise PostingError(safe_error, result=result) from error
        except Exception as error:
            safe_error = (
                "The Meta request failed. Any objects already created remain paused and are listed below."
            )
            result = self.store.update_stage(submission_id, "FAILED", safe_error=safe_error)
            raise PostingError(safe_error, result=result) from error

    def create_paused_ad(self, request):
        """Compatibility alias for callers upgraded from Posting V1."""
        return self.create_paused_campaign(request)

    def recent_posts(self, limit=20):
        return self.store.recent(limit=limit)
