import os
import io
import mimetypes
import secrets
import threading
import time
import zipfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from activity_log import record_activity_log
import dropbox_integration
import os_accounts
import sc_auth


FILES_UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
FILES_UPLOAD_SESSION_SECONDS = 6 * 60 * 60
FILES_THUMBNAIL_CACHE_SECONDS = 30 * 60
FILES_THUMBNAIL_CACHE_LIMIT = 256
FILES_DIRECTORY_CACHE_SECONDS = 3 * 60
FILES_DIRECTORY_CACHE_LIMIT = 64
DESKTOP_HELPER_DIR = Path(__file__).resolve().parent / "desktop_helper"
MACOS_DESKTOP_HELPER_DIR = Path(__file__).resolve().parent / "desktop_helper_macos"
FILES_WINDOW_FILE = (
    Path(__file__).resolve().parent / "components" / "files_window" / "index.html"
)
FILES_IMAGE_VIEWER_FILE = (
    Path(__file__).resolve().parent / "components" / "files_image_viewer" / "index.html"
)
FILES_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
FILES_IMAGE_PREVIEW_MAX_BYTES = 100 * 1024 * 1024


class FilesUploadError(RuntimeError):
    def __init__(self, message, *, status_code=400, code="upload_error", details=None):
        super().__init__(message)
        self.status_code = int(status_code)
        self.code = str(code)
        self.details = dict(details or {})


@dataclass
class ChunkUploadRecord:
    upload_id: str
    upload_secret: str
    access_token: str
    destination: str
    mode: str
    relative_path: str
    name: str
    size: int
    user: dict
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    offset: int = 0
    dropbox_session_id: str = ""
    state: str = "ready"
    metadata: dict = field(default_factory=dict)
    error: str = ""
    activity_recorded: bool = False
    operation_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class DropboxChunkUploadManager:
    def __init__(self):
        self._records = {}
        self._lock = threading.RLock()

    def _cleanup(self):
        cutoff = time.monotonic() - FILES_UPLOAD_SESSION_SECONDS
        for upload_id, record in list(self._records.items()):
            if record.updated_at < cutoff:
                self._records.pop(upload_id, None)

    def start(
        self,
        *,
        access_token,
        root_path,
        current_path,
        relative_path,
        size,
        conflict,
        user,
    ):
        clean_root = dropbox_integration.normalize_dropbox_path(root_path)
        clean_folder = dropbox_integration.normalize_dropbox_path(current_path)
        if not dropbox_integration.path_is_within_root(clean_folder, clean_root):
            raise FilesUploadError("This destination is not available.", status_code=403)
        clean_relative = dropbox_integration.sanitize_relative_upload_path(relative_path)
        total_size = max(0, int(size or 0))
        destination = dropbox_integration.join_upload_path(clean_folder, clean_relative)
        parent = str(PurePosixPath(clean_relative).parent)
        if parent not in {"", "."}:
            dropbox_integration.ensure_relative_folders(access_token, clean_folder, parent)
        resolved = dropbox_integration.resolve_upload_destination(
            access_token,
            destination,
            conflict,
        )
        if resolved is None:
            raise FilesUploadError(
                "A file with this name already exists.",
                status_code=409,
                code="name_conflict",
            )
        record = ChunkUploadRecord(
            upload_id=secrets.token_urlsafe(18),
            upload_secret=secrets.token_urlsafe(24),
            access_token=str(access_token),
            destination=str(resolved["path"]),
            mode=str(resolved["mode"]),
            relative_path=clean_relative,
            name=PurePosixPath(clean_relative).name,
            size=total_size,
            user=dict(user or {}),
        )
        with self._lock:
            self._cleanup()
            self._records[record.upload_id] = record
        return self.public_status(record, include_secret=True)

    def _record(self, upload_id, upload_secret):
        with self._lock:
            self._cleanup()
            record = self._records.get(str(upload_id or ""))
            if not record or not secrets.compare_digest(
                record.upload_secret,
                str(upload_secret or ""),
            ):
                raise FilesUploadError(
                    "This upload can no longer be resumed.",
                    status_code=404,
                    code="upload_missing",
                )
            return record

    @staticmethod
    def public_status(record, *, include_secret=False, just_completed=False):
        payload = {
            "upload_id": record.upload_id,
            "name": record.name,
            "relative_path": record.relative_path,
            "destination": record.destination,
            "mode": record.mode,
            "size": record.size,
            "offset": record.offset,
            "state": record.state,
            "error": record.error,
            "metadata": dict(record.metadata or {}),
            "just_completed": bool(just_completed),
        }
        if include_secret:
            payload["upload_secret"] = record.upload_secret
        return payload

    def status(self, upload_id, upload_secret):
        return self.public_status(self._record(upload_id, upload_secret))

    def append(self, upload_id, upload_secret, offset, data, *, final=False):
        record = self._record(upload_id, upload_secret)
        with record.operation_lock:
            return self._append_record(record, offset, data, final=final)

    def _append_record(self, record, offset, data, *, final=False):
        chunk = bytes(data or b"")
        if len(chunk) > FILES_UPLOAD_CHUNK_BYTES:
            raise FilesUploadError("Upload chunk is too large.", status_code=413)
        supplied_offset = max(0, int(offset or 0))
        with self._lock:
            if record.state == "completed":
                return self.public_status(record)
            if supplied_offset != record.offset:
                raise FilesUploadError(
                    f"Resume from byte {record.offset}.",
                    status_code=409,
                    code="offset_mismatch",
                    details={"offset": record.offset},
                )
            if record.offset + len(chunk) > record.size:
                raise FilesUploadError("Upload data exceeds the selected file size.")
            if final and record.offset + len(chunk) != record.size:
                raise FilesUploadError("The upload is incomplete.")
            if not final and record.offset + len(chunk) >= record.size:
                raise FilesUploadError("The final upload chunk was not marked complete.")
            record.state = "uploading"
            record.error = ""
            record.updated_at = time.monotonic()

        try:
            if final:
                if not record.dropbox_session_id:
                    record.dropbox_session_id = dropbox_integration.start_upload_session(
                        record.access_token,
                        b"",
                    )
                metadata = dropbox_integration.finish_upload_session(
                    record.access_token,
                    record.dropbox_session_id,
                    record.offset,
                    chunk,
                    record.destination,
                    mode=record.mode,
                )
                with self._lock:
                    record.offset += len(chunk)
                    record.metadata = dict(metadata or {})
                    record.state = "completed"
                    record.updated_at = time.monotonic()
                return self.public_status(record, just_completed=True)

            if not record.dropbox_session_id:
                record.dropbox_session_id = dropbox_integration.start_upload_session(
                    record.access_token,
                    chunk,
                )
            else:
                dropbox_integration.append_upload_session(
                    record.access_token,
                    record.dropbox_session_id,
                    record.offset,
                    chunk,
                )
            with self._lock:
                record.offset += len(chunk)
                record.updated_at = time.monotonic()
            return self.public_status(record)
        except FilesUploadError:
            raise
        except Exception as error:
            correct_offset = getattr(error, "correct_offset", None)
            if correct_offset is not None:
                with self._lock:
                    record.offset = max(0, min(int(correct_offset), record.size))
                    record.state = "uploading"
                    record.error = ""
                    record.updated_at = time.monotonic()
                raise FilesUploadError(
                    f"Resume from byte {record.offset}.",
                    status_code=409,
                    code="offset_mismatch",
                    details={"offset": record.offset},
                ) from error
            with self._lock:
                record.state = "failed"
                record.error = "Upload interrupted. Retry to continue."
                record.updated_at = time.monotonic()
            raise FilesUploadError(
                "Upload interrupted. Retry to continue.",
                status_code=503,
                code="upload_interrupted",
            ) from error

    def mark_activity_recorded(self, upload_id, upload_secret):
        record = self._record(upload_id, upload_secret)
        with self._lock:
            if record.activity_recorded:
                return False
            record.activity_recorded = True
            return True

    def activity_context(self, upload_id, upload_secret):
        record = self._record(upload_id, upload_secret)
        return {
            "name": record.name,
            "size": record.size,
            "destination": record.destination,
            "user": dict(record.user or {}),
        }

    def remove(self, upload_id, upload_secret):
        record = self._record(upload_id, upload_secret)
        with self._lock:
            self._records.pop(record.upload_id, None)


