"""Observed Shopify last-visit attribution; never infer paid traffic from a referrer."""
from urllib.parse import urlsplit, parse_qsl

META = {"facebook", "instagram", "meta", "fb", "ig"}
PAID = {"cpc", "ppc", "paid", "paid_social", "paid-social", "paidsocial", "paid_search", "paidsearch", "paid_shopping"}
ORGANIC = {"organic", "organic_social", "organic-social"}


def platform(value):
    value = str(value or "").strip().lower()
    if value in META: return "facebook"
    if value == "google": return "google"
    try:
        host = urlsplit(value if "://" in value else "https://"+value).hostname or ""
    except ValueError:
        return ""
    if host in ("facebook.com", "www.facebook.com", "m.facebook.com", "l.facebook.com", "lm.facebook.com", "instagram.com", "www.instagram.com", "l.instagram.com"):
        return "facebook"
    if host in ("google.com", "www.google.com", "google.com.au", "www.google.com.au"):
        return "google"
    return ""


def last_visit(journey):
    if not journey or journey.get("ready") is not True:
        return {"channel":"Unresolved", "reason":"journey_pending_or_missing"}
    visit = journey.get("lastVisit")
    if not visit:
        return {"channel":"Unresolved", "reason":"last_visit_missing"}
    utm = {k:str(v or "").strip().lower() for k,v in (visit.get("utmParameters") or {}).items()}
    try:
        pairs = parse_qsl(urlsplit(visit.get("landingPage") or "").query, keep_blank_values=True)
    except ValueError:
        return {"channel":"Unresolved", "reason":"invalid_landing_url"}
    query = {}
    for k,v in pairs:
        query.setdefault(k.lower(),set()).add(v.strip().lower())
    for name in ("source","medium","campaign"):
        values = query.get("utm_"+name, set())
        if len(values)>1 or (utm.get(name) and values and values!={utm[name]}):
            return {"channel":"Unresolved", "reason":"conflicting_tags"}
        if not utm.get(name) and values:
            utm[name] = next(iter(values))
    source, medium, campaign = (utm.get(k,"") for k in ("source","medium","campaign"))
    origin = platform(source) if source else platform(visit.get("source"))
    tactic = visit.get("sourceType")
    google_click = any(any(values) for key,values in query.items() if key in ("gclid","gbraid","wbraid"))
    if google_click and origin == "facebook":
        return {"channel":"Unresolved", "reason":"conflicting_paid_platforms"}
    if google_click and origin == "google":
        return {"channel":"Google paid", "reason":"google_click_tag"}
    if medium in PAID:
        if origin in ("facebook","google"):
            return {"channel":"Facebook paid" if origin=="facebook" else "Google paid", "reason":"explicit_paid_tags"}
        return {"channel":"Other", "reason":"other_paid_source"}
    if tactic in ("AD","RETARGETING") and origin in ("facebook","google"):
        if medium in ORGANIC:
            return {"channel":"Unresolved", "reason":"conflicting_paid_organic_evidence"}
        return {"channel":"Facebook paid" if origin=="facebook" else "Google paid", "reason":"shopify_ad_tactic"}
    if medium in ORGANIC or tactic == "SEO":
        return {"channel":"Organic", "reason":"explicit_organic_evidence"}
    if source=="google" and medium=="product_sync" and campaign=="sag_organic":
        return {"channel":"Organic", "reason":"shopify_google_free_listing_tags"}
    if medium in ("email","sms","affiliate"):
        return {"channel":"Other", "reason":"other_tagged_channel"}
    if medium in ("product_sync","sag_organic") or origin in ("facebook","google"):
        return {"channel":"Unresolved", "reason":"platform_without_paid_organic_evidence"}
    if source in ("direct","(direct)") or str(visit.get("source") or "").lower()=="direct":
        return {"channel":"Other", "reason":"recorded_direct_visit"}
    return {"channel":"Unresolved", "reason":"source_evidence_missing"}
