"""Google advertising workspace; reporting and planning only."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json

import streamlit as st
import google_ads_reviews as reviews
import google_ads_reporting as reporting
import google_ads_api_reporting as ads_api
import os_accounts
from sports_sales_calendar import sydney_date

REVIEW_PROMPT = """Review Sports Cave's preceding Friday–Thursday in Australia/Sydney.
Keep Google at A$20/day with Australia and USA in the existing campaign PM021126.
Check Google Ads spend, purchases, value, search terms, country and product performance.
Read complete Shopify non-test order journeys and GA4 purchase transaction IDs for the same dates.
Join exact order IDs. Assign each Shopify order once under a stated latest non-direct journey rule.
Keep Google paid, Meta paid, organic search/social, email, direct and unknown separate.
Leave product_sync/sag_organic and untagged Meta unresolved unless paid evidence exists.
Show Google/Meta platform-attributed results separately; never sum their purchases as unique orders.
Preserve currencies, timezones, refunds, date basis, attribution windows and source quality.
Missing data is null/unknown. Never carry old Ads figures forward as current.
Explain supported findings, uncertainty, tracking changes and next actions.
Publish the completed review into Ads > Google through the connected report queue and verify readback.
Do not change ads, budget, country targeting, pixels, consent, customer orders or existing Meta ads."""

TRACKING_PROMPT = """Audit the existing Sports Cave purchase measurement before scaling.
Google account 658-112-1605, PM021126 / 24420240881; GA4 property 355333982.
Merchant Center 705475729; Shopify sportscave-nb.myshopify.com.
Meta dataset 1158699336263893.
Check purchase event mapping, transaction ID, currency/value, browser/server event_id deduplication,
primary versus secondary Ads conversions, attribution windows and consent diagnostics.
Compare exact Shopify IDs with GA4. An absent report row alone does not prove a broken pixel.
Inspect paid UTMs and organic referrals; preserve valid purchase events for all channels.
Google and Meta can both credit a sale. Report overlaps instead of deleting legitimate events.
Keep A$20/day and AU/USA together. Prepare any changes with evidence; ask for approval before
new live changes. Existing Meta ads are outside the tracking rollout; update future OS posting only."""

IMPROVEMENT_PROMPT = """Prepare evidence-backed improvements to Sports Cave's existing Performance Max campaign.
Start with reconciled purchases and tracking quality. Separate branded demand from generic demand,
new customers from returning customers when supported, and reported attribution from incrementality.
Review product feed accuracy/eligibility, landing pages, truthful copy, image crops and search terms.
Use existing approved product imagery. Do not invent scarcity, endorsements or product claims.
Keep the current A$20/day budget and combined Australia/USA campaign.
Provide exact proposed changes, expected learning, success metrics and a weekly review plan.
Do not publish new creatives or change bidding/budget without a fresh explicit instruction."""

PREPARED_HEADLINES = (
    "Limited Edition Sports Art", "Framed Sports Wall Art", "Sports Legends For Your Wall",
    "Find Your Sporting Moment", "Art For Your Home Office", "Build Your Sports Cave",
    "Celebrate Sporting Greatness", "Explore Sports Wall Art", "Frames To Suit Your Space",
    "Basketball Wall Art", "Cricket Legends Wall Art", "Motorsport Wall Art",
    "Football Legends Wall Art", "Your Favourite Sports Icons", "Shop Sports Cave")
PREPARED_DESCRIPTIONS = (
    "Explore limited edition sports wall art and choose a frame to suit your space.",
    "Celebrate iconic athletes and sporting moments with wall art from Sports Cave.",
    "Find sports art for your home office, living room or collection. Explore the range.",
    "Browse basketball, cricket, football and motorsport artwork. Find your next piece.")


def latest_week(today):
    yesterday = today - timedelta(days=1)
    end = yesterday - timedelta(days=(yesterday.weekday() - 3) % 7)
    return end - timedelta(days=6), end


def _money(value):
    return "—" if value is None else f"A${value:,.2f}"


def _ratio(row):
    if row.get("spend") and row.get("value") is not None:
        return f'{row["value"] / row["spend"]:.2f}x'
    return "—"


def _synced_at(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        ZoneInfo("Australia/Sydney")).strftime("%d %b %Y %I:%M %p %Z")


@st.cache_data(ttl=300, show_spinner=False)
def _connected(end):
    return reporting.connected_sources(end)


def render_page(user):
    st.title("Google")
    st.caption("Campaign performance, tracking evidence and weekly reviews")
    if not reviews.can_view(user):
        st.info("Google financial reporting is available to authorised reporting users.")
        return
    st.caption("Current plan: A$20/day · Australia + USA together · improve tracking before scaling")
    with st.expander("Campaign setup"):
        st.write("Performance Max · PM021126 · campaign 24420240881")
        st.write("Google Ads 658-112-1605 · Merchant Center 705475729")
        st.write("GA4 Sports Cave Google · property 355333982 · measurement G-J89Q2E80VQ")
        st.caption("Audit configuration recorded 20 November 2026. Ads budget and settings still require an account review.")
    try:
        history = reviews.history()
    except Exception:
        st.error("Saved reviews could not be loaded. Refresh to retry.")
        return
    overview, weekly, tracking, prompts = st.tabs(["Overview", "Weekly reviews", "Tracking", "Prompts"])
    latest = history[0] if history else None
    with overview:
        start, end = latest_week(sydney_date())
        st.subheader("Automatic Google Ads reporting")
        st.caption("Fixed Sports Cave account and PM021126 campaign. Refreshes on page load with a 15-minute cache. Reads reporting only; budget stays at A$20/day.")
        automatic = ads_api.report(start, end)
        if automatic["status"] == "connected":
            st.caption(f'{automatic["period_start"]} to {automatic["period_end"]} · {automatic["timezone"]} · fetched {automatic["fetched_at"]}')
            a, b = st.columns(2)
            a.metric("API spend", _money(automatic["totals"]["spend"]))
            b.metric("API attributed purchases", str(automatic["totals"]["purchases"]))
            a.metric("API purchase value", _money(automatic["totals"]["value"]))
            b.metric("API value / spend", _ratio(automatic["totals"]))
            st.write(f'Campaign: {automatic["campaign_name"]} · {automatic["campaign_status"]} · observed daily budget {_money(automatic["daily_budget"])}')
            if not automatic["budget_matches_plan"] or automatic["budget_shared"]:
                st.warning("The observed budget differs from the A$20/day individual campaign plan, or is shared. Review it in Google Ads; this integration makes no budget changes.")
            st.caption(automatic["note"])
            st.dataframe(automatic["daily"], hide_index=True, width="stretch")
        else:
            st.info(automatic["note"])
            if os_accounts.is_admin(user):
                st.link_button("Connect Google Ads reporting", ads_api.CONNECT_PATH)
                st.caption("Use the existing Google Cloud project with Google Ads API enabled and Explorer or higher access. Google requests its standard Ads permission; this OS integration only reads reports.")
        if st.button("Refresh Google Ads", key="google_ads_api_refresh"):
            ads_api.CACHE.clear()
            st.rerun()
        st.subheader("Latest saved weekly review")
        if latest:
            edition = latest["edition"]
            st.caption(f'Latest sync: {_synced_at(latest["published_at"])} · {edition["period_start"]} to {edition["period_end"]}')
            expected = latest_week(sydney_date())[1].isoformat()
            if edition["period_end"] < expected:
                st.warning("The latest completed week's review has not synced yet. Previous results remain dated.")
            st.write(edition["summary"])
            google = next((r for r in edition["platforms"] if r["source"] == "google_ads"), {})
            a, b, c = st.columns(3)
            a.metric("Google Ads spend", _money(google.get("spend")))
            b.metric("Attributed purchases", "—" if google.get("purchases") is None else str(google["purchases"]))
            c.metric("Reported value / spend", _ratio(google))
            st.caption("Platform-attributed results can overlap with Meta. Revenue / spend does not measure incremental sales or profit.")
            for finding in edition["findings"]:
                st.write(finding)
        else:
            st.info("The first weekly review is awaiting sync.")
        st.subheader("Connected reporting")
        st.caption("Refresh reads Google Ads, GA4, stored Shopify orders and Meta through the OS connections. Each source shows its actual access and coverage.")
        end = st.date_input("Week ending Thursday", value=latest_week(sydney_date())[1],
                            max_value=sydney_date() - timedelta(days=1), key="google_report_end")
        if st.button("Refresh connected data", key="google_connected_refresh"):
            if end.weekday() != 3:
                st.error("Choose a Thursday for a Friday–Thursday review.")
            else:
                _connected.clear()
                ads_api.CACHE.clear()
                with st.spinner("Reading connected sources"):
                    st.session_state["google_connected_result"] = _connected(end)
        connected = st.session_state.get("google_connected_result")
        if connected:
            st.caption(f'Connected snapshot: {connected["period_start"]} to {connected["period_end"]}')
            for name, source in connected["sources"].items():
                with st.expander(f'{name.upper()} · {source["status"]}'):
                    st.caption(source.get("note", ""))
                    if name == "ga4" and source.get("rows") is not None:
                        st.caption(f'Property {source["property_id"]} · {source["timezone"]} · {source["currency"]} · fetched {source["fetched_at"]}')
                        st.dataframe([{**r["dimensions"], **r["metrics"]} for r in source["rows"]],
                                     hide_index=True, width="stretch")
                    elif name == "shopify" and source.get("orders") is not None:
                        st.metric("Stored orders", source["orders"])
                        st.dataframe(source.get("known_paid_order_totals_by_currency", []),
                                     hide_index=True, width="stretch")
                    elif name == "meta" and source.get("known_totals"):
                        st.caption(f'{source["rows"]} ad/date rows · {source["currency"]} · {source["timezone"]} · fetched {source["fetched_at"]}')
                        st.dataframe([{"metric": field, "known_total": value,
                                       "rows_missing_value": source["missing_rows"][field]}
                                      for field, value in source["known_totals"].items()],
                                     hide_index=True, width="stretch")
            source = connected["google_ads"]
            with st.expander(f'GOOGLE ADS · {source["status"]}'):
                st.caption(source["note"])
                if source.get("totals"):
                    st.write(source["totals"])
                    st.caption(f'{source["currency"]} · {source["timezone"]} · fetched {source["fetched_at"]}')
                    st.dataframe(source["daily"], hide_index=True, width="stretch")
        links = st.columns(4)
        links[0].link_button("Google Ads", "https://ads.google.com/")
        links[1].link_button("GA4", "https://analytics.google.com/analytics/web/#/a258394589p355333982/")
        links[2].link_button("Merchant Center", "https://merchants.google.com/")
        links[3].link_button("Shopify", "https://admin.shopify.com/store/sportscave-nb")
    with weekly:
        st.caption("Friday 10am Sydney · prior Friday–Thursday · reports archive automatically after verified publication")
        if st.button("Refresh reviews", key="google_reviews_refresh"):
            st.rerun()
        if history:
            selected = st.selectbox("Saved week", list(range(len(history))),
                format_func=lambda i: f'{history[i]["edition"]["period_start"]} to {history[i]["edition"]["period_end"]} · revision {history[i]["edition"]["revision"]}')
            saved, edition = history[selected], history[selected]["edition"]
            st.write(edition["summary"])
            st.subheader("Platform attribution")
            st.dataframe([{"Source": row["source"].replace("_", " ").title(),
                           "Coverage": row["status"], "Spend": _money(row["spend"]),
                           "Attributed purchases": row["purchases"], "Purchase value": _money(row["value"]),
                           "Value / spend": _ratio(row), "Basis": row["basis"]}
                          for row in edition["platforms"]],
                         hide_index=True, width="stretch")
            st.caption("Each platform has its own attribution. These rows must not be added as unique sales.")
            st.subheader("Exclusive Shopify order ledger")
            st.dataframe([{"Channel": row["channel"], "Unique orders": row["orders"],
                           "Order totals": _money(row["value"])} for row in edition["channels"]],
                         hide_index=True, width="stretch")
            st.caption("Latest observed non-direct Shopify journey classification. GA4 purchase-session evidence is separate.")
            st.subheader("Next actions")
            for action in edition["actions"]:
                st.write("• " + action)
            with st.expander("Sources and limitations"):
                for source in edition["sources"]:
                    st.write("• " + source)
                st.caption(f'Published {_synced_at(saved["published_at"])} · verified submission {saved["sha256"][:12]}')
            st.download_button("Download review JSON", json.dumps(edition, indent=2),
                file_name=f'google-review-{edition["period_end"]}.json', mime="application/json")
        else:
            st.info("No weekly reviews have been published yet.")
    with tracking:
        st.write("Google paid, Meta paid and organic are separate reporting categories. Valid purchase events continue across all channels; the order ledger resolves unique sales.")
        if latest:
            st.dataframe([{"Check": row["label"], "Status": row["status"],
                           "Evidence": row["detail"], "Checked on": row["checked_on"]}
                          for row in latest["edition"]["tracking"]], hide_index=True, width="stretch")
        st.caption("Verified means observed on the recorded check date. A live tag still needs validation on future real clicks and purchases.")
        from google_tracking_contract import CAMPAIGN_SUFFIX
        st.code("Google campaign final URL suffix: " + CAMPAIGN_SUFFIX, language=None)
        observed = (automatic or {}).get("tracking_health") or {}
        if observed:
            st.dataframe([{"Live setting": key.replace("_", " "), "Verified": value}
                          for key, value in observed.get("checks", {}).items()], hide_index=True, width="stretch")
            if observed.get("status") == "attention":
                st.warning("Google paid tracking settings need attention: " + ", ".join(observed.get("missing", [])))
            st.caption(observed.get("note", ""))
        st.write("Paid-only UTM term markers distinguish ad clicks from shared Merchant feed URLs. Keep Google auto-tagging enabled. Never label free listings as paid or tag internal links.")
        from ads_meta_contract import META_AD_URL_PARAMETERS
        st.code("Future OS Meta ads: " + META_AD_URL_PARAMETERS, language=None)
        st.write("Organic posts retain organic_social. Keep internal store links untagged.")
    with prompts:
        for title, prompt in (("Weekly review", REVIEW_PROMPT), ("Tracking audit", TRACKING_PROMPT),
                              ("Campaign improvements", IMPROVEMENT_PROMPT)):
            st.subheader(title)
            st.code(prompt, language=None)
        st.subheader("Prepared Google copy")
        st.caption("Prepared on 20 November 2026; not published. Use approved images with correct crops and a square logo.")
        st.dataframe([{"Asset": kind, "Copy": text, "Characters": len(text)}
                      for kind, texts in (("Headline", PREPARED_HEADLINES), ("Description", PREPARED_DESCRIPTIONS))
                      for text in texts], hide_index=True, width="stretch")
