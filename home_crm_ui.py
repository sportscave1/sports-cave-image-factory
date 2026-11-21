"""Small Home CRM table and nonblocking, accessible refresh controls."""
from html import escape
import json
from datetime import timedelta
import math
from datetime import datetime
from zoneinfo import ZoneInfo

CHANNELS = ("Facebook paid", "Google paid", "Organic", "Other", "Unresolved")


def html(today, initial=None):
    day = str(today - timedelta(days=1))
    # Only aggregate data is passed to the client. The backend never returns order IDs.
    initial = initial or {"state": "loading", "data": None}
    data = initial.get("data") or {}
    ledger = data.get("ledger") or {}
    indexed = {row["channel"]: row for row in ledger.get("rows", [])}
    def count(name, key):
        value = indexed.get(name, {}).get(key)
        return f"{value:,}" if type(value) is int and value >= 0 else "—"
    def ratio(name):
        value = data.get("roas", {}).get(name)
        return f"{value:.2f}×" if type(value) in (float, int) and math.isfinite(value) else "—"
    def number(value):
        return f"{value:,.2f}".rstrip("0").rstrip(".") if type(value) in (float, int) and math.isfinite(value) and value >= 0 else "—"
    google = data.get("coverage", {}).get("google", {})
    ads_purchases = number(google.get("purchases")) if google.get("status") == "verified" else "—"
    ga4_status = data.get("coverage", {}).get("ga4", {}).get("status")
    ga4_paid = number(ledger.get("ga4_channel_orders", {}).get("Google paid")) if ga4_status == "verified" else "—"
    raw_paid = number(ledger.get("shopify_channel_orders", {}).get("Google paid"))
    comparison = (f'Google paid orders: reconciled {count("Google paid", "total")} · Shopify last visit {raw_paid} · '
                  f'GA4 purchase session {ga4_paid}. Google Ads: {ads_purchases} attributed purchases '
                  '(ad interaction dates).') if ledger else ""
    warnings = []
    differences = ledger.get("paid_organic_differences", 0)
    if differences:
        warnings.append(f"{differences} {'order has' if differences == 1 else 'orders have'} paid/organic model differences; an organic last visit does not rule out an earlier ad.")
    listings = ledger.get("source_reasons", {}).get("google_listing_paid_status_unknown", 0)
    if listings:
        warnings.append(f"{listings} Google listing {'order has' if listings == 1 else 'orders have'} unverified paid/organic status; counted as Unresolved.")
    resolved = ledger.get("google_listing_resolutions", {})
    if sum(resolved.values()):
        warnings.append(f"Google listing orders resolved by exact Analytics transaction matches: {resolved.get('paid', 0)} paid · {resolved.get('organic', 0)} organic.")
    tracking = google.get("tracking_health") or {}
    if tracking.get("status") == "attention":
        warnings.append("Google paid tracking settings need attention; see Google Ads Tracking.")
    rows = "".join('<tr data-channel="' + escape(name) + '"><th scope="row">' +
        escape(name) + '</th>' + ''.join('<td data-device="' + key + '">' + count(name, key) + '</td>'
            for key in ("mobile", "desktop", "other", "total")) + '</tr>' for name in CHANNELS)
    def coverage_line():
        result = []
        for name, source in data.get("coverage", {}).items():
            result.append(name + ": " + source["status"] + (" · " + source["fetched_at"] if source.get("fetched_at") else ""))
        return escape(" | ".join(result))
    if data:
        stamp = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Australia/Sydney")).strftime("%d %b %H:%M")
        status = (f"{ledger['orders']} Shopify orders · {ledger['matched']} exact GA4 matches · {ledger['unmatched']} unmatched"
                  if ledger else "Shopify count unavailable")
        differences = sum(row["orders"] for row in ledger.get("source_reconciliation", [])) if ledger else 0
        if differences:
            status += f" · {differences} source-model differences"
        if data.get("partial_day"):
            status += " · Today is partial"
        if any(row["status"] not in ("verified", "no_delivery") for row in data.get("coverage", {}).values()):
            status += " · Source gaps; see coverage"
        if initial.get("state") != "ready":
            status += " · Refreshing"
        status += " · Checked " + stamp + " Sydney"
        dates = data["start"] + " – " + data["end"]
    else:
        status, dates = "Loading verified results · updates automatically", ""
    return f"""<section class="sc-home-crm" aria-label="CRM source and device snapshot">
      <small class="sc-crm-dates">{escape(dates)}</small>
      <div class="sc-crm-paid"><span>Facebook / Instagram ROAS <b data-roas="facebook">{ratio("facebook")}</b></span>
        <span>Google ROAS <b data-roas="google">{ratio("google")}</b></span></div>
      <div class="sc-crm-table-wrap"><table><caption>Recorded source · Shopify + matched Analytics</caption>
        <thead><tr><th scope="col">Source</th><th scope="col">Mobile</th><th scope="col">Desktop</th>
        <th scope="col">Other /<br>unknown</th><th scope="col">Total</th></tr></thead><tbody>{rows}</tbody></table></div>
      <small class="sc-crm-status" role="status" aria-live="polite">{escape(status)}</small>
      <p class="sc-crm-comparison">{escape(comparison)}</p>
      {('<p class="sc-crm-warning">' + escape(' '.join(warnings)) + '</p>') if warnings else ''}
      <details class="sc-crm-coverage"><summary>Coverage &amp; attribution</summary><p class="sc-crm-basis">{escape(data.get("basis", ""))}</p>
        <p>Other includes direct, email and other referrals. Unresolved includes missing or conflicting source evidence.
        Tablets and unknown devices stay in Other / unknown. Organic has no advertising ROAS.</p>
        <p>Raw GA4 → Shopify source differences: {escape("; ".join(f"{r['ga4_channel']} → {r['shopify_channel']}: {r['orders']}" for r in ledger.get("source_reconciliation", [])) or "None recorded")}</p>
        <p>Feed tags such as product_sync / sag_organic alone do not verify a free-listing sale.
        Ambiguous Google feed tags use one consistent Google source from an exact Analytics transaction match.
        The separate GA4 comparison counts each matched order once; missing or conflicting sessions stay unresolved.
        Google Ads purchases are platform conversion credit, not additional orders to add to the table.</p>
        <p class="sc-crm-sources">{coverage_line()}</p><p>Paid-platform ROAS can overlap and is separate from the order table.
        Facebook includes Instagram. Google covers PM021126. Values can change as conversions arrive.</p></details>
    </section>"""


