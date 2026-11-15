import json
import logging
import os
import uuid
from urllib.parse import quote

import requests
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

import collector_vault
from services import r2_storage


MAX_JSON_BODY_BYTES = 9 * 1024 * 1024
REQUEST_MARKER = "customer-account-extension"
LOGGER = logging.getLogger(__name__)


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Sports-Cave-Request",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Expose-Headers": (
            "X-Sports-Cave-Error-Code, X-Sports-Cave-Request-Id, "
            "X-Sports-Cave-Revision"
        ),
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }


def _json(payload, status_code=200, *, request_id="", error_code=""):
    headers = _cors_headers()
    headers["Cache-Control"] = "no-store"
    if request_id:
        headers["X-Sports-Cave-Request-Id"] = request_id
    if error_code:
        headers["X-Sports-Cave-Error-Code"] = error_code
    revision = str(
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT")
        or ""
    ).strip()
    if revision:
        headers["X-Sports-Cave-Revision"] = revision[:12]
    return JSONResponse(payload, status_code=status_code, headers=headers)


def _request_id():
    return uuid.uuid4().hex[:16]


def _error_response(error, operation, *, request_id=""):
    request_id = request_id or _request_id()
    status_code = getattr(error, "status_code", 500)
    error_code = str(
        getattr(error, "error_code", "")
        or "internal_server_error"
    )
    LOGGER.error(
        (
            "Collector Vault request failed operation=%s error_type=%s "
            "status=%s error_code=%s request_id=%s"
        ),
        operation,
        type(error).__name__,
        status_code,
        error_code,
        request_id,
        exc_info=status_code >= 500,
    )
    if isinstance(error, collector_vault.CollectorVaultError):
        public_message = error.public_message
        if error.status_code >= 500:
            public_message = f"{public_message} Reference {request_id}."
        return _json(
            {
                "ok": False,
                "error": public_message,
                "error_code": error_code,
                "request_id": request_id,
            },
            status_code=error.status_code,
            request_id=request_id,
            error_code=error_code,
        )
    return _json(
        {
            "ok": False,
            "error": (
                "The Collector Vault is temporarily unavailable. "
                f"Reference {request_id}."
            ),
            "error_code": error_code,
            "request_id": request_id,
        },
        status_code=500,
        request_id=request_id,
        error_code=error_code,
    )


async def _json_body(request):
    raw = await request.body()
    if len(raw) > MAX_JSON_BODY_BYTES:
        raise collector_vault.CollectorVaultError("Request is too large.")
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise collector_vault.CollectorVaultError("Request body must be valid JSON.") from error


