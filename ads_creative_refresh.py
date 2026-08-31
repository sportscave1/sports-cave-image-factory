from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import re
from datetime import date, datetime
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

import streamlit as st

from activity_log import record_activity_log
import ads_final_review
import ads_page
import dropbox_integration
import os_accounts
from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules
from ui_option_ordering import alphabetize_options


STATE_PREFIX = "ads_creative_refresh_"
RESULT_STATE_KEY = f"{STATE_PREFIX}result"
VALIDATION_STATE_KEY = f"{STATE_PREFIX}validation"
SAVE_STATE_KEY = f"{STATE_PREFIX}save"
PRODUCT_SELECTOR_KEY = f"{STATE_PREFIX}product_selector"
PRODUCT_URL_KEY = f"{STATE_PREFIX}product_url"
PRODUCT_AUTOFILL_IDENTITY_KEY = f"{STATE_PREFIX}product_autofill_identity"
PRODUCT_LAST_AUTO_URL_KEY = f"{STATE_PREFIX}product_last_auto_url"
PRODUCT_URL_MANUAL_KEY = f"{STATE_PREFIX}product_url_manual"
WINNING_CREATIVE_KEY = f"{STATE_PREFIX}winning_creative"
ORIGINAL_PROMPT_UPLOAD_KEY = f"{STATE_PREFIX}original_prompt_upload"
META_CSV_UPLOAD_KEY = f"{STATE_PREFIX}meta_csv_upload"
META_CSV_CONTAINER_KEY = f"{STATE_PREFIX}meta_csv_state"
CHALLENGER_CSV_UPLOAD_KEY = f"{STATE_PREFIX}challenger_csv_upload"
CHALLENGER_CSV_CONTAINER_KEY = f"{STATE_PREFIX}challenger_csv_state"
REVIEW_RESULT_STATE_KEY = f"{STATE_PREFIX}review_result_v2"
CHALLENGER_RESULT_STATE_KEY = f"{STATE_PREFIX}challenger_result_v2"
PROMPT_READY_CONTEXT_KEY = f"{STATE_PREFIX}review_prompt_ready_context_v2"

CREATIVE_REFRESH_VERSION = "SPORTS CAVE CREATIVE REFRESH V1"
CREATIVE_REFRESH_V2_VERSION = "SPORTS CAVE CREATIVE REFRESH V2"
CREATIVE_REFRESH_CSV_SCHEMA_VERSION = ads_page.STANDARD_ADS_CSV_SCHEMA_VERSION
CREATIVE_REFRESH_STRATEGIES = (
    "Winner Evolution",
    "Emotional / Collector Expansion",
    "Pattern Interrupt",
)
CREATIVE_REFRESH_CSV_HEADERS = ads_page.STANDARD_ADS_CSV_HEADERS
CREATIVE_REFRESH_REQUIRED_CSV_FIELDS = ads_page.STANDARD_ADS_CSV_REQUIRED_FIELDS
LEGACY_CREATIVE_REFRESH_CSV_SCHEMA_VERSION = "2"
LEGACY_CREATIVE_REFRESH_CSV_HEADERS = (
    "schema_version",
    "refresh_variant",
    "refresh_rank",
    "refresh_angle",
    "refresh_parent_product",
    "primary_text",
    "headline",
    "description",
    "cta",
    "on_image_headline",
    "supporting_line",
    "visual_concept",
    "composition",
    "product_placement",
    "environment_background",
    "lighting_mood",
    "text_placement",
    "hierarchy",
    "winner_keep",
    "winner_change",
    "test_reason",
    "image_prompt",
)
LEGACY_CREATIVE_REFRESH_REQUIRED_CSV_FIELDS = (
    "schema_version",
    "refresh_variant",
    "refresh_rank",
    "refresh_angle",
    "refresh_parent_product",
    "primary_text",
    "headline",
    "description",
    "cta",
    "visual_concept",
    "winner_keep",
    "winner_change",
    "test_reason",
    "image_prompt",
)
WINNING_ANGLE_OPTIONS = alphabetize_options((
    "Select emotional angle",
    "Nostalgia",
    "Scarcity",
    "Fan Identity",
    "Ownership and Display",
    "Legacy",
    "Rivalry",
    "Gifting",
    "Other",
))
PERFORMANCE_MODES = (
    "Manual metrics",
    "Meta CSV upload",
    "No metrics available",
)
AUDIENCE_TYPES = alphabetize_options(("Broad", "Interest", "Lookalike", "Retargeting", "Other"))
REFRESH_INTENSITIES = ("Balanced", "Conservative", "Bold")
PROTECTED_ELEMENTS = alphabetize_options((
    "Exact product and frame",
    "Proven emotional territory",
    "Premium Sports Cave positioning",
    "Product prominence",
    "Proven message hierarchy",
    "Verified scarcity facts",
    "Collector-led CTA intent",
    "Country localisation",
))
CONFOUNDERS = (
    "Price changed",
    "Offer changed",
    "Product page changed",
    "Checkout changed",
    "Audience changed",
    "Campaign objective or optimisation changed",
    "Placement mix changed",
    "Seasonal or event conditions changed",
    "Stock or delivery conditions changed",
)
REFRESH_ROUTES = (
    "Refresh 1 — Winner Evolution",
    "Refresh 2 — Scene Expansion",
    "Refresh 3 — Pattern Interrupt",
)
ROUTE_OUTPUT_FIELDS = (
    "Route name",
    "Strategic rationale",
    "What remained locked",
    "What changed",
    "Primary text",
    "Meta headline",
    "Meta description",
    "Meta CTA button",
    "Exact on-image headline",
    "Exact supporting line",
    "Exact on-image CTA",
    "Complete standalone image-generation prompt",
)

# Directional heuristics are intentionally conservative. They diagnose a pattern;
# they do not claim causation or predict that a challenger will win.
FATIGUE_THRESHOLDS = {
    "frequency_relative_rise": 0.20,
    "frequency_absolute_rise": 0.35,
    "frequency_large_absolute_rise": 0.75,
    "ctr_drop": -0.15,
    "cpa_rise": 0.20,
    "roas_drop": -0.20,
    "cpc_rise": 0.20,
    "cpm_context_rise": 0.20,
    "positive_counter_signal": 0.15,
}

METRIC_FIELDS = (
    ("spend", "Spend"),
    ("results", "Purchases or results"),
    ("purchase_value", "Purchase conversion value"),
    ("cpa", "Cost per result or CPA"),
    ("roas", "Purchase ROAS"),
    ("ctr", "Link CTR or outbound CTR (%)"),
    ("cpc", "CPC"),
    ("cpm", "CPM"),
    ("frequency", "Frequency"),
    ("reach", "Reach"),
    ("impressions", "Impressions"),
)

META_COLUMN_ALIASES = {
    "campaign_name": ("campaign name", "campaign"),
    "ad_set_name": ("ad set name", "adset name", "ad set"),
    "ad_name": ("ad name", "advert name", "ad"),
    "campaign_delivery": ("campaign delivery", "ad set delivery", "ad delivery", "delivery"),
    "date_start": ("reporting starts", "reporting start", "start date", "date start", "from"),
    "date_end": ("reporting ends", "reporting end", "end date", "date stop", "to"),
    "spend": ("amount spent", "spend", "total spent"),
    "purchase_results": ("website purchases", "purchases", "purchase"),
    "results": ("results", "results initial"),
    "result_indicator": ("result indicator", "results initial indicator"),
    "purchase_value": (
        "website purchase conversion value",
        "purchases conversion value",
        "purchase conversion value",
        "conversion value",
    ),
    "cpa": ("cost per purchase", "cost per results", "cost per result", "purchase cpa", "cpa"),
    "roas": (
        "website purchase roas return on ad spend",
        "purchase roas return on ad spend",
        "website purchase roas",
        "purchase roas",
        "roas",
    ),
    "ctr": (
        "ctr link click through rate",
        "outbound ctr",
        "link ctr",
        "ctr",
    ),
    "link_clicks": ("outbound clicks", "link clicks", "clicks all", "clicks"),
    "adds_to_cart": ("website adds to cart", "adds to cart", "add to cart"),
    "checkouts": ("checkouts initiated", "checkout initiated", "initiated checkouts"),
    "payment_info": ("adds of payment info", "payment info adds"),
    "cpc": ("cpc cost per link click", "cost per outbound click", "cost per link click", "cpc"),
    "cpm": ("cpm cost per 1 000 impressions", "cost per 1 000 impressions", "cpm"),
    "frequency": ("frequency",),
    "reach": ("reach",),
    "impressions": ("impressions",),
}

META_USEFUL_NUMERIC_FIELDS = (
    "spend",
    "results",
    "purchase_results",
    "purchase_value",
    "cpa",
    "roas",
    "ctr",
    "link_clicks",
    "cpc",
    "cpm",
    "frequency",
    "reach",
    "impressions",
    "adds_to_cart",
    "checkouts",
    "payment_info",
)


class CreativeRefreshValidationError(ValueError):
    pass


class MetaCSVValidationError(CreativeRefreshValidationError):
    pass


class CreativeRefreshSaveError(RuntimeError):
    pass


