"""Owner Home publication and dated fallback using synthetic briefs only."""

import json
from datetime import date
from unittest.mock import Mock

import pytest

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


def test_cloud_submission_publishes_once_without_browser_session(database, monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import chatgpt_crm_mcp as mcp
    import daily_brief_worker as worker

    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    monkeypatch.setenv("SPORTS_CAVE_HOSTED_BRIEFS", "1")
    monkeypatch.setattr(worker, "sydney_date", lambda: TODAY)
    for module in (db, brief, worker):
        monkeypatch.setattr(module, "connect", jobs.connect)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, "get_user",
                        lambda _: {**OWNER, "session_version": 1})
    monkeypatch.setattr(os_accounts, "can_access_page", lambda *_: True)
    key = b"test-connector-secret"
    monkeypatch.setattr(mcp, "_key", lambda: key)
    client = TestClient(Starlette(routes=[Route(mcp.MCP_PATH, mcp.mcp, methods=["POST"])]))
    payload = {**json.loads(edition(TODAY.isoformat())), "full_brief": "Complete synthetic edition."}

    def submit(scope, value=payload):
        access = mcp._seal(key, "access", {"sub": "owner", "version": "1", "scope": scope,
                                          "iss": mcp.ISSUER, "aud": mcp.RESOURCE})
        response = client.post(mcp.MCP_PATH, headers={"Authorization": f"Bearer {access}"}, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "submit_daily_home_brief", "arguments": {"kind": "sports", "edition": value}},
        })
        return response.json()["result"]

    assert submit(mcp.SPORTS_SCOPE)["isError"]
    assert submit(mcp.PUBLISH_SCOPE)["structuredContent"]["status"] == "scheduled"
    assert submit(mcp.PUBLISH_SCOPE, {**payload, "full_brief": "Conflicting edition."})["isError"]
    assert worker.process_one()
    assert submit(mcp.PUBLISH_SCOPE)["structuredContent"]["status"] == "completed"
    assert db.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False)["full_brief"] == payload["full_brief"]
    assert not worker.process_one()


def test_hosted_brief_retry_is_delayed_and_publishes_after_recovery(database, monkeypatch):
    import daily_brief_worker as worker

    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    monkeypatch.setattr(worker, "sydney_date", lambda: TODAY)
    for module in (db, brief, worker):
        monkeypatch.setattr(module, "connect", jobs.connect)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, "get_user",
                        lambda _: {**OWNER, "session_version": 1})
    monkeypatch.setattr(os_accounts, "can_access_page", lambda *_: True)
    parse, publish, limit = worker.BRIEFS["sports"]

    def publish_after_failure(raw, owner):
        if publishing.call_count == 1:
            raise TimeoutError
        return publish(raw, owner)

    publishing = Mock(side_effect=publish_after_failure)
    monkeypatch.setitem(worker.BRIEFS, "sports", (parse, publishing, limit))
    payload = {**json.loads(edition(TODAY.isoformat())), "full_brief": "Complete synthetic edition."}
    worker.enqueue("sports", payload, {"sub": "owner", "version": "1"})
    assert worker.process_one()
    assert worker.status("sports")["status"] == "retrying"
    assert not worker.process_one()
    sql.execute("UPDATE app_settings SET updated_at = now() - interval '3 minutes'")
    assert worker.process_one()
    assert worker.status("sports")["status"] == "completed"
    assert worker.status("sports")["attempts"] == 2


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


def test_publisher_archives_older_editions_without_replacing_latest(database, monkeypatch):
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
    older = brief.publish(edition("2026-11-11"), OWNER)
    entries, cursor = brief.archive_page(TODAY, size=2)
    assert entries == [current, prior]
    assert cursor == "2026-11-12"
    assert brief.archive_page(TODAY, before=cursor) == ([older], None)
    assert db.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False) == current
    assert db.get_app_setting("other", ensure_schema_first=False) == {"active": True}


def test_home_has_compact_links_and_no_publish_form(monkeypatch):
    previous = brief.parse_edition(edition("2026-11-12", "<script>example</script>"), TODAY)
    monkeypatch.setattr(brief, "get_app_setting", Mock(return_value=previous))
    monkeypatch.setattr(brief, "archive_page", Mock(return_value=([], None)))
    st = Mock()
    brief.render(st, OWNER, TODAY)
    assert "Today's brief is pending" in st.caption.call_args.args[0]
    markup = st.html.call_args.args[0]
    assert "Create Design" in markup and "Create Ad" in markup
    assert "Sports Cave event: Fixture release" in markup
    assert "Show the photos in this chat first" in markup
    assert "generate the design based on the photos you showed" in markup
    assert "designs-canvas.psd" in markup
    assert "Step 3. Generate this design now" in markup
    assert "<h4>Fixture release</h4>" not in markup
    assert "/g/g-p-6a1e449948e881919c1e345006d63654/project" in markup
    assert "&lt;script&gt;example&lt;/script&gt;" in markup
    assert "Morning Brief JSON" not in markup
    assert "Sports calendar" in markup and "News / updates" in markup
    assert all(f'data-market-tab="{market}"' in markup for market in ("AUS", "USA", "UK"))
    st.form.assert_not_called()


