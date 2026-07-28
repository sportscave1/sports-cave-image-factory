import os
import io
import hashlib
import mimetypes
import secrets
import threading
import time
import zipfile
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

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
FILES_DIRECTORY_PAGE_SECONDS = 2 * 60
FILES_DIRECTORY_PAGE_SIZE = 500
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
FILES_STREAM_CHUNK_BYTES = 256 * 1024
FILES_NATIVE_TRANSFER_SECONDS = 15 * 60
FILES_NATIVE_TRANSFER_LIMIT = 100
FILES_NATIVE_TRANSFER_FILE_LIMIT = 10000


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


@dataclass
class NativeTransferRecord:
    ticket: str
    secret: str
    access_token: str
    user_id: str
    roots: list
    items: list
    created_at: float = field(default_factory=time.monotonic)
    expires_at: float = field(
        default_factory=lambda: time.monotonic() + FILES_NATIVE_TRANSFER_SECONDS
    )


class NativeTransferManager:
    """Short-lived server-side Dropbox grants for the trusted desktop shell."""

    def __init__(self):
        self._records = {}
        self._lock = threading.RLock()

    def _cleanup(self):
        now = time.monotonic()
        for ticket, record in list(self._records.items()):
            if record.expires_at <= now:
                self._records.pop(ticket, None)

    def create(self, *, access_token, root_path, user, selections):
        if not isinstance(selections, (list, tuple)) or not selections:
            raise FilesUploadError("Select at least one item.")
        if len(selections) > FILES_NATIVE_TRANSFER_LIMIT:
            raise FilesUploadError(
                f"Select no more than {FILES_NATIVE_TRANSFER_LIMIT} items at once."
            )
        clean_root = dropbox_integration.normalize_dropbox_path(root_path)
        manifest = []
        transfer_roots = []
        seen_roots = set()
        for selection in selections:
            if not isinstance(selection, dict):
                raise FilesUploadError("A selected item is invalid.", status_code=403)
            if not set(selection).issubset({"path", "id", "revision", "tag"}):
                raise FilesUploadError(
                    "A selected item is invalid.",
                    status_code=400,
                    code="invalid_arguments",
                )
            relative_path = str(selection.get("path") or "")
            full_path = _validated_relative_path(relative_path, clean_root)
            if full_path.casefold() in seen_roots:
                continue
            seen_roots.add(full_path.casefold())
            metadata = dropbox_integration.get_file_metadata(access_token, full_path)
            supplied_id = str(selection.get("id") or "")
            actual_id = str(metadata.get("id") or "")
            supplied_revision = str(selection.get("revision") or "")
            actual_revision = str(
                metadata.get("rev") or metadata.get("content_hash") or ""
            )
            if supplied_id and actual_id and not secrets.compare_digest(supplied_id, actual_id):
                raise FilesUploadError(
                    "A selected item changed. Refresh Files and try again.",
                    status_code=409,
                    code="item_changed",
                )
            if (
                supplied_revision
                and actual_revision
                and not secrets.compare_digest(supplied_revision, actual_revision)
            ):
                raise FilesUploadError(
                    "A selected item changed. Refresh Files and try again.",
                    status_code=409,
                    code="item_changed",
                )
            tag = str(metadata.get(".tag") or "file").casefold()
            root_name = str(metadata.get("name") or PurePosixPath(full_path).name)
            source_relative_path = (
                full_path[len(clean_root) :].lstrip("/")
                if clean_root
                else full_path.lstrip("/")
            )
            if not source_relative_path:
                raise FilesUploadError(
                    "The Dropbox Team Space root cannot be transferred.",
                    status_code=400,
                    code="invalid_arguments",
                )
            transfer_roots.append(
                {
                    "source_relative_path": source_relative_path,
                    "name": root_name,
                    "is_directory": tag == "folder",
                    "revision": actual_revision,
                }
            )
            if tag == "folder":
                manifest.append(
                    self._manifest_item(
                        metadata,
                        full_path,
                        root_name,
                        is_directory=True,
                    )
                )
                descendants = dropbox_integration.list_folder_recursive(
                    access_token,
                    full_path,
                    max_entries=FILES_NATIVE_TRANSFER_FILE_LIMIT,
                )
                for descendant in descendants:
                    descendant_path = dropbox_integration.normalize_dropbox_path(
                        descendant.get("path_display")
                        or descendant.get("path_lower")
                        or ""
                    )
                    if not descendant_path or not dropbox_integration.path_is_within_root(
                        descendant_path, full_path
                    ):
                        raise FilesUploadError(
                            "A selected folder returned invalid Dropbox metadata.",
                            status_code=409,
                            code="item_changed",
                        )
                    suffix = descendant_path[len(full_path) :].lstrip("/")
                    output_path = f"{root_name}/{suffix}" if suffix else root_name
                    manifest.append(
                        self._manifest_item(
                            descendant,
                            descendant_path,
                            output_path,
                            is_directory=str(
                                descendant.get(".tag") or "file"
                            ).casefold()
                            == "folder",
                        )
                    )
            else:
                manifest.append(
                    self._manifest_item(
                        metadata,
                        full_path,
                        root_name,
                        is_directory=False,
                    )
                )
        file_count = sum(not item["is_directory"] for item in manifest)
        if file_count > FILES_NATIVE_TRANSFER_FILE_LIMIT:
            raise FilesUploadError(
                "This selection contains too many files for one desktop transfer."
            )
        ticket = secrets.token_urlsafe(24)
        record = NativeTransferRecord(
            ticket=ticket,
            secret=secrets.token_urlsafe(32),
            access_token=str(access_token),
            user_id=str((user or {}).get("id") or ""),
            roots=transfer_roots,
            items=manifest,
        )
        with self._lock:
            self._cleanup()
            self._records[ticket] = record
        return record

    @staticmethod
    def _manifest_item(metadata, dropbox_path, output_path, *, is_directory):
        metadata = dict(metadata or {})
        identity = str(metadata.get("id") or dropbox_path)
        revision = str(
            metadata.get("rev")
            or metadata.get("content_hash")
            or ("folder:" + identity if is_directory else "")
        )
        item_token = secrets.token_urlsafe(18)
        cache_identity = hashlib.sha256(
            f"{identity}\0{revision}".encode("utf-8")
        ).hexdigest()
        return {
            "token": item_token,
            "dropbox_path": dropbox_path,
            "dropbox_id": str(metadata.get("id") or ""),
            "revision": revision,
            "cache_key": cache_identity,
            "relative_path": str(output_path or ""),
            "name": str(metadata.get("name") or PurePosixPath(dropbox_path).name),
            "size": 0 if is_directory else int(metadata.get("size") or 0),
            "is_directory": bool(is_directory),
        }

    def get(self, ticket, secret):
        with self._lock:
            self._cleanup()
            record = self._records.get(str(ticket or ""))
            if (
                not record
                or not secret
                or not secrets.compare_digest(record.secret, str(secret))
            ):
                raise FilesUploadError(
                    "This desktop transfer has expired.",
                    status_code=404,
                    code="transfer_expired",
                )
            return record

    def item(self, ticket, secret, item_token):
        record = self.get(ticket, secret)
        for item in record.items:
            if secrets.compare_digest(item["token"], str(item_token or "")):
                return record, item
        raise FilesUploadError(
            "This desktop transfer item is unavailable.",
            status_code=404,
            code="transfer_item_missing",
        )


