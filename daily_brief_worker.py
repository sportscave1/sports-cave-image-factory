"""Receive completed cloud brief editions and publish them from the hosted worker."""

import json
import logging
import os
import signal
import threading

import home_design_refresh as refresh
import home_meta_morning_brief as meta
import home_sports_morning_brief as sports
import os_accounts
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting

LOG = logging.getLogger(__name__)
PREFIX = "hosted_daily_brief:"
BRIEFS = {
    "sports": (sports.parse_edition, sports.publish, sports.MAX_PAYLOAD),
    "meta": (meta.parse_edition, meta.publish, meta.MAX_PAYLOAD),
    "design_refresh": (refresh.parse, refresh.publish, refresh.MAX_PAYLOAD),
}
LATEST_KEYS = {"sports": sports.SETTING_KEY, "meta": meta.SETTING_KEY,
               "design_refresh": refresh.KEY}


def enabled():
    return os.getenv("SPORTS_CAVE_HOSTED_BRIEFS", "").strip() == "1"


def enqueue(kind, edition, claims):
    if kind not in BRIEFS or not isinstance(edition, dict):
        raise ValueError("Choose a brief type and supply a completed edition object.")
    parse, _, limit = BRIEFS[kind]
    today = sydney_date()
    raw = json.dumps(edition, ensure_ascii=False)
    if len(raw) > limit or edition.get("date") != today.isoformat():
        raise ValueError("Send today's completed Sydney edition within the brief size limit.")
    validated = parse(raw, today)
    if kind == "sports" and not validated.get("full_brief"):
        raise ValueError("Include the complete Sports Morning Brief.")
    if kind == "meta" and not validated.get("summary"):
        raise ValueError("Include the completed Meta review summary.")
    if kind == "meta" and (validated["roas"] is not None or validated["actions"]):
        raise ValueError("Use null ROAS and empty actions for hosted Meta editions.")
    key = f"{PREFIX}{today}:{kind}"
    job = {"kind": kind, "date": str(today), "edition": edition, "status": "scheduled",
           "attempts": 0, "owner": claims["sub"], "version": claims["version"]}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO app_settings(key, value, updated_at)
               VALUES (%s, %s::jsonb, now()) ON CONFLICT DO NOTHING""",
            (key, json.dumps(job)),
        )
        cur.execute("SELECT value FROM app_settings WHERE key=%s", (key,))
        existing = cur.fetchone()["value"]
        if existing["edition"] != edition:
            raise ValueError("An edition already exists for this brief and date.")
    return {"date": str(today), "brief": kind, "status": existing["status"]}


def status(kind):
    if kind not in BRIEFS:
        raise ValueError("Choose a known brief type.")
    today = str(sydney_date())
    job = get_app_setting(f"{PREFIX}{today}:{kind}", ensure_schema_first=False) or {}
    return {"brief": kind, "date": today, "status": job.get("status", "awaiting_report"),
            "attempts": job.get("attempts", 0)}


def process_one():
    today = sydney_date()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT key, value FROM app_settings
               WHERE key LIKE %s AND (
                   value->>'status' = 'scheduled' OR
                   (value->>'status' = 'retrying' AND updated_at <= now() - interval '2 minutes') OR
                   (value->>'status' = 'running' AND updated_at <= now() - interval '10 minutes')
               )
               ORDER BY updated_at, key LIMIT 1 FOR UPDATE SKIP LOCKED""",
            (PREFIX + "%",),
        )
        row = cur.fetchone()
        if row is None:
            return False
        job = row["value"]
        job["attempts"] += 1
        job["status"] = "running"
        cur.execute("UPDATE app_settings SET value=%s::jsonb, updated_at=now() WHERE key=%s",
                    (json.dumps(job), row["key"]))
    LOG.info("daily_brief_running kind=%s date=%s attempt=%s",
             job["kind"], job["date"], job["attempts"])
    try:
        if job["date"] != today.isoformat():
            raise ValueError("expired edition")
        owner = os_accounts.DEFAULT_STORE.get_user(job["owner"])
        if (not os_accounts.is_reporting_owner(owner)
                or not os_accounts.can_access_page(owner, "dashboard")
                or str(owner.get("session_version") or 1) != job["version"]):
            raise PermissionError("publisher access changed")
        if job["kind"] != "sports" and not meta.can_view(owner):
            raise PermissionError("reporting access changed")
        current = get_app_setting(LATEST_KEYS[job["kind"]], ensure_schema_first=False) or {}
        if current.get("date", "") < job["date"]:
            if job["attempts"] > 3:
                raise ValueError("retry limit reached")
            _, publish, _ = BRIEFS[job["kind"]]
            publish(json.dumps(job["edition"], ensure_ascii=False), owner)
    except (ValueError, PermissionError) as error:
        job.update(status="failed", error=type(error).__name__)
    except Exception as error:
        job.update(status="retrying" if job["attempts"] < 3 else "failed",
                   error=type(error).__name__)
    else:
        job.update(status="completed")
        job.pop("error", None)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE app_settings SET value=%s::jsonb, updated_at=now()
               WHERE key=%s AND value->>'status'='running' AND value->>'attempts'=%s""",
            (json.dumps(job), row["key"], str(job["attempts"])),
        )
    LOG.info("daily_brief_%s kind=%s date=%s", job["status"], job["kind"], job["date"])
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            if process_one():
                continue
        except Exception as error:
            LOG.warning("daily_brief_poll_failed type=%s", type(error).__name__)
        stop.wait(30)


if __name__ == "__main__":
    main()