UPLOAD_MANAGER = DropboxChunkUploadManager()
_DROPBOX_CONTEXT = {}
_DROPBOX_CONTEXT_LOCK = threading.Lock()
_THUMBNAIL_CACHE = {}
_THUMBNAIL_CACHE_LOCK = threading.Lock()
_DIRECTORY_CACHE = {}
_DIRECTORY_CACHE_LOCK = threading.Lock()


def invalidate_directory_cache(*paths):
    clean_paths = set()
    for path in paths:
        with suppress(Exception):
            clean_paths.add(dropbox_integration.normalize_dropbox_path(path).casefold())
    with _DIRECTORY_CACHE_LOCK:
        if not clean_paths:
            _DIRECTORY_CACHE.clear()
            return
        for key in list(_DIRECTORY_CACHE):
            if str(key).casefold() in clean_paths:
                _DIRECTORY_CACHE.pop(key, None)


def _directory_entries(access_token, path, *, force=False):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    now = time.monotonic()
    with _DIRECTORY_CACHE_LOCK:
        cached = _DIRECTORY_CACHE.get(clean_path) or {}
        if not force and cached.get("expires_at", 0) > now:
            return list(cached.get("entries") or ())
    entries = dropbox_integration.sort_folder_entries(
        dropbox_integration.list_folder(access_token, clean_path)
    )
    with _DIRECTORY_CACHE_LOCK:
        _DIRECTORY_CACHE[clean_path] = {
            "entries": list(entries),
            "expires_at": now + FILES_DIRECTORY_CACHE_SECONDS,
        }
        while len(_DIRECTORY_CACHE) > FILES_DIRECTORY_CACHE_LIMIT:
            oldest = min(
                _DIRECTORY_CACHE,
                key=lambda key: _DIRECTORY_CACHE[key].get("expires_at", 0),
            )
            _DIRECTORY_CACHE.pop(oldest, None)
    return list(entries)