NATIVE_TRANSFER_MANAGER = NativeTransferManager()
_DROPBOX_CONTEXT = {}
_DROPBOX_CONTEXT_LOCK = threading.Lock()
_THUMBNAIL_CACHE = {}
_THUMBNAIL_CACHE_LOCK = threading.Lock()
_DIRECTORY_CACHE = {}
_DIRECTORY_CACHE_LOCK = threading.Lock()
_DIRECTORY_INFLIGHT = {}
_DIRECTORY_PAGE_CURSORS = {}


def _directory_cache_key(path, *, root_path="", user_id=""):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    clean_root = dropbox_integration.normalize_dropbox_path(root_path)
    return (
        str(user_id or ""),
        clean_root.casefold(),
        clean_path.casefold(),
    )


def _directory_cache_path_from_key(key):
    if isinstance(key, tuple) and key and isinstance(key[0], tuple):
        return _directory_cache_path_from_key(key[0])
    return key[2] if isinstance(key, tuple) and len(key) >= 3 else str(key).casefold()


def _directory_cache_payload(key, now=None):
    now = time.monotonic() if now is None else now
    cached = _DIRECTORY_CACHE.get(key) or {}
    if cached.get("expires_at", 0) > now and cached.get("complete", True):
        return list(cached.get("entries") or ())
    return None


