"""Publish a compact, team-safe Meta brief using a fixed set of display fields."""

from datetime import date
from decimal import Decimal
import json
import math

import os_accounts
from home_sports_morning_brief import LOG
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


def parse_edition(raw, today):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError("The Meta brief is too long.")
    try:
        edition = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Enter valid Meta Morning Brief JSON.") from None
    if not isinstance(edition, dict) or set(edition) != FIELDS:
        raise ValueError("Include date, report_date, roas, orders and actions only.")
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
    return edition


def publish(raw, user):
    if not can_view(user):
        raise PermissionError("Reporting access is required to publish the Meta brief.")
    today = sydney_date()
    edition = parse_edition(raw, today)
    if edition["date"] != today.isoformat():
        raise ValueError("Publish only today's Sydney Meta brief.")
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
        edition = parse_edition(json.dumps(saved), today) if set(saved) == FIELDS else None
    except Exception as error:
        LOG.warning("home_meta_morning_brief_unavailable type=%s", type(error).__name__)
        st.warning("The Meta brief is temporarily unavailable.")
        return
    st.caption(f"{_label(day)} · Sydney" if day == today else f"{_label(day)} · Sydney · Today's brief pending")
    orders = edition["orders"] if edition else None
    roas = edition["roas"] if edition else None
    orders_value = f"{orders:,}" if orders is not None else "Unavailable"
    roas_value = f"{Decimal(str(roas)):.2f}×" if roas is not None else "Unavailable"
    actions = edition["actions"] if edition else ["check_reporting"]
    items = "".join(f"<li>{ACTIONS[action]}</li>" for action in actions)
    report_day = f'<p class="sc-meta-period">{_label(_day(edition["report_date"]))} reporting</p>' if edition else ""
    st.html(
        """<style>
        .sc-meta-brief {--line:rgba(128,114,82,.24);font-size:.82rem;line-height:1.4}
        .sc-meta-brief .sc-meta-period {margin:0 0 .45rem;opacity:.75;font-size:.76rem}
        .sc-meta-brief dl {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem;margin:0}
        .sc-meta-brief dl div,.sc-meta-actions {background:var(--background-color,#fff);
            border:1px solid var(--line);border-radius:12px;box-shadow:0 1px 3px #15110b0c}
        .sc-meta-brief dl div {padding:.65rem .75rem;border-top:2px solid #b49048;overflow-wrap:anywhere}
        .sc-meta-brief dt {font-size:.76rem;opacity:.82}
        .sc-meta-brief dd {margin:.12rem 0 0;font-size:1rem;font-weight:650;font-variant-numeric:tabular-nums}
        .sc-meta-actions {margin-top:.5rem;padding:.6rem .75rem}
        .sc-meta-actions h4 {font-size:.8rem;margin:0 0 .3rem;padding:0}
        .sc-meta-actions ul {margin:0;padding:0;list-style:none}
        .sc-meta-actions li {font-size:.8rem;padding:.3rem 0}
        .sc-meta-actions li+li {border-top:1px solid var(--line)}
        </style>"""
        f'<section class="sc-meta-brief" aria-label="Meta and Shopify snapshot">{report_day}'
        f'<dl><div><dt>Meta ROAS</dt><dd>{roas_value}</dd></div>'
        f'<div><dt>Shopify orders</dt><dd>{orders_value}</dd></div></dl>'
        + (f'<div class="sc-meta-actions"><h4>Suggested next steps</h4><ul>{items}</ul></div>' if items else "")
        + '</section>'
    )
