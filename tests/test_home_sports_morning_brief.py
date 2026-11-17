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


def legend():
    return {"title": "A hall of fame tribute", "recommendation": "Design idea: A timeless collector portrait.",
            "sport": "Baseball", "markets": ["USA"],
            "links": [{"label": "Club tribute", "url": "https://sports.example.test/tribute"}],
            "product_url": "https://www.sportscaveshop.com/products/tribute-edition"}


def test_legends_has_its_own_rows_and_uses_existing_actions_before_calendar():
    from home_morning_brief_actions import brief_html

    payload = {**json.loads(edition()), "full_brief": "Sports edition", "legends": [legend()]}
    parsed = brief.parse_edition(json.dumps(payload), TODAY)
    html = brief_html(parsed, editions=[parsed], today=TODAY, allow_ads=True)
    assert html.index('<section class="sc-sports-stories"') < html.index('aria-label="Legends Brief"') < html.index('<section class="sc-cal">')
    rows = html.split('aria-label="Legends Brief"', 1)[1].split('</section>', 1)[0]
    assert 'USA 1. A hall of fame tribute' in rows
    assert 'data-prompt=' in rows and 'Create Design' in rows and 'Create Ad' in rows
    assert 'brief_product=tribute-edition' in rows
    assert 'Fixture release' not in rows
    invalid = {**payload, "legends": [legend()] * 7}
    assert brief.parse_edition(json.dumps(invalid), TODAY) == {k: v for k, v in parsed.items() if k != "legends"}


def test_six_legends_group_by_primary_and_keep_secondary_markets_in_order():
    from home_morning_brief_actions import brief_html

    payload = json.loads(edition())
    payload["recommendations"][0].update(markets=["AUS", "USA", "UK"], primary_market="USA")
    payload["legends"] = [dict(legend(), title=f"{market} pick {number}", primary_market=market,
                               markets=[market, *(other for other in ("AUS", "USA", "UK") if other != market)])
                          for market in ("UK", "AUS", "USA") for number in (1, 2)]
    parsed = brief.parse_edition(json.dumps(payload), TODAY)
    assert len(parsed["legends"]) == 6
    html = brief_html(parsed, editions=[parsed], today=TODAY)
    assert '1. Fixture release (USA, AUS, UK)' in html
    labels = [f'{market} {number}. {market} pick {number}' for market in ("AUS", "USA", "UK") for number in (1, 2)]
    assert [html.index(label) for label in labels] == sorted(html.index(label) for label in labels)
    assert '<small class="sc-brief-secondary">Secondary: AUS, USA</small>' in html
    payload["legends"][0].update(primary_market="AUS")
    assert "legends" not in brief.parse_edition(json.dumps(payload), TODAY)


def test_legends_can_be_added_today_and_survives_a_sports_only_repeat(database, monkeypatch):
    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    for module in (brief, db):
        monkeypatch.setattr(module, "connect", jobs.connect)
    addition = json.dumps({"date": str(TODAY), "legends": [legend()]})
    with pytest.raises(ValueError, match="Sports Updates must be published"):
        brief.publish(addition, OWNER)
    prior = brief.publish(edition(), OWNER)
    added = brief.publish(addition, OWNER)
    brief.publish(edition(), OWNER)
    expected = {**prior, "legends": added["legends"]}
    assert db.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False) == expected
    assert brief.archive_page(TODAY)[0] == [expected]


