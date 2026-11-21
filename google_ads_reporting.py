"""Read existing GA4, Shopify and Meta connections without changing any ads."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from analytics_contracts import GA4ReportContract
from google_direct_reporting import GoogleReports
from sports_sales_calendar import sydney_date

PURCHASES = GA4ReportContract(
    "google_workspace_purchases", "Purchase sessions by source", "Ads",
    ("sessionSourceMedium",), ("ecommercePurchases", "purchaseRevenue"),
    "purchase session", (), 1000, "not applicable")


def period(end):
    return end - timedelta(days=6), end


def _available(fetch):
    try:
        return fetch()
    except Exception:
        return {"status": "unavailable", "note": "Source could not be read. Check its existing connection."}


def ga4(end):
    start, end = period(end)
    reports = GoogleReports()
    connection = reports.connection()
    property_id = connection.get("ga4_property_id")
    if not property_id:
        return {"status": "not_connected"}
    if str(property_id).removeprefix("properties/") != "355333982":
        return {"status": "property_mismatch",
                "note": "The existing GA4 connection selects a different property from this Google Ads audit. Review Analytics connection settings before comparing its figures."}
    result = reports.ga4(property_id, PURCHASES, start, end)
    tz = result["property_timezone"]
    if not tz or end >= datetime.now(ZoneInfo(tz)).date():
        return {"status": "reporting_day_incomplete"}
    return {"status": result["quality"]["status"], "property_id": property_id,
            "timezone": tz, "currency": result["currency"], "fetched_at": result["fetched_at"],
            "rows": result["rows"], "note": "GA4 purchase-session attribution; separate from Google Ads credit."}


def shopify(end):
    from chatgpt_reporting import _read, ORDERS_SQL, SYDNEY
    start, end = period(end)
    bounds = (datetime.combine(start, time.min, SYDNEY),
              datetime.combine(end + timedelta(days=1), time.min, SYDNEY))
    return {"status": "connected", **_read(ORDERS_SQL, bounds),
            "timezone": "Australia/Sydney",
            "note": "Stored Shopify orders by processed time (creation fallback). Known paid totals do not deduct refunds. Not the journey ledger."}


def meta(end):
    from crm_meta_history import meta_ad_history
    start, end = period(end)
    cursor, seen, rows = None, set(), []
    for page in range(100):
        data = meta_ad_history(start, end, cursor, page == 0)
        rows.extend(data["rows"])
        following = data["next_cursor"]
        if following is None:
            break
        if following in seen:
            raise ValueError("Repeated Meta cursor.")
        seen.add(following)
        # The internal reader takes a parsed cursor, unlike its MCP interface.
        from crm_meta_history import meta_history_args
        _, _, cursor, _ = meta_history_args(
            {"since": start.isoformat(), "until": end.isoformat(), "cursor": following})
    else:
        raise ValueError("Meta pagination did not finish.")
    totals, missing = {}, {}
    for field in ("spend", "purchases", "purchase_value"):
        values = [r["metrics"].get(field) for r in rows]
        missing[field] = sum(v is None for v in values)
        totals[field] = float(sum((Decimal(str(v)) for v in values if v is not None), Decimal(0))) if any(v is not None for v in values) else None
    return {"status": "partial" if any(missing.values()) else "connected",
            "currency": data["currency"], "timezone": data["timezone"], "fetched_at": data["captured_at"],
            "rows": len(rows), "known_totals": totals, "missing_rows": missing,
            "note": "All pages read; impression-date reporting, per-ad-set attribution. Nulls remain unknown."}


def connected_sources(end):
    if end.weekday() != 3 or end >= sydney_date():
        raise ValueError("Choose a completed Thursday for a weekly report.")
    start, end = period(end)
    import google_ads_api_reporting as ads
    with ThreadPoolExecutor(max_workers=4) as pool:
        ads_future = pool.submit(ads.report, start, end)
        futures = {name: pool.submit(_available, lambda f=fetch: f(end))
                   for name, fetch in (("ga4", ga4), ("shopify", shopify), ("meta", meta))}
        sources = {name: future.result() for name, future in futures.items()}
    return {"period_start": start.isoformat(), "period_end": end.isoformat(), "sources": sources,
            "google_ads": ads_future.result()}
