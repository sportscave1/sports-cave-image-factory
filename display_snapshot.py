"""Bounded nonblocking display reads. Never use a snapshot to authorise writes.

Each lane has a fixed worker budget and no queued backlog. A slow refresh keeps
the last successful value visible; failures are not mistaken for empty data.
Loaders must not access Streamlit session state or mutate external systems.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import BoundedSemaphore, Event, Lock
from time import monotonic, time
import logging


class Snapshots:
    def __init__(self, *, workers=2, limit=64, ttl=30, retry=5, max_age=900,
                 byte_limit=4_000_000, clock=monotonic):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='display-read')
        self.slots = BoundedSemaphore(workers)
        self.lock = Lock()
        self.rows = OrderedDict()
        self.limit, self.ttl, self.retry = limit, ttl, retry
        self.max_age, self.byte_limit, self.clock = max_age, byte_limit, clock

    def read(self, key, loader):
        with self.lock:
            now = self.clock()
            row = self.rows.get(key)
            if row is None:
                if len(self.rows) >= self.limit:
                    victim = next((k for k, v in self.rows.items() if not v['loading']), None)
                    if victim is None:
                        return dict(value=None, state='busy', checked_at=None)
                    del self.rows[victim]
                row = dict(value=None, loading=False, due=0, saved=0, checked_at=None, failed=False,
                           finished=Event())
                self.rows[key] = row
            self.rows.move_to_end(key)
            if now >= row['due'] and not row['loading'] and self.slots.acquire(blocking=False):
                row['loading'] = True
                row['finished'].clear()
                self.pool.submit(self._refresh, key, row, loader)
            value = row['value'] if now - row['saved'] <= self.max_age else None
            if value is not None:
                state = 'stale' if row['loading'] or row['failed'] or now >= row['due'] else 'ready'
            else:
                state = 'unavailable' if row['failed'] and not row['loading'] else 'loading'
            return dict(value=deepcopy(value), state=state, checked_at=row['checked_at'])

    def wait(self, key, timeout):
        """Wait for a specific display read without holding the cache lock.

        This never starts work or reads data. Callers recheck their route/scope
        and read the current entry afterwards, including after invalidation.
        """
        with self.lock:
            row = self.rows.get(key)
            finished = row['finished'] if row is not None else None
        return finished.wait(timeout) if finished is not None else False

    def _refresh(self, key, row, loader):
        try:
            value = loader()
            import json
            size = len(json.dumps(value, default=str).encode('utf-8'))
            if size > self.byte_limit // self.limit:
                raise ValueError('Display snapshot exceeds its size budget')
            value = deepcopy(value)
            with self.lock:
                row.update(value=value, saved=self.clock(), checked_at=time(), failed=False,
                           due=self.clock() + self.ttl)
        except Exception as error:
            logging.getLogger(__name__).warning('display_snapshot_refresh_failed type=%s', type(error).__name__)
            with self.lock:
                row.update(failed=True, due=self.clock() + self.retry)
        finally:
            with self.lock:
                row['loading'] = False
                row['finished'].set()
            self.slots.release()

    def invalidate(self, key):
        with self.lock:
            self.rows.pop(key, None)

    def invalidate_matching(self, predicate):
        with self.lock:
            for key in list(self.rows):
                if predicate(key):
                    del self.rows[key]

    def close(self):
        self.pool.shutdown(wait=True)