def test_hosted_legends_fills_an_already_published_sports_edition(database, monkeypatch):
    import daily_brief_worker as worker

    jobs, sql = database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)")
    monkeypatch.setattr(worker, "sydney_date", lambda: TODAY)
    for module in (db, brief, worker):
        monkeypatch.setattr(module, "connect", jobs.connect)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, "get_user", lambda _: {**OWNER, "session_version": 1})
    monkeypatch.setattr(os_accounts, "can_access_page", lambda *_: True)
    prior = brief.publish(edition(), OWNER)
    payload = {**json.loads(edition(recommendation="Hosted story")), "full_brief": "Complete edition.",
               "legends": [legend()]}
    worker.enqueue("sports", payload, {"sub": "owner", "version": "1"})
    assert worker.process_one() and worker.status("sports")["status"] == "completed"
    result = db.get_app_setting(brief.SETTING_KEY, ensure_schema_first=False)
    assert result["recommendations"] == prior["recommendations"]
    assert result["legends"][0]["title"] == legend()["title"]


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
    st.fragment.side_effect = lambda **kwargs: lambda fn: fn
    monkeypatch.setattr("morning_design_queue.list_jobs", lambda day=None: [])
    brief.render(st, OWNER, TODAY)
    assert "Today's brief is pending" in st.caption.call_args.args[0]
    markup = st.html.call_args.args[0]
    assert "Create Design" in markup and "Create Ad" in markup
    assert "Sports Cave event: Fixture release" in markup
    assert "Show the photos in this chat first" in markup
    assert "Hero photo selection" in markup
    assert "designs-canvas.psd" in markup
    assert "Step 3. Define the composition" in markup
    assert "MANDATORY CONTINUATION AND RECOVERY" in markup
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
    st.fragment.side_effect = lambda **kwargs: lambda fn: fn
    monkeypatch.setattr("morning_design_queue.list_jobs", lambda day=None: [])
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
    st.fragment.side_effect = lambda **kwargs: lambda fn: fn
    monkeypatch.setattr("morning_design_queue.list_jobs", lambda day=None: [])
    brief.render(st, OWNER, TODAY)
    assert "Big Bash League" in st.html.call_args.args[0]



