import base64
import hashlib
import hmac
import json
import os
from typing import Mapping

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request, Response


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


def _debug_webhook_security_enabled():
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_NAME"):
        return False
    return str(os.getenv("DEBUG_WEBHOOK_SECURITY") or "").strip().lower() in {"1", "true", "yes"}


def _service_version_info():
    return {
        "app_version": os.getenv("SPORTS_CAVE_APP_VERSION") or os.getenv("RENDER_GIT_COMMIT") or "local",
        "git_sha": os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "",
        "deployment_timestamp": os.getenv("RENDER_DEPLOY_CREATED_AT") or os.getenv("DEPLOYMENT_TIMESTAMP") or "",
        "service_role": os.getenv("SPORTS_CAVE_SERVICE_ROLE") or "webhook",
    }


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
                "looks_like_admin_token": secret.startswith(SHOPIFY_ADMIN_TOKEN_PREFIXES),
            }
        )
    return candidates


def _calculate_shopify_hmac(raw_body: bytes, secret: str):
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify_shopify_webhook_hmac(raw_body: bytes, headers: Mapping[str, str]):
    received_hmac = _header(headers, "X-Shopify-Hmac-Sha256", "X-Shopify-Hmac-SHA256").strip()
    candidates = _shopify_webhook_secret_candidates()
    candidate_results = []
    matched = None
    debug_security = _debug_webhook_security_enabled()

    for candidate in candidates:
        calculated = _calculate_shopify_hmac(raw_body, candidate["secret"])
        is_match = bool(received_hmac) and hmac.compare_digest(received_hmac, calculated)
        safe_candidate = {
            "env_name": candidate["env_name"],
        }
        if debug_security:
            safe_candidate["looks_like_admin_token"] = candidate["looks_like_admin_token"]
        candidate_results.append(safe_candidate)
        if is_match and matched is None:
            matched = safe_candidate

    return {
        "ok": bool(matched),
        "secret_env_used": (matched or {}).get("env_name") or "",
        "candidate_secret_env_names": [candidate["env_name"] for candidate in candidate_results] if debug_security else [],
        "candidate_results": candidate_results if debug_security else [],
        "admin_token_candidate_env_names": [
            candidate["env_name"] for candidate in candidates if candidate["looks_like_admin_token"]
        ] if debug_security else [],
    }


def _safe_hmac_log_fields(hmac_result):
    fields = {"hmac_verified": bool(hmac_result.get("ok"))}
    if hmac_result.get("secret_env_used"):
        fields["secret_env_used"] = hmac_result.get("secret_env_used")
    if _debug_webhook_security_enabled():
        fields["candidate_secret_env_names"] = hmac_result.get("candidate_secret_env_names") or []
        fields["candidate_hmac_diagnostics"] = hmac_result.get("candidate_results") or []
    return fields


def _is_shopify_test_webhook(headers):
    return str(_header(headers, "X-Shopify-Test") or "").strip().casefold() in {"true", "1", "yes"}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "sports-cave-os-webhooks", **_service_version_info()}


def _process_orders_paid_background(payload, webhook_id, topic):
    try:
        import supabase_backend

        supabase_backend.process_order_paid_webhook(
            payload,
            webhook_id,
            topic,
            claim_event=False,
        )
        try:
            import collector_vault

            collector_vault.process_framed_order_paid(payload)
        except Exception as frame_error:
            _webhook_log(
                "framed_certificate_order_update_failed",
                webhook_id=webhook_id,
                topic=topic,
                error=str(frame_error),
            )
    except Exception as error:
        _webhook_log("webhook_background_processing_failed", webhook_id=webhook_id, topic=topic, error=str(error))


