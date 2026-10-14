"""Private, demand-driven Files derivatives. No original or credential is persisted.

Disabled until an explicitly private existing R2 bucket and encryption key are
configured. This module never changes bucket policy or any shared automation.
"""
import base64
import hashlib
import io
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import PurePosixPath

import dropbox_integration as dbx

VERSION = "v3-jpeg-1600x1200-256x256-1"
PREFIX = "files-previews/"
MAX_OBJECT = 4 * 1024 * 1024
MAX_SOURCE = 100 * 1024 * 1024
MAX_OBJECTS = 256  # <= 1 GiB, including encrypted bundles; one serial writer
TTL = 30 * 86400
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="files-preview")
_slots = threading.BoundedSemaphore(8)
_pending = set()
_fast = {}  # Brief provider representations while the durable job is pending.
_failed = {}  # Stop browser polling from repeating a source download after storage failure.
_lock = threading.Lock()


class PreviewError(Exception):
    def __init__(self, message, status=404):
        super().__init__(message)
        self.status = status


def configured():
    return (os.getenv("FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED") == "1"
            and bool(os.getenv("FILES_PREVIEW_BUCKET"))
            and bool(os.getenv("FILES_PREVIEW_NAMESPACE"))
            and bool(os.getenv("FILES_PREVIEW_ENCRYPTION_KEY")))


def _missing(error):
    return str(getattr(error, "response", {}).get("Error", {}).get("Code")) in {"NoSuchKey", "404"}


class Store:
    def __init__(self):
        from services.r2_storage import get_r2_client
        from cryptography.fernet import Fernet
        self.client = get_r2_client()
        self.bucket = os.environ["FILES_PREVIEW_BUCKET"]
        self.cipher = Fernet(os.environ["FILES_PREVIEW_ENCRYPTION_KEY"].encode())
        # Namespace prevents collisions between installations sharing a bucket.
        self.prefix = PREFIX + hashlib.sha256(os.environ["FILES_PREVIEW_NAMESPACE"].encode()).hexdigest() + "/"

    def read(self, key):
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self.prefix + key)
        except Exception as error:
            if _missing(error):
                return None
            raise
        body = obj["Body"]
        try:
            data = body.read(MAX_OBJECT + 1)
            if len(data) > MAX_OBJECT:
                raise PreviewError("Preview cache entry exceeds its size limit.", 503)
            value = json.loads(self.cipher.decrypt(data))
            return value if value["expires"] > time.time() else None
        finally:
            body.close()

    def write(self, key, value):
        data = self.cipher.encrypt(json.dumps(value, separators=(",", ":")).encode())
        if len(data) > MAX_OBJECT:
            raise PreviewError("Prepared preview exceeds its size limit.")
        self.client.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=data,
                               ContentType="application/octet-stream", CacheControl="no-store")

    def lease(self):
        """One conditional lease across instances bounds decoding and storage races."""
        key = self.prefix + "preparation.lock"
        condition = {"IfNoneMatch": "*"}
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            try:
                value = json.loads(obj["Body"].read(4096))
            finally:
                obj["Body"].close()
            if value["expires"] > time.time():
                return None
            condition = {"IfMatch": obj["ETag"]}
        except Exception as error:
            if not _missing(error):
                raise
        try:
            result = self.client.put_object(Bucket=self.bucket, Key=key,
                Body=json.dumps({"expires": time.time() + 600, "nonce": secrets.token_hex(16)}).encode(),
                **condition)
            return result["ETag"]
        except Exception as error:
            if str(getattr(error, "response", {}).get("Error", {}).get("Code")) in {"PreconditionFailed", "412", "ConditionalRequestConflict"}:
                return None
            raise

    def release(self, etag):
        # Conditional replacement cannot release a newer worker's lease.
        self.client.put_object(Bucket=self.bucket, Key=self.prefix + "preparation.lock",
                               Body=b'{"expires":0}', IfMatch=etag)

    def renew(self, etag):
        return self.client.put_object(Bucket=self.bucket, Key=self.prefix + "preparation.lock",
            Body=json.dumps({"expires":time.time()+600,"nonce":secrets.token_hex(16)}).encode(),
            IfMatch=etag)["ETag"]

    def cleanup(self, renew=lambda: None):
        entries = []
        args = {"Bucket": self.bucket, "Prefix": self.prefix + "assets/"}
        while True:
            renew()
            page = self.client.list_objects_v2(**args)
            entries.extend(page.get("Contents", []))
            if not page.get("IsTruncated"):
                break
            args["ContinuationToken"] = page["NextContinuationToken"]
        entries.sort(key=lambda entry: entry["LastModified"])
        # Reserve one slot before writing. Only our exact version/namespace is touched.
        for index, entry in enumerate(entries):
            if index < len(entries) - MAX_OBJECTS + 1 or entry["LastModified"].timestamp() < time.time() - TTL:
                renew()
                self.client.delete_object(Bucket=self.bucket, Key=entry["Key"])


