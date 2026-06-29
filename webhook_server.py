import asyncio
import base64
import hashlib
import hmac
import json
import os

import uvicorn
from fastapi import FastAPI, Request, Response


WEBHOOK_ORDER_PAID_TIMEOUT_SECONDS = int(os.getenv("WEBHOOK_ORDER_PAID_TIMEOUT_SECONDS", "60"))

app = FastAPI(title="Sports Cave OS Webhooks")


def _webhook_log(event, **fields):
    payload = {"event": event}
    payload.update({key: value for key, value in fields.items() if value not in (None, "")})
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def _header(headers, *names):
    for name in names:
        value = headers.get(name)
        if value:
            return value
    return ""


def _shopify_webhook_secret():
    webhook_secret = os.getenv("SHOPIFY_WEBHOOK_SECRET", "").strip()
    if webhook_secret:
        return webhook_secret, "SHOPIFY_WEBHOOK_SECRET"
    client_secret = os.getenv("SHOPIFY_CLIENT_SECRET", "").strip()
    if client_secret:
        return client_secret, "SHOPIFY_CLIENT_SECRET"
    return "", ""


def _calculate_shopify_hmac(raw_body: bytes, secret: str):
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _verify_shopify_hmac(raw_body: bytes, hmac_header: str, secret: str):
    if not raw_body or not hmac_header or not secret:
        return False, ""
    calculated = _calculate_shopify_hmac(raw_body, secret)
    return hmac.compare_digest(calculated, str(hmac_header or "").strip()), calculated


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
    secret, secret_env_used = _shopify_webhook_secret()
    _webhook_log(
        "shopify_orders_paid_webhook_received",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        triggered_at=triggered_at,
        raw_body_bytes=len(raw_body),
        has_hmac_header=bool(hmac_header),
        secret_env_used=secret_env_used or "missing",
        secret_length=len(secret),
        received_hmac_length=len(str(hmac_header or "").strip()),
    )
    try:
        import shopify_sync
    except Exception as error:
        _webhook_log("webhook_order_processing_failed", webhook_id=webhook_id, error=str(error))
        return Response("Webhook processor is unavailable.", status_code=500)

    hmac_ok, calculated_hmac = _verify_shopify_hmac(raw_body, hmac_header, secret)
    if not hmac_ok:
        _webhook_log(
            "webhook_hmac_failed",
            webhook_id=webhook_id,
            topic=topic,
            shop_domain=shop_domain,
            raw_body_bytes=len(raw_body),
            has_hmac_header=bool(hmac_header),
            secret_env_used=secret_env_used or "missing",
            secret_length=len(secret),
            received_hmac_length=len(str(hmac_header or "").strip()),
            calculated_hmac_length=len(calculated_hmac),
        )
        return Response("Invalid Shopify webhook signature.", status_code=401)
    _webhook_log(
        "webhook_hmac_verified",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        raw_body_bytes=len(raw_body),
        has_hmac_header=True,
        secret_env_used=secret_env_used,
        secret_length=len(secret),
        received_hmac_length=len(str(hmac_header or "").strip()),
        calculated_hmac_length=len(calculated_hmac),
    )

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
