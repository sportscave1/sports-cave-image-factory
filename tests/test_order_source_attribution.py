"""Synthetic evidence only: paid/free separation and future Meta link hygiene."""
from datetime import date
from urllib.parse import parse_qs,urlsplit
import pytest
from order_source_attribution import last_visit
from home_crm_reporting import ledger


def journey(source="facebook",medium="paid_social",campaign="fixture",url="https://example.test/products/fixture",tactic=None):
    return {"ready":True,"lastVisit":{"source":"Google","sourceType":tactic,"landingPage":url,
        "utmParameters":{"source":source,"medium":medium,"campaign":campaign}}}


@pytest.mark.parametrize("source,medium,campaign,expected",[
    ("facebook","paid_social","fixture","Facebook paid"),
    ("ig","paid_social","fixture","Facebook paid"),
    ("google","cpc","fixture","Google paid"),
    ("google","organic","","Organic"),
    ("instagram","organic_social","fixture","Organic"),
    ("google","product_sync","sag_organic","Organic"),
    ("google","product_sync","","Unresolved"),
    ("facebook","referral","","Unresolved"),
    ("newsletter","email","fixture","Other"),
    ("bing","cpc","fixture","Other")])
def test_explicit_source_evidence(source,medium,campaign,expected):
    assert last_visit(journey(source,medium,campaign))["channel"]==expected


def test_google_click_overrides_free_feed_tags_but_meta_conflict_stays_unknown():
    url="https://example.test/?gclid=synthetic"
    assert last_visit(journey("google","product_sync","sag_organic",url))["channel"]=="Google paid"
    assert last_visit(journey(url=url))["channel"]=="Unresolved"
    assert last_visit(journey("google","organic",tactic="AD"))["channel"]=="Unresolved"
    assert last_visit(journey(url="https://example.test/?utm_source=google&utm_medium=cpc"))["reason"]=="conflicting_tags"
    assert last_visit(journey(url="https://example.test/?utm_source=facebook&utm_source=google"))["reason"]=="conflicting_tags"


def test_referrer_and_fbclid_do_not_prove_paid_or_organic():
    assert last_visit(journey("facebook","","",url="https://example.test/?fbclid=synthetic"))["channel"]=="Unresolved"
    assert last_visit(journey("google","",""))["channel"]=="Unresolved"
    assert last_visit({"ready":False,"lastVisit":journey()["lastVisit"]})["channel"]=="Unresolved"
    assert last_visit({"ready":True,"firstVisit":journey()["lastVisit"]})["channel"]=="Unresolved"


def test_last_visit_is_one_model_not_union_with_first_or_ga4():
    data=journey("google","product_sync","sag_organic")
    data["firstVisit"]=journey()["lastVisit"]
    evidence=last_visit(data)
    assert evidence["channel"]=="Organic"
    rows=[{"dimensions":{"transactionId":"1","sessionSourceMedium":"facebook / referral","deviceCategory":"mobile"},
           "metrics":{"ecommercePurchases":"1"}}]
    report=ledger({"1"},rows,{"1":evidence})
    assert report["rows"][2]["mobile"]==1
    assert report["source_reconciliation"]==[{"ga4_channel":"Unresolved","shopify_channel":"Organic","orders":1}]
    assert report["orders"]==1 and report["matched"]==1
    missing=ledger({"1"},rows,{})
    assert missing["rows"][-1]["total"]==1


def test_meta_new_destination_drops_stale_acquisition_keeps_variant_and_fragment():
    from meta_posting_service import validate_destination_url
    from ads_meta_contract import META_AD_URL_PARAMETERS
    url="https://example.test/products/fixture?variant=123&utm_source=google&utm_medium=product_sync&utm_campaign=sag_organic&gclid=old&FBCLID=old&ref=collection#details"
    clean=validate_destination_url(url)
    assert parse_qs(urlsplit(clean).query)=={"variant":["123"],"ref":["collection"]}
    assert urlsplit(clean).fragment=="details"
    tags=parse_qs(META_AD_URL_PARAMETERS)
    assert tags["utm_source"]==["facebook"] and tags["utm_medium"]==["paid_social"]
    assert tags["utm_id"]==["{{campaign.id}}"] and tags["ad_id"]==["{{ad.id}}"]


def test_organic_social_never_inherits_paid_click_or_campaign_identifiers():
    from social_media_creator import build_tracked_url
    url=build_tracked_url("https://example.test/products/fixture?variant=123&gclid=old&fbclid=old&utm_id=old&UTM_Source=google&utm_medium=cpc&ad_id=old",platform="Facebook",series="fixture",product_handle="fixture",market="AUS",content_format="post",hook="fixture",value=date(2026,11,21))
    query=parse_qs(urlsplit(url).query)
    assert query["utm_source"]==["facebook"] and query["utm_medium"]==["organic_social"]
    assert query["variant"]==["123"]
    assert not ({"gclid","fbclid","utm_id","ad_id","UTM_Source"}&query.keys())