def _store_directory_cache(key, entries, *, complete=True, expires_in=None):
    ttl = FILES_DIRECTORY_CACHE_SECONDS if expires_in is None else max(1, int(expires_in))
    _DIRECTORY_CACHE[key] = {
        "entries": list(entries or ()),
        "expires_at": time.monotonic() + ttl,
        "complete": bool(complete),
    }
    while len(_DIRECTORY_CACHE) > FILES_DIRECTORY_CACHE_LIMIT:
        oldest = min(
            _DIRECTORY_CACHE,
            key=lambda candidate: _DIRECTORY_CACHE[candidate].get("expires_at", 0),
        )
        _DIRECTORY_CACHE.pop(oldest, None)


def _cache_namespace(user, root_path):
    user_id = str((user or {}).get("id") or (user or {}).get("username") or "").strip()
    root = dropbox_integration.normalize_dropbox_path(root_path)
    seed = f"{user_id}\n{root.casefold()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def invalidate_directory_cache(*paths):
    clean_paths = set()
    for path in paths:
        with suppress(Exception):
            clean_paths.add(dropbox_integration.normalize_dropbox_path(path).casefold())
    with _DIRECTORY_CACHE_LOCK:
        if not clean_paths:
            _DIRECTORY_CACHE.clear()
            _DIRECTORY_INFLIGHT.clear()
            _DIRECTORY_PAGE_CURSORS.clear()
            return
        for key in list(_DIRECTORY_CACHE):
            if _directory_cache_path_from_key(key) in clean_paths:
                _DIRECTORY_CACHE.pop(key, None)
        for key in list(_DIRECTORY_INFLIGHT):
            if _directory_cache_path_from_key(key) in clean_paths:
                _DIRECTORY_INFLIGHT.pop(key, None)
        for token, page in list(_DIRECTORY_PAGE_CURSORS.items()):
            if str((page or {}).get("path") or "").casefold() in clean_paths:
                _DIRECTORY_PAGE_CURSORS.pop(token, None)


def _directory_entries(access_token, path, *, force=False, root_path="", user_id=""):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    cache_key = _directory_cache_key(clean_path, root_path=root_path, user_id=user_id)
    now = time.monotonic()
    wait_for = None
    owns_request = False
    with _DIRECTORY_CACHE_LOCK:
        cached = None if force else _directory_cache_payload(cache_key, now)
        if cached is not None:
            return cached
        if not force:
            wait_for = _DIRECTORY_INFLIGHT.get(cache_key)
            if wait_for is None:
                wait_for = threading.Event()
                _DIRECTORY_INFLIGHT[cache_key] = wait_for
                owns_request = True
        else:
            _DIRECTORY_INFLIGHT.pop(cache_key, None)
    if wait_for is not None and not owns_request:
        wait_for.wait(timeout=15)
        with _DIRECTORY_CACHE_LOCK:
            cached = _directory_cache_payload(cache_key)
            if cached is not None:
                return cached
    try:
        entries = dropbox_integration.sort_folder_entries(
            dropbox_integration.list_folder(access_token, clean_path)
        )
    except Exception:
        with _DIRECTORY_CACHE_LOCK:
            pending = _DIRECTORY_INFLIGHT.pop(cache_key, None)
            if pending is not None:
                pending.set()
        raise
    with _DIRECTORY_CACHE_LOCK:
        _store_directory_cache(cache_key, entries, complete=True)
        pending = _DIRECTORY_INFLIGHT.pop(cache_key, None)
        if pending is not None:
            pending.set()
    return list(entries)


