"""Publish one dated Sports Updates brief to the owner’s OS Home."""

from datetime import date, timedelta
import json
import logging
import re
import unicodedata
from urllib.parse import urlsplit

import os_accounts
from home_brief_calendar import HISTORY_PREFIX, article_fields, shop_product_handle
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
        if not isinstance(item, dict) or set(item) - {"title", "recommendation", "links", "sport", "markets", "primary_market", "start_date", "end_date", "product_url", "subject", "sales_rationale", "opportunity_status"}:
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
        for field, limit in (("subject", 160), ("sales_rationale", 1200), ("opportunity_status", 40)):
            if field in item:
                article[field] = _text(item[field], limit, field)
        recommendations.append(article)
    return recommendations


def _legends(items):
    if not isinstance(items, list) or len(items) > 6:
        raise ValueError("Include up to six ranked Legends Brief entries.")
    articles = _recommendations(items)
    if any(not raw.get("links") or not article["sport"] or not article["markets"]
           for raw, article in zip(items, articles)):
        raise ValueError("Each legend needs a source link, sport and market.")
    return articles


def subject_key(item):
    subject = item.get("subject") or re.split(r"\s+[—–-]\s+", item["title"])[0]
    return " ".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", subject).encode("ascii", "ignore").decode().casefold()))


def design_sections(edition):
    return ("design_recommendations",) if "design_recommendations" in edition else ("recommendations", "legends")


def validate_fresh_designs(edition, cursor):
    if "design_recommendations" not in edition:
        return
    day = date.fromisoformat(edition["date"])
    cursor.execute("""SELECT value FROM app_settings WHERE (starts_with(key, %s) OR key='home_sports_morning_brief')
                      AND value->>'date' >= %s AND value->>'date' < %s""",
                   (HISTORY_PREFIX, (day - timedelta(days=7)).isoformat(), day.isoformat()))
    previous = [row["value"] for row in cursor.fetchall()]
    excluded = {subject_key(item) for old in previous for section in design_sections(old)
                for item in old.get(section, [])}
    for item in edition["design_recommendations"]:
        key = subject_key(item)
        if key in excluded:
            raise ValueError(f"Design subject already recommended in the last seven days: {item['subject']}")
        excluded.add(key)


def parse_edition(raw, today):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError("The brief is too long.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Enter valid Morning Brief JSON.") from None
    if not isinstance(data, dict) or not {"date", "recommendations"} <= set(data) <= {"date", "recommendations", "full_brief", "legends", "summary", "design_recommendations", "rivalries"}:
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
    if "summary" in data:
        edition["summary"] = _text(data["summary"], 1800, "Daily summary")
    if "design_recommendations" in data:
        if not edition.get("summary") or not edition.get("full_brief"):
            raise ValueError("Include summary and full_brief with design recommendations.")
        picks = data["design_recommendations"]
        if not isinstance(picks, list) or len(picks) > 4:
            raise ValueError("Include only the top four design recommendations.")
        edition["design_recommendations"] = _recommendations(picks)
        for item in edition["design_recommendations"]:
            if not all(item.get(field) for field in ("subject", "sport", "markets", "links", "sales_rationale")):
                raise ValueError("Each design needs subject, sport, markets, source links and sales_rationale.")
            if item.get("opportunity_status") not in {"Create now", "Research first", "Watch"}:
                raise ValueError("Use Create now, Research first or Watch for opportunity_status.")
        if len({subject_key(item) for item in edition["design_recommendations"]}) != len(picks):
            raise ValueError("Each design must have a distinct subject.")
    if "rivalries" in data:
        if not isinstance(data["rivalries"], list) or len(data["rivalries"]) > 3:
            raise ValueError("Include up to three verified current rivalries.")
        edition["rivalries"] = _recommendations(data["rivalries"])
        if any(not item["links"] or not item["sport"] or not item["markets"] for item in edition["rivalries"]):
            raise ValueError("Each rivalry needs sources, sport and markets.")
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
            # Serialize daily editions so concurrent publishers cannot bypass history checks.
            cursor.execute("SELECT pg_advisory_xact_lock(73190421)")
            validate_fresh_designs(edition, cursor)
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
