"""Publish a compact, team-safe Meta brief using a fixed set of display fields."""

from datetime import date
from decimal import Decimal
from html import escape
import json
import math
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from crm_growth_reporting import device_orders
import meta_ads_client
import meta_review_live
import os_accounts
from home_sports_morning_brief import LOG, _text
from meta_reporting_contract import reporting_window, validate_account
from meta_review_analysis import action
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting


PATH = "/ops/meta-morning-brief/publish"
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
            if not isinstance(items, list) or not 1 <= len(items) <= 3:
                raise ValueError("Include one to three insights per section.")
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


def account_roas(day):
    """Read Meta's own account roll-up for one completed account day."""
    config = meta_ads_client.get_meta_config()
    account_id = config["ad_account_id"]
    reader = meta_review_live.Reader(config, max_pages=1, seconds=12)
    account = validate_account(
        reader.get(account_id, {"fields": "account_id,currency,timezone_name"}), account_id
    )
    reporting_window(account, day, day)
    rows = reader.pages(account_id + "/insights", {
        **meta_review_live.date_params(day, day),
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
        or rows[0].get("date_stop") != day.isoformat()
    ):
        raise ValueError("Meta returned an unexpected account or reporting period.")
    value = action(rows[0], "purchases", "purchase_roas")
    return value if value is not None and value <= 10_000 else None


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


def _label(day):
    return day.strftime("%d %B %Y").lstrip("0")


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
    st.caption(f"{_label(day)} · Sydney" if day == today else f"{_label(day)} · Sydney · Today's brief pending")
    roas = edition["roas"] if edition else None
    ga4 = (edition or {}).get("ga4_orders") or {}
    device_tiles = ""
    for device in ("desktop", "mobile"):
        count = ga4.get(device)
        value = f"{count:,}" if count is not None else "Unavailable"
        device_tiles += f'<div><dt>{device.title()} orders</dt><dd>{value}</dd><small>GA4</small></div>'
    roas_value = f"{Decimal(str(roas)):.2f}×" if roas is not None else "Unavailable"
    report_day = f'<p class="sc-meta-period">{_label(_day(edition["report_date"]))} reporting</p>' if edition else ""
    ga4_zone = (
        f'<p class="sc-meta-source">GA4 property time · {escape(ga4["timezone"])}</p>'
        if ga4 and ga4["timezone"] != "Australia/Sydney" else ""
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
    st.html(
        """<style>
        .sc-meta-brief {--line:rgba(128,114,82,.24);font-size:.82rem;line-height:1.4}
        .sc-meta-brief .sc-meta-period {margin:0 0 .45rem;opacity:.75;font-size:.76rem}
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
        .sc-meta-insight summary {padding:.55rem .8rem;font-weight:650;cursor:pointer}
        .sc-meta-insight ul {margin:0 .85rem .7rem;padding-left:1.15rem}
        .sc-meta-insight li+li {margin-top:.35rem}
        </style>"""
        f'<section class="sc-meta-brief" aria-label="CRM snapshot">{report_day}'
        f'<dl><div><dt>Meta ROAS</dt><dd>{roas_value}</dd></div>'
        f'{device_tiles}</dl>{ga4_zone}'
        + review + insight_cards + '</section>'
        + """<script>{
          const panel = [...document.querySelectorAll(".sc-meta-brief")].at(-1);
          const button = panel?.querySelector(".sc-meta-more");
          if (button && !button.dataset.ready) {
            button.dataset.ready = "true";
            button.addEventListener("click", () => panel.querySelector(".sc-meta-full").showModal());
          }
        }</script>""",
        unsafe_allow_javascript=True,
    )
