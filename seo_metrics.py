"""GSC-only normalisation and evidence calculations."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation


GSC_COUNTRY_CODES = {
    "AUS": "AU",
    "AU": "AU",
    "USA": "US",
    "US": "US",
    "GBR": "UK",
    "GB": "UK",
    "UK": "UK",
    "CAN": "CA",
    "CA": "CA",
    "NZL": "NZ",
    "NZ": "NZ",
}

RANK_BUCKETS = (
    (1, 3, Decimal("1.00"), "Positions 1-3"),
    (4, 10, Decimal("0.75"), "Positions 4-10"),
    (11, 20, Decimal("0.40"), "Positions 11-20"),
    (21, 50, Decimal("0.10"), "Positions 21-50"),
    (51, None, Decimal("0"), "Above 50"),
)


def decimal_value(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def normalize_gsc_country(value):
    clean = str(value or "").strip().upper()
    return GSC_COUNTRY_CODES.get(clean, clean)


def normalize_query(value):
    return " ".join(str(value or "").strip().casefold().split())


def weighted_ctr(clicks, impressions):
    impressions = decimal_value(impressions)
    return None if not impressions else decimal_value(clicks) / impressions


def weighted_position(position_weight, impressions):
    impressions = decimal_value(impressions)
    return None if not impressions else decimal_value(position_weight) / impressions


def aggregate_query_rows(rows, *, market="", device=""):
    market = normalize_gsc_country(market)
    device = str(device or "").strip().upper()
    grouped = defaultdict(
        lambda: {
            "raw_queries": set(),
            "clicks": Decimal("0"),
            "impressions": Decimal("0"),
            "position_weight": Decimal("0"),
            "markets": set(),
            "devices": set(),
        }
    )
    for source in rows or ():
        country = normalize_gsc_country(source.get("country_code") or source.get("country"))
        row_device = str(source.get("device") or "").strip().upper()
        if market and country != market:
            continue
        if device and row_device != device:
            continue
        raw_query = str(source.get("raw_query") or source.get("query") or "").strip()
        key = normalize_query(raw_query)
        if not key:
            continue
        impressions = decimal_value(source.get("impressions"))
        position_weight = source.get("position_weight")
        if position_weight in (None, ""):
            position_weight = decimal_value(source.get("average_position")) * impressions
        bucket = grouped[key]
        bucket["raw_queries"].add(raw_query)
        bucket["clicks"] += decimal_value(source.get("clicks"))
        bucket["impressions"] += impressions
        bucket["position_weight"] += decimal_value(position_weight)
        if country:
            bucket["markets"].add(country)
        if row_device:
            bucket["devices"].add(row_device.title())

    result = []
    for key, bucket in grouped.items():
        impressions = bucket["impressions"]
        result.append(
            {
                "query": sorted(bucket["raw_queries"], key=lambda item: (len(item), item.casefold()))[0],
                "normalized_query": key,
                "raw_queries": sorted(bucket["raw_queries"]),
                "clicks": bucket["clicks"],
                "impressions": impressions,
                "ctr": weighted_ctr(bucket["clicks"], impressions),
                "average_position": weighted_position(bucket["position_weight"], impressions),
                "market_mix": sorted(bucket["markets"]),
                "device_mix": sorted(bucket["devices"]),
            }
        )
    return sorted(result, key=lambda row: (row["clicks"], row["impressions"]), reverse=True)


def rank_quality(rows):
    weighted = Decimal("0")
    total_impressions = Decimal("0")
    distribution = {label: Decimal("0") for _low, _high, _weight, label in RANK_BUCKETS}
    for row in rows or ():
        impressions = decimal_value(row.get("impressions"))
        position = decimal_value(row.get("average_position"))
        if impressions <= 0 or position <= 0:
            continue
        for low, high, weight, label in RANK_BUCKETS:
            if position >= low and (high is None or position <= high):
                weighted += impressions * weight
                distribution[label] += impressions
                total_impressions += impressions
                break
    if not total_impressions:
        return {"score": None, "distribution": distribution, "impressions": Decimal("0")}
    return {
        "score": Decimal("100") * weighted / total_impressions,
        "distribution": distribution,
        "impressions": total_impressions,
    }


def known_query_coverage(property_clicks, property_impressions, query_rows):
    visible_clicks = sum((decimal_value(row.get("clicks")) for row in query_rows or ()), Decimal("0"))
    visible_impressions = sum((decimal_value(row.get("impressions")) for row in query_rows or ()), Decimal("0"))
    return {
        "visible_clicks": visible_clicks,
        "visible_impressions": visible_impressions,
        "click_coverage": weighted_ctr(visible_clicks, property_clicks),
        "impression_coverage": weighted_ctr(visible_impressions, property_impressions),
    }


def opportunity_score(row):
    impressions = decimal_value(row.get("impressions"))
    ctr = decimal_value(row.get("ctr"))
    position = decimal_value(row.get("average_position"))
    click_change = decimal_value(row.get("click_change"))
    mapped = bool(row.get("mapped_target"))
    content_gap = bool(row.get("content_gap"))
    cannibalisation = decimal_value(row.get("cannibalisation_risk"))

    impression_score = min(Decimal("35"), impressions / Decimal("40"))
    position_score = Decimal("0")
    if Decimal("4") <= position <= Decimal("20"):
        position_score = Decimal("30") - abs(position - Decimal("10"))
    ctr_gap_score = min(Decimal("15"), max(Decimal("0"), Decimal("0.05") - ctr) * Decimal("300"))
    movement_score = min(Decimal("10"), max(Decimal("0"), click_change))
    mapping_score = Decimal("5") if not mapped else Decimal("0")
    content_score = Decimal("10") if content_gap else Decimal("0")
    risk_penalty = min(Decimal("15"), max(Decimal("0"), cannibalisation))
    score = max(
        Decimal("0"),
        min(
            Decimal("100"),
            impression_score + position_score + ctr_gap_score + movement_score + mapping_score + content_score - risk_penalty,
        ),
    )
    return {
        "score": score.quantize(Decimal("0.01")),
        "explanation": (
            f"Impressions {impressions}; position {position}; CTR {ctr}; "
            f"click movement {click_change}; {'unmapped' if not mapped else 'mapped'}; "
            f"content gap {'yes' if content_gap else 'no'}."
        ),
    }
