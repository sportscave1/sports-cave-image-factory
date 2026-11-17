"""Owner-provisioned, read-only GPT Action for aggregate CRM campaign status."""

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

PATH = "/api/chatgpt/crm/campaign-summary"
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
LOG = logging.getLogger(__name__)


def _configured_digest():
    digest = os.getenv("SPORTS_CAVE_CHATGPT_CRM_KEY_SHA256", "").strip()
    return digest if re.fullmatch(r"[0-9a-f]{64}", digest) else ""


def home_url():
    """Show the launcher only after a private GPT link and scoped key are configured."""
    if not _configured_digest():
        return ""
    url = os.getenv("SPORTS_CAVE_CHATGPT_CRM_URL", "").strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if (parts.scheme == "https" and parts.netloc == "chatgpt.com"
            and re.fullmatch(r"/g/g-[A-Za-z0-9-]+", parts.path)
            and not parts.query and not parts.fragment):
        return url
    return ""


def _read_connection():
    from supabase_backend import connect

    connection = connect()
    try:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '4000ms'")
    except Exception:
        connection.close()
        raise
    return connection


def _campaign_summary():
    from crm_campaign_store import CampaignStore

    counts = CampaignStore(_read_connection).history_counts()
    return {
        "working_campaigns": int(counts["active"]),
        "sent_campaigns": int(counts["sent"]),
        "delivery_activity_detected": bool(counts["polling_active"]),
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
    }


async def campaign_summary(request):
    digest = _configured_digest()
    if not digest:
        return JSONResponse({"error": "not_found"}, status_code=404, headers=HEADERS)

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if (scheme.lower() != "bearer" or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token)
            or not hmac.compare_digest(hashlib.sha256(token.encode("ascii")).hexdigest(), digest)):
        return JSONResponse(
            {"error": "unauthorized"}, status_code=401,
            headers={**HEADERS, "WWW-Authenticate": "Bearer"},
        )

    try:
        summary = await run_in_threadpool(_campaign_summary)
    except Exception as error:
        LOG.warning("chatgpt_crm_summary_unavailable type=%s", type(error).__name__)
        return JSONResponse({"error": "crm_summary_unavailable"}, status_code=503, headers=HEADERS)
    return JSONResponse(summary, headers=HEADERS)


ROUTES = [(PATH, campaign_summary, ["GET"])]
