"""Synthetic-only CRM reconciliation and paid reporting contracts."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from types import SimpleNamespace
import json
import pytest
import home_crm_reporting as crm
from tests.test_auto_editions_jobs import database

START=date(2026,11,20)
END=START


def ga(id,source,device="mobile",count="1"):
    return {"dimensions":{"transactionId":str(id),"sessionSourceMedium":source,"deviceCategory":device},
            "metrics":{"ecommercePurchases":count}}


@pytest.mark.parametrize("source,expected",[
 ("google / cpc","Google paid"),("facebook / paid_social","Facebook paid"),
 ("instagram.com / paid_social","Facebook paid"),("google / organic","Organic"),
 ("instagram / organic_social","Organic"),("facebook.com / referral","Unresolved"),
 ("google / product_sync","Unresolved"),("google / sag_organic","Unresolved"),
 ("(not set) / (not set)","Unresolved"),("(direct) / (none)","Other"),("newsletter / email","Other")])
def test_channel_classification_requires_explicit_paid_evidence(source,expected):
    assert crm.channel(source)==expected


def test_exact_unique_order_ledger_reconciles_conflicts_missing_and_tablets():
    rows=[ga(1,"facebook / paid_social"),ga(1,"facebook / paid_social",count="2"),
          ga(2,"google / cpc","desktop"),ga(3,"google / organic","tablet"),
          ga(4,"google / cpc"),ga(4,"google / organic"),ga(999,"google / cpc")]
    value=crm.ledger(set("12345"),rows)
    by={r["channel"]:r for r in value["rows"]}
    assert value["orders"]==5 and value["matched"]==4 and value["unmatched"]==1
    assert sum(r["total"] for r in value["rows"])==5
    assert by["Facebook paid"]["mobile"]==1
    assert by["Google paid"]["desktop"]==1
    assert by["Organic"]["other"]==1
    assert by["Unresolved"]["total"]==2
    assert value["conflicted"]==1
    assert crm.order_id("#SC123") is None
    assert crm.order_id("gid://shopify/Order/123")=="123"


def test_shopify_enumerates_all_pages_excludes_tests_cancelled(monkeypatch):
    import shopify_sync as shop
    monkeypatch.setattr(shop,"get_config",lambda:{"store_domain":"sportscave-nb.myshopify.com"})
    def node(id,test=False,cancel=None):
        return {"id":"gid://shopify/Order/"+str(id),"createdAt":"2026-11-20T04:00:00Z","test":test,"cancelledAt":cancel}
    fetch=Mock(side_effect=[
      ({"orders":{"nodes":[node(1),node(2,True)],"pageInfo":{"hasNextPage":True,"endCursor":"next"}}},None),
      ({"orders":{"nodes":[node(3,cancel="cancelled"),node(4)],"pageInfo":{"hasNextPage":False,"endCursor":None}}},None)])
    monkeypatch.setattr(shop,"graphql_request",fetch)
    value=crm.orders(START,END)
    assert value["ids"]=={"1","4"}
    assert fetch.call_count==2
    assert "status:any" in fetch.call_args.kwargs["variables"]["query"] if "variables" in fetch.call_args.kwargs else "status:any" in fetch.call_args.args[1]["query"]


def test_shopify_old_period_without_all_orders_permission_withheld(monkeypatch):
    import shopify_sync as shop
    monkeypatch.setattr(shop,"get_config",lambda:{"store_domain":"sportscave-nb.myshopify.com"})
    monkeypatch.setattr(shop,"graphql_request",lambda *a,**k:({"currentAppInstallation":{"accessScopes":[{"handle":"read_orders"}]}},None))
    with pytest.raises(ValueError,match="read_all_orders"):
        crm.orders(date(2026,7,1),date(2026,7,2))


def test_meta_uses_value_over_spend_and_reported_roas_fallback(monkeypatch):
    import meta_ads_client as client
    import meta_review_live as live
    monkeypatch.setattr(client,"get_meta_config",lambda:{"ad_account_id":"act_1"})
    reader=Mock()
    reader.get.return_value={"account_id":"1","currency":"AUD","timezone_name":"Australia/Sydney"}
    reader.pages.return_value=[{"account_id":"1","date_start":str(START),"date_stop":str(END),
        "spend":"10","action_values":[{"action_type":"purchase","value":"80"},{"action_type":"omni_purchase","value":"80"}]}]
    monkeypatch.setattr(live,"Reader",lambda *a,**k:reader)
    assert crm.meta(START,END)["roas"]==8
    row=reader.pages.return_value[0]
    row.pop("action_values")
    row["website_purchase_roas"]=[{"action_type":"offsite_conversion.fb_pixel_purchase","value":"7"}]
    assert crm.meta(START,END)["roas"]==7
    row.pop("website_purchase_roas")
    assert crm.meta(START,END)["roas"] is None
    row["spend"]="0"
    assert crm.meta(START,END)["status"]=="no_spend"


def test_google_multichunk_roas_is_ratio_of_totals(monkeypatch):
    import google_ads_api_reporting as ads
    reports=Mock(side_effect=[
        {"status":"connected","currency":"AUD","timezone":"Australia/Sydney",
         "totals":{"spend":10,"value":100,"purchases":1.25},"fetched_at":"one"},
        {"status":"connected","currency":"AUD","timezone":"Australia/Sydney",
         "totals":{"spend":90,"value":90,"purchases":0.75},"fetched_at":"two"}])
    monkeypatch.setattr(ads,"report",reports)
    result=crm.google(START-timedelta(days=40),END)
    assert result["roas"]==1.9
    assert result["purchases"]==2 and result["spend"]==100 and result["value"]==190
    assert reports.call_count==2


def test_build_exposes_aggregates_only_and_source_failures_independent():
    readers={"shopify":lambda *a:{"status":"verified","ids":{"1","2"},"fetched_at":"synthetic"},
        "ga4":lambda *a:{"status":"verified","rows":[ga(1,"google / cpc")],"fetched_at":"synthetic"},
        "facebook":lambda *a:{"status":"verified","roas":5},
        "google":lambda *a: (_ for _ in ()).throw(TimeoutError())}
    value=crm.build(START,END,readers=readers)
    assert value["roas"]=={"facebook":5,"google":None}
    assert value["ledger"]["orders"]==2 and value["ledger"]["unmatched"]==1
    raw=json.dumps(value)
    assert "transactionId" not in raw and '"ids"' not in raw
    assert value["coverage"]["google"]["status"]=="unavailable"


def test_snapshot_storage_roundtrip_aggregate_only(database,monkeypatch):
    import supabase_backend as db
    jobs,sql=database
    sql.execute("CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz)")
    monkeypatch.setattr(db,"connect",jobs.connect)
    value={"version":crm.VERSION,"start":str(START),"end":str(END),"ledger":{"orders":2}}
    monkeypatch.setattr(crm,"build",lambda *a:value)
    assert crm.refresh(START,END)==value
    sql.execute("SELECT key,value FROM app_settings")
    rows=sql.fetchall()
    assert rows==[{"key":crm.key(START,END),"value":value}]


def test_private_result_endpoint_denies_before_cache_read(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import home_morning_brief_publish as api
    monkeypatch.setattr(api,"_request_user",lambda *a,**k:None)
    read=Mock(side_effect=AssertionError("Must not read private results"))
    monkeypatch.setattr(api.meta,"period_results",read)
    client=TestClient(Starlette(routes=[Route("/results",api.results)]))
    assert client.get("/results?period=yesterday").status_code==403
    read.assert_not_called()


@pytest.mark.parametrize("denied", [None,"dashboard","reporting","ads_google"])
def test_installed_crm_tool_rechecks_home_and_google_access(monkeypatch,denied):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import chatgpt_crm_mcp as mcp
    secret=b"synthetic-home-reporting-key"
    monkeypatch.setattr(mcp,"_key",lambda:secret)
    monkeypatch.setattr(mcp,"_active_owner",lambda claims,page:page!=denied)
    monkeypatch.setattr(mcp,"meta_daily",lambda *a:{"source":"synthetic"})
    reader=Mock(return_value={"state":"ready","data":{"ledger":{"orders":2}}})
    monkeypatch.setattr(crm,"request",reader)
    client=TestClient(Starlette(routes=[Route(mcp.MCP_PATH,mcp.mcp,methods=["POST"])]))
    bearer=mcp._seal(secret,"access",{"sub":"owner","version":"1","scope":mcp.META_SCOPE,
        "iss":mcp.ISSUER,"aud":mcp.RESOURCE})
    result=client.post(mcp.MCP_PATH,headers={"Authorization":"Bearer "+bearer},json={
        "jsonrpc":"2.0","id":1,"method":"tools/call",
        "params":{"name":"get_meta_daily_summary","arguments":{"date":str(START)}}}).json()["result"]
    assert not result.get("isError")
    assert ("home_crm" in result["structuredContent"]) is (denied is None)
    assert reader.call_count==int(denied is None)


def test_ga4_withholds_wrong_property_or_timezone(monkeypatch):
    report=Mock()
    report.connection.return_value={"ga4_property_id":"other"}
    monkeypatch.setattr(crm,"GoogleReports",lambda:report)
    with pytest.raises(ValueError,match="property"):
        crm.ga4(START,END)
    report.for_request.assert_not_called()
    report.connection.return_value={"ga4_property_id":"355333982"}
    report.for_request.return_value.ga4.return_value={"property_timezone":"UTC","quality":{"status":"GA4 verified"}}
    with pytest.raises(ValueError,match="timezone"):
        crm.ga4(START,END)


def test_shopify_repeated_cursor_rejected_not_partial_totals(monkeypatch):
    import shopify_sync as shop
    monkeypatch.setattr(shop,"get_config",lambda:{"store_domain":"sportscave-nb.myshopify.com"})
    monkeypatch.setattr(shop,"graphql_request",lambda *a,**k:({"orders":{"nodes":[],
        "pageInfo":{"hasNextPage":True,"endCursor":"repeat"}}},None))
    with pytest.raises(ValueError,match="pagination"):
        crm.orders(START,END)


def test_snapshot_request_nonblocking_and_manual_refresh_throttled(monkeypatch):
    from threading import Event
    from time import monotonic
    started,release=Event(),Event()
    snapshots=crm.Snapshots(workers=1,ttl=100)
    monkeypatch.setattr(crm,"SNAPSHOTS",snapshots)
    monkeypatch.setattr(crm,"saved",lambda *a:None)
    monkeypatch.setattr(crm,"FORCED",{})
    def slow(*args):
        started.set();release.wait(3)
        return {"synthetic":True}
    monkeypatch.setattr(crm,"refresh",slow)
    try:
        before=monotonic()
        result=crm.request(START,END)
        assert monotonic()-before<.3 and result["data"] is None
        assert started.wait(1)
        crm.request(START,END,force=True)
        row=snapshots.rows[crm.key(START,END)]
        crm.request(START,END,force=True)
        assert snapshots.rows[crm.key(START,END)] is row
    finally:
        release.set();snapshots.close()


def test_primary_reconciler_starts_once_and_retries_after_failure(monkeypatch):
    thread=Mock()
    thread.is_alive.return_value=True
    factory=Mock(return_value=thread)
    monkeypatch.setattr(crm,"_APP_THREAD",None)
    monkeypatch.setattr(crm,"Thread",factory)
    assert crm.start_app_reconciler() and crm.start_app_reconciler()
    factory.assert_called_once()
    thread.start.assert_called_once()
    stop=Mock()
    stop.is_set.side_effect=[False,False,True]
    tick=Mock(side_effect=[RuntimeError("synthetic"),None])
    monkeypatch.setattr(crm,"tick",tick)
    crm._loop(stop)
    assert tick.call_count==2 and stop.wait.call_count==2


def test_native_period_and_refresh_controls_use_exact_windows(monkeypatch):
    from streamlit.testing.v1 import AppTest
    calls=[]
    def result(start,end,**kwargs):
        calls.append((start,end,kwargs))
        return {"state":"loading","data":None}
    monkeypatch.setattr(crm,"request",result)
    test=AppTest.from_string("import streamlit as st\nimport home_crm_ui\nfrom datetime import date\nhome_crm_ui.render(st,date(2026,11,21))").run(timeout=10)
    assert not test.exception
    assert calls[-1][:2]==(date(2026,11,20),date(2026,11,20))
    test.selectbox[0].select("week").run(timeout=10)
    assert calls[-1][:2]==(date(2026,11,14),date(2026,11,20))
    test.button[0].click().run(timeout=10)
    assert calls[-1][2]["force"] is True
    assert not test.exception


def test_initial_html_is_useful_without_javascript_and_escapes_payload():
    import home_crm_ui as ui
    from html.parser import HTMLParser
    class Markup(HTMLParser):
        def __init__(self):
            super().__init__(); self.tags=[]
        def handle_starttag(self,tag,attrs):
            self.tags.append((tag,dict(attrs)))
    value={"state":"ready","data":{"start":"2026-11-20","end":"2026-11-20","checked_at":"2026-11-21T03:00:00Z",
        "ledger":{"rows":[{"channel":"Facebook paid","mobile":2,"desktop":0,"other":0,"total":2}],"orders":2,"matched":2,"unmatched":0},
        "roas":{"facebook":6.25,"google":None},"basis":'" onmouseover="bad() </section><script>bad()</script>'}}
    markup=ui.html(date(2026,11,21),value)
    parsed=Markup(); parsed.feed(markup)
    assert 'data-roas="facebook">6.25×</b>' in markup
    assert 'data-roas="google">—</b>' in markup
    assert 'data-device="mobile">2</td>' in markup
    assert '2 exact GA4 matches' in markup
    assert not any(tag=="script" or "onmouseover" in attrs for tag,attrs in parsed.tags)


def test_build_keeps_journey_records_transient_and_discloses_source_model():
    readers={"shopify":lambda *a:{"status":"verified","ids":{"1"},"journeys":{"1":{"channel":"Facebook paid","reason":"explicit_paid_tags"}}},
        "ga4":lambda *a:{"status":"verified","rows":[ga(1,"facebook / referral")]},
        "facebook":lambda *a:{"status":"verified","roas":5},"google":lambda *a:{"status":"verified","roas":3}}
    result=crm.build(START,END,readers=readers)
    assert result["version"]==4
    assert result["ledger"]["rows"][0]["mobile"]==1
    assert result["ledger"]["source_reconciliation"]==[{"ga4_channel":"Unresolved","shopify_channel":"Facebook paid","orders":1}]
    raw=json.dumps(result)
    assert '"ids"' not in raw and '"journeys"' not in raw and '"transactionId"' not in raw


def test_parallel_source_models_deduplicate_same_cohort_without_overwriting_visits():
    observations=[ga(1,"google / cpc"),ga(1,"google / cpc",count="2"),
        ga(2,"google / cpc"),ga(3,"google / cpc"),ga(3,"google / organic"),
        ga(999,"google / cpc")]
    journeys={"1":{"channel":"Organic","reason":"explicit_organic_evidence"},
        "2":{"channel":"Unresolved","reason":"google_listing_paid_status_unknown"},
        "5":{"channel":"Google paid","reason":"explicit_paid_tags"}}
    result=crm.ledger(set("12345"),observations,journeys)
    counts={r["channel"]:r["total"] for r in result["rows"]}
    assert counts=={"Facebook paid":0,"Google paid":2,"Organic":1,"Other":0,"Unresolved":2}
    assert result["ga4_channel_orders"]=={"Facebook paid":0,"Google paid":2,"Organic":0,"Other":0,"Unresolved":3}
    assert result["paid_organic_differences"]==1
    assert result["source_reasons"]["google_listing_ga4_paid"]==1
    assert result["shopify_channel_orders"]["Google paid"] == 1
    assert sum(result["ga4_channel_orders"].values())==result["orders"]==5


def test_visible_comparison_distinguishes_conversion_credit_from_order_counts():
    import home_crm_ui as ui
    report=crm.ledger({"1","2"},[ga(1,"google / cpc"),ga(2,"google / cpc")],{
        "1":{"channel":"Organic","reason":"explicit_organic_evidence"},
        "2":{"channel":"Unresolved","reason":"google_listing_paid_status_unknown"}})
    data={"start":str(START),"end":str(END),"checked_at":"2026-11-21T04:00:00Z",
        "ledger":report,"coverage":{"ga4":{"status":"verified"},"google":{"status":"verified","purchases":2.25}},
        "roas":{"google":3.5}}
    markup=ui.html(date(2026,11,21),{"state":"ready","data":data})
    before_details=markup.split('<details')[0]
    assert 'reconciled 1 · Shopify last visit 0 · GA4 purchase session 2' in before_details
    assert 'Google Ads: 2.25 attributed purchases (ad interaction dates)' in before_details
    assert '1 order has paid/organic model differences' in before_details
    assert 'Google listing orders resolved by exact Analytics transaction matches: 1 paid · 0 organic' in before_details
    assert 'Organic</th>' in before_details
    data["coverage"]["google"]={"status":"unavailable"}
    assert 'Google Ads: — attributed purchases' in ui.html(date(2026,11,21),{"state":"ready","data":data})
    data["coverage"]["ga4"]={"status":"unavailable"}
    assert 'GA4 purchase session —' in ui.html(date(2026,11,21),{"state":"ready","data":data})


def test_only_consistent_google_transaction_evidence_resolves_feed_ambiguity():
    journeys={str(i):{"channel":"Unresolved","reason":"google_listing_paid_status_unknown"} for i in range(1,8)}
    journeys["8"]={"channel":"Organic","reason":"explicit_organic_evidence"}
    result=crm.ledger(set(journeys),[
        ga(1,"google / cpc"),ga(1,"google / cpc",device="desktop"),
        ga(2,"google / organic"),ga(3,"google / cpc"),ga(3,"google / organic"),
        ga(4,"facebook / cpc"),ga(5,"google / referral"),ga(6,"google / cpc"),ga(6,""),
        ga(8,"google / cpc")],journeys)
    assert result["google_listing_resolutions"] == {"paid":1,"organic":1}
    assert result["source_reasons"]["google_listing_paid_status_unknown"] == 5
    assert result["shopify_channel_orders"]["Unresolved"] == 7
    assert result["paid_organic_differences"] == 1
    assert sum(row["total"] for row in result["rows"]) == 8
    assert next(row for row in result["rows"] if row["channel"]=="Google paid")["other"] == 1