def invalidate_thumbnail_cache(*paths):
    clean_paths = set()
    for path in paths:
        with suppress(Exception):
            clean_path = dropbox_integration.normalize_dropbox_path(path)
            if clean_path:
                clean_paths.add(clean_path.casefold())
    if not clean_paths:
        return
    with _THUMBNAIL_CACHE_LOCK:
        for key in list(_THUMBNAIL_CACHE):
            if str(key[0]).casefold() in clean_paths:
                _THUMBNAIL_CACHE.pop(key, None)


def _thumbnail_bytes(access_token, path, revision=""):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    cache_key = (clean_path, str(revision or ""))
    now = time.monotonic()
    with _THUMBNAIL_CACHE_LOCK:
        cached = _THUMBNAIL_CACHE.get(cache_key) or {}
        if cached.get("expires_at", 0) > now:
            return bytes(cached.get("content") or b"")
    content = dropbox_integration.get_thumbnail_bytes(
        access_token,
        clean_path,
        size="w64h64",
    )
    with _THUMBNAIL_CACHE_LOCK:
        _THUMBNAIL_CACHE[cache_key] = {
            "content": bytes(content),
            "expires_at": now + FILES_THUMBNAIL_CACHE_SECONDS,
        }
        while len(_THUMBNAIL_CACHE) > FILES_THUMBNAIL_CACHE_LIMIT:
            oldest = min(
                _THUMBNAIL_CACHE,
                key=lambda key: _THUMBNAIL_CACHE[key].get("expires_at", 0),
            )
            _THUMBNAIL_CACHE.pop(oldest, None)
    return bytes(content)


def _dropbox_context(*, force=False):
    now = time.monotonic()
    with _DROPBOX_CONTEXT_LOCK:
        if not force and _DROPBOX_CONTEXT.get("expires_at", 0) > now:
            return dict(_DROPBOX_CONTEXT)
    auth = dropbox_integration.resolve_server_auth()
    access_token = str(auth.get("access_token") or "")
    root_path = dropbox_integration.find_team_folder(access_token)
    context = {
        "access_token": access_token,
        "root_path": root_path,
        "expires_at": now + 25 * 60,
    }
    with _DROPBOX_CONTEXT_LOCK:
        _DROPBOX_CONTEXT.clear()
        _DROPBOX_CONTEXT.update(context)
    return dict(context)


def _request_user(request):
    token = str(request.cookies.get(sc_auth.AUTH_COOKIE_NAME) or "")
    password = sc_auth.DEFAULT_APP_PASSWORD
    extra_secret = str(os.getenv("SPORTS_CAVE_AUTH_SECRET") or "").strip()
    valid, _reason, payload = sc_auth.validate_user_auth_token(
        token,
        password=password,
        extra_secret=extra_secret,
    )
    if valid:
        try:
            user = os_accounts.DEFAULT_STORE.get_user(payload.get("sub"))
        except Exception:
            user = {}
        if user and os_accounts.can_access_page(user, "Files"):
            return user
    legacy_valid, _legacy_reason = sc_auth.validate_auth_token(
        token,
        password=password,
        extra_secret=extra_secret,
    )
    if legacy_valid:
        return {
            "id": "legacy-master-admin",
            "username": "admin",
            "display_name": "Sports Cave Admin",
            "email": "",
            "role": os_accounts.ROLE_ADMIN,
            "is_active": True,
            "page_permissions": [],
        }
    raise FilesUploadError("Access not approved.", status_code=403, code="access_denied")


def _request_files_delete_user(request):
    user = _request_user(request)
    if not os_accounts.can_delete_files(user):
        raise FilesUploadError("Access not approved.", status_code=403, code="access_denied")
    return user


def _validated_delete_paths(paths, current_path, root_path):
    if not isinstance(paths, (list, tuple)):
        raise FilesUploadError("Select at least one item.")
    try:
        clean_root = dropbox_integration.normalize_dropbox_path(root_path)
        clean_folder = dropbox_integration.normalize_dropbox_path(current_path)
    except (TypeError, ValueError) as error:
        raise FilesUploadError("This folder is not available.", status_code=403) from error
    if not dropbox_integration.path_is_within_root(clean_folder, clean_root):
        raise FilesUploadError("This folder is not available.", status_code=403)
    selected = []
    for path in paths or ():
        try:
            clean_path = dropbox_integration.normalize_dropbox_path(path)
        except (TypeError, ValueError) as error:
            raise FilesUploadError("This item is not available.", status_code=403) from error
        if not clean_path or clean_path.casefold() == clean_root.casefold():
            raise FilesUploadError("The shared Files folder cannot be removed.", status_code=403)
        if not dropbox_integration.path_is_within_root(clean_path, clean_root):
            raise FilesUploadError("This item is not available.", status_code=403)
        parent = clean_path.rsplit("/", 1)[0]
        if parent.casefold() != clean_folder.casefold():
            raise FilesUploadError("This item is not in the open folder.", status_code=403)
        if clean_path not in selected:
            selected.append(clean_path)
    if not selected:
        raise FilesUploadError("Select at least one item.")
    if len(selected) > 100:
        raise FilesUploadError("Select no more than 100 items at once.")
    return selected