def _directory_page(access_token, path, *, root_path, user_id, force=False, page_token="", limit=None):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    cache_key = _directory_cache_key(clean_path, root_path=root_path, user_id=user_id)
    page_limit = max(1, min(int(limit or FILES_DIRECTORY_PAGE_SIZE), 2000))
    now = time.monotonic()
    cursor = ""
    if page_token:
        with _DIRECTORY_CACHE_LOCK:
            page = _DIRECTORY_PAGE_CURSORS.get(str(page_token or "")) or {}
            if (
                page.get("expires_at", 0) <= now
                or page.get("key") != cache_key
            ):
                raise FilesUploadError(
                    "This folder page expired. Refresh the folder and try again.",
                    status_code=409,
                    code="folder_page_expired",
                )
            cursor = str(page.get("cursor") or "")
    elif not force:
        with _DIRECTORY_CACHE_LOCK:
            cached = _directory_cache_payload(cache_key, now)
            if cached is not None:
                return {
                    "entries": cached,
                    "cursor": "",
                    "page_token": "",
                    "has_more": False,
                    "from_cache": True,
                    "complete": True,
                }
            partial = _DIRECTORY_CACHE.get(cache_key) or {}
            if partial.get("expires_at", 0) > time.monotonic() and partial.get("entries"):
                return {
                    "entries": list(partial.get("entries") or ()),
                    "cursor": "",
                    "page_token": str(partial.get("next_page") or ""),
                    "has_more": bool(partial.get("has_more")),
                    "from_cache": True,
                    "complete": bool(partial.get("complete", False)),
                }

    request_key = (cache_key, cursor or "first", page_limit)
    wait_for = None
    owns_request = False
    with _DIRECTORY_CACHE_LOCK:
        if not force:
            wait_for = _DIRECTORY_INFLIGHT.get(request_key)
            if wait_for is None:
                wait_for = threading.Event()
                _DIRECTORY_INFLIGHT[request_key] = wait_for
                owns_request = True
        else:
            _DIRECTORY_INFLIGHT.pop(request_key, None)
    if wait_for is not None and not owns_request:
        wait_for.wait(timeout=15)
        with _DIRECTORY_CACHE_LOCK:
            cached = _directory_cache_payload(cache_key)
            if cached is not None:
                return {
                    "entries": cached,
                    "cursor": "",
                    "page_token": "",
                    "has_more": False,
                    "from_cache": True,
                    "complete": True,
                }

    try:
        page = dropbox_integration.list_folder_page(
            access_token,
            clean_path,
            cursor=cursor,
            limit=page_limit,
        )
        page_entries = list(page.get("entries") or ())
        has_more = bool(page.get("has_more"))
        next_cursor = str(page.get("cursor") or "")
        with _DIRECTORY_CACHE_LOCK:
            previous = [] if (force and not page_token) else list((_DIRECTORY_CACHE.get(cache_key) or {}).get("entries") or ())
            combined = previous + page_entries if page_token else page_entries
            next_token = ""
            if has_more and next_cursor:
                next_token = secrets.token_urlsafe(18)
                _DIRECTORY_PAGE_CURSORS[next_token] = {
                    "cursor": next_cursor,
                    "key": cache_key,
                    "path": clean_path.casefold(),
                    "expires_at": time.monotonic() + FILES_DIRECTORY_PAGE_SECONDS,
                }
            for token, cursor_record in list(_DIRECTORY_PAGE_CURSORS.items()):
                if cursor_record.get("expires_at", 0) <= time.monotonic():
                    _DIRECTORY_PAGE_CURSORS.pop(token, None)
            _store_directory_cache(
                cache_key,
                combined,
                complete=not has_more,
                expires_in=FILES_DIRECTORY_CACHE_SECONDS if not has_more else FILES_DIRECTORY_PAGE_SECONDS,
            )
            _DIRECTORY_CACHE[cache_key]["next_page"] = next_token
            _DIRECTORY_CACHE[cache_key]["has_more"] = has_more
            pending = _DIRECTORY_INFLIGHT.pop(request_key, None)
            if pending is not None:
                pending.set()
        return {
            "entries": combined,
            "cursor": next_cursor if has_more else "",
            "page_token": next_token,
            "has_more": has_more,
            "from_cache": False,
            "complete": not has_more,
        }
    except Exception:
        with _DIRECTORY_CACHE_LOCK:
            pending = _DIRECTORY_INFLIGHT.pop(request_key, None)
            if pending is not None:
                pending.set()
        raise


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


def _validated_relative_folder(relative_path, root_path):
    if relative_path in {None, ""}:
        return dropbox_integration.normalize_dropbox_path(root_path)
    return _validated_relative_path(relative_path, root_path)


def _validated_transfer_paths(paths, destination, root_path):
    if not isinstance(paths, (list, tuple)) or not paths:
        raise FilesUploadError("Select at least one item.")
    if len(paths) > 100:
        raise FilesUploadError("Select no more than 100 items at once.")
    clean_destination = _validated_relative_folder(destination, root_path)
    clean_sources = []
    for relative_path in paths:
        source = _validated_relative_path(relative_path, root_path)
        source_key = source.casefold()
        destination_key = clean_destination.casefold()
        if destination_key == source_key or destination_key.startswith(f"{source_key}/"):
            raise FilesUploadError(
                "A folder cannot be pasted into itself or one of its subfolders.",
                status_code=409,
                code="invalid_destination",
            )
        if source not in clean_sources:
            clean_sources.append(source)
    return clean_sources, clean_destination


