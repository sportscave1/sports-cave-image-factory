"""Store and display the daily Meta review for the OS reporting owner."""

from datetime import date
from html import escape
import json

import os_accounts
from home_sports_morning_brief import LOG, _text
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting


PATH = "/ops/meta-morning-brief/publish"
SETTING_KEY = "home_meta_morning_brief"
MAX_PAYLOAD = 16000
METRICS = {
    "spend": "Spend", "impressions": "Impressions", "reach": "Reach",
    "frequency": "Frequency", "clicks": "Clicks", "link_clicks": "Link clicks",
    "ctr": "CTR", "cpc": "CPC", "cpm": "CPM", "engagement": "Engagement",
    "likes": "Likes", "add_to_cart": "Adds to cart", "checkouts": "Checkouts",
    "purchases": "Purchases", "purchase_value": "Purchase value", "roas": "ROAS",
}


def can_view(user):
    return os_accounts.can_access_reporting(user)


def parse_edition(raw, today):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError("The Meta brief is too long.")
    try:
        edition = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Enter valid Meta Morning Brief JSON.") from None
    fields = {"date", "coverage", "summary", "metrics", "recommendations"}
    if not isinstance(edition, dict) or set(edition) != fields:
        raise ValueError("Include date, coverage, summary, metrics and recommendations.")
    day = edition["date"]
    if not isinstance(day, str):
        raise ValueError("Use YYYY-MM-DD for the Sydney date.")
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise ValueError("Use YYYY-MM-DD for the Sydney date.") from None
    if parsed.isoformat() != day or parsed > today:
        raise ValueError("Use YYYY-MM-DD and a date no later than today in Sydney.")
    metrics = edition["metrics"]
    if not isinstance(metrics, dict) or metrics.keys() - METRICS.keys():
        raise ValueError("Use the supported Meta metrics.")
    recommendations = edition["recommendations"]
    if not isinstance(recommendations, list) or len(recommendations) > 5:
        raise ValueError("Include up to five recommendations.")
    return {
        "date": day,
        "coverage": _text(edition["coverage"], 600, "Coverage"),
        "summary": _text(edition["summary"], 900, "Summary"),
        "metrics": {key: None if value is None else _text(value, 60, METRICS[key])
                    for key, value in metrics.items()},
        "recommendations": [_text(item, 420, "Recommendation") for item in recommendations],
    }


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


def render(st, user, today):
    if not can_view(user):
        return
    st.subheader("Meta CRM — Morning Brief")
    try:
        saved = get_app_setting(SETTING_KEY, ensure_schema_first=False)
        edition = parse_edition(json.dumps(saved), today) if saved else None
    except Exception as error:
        LOG.warning("home_meta_morning_brief_unavailable type=%s", type(error).__name__)
        st.warning("The Meta brief is temporarily unavailable.")
        return
    if edition is None:
        st.caption("No Meta brief has been published yet.")
        return
    day = date.fromisoformat(edition["date"])
    label = day.strftime("%d %B %Y").lstrip("0")
    st.caption(f"{label} · Sydney" if day == today else f"Latest brief · {label} Sydney. Today's brief is pending.")
    metrics = edition["metrics"]
    tiles = "".join(
        f"<div><dt>{label}</dt><dd>{escape(metrics[key])}</dd></div>"
        for key, label in METRICS.items() if metrics.get(key) is not None
    )
    missing = ", ".join(label for key, label in METRICS.items() if metrics.get(key) is None)
    items = "".join(f"<li>{escape(item)}</li>" for item in edition["recommendations"])
    st.html(
        '<style>.sc-meta-brief{border:1px solid #ded6c3;border-radius:12px;padding:14px;'
        'background:rgba(176,140,61,.05);overflow-wrap:anywhere}'
        '.sc-meta-brief p,.sc-meta-brief ol{margin:0 0 .65rem}'
        '.sc-meta-brief ol{padding-left:1.3rem}.sc-meta-brief li+li{margin-top:.35rem}'
        '.sc-meta-brief dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,7.5rem),1fr));'
        'gap:6px;margin:0 0 .65rem}.sc-meta-brief dl div{border-bottom:1px solid #ded6c3;padding:.2rem}'
        '.sc-meta-brief dt,.sc-meta-brief small{font-size:.8rem}.sc-meta-brief dd{margin:0;font-weight:650}'
        '.sc-meta-brief h3{font-size:1rem;margin:.7rem 0 .35rem}</style>'
        f'<section class="sc-meta-brief"><p>{escape(edition["summary"])}</p>'
        f'<p><small>{escape(edition["coverage"])}</small></p>'
        + (f'<dl aria-label="Meta performance">{tiles}</dl>' if tiles else "")
        + (f'<details><summary>Unavailable metrics</summary><small>{missing}</small></details>' if missing else "")
        + (f'<h3>Recommendations</h3><ol>{items}</ol>' if items else "")
        + '</section>'
    )