def _validated_current_folder(path, root_path):
    try:
        clean_root = dropbox_integration.normalize_dropbox_path(root_path)
        clean_path = dropbox_integration.normalize_dropbox_path(path)
    except (TypeError, ValueError) as error:
        raise FilesUploadError("This folder is not available.", status_code=403) from error
    if not clean_path:
        clean_path = clean_root
    if not dropbox_integration.path_is_within_root(clean_path, clean_root):
        raise FilesUploadError("This folder is not available.", status_code=403)
    return clean_path


def _validated_item_in_folder(path, current_path, root_path):
    clean_folder = _validated_current_folder(current_path, root_path)
    try:
        clean_path = dropbox_integration.normalize_dropbox_path(path)
    except (TypeError, ValueError) as error:
        raise FilesUploadError("This item is not available.", status_code=403) from error
    clean_root = dropbox_integration.normalize_dropbox_path(root_path)
    if (
        not clean_path
        or clean_path.casefold() == clean_root.casefold()
        or not dropbox_integration.path_is_within_root(clean_path, clean_root)
    ):
        raise FilesUploadError("This item is not available.", status_code=403)
    if clean_path.rsplit("/", 1)[0].casefold() != clean_folder.casefold():
        raise FilesUploadError("This item is not in the open folder.", status_code=403)
    return clean_path, clean_folder


def _validated_relative_path(relative_path, root_path):
    raw = str(relative_path or "")
    if (
        not raw
        or raw != raw.strip()
        or raw.startswith(("/", "\\"))
        or "\\" in raw
        or ":" in raw
        or "\x00" in raw
    ):
        raise FilesUploadError("This file is not available.", status_code=403)
    parts = raw.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise FilesUploadError("This file is not available.", status_code=403)
    clean_root = dropbox_integration.normalize_dropbox_path(root_path)
    try:
        clean_path = dropbox_integration.normalize_dropbox_path(f"{clean_root}/{raw}")
    except (TypeError, ValueError) as error:
        raise FilesUploadError("This file is not available.", status_code=403) from error
    if not dropbox_integration.path_is_within_root(clean_path, clean_root):
        raise FilesUploadError("This file is not available.", status_code=403)
    return clean_path


def _file_kind(name, tag):
    if str(tag or "").casefold() == "folder":
        return "folder"
    extension = PurePosixPath(str(name or "")).suffix.casefold()
    if extension in {".psd", ".psb"}:
        return "photoshop"
    if extension in FILES_IMAGE_EXTENSIONS:
        return "image"
    if extension == ".pdf":
        return "pdf"
    if extension in {".doc", ".docx", ".txt", ".rtf", ".md"}:
        return "document"
    if extension in {".xls", ".xlsx", ".csv"}:
        return "sheet"
    if extension in {".mp4", ".webm", ".mov", ".m4v", ".avi"}:
        return "video"
    if extension in {".zip", ".rar", ".7z"}:
        return "archive"
    if extension in {".ai", ".indd", ".eps"}:
        return "design"
    return "file"


def _file_type_label(name, tag):
    if str(tag or "").casefold() == "folder":
        return "File folder"
    extension = PurePosixPath(str(name or "")).suffix.lstrip(".").upper()
    labels = {
        "JPG": "JPEG image",
        "JPEG": "JPEG image",
        "PNG": "PNG image",
        "WEBP": "WebP image",
        "GIF": "GIF image",
        "PDF": "PDF document",
        "DOC": "Word document",
        "DOCX": "Word document",
        "TXT": "Text document",
        "XLS": "Excel worksheet",
        "XLSX": "Excel worksheet",
        "CSV": "CSV file",
        "PSD": "Adobe Photoshop document",
        "PSB": "Adobe Photoshop large document",
        "AI": "Adobe Illustrator artwork",
        "INDD": "Adobe InDesign document",
        "MP4": "MP4 video",
        "WEBM": "WebM video",
        "MOV": "QuickTime video",
        "ZIP": "Compressed folder",
    }
    return labels.get(extension, f"{extension} file" if extension else "File")


def _public_file_item(entry, root_path):
    entry = dict(entry or {})
    tag = str(entry.get(".tag") or "file").casefold()
    name = str(entry.get("name") or "Untitled")
    path = dropbox_integration.normalize_dropbox_path(
        entry.get("path_display") or entry.get("path_lower") or ""
    )
    clean_root = dropbox_integration.normalize_dropbox_path(root_path)
    if not path or not dropbox_integration.path_is_within_root(path, clean_root):
        return None
    relative_path = path[len(clean_root) :].lstrip("/")
    extension = PurePosixPath(name).suffix.casefold()
    thumbnail_supported = tag != "folder" and extension in {".jpg", ".jpeg", ".png"}
    revision = str(entry.get("rev") or entry.get("content_hash") or "")
    item = {
        "id": path,
        "path": path,
        "desktop_relative_path": relative_path,
        "name": name,
        "tag": tag,
        "kind": _file_kind(name, tag),
        "extension": extension.lstrip("."),
        "type": _file_type_label(name, tag),
        "size": int(entry.get("size") or 0) if tag != "folder" else 0,
        "size_label": "" if tag == "folder" else dropbox_integration.format_file_size(entry.get("size")),
        "modified": str(entry.get("server_modified") or ""),
        "status": "Online",
        "protected": path.casefold() == clean_root.casefold(),
    }
    if thumbnail_supported:
        item["thumbnail_url"] = (
            f"/api/files-thumbnail?path={quote(path, safe='')}&rev={quote(revision, safe='')}"
        )
        item["thumbnail_key"] = f"{path}|{revision}"
    return item


