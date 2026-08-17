"""Canonical GA4 report contracts and exact date-range rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


GA4_API_VERSION = "v1beta"
DATE_PRESETS = (
    "Today",
    "Yesterday",
    "Last 7 days",
    "Last 28 days",
    "Last 30 days",
    "Last 90 days",
    "Custom",
)
COMPARISON_OPTIONS = ("Off", "Previous period", "Previous year")


@dataclass(frozen=True)
class GA4ReportContract:
    key: str
    label: str
    ui_report: str
    dimensions: tuple[str, ...]
    metrics: tuple[str, ...]
    metric_scope: str
    ordering: tuple[tuple[str, bool], ...]
    row_limit: int
    currency_behavior: str
    comparisons: tuple[str, ...] = COMPARISON_OPTIONS
    filters: tuple[tuple[str, str, str], ...] = ()
    realtime: bool = False


_CONTRACTS = {
    "overview_totals": GA4ReportContract(
        "overview_totals",
        "Overview totals",
        "Reports snapshot / overview totals",
        (),
        (
            "activeUsers", "newUsers", "sessions", "screenPageViews",
            "engagementRate", "eventCount", "keyEvents", "ecommercePurchases",
            "purchaseRevenue", "totalRevenue",
        ),
        "mixed exact-range totals",
        (),
        1,
        "property currency; never combined with Shopify",
    ),
    "trend": GA4ReportContract(
        "trend",
        "Performance trend",
        "Overview trend",
        ("date",),
        ("sessions",),
        "selected exact metric by date",
        (("date", False),),
        10_000,
        "selected metric behavior",
    ),
    "trend_active_users": GA4ReportContract(
        "trend_active_users",
        "Active users trend",
        "Overview trend",
        ("date",),
        ("activeUsers",),
        "user",
        (("date", False),),
        10_000,
        "not applicable",
    ),
    "trend_views": GA4ReportContract(
        "trend_views",
        "Views trend",
        "Overview trend",
        ("date",),
        ("screenPageViews",),
        "event",
        (("date", False),),
        10_000,
        "not applicable",
    ),
    "trend_key_events": GA4ReportContract(
        "trend_key_events",
        "Key events trend",
        "Overview trend",
        ("date",),
        ("keyEvents",),
        "event",
        (("date", False),),
        10_000,
        "not applicable",
    ),
    "traffic_acquisition": GA4ReportContract(
        "traffic_acquisition",
        "Traffic acquisition",
        "Traffic acquisition: Session default channel group",
        ("sessionDefaultChannelGroup",),
        (
            "sessions", "engagedSessions", "engagementRate", "eventCount",
            "keyEvents", "sessionKeyEventRate", "totalRevenue",
        ),
        "session",
        (("sessions", True), ("sessionDefaultChannelGroup", False)),
        10_000,
        "property currency",
    ),
    "pages_screens": GA4ReportContract(
        "pages_screens",
        "Pages and screens",
        "Engagement: Pages and screens",
        ("pageTitle", "pagePathPlusQueryString"),
        ("screenPageViews", "activeUsers", "eventCount", "keyEvents", "totalRevenue"),
        "event and user",
        (("screenPageViews", True), ("pageTitle", False)),
        25_000,
        "property currency",
    ),
    "landing_pages": GA4ReportContract(
        "landing_pages",
        "Landing pages",
        "Engagement: Landing page",
        ("landingPagePlusQueryString",),
        ("sessions", "activeUsers", "newUsers", "engagementRate", "keyEvents", "totalRevenue"),
        "session",
        (("sessions", True), ("landingPagePlusQueryString", False)),
        25_000,
        "property currency",
    ),
    "countries": GA4ReportContract(
        "countries",
        "Countries",
        "User attributes: Demographic details",
        ("country", "countryId"),
        ("activeUsers", "sessions", "engagementRate", "totalRevenue"),
        "user and session",
        (("activeUsers", True), ("countryId", False)),
        10_000,
        "property currency",
    ),
    "devices": GA4ReportContract(
        "devices",
        "Devices",
        "Tech: Tech details",
        ("deviceCategory",),
        ("activeUsers", "sessions", "engagementRate", "totalRevenue"),
        "user and session",
        (("activeUsers", True), ("deviceCategory", False)),
        1_000,
        "property currency",
    ),
    "events": GA4ReportContract(
        "events",
        "Events",
        "Engagement: Events",
        ("eventName",),
        ("eventCount", "totalUsers", "keyEvents", "eventValue"),
        "event",
        (("eventCount", True), ("eventName", False)),
        25_000,
        "event value as reported by GA4",
    ),
    "ecommerce_products": GA4ReportContract(
        "ecommerce_products",
        "Ecommerce products",
        "Monetization: Ecommerce purchases",
        ("itemName", "itemId"),
        ("itemsViewed", "itemsAddedToCart", "itemsPurchased", "itemRevenue"),
        "item",
        (("itemRevenue", True), ("itemName", False)),
        25_000,
        "item revenue in property currency",
    ),
    "realtime": GA4ReportContract(
        "realtime",
        "Realtime",
        "Realtime overview",
        ("country", "deviceCategory"),
        ("activeUsers", "eventCount"),
        "realtime last 30 minutes",
        (("activeUsers", True), ("country", False)),
        10_000,
        "not applicable",
        comparisons=("Off",),
        realtime=True,
    ),
}

GA4_REPORT_CONTRACTS = MappingProxyType(_CONTRACTS)


def report_contract(key):
    try:
        return GA4_REPORT_CONTRACTS[str(key)]
    except KeyError as error:
        raise ValueError(f"Unknown GA4 report contract: {key}") from error


def _safe_zone(timezone_name):
    try:
        return ZoneInfo(str(timezone_name or "UTC"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def property_today(timezone_name, *, now=None):
    now = now or datetime.now(_safe_zone(timezone_name))
    if now.tzinfo is None:
        now = now.replace(tzinfo=_safe_zone(timezone_name))
    return now.astimezone(_safe_zone(timezone_name)).date()


def _shift_year(value, years=-1):
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def resolve_date_range(
    preset,
    *,
    timezone_name,
    comparison="Previous period",
    custom_start=None,
    custom_end=None,
    today=None,
):
    today = today or property_today(timezone_name)
    preset = str(preset or "Last 28 days")
    if preset == "Today":
        start = end = today
    elif preset == "Yesterday":
        start = end = today - timedelta(days=1)
    elif preset == "Custom":
        start = custom_start
        end = custom_end
        if not isinstance(start, date) or not isinstance(end, date) or start > end:
            raise ValueError("Choose a valid inclusive custom date range.")
    else:
        days = {
            "Last 7 days": 7,
            "Last 28 days": 28,
            "Last 30 days": 30,
            "Last 90 days": 90,
        }.get(preset)
        if not days:
            raise ValueError(f"Unknown date preset: {preset}")
        end = today
        start = end - timedelta(days=days - 1)

    comparison = str(comparison or "Off")
    previous_start = previous_end = None
    if comparison == "Previous period":
        span = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=span - 1)
    elif comparison == "Previous year":
        previous_start = _shift_year(start)
        previous_end = _shift_year(end)
    elif comparison != "Off":
        raise ValueError(f"Unknown comparison option: {comparison}")

    return {
        "preset": preset,
        "timezone": str(timezone_name or "UTC"),
        "start_date": start,
        "end_date": end,
        "comparison": comparison,
        "previous_start_date": previous_start,
        "previous_end_date": previous_end,
        "inclusive_days": (end - start).days + 1,
        "preliminary": end >= today - timedelta(days=2),
    }


def filter_expression(filters):
    filters = tuple(filters or ())
    if not filters:
        return None
    expressions = []
    for field, match_type, value in filters:
        expressions.append(
            {
                "filter": {
                    "fieldName": str(field),
                    "stringFilter": {
                        "matchType": str(match_type or "EXACT"),
                        "value": str(value),
                    },
                }
            }
        )
    return expressions[0] if len(expressions) == 1 else {"andGroup": {"expressions": expressions}}


def request_spec(contract, start_date, end_date, *, filters=(), metric_override=""):
    contract = report_contract(contract) if isinstance(contract, str) else contract
    metrics = (str(metric_override),) if metric_override else contract.metrics
    combined_filters = (*contract.filters, *tuple(filters or ()))
    return {
        "api_version": GA4_API_VERSION,
        "contract": contract.key,
        "date_ranges": ((start_date.isoformat(), end_date.isoformat()),),
        "dimensions": contract.dimensions,
        "metrics": metrics,
        "filters": combined_filters,
        "ordering": contract.ordering,
        "currency_behavior": contract.currency_behavior,
        "row_limit": contract.row_limit,
        "realtime": contract.realtime,
    }


def request_hash(property_id, spec, *, currency=""):
    payload = {
        "property_id": str(property_id),
        "currency": str(currency or ""),
        **dict(spec),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def safe_rate(numerator, denominator):
    try:
        denominator = float(denominator)
        return None if denominator == 0 else float(numerator) / denominator
    except (TypeError, ValueError):
        return None
