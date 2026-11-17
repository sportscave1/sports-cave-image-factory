"""Publish a compact, team-safe Meta brief using a fixed set of display fields."""

from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from html import escape
import json
import math
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from crm_growth_reporting import device_orders
from google_direct_reporting import MemoryReports
import meta_ads_client
import meta_review_live
import os_accounts
import home_design_refresh
from home_sports_morning_brief import LOG, _text
from meta_reporting_contract import validate_account
from meta_review_analysis import action
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting


PATH = "/ops/meta-morning-brief/publish"
RESULTS_PATH = "/ops/meta-morning-brief/results"
PERIODS = {"yesterday": "Yesterday", "week": "Last 7 days", "month": "Last 30 days",
           "quarter": "Last 3 months", "today": "Today"}
RESULTS_CACHE = MemoryReports(max_bytes=65536)
RESULTS_POOL = ThreadPoolExecutor(max_workers=4)
SETTING_KEY = "home_meta_morning_brief"
MAX_PAYLOAD = 16000
ACTIONS = {
    "check_reporting": "Check Meta reporting coverage",
    "review_delivery": "Review active ad delivery",
    "check_orders": "Verify the Shopify order count",
    "review_creative": "Review creatives for a refresh",
    "review_catalogue": "Check product and variant availability",
    "review_sports": "Review sports stories for an ad test",
}
FIELDS = {"date", "report_date", "roas", "orders", "actions"}
REVIEW_FIELDS = {"summary", "recommendations"}
INSIGHT_LABELS = {
    "shopify": "Shopify · catalogue and storefront",
    "ga4": "GA4 · acquisition and checkout",
    "seo": "Search Console · SEO opportunities",
    "sports": "Sports · opportunities to test",
}
MAX_RECOMMENDATIONS = 8
VISIBLE_RECOMMENDATIONS = 3
PRIORITY_PREFIX = re.compile(r"^(?:first|second|third|fourth|fifth|sixth|seventh|eighth)\s*:\s*", re.IGNORECASE)
FINANCIAL_TEXT = re.compile(
    r"\b(?:aud|usd|nzd|cad|gbp|eur|jpy|inr|chf|dollars?|cents?|euros?|pounds?|"
    r"spend(?:ing)?|spent|payouts?|revenue|sales value|purchase value|"
    r"budgets?|costs?|prices?|cpc|cpm|cpa)\b", re.IGNORECASE
)


def _home_text(value, limit, field):
    value = _text(value, limit, field)
    normalized = unicodedata.normalize("NFKC", value)
    if FINANCIAL_TEXT.search(normalized) or any(
        unicodedata.category(char) in {"Sc", "Cf"} or char.isnumeric()
        for char in normalized
    ):
        raise ValueError(f"Keep {field.lower()} qualitative and free of financial figures.")
    return value


