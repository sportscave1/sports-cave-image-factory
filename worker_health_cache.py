"""Bounded, stale-while-refresh Editions display index. Never authorises actions."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Condition, Lock, BoundedSemaphore
import hashlib
import json
import logging
import sqlite3
import time

FILTERS = ('All', 'Active', 'Queued', 'Failed', 'Needs Review', 'Completed')
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='editions-display')
_capacity = BoundedSemaphore(2)

class DisplayIndex:
    def __init__(self, value):
        jobs = value['jobs']
        if len(jobs) > 10000:
            raise ValueError('Display backlog exceeds 10000 jobs; status unavailable rather than truncated.')
        self.summary = deepcopy({k:v for k,v in value.items() if k != 'jobs'})
        self.filters = {name: 0 for name in FILTERS}
        rows = []
        size = 0
        for rank, job in enumerate(jobs):
            version = hashlib.sha256(json.dumps(job, sort_keys=True, default=str).encode()).hexdigest()[:20]
            payload = json.dumps(dict(job, version=version), default=str)
            size += len(payload.encode())
            if size > 16000000:
                raise ValueError('Display index exceeds memory budget')
            rows.append((job['id'], job['category'], rank, payload, version))
            self.filters['All'] += 1
            self.filters[job['category']] += 1
        self.lock = Lock()
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY, category TEXT, rank INTEGER, payload TEXT, version TEXT)')
        self.db.executemany('INSERT INTO jobs VALUES(?,?,?,?,?)', rows)
        self.db.execute('CREATE INDEX category_id ON jobs(category,id)')
        self.db.execute('CREATE INDEX job_rank ON jobs(rank)')
        self.db.commit()
        self.bytes = size

    def __del__(self):
        # Readers hold this index by reference, so disposal cannot close an
        # index still in use after an atomic refresh swaps in its replacement.
        try:
            if hasattr(self, 'db'): self.db.close()
        except Exception:
            pass

    def select(self, category='All', cursor='', limit=50, offset=0, ranked=False):
        where, args = ('id > ?', [cursor]) if category == 'All' else ('category = ? AND id > ?', [category, cursor])
        with self.lock:
            rows = self.db.execute('SELECT payload FROM jobs WHERE '+where+' ORDER BY '+('rank' if ranked else 'id')+' LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def changes(self, category, known, scanned_to):
        # One indexed join against a bounded client version set, not a full payload scan.
        with self.lock:
            self.db.execute('CREATE TEMP TABLE IF NOT EXISTS known(id TEXT PRIMARY KEY, version TEXT)')
            self.db.execute('DELETE FROM known')
            self.db.executemany('INSERT INTO known VALUES(?,?)', known.items())
            condition, args = ('1=1', ()) if category == 'All' else ('j.category=?', (category,))
            changed = self.db.execute('SELECT j.payload FROM jobs j JOIN known k ON k.id=j.id WHERE '+condition+' AND j.version<>k.version ORDER BY j.id LIMIT 50', args).fetchall()
            arrivals = self.db.execute('SELECT j.payload FROM jobs j LEFT JOIN known k ON k.id=j.id WHERE '+condition+' AND k.id IS NULL AND (? OR j.id<=?) ORDER BY j.id LIMIT 50', (*args, scanned_to=='end', scanned_to)).fetchall()
            removed = self.db.execute('SELECT k.id FROM known k LEFT JOIN jobs j ON k.id=j.id AND '+condition+' WHERE j.id IS NULL', args).fetchall()
        return [json.loads(r[0]) for r in (changed+arrivals)[:50]], [r[0] for r in removed]

class Snapshot:
    def __init__(self, ttl=5, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self.condition = Condition()
        self.value = None
        self.expires = self.saved = self.checked_at = 0
        self.loading = False
        self.generation = self.failures = 0

    def invalidate(self):
        with self.condition:
            self.generation += 1
            self.expires = 0
            # Last good data remains visibly stale until the next verified read.
            self.condition.notify_all()

    def _refresh(self, loader, generation):
        started = time.monotonic()
        try:
            value = DisplayIndex(loader())
            logging.getLogger(__name__).info("companion_display_refresh rows=%s bytes=%s duration_ms=%.1f", value.filters["All"], value.bytes, (time.monotonic()-started)*1000)
            with self.condition:
                if generation == self.generation:
                    self.value = value
                    self.saved = self.clock()
                    self.checked_at = time.time()
                    self.expires = self.saved + self.ttl
                    self.failures = 0
        except Exception as error:
            logging.getLogger(__name__).warning("companion_display_refresh_failed type=%s duration_ms=%.1f", type(error).__name__, (time.monotonic()-started)*1000)
            with self.condition:
                self.failures += 1
                self.expires = self.clock() + min(30, 2 ** min(self.failures, 5))
        finally:
            with self.condition:
                self.loading = False
                self.condition.notify_all()
            _capacity.release()

    def read_index(self, loader):
        with self.condition:
            if self.clock() >= self.expires and not self.loading and _capacity.acquire(False):
                self.loading = True
                _pool.submit(self._refresh, loader, self.generation)
            if self.value is None and self.loading:
                self.condition.wait_for(lambda: not self.loading, timeout=.05)
            if self.value is None or self.clock()-self.saved > 120:
                raise TimeoutError('Status is refreshing. Last verified data is not yet available.')
            meta = dict(state='stale' if self.loading or self.failures or self.clock() >= self.expires else 'ready',
                        checked_at=self.checked_at, age_seconds=round(self.clock()-self.saved, 1))
            return self.value, meta

    def read(self, loader):
        index, freshness = self.read_index(loader)
        return summary(index, freshness) | {'jobs': index.select(limit=10000, ranked=True)}


def summary(index, freshness):
    result = deepcopy(index.summary)
    result['filters'] = dict(index.filters)
    result['freshness'] = freshness
    cost = result.get('cost', {})
    result['cost'] = {**cost, 'snapshot_queries':cost.get('queries', 0), 'queries':0,
                      'cached':True, 'index_bytes':index.bytes}
    return result

_lock = Lock()
_slots = OrderedDict()
def slot(connect):
    with _lock:
        if connect not in _slots:
            if len(_slots) >= 8:
                victim = next((key for key,value in _slots.items() if not value.loading), None)
                if victim is None: raise TimeoutError('Display refresh capacity is busy')
                del _slots[victim]
            _slots[connect] = Snapshot()
        _slots.move_to_end(connect)
        return _slots[connect]

def index(service): return slot(service.connect).read_index(service.snapshot)
def snapshot(service): return slot(service.connect).read(service.snapshot)
def invalidate(connect): slot(connect).invalidate()
