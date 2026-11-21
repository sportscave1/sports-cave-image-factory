"""Private, append-only weekly Google workspace reports and hosted publication."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import math
import re

import os_accounts
from sports_sales_calendar import sydney_date
from supabase_backend import connect

REPORT_PREFIX = "google_ads_review:"
QUEUE_PREFIX = "google_ads_review_queue:"
MAX_PAYLOAD = 96000
MAX_ATTEMPTS = 10
CHANNELS = (
    "Google paid", "Meta paid", "Organic search", "Organic social", "Email", "Direct",
    "Google product listing unresolved", "Meta paid or organic unresolved", "Unknown", "Other referral",
)
FIELDS = {"date", "period_start", "period_end", "currency", "summary", "platforms",
          "channels", "tracking", "findings", "actions", "sources"}


def can_view(user):
    return bool(os_accounts.can_access_reporting(user)
                and os_accounts.can_access_page(user, "ads_google"))


def _text(value, maximum=2000):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or re.search(r"[<>]|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|access_token=|Bearer ", value)):
        raise ValueError("Use bounded report text without HTML, contact data or credentials.")
    return value.strip()


def _date(value):
    if not isinstance(value, str):
        raise ValueError("Use ISO dates.")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Use ISO dates.")
    return parsed


def _number(value, *, whole=False):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Metrics must be finite nonnegative numbers or null.")
    if whole and type(value) is not int:
        raise ValueError("Unique orders must be whole numbers.")
    return value


def parse(edition, *, today=None):
    today = today or sydney_date()
    if not isinstance(edition, dict) or len(json.dumps(edition)) > MAX_PAYLOAD:
        raise ValueError("Supply a bounded completed review.")
    if not FIELDS <= set(edition) <= FIELDS | {"destination", "revision"}:
        raise ValueError("Use the Google weekly review fields.")
    if edition.get("destination", "ads_google") != "ads_google":
        raise ValueError("Use the Google workspace destination.")
    result = deepcopy(edition)
    published, start, end = (_date(result[k]) for k in ("date", "period_start", "period_end"))
    if (start.weekday() != 4 or end - start != timedelta(days=6)
            or end >= published or published > today or published < today - timedelta(days=14)):
        raise ValueError("Use a completed Friday–Thursday week and a recent Sydney publication date.")
    revision = result.get("revision", 1)
    if type(revision) is not int or not 1 <= revision <= 99 or result["currency"] != "AUD":
        raise ValueError("Use AUD and a revision from 1 to 99.")
    result.update(destination="ads_google", revision=revision, summary=_text(result["summary"], 4000))
    for field, limit in (("findings", 16), ("actions", 12), ("sources", 20)):
        if not isinstance(result[field], list) or len(result[field]) > limit:
            raise ValueError("Report sections exceed their item limit.")
        result[field] = [_text(item) for item in result[field]]
    if not isinstance(result["platforms"], list) or len(result["platforms"]) > 4:
        raise ValueError("Supply up to four platform summaries.")
    seen = set()
    for row in result["platforms"]:
        required = {"source", "status", "period_start", "period_end", "currency",
                    "spend", "purchases", "value", "basis"}
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("Use the platform summary fields.")
        if row["source"] not in {"google_ads", "meta_ads", "ga4", "shopify"} or row["source"] in seen:
            raise ValueError("Use each known platform once.")
        seen.add(row["source"])
        if row["status"] not in {"verified", "partial", "unavailable"}:
            raise ValueError("Use a known source coverage status.")
        if (row["period_start"], row["period_end"], row["currency"]) != (
                result["period_start"], result["period_end"], result["currency"]):
            raise ValueError("Platform metrics must match the review dates and currency.")
        for field in ("spend", "purchases", "value"):
            _number(row[field])
            if row["status"] == "unavailable" and row[field] is not None:
                raise ValueError("Unavailable sources must use null metrics.")
        row["basis"] = _text(row["basis"])
    if not isinstance(result["channels"], list) or len(result["channels"]) > len(CHANNELS):
        raise ValueError("Supply bounded exclusive order channels.")
    seen = set()
    for row in result["channels"]:
        if (not isinstance(row, dict) or set(row) != {"channel", "orders", "value"}
                or row["channel"] not in CHANNELS or row["channel"] in seen):
            raise ValueError("Use each exclusive channel once.")
        seen.add(row["channel"])
        _number(row["orders"], whole=True)
        _number(row["value"])
    shopify = next((r for r in result["platforms"] if r["source"] == "shopify"), None)
    if (shopify and shopify["status"] == "verified" and shopify["purchases"] is not None
            and result["channels"] and all(r["orders"] is not None for r in result["channels"])
            and sum(r["orders"] for r in result["channels"]) != shopify["purchases"]):
        raise ValueError("Exclusive channel orders must reconcile to unique Shopify orders.")
    if (shopify and shopify["status"] == "verified" and shopify["value"] is not None
            and result["channels"] and all(r["value"] is not None for r in result["channels"])
            and abs(sum(Decimal(str(r["value"])) for r in result["channels"])
                    - Decimal(str(shopify["value"]))) > Decimal("0.01")):
        raise ValueError("Exclusive channel values must reconcile to Shopify order totals.")
    if not isinstance(result["tracking"], list) or len(result["tracking"]) > 16:
        raise ValueError("Supply bounded tracking checks.")
    for row in result["tracking"]:
        if (not isinstance(row, dict) or set(row) != {"label", "status", "detail", "checked_on"}
                or row["status"] not in {"live", "verified", "open", "prepared"}):
            raise ValueError("Use the tracking check fields.")
        row["label"], row["detail"] = _text(row["label"], 100), _text(row["detail"])
        if _date(row["checked_on"]) > today:
            raise ValueError("Tracking checks cannot be in the future.")
    return result


def digest(edition):
    return hashlib.sha256(json.dumps(edition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def identity(edition):
    return edition["period_end"] + ":" + str(edition["revision"]).zfill(2)


def _read(cur, key, *, lock=False):
    cur.execute("SELECT value FROM app_settings WHERE key=%s" + (" FOR UPDATE" if lock else ""), (key,))
    row = cur.fetchone()
    return row["value"] if row else None


def _write(cur, key, value):
    cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
                   ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()""",
                (key, json.dumps(value)))