@app.post("/webhooks/shopify/orders-paid")
async def shopify_orders_paid_webhook(request: Request, background_tasks: BackgroundTasks):
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
        has_hmac_header=bool(hmac_header),
        **_safe_hmac_log_fields(hmac_result),
    )
    if _debug_webhook_security_enabled() and hmac_result.get("admin_token_candidate_env_names"):
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
            has_hmac_header=bool(hmac_header),
            **_safe_hmac_log_fields(hmac_result),
        )
        return Response("Invalid Shopify webhook signature.", status_code=401)

    _webhook_log(
        "webhook_hmac_verified",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        has_hmac_header=True,
        **_safe_hmac_log_fields(hmac_result),
    )

    if _is_shopify_test_webhook(request.headers):
        _webhook_log(
            "webhook_shopify_test_verified",
            webhook_id=webhook_id,
            topic=topic,
            shop_domain=shop_domain,
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

        claim = supabase_backend.claim_order_paid_webhook_receipt(
            payload,
            webhook_id,
            topic,
            shop_domain=shop_domain,
        )
    except Exception as error:
        _webhook_log("webhook_receipt_record_failed", webhook_id=webhook_id, topic=topic, error=str(error))
        return Response("Webhook receipt could not be recorded.", status_code=500)
    if claim.get("duplicate"):
        _webhook_log("webhook_duplicate_skipped", status="completed", webhook_id=webhook_id, topic=topic)
        return {
            "ok": True,
            "status": "skipped_duplicate",
            "source": "webhook",
            "webhook_id": webhook_id,
        }
    background_tasks.add_task(_process_orders_paid_background, payload, claim.get("webhook_id") or webhook_id, topic)
    return {
        "ok": True,
        "status": "accepted",
        "source": "webhook",
        "webhook_id": claim.get("webhook_id") or webhook_id,
        "order_name": claim.get("order_name") or "",
        "shopify_order_id": claim.get("shopify_order_id") or "",
    }


async def _shopify_products_webhook(request: Request, *, default_topic: str):
    raw_body = await request.body()
    topic = _header(request.headers, "X-Shopify-Topic") or default_topic
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
        "shopify_products_create_webhook_received",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        triggered_at=triggered_at,
        has_hmac_header=bool(hmac_header),
        **_safe_hmac_log_fields(hmac_result),
    )
    if _debug_webhook_security_enabled() and hmac_result.get("admin_token_candidate_env_names"):
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
            has_hmac_header=bool(hmac_header),
            **_safe_hmac_log_fields(hmac_result),
        )
        return Response("Invalid Shopify webhook signature.", status_code=401)

    _webhook_log(
        "webhook_hmac_verified",
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain,
        has_hmac_header=True,
        **_safe_hmac_log_fields(hmac_result),
    )

    if _is_shopify_test_webhook(request.headers):
        _webhook_log(
            "webhook_shopify_test_verified",
            webhook_id=webhook_id,
            topic=topic,
            shop_domain=shop_domain,
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
        _webhook_log("webhook_product_processing_failed", webhook_id=webhook_id, error=str(error))
        return Response("Webhook processor is unavailable.", status_code=500)

    if not shopify_sync.is_products_create_webhook_topic(topic):
        _webhook_log("webhook_product_processing_failed", webhook_id=webhook_id, topic=topic, error="Unsupported topic")
        return Response("Unsupported Shopify webhook topic.", status_code=400)

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except ValueError:
        return Response("Invalid JSON payload.", status_code=400)

    try:
        import supabase_backend

        if not supabase_backend.is_configured():
            return Response("Supabase is not configured for webhook processing.", status_code=500)

        claim = supabase_backend.claim_product_create_webhook_receipt(
            payload,
            webhook_id,
            topic,
            shop_domain=shop_domain,
        )
    except Exception as error:
        _webhook_log("webhook_receipt_record_failed", webhook_id=webhook_id, topic=topic, error=str(error))
        return Response("Webhook receipt could not be recorded.", status_code=500)
    if claim.get("duplicate"):
        _webhook_log("webhook_duplicate_skipped", status="completed", webhook_id=webhook_id, topic=topic)
        return {
            "ok": True,
            "status": "skipped_duplicate",
            "source": "webhook",
            "webhook_id": webhook_id,
        }
    try:
        result = supabase_backend.process_product_create_webhook(
            payload,
            claim.get("webhook_id") or webhook_id,
            topic,
            claim_event=False,
        )
    except Exception as error:
        _webhook_log("webhook_product_processing_failed", webhook_id=webhook_id, topic=topic, error=str(error))
        return Response("Webhook product could not be processed.", status_code=500)

    return {
        "ok": True,
        "status": "processed" if not (result.get("errors") or []) else "processed_with_warnings",
        "source": "webhook",
        "webhook_id": claim.get("webhook_id") or webhook_id,
        "shopify_product_id": result.get("shopify_product_id") or claim.get("shopify_product_id") or "",
        "shopify_handle": result.get("shopify_handle") or claim.get("shopify_handle") or "",
    }


@app.post("/webhooks/shopify/products-create")
async def shopify_products_create_webhook(request: Request, background_tasks: BackgroundTasks):
    return await _shopify_products_webhook(request, default_topic="products/create")


@app.post("/webhooks/shopify/products-update")
async def shopify_products_update_webhook(request: Request, background_tasks: BackgroundTasks):
    return await _shopify_products_webhook(request, default_topic="products/update")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8500")))
