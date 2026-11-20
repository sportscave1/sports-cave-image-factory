"""Synthetic report, permission, pagination and hosted publication regressions."""
from copy import deepcopy
from datetime import date
import json
from unittest.mock import Mock

import pytest
import google_ads_reviews as reviews
import google_ads_reporting as reporting
import os_accounts
from tests.test_auto_editions_jobs import database  # noqa: F401

TODAY = date(2026, 11, 20)
OWNER = {"email": "owner@example.test", "role": "admin", "session_version": 1}


def edition():
    return {"date": str(TODAY), "period_start": "2026-11-13", "period_end": "2026-11-19",
        "currency": "AUD", "summary": "Synthetic weekly audit.",
        "platforms": [{"source": "google_ads", "status": "unavailable",
            "period_start": "2026-11-13", "period_end": "2026-11-19", "currency": "AUD",
            "spend": None, "purchases": None, "value": None, "basis": "No fresh Ads inputs."},
            {"source": "shopify", "status": "verified",
            "period_start": "2026-11-13", "period_end": "2026-11-19", "currency": "AUD",
            "spend": None, "purchases": 2, "value": 80, "basis": "Unique synthetic created orders."}],
        "channels": [{"channel": "Google paid", "orders": 1, "value": 40},
                     {"channel": "Unknown", "orders": 1, "value": 40}],
        "tracking": [{"label": "Purchase", "status": "open", "detail": "Verify exact IDs.",
                      "checked_on": str(TODAY)}],
        "findings": ["Missing source fields remain unknown."], "actions": ["Review tracking."],
        "sources": ["Synthetic offline fixture only."]}


def test_report_normalizes_without_mutating_input():
    raw = edition()
    assert reviews.parse(raw, today=TODAY)["revision"] == 1
    assert "revision" not in raw


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(period_end="2026-11-20"),
    lambda e: e["platforms"][0].update(spend=10),
    lambda e: e["platforms"][1].update(period_end="2026-11-12"),
    lambda e: e["channels"][0].update(orders=4),
    lambda e: e["channels"][0].update(value=400),
    lambda e: e["channels"][0].update(value=float("nan")),
    lambda e: e.update(summary="Contact customer@example.test"),
    lambda e: e.update(revision=True),
    lambda e: e["tracking"][0].update(checked_on="2026-11-21"),
    lambda e: e["channels"].append(deepcopy(e["channels"][0])),
])
def test_report_rejects_ambiguous_or_unsafe_data(mutate):
    value = edition()
    mutate(value)
    with pytest.raises(ValueError):
        reviews.parse(value, today=TODAY)


@pytest.fixture
def stored(database, monkeypatch):
    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz)")
    monkeypatch.setattr(reviews, "connect", jobs.connect)
    monkeypatch.setattr(reviews, "sydney_date", lambda: TODAY)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, "get_user", lambda _: OWNER)
    monkeypatch.setattr(reviews, "can_view", lambda user: user == OWNER)
    monkeypatch.setattr(os_accounts, "is_reporting_owner", lambda user: user == OWNER)
    return sql


def test_queue_publishes_with_exact_readback_and_no_home_mutation(stored):
    claims = {"sub": "owner", "version": "1"}
    first = reviews.enqueue(edition(), claims)
    assert first["status"] == "scheduled" and not first["verified"]
    assert reviews.process_one()
    actual = reviews.enqueue(edition(), claims)
    assert actual["status"] == "completed" and actual["verified"] and actual["sha256"]
    assert len(reviews.history()) == 1
    assert not reviews.process_one()
    stored.execute("SELECT key FROM app_settings WHERE key LIKE 'home_%'")
    assert not stored.fetchall()
    changed = edition()
    changed["summary"] = "Corrected synthetic review."
    with pytest.raises(ValueError, match="next revision"):
        reviews.enqueue(changed, claims)
    changed["revision"] = 2
    reviews.enqueue(changed, claims)
    assert reviews.process_one()
    assert [r["edition"]["revision"] for r in reviews.history()] == [2, 1]


def test_revoked_owner_cannot_submit_or_publish(stored, monkeypatch):
    reviews.enqueue(edition(), {"sub": "owner", "version": "1"})
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, "get_user", lambda _: {**OWNER, "session_version": 2})
    with pytest.raises(PermissionError):
        reviews.enqueue(edition(), {"sub": "owner", "version": "1"})
    assert reviews.process_one()
    assert reviews.history() == []


def test_missing_publication_is_recovered_from_accepted_submission(stored):
    claims = {"sub": "owner", "version": "1"}
    reviews.enqueue(edition(), claims)
    assert reviews.process_one()
    stored.execute("DELETE FROM app_settings WHERE key LIKE 'google_ads_review:%'")
    retry = reviews.enqueue(edition(), claims)
    assert retry["status"] == "scheduled" and not retry["verified"]
    assert reviews.process_one()
    assert reviews.enqueue(edition(), claims)["verified"]


