"""Hosted handoff regressions; synthetic database and content only."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock

import pytest
import daily_brief_worker as worker
import home_design_refresh as refresh
import home_sports_morning_brief as sports
import home_meta_morning_brief as meta
import os_accounts
import supabase_backend as db
from tests.test_auto_editions_jobs import database  # noqa: F401
from tests.test_home_sports_morning_brief import TODAY, OWNER, edition


@pytest.fixture
def setup(database, monkeypatch):
    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    for module in (db, sports, worker, refresh, meta):
        monkeypatch.setattr(module, "connect", jobs.connect)
        if hasattr(module, "sydney_date"):
            monkeypatch.setattr(module, "sydney_date", lambda: TODAY)
    for key in os_accounts.REPORTING_OWNER_ENV_KEYS:
        monkeypatch.setenv(key, OWNER["email"])
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, "get_user", lambda _: {**OWNER, "session_version": 1})
    monkeypatch.setattr(os_accounts, "can_access_page", lambda *_: True)
    monkeypatch.setattr(os_accounts, "can_access_reporting", lambda *_: True)
    return sql


def payload():
    return {**json.loads(edition()), "full_brief": "Complete verified synthetic sports edition."}


def candidate():
    return dict(product_id="123", handle="synthetic-art", title="Synthetic artwork", reason="artwork",
                evidence="Verified thumbnail hierarchy issue.", suggestion="A collector concept. " * 12,
                sessions=None, orders=None)


def test_design_length_is_repaired_without_changing_evidence(setup):
    value = dict(date=str(TODAY), candidates=[candidate()])
    original = json.loads(json.dumps(value))
    worker.enqueue("design_refresh", value, dict(sub="owner", version="1"))
    assert value == original
    assert worker.process_one()
    result = worker.status("design_refresh")
    assert result["verified"] and result["matches_submission"]
    saved = db.get_app_setting(refresh.KEY, ensure_schema_first=False)["candidates"][0]
    assert len(saved["suggestion"]) <= 220
    assert saved["evidence"] == value["candidates"][0]["evidence"]


def test_validation_names_the_bad_field():
    value = dict(date=str(TODAY), candidates=[candidate()])
    with pytest.raises(ValueError, match=r"candidates\[0\].suggestion exceeds 220"):
        refresh.parse(json.dumps(value), TODAY)


def test_publication_readback_is_required_and_recovers(setup, monkeypatch):
    parse, publish, limit = worker.BRIEFS["sports"]
    publishing = Mock(return_value=payload())  # A success response without a durable write.
    monkeypatch.setitem(worker.BRIEFS, "sports", (parse, publishing, limit))
    worker.enqueue("sports", payload(), dict(sub="owner", version="1"))
    assert worker.process_one()
    status = worker.status("sports")
    assert not status["verified"] and status["status"] == "retrying"
    monkeypatch.setitem(worker.BRIEFS, "sports", (parse, publish, limit))
    setup.execute("UPDATE app_settings SET updated_at=now()-interval '3 minutes'")
    assert worker.process_one()
    assert worker.status("sports")["verified"]


def test_transient_outage_can_recover_after_more_than_three_attempts(setup, monkeypatch):
    parse, publish, limit = worker.BRIEFS["sports"]
    failing = Mock(side_effect=TimeoutError)
    monkeypatch.setitem(worker.BRIEFS, "sports", (parse, failing, limit))
    worker.enqueue("sports", payload(), dict(sub="owner", version="1"))
    for _ in range(4):
        assert worker.process_one()
        assert worker.status("sports")["status"] == "retrying"
        setup.execute("UPDATE app_settings SET updated_at=now()-interval '3 minutes'")
    monkeypatch.setitem(worker.BRIEFS, "sports", (parse, publish, limit))
    assert worker.process_one()
    assert worker.status("sports")["attempts"] == 5
    assert worker.status("sports")["verified"]


def test_existing_home_publication_is_visible_without_a_queue_job(setup):
    sports.publish(json.dumps(payload()), OWNER)
    status = worker.status("sports")
    assert status["status"] == "completed" and status["verified"]
    assert status["matches_submission"] is None
    assert not worker.process_one()


def test_meta_verification_ignores_server_enriched_metrics(setup, monkeypatch):
    monkeypatch.setattr(meta, "account_roas", lambda _: None)
    monkeypatch.setattr(meta, "device_orders", lambda _: None)
    value = dict(date=str(TODAY), report_date="2026-11-12", roas=None, orders=3, actions=[],
                 summary="Keep the strongest verified creative running.",
                 recommendations=["Review the active baseball edition."])
    worker.enqueue("meta", value, dict(sub="owner", version="1"))
    assert worker.process_one()
    assert worker.status("meta")["verified"]
    assert worker.status("meta")["matches_submission"]


def test_ten_minute_reconciliation_recovers_lost_home_write(setup):
    worker.enqueue("sports", payload(), dict(sub="owner", version="1"))
    assert worker.process_one()
    setup.execute("DELETE FROM app_settings WHERE key LIKE 'home_sports_morning_brief%'")
    now = datetime(TODAY.year, TODAY.month, TODAY.day, 5, 30, tzinfo=ZoneInfo("Australia/Sydney"))
    assert worker.reconcile_morning(now)
    assert not worker.reconcile_morning(now)
    assert worker.status("sports")["status"] == "retrying"
    assert worker.process_one()
    assert worker.status("sports")["verified"]


def test_reconciliation_records_missing_sources_and_final_deadline(setup):
    now = datetime(TODAY.year, TODAY.month, TODAY.day, 6, 31, tzinfo=ZoneInfo("Australia/Sydney"))
    assert worker.reconcile_morning(now)
    saved = db.get_app_setting(f"hosted_daily_brief_health:{TODAY}", ensure_schema_first=False)
    assert saved["deadline_reached"] and not saved["ready"]
    assert saved["briefs"]["meta"]["stage"] == "research_or_submission"
    assert not worker.reconcile_morning(now.replace(hour=4))
