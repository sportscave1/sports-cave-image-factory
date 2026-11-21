"""Receive completed cloud brief editions and publish them from the hosted worker."""

import json
import logging
import os
import signal
import threading
import hashlib
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import home_seo_report as seo_report
import home_design_refresh as refresh
import home_meta_morning_brief as meta
import home_sports_morning_brief as sports
import os_accounts
import google_ads_reviews
from sports_sales_calendar import sydney_date
from supabase_backend import connect, get_app_setting

LOG = logging.getLogger(__name__)
PREFIX = "hosted_daily_brief:"
MAX_ATTEMPTS = 30
BRIEFS = {
    "seo": (seo_report.parse, seo_report.publish, seo_report.MAX_PAYLOAD),
    "sports": (sports.parse_edition, sports.publish, sports.MAX_PAYLOAD),
    "meta": (meta.parse_edition, meta.publish, meta.MAX_PAYLOAD),
    "design_refresh": (refresh.parse, refresh.publish, refresh.MAX_PAYLOAD),
}
LATEST_KEYS = {"seo": seo_report.KEY, "sports": sports.SETTING_KEY, "meta": meta.SETTING_KEY,
               "design_refresh": refresh.KEY}


def contract_upgrade(kind, previous, incoming):
    if kind == 'meta' and incoming.get('ad_format_version') == 3 and previous.get('ad_format_version', 0) < 3:
        return True
    if (kind == 'meta' and incoming.get('ad_format_version') == previous.get('ad_format_version') == 3
            and not any(row.get('secondary_product') for row in previous.get('ad_recommendations', []))
            and any(row.get('secondary_product') for row in incoming.get('ad_recommendations', []))):
        return True  # One evidence-backed enrichment after an inventory outage.
    field = {"sports": "design_recommendations", "meta": "ad_recommendations"}.get(kind)
    return bool(field and field in incoming and field not in previous)


def enabled():
    return os.getenv("SPORTS_CAVE_HOSTED_BRIEFS", "").strip() == "1"


def normalize(kind, edition):
    """Only shorten presentation copy; never alter IDs, counts, dates or evidence."""
    edition = deepcopy(edition)
    if kind == "design_refresh" and isinstance(edition.get("candidates"), list):
        for row in edition["candidates"]:
            if isinstance(row, dict) and isinstance(row.get("suggestion"), str):
                text = row["suggestion"].strip()
                if len(text) > 220:
                    text = text[:217].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
                row["suggestion"] = text
    return edition


def publication(kind, today):
    """Read and validate the actual Home record, independently of the queue."""
    current = get_app_setting(LATEST_KEYS[kind], ensure_schema_first=False) or {}
    if current.get("date") != str(today):
        return None
    raw = json.dumps(current, ensure_ascii=False)
    try:
        if kind == "meta":
            parsed = meta.parse_edition(raw, today, stored=True)
            if not parsed.get("summary"):
                return None
            # These metrics are independently enriched by the Home publisher.
            parsed.pop("ga4_orders", None)
            parsed["roas"] = None
        elif kind == "seo":
            parsed = seo_report.parse(json.dumps({k: current[k] for k in ("date", "summary", "period_start", "period_end", "source_gaps", "opportunities", "next_action")}), today)
        elif kind == "design_refresh":
            parsed = refresh.parse(json.dumps({k: current[k] for k in ("date", "candidates")}), today)
        else:
            parsed = sports.parse_edition(raw, today)
            if not parsed.get("full_brief"):
                return None
        return parsed
    except (ValueError, KeyError, TypeError):
        return None