def _paste_plan(access_token, sources, destination, *, operation, conflict):
    mode = str(operation or "copy").casefold()
    policy = str(conflict or "prompt").casefold().replace(" ", "_")
    if mode not in {"copy", "move"}:
        raise FilesUploadError("This clipboard operation is not available.")
    if policy not in {"prompt", "replace", "skip", "keep_both"}:
        raise FilesUploadError("This conflict choice is not available.")
    plan = []
    conflicts = []
    skipped = []
    for source in sources:
        source_metadata = dropbox_integration.get_file_metadata(access_token, source)
        name = str(source_metadata.get("name") or PurePosixPath(source).name)
        target = dropbox_integration.normalize_dropbox_path(f"{destination}/{name}")
        if mode == "move" and target.casefold() == source.casefold():
            skipped.append({"source_path": source, "name": name, "reason": "same_folder"})
            continue
        existing = dropbox_integration.get_metadata_if_exists(access_token, target)
        if existing:
            conflict_item = {
                "source_path": source,
                "destination_path": target,
                "name": name,
                "source_type": str(source_metadata.get(".tag") or "file"),
                "destination_type": str(existing.get(".tag") or "file"),
            }
            conflicts.append(conflict_item)
            if policy == "prompt":
                continue
            if policy == "skip":
                skipped.append({**conflict_item, "reason": "conflict"})
                continue
            if policy == "keep_both":
                target = dropbox_integration.windows_numbered_path(access_token, target)
        plan.append(
            {
                "source_path": source,
                "destination_path": target,
                "name": name,
                "replace": bool(existing and policy == "replace"),
            }
        )
    if conflicts and policy == "prompt":
        raise FilesUploadError(
            "One or more items already exist in this folder.",
            status_code=409,
            code="paste_conflict",
            details={"conflicts": conflicts},
        )
    return plan, skipped


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


def _files_timezone_name(user):
    timezone_name = str(os_accounts.timezone_for_user(user or {}) or "").strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"
    return timezone_name


