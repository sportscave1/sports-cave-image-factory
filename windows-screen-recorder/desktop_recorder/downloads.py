"""Run-local completion gate. Requires a correlated browser download receipt.

No directory guessing, latest-file lookup, network requests or persisted paths.
This is not advertised as a playable action until the browser event transport
and Save As capture have passed integration acceptance.
"""
from pathlib import Path
from threading import Condition
from time import monotonic
from uuid import uuid4
import hashlib


class DownloadError(ValueError):
    pass


class Download:
    def __init__(self, root, source_url, *, timeout=30):
        if not 0 < timeout <= 300:
            raise DownloadError('Invalid download deadline.')
        self.root=Path(root).resolve(strict=True)
        if not self.root.is_dir():raise DownloadError('Download destination is not a directory.')
        self.source_url=source_url
        self.nonce=str(uuid4())
        self.deadline=monotonic()+timeout
        self.condition=Condition()
        self.existing={p.resolve() for p in self.root.rglob('*') if p.is_file()}
        self.existing_ids={(p.stat().st_dev,p.stat().st_ino) for p in self.existing}
        self.download_id=None
        self.result=None
        self.failure=None

    def created(self, nonce, download_id, source_url):
        with self.condition:
            if nonce!=self.nonce or source_url!=self.source_url or self.download_id is not None or self.failure:
                raise DownloadError('Download creation could not be associated uniquely with this action.')
            if not isinstance(download_id,str) or not download_id or len(download_id)>180:
                raise DownloadError('Invalid download identifier.')
            self.download_id=download_id

    def cancel(self):
        with self.condition:
            self.failure='Download cancelled; no file reference retained.'
            self.result=None
            self.condition.notify_all()

    def completed(self, nonce, download_id, final_path, total_bytes):
        with self.condition:
            if (self.failure or self.result or monotonic()>=self.deadline or nonce!=self.nonce or
                self.download_id is None or download_id!=self.download_id):
                raise DownloadError('Stale, cancelled or unrelated download completion.')
            path=Path(final_path).resolve(strict=True)
            if (not path.is_relative_to(self.root) or path in self.existing or not path.is_file() or
                path.suffix.lower() in {'.crdownload','.part','.tmp'}):
                raise DownloadError('Download is not a new completed file in the approved destination.')
            before=path.stat()
            if (before.st_dev,before.st_ino) in self.existing_ids:
                raise DownloadError('An older file was renamed or linked; it is not this download.')
            if type(total_bytes) is not int or total_bytes<0 or before.st_size!=total_bytes:
                raise DownloadError('Download size does not match its completion receipt.')
            digest=hashlib.sha256()
            with path.open('rb') as handle:
                for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
            after=path.stat()
            if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
                raise DownloadError('Download changed during verification.')
            self.result=(path,after.st_size,digest.hexdigest())
            self.condition.notify_all()

    def wait(self):
        with self.condition:
            while self.result is None and self.failure is None:
                remaining=self.deadline-monotonic()
                if remaining<=0:
                    self.failure='Download completion deadline exceeded; no older file substituted.'
                    break
                self.condition.wait(remaining)
            if self.failure:raise DownloadError(self.failure)
            return self.result
