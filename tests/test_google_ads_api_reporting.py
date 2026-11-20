from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
import google_seo
import google_seo_api
import google_ads_api_reporting as ads

END = date(2026, 11, 19)
START = date(2026, 11, 13)
NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def store(scopes=None):
    connection = {"has_refresh_token": True, "granted_scopes": scopes if scopes is not None else [google_seo.GOOGLE_ADS_SCOPE]}
    return SimpleNamespace(get_connection=lambda: connection)


def response(rows):
    return SimpleNamespace(status_code=200, json=lambda: [{"results": rows}])


def settings(**overrides):
    row = {"customer": {"id": ads.CUSTOMER_ID, "currencyCode": "AUD", "timeZone": "Australia/Sydney"},
           "campaign": {"id": ads.CAMPAIGN_ID, "name": "Synthetic campaign", "status": "ENABLED"},
           "campaignBudget": {"amountMicros": "20000000"}}
    row.update(overrides)
    return row


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setattr(google_seo, "load_config", lambda: {})
    monkeypatch.setattr(google_seo, "access_token_for_connection",
                        lambda *args: ("synthetic-token", {"granted_scopes": [google_seo.GOOGLE_ADS_SCOPE]}))
    monkeypatch.delenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", raising=False)


def test_fixed_search_only_totals_and_fractional_purchase_credit(auth):
    post = Mock(side_effect=[
        response([settings()]),
        response([{"segments": {"date": "2026-11-14"}, "metrics": {"costMicros": "12000000", "clicks": "12", "impressions": "120"}},
                  {"segments": {"date": "2026-11-15"}, "metrics": {"costMicros": "8000000"}}]),
        response([{"segments": {"date": "2026-11-14"}, "metrics": {"conversions": 1.25, "conversionsValue": 100.50}},
                  {"segments": {"date": "2026-11-15"}, "metrics": {"conversions": .75, "conversionsValue": 59.50}}])])
    result = ads.fetch(START, END, store=store(), post=post, now=NOW)
    assert result["totals"] == {"spend": 20, "clicks": 12, "impressions": 120, "purchases": 2, "value": 160}
    assert len(result["daily"]) == 7
    assert result["budget_matches_plan"]
    for call in post.call_args_list:
        assert call.args[0] == f"https://googleads.googleapis.com/v26/customers/{ads.CUSTOMER_ID}/googleAds:searchStream"
        assert "mutate" not in call.args[0]
        assert f"campaign.id = {ads.CAMPAIGN_ID}" in call.kwargs["json"]["query"]
    assert "conversion_action_category = 'PURCHASE'" in post.call_args_list[2].kwargs["json"]["query"]


def test_no_scope_never_calls_google(auth):
    post = Mock()
    result = ads.fetch(START, END, store=store([]), post=post, now=NOW)
    assert result["status"] == "authorization_required"
    post.assert_not_called()


@pytest.mark.parametrize("row,code", [
    (settings(customer={"id": "1111111111", "currencyCode": "AUD", "timeZone": "Australia/Sydney"}), "account_mismatch"),
    (settings(customer={"id": ads.CUSTOMER_ID, "currencyCode": "USD", "timeZone": "Australia/Sydney"}), "account_mismatch"),
    (settings(campaign={"id": "11111111111"}), "campaign_missing"),
])
def test_wrong_identity_rejected_before_metrics(auth, row, code):
    post = Mock(return_value=response([row]))
    with pytest.raises(ads.AdsReportingError) as error:
        ads.fetch(START, END, store=store(), post=post, now=NOW)
    assert error.value.code == code
    assert post.call_count == 1


def test_current_day_rejected_in_account_timezone(auth):
    post = Mock(return_value=response([settings()]))
    with pytest.raises(ads.AdsReportingError, match="completed dates"):
        ads.fetch(START, date(2026, 11, 20), store=store(), post=post, now=NOW)
    assert post.call_count == 1


def test_non20_budget_observed_never_written(auth):
    post = Mock(side_effect=[response([settings(campaignBudget={"amountMicros": "25000000"})]), response([]), response([])])
    result = ads.fetch(START, END, store=store(), post=post, now=NOW)
    assert not result["budget_matches_plan"]
    assert result["daily_budget"] == 25
    assert result["totals"]["spend"] == 0
    assert all("searchStream" in c.args[0] for c in post.call_args_list)


def test_cloud_approval_error_is_actionable_and_redacted(auth):
    post = Mock(return_value=SimpleNamespace(status_code=403, json=lambda: {"error": {
        "message": "sensitive-provider-detail", "details": [{"errors": [{
            "errorCode": {"authorizationError": "CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION"}}]}]}}))
    with pytest.raises(ads.AdsReportingError) as error:
        ads.fetch(START, END, store=store(), post=post, now=NOW)
    assert error.value.code == "project_access_required"
    assert "sensitive-provider" not in str(error.value)


def test_bad_date_result_never_becomes_zero_report(auth):
    post = Mock(side_effect=[response([settings()]), response([{"segments": {"date": "2026-11-12"}}]), response([])])
    with pytest.raises(ads.AdsReportingError, match="outside"):
        ads.fetch(START, END, store=store(), post=post, now=NOW)