def _same_origin(request):
    origin = str(request.headers.get("origin") or "").strip()
    if not origin:
        return True
    return origin.rstrip("/") == str(request.base_url).rstrip("/")


async def _json_body(request):
    try:
        return dict(await request.json())
    except Exception as error:
        raise FilesUploadError("Files request is invalid.") from error


async def _bounded_chunk(request):
    content_length = request.headers.get("content-length")
    try:
        declared_length = int(content_length) if content_length else 0
    except (TypeError, ValueError) as error:
        raise FilesUploadError("Upload request is invalid.") from error
    if declared_length > FILES_UPLOAD_CHUNK_BYTES:
        raise FilesUploadError("Upload chunk is too large.", status_code=413)
    body = bytearray()
    total = 0
    async for part in request.stream():
        total += len(part)
        if total > FILES_UPLOAD_CHUNK_BYTES:
            raise FilesUploadError("Upload chunk is too large.", status_code=413)
        body.extend(part)
    return bytes(body)


def _response_error(error):
    if isinstance(error, FilesUploadError):
        return JSONResponse(
            {
                "ok": False,
                "code": error.code,
                "message": str(error),
                **error.details,
            },
            status_code=error.status_code,
        )
    return JSONResponse(
        {"ok": False, "code": "files_unavailable", "message": "Files is unavailable right now."},
        status_code=503,
    )


def _activity_actor(user):
    return (
        str((user or {}).get("display_name") or "").strip()
        or str((user or {}).get("email") or "").strip()
        or str((user or {}).get("username") or "").strip()
        or "Sports Cave"
    )


async def files_window_page(request: Request):
    """Serve the standalone Files application to an approved signed-in user."""
    try:
        await run_in_threadpool(_request_user, request)
        source = await run_in_threadpool(FILES_WINDOW_FILE.read_text, encoding="utf-8")
        return HTMLResponse(
            source,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
            },
        )
    except Exception as error:
        if isinstance(error, FilesUploadError):
            return HTMLResponse(
                "<!doctype html><title>Files unavailable</title>"
                "<p style='font:14px Segoe UI,sans-serif;padding:24px'>"
                "Files access is not approved for this account.</p>",
                status_code=error.status_code,
                headers={"Cache-Control": "no-store"},
            )
        return HTMLResponse(
            "<!doctype html><title>Files unavailable</title>"
            "<p style='font:14px Segoe UI,sans-serif;padding:24px'>"
            "Files could not be opened right now.</p>",
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )


async def files_image_viewer_page(request: Request):
    """Serve the standalone image viewer to an approved signed-in user."""
    try:
        await run_in_threadpool(_request_user, request)
        source = await run_in_threadpool(FILES_IMAGE_VIEWER_FILE.read_text, encoding="utf-8")
        return HTMLResponse(
            source,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
            },
        )
    except Exception as error:
        status = error.status_code if isinstance(error, FilesUploadError) else 503
        return HTMLResponse(
            "<!doctype html><title>Image unavailable</title>"
            "<p style='font:14px Segoe UI,sans-serif;padding:24px'>"
            "This image could not be opened.</p>",
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )


