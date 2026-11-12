"""Owner Home publication and dated fallback using synthetic briefs only."""

import json
from datetime import date
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import home_sports_morning_brief as brief
import os_accounts
import supabase_backend as db
from tests.test_auto_editions_jobs import database  # noqa: F401


TODAY = date(2026, 11, 13)
OWNER = {"email": "owner@example.test", "role": "admin"}


@pytest.fixture(autouse=True)
def owner_configuration(monkeypatch):
    for key in os_accounts.REPORTING_OWNER_ENV_KEYS:
        monkeypatch.setenv(key, OWNER["email"])
    monkeypatch.setattr(brief, "sydney_date", lambda: TODAY)


def edition(day="2026-11-13", recommendation="Schedule the campaign after the official announcement."):
    return json.dumps({
        "date": day,
        "recommendations": [
            {"title": "Fixture release", "recommendation": recommendation,
             "links": [{"label": "Official source", "url": "https://sports.example.test/fixtures"}]},
        ],
    })


def test_publishing_rejects_a_worker_before_opening_storage(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(brief, "connect", connection)
    with pytest.raises(PermissionError):
        brief.publish(edition(), {**OWNER, "role": "worker"})
    connection.assert_not_called()


def test_payload_validates_date_and_links():
    with pytest.raises(ValueError, match="after today"):
        brief.parse_edition(edition("2026-11-14"), TODAY)
    with pytest.raises(ValueError, match="HTTPS"):
        brief.parse_edition(edition().replace("https:", "javascript:"), TODAY)
    with pytest.raises(ValueError, match="credentials"):
        brief.parse_edition(edition().replace("https://", "https://name@"), TODAY)


def test_publisher_updates_only_its_setting_and_rejects_older_editions(database, monkeypatch):
    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    monkeypatch.setattr(db, "connect", jobs.connect)
    monkeypatch.setattr(brief, "connect", jobs.connect)
    sql.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (%s, %s::jsonb, now())",
        ("other", json.dumps({"active": True})),
    )

    prior = brief.publish(edition("2026-11-12"), OWNER)
    assert db.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False) == prior
    current = brief.publish(edition(), OWNER)
    assert brief.publish(edition(), OWNER) == current
    with pytest.raises(ValueError, match="newer"):
        brief.publish(edition("2026-11-12"), OWNER)
    assert db.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False) == current
    assert db.get_app_setting("other", ensure_schema_first=False) == {"active": True}


def test_home_form_publishes_and_updates_the_dated_display(monkeypatch):
    previous = brief.parse_edition(edition("2026-11-12"), TODAY)
    current = brief.parse_edition(edition(recommendation="![example](https://example.test/image.png)"), TODAY)
    # Two stories can cite the same source without duplicating widget keys.
    current["recommendations"] *= 2
    monkeypatch.setattr(brief, "get_app_setting", Mock(side_effect=[previous, current]))
    publish = Mock(return_value=current)
    monkeypatch.setattr(brief, "publish", publish)
    app = AppTest.from_string("""
from datetime import date
import streamlit as st
import home_sports_morning_brief as brief
brief.render(st, {"email": "owner@example.test", "role": "admin"}, date(2026, 11, 13))
""").run()
    assert not app.exception
    assert any("Today's brief is pending" in caption.value for caption in app.caption)
    app.text_area[0].set_value(edition())
    app.button[0].click().run()
    assert not app.exception
    publish.assert_called_once_with(edition(), OWNER)
    assert app.success[0].value == "Published the 2026-11-13 Morning Brief."
    assert any("13 November 2026" in caption.value for caption in app.caption)
    assert any(r"\!\[example\]" in item.value for item in app.markdown)