@lru_cache(maxsize=2)
def _store_for_configuration(fingerprint):
    # Reuse the SDK connection pool. Configuration rotation gets a new client;
    # the digest contains no recoverable credentials and is never logged.
    return Store()


def current_store():
    names = ("R2_ENDPOINT", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
             "FILES_PREVIEW_BUCKET", "FILES_PREVIEW_NAMESPACE", "FILES_PREVIEW_ENCRYPTION_KEY")
    fingerprint = hashlib.sha256(json.dumps([os.getenv(name, "") for name in names]).encode()).hexdigest()
    return _store_for_configuration(fingerprint)


def verified(token, path, root, revision):
    meta = dbx.get_file_metadata(token, path)
    actual = meta.get("path_display") or meta.get("path_lower") or ""
    if (meta.get(".tag") != "file" or not meta.get("id", "").startswith("id:")
            or not meta.get("rev") or not actual or not dbx.path_is_within_root(actual, root)
            or actual.casefold() != path.casefold()):
        raise PreviewError("This file is not available.", 403)
    if revision and meta["rev"] != revision:
        raise PreviewError("The file changed. Refresh the folder to view its current revision.", 409)
    return meta


def asset_key(user_id, root, meta):
    if not user_id:
        raise PreviewError("Files access is required.", 403)
    identity = json.dumps([os.getenv("FILES_PREVIEW_NAMESPACE"), os.getenv("FILES_PREVIEW_BUCKET"),
                           user_id, root.casefold(), meta["id"], meta["rev"], VERSION])
    return "assets/" + VERSION + "/" + hashlib.sha256(identity.encode()).hexdigest()


def _bounded_response(response, destination, limit, deadline):
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=256 * 1024):
            total += len(chunk)
            if total > limit or time.monotonic() > deadline:
                raise PreviewError("Preview preparation exceeded its safe transfer limit.")
            destination.write(chunk)
    finally:
        response.close()
    return total


def _same_revision(actual, expected):
    if actual.get("id") != expected["id"] or actual.get("rev") != expected["rev"]:
        raise PreviewError("The source changed during preparation.", 409)


def _provider_preview(token, meta):
    sdk = dbx._dropbox_sdk()
    actual, response = dbx.team_space_client(token).files_get_thumbnail(
        meta["id"], format=sdk.files.ThumbnailFormat("jpeg"),
        size=sdk.files.ThumbnailSize("w1024h768"), mode=sdk.files.ThumbnailMode("bestfit"))
    try:
        _same_revision(dbx._metadata_to_dict(actual), meta)
    except Exception:
        response.close()
        raise
    output = io.BytesIO()
    _bounded_response(response, output, 4 * 1024 * 1024, time.monotonic() + 60)
    if not output.tell():
        raise PreviewError("A lightweight preview is unavailable.")
    return output.getvalue()


def prepare(token, meta, allow_original, prefetched=None, skip_provider=False):
    """Provider preview first. PSD layers are never downloaded or interpreted."""
    from PIL import Image, ImageOps
    source = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024)
    try:
        try:
            if skip_provider and prefetched is None:
                raise PreviewError("Provider representation is unavailable.")
            source.write(prefetched if prefetched is not None else _provider_preview(token, meta))
        except Exception:
            extension = PurePosixPath(meta.get("name", "")).suffix.lower()
            if not allow_original or extension not in {".jpg", ".jpeg", ".png", ".webp"} or not 0 < int(meta.get("size", 0)) <= MAX_SOURCE:
                raise PreviewError("A lightweight preview is unavailable. Use Download.")
            source.seek(0); source.truncate()
            actual, response = dbx.get_psd_file_response(token, meta["id"], meta["rev"])
            try:
                _same_revision(actual, meta)
            except Exception:
                response.close()
                raise
            received = _bounded_response(response, source, meta["size"], time.monotonic() + 120)
            if received != meta["size"]:
                raise PreviewError("The source transfer was incomplete.")
        source.seek(0)
        with Image.open(source) as original:
            limit = 80_000_000 if original.format == "JPEG" else 32_000_000
            if original.format not in {"JPEG", "PNG", "WEBP"} or original.width * original.height > limit:
                raise PreviewError("This artwork exceeds safe preview decoding limits. Use Download.")
            original.draft("RGB", (1600, 1200))
            original.thumbnail((1600, 1200))
            screen = ImageOps.exif_transpose(original).convert("RGBA")
            background = Image.new("RGB", screen.size, "white")
            background.paste(screen, mask=screen.getchannel("A"))
            result = {}
            for name, bounds in [("screen", (1600, 1200)), ("small", (256, 256))]:
                background.thumbnail(bounds)
                output = io.BytesIO()
                background.save(output, "JPEG", quality=86)
                result[name] = base64.b64encode(output.getvalue()).decode()
            return result
    finally:
        source.close()