def _status(cur, key, job):
    saved = _read(cur, REPORT_PREFIX + key)
    verified = bool(saved and digest(saved["edition"]) == digest(job["edition"]))
    return {"destination": "ads_google", "period_end": job["edition"]["period_end"],
            "revision": job["edition"]["revision"], "status": "completed" if verified else job["status"],
            "verified": verified, "sha256": digest(job["edition"]) if verified else None,
            "published_at": saved.get("published_at") if verified else None}


def enqueue(edition, claims):
    edition = parse(edition)
    owner = os_accounts.DEFAULT_STORE.get_user(claims["sub"])
    if (not os_accounts.is_reporting_owner(owner) or not can_view(owner)
            or str(owner.get("session_version") or 1) != claims["version"]):
        raise PermissionError("Google reporting owner access is required.")
    key = identity(edition)
    job = {"edition": edition, "owner": claims["sub"], "version": claims["version"],
           "attempts": 0, "status": "scheduled"}
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
                       ON CONFLICT DO NOTHING""", (QUEUE_PREFIX + key, json.dumps(job)))
        existing = _read(cur, QUEUE_PREFIX + key, lock=True)
        if existing["edition"] != edition:
            raise ValueError("This week and revision already exist. Use the next revision for a correction.")
        state = _status(cur, key, existing)
        if existing["status"] == "completed" and not state["verified"]:
            existing["status"] = "scheduled"
            _write(cur, QUEUE_PREFIX + key, existing)
        return _status(cur, key, existing)


def process_one():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT key,value FROM app_settings WHERE key LIKE %s
                       AND (value->>'status'='scheduled'
                         OR (value->>'status'='retrying' AND updated_at < now()-interval '2 minutes')
                         OR (value->>'status'='running' AND updated_at < now()-interval '10 minutes'))
                       ORDER BY updated_at,key LIMIT 1 FOR UPDATE SKIP LOCKED""", (QUEUE_PREFIX + "%",))
        row = cur.fetchone()
        if not row:
            return False
        job = row["value"]
        job.update(status="running", attempts=job["attempts"] + 1)
        _write(cur, row["key"], job)
    try:
        edition = parse(job["edition"])
        owner = os_accounts.DEFAULT_STORE.get_user(job["owner"])
        if (not os_accounts.is_reporting_owner(owner) or not can_view(owner)
                or str(owner.get("session_version") or 1) != job["version"]):
            raise PermissionError("Reporting access changed.")
        with connect() as conn, conn.cursor() as cur:
            if job["attempts"] > MAX_ATTEMPTS:
                raise ValueError("Publication retry limit reached.")
            saved = {"edition": edition, "published_at": datetime.now(timezone.utc).isoformat(),
                     "sha256": digest(edition)}
            key = identity(edition)
            cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
                           ON CONFLICT DO NOTHING""", (REPORT_PREFIX + key, json.dumps(saved)))
            if not _status(cur, key, job)["verified"]:
                raise ValueError("Google report readback did not match its submission.")
            job.update(status="completed")
    except (ValueError, PermissionError) as error:
        job.update(status="failed", error=type(error).__name__)
    except Exception as error:
        job.update(status="retrying" if job["attempts"] < MAX_ATTEMPTS else "failed",
                   error=type(error).__name__)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE app_settings SET value=%s::jsonb,updated_at=now()
                       WHERE key=%s AND value->>'status'='running'
                       AND (value->>'attempts')::integer=%s""",
                    (json.dumps(job), row["key"], job["attempts"]))
    return True


def history():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT value FROM app_settings WHERE key LIKE %s
                       ORDER BY key DESC LIMIT 52""", (REPORT_PREFIX + "%",))
        return [r["value"] for r in cur.fetchall()]


def report_context():
    """MCP caller permissions are checked before entering this read."""
    reviews = history()
    return {"destination": "ads_google", "reviews": reviews,
            "status": "published" if reviews else "awaiting_report"}