def _day(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Use YYYY-MM-DD for Sydney dates.") from None
    if parsed.isoformat() != value:
        raise ValueError("Use YYYY-MM-DD for Sydney dates.")
    return parsed


def can_view(user):
    return os_accounts.can_access_reporting(user)


def parse_edition(raw, today, *, stored=False):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError("The Meta brief is too long.")
    try:
        edition = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Enter valid Meta Morning Brief JSON.") from None
    optional = {"insights"} | ({"ga4_orders"} if stored else set())
    if (not isinstance(edition, dict) or not FIELDS <= set(edition) <= FIELDS | REVIEW_FIELDS | optional
            or set(edition) & REVIEW_FIELDS not in (set(), REVIEW_FIELDS)):
        raise ValueError("Include date, report_date, roas, orders and actions. Add summary and recommendations together.")
    day = _day(edition["date"])
    report_day = _day(edition["report_date"])
    if day > today or report_day >= day:
        raise ValueError("Use a completed Sydney reporting day before the edition date.")
    orders = edition["orders"]
    if orders is not None and (type(orders) is not int or not 0 <= orders <= 1_000_000):
        raise ValueError("Orders must be a nonnegative whole number or null.")
    roas = edition["roas"]
    if roas is not None and (
        type(roas) not in (int, float) or not 0 <= roas <= 10_000 or not math.isfinite(roas)
    ):
        raise ValueError("ROAS must be a nonnegative number or null.")
    actions = edition["actions"]
    if not isinstance(actions, list) or len(actions) > 3 or any(
        not isinstance(action, str) or action not in ACTIONS for action in actions
    ) or len(set(actions)) != len(actions):
        raise ValueError("Choose up to three distinct supported action codes.")
    if "summary" in edition:
        edition["summary"] = _home_text(edition["summary"], 240, "Summary")
        items = edition["recommendations"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_RECOMMENDATIONS:
            raise ValueError(f"Include one to {MAX_RECOMMENDATIONS} recommendations.")
        edition["recommendations"] = [_home_text(item, 190, "Recommendation") for item in items]
        distinct = {}
        for item in edition["recommendations"]:
            key = " ".join((PRIORITY_PREFIX.sub("", item) or item).casefold().split()).rstrip(".!?")
            distinct.setdefault(key, item)
        if not stored and len(distinct) != len(items):
            raise ValueError("Each recommendation must be distinct.")
        edition["recommendations"] = list(distinct.values())
    if "insights" in edition:
        insights = edition["insights"]
        if not isinstance(insights, dict) or not set(insights) <= INSIGHT_LABELS.keys():
            raise ValueError("Use Shopify, GA4, SEO or sports insight sections.")
        for section, items in insights.items():
            maximum = 6 if section == "sports" else 3
            if not isinstance(items, list) or not 1 <= len(items) <= maximum:
                raise ValueError(f"Include one to {maximum} insights for {section}.")
            insights[section] = [_home_text(item, 220, "Insight") for item in items]
    devices = edition.get("ga4_orders")
    if devices is not None:
        if (not isinstance(devices, dict) or set(devices) != {"desktop", "mobile", "timezone"}
                or not isinstance(devices["timezone"], str)):
            raise ValueError("Invalid saved GA4 orders.")
        for device in ("desktop", "mobile"):
            count = devices[device]
            if count is not None and (type(count) is not int or not 0 <= count <= 1_000_000):
                raise ValueError("Invalid saved GA4 order count.")
        try:
            ZoneInfo(devices["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid saved GA4 time zone.") from None
    return edition


def account_roas(day, end=None):
    """Read Meta's account roll-up for the exact requested calendar window."""
    end = end or day
    config = meta_ads_client.get_meta_config()
    account_id = config["ad_account_id"]
    reader = meta_review_live.Reader(config, max_pages=1, seconds=12)
    account = validate_account(
        reader.get(account_id, {"fields": "account_id,currency,timezone_name"}), account_id
    )
    if account["timezone_name"] != "Australia/Sydney" or not day <= end <= sydney_date():
        raise ValueError("Meta reporting dates do not match the Sydney window.")
    rows = reader.pages(account_id + "/insights", {
        **meta_review_live.date_params(day, end),
        "fields": "account_id,date_start,date_stop,purchase_roas",
        "level": "account",
        "use_unified_attribution_setting": "true",
        "action_report_time": "impression",
    })
    if not rows:
        return None
    if len(rows) != 1 or (
        str(rows[0].get("account_id")) != account_id.removeprefix("act_")
        or rows[0].get("date_start") != day.isoformat()
        or rows[0].get("date_stop") != end.isoformat()
    ):
        raise ValueError("Meta returned an unexpected account or reporting period.")
    value = action(rows[0], "purchases", "purchase_roas")
    return value if value is not None and value <= 10_000 else None


def period_window(period, today):
    if period == "today":
        return today, today
    end = today - timedelta(days=1)
    if period == "quarter":
        year, month = divmod(today.year * 12 + today.month - 4, 12)
        month += 1
        return date(year, month, min(today.day, monthrange(year, month)[1])), end
    return today - timedelta(days={"yesterday": 1, "week": 7, "month": 30}[period]), end


def period_results(period, today):
    start, end = period_window(period, today)

    def read(source, call):
        try:
            return RESULTS_CACHE.read((source, period, start.isoformat(), end.isoformat()),
                                      180 if period == "today" else 900, call)
        except Exception as error:
            LOG.warning("home_period_unavailable source=%s type=%s", source, type(error).__name__)
            return None

    meta = RESULTS_POOL.submit(read, "meta", lambda: account_roas(start, end))
    google = RESULTS_POOL.submit(read, "ga4", lambda: device_orders(start, end, include_today=period == "today"))
    ga4 = google.result() or {}
    if ga4.get("timezone") != "Australia/Sydney":
        ga4 = {}
    roas = meta.result()
    return {"roas": f"{Decimal(str(roas)):.2f}×" if roas is not None else None,
            "desktop": ga4.get("desktop"), "mobile": ga4.get("mobile")}


def publish(raw, user):
    if not can_view(user):
        raise PermissionError("Reporting access is required to publish the Meta brief.")
    today = sydney_date()
    edition = parse_edition(raw, today)
    if edition["date"] != today.isoformat():
        raise ValueError("Publish only today's Sydney Meta brief.")
    try:
        edition["roas"] = account_roas(_day(edition["report_date"]))
    except (meta_ads_client.MetaAdsApiError, TimeoutError, OSError, ValueError, ZoneInfoNotFoundError) as error:
        LOG.warning("home_meta_account_roas_unavailable type=%s", type(error).__name__)
        edition["roas"] = None
    try:
        edition["ga4_orders"] = device_orders(_day(edition["report_date"]))
    except Exception as error:
        LOG.warning("home_ga4_device_orders_unavailable type=%s", type(error).__name__)
        edition["ga4_orders"] = None
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (%s, %s::jsonb, now())
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
            WHERE (app_settings.value->>'date') <= (EXCLUDED.value->>'date')
            RETURNING key
            """,
            (SETTING_KEY, json.dumps(edition, ensure_ascii=False)),
        )
        if cursor.fetchone() is None:
            raise ValueError("A more recent Meta brief is already published.")
    return edition


def render(st, user, today):
    if not can_view(user):
        return
    st.subheader("Meta CRM — Morning Brief")
    try:
        saved = get_app_setting(SETTING_KEY, ensure_schema_first=False)
        if not saved:
            st.caption("No Meta brief has been published yet.")
            return
        day = _day(saved["date"])
        # Older editions include unrestricted text and financial metrics. Keep them out of the page entirely.
        edition = parse_edition(json.dumps(saved), today, stored=True) if FIELDS <= set(saved) else None
    except Exception as error:
        LOG.warning("home_meta_morning_brief_unavailable type=%s", type(error).__name__)
        st.warning("The Meta brief is temporarily unavailable.")
        return
    if day != today:
        st.caption("Today's recommendations are pending.")
    yesterday_saved = bool(edition and _day(edition["report_date"]) == today - timedelta(days=1))
    roas = edition["roas"] if yesterday_saved else None
    ga4 = (edition.get("ga4_orders") or {}) if yesterday_saved else {}
    if ga4.get("timezone") != "Australia/Sydney":
        ga4 = {}
    device_tiles = ""
    for device in ("desktop", "mobile"):
        count = ga4.get(device)
        value = f"{count:,}" if count is not None else "Unavailable"
        device_tiles += f'<div><dt>{device.title()} orders</dt><dd>{value}</dd><small>GA4</small></div>'
    roas_value = f"{Decimal(str(roas)):.2f}×" if roas is not None else "Unavailable"
    periods = (
        '<label class="sc-meta-period">Results <select aria-label="Reporting period">'
        + "".join(f'<option value="{key}">{label}</option>' for key, label in PERIODS.items())
        + '</select></label><small class="sc-meta-source" role="status"></small>'
    )
    review = ""
    if edition and edition.get("summary"):
        items = [
            f"<li>{escape(PRIORITY_PREFIX.sub('', item) or item)}</li>"
            for item in edition["recommendations"]
        ]
        extra = items[VISIBLE_RECOMMENDATIONS:]
        more = (
            '<button type="button" class="sc-meta-more" aria-haspopup="dialog">More recommendations</button>'
            '<dialog class="sc-meta-full" aria-label="More ad recommendations">'
            '<header><h4>More ad recommendations</h4><form method="dialog"><button>Close</button></form></header>'
            f'<ol start="{VISIBLE_RECOMMENDATIONS + 1}">{"".join(extra)}</ol></dialog>'
            if extra else ""
        )
        review = (
            '<section class="sc-meta-review" aria-label="Daily ad review">'
            f'<p>{escape(edition["summary"])}</p>'
            f'<h4>Ad recommendations</h4><ol>{"".join(items[:VISIBLE_RECOMMENDATIONS])}</ol>{more}</section>'
        )
    insights = (edition or {}).get("insights", {})
    insight_cards = "".join(
        f'<details class="sc-meta-insight"><summary>{label}</summary><ul>'
        + "".join(f"<li>{escape(item)}</li>" for item in insights[section])
        + "</ul></details>"
        for section, label in INSIGHT_LABELS.items() if section in insights
    )
    try:
        refresh = home_design_refresh.render_html(today)
    except Exception as error:
        LOG.warning("home_design_refresh_unavailable type=%s", type(error).__name__)
        refresh = ""
    st.html(
        """<style>
        .sc-meta-brief {--line:rgba(128,114,82,.24);font-size:.82rem;line-height:1.4}
        .sc-meta-period {display:inline-flex;align-items:center;gap:.45rem;margin:0 .5rem .55rem 0;font-size:.76rem}
        .sc-meta-period select {font:inherit;color:inherit;background:var(--background-color,#fff);
            border:1px solid var(--line);border-radius:6px;padding:.22rem .35rem}
        .sc-meta-brief dl {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(7rem,100%),1fr));
            gap:.55rem;margin:0;padding:0}
        .sc-meta-brief dl div {background:var(--background-color,#fff);
            border:1px solid var(--line);border-radius:12px;box-shadow:0 1px 3px #15110b0c}
        .sc-meta-brief dl div {padding:.75rem .85rem;border-top:2px solid #b49048;overflow-wrap:anywhere}
        .sc-meta-brief dt {font-size:.76rem;opacity:.82}
        .sc-meta-brief dd {margin:.12rem 0 0;font-size:1rem;font-weight:650;font-variant-numeric:tabular-nums}
        .sc-meta-brief small,.sc-meta-source {font-size:.72rem;opacity:.75}
        .sc-meta-source {margin:.45rem 0 0}
        .sc-meta-review {margin-top:.75rem;padding:.85rem 1rem;border:1px solid var(--line);
            border-radius:16px;background:var(--background-color,#fff);overflow-wrap:anywhere;box-shadow:0 2px 8px #20190c0d}
        .sc-meta-review p,.sc-meta-review li {font-size:.82rem;line-height:1.45}
        .sc-meta-review p {margin:0 0 .55rem}
        .sc-meta-review h4 {font-size:.85rem;margin:0 0 .2rem;padding:0}
        .sc-meta-review ol {margin:0;padding-left:1.35rem}
        .sc-meta-review li {padding:.48rem 0 .48rem .15rem}
        .sc-meta-review li::marker {color:#8c601a;font-weight:650}
        .sc-meta-review li+li {border-top:1px solid var(--line)}
        .sc-meta-more,.sc-meta-full button {margin-top:.35rem;padding:.3rem .6rem;font:inherit;font-weight:650;
            border:1px solid var(--line);border-radius:6px;background:transparent;color:inherit;cursor:pointer}
        .sc-meta-full {width:min(37rem,calc(100vw - 2rem));max-height:80dvh;padding:1rem;
            border:1px solid var(--line);border-radius:14px;background:var(--background-color,#fff);color:inherit}
        .sc-meta-full::backdrop {background:#181512a0}
        .sc-meta-full header {display:flex;justify-content:space-between;align-items:center;gap:.7rem}
        .sc-meta-insight {margin-top:.45rem;border:1px solid var(--line);border-radius:12px;
            background:var(--background-color,#fff);overflow-wrap:anywhere}
        .sc-meta-insight summary {padding:.45rem .75rem;font-size:.8rem;font-weight:700;cursor:pointer}
        .sc-meta-insight ul,.sc-meta-insight p {margin:0 .85rem .6rem;font-size:.77rem;line-height:1.4}
        .sc-meta-insight ul {padding-left:1.1rem}
        .sc-meta-insight li+li {margin-top:.35rem}
        </style>"""
        f'<section class="sc-meta-brief" aria-label="CRM snapshot" data-saved="{int(yesterday_saved)}">{periods}'
        f'<dl><div><dt>Meta ROAS</dt><dd>{roas_value}</dd></div>'
        f'{device_tiles}</dl>'
        + review + insight_cards + refresh + '</section>'
        + """<script>{
          const panel = [...document.querySelectorAll(".sc-meta-brief")].at(-1);
          const button = panel?.querySelector(".sc-meta-more");
          if (button && !button.dataset.ready) {
            button.dataset.ready = "true";
            button.addEventListener("click", () => panel.querySelector(".sc-meta-full").showModal());
          }
          const select = panel?.querySelector("select");
          if (select && !select.dataset.ready) {
            select.dataset.ready = "true";
            const values = [...panel.querySelectorAll("dl dd")];
            const status = panel.querySelector(".sc-meta-source");
            const saved = values.map(tile => tile.textContent);
            let request;
            const render = (items, note) => {
              values.forEach((tile, index) => { tile.textContent = items[index] ?? "Unavailable"; });
              status.textContent = note;
            };
            async function load() {
              request?.abort();
              const period = select.value;
              if (period === "yesterday" && panel.dataset.saved === "1") {
                render(saved, "");
                return;
              }
              const controller = new AbortController();
              request = controller;
              render(["…", "…", "…"], "Loading results");
              try {
                const response = await fetch("/ops/meta-morning-brief/results?period=" + encodeURIComponent(period),
                                             {signal: controller.signal});
                if (!response.ok) throw new Error();
                const data = await response.json();
                if (!controller.signal.aborted) render([data.roas, data.desktop, data.mobile],
                  period === "today" ? "Today is partial. Reporting may lag." : "");
              } catch {
                if (!controller.signal.aborted) render([], "Results temporarily unavailable");
              }
            }
            select.addEventListener("change", load);
            if (panel.dataset.saved !== "1") load();
          }
        }</script>""",
        unsafe_allow_javascript=True,
    )
