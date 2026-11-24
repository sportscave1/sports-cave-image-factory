import json
import logging
import os
import uuid
from collection_performance import observe
from fastapi.encoders import jsonable_encoder
from urllib.parse import quote

import requests
from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, JSONResponse, Response, StreamingResponse

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
            "X-Sports-Cave-Revision, Server-Timing"
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
    return JSONResponse(jsonable_encoder(payload), status_code=status_code, headers=headers)


def _request_id():
    return uuid.uuid4().hex[:16]


def _error_response(error, operation, *, request_id=""):
    request_id = request_id or _request_id()
    status_code = getattr(error, "status_code", 500)
    error_code = str(
        getattr(error, "error_code", "")
        or "internal_server_error"
    )
    if isinstance(error, collector_vault.CollectorVaultAuthenticationError):
        # These verifier messages are fixed strings: no tokens, claims, secrets,
        # or customer identifiers. Keep the public response generic.
        LOGGER.warning("Collector Vault authentication rejected reason=%s request_id=%s", str(error), request_id)
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
        if request.query_params.get("include_review") == "false":
            payload = await run_in_threadpool(
                collector_vault.build_vault_payload,
                session["shopify_customer_id"], include_review=False,
            )
        else:
            payload = await run_in_threadpool(
                collector_vault.build_vault_payload, session["shopify_customer_id"],
            )
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


