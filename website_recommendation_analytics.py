"""Consent-gated storefront recommendation events and private reporting."""
from collections import defaultdict
import json
import os
import re
import threading
import time
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from crm_store import Store


PREFIX = "website_recommendations/event/"
PAID_PREFIX = "website_recommendations/paid/"
PROPERTY = "_sc_reco_event"
PATH = "/api/website-recommendations/events"
RANK_PATH = "/api/website-recommendations/ranking"
PLACEMENTS = {"desktop_menu", "mobile_featured", "mobile_lifestyle", "mobile_collector", "product_bundle"}
EVENTS = {"view", "click", "add_to_cart"}
FIELDS = {"event_id", "session_id", "event", "placement", "market", "product_ids"}
_WINDOW_SECONDS = 60
_MAX_BATCHES = 1200
_MAX_SESSION_BATCHES = 60
_LOCK = threading.Lock()
_window = 0
_seen = defaultdict(int)
_total = 0
_RANK_LOCK = threading.Lock()
_rank_cache = (0, None)


def clean_event(payload):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError("Invalid event fields")
    event_id, session_id = (str(UUID(payload[key])) for key in ("event_id", "session_id"))
    event = payload["event"]
    placement = payload["placement"]
    market = payload["market"]
    products = payload["product_ids"]
    if event not in EVENTS or placement not in PLACEMENTS:
        raise ValueError("Invalid event or placement")
    if (event == "add_to_cart" and placement != "product_bundle"
            or event == "click" and placement == "mobile_collector"):
        raise ValueError("Invalid action for this placement")
    if not isinstance(market, str) or not re.fullmatch(r"[A-Z]{2}", market):
        raise ValueError("Invalid market")
    if (not isinstance(products, list) or not 1 <= len(products) <= 4
            or any(not isinstance(item, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", item) for item in products)
            or len(set(products)) != len(products)):
        raise ValueError("Invalid product IDs")
    return session_id, {
        "event_id": event_id, "event": event, "placement": placement, "market": market, "product_ids": products,
    }


def _allow_batch(session_id):
    global _window, _total
    window = int(time.monotonic()) // _WINDOW_SECONDS
    with _LOCK:
        if window != _window:
            _window = window
            _seen.clear()
            _total = 0
        if _total >= _MAX_BATCHES or _seen.get(session_id, 0) >= _MAX_SESSION_BATCHES:
            return False
        _seen[session_id] += 1
        _total += 1
        return True


def record(event, store=None):
    """The browser session ID is used only in the in-memory rate limiter."""
    return (store or Store()).q(
        """INSERT INTO crm_runtime_state(key,value) VALUES(%s,%s::jsonb)
           ON CONFLICT(key) DO NOTHING""",
        (PREFIX + event["event_id"], json.dumps(event)),
    )


def paid_facts(payload):
    """Extract only the opaque recommendation marker and verified product ID."""
    if not isinstance(payload, dict) or payload.get("test") or payload.get("cancelled_at"):
        return []
    if str(payload.get("financial_status") or "").lower() != "paid":
        return []
    facts = {}
    for line in payload.get("line_items") or ():
        if not isinstance(line, dict):
            continue
        product = str(line.get("product_id") or "")
        if not re.fullmatch(r"[1-9][0-9]{0,19}", product):
            continue
        try:
            if int(line.get("quantity") or 0) < 1:
                continue
        except (ValueError, TypeError):
            continue
        for prop in line.get("properties") or ():
            if not isinstance(prop, dict) or prop.get("name") != PROPERTY:
                continue
            try:
                event_id = str(UUID(prop.get("value")))
            except (ValueError, TypeError, AttributeError):
                continue
            key = f"{PAID_PREFIX}{event_id}/{product}"
            facts[key] = {"key": key, "event_id": event_id, "product_id": product}
            break
    return list(facts.values())


def record_paid_order(payload, store=None):
    """Called after Shopify HMAC verification. No order/customer ID is copied."""
    facts = paid_facts(payload)
    if facts:
        (store or Store()).q(
            """INSERT INTO crm_runtime_state(key,value)
               SELECT item->>'key', item - 'key' FROM jsonb_array_elements(%s::jsonb) AS facts(item)
               ON CONFLICT(key) DO NOTHING""",
            (json.dumps(facts),),
        )


_RECENT = """WITH recent AS (
    SELECT value, updated_at FROM crm_runtime_state
    WHERE starts_with(key,%s) AND updated_at > now() - interval '30 days'
), confirmed AS (
    SELECT value->>'event_id' AS event_id, value->>'market' AS market,
           value->>'placement' AS placement, updated_at, product.id AS product_id
    FROM recent
    CROSS JOIN LATERAL jsonb_array_elements_text(value->'product_ids') AS product(id)
    WHERE value->>'event'='add_to_cart' AND value->>'placement'='product_bundle'
), outcome AS (
    SELECT c.*, p.key IS NOT NULL AS purchased
    FROM confirmed c
    LEFT JOIN crm_runtime_state p
      ON p.key = %s || c.event_id || '/' || c.product_id
     AND p.updated_at BETWEEN c.updated_at - interval '10 minutes' AND c.updated_at + interval '14 days'
)"""


def report(store=None):
    """Count attributed products, with one paid conversion per confirmed add-on."""
    return (store or Store()).q(
        _RECENT + """, metrics AS (
               SELECT value->>'market' AS market, value->>'placement' AS placement,
                      value->>'event' AS event, jsonb_array_length(value->'product_ids') AS products
               FROM recent
               UNION ALL
               SELECT market, placement, 'purchase', 1 FROM outcome WHERE purchased
           )
           SELECT market, placement,
                  coalesce(sum(products) FILTER (WHERE event='view'),0) AS views,
                  coalesce(sum(products) FILTER (WHERE event='click'),0) AS clicks,
                  coalesce(sum(products) FILTER (WHERE event='add_to_cart'),0) AS cart_adds,
                  coalesce(sum(products) FILTER (WHERE event='purchase'),0) AS purchases
           FROM metrics GROUP BY 1,2 ORDER BY 1,2""",
        (PREFIX, PAID_PREFIX),
    )


def ranking_scores(store=None):
    rows = (store or Store()).q(
        _RECENT + """, scores AS (
           SELECT market, product_id, count(*) AS adds, count(*) FILTER (WHERE purchased) AS paid
           FROM outcome GROUP BY 1,2 HAVING count(*) >= 8 AND count(*) FILTER (WHERE purchased) >= 2
        ), ranked AS (
           SELECT market, product_id, least(6, greatest(1, round(8.0*paid/(adds+6))))::int AS score,
                  row_number() OVER (PARTITION BY market ORDER BY 8.0*paid/(adds+6) DESC, paid DESC, product_id) AS position
           FROM scores
        )
        SELECT market, product_id, score FROM ranked WHERE position <= 50""",
        (PREFIX, PAID_PREFIX),
    )
    markets = defaultdict(dict)
    for row in rows:
        markets[row["market"]][row["product_id"]] = row["score"]
    return dict(markets)


def _ranking_snapshot():
    global _rank_cache
    expiry, cached = _rank_cache
    if time.monotonic() < expiry:
        return cached
    if not _RANK_LOCK.acquire(blocking=False):
        return cached
    try:
        expiry, cached = _rank_cache
        if time.monotonic() >= expiry:
            try:
                cached = ranking_scores()
            except Exception:
                if cached is None:
                    raise
                _rank_cache = (time.monotonic() + 30, cached)
            else:
                _rank_cache = (time.monotonic() + 300, cached)
        return cached
    finally:
        _RANK_LOCK.release()


def _allowed_origins():
    return {
        item.strip() for item in os.getenv(
            "WEBSITE_RECOMMENDATION_ALLOWED_ORIGINS", "https://www.sportscaveshop.com,https://sportscaveshop.com",
        ).split(",")
    } - {""}


async def ranking(request):
    origin = request.headers.get("origin", "")
    headers = {"Vary": "Origin", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
    if origin and origin not in _allowed_origins():
        return Response(status_code=403, headers=headers)
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
    market = request.query_params.get("market", "")
    if not re.fullmatch(r"[A-Z]{2}", market):
        return Response(status_code=400, headers=headers)
    # The immutable snapshot is replaced atomically by the refresh worker.
    # Serve cache hits on the event loop so storefront traffic uses no DB workers.
    expiry, snapshot = _rank_cache
    if time.monotonic() >= expiry:
        try:
            snapshot = await run_in_threadpool(_ranking_snapshot)
        except Exception:
            snapshot = None
        expiry, _ = _rank_cache
    if snapshot is None:
        headers["Retry-After"] = "2"
        return Response(status_code=503, headers=headers)
    age = max(0, int(expiry - time.monotonic()))
    headers["Cache-Control"] = f"public, max-age={age}"
    return JSONResponse({"scores": snapshot.get(market, {})}, headers=headers)


async def ingest(request):
    allowed = _allowed_origins()
    origin = request.headers.get("origin", "")
    headers = {"Vary": "Origin", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if origin not in allowed:
        return Response(status_code=403, headers=headers)
    headers.update({
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    })
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=headers)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2048:
            return Response(status_code=413, headers=headers)
        body.extend(chunk)
    try:
        session_id, event = clean_event(json.loads(body))
    except (ValueError, TypeError, AttributeError):
        return Response(status_code=400, headers=headers)
    if not _allow_batch(session_id):
        return Response(status_code=429, headers=headers)
    try:
        await run_in_threadpool(record, event)
    except Exception:
        return Response(status_code=503, headers=headers)
    return Response(status_code=204, headers=headers)


ROUTES = ((PATH, ingest, ("POST", "OPTIONS")), (RANK_PATH, ranking, ("GET",)))
