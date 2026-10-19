"""Bounded, one-use browser-to-native handoff for a verified saved package."""
import secrets
import threading
import time


class ClipboardRequests:
    def __init__(self):
        self.lock = threading.RLock()
        self.records = {}

    def create(self, user, key, version, validate):
        validate()
        with self.lock:
            self.records = {k: v for k, v in self.records.items() if v['expires'] > time.monotonic()}
            if len(self.records) >= 200:
                raise ValueError('Clipboard service is busy. Retry shortly.')
            code = secrets.token_urlsafe(32)
            self.records[code] = dict(user=dict(user), key=key, version=version,
                validate=validate, state='Waiting', count=0, error='', secret='', expires=time.monotonic()+240)
            return code

    def get(self, code):
        record = self.records.get(code)
        if not record or record['expires'] <= time.monotonic():
            raise ValueError('Clipboard request expired. Click Copy all WEBP files again.')
        return record

    def claim(self, code):
        with self.lock:
            record = self.get(code)
            if record['state'] != 'Waiting':
                raise ValueError('This clipboard request was already opened. Click Copy all WEBP files again.')
            record['validate']()
            record.update(state='Preparing', secret=secrets.token_urlsafe(32))
            return record

    def active(self, code):
        with self.lock:
            record = self.get(code)
            if record['state'] not in ('Waiting', 'Preparing'):
                raise ValueError('This clipboard request is no longer active.')
            return record['validate']()

    def finish(self, code, secret, count, error=''):
        with self.lock:
            record = self.get(code)
            if not record['secret'] or not secrets.compare_digest(record['secret'], str(secret)):
                raise PermissionError('Clipboard completion rejected.')
            if record['state'] in ('Complete', 'Failed'):
                return
            self.active(code)
            if error or type(count) is not int or count != 8:
                record.update(state='Failed', error=str(error or 'Windows did not copy all eight files.')[:400])
            else:
                record.update(state='Complete', count=8)

    def status(self, code, user, cancel=False):
        with self.lock:
            record = self.get(code)
            if str(record['user']['id']) != str(user['id']):
                raise PermissionError('This clipboard request belongs to another account.')
            if cancel:
                record.update(state='Cancelled')
            else:
                record['validate']()
            return {k: record[k] for k in ('state', 'count', 'error')}


REQUESTS = ClipboardRequests()
