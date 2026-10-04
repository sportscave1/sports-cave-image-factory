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
from starlette.responses import JSONResponse, Response

import dropbox_integration
import wall_preview_store


WALL_PREVIEW_PATH = "/api/wall-previews"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
RATE_WINDOW_SECONDS = 10 * 60
RATE_LIMIT = 60
DEFAULT_ALLOWED_ORIGINS = {
    "https://www.sportscaveshop.com",
    "https://sportscaveshop.com",
}
DROPBOX_RELATIVE_ROOT = "11 Wall Preview Inbox"

LOGGER = logging.getLogger(__name__)
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS = {}
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
        "Access-Control-Allow-Headers": "Content-Type, Accept",
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
        return forwarded[:80]
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "") or "unknown")[:80]


def _rate_allowed(key):
    now = time.monotonic()
    with _RATE_LOCK:
        recent = [stamp for stamp in _RATE_BUCKETS.get(key, ()) if now - stamp < RATE_WINDOW_SECONDS]
        if len(recent) >= RATE_LIMIT:
            _RATE_BUCKETS[key] = recent
            return False
        recent.append(now)
        _RATE_BUCKETS[key] = recent
        if len(_RATE_BUCKETS) > 2000:
            cutoff = now - RATE_WINDOW_SECONDS
            for bucket_key in list(_RATE_BUCKETS)[:500]:
                kept = [stamp for stamp in _RATE_BUCKETS[bucket_key] if stamp >= cutoff]
                if kept:
                    _RATE_BUCKETS[bucket_key] = kept
                else:
                    _RATE_BUCKETS.pop(bucket_key, None)
        return True


def _query_text(request, name, limit):
    return " ".join(str(request.query_params.get(name) or "").split())[:limit]


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
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("The preview image dimensions are not accepted.")
    return int(width), int(height)


def _dropbox_destination(root_path, handle, digest, content_type):
    now = datetime.now(timezone.utc)
    extension = ".png" if content_type == "image/png" else ".jpg"
    filename = f"sports-cave-{_safe_handle(handle)}-wall-preview-{digest[:12]}{extension}"
    folder = dropbox_integration.normalize_dropbox_path(
        f"{root_path}/{DROPBOX_RELATIVE_ROOT}/{now:%Y}/{now:%m}"
    )
    if not dropbox_integration.path_is_within_root(folder, root_path):
        raise ValueError("Wall preview destination is outside the Dropbox root.")
    return folder, dropbox_integration.normalize_dropbox_path(f"{folder}/{filename}")


async def wall_preview_ingest(request):
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

    try:
        width, height = _inspect_image(data, content_type)
        digest = hashlib.sha256(data).hexdigest()
        product_handle = _query_text(request, "product_handle", 255)
        token, root_path = _dropbox_connection()
        folder, destination = _dropbox_destination(
            root_path,
            product_handle,
            digest,
            content_type,
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
    except Exception:
        LOGGER.exception("wall_preview_ingest_failed")
        return JSONResponse(
            {"ok": False, "error": "storage_unavailable"},
            status_code=503,
            headers=cors,
        )


WALL_PREVIEW_ROUTES = (
    (WALL_PREVIEW_PATH, wall_preview_ingest, ("POST", "OPTIONS")),
)
