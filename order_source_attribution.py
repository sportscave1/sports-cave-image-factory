"""Observed Shopify last-visit attribution; never infer paid traffic from a referrer."""
from urllib.parse import urlsplit, parse_qsl
from google_tracking_contract import paid_term

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
    term_values = query.get("utm_term", set())
    marker = utm.get("term") or (next(iter(term_values)) if len(term_values) == 1 else "")
    if paid_term(marker):
        origin = platform(utm.get("source") or visit.get("source"))
        mediums = query.get("utm_medium", set()) | {utm.get("medium", "")}
        # A paid-only term survives Shopify's supported UTM fields even when
        # the shared Merchant link also contributes product_sync defaults.
        # Explicit organic/other-channel or conflicting marker evidence wins.
        if (origin != "google" or visit.get("sourceType") == "SEO"
                or not mediums <= (PAID | {"", "product_sync"})
                or query.get("utm_source", {"google"}) != {"google"}
                or (term_values and term_values != {marker})):
            return {"channel":"Unresolved", "reason":"conflicting_paid_marker"}
        return {"channel":"Google paid", "reason":"google_paid_utm_marker"}
    for name in ("source","medium","campaign","term"):
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
        # Merchant feed URLs can also be used by Shopping ads. Absence of a
        # click ID in Shopify's recorded URL does not establish an unpaid click.
        return {"channel":"Unresolved", "reason":"google_listing_paid_status_unknown"}
    if medium in ("email","sms","affiliate"):
        return {"channel":"Other", "reason":"other_tagged_channel"}
    if medium in ("product_sync","sag_organic") or origin in ("facebook","google"):
        return {"channel":"Unresolved", "reason":"platform_without_paid_organic_evidence"}
    if source in ("direct","(direct)") or str(visit.get("source") or "").lower()=="direct":
        return {"channel":"Other", "reason":"recorded_direct_visit"}
    return {"channel":"Unresolved", "reason":"source_evidence_missing"}


def observed_referral(visit):
    """Allowlisted referral identity only; does not establish paid/organic."""
    def label(value):
        value = str(value or "").strip().lower()
        origin = platform(value)
        if origin == "google":
            return "Google"
        if origin == "facebook":
            return "Instagram" if value in ("instagram", "ig") or (urlsplit(value if "://" in value else "https://" + value).hostname or "") in ("instagram.com", "www.instagram.com", "l.instagram.com") else "Facebook"
        try:
            host = urlsplit(value if "://" in value else "https://" + value).hostname
        except ValueError:
            return None
        return "Brave Search" if host == "search.brave.com" else None
    source = label(visit.get("source"))
    referrer = label(visit.get("referrerUrl"))
    if source and referrer and source != referrer:
        return None
    return source or referrer


def order_source(order):
    """Keep sales-channel evidence separate from storefront acquisition."""
    source = str(order.get("sourceName") or "").strip().lower()
    app_id = str((order.get("app") or {}).get("id") or "")
    if source == "etsy":
        if app_id == "gid://shopify/App/1777077":
            return {"channel":"Etsy", "reason":"etsy_sales_channel"}
        return {"channel":"Unresolved", "reason":"unverified_etsy_sales_channel"}
    journey = order.get("customerJourneySummary")
    evidence = last_visit(journey)
    if evidence["reason"] in ("platform_without_paid_organic_evidence", "source_evidence_missing"):
        visit = (journey or {}).get("lastVisit") or {}
        referral = observed_referral(visit)
        if referral:
            evidence["observed_referral"] = referral
    return evidence