def test_transient_publication_failure_is_retryable(stored, monkeypatch):
    reviews.enqueue(edition(), {"sub": "owner", "version": "1"})
    read = reviews._status
    monkeypatch.setattr(reviews, "_status", Mock(side_effect=TimeoutError))
    assert reviews.process_one()
    assert not reviews.history()
    monkeypatch.setattr(reviews, "_status", read)
    stored.execute("UPDATE app_settings SET updated_at=now()-interval '3 minutes'")
    assert reviews.process_one()
    assert reviews.enqueue(edition(), {"sub": "owner", "version": "1"})["verified"]


def test_legacy_connector_routes_google_edition_only_to_google(stored, monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import chatgpt_crm_mcp as mcp
    monkeypatch.setenv("SPORTS_CAVE_HOSTED_BRIEFS", "1")
    key = b"synthetic-private-report-key"
    monkeypatch.setattr(mcp, "_key", lambda: key)
    monkeypatch.setattr(mcp, "_active_owner", lambda *args: True)
    client = TestClient(Starlette(routes=[Route(mcp.MCP_PATH, mcp.mcp, methods=["POST"])]))
    def call(name, arguments, scope=mcp.PUBLISH_SCOPE):
        access = mcp._seal(key, "access", {"sub": "owner", "version": "1", "scope": scope,
                                         "iss": mcp.ISSUER, "aud": mcp.RESOURCE})
        return client.post(mcp.MCP_PATH, headers={"Authorization": "Bearer " + access}, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}).json()["result"]
    value = {**edition(), "destination": "ads_google"}
    assert call("submit_daily_home_brief", {"kind": "meta", "edition": value})["structuredContent"]["destination"] == "ads_google"
    assert reviews.process_one()
    assert call("submit_google_ads_review", {"edition": value})["structuredContent"]["verified"]
    assert call("submit_google_ads_review", {"edition": value}, mcp.GROWTH_SCOPE)["isError"]
    assert len(call("get_google_ads_reviews", {}, mcp.GROWTH_SCOPE)["structuredContent"]["reviews"]) == 1


def test_meta_pages_preserve_unknowns_and_read_every_page(monkeypatch):
    import crm_meta_history as meta
    def row(spend, purchases):
        return {"metrics": {"spend": spend, "purchases": purchases, "purchase_value": None}}
    reader = Mock(side_effect=[
        {"rows": [row(4, 1)], "next_cursor": "2026-11-14/2"},
        {"rows": [row(6, None)], "next_cursor": None, "currency": "AUD",
         "timezone": "Australia/Sydney", "captured_at": "2026-11-20T00:00:00Z"}])
    monkeypatch.setattr(meta, "meta_ad_history", reader)
    value = reporting.meta(date(2026, 11, 19))
    assert reader.call_count == 2
    assert value["known_totals"] == {"spend": 10, "purchases": 1, "purchase_value": None}
    assert value["missing_rows"]["purchases"] == 1
    assert value["status"] == "partial"


def test_connected_source_failure_does_not_fabricate_ads_metrics(monkeypatch):
    monkeypatch.setattr(reporting, "ga4", Mock(side_effect=TimeoutError))
    monkeypatch.setattr(reporting, "shopify", lambda end: {"status": "connected"})
    monkeypatch.setattr(reporting, "meta", lambda end: {"status": "partial"})
    result = reporting.connected_sources(date(2026, 11, 19))
    assert result["sources"]["ga4"]["status"] == "unavailable"
    assert result["sources"]["shopify"]["status"] == "connected"
    assert result["google_ads"]["status"] == "manual_review_required"


def test_ga4_uses_only_the_audited_property(monkeypatch):
    reports = Mock()
    reports.connection.return_value = {"ga4_property_id": "properties/999"}
    monkeypatch.setattr(reporting, "GoogleReports", lambda: reports)
    assert reporting.ga4(date(2026, 11, 19))["status"] == "property_mismatch"
    reports.ga4.assert_not_called()


def test_navigation_and_page_render_synthetic_review(monkeypatch):
    import ads_navigation
    import ads_google_page as page
    from streamlit.testing.v1 import AppTest
    value = reviews.parse(edition(), today=TODAY)
    monkeypatch.setattr(reviews, "can_view", lambda _: True)
    monkeypatch.setattr(reviews, "history", lambda: [{"edition": value,
        "published_at": "2026-11-20T00:00:00Z", "sha256": reviews.digest(value)}])
    monkeypatch.setattr(page, "sydney_date", lambda: TODAY)
    assert ads_navigation.ADS_NAV_LABELS["Google"] == "Google"
    test = AppTest.from_string("import ads_google_page\nads_google_page.render_page({})").run(timeout=15)
    assert not test.exception
    assert test.title[0].value == "Google"
    assert [t.label for t in test.tabs] == ["Overview", "Weekly reviews", "Tracking", "Prompts"]
    assert test.metric[0].value == "—"  # No fabricated Google spend.


def test_google_page_denies_data_before_reading_storage(monkeypatch):
    import ads_google_page
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(reviews, "can_view", lambda _: False)
    reader = Mock(side_effect=AssertionError("Must not read private reports"))
    monkeypatch.setattr(reviews, "history", reader)
    test = AppTest.from_string("import ads_google_page\nads_google_page.render_page({})").run(timeout=15)
    assert not test.exception
    reader.assert_not_called()
    assert not test.tabs
