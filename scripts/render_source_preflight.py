"""Standalone read-only probe, suitable for `python -B -` in Render Web Shell.

No application imports, database access, files written, retries or business writes.
Shopify client-credentials authentication may issue a token in process memory.
"""
import ast
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import requests

ACCESS_QUERY = "query SportsCaveOrderReadAccess { currentAppInstallation { app { title } accessScopes { handle } } }"


def safe_id(value):
    value = str(value or "")
    return value if re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value) else None


def call(session, method, url, **kwargs):
    # One attempt only. Never emit response text, exception text or request URLs.
    try:
        response = session.request(method, url, timeout=(5, 20), allow_redirects=False, **kwargs)
        result = {"http_status": response.status_code,
                  "request_id": safe_id(response.headers.get("x-request-id") or response.headers.get("x-fb-request-id")),
                  "served_api_version": None}
        served = response.headers.get("x-shopify-api-version") or response.headers.get("facebook-api-version") or ""
        if re.fullmatch(r"(?:20\d{2}-(?:01|04|07|10)|v[0-9]+\.0)", served):
            result["served_api_version"] = served
        try:
            data = response.json()
        except ValueError:
            return None, {**result, "status": "invalid_response"}
        if not isinstance(data, dict):
            return None, {**result, "status": "invalid_response"}
        error = data.get("error")
        if isinstance(error, dict):
            result.update(error_code=error.get("code") if type(error.get("code")) is int else None,
                          error_subcode=error.get("error_subcode") if type(error.get("error_subcode")) is int else None,
                          fbtrace_id=safe_id(error.get("fbtrace_id")))
        if response.status_code != 200 or error or data.get("errors"):
            return None, {**result, "status": "request_failed"}
        return data, result
    except requests.RequestException:
        return None, {"status": "transport_failed"}


def shopify(session, env):
    domain = str(env.get("SHOPIFY_STORE_DOMAIN", "")).strip().lower()
    domain = urlparse(domain if "://" in domain else "https://" + domain).hostname or ""
    version = env.get("SHOPIFY_API_VERSION", "").strip()
    client_id, client_secret = (env.get(k, "").strip() for k in ("SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET"))
    token = env.get("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
    base = {"credential_context": "OS Render service environment", "requested_api_version": version if re.fullmatch(r"20\d{2}-(01|04|07|10)", version) else None}
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", domain) or not re.fullmatch(r"20\d{2}-(01|04|07|10)", version):
        return {**base, "status": "missing_or_invalid_shop_configuration"}
    base["shop"] = domain
    # Match get_config()/get_shopify_access_token_details() precedence exactly.
    if client_id and client_secret:
        auth, result = call(session, "POST", f"https://{domain}/admin/oauth/access_token",
            data={"grant_type":"client_credentials", "client_id":client_id, "client_secret":client_secret})
        if auth is None:
            return {**base, **result, "stage": "authentication"}
        token = auth.get("access_token")
        base["auth_mode"] = "client_credentials"
    else:
        base["auth_mode"] = "admin_access_token"
    if not isinstance(token, str) or not token:
        return {**base, "status": "missing_credential"}
    data, result = call(session, "POST", f"https://{domain}/admin/api/{version}/graphql.json",
        headers={"X-Shopify-Access-Token": token}, json={"query": ACCESS_QUERY})
    if data is None:
        return {**base, **result, "stage": "order_read_scopes"}
    app = data.get("data", {}).get("currentAppInstallation")
    if not isinstance(app, dict) or not isinstance(app.get("accessScopes"), list):
        return {**base, **result, "status": "missing_scope_response"}
    scopes = {s.get("handle") for s in app["accessScopes"] if isinstance(s, dict)}
    return {**base, **result, "status": "read_succeeded", "read_orders": "read_orders" in scopes,
            "write_orders": "write_orders" in scopes, "read_all_orders": "read_all_orders" in scopes,
            "historical_order_scope_present": "read_all_orders" in scopes and bool(scopes & {"read_orders","write_orders"})}


def deployed_meta_version():
    # Read a literal default from deployed source without importing application code.
    for item in ast.parse(Path("meta_ads_client.py").read_text(encoding="utf-8")).body:
        if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEFAULT_META_API_VERSION" for t in item.targets):
            return ast.literal_eval(item.value)
    raise ValueError("No deployed default")


def meta(session, env, at=None):
    account = env.get("META_AD_ACCOUNT_ID", "").strip().removeprefix("act_")
    token = env.get("META_ACCESS_TOKEN", "").strip()
    version = env.get("META_API_VERSION", "").strip()
    if not version:
        try:
            version = deployed_meta_version()
        except (ValueError, OSError, SyntaxError):
            return {"status":"missing_version_configuration"}
    base = {"credential_context":"OS Render service environment", "requested_api_version":version if re.fullmatch(r"v[0-9]+\.0", version) else None}
    if not re.fullmatch(r"[0-9]+", account) or not token or not re.fullmatch(r"v[0-9]+\.0", version):
        return {**base, "status":"missing_or_invalid_account_configuration"}
    endpoint = f"https://graph.facebook.com/{version}/act_{account}"
    data, result = call(session, "GET", endpoint,
        params={"access_token":token,"fields":"account_id,currency,timezone_name"})
    if data is None:
        return {**base, **result, "stage":"account_read"}
    if str(data.get("account_id")) != account:
        return {**base, **result, "status":"account_mismatch"}
    try:
        zone = ZoneInfo(data["timezone_name"])
        if not re.fullmatch(r"[A-Z]{3}", str(data.get("currency") or "")):
            raise ValueError("Unknown currency")
    except (KeyError, ValueError, TypeError):
        return {**base, **result, "status":"incomplete_account_metadata"}
    day = ((at or datetime.now(timezone.utc)).astimezone(zone).date()-timedelta(days=1)).isoformat()
    base.update(account_id=account,currency=data["currency"],timezone=data["timezone_name"],day=day,
                account_read={**result,"status":"read_succeeded"})
    data, result = call(session, "GET", endpoint+"/insights", params={"access_token":token,
        "fields":"account_id,date_start,date_stop,spend,impressions", "level":"ad", "time_increment":1,
        "time_range":json.dumps({"since":day,"until":day}), "limit":1,
        "use_unified_attribution_setting":"true", "action_report_time":"impression"})
    if data is None:
        return {**base, **result, "stage":"insights_read"}
    rows = data.get("data")
    if not isinstance(rows,list) or any(not isinstance(r,dict) or str(r.get("account_id"))!=account
        or r.get("date_start")!=day or r.get("date_stop")!=day for r in rows):
        return {**base, **result, "status":"invalid_insights_response"}
    return {**base, **result, "status":"read_succeeded", "sample_rows":len(rows),
            "has_more":bool((data.get("paging") or {}).get("next")), "complete_report":False,
            "note":"Access sample only; no persistence or business reconciliation."}


def main():
    with requests.Session() as session:
        session.trust_env = False  # Never forward credentials via an ambient proxy.
        output = {"checked_at":datetime.now(timezone.utc).isoformat(), "database_writes":0,
                  "business_writes":0,"ai_calls":0,"attempts_per_request":1}
        for name, probe in (("shopify",shopify),("meta",meta)):
            try:
                output[name] = probe(session, os.environ)
            except Exception:
                output[name] = {"status":"probe_failed_without_details"}
        print(json.dumps(output,sort_keys=True))


if __name__ == "__main__":
    main()
