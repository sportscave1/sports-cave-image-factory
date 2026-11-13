"""Store the read-only design worker's daily shortlist."""

from calendar import monthrange
from datetime import date, timedelta
from html import escape
import json
import re

from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting

PATH = "/ops/design-refresh/publish"
KEY = "home_design_refresh"
MAX_PAYLOAD = 8000


def recent_ids(today):
    saved = get_app_setting(KEY, ensure_schema_first=False) or {}
    earliest = (today - timedelta(days=30)).isoformat()
    return sorted(key for key, day in saved.get("recent", {}).items()
                  if earliest <= day < today.isoformat())


def parse(raw, today):
    try:
        edition = json.loads(raw)
        if set(edition) != {"date", "candidates"} or edition["date"] != today.isoformat():
            raise ValueError
        candidates = edition["candidates"]
        if not isinstance(candidates, list) or len(candidates) > 3:
            raise ValueError
        year, month = divmod(today.year * 12 + today.month - 7, 12)
        month += 1
        cutoff = date(year, month, min(today.day, monthrange(year, month)[1]))
        ids = set()
        for row in candidates:
            if set(row) != {"product_id", "handle", "title", "created", "image_updated",
                            "lifetime_orders", "sessions", "suggestion"}:
                raise ValueError
            if (not re.fullmatch(r"[0-9]{1,20}", row["product_id"]) or row["product_id"] in ids
                    or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,250}", row["handle"])
                    or type(row["lifetime_orders"]) is not int or row["lifetime_orders"] != 0
                    or type(row["sessions"]) is not int or row["sessions"] <= 0
                    or not date.fromisoformat(row["created"]) < cutoff
                    or date.fromisoformat(row["image_updated"]) > cutoff
                    or not all(isinstance(row[key], str) and 0 < len(row[key].strip()) <= limit
                               for key, limit in (("title", 160), ("suggestion", 220)))):
                raise ValueError
            ids.add(row["product_id"])
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("Enter today's verified shortlist with up to three eligible products.") from None
    return edition


def publish(raw, user):
    today = sydney_date()
    edition = parse(raw, today)
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES (%s,'{}'::jsonb,now()) ON CONFLICT DO NOTHING",
            (KEY,),
        )
        cursor.execute("SELECT value FROM app_settings WHERE key=%s FOR UPDATE", (KEY,))
        previous = cursor.fetchone()["value"]
        if previous.get("date", "") > edition["date"]:
            raise ValueError("A newer shortlist is already published.")
        earliest = (today - timedelta(days=30)).isoformat()
        recent = {key: day for key, day in previous.get("recent", {}).items() if day >= earliest}
        for row in edition["candidates"]:
            key = row["product_id"]
            if key in recent and recent[key] != edition["date"]:
                raise ValueError("A suggested product appeared in the last thirty days.")
            recent[key] = edition["date"]
        cursor.execute("UPDATE app_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s",
                       (json.dumps({**edition, "recent": recent}), KEY))
    return edition


def render_html(today):
    saved = get_app_setting(KEY, ensure_schema_first=False) or {}
    if saved.get("date") != today.isoformat():
        body = "<p>Today's shortlist is pending.</p>"
    else:
        items = "".join(
            f'<li><a href="https://www.sportscaveshop.com/products/{escape(row["handle"], quote=True)}">'
            f'<strong>{escape(row["title"])}</strong></a> · {row["sessions"]:,} GA4 landing sessions'
            f'<br>{escape(row["suggestion"])}</li>'
            for row in saved["candidates"]
        )
        body = f"<ul>{items}</ul>" if items else "<p>No eligible designs were verified today.</p>"
    return f'<details class="sc-meta-insight"><summary>Designs to Refresh</summary>{body}</details>'