def _session(request):
    authorization = str(request.headers.get("Authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        raise collector_vault.CollectorVaultAuthenticationError("Shopify session token is missing.")
    return collector_vault.verify_shopify_session_token(authorization.split(" ", 1)[1].strip())


def _require_post_marker(request):
    if str(request.headers.get("X-Sports-Cave-Request") or "") != REQUEST_MARKER:
        raise collector_vault.CollectorVaultAuthorizationError("Request marker is missing.")


async def collector_vault_options(_request):
    return Response(status_code=204, headers=_cors_headers())


async def collector_vault_bootstrap(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    request_id = _request_id()
    try:
        session = _session(request)
        payload = collector_vault.build_vault_payload(session["shopify_customer_id"])
        certificate_count = len(payload.get("certificates") or [])
        LOGGER.info(
            "Collector Vault bootstrap completed status=200 certificate_count=%s request_id=%s",
            certificate_count,
            request_id,
        )
        return _json(
            {"ok": True, **payload},
            request_id=request_id,
        )
    except Exception as error:
        return _error_response(error, "bootstrap", request_id=request_id)


async def collector_vault_event(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        _require_post_marker(request)
        session = _session(request)
        body = await _json_body(request)
        event_name = str(body.get("event") or "")
        if event_name not in collector_vault.COLLECTOR_EVENTS:
            raise collector_vault.CollectorVaultError("Event type is invalid.")
        collector_vault.record_event(
            event_name,
            session["shopify_customer_id"],
            event_key=str(body.get("event_key") or "")[:200],
        )
        return _json({"ok": True})
    except Exception as error:
        return _error_response(error, "event")


async def collector_vault_frame_request(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        _require_post_marker(request)
        session = _session(request)
        body = await _json_body(request)
        result = collector_vault.create_frame_request(
            session["shopify_customer_id"],
            certificate_reference=body.get("certificate_reference"),
            frame_variant_id=body.get("frame_variant_id"),
            idempotency_key=body.get("idempotency_key"),
            allow_repeat=bool(body.get("allow_repeat")),
        )
        return _json({"ok": True, **result})
    except Exception as error:
        return _error_response(error, "frame_request")


async def collector_vault_frame_cart_created(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        _require_post_marker(request)
        session = _session(request)
        body = await _json_body(request)
        result = collector_vault.mark_frame_cart_created(
            session["shopify_customer_id"],
            request_reference=body.get("request_reference"),
            cart_id=body.get("cart_id"),
            checkout_url=body.get("checkout_url"),
        )
        return _json({"ok": True, **result})
    except Exception as error:
        return _error_response(error, "frame_cart_created")


async def collector_vault_review_submit(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        _require_post_marker(request)
        session = _session(request)
        body = await _json_body(request)
        result = collector_vault.submit_review(
            session["shopify_customer_id"],
            review_reference=body.get("review_reference"),
            rating=body.get("rating"),
            title=body.get("title"),
            body=body.get("body"),
            photo=body.get("photo"),
        )
        return _json({"ok": True, **result})
    except Exception as error:
        return _error_response(error, "review_submit")


def _content_disposition(asset):
    kind = asset.get("kind")
    disposition = "inline" if kind == "preview" else "attachment"
    filename = (
        str(asset.get("filename") or "certificate")
        .replace('"', "")
        .replace("\r", "")
        .replace("\n", "")
    )
    fallback = filename.encode("ascii", "ignore").decode("ascii").strip() or "certificate"
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def _stream_chunks(response):
    try:
        yield from response.iter_content(chunk_size=64 * 1024)
    finally:
        response.close()


async def collector_vault_asset(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        asset = collector_vault.resolve_asset_token(request.query_params.get("token"))
        headers = {
            **_cors_headers(),
            "Cache-Control": "private, max-age=300" if asset.get("kind") == "preview" else "no-store",
            "Content-Disposition": _content_disposition(asset),
            "X-Content-Type-Options": "nosniff",
        }
        if asset.get("storage") == "r2":
            source_url = r2_storage.generate_presigned_download_url(
                asset.get("bucket"),
                asset.get("key"),
                expires_seconds=300,
            )
        else:
            source_url = asset.get("url")
        if not source_url:
            raise collector_vault.CollectorVaultNotFoundError("Certificate asset is unavailable.")
        upstream = requests.get(source_url, stream=True, timeout=(8, 60))
        upstream.raise_for_status()
        content_length = upstream.headers.get("Content-Length")
        if content_length:
            headers["Content-Length"] = content_length
        return StreamingResponse(
            _stream_chunks(upstream),
            media_type=asset.get("mime_type") or upstream.headers.get("Content-Type") or "application/octet-stream",
            headers=headers,
        )
    except Exception as error:
        return _error_response(error, "asset")


COLLECTOR_VAULT_ROUTES = (
    ("/api/collector-vault/bootstrap", collector_vault_bootstrap, ("GET", "OPTIONS")),
    ("/api/collector-vault/events", collector_vault_event, ("POST", "OPTIONS")),
    ("/api/collector-vault/frame/request", collector_vault_frame_request, ("POST", "OPTIONS")),
    (
        "/api/collector-vault/frame/cart-created",
        collector_vault_frame_cart_created,
        ("POST", "OPTIONS"),
    ),
    ("/api/collector-vault/review", collector_vault_review_submit, ("POST", "OPTIONS")),
    ("/api/collector-vault/asset", collector_vault_asset, ("GET", "OPTIONS")),
)
