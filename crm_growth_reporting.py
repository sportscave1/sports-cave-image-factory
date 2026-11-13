"""Bounded, read-only Google and Sports reports for the private CRM connector."""

from datetime import datetime, timedelta
import logging
import re
from zoneinfo import ZoneInfo

from analytics_contracts import GA4ReportContract
from google_direct_reporting import GoogleReports
from home_sports_morning_brief import SETTING_KEY
from supabase_backend import get_app_setting


LOG = logging.getLogger(__name__)
DEVICE = GA4ReportContract(
    "crm_devices", "Orders and funnel by device", "CRM",
    ("deviceCategory",), ("sessions", "addToCarts", "checkouts", "ecommercePurchases"),
    "device", (), 16, "not applicable",
)
ACQUISITION = GA4ReportContract(
    "crm_acquisition", "Acquisition and funnel", "CRM",
    ("sessionDefaultChannelGroup", "sessionSource", "sessionMedium"),
    ("sessions", "engagedSessions", "addToCarts", "checkouts", "ecommercePurchases"),
    "session acquisition", (), 1000, "not applicable",
)
LANDING = GA4ReportContract(
    "crm_landing", "Landing page and device funnel", "CRM",
    ("landingPage", "deviceCategory"),
    ("sessions", "engagedSessions", "ecommercePurchases"),
    "session landing page", (("sessions", True),), 5000, "not applicable",
)


def _ga4(report, connection, contract, start, end):
    data = report.ga4(connection["ga4_property_id"], contract, start, end)
    timezone = data["property_timezone"]
    if not timezone or end >= datetime.now(ZoneInfo(timezone)).date():
        return {"status": "reporting_day_incomplete"}
    rows = data["rows"]
    if contract == LANDING:
        rows = rows[:40]
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "timezone": timezone, "quality": data["quality"]["status"],
        "fetched_at": data["fetched_at"], "rows": rows, "total_rows": len(data["rows"]),
    }


def device_orders(day):
    """Return only explicit, verified GA4 device purchase counts for Home."""
    report = GoogleReports()
    connection = report.connection()
    result = _ga4(report, connection, DEVICE, day, day)
    if result.get("quality") != "GA4 verified" or not result["rows"]:
        return None
    counts = {"desktop": None, "mobile": None}
    seen = set()
    for row in result["rows"]:
        device = row["dimensions"].get("deviceCategory")
        if device in counts:
            raw = row["metrics"].get("ecommercePurchases", "")
            if device in seen or not re.fullmatch(r"[0-9]{1,7}", raw) or int(raw) > 1_000_000:
                return None
            counts[device] = int(raw)
            seen.add(device)
    return {**counts, "timezone": result["timezone"]} if seen else None


def _available(name, fetch):
    try:
        return fetch()
    except Exception as error:
        LOG.warning("crm_growth_source_unavailable source=%s type=%s", name, type(error).__name__)
        return {"status": "unavailable"}


def _gsc_period(report, start, end):
    daily = report.gsc(start, end, ("date",), {})
    fields = ("clicks", "impressions", "ctr", "average_position")

    def ranked(dimension):
        rows = report.gsc(start, end, (dimension,), {})
        return [
            {dimension: row[dimension].partition("?")[0] if dimension == "page" else row[dimension],
             **{key: float(row[key]) for key in fields}}
            for row in sorted(rows, key=lambda item: item["impressions"], reverse=True)[:40]
        ]

    return {
        "start": start.isoformat(), "end": end.isoformat(), "timezone": "America/Los_Angeles",
        "final_days_with_rows": sorted(row["date"] for row in daily),
        "daily": [{key: row[key] if key == "date" else float(row[key]) for key in ("date", *fields)}
                  for row in daily],
        "top_queries_by_impressions": _available("gsc_queries", lambda: ranked("query")),
        "top_pages_by_impressions": _available("gsc_pages", lambda: ranked("page")),
    }


def growth_report(day):
    report = GoogleReports()
    connection = report.connection()
    report = report.for_request(connection)
    ga4 = {}
    gsc = {}
    for name, end in (("current", day), ("prior", day - timedelta(days=7))):
        start = end - timedelta(days=6)
        ga4[name] = {
            contract.key: _available(contract.key, lambda: _ga4(report, connection, contract, start, end))
            for contract in (DEVICE, ACQUISITION, LANDING)
        }
        # Compare finalized Search Console periods and expose actual days returned.
        gsc_end = end - timedelta(days=3)
        gsc[name] = _available("gsc", lambda: _gsc_period(report, gsc_end - timedelta(days=6), gsc_end))
    return {"ga4": ga4, "search_console": gsc}


def published_sports_edition(day):
    edition = get_app_setting(SETTING_KEY, ensure_schema_first=False)
    if not edition or edition.get("date") != day.isoformat():
        return {"date": day.isoformat(), "status": "pending"}
    return edition