def digest(edition):
    return hashlib.sha256(json.dumps(edition, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def enqueue(kind, edition, claims):
    if kind not in BRIEFS or not isinstance(edition, dict):
        raise ValueError("Choose a brief type and supply a completed edition object.")
    edition = normalize(kind, edition)
    parse, _, limit = BRIEFS[kind]
    today = sydney_date()
    raw = json.dumps(edition, ensure_ascii=False)
    if len(raw) > limit or edition.get("date") != today.isoformat():
        raise ValueError("Send today's completed Sydney edition within the brief size limit.")
    validated = parse(raw, today)
    if kind == "seo":
        owner = os_accounts.DEFAULT_STORE.get_user(claims["sub"])
        if not os_accounts.can_access_page(owner, "seo"):
            raise PermissionError("SEO access required")
    if kind == "sports" and "design_recommendations" in validated:
        with connect() as conn, conn.cursor() as cur:
            sports.validate_fresh_designs(validated, cur)
    if kind == "meta" and "ad_recommendations" in validated:
        from home_brief_opportunities import validate_ad_products
        validate_ad_products(validated['ad_recommendations'], today, require_all=validated.get('ad_format_version') == 3)
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
        cur.execute("SELECT value FROM app_settings WHERE key=%s FOR UPDATE", (key,))
        existing = cur.fetchone()["value"]
        if existing["status"] == "completed" and contract_upgrade(kind, existing["edition"], edition):
            cur.execute("UPDATE app_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s",
                        (json.dumps(job), key))
            existing = job
        if existing["edition"] != edition:
            raise ValueError("An edition already exists for this brief and date.")
    return {"date": str(today), "brief": kind, "status": existing["status"]}


def status(kind):
    if kind not in BRIEFS:
        raise ValueError("Choose a known brief type.")
    day = sydney_date()
    today = str(day)
    job = get_app_setting(f"{PREFIX}{today}:{kind}", ensure_schema_first=False) or {}
    published = publication(kind, day)
    verified = published is not None
    state = job.get("status", "awaiting_report")
    if state == "completed" and not verified:
        state = "publication_missing"
    result = {"brief": kind, "date": today,
              "status": "completed" if verified else state,
              "attempts": job.get("attempts", 0), "verified": verified,
              "publication_date": published["date"] if verified else None,
              "stage": "published" if verified else "research_or_submission" if not job else
                       job.get("error_stage", "publication"),
              "retryable": not verified and job.get("status") in ("scheduled", "running", "retrying")}
    if verified:
        result['format_version'] = 3 if kind == 'meta' and published.get('ad_format_version') == 3 else 2 if (kind == 'sports' and 'design_recommendations' in published
                                         or kind == 'meta' and 'ad_recommendations' in published) else 1
        result["publication_sha256"] = digest(published)
        if kind == 'meta':
            result['live_sport_count'] = len(published.get('ad_recommendations', []))
            result['secondary_product_count'] = sum(bool(row.get('secondary_product')) for row in published.get('ad_recommendations', []))
        result["matches_submission"] = (published == BRIEFS[kind][0](
            json.dumps(job["edition"], ensure_ascii=False), day)) if job else None
    elif job.get("error"):
        result["error"] = job["error"]
    return result


def reconcile_morning(now=None):
    """Durable ten-minute reconciliation; cloud tasks recover missing research."""
    now = now or datetime.now(ZoneInfo("Australia/Sydney"))
    minute = now.hour * 60 + now.minute
    # Include the final slot even if a restart happens just after 06:30.
    if not 330 <= minute < 400:
        return False
    slot = minute // 10 * 10
    day = now.date()
    key = f"hosted_daily_brief_health:{day}"
    previous = get_app_setting(key, ensure_schema_first=False) or {}
    if previous.get("slot") == slot:
        return False
    states = {kind: status(kind) for kind in BRIEFS}
    for kind, state in states.items():
        if state["verified"]:
            continue
        # Restore a lost Home write only from the original accepted edition.
        # Do not retry deterministic authorization/validation failures.
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE app_settings SET
                       value=jsonb_set(value, '{status}', '\"retrying\"'::jsonb),
                       updated_at=now()-interval '2 minutes'
                   WHERE key=%s AND value->>'status'='completed'
                     AND (value->>'attempts')::integer < %s""",
                (f"{PREFIX}{day}:{kind}", MAX_ATTEMPTS),
            )
    health = {"date": str(day), "slot": slot, "checked_at": now.isoformat(),
              "briefs": states, "ready": all(s["verified"] for s in states.values()),
              "deadline_reached": slot >= 390}
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
                       ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()""",
                    (key, json.dumps(health)))
    LOG.info("daily_brief_reconciliation date=%s slot=%s ready=%s deadline=%s",
             day, slot, health["ready"], health["deadline_reached"])
    return True


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
        if current.get("date", "") > job["date"]:
            raise ValueError("newer edition already published")
        published_here = False
        if (current.get("date", "") < job["date"] or publication(job["kind"], today) is None
                or contract_upgrade(job['kind'], current, job['edition'])):
            if job["attempts"] > MAX_ATTEMPTS:
                raise ValueError("retry limit reached")
            _, publish, _ = BRIEFS[job["kind"]]
            publish(json.dumps(job["edition"], ensure_ascii=False), owner)
            published_here = True
        elif (job["kind"] == "sports" and current.get("date") == job["date"]
              and not current.get("legends") and job["edition"].get("legends")):
            # The desktop fallback may have already published today's sports copy.
            # Add the new section without replacing that edition's sports content.
            edition = sports.parse_edition(json.dumps(job["edition"], ensure_ascii=False), today)
            if edition.get("legends"):
                if job["attempts"] > MAX_ATTEMPTS:
                    raise ValueError("retry limit reached")
                sports.publish_legends(edition, today, overwrite=False)
        actual = publication(job["kind"], today)
        if actual is None:
            raise RuntimeError("Home readback did not verify publication")
        expected = BRIEFS[job["kind"]][0](json.dumps(job["edition"], ensure_ascii=False), today)
        if published_here:
            # Sports may preserve an existing, independently verified Legends section.
            compared = {k: actual.get(k) for k in expected}
            if compared != expected:
                raise ValueError("published content differs from the accepted edition")
        job["publication_sha256"] = digest(actual)
        job["verified"] = True
    except (ValueError, PermissionError) as error:
        job.update(status="failed", error=type(error).__name__,
                   error_stage="authorization" if isinstance(error, PermissionError) else "validation")
    except Exception as error:
        job.update(status="retrying" if job["attempts"] < MAX_ATTEMPTS else "failed",
                   error=type(error).__name__, error_stage="publication")
    else:
        job.update(status="completed")
        job.pop("error", None)
        job.pop("error_stage", None)
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
            reconcile_morning()
        except Exception as error:
            LOG.warning("daily_brief_reconciliation_failed type=%s", type(error).__name__)
        try:
            if google_ads_reviews.process_one():
                continue
            if process_one():
                continue
        except Exception as error:
            LOG.warning("daily_brief_poll_failed type=%s", type(error).__name__)
        stop.wait(30)


if __name__ == "__main__":
    main()
