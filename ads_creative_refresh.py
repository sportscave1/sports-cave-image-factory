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

CREATIVE_REFRESH_VERSION = "SPORTS CAVE CREATIVE REFRESH V1"
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
    "date_start": ("reporting starts", "reporting start", "start date", "date start", "from"),
    "date_end": ("reporting ends", "reporting end", "end date", "date stop", "to"),
    "spend": ("amount spent", "spend", "total spent"),
    "results": ("website purchases", "purchases", "results", "purchase"),
    "purchase_value": (
        "website purchase conversion value",
        "purchases conversion value",
        "purchase conversion value",
        "conversion value",
    ),
    "cpa": ("cost per purchase", "cost per result", "purchase cpa", "cpa"),
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
    "cpc": ("cpc cost per link click", "cost per outbound click", "cost per link click", "cpc"),
    "cpm": ("cpm cost per 1 000 impressions", "cost per 1 000 impressions", "cpm"),
    "frequency": ("frequency",),
    "reach": ("reach",),
    "impressions": ("impressions",),
}


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
    result = {
        "date_start": parse_metric_date(source.get("date_start")),
        "date_end": parse_metric_date(source.get("date_end")),
    }
    for key, _label in METRIC_FIELDS:
        result[key] = parse_metric_number(source.get(key), percentage=key == "ctr")
    result["link_clicks"] = parse_metric_number(source.get("link_clicks"))
    result["campaign_name"] = _clean_text(source.get("campaign_name"))
    result["ad_set_name"] = _clean_text(source.get("ad_set_name"))
    result["ad_name"] = _clean_text(source.get("ad_name"))
    derived = []

    spend = result["spend"]
    results = result["results"]
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


def _header_matches_alias(header, alias):
    if header == alias:
        return True
    currency_suffixes = (" aud", " usd", " cad", " nzd", " gbp")
    return any(header == f"{alias}{suffix}" for suffix in currency_suffixes)