def _parse_dropbox_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        clean_value = str(value or "").strip()
        if not clean_value:
            return None
        try:
            parsed = datetime.fromisoformat(clean_value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_timestamp(value):
    parsed = _parse_dropbox_timestamp(value)
    if not parsed:
        return ""
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _format_files_timestamp(value, timezone_name, *, include_zone=False):
    parsed = _parse_dropbox_timestamp(value)
    if not parsed:
        return "-"
    try:
        local_value = parsed.astimezone(ZoneInfo(str(timezone_name or "UTC")))
    except (ZoneInfoNotFoundError, ValueError):
        local_value = parsed
        timezone_name = "UTC"
    hour = local_value.strftime("%I").lstrip("0") or "0"
    label = (
        f"{local_value.day} {local_value.strftime('%b %Y')}, "
        f"{hour}:{local_value.strftime('%M %p')}"
    )
    if not include_zone:
        return label
    zone_label = "PHT" if timezone_name == "Asia/Manila" else str(local_value.tzname() or "UTC")
    return f"{label} {zone_label}"


def _file_tooltip_type_label(name, tag):
    if str(tag or "").casefold() == "folder":
        return "File folder"
    extension = PurePosixPath(str(name or "")).suffix.lstrip(".").upper()
    return f"{extension} File" if extension else "File"


def _tooltip_size_label(size):
    value = max(0, int(size or 0))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{value} B"


def _cached_dimensions(entry):
    dimensions = entry.get("dimensions")
    if isinstance(dimensions, dict):
        width = dimensions.get("width")
        height = dimensions.get("height")
    elif isinstance(dimensions, (list, tuple)) and len(dimensions) >= 2:
        width, height = dimensions[:2]
    else:
        width = entry.get("image_width") or entry.get("thumbnail_width")
        height = entry.get("image_height") or entry.get("thumbnail_height")
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {"width": width, "height": height}


def _public_file_item(entry, root_path, *, timezone_name="UTC"):
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
    modified = _utc_timestamp(entry.get("server_modified")) if tag != "folder" else ""
    latest_activity = ""
    if tag == "folder":
        latest_activity = _utc_timestamp(
            entry.get("latest_known_activity")
            or entry.get("latest_activity")
            or entry.get("activity_timestamp")
        )
    item = {
        "id": str(entry.get("id") or ""),
        "path": path,
        "desktop_relative_path": relative_path,
        "name": name,
        "tag": tag,
        "kind": _file_kind(name, tag),
        "extension": extension.lstrip("."),
        "type": _file_type_label(name, tag),
        "size": int(entry.get("size") or 0) if tag != "folder" else 0,
        "size_label": "" if tag == "folder" else dropbox_integration.format_file_size(entry.get("size")),
        "tooltip_size_label": "" if tag == "folder" else _tooltip_size_label(entry.get("size")),
        "modified": modified,
        "modified_label": _format_files_timestamp(modified, timezone_name),
        "modified_tooltip_label": _format_files_timestamp(
            modified,
            timezone_name,
            include_zone=True,
        ),
        "latest_activity": latest_activity,
        "latest_activity_tooltip_label": _format_files_timestamp(
            latest_activity,
            timezone_name,
            include_zone=True,
        ),
        "tooltip_type": _file_tooltip_type_label(name, tag),
        "status": "Online",
        "protected": path.casefold() == clean_root.casefold(),
        "revision": revision,
    }
    dimensions = _cached_dimensions(entry) if item["kind"] == "image" else None
    if dimensions:
        item["dimensions"] = dimensions
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


def _stream_upstream_response(upstream):
    try:
        iterator = getattr(upstream, "iter_content", None)
        if callable(iterator):
            for chunk in iterator(chunk_size=FILES_STREAM_CHUNK_BYTES):
                if chunk:
                    yield bytes(chunk)
        else:
            content = bytes(getattr(upstream, "content", b"") or b"")
            if content:
                yield content
    finally:
        close = getattr(upstream, "close", None)
        if callable(close):
            close()


def _content_disposition(disposition, filename):
    clean_name = str(filename or "download").replace("\r", "").replace("\n", "")
    ascii_name = clean_name.encode("ascii", "ignore").decode("ascii").replace('"', "'")
    ascii_name = ascii_name or "download"
    return (
        f'{disposition}; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(clean_name, safe='')}"
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
        page_size = request.query_params.get("page_size")
        page_token = str(request.query_params.get("page") or "").strip()
        user_id = str(user.get("id") or user.get("username") or "")
        try:
            if page_size or page_token:
                page = await run_in_threadpool(
                    _directory_page,
                    context["access_token"],
                    current_path,
                    root_path=context["root_path"],
                    user_id=user_id,
                    force=force,
                    page_token=page_token,
                    limit=page_size,
                )
                entries = page["entries"]
            else:
                page = {
                    "has_more": False,
                    "page_token": "",
                    "from_cache": False,
                    "complete": True,
                }
                entries = await run_in_threadpool(
                    _directory_entries,
                    context["access_token"],
                    current_path,
                    force=force,
                    root_path=context["root_path"],
                    user_id=user_id,
                )
        except Exception:
            context = await run_in_threadpool(_dropbox_context, force=True)
            current_path = _validated_current_folder(current_path, context["root_path"])
            if page_size or page_token:
                page = await run_in_threadpool(
                    _directory_page,
                    context["access_token"],
                    current_path,
                    root_path=context["root_path"],
                    user_id=user_id,
                    force=True,
                    page_token=page_token,
                    limit=page_size,
                )
                entries = page["entries"]
            else:
                page = {
                    "has_more": False,
                    "page_token": "",
                    "from_cache": False,
                    "complete": True,
                }
                entries = await run_in_threadpool(
                    _directory_entries,
                    context["access_token"],
                    current_path,
                    force=True,
                    root_path=context["root_path"],
                    user_id=user_id,
                )
        timezone_name = _files_timezone_name(user)
        items = [
            item
            for item in (
                _public_file_item(
                    entry,
                    context["root_path"],
                    timezone_name=timezone_name,
                )
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
                "timezone": timezone_name,
                "can_delete": bool(os_accounts.can_delete_files(user)),
                "cached_for_seconds": FILES_DIRECTORY_CACHE_SECONDS,
                "cache_namespace": _cache_namespace(user, context["root_path"]),
                "has_more": bool(page.get("has_more")),
                "next_page": str(page.get("page_token") or ""),
                "from_cache": bool(page.get("from_cache")),
                "complete": bool(page.get("complete", True)),
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
        user = await run_in_threadpool(_request_user, request)
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
        await run_in_threadpool(
            record_activity_log,
            "files_downloaded",
            "Files",
            f"Downloaded file: {PurePosixPath(path).name}",
            entity_type="dropbox_file",
            entity_id=path,
            metadata={"filename": PurePosixPath(path).name},
            actor=_activity_actor(user),
        )
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
        metadata, upstream = await run_in_threadpool(
            dropbox_integration.get_file_response,
            context["access_token"],
            path,
        )
        if str(metadata.get(".tag") or "file").casefold() == "folder":
            upstream.close()
            raise FilesUploadError("This preview is not available.", status_code=404)
        if int(metadata.get("size") or 0) > FILES_IMAGE_PREVIEW_MAX_BYTES:
            upstream.close()
            raise FilesUploadError(
                "This image is too large for browser preview. Open it in the desktop app instead.",
                status_code=413,
            )
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        filename = PurePosixPath(path).name

        return StreamingResponse(
            _stream_upstream_response(upstream),
            media_type=media_type,
            headers={
                "Cache-Control": "private, max-age=300",
                "Content-Disposition": _content_disposition("inline", filename),
                "Content-Length": str(int(metadata.get("size") or 0)),
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


async def create_native_transfer(request: Request):
    """Issue a short-lived Dropbox transfer grant to the trusted desktop shell."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Desktop transfer is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_user, request)
        payload = await _json_body(request)
        if set(payload) != {"items"}:
            raise FilesUploadError(
                "Desktop transfer request is invalid.",
                status_code=400,
                code="invalid_arguments",
            )
        context = await run_in_threadpool(_dropbox_context)
        record = await run_in_threadpool(
            NATIVE_TRANSFER_MANAGER.create,
            access_token=context["access_token"],
            root_path=context["root_path"],
            user=user,
            selections=payload.get("items"),
        )
        return JSONResponse(
            {
                "ok": True,
                "ticket": record.ticket,
                "secret": record.secret,
                "expires_in": FILES_NATIVE_TRANSFER_SECONDS,
                "item_count": len(record.items),
                "file_count": sum(
                    not item["is_directory"] for item in record.items
                ),
                "total_bytes": sum(item["size"] for item in record.items),
            },
            headers={"Cache-Control": "no-store"},
        )
    except Exception as error:
        return _response_error(error)


def _native_transfer_secret(request):
    return str(request.headers.get("x-sports-cave-transfer-secret") or "")


async def native_transfer_manifest(request: Request):
    """Return only the validated manifest attached to one transfer grant."""
    try:
        record = NATIVE_TRANSFER_MANAGER.get(
            request.query_params.get("ticket"),
            _native_transfer_secret(request),
        )
        public_items = [
            {
                key: item[key]
                for key in (
                    "token",
                    "cache_key",
                    "relative_path",
                    "name",
                    "size",
                    "is_directory",
                    "revision",
                )
            }
            for item in record.items
        ]
        public_roots = [
            {
                key: item[key]
                for key in (
                    "source_relative_path",
                    "name",
                    "is_directory",
                    "revision",
                )
            }
            for item in record.roots
        ]
        return JSONResponse(
            {
                "ok": True,
                "ticket": record.ticket,
                "roots": public_roots,
                "items": public_items,
                "total_bytes": sum(item["size"] for item in record.items),
            },
            headers={"Cache-Control": "no-store"},
        )
    except Exception as error:
        return _response_error(error)


async def native_transfer_content(request: Request):
    """Stream one ticketed Dropbox file without exposing Dropbox credentials."""
    upstream = None
    try:
        record, item = NATIVE_TRANSFER_MANAGER.item(
            request.query_params.get("ticket"),
            _native_transfer_secret(request),
            request.query_params.get("item"),
        )
        if item["is_directory"]:
            raise FilesUploadError(
                "Folders do not have downloadable content.",
                status_code=400,
                code="transfer_item_invalid",
            )
        metadata, upstream = await run_in_threadpool(
            dropbox_integration.get_file_response,
            record.access_token,
            item["dropbox_path"],
        )
        current_id = str(metadata.get("id") or "")
        current_revision = str(metadata.get("rev") or metadata.get("content_hash") or "")
        if (
            item["dropbox_id"]
            and current_id
            and not secrets.compare_digest(item["dropbox_id"], current_id)
        ) or (
            item["revision"]
            and current_revision
            and not secrets.compare_digest(item["revision"], current_revision)
        ):
            upstream.close()
            upstream = None
            raise FilesUploadError(
                "This Dropbox file changed during transfer. Refresh Files and try again.",
                status_code=409,
                code="item_changed",
            )
        return StreamingResponse(
            _stream_upstream_response(upstream),
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": _content_disposition("attachment", item["name"]),
                "Content-Length": str(int(metadata.get("size") or item["size"] or 0)),
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as error:
        if upstream is not None:
            with suppress(Exception):
                upstream.close()
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
        names = list(
            ("Install.command", "SportsCaveFilesHelper.py", "Uninstall.command", "README.md")
            if is_macos
            else (
                "Install.cmd",
                "Install.ps1",
                "SportsCaveFiles.ico",
                "SportsCaveFilesDesktop.cs",
                "SportsCaveFilesHelper.ps1",
                "Uninstall.ps1",
                "README.md",
            )
        )
        if not is_macos:
            names.extend(
                str(path.relative_to(helper_dir)).replace("\\", "/")
                for path in sorted((helper_dir / "lib").glob("*.dll"))
            )
            names.extend(
                str(path.relative_to(helper_dir)).replace("\\", "/")
                for path in sorted((helper_dir / "runtimes").rglob("*.dll"))
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


async def paste_files(request: Request):
    """Copy or move selected Dropbox items into one approved destination folder."""
    try:
        if not _same_origin(request):
            raise FilesUploadError("Paste request is not allowed.", status_code=403)
        user = await run_in_threadpool(_request_user, request)
        payload = await _json_body(request)
        context = await run_in_threadpool(_dropbox_context)
        sources, destination = _validated_transfer_paths(
            payload.get("paths"),
            payload.get("destination"),
            context["root_path"],
        )
        operation = str(payload.get("operation") or "copy").casefold()
        plan, skipped = await run_in_threadpool(
            _paste_plan,
            context["access_token"],
            sources,
            destination,
            operation=operation,
            conflict=payload.get("conflict") or "prompt",
        )
        successful = []
        failed = []
        transfer = (
            dropbox_integration.move_path
            if operation == "move"
            else dropbox_integration.copy_path
        )
        for item in plan:
            try:
                if item["replace"]:
                    metadata = await run_in_threadpool(
                        dropbox_integration.replace_path,
                        context["access_token"],
                        item["source_path"],
                        item["destination_path"],
                        operation=operation,
                        root_path=context["root_path"],
                    )
                else:
                    metadata = await run_in_threadpool(
                        transfer,
                        context["access_token"],
                        item["source_path"],
                        item["destination_path"],
                        root_path=context["root_path"],
                    )
                successful.append(
                    {
                        "source_path": item["source_path"],
                        "destination_path": item["destination_path"],
                        "item": _public_file_item(metadata, context["root_path"]),
                    }
                )
                invalidate_thumbnail_cache(item["source_path"], item["destination_path"])
            except Exception:
                failed.append(
                    {
                        "source_path": item["source_path"],
                        "destination_path": item["destination_path"],
                        "message": "This item could not be pasted right now.",
                    }
                )
        source_folders = {path.rsplit("/", 1)[0] for path in sources}
        invalidate_directory_cache(destination, *source_folders)
        if successful:
            await run_in_threadpool(
                record_activity_log,
                "files_items_moved" if operation == "move" else "files_items_copied",
                "Files",
                f"{'Moved' if operation == 'move' else 'Copied'} {len(successful)} item{'s' if len(successful) != 1 else ''}",
                entity_type="dropbox_folder",
                entity_id=destination,
                metadata={
                    "destination": destination,
                    "item_count": len(successful),
                    "failed_count": len(failed),
                },
                actor=_activity_actor(user),
            )
        return JSONResponse(
            {
                "ok": True,
                "operation": operation,
                "successful": successful,
                "skipped": skipped,
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
    ("/api/files-native-transfer", create_native_transfer, ("POST",)),
    ("/api/files-native-transfer/manifest", native_transfer_manifest, ("GET",)),
    ("/api/files-native-transfer/content", native_transfer_content, ("GET",)),
    ("/api/files-thumbnail", file_thumbnail, ("GET",)),
    ("/api/files-desktop-helper", desktop_helper_package, ("GET",)),
    ("/api/files-delete", delete_files, ("POST",)),
    ("/api/files-paste", paste_files, ("POST",)),
)