def test_publisher_route_rejects_cross_origin_and_nonowners(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import home_morning_brief_publish as route

    get_user = Mock(return_value={**OWNER, "role": "worker"})
    publish = Mock(return_value={"date": "2026-11-13"})
    monkeypatch.setattr(route, "_request_user", get_user)
    monkeypatch.setattr(route, "publish", publish)
    client = TestClient(Starlette(routes=[Route(path, endpoint, methods=methods)
                                          for path, endpoint, methods in route.ROUTES]))
    payload = {"brief": edition()}
    assert client.get(route.PATH).status_code == 403
    assert client.get("/ops/morning-brief/history?sport=Rugby+League&market=AUS").status_code == 403
    assert client.post(route.PATH, data=payload, headers={"Origin": "https://other.test"}).status_code == 403
    publish.assert_not_called()
    get_user.return_value = OWNER
    assert "Morning Brief JSON" in client.get(route.PATH).text
    data = json.loads(edition())
    data["recommendations"][0].update(sport="Rugby League", markets=["AUS"])
    entry = brief.parse_edition(json.dumps(data), TODAY)
    monkeypatch.setattr(route, "sydney_date", lambda: TODAY)
    monkeypatch.setattr(route, "archive_page", Mock(return_value=([entry], "2026-11-12")))
    monkeypatch.setattr(route, "get_app_setting", Mock(return_value=None))
    history = client.get("/ops/morning-brief/history?sport=Rugby+League&market=AUS").json()
    assert "Fixture release" in history["html"] and history["before"] == "2026-11-12"
    assert client.get("/ops/morning-brief/history?sport=Rugby+League&market=UK").json()["html"] == ""
    response = client.post(route.PATH, data=payload, headers={"Origin": "http://testserver"})
    assert response.status_code == 200
    assert "Published the 2026-11-13 Morning Brief." in response.text
    publish.assert_called_once_with(edition(), OWNER)



def test_calendar_dates_history_and_product_identity(monkeypatch):
    from home_brief_calendar import calendar_rows
    from home_morning_brief_actions import article_html
    import ads_page

    value = json.loads(edition())
    article = value["recommendations"][0]
    article.update(sport="Rugby League", markets=["AUS"], start_date="2026-11-15", end_date="2026-11-17")
    article["links"].append({"label": "Product", "url": "https://www.sportscaveshop.com/products/fixture-final"})
    parsed = brief.parse_edition(json.dumps(value), TODAY)
    aus = {sport: (event, news) for sport, event, news in calendar_rows([parsed], "AUS", TODAY)}
    usa = {sport: (event, news) for sport, event, news in calendar_rows([parsed], "USA", TODAY)}
    assert aus["Rugby League"][0].title == "Rugby League World Cup finals"
    assert aus["Rugby League"][0].end == date(2026, 11, 15)
    assert aus["Rugby League"][1] and not usa["Rugby League"][1]
    assert 'href="/?page=ads&amp;brief_product=fixture-final"' in article_html(parsed["recommendations"][0], allow_ads=True)

    browser = Mock()
    browser.query_params = {"brief_product": "fixture-final"}
    browser.session_state = {}
    monkeypatch.setattr(ads_page, "st", browser)
    row = {"product_handle": "fixture-final", "shopify_product_id": "gid://shopify/Product/123", "title": "Fixture final"}
    ads_page._apply_morning_brief_product([row])
    assert browser.query_params == {}
    assert browser.session_state[ads_page.ADS_PRODUCT_SELECTOR_KEY] == ads_page._edition_ops_product_selector_identity(row)


def test_meta_brief_publication_and_home_display(monkeypatch, database):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import home_meta_morning_brief as meta
    import home_morning_brief_publish as route

    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    monkeypatch.setattr(db, "connect", jobs.connect)
    monkeypatch.setattr(meta, "connect", jobs.connect)
    monkeypatch.setattr(meta, "sydney_date", lambda: TODAY)
    live_roas = Mock(return_value=2.75)
    monkeypatch.setattr(meta, "account_roas", live_roas)
    devices = {"desktop": 2, "mobile": 0, "timezone": "Australia/Sydney"}
    monkeypatch.setattr(meta, "device_orders", Mock(return_value=devices))
    get_user = Mock(return_value=OWNER)
    monkeypatch.setattr(route, "_request_user", get_user)
    client = TestClient(Starlette(routes=[Route(path, endpoint, methods=methods)
                                          for path, endpoint, methods in route.ROUTES]))
    data = {
        "date": TODAY.isoformat(), "report_date": "2026-11-12",
        "roas": None, "orders": 0, "actions": ["review_creative"],
    }
    payload = {"brief": json.dumps(data)}
    assert client.get(meta.PATH).status_code == 403
    get_user.return_value = {**OWNER, "page_permissions": ["reporting"]}
    assert "Meta Morning Brief JSON" in client.get(meta.PATH).text
    assert client.post(meta.PATH, data=payload, headers={"Origin": "https://other.test"}).status_code == 403
    headers = {"Origin": "http://testserver"}
    legacy = {"date": TODAY.isoformat(), "summary": "AUD 122.10", "coverage": "Payouts",
              "metrics": {"roas": "$5", "spend": "$122.10"}, "recommendations": ["Budget $50"]}
    assert client.post(meta.PATH, data={"brief": json.dumps(legacy)}, headers=headers).status_code == 400
    unsafe = {**data, "actions": ["Payout $50"]}
    assert client.post(meta.PATH, data={"brief": json.dumps(unsafe)}, headers=headers).status_code == 400
    assert "Published the 2026-11-13 Meta Morning Brief." in client.post(meta.PATH, data=payload, headers=headers).text
    previous = {**data, "date": "2026-11-12"}
    assert client.post(meta.PATH, data={"brief": json.dumps(previous)}, headers=headers).status_code == 400
    assert db.get_app_setting(meta.SETTING_KEY, ensure_schema_first=False) == {
        **data, "roas": 2.75, "ga4_orders": devices,
    }
    live_roas.assert_called_once_with(date(2026, 11, 12))

    st = Mock()
    meta.render(st, OWNER, TODAY)
    st.html.assert_not_called()
    meta.render(st, get_user.return_value, date(2026, 11, 14))
    assert "Today's recommendations are pending." in st.caption.call_args.args[0]
    meta.render(st, get_user.return_value, TODAY)
    markup = st.html.call_args.args[0]
    assert "<dt>Desktop orders</dt><dd>2</dd><small>GA4</small>" in markup
    assert "<dt>Mobile orders</dt><dd>0</dd><small>GA4</small>" in markup
    assert "<dt>Shopify orders</dt>" not in markup
    assert "<dt>Meta ROAS</dt><dd>2.75×</dd>" in markup
    assert "Review creatives for a refresh" not in markup

    review = {
        **data,
        "summary": "The Final Lap leads recent performance.",
        "recommendations": [
            "Test <creative> from the older campaign.",
            "Check checkout tracking.",
            "Monitor Alan Jones.",
            "Review Warne creative for a refresh.",
            "Check Reece Walsh product availability.",
            "Test a baseball creative tied to the awards.",
            "Compare historical prospecting creative.",
            "Review delivery of the latest catalogue ad.",
        ],
        "insights": {"shopify": ["Compare the product page on desktop and mobile."],
                     "seo": ["Review the collector print landing page."]},
    }
    for unsafe_text in ("Spend rose by $20.", "Payouts rose", "Revenue rose", "Revenue: ＄１２"):
        rejected = {**review, "recommendations": [unsafe_text]}
        assert client.post(meta.PATH, data={"brief": json.dumps(rejected)}, headers=headers).status_code == 400
        rejected = {**review, "insights": {"seo": [unsafe_text]}}
        assert client.post(meta.PATH, data={"brief": json.dumps(rejected)}, headers=headers).status_code == 400
    for rejected in (
        {**review, "recommendations": ["Check checkout tracking.", "Second: Check checkout tracking!"]},
        {**review, "ga4_orders": devices},
    ):
        assert client.post(meta.PATH, data={"brief": json.dumps(rejected)}, headers=headers).status_code == 400
    assert client.post(meta.PATH, data={"brief": json.dumps(review)}, headers=headers).status_code == 200
    meta.render(st, get_user.return_value, TODAY)
    markup = st.html.call_args.args[0]
    assert "The Final Lap leads recent performance." in markup
    assert "Test &lt;creative&gt;" in markup
    assert 'aria-haspopup="dialog">More recommendations</button>' in markup
    assert '<dialog class="sc-meta-full"' in markup
    popup = markup.split('<dialog class="sc-meta-full"', 1)[1].split("</dialog>", 1)[0]
    assert '<ol start="4">' in popup and popup.count("<li>") == 5
    assert "Test a baseball creative tied to the awards." in popup
    assert "Check checkout tracking." not in popup
    assert "Shopify · catalogue and storefront" in markup
    assert "Search Console · SEO opportunities" in markup

    monkeypatch.setattr(meta, "get_app_setting", Mock(return_value=legacy))
    meta.render(st, get_user.return_value, TODAY)
    markup = st.html.call_args.args[0]
    assert all(private not in markup for private in ("122.10", "Payouts", "$50", "$5"))


def test_meta_roas_uses_meta_account_rollup(monkeypatch):
    import home_meta_morning_brief as meta

    config = {"ad_account_id": "act_123", "configured": True}
    reader = Mock()
    reader.get.return_value = {"account_id": "123", "currency": "AUD", "timezone_name": "Australia/Sydney"}
    day = date(2026, 11, 12)
    row = {"account_id": "123", "date_start": day.isoformat(), "date_stop": day.isoformat()}
    reader.pages.return_value = [{**row, "purchase_roas": [{"action_type": "omni_purchase", "value": "4.12"}]}]
    monkeypatch.setattr(meta.meta_ads_client, "get_meta_config", lambda: config)
    monkeypatch.setattr(meta.meta_review_live, "Reader", Mock(return_value=reader))
    assert meta.account_roas(day) == 4.12
    path, params = reader.pages.call_args.args
    assert path == "act_123/insights" and params["level"] == "account"
    assert "spend" not in params["fields"]
    reader.pages.return_value = [row]
    assert meta.account_roas(day) is None
    reader.pages.return_value = [{**row, "account_id": "124"}]
    with pytest.raises(ValueError, match="unexpected account"):
        meta.account_roas(day)



def test_static_schedule_covers_every_sport_without_news_and_ranks_by_market():
    from home_brief_calendar import MARKETS, calendar_rows
    from sports_categories import CANONICAL_SPORT_CATEGORIES

    for market in MARKETS:
        rows = calendar_rows([], market, TODAY)
        assert len(rows) == len(CANONICAL_SPORT_CATEGORIES)
        assert all(event and event.source.startswith("https://") and not news for _, event, news in rows)
        top = {sport for sport, _, _ in rows[:4]}
        assert {"AUS": "Cricket", "USA": "NFL", "UK": "Football"}[market] in top

    upcoming = calendar_rows([], "AUS", date(2027, 2, 25))
    assert next(event for sport, event, _ in upcoming if sport == "V8 Supercars").status(date(2027, 2, 25)) == "Upcoming"


def test_recent_ranked_news_breaks_schedule_ties():
    from home_brief_calendar import calendar_rows

    edition = {"date": TODAY.isoformat(), "recommendations": [
        {"sport": "NFL", "markets": ["USA"]}, {"sport": "NBA", "markets": ["USA"]}
    ]}
    order = [sport for sport, _, _ in calendar_rows([edition], "USA", TODAY)]
    assert order.index("NFL") < order.index("NBA")


def test_calendar_still_renders_when_brief_storage_is_unavailable(monkeypatch):
    monkeypatch.setattr(brief, "get_app_setting", Mock(side_effect=RuntimeError))
    monkeypatch.setattr(brief, "archive_page", Mock(side_effect=RuntimeError))
    st = Mock()
    brief.render(st, OWNER, TODAY)
    assert "Big Bash League" in st.html.call_args.args[0]



def test_full_edition_and_selected_story_design_prompt(monkeypatch):
    from home_morning_brief_actions import _prompt

    story = ("Shopify verified: Active — Reece Walsh.\n"
             "**Recommended Meta ad**\n\nHeadline: Hide this copy.\n"
             "Primary text: Hide this too.\n\n"
             "Timing: Before Sunday's final.\n"
             "Design decision: Feature Reece Walsh.")
    result = _prompt("World Cup finals", story)
    assert "Shopify verified: Active — Reece Walsh." in result
    assert "Design decision: Feature Reece Walsh." in result
    assert "Timing: Before Sunday's final." in result
    assert "Hide this" not in result and "Recommended Meta ad" not in result
    assert result.index("Use web image search") < result.index("Step 1.") < result.index("Step 2.") < result.index("Step 3.")
    assert "photographer or agency credit" not in result
    assert "wall-art reproduction and compositing" not in result
    signature = result.index("Keep the original letterforms and strokes.")
    generation = result.index("Step 5. Use the image generation tool")
    review = result.index("Step 6. Inspect the generated artwork against the original photo.")
    upload = result.index("Step 7. Place the final generated artwork on a copy of designs-canvas.psd.")
    assert signature < generation < review < upload
    assert "99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/" in result[upload:]

    data = json.loads(edition())
    data["full_brief"] = "Other sports and updates\n" + ("Additional source detail. " * 130)
    parsed = brief.parse_edition(json.dumps(data), TODAY)
    monkeypatch.setattr(brief, "get_app_setting", Mock(return_value=parsed))
    monkeypatch.setattr(brief, "archive_page", Mock(return_value=([], None)))
    st = Mock()
    brief.render(st, OWNER, TODAY)
    markup = st.html.call_args.args[0]
    assert "Read the full Morning Brief" in markup and "Other sports and updates" in markup