async def list_files(request: Request):
    """Return metadata only for one approved Dropbox folder."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Files request is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_user, request)
        context = await run_in_threadpool(_dropbox_context)
        current_path = _validated_current_folder(
            request.query_params.get("path") or context["root_path"],
            context["root_path"],
        )
        force = str(request.query_params.get("refresh") or "").casefold() in {"1", "true"}
        try:
            entries = await run_in_threadpool(
                _directory_entries,
                context["access_token"],
                current_path,
                force=force,
            )
        except Exception:
            context = await run_in_threadpool(_dropbox_context, force=True)
            current_path = _validated_current_folder(current_path, context["root_path"])
            entries = await run_in_threadpool(
                _directory_entries,
                context["access_token"],
                current_path,
                force=True,
            )
        items = [
            item
            for item in (
                _public_file_item(entry, context["root_path"])
                for entry in entries
            )
            if item
        ]
        return JSONResponse(
            {
                "ok": True,
                "root_path": context["root_path"],
                "root_name": context["root_path"].rsplit("/", 1)[-1],
                "current_path": current_path,
                "items": items,
                "can_delete": bool(os_accounts.can_delete_files(user)),
                "cached_for_seconds": FILES_DIRECTORY_CACHE_SECONDS,
            },
            headers={"Cache-Control": "no-store"},
        )
    except Exception as error:
        return _response_error(error)


async def create_files_folder(request: Request):
    try:
        if not _same_origin(request):
            raise FilesUploadError("Folder request is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_user, request)
        payload = await _json_body(request)
        context = await run_in_threadpool(_dropbox_context)
        folder_name = str(payload.get("name") or "").strip()
        if not folder_name:
            raise FilesUploadError("Enter a folder name.", code="invalid_name")
        try:
            dropbox_integration.sanitize_path_component(folder_name)
        except ValueError as error:
            raise FilesUploadError(
                "Enter a valid folder name.",
                code="invalid_name",
            ) from error
        current_path = _validated_current_folder(
            payload.get("current_path"),
            context["root_path"],
        )
        try:
            metadata = await run_in_threadpool(
                dropbox_integration.create_folder,
                context["access_token"],
                current_path,
                folder_name,
                conflict=payload.get("conflict") or "cancel",
            )
        except dropbox_integration.DropboxConflictError as error:
            raise FilesUploadError(
                "A file or folder already uses this name.",
                status_code=409,
                code="name_conflict",
            ) from error
        if not metadata:
            raise FilesUploadError(
                "A file or folder already uses this name.",
                status_code=409,
                code="name_conflict",
            )
        created_path = dropbox_integration.normalize_dropbox_path(
            metadata.get("path_display") or metadata.get("path_lower") or ""
        )
        invalidate_directory_cache(current_path)
        await run_in_threadpool(
            record_activity_log,
            "files_folder_created",
            "Files",
            f"Folder created: {metadata.get('name') or folder_name}",
            entity_type="dropbox_folder",
            entity_id=created_path,
            actor=_activity_actor(user),
        )
        return JSONResponse(
            {
                "ok": True,
                "item": _public_file_item(metadata, context["root_path"]),
            }
        )
    except Exception as error:
        return _response_error(error)


async def rename_files_item(request: Request):
    try:
        if not _same_origin(request):
            raise FilesUploadError("Rename request is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_user, request)
        payload = await _json_body(request)
        context = await run_in_threadpool(_dropbox_context)
        new_name = str(payload.get("name") or "").strip()
        if not new_name:
            raise FilesUploadError("Enter a new name.", code="invalid_name")
        try:
            dropbox_integration.sanitize_path_component(new_name)
        except ValueError as error:
            raise FilesUploadError("Enter a valid name.", code="invalid_name") from error
        old_path, current_path = _validated_item_in_folder(
            payload.get("path"),
            payload.get("current_path"),
            context["root_path"],
        )
        try:
            metadata = await run_in_threadpool(
                dropbox_integration.rename_path,
                context["access_token"],
                old_path,
                new_name,
                root_path=context["root_path"],
            )
        except dropbox_integration.DropboxConflictError as error:
            raise FilesUploadError(
                "A file or folder already uses this name.",
                status_code=409,
                code="name_conflict",
            ) from error
        new_path = dropbox_integration.normalize_dropbox_path(
            metadata.get("path_display") or metadata.get("path_lower") or ""
        )
        invalidate_directory_cache(current_path, old_path, new_path)
        invalidate_thumbnail_cache(old_path, new_path)
        await run_in_threadpool(
            record_activity_log,
            "files_item_renamed",
            "Files",
            f"Renamed {old_path.rsplit('/', 1)[-1]} to {metadata.get('name') or new_name}",
            entity_type="dropbox_item",
            entity_id=new_path,
            actor=_activity_actor(user),
        )
        return JSONResponse(
            {
                "ok": True,
                "item": _public_file_item(metadata, context["root_path"]),
            }
        )
    except Exception as error:
        return _response_error(error)


async def start_files_upload(request: Request):
    try:
        if not _same_origin(request):
            raise FilesUploadError("Upload request is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_user, request)
        payload = await _json_body(request)
        context = await run_in_threadpool(_dropbox_context)
        result = await run_in_threadpool(
            UPLOAD_MANAGER.start,
            access_token=context["access_token"],
            root_path=context["root_path"],
            current_path=payload.get("current_path"),
            relative_path=payload.get("relative_path"),
            size=payload.get("size"),
            conflict=payload.get("conflict"),
            user=user,
        )
        return JSONResponse({"ok": True, **result})
    except Exception as error:
        return _response_error(error)


async def append_files_upload_chunk(request: Request):
    try:
        if not _same_origin(request):
            raise FilesUploadError("Upload request is not allowed.", status_code=403)
        chunk = await _bounded_chunk(request)
        result = await run_in_threadpool(
            UPLOAD_MANAGER.append,
            request.headers.get("x-upload-id"),
            request.headers.get("x-upload-secret"),
            request.headers.get("x-upload-offset"),
            chunk,
            final=str(request.headers.get("x-upload-final") or "").casefold() == "true",
        )
        if result.get("just_completed") and UPLOAD_MANAGER.mark_activity_recorded(
            result.get("upload_id"),
            request.headers.get("x-upload-secret"),
        ):
            context = UPLOAD_MANAGER.activity_context(
                result.get("upload_id"),
                request.headers.get("x-upload-secret"),
            )
            invalidate_thumbnail_cache(context["destination"])
            invalidate_directory_cache(context["destination"].rsplit("/", 1)[0])
            actor = (
                str(context["user"].get("display_name") or "").strip()
                or str(context["user"].get("email") or "").strip()
                or str(context["user"].get("username") or "").strip()
                or "Sports Cave"
            )
            await run_in_threadpool(
                record_activity_log,
                "files_uploaded",
                "Files",
                f"Uploaded file: {context['name']}",
                entity_type="dropbox_file",
                entity_id=context["destination"],
                metadata={
                    "size": context["size"],
                    "destination": context["destination"],
                },
                actor=actor,
            )
        return JSONResponse({"ok": True, **result})
    except Exception as error:
        return _response_error(error)


async def files_upload_status(request: Request):
    try:
        if not _same_origin(request):
            raise FilesUploadError("Upload request is not allowed.", status_code=403)
        result = UPLOAD_MANAGER.status(
            request.query_params.get("upload_id"),
            request.headers.get("x-upload-secret"),
        )
        return JSONResponse({"ok": True, **result})
    except Exception as error:
        return _response_error(error)


async def remove_files_upload(request: Request):
    try:
        if not _same_origin(request):
            raise FilesUploadError("Upload request is not allowed.", status_code=403)
        payload = await _json_body(request)
        UPLOAD_MANAGER.remove(
            payload.get("upload_id"),
            request.headers.get("x-upload-secret"),
        )
        return JSONResponse({"ok": True})
    except Exception as error:
        return _response_error(error)


async def download_file(request: Request):
    """Resolve a short-lived Dropbox link only after an explicit Download action."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Download request is not allowed.", status_code=403)
        await run_in_threadpool(_request_user, request)
        context = await run_in_threadpool(_dropbox_context)
        relative_path = request.query_params.get("relative_path")
        path = (
            _validated_relative_path(relative_path, context["root_path"])
            if relative_path is not None
            else dropbox_integration.normalize_dropbox_path(request.query_params.get("path") or "")
        )
        if not path or not dropbox_integration.path_is_within_root(path, context["root_path"]):
            raise FilesUploadError("This file is not available.", status_code=403)
        link = await run_in_threadpool(
            dropbox_integration.get_temporary_link,
            context["access_token"],
            path,
        )
        if not link:
            raise FilesUploadError("This file could not be downloaded right now.", status_code=503)
        return RedirectResponse(str(link), status_code=307)
    except Exception as error:
        return _response_error(error)


