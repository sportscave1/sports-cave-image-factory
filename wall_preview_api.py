"""Public ingest route for shopper-created See It On Your Wall previews."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath

from PIL import Image
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

import dropbox_integration
import wall_preview_store
import wall_preview_identity


WALL_PREVIEW_PATH = "/api/wall-previews"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
RATE_WINDOW_SECONDS = 10 * 60
RATE_LIMIT = 60
DEFAULT_ALLOWED_ORIGINS = {
    "https://www.sportscaveshop.com",
    "https://sportscaveshop.com",
}
DROPBOX_RELATIVE_ROOT = "03_ASSETS/11 Wall Preview Inbox"

LOGGER = logging.getLogger(__name__)
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS = {}
_INGEST_SLOTS = threading.BoundedSemaphore(4)
_ARCHIVE_LOCKS = tuple(threading.Lock() for _ in range(32))
_DROPBOX_LOCK = threading.Lock()
_DROPBOX_CACHE = {"token": "", "root": "", "expires_at": 0.0}


def _allowed_origins():
    values = set(DEFAULT_ALLOWED_ORIGINS)
    for raw in str(os.getenv("WALL_PREVIEW_ALLOWED_ORIGINS", "") or "").split(","):
        clean = raw.strip().rstrip("/")
        if clean.startswith("https://"):
            values.add(clean)
    return values


def _cors_headers(origin):
    headers = {
        "Cache-Control": "no-store",
        "Vary": "Origin",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept, X-Wall-Preview-Token",
        "Access-Control-Max-Age": "600",
    }
    if origin in _allowed_origins():
        headers["Access-Control-Allow-Origin"] = origin
    return headers


def _origin(request):
    return str(request.headers.get("origin") or "").strip().rstrip("/")


def _client_key(request):
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return hashlib.sha256(forwarded[:80].encode()).hexdigest()
    client = getattr(request, "client", None)
    return hashlib.sha256(str(getattr(client, "host", "") or "unknown").encode()).hexdigest()


def _rate_allowed(key, limit=None):
    now = time.monotonic()
    with _RATE_LOCK:
        recent = [stamp for stamp in _RATE_BUCKETS.get(key, ()) if now - stamp < RATE_WINDOW_SECONDS]
        if len(recent) >= (RATE_LIMIT if limit is None else limit):
            _RATE_BUCKETS[key] = recent
            return False
        recent.append(now)
        _RATE_BUCKETS[key] = recent
        while len(_RATE_BUCKETS) > 2000:
            _RATE_BUCKETS.pop(next(iter(_RATE_BUCKETS)))
        return True


def _query_text(request, name, limit):
    value=re.sub(r'[\x00-\x1f\x7f]',' ',str(request.query_params.get(name) or ''))
    return " ".join(value.split())[:limit]


def _safe_handle(value):
    clean = re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")
    return clean[:80] or "sports-cave-edition"


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _dropbox_connection():
    now = time.monotonic()
    with _DROPBOX_LOCK:
        if _DROPBOX_CACHE["token"] and _DROPBOX_CACHE["root"] and _DROPBOX_CACHE["expires_at"] > now:
            return _DROPBOX_CACHE["token"], _DROPBOX_CACHE["root"]
        auth = dropbox_integration.resolve_server_auth(validate=False)
        token = auth["access_token"]
        root = dropbox_integration.find_team_folder(token)
        _DROPBOX_CACHE.update(
            token=token,
            root=root,
            expires_at=now + 20 * 60,
        )
        return token, root


def _inspect_image(data, content_type):
    if content_type not in {"image/jpeg", "image/png"}:
        raise ValueError("Only JPEG or PNG previews are accepted.")
    if content_type == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("The preview is not a valid JPEG.")
    if content_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The preview is not a valid PNG.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if not (0 < width <= 10000 and 0 < height <= 10000) or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("The preview image dimensions are not accepted.")
            if image.format != {"image/jpeg": "JPEG", "image/png": "PNG"}[content_type]:
                raise ValueError("The preview format does not match its content type.")
            image.verify()
        # Force decoding: verify() alone does not reject all truncated JPEGs.
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("The preview is not a valid bounded image.") from error
    return int(width), int(height)


def _dropbox_destination(root_path, handle, digest, content_type, customer_email):
    now = datetime.now(timezone.utc)
    extension = ".png" if content_type == "image/png" else ".jpg"
    filename = f"{_safe_handle(handle)}-{now:%Y%m%dT%H%M%S%fZ}-{digest[:16]}{extension}"
    folder = dropbox_integration.normalize_dropbox_path(
        f"{root_path}/{DROPBOX_RELATIVE_ROOT}/{wall_preview_identity.customer_folder_name(customer_email)}"
    )
    if not dropbox_integration.path_is_within_root(folder, root_path):
        raise ValueError("Wall preview destination is outside the Dropbox root.")
    return folder, dropbox_integration.normalize_dropbox_path(f"{folder}/{filename}")


async def wall_preview_ingest(request):
    if request.method == 'OPTIONS' or _origin(request) not in _allowed_origins():
        return await _ingest(request)
    # Bound body buffers and expensive image/storage operations together.
    if not _INGEST_SLOTS.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "storage_busy"}, status_code=503,
                            headers=_cors_headers(_origin(request)))
    try:
        return await _ingest(request)
    finally:
        _INGEST_SLOTS.release()


async def _ingest(request):
    origin = _origin(request)
    cors = _cors_headers(origin)
    if request.method == "OPTIONS":
        status = 204 if origin in _allowed_origins() else 403
        return Response(status_code=status, headers=cors)
    if origin not in _allowed_origins():
        return JSONResponse({"ok": False, "error": "origin_not_allowed"}, status_code=403, headers=cors)
    if not _rate_allowed(_client_key(request)):
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429, headers=cors)

    content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    try:
        declared_size = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared_size = 0
    if declared_size > MAX_IMAGE_BYTES:
        return JSONResponse({"ok": False, "error": "image_too_large"}, status_code=413, headers=cors)

    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            return JSONResponse(
                {"ok": False, "error": "image_too_large"},
                status_code=413,
                headers=cors,
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        return JSONResponse(
            {"ok": False, "error": "empty_preview"},
            status_code=400,
            headers=cors,
        )

    return await run_in_threadpool(_save_preview, request, data, content_type, cors)


def _save_preview(request, data, content_type, cors):
    if request.query_params.get('client_preview_id') or not request.query_params.get('customer_email'):
        from wall_preview_crm_api import save
        return save(request, data, content_type, cors)
    # Bounded stripes serialize same-owner retries in the single web process.
    # No growing lock registry and no duplicate physical upload on double-click.
    address = str(request.query_params.get('customer_email') or '').strip().lower()
    key = hashlib.sha256(address.encode() + b'\0' + data).digest()
    with _ARCHIVE_LOCKS[key[0] % len(_ARCHIVE_LOCKS)]:
        return _save_preview_locked(request, data, content_type, cors)


def _save_preview_locked(request, data, content_type, cors):
    try:
        if _query_text(request, "unit", 2) not in {'', 'cm', 'in'}:
            raise ValueError("Choose cm or in for the measurement unit.")
        width, height = _inspect_image(data, content_type)
        # Legacy canvas uploads normally have no metadata. Strip metadata when
        # present while retaining their accepted format and clean-byte retries.
        with Image.open(io.BytesIO(data)) as original:
            if original.info.get('exif') or original.info.get('icc_profile') or original.info.get('comment'):
                from PIL import ImageOps
                clean=ImageOps.exif_transpose(original).convert('RGB')
                buffer=io.BytesIO();clean.save(buffer,'PNG' if content_type=='image/png' else 'JPEG')
                data=buffer.getvalue();width,height=clean.size
        identity = wall_preview_identity.resolve(
            request.query_params.get('customer_email'),
            request.query_params.get('customer_name'),
            request.query_params.get('identity_source'),
        )
        digest = hashlib.sha256(data).hexdigest()
        existing = wall_preview_store.find_preview(digest, customer_email=identity['customer_email'])
        if existing:
            return JSONResponse({"ok": True, "preview_id": str(existing['id']),
                                 "duplicate": True,
                                 "marketing_permission": bool(existing['marketing_permission'])},
                                headers=cors)
        product_handle = _query_text(request, "product_handle", 255)
        token, root_path = _dropbox_connection()
        if root_path.rstrip('/') != "/Sportscave Team Folder":
            raise ValueError("The configured Wall Preview folder is unavailable.")
        folder, destination = _dropbox_destination(
            root_path,
            product_handle,
            digest,
            content_type,
            identity['customer_email'],
        )
        dropbox_integration.ensure_folder_path(token, folder, root_path=root_path)
        metadata = dropbox_integration.upload_stream(
            token,
            destination,
            io.BytesIO(data),
            size=len(data),
            conflict="replace",
        )
        file_id = str(
            (metadata or {}).get("id")
            or (metadata or {}).get("file_id")
            or ""
        )
        saved = wall_preview_store.record_preview(
            {
                "image_sha256": digest,
                **identity,
                "customer_folder": folder,
                "product_id": _query_text(request, "product_id", 80),
                "variant_id": _query_text(request, "variant_id", 80),
                "product_handle": product_handle,
                "product_title": _query_text(request, "product_title", 500),
                "product_url": _query_text(request, "product_url", 1200),
                "frame_label": _query_text(request, "frame", 120),
                "size_label": _query_text(request, "size", 160),
                "measurement_unit": _query_text(request, "unit", 2),
                "marketing_permission": _truthy(request.query_params.get("marketing_permission")),
                "dropbox_file_id": file_id,
                "dropbox_path": destination,
                "content_type": content_type,
                "image_width": width,
                "image_height": height,
                "image_bytes": len(data),
            }
        )
        LOGGER.info(
            "wall_preview_saved id=%s product=%s permission=%s bytes=%s duplicate=%s",
            str(saved.get("id") or ""),
            product_handle,
            bool(saved.get("marketing_permission")),
            len(data),
            bool(saved.get("duplicate")),
        )
        return JSONResponse(
            {
                "ok": True,
                "preview_id": str(saved.get("id") or ""),
                "duplicate": bool(saved.get("duplicate")),
                "marketing_permission": bool(saved.get("marketing_permission")),
            },
            status_code=200,
            headers=cors,
        )
    except ValueError as error:
        return JSONResponse(
            {"ok": False, "error": "invalid_preview", "message": str(error)[:180]},
            status_code=400,
            headers=cors,
        )
    except Exception as error:
        LOGGER.warning("wall_preview_ingest_failed error_type=%s", type(error).__name__)
        return JSONResponse(
            {"ok": False, "error": "storage_unavailable"},
            status_code=503,
            headers=cors,
        )


WALL_PREVIEW_ROUTES = (
    (WALL_PREVIEW_PATH, wall_preview_ingest, ("POST", "OPTIONS")),
)
