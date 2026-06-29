import asyncio
import base64
import hashlib
import hmac
import json
import os
from typing import Mapping

import uvicorn
from fastapi import FastAPI, Request, Response


WEBHOOK_ORDER_PAID_TIMEOUT_SECONDS = int(os.getenv("WEBHOOK_ORDER_PAID_TIMEOUT_SECONDS", "60"))
SHOPIFY_WEBHOOK_SECRET_ENV_NAMES = (
    "SHOPIFY_WEBHOOK_SECRET",
    "SHOPIFY_API_SECRET_KEY",
    "SHOPIFY_API_SECRET",
    "SHOPIFY_SHARED_SECRET",
    "SHOPIFY_CLIENT_SECRET",
)
SHOPIFY_ADMIN_TOKEN_PREFIXES = ("shpat_", "shpca_", "shppa_", "shpss_")

app = FastAPI(title="Sports Cave OS Webhooks")


def _webhook_log(event, **fields):
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if value not in (None, "")})
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def _header(headers, *names):
    if not headers:
        return ""
    for name in names:
        value = headers.get(name) if hasattr(headers, "get") else None
        if value:
            return str(value)
    try:
        lowered = {str(key).casefold(): value for key, value in headers.items()}
    except Exception:
        return ""
    for name in names:
        value = lowered.get(str(name).casefold())
        if value:
            return str(value)
    return ""


def _short_hmac(value):
    value = str(value or "").strip()
    if not value:
        return {"length": 0, "prefix": "", "suffix": ""}
    return {"length": len(value), "prefix": value[:6], "suffix": value[-4:]}


def _shopify_webhook_secret_candidates():
    candidates = []
    for env_name in SHOPIFY_WEBHOOK_SECRET_ENV_NAMES:
        secret = os.getenv(env_name, "").strip()
        if not secret:
            continue
        candidates.append(
            {
                "env_name": env_name,
                "secret": secret,
                "secret_length": len(secret),
                "looks_like_admin_token": secret.startswith(SHOPIFY_ADMIN_TOKEN_PREFIXES),
            }
        )
    return candidates


def _calculate_shopify_hmac(raw_body: bytes, secret: str):
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify_shopify_webhook_hmac(raw_body: bytes, headers: Mapping[str, str]):
    received_hmac = _header(headers, "X-Shopify-Hmac-Sha256", "X-Shopify-Hmac-SHA256").strip()
    received_short = _short_hmac(received_hmac)
    candidates = _shopify_webhook_secret_candidates()
    candidate_results = []
    matched = None

    for candidate in candidates:
        calculated = _calculate_shopify_hmac(raw_body, candidate["secret"])
        calculated_short = _short_hmac(calculated)
        is_match = bool(received_hmac) and hmac.compare_digest(received_hmac, calculated)
        safe_candidate = {
            "env_name": candidate["env_name"],
            "secret_length": candidate["secret_length"],
            "looks_like_admin_token": candidate["looks_like_admin_token"],
            "calculated_hmac_length": calculated_short["length"],
            "calculated_hmac_prefix": calculated_short["prefix"],
            "calculated_hmac_suffix": calculated_short["suffix"],
        }
        candidate_results.append(safe_candidate)
        if is_match and matched is None:
            matched = safe_candidate

    fallback_calculated = candidate_results[0] if candidate_results else {}
    return {
        "ok": bool(matched),
        "secret_env_used": (matched or {}).get("env_name") or "",
        "secret_length": (matched or {}).get("secret_length") or 0,
        "received_hmac_length": received_short["length"],
        "received_hmac_prefix": received_short["prefix"],
        "received_hmac_suffix": received_short["suffix"],
        "calculated_hmac_length": (matched or fallback_calculated).get("calculated_hmac_length", 0),
        "candidate_secret_count": len(candidates),
        "candidate_secret_env_names": [candidate["env_name"] for candidate in candidates],
        "candidate_results": candidate_results,
        "admin_token_candidate_env_names": [
            candidate["env_name"] for candidate in candidates if candidate["looks_like_admin_token"]
        ],
    }


def _safe_hmac_log_fields(hmac_result):
    return {
        "secret_env_used": hmac_result.get("secret_env_used") or "none",
        "secret_length": hmac_result.get("secret_length") or 0,
        "candidate_secret_count": hmac_result.get("candidate_secret_count") or 0,
        "candidate_secret_env_names": hmac_result.get("candidate_secret_env_names") or [],
        "received_hmac_length": hmac_result.get("received_hmac_length") or 0,
        "received_hmac_prefix": hmac_result.get("received_hmac_prefix") or "",
        "received_hmac_suffix": hmac_result.get("received_hmac_suffix") or "",
        "calculated_hmac_length": hmac_result.get("calculated_hmac_length") or 0,
        "candidate_hmac_diagnostics": hmac_result.get("candidate_results") or [],
    }