async def image_preview(request: Request):
    """Proxy one approved image from Dropbox without exposing credentials or cloud paths."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Preview request is not allowed.", status_code=403)
        await run_in_threadpool(_request_user, request)
        context = await run_in_threadpool(_dropbox_context)
        path = _validated_relative_path(
            request.query_params.get("path"),
            context["root_path"],
        )
        extension = PurePosixPath(path).suffix.casefold()
        if extension not in FILES_IMAGE_EXTENSIONS:
            raise FilesUploadError("This preview is not available.", status_code=404)
        metadata = await run_in_threadpool(
            dropbox_integration.get_file_metadata,
            context["access_token"],
            path,
        )
        if str(metadata.get(".tag") or "file").casefold() == "folder":
            raise FilesUploadError("This preview is not available.", status_code=404)
        if int(metadata.get("size") or 0) > FILES_IMAGE_PREVIEW_MAX_BYTES:
            raise FilesUploadError(
                "This image is too large for browser preview. Open it in the desktop app instead.",
                status_code=413,
            )
        _metadata, content = await run_in_threadpool(
            dropbox_integration.get_file_bytes,
            context["access_token"],
            path,
        )
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return Response(
            content,
            media_type=media_type,
            headers={
                "Cache-Control": "private, max-age=300",
                "Content-Disposition": "inline",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as error:
        return _response_error(error)


async def image_folder_items(request: Request):
    """Return root-relative image navigation metadata for one approved folder."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Preview request is not allowed.", status_code=403)
        await run_in_threadpool(_request_user, request)
        context = await run_in_threadpool(_dropbox_context)
        folder_value = request.query_params.get("folder")
        folder_path = (
            context["root_path"]
            if folder_value in {None, ""}
            else _validated_relative_path(folder_value, context["root_path"])
        )
        entries = await run_in_threadpool(
            _directory_entries,
            context["access_token"],
            folder_path,
        )
        clean_root = dropbox_integration.normalize_dropbox_path(context["root_path"])
        images = []
        for entry in entries:
            if str(entry.get(".tag") or "file").casefold() == "folder":
                continue
            path = dropbox_integration.normalize_dropbox_path(
                entry.get("path_display") or entry.get("path_lower") or ""
            )
            if (
                PurePosixPath(path).suffix.casefold() in FILES_IMAGE_EXTENSIONS
                and dropbox_integration.path_is_within_root(path, clean_root)
                and path.rsplit("/", 1)[0].casefold() == folder_path.casefold()
            ):
                images.append(
                    {
                        "path": path[len(clean_root) :].lstrip("/"),
                        "name": str(entry.get("name") or PurePosixPath(path).name),
                    }
                )
        return JSONResponse({"ok": True, "images": images}, headers={"Cache-Control": "no-store"})
    except Exception as error:
        return _response_error(error)