CSS = """<style>
.sc-home-crm{border:1px solid #9f875c44;border-radius:12px;padding:.65rem .8rem;font-size:.77rem;line-height:1.35;background:var(--background-color,#fff)}
.sc-crm-controls{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap;margin-bottom:.5rem}
.sc-crm-controls label{display:flex;align-items:center;gap:.35rem}
.sc-crm-controls select,.sc-crm-controls button{font:inherit;color:inherit;background:transparent;border:1px solid #9f875c55;border-radius:5px;padding:.2rem .4rem}
.sc-crm-dates{margin-left:auto}.sc-crm-paid{display:flex;gap:.6rem;flex-wrap:wrap;margin-bottom:.5rem}
.sc-crm-paid span{flex:1;border-top:2px solid #b49048;padding:.35rem .4rem;background:#b490480b;white-space:nowrap}
.sc-crm-paid b{float:right;margin-left:.6rem;font-variant-numeric:tabular-nums}
.sc-crm-table-wrap{overflow-x:auto}.sc-home-crm table{width:100%;border-collapse:collapse;font-size:.76rem}
.sc-home-crm caption{text-align:left;font-size:.72rem;opacity:.75;margin-bottom:.25rem}
.sc-home-crm th,.sc-home-crm td{padding:.3rem .25rem;border-bottom:1px solid #9f875c22;text-align:right;font-variant-numeric:tabular-nums}
.sc-home-crm th:first-child{text-align:left}.sc-home-crm tbody th{font-weight:500}
.sc-home-crm thead th{font-size:.7rem;line-height:1.2}
.sc-crm-status{display:block;margin-top:.45rem;opacity:.8}.sc-crm-coverage{font-size:.7rem;margin-top:.35rem}
.sc-crm-comparison,.sc-crm-warning{font-size:.72rem;margin:.4rem 0 0;line-height:1.4}
.sc-crm-warning{border-left:2px solid #b49048;padding-left:.4rem}
.sc-crm-coverage summary{cursor:pointer;font-weight:600}.sc-crm-coverage p{margin:.35rem 0}
</style>"""

def render(st, today, initial=None):
    import home_crm_reporting as crm
    from home_meta_morning_brief import PERIODS, period_window
    controls = st.columns([4, 1], gap="small")
    period = controls[0].selectbox("CRM reporting period", list(PERIODS),
        format_func=PERIODS.get, key="home_crm_period", label_visibility="collapsed")
    if period not in PERIODS:
        period = "yesterday"
    force = controls[1].button("Refresh", key="home_crm_refresh") is True
    start, end = period_window(period, today)
    result = crm.request(start, end, force=force)
    if result.get("data") is None and period == "yesterday" and initial and initial.get("data"):
        result = dict(state=result["state"], data=initial["data"])
    st.html(CSS + html(today, result))