def _is_shopify_test_webhook(headers):
    return str(_header(headers, "X-Shopify-Test") or "").strip().casefold() in {"true", "1", "yes"}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "sports-cave-os-webhooks"}


@app.post("/webhooks/shopify/orders-paid")
async def shopify_orders_paid_webhook(request: Request):
    raw_body = await request.body()
    topic = _header(request.headers, "X-Shopify-Topic") or "orders/paid"
    webhook_id = (
        _header(request.headers, "X-Shopify-Webhook-Id")
        or _header(request.headers, "X-Shopify-Event-Id")
        or ""
    )
    shop_domain = _header(request.headers, "X-Shopify-Shop-Domain")
    triggered_at = _header(request.headers, "X-Shopify-Triggered-At")
    hmac_header = _header(request.headers, "X-Shopify-Hmac-Sha256", "X-Shopify-Hmac-SHA256")
    hmac_result = verify_shopify_webhook_hmac(raw_body, request.headers)
    _webhook_log(
        "shopify_orders_paid_webhook_received",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        triggered_at=triggered_at,
        raw_body_bytes=len(raw_body),
        has_hmac_header=bool(hmac_header),
        **_safe_hmac_log_fields(hmac_result),
    )
    if hmac_result.get("admin_token_candidate_env_names"):
        _webhook_log(
            "webhook_secret_candidate_warning",
            webhook_id=webhook_id,
            topic=topic,
            candidate_env_names=hmac_result.get("admin_token_candidate_env_names"),
            warning="candidate secret looks like a Shopify Admin API token",
        )

    if not hmac_result.get("ok"):
        _webhook_log(
            "webhook_hmac_failed",
            webhook_id=webhook_id,
            topic=topic,
            shop_domain=shop_domain,
            raw_body_bytes=len(raw_body),
            has_hmac_header=bool(hmac_header),
            **_safe_hmac_log_fields(hmac_result),
        )
        return Response("Invalid Shopify webhook signature.", status_code=401)

    _webhook_log(
        "webhook_hmac_verified",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        raw_body_bytes=len(raw_body),
        has_hmac_header=True,
        **_safe_hmac_log_fields(hmac_result),
    )

    if _is_shopify_test_webhook(request.headers):
        _webhook_log(
            "webhook_shopify_test_verified",
            webhook_id=webhook_id,
            topic=topic,
            shop_domain=shop_domain,
            raw_body_bytes=len(raw_body),
            secret_env_used=hmac_result.get("secret_env_used"),
        )
        return {
            "ok": True,
            "status": "shopify_test_verified",
            "source": "webhook",
            "webhook_id": webhook_id,
        }

    try:
        import shopify_sync
    except Exception as error:
        _webhook_log("webhook_order_processing_failed", webhook_id=webhook_id, error=str(error))
        return Response("Webhook processor is unavailable.", status_code=500)

    if not shopify_sync.is_orders_paid_webhook_topic(topic):
        _webhook_log("webhook_order_processing_failed", webhook_id=webhook_id, topic=topic, error="Unsupported topic")
        return Response("Unsupported Shopify webhook topic.", status_code=400)

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except ValueError:
        return Response("Invalid JSON payload.", status_code=400)

    try:
        import supabase_backend

        if not supabase_backend.is_configured():
            return Response("Supabase is not configured for webhook processing.", status_code=500)

        result = await asyncio.wait_for(
            asyncio.to_thread(
                supabase_backend.process_order_paid_webhook,
                payload,
                webhook_id,
                topic,
            ),
            timeout=WEBHOOK_ORDER_PAID_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        _webhook_log(
            "webhook_order_processing_failed",
            webhook_id=webhook_id,
            topic=topic,
            error="orders paid webhook processing timed out",
            timeout_seconds=WEBHOOK_ORDER_PAID_TIMEOUT_SECONDS,
        )
        return Response("Webhook processing timed out. Shopify can retry.", status_code=500)
    except Exception as error:
        _webhook_log("webhook_order_processing_failed", webhook_id=webhook_id, topic=topic, error=str(error))
        return Response("Webhook accepted but processing failed.", status_code=500)

    status = "duplicate" if result.get("duplicate") else ("processed" if result.get("processed") else "skipped")
    return {
        "ok": True,
        "status": status,
        "source": result.get("source") or "webhook",
        "order_name": result.get("order_name") or "",
        "shopify_order_id": result.get("shopify_order_id") or "",
        "imported_lines": result.get("imported_lines", 0),
        "skipped_existing_lines": result.get("skipped_existing_lines", 0),
        "editions_assigned": result.get("editions_assigned", 0),
        "affected_handles": result.get("affected_handles", []),
        "metafields_updated": result.get("metafields_updated", 0),
        "errors": result.get("errors", []),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8500")))
