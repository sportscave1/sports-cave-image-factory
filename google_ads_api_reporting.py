"""Fixed-account Google Ads reporting. No mutation endpoints or user-supplied GAQL."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import math
import os
import re
from zoneinfo import ZoneInfo

import requests
import google_seo
from google_direct_reporting import MemoryReports

CUSTOMER_ID = "6581121605"
CAMPAIGN_ID = "24420240881"
API_VERSION = "v26"
CACHE = MemoryReports()
CONNECT_PATH = "/api/os/google/ads/connect"


class AdsReportingError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def connection_status(store=None):
    connection = (store or google_seo.default_store()).get_connection()
    if not connection.get("has_refresh_token") or connection.get("disconnected_at"):
        return {"status": "not_connected", "note": "Connect the existing Sports Cave Google account."}
    if google_seo.GOOGLE_ADS_SCOPE not in (connection.get("granted_scopes") or []):
        return {"status": "authorization_required",
                "note": "Authorise Google Ads reporting using the existing Google account."}
    return {"status": "authorised", "note": "Google access granted; API access and campaign reporting are checked when fetched."}


def _number(value):
    value = float(value or 0)  # Protobuf JSON omits default numeric zero values.
    if not math.isfinite(value) or value < 0:
        raise AdsReportingError("invalid_metrics", "Google returned invalid reporting metrics.")
    return value


def _read(query, token, post):
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    # Optional manager is an existing hierarchy, never a new account link.
    manager = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    if manager:
        if len(manager) != 10 or not manager.isdigit():
            raise AdsReportingError("manager_configuration", "Check the configured Google Ads manager ID.")
        headers["login-customer-id"] = manager
    response = post(
        f"https://googleads.googleapis.com/{API_VERSION}/customers/{CUSTOMER_ID}/googleAds:searchStream",
        headers=headers, json={"query": query}, timeout=(5, 40))
    if response.status_code != 200:
        codes = set()
        provider_message = ""
        try:
            error_payload = response.json().get("error", {})
            if isinstance(error_payload, dict):
                provider_message = str(error_payload.get("message") or "")
            for detail in error_payload.get("details", []):
                reason = str(detail.get("reason") or "")
                if re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", reason):
                    codes.add(reason)
                for error in detail.get("errors", []):
                    codes.update(str(v) for v in error.get("errorCode", {}).values()
                                 if re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", str(v)))
        except (ValueError, TypeError, AttributeError):
            pass
        if "CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION" in codes:
            raise AdsReportingError("project_access_required", "Google Cloud needs Explorer or higher Ads API access for production reporting.")
        if response.status_code == 401:
            raise AdsReportingError("reconnect_required", "Reconnect Google Ads access.")
        if response.status_code == 429:
            raise AdsReportingError("rate_limited", "Google Ads reporting is rate limited. Retry later.")
        # Fixed queries contain no customer contacts. Never reflect OAuth credentials
        # or provider contact addresses, even in diagnostic messages.
        detail = ""
        if response.status_code == 400:
            detail = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted]",
                            provider_message.replace(token, "[redacted]"))[:600]
        raise AdsReportingError("api_access_required" if response.status_code == 403 else "report_failed",
                                f"Google Ads could not return this report (HTTP {response.status_code}; {', '.join(sorted(codes)) or 'no Ads error code'}). {detail}".strip())
    payload = response.json()
    if not isinstance(payload, list):
        raise AdsReportingError("invalid_response", "Google Ads returned an unexpected response.")
    return [row for batch in payload for row in batch.get("results", [])]


def fetch(start, end, *, store=None, post=requests.post, now=None):
    """Completed dates only, fixed campaign; purchase category and primary conversions."""
    if type(start) is not date or type(end) is not date or not 0 <= (end-start).days <= 30:
        raise ValueError("Choose at most 31 completed reporting dates.")
    store = store or google_seo.default_store()
    state = connection_status(store)
    if state["status"] != "authorised":
        return state
    token, connection = google_seo.access_token_for_connection(store, google_seo.load_config())
    if google_seo.GOOGLE_ADS_SCOPE not in connection.get("granted_scopes", []):
        return {"status": "authorization_required", "note": "Reconnect Google Ads reporting."}
    settings = _read(
        "SELECT customer.id, customer.currency_code, customer.time_zone, campaign.id, campaign.name, "
        "campaign.status, campaign.advertising_channel_type, campaign.bidding_strategy_type, "
        "campaign.maximize_conversion_value.target_roas, campaign.target_roas.target_roas, "
        "campaign_budget.amount_micros, campaign_budget.explicitly_shared "
        f"FROM campaign WHERE campaign.id = {CAMPAIGN_ID}", token, post)
    if len(settings) != 1 or str(settings[0].get("campaign", {}).get("id")) != CAMPAIGN_ID:
        raise AdsReportingError("campaign_missing", "The configured Sports Cave campaign was not returned.")
    row = settings[0]
    account = row["customer"]
    if str(account.get("id")) != CUSTOMER_ID or account.get("currencyCode") != "AUD":
        raise AdsReportingError("account_mismatch", "Expected Sports Cave account 658-112-1605 in AUD.")
    tz = account.get("timeZone")
    instant = now or datetime.now(timezone.utc)
    if not tz or end >= instant.astimezone(ZoneInfo(tz)).date():
        raise AdsReportingError("incomplete_dates", "Choose completed dates in the Google Ads account timezone.")
    window = f"campaign.id = {CAMPAIGN_ID} AND segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'"
    delivery = _read("SELECT segments.date, metrics.cost_micros, metrics.clicks, metrics.impressions "
                     "FROM campaign WHERE " + window + " ORDER BY segments.date", token, post)
    purchases = _read("SELECT segments.date, metrics.conversions, metrics.conversions_value "
                     "FROM campaign WHERE " + window + " AND segments.conversion_action_category = 'PURCHASE' "
                     "ORDER BY segments.date", token, post)
    daily = {}
    for offset in range((end-start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        daily[day] = {"date": day, "spend": 0.0, "clicks": 0, "impressions": 0, "purchases": 0.0, "value": 0.0}
    for rows, fields in ((delivery, (("costMicros", "spend"), ("clicks", "clicks"), ("impressions", "impressions"))),
                         (purchases, (("conversions", "purchases"), ("conversionsValue", "value")))):
        for record in rows:
            day = record.get("segments", {}).get("date")
            if day not in daily:
                raise AdsReportingError("date_mismatch", "Google returned dates outside the requested report.")
            metrics = record.get("metrics", {})
            for provider, field in fields:
                value = _number(metrics.get(provider))
                daily[day][field] += value / 1_000_000 if field == "spend" else value
    totals = {field: float(sum(Decimal(str(r[field])) for r in daily.values()))
              for field in ("spend", "clicks", "impressions", "purchases", "value")}
    campaign, budget = row["campaign"], row.get("campaignBudget", {})
    current_budget = _number(budget.get("amountMicros")) / 1_000_000
    return {"status": "connected", "customer_id": CUSTOMER_ID, "campaign_id": CAMPAIGN_ID,
            "campaign_name": campaign.get("name"), "campaign_status": campaign.get("status"),
            "campaign_type": campaign.get("advertisingChannelType"), "timezone": tz, "currency": "AUD",
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "fetched_at": instant.isoformat(), "daily": list(daily.values()), "totals": totals,
            "daily_budget": current_budget, "budget_matches_plan": current_budget == 20,
            "budget_shared": bool(budget.get("explicitlyShared")),
            "bidding_strategy": campaign.get("biddingStrategyType"),
            "target_roas": (campaign.get("maximizeConversionValue", {}).get("targetRoas")
                            or campaign.get("targetRoas", {}).get("targetRoas")),
            "note": "Read-only Google Ads API. Primary PURCHASE conversions by ad interaction date; fractional attribution and later adjustments are possible. Platform credit can overlap Meta and differs from Shopify order-date sales. Budget is observed, never changed."}


def report(start, end, *, store=None):
    try:
        store = store or google_seo.default_store()
        connection = store.get_connection()
        identity = tuple(str(connection.get(k) or "") for k in
                         ("workspace_key", "connected_at", "updated_at", "disconnected_at", "granted_scopes"))
        return CACHE.read(("ads", identity, start.isoformat(), end.isoformat()), 15*60,
                          lambda: fetch(start, end, store=store))
    except AdsReportingError as error:
        return {"status": error.code, "note": str(error)}
    except Exception:
        return {"status": "unavailable", "note": "Google Ads reporting is unavailable. Check the existing connection."}
