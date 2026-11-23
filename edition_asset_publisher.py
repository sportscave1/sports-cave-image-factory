"""Bounded, immutable Dropbox publishing for already validated edition assets."""
from pathlib import Path
import hashlib
import threading
import time

import requests

import auto_editions as ae


class ImmutableAssetUploader:
    CHUNK = 8 * 1024 * 1024
    MAX_BYTES = 128 * 1024 * 1024
    ATTEMPTS = 3

    def __init__(self, integration, token):
        self.api, self.token = integration, token
        self.sdk = integration._dropbox_sdk()
        # Positive limits are deliberate: SDK clone treats zero as "inherit".
        # Default SDK rate-limit retries are unlimited. Preserve the rooted
        # client's auth, namespace and pooled session, but bound its retries.
        self.client = integration.team_space_client(token).clone(
            max_retries_on_error=1, max_retries_on_rate_limit=1, timeout=60)
        self.lock = threading.Lock()
        self.resume_at = 0.0
        self.metrics = dict(provider_calls=0, reconciliation_reads=0,
                            recovered_assets=0, retry_cycles=0, rate_limits=0)

    def _count(self, key):
        with self.lock:
            self.metrics[key] += 1

    def _wait(self):
        while True:
            with self.lock:
                delay = self.resume_at - time.monotonic()
            if delay <= 0:
                return
            time.sleep(delay)

    def _cooldown(self, delay):
        with self.lock:
            self.resume_at = max(self.resume_at, time.monotonic() + delay)

    def _call(self, method, *args, **kwargs):
        self._wait()
        self._count('provider_calls')
        return method(*args, **kwargs)

    def _transient(self, error):
        detail = getattr(error, 'error', None)
        # An SDK retry of a committed finish can report a closed/missing
        # session instead of the original lost acknowledgement. Reconcile it.
        session = (detail.get_lookup_failed() if detail and
                   getattr(detail, 'is_lookup_failed', lambda: False)() else None)
        return (bool(session and (getattr(session, 'is_closed', lambda: False)()
                                  or getattr(session, 'is_not_found', lambda: False)()))
                or bool(detail and getattr(detail, 'is_too_many_write_operations', lambda: False)())
                or isinstance(error, (requests.ConnectionError, requests.Timeout,
                                   self.sdk.exceptions.RateLimitError))
                or isinstance(error, self.sdk.exceptions.HttpError)
                and (error.status_code in (408, 429) or error.status_code >= 500))

    @staticmethod
    def _conflict(error):
        detail = getattr(error, 'error', None)
        if not detail or not getattr(detail, 'is_path', lambda: False)():
            return False
        path_error = detail.get_path()
        # /files/upload wraps WriteError in UploadWriteFailed; session finish
        # returns WriteError directly.
        reason = getattr(path_error, 'reason', path_error)
        return bool(getattr(reason, 'is_conflict', lambda: False)())

    @staticmethod
    def _verified(metadata, destination, size, digest):
        remote_path = (metadata or {}).get('path_lower') or (metadata or {}).get('path_display')
        if (not metadata or not metadata.get('id') or not metadata.get('rev')
                or metadata.get('size') != size or metadata.get('content_hash') != digest
                or not remote_path or remote_path.lower() != destination.lower()):
            raise ValueError('Existing or uploaded asset differs; it was not overwritten.')
        return metadata

    def _upload(self, destination, path, size, digest):
        files = self.sdk.files
        with path.open('rb') as stream:
            blocks = hashlib.sha256()
            def read():
                expected = min(self.CHUNK, size - stream.tell())
                data = stream.read(expected)
                if len(data) != expected:
                    raise ValueError('Prepared asset changed during publication.')
                for offset in range(0, len(data), 4 * 1024 * 1024):
                    blocks.update(hashlib.sha256(data[offset:offset+4*1024*1024]).digest())
                if stream.tell() == size and (stream.read(1) or blocks.hexdigest() != digest):
                    raise ValueError('Prepared asset changed during publication.')
                return data
            if size <= self.CHUNK:
                result = self._call(self.client.files_upload, read(), destination,
                                    mode=files.WriteMode.add, autorename=False,
                                    strict_conflict=True, mute=False, content_hash=digest)
            else:
                session = self._call(self.client.files_upload_session_start, read())
                cursor = files.UploadSessionCursor(session.session_id, stream.tell())
                while size - stream.tell() > self.CHUNK:
                    self._call(self.client.files_upload_session_append_v2,
                               read(), cursor)
                    cursor.offset = stream.tell()
                commit = files.CommitInfo(path=destination, mode=files.WriteMode.add,
                                          autorename=False, strict_conflict=True, mute=False)
                result = self._call(self.client.files_upload_session_finish,
                                    read(), cursor, commit)
        return self.api._metadata_to_dict(result)

    def _receipt(self, destination):
        self._count('reconciliation_reads')
        try:
            result = self._call(self.client.files_get_metadata, destination)
        except self.sdk.exceptions.ApiError as error:
            detail = error.error
            if (getattr(detail, 'is_path', lambda: False)()
                    and getattr(detail.get_path(), 'is_not_found', lambda: False)()):
                return None
            raise
        return self.api._metadata_to_dict(result)

    def __call__(self, destination, local_path):
        path = Path(local_path)
        destination = self.api.normalize_dropbox_path(destination)
        size = path.stat().st_size
        if not 0 < size <= self.MAX_BYTES:
            raise ValueError('Prepared asset exceeds the transfer limit.')
        digest = ae.file_hash(path, dropbox=True)
        for attempt in range(self.ATTEMPTS):
            try:
                result = self._upload(destination, path, size, digest)
            except Exception as error:
                transient = self._transient(error)
                if not transient and not self._conflict(error):
                    raise
                if isinstance(error, self.sdk.exceptions.RateLimitError):
                    self._count('rate_limits')
                    # Share the provider's Retry-After across all three workers.
                    self._cooldown(max(1.0, float(error.backoff if error.backoff is not None else 5)))
                elif getattr(getattr(error, 'error', None), 'is_too_many_write_operations', lambda: False)():
                    self._count('rate_limits')
                    self._cooldown(5)
                else:
                    self._cooldown(2 ** attempt if transient else 0)
                self._wait()
                result = self._receipt(destination)
                if result:
                    self._count('recovered_assets')
                    return self._verified(result, destination, size, digest)
                if not transient or attempt == self.ATTEMPTS - 1:
                    raise
                self._count('retry_cycles')
                continue
            return self._verified(result, destination, size, digest)
