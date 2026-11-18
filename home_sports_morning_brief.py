"""Publish one dated Sports Updates brief to the owner’s OS Home."""

from datetime import date
import json
import logging
import re
from urllib.parse import urlsplit

import os_accounts
from home_brief_calendar import HISTORY_PREFIX, MARKETS, article_fields, shop_product_handle
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting

SETTING_KEY = "home_sports_morning_brief"
MAX_PAYLOAD = 96000
LOG = logging.getLogger(__name__)


def _text(value, limit, field):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters.")
    value = value.strip()
    if any((ord(char) < 32 and char not in "\n\r\t") or 0xD800 <= ord(char) <= 0xDFFF
           for char in value):
        raise ValueError(f"{field} contains an unsupported character.")
    return value


def _link(item):
    if not isinstance(item, dict) or set(item) != {"label", "url"}:
        raise ValueError("Each link needs a label and URL.")
    label = _text(item["label"], 80, "Link label")
    url = _text(item["url"], 1200, "Link URL")
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname
                 and parsed.username is None and parsed.password is None
                 and not any(char.isspace() or ord(char) < 32 or char == "\\" for char in url))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Links must use HTTPS and contain no credentials.")
    return {"label": label, "url": url}


def _recommendations(items):
    recommendations = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {"title", "recommendation", "links", "sport", "markets", "primary_market", "start_date", "end_date", "product_url"}:
            raise ValueError("Each item needs a title and recommendation, with optional links.")
        links = item.get("links", [])
        if not isinstance(links, list) or len(links) > 5:
            raise ValueError("Include up to five links per recommendation.")
        article = {
            "title": _text(item.get("title"), 160, "Title"),
            "recommendation": _text(item.get("recommendation"), 10000, "Recommendation"),
            "links": [_link(link) for link in links],
        }
        if item.get("product_url"):
            recommended = _link({"label": "Recommended product", "url": item["product_url"]})
            if not shop_product_handle(recommended["url"]):
                raise ValueError("Use an exact Sports Cave product URL.")
            article["product_url"] = recommended["url"]
            if all(link["url"] != recommended["url"] for link in article["links"]):
                if len(article["links"]) == 5:
                    raise ValueError("Include the recommended product within the five links.")
                article["links"].append(recommended)
        article.update(article_fields({**item, **article}))
        recommendations.append(article)
    return recommendations


def _legends(items):
    if not isinstance(items, list) or len(items) > 6:
        raise ValueError("Include up to six ranked Legends Brief entries.")
    articles = _recommendations(items)
    if any(not raw.get("links") or not article["sport"] or not article["markets"]
           for raw, article in zip(items, articles)):
        raise ValueError("Each legend needs a source link, sport and market.")
    # Earlier editions had only a list of applicable markets and remain readable.
    if len(items) > 4 or any("primary_market" in item for item in items):
        primaries = [article.get("primary_market") for article in articles]
        if any(market not in MARKETS for market in primaries) or any(primaries.count(market) > 2 for market in MARKETS):
            raise ValueError("Assign each legend a primary market and use up to two entries per AUS, USA or UK.")
    return articles


def parse_edition(raw, today):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError("The brief is too long.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Enter valid Morning Brief JSON.") from None
    if not isinstance(data, dict) or not {"date", "recommendations"} <= set(data) <= {"date", "recommendations", "full_brief", "legends"}:
        raise ValueError("Include the Sydney date and a list of recommendations.")
    raw_day = data["date"]
    if not isinstance(raw_day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day):
        raise ValueError("Use YYYY-MM-DD for the Sydney date.")
    try:
        day = date.fromisoformat(raw_day)
    except ValueError:
        raise ValueError("Enter a valid Sydney date.") from None
    if day > today:
        raise ValueError("The brief cannot be dated after today in Sydney.")
    items = data["recommendations"]
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        raise ValueError("Include 1 to 10 recommendations.")
    recommendations = _recommendations(items)
    edition = {"date": day.isoformat(), "recommendations": recommendations}
    if "full_brief" in data:
        edition["full_brief"] = _text(data["full_brief"], 50000, "Full brief")
    if "legends" in data:
        try:
            edition["legends"] = _legends(data["legends"])
            if len(_edition_json(edition)) > MAX_PAYLOAD:
                raise ValueError("The Legends Brief exceeds the edition size limit.")
        except ValueError:
            # A problem in the optional section must not stop the Sports Updates.
            edition.pop("legends", None)
            LOG.warning("home_legends_brief_invalid date=%s", edition["date"])
    if len(_edition_json(edition)) > MAX_PAYLOAD:
        raise ValueError("The brief is too long.")
    return edition


def _edition_json(edition):
    return json.dumps(edition, ensure_ascii=False, separators=(",", ":"))