def map_meta_csv_columns(fieldnames):
    normalised = {field: _normalise_header(field) for field in (fieldnames or ()) if field}
    mapped = {}
    warnings = []
    for canonical, aliases in META_COLUMN_ALIASES.items():
        candidates = []
        for alias_rank, alias in enumerate(aliases):
            normal_alias = _normalise_header(alias)
            for field, normal_field in normalised.items():
                if _header_matches_alias(normal_field, normal_alias):
                    candidates.append((alias_rank, field))
        if candidates:
            candidates.sort(key=lambda item: (item[0], str(item[1]).casefold()))
            mapped[canonical] = candidates[0][1]
            distinct = []
            for _rank, field in candidates:
                if field not in distinct:
                    distinct.append(field)
            if len(distinct) > 1:
                warnings.append(
                    f"Mapped {canonical.replace('_', ' ')} from '{mapped[canonical]}' using the documented priority rule."
                )
    return mapped, warnings


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
    missing_dates = [key for key in ("date_start", "date_end") if key not in column_map]
    if missing_dates:
        raise MetaCSVValidationError(
            "Could not map the reporting start and end dates. Include Meta columns such as "
            "'Reporting starts' and 'Reporting ends'."
        )
    mapped_metrics = [key for key, _label in METRIC_FIELDS if key in column_map]
    if not mapped_metrics:
        raise MetaCSVValidationError(
            "Could not map any performance metrics. Include spend, results, ROAS, CTR, CPA, CPC, CPM, frequency, reach or impressions."
        )

    rows = []
    for source_index, raw in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        period = {}
        for canonical, source_column in column_map.items():
            period[canonical] = raw.get(source_column)
        derived = derive_period_metrics(period)
        if not derived["date_start"] or not derived["date_end"]:
            raise MetaCSVValidationError(
                f"Row {source_index} has an invalid reporting date. Use ISO or day/month/year dates."
            )
        identity = derived["ad_name"] or derived["ad_set_name"] or derived["campaign_name"] or "Unlabelled row"
        row_id = hashlib.sha256(
            json.dumps(
                {
                    "source_index": source_index,
                    "identity": identity,
                    "start": derived["date_start"].isoformat(),
                    "end": derived["date_end"].isoformat(),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        derived.update(
            {
                "row_id": row_id,
                "source_row": source_index,
                "label": (
                    f"{identity} | {derived['date_start'].isoformat()} to "
                    f"{derived['date_end'].isoformat()} | row {source_index}"
                ),
            }
        )
        rows.append(derived)
    if not rows:
        raise MetaCSVValidationError("The Meta CSV contains no data rows.")
    if len(rows) < 2:
        warnings.append("At least two rows are needed to compare a winning period with a recent period.")
    return {
        "rows": rows,
        "column_map": column_map,
        "warnings": warnings,
        "requires_explicit_selection": len(rows) >= 2,
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


def render_page():
    _render_styles()
    st.title("Creative Refresh")
    st.markdown(
        '<div class="sc-creative-refresh-subtitle">Turn a fatigued winning ad into three controlled challengers without losing what made it work.</div>',
        unsafe_allow_html=True,
    )
    with st.expander("How to use", expanded=False):
        st.markdown(
            "1. Select the product and campaign.\n"
            "2. Supply the winning ad and copy.\n"
            "3. Compare the winning period with the recent period.\n"
            "4. Lock the winning elements.\n"
            "5. Generate three refreshed challengers.\n"
            "6. Keep the original winner as the testing control."
        )

    product_inputs = _render_product_campaign_section()
    winner_inputs = _render_winning_ad_section()
    performance = _render_performance_section()
    audience = _render_audience_context()
    controls = _render_refresh_controls()

    inputs = {
        **product_inputs,
        **{key: value for key, value in winner_inputs.items() if not key.endswith("_upload")},
        **controls,
        "performance_mode": performance["performance_mode"],
        "winning_period": performance["winning_period"],
        "recent_period": performance["recent_period"],
        "audience_context": audience,
        "original_prompt_available": bool(
            _multiline_text(winner_inputs.get("original_prompt_text"))
            or winner_inputs.get("original_prompt_upload") is not None
        ),
        "metrics_csv_available": performance.get("imported_csv") is not None,
    }
    reset_col, generate_col = st.columns([1, 3])
    if reset_col.button(
        "Reset",
        icon=":material/restart_alt:",
        key=f"{STATE_PREFIX}reset",
        use_container_width=True,
    ):
        reset_creative_refresh_state()
        st.rerun()
    generate = generate_col.button(
        "Generate Creative Refresh Package",
        type="primary",
        icon=":material/auto_awesome:",
        key=f"{STATE_PREFIX}generate",
        use_container_width=True,
    )
    if generate:
        winning_asset = None
        upload_errors = []
        winning_upload = winner_inputs.get("winning_upload")
        if winning_upload is not None:
            try:
                winning_asset = validate_winning_creative(
                    winning_upload.getvalue(),
                    filename=winning_upload.name,
                )
                inputs["winning_creative_signature"] = winning_asset["signature"]
                inputs["winning_creative_filename"] = winning_asset["filename"]
            except CreativeRefreshValidationError as error:
                upload_errors.append(str(error))
        original_upload = winner_inputs.get("original_prompt_upload")
        if original_upload is not None:
            try:
                validate_original_prompt_upload(
                    original_upload.getvalue(),
                    filename=original_upload.name,
                )
            except CreativeRefreshValidationError as error:
                upload_errors.append(str(error))

        errors = validate_creative_refresh_inputs(
            inputs,
            winning_creative=winning_asset,
            csv_selection_error=performance.get("csv_selection_error") or "",
        )
        if upload_errors:
            errors.setdefault("winning_ad", []).extend(upload_errors)
        st.session_state[VALIDATION_STATE_KEY] = errors
        if errors:
            st.error("Complete the highlighted Creative Refresh fields. Your entered values have been kept.")
            for messages in errors.values():
                for message in messages:
                    st.caption(f"- {message}")
        else:
            result = build_creative_refresh_result(inputs, performance["diagnosis"])
            st.session_state[RESULT_STATE_KEY] = result
            st.session_state.pop(SAVE_STATE_KEY, None)
            record_activity_log(
                "ad_prompt_generated",
                "Ads",
                f"Generated Creative Refresh package: {inputs['product_name']}",
                entity_type="ad_prompt",
                entity_id=result["context_key"],
                metadata={
                    "campaign_type": inputs["campaign_type"],
                    "country": inputs["country"],
                    "diagnosis": performance["diagnosis"]["classification"],
                },
            )

    result = st.session_state.get(RESULT_STATE_KEY)
    if isinstance(result, dict) and result.get("prompt"):
        _render_generated_result(
            result,
            winning_upload=winner_inputs.get("winning_upload"),
            original_prompt_upload=winner_inputs.get("original_prompt_upload"),
            imported_csv=performance.get("imported_csv"),
        )


render_creative_refresh_page = render_page
