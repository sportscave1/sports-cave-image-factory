"""Authenticated browser/native preparation sessions. Preparation never copies."""
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
            # A new product/preparation revokes older pending work for this user.
            for record in self.records.values():
                if str(record['user']['id']) == str(user['id']):
                    record['state'] = 'Cancelled'
            code = secrets.token_urlsafe(32)
            self.records[code] = dict(user=dict(user), key=key, version=version,
                validate=validate, state='Waiting', count=0, error='', secret='', sequence=0,
                heartbeat=time.monotonic(), copy_ms=None, expires=time.monotonic()+840)
            return code

    def get(self, code):
        record = self.records.get(code)
        if not record or record['expires'] <= time.monotonic():
            raise ValueError('File preparation expired. Prepare files again; cached files will be reused.')
        return record

    def claim(self, code):
        with self.lock:
            record = self.get(code)
            if record['state'] != 'Waiting':
                raise ValueError('This preparation was already opened. Retry from Product Uploads.')
            record['validate']()
            record.update(state='Preparing', secret=secrets.token_urlsafe(32), heartbeat=time.monotonic())
            return record

    def active(self, code):
        with self.lock:
            record = self.get(code)
            if record['state'] in ('Cancelled', 'Failed'):
                raise ValueError('This preparation is no longer active. Prepare the current files again.')
            return record['validate']()

    def native(self, code, secret, event, count=0, sequence=0, error='', copy_ms=None):
        with self.lock:
            record = self.get(code)
            if not record['secret'] or not secrets.compare_digest(record['secret'], str(secret)):
                raise PermissionError('Clipboard acknowledgement rejected.')
            self.active(code)
            record['heartbeat'] = time.monotonic()
            if event == 'failed':
                record.update(state='Failed', error=str(error or 'Windows could not prepare all files. Retry.')[:400])
            elif event == 'ready':
                if type(count) is not int or count != 8:
                    raise ValueError('Windows did not verify all eight saved files.')
                if record['state'] == 'Preparing': record.update(state='Ready', count=count)
            elif event == 'complete':
                if sequence != record['sequence'] or record['state'] not in ('Copying', 'Complete'):
                    raise ValueError('This copy is no longer current.')
                if type(count) is not int or count != 8:
                    record.update(state='Failed', error='Windows did not verify all eight clipboard files.')
                else:
                    record.update(state='Complete', count=count, copy_ms=copy_ms)
            elif event not in ('poll', 'heartbeat'):
                raise ValueError('Unknown clipboard event.')
            if event == 'poll' and record['state'] == 'CopyRequested':
                record['state'] = 'Copying'
                return dict(command='copy', sequence=record['sequence'])
            return dict(command='wait', sequence=record['sequence'])

    def status(self, code, user, cancel=False, copy=False):
        with self.lock:
            record = self.get(code)
            if str(record['user']['id']) != str(user['id']):
                raise PermissionError('This preparation belongs to another account.')
            if cancel:
                record.update(state='Cancelled')
            else:
                record['validate']()
                if record['state'] not in ('Waiting', 'Failed', 'Cancelled') and time.monotonic()-record['heartbeat'] > 12:
                    raise ValueError('Windows helper disconnected. Reopen preparation and retry.')
                if copy:
                    if record['state'] not in ('Ready', 'Complete'):
                        raise ValueError('Wait for all files to be ready before copying.')
                    record.update(state='CopyRequested', sequence=record['sequence']+1, copy_ms=None)
            return {k: record[k] for k in ('state', 'count', 'error', 'sequence', 'copy_ms')}


REQUESTS = ClipboardRequests()