def publish(raw, user):
    if not os_accounts.is_reporting_owner(user):
        raise PermissionError("Only the Sports Cave OS owner can publish the Morning Brief.")
    today = sydney_date()
    try:
        payload = json.loads(raw) if isinstance(raw, str) and len(raw) <= MAX_PAYLOAD else None
    except (ValueError, RecursionError):
        payload = None
    if isinstance(payload, dict) and set(payload) == {"date", "legends"}:
        return publish_legends(payload, today)
    edition = parse_edition(raw, today)
    with connect() as conn:
        with conn.cursor() as cursor:
            # Preserve the pre-archive edition before replacing the latest pointer.
            cursor.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                SELECT %s || (value->>'date'), value, updated_at FROM app_settings WHERE key=%s
                ON CONFLICT (key) DO NOTHING
                """,
                (HISTORY_PREFIX, SETTING_KEY),
            )
            cursor.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (%s, %s::jsonb, now()), (%s, %s::jsonb, now())
                ON CONFLICT (key) DO UPDATE SET
                    value=CASE WHEN app_settings.value->>'date'=EXCLUDED.value->>'date'
                        AND app_settings.value ? 'legends'
                        AND COALESCE(jsonb_array_length(EXCLUDED.value->'legends'), 0)=0
                        THEN EXCLUDED.value || jsonb_build_object('legends', app_settings.value->'legends')
                        ELSE EXCLUDED.value END,
                    updated_at=now()
                WHERE app_settings.key <> %s OR
                    (app_settings.value->>'date') <= (EXCLUDED.value->>'date')
                """,
                (HISTORY_PREFIX + edition["date"], _edition_json(edition),
                 SETTING_KEY, _edition_json(edition), SETTING_KEY),
            )
    return edition


def publish_legends(payload, today, *, overwrite=True):
    """Add today's companion section without rewriting any Sports Updates."""
    day = today.isoformat()
    if payload["date"] != day:
        raise ValueError("Add Legends to today's Sydney edition.")
    legends = _legends(payload["legends"])
    if not legends:
        raise ValueError("Include at least one verified legend when adding to a published edition.")
    with connect() as conn, conn.cursor() as cursor:
        rows = []
        for key in (HISTORY_PREFIX + day, SETTING_KEY):
            cursor.execute(
                """
                UPDATE app_settings
                SET value=CASE WHEN %s OR COALESCE(jsonb_array_length(value->'legends'), 0)=0
                    THEN jsonb_set(value, '{legends}', %s::jsonb) ELSE value END
                WHERE key=%s AND value->>'date'=%s
                RETURNING value
                """,
                (overwrite, _edition_json(legends), key, day),
            )
            rows.extend(cursor.fetchall())
        if not rows:
            raise ValueError("Today's Sports Updates must be published before adding this section.")
        for row in rows:
            if not parse_edition(_edition_json(row["value"]), today).get("legends"):
                raise ValueError("The combined Morning Brief is too long.")
    return {"date": day, "legends": legends}


def archive_page(today, *, before=None, size=20):
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT value FROM app_settings
            WHERE key > %s AND key < %s AND starts_with(key, %s)
            ORDER BY key DESC LIMIT %s
            """,
            (HISTORY_PREFIX, HISTORY_PREFIX + (before or "9999-99-99"),
             HISTORY_PREFIX, size + 1),
        )
        rows = cursor.fetchall()
    editions = [parse_edition(_edition_json(row["value"]), today) for row in rows[:size]]
    return editions, editions[-1]["date"] if len(rows) > size else None


def render(st, user, today, *, snapshot=None):
    if not os_accounts.is_reporting_owner(user):
        return
    st.subheader("Sports Updates — Morning Brief")
    brief_unavailable = False
    try:
        saved = snapshot['saved'] if snapshot is not None else get_app_setting(SETTING_KEY, ensure_schema_first=False)
        edition = parse_edition(_edition_json(saved), today) if saved else None
    except Exception as error:
        LOG.warning("home_morning_brief_unavailable type=%s", type(error).__name__)
        st.warning("The Morning Brief is temporarily unavailable.")
        brief_unavailable = True
        edition = None
    editions = []
    try:
        editions = snapshot['editions'] if snapshot is not None else archive_page(today, size=20)[0]
    except Exception as error:
        LOG.warning("home_brief_archive_unavailable type=%s", type(error).__name__)
    if edition:
        editions = [edition, *(entry for entry in editions if entry["date"] != edition["date"])]
        day = date.fromisoformat(edition["date"])
        if day != today:
            st.caption("Today's brief is pending.")
    elif not brief_unavailable:
        st.caption("No Morning Brief has been published yet.")
    from home_morning_brief_actions import brief_html

    def live_brief():
        from morning_design_queue import list_jobs
        statuses = None
        try:
            statuses = snapshot['statuses'] if snapshot is not None else ({job['id']: job['label'] for job in list_jobs(edition['date'])} if edition else {})
        except Exception:
            pass
        st.html(brief_html(edition, editions=editions, today=today, design_statuses=statuses,
                          allow_ads=os_accounts.can_access_page(user, "ads")), unsafe_allow_javascript=True)
    if snapshot is not None:
        live_brief()
    else:
        st.fragment(run_every=15)(live_brief)()