def test_create_design_uses_recent_performance_as_context_for_a_timeless_title():
    from home_morning_brief_actions import _prompt

    result = _prompt("Tom Banton — The Adelaide Century",
                     "Decision: Monitor the decider before starting another cricket print.")
    assert 'Execution decision: Create “Tom Banton — The Adelaide Century” now.' not in result
    assert 'does not override this instruction to create the artwork now' in result
    research = result.index('use the authorised Shopify connection in read-only mode')
    title = result.index('**STORY-LED COLLECTOR TITLES**')
    assert research < title < result.index('Use web image search')
    assert 'closest comparable sport or collector collection' in result
    assert 'Treat unranked products as style references only' in result
    assert 'Use the athlete’s name alone only when that is a deliberate creative choice' in result
    assert 'completed landmark series such as the Ashes' in result
    assert 'Use a single concise verified statistic or accolade only if it tells that lasting story' in result


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
    assert "If a required operation is unavailable or fails" not in result
    assert "10/10" not in result
    assert "three distinct credible sources" not in result
    assert "SIGNATURE-FREE COLLECTOR COMPOSITION" in result
    signature = result.index("SIGNATURE-FREE COLLECTOR COMPOSITION")
    first_generation = result.index("Step 5. Use the image generation tool")
    first_review = result.index("Step 6. Inspect the generated artwork")
    first_save = result.index("Step 7. Place the first complete artwork")
    second_pass = result.index("**STEP 8")
    pending_trial = result.index("If the trial save is pending, use the retained first artwork", second_pass)
    second_generation = result.index("Make a **new image-generation call**")
    final_save = result.index("**8E. Save and verify the final PSD**")
    cleanup = result.index("Only after successful final verification")
    display = result.index("After Dropbox confirms trial deletion, display the final artwork")
    assert signature < first_generation < first_review < first_save < second_pass
    assert pending_trial < second_generation < final_save < cleanup < display
    assert "If master PSD retrieval or a Dropbox save fails after reasonable recovery attempts" in result
    assert "both full artwork generations, photographic corrections, final inspection" in result
    assert "only after exhausting authorised recovery methods and finishing all independent work" in result
    assert "Continue to the final display and status in Step 8F." in result[second_generation:final_save]
    assert "Never invent or replace the master badge or editable edition-number layer." in result
    assert "Dropbox must have confirmed the trial save" not in result
    assert "After Dropbox confirms the trial save and before the second generation" not in result
    assert "skip it without prompting and use an authorised alternative" in result
    assert "at most two additional image-generation attempts total across both passes" in result
    assert "up to the three strongest accessible references per featured person" not in result
    assert "search beyond the first three sources" not in result
    assert "After each pass, use source-photo compositing" in result
    assert "attempt the second pass independently" in result[second_pass:second_generation]
    assert "If any PSD save, verification or cleanup step is pending, display the inspected final artwork" in result
    assert "as a review draft" in result[first_save:second_pass]
    assert "99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/" in result[first_save:second_pass]
    assert "hidden REVIEW NOTES layer" in result[first_save:second_pass]
    assert "Continue immediately to Step 8 in either case." in result[first_save:second_pass]
    assert "[Product Title] - TRIAL.psd" in result[first_save:second_pass]
    assert "[Product Title] - v2 - TRIAL.psd" in result[first_save:second_pass]
    assert "[Product Title] - v2.psd" in result[first_save:second_pass]
    assert "ORIGINAL EDITABLE ARTWORK" in result[second_generation:final_save]
    assert "explicitly lock those strengths before generating again" in result[second_pass:second_generation]
    assert "A new layout is optional." in result[second_generation:final_save]
    assert "If the first artwork still wins, use it." in result[second_generation:final_save]
    assert "Place the strongest inspected artwork in **FINAL POLISHED ARTWORK**" in result[second_generation:final_save]
    assert "Generate a visibly different" not in result
    assert "Do not search for, source, generate, trace, reproduce or include athlete signatures" in result[signature:first_generation]
    assert "Use the original official badge asset and preserve its design and edition number" in result[signature:first_generation]
    assert "at 100% magnification to this first generation" in result[first_review:first_save]
    assert "Restore visible discrepancies with original photograph pixels and a precise mask" in result[second_generation:final_save]
    assert "smallest coherent source region" in result[second_generation:final_save]
    assert "Use contact shadows only at actual points of contact." in result[second_pass:second_generation]
    assert "subject visibly separated from the ground" in result[second_generation:final_save]
    assert "Complete the digital integration review before selecting the final artwork." in result[second_generation:final_save]
    assert "REVIEW DRAFT, keep the trial" not in result
    assert "continue directly to the final PSD" in result[second_generation:final_save]
    assert "After completing your own inspection and corrections, save the final PSD" in result[final_save:cleanup]
    assert "retain the trial and continue" in result[final_save:cleanup]
    assert "Photoshop is optional" in result[final_save:cleanup]
    assert "parser plus a rendered preview" in result[final_save:cleanup]
    assert "trial cleanup may proceed" in result[final_save:cleanup]
    assert "report the specific unverified property" in result[final_save:cleanup]
    assert "Photoshop live-number check pending" not in result
    assert "recoverable delete" in result[cleanup:display]
    assert "report it as pending" in result[cleanup:display]
    metadata_start = result.index("**SMART UPLOAD HANDOFF METADATA**", final_save)
    metadata_end = result.index("**8F.", metadata_start)
    metadata = result[metadata_start:metadata_end]
    assert "Never write a handoff for the trial or overwrite an existing file." in metadata
    assert "99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/JSON/" in metadata
    assert "intended_collections" in metadata and "dropbox_revision" in metadata
    assert "overwrite" not in (result[:metadata_start] + result[metadata_end:]).lower()

    data = json.loads(edition())
    data["full_brief"] = "Other sports and updates\n" + ("Additional source detail. " * 130)
    parsed = brief.parse_edition(json.dumps(data), TODAY)
    monkeypatch.setattr(brief, "get_app_setting", Mock(return_value=parsed))
    monkeypatch.setattr(brief, "archive_page", Mock(return_value=([], None)))
    st = Mock()
    st.fragment.side_effect = lambda **kwargs: lambda fn: fn
    monkeypatch.setattr("morning_design_queue.list_jobs", lambda day=None: [])
    brief.render(st, OWNER, TODAY)
    markup = st.html.call_args.args[0]
    assert "Read the full Morning Brief" in markup and "Other sports and updates" in markup