def _clean_text(value):
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _multiline_text(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _resolved_winning_angle(inputs):
    angle = _clean_text((inputs or {}).get("winning_emotional_angle"))
    if angle == "Other":
        return _clean_text((inputs or {}).get("winning_emotional_angle_other")) or "Other"
    return angle or "Not supplied"


def _normalise_header(value):
    text = str(value or "").strip().casefold()
    text = text.replace("%", " percent ").replace("&", " and ")
    text = re.sub(r"\([^)]*(?:aud|usd|cad|nzd|gbp)[^)]*\)", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def parse_metric_number(value, *, percentage=False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    text = str(value).strip().replace("\u00a0", "")
    if not text or text.casefold() in {"n/a", "na", "none", "null", "-", "--"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace(",", "").replace("%", "")
    text = re.sub(r"(?i)(aud|usd|cad|nzd|gbp)", "", text)
    text = re.sub(r"(?i)(?:a|us|ca|nz)?\$", "", text)
    text = re.sub(r"[$£€¥]", "", text).strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if negative:
        number *= -1
    if not math.isfinite(number):
        return None
    # CTR values are stored as percentage points: 2.4 means 2.4%, not 0.024.
    return number


def parse_metric_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def percentage_change(before, after):
    if before is None or after is None:
        return None
    before = float(before)
    after = float(after)
    if before == 0:
        return 0.0 if after == 0 else None
    return (after - before) / abs(before)


def derive_period_metrics(period):
    source = dict(period or {})
    result_indicator = _clean_text(source.get("result_indicator")).casefold()
    purchase_indicator = _result_indicator_semantic(result_indicator) == "purchase"
    explicit_purchase_results = parse_metric_number(source.get("purchase_results"))
    generic_results = parse_metric_number(source.get("results"))
    purchase_results = explicit_purchase_results
    if purchase_results is None and purchase_indicator:
        purchase_results = generic_results
    # Legacy manual-period callers did not supply an indicator. Keep their existing
    # result/CPA behaviour while campaign CSVs retain explicit result semantics.
    result_count_for_legacy_derivation = (
        purchase_results
        if purchase_results is not None
        else generic_results
        if not result_indicator
        else None
    )
    result = {
        "date_start": parse_metric_date(source.get("date_start")),
        "date_end": parse_metric_date(source.get("date_end")),
    }
    for key, _label in METRIC_FIELDS:
        result[key] = parse_metric_number(source.get(key), percentage=key == "ctr")
    result["results"] = generic_results if generic_results is not None else explicit_purchase_results
    result["purchase_results"] = purchase_results
    result["result_indicator"] = result_indicator
    result["result_semantic"] = _result_indicator_semantic(result_indicator)
    result["campaign_delivery"] = _clean_text(source.get("campaign_delivery")).casefold()
    result["link_clicks"] = parse_metric_number(source.get("link_clicks"))
    result["adds_to_cart"] = parse_metric_number(source.get("adds_to_cart"))
    result["checkouts"] = parse_metric_number(source.get("checkouts"))
    result["payment_info"] = parse_metric_number(source.get("payment_info"))
    result["campaign_name"] = _clean_text(source.get("campaign_name"))
    result["ad_set_name"] = _clean_text(source.get("ad_set_name"))
    result["ad_name"] = _clean_text(source.get("ad_name"))
    derived = []

    spend = result["spend"]
    results = result_count_for_legacy_derivation
    purchase_value = result["purchase_value"]
    clicks = result["link_clicks"]
    impressions = result["impressions"]
    reach = result["reach"]

    if result["cpa"] is None and spend is not None and results is not None and results > 0:
        result["cpa"] = spend / results
        derived.append("cpa")
    if result["roas"] is None and spend is not None and spend > 0 and purchase_value is not None:
        result["roas"] = purchase_value / spend
        derived.append("roas")
    if result["ctr"] is None and clicks is not None and impressions is not None and impressions > 0:
        result["ctr"] = (clicks / impressions) * 100
        derived.append("ctr")
    if result["cpc"] is None and spend is not None and clicks is not None and clicks > 0:
        result["cpc"] = spend / clicks
        derived.append("cpc")
    if result["cpm"] is None and spend is not None and impressions is not None and impressions > 0:
        result["cpm"] = (spend / impressions) * 1000
        derived.append("cpm")
    if result["frequency"] is None and impressions is not None and reach is not None and reach > 0:
        result["frequency"] = impressions / reach
        derived.append("frequency")
    result["derived_fields"] = tuple(derived)
    return result


def _result_indicator_semantic(value):
    indicator = _normalise_header(value)
    if not indicator:
        return "unknown"
    if "purchase" in indicator:
        return "purchase"
    if "link click" in indicator or indicator.endswith("click"):
        return "link_click"
    if indicator == "reach" or indicator.endswith(" reach"):
        return "reach"
    return "other"


def _header_matches_alias(header, alias):
    if header == alias:
        return True
    currency_suffixes = (" aud", " usd", " cad", " nzd", " gbp")
    return any(header == f"{alias}{suffix}" for suffix in currency_suffixes)


def _meta_csv_column_candidates(fieldnames):
    normalised = {field: _normalise_header(field) for field in (fieldnames or ()) if field}
    candidate_map = {}
    for canonical, aliases in META_COLUMN_ALIASES.items():
        candidates = []
        for alias_rank, alias in enumerate(aliases):
            normal_alias = _normalise_header(alias)
            for field, normal_field in normalised.items():
                if _header_matches_alias(normal_field, normal_alias):
                    candidates.append((alias_rank, field))
        if candidates:
            candidates.sort(key=lambda item: (item[0], str(item[1]).casefold()))
            distinct = []
            for _rank, field in candidates:
                if field not in distinct:
                    distinct.append(field)
            candidate_map[canonical] = tuple(distinct)
    return candidate_map


def map_meta_csv_columns(fieldnames):
    candidate_map = _meta_csv_column_candidates(fieldnames)
    mapped = {}
    warnings = []
    for canonical, distinct in candidate_map.items():
        mapped[canonical] = distinct[0]
        if len(distinct) > 1:
            warnings.append(
                f"Recognised multiple {canonical.replace('_', ' ')} columns; each row uses the first non-blank value by documented priority."
            )
    return mapped, warnings


def _meta_cell_is_missing(value):
    return _clean_text(value).casefold() in {"", "nan", "n/a", "na", "none", "null", "-", "--"}


def _decode_csv_bytes(data):
    source = bytes(data or b"")
    if not source:
        raise MetaCSVValidationError("The Meta CSV file is empty.")
    if len(source) > 5 * 1024 * 1024:
        raise MetaCSVValidationError("The Meta CSV file is too large. Upload a CSV under 5 MB.")
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return source.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise MetaCSVValidationError("The Meta CSV must be UTF-8 encoded.")


def parse_meta_ads_csv(data, *, filename="meta-export.csv"):
    if not str(filename or "").casefold().endswith(".csv"):
        raise MetaCSVValidationError("Upload a CSV file exported from Meta Ads Manager.")
    text = _decode_csv_bytes(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise MetaCSVValidationError("The Meta CSV has no header row.")

    column_map, warnings = map_meta_csv_columns(reader.fieldnames)
    column_candidates = _meta_csv_column_candidates(reader.fieldnames)
    mapped_metrics = [
        key
        for key in (
            "spend",
            "results",
            "purchase_results",
            "purchase_value",
            "cpa",
            "roas",
            "ctr",
            "link_clicks",
            "cpc",
            "cpm",
            "frequency",
            "reach",
            "impressions",
            "adds_to_cart",
            "checkouts",
            "payment_info",
        )
        if key in column_map
    ]
    if not mapped_metrics:
        raise MetaCSVValidationError(
            "Could not map any performance metrics. Include spend, results, ROAS, CTR, CPA, CPC, CPM, frequency, reach or impressions."
        )

    rows = []
    for source_index, raw in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        period = {}
        for canonical, source_columns in column_candidates.items():
            values = [raw.get(source_column) for source_column in source_columns]
            period[canonical] = next(
                (value for value in values if not _meta_cell_is_missing(value)),
                None,
            )
        derived = derive_period_metrics(period)
        raw_start = _clean_text(period.get("date_start"))
        raw_end = _clean_text(period.get("date_end"))
        if (raw_start and not derived["date_start"]) or (raw_end and not derived["date_end"]):
            warnings.append(
                f"Row {source_index} contains an unrecognised reporting date; its metrics were still imported."
            )
        identity = derived["ad_name"] or derived["ad_set_name"] or derived["campaign_name"] or "Unlabelled row"
        start_label = derived["date_start"].isoformat() if derived["date_start"] else "date unavailable"
        end_label = derived["date_end"].isoformat() if derived["date_end"] else "date unavailable"
        row_id = hashlib.sha256(
            json.dumps(
                {
                    "source_index": source_index,
                    "identity": identity,
                    "start": start_label,
                    "end": end_label,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        derived.update(
            {
                "row_id": row_id,
                "source_row": source_index,
                "label": (
                    f"{identity} | {start_label} to {end_label} | row {source_index}"
                ),
            }
        )
        rows.append(derived)
    if not rows:
        raise MetaCSVValidationError("The Meta CSV contains no data rows.")
    useful_metric_fields = tuple(
        field
        for field in META_USEFUL_NUMERIC_FIELDS
        if any(row.get(field) is not None for row in rows)
    )
    if not useful_metric_fields:
        raise MetaCSVValidationError(
            "The Meta CSV contains recognised metric columns, but no usable performance values."
        )
    if len(rows) < 2:
        warnings.append("At least two rows are needed to compare a winning period with a recent period.")
    report_level = (
        "ad"
        if "ad_name" in column_map
        else "ad set"
        if "ad_set_name" in column_map
        else "campaign"
        if "campaign_name" in column_map
        else "unknown"
    )
    spend_header = str(column_map.get("spend") or "")
    currency_match = re.search(r"\b(AUD|USD|CAD|NZD|GBP)\b", spend_header, flags=re.IGNORECASE)
    return {
        "rows": rows,
        "column_map": column_map,
        "column_candidates": column_candidates,
        "warnings": list(dict.fromkeys(warnings)),
        "requires_explicit_selection": len(rows) >= 2,
        "report_level": report_level,
        "row_count": len(rows),
        "named_row_count": sum(
            1
            for row in rows
            if row.get("ad_name") or row.get("ad_set_name") or row.get("campaign_name")
        ),
        "aggregate_row_count": sum(
            1
            for row in rows
            if not (row.get("ad_name") or row.get("ad_set_name") or row.get("campaign_name"))
        ),
        "currency": currency_match.group(1).upper() if currency_match else "",
        "useful_metric_fields": useful_metric_fields,
    }


def select_meta_csv_periods(parsed, winning_row_id, recent_row_id):
    rows = {row["row_id"]: row for row in (parsed or {}).get("rows", ())}
    if not winning_row_id or not recent_row_id:
        raise MetaCSVValidationError("Choose one CSV row for each comparison period.")
    if winning_row_id == recent_row_id:
        raise MetaCSVValidationError("Choose different CSV rows for the winning and recent periods.")
    if winning_row_id not in rows or recent_row_id not in rows:
        raise MetaCSVValidationError("A selected CSV row is no longer available. Re-select both periods.")
    return rows[winning_row_id], rows[recent_row_id]


def _first_row_text(row, *fields):
    row = row if isinstance(row, dict) else {}
    for field in fields:
        value = _clean_text(row.get(field))
        if value:
            return value
    return ""


def build_creative_refresh_product_context(selection):
    """Build prompt-safe product context from the canonical Ads/Edition Ops selection."""
    selection = dict(selection or {})
    row = dict(selection.get("row") or {})
    product_name = _first_row_text(
        row,
        "product_title",
        "Product title",
        "edition_name",
        "product_name",
        "title",
        "name",
    ) or _clean_text(selection.get("selected_label"))
    handle = _first_row_text(
        row,
        "shopify_handle",
        "Shopify handle",
        "product_handle",
        "handle",
        "Handle",
    )
    category = _first_row_text(
        row,
        "product_sport",
        "sport",
        "Sport",
        "sport_category",
        "category",
        "Category",
        "product_category",
    )
    country = _first_row_text(row, "country", "Country", "market", "Market")
    product_url = _clean_text(selection.get("product_url")) or _first_row_text(
        row,
        "online_store_url",
        "live_product_url",
        "product_page_url",
        "product_url",
        "storefront_url",
        "url",
    )
    asset_reference = _first_row_text(
        row,
        "image_url",
        "product_image_url",
        "source_image_url",
        "artwork_url",
        "psd_url",
    )
    metadata = ads_page.instant_experience_product_metadata_from_selection(
        selection,
        category=category,
    )
    return {
        "product_name": product_name,
        "handle": handle,
        "product_url": product_url,
        "category": category,
        "country": country,
        "product_id": _clean_text(selection.get("product_id")),
        "record_key": _clean_text(selection.get("record_key")),
        "product_type": _clean_text(metadata.get("product_type")),
        "collections": tuple(metadata.get("collections") or ()),
        "edition_limit": metadata.get("edition_limit"),
        "edition_limit_source": _clean_text(metadata.get("edition_limit_source")),
        "asset_reference": asset_reference,
    }


def validate_creative_refresh_v2_inputs(product_context, winning_primary_text, winning_headline):
    errors = []
    if not _clean_text((product_context or {}).get("product_name")):
        errors.append("Select a Sports Cave product.")
    if not _multiline_text(winning_primary_text):
        errors.append("Paste the winning primary text.")
    if not _clean_text(winning_headline):
        errors.append("Paste the winning headline.")
    return errors


def _sum_available(rows, key):
    values = [row.get(key) for row in rows if row.get(key) is not None]
    return math.fsum(float(value) for value in values) if values else None


def _product_match_tokens(product_context):
    candidates = (
        (product_context or {}).get("product_name"),
        (product_context or {}).get("handle"),
    )
    tokens = set()
    stop = {"the", "and", "wall", "art", "framed", "tribute", "edition", "limited"}
    for candidate in candidates:
        for token in _normalise_header(candidate).split():
            if len(token) >= 4 and token not in stop:
                tokens.add(token)
    return tokens


def _row_matches_product(row, product_context):
    campaign_text = _normalise_header(
        " ".join(
            str(row.get(field) or "")
            for field in ("campaign_name", "ad_set_name", "ad_name")
        )
    )
    tokens = _product_match_tokens(product_context)
    return bool(campaign_text and tokens and any(token in campaign_text.split() for token in tokens))


def _format_evidence_number(value, *, money=False, percent=False, ratio=False, currency=""):
    if value is None:
        return "not available"
    number = float(value)
    if money:
        prefix = f"{currency} " if currency else ""
        return f"{prefix}{number:,.2f}"
    if percent:
        return f"{number:,.2f}%"
    if ratio:
        return f"{number:,.2f}x"
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"


def build_meta_evidence_pack(parsed, product_context=None):
    if not parsed:
        return {
            "summary": "No Meta performance CSV was supplied. Treat all performance explanations as hypotheses to test.",
            "metrics": {},
            "applied": False,
            "relevant_rows": (),
            "context_rows": (),
            "limitations": (
                "No Meta performance evidence was supplied, so the attached creative and copy are the only winner evidence.",
            ),
        }

    rows = list(parsed.get("rows") or ())
    named_rows = [
        row
        for row in rows
        if row.get("campaign_name") or row.get("ad_set_name") or row.get("ad_name")
    ]
    evidence_rows = named_rows or rows
    currency = _clean_text(parsed.get("currency"))
    spend = _sum_available(evidence_rows, "spend")
    impressions = _sum_available(evidence_rows, "impressions")
    reach = _sum_available(evidence_rows, "reach")
    link_clicks = _sum_available(evidence_rows, "link_clicks")
    adds_to_cart = _sum_available(evidence_rows, "adds_to_cart")
    checkouts = _sum_available(evidence_rows, "checkouts")
    purchases = _sum_available(evidence_rows, "purchase_results")
    purchase_value = _sum_available(evidence_rows, "purchase_value")
    ctr = (
        (link_clicks / impressions) * 100
        if link_clicks is not None and impressions and impressions > 0
        else None
    )
    cpc = spend / link_clicks if spend is not None and link_clicks and link_clicks > 0 else None
    cpm = (spend / impressions) * 1000 if spend is not None and impressions and impressions > 0 else None
    frequency = impressions / reach if impressions is not None and reach and reach > 0 else None
    roas = purchase_value / spend if purchase_value is not None and spend and spend > 0 else None
    if roas is None:
        weighted_roas = [
            (row.get("roas"), row.get("spend"))
            for row in evidence_rows
            if row.get("roas") is not None and row.get("spend") is not None and row.get("spend") > 0
        ]
        if weighted_roas:
            roas = sum(float(value) * float(weight) for value, weight in weighted_roas) / sum(
                float(weight) for _value, weight in weighted_roas
            )

    metrics = {
        "spend": spend,
        "impressions": impressions,
        "reach": reach,
        "frequency": frequency,
        "ctr": ctr,
        "cpc": cpc,
        "cpm": cpm,
        "link_clicks": link_clicks,
        "purchases": purchases,
        "roas": roas,
        "adds_to_cart": adds_to_cart,
        "checkouts": checkouts,
    }
    relevant_rows = [row for row in evidence_rows if _row_matches_product(row, product_context or {})]
    relevant_rows.sort(key=lambda row: float(row.get("spend") or 0), reverse=True)
    context_rows = sorted(
        evidence_rows,
        key=lambda row: (
            float(row.get("spend") or 0),
            float(row.get("purchase_results") or 0),
        ),
        reverse=True,
    )[:3]
    report_level = parsed.get("report_level") or "unknown"
    limitations = [
        f"The uploaded Meta file is {report_level}-level. These metrics provide campaign/account context; they cannot by themselves prove the exact ad-level performance of the attached creative."
    ]
    if parsed.get("aggregate_row_count"):
        limitations.append(
            "Blank-name aggregate rows were accepted but excluded from totals when named rows were available, preventing double counting."
        )
    if not relevant_rows:
        limitations.append(
            "No reliable product-name or handle match was found in campaign/ad-set/ad names, so no row is attributed to the selected product."
        )
    if any(
        row.get("results") is not None and row.get("purchase_results") is None
        for row in evidence_rows
    ):
        limitations.append(
            "Generic Results values whose Result indicator was not purchase were not counted as purchases."
        )

    lines = [
        f"Import: {len(rows)} rows ({parsed.get('named_row_count', 0)} named; {parsed.get('aggregate_row_count', 0)} blank-name aggregate), detected at {report_level} level.",
        "Overall row-level context (blank-name aggregate excluded when named rows exist):",
        f"- Spend: {_format_evidence_number(spend, money=True, currency=currency)}",
        f"- Impressions: {_format_evidence_number(impressions)}",
        f"- Reported reach sum: {_format_evidence_number(reach)}",
        f"- Derived frequency context: {_format_evidence_number(frequency)}",
        f"- Link clicks: {_format_evidence_number(link_clicks)}",
        f"- Derived link CTR: {_format_evidence_number(ctr, percent=True)}",
        f"- Derived CPC: {_format_evidence_number(cpc, money=True, currency=currency)}",
        f"- Derived CPM: {_format_evidence_number(cpm, money=True, currency=currency)}",
        f"- Purchase-semantic results only: {_format_evidence_number(purchases)}",
        f"- Purchase ROAS context: {_format_evidence_number(roas, ratio=True)}",
        f"- Adds to cart: {_format_evidence_number(adds_to_cart)}",
        f"- Checkouts initiated: {_format_evidence_number(checkouts)}",
    ]
    if relevant_rows:
        lines.append("Likely product-name/handle matches (context only):")
        for row in relevant_rows[:3]:
            identity = row.get("ad_name") or row.get("ad_set_name") or row.get("campaign_name") or "Unlabelled"
            lines.append(
                f"- {identity}: spend {_format_evidence_number(row.get('spend'), money=True, currency=currency)}, "
                f"purchases {_format_evidence_number(row.get('purchase_results'))}, ROAS {_format_evidence_number(row.get('roas'), ratio=True)}."
            )
    lines.append("Highest-spend context rows:")
    for row in context_rows:
        identity = row.get("ad_name") or row.get("ad_set_name") or row.get("campaign_name") or "Unlabelled"
        indicator = row.get("result_indicator") or "not supplied"
        lines.append(
            f"- {identity}: spend {_format_evidence_number(row.get('spend'), money=True, currency=currency)}, "
            f"results {_format_evidence_number(row.get('results'))} ({indicator}), CTR {_format_evidence_number(row.get('ctr'), percent=True)}."
        )
    lines.append("Evidence limitations:")
    lines.extend(f"- {limitation}" for limitation in limitations)
    return {
        "summary": "\n".join(lines),
        "metrics": metrics,
        "applied": bool(parsed.get("useful_metric_fields")),
        "relevant_rows": tuple(relevant_rows[:3]),
        "context_rows": tuple(context_rows),
        "limitations": tuple(limitations),
    }


def _product_context_prompt_lines(product_context):
    context = dict(product_context or {})
    rows = [f"- Canonical product: {context.get('product_name') or 'not available'}"]
    optional = (
        ("Handle", context.get("handle")),
        ("Product page URL", context.get("product_url")),
        ("Sport/category", context.get("category")),
        ("Product type", context.get("product_type")),
        ("Stored market", context.get("country")),
        ("Edition limit", context.get("edition_limit")),
        ("Edition evidence source", context.get("edition_limit_source")),
        ("Existing exact product asset reference", context.get("asset_reference")),
    )
    rows.extend(f"- {label}: {value}" for label, value in optional if value not in (None, "", ()))
    if context.get("collections"):
        rows.append(f"- Collections: {', '.join(context['collections'])}")
    return "\n".join(rows)


def build_creative_refresh_review_prompt(
    product_context,
    winning_primary_text,
    winning_headline,
    *,
    meta_evidence=None,
):
    evidence = meta_evidence or build_meta_evidence_pack(None, product_context)
    csv_header = ",".join(ads_page.STANDARD_ADS_CSV_HEADERS)
    strategies = "\n".join(
        f"{index}. {strategy}" for index, strategy in enumerate(CREATIVE_REFRESH_STRATEGIES, start=1)
    )
    standard_output_contract = ads_page.build_standard_ads_output_contract(
        strategies=CREATIVE_REFRESH_STRATEGIES,
    )
    standard_image_requirements = ads_page.build_standard_ads_image_prompt_requirements(
        (product_context or {}).get("product_name"),
        (product_context or {}).get("category"),
        (product_context or {}).get("country"),
    )
    return f"""==================================================
SPORTS CAVE — CREATIVE REFRESH ANALYSIS
==================================================

Attach the actual winning ad creative image and the empty Sports Cave Ads CSV supplied by Sports Cave OS to this ChatGPT conversation before running this prompt.

The selected Sports Cave product/artwork is the immutable product identity. The manually attached winning ad image is a creative/composition reference only. Never replace the exact product artwork with imagery extracted or reconstructed from the winning advertisement.

Your job is to study a proven Sports Cave advertisement and develop THREE upgraded controlled challenger ads that preserve the winning DNA without merely duplicating it.

PRODUCT CONTEXT
{_product_context_prompt_lines(product_context)}

WINNER INPUT
Winning primary text:
{_multiline_text(winning_primary_text)}

Winning headline:
{_clean_text(winning_headline)}

PERFORMANCE EVIDENCE
{evidence.get('summary') or 'No Meta evidence supplied.'}

ANALYSIS REQUIREMENTS

1. Inspect the attached winning creative carefully. Analyse layout, hierarchy, product prominence, framing, room/environment, colour contrast, text placement, headline visibility, amount of copy, social-feed stopping power, collector appeal, emotional trigger, scarcity treatment, credibility, visual simplicity, mobile readability, likely attention mechanism, possible weaknesses and what must not be lost.

2. Analyse the winning primary text and headline. Determine the hook, emotion, collector motivation, scarcity/FOMO mechanism, fan identity, nostalgia, urgency, product clarity, CTA strength and message-match with the creative.

3. Analyse supplied Meta metrics when available. Use actual evidence rather than guessing. Consider CTR, CPC, CPM, frequency, spend, purchase-semantic results, ROAS, adds to cart, checkouts and plausible deterioration/fatigue signals. Clearly label every important claim as FACT, INFERENCE or HYPOTHESIS. Never treat a generic Results value as a purchase unless its Result indicator proves purchase semantics.

4. Research the product, athlete/team/sport and fan context where useful. Use current web research where appropriate. Research fan identity, collector motivations, relevant sports history, emotional hooks, audience language, competing creative patterns and what makes the product compelling today. Do not change verified sports facts.

5. Diagnose why the winner likely worked without claiming certainty. Return a concise WINNER DNA section with KEEP, IMPROVE, REMOVE and TEST.

6. Analyse the most plausible audience motivations, such as die-hard fan identity, nostalgia, gifting, collecting, legacy/status, man-cave/home decor and verified limited-edition scarcity. Do not claim Meta targeting data exists unless it is actually present.

7. Build exactly THREE refreshed challengers. All must remain recognisably derived from the winner and be controlled enough to learn from:
{strategies}

- Winner Evolution is the closest, lowest-risk evolution and fixes the weakest elements.
- Emotional / Collector Expansion preserves core visual DNA while strengthening the emotional or collector reason to care.
- Pattern Interrupt is the boldest evolution, with a stronger visual/message hook while retaining product and winner lineage.

For each challenger create the standard Sports Cave Ads production fields shown below. The analysis may explain the angle, what is retained, what changes and why the challenger deserves a test, but those analysis headings must not replace or rename the production fields.

All creative must be premium, realistic, Sports Cave branded, mobile-first, uncluttered, Meta-suitable, emotionally compelling, focused on the exact product, believable rather than AI-looking and controlled enough to learn from. Do not create fake reviews, facts, product claims, scarcity numbers or offers.

8. Rank all three challengers #1, #2 and #3, with a brief test-order reason.

9. After completing the concise analysis, switch to the standard SPORTS CAVE ADS OUTPUT FORMAT below. Do not invent a Creative Refresh-specific schema, alternative ad headings or replacement production fields. The strategy names are analysis/internal metadata only; they do not replace Primary Text, Headline, Description, CTA or Image Generation Prompt.

STANDARD SPORTS CAVE ADS OUTPUT FORMAT — EXACT

{standard_output_contract}

Every field must be complete. Preserve intentional paragraph breaks in Primary Text. Do not return placeholders such as TBD, N/A, same as previous or see above.

10. Return exactly THREE complete standalone Image Generation Prompts — one inside each standard ad. Each prompt must be independently usable in a fresh image-generation conversation and must repeat all relevant technical, product-lock, realism, layout, mobile-readability and brand requirements in full. The three prompts must be meaningfully different while following the controlled strategy order above.

{standard_image_requirements}

11. Populate the attached empty Sports Cave Ads CSV with the same three ads and return the completed CSV as a downloadable .csv file. The readable three-ad response and CSV must contain the same production data and must not contradict each other.

CSV CONTRACT — EXACT
- Schema version: {CREATIVE_REFRESH_CSV_SCHEMA_VERSION}
- Exactly three data rows, in this exact strategy order: {', '.join(CREATIVE_REFRESH_STRATEGIES)}.
- Populate the supplied empty Sports Cave Ads CSV. Preserve every header and identity cell already present.
- Use this exact canonical Sports Cave Ads header row and no extra columns:
{csv_header}
- ad_number must remain 1, 2 and 3 in row order.
- product_name must remain exactly: {product_context.get('product_name') or ''}
- strategy must remain in this order: {', '.join(CREATIVE_REFRESH_STRATEGIES)}.
- Required non-empty fields: {', '.join(CREATIVE_REFRESH_REQUIRED_CSV_FIELDS)}.
- Quote fields correctly. Preserve commas and line breaks inside quoted fields. Do not put Markdown formatting inside CSV fields.
- image_prompt must be complete and standalone. It must preserve the exact selected Sports Cave product identity and must not depend on another row or prompt.
- Do not rename, add or remove columns. Do not leave placeholders. Fill every required field.
- Return the populated supplied CSV as a downloadable file, not a Markdown approximation of a CSV.

Return the concise CREATIVE REFRESH ANALYSIS and WINNER DNA first, then the THREE STANDARD SPORTS CAVE ADS in the exact format above, then the downloadable completed CSV. Do not generate any image until explicitly asked in ChatGPT.
""".strip()


def _normalised_csv_header_map(headers):
    mapped = {}
    duplicates = []
    for header in headers or ():
        normal = _normalise_header(header)
        if normal in mapped:
            duplicates.append(str(header))
        mapped[normal] = header
    return mapped, duplicates


def _canonical_refresh_strategy(value):
    normal = _normalise_header(value)
    aliases = {
        "winner evolution": CREATIVE_REFRESH_STRATEGIES[0],
        "emotional collector expansion": CREATIVE_REFRESH_STRATEGIES[1],
        "emotional expansion": CREATIVE_REFRESH_STRATEGIES[1],
        "pattern interrupt": CREATIVE_REFRESH_STRATEGIES[2],
    }
    return aliases.get(normal, "")


def _parse_legacy_creative_refresh_challenger_csv(
    data,
    *,
    product_name="",
    filename="creative-refresh.csv",
):
    if not str(filename or "").casefold().endswith(".csv"):
        raise CreativeRefreshValidationError("Upload the ChatGPT Refresh CSV as a .csv file.")
    source = bytes(data or b"")
    if not source:
        raise CreativeRefreshValidationError("Choose the ChatGPT Refresh CSV.")
    if len(source) > 2 * 1024 * 1024:
        raise CreativeRefreshValidationError("The ChatGPT Refresh CSV must be smaller than 2 MB.")
    try:
        decoded = source.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CreativeRefreshValidationError("Save the ChatGPT Refresh CSV as UTF-8 and try again.") from error
    if "\x00" in decoded:
        raise CreativeRefreshValidationError("The ChatGPT Refresh CSV contains invalid text data.")
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        headers = list(reader.fieldnames or ())
        header_map, duplicate_headers = _normalised_csv_header_map(headers)
        if duplicate_headers:
            raise CreativeRefreshValidationError("The ChatGPT Refresh CSV contains duplicate column headers.")
        missing = [
            header
            for header in LEGACY_CREATIVE_REFRESH_CSV_HEADERS
            if _normalise_header(header) not in header_map
        ]
        if missing:
            raise CreativeRefreshValidationError(
                "The ChatGPT Refresh CSV is missing required columns: " + ", ".join(missing) + "."
            )
        unexpected = [
            header
            for header in headers
            if _normalise_header(header)
            not in {_normalise_header(expected) for expected in LEGACY_CREATIVE_REFRESH_CSV_HEADERS}
        ]
        if unexpected:
            raise CreativeRefreshValidationError(
                "The ChatGPT Refresh CSV contains unexpected columns: " + ", ".join(unexpected) + "."
            )
        raw_rows = []
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise CreativeRefreshValidationError(
                    f"ChatGPT Refresh CSV row {row_number} has an unexpected or missing value. Check its quoting."
                )
            if any(_multiline_text(value) for value in row.values()):
                raw_rows.append(row)
    except CreativeRefreshValidationError:
        raise
    except (csv.Error, AttributeError) as error:
        raise CreativeRefreshValidationError(
            "The ChatGPT Refresh CSV could not be read. Check its quoting and line breaks."
        ) from error
    if len(raw_rows) != 3:
        raise CreativeRefreshValidationError(
            f"Creative Refresh expects exactly 3 challenger rows; this file contains {len(raw_rows)}."
        )

    challengers = []
    expected_product = _clean_text(product_name)
    for index, raw in enumerate(raw_rows, start=1):
        row = {
            expected: _multiline_text(raw.get(header_map[_normalise_header(expected)]))
            for expected in LEGACY_CREATIVE_REFRESH_CSV_HEADERS
        }
        missing_values = [
            field
            for field in LEGACY_CREATIVE_REFRESH_REQUIRED_CSV_FIELDS
            if not row.get(field)
        ]
        if missing_values:
            raise CreativeRefreshValidationError(
                f"Challenger row {index} is missing required values: {', '.join(missing_values)}."
            )
        if row["schema_version"] != LEGACY_CREATIVE_REFRESH_CSV_SCHEMA_VERSION:
            raise CreativeRefreshValidationError(
                f"Challenger row {index} has schema_version {row['schema_version']!r}; expected {LEGACY_CREATIVE_REFRESH_CSV_SCHEMA_VERSION}."
            )
        strategy = _canonical_refresh_strategy(row["refresh_variant"])
        expected_strategy = CREATIVE_REFRESH_STRATEGIES[index - 1]
        if strategy != expected_strategy:
            raise CreativeRefreshValidationError(
                f"Challenger row {index} must use refresh_variant {expected_strategy!r}."
            )
        try:
            rank = int(row["refresh_rank"])
        except ValueError as error:
            raise CreativeRefreshValidationError(
                f"Challenger row {index} refresh_rank must be {index}."
            ) from error
        if rank != index:
            raise CreativeRefreshValidationError(
                f"Challenger row {index} refresh_rank must be {index}."
            )
        if expected_product and _normalise_header(row["refresh_parent_product"]) != _normalise_header(expected_product):
            raise CreativeRefreshValidationError(
                f"Challenger row {index} refresh_parent_product must match the selected product: {expected_product}."
            )
        row["refresh_variant"] = strategy
        row["refresh_rank"] = rank
        row["refresh_parent_product"] = expected_product or row["refresh_parent_product"]
        challengers.append(row)
    return tuple(challengers)


def _normalise_creative_refresh_ad(raw_ad, index, *, product_name=""):
    raw_ad = dict(raw_ad or {})
    clean_product = _clean_text(
        product_name
        or raw_ad.get("product_name")
        or raw_ad.get("refresh_parent_product")
    )
    strategy = _clean_text(
        raw_ad.get("strategy")
        or raw_ad.get("refresh_variant")
        or (CREATIVE_REFRESH_STRATEGIES[index - 1] if index <= len(CREATIVE_REFRESH_STRATEGIES) else "")
    )
    try:
        ad_number = int(raw_ad.get("ad_number") or raw_ad.get("refresh_rank") or index)
    except (TypeError, ValueError):
        ad_number = index
    return {
        "schema_version": CREATIVE_REFRESH_CSV_SCHEMA_VERSION,
        "ad_number": ad_number,
        "product_name": clean_product,
        "strategy": strategy,
        "primary_text": _multiline_text(raw_ad.get("primary_text")),
        "headline": _multiline_text(raw_ad.get("headline")),
        "description": _multiline_text(raw_ad.get("description")),
        "cta": _multiline_text(raw_ad.get("cta")),
        "image_prompt": _multiline_text(
            raw_ad.get("image_prompt") or raw_ad.get("image_generation_prompt")
        ),
    }


def parse_creative_refresh_challenger_csv(data, *, product_name="", filename="creative-refresh.csv"):
    source = bytes(data or b"")
    try:
        decoded = source.decode("utf-8-sig")
        headers = list(csv.DictReader(io.StringIO(decoded, newline="")).fieldnames or ())
    except (UnicodeDecodeError, csv.Error, AttributeError):
        headers = []
    normalized_headers = {_normalise_header(header) for header in headers}
    legacy_headers = {_normalise_header(header) for header in LEGACY_CREATIVE_REFRESH_CSV_HEADERS}
    if normalized_headers == legacy_headers:
        legacy_rows = _parse_legacy_creative_refresh_challenger_csv(
            source,
            product_name=product_name,
            filename=filename,
        )
        return tuple(
            _normalise_creative_refresh_ad(row, index, product_name=product_name)
            for index, row in enumerate(legacy_rows, start=1)
        )
    try:
        return ads_page.parse_standard_ads_csv(
            source,
            product_name=product_name,
            expected_rows=len(CREATIVE_REFRESH_STRATEGIES),
            strategies=CREATIVE_REFRESH_STRATEGIES,
            filename=filename,
        )
    except ads_page.StandardAdsCSVError as error:
        raise CreativeRefreshValidationError(str(error)) from error


def build_creative_refresh_challenger_csv(challengers):
    rows = [
        _normalise_creative_refresh_ad(challenger, index)
        for index, challenger in enumerate(challengers or (), start=1)
    ]
    return ads_page.build_standard_ads_csv(rows)


def build_creative_refresh_empty_csv(product_context):
    return ads_page.build_standard_ads_csv(
        product_name=(product_context or {}).get("product_name"),
        strategies=CREATIVE_REFRESH_STRATEGIES,
        row_count=len(CREATIVE_REFRESH_STRATEGIES),
    )


def build_creative_refresh_ads_result(
    product_context,
    challengers,
    csv_data,
    *,
    review_context_key="",
):
    standard_ads = tuple(
        _normalise_creative_refresh_ad(
            challenger,
            index,
            product_name=(product_context or {}).get("product_name"),
        )
        for index, challenger in enumerate(challengers or (), start=1)
    )
    canonical_csv = build_creative_refresh_challenger_csv(standard_ads)
    context_payload = {
        "version": CREATIVE_REFRESH_V2_VERSION,
        "product_id": (product_context or {}).get("product_id"),
        "record_key": (product_context or {}).get("record_key"),
        "csv_hash": hashlib.sha256(canonical_csv).hexdigest(),
        "review_context_key": str(review_context_key or ""),
    }
    context_key = hashlib.sha256(
        json.dumps(context_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    category = _clean_text((product_context or {}).get("category")) or "Other"
    country = _clean_text((product_context or {}).get("country")) or "Unspecified"
    return {
        "context_key": f"creative-refresh::{context_key}",
        "product_name": _clean_text((product_context or {}).get("product_name")),
        "product_id": _clean_text((product_context or {}).get("product_id")),
        "record_key": _clean_text((product_context or {}).get("record_key")),
        "category": category,
        "country": country,
        "campaign_type": "Creative Refresh",
        "product_url": _clean_text((product_context or {}).get("product_url")),
        "campaign_moment": ads_page.empty_campaign_moment(),
        "source": "Creative Refresh",
        "source_review_context_key": str(review_context_key or ""),
        "parent_product": _clean_text((product_context or {}).get("product_name")),
        "standard_ads": standard_ads,
        "refresh_challengers": standard_ads,
        "creative_refresh_csv": bytes(csv_data or canonical_csv),
        "creative_refresh_canonical_csv": canonical_csv,
    }


def creative_refresh_setup_notes(challengers):
    sections = []
    for index, raw_challenger in enumerate(challengers or (), start=1):
        challenger = _normalise_creative_refresh_ad(raw_challenger, index)
        sections.extend(
            [
                f"AD {challenger.get('ad_number')}: {challenger.get('strategy')}",
                f"Primary text: {challenger.get('primary_text')}",
                f"Headline: {challenger.get('headline')}",
                f"Description: {challenger.get('description')}",
                f"CTA: {challenger.get('cta')}",
                f"Image prompt: {challenger.get('image_prompt')}",
                "",
            ]
        )
    return "\n".join(sections).strip()


def _metric_change_row(metric, label, winning, recent):
    before = winning.get(metric)
    after = recent.get(metric)
    change = percentage_change(before, after)
    if before is None or after is None:
        direction = "Unavailable"
    elif after > before:
        direction = "Up"
    elif after < before:
        direction = "Down"
    else:
        direction = "Flat"
    return {
        "metric": metric,
        "label": label,
        "winning": before,
        "recent": after,
        "absolute_change": None if before is None or after is None else after - before,
        "percentage_change": change,
        "direction": direction,
    }


def diagnose_creative_fatigue(winning_period=None, recent_period=None, *, confounders=()):
    winning = derive_period_metrics(winning_period or {})
    recent = derive_period_metrics(recent_period or {})
    labels = dict(METRIC_FIELDS)
    compared_metrics = ("frequency", "ctr", "cpa", "roas", "cpc", "cpm")
    changes = {
        metric: _metric_change_row(metric, labels[metric], winning, recent)
        for metric in compared_metrics
    }
    paired_count = sum(
        1
        for change in changes.values()
        if change["winning"] is not None and change["recent"] is not None
    )
    frequency = changes["frequency"]
    frequency_delta = frequency["absolute_change"]
    frequency_pct = frequency["percentage_change"]
    frequency_rise = bool(
        frequency_delta is not None
        and frequency_delta > 0
        and (
            (
                frequency_delta >= FATIGUE_THRESHOLDS["frequency_absolute_rise"]
                and frequency_pct is not None
                and frequency_pct >= FATIGUE_THRESHOLDS["frequency_relative_rise"]
            )
            or frequency_delta >= FATIGUE_THRESHOLDS["frequency_large_absolute_rise"]
        )
    )

    negative_signals = []
    if changes["ctr"]["percentage_change"] is not None and changes["ctr"]["percentage_change"] <= FATIGUE_THRESHOLDS["ctr_drop"]:
        negative_signals.append("Link CTR fell meaningfully")
    if changes["cpa"]["percentage_change"] is not None and changes["cpa"]["percentage_change"] >= FATIGUE_THRESHOLDS["cpa_rise"]:
        negative_signals.append("CPA rose meaningfully")
    if changes["roas"]["percentage_change"] is not None and changes["roas"]["percentage_change"] <= FATIGUE_THRESHOLDS["roas_drop"]:
        negative_signals.append("ROAS fell meaningfully")
    if changes["cpc"]["percentage_change"] is not None and changes["cpc"]["percentage_change"] >= FATIGUE_THRESHOLDS["cpc_rise"]:
        negative_signals.append("CPC rose meaningfully")

    counter_signals = []
    counter_threshold = FATIGUE_THRESHOLDS["positive_counter_signal"]
    if changes["ctr"]["percentage_change"] is not None and changes["ctr"]["percentage_change"] >= counter_threshold:
        counter_signals.append("Link CTR improved")
    if changes["cpa"]["percentage_change"] is not None and changes["cpa"]["percentage_change"] <= -counter_threshold:
        counter_signals.append("CPA improved")
    if changes["roas"]["percentage_change"] is not None and changes["roas"]["percentage_change"] >= counter_threshold:
        counter_signals.append("ROAS improved")
    if changes["cpc"]["percentage_change"] is not None and changes["cpc"]["percentage_change"] <= -counter_threshold:
        counter_signals.append("CPC improved")

    cpm_change = changes["cpm"]["percentage_change"]
    cpm_context = bool(
        cpm_change is not None and cpm_change >= FATIGUE_THRESHOLDS["cpm_context_rise"]
    )
    if paired_count < 2:
        classification = "Insufficient Evidence"
    elif frequency_rise and len(negative_signals) >= 2:
        classification = "Likely Creative Fatigue"
    elif negative_signals and counter_signals:
        classification = "Mixed Signals"
    elif (frequency_rise and negative_signals) or len(negative_signals) >= 2:
        classification = "Possible Creative Fatigue"
    else:
        classification = "Probably Not Primarily Creative Fatigue"

    selected_confounders = tuple(_clean_text(item) for item in confounders if _clean_text(item))
    original_classification = classification
    if selected_confounders:
        classification = {
            "Likely Creative Fatigue": "Possible Creative Fatigue",
            "Possible Creative Fatigue": "Mixed Signals",
            "Probably Not Primarily Creative Fatigue": "Mixed Signals",
        }.get(classification, classification)

    notes = []
    if frequency_rise:
        notes.append("Frequency rose meaningfully.")
    if negative_signals:
        notes.append("; ".join(negative_signals) + ".")
    if counter_signals:
        notes.append("Counter-signals: " + "; ".join(counter_signals) + ".")
    if cpm_context:
        notes.append("CPM also rose meaningfully, so auction cost is a material alternative explanation.")
    if selected_confounders:
        notes.append(
            "Confounders are present; the performance change cannot be attributed solely to creative fatigue."
        )
    if not notes:
        notes.append("The available comparison does not show a strong creative-fatigue pattern.")
    return {
        "classification": classification,
        "classification_before_confounders": original_classification,
        "frequency_rise": frequency_rise,
        "negative_signals": tuple(negative_signals),
        "counter_signals": tuple(counter_signals),
        "cpm_context": cpm_context,
        "confounders": selected_confounders,
        "changes": changes,
        "paired_metric_count": paired_count,
        "summary": " ".join(notes),
        "thresholds": dict(FATIGUE_THRESHOLDS),
        "winning_period": winning,
        "recent_period": recent,
    }


def format_metric(value, metric=""):
    if value is None:
        return "Not supplied"
    if metric == "ctr":
        return f"{value:.2f}%"
    if metric in {"spend", "purchase_value", "cpa", "cpc", "cpm"}:
        return f"{value:.2f}"
    if metric in {"reach", "impressions", "results", "link_clicks"}:
        return f"{value:,.0f}"
    return f"{value:.2f}"


def build_performance_evidence_summary(diagnosis):
    diagnosis = dict(diagnosis or {})
    lines = [
        f"Diagnosis: {diagnosis.get('classification') or 'Insufficient Evidence'}",
        f"Evidence note: {diagnosis.get('summary') or 'No comparable metrics supplied.'}",
    ]
    changes = diagnosis.get("changes") or {}
    for metric in ("frequency", "ctr", "cpa", "roas", "cpc", "cpm"):
        change = changes.get(metric) or {}
        if change.get("winning") is None or change.get("recent") is None:
            continue
        pct = change.get("percentage_change")
        pct_text = "percentage unavailable from a zero baseline" if pct is None else f"{pct * 100:+.1f}%"
        lines.append(
            f"- {change.get('label')}: {format_metric(change.get('winning'), metric)} -> "
            f"{format_metric(change.get('recent'), metric)} ({pct_text}; {change.get('direction')})"
        )
    confounders = diagnosis.get("confounders") or ()
    lines.append("Confounders: " + (", ".join(confounders) if confounders else "None supplied"))
    lines.append("CPM is diagnostic context, not proof that creative is the primary cause.")
    return "\n".join(lines)


def build_input_summary(inputs):
    inputs = dict(inputs or {})
    moment = ads_page.normalize_campaign_moment(
        inputs.get("campaign_moment"),
        selected_country=inputs.get("country"),
    )
    lines = [
        f"Product: {inputs.get('product_name') or 'Not supplied'}",
        f"Category: {inputs.get('category') or 'Not supplied'}",
        f"Country: {inputs.get('country') or 'Not supplied'}",
        f"Campaign type: {inputs.get('campaign_type') or 'Not supplied'}",
        f"Product page URL: {inputs.get('product_url') or 'Not supplied'}",
        f"Exact product source URL: {inputs.get('product_source_url') or 'Attach the exact source manually'}",
        f"Winning emotional angle: {_resolved_winning_angle(inputs)}",
        f"Winning primary text: {_multiline_text(inputs.get('winning_primary_text')) or 'Not supplied'}",
        f"Winning Meta headline: {_clean_text(inputs.get('winning_meta_headline')) or 'Not supplied'}",
        f"Winning Meta description: {_clean_text(inputs.get('winning_meta_description')) or 'Not supplied'}",
        f"Winning Meta CTA: {_clean_text(inputs.get('winning_meta_cta')) or 'Not supplied'}",
        f"Winning on-image headline: {_clean_text(inputs.get('winning_on_image_headline')) or 'Not present'}",
        f"Winning supporting line: {_clean_text(inputs.get('winning_supporting_line')) or 'Not present'}",
        f"Winning on-image CTA: {_clean_text(inputs.get('winning_on_image_cta')) or 'Not present'}",
        f"Campaign moment: {moment.get('name') or 'None'}",
        f"Moment/end date: {moment.get('date') or 'Not supplied'}",
        f"Relevant market: {moment.get('resolved_market') or 'Not supplied'}",
        f"Confirmed offer: {moment.get('promotion') or 'None supplied'}",
        f"Relevance strength: {moment.get('strength') or 'Subtle'}",
        f"Refresh intensity: {inputs.get('refresh_intensity') or 'Balanced'}",
        f"Hybrid winner mode: {'Yes' if inputs.get('hybrid_mode') else 'No'}",
    ]
    for label, key in (
        ("Campaign name", "campaign_name"),
        ("Ad-set name", "ad_set_name"),
        ("Ad name", "ad_name"),
        ("Original launch date", "original_launch_date"),
        ("Why it worked", "why_it_worked"),
        ("Additional recognisable elements", "recognisable_elements"),
    ):
        value = inputs.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def build_winner_dna_summary(inputs):
    inputs = dict(inputs or {})
    return "\n".join(
        (
            f"Known emotional territory: {_resolved_winning_angle(inputs)}",
            f"Known opening copy: {_multiline_text(inputs.get('winning_primary_text')) or 'Not supplied'}",
            f"Known message hierarchy: {_clean_text(inputs.get('winning_meta_headline')) or 'Not supplied'} / "
            f"{_clean_text(inputs.get('winning_meta_description')) or 'Not supplied'} / "
            f"{_clean_text(inputs.get('winning_meta_cta')) or 'Not supplied'}",
            f"User belief about why it worked: {_multiline_text(inputs.get('why_it_worked')) or 'Not supplied'}",
            "Visual DNA is intentionally not guessed in Sports Cave OS. ChatGPT must inspect the attached winning creative, "
            "separate supported observations from assumptions, and report that analysis before writing challengers.",
        )
    )


def build_lock_change_strategy(inputs):
    inputs = dict(inputs or {})
    protected = tuple(inputs.get("protected_elements") or PROTECTED_ELEMENTS)
    return "\n".join(
        (
            "LOCK",
            *(f"- {item}" for item in protected),
            "CHANGE",
            "- Camera perspective, crop or product scale, lighting, copy hook and material environmental treatment according to route.",
            f"- Requested changes: {_multiline_text(inputs.get('elements_to_change')) or 'Use the route contracts.'}",
            f"- Visible problems to correct: {_multiline_text(inputs.get('original_problems')) or 'None supplied.'}",
            f"- Environments to avoid: {_multiline_text(inputs.get('environments_to_avoid')) or 'None supplied.'}",
            f"- New opportunity: {_multiline_text(inputs.get('new_context_opportunity')) or 'None supplied.'}",
        )
    )


def build_attachment_checklist(inputs):
    inputs = dict(inputs or {})
    lines = [
        "1. Attach the exact Sports Cave product source as the immutable product asset.",
        "2. Attach the uploaded winning ad creative as strategy, composition and style reference only.",
        "3. Confirm ChatGPT can see both files before using the prompt.",
    ]
    if inputs.get("original_prompt_available"):
        lines.append("4. Attach or paste the original image-generation prompt as supporting context.")
    else:
        lines.append("4. No original image-generation prompt was supplied.")
    if inputs.get("metrics_csv_available"):
        lines.append("5. Keep the imported Meta metrics CSV with the saved package for evidence, not customer copy.")
    else:
        lines.append("5. No Meta metrics CSV is required for the ChatGPT conversation.")
    lines.append("6. Do not use the product visible inside the winning room mockup as the source product.")
    return "\n".join(lines)


def build_creative_refresh_format_contract(campaign_type):
    if campaign_type == "Carousel":
        return f"""CAMPAIGN FORMAT - CAROUSEL

Each refresh route is one matched five-card Carousel concept. Its standalone image-generation prompt must specify all five 1024 × 1024 cards in the existing Card 1-5 order, with complete instructions for every card. Preserve the existing {ads_page.CAROUSEL_CARD_MAX_CHARACTERS}-character Carousel headline and description limits. Card 1 is the strongest close product hero; Cards 2-4 widen the ownership story without shrinking the product into the background; Card 5 carries truthful scarcity and collector action.

{ads_page.build_carousel_square_format_lock()}"""
    if campaign_type == "Instant Experience":
        return f"""CAMPAIGN FORMAT - INSTANT EXPERIENCE

Each route must produce one ultra-realistic 1024 × 1024 square Instant Experience cover. Preserve the current Instant Experience cover hierarchy, premium scarcity treatment, product prominence and native Meta setup expectations. The Meta description output field must say "Not used by the existing Instant Experience contract" rather than inventing a link-description field.

{ads_page.build_instant_experience_creative_cta_rules()}"""
    return """CAMPAIGN FORMAT - SINGLE IMAGE / VIDEO

Each route must produce one complete, separately copyable production prompt for one 1024 × 1024 square Meta creative. Preserve the current Single Image / Video copy fields, product-first composition, placement safety and one-asset output structure."""


def build_creative_refresh_product_lock():
    return f"""{ads_page.build_product_lock_visual_rules()}

CREATIVE REFRESH PRODUCT FIDELITY EXTENSION - REPEAT IN EVERY ROUTE PROMPT

- Isolate and preserve the complete supplied Sports Cave product.
- Preserve all existing artwork pixels wherever technically possible.
- Preserve faces, expressions, bodies, uniforms, poses, vehicles, liveries, colours, typography, signatures, plaques, badges, edition markings, border, frame colour, frame profile, proportions and crop.
- Never redraw, reconstruct, face-swap, re-pose, rewrite, blur, stretch, bend, warp, squash or redesign the product.
- Keep everything inside the original product border or frame.
- Never invent missing product details.
- Never add fake logos, sponsors, signatures, certificates, plaques or edition numbers.
- Do not treat the product visible inside the winning room mockup as the source product when the exact product source is supplied.
- Keep the product large, recognisable and commercially dominant.
- Do not add competing framed artwork."""


def build_creative_refresh_realism_lock():
    return f"""{ads_page.build_frame_and_glass_visual_rules()}

{ads_page.build_room_realism_visual_rules()}

CREATIVE REFRESH REALISM EXTENSION - REPEAT IN EVERY ROUTE PROMPT

- Premium real interior photography.
- Realistic product scale and believable wall mounting.
- Sharp frame geometry.
- Natural contact shadows behind and below the frame.
- Subtle physically realistic glass reflections where appropriate.
- Real materials, believable room depth and controlled premium lighting.
- No warped furniture, duplicated objects, malformed architecture or unreadable room signage.
- No fake brands, unnecessary clutter or AI-looking people.
- No element may compete with the product.

{build_sports_cave_image_realism_rules(include_product_lock=True)}"""


def _prompt_context_value(value, fallback="Not supplied"):
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_clean_text(item) for item in value if _clean_text(item)) or fallback
    return _multiline_text(value) or fallback


def build_creative_refresh_prompt(inputs, diagnosis):
    inputs = dict(inputs or {})
    campaign_type = _clean_text(inputs.get("campaign_type"))
    country = _clean_text(inputs.get("country"))
    moment = ads_page.normalize_campaign_moment(
        inputs.get("campaign_moment"),
        selected_country=country,
    )
    moment_block = ads_page.build_campaign_moment_copy_relevance_block(
        moment,
        selected_country=country,
        campaign_type=campaign_type,
    )
    audience = dict(inputs.get("audience_context") or {})
    performance_summary = build_performance_evidence_summary(diagnosis)
    route_fields = "\n".join(f"- {field}." for field in ROUTE_OUTPUT_FIELDS)
    approved_ctas = ", ".join(
        (
            "Claim Your Edition",
            "Secure Your Edition",
            "Claim This Edition",
            "Secure This Edition",
        )
    )
    return f"""{CREATIVE_REFRESH_VERSION}

ROLE AND OBJECTIVE

Act as Sports Cave's senior Meta creative strategist, performance diagnostician, direct-response copywriter and photorealistic art director. Use one commercially successful winning ad to create exactly three controlled challenger routes. Preserve the supported reason the winner worked while materially refreshing what customers see. Do not promise, predict or guarantee improved performance.

REFERENCE ROLES - MANDATORY

Two different references are supplied:

1. Exact Sports Cave product source - immutable product asset.
2. Original winning ad creative - strategy, composition and style reference only.

The winning creative must never replace the exact product source. Never extract, crop or reconstruct a degraded product from the winning room mockup when the exact source product is available. The winner may guide premium tone, hierarchy, colour relationships and emotional character, but must not force the exact room, camera position or composition to repeat.

INPUT SUMMARY

{build_input_summary(inputs)}

PERFORMANCE EVIDENCE

{performance_summary}

Treat the diagnosis as directional evidence, not causal proof. If evidence is absent, mixed or confounded, state the uncertainty and still create the controlled refresh package. Higher CPM is auction-cost context and must not be presented as proof of creative fatigue.

WINNER DNA ANALYSIS - REQUIRED BEFORE WRITING ADS

Inspect the attached winning creative and identify:

- Core emotional angle.
- Opening hook.
- Promise.
- Ownership reason.
- Scarcity mechanism.
- CTA intent.
- Product scale and prominence.
- Composition and visual hierarchy.
- Camera perspective.
- Room archetype.
- Wall treatment and materials.
- Lighting mood and direction.
- Dominant colour palette.
- Typography character and placement.
- On-image copy hierarchy.
- Premium collector cues.
- Elements likely to have made the creative recognisable.

Separate supported observations from assumptions. Do not infer product facts from visual ambiguity. Create a concise Lock vs Change Matrix before producing any route.

KNOWN WINNER CONTEXT

{build_winner_dna_summary(inputs)}

PROTECTED ELEMENTS AND USER DIRECTION

{build_lock_change_strategy(inputs)}

REFRESH INTENSITY

Selected intensity: {_prompt_context_value(inputs.get('refresh_intensity'), 'Balanced')}.

- Conservative: preserve more of the winner's composition family while still satisfying every mandatory route change.
- Balanced: preserve the winner insight and hierarchy while making each route obviously fresh at thumbnail size.
- Bold: use stronger composition and scene departures without losing the verified product, promise, emotional reason to own it or Sports Cave character.

MANDATORY ROUTE 1 — WINNER EVOLUTION

Purpose: the closest evolution of the proven winner.

Preserve the core emotional angle, message architecture, premium style family, product prominence and recognisable visual hierarchy.

Change the camera angle, crop or product scale, lighting direction, headline wording, supporting wording and at least one material environmental detail. It must feel familiar but freshly produced, not duplicated.

MANDATORY ROUTE 2 — SCENE EXPANSION

Purpose: carry the same winning message into a visibly different premium environment.

Preserve the core promise, fan emotion, collector positioning, CTA intent and product fidelity.

Change the room type or environmental setting, wall material, camera perspective, lighting mood, secondary emotional emphasis and copy phrasing. This route must be visibly different from the original winner and Route 1.

MANDATORY ROUTE 3 — PATTERN INTERRUPT

Purpose: create the boldest new composition while preserving the underlying winner insight.

Preserve the exact product, verified claims, primary emotional reason to own it, premium Sports Cave character and collector-led action.

Change the composition, visual rhythm, setting or product presentation, hook wording, secondary angle, lighting and wall treatment. Keep it recognisably derived from the winner's strategy; do not turn it into unrelated generic advertising.

FRESHNESS SEPARATION CONTRACT

- All three routes must be meaningfully different from the original winning creative and from one another.
- Use three different camera perspectives, room/wall/setting treatments, lighting directions or moods, and fresh copy hooks.
- Keep the exact Sports Cave product as the dominant subject.
- Do not return three minor colour or wording variations.
- Do not recreate the original room with only small furniture changes.
- Do not change so many variables that the winner's underlying reason is lost.
- Inspect the supplied winner before selecting directions. If it already uses a left angle, do not blindly repeat a left-angle composition.

MATCHED OUTPUT REQUIRED FOR EACH ROUTE

{route_fields}

Every route's copy and image prompt must be internally matched. Route 1 may be the closest copy evolution. Routes 2 and 3 must express the same supported reason to buy in meaningfully fresher language.

COPY AND FACTUAL ACCURACY CONTRACT

Use concise, human, emotional Sports Cave copy with product-specific fan language and appropriate country localisation. Preserve the winning message architecture without merely repeating its wording.

Never use these generic AI phrases: Elevate your space; Transform your room; Ultimate tribute; Perfect addition; Must-have; Stunning masterpiece; Timeless decor; Bring your walls to life.

Do not invent facts, records, dates, teams, athletes, venues, edition quantities, signatures, authentication, prices, discounts, delivery claims or offers. Do not claim that a refresh will double results, guarantee improvement or definitely beat the winner.

Approved collector-led creative CTAs are: {approved_ctas}. Do not use "Own the Feeling". Where the selected campaign type has a stricter existing CTA contract, that stricter contract wins.

{ads_page.SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1}

{ads_page.build_country_language_guidance(country)}

{moment_block or 'No campaign moment is active. Keep the package evergreen and do not invent an event or offer.'}

ON-IMAGE COPY CONTRACT

Each route may place only its exact approved on-image headline, optional supporting line and on-image CTA on the image. Keep that wording concise, readable and subordinate to the product. Do not put Primary Text, Meta headline, Meta description, targeting information, performance claims, prices, discounts, offers or additional advertising wording on the image unless the selected existing campaign contract explicitly permits it.

AUDIENCE CONTEXT - STRATEGY ONLY

- Audience type: {_prompt_context_value(audience.get('audience_type'))}
- Approximate audience size: {_prompt_context_value(audience.get('audience_size'))}
- Age range: {_prompt_context_value(audience.get('age_range'))}
- Gender targeting: {_prompt_context_value(audience.get('gender_targeting'))}
- Interests: {_prompt_context_value(audience.get('interests'))}
- Placements: {_prompt_context_value(audience.get('placements'))}
- Campaign objective: {_prompt_context_value(audience.get('campaign_objective'))}
- Optimisation event: {_prompt_context_value(audience.get('optimisation_event'))}
- Attribution setting: {_prompt_context_value(audience.get('attribution_setting'))}

Use audience context only to improve strategy. Never automatically place audience size, targeting details, interests or attribution settings in customer-facing copy.

{build_creative_refresh_format_contract(campaign_type)}

IMAGE PROMPT REFERENCE CONTRACT - REPEAT IN ALL THREE STANDALONE PROMPTS

Each route's complete standalone image-generation prompt must explicitly state:

1. Exact Sports Cave product source - immutable product asset.
2. Original winning ad creative - strategy and style reference only.

Never write "same as previous prompt", "use the shared lock above" or any other cross-reference. Repeat the complete product-fidelity lock and realism lock inside every one of the three returned image prompts.

{build_creative_refresh_product_lock()}

{build_creative_refresh_realism_lock()}

TESTING GUIDANCE

- Keep the original winning ad as the control while it remains commercially viable.
- Do not edit or overwrite the winner in place.
- Keep the audience, offer, objective, optimisation event and landing page stable during the first creative comparison where practical.
- Launch the three refreshed ads as new challengers.
- Do not claim that one route will win before sufficient delivery data exists.
- Record which refreshed route becomes the next control.

RESPONSE ORDER - EXACT

1. Fatigue Evidence Summary.
2. Winner DNA.
3. Lock vs Change Matrix.
4. Refresh 1 — Winner Evolution.
5. Refresh 2 — Scene Expansion.
6. Refresh 3 — Pattern Interrupt.
7. Recommended Test Order.
8. Final Quality Check.

Provide all copy and all three complete standalone image prompts in the first text response before using any image tool.

"Do not generate any image automatically. Only generate Refresh Image 1, 2 or 3 after I explicitly request that image."
"""


def creative_refresh_package_name(product_name, country, *, package_date=None):
    if package_date is None:
        package_date = datetime.now(ZoneInfo(os_accounts.ADMIN_TIMEZONE)).date()
    if isinstance(package_date, datetime):
        package_date = package_date.date()
    slug_source = f"{_clean_text(product_name)}-{_clean_text(country)}"
    slug = re.sub(r"[^a-z0-9]+", "-", slug_source.casefold()).strip("-")
    slug = slug or "sports-cave"
    return f"{slug}-creative-refresh-{package_date.isoformat()}"


def build_creative_refresh_result(inputs, diagnosis, *, generated_at=None):
    safe_inputs = dict(inputs or {})
    generated_at = generated_at or datetime.now(ZoneInfo(os_accounts.ADMIN_TIMEZONE))
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=ZoneInfo(os_accounts.ADMIN_TIMEZONE))
    prompt = build_creative_refresh_prompt(safe_inputs, diagnosis)
    input_summary = build_input_summary(safe_inputs)
    evidence_summary = build_performance_evidence_summary(diagnosis)
    winner_dna_summary = build_winner_dna_summary(safe_inputs)
    strategy_summary = build_lock_change_strategy(safe_inputs)
    attachment_checklist = build_attachment_checklist(safe_inputs)
    context_payload = {
        "product_name": safe_inputs.get("product_name"),
        "country": safe_inputs.get("country"),
        "campaign_type": safe_inputs.get("campaign_type"),
        "winning_creative_signature": safe_inputs.get("winning_creative_signature"),
        "prompt": prompt,
    }
    context_key = hashlib.sha256(
        json.dumps(context_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "context_key": context_key,
        "contract_version": CREATIVE_REFRESH_VERSION,
        "generated_at": generated_at.isoformat(),
        "package_name": creative_refresh_package_name(
            safe_inputs.get("product_name"),
            safe_inputs.get("country"),
            package_date=generated_at.date(),
        ),
        "inputs": safe_inputs,
        "diagnosis": dict(diagnosis or {}),
        "input_summary": input_summary,
        "performance_evidence_summary": evidence_summary,
        "winner_dna_summary": winner_dna_summary,
        "lock_change_strategy": strategy_summary,
        "prompt": prompt,
        "attachment_checklist": attachment_checklist,
    }


def validate_winning_creative(data, *, filename):
    extension = PurePosixPath(str(filename or "")).suffix.casefold()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise CreativeRefreshValidationError("Upload the winning creative as PNG, JPG, JPEG or WebP.")
    try:
        return ads_final_review.validate_review_image(data, filename=filename)
    except ads_final_review.AdsReviewValidationError as error:
        raise CreativeRefreshValidationError(str(error)) from error


def validate_original_prompt_upload(data, *, filename):
    extension = PurePosixPath(str(filename or "")).suffix.casefold()
    if extension not in {".txt", ".md"}:
        raise CreativeRefreshValidationError("Upload the original prompt as a TXT or MD file.")
    source = bytes(data or b"")
    if len(source) > 2 * 1024 * 1024:
        raise CreativeRefreshValidationError("The original prompt file must be under 2 MB.")
    try:
        return source.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CreativeRefreshValidationError("The original prompt file must be UTF-8 text.") from error


def validate_creative_refresh_inputs(inputs, *, winning_creative=None, csv_selection_error=""):
    inputs = dict(inputs or {})
    errors = {"product_campaign": [], "winning_ad": [], "performance": []}
    if not _clean_text(inputs.get("product_name")):
        errors["product_campaign"].append("Select or enter a product name.")
    if inputs.get("category") not in ads_page.CATEGORY_OPTIONS[1:]:
        errors["product_campaign"].append("Select a category.")
    if inputs.get("country") not in ads_page.COUNTRY_OPTIONS[1:]:
        errors["product_campaign"].append("Select a country.")
    if inputs.get("campaign_type") not in ads_page.CAMPAIGN_TYPE_OPTIONS[1:]:
        errors["product_campaign"].append("Select a campaign type.")
    if not ads_page.is_valid_product_page_url(inputs.get("product_url")):
        errors["product_campaign"].append(ads_page.PRODUCT_URL_ERROR)
    moment_error = ads_page.validate_campaign_moment(
        inputs.get("campaign_moment"),
        selected_country=inputs.get("country"),
    )
    if moment_error:
        errors["product_campaign"].append(moment_error)

    if not winning_creative:
        errors["winning_ad"].append("Upload the winning creative.")
    for key, label in (
        ("winning_primary_text", "Winning primary text"),
        ("winning_meta_headline", "Winning Meta headline"),
        ("winning_meta_description", "Winning Meta description"),
        ("winning_meta_cta", "Winning Meta CTA button"),
    ):
        if not _multiline_text(inputs.get(key)):
            errors["winning_ad"].append(f"Enter {label.lower()}.")
    angle = _clean_text(inputs.get("winning_emotional_angle"))
    if angle not in WINNING_ANGLE_OPTIONS[1:]:
        errors["winning_ad"].append("Select the winning emotional angle.")
    if angle == "Other" and not _clean_text(inputs.get("winning_emotional_angle_other")):
        errors["winning_ad"].append("Describe the other winning emotional angle.")
    for value_key, absent_key, label in (
        ("winning_on_image_headline", "no_on_image_headline", "winning on-image headline"),
        ("winning_supporting_line", "no_supporting_line", "winning supporting line"),
        ("winning_on_image_cta", "no_on_image_cta", "winning on-image CTA"),
    ):
        if not _clean_text(inputs.get(value_key)) and not inputs.get(absent_key):
            errors["winning_ad"].append(f"Enter the {label} or confirm it was not present.")

    if inputs.get("performance_mode") == "Meta CSV upload" and csv_selection_error:
        errors["performance"].append(csv_selection_error)
    return {section: messages for section, messages in errors.items() if messages}


def _asset_item(relative_path, data):
    source = bytes(data or b"")
    return {"relative_path": relative_path, "data": source, "size": len(source)}


def build_creative_refresh_package_items(
    result,
    *,
    winning_creative=None,
    original_prompt_upload=None,
    imported_metrics_csv=None,
):
    result = dict(result or {})
    items = [
        _asset_item("creative-refresh-prompt.txt", result.get("prompt", "").encode("utf-8")),
        _asset_item("winner-inputs-summary.txt", result.get("input_summary", "").encode("utf-8")),
        _asset_item(
            "performance-evidence-summary.txt",
            result.get("performance_evidence_summary", "").encode("utf-8"),
        ),
        _asset_item(
            "refresh-strategy-summary.txt",
            (
                result.get("winner_dna_summary", "")
                + "\n\n"
                + result.get("lock_change_strategy", "")
            ).encode("utf-8"),
        ),
        _asset_item(
            "attachment-checklist.txt",
            result.get("attachment_checklist", "").encode("utf-8"),
        ),
    ]
    if winning_creative:
        extension = PurePosixPath(str(winning_creative.get("filename") or "")).suffix.casefold()
        extension = extension if extension in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
        items.append(
            _asset_item(
                f"winning-creative-reference{extension}",
                winning_creative.get("data"),
            )
        )
    if original_prompt_upload:
        extension = PurePosixPath(str(original_prompt_upload.get("filename") or "")).suffix.casefold()
        extension = extension if extension in {".txt", ".md"} else ".txt"
        items.append(
            _asset_item(
                f"original-image-prompt-upload{extension}",
                original_prompt_upload.get("data"),
            )
        )
    pasted_prompt = _multiline_text((result.get("inputs") or {}).get("original_prompt_text"))
    if pasted_prompt:
        items.append(_asset_item("original-image-prompt-pasted.txt", pasted_prompt.encode("utf-8")))
    if imported_metrics_csv:
        items.append(_asset_item("imported-meta-metrics.csv", imported_metrics_csv.get("data")))
    return items


def creative_refresh_package_signature(items):
    digest = hashlib.sha256()
    for item in sorted(items or (), key=lambda row: row.get("relative_path", "")):
        digest.update(str(item.get("relative_path") or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes(item.get("data") or b""))
        digest.update(b"\0")
    return digest.hexdigest()


def save_creative_refresh_package_to_dropbox(
    access_token,
    root_path,
    destination,
    result,
    items,
):
    items = list(items or ())
    clean_root = dropbox_integration.normalize_dropbox_path(root_path)
    clean_destination = dropbox_integration.normalize_dropbox_path(destination)
    if not dropbox_integration.path_is_within_root(clean_destination, clean_root):
        raise CreativeRefreshSaveError("The selected destination is outside the approved Files folder.")
    package_name = str((result or {}).get("package_name") or "creative-refresh-package")
    export_folder = dropbox_integration.join_upload_path(clean_destination, package_name)
    if not dropbox_integration.path_is_within_root(export_folder, clean_root):
        raise CreativeRefreshSaveError("The Creative Refresh package path is outside the approved Files folder.")
    if dropbox_integration.get_metadata_if_exists(access_token, export_folder):
        export_folder = dropbox_integration.windows_numbered_path(access_token, export_folder)
    dropbox_integration.ensure_folder_path(access_token, export_folder, root_path=clean_root)
    upload_result = dropbox_integration.upload_batch(
        access_token,
        export_folder,
        items,
        conflict="cancel",
    )
    failures = list(upload_result.get("failures") or ())
    if failures:
        message = str((failures[0] or {}).get("error") or "Package upload failed.")
        raise CreativeRefreshSaveError(message)
    successes = list(upload_result.get("successes") or ())
    if len(successes) != len(items):
        raise CreativeRefreshSaveError("The Creative Refresh package was only partially saved.")
    return {
        "status": "saved",
        "path": export_folder,
        "files": [str(item.get("relative_path") or "") for item in items],
        "signature": creative_refresh_package_signature(items),
    }


def reset_creative_refresh_state(state=None):
    state = st.session_state if state is None else state
    for key in list(state):
        if str(key).startswith(STATE_PREFIX):
            state.pop(key, None)


def _on_product_url_changed():
    current = _clean_text(st.session_state.get(PRODUCT_URL_KEY))
    last_auto = _clean_text(st.session_state.get(PRODUCT_LAST_AUTO_URL_KEY))
    if current != last_auto:
        st.session_state[PRODUCT_URL_MANUAL_KEY] = True


def _render_styles():
    st.markdown(
        """
        <style>
        .sc-creative-refresh-subtitle {
            margin: -0.45rem 0 0.85rem;
            color: #66615a;
            font-size: 0.92rem;
        }
        .sc-creative-refresh-stage-note {
            margin: -0.2rem 0 0.45rem;
            color: #6b665f;
            font-size: 0.82rem;
        }
        .sc-creative-refresh-card-copy {
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            color: #24211d;
            line-height: 1.45;
        }
        .sc-creative-refresh-asset-note {
            border-left: 3px solid #c89b3c;
            padding: 0.42rem 0.62rem;
            background: #fffaf0;
            color: #2b2925;
            font-size: 0.82rem;
            line-height: 1.42;
            overflow-wrap: anywhere;
        }
        .sc-creative-refresh-diagnosis {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.8rem;
            margin: 0.45rem 0 0.7rem;
            padding: 0.65rem 0.75rem;
            border: 1px solid #ddd8cd;
            border-left: 4px solid #c89b3c;
            border-radius: 6px;
            background: #fffdf8;
            color: #1b1a18;
        }
        .sc-creative-refresh-diagnosis strong {
            font-size: 0.95rem;
        }
        .sc-creative-refresh-diagnosis span {
            color: #676159;
            font-size: 0.78rem;
            text-align: right;
        }
        div[class*="st-key-ads_creative_refresh_"] {
            min-width: 0;
        }
        div[class*="st-key-ads_creative_refresh_"] textarea,
        div[class*="st-key-ads_creative_refresh_"] input {
            min-width: 0;
        }
        .st-key-ads-creative-refresh-dropbox-picker button {
            min-height: 32px !important;
        }
        @media (max-width: 720px) {
            .sc-creative-refresh-diagnosis {
                flex-direction: column;
            }
            .sc-creative-refresh-diagnosis span {
                text-align: left;
            }
            div[class*="st-key-ads_creative_refresh_"] button {
                min-height: 40px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_section_errors(section):
    for message in (st.session_state.get(VALIDATION_STATE_KEY) or {}).get(section, ()):
        st.error(message)


def _render_product_campaign_section():
    with st.container(border=True, key=f"{STATE_PREFIX}product_campaign_card"):
        st.subheader("1. Product and Campaign")
        product_rows = ads_page.load_edition_ops_product_rows()
        records = ads_page.build_ads_product_selector_records(product_rows)
        records_by_identity = {record["identity"]: record for record in records}
        if records:
            selector_value = st.selectbox(
                "Product name",
                options=alphabetize_options(
                    records_by_identity,
                    label=lambda identity: records_by_identity.get(identity, {}).get("label") or identity,
                ),
                index=None,
                placeholder="Select or enter a product",
                accept_new_options=True,
                filter_mode="fuzzy",
                format_func=lambda identity: records_by_identity.get(identity, {}).get("label") or identity,
                key=PRODUCT_SELECTOR_KEY,
            )
        else:
            selector_value = st.text_input(
                "Product name",
                placeholder="Example: Six Laps Ahead",
                key=PRODUCT_SELECTOR_KEY,
            )
        selection = ads_page.resolve_ads_product_selector_value(
            selector_value,
            rows=product_rows,
            records=records,
        )
        product_name = selection.get("selected_label") or ""
        selection_identity = selection.get("selector_identity") or ""
        previous_identity = st.session_state.get(PRODUCT_AUTOFILL_IDENTITY_KEY)
        if selection_identity != previous_identity:
            selected_url = selection.get("product_url") or ""
            st.session_state[PRODUCT_AUTOFILL_IDENTITY_KEY] = selection_identity
            st.session_state[PRODUCT_URL_KEY] = selected_url
            st.session_state[PRODUCT_LAST_AUTO_URL_KEY] = selected_url
            st.session_state[PRODUCT_URL_MANUAL_KEY] = False

        category_col, country_col, campaign_col = st.columns(3)
        with category_col:
            category = st.selectbox(
                "Category",
                ads_page.CATEGORY_OPTIONS,
                key=f"{STATE_PREFIX}category",
            )
        with country_col:
            country = st.selectbox(
                "Country",
                ads_page.COUNTRY_OPTIONS,
                key=f"{STATE_PREFIX}country",
            )
        with campaign_col:
            campaign_type = st.selectbox(
                "Campaign type",
                ads_page.CAMPAIGN_TYPE_OPTIONS,
                key=f"{STATE_PREFIX}campaign_type",
            )
        product_url = st.text_input(
            "Product page URL *",
            placeholder="https://sportscave.com.au/products/example",
            key=PRODUCT_URL_KEY,
            on_change=_on_product_url_changed,
        )
        if product_name and not selection.get("product_url"):
            st.caption(ads_page.NO_EDITION_OPS_PRODUCT_URL_MESSAGE)

        st.markdown("**Campaign moment (optional)**")
        moment_type_col, moment_name_col = st.columns([1, 2])
        with moment_type_col:
            moment_type = st.selectbox(
                "Campaign moment",
                [""] + ads_page.CAMPAIGN_MOMENT_TYPE_OPTIONS,
                format_func=lambda option: "Select a moment type" if not option else option,
                key=f"{STATE_PREFIX}moment_type",
            )
        with moment_name_col:
            moment_name = st.text_input(
                "Moment name",
                placeholder="Father's Day, NBA Playoffs, Bathurst",
                key=f"{STATE_PREFIX}moment_name",
            )
        market_col, date_col = st.columns(2)
        with market_col:
            moment_market = st.selectbox(
                "Relevant market",
                ads_page.CAMPAIGN_MOMENT_MARKET_OPTIONS,
                key=f"{STATE_PREFIX}moment_market",
            )
        with date_col:
            moment_date = st.date_input(
                "Moment date or end date",
                value=None,
                key=f"{STATE_PREFIX}moment_date",
            )
        offer_col, strength_col = st.columns([2, 1])
        with offer_col:
            promotion = st.text_input(
                "Promotion or offer",
                placeholder="Use only a verified offer; leave blank for none",
                key=f"{STATE_PREFIX}promotion",
            )
        with strength_col:
            strength = st.selectbox(
                "Relevance strength",
                ads_page.CAMPAIGN_MOMENT_STRENGTH_OPTIONS,
                key=f"{STATE_PREFIX}relevance_strength",
            )
        include_in_images = st.checkbox(
            "Use the campaign moment as restrained visual context",
            key=f"{STATE_PREFIX}moment_in_images",
        )
        source_url = _clean_text((selection.get("row") or {}).get("image_url"))
        source_status = (
            "The selected Edition Ops record includes an exact product image source."
            if source_url
            else "Attach the exact Sports Cave product source in ChatGPT with the saved prompt."
        )
        st.markdown(
            '<div class="sc-creative-refresh-asset-note"><strong>Two separate references:</strong> '
            f"{source_status} It is the immutable product asset. The winning ad uploaded below is only a strategy, "
            "composition and style reference, and must never replace or be used to extract the product.</div>",
            unsafe_allow_html=True,
        )
        _render_section_errors("product_campaign")

    campaign_moment = ads_page.normalize_campaign_moment(
        {
            "type": moment_type,
            "name": moment_name,
            "market": moment_market,
            "date": moment_date,
            "promotion": promotion,
            "strength": strength,
            "include_in_image_prompts": include_in_images,
        },
        selected_country=country,
    )
    return {
        "product_name": product_name,
        "product_selection": selection,
        "product_source_url": source_url,
        "category": category,
        "country": country,
        "campaign_type": campaign_type,
        "product_url": product_url,
        "campaign_moment": campaign_moment,
        "product_metadata": ads_page.instant_experience_product_metadata_from_selection(
            selection,
            category=category,
        ),
    }


def _render_winning_ad_section():
    with st.container(border=True, key=f"{STATE_PREFIX}winning_ad_card"):
        st.subheader("2. Winning Ad")
        winning_upload = st.file_uploader(
            "Winning creative",
            type=["png", "jpg", "jpeg", "webp"],
            key=WINNING_CREATIVE_KEY,
            help="Upload the exact winning ad creative. This is a strategy and style reference, not the product source.",
            max_upload_size=20,
        )
        if winning_upload is not None:
            preview_col, file_col = st.columns([1, 3])
            with preview_col:
                st.image(winning_upload, width="stretch")
            with file_col:
                st.caption(f"Winning reference: {winning_upload.name}")
                st.caption("The exact product source remains authoritative even if this mockup contains a lower-quality product rendering.")

        primary_text = st.text_area(
            "Winning primary text",
            height=92,
            key=f"{STATE_PREFIX}winning_primary_text",
        )
        headline_col, description_col = st.columns(2)
        with headline_col:
            meta_headline = st.text_input(
                "Winning Meta headline",
                key=f"{STATE_PREFIX}winning_meta_headline",
            )
        with description_col:
            meta_description = st.text_input(
                "Winning Meta description",
                key=f"{STATE_PREFIX}winning_meta_description",
            )
        cta_col, angle_col = st.columns(2)
        with cta_col:
            meta_cta = st.text_input(
                "Winning Meta CTA button",
                placeholder="Example: Shop Now",
                key=f"{STATE_PREFIX}winning_meta_cta",
            )
        with angle_col:
            emotional_angle = st.selectbox(
                "Winning emotional angle",
                WINNING_ANGLE_OPTIONS,
                key=f"{STATE_PREFIX}winning_emotional_angle",
            )
        emotional_angle_other = ""
        if emotional_angle == "Other":
            emotional_angle_other = st.text_input(
                "Describe the other emotional angle",
                key=f"{STATE_PREFIX}winning_emotional_angle_other",
            )

        st.markdown("**Exact wording visible on the winning image**")
        image_headline_col, supporting_col, image_cta_col = st.columns(3)
        with image_headline_col:
            image_headline = st.text_input(
                "Winning on-image headline",
                key=f"{STATE_PREFIX}winning_on_image_headline",
            )
            no_image_headline = st.checkbox(
                "Not present in winner",
                key=f"{STATE_PREFIX}no_on_image_headline",
            )
        with supporting_col:
            supporting_line = st.text_input(
                "Winning supporting line",
                key=f"{STATE_PREFIX}winning_supporting_line",
            )
            no_supporting_line = st.checkbox(
                "Not present in winner",
                key=f"{STATE_PREFIX}no_supporting_line",
            )
        with image_cta_col:
            image_cta = st.text_input(
                "Winning on-image CTA",
                key=f"{STATE_PREFIX}winning_on_image_cta",
            )
            no_image_cta = st.checkbox(
                "Not present in winner",
                key=f"{STATE_PREFIX}no_on_image_cta",
            )

        original_prompt_text = st.text_area(
            "Original image-generation prompt (optional)",
            height=74,
            key=f"{STATE_PREFIX}original_prompt_text",
        )
        original_prompt_upload = st.file_uploader(
            "Original prompt file (optional)",
            type=["txt", "md"],
            key=ORIGINAL_PROMPT_UPLOAD_KEY,
            help="TXT or MD only. The source file is preserved unchanged in the saved package.",
        )
        campaign_name_col, ad_set_name_col, ad_name_col = st.columns(3)
        with campaign_name_col:
            campaign_name = st.text_input(
                "Campaign name (optional)",
                key=f"{STATE_PREFIX}campaign_name",
            )
        with ad_set_name_col:
            ad_set_name = st.text_input(
                "Ad-set name (optional)",
                key=f"{STATE_PREFIX}ad_set_name",
            )
        with ad_name_col:
            ad_name = st.text_input(
                "Ad name (optional)",
                key=f"{STATE_PREFIX}ad_name",
            )
        launch_date = st.date_input(
            "Original launch date (optional)",
            value=None,
            key=f"{STATE_PREFIX}launch_date",
        )
        why_it_worked = st.text_area(
            "Why do you believe it worked? (optional)",
            height=70,
            key=f"{STATE_PREFIX}why_it_worked",
        )
        recognisable_elements = st.text_area(
            "Additional elements that must remain recognisable (optional)",
            height=70,
            key=f"{STATE_PREFIX}recognisable_elements",
        )
        with st.expander("Advanced: hybrid winning inputs", expanded=False):
            hybrid_mode = st.checkbox(
                "The creative or copy fields came from different winning ads",
                key=f"{STATE_PREFIX}hybrid_mode",
            )
            hybrid_notes = st.text_area(
                "Identify which winning ad supplied each element",
                height=80,
                disabled=not hybrid_mode,
                key=f"{STATE_PREFIX}hybrid_notes",
            )
            st.caption("Use one coherent winning ad by default. Hybrid mode is for known, intentional combinations only.")
        _render_section_errors("winning_ad")

    return {
        "winning_upload": winning_upload,
        "original_prompt_upload": original_prompt_upload,
        "winning_primary_text": primary_text,
        "winning_meta_headline": meta_headline,
        "winning_meta_description": meta_description,
        "winning_meta_cta": meta_cta,
        "winning_emotional_angle": emotional_angle,
        "winning_emotional_angle_other": emotional_angle_other,
        "winning_on_image_headline": image_headline,
        "winning_supporting_line": supporting_line,
        "winning_on_image_cta": image_cta,
        "no_on_image_headline": no_image_headline,
        "no_supporting_line": no_supporting_line,
        "no_on_image_cta": no_image_cta,
        "original_prompt_text": original_prompt_text,
        "campaign_name": campaign_name,
        "ad_set_name": ad_set_name,
        "ad_name": ad_name,
        "original_launch_date": launch_date.isoformat() if launch_date else "",
        "why_it_worked": why_it_worked,
        "recognisable_elements": recognisable_elements,
        "hybrid_mode": hybrid_mode,
        "hybrid_notes": hybrid_notes,
    }


def _render_manual_period(label, prefix):
    st.markdown(f"**{label}**")
    start_col, end_col = st.columns(2)
    with start_col:
        start = st.date_input(
            "Start date",
            value=None,
            key=f"{STATE_PREFIX}{prefix}_date_start",
        )
    with end_col:
        end = st.date_input(
            "End date",
            value=None,
            key=f"{STATE_PREFIX}{prefix}_date_end",
        )
    period = {"date_start": start, "date_end": end}
    for field, field_label in METRIC_FIELDS:
        period[field] = st.text_input(
            field_label,
            placeholder="Optional",
            key=f"{STATE_PREFIX}{prefix}_{field}",
        )
    return derive_period_metrics(period)


@st.cache_data(show_spinner=False, max_entries=12)
def _cached_parse_meta_ads_csv(data, filename):
    return parse_meta_ads_csv(data, filename=filename)


def _render_diagnosis(diagnosis):
    classification = diagnosis.get("classification") or "Insufficient Evidence"
    note = diagnosis.get("summary") or "No comparable metrics supplied."
    st.markdown(
        '<div class="sc-creative-refresh-diagnosis">'
        f"<strong>{classification}</strong><span>{note}</span></div>",
        unsafe_allow_html=True,
    )
    rows = []
    for metric in ("frequency", "ctr", "cpa", "roas", "cpc", "cpm"):
        change = (diagnosis.get("changes") or {}).get(metric) or {}
        if change.get("winning") is None or change.get("recent") is None:
            continue
        pct = change.get("percentage_change")
        rows.append(
            {
                "Metric": change.get("label"),
                "Winning": format_metric(change.get("winning"), metric),
                "Recent": format_metric(change.get("recent"), metric),
                "Change": "From zero" if pct is None else f"{pct * 100:+.1f}%",
                "Direction": change.get("direction"),
            }
        )
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_performance_section():
    with st.container(border=True, key=f"{STATE_PREFIX}performance_card"):
        st.subheader("3. Performance Evidence")
        st.caption("Compare a winning period with a recent period for a meaningful fatigue diagnosis. Missing or mixed evidence will not block generation.")
        mode = st.radio(
            "Evidence mode",
            PERFORMANCE_MODES,
            horizontal=True,
            key=f"{STATE_PREFIX}performance_mode",
        )
        winning_period = {}
        recent_period = {}
        imported_csv = None
        csv_selection_error = ""
        if mode == "Manual metrics":
            winning_col, recent_col = st.columns(2)
            with winning_col:
                winning_period = _render_manual_period("A. Winning Period", "winning_period")
            with recent_col:
                recent_period = _render_manual_period("B. Recent Period", "recent_period")
        elif mode == "Meta CSV upload":
            csv_upload = st.file_uploader(
                "Meta Ads CSV",
                type=["csv"],
                key=META_CSV_UPLOAD_KEY,
                help="The source CSV is read only and saved unchanged with the package.",
                max_upload_size=5,
            )
            parsed = None
            if csv_upload is None:
                csv_selection_error = "Upload a Meta CSV and choose both comparison rows."
            else:
                imported_csv = {"filename": csv_upload.name, "data": csv_upload.getvalue()}
                try:
                    parsed = _cached_parse_meta_ads_csv(imported_csv["data"], csv_upload.name)
                except MetaCSVValidationError as error:
                    csv_selection_error = str(error)
                    st.error(csv_selection_error)
            if parsed:
                for warning in parsed.get("warnings") or ():
                    st.warning(warning)
                row_options = tuple(row["row_id"] for row in parsed["rows"])
                row_labels = {row["row_id"]: row["label"] for row in parsed["rows"]}
                winning_select_col, recent_select_col = st.columns(2)
                with winning_select_col:
                    winning_row_id = st.selectbox(
                        "Winning Period CSV row",
                        row_options,
                        index=None,
                        placeholder="Choose the winning row",
                        format_func=lambda row_id: row_labels.get(row_id, row_id),
                        key=f"{STATE_PREFIX}csv_winning_row",
                    )
                with recent_select_col:
                    recent_row_id = st.selectbox(
                        "Recent Period CSV row",
                        row_options,
                        index=None,
                        placeholder="Choose the recent row",
                        format_func=lambda row_id: row_labels.get(row_id, row_id),
                        key=f"{STATE_PREFIX}csv_recent_row",
                    )
                try:
                    winning_period, recent_period = select_meta_csv_periods(
                        parsed,
                        winning_row_id,
                        recent_row_id,
                    )
                    csv_selection_error = ""
                except MetaCSVValidationError as error:
                    csv_selection_error = str(error)
        else:
            st.info("No metrics supplied. The package will describe the fatigue evidence as insufficient and keep all strategic uncertainty visible.")

        st.markdown("**Possible confounders**")
        confounders = []
        confounder_columns = st.columns(3)
        for index, label in enumerate(CONFOUNDERS):
            with confounder_columns[index % len(confounder_columns)]:
                if st.checkbox(label, key=f"{STATE_PREFIX}confounder_{index}"):
                    confounders.append(label)
        diagnosis = diagnose_creative_fatigue(
            winning_period,
            recent_period,
            confounders=confounders,
        )
        _render_diagnosis(diagnosis)
        with st.expander("Diagnosis thresholds", expanded=False):
            st.caption(
                "Meaningful frequency rise: at least +20% and +0.35, or +0.75 absolute. Negative signals: CTR -15%, CPA +20%, ROAS -20% or CPC +20%. Likely fatigue requires frequency plus at least two negative signals. CPM is context only."
            )
        _render_section_errors("performance")
    return {
        "performance_mode": mode,
        "winning_period": winning_period,
        "recent_period": recent_period,
        "diagnosis": diagnosis,
        "imported_csv": imported_csv,
        "csv_selection_error": csv_selection_error,
    }


def _render_audience_context():
    with st.expander("4. Audience Context (Advanced)", expanded=False):
        st.caption("Strategic context only. These details must never be copied into customer-facing ad copy.")
        audience_col, size_col = st.columns(2)
        with audience_col:
            audience_type = st.selectbox(
                "Audience type",
                AUDIENCE_TYPES,
                key=f"{STATE_PREFIX}audience_type",
            )
        with size_col:
            audience_size = st.text_input(
                "Approximate audience size",
                key=f"{STATE_PREFIX}audience_size",
            )
        age_col, gender_col = st.columns(2)
        with age_col:
            age_range = st.text_input("Age range", key=f"{STATE_PREFIX}age_range")
        with gender_col:
            gender_targeting = st.text_input(
                "Gender targeting",
                key=f"{STATE_PREFIX}gender_targeting",
            )
        interests = st.text_area("Interests", height=60, key=f"{STATE_PREFIX}interests")
        placements = st.text_input("Placements", key=f"{STATE_PREFIX}placements")
        objective_col, optimisation_col = st.columns(2)
        with objective_col:
            campaign_objective = st.text_input(
                "Campaign objective",
                key=f"{STATE_PREFIX}campaign_objective",
            )
        with optimisation_col:
            optimisation_event = st.text_input(
                "Optimisation event",
                key=f"{STATE_PREFIX}optimisation_event",
            )
        attribution_setting = st.text_input(
            "Attribution setting",
            key=f"{STATE_PREFIX}attribution_setting",
        )
    return {
        "audience_type": audience_type,
        "audience_size": audience_size,
        "age_range": age_range,
        "gender_targeting": gender_targeting,
        "interests": interests,
        "placements": placements,
        "campaign_objective": campaign_objective,
        "optimisation_event": optimisation_event,
        "attribution_setting": attribution_setting,
    }


def _render_refresh_controls():
    with st.container(border=True, key=f"{STATE_PREFIX}controls_card"):
        st.subheader("5. Refresh Direction")
        intensity = st.radio(
            "Refresh intensity",
            REFRESH_INTENSITIES,
            index=0,
            horizontal=True,
            key=f"{STATE_PREFIX}refresh_intensity",
        )
        protected = st.multiselect(
            "Protected elements",
            PROTECTED_ELEMENTS,
            default=PROTECTED_ELEMENTS,
            key=f"{STATE_PREFIX}protected_elements",
        )
        remain_col, change_col = st.columns(2)
        with remain_col:
            elements_to_remain = st.text_area(
                "Elements that must remain (optional)",
                height=68,
                key=f"{STATE_PREFIX}elements_to_remain",
            )
            original_problems = st.text_area(
                "Problems visible in the original creative (optional)",
                height=68,
                key=f"{STATE_PREFIX}original_problems",
            )
        with change_col:
            elements_to_change = st.text_area(
                "Elements that should change (optional)",
                height=68,
                key=f"{STATE_PREFIX}elements_to_change",
            )
            environments_to_avoid = st.text_area(
                "Rooms or environments to avoid (optional)",
                height=68,
                key=f"{STATE_PREFIX}environments_to_avoid",
            )
        new_context = st.text_area(
            "Requested campaign moment or new contextual opportunity (optional)",
            height=68,
            key=f"{STATE_PREFIX}new_context_opportunity",
        )
    return {
        "refresh_intensity": intensity,
        "protected_elements": protected,
        "elements_to_remain": elements_to_remain,
        "elements_to_change": elements_to_change,
        "original_problems": original_problems,
        "environments_to_avoid": environments_to_avoid,
        "new_context_opportunity": new_context,
    }


def _asset_from_upload(uploaded_file):
    if uploaded_file is None:
        return None
    return {"filename": uploaded_file.name, "data": uploaded_file.getvalue()}


def _save_state_for_result(result):
    workflow = st.session_state.get(SAVE_STATE_KEY)
    if not isinstance(workflow, dict) or workflow.get("context_key") != result.get("context_key"):
        workflow = {
            "context_key": result.get("context_key"),
            "picker_path": "",
            "destination_path": "",
            "save_open": False,
            "saving": False,
            "saved_path": "",
            "saved_signature": "",
            "error": "",
        }
        st.session_state[SAVE_STATE_KEY] = workflow
    return workflow


def _render_package_save(result, items):
    workflow = _save_state_for_result(result)
    signature = creative_refresh_package_signature(items)
    already_saved = bool(
        workflow.get("saved_path") and workflow.get("saved_signature") == signature
    )
    if st.button(
        "Save Creative Refresh Package",
        type="primary",
        icon=":material/save:",
        disabled=bool(workflow.get("saving")) or already_saved,
        key=f"{STATE_PREFIX}save_open_{result['context_key']}",
        use_container_width=True,
    ):
        workflow["save_open"] = True
        workflow["error"] = ""
        st.session_state[SAVE_STATE_KEY] = workflow
        st.rerun()
    if not workflow.get("save_open"):
        if already_saved:
            st.success(f"Creative Refresh package saved to {workflow['saved_path']}.")
        return

    user = ads_page.current_ads_user()
    if not os_accounts.can_access_page(user, "Files"):
        st.info("Files access is not approved for this account.")
        return
    try:
        access_token, root_path = ads_page._ads_dropbox_connection()
        destination = workflow.get("destination_path") or ads_page._render_ads_folder_picker(
            access_token,
            root_path,
            {"context_key": result["context_key"]},
            workflow,
            state_key=SAVE_STATE_KEY,
            key_prefix="ads-creative-refresh-picker",
            container_key="ads-creative-refresh-dropbox-picker",
        )
    except Exception as error:
        logging.warning("Creative Refresh destination unavailable: %s", error)
        st.info("Dropbox is unavailable right now.")
        return

    st.caption(f"Destination: {destination}")
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button(
        "Save package here",
        key=f"{STATE_PREFIX}save_confirm_{result['context_key']}",
        disabled=bool(workflow.get("saving")),
        use_container_width=True,
    ):
        workflow["saving"] = True
        workflow["error"] = ""
        st.session_state[SAVE_STATE_KEY] = workflow
        try:
            outcome = save_creative_refresh_package_to_dropbox(
                access_token,
                root_path,
                destination,
                result,
                items,
            )
            workflow["destination_path"] = destination
            workflow["saved_path"] = outcome["path"]
            workflow["saved_signature"] = outcome["signature"]
            workflow["save_open"] = False
            ads_page._ads_clear_directory_cache(destination, outcome["path"])
            record_activity_log(
                "ad_images_saved",
                "Ads",
                f"Saved Creative Refresh package: {(result.get('inputs') or {}).get('product_name')}",
                entity_type="dropbox_folder",
                entity_id=outcome["path"],
                metadata={
                    "campaign_type": (result.get("inputs") or {}).get("campaign_type"),
                    "diagnosis": (result.get("diagnosis") or {}).get("classification"),
                    "file_count": len(outcome["files"]),
                },
            )
        except Exception as error:
            logging.warning("Creative Refresh package save failed: %s", error)
            workflow["error"] = str(error) or "The Creative Refresh package could not be saved."
        finally:
            workflow["saving"] = False
            st.session_state[SAVE_STATE_KEY] = workflow
        st.rerun()
    if cancel_col.button(
        "Cancel",
        key=f"{STATE_PREFIX}save_cancel_{result['context_key']}",
        use_container_width=True,
    ):
        workflow["save_open"] = False
        workflow["error"] = ""
        st.session_state[SAVE_STATE_KEY] = workflow
        st.rerun()
    if workflow.get("error"):
        st.error(workflow["error"])


def _render_generated_result(result, *, winning_upload, original_prompt_upload, imported_csv):
    st.divider()
    st.subheader("Creative Refresh Package")
    summary_col, evidence_col = st.columns(2)
    with summary_col:
        with st.expander("Input summary", expanded=True):
            st.text(result["input_summary"])
        with st.expander("Winner DNA summary", expanded=False):
            st.text(result["winner_dna_summary"])
    with evidence_col:
        with st.expander("Fatigue evidence summary", expanded=True):
            st.text(result["performance_evidence_summary"])
        with st.expander("Lock vs change strategy", expanded=False):
            st.text(result["lock_change_strategy"])

    st.markdown("**Complete ChatGPT prompt**")
    st.text_area(
        "Complete ChatGPT prompt",
        value=result["prompt"],
        height=420,
        disabled=True,
        label_visibility="collapsed",
        key=f"{STATE_PREFIX}prompt_output_{result['context_key']}",
    )
    action_col, download_col = st.columns(2)
    with action_col:
        ads_page.render_prompt_copy_button(
            result["prompt"],
            f"creative-refresh::{result['context_key']}",
            label="Copy prompt",
            success_label="Creative Refresh prompt copied",
        )
    with download_col:
        st.download_button(
            "Download prompt",
            data=result["prompt"].encode("utf-8"),
            file_name="creative-refresh-prompt.txt",
            mime="text/plain",
            icon=":material/download:",
            key=f"{STATE_PREFIX}download_prompt_{result['context_key']}",
            use_container_width=True,
        )
    with st.expander("Attachment checklist", expanded=False):
        st.text(result["attachment_checklist"])

    winning_asset = None
    if winning_upload is not None:
        try:
            winning_asset = validate_winning_creative(
                winning_upload.getvalue(),
                filename=winning_upload.name,
            )
        except CreativeRefreshValidationError as error:
            st.error(str(error))
    original_asset = _asset_from_upload(original_prompt_upload)
    items = build_creative_refresh_package_items(
        result,
        winning_creative=winning_asset,
        original_prompt_upload=original_asset,
        imported_metrics_csv=imported_csv,
    )
    if winning_asset is None:
        st.warning("Re-attach the winning creative before saving the package.")
        return
    _render_package_save(result, items)


@st.cache_data(show_spinner=False, max_entries=12)
def _cached_parse_creative_refresh_challenger_csv(data, product_name, filename):
    return parse_creative_refresh_challenger_csv(
        data,
        product_name=product_name,
        filename=filename,
    )


def _render_v2_product_selector():
    product_rows = ads_page.load_edition_ops_product_rows()
    records = ads_page.build_ads_product_selector_records(product_rows)
    records_by_identity = {record["identity"]: record for record in records}
    current = st.session_state.get(PRODUCT_SELECTOR_KEY)
    if current and current not in records_by_identity:
        st.session_state.pop(PRODUCT_SELECTOR_KEY, None)
    if records:
        selector_value = st.selectbox(
            "Product",
            options=alphabetize_options(
                records_by_identity,
                label=lambda identity: records_by_identity.get(identity, {}).get("label") or identity,
            ),
            index=None,
            placeholder="Select a Sports Cave product",
            filter_mode="fuzzy",
            format_func=lambda identity: records_by_identity.get(identity, {}).get("label") or identity,
            key=PRODUCT_SELECTOR_KEY,
        )
    else:
        selector_value = st.selectbox(
            "Product",
            options=(),
            index=None,
            placeholder="No Sports Cave products are available",
            disabled=True,
            key=PRODUCT_SELECTOR_KEY,
        )
        st.caption("Product data is unavailable right now. Creative Refresh will not guess a product.")
    selection = ads_page.resolve_ads_product_selector_value(
        selector_value,
        rows=product_rows,
        records=records,
    )
    return selection, build_creative_refresh_product_context(selection)


def _render_imported_metrics_details(parsed, evidence):
    with st.expander("View imported metrics", expanded=False):
        st.caption(
            f"Detected level: {parsed.get('report_level') or 'unknown'} · "
            f"Named rows: {parsed.get('named_row_count', 0)} · "
            f"Blank-name aggregate rows: {parsed.get('aggregate_row_count', 0)}"
        )
        st.text(evidence.get("summary") or "No metric summary available.")
        for warning in parsed.get("warnings") or ():
            st.caption(f"Note: {warning}")


def _mark_review_prompt_ready(context_key):
    st.session_state[PROMPT_READY_CONTEXT_KEY] = str(context_key or "")


def _meta_csv_ui_state(*, uploaded, parsed=None, evidence=None, error=""):
    if not uploaded:
        return "neutral"
    if parsed and (evidence or {}).get("applied"):
        return "applied"
    if error:
        return "error"
    return "error"


def _render_csv_file_state(container_key, state):
    if state not in {"applied", "error"}:
        return
    if state == "applied":
        background, border, foreground = "#EEF8F0", "#65A873", "#236332"
    else:
        background, border, foreground = "#FFF0F0", "#D66A6A", "#9E2424"
    st.markdown(
        f"""
        <style>
        .st-key-{container_key} [data-testid="stFileUploaderFile"] {{
            background: {background} !important;
            border-color: {border} !important;
            color: {foreground} !important;
        }}
        .st-key-{container_key} [data-testid="stFileUploaderFile"] svg {{
            color: {foreground} !important;
            fill: {foreground} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_meta_csv_file_state(state):
    _render_csv_file_state(META_CSV_CONTAINER_KEY, state)


def _render_primary_review_prompt_copy(prompt, context_key):
    copied_context = ads_page.render_prompt_copy_button(
        prompt,
        f"creative-refresh-v2-primary::{context_key or 'unavailable'}",
        label="Copy Creative Refresh Review Prompt",
        success_label="✓ Prompt copied",
        primary=True,
        disabled=not bool(prompt),
        track_copy=True,
    )
    if prompt and copied_context:
        _mark_review_prompt_ready(context_key)


def _render_review_winner_stage():
    with st.container(border=True, key=f"{STATE_PREFIX}review_winner_v2_card"):
        st.subheader("1. Review Winner")
        st.markdown(
            '<div class="sc-creative-refresh-stage-note">Select the product, paste the proven copy, then take one review prompt to ChatGPT.</div>',
            unsafe_allow_html=True,
        )
        _selection, product_context = _render_v2_product_selector()
        primary_col, headline_col = st.columns([3, 2])
        with primary_col:
            winning_primary_text = st.text_area(
                "Winning primary text",
                height=112,
                placeholder="Paste the winning Meta primary text",
                key=f"{STATE_PREFIX}winning_primary_text",
            )
        with headline_col:
            winning_headline = st.text_input(
                "Winning headline",
                placeholder="Paste the winning Meta headline",
                key=f"{STATE_PREFIX}winning_meta_headline",
            )
            with st.container(key=META_CSV_CONTAINER_KEY):
                meta_upload = st.file_uploader(
                    "Meta performance CSV (optional)",
                    type=["csv"],
                    key=META_CSV_UPLOAD_KEY,
                    max_upload_size=5,
                )

        parsed = None
        csv_error = ""
        if meta_upload is not None:
            try:
                parsed = _cached_parse_meta_ads_csv(meta_upload.getvalue(), meta_upload.name)
            except MetaCSVValidationError as error:
                csv_error = str(error)
                st.error(csv_error)
        evidence = build_meta_evidence_pack(parsed, product_context)
        meta_csv_state = _meta_csv_ui_state(
            uploaded=meta_upload is not None,
            parsed=parsed,
            evidence=evidence,
            error=csv_error,
        )
        _render_meta_csv_file_state(meta_csv_state)
        if meta_csv_state == "applied":
            st.success(
                "✓ Meta performance CSV applied"
                f" — {parsed.get('row_count', len(parsed.get('rows') or ())) } rows"
            )
            _render_imported_metrics_details(parsed, evidence)

        errors = validate_creative_refresh_v2_inputs(
            product_context,
            winning_primary_text,
            winning_headline,
        )
        prompt = ""
        review_result = None
        if not errors and not csv_error:
            prompt = build_creative_refresh_review_prompt(
                product_context,
                winning_primary_text,
                winning_headline,
                meta_evidence=evidence,
            )
            context_payload = {
                "product": product_context.get("record_key") or product_context.get("product_name"),
                "primary_text": _multiline_text(winning_primary_text),
                "headline": _clean_text(winning_headline),
                "meta": hashlib.sha256(meta_upload.getvalue()).hexdigest() if meta_upload else "",
            }
            context_key = hashlib.sha256(
                json.dumps(context_payload, sort_keys=True).encode("utf-8")
            ).hexdigest()[:20]
            review_result = {
                "context_key": context_key,
                "product_context": product_context,
                "winning_primary_text": _multiline_text(winning_primary_text),
                "winning_headline": _clean_text(winning_headline),
                "meta_parsed": parsed,
                "meta_evidence": evidence,
                "prompt": prompt,
            }
            st.session_state[REVIEW_RESULT_STATE_KEY] = review_result

        template_column, prompt_column = st.columns([1, 2])
        with template_column:
            st.download_button(
                "Download Empty CSV",
                data=build_creative_refresh_empty_csv(product_context),
                file_name="sports-cave-ads-empty.csv",
                mime="text/csv",
                icon=":material/table_view:",
                disabled=not bool(prompt),
                key=f"{STATE_PREFIX}download_empty_ads_csv",
                use_container_width=True,
            )
        with prompt_column:
            _render_primary_review_prompt_copy(
                prompt,
                (review_result or {}).get("context_key"),
            )
        if errors:
            st.caption("Complete Product, Winning primary text and Winning headline to create the review prompt.")
        if prompt:
            with st.expander("Preview or copy Review Prompt", expanded=False):
                st.text_area(
                    "Creative Refresh Review Prompt",
                    value=prompt,
                    height=280,
                    disabled=True,
                    key=f"{STATE_PREFIX}review_prompt_preview_{review_result['context_key']}",
                )
                ads_page.render_prompt_copy_button(
                    prompt,
                    f"creative-refresh-v2::{review_result['context_key']}",
                    label="Copy Review Prompt",
                    success_label="Creative Refresh Review Prompt copied",
                )
    return review_result


def _render_build_challengers_stage(review_result):
    st.divider()
    with st.container(border=True, key=f"{STATE_PREFIX}build_challengers_v2_card"):
        st.subheader("2. Build Challengers")
        st.caption("In ChatGPT, attach the winning image and empty CSV, run the prompt, then import the completed CSV.")
        with st.container(key=CHALLENGER_CSV_CONTAINER_KEY):
            csv_upload = st.file_uploader(
                "Import Completed CSV",
                type=["csv"],
                key=CHALLENGER_CSV_UPLOAD_KEY,
                max_upload_size=2,
            )
        result = st.session_state.get(CHALLENGER_RESULT_STATE_KEY)
        if not isinstance(result, dict) or result.get("source_review_context_key") != review_result.get("context_key"):
            result = None
        if csv_upload is not None:
            try:
                challengers = _cached_parse_creative_refresh_challenger_csv(
                    csv_upload.getvalue(),
                    review_result["product_context"].get("product_name") or "",
                    csv_upload.name,
                )
                result = build_creative_refresh_ads_result(
                    review_result["product_context"],
                    challengers,
                    csv_upload.getvalue(),
                    review_context_key=review_result.get("context_key"),
                )
                st.session_state[CHALLENGER_RESULT_STATE_KEY] = result
                _render_csv_file_state(CHALLENGER_CSV_CONTAINER_KEY, "applied")
                st.success("✓ 3 ads imported")
            except CreativeRefreshValidationError as error:
                result = None
                st.session_state.pop(CHALLENGER_RESULT_STATE_KEY, None)
                _render_csv_file_state(CHALLENGER_CSV_CONTAINER_KEY, "error")
                st.error(str(error))
        if result is None:
            return

    workflow = ads_page._ads_image_workflow(result)
    standard_ads = tuple(result.get("standard_ads") or result.get("refresh_challengers") or ())
    workflow["ad_notes"] = {
        "headlines": "\n\n".join(
            f"Ad {row['ad_number']} — {row['strategy']}: {row['headline']}"
            for row in standard_ads
        ),
        "descriptions": "\n\n".join(
            f"Ad {row['ad_number']} — {row['strategy']}: {row['description']}"
            for row in standard_ads
        ),
        "primary_text_variations": "\n\n".join(
            f"Ad {row['ad_number']} — {row['strategy']}:\n{row['primary_text']}"
            for row in standard_ads
        ),
        "cards": creative_refresh_setup_notes(standard_ads),
    }
    st.session_state[ads_page.ADS_IMAGE_STATE_KEY] = workflow
    ads_page._render_ads_image_slots(result, workflow)
    ads_page._render_ads_image_save(result, workflow)


def render_page():
    _render_styles()
    st.title("Creative Refresh")
    st.markdown(
        '<div class="sc-creative-refresh-subtitle">Turn a proven winner into three stronger controlled challengers.</div>',
        unsafe_allow_html=True,
    )
    with st.expander("How to use", expanded=False):
        st.markdown(
            "1. Select the product and paste the winning primary text and headline.\n"
            "2. Optionally add a Meta performance CSV, then download the empty CSV and copy the Review Prompt.\n"
            "3. In ChatGPT, attach the winning image and empty CSV, then run the prompt.\n"
            "4. Import the completed three-row CSV, upload the three generated images and save through the normal Ads workflow."
        )
    review_result = _render_review_winner_stage()
    if (
        review_result
        and review_result.get("prompt")
        and st.session_state.get(PROMPT_READY_CONTEXT_KEY) == review_result.get("context_key")
    ):
        _render_build_challengers_stage(review_result)


render_creative_refresh_page = render_page
