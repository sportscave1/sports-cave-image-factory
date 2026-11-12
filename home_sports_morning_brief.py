"""Publish one dated Sports Updates brief to the owner’s OS Home."""

from datetime import date
import json
import logging
import re
from urllib.parse import urlsplit

import os_accounts
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting

SETTING_KEY = "home_sports_morning_brief"
MAX_PAYLOAD = 24000
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


def parse_edition(raw, today):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError("The brief is too long.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("Paste a brief in the JSON format shown below.") from None
    if not isinstance(data, dict) or set(data) != {"date", "recommendations"}:
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
    recommendations = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {"title", "recommendation", "links"}:
            raise ValueError("Each item needs a title and recommendation, with optional links.")
        links = item.get("links", [])
        if not isinstance(links, list) or len(links) > 5:
            raise ValueError("Include up to five links per recommendation.")
        recommendations.append({
            "title": _text(item.get("title"), 160, "Title"),
            "recommendation": _text(item.get("recommendation"), 2600, "Recommendation"),
            "links": [_link(link) for link in links],
        })
    edition = {"date": day.isoformat(), "recommendations": recommendations}
    if len(_edition_json(edition)) > MAX_PAYLOAD:
        raise ValueError("The brief is too long.")
    return edition


def _edition_json(edition):
    return json.dumps(edition, ensure_ascii=False, separators=(",", ":"))


def publish(raw, user):
    if not os_accounts.is_reporting_owner(user):
        raise PermissionError("Only the Sports Cave OS owner can publish the Morning Brief.")
    edition = parse_edition(raw, sydney_date())
    with connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (%s, %s::jsonb, now())
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
                WHERE (app_settings.value->>'date') <= (EXCLUDED.value->>'date')
                RETURNING key
                """,
                (SETTING_KEY, _edition_json(edition)),
            )
            if cursor.fetchone() is None:
                raise ValueError("A newer Morning Brief is already published.")
    return edition


def _plain(value):
    return re.sub(r"([\\\x60*_{}\[\]()<>#+.!|~$-])", r"\\\1", value)


def render(st, user, today):
    if not os_accounts.is_reporting_owner(user):
        return
    st.subheader("Sports Updates — Morning Brief")
    with st.expander("Publish Morning Brief"):
        with st.form("sports-morning-brief-publish", clear_on_submit=False):
            raw = st.text_area("Morning Brief JSON", max_chars=MAX_PAYLOAD, height=160)
            st.caption(
                'Use {"date":"YYYY-MM-DD","recommendations":'
                '[{"title":"Story","recommendation":"What to do and when",'
                '"links":[{"label":"Source","url":"https://example.com"}]}]}.'
            )
            submitted = st.form_submit_button("Publish brief")
    if submitted:
        try:
            edition = publish(raw, user)
        except ValueError as error:
            st.error(str(error))
        except Exception as error:
            LOG.warning("home_morning_brief_publish_failed type=%s", type(error).__name__)
            st.error("The Morning Brief could not be published. Try again.")
        else:
            st.success(f"Published the {edition['date']} Morning Brief.")
    try:
        saved = get_app_setting(SETTING_KEY, ensure_schema_first=False)
        edition = parse_edition(_edition_json(saved), today) if saved else None
    except Exception as error:
        LOG.warning("home_morning_brief_unavailable type=%s", type(error).__name__)
        st.warning("The Morning Brief is temporarily unavailable.")
        return
    if edition is None:
        st.caption("No Morning Brief has been published yet.")
        return
    day = date.fromisoformat(edition["date"])
    label = day.strftime("%d %B %Y").lstrip("0")
    if day == today:
        st.caption(f"{label} · Sydney")
    else:
        st.caption(f"Latest published brief · {label} Sydney. Today's brief is pending.")
    for rank, item in enumerate(edition["recommendations"], 1):
        title = _plain(" ".join(item["title"].split()))
        with st.expander(f"{rank}. {title}", expanded=rank == 1):
            st.markdown("  \n".join(_plain(line) for line in item["recommendation"].splitlines()))
            for index, link in enumerate(item["links"], 1):
                st.link_button(_plain(link["label"]), link["url"], key=f"morning-brief-{rank}-link-{index}")
