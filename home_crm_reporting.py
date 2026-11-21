"""Private Home CRM: Shopify order cohort, GA4 ID matches and separate paid ROAS."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
import re
from threading import Event, Lock, Thread
from time import monotonic
from zoneinfo import ZoneInfo

from analytics_contracts import GA4ReportContract
from display_snapshot import Snapshots
from google_direct_reporting import GoogleReports, MemoryReports

SYDNEY = ZoneInfo("Australia/Sydney")
VERSION = 3
PREFIX = "home_crm_v3:"
CHANNELS = ("Facebook paid", "Google paid", "Organic", "Other", "Unresolved")
DEVICES = ("mobile", "desktop", "other")
SNAPSHOTS = Snapshots(workers=2, limit=24, ttl=900, retry=60, max_age=21600, byte_limit=2_000_000)
SAVED = MemoryReports(max_bytes=2_000_000)
FORCED = {}
FORCE_LOCK = Lock()
PURCHASES = GA4ReportContract("home_crm_transactions", "Purchase source and device by transaction",
    "CRM", ("transactionId", "sessionSourceMedium", "deviceCategory"), ("ecommercePurchases",),
    "purchase session; exact transaction ID", (), 10000, "not applicable")
ORDERS_QUERY = """query HomeCRMOrders($query: String!, $after: String) {
  currentAppInstallation { accessScopes { handle } }
  orders(first: 250, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes { id createdAt cancelledAt test
      customerJourneySummary { ready lastVisit { source sourceType landingPage
        utmParameters { source medium campaign } } }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""


def order_id(value):
    value = str(value or "")
    match = re.fullmatch(r"(?:gid://shopify/Order/)?([1-9][0-9]*)", value)
    return match[1] if match else None


def channel(source_medium):
    source, sep, medium = str(source_medium or "").lower().partition(" / ")
    if not sep or source in ("", "(not set)", "(data not available)"):
        return "Unresolved"
    if source == "google" and medium in ("cpc", "ppc", "paid_search", "paidsearch", "paid_shopping"):
        return "Google paid"
    meta = source in ("facebook", "instagram", "meta", "fb", "ig") or bool(
        re.fullmatch(r"(?:[a-z]+[.])?(?:facebook|instagram)[.]com", source))
    if meta and medium in ("cpc", "ppc", "paid", "paid_social", "paid-social", "paidsocial"):
        return "Facebook paid"
    if medium in ("organic", "organic_social", "organic-social"):
        return "Organic"
    if meta or medium in ("product_sync", "sag_organic"):
        return "Unresolved"
    return "Other"


def orders(start, end):
    import shopify_sync
    config = shopify_sync.get_config()
    if config.get("store_domain") != "sportscave-nb.myshopify.com":
        raise ValueError("Unexpected Shopify store.")
    low = datetime.combine(start, time.min, SYDNEY)
    high = datetime.combine(end + timedelta(days=1), time.min, SYDNEY)
    search = f"status:any created_at:>='{low.isoformat()}' created_at:<'{high.isoformat()}'"
    cursor, cursors, ids = None, set(), set()
    journeys = {}
    deadline = monotonic() + 50
    for _ in range(40):
        if monotonic() > deadline:
            raise TimeoutError("Shopify reporting time limit.")
        data, _ = shopify_sync.graphql_request(ORDERS_QUERY,
            {"query": search, "after": cursor}, config=config, timeout=12)
        if start < datetime.now(SYDNEY).date() - timedelta(days=60):
            scopes = {s["handle"] for s in (data.get("currentAppInstallation") or {}).get("accessScopes", [])}
            if "read_all_orders" not in scopes:
                raise ValueError("Older Shopify orders require existing read_all_orders access; totals withheld.")
        connection = data["orders"]
        for row in connection["nodes"]:
            stamp = datetime.fromisoformat(row["createdAt"].replace("Z", "+00:00"))
            if not low <= stamp < high:
                raise ValueError("Shopify returned an order outside the requested dates.")
            if row["test"] is False and row["cancelledAt"] is None:
                identity = order_id(row["id"])
                if not identity:
                    raise ValueError("Shopify returned an invalid order ID.")
                ids.add(identity)
                from order_source_attribution import last_visit
                journeys[identity] = last_visit(row.get("customerJourneySummary"))
        info = connection["pageInfo"]
        if not info["hasNextPage"]:
            return {"status": "verified", "ids": ids, "journeys": journeys, "fetched_at": datetime.now(timezone.utc).isoformat()}
        cursor = info["endCursor"]
        if not cursor or cursor in cursors:
            raise ValueError("Shopify pagination did not finish.")
        cursors.add(cursor)
    raise ValueError("Shopify reporting row limit.")


def ga4(start, end):
    report = GoogleReports()
    connection = report.connection()
    if str(connection.get("ga4_property_id", "")).removeprefix("properties/") != "355333982":
        raise ValueError("Select the audited Sports Cave GA4 property.")
    result = report.for_request(connection).ga4(connection["ga4_property_id"], PURCHASES, start, end)
    if result["property_timezone"] != "Australia/Sydney" or result["quality"]["status"] != "GA4 verified":
        raise ValueError("GA4 source quality or timezone could not be verified.")
    return {"status": "verified", "rows": result["rows"], "fetched_at": result["fetched_at"]}


def ledger(order_ids, rows, journeys=None):
    matches = {}
    for row in rows:
        if float(row["metrics"].get("ecommercePurchases", 0)) <= 0:
            continue
        dims = row["dimensions"]
        identity = order_id(dims.get("transactionId"))
        if identity not in order_ids:
            continue
        device = dims.get("deviceCategory")
        matches.setdefault(identity, set()).add((
            channel(dims.get("sessionSourceMedium")), device if device in ("mobile", "desktop") else "other"))
    table = {name: dict(channel=name, mobile=0, desktop=0, other=0, total=0) for name in CHANNELS}
    conflicted = 0
    ga4_counts = {name: 0 for name in CHANNELS}
    paid_organic_differences = 0
    reconciliations, reasons = {}, {}
    for identity in order_ids:
        observations = matches.get(identity, set())
        sources = {s for s, _ in observations}
        devices = {d for _, d in observations}
        source = next(iter(sources)) if len(sources) == 1 else "Unresolved"
        # Same order cohort and exact-ID deduplication as the main table. Missing
        # or multiple session-source observations remain unresolved in this model.
        ga4_counts[source] += 1
        if journeys is not None:
            evidence = journeys.get(identity, {"channel":"Unresolved", "reason":"journey_pending_or_missing"})
            chosen = evidence["channel"]
            paid_organic_differences += (
                source in ("Facebook paid", "Google paid") and chosen == "Organic"
                or chosen in ("Facebook paid", "Google paid") and source == "Organic")
            if chosen != source:
                pair = (source, chosen)
                reconciliations[pair] = reconciliations.get(pair, 0) + 1
            source = chosen
            reason = evidence["reason"]
            reasons[reason] = reasons.get(reason, 0) + 1
        device = next(iter(devices)) if len(devices) == 1 else "other"
        conflicted += len(sources) > 1 or len(devices) > 1
        table[source][device] += 1
        table[source]["total"] += 1
    return {"rows": list(table.values()), "orders": len(order_ids),
            "matched": len(matches), "unmatched": len(order_ids)-len(matches), "conflicted": conflicted,
            "source_reconciliation": [{"ga4_channel":a,"shopify_channel":b,"orders":n} for (a,b),n in sorted(reconciliations.items())],
            "source_reasons": reasons, "ga4_channel_orders": ga4_counts,
            "paid_organic_differences": paid_organic_differences}


def meta(start, end):
    import meta_ads_client
    import meta_review_live as live
    from meta_reporting_contract import validate_account
    from meta_review_analysis import action, number
    config = meta_ads_client.get_meta_config()
    account_id = config["ad_account_id"]
    reader = live.Reader(config, max_pages=3, seconds=45)
    account = validate_account(reader.get(account_id,
        {"fields": "account_id,currency,timezone_name"}), account_id)
    if account["timezone_name"] != "Australia/Sydney" or account["currency"] != "AUD":
        raise ValueError("Meta reporting currency or timezone mismatch.")
    rows = reader.pages(account_id + "/insights", {
        **live.date_params(start, end), "level": "account",
        "fields": "account_id,date_start,date_stop,spend,action_values,purchase_roas,website_purchase_roas",
        "use_unified_attribution_setting": "true", "action_report_time": "impression"})
    if not rows:
        return {"status": "no_delivery", "roas": None, "note": "No delivery row; ROAS is not defined."}
    if len(rows) != 1:
        raise ValueError("Unexpected Meta account roll-up.")
    row = rows[0]
    if (str(row.get("account_id")) != account_id.removeprefix("act_")
            or row.get("date_start") != str(start) or row.get("date_stop") != str(end)):
        raise ValueError("Unexpected Meta account or reporting dates.")
    spend, value = number(row.get("spend")), action(row, "purchase_value", "action_values")
    if spend == 0:
        return {"status": "no_spend", "roas": None, "note": "No spend; ROAS is not defined."}
    reported = action(row, "purchases", "purchase_roas")
    if reported is None:
        reported = action(row, "purchases", "website_purchase_roas")
    roas = value / spend if value is not None and spend else reported
    return {"status": "verified" if roas is not None else "missing_purchase_value",
            "roas": roas, "note": "Meta account-attributed purchase value / spend; impression-date, unified ad-set attribution. Includes Facebook and Instagram.",
            "fetched_at": datetime.now(timezone.utc).isoformat()}


def google(start, end):
    import google_ads_api_reporting as ads
    if end >= datetime.now(SYDNEY).date():
        return {"status": "partial_day", "roas": None, "note": "Google Ads appears after the reporting day completes."}
    totals = {"spend": Decimal(0), "value": Decimal(0), "purchases": Decimal(0)}
    current, chunks = start, []
    while current <= end:
        last = min(end, current+timedelta(days=30))
        report = ads.report(current, last)
        if report.get("status") != "connected" or report.get("currency") != "AUD" or report.get("timezone") != "Australia/Sydney":
            return {"status": report.get("status", "unavailable"), "roas": None, "note": report.get("note", "Google Ads unavailable.")}
        for key in totals:
            totals[key] += Decimal(str(report["totals"][key]))
        chunks.append(report["fetched_at"])
        current = last + timedelta(days=1)
    return {"status": "verified", "roas": float(totals["value"]/totals["spend"]) if totals["spend"] else None,
            "purchases": float(totals["purchases"]),
            "spend": float(totals["spend"]), "value": float(totals["value"]),
            "note": "PM021126 primary purchase value / spend by ad interaction date. Budget remains A$20/day.",
            "fetched_at": max(chunks)}


def _available(fetch):
    try:
        return fetch()
    except Exception as error:
        return {"status": "unavailable", "note": "Source could not be verified (" + type(error).__name__ + ")."}


def build(start, end, *, readers=None):
    readers = readers or {"shopify": orders, "ga4": ga4, "facebook": meta, "google": google}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {name: pool.submit(_available, lambda f=fetch: f(start, end)) for name, fetch in readers.items()}
        sources = {name: future.result() for name, future in pending.items()}
    shop, analytics = sources["shopify"], sources["ga4"]
    cohort = ledger(shop["ids"], analytics.get("rows", []), shop.get("journeys", {})) if shop["status"] == "verified" else None
    # Only aggregate data leaves this function or enters durable storage.
    coverage = {name: {k: v for k, v in result.items() if k not in ("rows", "ids", "journeys")}
                for name, result in sources.items()}
    return {"version": VERSION, "start": str(start), "end": str(end), "timezone": "Australia/Sydney",
            "checked_at": datetime.now(timezone.utc).isoformat(), "partial_day": end >= datetime.now(SYDNEY).date(),
            "ledger": cohort, "coverage": coverage,
            "roas": {name: sources[name].get("roas") for name in ("facebook", "google")},
            "basis": "One non-test, non-cancelled Shopify order per row, by creation date. Source is Shopify last recorded visit, using explicit paid/organic evidence; Google product-feed tags alone do not prove paid or organic and stay unresolved. Device is from exact GA4 purchase transaction-ID matches. GA4 purchase-session source is a separate model for the same order cohort, not added to this table. Organic last visit does not rule out an earlier ad interaction. Google Ads purchases and ROAS use ad interaction dates, can include later purchases, and cannot identify individual Shopify orders from this aggregate report. Paid platforms can claim overlapping credit."}


def key(start, end):
    return PREFIX + str(start) + ":" + str(end)


def saved(start, end):
    from supabase_backend import get_app_setting
    value = SAVED.read(key(start, end), 30,
        lambda: get_app_setting(key(start, end), ensure_schema_first=False))
    return value if value and (value.get("start"), value.get("end"), value.get("version")) == (str(start), str(end), VERSION) else None


def refresh(start, end):
    from supabase_backend import connect
    value = build(start, end)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()""",
            (key(start, end), json.dumps(value)))
    SAVED.clear()
    return value


def request(start, end, *, force=False):
    if type(start) is not date or type(end) is not date or not 0 <= (end-start).days <= 93:
        raise ValueError("Choose a bounded reporting window.")
    if force:
        with FORCE_LOCK:
            now = monotonic()
            if now - FORCED.get(key(start, end), -1000) > 60:
                SNAPSHOTS.invalidate(key(start, end))
                FORCED[key(start, end)] = now
                for old in list(FORCED):
                    if now - FORCED[old] > 3600:
                        del FORCED[old]
    state = SNAPSHOTS.read(key(start, end), lambda: refresh(start, end))
    value = state["value"]
    if value is None:
        try:
            value = saved(start, end)
        except Exception:
            value = None
    return {"state": state["state"], "data": value}


def tick():
    """Primary app keeps yesterday warm after 05:00 Sydney, without waiting."""
    now = datetime.now(SYDNEY)
    if now.hour >= 5:
        day = now.date() - timedelta(days=1)
        request(day, day)


_APP_THREAD = None
_APP_LOCK = Lock()


def _loop(stop):
    import logging
    while not stop.is_set():
        try:
            tick()
        except Exception as error:
            logging.getLogger(__name__).warning("home_crm_refresh_failed type=%s", type(error).__name__)
        stop.wait(30)


def start_app_reconciler():
    """Use the primary app's existing provider grants; never copy worker secrets."""
    import atexit
    global _APP_THREAD
    with _APP_LOCK:
        if _APP_THREAD is not None and _APP_THREAD.is_alive():
            return True
        stop = Event()
        _APP_THREAD = Thread(target=_loop,args=(stop,),name="home-crm-refresh",daemon=True)
        atexit.register(stop.set)
        _APP_THREAD.start()
    return True
