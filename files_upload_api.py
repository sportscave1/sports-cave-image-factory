import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from activity_log import record_activity_log
import dropbox_integration
import os_accounts
import sc_auth


FILES_UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
FILES_UPLOAD_SESSION_SECONDS = 6 * 60 * 60


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


def _same_origin(request):
    origin = str(request.headers.get("origin") or "").strip()
    if not origin:
        return True
    return origin.rstrip("/") == str(request.base_url).rstrip("/")


async def _json_body(request):
    try:
        return dict(await request.json())
    except Exception as error:
        raise FilesUploadError("Upload request is invalid.") from error


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
        {"ok": False, "code": "upload_unavailable", "message": "Upload is unavailable right now."},
        status_code=503,
    )


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
        path = dropbox_integration.normalize_dropbox_path(request.query_params.get("path") or "")
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
            except Exception:
                failed.append(
                    {
                        "path": path,
                        "message": "This item could not be removed right now.",
                    }
                )
        if successful:
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
    ("/api/files-upload/start", start_files_upload, ("POST",)),
    ("/api/files-upload/chunk", append_files_upload_chunk, ("POST",)),
    ("/api/files-upload/status", files_upload_status, ("GET",)),
    ("/api/files-upload/remove", remove_files_upload, ("POST",)),
    ("/api/files-download", download_file, ("GET",)),
    ("/api/files-delete", delete_files, ("POST",)),
)