def test_oauth_ads_scope_is_explicit_and_seo_keeps_readonly_default():
    config = {"client_id": "synthetic", "redirect_uri": "https://example.com/callback"}
    regular = parse_qs(urlparse(google_seo.build_authorization_url("state", config)).query)["scope"][0]
    extended = parse_qs(urlparse(google_seo.build_authorization_url("state", config, ads=True)).query)["scope"][0]
    assert google_seo.GOOGLE_ADS_SCOPE not in regular
    assert google_seo.GOOGLE_ADS_SCOPE in extended
    assert google_seo.verify_required_scopes({"scope": extended}) == (*google_seo.GOOGLE_SCOPES, google_seo.GOOGLE_ADS_SCOPE)


def test_declined_ads_scope_keeps_existing_authorisation(monkeypatch):
    token = {"scope": " ".join(google_seo.GOOGLE_SCOPES), "access_token": "synthetic"}
    monkeypatch.setattr(google_seo, "exchange_authorization_code", lambda *args, **kwargs: token)
    existing = Mock()
    with pytest.raises(google_seo.GoogleSEOError, match="not approved"):
        google_seo.complete_authorization(existing, {"role": "Admin", "is_active": True}, "code", {}, require_ads=True)
    existing.save_authorization.assert_not_called()


def test_ads_callback_uses_server_bound_state_not_query(monkeypatch):
    owner = {"id": "synthetic"}
    monkeypatch.setattr(google_seo_api, "_request_admin", lambda _: owner)
    monkeypatch.setattr(google_seo, "default_store", lambda: "synthetic-store")
    monkeypatch.setattr(google_seo, "consume_oauth_state", lambda *args: {"return_page": "ads_google"})
    monkeypatch.setattr(google_seo, "load_config", lambda: {})
    complete = Mock()
    monkeypatch.setattr(google_seo, "complete_authorization", complete)
    request = SimpleNamespace(query_params={"state": "synthetic", "code": "synthetic", "page": "untrusted"})
    assert google_seo_api._complete_callback(request) == "ads_google"
    assert complete.call_args.kwargs["require_ads"] is True


def test_reporting_cache_changes_with_authorisation(monkeypatch):
    from google_direct_reporting import MemoryReports
    monkeypatch.setattr(ads, "CACHE", MemoryReports())
    fake = Mock(return_value={"status": "connected"})
    monkeypatch.setattr(ads, "fetch", fake)
    record = {"granted_scopes": []}
    connection = SimpleNamespace(get_connection=lambda: record)
    ads.report(START, END, store=connection)
    ads.report(START, END, store=connection)
    assert fake.call_count == 1
    record["granted_scopes"] = [google_seo.GOOGLE_ADS_SCOPE]
    ads.report(START, END, store=connection)
    assert fake.call_count == 2


@pytest.mark.parametrize("google_page_access", [True, False])
def test_installed_growth_tool_enforces_google_page_access(monkeypatch, google_page_access):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import chatgpt_crm_mcp as mcp
    monkeypatch.setattr(mcp, "_key", lambda: b"synthetic-reporting-key")
    monkeypatch.setattr(mcp, "_active_owner", lambda claims, page: google_page_access if page == "ads_google" else True)
    monkeypatch.setattr(mcp, "growth_report", lambda *args: {"ga4": {"status": "synthetic"}})
    reader = Mock(return_value={"status": "connected", "totals": {"spend": 20}})
    monkeypatch.setattr(ads, "report", reader)
    client = TestClient(Starlette(routes=[Route(mcp.MCP_PATH, mcp.mcp, methods=["POST"])]))
    access = mcp._seal(b"synthetic-reporting-key", "access", {"sub": "owner", "version": "1",
                      "scope": mcp.GROWTH_SCOPE, "iss": mcp.ISSUER, "aud": mcp.RESOURCE})
    result = client.post(mcp.MCP_PATH, headers={"Authorization": "Bearer " + access}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_growth_analytics", "arguments": {"date": str(END)}}}).json()["result"]
    assert not result.get("isError")
    assert ("google_ads" in result["structuredContent"]) is google_page_access
    assert reader.call_count == int(google_page_access)
    if google_page_access:
        reader.assert_called_once_with(START, END)


def test_page_loads_fresh_api_report_and_does_not_replace_history(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import ads_google_page as page
    import google_ads_reviews as reviews
    from tests.test_google_ads_workspace import edition, TODAY
    monkeypatch.setattr(reviews, "can_view", lambda _: True)
    monkeypatch.setattr(reviews, "history", lambda: [{"edition": reviews.parse(edition(), today=TODAY),
        "published_at": NOW.isoformat(), "sha256": "synthetic-review-digest"}])
    monkeypatch.setattr(page, "sydney_date", lambda: TODAY)
    monkeypatch.setattr(ads, "report", lambda *args: {
        "status": "connected", "period_start": str(START), "period_end": str(END),
        "fetched_at": NOW.isoformat(), "timezone": "Australia/Sydney", "totals": {
            "spend": 20, "purchases": 2, "value": 160}, "daily": [],
        "campaign_name": "Synthetic", "campaign_status": "ENABLED", "daily_budget": 20,
        "budget_matches_plan": True, "budget_shared": False, "note": "Synthetic read-only report"})
    test = AppTest.from_string("import ads_google_page\nads_google_page.render_page({})").run(timeout=15)
    assert not test.exception
    assert test.metric[0].value == "A$20.00"
    assert test.metric[4].value == "—"  # Historical unknown stays unknown.