async def collector_vault_review_prompt(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        session = _session(request)
        payload = await run_in_threadpool(
            collector_vault.build_review_prompt_payload, session["shopify_customer_id"],
        )
        return _json({"ok": True, **payload})
    except Exception as error:
        return _error_response(error, "review_prompt")


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
            country=body.get("country"),
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


from reviews_http import bounded_upload

@bounded_upload
async def collector_vault_review_submit(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        _require_post_marker(request)
        session = _session(request)
        from reviews_http import read_submission
        if request.headers.get('content-type','').startswith('multipart/form-data'):
            body,uploads=await read_submission(request)
        else:
            body=await _json_body(request)
            photo=collector_vault.validate_review_photo(body.get('photo'))
            uploads=[{'kind':'image','data':photo['bytes']}] if photo else []
        from reviews_account import submit
        from reviews_store import ReviewsStore
        from crm_shopify import Shopify
        result=await run_in_threadpool(submit,ReviewsStore(),Shopify(),session['shopify_customer_id'],body.get('review_reference'),
            {k:body.get(k,'') for k in ('rating','title','reviewer_name','body')},uploads)
        return _json({"ok": True, **result})
    except ValueError:
        return _error_response(collector_vault.CollectorVaultError("Check your review fields and attached files."),"review_submit")
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


async def _framed_preview_response(asset, frame, width):
    from collector_preview_cache import PREVIEWS, PreviewBusyError, PreviewSourceError
    def source_url():
        url = (r2_storage.generate_presigned_download_url(asset.get("bucket"), asset.get("key"), expires_seconds=300)
               if asset.get("storage") == "r2" else asset.get("url"))
        if not url:
            raise collector_vault.CollectorVaultNotFoundError("Certificate asset is unavailable.")
        return url
    try:
        image = await run_in_threadpool(PREVIEWS.framed, asset, frame, width, source_url)
    except (PreviewBusyError, PreviewSourceError, TimeoutError):
        raise collector_vault.CollectorVaultUnavailableError("Certificate preview is temporarily unavailable.") from None
    return Response(image, media_type="image/webp", headers={
        **_cors_headers(), "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    })


async def collector_vault_cart_preview(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        frame = request.query_params.get("frame")
        if frame not in ("black", "oak", "white"):
            raise collector_vault.CollectorVaultError("Invalid certificate frame preview.")
        asset = await run_in_threadpool(collector_vault.resolve_cart_preview,
            request.query_params.get("reference"), request.query_params.get("variant_id"))
        # Fixed thumbnail output. This route cannot return a print/PDF or a source URL.
        return await _framed_preview_response(asset, frame, 400)
    except Exception as error:
        return _error_response(error, "cart_preview")


async def collector_vault_asset(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        asset = await run_in_threadpool(collector_vault.resolve_asset_token, request.query_params.get("token"))
        frame = request.query_params.get("frame")
        if frame and (frame not in ("black", "oak", "white") or asset.get("kind") != "preview"):
            raise collector_vault.CollectorVaultError("Invalid certificate frame preview.")
        width_value = request.query_params.get("w", "1000")
        if width_value not in ("400", "1000") or ("w" in request.query_params and not frame):
            raise collector_vault.CollectorVaultError("Invalid certificate preview size.")
        if frame:
            return await _framed_preview_response(asset, frame, int(width_value))
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
        upstream = await run_in_threadpool(requests.get, source_url, stream=True, timeout=(8, 60))
        upstream.raise_for_status()
        if asset.get("kind") == "print" and asset.get("render_print"):
            from collector_certificate_print import MAX_SOURCE_BYTES, render_print_jpg
            def read_original():
                content = bytearray()
                try:
                    for chunk in upstream.iter_content(chunk_size=64 * 1024):
                        content.extend(chunk)
                        if len(content) > MAX_SOURCE_BYTES:
                            raise collector_vault.CollectorVaultError("Certificate source is too large.")
                finally:
                    upstream.close()
                return bytes(content)
            content = await run_in_threadpool(read_original)
            image = await run_in_threadpool(render_print_jpg, content)
            return Response(image, media_type="image/jpeg", headers=headers)
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


async def collector_vault_recommendations(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        session = _session(request)
        from collector_collection_offers import recommendations
        from starlette.concurrency import run_in_threadpool
        products = await run_in_threadpool(recommendations, session["shopify_customer_id"],
            country=request.query_params.get("country"), seed_product_id=request.query_params.get("product_id"))
        if request.query_params.get("fields") == "ids":
            products = [{"id": product["id"]} for product in products[:8]]
        return _json({"ok": True, "products": products})
    except Exception as error:
        return _error_response(error, "recommendations")


async def collector_vault_cart_launch(request: Request):
    """Apply Shopify's account return country before the existing cart/drawer bridge."""
    try:
        token=str(request.query_params.get("sc_certificate_cart") or "")
        payload=collector_vault._verify_signed_token(token, expected_purpose="frame_cart")
        country=str(payload.get("country") or "AU")
        if not collector_vault.re.fullmatch(r"[A-Z]{2}",country):
            raise collector_vault.CollectorVaultError("Invalid cart country.")
        # Match Shopify's customer-account return link. A cross-site localization
        # POST can retain the browser's previous market; country on the top-level
        # storefront GET applies the market before the existing cart bridge runs.
        destination=("https://www.sportscaveshop.com/?country=" + country
                     + "&sc_certificate_cart=" + quote(token, safe=""))
        return RedirectResponse(destination, status_code=303, headers={
            "Cache-Control":"no-store", "Referrer-Policy":"no-referrer"})
    except Exception as error:
        return _error_response(error,"cart_launch")


async def collector_vault_cart_handoff(request: Request):
    if request.method == "OPTIONS":
        return await collector_vault_options(request)
    try:
        body = await _json_body(request)
        return _json({"ok": True, **collector_vault.frame_cart_handoff(body.get("token"))})
    except Exception as error:
        return _error_response(error, "cart_handoff")


async def collector_vault_performance(request: Request):
    if request.method == 'OPTIONS':
        return await collector_vault_options(request)
    try:
        _require_post_marker(request)
        _session(request)
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > 4096:
                raise collector_vault.CollectorVaultError('Performance report is too large.')
            content.extend(chunk)
        from collection_performance import validate_samples, LOGGER as PERFORMANCE_LOGGER
        try:
            samples = validate_samples(json.loads(content))
        except (ValueError, TypeError, KeyError):
            raise collector_vault.CollectorVaultError('Invalid performance report.') from None
        for operation, duration, outcome in samples:
            PERFORMANCE_LOGGER.info('collection_perf source=client operation=%s outcome=%s duration_ms=%d', operation, outcome, duration)
        return _json({'ok': True})
    except Exception as error:
        return _error_response(error, 'performance')


COLLECTOR_VAULT_ROUTES = (
    ('/api/collector-vault/performance', collector_vault_performance, ('POST', 'OPTIONS')),
    ("/api/collector-vault/frame/launch", collector_vault_cart_launch, ("GET",)),
    ("/api/collector-vault/frame/preview", observe("frame_preview", collector_vault_cart_preview), ("GET", "OPTIONS")),
    ("/api/collector-vault/frame/cart-handoff", collector_vault_cart_handoff, ("POST", "OPTIONS")),
    ("/api/collector-vault/recommendations", observe('recommendations', collector_vault_recommendations), ("GET", "OPTIONS")),
    ("/api/collector-vault/bootstrap", observe('bootstrap', collector_vault_bootstrap), ("GET", "OPTIONS")),
    ("/api/collector-vault/review-prompt", observe('review_options', collector_vault_review_prompt), ("GET", "OPTIONS")),
    ("/api/collector-vault/events", collector_vault_event, ("POST", "OPTIONS")),
    ("/api/collector-vault/frame/request", collector_vault_frame_request, ("POST", "OPTIONS")),
    (
        "/api/collector-vault/frame/cart-created",
        collector_vault_frame_cart_created,
        ("POST", "OPTIONS"),
    ),
    ("/api/collector-vault/review", collector_vault_review_submit, ("POST", "OPTIONS")),
    ("/api/collector-vault/asset", observe('frame_preview', collector_vault_asset), ("GET", "OPTIONS")),
)