def _job(store, key, token, meta, allow_original, prefetched=None, skip_provider=False):
    etag = None
    try:
        etag = store.lease()
        if not etag:
            return
        existing = store.read(key)
        if existing and not (existing.get("thumbnail_only") and allow_original):
            return
        started = time.monotonic()
        try:
            assets = prepare(token, meta, allow_original, prefetched, skip_provider)
            value = {"assets": assets, "expires": time.time() + TTL,
                     "preparation_ms": round((time.monotonic()-started)*1000, 1)}
        except Exception:
            # Short negative cache; no source details or credentials persisted.
            value = {"unavailable": True, "thumbnail_only": not allow_original,
                     "expires": time.time() + 30}
        if time.monotonic() - started > 480:
            return  # Never publish past the lease's safety margin.
        def renew():
            nonlocal etag
            etag = store.renew(etag)
        store.cleanup(renew)
        renew()
        store.write(key, value)
        logging.getLogger(__name__).info("FILES_PREVIEW prepared outcome=%s duration_ms=%.1f",
            "unavailable" if value.get("unavailable") else "ready", (time.monotonic()-started)*1000)
    except Exception as error:
        # A failed optional job does not affect original download/file operations.
        logging.getLogger(__name__).warning("FILES_PREVIEW preparation failed type=%s", type(error).__name__)
        with _lock:
            _failed[key] = time.monotonic()+30
            while len(_failed)>128:
                _failed.pop(next(iter(_failed)))
    finally:
        if etag:
            try:
                store.release(etag)
            except Exception:
                pass
        with _lock:
            _pending.discard(key)
        _slots.release()


def request_preview(token, path, *, root, user_id, revision, representation):
    """Called only after current session/Files authorization. Recheck source on every read."""
    started = time.perf_counter()
    meta = verified(token, path, root, revision)
    metadata_ms = (time.perf_counter() - started) * 1000
    store = current_store()
    key = asset_key(user_id, root, meta)
    with _lock:
        fast = _fast.get(key)
        if representation == "screen" and fast and fast[0] > time.monotonic():
            return fast[1], f'metadata;dur={metadata_ms:.1f}, storage;dur=0'
        if _failed.get(key, 0) > time.monotonic():
            raise PreviewError("Preview preparation failed. Retry shortly or use Download.", 503)
    started = time.perf_counter()
    cached = store.read(key)
    storage_ms = (time.perf_counter() - started) * 1000
    timing = f'metadata;dur={metadata_ms:.1f}, storage;dur={storage_ms:.1f}'
    if cached and not (cached.get("thumbnail_only") and representation == "screen"):
        if cached.get("unavailable"):
            raise PreviewError("A lightweight preview is unavailable. Use Download.")
        return base64.b64decode(cached["assets"][representation], validate=True), timing
    if representation == "small":
        # Do not fill the preparation queue by scrolling. The caller uses V2's
        # visible-first provider thumbnail path until a selected file is prepared.
        return None, timing
    with _lock:
        if key in _pending or not _slots.acquire(blocking=False):
            return None, timing
        _pending.add(key)
    # Preserve the fast provider path: do not add a polling interval when Dropbox
    # already has a representation. Pass those same bytes to the persistence job.
    started = time.perf_counter()
    try:
        prefetched = _provider_preview(token, meta)
    except Exception:
        prefetched = None
    timing += f', provider;dur={(time.perf_counter()-started)*1000:.1f}'
    if prefetched:
        with _lock:
            _fast.pop(key, None)
            _fast[key] = (time.monotonic()+30, prefetched)
            while len(_fast)>128 or sum(len(v[1]) for v in _fast.values())>32*1024*1024:
                _fast.pop(next(iter(_fast)))
    try:
        _pool.submit(_job, store, key, token, meta, True, prefetched, True)
    except Exception:
        with _lock:
            _pending.discard(key)
        _slots.release()
        raise
    return prefetched, timing