async def file_thumbnail(request: Request):
    """Serve a cached, tiny Dropbox thumbnail to an approved Files user."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Preview request is not allowed.", status_code=403)
        await run_in_threadpool(_request_user, request)
        context = await run_in_threadpool(_dropbox_context)
        path = dropbox_integration.normalize_dropbox_path(request.query_params.get("path") or "")
        if not path or not dropbox_integration.path_is_within_root(path, context["root_path"]):
            raise FilesUploadError("This preview is not available.", status_code=403)
        if PurePosixPath(path).suffix.casefold() not in {".jpg", ".jpeg", ".png"}:
            raise FilesUploadError("This preview is not available.", status_code=404)
        content = await run_in_threadpool(
            _thumbnail_bytes,
            context["access_token"],
            path,
            request.query_params.get("rev") or "",
        )
        return Response(
            content,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=900"},
        )
    except Exception as error:
        if isinstance(error, FilesUploadError):
            return _response_error(error)
        return Response(status_code=404)


async def desktop_helper_package(request: Request):
    """Download a credential-free helper package for the requested desktop platform."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Helper request is not allowed.", status_code=403)
        await run_in_threadpool(_request_user, request)
        platform = str(request.query_params.get("platform") or "windows").casefold()
        is_macos = platform in {"mac", "macos", "darwin"}
        helper_dir = MACOS_DESKTOP_HELPER_DIR if is_macos else DESKTOP_HELPER_DIR
        names = (
            ("Install.command", "SportsCaveFilesHelper.py", "Uninstall.command", "README.md")
            if is_macos
            else ("Install.cmd", "Install.ps1", "SportsCaveFilesHelper.ps1", "Uninstall.ps1", "README.md")
        )
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                source = helper_dir / name
                if is_macos:
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    mode = 0o755 if name.endswith((".command", ".py")) else 0o644
                    info.external_attr = (0o100000 | mode) << 16
                    archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
                else:
                    archive.writestr(name, source.read_bytes())
        filename = (
            "Sports-Cave-Files-Desktop-Helper-macOS.zip"
            if is_macos
            else "Sports-Cave-Files-Desktop-Helper.zip"
        )
        return Response(
            package.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as error:
        return _response_error(error)


async def delete_files(request: Request):
    """Move selected Dropbox items into recoverable Dropbox Deleted Files."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Delete request is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_files_delete_user, request)
        payload = await _json_body(request)
        context = await run_in_threadpool(_dropbox_context)
        paths = _validated_delete_paths(
            payload.get("paths"),
            payload.get("current_path"),
            context["root_path"],
        )
        successful = []
        failed = []
        for path in paths:
            try:
                metadata = await run_in_threadpool(
                    dropbox_integration.delete_path_recoverable,
                    context["access_token"],
                    path,
                    root_path=context["root_path"],
                )
                successful.append({"path": path, "metadata": dict(metadata or {})})
                invalidate_thumbnail_cache(path)
            except Exception:
                failed.append(
                    {
                        "path": path,
                        "message": "This item could not be removed right now.",
                    }
                )
        if successful:
            invalidate_directory_cache(payload.get("current_path"))
            actor = (
                str(user.get("display_name") or "").strip()
                or str(user.get("email") or "").strip()
                or str(user.get("username") or "").strip()
                or "Sports Cave"
            )
            await run_in_threadpool(
                record_activity_log,
                "files_moved_to_recycle_bin",
                "Files",
                f"Moved {len(successful)} item{'s' if len(successful) != 1 else ''} to Recycle Bin",
                entity_type="dropbox_folder",
                entity_id=dropbox_integration.normalize_dropbox_path(payload.get("current_path")),
                metadata={
                    "folder": dropbox_integration.normalize_dropbox_path(payload.get("current_path")),
                    "item_count": len(successful),
                    "failed_count": len(failed),
                    "paths": [item["path"] for item in successful],
                },
                actor=actor,
            )
        return JSONResponse(
            {
                "ok": True,
                "successful": successful,
                "failed": failed,
            }
        )
    except Exception as error:
        return _response_error(error)


FILES_UPLOAD_ROUTES = (
    ("/files-window", files_window_page, ("GET",)),
    ("/files-image-viewer", files_image_viewer_page, ("GET",)),
    ("/api/files-list", list_files, ("GET",)),
    ("/api/files-folder", create_files_folder, ("POST",)),
    ("/api/files-rename", rename_files_item, ("POST",)),
    ("/api/files-upload/start", start_files_upload, ("POST",)),
    ("/api/files-upload/chunk", append_files_upload_chunk, ("POST",)),
    ("/api/files-upload/status", files_upload_status, ("GET",)),
    ("/api/files-upload/remove", remove_files_upload, ("POST",)),
    ("/api/files-download", download_file, ("GET",)),
    ("/api/files-image-preview", image_preview, ("GET",)),
    ("/api/files-image-items", image_folder_items, ("GET",)),
    ("/api/files-thumbnail", file_thumbnail, ("GET",)),
    ("/api/files-desktop-helper", desktop_helper_package, ("GET",)),
    ("/api/files-delete", delete_files, ("POST",)),
)
